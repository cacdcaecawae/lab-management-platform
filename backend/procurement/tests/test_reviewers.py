"""Who reviews a purchase with the base role and the 管理员 / 终审人 tags (issue #48 R1, roles-and-identity note)."""

import pytest

from accounts.models import User
from conftest import make_user
from core.models import Notification
from procurement.models import Fund

from .test_procurement import review, status_of, submitted

pytestmark = pytest.mark.django_db


@pytest.fixture
def fund(group):
    return Fund.objects.create(group=group, code="NSFC-001", name="国自然面上")


def test_final_reviews_go_to_approvers_not_to_every_advisor(api, group, student_a, manager, advisor, fund):
    plain = make_user("adv_plain", group, User.Role.ADVISOR)  # an advisor without the 终审人 tag
    pid = submitted(api(student_a), fund)
    assert review(api(manager), pid).data["status"] == "pending_final"
    assert Notification.objects.filter(recipient=advisor, title="采购申请待终审").exists()
    assert not Notification.objects.filter(recipient=plain, title="采购申请待终审").exists()
    assert review(api(plain), pid).status_code == 404  # not a manager or approver: does not see it at all
    assert review(api(advisor), pid).data["status"] == "approved"


def test_one_person_does_both_reviews_only_when_nobody_else_could(api, group, student_a, fund):
    boss = make_user("boss", group, User.Role.ADVISOR, is_manager=True, is_approver=True)
    pid = submitted(api(student_a), fund)
    assert review(api(boss), pid).data["status"] == "pending_final"
    r = review(api(boss), pid)  # the group's only approver: allowed, the page says so
    assert r.status_code == 200 and r.data["status"] == "approved"
    assert [a["reviewer"]["id"] for a in r.data["approvals"]] == [boss.id, boss.id]

    second = make_user("adv2", group, User.Role.ADVISOR, is_approver=True)
    pid = submitted(api(student_a), fund)
    review(api(boss), pid)
    r = review(api(boss), pid)
    assert r.status_code == 403 and status_of(pid) == "pending_final"
    assert review(api(second), pid).data["status"] == "approved"


def test_an_approvers_own_request(api, group, manager, advisor, fund):
    pid = submitted(api(advisor), fund)
    assert review(api(manager), pid).data["status"] == "approved"  # the only approver: no one else for the final review
    second = make_user("adv2", group, User.Role.ADVISOR, is_approver=True)
    pid = submitted(api(advisor), fund)
    assert review(api(manager), pid).data["status"] == "pending_final"
    assert review(api(advisor), pid).status_code == 403  # never one's own
    assert review(api(second), pid).data["status"] == "approved"


def test_a_sole_approver_with_the_manager_tag_still_gets_an_initial_review(api, group, manager, fund):
    boss = make_user("boss", group, User.Role.ADVISOR, is_manager=True, is_approver=True)
    pid = submitted(api(boss), fund)  # skipping the initial review would leave the request with nobody
    assert status_of(pid) == "pending_initial"
    assert review(api(manager), pid).data["status"] == "approved"
