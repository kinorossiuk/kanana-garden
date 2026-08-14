#!/usr/bin/env bash
set -euo pipefail
umask 077

config_root="${XDG_CONFIG_HOME:-$HOME/.config}"
secret_dir="$config_root/kanana-garden/secrets"
token_file="$secret_dir/duckdns-token"

install -d -m 0700 "$secret_dir"
read -r -s -p "새 DuckDNS 토큰을 붙여넣고 Enter: " new_token
printf '\n'

if [[ ! "$new_token" =~ ^[A-Za-z0-9-]{20,128}$ ]]; then
  unset new_token
  echo "DuckDNS 토큰 형식이 올바르지 않습니다." >&2
  exit 1
fi

temporary_file="$(mktemp "$secret_dir/.duckdns-token.XXXXXX")"
cleanup() {
  rm -f "$temporary_file"
}
trap cleanup EXIT
printf '%s' "$new_token" > "$temporary_file"
unset new_token
chmod 0600 "$temporary_file"
mv -f "$temporary_file" "$token_file"
trap - EXIT

echo "DuckDNS 토큰을 보호 파일에 저장했습니다: $token_file"
echo "시스템 반영: sudo ./ops/report-host/apply-duckdns-config.sh"
