from datetime import datetime
from io import BytesIO

import pytest
from openpyxl import load_workbook

from equipment.models import Booking, Equipment, UsageReport

pytestmark = pytest.mark.django_db
URL = "/api/equipment/usage-stats/"
QUERY = {"from": "2026-11-30", "to": "2026-12-02"}


def dt(s):
    return datetime.fromisoformat(s + "+08:00")


def test_month_clip_and_counts(api, group, manager, advisor, student_a, other_manager):
    equipment = Equipment.objects.create(group=group, code="A", name="校验")
    Equipment.objects.create(group=group, code="B", name="无预约")
    cross = Booking.objects.create(
        equipment=equipment, user=student_a, start_at=dt("2026-11-30T23:00"), end_at=dt("2026-12-01T02:00")
    )
    UsageReport.objects.create(booking=cross, condition="abnormal")
    Booking.objects.create(equipment=equipment, user=student_a, start_at=dt("2026-11-29T23:00"), end_at=dt("2026-11-30T01:00"))
    Booking.objects.create(equipment=equipment, user=student_a, start_at=dt("2026-12-01T23:00"), end_at=dt("2026-12-02T01:00"))
    Booking.objects.create(equipment=equipment, user=student_a, kind="maintenance",
                           start_at=dt("2026-12-01T02:00"), end_at=dt("2026-12-01T03:00"))
    Booking.objects.create(equipment=equipment, user=student_a, cancelled_at=dt("2026-12-01T01:00"),
                           start_at=dt("2026-12-01T02:00"), end_at=dt("2026-12-01T03:00"))
    client = api(manager)
    months = client.get(URL, {**QUERY, "by": "month"})
    assert months.status_code == 200
    assert [(r["key"]["id"], r["booked_hours"], r["reported_hours"], r["bookings"], r["abnormal"]) for r in months.data] == [
        ("2026-11", 2, 1, 2, 1), ("2026-12", 3, 2, 1, 0)
    ]
    assert api(advisor).get(URL, QUERY).status_code == 200
    assert api(student_a).get(URL, QUERY).status_code == 403
    assert api(student_a).get(URL + "export/", QUERY).status_code == 403
    assert api(other_manager).get(URL, QUERY).data == []
    equipment_rows = client.get(URL, QUERY).data
    assert [(r["key"]["label"], r["booked_hours"], r["bookings"]) for r in equipment_rows] == [("A 校验", 5, 3), ("B 无预约", 0, 0)]
    assert client.get(URL, {**QUERY, "by": "user"}).data[0]["key"]["id"] == student_a.pk
    assert client.get(URL, {**QUERY, "by": "project"}).data[0]["key"] == {"id": None, "label": "未关联项目"}
    exported = client.get(URL + "export/", {**QUERY, "by": "month"})
    assert exported.status_code == 200
    assert list(load_workbook(BytesIO(exported.content)).active.values)[1:] == [("2026-11", 2, 1, 2, 1), ("2026-12", 3, 2, 1, 0)]


@pytest.mark.parametrize("query", [{}, {"from": "2026-11-30", "to": "2026-11-30"}, {"from": "2026-01-01", "to": "2027-01-03"}, {**QUERY, "by": "invalid"}])
def test_invalid_query(api, manager, query):
    assert api(manager).get(URL, query).status_code == 400
    assert api(manager).get(URL + "export/", query).status_code == 400


def test_historical_usage_keeps_counts_without_out_of_group_labels(api, group, manager, student_a, student_b, project, other_group):
    equipment = Equipment.objects.create(group=group, code="SCOPE", name="校验")
    moved = Booking.objects.create(
        equipment=equipment, user=student_a, project=project, start_at=dt("2026-12-01T09:00"), end_at=dt("2026-12-01T11:00"),
    )
    UsageReport.objects.create(booking=moved, condition="abnormal")
    Booking.objects.create(
        equipment=equipment, user=student_b, start_at=dt("2026-12-01T12:00"), end_at=dt("2026-12-01T13:00"),
    )
    student_a.group = other_group
    student_a.name = "本组不可见的当前姓名"
    student_a.save(update_fields=["group", "name"])
    project.group = other_group
    project.name = "本组不可见的当前项目名"
    project.save(update_fields=["group", "name"])
    client = api(manager)
    for by, label, expected in [
        ("user", "未归属成员", [(student_b.pk, 1, 0, 1, 0), (None, 2, 2, 1, 1)]),
        ("project", "未关联项目", [(None, 3, 2, 2, 1)]),
    ]:
        args = {**QUERY, "by": by}
        result = client.get(URL, args)
        assert result.status_code == 200
        fields = ("booked_hours", "reported_hours", "bookings", "abnormal")
        assert [(r["key"]["id"], *(r[field] for field in fields)) for r in result.data] == expected
        assert result.data[-1]["key"] == {"id": None, "label": label}
        exported = client.get(URL + "export/", args)
        book_rows = list(load_workbook(BytesIO(exported.content)).active.values)[1:]
        assert book_rows == [(r["key"]["label"], *(r[field] for field in fields)) for r in result.data]
