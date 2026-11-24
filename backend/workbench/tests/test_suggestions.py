"""Suggestions for free-text fields (issue #48 S4): the group's own values, most used first."""
import pytest

from equipment.models import Equipment
from knowledge.models import Doc

pytestmark = pytest.mark.django_db


def test_most_used_values_of_the_group_only(api, group, other_group, student_a, manager, other_manager):
    for code, place in (("A", "A302"), ("B", "A302"), ("C", "A-302"), ("D", "")):
        Equipment.objects.create(group=group, code=code, name=code, location=place)
    Equipment.objects.create(group=other_group, code="X", name="X", location="外组仓库")
    client = api(student_a)
    assert client.get("/api/suggestions/equipment.location/").data == ["A302", "A-302"]
    assert client.get("/api/suggestions/equipment.location/", {"search": "a-"}).data == ["A-302"]
    assert client.get("/api/suggestions/equipment.location/", {"search": "外组"}).data == []
    assert api(other_manager).get("/api/suggestions/equipment.location/").data == ["外组仓库"]


def test_tags_unknown_fields_and_bad_input(api, group, student_a, manager):
    Doc.objects.create(group=group, author=manager, title="手册", category="manual", tags=["探头", "校准"])
    Doc.objects.create(group=group, author=manager, title="规程", category="manual", tags=["校准"])
    client = api(student_a)
    assert client.get("/api/suggestions/doc.tags/").data == ["校准", "探头"]
    assert client.get("/api/suggestions/doc.tags/", {"search": "探"}).data == ["探头"]
    assert client.get("/api/suggestions/user.password/").status_code == 404
    assert client.get("/api/suggestions/equipment.location/", {"search": "a\x00"}).status_code == 400
