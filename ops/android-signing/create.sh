#!/usr/bin/env bash
set -euo pipefail
umask 077

for command_name in openssl base64 rg; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Missing required command: $command_name" >&2
    exit 1
  fi
done

config_root="${XDG_CONFIG_HOME:-$HOME/.config}"
signing_dir="${KANANA_SIGNING_DIR:-$config_root/kanana-garden/signing}"
keystore_file="$signing_dir/kanana-bridge-release.p12"
password_file="$signing_dir/android-signing-password"
base64_file="$signing_dir/android-signing-key.base64"

write_base64() {
  base64 -w 0 "$keystore_file" > "$base64_file"
  printf '\n' >> "$base64_file"
}

mkdir -p "$signing_dir"
chmod 700 "$signing_dir"

if [[ -e "$base64_file" && ! -e "$keystore_file" ]]; then
  echo "Base64 data exists without its keystore: $base64_file" >&2
  exit 1
fi
if [[ -e "$password_file" ]]; then
  if [[ ! -f "$password_file" ]] || ! rg -q '^[0-9a-f]{64}$' "$password_file"; then
    echo "Existing signing password file has an unexpected format: $password_file" >&2
    exit 1
  fi
else
  openssl rand -hex 32 > "$password_file"
fi

if [[ -e "$keystore_file" ]]; then
  openssl pkcs12 -in "$keystore_file" -passin "file:$password_file" -noout
  write_base64
  chmod 600 "$keystore_file" "$password_file" "$base64_file"
  echo "Existing Android OTA signing material is valid."
  echo "GitHub secret ANDROID_SIGNING_KEY_BASE64: $base64_file"
  echo "GitHub secret ANDROID_SIGNING_PASSWORD: $password_file"
  exit 0
fi

temporary_dir="$(mktemp -d)"
private_key="$temporary_dir/private-key.pem"
certificate="$temporary_dir/certificate.pem"
output_password="$temporary_dir/output-password"
temporary_keystore="$temporary_dir/kanana-bridge-release.p12"
cleanup() {
  rm -f "$private_key" "$certificate" "$output_password" "$temporary_keystore"
  rmdir "$temporary_dir" 2>/dev/null || true
}
trap cleanup EXIT

cp "$password_file" "$output_password"
openssl req -x509 -newkey rsa:4096 -sha256 -days 10950 \
  -keyout "$private_key" \
  -out "$certificate" \
  -passout "file:$password_file" \
  -subj "/CN=Kanana Garden/OU=Release/O=Personal/C=KR"
openssl pkcs12 -export \
  -out "$temporary_keystore" \
  -inkey "$private_key" \
  -in "$certificate" \
  -name kanana-bridge \
  -passin "file:$password_file" \
  -passout "file:$output_password"
openssl pkcs12 -in "$temporary_keystore" -passin "file:$password_file" -noout
install -m 0600 "$temporary_keystore" "$keystore_file"
write_base64

chmod 600 "$keystore_file" "$password_file" "$base64_file"

echo "Android OTA signing material was created."
echo "GitHub secret ANDROID_SIGNING_KEY_BASE64: $base64_file"
echo "GitHub secret ANDROID_SIGNING_PASSWORD: $password_file"
echo "Keep the entire directory backed up offline: $signing_dir"
