"""Shared fixtures. Every module must test data isolation with these:

    group / other_group          two research groups
    student_a, student_b         students in `group`
    manager, advisor             supervisors of `group`
    other_manager                supervisor of `other_group` (must NOT see `group` data)
    ops                          the ops account: a superuser without a group (系统管理 only)
    project                      project in `group`, leader student_a, members a + b
    api(user)                    DRF APIClient logged in as `user` (CSRF not enforced)
"""

import pytest
from rest_framework.test import APIClient

from accounts.models import ResearchGroup, User
from core.models import SiteSettings
from projects.models import Project

PASSWORD = "Passw0rd!x"


@pytest.fixture(autouse=True)
def _isolated_settings(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "data"
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


def enable_mail():
    """Mail switched on in 系统管理; messages go to the test backend (pytest-django's locmem outbox)."""
    SiteSettings.objects.update_or_create(
        pk=1,
        defaults={"mail_enabled": True, "mail_host": "smtp.example.edu", "mail_username": "lab@example.edu", "mail_password": "code"},
    )


def make_user(username, group, role=User.Role.STUDENT, **extra):
    extra.setdefault("name", username)
    extra.setdefault("must_change_password", False)
    return User.objects.create_user(username=username, password=PASSWORD, group=group, role=role, **extra)


@pytest.fixture
def group(db):
    return ResearchGroup.objects.create(name="超声检测课题组")


@pytest.fixture
def other_group(db):
    return ResearchGroup.objects.create(name="其他课题组")


@pytest.fixture
def student_a(group):
    return make_user("s_a", group)


@pytest.fixture
def student_b(group):
    return make_user("s_b", group)


@pytest.fixture
def manager(group):
    return make_user("mgr", group, User.Role.MANAGER)


@pytest.fixture
def advisor(group):
    return make_user("adv", group, User.Role.ADVISOR)


@pytest.fixture
def other_manager(other_group):
    return make_user("other_mgr", other_group, User.Role.MANAGER)


@pytest.fixture
def ops(db):
    return User.objects.create_superuser("ops", password=PASSWORD, name="运维", must_change_password=False)


@pytest.fixture
def project(group, student_a, student_b):
    p = Project.objects.create(group=group, name="导波螺栓松动", leader=student_a, stage="重复性验证")
    p.members.set([student_a, student_b])
    return p


@pytest.fixture
def api():
    def _client(user=None):
        client = APIClient()
        if user is not None:
            client.force_login(user)
        return client

    return _client
