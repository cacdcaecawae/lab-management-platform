"""Run scripts/install.sh with git and docker doubles: no network, Docker or database."""
import json
import os
from pathlib import Path
import re
import shlex
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
  rev-parse) printf '%b' "$TAGS" | grep -qx "${4#refs/tags/}" || exit 1 ;;
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
def env_file(key):
    return [l.split('=', 1)[1] for l in pathlib.Path('.env').read_text().splitlines() if l.startswith(key + '=')][-1]
volumes = root / 'volumes'  # what Compose has created, like the Docker daemon remembers it
def create(*names):
    with volumes.open('a') as f:
        f.write(''.join(n + '\n' for n in names))
if args[:1] == ['info'] and mode == 'docker-down':
    sys.exit(1)
if args[:2] == ['volume', 'ls']:
    if mode == 'volume-query-fails':
        sys.exit(1)
    labelled = any(a.startswith('label=') for a in args)
    if mode == 'existing-volumes' or (mode == 'unlabeled-volume' and not labelled):
        print('infra_pgdata')  # unlabeled: created by hand, or moved back from another machine
    if volumes.exists():
        print(volumes.read_text(), end='')
if args[0] == 'compose' and 'config' in args and '--images' in args:
    print('postgres:17-alpine\nghcr.io/x/backend:v\nghcr.io/x/web:v\nrestic/restic:0.19.1')
elif args[-1:] == ['config']:
    print('name: infra\nservices:\n  backend:\n    volumes:\n      - source: labdata\n'
          'volumes:\n  labdata:\n    name: infra_labdata\n  pgdata:\n    name: infra_pgdata\n  static:\n    name: infra_static')
if 'pull' in args and mode == 'pull-fails':
    sys.exit(1)
if args[0] == 'compose' and 'run' in args:
    create('infra_labdata')  # Compose creates the volumes a service mounts before running it
if args[-1] == 'init' and mode == 'init-fails-once' and not (root / 'init_failed').exists():  # e.g. not writable
    (root / 'init_failed').touch()
    sys.exit(1)
if 'up' in args:
    create('infra_labdata', 'infra_pgdata', 'infra_static')
    keys = ('APP_VERSION', 'HTTP_PORT', 'COMPOSE_FILE', 'COMPOSE_PROJECT_NAME', 'ENV_FILE', 'IMAGE_PREFIX',
            'POSTGRES_USER', 'POSTGRES_DB', 'MAX_UPLOAD_SIZE')
    (root / 'up_env').write_text(json.dumps({k: os.environ.get(k) for k in keys}))
if 'ps' in args and '--format' in args:
    service = args[-1]
    version = 'v0.0.1' if mode == 'old-image' and service == 'web' else env_file('APP_VERSION')
    print(f'ghcr.io/x/{service}:{version}')
if 'port' in args:
    bind = env_file('HTTP_PORT')
    p = bind.rsplit(':', 1)[-1]
    print('0.0.0.0:' + p if mode == 'exposed' else bind if ':' in bind else f'0.0.0.0:{p}\n[::]:{p}')
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
        for name in ('server.env.example', 'docker-compose.prod.yml'):
            shutil.copyfile(ROOT / 'infra' / name, fixture / 'infra' / name)
        (self.root / 'bin').mkdir()
        self.executable('git', GIT)
        self.executable('docker', '#!' + sys.executable + '\n' + DOCKER)
        self.executable('sleep', '#!/bin/bash\nexit 0\n')
        # v0.11.0 is tagged but not released yet (its images may still be building, or the release failed).
        self.release('v0.10.0')
        self.env = dict(os.environ, PATH=str(self.root / 'bin') + os.pathsep + os.environ['PATH'],
                        TEST_ROOT=str(self.root), FIXTURE=str(fixture), TAGS='v0.2.0\\nv0.10.0\\nv0.11.0\\nv1.0\\n',
                        LAB_RELEASE_API=(self.root / 'latest.json').as_uri())
        for key in ('ENV_FILE', 'COMPOSE_FILE', 'COMPOSE_PROJECT_NAME', 'MODE', 'IMAGE_PREFIX', 'LAB_REPO',
                    'APP_VERSION', 'HTTP_PORT'):
            self.env.pop(key, None)
        self.dir = self.root / 'site' / 'lab'
        self.dir.parent.mkdir()

    def executable(self, name, text):
        path = self.root / 'bin' / name
        path.write_text(text)
        path.chmod(0o755)

    def release(self, tag):
        """GitHub's latest-release JSON (pretty printed, a tag_name look-alike inside the body)."""
        body = {'tag_name': tag, 'body': 'not "tag_name": "v9.9.9"', 'draft': False}
        (self.root / 'latest.json').write_text(json.dumps(body, indent=2))

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

    def started(self):
        return any('"up"' in c for c in self.calls())

    def test_fresh_install_writes_private_settings_and_creates_ops(self):
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        env = self.settings()
        self.assertEqual(env['APP_VERSION'], 'v0.10.0')  # the published release, not the newer tag v0.11.0
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
        self.assertFalse((self.dir / '.install-lock').exists())
        self.assertEqual([p.name for p in self.dir.glob('.env.*')], [])
        calls = self.calls()
        pull = next(i for i, c in enumerate(calls) if '"pull", "backend", "web"' in c)
        init = next(i for i, c in enumerate(calls) if c.startswith('["run"') and c.endswith('"restic/restic:0.19.1", "init"]'))
        up = next(i for i, c in enumerate(calls) if c.endswith('"up", "-d", "--no-build"]'))
        self.assertLess(pull, init)
        self.assertLess(init, up)
        self.assertIn(f'"{self.root / "site" / "lab-backup"}:/repo"', calls[init])  # nothing but the backup directory
        self.assertFalse(any(c.startswith('["compose"') and '"run"' in c for c in calls))
        password = re.search(r'初始密码：\s+([0-9a-f]{16})', r.stdout).group(1)
        self.assertIn(f'create_superuser("ops", password="{password}")', (self.root / 'shell_input').read_text())
        self.assertFalse(any(p in c for c in calls for p in (password, env['BACKUP_PASSWORD'])))  # no command line
        for secret in secrets:
            self.assertNotIn(secret, r.stdout + r.stderr)

    def test_exported_variables_never_override_the_generated_settings(self):
        # POSTGRES_USER, POSTGRES_DB and MAX_UPLOAD_SIZE are not in .env: a later update from a clean shell uses the
        # Compose defaults, so the install must too.
        self.env.update(HTTP_PORT='18090', APP_VERSION='v0.9.0', COMPOSE_PROJECT_NAME='other',
                        COMPOSE_FILE='infra/docker-compose.prod.yml:infra/docker-compose.https.yml', ENV_FILE='other.env',
                        POSTGRES_USER='other', POSTGRES_DB='other', MAX_UPLOAD_SIZE='1')
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads((self.root / 'up_env').read_text()), {
            'APP_VERSION': None, 'HTTP_PORT': None, 'COMPOSE_PROJECT_NAME': None, 'IMAGE_PREFIX': None,
            'POSTGRES_USER': None, 'POSTGRES_DB': None, 'MAX_UPLOAD_SIZE': None,
            'COMPOSE_FILE': 'infra/docker-compose.prod.yml', 'ENV_FILE': '.env'})
        self.assertEqual(self.settings()['HTTP_PORT'], '127.0.0.1:8090')

    def test_success_needs_the_release_images_and_the_expected_address(self):
        for mode in ('old-image', 'exposed'):
            with self.subTest(mode=mode):
                for leftover in (self.dir, self.root / 'site' / 'lab-backup'):
                    shutil.rmtree(leftover, ignore_errors=True)
                for leftover in ('shell_input', 'volumes'):
                    (self.root / leftover).unlink(missing_ok=True)
                r = self.install(mode=mode)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn('不是' if mode == 'old-image' else '地址不对', r.stderr)
                self.assertNotIn('安装完成', r.stdout)
                self.assertFalse((self.root / 'shell_input').exists())  # no ops account on a wrong site

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

    def test_printed_commands_survive_spaces_in_the_path(self):
        self.dir = self.root / 'site' / "my lab's"
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        cron = re.search(r'^\s+30 2 \* \* \* (.+)$', r.stdout, re.M).group(1)
        words = shlex.split(cron)
        self.assertEqual(words[:2], ['cd', str(self.dir)])
        self.assertEqual(words[-2:], [f'{self.dir}-backup.log', '2>&1'])
        update = re.search(r'更新：\s+(.+)$', r.stdout, re.M).group(1)
        self.assertEqual(shlex.split(update)[:2], ['cd', str(self.dir)])

    def test_installed_directory_is_never_touched(self):
        shutil.copytree(self.env['FIXTURE'], self.dir)
        (self.dir / '.env').write_text('APP_VERSION=v0.1.0\n')
        r = self.install()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('已经安装过', r.stderr)
        self.assertEqual((self.dir / '.env').read_text(), 'APP_VERSION=v0.1.0\n')
        self.assertFalse(any('"config"' in c or '"up"' in c for c in self.calls()))  # the stack is never touched

    def test_an_install_in_progress_is_left_alone(self):
        shutil.copytree(self.env['FIXTURE'], self.dir)
        (self.dir / '.install-lock').mkdir()
        (self.dir / '.env.tmp').write_text('theirs')
        r = self.install()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('另一个安装正在进行', r.stderr)
        self.assertTrue((self.dir / '.install-lock').is_dir())  # not ours to remove
        self.assertEqual((self.dir / '.env.tmp').read_text(), 'theirs')
        self.assertFalse((self.dir / '.env').exists())
        self.assertFalse(self.started())

    def test_run_from_inside_a_clone_installs_that_clone(self):
        shutil.copytree(self.env['FIXTURE'], self.dir)
        stale = self.dir / '.env.tmp'  # someone else's file under the old fixed temporary name
        stale.write_text('world readable')
        stale.chmod(0o644)
        r = self.install(script=self.dir / 'scripts/install.sh')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(stat.S_IMODE((self.dir / '.env').stat().st_mode), 0o600)
        self.assertEqual(stale.read_text(), 'world readable')
        self.assertFalse(any(c.startswith('git clone') for c in self.calls()))

    def test_failures_before_start_leave_nothing_behind(self):
        cases = (('existing-volumes', None), ('unlabeled-volume', None), ('volume-query-fails', None),
                 ('pull-fails', None), ('', 'no release'), ('', 'release without tag'))
        for mode, release in cases:
            with self.subTest(mode=mode, release=release):
                for leftover in (self.dir, self.root / 'site' / 'lab-backup'):
                    shutil.rmtree(leftover, ignore_errors=True)
                for leftover in ('calls', 'volumes'):
                    (self.root / leftover).unlink(missing_ok=True)
                self.release('v0.10.0')
                if release == 'no release':
                    (self.root / 'latest.json').unlink()
                elif release == 'release without tag':
                    self.release('v0.12.0')
                r = self.install(mode=mode)
                self.assertNotEqual(r.returncode, 0)
                self.assertFalse((self.dir / '.env').exists())
                self.assertEqual([p.name for p in self.dir.glob('.env.*')], [])
                self.assertFalse((self.dir / '.install-lock').exists())
                self.assertFalse((self.root / 'site' / 'lab-backup').exists())
                self.assertFalse(self.started())
                self.assertNotIn('down -v', r.stderr)  # never suggest deleting volumes it did not create

    def test_failed_backup_init_can_simply_be_retried(self):
        r = self.install(mode='init-fails-once')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('备份仓库初始化失败', r.stderr)
        self.assertFalse((self.dir / '.env').exists())
        self.assertFalse((self.root / 'site' / 'lab-backup').exists())
        self.assertFalse((self.root / 'volumes').exists())  # no data volume left to block the retry
        r = self.install(mode='init-fails-once')  # the cause is fixed: the second init succeeds
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_failed_start_keeps_settings_and_says_how_to_retry(self):
        r = self.install(mode='unhealthy')
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue((self.dir / '.env').exists())
        # The volumes it names were checked to be absent before the install; never a blanket `down -v`.
        self.assertIn('docker volume rm infra_labdata infra_pgdata infra_static', r.stderr)
        self.assertNotIn('down -v', r.stderr)
        self.assertFalse((self.root / 'shell_input').exists())
        self.assertFalse((self.dir / '.install-lock').exists())

    def test_bad_arguments_and_missing_docker_stop_before_anything(self):
        for args, mode in ((['--host', 'http://x'], ''), (['--port', '0'], ''), (['--bogus'], ''), ([], 'docker-down')):
            with self.subTest(args=args, mode=mode):
                r = self.install(*args, mode=mode)
                self.assertNotEqual(r.returncode, 0)
                self.assertFalse(self.dir.exists())


if __name__ == '__main__':
    unittest.main()
