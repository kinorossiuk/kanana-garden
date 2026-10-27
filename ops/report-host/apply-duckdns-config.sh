#!/usr/bin/env bash
set -euo pipefail
umask 077

if (( EUID != 0 )); then
  echo "이 작업은 Certbot 설정 보호를 위해 root 권한이 필요합니다." >&2
  echo "sudo ./ops/report-host/apply-duckdns-config.sh 로 실행하세요." >&2
  exit 1
fi

owner_user="${SUDO_USER:-khadas}"
owner_home="$(getent passwd "$owner_user" | cut -d: -f6)"
if [[ -z "$owner_home" || ! -d "$owner_home" ]]; then
  echo "사용자 홈 디렉터리를 찾을 수 없습니다: $owner_user" >&2
  exit 1
fi
owner_group="$(id -gn "$owner_user")"

secret_file="${KANANA_DUCKDNS_TOKEN_FILE:-$owner_home/.config/kanana-garden/secrets/duckdns-token}"
duck_script="${KANANA_DUCKDNS_SCRIPT:-$owner_home/duckdns/duck.sh}"
jenkins_root="${KANANA_JENKINS_ROOT:-$owner_home/jenkins-cicd}"
jenkins_compose="$jenkins_root/docker-compose.yml"
jenkins_job="$jenkins_root/jenkins_home/jobs/ddns-update/config.xml"
certbot_renewal="${KANANA_CERTBOT_RENEWAL:-/etc/letsencrypt/renewal/rossiuk-server.duckdns.org.conf}"

for required_file in "$secret_file" "$duck_script" "$jenkins_compose" "$jenkins_job" "$certbot_renewal"; do
  if [[ ! -f "$required_file" ]]; then
    echo "필수 파일을 찾을 수 없습니다: $required_file" >&2
    exit 1
  fi
done

token="$(<"$secret_file")"
if [[ "$token" == *$'\n'* || "$token" == *$'\r'* || ! "$token" =~ ^[A-Za-z0-9-]{20,128}$ ]]; then
  unset token
  echo "보호 파일의 DuckDNS 토큰 형식이 올바르지 않습니다." >&2
  exit 1
fi

if ! grep -Eq '^dns_duckdns_token[[:space:]]*=' "$certbot_renewal"; then
  unset token
  echo "Certbot DuckDNS 토큰 항목을 찾지 못했습니다." >&2
  exit 1
fi
if ! grep -Fq '/run/secrets/duckdns-token:ro' "$jenkins_compose" \
    && ! grep -Fq './jenkins_home:/var/jenkins_home' "$jenkins_compose"; then
  unset token
  echo "Jenkins volume 삽입 위치를 찾지 못했습니다." >&2
  exit 1
fi
python3 - "$jenkins_job" <<'PY'
import sys
import xml.etree.ElementTree as ET
root = ET.parse(sys.argv[1]).getroot()
if root.tag != "project" or root.find("builders") is None or root.find("triggers") is None:
    raise SystemExit("Jenkins job의 builders/triggers 구조를 확인할 수 없습니다.")
PY

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="$owner_home/.config/kanana-garden/backups/duckdns-$timestamp"
install -d -o "$owner_user" -g "$owner_group" -m 0700 "$backup_dir"
for source_file in "$duck_script" "$jenkins_compose" "$jenkins_job" "$certbot_renewal"; do
  backup_file="$backup_dir/$(printf '%s' "$source_file" | sed 's#^/##; s#/#__#g')"
  cp --preserve=mode,timestamps "$source_file" "$backup_file"
  chown "$owner_user:$owner_group" "$backup_file"
  chmod 0600 "$backup_file"
done

changes_started=0
apply_complete=0
rollback_on_exit() {
  status=$?
  if (( apply_complete == 0 && changes_started == 1 )); then
    echo "DuckDNS 설정 적용 실패: 이전 파일을 복원합니다." >&2
    for source_file in "$duck_script" "$jenkins_compose" "$jenkins_job" "$certbot_renewal"; do
      backup_file="$backup_dir/$(printf '%s' "$source_file" | sed 's#^/##; s#/#__#g')"
      cp "$backup_file" "$source_file" || echo "복원 실패: $source_file" >&2
    done
  fi
  exit "$status"
}
trap rollback_on_exit EXIT

duck_tmp="$(mktemp)"
cat > "$duck_tmp" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

token_file="${KANANA_DUCKDNS_TOKEN_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/kanana-garden/secrets/duckdns-token}"
log_file="${KANANA_DUCKDNS_LOG_FILE:-$HOME/duckdns/duck.log}"

if [[ ! -r "$token_file" ]]; then
  echo "DuckDNS token file is not readable: $token_file" >&2
  exit 1
fi

response="$(curl --silent --show-error --fail --get \
  --data-urlencode 'domains=rossiuk-server' \
  --data-urlencode "token@$token_file" \
  --data-urlencode 'ip=' \
  https://www.duckdns.org/update)"

install -d -m 0700 "$(dirname "$log_file")"
printf '%s\n' "$response" > "$log_file"
if [[ "$response" != "OK" ]]; then
  echo "DuckDNS update failed: $response" >&2
  exit 1
fi
printf '%s\n' "$response"
EOF
changes_started=1
install -o "$owner_user" -g "$owner_group" -m 0700 "$duck_tmp" "$duck_script"
rm -f "$duck_tmp"

compose_tmp="$(mktemp)"
mount_line="      - $secret_file:/run/secrets/duckdns-token:ro"
if grep -Fq '/run/secrets/duckdns-token:ro' "$jenkins_compose"; then
  cp "$jenkins_compose" "$compose_tmp"
else
  inserted=0
  while IFS= read -r line || [[ -n "$line" ]]; do
    printf '%s\n' "$line" >> "$compose_tmp"
    if [[ "$line" == *'./jenkins_home:/var/jenkins_home'* ]]; then
      printf '%s\n' "$mount_line" >> "$compose_tmp"
      inserted=1
    fi
  done < "$jenkins_compose"
  if (( inserted == 0 )); then
    unset token
    rm -f "$compose_tmp"
    echo "Jenkins volume 삽입 위치를 찾지 못했습니다." >&2
    exit 1
  fi
fi
chown --reference="$jenkins_compose" "$compose_tmp"
chmod --reference="$jenkins_compose" "$compose_tmp"
mv -f "$compose_tmp" "$jenkins_compose"

job_tmp="$(mktemp)"
python3 - "$jenkins_job" "$job_tmp" <<'PY'
import sys
import xml.etree.ElementTree as ET

source, destination = sys.argv[1:]
tree = ET.parse(source)
root = tree.getroot()
builders = root.find("builders")
triggers = root.find("triggers")
command_text = '''set +x
token_file=/run/secrets/duckdns-token
if [ ! -r "$token_file" ]; then
  echo "DuckDNS token file is not readable" >&2
  exit 1
fi
response="$(curl --silent --show-error --fail --get \\
  --data-urlencode 'domains=rossiuk-server' \\
  --data-urlencode "token@$token_file" \\
  --data-urlencode 'ip=' \\
  https://www.duckdns.org/update)"
printf '%s\\n' "$response"
test "$response" = OK'''
shells = [
    shell for shell in builders.findall("hudson.tasks.Shell")
    if "duckdns.org/update" in (shell.findtext("command") or "")
    or "/run/secrets/duckdns-token" in (shell.findtext("command") or "")
]
if len(shells) > 1:
    raise SystemExit("DuckDNS Jenkins shell이 여러 개라 안전하게 갱신할 수 없습니다.")
if shells:
    shell = shells[0]
else:
    shell = ET.SubElement(builders, "hudson.tasks.Shell")
    ET.SubElement(shell, "configuredLocalRules")
command = shell.find("command")
if command is None:
    command = ET.SubElement(shell, "command")
command.text = command_text
timers = triggers.findall("hudson.triggers.TimerTrigger")
if not timers:
    timers = [ET.SubElement(triggers, "hudson.triggers.TimerTrigger")]
for timer in timers:
    spec = timer.find("spec")
    if spec is None:
        spec = ET.SubElement(timer, "spec")
    spec.text = "H/5 * * * *"
ET.indent(tree, space="  ")
tree.write(destination, encoding="UTF-8", xml_declaration=True)
PY
chown --reference="$jenkins_job" "$job_tmp"
chmod --reference="$jenkins_job" "$job_tmp"
mv -f "$job_tmp" "$jenkins_job"

certbot_tmp="$(mktemp)"
token_replaced=0
while IFS= read -r line || [[ -n "$line" ]]; do
  if [[ "$line" =~ ^dns_duckdns_token[[:space:]]*= ]]; then
    printf 'dns_duckdns_token = %s\n' "$token" >> "$certbot_tmp"
    token_replaced=1
  else
    printf '%s\n' "$line" >> "$certbot_tmp"
  fi
done < "$certbot_renewal"
unset token
if (( token_replaced == 0 )); then
  rm -f "$certbot_tmp"
  echo "Certbot DuckDNS 토큰 항목을 찾지 못했습니다." >&2
  exit 1
fi
install -o root -g root -m 0600 "$certbot_tmp" "$certbot_renewal"
rm -f "$certbot_tmp"

apply_complete=1
trap - EXIT
echo "DuckDNS 설정 반영 완료"
echo "보안 백업: $backup_dir"
echo "Jenkins는 다음 docker compose 기동 때 보호 토큰을 읽습니다."
