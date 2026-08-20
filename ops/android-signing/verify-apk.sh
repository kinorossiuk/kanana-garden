#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 APK_FILE" >&2
  exit 2
fi

apk_file="$1"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
fingerprint_file="$script_dir/../../android/uis7862s-bridge/release-cert-sha256.txt"

if [[ ! -f "$apk_file" ]]; then
  echo "Android release APK not found: $apk_file" >&2
  exit 1
fi
if [[ ! -f "$fingerprint_file" ]]; then
  echo "Pinned Android signing certificate fingerprint not found: $fingerprint_file" >&2
  exit 1
fi

expected_signer="$(tr -d '[:space:]:' < "$fingerprint_file" | tr '[:upper:]' '[:lower:]')"
if [[ ! "$expected_signer" =~ ^[0-9a-f]{64}$ ]]; then
  echo "Pinned Android signing certificate fingerprint is invalid." >&2
  exit 1
fi

apksigner_command="${APKSIGNER:-}"
if [[ -z "$apksigner_command" && -n "${ANDROID_HOME:-}" ]]; then
  apksigner_command="$ANDROID_HOME/build-tools/36.0.0/apksigner"
fi
if [[ -z "$apksigner_command" ]]; then
  apksigner_command="$(command -v apksigner || true)"
fi
if [[ -z "$apksigner_command" || ! -x "$apksigner_command" ]]; then
  echo "Android apksigner executable not found." >&2
  exit 1
fi

if ! signer_output="$("$apksigner_command" verify --verbose --print-certs "$apk_file" 2>&1)"; then
  printf '%s\n' "$signer_output"
  echo "Android APK signature verification failed." >&2
  exit 1
fi
printf '%s\n' "$signer_output"

mapfile -t signer_digests < <(
  printf '%s\n' "$signer_output" |
    sed -nE 's/^Signer #[0-9]+ certificate SHA-256 digest: ([0-9A-Fa-f:]+)\r?$/\1/p'
)
if [[ ${#signer_digests[@]} -ne 1 ]]; then
  echo "Expected exactly one Android APK signer, found ${#signer_digests[@]}." >&2
  exit 1
fi

actual_signer="$(printf '%s' "${signer_digests[0]}" | tr -d ':' | tr '[:upper:]' '[:lower:]')"
if [[ "$actual_signer" != "$expected_signer" ]]; then
  echo "Android APK signer does not match the pinned OTA certificate." >&2
  echo "Expected: $expected_signer" >&2
  echo "Actual:   $actual_signer" >&2
  exit 1
fi

echo "Pinned Android OTA signer verified: $actual_signer"
