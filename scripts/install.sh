#!/usr/bin/env bash
# One-command install of the newest release, on a machine with Docker (compose plugin), git and curl:
#   curl -fsSL https://raw.githubusercontent.com/cacdcaecawae/lab-management-platform/main/scripts/install.sh | bash
#   curl -fsSL .../scripts/install.sh | bash -s -- --host 192.168.1.20 --port 80 --dir /srv/lab-management-platform
# Linux; Windows inside WSL. Not macOS: update.sh (GNU sed -i) and the printed cron line (bash 4) do not run
# there. Run from inside a clone (bash scripts/install.sh) to install that clone instead.
# Clones the repository at the newest published GitHub release, writes .env with random secrets (readable by the
# owner only, plain HTTP), pulls that release's images, initialises a backup repository next to the install
# directory, starts the site and creates the ops account with a one-time password. Later: scripts/update.sh
# updates, README "正式域名 HTTPS" adds HTTPS.
# LAB_REPO and LAB_RELEASE_API point at a mirror or a test copy of the repository and its latest-release JSON.
set -euo pipefail

die() { echo "$*" >&2; exit 1; }
rand() { od -An -N"$1" -tx1 /dev/urandom | tr -d ' \n'; }
sq() { printf "'%s'" "${1//\'/\'\\\'\'}"; } # one shell word, for the commands printed to copy

# What this run created, for cleanup: a failed or concurrent run removes only its own files.
dir='' backup='' tmp='' lock_id='' env_created='' backup_created='' started='' project='' volume_names=''
LOCK=lab-platform-install

main() {
  [ "${BASH_VERSINFO[0]}" -ge 4 ] || die "需要 bash 4 以上"
  case "$(uname -s)" in
    MINGW* | MSYS* | CYGWIN*) die "Windows 上请在 WSL 里运行（Docker Desktop 打开 WSL 集成）" ;;
    Darwin) die "暂不支持 Mac：装好以后的更新和每日备份脚本在 Mac 上还不能运行。请用 Linux，或者 Windows 的 WSL" ;;
  esac

  local port=8090 host='' self=${BASH_SOURCE[0]:-}
  dir=lab-management-platform
  # Run as a file inside a clone: install that clone. Piped from curl there is no file.
  if [ -f "$self" ] && [ -d "$(dirname "$self")/../.git" ]; then dir=$(cd "$(dirname "$self")/.." && pwd); fi
  while [ $# -gt 0 ]; do
    case $1 in
      --dir) dir=${2:?--dir 后面写安装目录}; shift 2 ;;
      --port) port=${2:?--port 后面写端口}; shift 2 ;;
      --host) host=${2:?--host 后面写本机 IP 或域名}; shift 2 ;;
      *) die "不认识的参数：$1（可用：--dir 安装目录、--port 端口、--host 让别的电脑用这个 IP 或域名访问）" ;;
    esac
  done
  [[ $port =~ ^[0-9]{1,5}$ ]] && port=$((10#$port)) && [ "$port" -ge 1 ] && [ "$port" -le 65535 ] ||
    die "端口应是 1 到 65535：$port" # 10#: "080" is port 80, as Compose reads it
  # shortcut: host names and IPv4 only; IPv6 literals need brackets in the origins, add them when someone needs it
  [[ -z $host || $host =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$ ]] ||
    die "--host 只写主机名或 IP，不带 http:// 和端口：$host"

  command -v git >/dev/null || die "先安装 git"
  command -v curl >/dev/null || die "先安装 curl"
  docker compose version >/dev/null 2>&1 || die "先安装 Docker（带 compose 插件）"
  docker info >/dev/null 2>&1 || die "Docker 没有运行，或者当前用户没有使用 Docker 的权限"

  if [ -d "$dir/.git" ]; then
    [ ! -e "$dir/.env" ] || die "$dir 已经安装过。更新用：cd $(sq "$dir") && bash scripts/update.sh"
    git -C "$dir" fetch --quiet --tags origin
  elif [ -e "$dir" ]; then
    die "$dir 已经存在，但不是本项目的仓库。换一个目录：--dir <目录>"
  else
    echo "== 下载到 $dir"
    git clone --quiet "${LAB_REPO:-https://github.com/cacdcaecawae/lab-management-platform.git}" "$dir"
  fi
  cd "$dir"
  dir=$PWD
  trap 'cleanup $?' EXIT
  # On a signal the EXIT trap would see the last command's status (0) and clean up as after a success.
  trap 'exit 130' INT
  trap 'exit 143' TERM
  trap 'exit 129' HUP
  # One install at a time on this Docker, held to the end: every install uses Compose project "infra" and its
  # volumes, so two at once (even from two directories, or WSL and another distro) would both pass the volume
  # check below. A network name is unique per Docker daemon and creating one is atomic. Released by its ID.
  lock_id=$(docker network create --label "lab-platform.install=$dir" "$LOCK") || {
    docker network inspect "$LOCK" >/dev/null 2>&1 &&
      die "这台电脑的 Docker 上另一个安装正在进行。等它结束；确认没有安装在运行后，运行 docker network rm $LOCK 再重试"
    die "建不了安装锁（Docker 网络 $LOCK），原因见上面 Docker 的报错"
  }
  [ ! -e .env ] || die "$dir 已经安装过。更新用：cd $(sq "$dir") && bash scripts/update.sh"
  git diff --quiet HEAD || die "$dir 里有未提交的改动（git status 查看），处理后再安装"

  # The newest published release, not the newest tag: the tag exists before its images are built, and stays if
  # the release workflow fails. The release is created only after both images are pushed.
  local version
  version=$(curl -fsSL "${LAB_RELEASE_API:-https://api.github.com/repos/cacdcaecawae/lab-management-platform/releases/latest}" |
    sed -nE 's/.*"tag_name":[[:space:]]*"(v[0-9]+\.[0-9]+\.[0-9]+)".*/\1/p' | head -n 1) || true
  [ -n "$version" ] || die "查不到已发布的正式版本：还没有发布过、连不上 api.github.com，或者请求太频繁（稍后再试）"
  git rev-parse -q --verify "refs/tags/$version" >/dev/null || die "仓库里没有 $version 这个标签"
  git checkout --quiet "$version"

  local origins hosts bind site
  backup="$(dirname "$dir")/$(basename "$dir")-backup"
  [ ! -e "$backup" ] || die "备份目录已经存在：$backup（可能是上一次安装留下的备份），移走或改名后再安装"
  origin() { if [ "$port" = 80 ]; then echo "http://$1"; else echo "http://$1:$port"; fi; }
  hosts=localhost,127.0.0.1 origins="$(origin localhost),$(origin 127.0.0.1)" bind=127.0.0.1:$port site=$(origin localhost)
  if [ -n "$host" ]; then
    hosts=$host,$hosts origins="$(origin "$host"),$origins" bind=$port site=$(origin "$host")
  fi
  declare -A value=(
    [APP_VERSION]=$version [DJANGO_SECRET_KEY]=$(rand 32) [DJANGO_ALLOWED_HOSTS]=$hosts
    [DJANGO_CSRF_TRUSTED_ORIGINS]=$origins [SITE_URL]=$site [DJANGO_SECURE_COOKIES]=0 [HTTP_PORT]=$bind
    [POSTGRES_PASSWORD]=$(rand 32) [BACKUP_REPO]=$backup [BACKUP_PASSWORD]=$(rand 32)
  )

  umask 077
  tmp=$(mktemp "$dir/.env.XXXXXX") # a new file of our own, mode 600
  local line key
  while IFS= read -r line; do
    key=${line%%=*}
    if [[ $line == *=* && $line != \#* && -n ${value[$key]+set} ]]; then
      printf '%s=%s\n' "$key" "${value[$key]}"
      unset "value[$key]"
    else
      printf '%s\n' "$line"
    fi
  done <infra/server.env.example >"$tmp"
  [ ${#value[@]} -eq 0 ] || die "infra/server.env.example 里缺少这几项：${!value[*]}"
  [ -z "${IMAGE_PREFIX:-}" ] || echo "IMAGE_PREFIX=$IMAGE_PREFIX" >>"$tmp" # a registry mirror, kept for updates
  mv "$tmp" .env
  tmp='' env_created=1

  # Only .env decides: Compose prefers a variable exported in this shell (an HTTP_PORT without 127.0.0.1, another
  # APP_VERSION, a POSTGRES_USER...), and later updates from a clean shell read .env and the defaults alone.
  while IFS='=' read -r key _; do
    if [[ $key =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then unset "$key"; fi
  done < <(grep -v '^#' .env)
  for key in $(grep -oE '\$\{[A-Za-z_][A-Za-z0-9_]*' infra/docker-compose.prod.yml | cut -c3- | sort -u); do
    unset "$key"
  done
  unset COMPOSE_PROJECT_NAME COMPOSE_PROFILES
  export ENV_FILE=.env COMPOSE_FILE=infra/docker-compose.prod.yml
  # shellcheck source=server-env.sh
  source scripts/server-env.sh
  # Nothing of Compose project "infra" may exist yet: any volume this stack would use, by its real name (Compose
  # reuses one created by hand or moved back without labels), and any volume or container labelled with the
  # project ("infra" is a common directory name: another application's containers would be replaced).
  local config existing labelled containers clash
  config=$(dc config) || die "读不出 Docker Compose 的配置"
  project=$(sed -n 's/^name: //p' <<<"$config" | head -n 1)
  volume_names=$(awk '/^volumes:/ { v = 1; next } /^[^ ]/ { v = 0 } v && /^    name: / { print $2 }' <<<"$config")
  [ -n "$project" ] && [ -n "$volume_names" ] || die "读不出 Docker Compose 的项目名和数据卷名"
  existing=$(docker volume ls -q) &&
    labelled=$(docker volume ls -q --filter "label=com.docker.compose.project=$project") &&
    containers=$(docker ps -aq --filter "label=com.docker.compose.project=$project") ||
    die "查不出这台电脑的 Docker 上已有哪些数据卷和容器，停止安装"
  clash=$(grep -xF -f <(printf '%s\n' "$volume_names") <<<"$existing" || true)
  [ -z "$clash$labelled$containers" ] ||
    die "这台电脑的 Docker 上已经有 Compose 项目 $project 的数据卷或容器（数据卷：$(printf '%s\n' $clash $labelled | sort -u | tr '\n' ' ')容器 $(wc -w <<<"$containers") 个）。它们可能是这个平台以前的安装，也可能属于别的应用；安装不会动它们。换一台电脑，或者先查清它们是什么"
  volume_names=$(echo $volume_names) # one line, for the retry hint

  echo "== 下载 $version 的镜像"
  dc --profile ops pull ||
    die "拉不到 $version 的镜像。平台的两个镜像：确认 GitHub 的 Packages 页里是 Public，国内可以先 export IMAGE_PREFIX=<镜像仓库地址> 再安装；postgres、restic 来自 Docker Hub，拉不到时给 Docker 配置镜像加速"

  echo "== 初始化备份仓库 $backup"
  mkdir "$backup"
  backup_created=1
  # Only the backup directory is mounted. Compose's restic service also mounts the data volume, so running it
  # would create that volume before the site starts, and a retry after a failed init would find "existing data".
  local restic_image
  restic_image=$(dc --profile ops config --images | grep -m 1 '^restic/restic:') || die "读不出备份工具 restic 的镜像名"
  RESTIC_PASSWORD=$(envget BACKUP_PASSWORD) docker run --rm -e RESTIC_REPOSITORY=/repo -e RESTIC_PASSWORD \
    -v "$backup:/repo" "$restic_image" init >/dev/null || die "备份仓库初始化失败：确认 $backup 可以写入"

  echo "== 启动 $version"
  started=1
  dc up -d --no-build # the pulled release images, never a build from this checkout
  healthy || die "网站没有正常启动"
  local service image allowed actual
  for service in backend web; do
    image=$(dc ps --format '{{.Image}}' "$service") || image=''
    [[ $image != *$'\n'* && $image == *"/$service:$version" ]] || die "$service 运行的不是 $version 的镜像：${image:-没有运行}"
  done
  allowed="127.0.0.1:$port"
  [ -z "$host" ] || allowed="0.0.0.0:$port"$'\n'"[::]:$port"
  actual=$(dc port web 80) || actual=''
  [ -n "$actual" ] && ! grep -vxF -e "$allowed" <<<"$actual" >/dev/null ||
    die "网站监听的地址不对：${actual:-没有监听}，应该是 ${allowed//$'\n'/ 或 }"

  local password
  password=$(rand 8)
  # The password goes in on stdin, never on a command line that other processes can read.
  printf 'from accounts.models import User\nUser.objects.create_superuser("ops", password="%s")\n' "$password" |
    dc exec -T backend python manage.py shell >/dev/null

  # cron runs with PATH=/usr/bin:/bin: name docker's directory and this bash (4+, which the scripts need).
  local cron
  cron="30 2 * * * cd $(sq "$dir") && PATH=$(sq "$(dirname "$(command -v docker)"):/usr/bin:/bin") $(sq "$BASH")"
  cron+=" scripts/backup.sh >> $(sq "$dir-backup.log") 2>&1"
  cat <<EOF

安装完成：$version
  网址：      $site
  运维账号：  ops
  初始密码：  $password（只显示这一次；第一次登录必须改密码）
  配置文件：  $dir/.env（含密钥，只有你能读）
  备份：      $backup
              它和网站在同一块硬盘上。有第二块硬盘或 NAS 后，按 README"备份与恢复"换过去。
              备份密码是 .env 里的 BACKUP_PASSWORD，另外抄一份保存，丢了备份就打不开。
  每天备份：  crontab -e 加一行：
              ${cron//%/\\%}
  更新：      cd $(sq "$dir") && bash scripts/update.sh <新版本号>
              新版本号看"系统管理 → 版本"，那里只列正式发布了的版本
EOF
  if [ -n "$host" ]; then
    echo "  别的电脑打不开时，检查防火墙是否放行了 $port 端口。现在是 HTTP，只在内网用；公网要先配 HTTPS（README）。"
  else
    echo "  现在只有这台电脑能访问。要让别的电脑访问，重新安装时加 --host <本机 IP>。"
  fi
}

cleanup() {
  local rc=$1 compose
  [ -z "$tmp" ] || rm -f -- "$tmp"
  if [ "$rc" != 0 ] && [ -z "$started" ]; then
    [ -z "$env_created" ] || rm -f -- "$dir/.env"
    # Files restic wrote there belong to root (the container user), so this can fail.
    if [ -n "$backup_created" ]; then
      rm -rf -- "$backup" 2>/dev/null || echo "请手动删除备份目录：sudo rm -rf $(sq "$backup")" >&2
    fi
    [ -z "$env_created" ] || echo "安装没有完成，本次生成的配置和备份目录已删除。处理好上面的问题后重新运行。" >&2
  elif [ "$rc" != 0 ]; then
    # -p: an operator's shell may export COMPOSE_PROJECT_NAME for another stack (README, manual restore).
    compose="docker compose -p $(sq "$project") -f infra/docker-compose.prod.yml --env-file .env"
    echo "安装没有完成，网站可能已经部分启动。查看原因：cd $(sq "$dir") && $compose logs backend" >&2
    echo "要从头重装，依次运行（下面这些数据卷是这次安装新建的，安装前已确认它们都不存在）：" >&2
    echo "  cd $(sq "$dir")" >&2
    echo "  $compose down" >&2
    echo "  docker volume rm $volume_names" >&2
    echo "  rm .env && sudo rm -rf $(sq "$backup")" >&2
  fi
  [ -z "$lock_id" ] || docker network rm "$lock_id" >/dev/null 2>&1 || echo "请手动释放安装锁：docker network rm $LOCK" >&2
}

# Everything runs from main: piped from curl, and git checkout may replace this file while it runs.
main "$@"
exit
