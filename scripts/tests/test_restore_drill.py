"""Synthetic orchestration regression; never uses Docker or a real backup."""
import os
import runpy
from pathlib import Path
import subprocess

import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]

DOCKER = r'''#!/usr/bin/env python3
import hashlib, json, os, pathlib, subprocess, sys
args = sys.argv[1:]
with open(os.environ["DOCKER_LOG"], "a") as log:
    print(" ".join(args), file=log)
if args[0] != "compose":
    if os.environ.get("MODE") == "collision":
        print("existing")
    sys.exit(0)
assert args[1] == "--project-name" and args[2].startswith("labdrill-")
assert args[3:5] == ["--file", "infra/docker-compose.drill.yml"]
args = args[7:]
if args[0] == "up":
    sys.exit(0)
if args[0] == "down":
    sys.exit(int(os.environ.get("MODE") == "cleanup"))
if args[0] == "exec":
    assert sys.stdin.buffer.read() == b"dump"
    sys.exit(0)
assert args[:4] == ["run", "--rm", "-T", "--no-deps"]
service, *argv = args[4:]
path = "datasets/1/" + "b"*32
id = "a"*64
if service == "restic":
    if "cat" in argv and argv[-1] == "config":
        print('  "id": "' + ('b' if os.environ.get("MODE") == "wrong-id" else 'a') * 64 + '",')
    elif argv[0] == "snapshots":
        print(json.dumps([{"time":"2026-11-19", "hostname":"lab", "id":id}]))
    else:
        assert argv[:2] == ["dump", id]
        if argv[2] == "/dump/lab.dump":
            sys.stdout.buffer.write(b"dump")
        elif os.environ.get("MODE") == "missing":
            sys.exit(1)
        else:
            assert argv[2] == "/data/files/" + path
            sys.stdout.buffer.write(b"corrupt" if os.environ.get("MODE") == "corrupt" else b"file")
elif argv[0] == "sample":
    print(json.dumps([["DataFile", path, hashlib.sha256(b"file").hexdigest()]]))
else:
    # Exercise the real bundled snapshot parser and file verifier.
    script = pathlib.Path(os.environ["DRILL_SCRIPT"]).read_text()
    sys.exit(subprocess.call([sys.executable, "-c", script, *argv]))
'''


class RestoreDrillTests(unittest.TestCase):
    def test_applied_migrations_match_image_or_replacement(self):
        check = runpy.run_path(str(ROOT / "scripts/restore-drill-verify.py"))["check_applied_migrations"]
        disk = {("app", "0002_squashed"): SimpleNamespace(replaces=[("app", "0001")])}
        check({("app", "0001")}, disk)
        with self.assertRaisesRegex(ValueError, "does not know"):
            check({("app", "0003")}, disk)

    def test_restore_drill(self):
        for mode in ("ok", "missing", "corrupt", "cleanup", "collision", "right-id", "wrong-id", "missing-id", "missing-mount"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                self.run_case(mode, Path(directory))

    def run_case(self, mode, tmp_path):
        docker = tmp_path / "docker"
        docker.write_text(DOCKER)
        docker.chmod(0o755)
        log = tmp_path / "docker.log"
        env_file = tmp_path / "synthetic.env"
        repo_id = "BACKUP_REPO_ID=" + "a" * 64 + "\n"
        env_file.write_text(
            repo_id if mode in ("right-id", "wrong-id") else
            "BACKUP_MOUNTPOINT=/fixture\n" if mode == "missing-id" else ""
        )
        if mode == "missing-mount":
            with env_file.open("a") as config:
                config.write(repo_id + f"BACKUP_MOUNTPOINT={tmp_path}\n")
            mountpoint = tmp_path / "mountpoint"
            mountpoint.write_text("#!/bin/sh\nexit 1\n")
            mountpoint.chmod(0o755)
        result = subprocess.run(["bash", "scripts/restore-drill.sh", "v0.1.0"], cwd=ROOT,
                                env=dict(os.environ, PATH=f"{tmp_path}:{os.environ['PATH']}",
                                         ENV_FILE=str(env_file), MODE=mode, DOCKER_LOG=str(log), TMPDIR=str(tmp_path)),
                                text=True, capture_output=True)
        if mode in ("missing-id", "missing-mount"):
            assert result.returncode != 0
            assert ("BACKUP_REPO_ID" if mode == "missing-id" else "备份挂载点未挂载") in result.stderr
            assert not log.exists()
            return
        calls = log.read_text()
        assert not list(tmp_path.glob("labdrill.*"))
        assert ("down --volumes --remove-orphans" in calls) == (mode != "collision")
        assert ("dump " in calls) == (mode not in ("collision", "wrong-id"))
        assert (result.returncode == 0) == (mode in ("ok", "right-id")), (result.stdout, result.stderr)
        assert ("演练通过" in result.stdout) == (mode in ("ok", "right-id"))
        if mode == "wrong-id":
            assert "身份不符" in result.stderr and "snapshots" not in calls and "up -d" not in calls
        if mode == "corrupt":
            assert "checksum mismatch" in result.stderr
        if mode == "cleanup":
            assert "演练清理失败" in result.stderr
