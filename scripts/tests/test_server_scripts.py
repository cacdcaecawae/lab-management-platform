"""Run real ops scripts with command doubles, never Docker or a real database."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
A = 'a' * 64
B = 'b' * 64

DOCKER = r'''
import json, os, pathlib, sys
root = pathlib.Path(os.environ['TEST_ROOT'])
args = sys.argv[1:]
with (root / 'calls').open('a') as f:
    f.write(json.dumps(args) + '\n')
command = ' '.join(args)
mode = os.environ.get('MODE', '')
if 'snapshots --json' in command:
    print(os.environ['SNAPSHOT_JSON'])
    sys.exit(1 if mode == 'query-fails' else 0)
if 'restic dump' in command:
    snap = args[args.index('dump') + 1]
    print('database:' + (('a' * 64) if snap == 'latest' else snap))
    (root / 'latest').write_text('b' * 64)  # another backup completed
elif 'restic restore' in command:
    snap = args[args.index('restore') + 1].split(':')[0]
    (root / 'files_snapshot').write_text((root / 'latest').read_text() if snap == 'latest' else snap)
    if mode == 'files-fail':
        print('no space left on device', file=sys.stderr)
        sys.exit(1)
elif 'pg_restore' in command:
    (root / 'database_dump').write_text(sys.stdin.read())
    if mode == 'pg-restore-fails':
        sys.exit(1)
elif 'ps' in args and '--format' in args:
    # Like Compose: an APP_VERSION exported in the shell wins over the env file.
    version = os.environ.get('APP_VERSION') or [
        line.split('=', 1)[1] for line in (root / '.env').read_text().splitlines() if line.startswith('APP_VERSION=')][-1]
    print(f'ghcr.io/x/backend:{version}\nghcr.io/x/web:{version}')
elif 'SELECT count' in command:
    print('20')
elif args[-2:] == ['up', '-d']:
    counter = root / 'up_count'
    n = int(counter.read_text()) + 1 if counter.exists() else 1
    counter.write_text(str(n))
    if mode == 'start-fails' and n == 1:
        print('recreation failed; old containers still serving', file=sys.stderr)
        sys.exit(1)
elif 'wget' in args:
    if mode == 'unhealthy' and (root / 'up_count').read_text() == '1':
        sys.exit(1)
'''


class ServerScripts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'scripts').mkdir()
        (self.root / 'bin').mkdir()
        for name in ('update.sh', 'restore.sh', 'server-env.sh'):
            shutil.copyfile(ROOT / 'scripts' / name, self.root / 'scripts' / name)
        (self.root / 'scripts/backup.sh').write_text(
            'echo \'["backup.sh"]\' >>"$TEST_ROOT/calls"\n'
            '[ "$MODE" != backup-fails ] || exit 1\n'
            "echo 'snapshot abcdef12 saved'\n")
        (self.root / '.env').write_text('APP_VERSION=v0.1.0\nBACKUP_REPO=/unused\nBACKUP_PASSWORD=dummy\n')
        self.executable('docker', '#!' + sys.executable + '\n' + DOCKER)
        self.executable('git', '#!/bin/bash\n[ "$1" != symbolic-ref ] || echo main\nexit 0\n')
        self.executable('sleep', '#!/bin/bash\nexit 0\n')
        self.env = dict(os.environ, PATH=str(self.root / 'bin') + os.pathsep + os.environ['PATH'],
                        TEST_ROOT=str(self.root), SNAPSHOT_JSON=json.dumps([{'id': A}]))
        # Do not inherit an operator's target-stack overrides.
        for key in ('ENV_FILE', 'COMPOSE_FILE', 'COMPOSE_PROJECT_NAME', 'MODE'):
            self.env.pop(key, None)

    def executable(self, name, text):
        path = self.root / 'bin' / name
        path.write_text(text)
        path.chmod(0o755)

    def run_script(self, name, *args, mode=''):
        return subprocess.run(['bash', str(self.root / 'scripts' / name), *args],
                              env=dict(self.env, MODE=mode), text=True, capture_output=True, timeout=20)

    def calls(self):
        return [json.loads(line) for line in (self.root / 'calls').read_text().splitlines()]

    def test_failed_start_cannot_succeed_from_old_healthy_endpoint(self):
        r = self.run_script('update.sh', 'v0.2.0', mode='start-fails')
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertNotIn('已更新到', r.stdout)
        self.assertIn('APP_VERSION=v0.1.0', (self.root / '.env').read_text())
        self.assertEqual((self.root / 'up_count').read_text(), '2')
        calls = self.calls()
        up = [i for i, c in enumerate(calls) if c[-2:] == ['up', '-d']]
        self.assertFalse(any('wget' in c for c in calls[up[0] + 1:up[1]]))

    def test_successful_start_and_health_still_succeed(self):
        r = self.run_script('update.sh', 'v0.2.0')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('已更新到 v0.2.0', r.stdout)

    def test_site_is_stopped_before_the_rollback_backup(self):
        # A change saved after the backup would be lost when the rollback restores that backup.
        r = self.run_script('update.sh', 'v0.2.0')
        self.assertEqual(r.returncode, 0, r.stderr)
        calls = self.calls()
        self.assertLess(calls.index(['compose', '--env-file', '.env', 'stop', 'backend', 'web']), calls.index(['backup.sh']))

    def test_failed_backup_restarts_the_old_version_without_updating(self):
        r = self.run_script('update.sh', 'v0.2.0', mode='backup-fails')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('网站已重新启动', r.stderr)
        self.assertIn('APP_VERSION=v0.1.0', (self.root / '.env').read_text())
        self.assertEqual(self.calls()[-1][-2:], ['up', '-d'])

    def test_old_images_answering_is_not_an_update(self):
        # An APP_VERSION exported in the operator's shell keeps the old images running after up -d.
        self.env['APP_VERSION'] = 'v0.1.0'
        r = self.run_script('update.sh', 'v0.2.0')
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn('已更新到', r.stdout)
        self.assertIn('已退回 v0.1.0', r.stderr)

    def test_health_failure_still_rolls_back(self):
        r = self.run_script('update.sh', 'v0.2.0', mode='unhealthy')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('已退回 v0.1.0', r.stderr)
        self.assertIn('APP_VERSION=v0.1.0', (self.root / '.env').read_text())

    def test_latest_stays_pinned_when_new_backup_completes(self):
        # Both compact and pretty restic JSON; fake id text within an escaped path must not match.
        for indent in (None, 2):
            with self.subTest(indent=indent):
                self.env['SNAPSHOT_JSON'] = json.dumps([{'id': A, 'paths': ['a "id":"' + B + '"']}], indent=indent)
                r = self.run_script('restore.sh', 'latest', '--yes')
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual((self.root / 'database_dump').read_text().strip(), 'database:' + A)
                self.assertEqual((self.root / 'files_snapshot').read_text(), A)
                self.assertNotIn('latest:/data', str(self.calls()))

    def test_invalid_selection_never_stops_site(self):
        for value in ('[]', '[{"id":"bad"}]', json.dumps([{'id': A}, {'id': B}])):
            with self.subTest(value=value):
                self.env['SNAPSHOT_JSON'] = value
                r = self.run_script('restore.sh', 'latest', '--yes')
                self.assertNotEqual(r.returncode, 0)
                self.assertFalse(any('stop' in c for c in self.calls()))

    def test_snapshot_query_failure_never_stops_site_even_with_valid_output(self):
        r = self.run_script('restore.sh', 'latest', '--yes', mode='query-fails')
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(any('stop' in c for c in self.calls()))

    def test_database_from_before_is_kept_until_files_and_site_are_back(self):
        for mode in ('files-fail', 'unhealthy'):
            with self.subTest(mode=mode):
                (self.root / 'calls').unlink(missing_ok=True)
                (self.root / 'up_count').unlink(missing_ok=True)
                r = self.run_script('restore.sh', A, '--yes', mode=mode)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn('恢复前的数据库保留为 before_restore_', r.stderr)
                self.assertFalse(any('dropdb' in c and '"$OLD"' in c for c in map(' '.join, self.calls())))

    def test_successful_restore_drops_the_database_from_before_last(self):
        r = self.run_script('restore.sh', A, '--yes')
        self.assertEqual(r.returncode, 0, r.stderr)
        calls = [' '.join(c) for c in self.calls()]
        self.assertIn('dropdb', calls[-1])
        self.assertIn('"$OLD"', calls[-1])
        self.assertTrue(any('wget' in c for c in calls[:-1]))
        self.assertFalse(any('IF EXISTS' in c or '--if-exists' in c for c in calls))  # never drop a kept database

    def test_failed_database_restore_never_stops_site(self):
        r = self.run_script('restore.sh', A, '--yes', mode='pg-restore-fails')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('当前的数据没有变化', r.stderr)
        calls = self.calls()
        self.assertFalse(any('stop' in c for c in calls))
        self.assertTrue('dropdb' in ' '.join(calls[-1]) and '"$NEW"' in ' '.join(calls[-1]))

    def test_explicit_id_db_only_skips_resolution_and_files(self):
        r = self.run_script('restore.sh', A, '--yes', '--db-only')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.root / 'database_dump').read_text().strip(), 'database:' + A)
        self.assertFalse(any('snapshots' in c or 'restore' in c for c in self.calls()))
        self.assertFalse((self.root / 'files_snapshot').exists())


if __name__ == '__main__':
    unittest.main()
