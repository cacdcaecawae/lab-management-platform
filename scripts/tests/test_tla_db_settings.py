"""Exercise source slices and Git states without Django or the TLC Java dependency."""
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".claude/skills/verify-equipment-tla/scripts/check_database_settings.py"
SIGNATURE = runpy.run_path(str(SCRIPT))["signature"]
BASE = 'import os\nDATABASES = {"default": {"NAME": os.environ.get("DB_NAME")}}\n'


class DatabaseSettingsTests(unittest.TestCase):
    def test_formatting_and_unrelated_configuration(self):
        changed = """import os
DATABASES = {
  'default': {
    'NAME': (
      os.environ.get('DB_NAME')
    ),
  }
}
INSTALLED_APPS = ['new_app']
APP_VERSION = os.environ.get('APP_VERSION', '')
"""
        self.assertEqual(SIGNATURE(BASE), SIGNATURE(changed))

    def test_database_and_related_settings_change(self):
        for source in (
            BASE.replace('"NAME":', '"ATOMIC_REQUESTS": True, "NAME":'),
            BASE.replace('"NAME":', '"OPTIONS": {"isolation_level": 3}, "NAME":'),
            BASE + 'DATABASE_ROUTERS = ["project.Router"]\n',
            BASE + 'globals()["DATABASES"] = {}\n',
            BASE + 'os.environ["DB_NAME"] = "another"\n',
            BASE + 'os = custom_os\n',
            BASE + 'os.putenv("DB_NAME", "another")\n',
        ):
            with self.subTest(source=source):
                self.assertNotEqual(SIGNATURE(BASE), SIGNATURE(source))

    def test_ambiguous_forms_require_review(self):
        for source in (
            'INSTALLED_APPS = []',
            'from .database import DATABASES',
            'DATABASES = load_config()',
            BASE + 'DATABASES["default"]["ATOMIC_REQUESTS"] = True',
            BASE + 'if DEBUG:\n    DATABASES = {}',
            BASE + 'from .override import *',
            'from os import environ as db_env\ndb_env["DB_NAME"] = "another"\n' + BASE,
            'import os as alias\nalias.environ["DB_NAME"] = "another"\n' + BASE,
            BASE + 'env_alias = os.environ\nenv_alias["DB_NAME"] = "another"\n',
            BASE + 'set_db = os.environ.setdefault\nset_db("DB_NAME", "another")\n',

            'DATABASES = {',
        ):
            with self.subTest(source=source), self.assertRaises(ValueError):
                SIGNATURE(source)

    def test_git_states_review_even_if_other_state_reverts_change(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            path = repo / "backend/config/settings.py"
            path.parent.mkdir(parents=True)
            path.write_text(BASE, encoding="utf-8")

            def git(*args):
                return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()

            def check(sync):
                return subprocess.run([sys.executable, str(SCRIPT), str(repo), sync],
                                      capture_output=True, text=True)

            git("init", "-q")
            git("add", ".")
            git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "baseline")
            sync = git("rev-parse", "HEAD")
            self.assertEqual(check(sync).returncode, 0)
            self.assertEqual(check("missing-ref").returncode, 1)
            path.write_text(BASE.replace('"NAME":', '"ATOMIC_REQUESTS": True, "NAME":'), encoding="utf-8")
            self.assertIn("(worktree)", check(sync).stdout)
            git("add", ".")
            path.write_text(BASE, encoding="utf-8")
            result = check(sync)
            self.assertEqual(result.returncode, 2)
            self.assertIn("(index)", result.stdout)
            self.assertNotIn("(worktree)", result.stdout)
            git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "db change")
            git("add", ".")
            result = check(sync)
            self.assertEqual(result.returncode, 2)
            self.assertIn("(HEAD)", result.stdout)
            self.assertNotIn("(index)", result.stdout)
