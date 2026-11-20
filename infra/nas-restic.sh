#!/bin/sh
set -eu
marker=/data/.lab-storage-id
if [ -z "${LAB_NAS_STORAGE_ID:-}" ] ||
   [ -L "$marker" ] || [ ! -f "$marker" ] ||
   [ -L /data/files ] || [ ! -d /data/files ] ||
   ! actual=$(head -c 129 "$marker") || [ "$actual" != "$LAB_NAS_STORAGE_ID" ]; then
  echo 'NAS 主存储未挂载或标识不匹配；未运行 restic。' >&2
  exit 1
fi
exec restic "$@"
