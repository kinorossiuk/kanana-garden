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

IFS= read -r token < "$secret_file"
if [[ ! "$token" =~ ^[A-Za-z0-9-]{20,128}$ ]]; then
  unset token
  echo "보호 파일의 DuckDNS 토큰 형식이 올바르지 않습니다." >&2
  exit 1
fi

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="$owner_home/.config/kanana-garden/backups/duckdns-$timestamp"
install -d -o "$owner_user" -g "$owner_group" -m 0700 "$backup_dir"
for source_file in "$duck_script" "$jenkins_compose" "$jenkins_job" "$certbot_renewal"; do
  backup_file="$backup_dir/$(printf '%s' "$source_file" | sed 's#^/##; s#/#__#g')"
  cp --preserve=mode,timestamps "$source_file" "$backup_file"
  chown "$owner_user:$owner_group" "$backup_file"
  chmod 0600 "$backup_file"
done

secret_tmp="$(mktemp "$(dirname "$secret_file")/.duckdns-token.XXXXXX")"
printf '%s' "$token" > "$secret_tmp"
chown "$owner_user:$owner_group" "$secret_tmp"
chmod 0600 "$secret_tmp"
mv -f "$secret_tmp" "$secret_file"

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
cat > "$job_tmp" <<'EOF'
<?xml version='1.1' encoding='UTF-8'?>
<project>
  <actions/>
  <description>DuckDNS 업데이트. 토큰은 /run/secrets/duckdns-token에서 읽습니다.</description>
  <keepDependencies>false</keepDependencies>
  <properties/>
  <scm class="hudson.scm.NullSCM"/>
  <canRoam>true</canRoam>
  <disabled>false</disabled>
  <blockBuildWhenDownstreamBuilding>false</blockBuildWhenDownstreamBuilding>
  <blockBuildWhenUpstreamBuilding>false</blockBuildWhenUpstreamBuilding>
  <triggers>
    <hudson.triggers.TimerTrigger>
      <spec>H/5 * * * *</spec>
    </hudson.triggers.TimerTrigger>
  </triggers>
  <concurrentBuild>false</concurrentBuild>
  <builders>
    <hudson.tasks.Shell>
      <command>set +x
token_file=/run/secrets/duckdns-token
if [ ! -r "$token_file" ]; then
  echo "DuckDNS token file is not readable" &gt;&amp;2
  exit 1
fi
response="$(curl --silent --show-error --fail --get \
  --data-urlencode 'domains=rossiuk-server' \
  --data-urlencode "token@$token_file" \
  --data-urlencode 'ip=' \
  https://www.duckdns.org/update)"
printf '%s\n' "$response"
test "$response" = OK</command>
      <configuredLocalRules/>
    </hudson.tasks.Shell>
  </builders>
  <publishers/>
  <buildWrappers/>
</project>
EOF
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

echo "DuckDNS 설정 반영 완료"
echo "보안 백업: $backup_dir"
echo "Jenkins는 다음 docker compose 기동 때 보호 토큰을 읽습니다."
