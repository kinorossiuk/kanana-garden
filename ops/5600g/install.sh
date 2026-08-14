#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd -- "$script_dir/../.." && pwd)"

python3 -m venv "$repo_dir/.venv"
"$repo_dir/.venv/bin/python" -m pip install --upgrade pip
"$repo_dir/.venv/bin/python" -m pip install -e "$repo_dir[server]"

config_dir="$HOME/.config/kanana-garden"
mkdir -p "$config_dir"
if [[ ! -e "$config_dir/server.env" ]]; then
  sed "s|KANANA_REPO_DIR=/home/USER/kanana|KANANA_REPO_DIR=$repo_dir|" \
    "$script_dir/server.env.example" > "$config_dir/server.env"
  echo "Created $config_dir/server.env; set KANANA_API_KEY and HF_HOME."
fi
if [[ ! -e "$config_dir/report-receiver.env" ]]; then
  sed "s|/home/USER/kanana|$repo_dir|g" \
    "$script_dir/report-receiver.env.example" > "$config_dir/report-receiver.env"
  chmod 600 "$config_dir/report-receiver.env"
  echo "Created $config_dir/report-receiver.env; generate KANANA_REPORT_TOKEN before starting it."
fi

user_unit_dir="$HOME/.config/systemd/user"
mkdir -p "$user_unit_dir"
install -m 0644 "$script_dir/kanana-garden.service" \
  "$user_unit_dir/kanana-garden.service"
install -m 0644 "$script_dir/kanana-report-receiver.service" \
  "$user_unit_dir/kanana-report-receiver.service"
if command -v systemctl >/dev/null 2>&1; then
  systemctl --user daemon-reload || \
    echo "systemd user bus is unavailable; run systemctl --user daemon-reload later."
fi

echo "Installed the 5600G model server environment."
echo "Start: $repo_dir/ops/5600g/run.sh"
echo "LTE report receiver: edit $config_dir/report-receiver.env, then run:"
echo "  systemctl --user enable --now kanana-report-receiver"
