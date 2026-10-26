"""Collection-time profile selection and applicability checks (no hardware I/O)."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import inspect
from itertools import product
from pathlib import Path
from types import MappingProxyType
from typing import Mapping
from urllib.parse import quote, unquote

import pytest
import yaml

from .app import find_sketch_yaml, load_sketch_yaml, resolve_profile_name, resolve_sketch_dir


@dataclass(frozen=True)
class ArduinoCombination:
    """Read-only profiles for one test. ``None`` denotes an unresolved profile."""

    primary: str | None
    peers: Mapping[str, str | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "peers", MappingProxyType(dict(sorted(self.peers.items()))))

    @property
    def id(self) -> str:
        def encode(value: str | None) -> str:
            return quote(value, safe="") if value is not None else "<unresolved>"

        return ",".join(
            [f"primary={encode(self.primary)}"]
            + [f"{quote(name, safe='')}={encode(value)}" for name, value in self.peers.items()]
        )


@dataclass(frozen=True)
class ExecutionPlan:
    combination: ArduinoCombination
    multiple_roles: frozenset[str]
    skip_reasons: tuple[str, ...] = ()
    supported: bool = True
    label: str | None = None

    @property
    def id(self) -> str:
        return self.label or self.combination.id


@dataclass(frozen=True)
class Combo:
    """One ``--combo`` entry: profiles by role (``primary`` / ``peer:<name>``)."""

    label: str
    roles: tuple[tuple[str, str], ...]
    explicit: bool


class Hooks:
    @pytest.hookspec
    def pytest_arduino_cli_skip_reason(self, item, combination):
        """Return a nonempty skip reason or None, without fixtures or hardware I/O.

        Called during collection for each selected item through its scoped hooks.
        ``combination`` is None for ordinary Python tests. All reasons accumulate.
        """


_PLAN_CACHE = pytest.StashKey[dict]()
_KNOWN = pytest.StashKey[dict[str, set[str]]]()
_OPTIONS = pytest.StashKey[tuple]()
_COMBOS = pytest.StashKey["tuple[Combo, ...] | None"]()
_APPLIED = pytest.StashKey[set[str]]()
COMBINATION = pytest.StashKey[ArduinoCombination | None]()
PLAN = pytest.StashKey[ExecutionPlan]()
PLANNED = pytest.StashKey[list[str]]()
RULE_REASONS = pytest.StashKey[tuple[str, ...]]()


def enabled(config) -> bool:
    option = getattr(config, "option", None)
    return bool(getattr(option, "profiles", None) or getattr(option, "peer_profiles", None)
                or getattr(option, "combos", None))


def _parse_combo(spec: str, origin: str) -> tuple[tuple[str, str], ...]:
    roles = {}
    for part in spec.split(","):
        name, sep, value = (unquote(text.strip()) for text in part.partition("="))
        if not sep or not name or not value or name in roles:
            raise pytest.UsageError(f"{origin}: expected primary=PROFILE[,PEER=PROFILE...]: {spec!r}")
        roles[name] = value
    if "primary" not in roles:
        raise pytest.UsageError(f"{origin}: primary=PROFILE is required: {spec!r}")
    return tuple(("primary" if name == "primary" else f"peer:{name}", value) for name, value in roles.items())


def _defined_combos(config) -> dict[str, tuple[tuple[str, str], ...]]:
    defined = {}
    for line in config.getini("arduino_combos"):
        name, sep, spec = line.partition(":")
        name = name.strip()
        if not sep or not name or "=" in name or "," in name or name == "all" or name in defined:
            raise pytest.UsageError(f"arduino_combos: expected unique 'NAME: primary=PROFILE,...' lines: {line!r}")
        defined[name] = _parse_combo(spec.strip(), f"arduino_combos {name}")
    return defined


def _combos(config) -> tuple[Combo, ...] | None:
    values = getattr(config.option, "combos", None) or []
    if not values:
        return None
    defined = _defined_combos(config)
    if "all" in values:
        if len(values) != 1:
            raise pytest.UsageError("--combo all cannot be combined with other --combo values")
        if not defined:
            raise pytest.UsageError("--combo all: arduino_combos defines no combinations")
        combos = [Combo(name, roles, False) for name, roles in defined.items()]
    else:
        combos = []
        for value in values:
            if "=" in value:
                roles = _parse_combo(value, "--combo")
            elif value in defined:
                roles = defined[value]
            else:
                known = ", ".join(defined) or "none"
                raise pytest.UsageError(f"--combo: unknown combination name {value!r} (arduino_combos defines: {known})")
            combos.append(Combo(value, roles, True))
    seen = {}
    for combo in combos:
        key = frozenset(combo.roles)
        if key in seen:
            raise pytest.UsageError(f"--combo: {combo.label!r} repeats {seen[key]!r}")
        seen[key] = combo.label
    return tuple(combos)


def _candidates(value: str, option: str) -> tuple[str, ...] | str:
    if value == "all":
        return "all"
    names = tuple(name.strip() for name in value.split(","))
    if not all(names) or len(set(names)) != len(names) or "all" in names:
        raise pytest.UsageError(f"{option}: expected unique profile names or 'all': {value!r}")
    return names


def named_options(values, option: str) -> dict[str, str]:
    result = {}
    for value in values or ():
        name, sep, selection = value.partition(":")
        if not sep or not name or not selection or name in result:
            raise pytest.UsageError(f"{option}: expected unique NAME:VALUE entries: {value!r}")
        result[name] = selection
    return result


def configure(config) -> None:
    config.addinivalue_line(
        "markers", "arduino_skip_if(predicate, reason): collection-time predicate(item, combination) returning bool"
    )
    primary = getattr(config.option, "profiles", None)
    peers = getattr(config.option, "peer_profiles", [])
    combos = _combos(config)
    if combos is not None:
        conflicts = [option for option, value in (
            ("--profile", config.getoption("profile")), ("--profiles", primary),
            ("--peer-profile", config.getoption("peer_profile")), ("--peer-profiles", peers),
        ) if value]
        if conflicts:
            raise pytest.UsageError(f"--combo cannot be combined with {', '.join(conflicts)}")
    config.stash[_COMBOS] = combos
    config.stash[_APPLIED] = set()
    if primary is not None and config.getoption("profile") is not None:
        raise pytest.UsageError("--profiles and --profile cannot be combined")
    primary = _candidates(primary, "--profiles") if primary is not None else None
    singles = named_options(config.getoption("peer_profile"), "--peer-profile") if enabled(config) else {}
    if "all" in peers:
        if len(peers) != 1 or singles:
            raise pytest.UsageError("--peer-profiles=all cannot be combined with other peer profile selections")
        peer_selections = "all"
    else:
        peer_selections = {
            name: _candidates(value, "--peer-profiles")
            for name, value in named_options(peers, "--peer-profiles").items()
        }
        if singles.keys() & peer_selections.keys():
            raise pytest.UsageError("--peer-profile and --peer-profiles select the same peer")
    config.stash[_OPTIONS] = primary, peer_selections, singles
    config.stash[_PLAN_CACHE] = {}
    config.stash[_KNOWN] = {}
    if enabled(config) and (getattr(config.option, "numprocesses", 0) or getattr(config.option, "dist", "no") != "no"):
        raise pytest.UsageError("profile combinations require sequential pytest execution (no xdist)")


def _profile_candidates(data, selection, explicit, *, peer=False):
    profiles = data.get("profiles") or {}
    if any(not isinstance(name, str) or not isinstance(value, dict) for name, value in profiles.items()):
        raise pytest.UsageError("profile definitions must map string names to mappings")
    default = data.get("default_profile")
    if default is not None and not isinstance(default, str):
        raise pytest.UsageError("default_profile must be a string")
    if selection == "all":
        if not profiles:
            raise pytest.UsageError("cannot select all: sketch.yaml defines no profiles")
        return tuple(sorted(profiles))
    if selection is not None:
        return selection
    # Keep an explicitly requested, unsupported name for a reasoned skip item.
    if explicit is not None:
        return (explicit,)
    if peer:
        return (data.get("default_profile") or None,)
    return (resolve_profile_name(data, None),)


def plans(config, path: Path, uses_peers: bool) -> list[ExecutionPlan]:
    key = (path, uses_peers)
    cache = config.stash[_PLAN_CACHE]
    if key in cache:
        return cache[key]
    primary_selection, peer_selections, singles = config.stash[_OPTIONS]
    combos = config.stash[_COMBOS]
    sketch = resolve_sketch_dir(path)
    data = load_sketch_yaml(find_sketch_yaml(sketch))
    known = config.stash[_KNOWN]
    known.setdefault("primary", set()).update(data.get("profiles") or {})
    definitions = {"primary": data.get("profiles") or {}}
    peer_data = {}
    for directory in sorted(sketch.glob("peer_*")):
        if not directory.is_dir():
            continue
        name = directory.name.removeprefix("peer_")
        if not name:
            raise pytest.UsageError(f"invalid peer directory: {directory}")
        role = f"peer:{name}"
        peer_data[role] = load_sketch_yaml(find_sketch_yaml(resolve_sketch_dir(directory)))
        known.setdefault(role, set()).update(peer_data[role].get("profiles") or {})
        if uses_peers:
            definitions[role] = peer_data[role].get("profiles") or {}
    if combos is not None:
        selections = _combo_selections(config, combos, definitions, peer_data)
    else:
        axes = {"primary": _profile_candidates(data, primary_selection, config.getoption("profile"))}
        for role in definitions:
            if role == "primary":
                continue
            name = role.removeprefix("peer:")
            selection = "all" if peer_selections == "all" else peer_selections.get(name)
            axes[role] = _profile_candidates(peer_data[role], selection, singles.get(name), peer=True)
        selections = [dict(zip(axes, values)) for values in product(*axes.values())]
    multiple = frozenset(role for role in definitions if len({selected[role] for selected in selections}) > 1)
    if "primary" in multiple and (config.getoption("port") or config.getoption("flash_port")):
        raise pytest.UsageError("multiple primary profiles require profile-specific ports; omit --port / --flash-port")
    peer_ports = named_options(config.getoption("peer_port"), "--peer-port")
    if multiple & {f"peer:{name}" for name in peer_ports}:
        raise pytest.UsageError("multiple peer profiles require profile-specific ports; omit --peer-port for that peer")
    result = []
    for selected in selections:
        reasons = tuple(
            f"{role}: profile is not resolved" if value is None
            else f"{role}: profile {value!r} is not defined in sketch.yaml"
            for role, value in selected.items() if value is None or value not in definitions[role]
        )
        supported = all(value is None or value in definitions[role] for role, value in selected.items())
        primary = selected.pop("primary")
        result.append(ExecutionPlan(ArduinoCombination(primary, {role.removeprefix("peer:"): value for role, value in selected.items()}), multiple, reasons, supported))
    if not result:
        profiles = ", ".join(sorted(definitions["primary"])) or "none"
        result.append(ExecutionPlan(
            ArduinoCombination(None), frozenset(),
            (f"no --combo applies to this sketch (primary profiles: {profiles})",), False, "combo=none"))
    cache[key] = result
    return result


def _combo_selections(config, combos, definitions, peer_data) -> list[dict]:
    """Selections from the combos that fit this sketch; unlisted used peers keep their default."""
    applied = config.stash[_APPLIED]
    selections = []
    for combo in combos:
        roles = dict(combo.roles)
        if roles["primary"] not in definitions["primary"]:
            continue
        if any(role in roles and roles[role] not in definitions[role] for role in definitions):
            continue
        applied.add(combo.label)
        selected = {role: roles.get(role) or peer_data[role].get("default_profile") or None for role in definitions}
        selected["primary"] = roles["primary"]
        if selected not in selections:
            selections.append(selected)
    return selections


def validate_selection(config) -> None:
    if not enabled(config):
        return
    primary, peers, singles = config.stash[_OPTIONS]
    combos = config.stash[_COMBOS]
    known = config.stash[_KNOWN]
    if not known:
        raise pytest.UsageError("profile selection matched no Arduino sketches")
    for name in named_options(config.getoption("peer_port"), "--peer-port"):
        if f"peer:{name}" not in known:
            raise pytest.UsageError(f"unknown peer: {name}")
    if combos is not None:
        for combo in combos:
            if not combo.explicit:
                continue
            for role, value in combo.roles:
                if role not in known:
                    raise pytest.UsageError(f"--combo {combo.label}: unknown peer: {role.removeprefix('peer:')}")
                if value not in known[role]:
                    raise pytest.UsageError(f"--combo {combo.label}: {role}: unknown profile: {value}")
            if combo.label not in config.stash[_APPLIED]:
                raise pytest.UsageError(f"--combo {combo.label}: no collected sketch defines all of its profiles")
    else:
        selections = {"primary": primary}
        if peers != "all":
            selections.update({f"peer:{name}": value for name, value in peers.items()})
        selections.update({f"peer:{name}": (value,) for name, value in singles.items()})
        if config.getoption("profile"):
            selections["primary"] = (config.getoption("profile"),)
        for role, selection in selections.items():
            if role not in known:
                raise pytest.UsageError(f"unknown peer: {role}")
            if selection is None or selection == "all":
                continue
            unknown = set(selection) - known[role]
            if unknown:
                raise pytest.UsageError(f"{role}: unknown profiles: {', '.join(sorted(unknown))}")
    if not any(plan.supported for batch in config.stash[_PLAN_CACHE].values() for plan in batch):
        raise pytest.UsageError("no structurally supported Arduino configuration was selected")


def legacy_combination(item) -> ArduinoCombination | None:
    """Describe a legacy item without moving its setup errors into collection."""
    from .app import SketchConfigError

    path = Path(item.path).parent
    if not any(path.glob("*.ino")):
        return None
    primary = item.config.getoption("profile")
    peers = {}
    try:
        data = load_sketch_yaml(find_sketch_yaml(path))
        primary = resolve_profile_name(data, primary)
        if "peers" in getattr(item, "fixturenames", ()):
            singles = named_options(item.config.getoption("peer_profile"), "--peer-profile")
            for directory in sorted(path.glob("peer_*")):
                if directory.is_dir():
                    name = directory.name.removeprefix("peer_")
                    data = load_sketch_yaml(find_sketch_yaml(directory))
                    peers[name] = singles.get(name) or data.get("default_profile")
    except (SketchConfigError, pytest.UsageError, yaml.YAMLError, OSError):
        pass
    return ArduinoCombination(primary, peers)


def _source(function) -> str:
    try:
        return f"{inspect.getsourcefile(function)}:{inspect.getsourcelines(function)[1]}"
    except (OSError, TypeError):
        return getattr(function, "__qualname__", repr(function))


def apply_skip_rules(item, combination) -> None:
    """Evaluate every applicable rule, even after one has requested a skip."""
    reasons = []
    for node, marker in item.iter_markers_with_node("arduino_skip_if"):
        origin = f"arduino_skip_if at {node.nodeid}"
        if len(marker.args) != 1 or set(marker.kwargs) != {"reason"}:
            raise pytest.UsageError(f"{origin}: expected (predicate, reason='...')")
        predicate, = marker.args
        reason = marker.kwargs["reason"]
        if not callable(predicate) or not isinstance(reason, str) or not reason.strip():
            raise pytest.UsageError(f"{origin}: a callable and nonempty reason are required")
        origin += f" ({_source(predicate)})"
        try:
            skip = predicate(item, combination)
            if type(skip) is not bool:
                raise TypeError("predicate must return bool")
        except (Exception, pytest.skip.Exception, pytest.fail.Exception, pytest.xfail.Exception) as exc:
            raise pytest.UsageError(f"{item.nodeid}: {origin}: {type(exc).__name__}: {exc}") from exc
        if skip:
            reasons.append(f"{origin}: {reason}")

    # Use each item's scoped hook caller, not config.hook: sibling conftests
    # must not affect one another. Invoke implementations independently to
    # retain their source with each reason while using pluggy's argument rules.
    implementations = item.ihook.pytest_arduino_cli_skip_reason.get_hookimpls()
    manager = item.config.pluginmanager
    for impl in implementations:
        origin = f"pytest_arduino_cli_skip_reason ({_source(impl.function)})"
        if impl.hookwrapper or impl.wrapper:
            raise pytest.UsageError(f"{origin}: wrappers are not supported for skip rules")
        caller = manager.subset_hook_caller(
            "pytest_arduino_cli_skip_reason",
            remove_plugins=[plugin for _, plugin in manager.list_name_plugin() if plugin is not impl.plugin and plugin is not None],
        )
        try:
            results = caller(item=item, combination=combination)
            for reason in results:
                if not isinstance(reason, str) or not reason.strip():
                    raise TypeError("hook must return a nonempty str or None")
                reasons.append(f"{origin}: {reason}")
        except (Exception, pytest.skip.Exception, pytest.fail.Exception, pytest.xfail.Exception) as exc:
            raise pytest.UsageError(f"{item.nodeid}: {origin}: {type(exc).__name__}: {exc}") from exc
    if reasons:
        item.add_marker(pytest.mark.skip(reason="; ".join(reasons)))
    item.stash[RULE_REASONS] = tuple(reasons)


def artifact_name(nodeid: str) -> str:
    """Safe, stable directory name, including identity beyond the function name."""
    readable = quote(nodeid.split("::")[-1], safe="=,[]-_")[:100]
    return f"{readable}-{hashlib.sha256(nodeid.encode()).hexdigest()[:16]}"
