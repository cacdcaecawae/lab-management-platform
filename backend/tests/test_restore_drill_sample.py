"""The monthly restore drill's sampler (scripts/restore-drill-verify.py, run inside the backend image): which uploaded
files it checks in the snapshot, and against what."""
import importlib.util
import json
from pathlib import Path

import pytest

from accounts.models import User
from achievements.models import Achievement

pytestmark = pytest.mark.django_db
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "restore-drill-verify.py"


@pytest.fixture
def drill():
    spec = importlib.util.spec_from_file_location("restore_drill_verify", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_kind_of_uploaded_file_is_sampled(drill, student_a, group, capsys):
    # Pictures and full texts have no checksum column; the drill still has to find them in the snapshot.
    avatar, fulltext = "avatars/" + "a" * 32 + ".jpg", "achievements/" + "b" * 32 + ".pdf"
    User.objects.filter(pk=student_a.pk).update(avatar=avatar)
    Achievement.objects.create(group=group, type="paper", title="t", authors="甲", date="2026-01-01",
                               status="published", created_by=student_a, fulltext=fulltext)
    drill.sample(20, "seed")
    rows = json.loads(capsys.readouterr().out)
    # no history copies, and only that they are in the snapshot: neither table records a checksum or a size
    assert sorted(rows) == [["accounts.User.avatar", avatar, "present"], ["achievements.Achievement.fulltext", fulltext, "present"]]
