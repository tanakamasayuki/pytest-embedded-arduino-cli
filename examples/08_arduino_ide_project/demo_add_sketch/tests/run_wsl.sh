#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f .env ]; then
  ENV="--env-file .env"
else
  ENV=""
fi

uv run ${ENV} pytest --run-mode=build "$@"

set -a
[ -f .env ] && source .env
set +a

WIN_DIR=$(wslpath -w "$SCRIPT_DIR")

CMD=""
CMD+="pushd ${WIN_DIR}"
if [ -n "$UV_PROJECT_ENVIRONMENT_WIN" ]; then
  CMD+="&&set UV_PROJECT_ENVIRONMENT=${UV_PROJECT_ENVIRONMENT_WIN}"
fi
CMD+="&&uv run ${ENV} pytest --run-mode=test"

cmd.exe /C "${CMD}" "$@"
