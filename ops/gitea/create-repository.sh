#!/usr/bin/env bash
set -euo pipefail

: "${GITEA_URL:?Set GITEA_URL, for example http://192.168.0.40:3000}"
: "${GITEA_TOKEN:?Set a Gitea personal access token in the environment}"
: "${GITEA_REPO:=kanana}"
: "${GITEA_SSH_BASE:=ssh://git@192.168.0.40:222}"

user_json="$(curl -fsS \
  -H "Authorization: token $GITEA_TOKEN" \
  "$GITEA_URL/api/v1/user")"
gitea_owner="$(printf '%s' "$user_json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["login"])')"

payload="$(GITEA_REPO_VALUE="$GITEA_REPO" python3 -c \
  'import json,os; print(json.dumps({"name": os.environ["GITEA_REPO_VALUE"], "private": True, "auto_init": False}))')"
curl -fsS \
  -X POST \
  -H "Authorization: token $GITEA_TOKEN" \
  -H "Content-Type: application/json" \
  -d "$payload" \
  "$GITEA_URL/api/v1/user/repos" >/dev/null

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git init -b main
fi
remote_url="$GITEA_SSH_BASE/$gitea_owner/$GITEA_REPO.git"
if git remote get-url gitea >/dev/null 2>&1; then
  git remote set-url gitea "$remote_url"
else
  git remote add gitea "$remote_url"
fi

echo "Created $GITEA_URL/$gitea_owner/$GITEA_REPO"
echo "Configured remote: gitea -> $remote_url"
echo "Review files, then commit and run: git push -u gitea main"
