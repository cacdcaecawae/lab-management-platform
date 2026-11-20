"""Run scripts/install.sh with git and docker doubles: no network, Docker or database."""
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]

GIT = r'''#!/bin/bash
echo "git $*" >>"$TEST_ROOT/calls"
[ "$1" != -C ] || shift 2
case $1 in
  clone) cp -r "$FIXTURE" "${@: -1}" ;;
  tag) printf '%b' "$TAGS" | sort -rV ;;  # like --sort=-v:refname
  checkout) echo "$3" >"$TEST_ROOT/checked_out" ;;
esac
exit 0
'''

DOCKER = r'''
import json, os, pathlib, sys
root = pathlib.Path(os.environ['TEST_ROOT'])
args = sys.argv[1:]
with (root / 'calls').open('a') as f:
    f.write(json.dumps(args) + '\n')
mode = os.environ.get('MODE', '')
if args[:1] == ['info'] and mode == 'docker-down':
    sys.exit(1)
if args[:2] == ['volume', 'ls'] and mode == 'existing-volumes':
    print('infra_pgdata')
if args[-1:] == ['config']:
    print('name: infra\nservices:')
if 'nc' in args:
    for line in sys.stdin:
        if not line.strip():
            break
    print('HTTP/1.1 ' + ('502' if mode == 'unhealthy' else '204') + ' Test\r\n')
if 'shell' in args:
    (root / 'shell_input').write_text(sys.stdin.read())
'''


class Install(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # What `git clone` produces: the scripts and the env template of the release.
        fixture = self.root / 'fixture'
        (fixture / '.git').mkdir(parents=True)
        (fixture / 'infra').mkdir()
        shutil.copytree(ROOT / 'scripts', fixture / 'scripts', ignore=shutil.ignore_patterns('tests', '__pycache__'))
        shutil.copyfile(ROOT / 'infra/server.env.example', fixture / 'infra/server.env.example')
        (self.root / 'bin').mkdir()
        self.executable('git', GIT)
        self.executable('docker', '#!' + sys.executable + '\n' + DOCKER)
        self.executable('sleep', '#!/bin/bash\nexit 0\n')
        self.env = dict(os.environ, PATH=str(self.root / 'bin') + os.pathsep + os.environ['PATH'],
                        TEST_ROOT=str(self.root), FIXTURE=str(fixture), TAGS='v0.2.0\\nv0.10.0\\nv1.0\\nv0.9.1\\n')
        for key in ('ENV_FILE', 'COMPOSE_FILE', 'COMPOSE_PROJECT_NAME', 'MODE', 'IMAGE_PREFIX', 'LAB_REPO'):
            self.env.pop(key, None)
        self.dir = self.root / 'site' / 'lab'
        self.dir.parent.mkdir()

    def executable(self, name, text):
        path = self.root / 'bin' / name
        path.write_text(text)
        path.chmod(0o755)

    def install(self, *args, mode='', script=None):
        """Piped like `curl ... | bash -s -- args`, unless a script file inside a clone is given."""
        env = dict(self.env, MODE=mode)
        if script:
            return subprocess.run(['bash', str(script), *args], env=env, text=True, capture_output=True, timeout=30)
        return subprocess.run(['bash', '-s', '--', '--dir', str(self.dir), *args], input=(ROOT / 'scripts/install.sh').read_text(),
                              env=env, text=True, capture_output=True, timeout=30)

    def settings(self):
        return dict(line.split('=', 1) for line in (self.dir / '.env').read_text().splitlines()
                    if '=' in line and not line.startswith('#'))

    def calls(self):
        path = self.root / 'calls'
        return path.read_text().splitlines() if path.exists() else []

    def test_fresh_install_writes_private_settings_and_creates_ops(self):
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        env = self.settings()
        self.assertEqual(env['APP_VERSION'], 'v0.10.0')  # newest by version order; "v1.0" is not a release tag
        self.assertEqual((self.root / 'checked_out').read_text().strip(), 'v0.10.0')
        secrets = [env[k] for k in ('DJANGO_SECRET_KEY', 'POSTGRES_PASSWORD', 'BACKUP_PASSWORD')]
        self.assertTrue(all(re.fullmatch('[0-9a-f]{64}', s) for s in secrets), secrets)
        self.assertEqual(len(set(secrets)), 3)
        self.assertNotIn('换成', (self.dir / '.env').read_text())
        self.assertEqual(stat.S_IMODE((self.dir / '.env').stat().st_mode), 0o600)
        self.assertEqual(env['DJANGO_SECURE_COOKIES'], '0')  # plain HTTP must still let people log in
        self.assertEqual(env['HTTP_PORT'], '127.0.0.1:8090')  # this machine only by default
        self.assertEqual(env['DJANGO_ALLOWED_HOSTS'], 'localhost,127.0.0.1')
        self.assertEqual(env['DJANGO_CSRF_TRUSTED_ORIGINS'], 'http://localhost:8090,http://127.0.0.1:8090')
        self.assertEqual(env['BACKUP_REPO'], str(self.root / 'site' / 'lab-backup'))
        self.assertTrue((self.root / 'site' / 'lab-backup').is_dir())
        calls = self.calls()
        init = next(i for i, c in enumerate(calls) if '"restic", "init"' in c)
        up = next(i for i, c in enumerate(calls) if c.endswith('"up", "-d"]'))
        self.assertLess(init, up)
        password = re.search(r'初始密码：\s+([0-9a-f]{16})', r.stdout).group(1)
        self.assertIn(f'create_superuser("ops", password="{password}")', (self.root / 'shell_input').read_text())
        self.assertFalse(any(password in c for c in calls))  # never on a command line
        for secret in secrets:
            self.assertNotIn(secret, r.stdout + r.stderr)

    def test_host_opens_the_port_and_port_80_has_no_suffix(self):
        r = self.install('--host', '192.168.1.20', '--port', '80')
        self.assertEqual(r.returncode, 0, r.stderr)
        env = self.settings()
        self.assertEqual(env['HTTP_PORT'], '80')
        self.assertEqual(env['DJANGO_ALLOWED_HOSTS'], '192.168.1.20,localhost,127.0.0.1')
        self.assertEqual(env['DJANGO_CSRF_TRUSTED_ORIGINS'], 'http://192.168.1.20,http://localhost,http://127.0.0.1')
        self.assertEqual(env['SITE_URL'], 'http://192.168.1.20')

    def test_registry_mirror_is_kept_for_later_updates(self):
        self.env['IMAGE_PREFIX'] = 'registry.example.cn/lab'
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.settings()['IMAGE_PREFIX'], 'registry.example.cn/lab')

    def test_installed_directory_is_never_touched(self):
        shutil.copytree(self.env['FIXTURE'], self.dir)
        (self.dir / '.env').write_text('APP_VERSION=v0.1.0\n')
        r = self.install()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('已经安装过', r.stderr)
        self.assertEqual((self.dir / '.env').read_text(), 'APP_VERSION=v0.1.0\n')
        self.assertFalse(any('"config"' in c or '"up"' in c for c in self.calls()))  # the stack is never touched

    def test_run_from_inside_a_clone_installs_that_clone(self):
        shutil.copytree(self.env['FIXTURE'], self.dir)
        r = self.install(script=self.dir / 'scripts/install.sh')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.dir / '.env').exists())
        self.assertFalse(any(c.startswith('git clone') for c in self.calls()))

    def test_failures_before_start_leave_nothing_behind(self):
        for mode, tags in (('existing-volumes', None), ('', '')):
            with self.subTest(mode=mode, tags=tags):
                shutil.rmtree(self.dir, ignore_errors=True)
                (self.root / 'calls').unlink(missing_ok=True)
                if tags is not None:
                    self.env['TAGS'] = tags
                r = self.install(mode=mode)
                self.assertNotEqual(r.returncode, 0)
                self.assertFalse((self.dir / '.env').exists())
                self.assertFalse((self.root / 'site' / 'lab-backup').exists())
                self.assertFalse(any(c.endswith('"up", "-d"]') for c in self.calls()))

    def test_failed_start_keeps_settings_and_says_how_to_retry(self):
        r = self.install(mode='unhealthy')
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue((self.dir / '.env').exists())
        self.assertIn('down -v', r.stderr)
        self.assertFalse((self.root / 'shell_input').exists())

    def test_bad_arguments_and_missing_docker_stop_before_anything(self):
        for args, mode in ((['--host', 'http://x'], ''), (['--port', '0'], ''), (['--bogus'], ''), ([], 'docker-down')):
            with self.subTest(args=args, mode=mode):
                r = self.install(*args, mode=mode)
                self.assertNotEqual(r.returncode, 0)
                self.assertFalse(self.dir.exists())


if __name__ == '__main__':
    unittest.main()
