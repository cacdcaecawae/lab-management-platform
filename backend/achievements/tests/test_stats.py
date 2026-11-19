from io import BytesIO

import pytest
from openpyxl import load_workbook

from achievements.models import Achievement

pytestmark = pytest.mark.django_db
STATS = "/api/achievements/stats/"


def test_formal_scope_dedup_and_excel(api, group, student_a, student_b, manager, advisor, other_manager):
    def record(kind, status, year=2026, group=group, title="测试成果"):
        return Achievement.objects.create(group=group, created_by=manager, title=title, authors="合成署名",
                                          date=f"{year}-01-01", type=kind, status=status)

    paper = record("paper", "accepted")
    paper.members.add(student_a, student_a, student_b, other_manager)
    record("paper", "published", year=2025).members.add(student_a)
    record("patent", "granted").members.add(student_a)
    record("award", "awarded")  # external authors only: counted once globally, not by member
    record("software", "registered").members.add(student_b)
    record("paper", "submitted").members.add(student_a)
    record("patent", "filed").members.add(student_a)
    record("award", "awarded", group=other_manager.group)
    student_b.name = "=1+1"
    student_b.save(update_fields=["name"])

    client = api(student_a)
    data = client.get(STATS).data
    assert data["status"] == "formal"
    assert data["total"] == {"paper": 2, "patent": 1, "award": 1, "software": 1, "total": 5}
    assert [row["year"] for row in data["by_year"]] == [2025, 2026]
    assert [row["total"] for row in data["by_year"]] == [1, 4]
    by_user = {row["user"]["id"]: row for row in data["by_member"]}
    assert set(by_user) == {student_a.pk, student_b.pk}
    assert [(by_user[who]["paper"], by_user[who]["total"]) for who in (student_a.pk, student_b.pk)] == [(2, 3), (1, 2)]
    assert api(other_manager).get(STATS).data["total"]["total"] == 1
    assert api(advisor).get(STATS).data["total"] == data["total"]
    assert api(manager).get(STATS, {"status": "all"}).data["total"]["total"] == 7
    assert api(manager).get(STATS, {"status": "accepted,published"}).data["total"]["total"] == 2
    assert client.get("/api/achievements/", {"status": "formal"}).data["count"] == data["total"]["total"]
    assert client.get(STATS, {"year_from": 2026, "year_to": 2026}).data["total"]["total"] == 4
    assert client.get(STATS, {"year_to": 2024}).data["by_year"] == []

    excel = client.get(STATS + "export/")
    assert excel.status_code == 200
    book = load_workbook(BytesIO(excel.content))
    assert book.sheetnames == ["按年统计", "按成员统计"]
    total_row = ("全组去重总计", 2, 1, 1, 1, 5)
    columns = ("paper", "patent", "award", "software", "total")
    for sheet, key, get_label in [
        ("按年统计", "by_year", lambda row: row["year"]),
        ("按成员统计", "by_member", lambda row: row["user"]["name"]),
    ]:
        assert list(book[sheet].values)[1:] == [
            (get_label(row), *(row[k] for k in columns)) for row in data[key]
        ] + [total_row]
    example = [row[0] for row in book["按成员统计"].iter_rows() if row[0].value == "=1+1"]
    assert example and example[0].data_type == "s"


@pytest.mark.parametrize("query", [
    {"year_from": 2026, "year_to": 2025}, {"year_from": 0}, {"year_to": 10000}, {"status": "unknown"},
])
def test_stats_reject_invalid_filters(api, student_a, query):
    assert api(student_a).get(STATS, query).status_code == 400
    assert api(student_a).get(STATS + "export/", query).status_code == 400
