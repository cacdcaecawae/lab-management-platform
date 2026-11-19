"""Include isolated shell regressions in the normal backend/CI test run (no database needed)."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


@pytest.mark.skipif(os.name != 'posix' or shutil.which('bash') is None,
                    reason='isolated command doubles require POSIX/Bash; Linux CI runs this test')
def test_server_script_regressions():
    root = Path(__file__).resolve().parents[2]
    subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'scripts/tests', '-v'],
                   cwd=root, check=True)
