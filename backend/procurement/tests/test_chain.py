"""Issue #48 N2: several reimbursements at once, and the purchase list's export."""
import datetime
import io
from decimal import Decimal

import pytest
from openpyxl import load_workbook

from procurement.models import Approval, Attachment, Fund, PurchaseItem, PurchaseRequest, Reimbursement

pytestmark = pytest.mark.django_db
R = Reimbursement.Status


@pytest.fixture
def fund(group):
    return Fund.objects.create(group=group, code="NSFC-001", name="面上")


def bill(owner, fund, invoice=True, status=R.PENDING):
    r = Reimbursement.objects.create(owner=owner, fund=fund, amount=Decimal("10.00"), occurred_on=datetime.date(2026, 11, 2), status=status)
    if invoice:
        Attachment.objects.create(reimbursement=r, kind=Attachment.Kind.INVOICE, name="发票.pdf", size=1, uploaded_by=owner)
    return r


def test_batch_hand_in_lists_the_ones_without_invoice(api, student_a, student_b, fund, other_manager):
    ready, missing, theirs = bill(student_a, fund), bill(student_a, fund, invoice=False), bill(student_b, fund)
    response = api(student_a).post("/api/reimbursements/batch-advance/", {"ids": [ready.pk, missing.pk, theirs.pk, 999999], "status": "submitted"}, format="json")
    assert response.status_code == 200
    assert response.data["done"] == [ready.pk]
    assert [(f["code"], f["reason"]) for f in response.data["failed"]] == [
        (missing.code, "交财务前请先上传发票"), ("", "不存在或无权查看"), ("", "不存在或无权查看"),
    ]
    assert Reimbursement.objects.get(pk=ready.pk).status == R.SUBMITTED
    assert Reimbursement.objects.get(pk=missing.pk).status == R.PENDING


def test_only_managers_mark_several_paid(api, student_a, manager, fund):
    handed = [bill(student_a, fund, status=R.SUBMITTED) for _ in range(2)]
    pending = bill(student_a, fund)
    ids = [r.pk for r in handed] + [pending.pk]
    assert api(student_a).post("/api/reimbursements/batch-advance/", {"ids": ids, "status": "paid"}, format="json").status_code == 403
    result = api(manager).post("/api/reimbursements/batch-advance/", {"ids": ids, "status": "paid"}, format="json").data
    assert result["done"] == [r.pk for r in handed] and [f["id"] for f in result["failed"]] == [pending.pk]
    assert api(manager).post("/api/reimbursements/batch-advance/", {"ids": ids, "status": "pending"}, format="json").status_code == 400


def test_purchase_export_follows_the_list(api, student_a, student_b, manager, fund):
    for owner, purpose, price in ((student_a, "探头", "1200"), (student_b, "耦合剂", "45.5")):
        p = PurchaseRequest.objects.create(owner=owner, fund=fund, purpose=purpose)
        PurchaseItem.objects.create(request=p, name=purpose, spec="Φ10", quantity=2, unit_price=Decimal(price))
    response = api(manager).get("/api/purchases/export/", {"ordering": "total_amount"})
    assert response.status_code == 200
    rows = list(load_workbook(io.BytesIO(response.content)).active.iter_rows(min_row=2, values_only=True))
    assert [(r[1], r[4], r[5], r[6]) for r in rows] == [("s_b", "耦合剂", "耦合剂 Φ10 × 2", 91), ("s_a", "探头", "探头 Φ10 × 2", 2400)]
    mine = api(student_a).get("/api/purchases/export/").content
    assert len(list(load_workbook(io.BytesIO(mine)).active.iter_rows(min_row=2))) == 1  # the student's own only


def test_returned_and_missing_invoice_filters(api, student_a, manager, fund):
    """What the workbench's 采购被退回 and 报销缺发票 open: only those, not every draft or every pending one."""
    sent_back = PurchaseRequest.objects.create(owner=student_a, fund=fund, purpose="退回的", submitted_at=datetime.datetime(2026, 11, 2, tzinfo=datetime.UTC))
    Approval.objects.create(request=sent_back, stage=Approval.Stage.INITIAL, reviewer=manager, verdict=Approval.Verdict.RETURN, total=Decimal("0"))
    PurchaseRequest.objects.create(owner=student_a, fund=fund, purpose="没交过的草稿")
    client = api(student_a)
    assert [p["purpose"] for p in client.get("/api/purchases/", {"mine": "1", "returned": "1"}).data["results"]] == ["退回的"]
    # 采购草稿 counts the drafts never sent back; its "全部" asks for the same
    assert [p["purpose"] for p in client.get("/api/purchases/", {"status": "draft", "returned": "0"}).data["results"]] == ["没交过的草稿"]
    assert client.get("/api/purchases/", {"returned": "x"}).data["count"] == 0
    missing, _ = bill(student_a, fund, invoice=False), bill(student_a, fund)
    rows = client.get("/api/reimbursements/", {"status": "pending", "no_invoice": "1"}).data["results"]
    assert [r["id"] for r in rows] == [missing.pk]
