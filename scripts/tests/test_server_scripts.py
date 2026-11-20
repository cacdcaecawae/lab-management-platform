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
if 'cat config' in command:
    assert 'BACKUP_REPO_ID' not in os.environ
    if mode == 'bad-repo':
        print('untrusted backend diagnostics', file=sys.stderr)
        sys.exit(1)
    config = {'version': 2, 'id': ('b' if mode == 'other-repo' else 'a') * 64}
    print(json.dumps(config, indent=2) if mode != 'malformed-config' else '{"id": "wrong"}')
    sys.exit(0)
if 'pg_dump' in command:
    print('synthetic dump')
    sys.exit(0)
if args[-2:] == ['config', '--quiet'] and mode == 'bad-compose':
    sys.exit(1)
if '--single-transaction' in command and 'psql' in command:
    (root / 'rename_sql').write_text(sys.stdin.read())
    sys.exit(1 if mode in ('swap-fails', 'swap-ambiguous', 'changed-swap-fails') else 0)
if 'psql' in command and '-qtA' in command:
    sys.stdin.read()
    print('unknown' if mode == 'swap-ambiguous' else 'original')
    sys.exit(0)
if 'snapshots --json' in command:
    print(os.environ['SNAPSHOT_JSON'])
    sys.exit(1 if mode == 'query-fails' else 0)
if 'restic ls' in command:
    assert args[-1].endswith(':/data/files')
    sys.exit(1 if mode == 'missing-file-tree' else 0)
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
    for service in args[args.index('--format') + 2:]:
        print(f"ghcr.io/x/{service}:{(root / service).read_text()}")
elif 'FROM django_migrations' in command:
    if mode == 'unknown-migrations' and (root / 'up_count').exists():
        sys.exit(1)
    print('["core","new"]' if mode in ('changed-migrations', 'changed-swap-fails') and (root / 'up_count').exists() else '["core","old"]')
elif args[-2:] == ['up', '-d'] or args[-4:] == ['up', '-d', 'backend', 'web']:
    counter = root / 'up_count'
    n = int(counter.read_text()) + 1 if counter.exists() else 1
    counter.write_text(str(n))
    if mode in ('start-fails', 'unknown-migrations', 'changed-migrations', 'changed-swap-fails') and n == 1:
        print('recreation failed; old containers still serving', file=sys.stderr)
        sys.exit(1)
    version = os.environ.get('APP_VERSION') or [
        line.split('=', 1)[1] for line in (root / '.env').read_text().splitlines() if line.startswith('APP_VERSION=')][-1]
    (root / 'backend').write_text(version)
    (root / 'web').write_text('v0.9.9' if mode == 'wrong-web' or (mode == 'stale-web' and n == 1) else version)
elif 'nc' in args or 'curl' in args:
    tls = 'curl' in args
    request = args[-1] if tls else ''
    if not tls:
        for line in sys.stdin:
            if not line.strip():
                break
            request += line
    with (root / 'health_requests').open('a') as f:
        f.write(json.dumps(request) + '\n')
    count = int((root / 'up_count').read_text()) if (root / 'up_count').exists() else 0
    path = '/api/auth/csrf/' if ' /api/auth/csrf/ ' in request else '/healthz'
    code = '204'
    if mode == 'unhealthy' and count == 1:
        code = '502'
    elif mode == 'redirect':
        code = '301'
    elif mode == 'tls-cert-failure':
        assert tls
        print('204', end='')  # even if a transport failure yields output, it must not pass
        sys.exit(60)
    elif mode in ('legacy-http', 'spa-only'):
        code = '200' if path == '/healthz' or mode == 'spa-only' else '204'
    if tls:
        print(code, end='')
    else:
        print('HTTP/1.1 ' + code + ' Test\r\nConnection: close\r\n')
        if code == '301':
            print('HTTP/1.1 204 Not the first status')
        sys.stdout.flush()
        sys.stdin.read()  # Compose exec waits for the caller to close stdin.
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
            'case "$MODE" in INT|TERM) kill -"$MODE" "$PPID";; esac\n'
            '[ "$MODE" != missing-snapshot ] || exit 0\n'
            "echo 'snapshot abcdef12 saved'\n"
            '[ "$MODE" != incomplete-backup ] || exit 3\n')
        (self.root / 'repo').mkdir()
        (self.root / '.env').write_text(f'APP_VERSION=v0.1.0\nBACKUP_REPO={self.root / "repo"}\nBACKUP_PASSWORD=dummy\n')
        self.executable('docker', '#!' + sys.executable + '\n' + DOCKER)
        self.executable('git', '#!/bin/bash\n[ "$1" != symbolic-ref ] || echo main\nexit 0\n')
        self.executable('sleep', '#!/bin/bash\nexit 0\n')
        self.env = dict(os.environ, PATH=str(self.root / 'bin') + os.pathsep + os.environ['PATH'],
                        TEST_ROOT=str(self.root), SNAPSHOT_JSON=json.dumps([{'id': A}]))
        # Do not inherit an operator's target-stack overrides.
        for key in ('ENV_FILE', 'COMPOSE_FILE', 'COMPOSE_PROJECT_NAME', 'APP_VERSION', 'MODE', 'HTTPS_DOMAIN', 'DJANGO_ALLOWED_HOSTS'):
            self.env.pop(key, None)

    def executable(self, name, text):
        path = self.root / 'bin' / name
        path.write_text(text)
        path.chmod(0o755)

    def run_script(self, name, *args, mode=''):
        return subprocess.run(['bash', str(self.root / 'scripts' / name), *args],
                              env=dict(self.env, MODE=mode), text=True, capture_output=True, timeout=20)

    def calls(self):
        return [json.loads(line) for line in (self.root / 'calls').read_text().splitlines()] if (self.root / 'calls').exists() else []

    def test_failed_start_cannot_succeed_from_old_healthy_endpoint(self):
        r = self.run_script('update.sh', 'v0.2.0', mode='start-fails')
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertNotIn('已更新到', r.stdout)
        self.assertIn('APP_VERSION=v0.1.0', (self.root / '.env').read_text())
        self.assertEqual((self.root / 'up_count').read_text(), '2')
        calls = self.calls()
        up = [i for i, c in enumerate(calls) if c[-2:] == ['up', '-d']]
        self.assertFalse(any('nc' in c for c in calls[up[0] + 1:up[1]]))

    def test_successful_start_and_health_still_succeed(self):
        r = self.run_script('update.sh', 'v0.2.0')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('已更新到 v0.2.0', r.stdout)

    def health_requests(self):
        return [json.loads(line) for line in (self.root / 'health_requests').read_text().splitlines()]

    def enable_tls(self):
        self.env['COMPOSE_FILE'] = 'infra/docker-compose.prod.yml:infra/docker-compose.https.yml'
        with (self.root / '.env').open('a') as f:
            f.write('HTTPS_DOMAIN=lab.synthetic.test\nDJANGO_ALLOWED_HOSTS=legacy.test\n')

    def test_tls_update_and_restore_probe_real_https_listener_using_certificate_name(self):
        self.enable_tls()
        r = self.run_script('update.sh', 'v0.2.0')
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.run_script('restore.sh', A, '--db-only', '--yes')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.health_requests(), ['https://lab.synthetic.test/healthz'] * 2)
        probes = [c for c in self.calls() if 'curl' in c]
        self.assertEqual(len(probes), 2)
        for probe in probes:
            self.assertIn('lab.synthetic.test:443:127.0.0.1', probe)
            self.assertNotIn('--insecure', probe)
            self.assertNotIn('-L', probe)

    def test_tls_missing_target_config_is_rejected_before_pull_backup_or_stop(self):
        self.enable_tls()
        # Simulate a tag that has the overlay but lacks a bind-mounted template.
        self.executable('git', '#!/bin/bash\n[ "$1" != symbolic-ref ] || echo main\n'
                        '[[ "$*" != cat-file*"infra/nginx.https.conf.template" ]]\n')
        r = self.run_script('update.sh', 'v0.2.0')
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn('未停止网站', r.stderr)
        self.assertFalse((self.root / 'calls').exists())
        self.assertIn('APP_VERSION=v0.1.0', (self.root / '.env').read_text())

    def test_redirect_is_never_a_healthy_response_or_legacy_fallback(self):
        r = self.run_script('restore.sh', A, '--db-only', '--yes', mode='redirect')
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertTrue(self.health_requests())
        self.assertTrue(all(x.startswith('GET /healthz HTTP/1.1') for x in self.health_requests()))

    def test_tls_never_falls_back_to_plain_http_or_ignores_transport_errors(self):
        self.enable_tls()
        for mode in ('redirect', 'tls-cert-failure', 'spa-only'):
            with self.subTest(mode=mode):
                (self.root / 'health_requests').unlink(missing_ok=True)
                r = self.run_script('restore.sh', A, '--db-only', '--yes', mode=mode)
                self.assertNotEqual(r.returncode, 0, r.stdout)
                self.assertTrue(self.health_requests())
                self.assertEqual(set(self.health_requests()), {'https://lab.synthetic.test/healthz'})

    def test_legacy_plain_http_rollback_needs_backend_204_not_spa_200(self):
        for mode, result in [('legacy-http', 0), ('spa-only', 1)]:
            with self.subTest(mode=mode):
                (self.root / 'health_requests').unlink(missing_ok=True)
                r = self.run_script('restore.sh', A, '--db-only', '--yes', mode=mode)
                self.assertEqual(r.returncode, result, r.stderr)
                self.assertEqual([line.split()[1] for line in self.health_requests()[:2]],
                                 ['/healthz', '/api/auth/csrf/'])

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
        self.assertEqual((self.root / 'web').read_text(), 'v0.1.0')

    def test_snapshot_printed_before_backup_error_cannot_authorize_update(self):
        r = self.run_script('update.sh', 'v0.2.0', mode='incomplete-backup')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('snapshot abcdef12 saved', r.stdout)
        self.assertIn('网站已重新启动', r.stderr)
        self.assertEqual((self.root / 'up_count').read_text(), '1')
        self.assertEqual((self.root / 'backend').read_text(), 'v0.1.0')

    def test_interruption_during_backup_resumes_old_site(self):
        for signal, code in [('INT', 130), ('TERM', 143)]:
            with self.subTest(signal=signal):
                r = self.run_script('update.sh', 'v0.2.0', mode=signal)
                self.assertEqual(r.returncode, code, r.stderr)
                self.assertIn('网站已重新启动', r.stderr)
                self.assertEqual((self.root / 'web').read_text(), 'v0.1.0')

    def test_successful_backup_without_snapshot_resumes_old_site(self):
        r = self.run_script('update.sh', 'v0.2.0', mode='missing-snapshot')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('快照编号', r.stderr)
        self.assertIn('网站已重新启动', r.stderr)

    def test_checkout_failure_after_stop_resumes_old_site(self):
        self.executable('git', '#!/bin/bash\n[ "$1" != symbolic-ref ] || echo main\n'
                        '[ "$*" != "checkout --quiet refs/tags/v0.2.0" ]\n')
        r = self.run_script('update.sh', 'v0.2.0')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('网站已重新启动', r.stderr)
        self.assertEqual((self.root / 'web').read_text(), 'v0.1.0')

    def test_shell_version_does_not_override_release(self):
        self.env['APP_VERSION'] = 'v0.3.0'
        r = self.run_script('update.sh', 'v0.2.0')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.root / 'web').read_text(), 'v0.2.0')

    def test_env_write_failure_restores_checkout_and_old_version(self):
        (self.root / 'bin/git').unlink()

        def git(*args):
            return subprocess.check_output(['git', '-c', 'user.name=test', '-c', 'user.email=test@localhost',
                                            *args], cwd=self.root, text=True).strip()

        git('init', '-q', '-b', 'main')
        git('remote', 'add', 'origin', '.')
        git('add', 'scripts/update.sh')
        git('commit', '-qm', 'old release')
        git('tag', 'v0.1.0')
        git('checkout', '-q', '--detach')
        (self.root / 'scripts/update.sh').write_text('exit 42\n')
        git('commit', '-qam', 'new release replaces the running script')
        git('tag', 'v0.2.0')
        git('checkout', '-q', 'main')
        self.executable('sed', '#!/bin/bash\n/bin/sed "$@" || exit 1\n'
                        '[[ $1 != -i || $2 != *v0.2.0* ]]\n')
        r = self.run_script('update.sh', 'v0.2.0')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('网站已重新启动', r.stderr)
        self.assertEqual(git('symbolic-ref', '--short', 'HEAD'), 'main')
        self.assertIn('APP_VERSION=v0.1.0', (self.root / '.env').read_text())
        self.assertEqual((self.root / 'web').read_text(), 'v0.1.0')

    def test_old_images_answering_is_not_an_update(self):
        self.env['APP_VERSION'] = 'v0.3.0'
        r = self.run_script('update.sh', 'v0.2.0', mode='stale-web')
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn('已更新到', r.stdout)
        self.assertIn('已退回 v0.1.0', r.stderr)
        self.assertEqual((self.root / 'backend').read_text(), 'v0.1.0')

    def test_healthy_wrong_web_image_cannot_confirm_rollback(self):
        r = self.run_script('update.sh', 'v0.2.0', mode='wrong-web')
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn('已退回', r.stderr)
        self.assertEqual((self.root / 'up_count').read_text(), '2')

    def test_health_failure_still_rolls_back(self):
        r = self.run_script('update.sh', 'v0.2.0', mode='unhealthy')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('已退回 v0.1.0', r.stderr)
        self.assertIn('APP_VERSION=v0.1.0', (self.root / '.env').read_text())

    def test_unknown_migration_state_stops_rollback(self):
        r = self.run_script('update.sh', 'v0.2.0', mode='unknown-migrations')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('无法核对数据库迁移', r.stderr)
        self.assertFalse(any('dump' in c or 'restore' in c for c in self.calls()))
        self.assertEqual((self.root / 'up_count').read_text(), '1')

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
        self.assertTrue(any('nc' in c for c in calls[:-1]))
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


    def enable_nas(self, data):
        self.env['COMPOSE_FILE'] = 'infra/docker-compose.prod.yml:infra/docker-compose.nas.yml'
        data.mkdir(exist_ok=True)
        with (self.root / '.env').open('a') as f:
            f.write(f'LAB_NAS_ROOT={data}\n')

    def test_nas_attach_and_repo_must_not_overlap(self):
        self.enable_nas(self.root / 'repo')
        r = self.run_script('update.sh', 'v0.2.0')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('不能相互嵌套', r.stderr)
        self.assertEqual(self.calls(), [])

    def test_nas_release_without_overlay_support_fails_before_any_docker(self):
        self.enable_nas(self.root / 'live-data')
        self.executable('git', '#!/bin/bash\n[[ "$*" != cat-file*refs/tags*v0.2.0*nas-restic.sh ]]\n')
        r = self.run_script('update.sh', 'v0.2.0')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('不支持 NAS 主存储', r.stderr)
        self.assertEqual(self.calls(), [])

    def test_missing_upload_tree_does_not_stop_or_change_live_database(self):
        r = self.run_script('restore.sh', A, '--yes', mode='missing-file-tree')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('未停止网站', r.stderr)
        self.assertFalse(any('stop' in c or 'dump' in c or 'restore' in c for c in self.calls()))

    def test_restore_deletion_targets_only_attachment_tree(self):
        r = self.run_script('restore.sh', A, '--yes')
        self.assertEqual(r.returncode, 0, r.stderr)
        restore, = [c for c in self.calls() if 'restore' in c]
        self.assertEqual(restore[-4:], [A + ':/data/files', '--target', '/data/files', '--delete'])

    def test_preflight_failures_never_stop_or_start_anything(self):
        for mode in ('bad-repo', 'bad-compose'):
            with self.subTest(mode=mode):
                r = self.run_script('update.sh', 'v0.2.0', mode=mode)
                self.assertNotEqual(r.returncode, 0)
                self.assertFalse(any('stop' in c or 'up' in c for c in self.calls()))

    def test_no_implicit_init_when_repository_is_unreadable(self):
        shutil.copyfile(ROOT / 'scripts/backup.sh', self.root / 'scripts/backup.sh')
        r = self.run_script('backup.sh', mode='bad-repo')
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue(any('cat' in c for c in self.calls()))
        self.assertFalse(any('init' in c or 'exec' in c for c in self.calls()))

    def test_init_requires_an_existing_empty_directory(self):
        shutil.copyfile(ROOT / 'scripts/backup.sh', self.root / 'scripts/backup.sh')
        (self.root / 'repo/existing').touch()
        r = self.run_script('backup.sh', '--init')
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.calls(), [])
        (self.root / 'repo/existing').unlink()
        r = self.run_script('backup.sh', '--init')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self.calls()), 1)
        self.assertIn('init', self.calls()[0])

    def test_missing_nas_mount_refuses_even_existing_directory(self):
        with (self.root / '.env').open('a') as f:
            f.write(f'BACKUP_MOUNTPOINT={self.root}\n')
        self.executable('mountpoint', '#!/bin/bash\nexit 1\n')
        shutil.copyfile(ROOT / 'scripts/backup.sh', self.root / 'scripts/backup.sh')
        for script, args in [('backup.sh', []), ('backup.sh', ['--init']), ('restore.sh', []), ('update.sh', ['v0.2.0'])]:
            r = self.run_script(script, *args)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('未挂载', r.stderr)
        self.assertFalse(any('restic' in c or 'stop' in c for c in self.calls()))

    def configure_repository_pin(self, expected=None, mounted=True):
        if mounted:
            with (self.root / '.env').open('a') as f:
                f.write(f'BACKUP_MOUNTPOINT={self.root}\n')
            self.executable('mountpoint', '#!/bin/bash\nexit 0\n')
        if expected is not None:
            with (self.root / '.env').open('a') as f:
                f.write(f'BACKUP_REPO_ID={expected}\n')
        shutil.copyfile(ROOT / 'scripts/backup.sh', self.root / 'scripts/backup.sh')

    def test_mounted_repository_requires_pin_except_explicit_bootstrap(self):
        self.configure_repository_pin()
        self.env['BACKUP_REPO_ID'] = A  # inherited value is not the deployment .env
        for script, args in [('backup.sh', []), ('restore.sh', [A]), ('update.sh', ['v0.2.0'])]:
            with self.subTest(script=script):
                r = self.run_script(script, *args)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn('BACKUP_REPO_ID', r.stderr)
        self.assertFalse(any('restic' in c or 'stop' in c or 'exec' in c for c in self.calls()))
        self.assertEqual(self.run_script('backup.sh', '--init').returncode, 0)
        r = self.run_script('backup.sh', '--repo-id')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), A)

    def test_wrong_repository_identity_rejected_before_effects(self):
        self.configure_repository_pin(A)
        self.env['BACKUP_REPO_ID'] = B
        r = self.run_script('backup.sh', '--init')
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.calls(), [])
        for mode in ('other-repo', 'malformed-config', 'bad-repo'):
            for script, args in [('backup.sh', []), ('restore.sh', [A]), ('update.sh', ['v0.2.0'])]:
                with self.subTest(script=script, mode=mode):
                    r = self.run_script(script, *args, mode=mode)
                    self.assertNotEqual(r.returncode, 0)
                    self.assertNotIn(A, r.stdout + r.stderr)
                    self.assertNotIn(B, r.stdout + r.stderr)
                    self.assertNotIn('untrusted backend diagnostics', r.stdout + r.stderr)
        self.assertTrue(any('cat' in c for c in self.calls()))
        self.assertFalse(any(set(c) & {'exec', 'stop', 'up', 'pull', 'init', 'dump', 'backup', 'restore', 'forget'}
                             for c in self.calls()))

    def test_matching_pin_can_backup_and_is_not_logged(self):
        self.configure_repository_pin(A)
        r = self.run_script('backup.sh')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn(A, r.stdout + r.stderr)
        calls = self.calls()
        digest_step = next(i for i, c in enumerate(calls) if 'cat' in c)
        db_step = next(i for i, c in enumerate(calls) if any('pg_dump' in arg for arg in c))
        self.assertLess(digest_step, db_step)
        self.assertTrue(any('backup' in c for c in calls))

    def test_optional_pin_also_verifies_non_mount_repo(self):
        self.configure_repository_pin(A, mounted=False)
        r = self.run_script('backup.sh', mode='other-repo')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('身份不符', r.stderr)
        self.assertFalse(any('exec' in c for c in self.calls()))

    def test_explicit_older_or_unproven_release_never_stops(self):
        r = self.run_script('update.sh', 'v0.0.9')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('降级', r.stderr)
        self.executable('git', '#!/bin/bash\n[ "$1" != merge-base ]\n')
        r = self.run_script('update.sh', 'v0.2.0')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('降级', r.stderr)
        self.assertEqual(self.calls(), [])

    def test_restore_swap_in_one_transaction_and_resume_only_known_original(self):
        for mode in ('swap-fails', 'swap-ambiguous'):
            with self.subTest(mode=mode):
                (self.root / 'calls').unlink(missing_ok=True)
                r = self.run_script('restore.sh', A, '--yes', mode=mode)
                self.assertNotEqual(r.returncode, 0)
                self.assertEqual((self.root / 'rename_sql').read_text().count('ALTER DATABASE'), 2)
                calls = self.calls()
                self.assertEqual(sum(any('--single-transaction' in a and 'psql' in a for a in c) for c in calls), 1)
                self.assertFalse(any('restore' in c for c in calls))
                self.assertEqual(any('up' in c for c in calls), mode == 'swap-fails')

    def test_changed_migration_names_even_with_same_count_restore_snapshot(self):
        r = self.run_script('update.sh', 'v0.2.0', mode='changed-migrations')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('已退回 v0.1.0', r.stderr)
        self.assertEqual((self.root / 'database_dump').read_text().strip(), 'database:abcdef12')
        self.assertEqual((self.root / 'backend').read_text(), 'v0.1.0')

    def test_failed_rollback_swap_does_not_boot_old_image_on_new_schema(self):
        r = self.run_script('update.sh', 'v0.2.0', mode='changed-swap-fails')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('保持网站停止', r.stderr)
        self.assertEqual((self.root / 'up_count').read_text(), '1')


if __name__ == '__main__':
    unittest.main()
