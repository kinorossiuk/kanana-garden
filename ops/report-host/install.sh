#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd -- "$script_dir/../.." && pwd)"

if [[ ! -x "$repo_dir/.venv/bin/python" ]]; then
  python3 -m venv "$repo_dir/.venv"
fi
"$repo_dir/.venv/bin/python" -m pip install -e "$repo_dir"

config_dir="$HOME/.config/kanana-garden"
mkdir -p "$config_dir"
if [[ ! -e "$config_dir/report-receiver.env" ]]; then
  sed "s|/home/USER/kanana|$repo_dir|g" \
    "$script_dir/report-receiver.env.example" > "$config_dir/report-receiver.env"
  chmod 600 "$config_dir/report-receiver.env"
  echo "Created $config_dir/report-receiver.env."
  echo "Replace KANANA_REPORT_TOKEN before starting the receiver."
fi

user_unit_dir="$HOME/.config/systemd/user"
mkdir -p "$user_unit_dir"
install -m 0644 "$script_dir/kanana-report-receiver.service" \
  "$user_unit_dir/kanana-report-receiver.service"
if command -v systemctl >/dev/null 2>&1; then
  systemctl --user daemon-reload || \
    echo "systemd user bus is unavailable; run systemctl --user daemon-reload later."
fi

echo "Installed the UIS7862S report receiver on this analysis host."
echo "Edit: $config_dir/report-receiver.env"
echo "Start: systemctl --user enable --now kanana-report-receiver"
