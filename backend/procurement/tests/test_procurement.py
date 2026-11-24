import io
import threading
from decimal import Decimal
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import connection
from django.utils import timezone
from openpyxl import load_workbook

from conftest import enable_mail, make_user
from core.models import SiteSettings
from equipment.models import Equipment
from inventory.models import Consumable
from procurement import serializers as procurement_serializers
from procurement.models import Approval, Attachment, Fund, PurchaseRequest, Reimbursement
from procurement.views import PurchaseViewSet

pytestmark = pytest.mark.django_db

ITEMS = [{"name": "5MHz 探头", "spec": "Φ10", "quantity": 2, "unit_price": "1200.00"}, {"name": "耦合剂", "quantity": 3, "unit_price": "45.50"}]
TOTAL = "2536.50"


@pytest.fixture
def fund(group):
    return Fund.objects.create(group=group, code="NSFC-001", name="国自然面上")


@pytest.fixture
def other_fund(other_group):
    return Fund.objects.create(group=other_group, code="X-1", name="外组经费")


def create(client, fund, **extra):
    body = {"purpose": "搭建相控阵实验台", "fund_id": fund.id, "items": ITEMS, **extra}
    return client.post("/api/purchases/", body, format="json")


def submitted(client, fund):
    pid = create(client, fund).data["id"]
    assert client.post(f"/api/purchases/{pid}/submit/").status_code == 200
    return pid


def review(client, pid, verdict="approve", comment="", seen=None, total=TOTAL):
    purchase = PurchaseRequest.objects.get(pk=pid)
    status_seen = seen or purchase.status
    body = {
        "verdict": verdict, "comment": comment, "status_seen": status_seen, "total_seen": total,
        "submitted_seen": (purchase.submitted_at or timezone.now()).isoformat(),
    }
    return client.post(f"/api/purchases/{pid}/review/", body, format="json")


def status_of(pid):
    return PurchaseRequest.objects.get(pk=pid).status


def pdf(name="报价单.pdf", size=None):
    return SimpleUploadedFile(name, b"%PDF-1.4 fake" if size is None else b"0" * size, content_type="application/pdf")


# --- purchase requests ----------------------------------------------------------------------

def test_student_request_goes_through_both_reviews(api, student_a, manager, advisor, fund):
    a = api(student_a)
    r = create(a, fund)
    assert r.status_code == 201 and r.data["status"] == "draft" and r.data["total"] == TOTAL
    assert r.data["code"].startswith("PR-") and [i["subtotal"] for i in r.data["items"]] == ["2400.00", "136.50"]
    pid = r.data["id"]
    assert a.post(f"/api/purchases/{pid}/submit/").data["status"] == "pending_initial"
    assert review(a, pid).status_code == 403  # the applicant
    assert review(api(advisor), pid).status_code == 403  # an advisor cannot do the initial review
    assert review(api(manager), pid).data["status"] == "pending_final"
    assert review(api(manager), pid).status_code == 403  # a manager cannot do the final review
    r = review(api(advisor), pid, comment="同意")
    assert r.status_code == 200 and r.data["status"] == "approved"
    assert [(x["stage"], x["verdict"], x["reviewer"]["id"], x["total"]) for x in r.data["approvals"]] == [
        ("initial", "approve", manager.id, TOTAL),
        ("final", "approve", advisor.id, TOTAL),
    ]
    assert a.post(f"/api/purchases/{pid}/purchased/").status_code == 403
    assert api(manager).post(f"/api/purchases/{pid}/arrived/").status_code == 409  # not purchased yet
    assert api(manager).post(f"/api/purchases/{pid}/purchased/").data["status"] == "purchased"
    assert api(manager).post(f"/api/purchases/{pid}/arrived/").data["status"] == "arrived"


def test_manager_request_skips_the_initial_review(api, manager, advisor, fund):
    pid = submitted(api(manager), fund)
    assert status_of(pid) == "pending_final"
    assert review(api(manager), pid).status_code == 403
    assert review(api(advisor), pid).data["status"] == "approved"


def test_advisor_request_is_approved_by_the_initial_review(api, manager, advisor, fund):
    pid = submitted(api(advisor), fund)
    assert status_of(pid) == "pending_initial"
    assert review(api(advisor), pid).status_code == 403
    assert review(api(manager), pid).data["status"] == "approved"
    assert list(Approval.objects.filter(request_id=pid).values_list("stage", flat=True)) == ["initial"]


def test_scope(api, student_a, student_b, manager, advisor, other_manager, fund):
    pid = create(api(student_a), fund).data["id"]
    assert api(student_b).get(f"/api/purchases/{pid}/").status_code == 404
    assert api(other_manager).get(f"/api/purchases/{pid}/").status_code == 404
    assert review(api(other_manager), pid, seen="draft").status_code == 404
    assert api(manager).get(f"/api/purchases/{pid}/").status_code == 200
    assert api(advisor).get(f"/api/purchases/{pid}/").status_code == 200
    assert api(student_b).get("/api/purchases/").data["count"] == 0
    assert api(manager).get("/api/purchases/").data["count"] == 1


def test_submit_rules(api, student_a, fund, other_fund):
    a = api(student_a)
    assert create(a, other_fund).status_code == 400  # another group's fund
    pid = create(a, fund, items=[]).data["id"]
    assert set(a.post(f"/api/purchases/{pid}/submit/").data["errors"]) == {"items"}
    a.patch(f"/api/purchases/{pid}/", {"items": [{"name": "赠品", "quantity": 1, "unit_price": "0"}]}, format="json")
    assert a.post(f"/api/purchases/{pid}/submit/").data["errors"] == {"items": ["合计必须大于 0"]}
    a.patch(f"/api/purchases/{pid}/", {"items": ITEMS}, format="json")
    fund.active = False
    fund.save()
    assert set(a.post(f"/api/purchases/{pid}/submit/").data["errors"]) == {"fund_id"}
    assert create(a, fund).status_code == 400  # a stopped fund cannot be picked
    bad = [{"name": "x", "quantity": 0, "unit_price": "-1"}]
    assert set(a.patch(f"/api/purchases/{pid}/", {"items": bad}, format="json").data["errors"]["items"][0]) == {
        "quantity", "unit_price"
    }


def test_return_needs_a_comment_and_the_applicant_sees_it(api, student_a, manager, fund):
    pid = submitted(api(student_a), fund)
    r = review(api(manager), pid, verdict="return")
    assert r.status_code == 400 and "comment" in r.data["errors"]
    assert review(api(manager), pid, verdict="return", comment="  请补报价单 ").data["status"] == "draft"
    assert Approval.objects.get(request_id=pid).comment == "请补报价单"
    assert api(student_a).get(f"/api/purchases/{pid}/").data["returned"] is True
    assert [p["id"] for p in api(student_a).get("/api/dashboard/").data["my"]["returned_purchases"]] == [pid]
    assert api(student_a).post(f"/api/purchases/{pid}/submit/").data["status"] == "pending_initial"
    assert api(student_a).get(f"/api/purchases/{pid}/").data["returned"] is False


def test_withdraw(api, student_a, student_b, manager, fund):
    pid = submitted(api(student_a), fund)
    assert api(manager).post(f"/api/purchases/{pid}/withdraw/").status_code == 403
    r = api(student_a).post(f"/api/purchases/{pid}/withdraw/")
    assert r.status_code == 200 and r.data["status"] == "draft" and r.data["returned"] is False
    assert api(student_a).post(f"/api/purchases/{pid}/withdraw/").status_code == 409
    assert api(student_a).delete(f"/api/purchases/{pid}/").status_code == 409  # submitted once: kept as a record
    draft = create(api(student_a), fund).data["id"]
    assert api(student_b).delete(f"/api/purchases/{draft}/").status_code == 404
    assert api(student_a).delete(f"/api/purchases/{draft}/").status_code == 204


def test_review_of_a_changed_request_is_409(api, student_a, manager, manager_b, fund):
    pid = submitted(api(student_a), fund)
    # The applicant withdraws, raises a price and resubmits while the manager still looks at the old total.
    api(student_a).post(f"/api/purchases/{pid}/withdraw/")
    api(student_a).patch(f"/api/purchases/{pid}/", {"items": ITEMS[:1]}, format="json")
    api(student_a).post(f"/api/purchases/{pid}/submit/")
    r = review(api(manager), pid, total=TOTAL)
    assert r.status_code == 409 and r.data["code"] == "stale"
    # Two managers looking at the same request: the second decision is about a state that is gone.
    assert review(api(manager), pid, total="2400.00").data["status"] == "pending_final"
    assert review(api(manager_b), pid, seen="pending_initial", total="2400.00").status_code == 409
    assert Approval.objects.filter(request_id=pid).count() == 1


@pytest.mark.parametrize("verdict", ["approve", "return"])
@pytest.mark.parametrize("stage", ["initial", "final"])
def test_equal_total_resubmission_rejects_old_review(api, student_a, manager, advisor, fund, verdict, stage):
    applicant = api(student_a)
    pid = submitted(applicant, fund)
    if stage == "final":
        assert review(api(manager), pid).status_code == 200
    reviewer = api(manager if stage == "initial" else advisor)
    old = reviewer.get(f"/api/purchases/{pid}/").data
    assert applicant.post(f"/api/purchases/{pid}/withdraw/").status_code == 200
    changed_items = [{**ITEMS[0], "name": "同价不同型号探头"}, ITEMS[1]]
    assert applicant.patch(f"/api/purchases/{pid}/", {"items": changed_items}, format="json").status_code == 200
    assert applicant.post(f"/api/purchases/{pid}/submit/").status_code == 200
    if stage == "final":
        assert review(api(manager), pid).status_code == 200
    count = Approval.objects.filter(request_id=pid).count()
    result = reviewer.post(f"/api/purchases/{pid}/review/", {
        "verdict": verdict, "comment": "审批意见", "status_seen": old["status"], "total_seen": old["total"],
        "submitted_seen": old["submitted_at"],
    }, format="json")
    assert result.status_code == 409 and result.data["code"] == "stale"
    assert status_of(pid) == old["status"]
    assert Approval.objects.filter(request_id=pid).count() == count
    # Refreshing the page supplies the new submission and permits a deliberate approval.
    assert review(reviewer, pid).status_code == 200


@pytest.mark.parametrize("value", ["missing", None, "not-a-date"])
def test_review_requires_valid_submission_time(api, student_a, manager, fund, value):
    pid = submitted(api(student_a), fund)
    body = {"verdict": "approve", "status_seen": "pending_initial", "total_seen": TOTAL}
    if value != "missing":
        body["submitted_seen"] = value
    result = api(manager).post(f"/api/purchases/{pid}/review/", body, format="json")
    assert result.status_code == 400 and "submitted_seen" in result.data["errors"]
    assert not Approval.objects.filter(request_id=pid).exists()


def test_attachment_does_not_invalidate_current_submission(api, student_a, manager, fund):
    applicant = api(student_a)
    pid = submitted(applicant, fund)
    reviewer = api(manager)
    old = reviewer.get(f"/api/purchases/{pid}/").data
    assert applicant.post(f"/api/purchases/{pid}/attachments/", {"file": pdf()}, format="multipart").status_code == 201
    result = reviewer.post(f"/api/purchases/{pid}/review/", {
        "verdict": "approve", "status_seen": old["status"], "total_seen": old["total"],
        "submitted_seen": old["submitted_at"],
    }, format="json")
    assert result.status_code == 200 and result.data["status"] == "pending_final"


@pytest.fixture
def manager_b(group):
    return make_user("mgr_b", group, is_manager=True)


@pytest.mark.django_db(transaction=True)
def test_concurrent_reviews_only_one_applies(api, monkeypatch, student_a, manager, manager_b, fund):
    """Both requests read the request before either writes: the row lock makes the second see the first's result."""
    pid = submitted(api(student_a), fund)
    both_read, results = threading.Barrier(2, timeout=10), {}
    get_object = PurchaseViewSet.get_object

    def paused_get_object(view):
        obj = get_object(view)
        if view.action == "review":
            both_read.wait()
        return obj

    monkeypatch.setattr(PurchaseViewSet, "get_object", paused_get_object)

    def run(user):
        try:
            results[user.username] = review(api(user), pid, seen="pending_initial").status_code
        finally:
            connection.close()

    threads = [threading.Thread(target=run, args=(u,)) for u in (manager, manager_b)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(15)
    assert sorted(results.values()) == [200, 409]
    assert Approval.objects.filter(request_id=pid).count() == 1 and status_of(pid) == "pending_final"


def test_editing_items_after_approval_starts_over(api, student_a, manager, advisor, fund):
    pid = submitted(api(student_a), fund)
    review(api(manager), pid)
    review(api(advisor), pid)
    a = api(student_a)
    assert a.patch(f"/api/purchases/{pid}/", {"purpose": "改了用途"}, format="json").data["status"] == "approved"
    same = [{**ITEMS[0], "spec": "Φ12"}, ITEMS[1]]  # spec is not part of what was approved
    assert a.patch(f"/api/purchases/{pid}/", {"items": same}, format="json").data["status"] == "approved"
    dearer = [{**ITEMS[0], "unit_price": "1350.00"}, ITEMS[1]]
    r = api(manager).patch(f"/api/purchases/{pid}/", {"items": dearer}, format="json")  # a manager may correct prices
    assert r.status_code == 200 and r.data["status"] == "pending_initial" and r.data["total"] == "2836.50"
    assert len(r.data["approvals"]) == 2  # kept
    entry = a.get(f"/api/purchases/{pid}/history/").data[0]
    assert "5MHz 探头 2×1200.00" in entry["reason"] and "5MHz 探头 2×1350.00" in entry["reason"]
    assert {"field": "status", "old": "approved", "new": "pending_initial"} in entry["changes"]
    assert a.patch(f"/api/purchases/{pid}/", {"purpose": "x"}, format="json").status_code == 409  # under review
    assert api(advisor).patch(f"/api/purchases/{pid}/", {"purpose": "x"}, format="json").status_code == 403


def test_a_correction_after_approval_is_still_a_request_worth_reviewing(api, student_a, manager, advisor, fund):
    pid = submitted(api(student_a), fund)
    review(api(manager), pid)
    review(api(advisor), pid)
    patch = lambda items: api(student_a).patch(f"/api/purchases/{pid}/", {"items": items}, format="json")  # noqa: E731
    r = patch([])
    assert r.status_code == 400 and r.data["errors"]["items"] == ["至少需要 1 条明细"]
    r = patch([{"name": "赠品", "quantity": 1, "unit_price": "0.00"}])
    assert r.status_code == 400 and r.data["errors"]["items"] == ["合计必须大于 0"]
    assert status_of(pid) == "approved" and PurchaseRequest.objects.get(pk=pid).total == Decimal(TOTAL)  # untouched
    r = api(student_a).patch(f"/api/purchases/{pid}/", {"purpose": " ", "fund_id": None}, format="json")
    assert r.status_code == 400 and set(r.data["errors"]) == {"purpose", "fund_id"}
    assert PurchaseRequest.objects.get(pk=pid).fund_id == fund.id
    Fund.objects.filter(pk=fund.id).update(active=False)  # stopped since: other corrections still go through
    assert api(student_a).patch(f"/api/purchases/{pid}/", {"purpose": "改了用途"}, format="json").status_code == 200


def test_a_draft_a_reimbursement_points_at_is_kept(api, student_a, fund):
    pid = create(api(student_a), fund).data["id"]
    code = reimburse(api(student_a), fund, purchase_id=pid).data["code"]
    r = api(student_a).delete(f"/api/purchases/{pid}/")
    assert r.status_code == 409 and code in r.data["message"]
    assert PurchaseRequest.objects.filter(pk=pid).exists()


def test_manager_own_request_restarts_at_the_final_review(api, manager, advisor, fund):
    pid = submitted(api(manager), fund)
    review(api(advisor), pid)
    r = api(manager).patch(f"/api/purchases/{pid}/", {"items": ITEMS[:1]}, format="json")
    assert r.data["status"] == "pending_final"


def test_arrived_request_is_frozen(api, student_a, manager, advisor, fund):
    pid = submitted(api(student_a), fund)
    review(api(manager), pid)
    review(api(advisor), pid)
    api(manager).post(f"/api/purchases/{pid}/purchased/")
    api(manager).post(f"/api/purchases/{pid}/arrived/")
    assert api(student_a).patch(f"/api/purchases/{pid}/", {"purpose": "x"}, format="json").status_code == 409


def test_list_filters_and_my_reviews(api, student_a, manager, advisor, fund):
    initial = submitted(api(student_a), fund)
    final = submitted(api(manager), fund)
    create(api(student_a), fund)
    todo = lambda user: [p["id"] for p in api(user).get("/api/purchases/", {"todo": 1}).data["results"]]  # noqa: E731
    assert todo(manager) == [initial] and todo(advisor) == [final] and todo(student_a) == []
    assert api(manager).get("/api/purchases/", {"status": "pending_final"}).data["count"] == 1
    assert api(manager).get("/api/purchases/", {"mine": 1}).data["count"] == 1
    assert api(manager).get("/api/purchases/", {"search": "探头"}).data["count"] == 3
    board = lambda user: [p["id"] for p in api(user).get("/api/dashboard/").data["supervisor"]["purchases_to_review"]]  # noqa: E731
    assert board(manager) == [initial] and board(advisor) == [final]


# --- attachments ----------------------------------------------------------------------------

def test_attachments(api, student_a, student_b, manager, other_manager, fund, monkeypatch):
    pid = create(api(student_a), fund).data["id"]
    url = f"/api/purchases/{pid}/attachments/"
    assert api(student_a).post(url, {"file": SimpleUploadedFile("x.exe", b"MZ"), "kind": "quote"}).status_code == 400
    monkeypatch.setattr(procurement_serializers, "ATTACHMENT_MAX_SIZE", 10)
    assert api(student_a).post(url, {"file": pdf(size=11), "kind": "quote"}).status_code == 400
    monkeypatch.undo()
    r = api(student_a).post(url, {"file": pdf(), "kind": "quote"})
    assert r.status_code == 201 and r.data["name"] == "报价单.pdf"
    stored = Attachment.objects.get().file.name
    assert stored.startswith("procurement/") and stored.endswith(".pdf") and "报价单" not in stored
    download = api(manager).get(r.data["url"])
    assert download.status_code == 200 and b"".join(download.streaming_content) == b"%PDF-1.4 fake"
    assert download["Cache-Control"] == "private"
    assert download["Content-Security-Policy"] == "default-src 'none'; frame-ancestors 'self'"
    assert api(student_b).get(r.data["url"]).status_code == 404
    assert api(other_manager).get(r.data["url"]).status_code == 404
    assert api(student_b).post(url, {"file": pdf()}).status_code == 404
    api(student_a).post(f"/api/purchases/{pid}/submit/")
    assert api(student_a).delete(f"/api/attachments/{r.data['id']}/").status_code == 409  # under review
    api(student_a).post(f"/api/purchases/{pid}/withdraw/")
    assert api(student_a).delete(f"/api/attachments/{r.data['id']}/").status_code == 204
    assert not Attachment.objects.exists()


def test_an_upload_to_a_draft_deleted_meanwhile_leaves_no_file(api, settings, monkeypatch, student_a, fund):
    pid = create(api(student_a), fund).data["id"]
    get_object = PurchaseViewSet.get_object

    def then_deleted(view):
        purchase = get_object(view)
        PurchaseRequest.objects.filter(pk=purchase.pk).delete()  # deleted in another tab while the file uploads
        return purchase

    monkeypatch.setattr(PurchaseViewSet, "get_object", then_deleted)
    assert api(student_a).post(f"/api/purchases/{pid}/attachments/", {"file": pdf()}).status_code == 404
    assert not [p for p in Path(settings.MEDIA_ROOT).rglob("*") if p.is_file()]



def test_files_a_reviewer_has_seen_stay(api, student_a, manager, advisor, fund):
    """Draft: delete freely. Under review: no. After a review: only files uploaded since the latest review."""
    a = api(student_a)
    pid = create(a, fund).data["id"]
    url = f"/api/purchases/{pid}/attachments/"
    quote = a.post(url, {"file": pdf(), "kind": "quote"}).data["id"]
    a.post(f"/api/purchases/{pid}/submit/")
    review(api(manager), pid)
    review(api(advisor), pid)
    invoice_id = a.post(url, {"file": pdf("发票.pdf"), "kind": "invoice"}).data["id"]  # invoices come after ordering
    r = a.delete(f"/api/attachments/{quote}/")
    assert r.status_code == 409 and "看过" in r.data["message"]
    assert a.delete(f"/api/attachments/{invoice_id}/").status_code == 204

    api(manager).post(f"/api/purchases/{pid}/purchased/")
    api(manager).post(f"/api/purchases/{pid}/arrived/")
    late = api(manager).post(url, {"file": pdf("到货单.pdf"), "kind": "other"}).data["id"]
    assert api(manager).delete(f"/api/attachments/{late}/").status_code == 204
    assert api(manager).delete(f"/api/attachments/{quote}/").status_code == 409
    assert list(Attachment.objects.values_list("id", flat=True)) == [quote]


def test_handed_in_reimbursements_take_no_more_files(api, student_a, manager, fund):
    a = api(student_a)
    rid = reimburse(a, fund).data["id"]
    first = invoice(a, rid).data["id"]
    advance(a, rid, "submitted")
    r = invoice(a, rid)
    assert r.status_code == 409 and "退回" in r.data["message"]
    advance(api(manager), rid, "paid")
    assert invoice(api(manager), rid).status_code == 409
    assert api(manager).delete(f"/api/attachments/{first}/").status_code == 409
    assert list(Attachment.objects.values_list("id", flat=True)) == [first]


# --- mail -----------------------------------------------------------------------------------

def test_each_step_mails_the_next_person(
    api, settings, mailoutbox, django_capture_on_commit_callbacks, group, student_a, manager, advisor, fund
):
    enable_mail()
    for user, email in ((student_a, "s_a@example.edu"), (manager, "mgr@example.edu"), (advisor, "adv@example.edu")):
        user.email = email
        user.save()
    make_user("mgr_left", group, "manager", email="left@example.edu", is_active=False)

    def step(fn):
        mailoutbox.clear()
        with django_capture_on_commit_callbacks(execute=True):
            fn()
        return [(m.to, m.subject) for m in mailoutbox]

    pid = create(api(student_a), fund).data["id"]
    code = PurchaseRequest.objects.get(pk=pid).code
    assert step(lambda: api(student_a).post(f"/api/purchases/{pid}/submit/")) == [(["mgr@example.edu"], f"[采购待初审] {code}")]
    assert step(lambda: review(api(manager), pid, "return", "补报价单")) == [(["s_a@example.edu"], f"[采购退回修改] {code}")]
    assert "补报价单" in mailoutbox[0].body
    step(lambda: api(student_a).post(f"/api/purchases/{pid}/submit/"))
    assert step(lambda: review(api(manager), pid)) == [(["adv@example.edu"], f"[采购待终审] {code}")]
    assert step(lambda: review(api(advisor), pid)) == [(["s_a@example.edu"], f"[采购已批准] {code}")]
    assert step(lambda: api(manager).post(f"/api/purchases/{pid}/purchased/")) == []
    assert step(lambda: api(manager).post(f"/api/purchases/{pid}/arrived/")) == [(["s_a@example.edu"], f"[采购已到货] {code}")]


class BrokenBackend:
    def __init__(self, *args, **kwargs):
        pass

    def send_messages(self, messages):
        raise OSError("SMTP unreachable")


def test_mail_failure_does_not_undo_the_step(api, settings, django_capture_on_commit_callbacks, student_a, manager, fund, caplog):
    enable_mail()
    settings.EMAIL_BACKEND = f"{__name__}.BrokenBackend"
    manager.email = "mgr@example.edu"
    manager.save()
    pid = create(api(student_a), fund).data["id"]
    with django_capture_on_commit_callbacks(execute=True):
        assert api(student_a).post(f"/api/purchases/{pid}/submit/").status_code == 200
    assert status_of(pid) == "pending_initial" and "采购通知邮件发送失败" in caplog.text


def test_no_mail_without_smtp(api, settings, mailoutbox, django_capture_on_commit_callbacks, student_a, manager, fund):
    manager.email = "mgr@example.edu"
    manager.save()
    with django_capture_on_commit_callbacks(execute=True):
        submitted(api(student_a), fund)
    assert mailoutbox == []


# --- arrival: equipment and stock-in --------------------------------------------------------

def arrived(api, owner, manager, advisor, fund):
    pid = submitted(api(owner), fund)
    review(api(manager), pid)
    review(api(advisor), pid)
    api(manager).post(f"/api/purchases/{pid}/purchased/")
    api(manager).post(f"/api/purchases/{pid}/arrived/")
    return pid


def test_equipment_and_stock_in_link_an_arrived_purchase(api, group, student_a, manager, advisor, fund):
    pending = submitted(api(student_a), fund)
    pid = arrived(api, student_a, manager, advisor, fund)
    m = api(manager)
    body = {"code": "PA-002", "name": "相控阵探头", "status": "available"}
    assert m.post("/api/equipment/", {**body, "purchase_id": pending}, format="json").status_code == 400
    r = m.post("/api/equipment/", {**body, "purchase_id": pid}, format="json")
    assert r.status_code == 201 and r.data["purchase"]["code"] == PurchaseRequest.objects.get(pk=pid).code
    gel = Consumable.objects.create(group=group, name="耦合剂", unit="瓶")
    txns = f"/api/consumables/{gel.id}/txns/"
    assert m.post(txns, {"kind": "in", "quantity": 3, "purchase_id": pid}, format="json").status_code == 201
    assert m.post(txns, {"kind": "out", "quantity": 1, "purchase_id": pid}, format="json").status_code == 400
    detail = api(student_a).get(f"/api/purchases/{pid}/").data
    assert [e["code"] for e in detail["linked_equipment"]] == ["PA-002"]
    assert [(t["consumable"], t["quantity"]) for t in detail["linked_stock"]] == [("耦合剂", 3)]
    device = Equipment.objects.get(code="PA-002")
    m.patch(f"/api/equipment/{device.id}/", {"purchase_id": None}, format="json")
    history = api(student_a).get(f"/api/equipment/{device.id}/history/").data
    assert {"field": "purchase", "old": PurchaseRequest.objects.get(pk=pid).code, "new": None} in history[0]["changes"]


# --- funds ----------------------------------------------------------------------------------

def test_funds(api, student_a, manager, other_manager, fund):
    assert api(student_a).post("/api/funds/", {"code": "F-2", "name": "横向"}).status_code == 403
    assert api(manager).post("/api/funds/", {"code": "NSFC-001", "name": "重复"}).status_code == 409
    assert api(other_manager).post("/api/funds/", {"code": "NSFC-001", "name": "外组同号"}).status_code == 201
    assert [f["code"] for f in api(student_a).get("/api/funds/").data["results"]] == ["NSFC-001"]
    api(manager).patch(f"/api/funds/{fund.id}/", {"active": False}, format="json")
    assert api(student_a).get("/api/funds/", {"active": 1}).data["count"] == 0
    assert api(other_manager).get(f"/api/funds/{fund.id}/").status_code == 404


# --- reimbursements -------------------------------------------------------------------------

def reimburse(client, fund, **extra):
    body = {"fund_id": fund.id, "category": "consumable", "amount": "136.50", "occurred_on": "2026-11-10", **extra}
    return client.post("/api/reimbursements/", body, format="json")


def invoice(client, rid):
    return client.post(f"/api/reimbursements/{rid}/attachments/", {"file": pdf("发票.pdf"), "kind": "invoice"})


def advance(client, rid, to):
    return client.post(f"/api/reimbursements/{rid}/advance/", {"status": to}, format="json")


def test_reimbursement_flow(api, student_a, student_b, manager, other_manager, fund):
    a = api(student_a)
    rid = reimburse(a, fund, description="耦合剂 3 瓶").data["id"]
    assert api(student_b).get(f"/api/reimbursements/{rid}/").status_code == 404
    assert api(other_manager).get(f"/api/reimbursements/{rid}/").status_code == 404
    assert advance(a, rid, "paid").status_code == 409
    r = advance(a, rid, "submitted")
    assert r.status_code == 400 and "attachments" in r.data["errors"]
    assert invoice(a, rid).status_code == 201
    r = advance(a, rid, "submitted")
    assert r.status_code == 200 and r.data["status"] == "submitted" and r.data["submitted_at"]
    assert a.patch(f"/api/reimbursements/{rid}/", {"amount": "150.00"}, format="json").status_code == 409
    assert advance(a, rid, "pending").status_code == 403  # only a manager sends it back
    assert advance(api(manager), rid, "pending").data["submitted_at"] is None
    assert a.patch(f"/api/reimbursements/{rid}/", {"amount": "150.00"}, format="json").data["amount"] == "150.00"
    history = a.get(f"/api/reimbursements/{rid}/history/").data
    assert any("退回待提交" in h["reason"] for h in history)
    advance(a, rid, "submitted")
    r = advance(api(manager), rid, "paid")
    assert r.data["status"] == "paid" and r.data["paid_at"]
    assert a.delete(f"/api/reimbursements/{rid}/").status_code == 409


def test_reimbursement_links_only_the_owners_purchase(api, student_a, student_b, manager, fund):
    mine = create(api(student_a), fund).data["id"]
    theirs = create(api(student_b), fund).data["id"]
    assert reimburse(api(student_a), fund, purchase_id=theirs).status_code == 400  # not visible to a student
    rid = reimburse(api(student_a), fund, purchase_id=mine).data["id"]
    r = api(manager).patch(f"/api/reimbursements/{rid}/", {"purchase_id": theirs}, format="json")
    assert r.status_code == 400 and "purchase_id" in r.data["errors"]
    assert reimburse(api(student_a), fund, amount="0").status_code == 400


def test_statistics_and_export_agree_with_the_records(api, group, student_a, student_b, manager, advisor, fund):
    other = Fund.objects.create(group=group, code="HX-002", name="横向")
    rows = [
        (student_a, fund, "consumable", "136.50", "2026-10-03"),
        (student_a, other, "travel", "820.00", "2026-11-02"),
        (student_b, fund, "consumable", "45.25", "2026-11-09"),
        (student_b, fund, "ai_tool", "140.00", "2026-11-12"),
    ]
    for owner, f, category, amount, day in rows:
        Reimbursement.objects.create(owner=owner, fund=f, category=category, amount=Decimal(amount), occurred_on=day)
    expected = sum(Decimal(r[3]) for r in rows)
    assert api(student_a).get("/api/reimbursements/stats/").status_code == 403
    for by in ("fund", "category", "owner", "month"):
        data = api(advisor).get("/api/reimbursements/stats/", {"by": by}).data
        assert Decimal(data["total"]) == expected and data["count"] == 4
        assert sum(Decimal(r["total"]) for r in data["rows"]) == expected
    data = api(manager).get("/api/reimbursements/stats/", {"by": "month"}).data
    assert [(r["label"], r["total"]) for r in data["rows"]] == [("2026-10", "136.50"), ("2026-11", "1005.25")]
    data = api(manager).get("/api/reimbursements/stats/", {"by": "owner", "category": "consumable"}).data
    assert {r["label"]: r["total"] for r in data["rows"]} == {student_a.name: "136.50", student_b.name: "45.25"}
    assert api(manager).get("/api/reimbursements/stats/", {"by": "nope"}).status_code == 400
    assert api(manager).get("/api/reimbursements/", {"month": "2026-13x"}).status_code == 400
    assert api(manager).get("/api/reimbursements/", {"month": "2026-11", "fund": fund.id}).data["count"] == 2

    r = api(manager).get("/api/reimbursements/export/", {"by": "fund"})
    assert r.status_code == 200 and "attachment" in r["Content-Disposition"]
    book = load_workbook(io.BytesIO(r.content))
    summary, details = book["汇总"], book["明细"]
    summary_rows = list(summary.iter_rows(min_row=2, values_only=True))
    assert summary_rows[-1][0] == "合计" and Decimal(str(summary_rows[-1][2])) == expected
    assert sum(Decimal(str(row[2])) for row in summary_rows[:-1]) == expected
    assert details.max_row == 1 + len(rows)


def test_export_keeps_typed_text_as_text(api, student_a, manager, fund):
    Reimbursement.objects.create(owner=student_a, fund=fund, category="other", amount=Decimal("1"), occurred_on="2026-11-01",
                                 description="=1+1")
    details = load_workbook(io.BytesIO(api(manager).get("/api/reimbursements/export/").content))["明细"]
    note = details.cell(row=2, column=12)
    assert note.value == "=1+1" and note.data_type == "s"  # not a formula Excel would evaluate
    assert details.cell(row=2, column=6).data_type == "n"  # amounts stay numbers


def test_finance_reminder(api, settings, mailoutbox, group, other_group, student_a, manager, other_manager, fund, other_fund):
    enable_mail()
    paid = Reimbursement.objects.create(owner=student_a, fund=fund, category="travel", amount=Decimal("820.00"), occurred_on="2026-11-01")
    for status in ("submitted", "pending"):
        Reimbursement.objects.create(
            owner=student_a, fund=fund, category="consumable", amount=Decimal("45.50"), occurred_on="2026-11-03", status=status
        )
    Reimbursement.objects.filter(pk=paid.pk).update(status="paid")
    # 00:30 Beijing time is still the previous day in UTC: the mail must show the local date
    Reimbursement.objects.filter(status="submitted").update(submitted_at="2026-11-05T00:30+08:00")
    Reimbursement.objects.create(
        owner=other_manager, fund=other_fund, category="other", amount=Decimal("9.90"), occurred_on="2026-11-03", status="submitted",
        submitted_at="2026-11-05T09:00+08:00",
    )

    assert api(manager).post("/api/reimbursements/remind-finance/").status_code == 409  # no finance mailbox yet
    group.finance_email = "finance@example.edu"
    group.save()
    assert api(student_a).post("/api/reimbursements/remind-finance/").status_code == 403
    r = api(manager).post("/api/reimbursements/remind-finance/")
    assert r.data == {"sent": 1, "to": "finance@example.edu"}
    message = mailoutbox[0]
    assert message.to == ["finance@example.edu"] and "45.50" in message.body and "820.00" not in message.body
    assert "交财务 2026-11-05" in message.body
    assert "9.90" not in message.body  # another group's

    mailoutbox.clear()
    other_group.finance_email = "other-finance@example.edu"
    other_group.save()
    call_command("send_finance_reminder", stdout=io.StringIO())
    assert sorted(m.to[0] for m in mailoutbox) == ["finance@example.edu", "other-finance@example.edu"]
    SiteSettings.objects.update(mail_enabled=False)
    assert api(manager).post("/api/reimbursements/remind-finance/").status_code == 409
    assert "系统管理" in api(manager).post("/api/reimbursements/remind-finance/").data["message"]


def test_managers_set_the_finance_email(api, group, student_a, manager, advisor):
    url = "/api/reimbursements/finance-email/"
    assert api(manager).get(url).data == {"finance_email": ""}
    assert api(manager).patch(url, {"finance_email": "finance@example.edu"}, format="json").data == {"finance_email": "finance@example.edu"}
    group.refresh_from_db()
    assert group.finance_email == "finance@example.edu"
    assert api(manager).patch(url, {"finance_email": "不是邮箱"}, format="json").status_code == 400
    for user in (student_a, advisor):
        assert api(user).patch(url, {"finance_email": "x@example.edu"}, format="json").status_code == 403


def test_items_cannot_overflow_the_total(api, student_a, manager, fund):
    """The total is computed on read and shown with 12 digits: a typo must be refused, not stored and 500 forever."""
    huge = [{"name": "5MHz 探头", "quantity": 10000, "unit_price": "1000000.00"}]  # 10 000 000 000.00: 13 digits
    r = create(api(student_a), fund, items=huge)
    assert r.status_code == 400 and "合计" in r.data["errors"]["items"][0]
    r = create(api(student_a), fund, items=[{"name": "线缆", "quantity": 3_000_000_000, "unit_price": "0.00"}])
    assert r.status_code == 400 and "quantity" in r.data["errors"]["items"][0]  # would overflow the integer column
    assert not PurchaseRequest.objects.exists()

    pid = create(api(student_a), fund).data["id"]
    assert api(student_a).patch(f"/api/purchases/{pid}/", {"items": huge}, format="json").status_code == 400
    largest = [{"name": "整机", "quantity": 1, "unit_price": "9999999999.99"}]
    assert api(student_a).patch(f"/api/purchases/{pid}/", {"items": largest}, format="json").status_code == 200
    assert api(manager).get("/api/purchases/").status_code == 200
