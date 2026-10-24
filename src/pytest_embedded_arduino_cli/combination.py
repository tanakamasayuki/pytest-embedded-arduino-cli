"""Collection-time profile selection and applicability checks (no hardware I/O)."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import inspect
from itertools import product
from pathlib import Path
from types import MappingProxyType
from typing import Mapping
from urllib.parse import quote

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
COMBINATION = pytest.StashKey[ArduinoCombination | None]()
PLAN = pytest.StashKey[ExecutionPlan]()
PLANNED = pytest.StashKey[list[str]]()
RULE_REASONS = pytest.StashKey[tuple[str, ...]]()


def enabled(config) -> bool:
    option = getattr(config, "option", None)
    return bool(getattr(option, "profiles", None) or getattr(option, "peer_profiles", None))


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
    sketch = resolve_sketch_dir(path)
    data = load_sketch_yaml(find_sketch_yaml(sketch))
    known = config.stash[_KNOWN]
    known.setdefault("primary", set()).update(data.get("profiles") or {})
    axes = {"primary": _profile_candidates(data, primary_selection, config.getoption("profile"))}
    definitions = {"primary": data.get("profiles") or {}}
    for directory in sorted(sketch.glob("peer_*")):
        if not directory.is_dir():
            continue
        name = directory.name.removeprefix("peer_")
        if not name:
            raise pytest.UsageError(f"invalid peer directory: {directory}")
        peer_data = load_sketch_yaml(find_sketch_yaml(resolve_sketch_dir(directory)))
        role = f"peer:{name}"
        known.setdefault(role, set()).update(peer_data.get("profiles") or {})
        if uses_peers:
            selection = "all" if peer_selections == "all" else peer_selections.get(name)
            axes[role] = _profile_candidates(peer_data, selection, singles.get(name), peer=True)
            definitions[role] = peer_data.get("profiles") or {}
    multiple = frozenset(name for name, candidates in axes.items() if len(candidates) > 1)
    if "primary" in multiple and (config.getoption("port") or config.getoption("flash_port")):
        raise pytest.UsageError("multiple primary profiles require profile-specific ports; omit --port / --flash-port")
    peer_ports = named_options(config.getoption("peer_port"), "--peer-port")
    if multiple & {f"peer:{name}" for name in peer_ports}:
        raise pytest.UsageError("multiple peer profiles require profile-specific ports; omit --peer-port for that peer")
    result = []
    for values in product(*axes.values()):
        selected = dict(zip(axes, values))
        reasons = tuple(
            f"{role}: profile is not resolved" if value is None
            else f"{role}: profile {value!r} is not defined in sketch.yaml"
            for role, value in selected.items() if value is None or value not in definitions[role]
        )
        supported = all(value is None or value in definitions[role] for role, value in selected.items())
        primary = selected.pop("primary")
        result.append(ExecutionPlan(ArduinoCombination(primary, {role.removeprefix("peer:"): value for role, value in selected.items()}), multiple, reasons, supported))
    cache[key] = result
    return result


def validate_selection(config) -> None:
    if not enabled(config):
        return
    primary, peers, singles = config.stash[_OPTIONS]
    known = config.stash[_KNOWN]
    if not known:
        raise pytest.UsageError("profile selection matched no Arduino sketches")
    selections = {"primary": primary}
    if peers != "all":
        selections.update({f"peer:{name}": value for name, value in peers.items()})
    selections.update({f"peer:{name}": (value,) for name, value in singles.items()})
    if config.getoption("profile"):
        selections["primary"] = (config.getoption("profile"),)
    for name in named_options(config.getoption("peer_port"), "--peer-port"):
        if f"peer:{name}" not in known:
            raise pytest.UsageError(f"unknown peer: {name}")
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
