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
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
fingerprint_file="$script_dir/../../android/uis7862s-bridge/release-cert-sha256.txt"

if [[ ! -f "$fingerprint_file" ]]; then
  echo "Pinned Android signing certificate fingerprint not found: $fingerprint_file" >&2
  exit 1
fi
expected_signer="$(tr -d '[:space:]:' < "$fingerprint_file" | tr '[:upper:]' '[:lower:]')"
if [[ ! "$expected_signer" =~ ^[0-9a-f]{64}$ ]]; then
  echo "Pinned Android signing certificate fingerprint is invalid." >&2
  exit 1
fi

write_base64() {
  base64 -w 0 "$keystore_file" > "$base64_file"
  printf '\n' >> "$base64_file"
}

if [[ ! -e "$keystore_file" ]]; then
  echo "Pinned Android OTA signing key is missing: $keystore_file" >&2
  echo "Refusing to generate a replacement key; restore the original signing backup." >&2
  exit 1
fi
if [[ ! -f "$keystore_file" ]]; then
  echo "Android OTA signing key is not a regular file: $keystore_file" >&2
  exit 1
fi
if [[ ! -f "$password_file" ]] || ! rg -q '^[0-9a-f]{64}$' "$password_file"; then
  echo "Existing signing password file has an unexpected format: $password_file" >&2
  exit 1
fi

openssl pkcs12 -in "$keystore_file" -passin "file:$password_file" -noout
actual_signer="$({
  openssl pkcs12 -in "$keystore_file" -passin "file:$password_file" \
    -clcerts -nokeys 2>/dev/null |
    openssl x509 -noout -fingerprint -sha256
} | sed -n 's/^[^=]*=//p' | tr -d '[:space:]:' | tr '[:upper:]' '[:lower:]')"
if [[ ! "$actual_signer" =~ ^[0-9a-f]{64}$ ]]; then
  echo "Android OTA signing certificate fingerprint could not be read." >&2
  exit 1
fi
if [[ "$actual_signer" != "$expected_signer" ]]; then
  echo "Android OTA keystore does not match the pinned release certificate." >&2
  echo "Expected: $expected_signer" >&2
  echo "Actual:   $actual_signer" >&2
  exit 1
fi

write_base64
chmod 600 "$keystore_file" "$password_file" "$base64_file"

echo "Existing Android OTA signing material matches the pinned certificate."
echo "GitHub secret ANDROID_SIGNING_KEY_BASE64: $base64_file"
echo "GitHub secret ANDROID_SIGNING_PASSWORD: $password_file"
echo "Keep the entire directory backed up offline: $signing_dir"
