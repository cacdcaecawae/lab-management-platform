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
elif 'pg_restore' in command:
    (root / 'database_dump').write_text(sys.stdin.read())
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
        (self.root / 'scripts/backup.sh').write_text("echo 'snapshot abcdef12 saved'\n")
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

    def test_explicit_id_db_only_skips_resolution_and_files(self):
        r = self.run_script('restore.sh', A, '--yes', '--db-only')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.root / 'database_dump').read_text().strip(), 'database:' + A)
        self.assertFalse(any('snapshots' in c or 'restore' in c for c in self.calls()))
        self.assertFalse((self.root / 'files_snapshot').exists())


if __name__ == '__main__':
    unittest.main()
