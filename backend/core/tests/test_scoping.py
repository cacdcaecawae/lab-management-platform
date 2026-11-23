import pytest

from accounts.models import User
from conftest import make_user

from core.permissions import scope_finance, scope_group, scope_private
from datasets.models import Dataset
from procurement.models import PurchaseRequest
from projects.models import Project

pytestmark = pytest.mark.django_db


def test_scope_private(project, student_a, student_b, manager, advisor, other_manager):
    mine = Dataset.objects.create(owner=student_a, project=project, name="a")
    theirs = Dataset.objects.create(owner=student_b, project=project, name="b")
    qs = Dataset.objects.all()
    assert list(scope_private(qs, student_a)) == [mine]
    assert not scope_private(qs, manager).exists()  # a student with the 管理员 tag: their own research records only
    assert set(scope_private(qs, advisor)) == {mine, theirs}
    assert not scope_private(qs, other_manager).exists()


def test_scope_finance(group, student_a, student_b, manager, advisor, other_manager):
    mine = PurchaseRequest.objects.create(owner=student_a, purpose="a")
    theirs = PurchaseRequest.objects.create(owner=student_b, purpose="b")
    qs = PurchaseRequest.objects.all()
    assert list(scope_finance(qs, student_a)) == [mine]
    assert set(scope_finance(qs, manager)) == set(scope_finance(qs, advisor)) == {mine, theirs}  # 管理员, 终审人
    plain_advisor = make_user("adv_plain", group, User.Role.ADVISOR)  # an advisor without the 终审人 tag
    assert not scope_finance(qs, plain_advisor).exists()
    assert not scope_finance(qs, other_manager).exists()


def test_scope_group(project, student_b, other_manager):
    assert list(scope_group(Project.objects.all(), student_b)) == [project]
    assert not scope_group(Project.objects.all(), other_manager).exists()


def test_serialize_history_records_changes_and_reason(project, student_a):
    from core.history import serialize_history

    ds = Dataset.objects.create(owner=student_a, project=project, name="old")
    ds.name = "new"
    ds._change_reason = "改名"
    ds.save()
    newest, created = serialize_history(ds)
    assert created["type"] == "created" and created["changes"] == []
    assert newest["type"] == "changed" and newest["reason"] == "改名"
    assert newest["changes"] == [{"field": "name", "old": "old", "new": "new"}]
