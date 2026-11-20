#!/usr/bin/env bash
# One-command install of the newest release, on a machine with Docker (compose plugin) and git:
#   curl -fsSL https://raw.githubusercontent.com/cacdcaecawae/lab-management-platform/main/scripts/install.sh | bash
#   curl -fsSL .../scripts/install.sh | bash -s -- --host 192.168.1.20 --port 80 --dir /srv/lab-management-platform
# Linux; Windows inside WSL; macOS with a bash 4+ (brew install bash). Run from inside a clone
# (bash scripts/install.sh) to install that clone instead.
# Clones the repository at the newest release, writes .env with random secrets (readable by the owner only, plain
# HTTP), initialises a backup repository next to the install directory, starts the release images and creates the
# ops account with a one-time password. Later: scripts/update.sh updates, README "正式域名 HTTPS" adds HTTPS.
set -euo pipefail

die() { echo "$*" >&2; exit 1; }
rand() { od -An -N"$1" -tx1 /dev/urandom | tr -d ' \n'; }

main() {
  [ "${BASH_VERSINFO[0]}" -ge 4 ] || die "需要 bash 4 以上。Mac 先 brew install bash，再用新装的 bash 运行"
  case "$(uname -s)" in MINGW* | MSYS* | CYGWIN*) die "Windows 上请在 WSL 里运行（Docker Desktop 打开 WSL 集成）" ;; esac

  local dir=lab-management-platform port=8090 host='' self=${BASH_SOURCE[0]:-}
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
  [[ $port =~ ^[0-9]+$ ]] && [ "$port" -ge 1 ] && [ "$port" -le 65535 ] || die "端口应是 1 到 65535：$port"
  # shortcut: host names and IPv4 only; IPv6 literals need brackets in the origins, add them when someone needs it
  [[ -z $host || $host =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$ ]] ||
    die "--host 只写主机名或 IP，不带 http:// 和端口：$host"

  command -v git >/dev/null || die "先安装 git"
  docker compose version >/dev/null 2>&1 || die "先安装 Docker（带 compose 插件）"
  docker info >/dev/null 2>&1 || die "Docker 没有运行，或者当前用户没有使用 Docker 的权限"

  if [ -d "$dir/.git" ]; then
    [ ! -e "$dir/.env" ] || die "$dir 已经安装过。更新用：cd $dir && bash scripts/update.sh"
    git -C "$dir" fetch --quiet --tags origin
  elif [ -e "$dir" ]; then
    die "$dir 已经存在，但不是本项目的仓库。换一个目录：--dir <目录>"
  else
    echo "== 下载到 $dir"
    git clone --quiet "${LAB_REPO:-https://github.com/cacdcaecawae/lab-management-platform.git}" "$dir"
  fi
  cd "$dir"
  dir=$PWD
  git diff --quiet HEAD || die "$dir 里有未提交的改动（git status 查看），处理后再安装"
  local version
  version=$(git tag -l 'v*' --sort=-v:refname | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | head -n 1 || true)
  [ -n "$version" ] || die "还没有发布过正式版本（GitHub 的 Releases 页是空的）"
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

  # From here a failure removes what this run created, so it can simply be run again.
  started=''
  trap 'cleanup $?' EXIT
  umask 077
  local line key
  while IFS= read -r line; do
    key=${line%%=*}
    if [[ $line == *=* && $line != \#* && -n ${value[$key]+set} ]]; then
      printf '%s=%s\n' "$key" "${value[$key]}"
      unset "value[$key]"
    else
      printf '%s\n' "$line"
    fi
  done <infra/server.env.example >.env.tmp
  [ ${#value[@]} -eq 0 ] || die "infra/server.env.example 里缺少这几项：${!value[*]}"
  [ -z "${IMAGE_PREFIX:-}" ] || echo "IMAGE_PREFIX=$IMAGE_PREFIX" >>.env.tmp  # a registry mirror, kept for updates
  mv .env.tmp .env

  # shellcheck source=server-env.sh
  source scripts/server-env.sh
  local project
  project=$(dc config | sed -n 's/^name: //p' | head -n 1) && [ -n "$project" ] || die "读不出 Docker Compose 的项目名"
  [ -z "$(docker volume ls -q --filter "label=com.docker.compose.project=$project")" ] ||
    die "这台电脑上已经有一套平台的数据（Docker 项目 $project 的数据卷）。不要覆盖它：换一台电脑，或者先备份再删除那些数据卷"

  echo "== 初始化备份仓库 $backup"
  mkdir "$backup"
  bash scripts/backup.sh --init >/dev/null

  echo "== 启动 $version（第一次要下载镜像，几分钟）"
  started=1
  dc up -d
  healthy || die "网站没有正常启动"

  local password
  password=$(rand 8)
  # The password goes in on stdin, never on a command line that other processes can read.
  printf 'from accounts.models import User\nUser.objects.create_superuser("ops", password="%s")\n' "$password" |
    dc exec -T backend python manage.py shell >/dev/null

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
              30 2 * * * cd $dir && bash scripts/backup.sh >> $dir-backup.log 2>&1
  更新：      cd $dir && bash scripts/update.sh
EOF
  if [ -n "$host" ]; then
    echo "  别的电脑打不开时，检查防火墙是否放行了 $port 端口。现在是 HTTP，只在内网用；公网要先配 HTTPS（README）。"
  else
    echo "  现在只有这台电脑能访问。要让别的电脑访问，重新安装时加 --host <本机 IP>。"
  fi
}

cleanup() {
  [ "$1" != 0 ] || return 0
  if [ -z "$started" ]; then
    rm -f .env .env.tmp
    # Created by this run: the checks above stop before an existing backup directory. Files restic wrote there
    # belong to root (the container user), so this can fail.
    [ ! -d "$backup" ] || rm -rf -- "$backup" 2>/dev/null || echo "请手动删除备份目录：sudo rm -rf $backup" >&2
    echo "安装没有完成，没有留下配置。处理好上面的问题后重新运行。" >&2
  else
    echo "安装没有完成，网站可能已经部分启动。查看原因：cd $PWD && docker compose -f infra/docker-compose.prod.yml --env-file .env logs backend" >&2
    echo "要从头重装：cd $PWD && docker compose -f infra/docker-compose.prod.yml --env-file .env down -v && rm .env && sudo rm -rf $backup" >&2
  fi
}

# Everything runs from main: piped from curl, and git checkout may replace this file while it runs.
main "$@"
exit
