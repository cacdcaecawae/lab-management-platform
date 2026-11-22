#!/usr/bin/env bash
# Runs the update an ops account starts with 立即更新 in 系统管理 → 版本, on the server as the user who installed the
# site, so no container gets Docker access. cron starts it every minute; the copy holding the lock looks for a request
# every 2 seconds, runs scripts/update.sh and exits, and cron then starts the new release's copy.
#   scripts/update-agent.sh             from cron
#   scripts/update-agent.sh --install   add it and the nightly backup to this user's crontab (install.sh runs this)
set -euo pipefail

main() {
  source "$(dirname "$0")/server-env.sh"
  if [ "${1:-}" = --install ]; then install_cron; return; fi
  local state=$PWD/run/update file target='' beat=0
  exec 9>"$state/agent.lock"
  flock -n 9 || exit 0
  # The backend container (uid 1000) writes requests whoever owns the checkout; other users of the server get nothing.
  chmod 700 "$state" && chmod 1777 "$state/request" && chmod 755 "$state/status"
  while [ -z "$target" ]; do
    if ((SECONDS >= beat)); then
      date +%s >"$state/status/agent.tmp" && mv -f -- "$state/status/agent.tmp" "$state/status/agent"
      beat=$((SECONDS + 30))
    fi
    for file in "$state"/request/*; do
      # The file name is the request: never follow or read what the backend put there.
      if [[ -f $file && ! -L $file && ${file##*/} =~ ^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]; then
        target=${file##*/}
      fi
      rm -rf -- "$file"
    done
    [ -n "$target" ] || sleep 2
  done
  update "$target"
}

update() {
  export LAB_UPDATE_STATUS=$PWD/run/update/status/status.json LAB_UPDATE_TARGET=$1 LAB_UPDATE_STARTED
  LAB_UPDATE_STARTED=$(date +%s)
  progress running 0
  echo "== $(date '+%F %T') 网页上请求更新到 $1"
  # Read the site's Compose files again (server-env.sh): ops may have switched an overlay on since this copy started.
  unset COMPOSE_FILE COMPOSE_PROJECT_NAME
  running_stack
  if [[ -n $SITE_RUNNING ]]; then
    if bash scripts/update.sh "$1"; then
      progress done 3
      exit 0
    fi
  else
    echo "没有找到正在运行的网站（$PWD/infra 的 backend 容器），没有更新" >&2
  fi
  progress failed 0
  exit 1
}

sq() { printf "'%s'" "${1//\'/\'\\\'\'}"; }

install_cron() {
  local line name current added=''
  # cron runs with PATH=/usr/bin:/bin: name docker's directory and this bash (4+, which the scripts need).
  local run="cd $(sq "$PWD") && PATH=$(sq "$(dirname "$(command -v docker)"):/usr/bin:/bin") $(sq "$BASH")"
  local lines=("30 2 * * * $run scripts/backup.sh >> $(sq "$PWD-backup.log") 2>&1"
    "* * * * * $run scripts/update-agent.sh >> run/update/update.log 2>&1")
  lines=("${lines[@]//%/\\%}")
  if ! command -v crontab >/dev/null; then
    echo "没有 crontab（先安装 cron），请手动加入定时任务："
    printf '  %s\n' "${lines[@]}"
    return 0
  fi
  current=$(crontab -l 2>/dev/null) || current=''
  for line in "${lines[@]}"; do
    name=${line##* scripts/} name=scripts/${name%% *}
    # Already there, perhaps added by hand from the old install message: same directory and script.
    if awk -v d="$PWD" -v s="$name" '!/^[[:space:]]*#/ && index($0, d) && index($0, s) {f = 1} END {exit !f}' <<<"$current"
    then continue; fi
    current=${current:+$current$'\n'}$line
    added+="  $line"$'\n'
  done
  if [ -z "$added" ]; then
    echo "定时任务已经有了（crontab -l 查看）"
  elif printf '%s\n' "$current" | crontab -; then
    printf '已加入定时任务（crontab -l 查看）：\n%s' "$added"
  else
    printf '写入 crontab 失败，请手动加入：\n%s' "$added"
  fi
}

# Everything runs from main: update.sh's git checkout may replace this file while it runs.
main "$@"
exit
