#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd -- "$script_dir/../.." && pwd)"
server_env="${KANANA_SERVER_ENV:-$HOME/.config/kanana-garden/server.env}"

if [[ -f "$server_env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$server_env"
  set +a
fi

server_host="${KANANA_SERVER_HOST:-127.0.0.1}"
server_port="${KANANA_SERVER_PORT:-8000}"
server_threads="${KANANA_SERVER_THREADS:-6}"
server_dtype="${KANANA_SERVER_DTYPE:-float32}"
max_input_tokens="${KANANA_MAX_INPUT_TOKENS:-2048}"
max_output_tokens="${KANANA_MAX_OUTPUT_TOKENS:-512}"

if [[ "$server_host" != "127.0.0.1" && "$server_host" != "localhost" && -z "${KANANA_API_KEY:-}" ]]; then
  echo "KANANA_API_KEY is required when binding outside loopback." >&2
  exit 2
fi
if [[ ! -x "$repo_dir/.venv/bin/kanana-garden" ]]; then
  echo "Missing $repo_dir/.venv. Run ops/5600g/install.sh first." >&2
  exit 2
fi

exec "$repo_dir/.venv/bin/kanana-garden" serve-local \
  --host "$server_host" \
  --port "$server_port" \
  --threads "$server_threads" \
  --dtype "$server_dtype" \
  --max-input-tokens "$max_input_tokens" \
  --max-output-tokens "$max_output_tokens" \
  --api-key "${KANANA_API_KEY:-}"
