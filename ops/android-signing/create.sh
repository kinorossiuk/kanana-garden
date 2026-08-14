#!/usr/bin/env bash
set -euo pipefail
umask 077

for command_name in openssl base64; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Missing required command: $command_name" >&2
    exit 1
  fi
done

config_root="${XDG_CONFIG_HOME:-$HOME/.config}"
signing_dir="$config_root/kanana-garden/signing"
keystore_file="$signing_dir/kanana-bridge-release.p12"
password_file="$signing_dir/android-signing-password"
base64_file="$signing_dir/android-signing-key.base64"

mkdir -p "$signing_dir"
chmod 700 "$signing_dir"
for target_file in "$keystore_file" "$password_file" "$base64_file"; do
  if [[ -e "$target_file" ]]; then
    echo "Refusing to overwrite existing signing material: $target_file" >&2
    exit 1
  fi
done

temporary_dir="$(mktemp -d)"
private_key="$temporary_dir/private-key.pem"
certificate="$temporary_dir/certificate.pem"
cleanup() {
  rm -f "$private_key" "$certificate"
  rmdir "$temporary_dir" 2>/dev/null || true
}
trap cleanup EXIT

openssl rand -hex 32 > "$password_file"
openssl req -x509 -newkey rsa:4096 -sha256 -days 10950 \
  -keyout "$private_key" \
  -out "$certificate" \
  -passout "file:$password_file" \
  -subj "/CN=Kanana Garden/OU=Release/O=Personal/C=KR"
openssl pkcs12 -export \
  -out "$keystore_file" \
  -inkey "$private_key" \
  -in "$certificate" \
  -name kanana-bridge \
  -passin "file:$password_file" \
  -passout "file:$password_file"
base64 -w 0 "$keystore_file" > "$base64_file"

chmod 600 "$keystore_file" "$password_file" "$base64_file"

echo "Android OTA signing material was created."
echo "GitHub secret ANDROID_SIGNING_KEY_BASE64: $base64_file"
echo "GitHub secret ANDROID_SIGNING_PASSWORD: $password_file"
echo "Keep the entire directory backed up offline: $signing_dir"
