import pytest

from specimens.models import Specimen, SpecimenLoan

pytestmark = pytest.mark.django_db

URL = "/api/specimens/"
BLOCK = {
    "code": "CSK-IA-01",
    "name": "CSK-IA 标准试块",
    "kind": "standard",
    "material": "20 钢",
    "dimensions": "300×100×25 mm",
    "defects": [
        {"kind": "sdh", "size_mm": "2.00", "depth_mm": "15.00", "position": "距左端 50 mm"},
        {"kind": "fbh", "size_mm": "3.00", "depth_mm": "40.00"},
    ],
}


def create(api, manager, **extra):
    r = api(manager).post(URL, {**BLOCK, **extra}, format="json")
    assert r.status_code == 201, r.json()
    return r.json()


def test_only_managers_create_and_edit(api, student_a, advisor, manager):
    for user in (student_a, advisor):
        assert api(user).post(URL, BLOCK, format="json").status_code == 403
    data = create(api, manager)
    assert [(d["kind"], d["size_mm"]) for d in data["defects"]] == [("sdh", "2.00"), ("fbh", "3.00")]
    assert data["status"] == "available" and data["current_loan"] is None and data["defects_public"] is False
    assert api(student_a).patch(f"{URL}{data['id']}/", {"name": "x"}, format="json").status_code == 403
    r = api(manager).post(URL, {**BLOCK, "defects": []}, format="json")
    assert r.status_code == 409  # same code in the group


def test_other_groups_see_nothing(api, manager, other_manager):
    data = create(api, manager)
    assert api(other_manager).get(URL).json()["count"] == 0
    assert api(other_manager).get(f"{URL}{data['id']}/").status_code == 404
    assert api(other_manager).post(f"{URL}{data['id']}/borrow/", {}, format="json").status_code == 404
    create(api, other_manager)  # codes are unique per group only


def test_defects_hidden_from_students_until_public(api, student_a, advisor, manager):
    sid = create(api, manager)["id"]
    student = api(student_a).get(f"{URL}{sid}/").json()
    assert student["defects"] is None and student["code"] == "CSK-IA-01"
    assert api(student_a).get(URL).json()["results"][0]["defects"] is None
    assert len(api(advisor).get(f"{URL}{sid}/").json()["defects"]) == 2
    # searching the defect fields would let a student probe the answer
    assert api(student_a).get(URL, {"search": "距左端"}).json()["count"] == 0
    api(manager).patch(f"{URL}{sid}/", {"defects_public": True}, format="json")
    assert len(api(student_a).get(f"{URL}{sid}/").json()["defects"]) == 2


def test_defects_replaced_and_history_keeps_no_values(api, student_a, manager):
    sid = create(api, manager)["id"]
    same = [{**d, "size_mm": d["size_mm"].rstrip("0").rstrip(".")} for d in BLOCK["defects"]]  # "2" == "2.00"
    api(manager).patch(f"{URL}{sid}/", {"defects": same}, format="json")
    changed = api(manager).patch(f"{URL}{sid}/", {"defects": [{"kind": "notch", "size_mm": "10", "depth_mm": "1"}]}, format="json")
    assert [d["kind"] for d in changed.json()["defects"]] == ["notch"]
    history = api(student_a).get(f"{URL}{sid}/history/").json()
    reasons = [h["reason"] for h in history]
    assert reasons.count("修改了缺陷参数") == 1, reasons
    assert "notch" not in str(history) and "10.00" not in str(history)


def test_borrow_and_return(api, student_a, student_b, manager, project):
    sid = create(api, manager)["id"]
    url = f"{URL}{sid}/"
    r = api(student_a).post(f"{url}borrow/", {"project_id": project.id, "purpose": "重复性实验", "due_date": "2026-12-01"}, format="json")
    assert r.status_code == 201, r.json()
    assert r.json()["borrower"]["id"] == student_a.id and r.json()["project"]["name"] == project.name
    assert api(student_b).get(url).json()["current_loan"]["borrower"]["id"] == student_a.id
    loan_id = r.json()["id"]
    second = api(student_b).post(f"{url}borrow/", {}, format="json")
    assert (second.status_code, second.json()["code"]) == (409, "on_loan")
    assert api(student_b).get(URL, {"on_loan": "1"}).json()["count"] == 1
    assert api(student_b).get(URL, {"mine": "1"}).json()["count"] == 0
    assert api(student_a).get(URL, {"mine": "1"}).json()["count"] == 1
    assert api(student_b).post(f"{url}return/", {"loan_id_seen": loan_id}, format="json").status_code == 403
    done = api(student_a).post(f"{url}return/", {"loan_id_seen": loan_id, "note": "完好"}, format="json")
    assert done.status_code == 200 and done.json()["returned_by"]["id"] == student_a.id and done.json()["return_note"] == "完好"
    again = api(student_a).post(f"{url}return/", {"loan_id_seen": loan_id}, format="json")
    assert (again.status_code, again.json()["code"]) == (409, "not_on_loan")
    # a manager may close someone else's loan, e.g. when the borrower has left
    loan_id = api(student_b).post(f"{url}borrow/", {}, format="json").json()["id"]
    assert api(manager).post(f"{url}return/", {"loan_id_seen": loan_id}, format="json").status_code == 200
    loans = api(student_a).get(f"{url}loans/").json()
    assert loans["count"] == 2 and all(loan["returned_at"] for loan in loans["results"])


def test_only_available_specimens_are_lent(api, student_a, manager):
    sid = create(api, manager)["id"]
    api(manager).patch(f"{URL}{sid}/", {"status": "damaged"}, format="json")
    r = api(student_a).post(f"{URL}{sid}/borrow/", {}, format="json")
    assert (r.status_code, r.json()["code"]) == (409, "not_available")
    assert not SpecimenLoan.objects.exists()


def test_one_open_loan_is_a_database_rule(manager, student_a, group):
    from django.db import IntegrityError, transaction

    s = Specimen.objects.create(group=group, code="S-1", name="试样")
    SpecimenLoan.objects.create(specimen=s, borrower=student_a)
    with pytest.raises(IntegrityError), transaction.atomic():
        SpecimenLoan.objects.create(specimen=s, borrower=manager)


def test_experiments_link_specimens_from_my_group(api, student_a, manager, other_manager, project):
    mine = create(api, manager)
    outside = create(api, other_manager)
    body = {"project_id": project.pk, "title": "声速测量", "date": "2026-11-18"}
    r = api(student_a).post("/api/experiments/", {**body, "specimen_item_ids": [outside["id"]]}, format="json")
    assert r.status_code == 400 and "specimen_item_ids" in r.json()["errors"]
    data = api(student_a).post("/api/experiments/", {**body, "specimen_item_ids": [mine["id"]]}, format="json").json()
    # the brief form only: an experiment never carries the defects
    assert data["specimen_items"] == [{"id": mine["id"], "code": "CSK-IA-01", "name": "CSK-IA 标准试块", "status": "available"}]


@pytest.mark.parametrize('new_borrower', ['same', 'different'])
@pytest.mark.parametrize('returner', ['manager', 'borrower'])
def test_old_return_does_not_close_new_loan(api, student_a, student_b, manager, new_borrower, returner):
    sid = create(api, manager)['id']
    url = f'{URL}{sid}/'
    first = api(student_a).post(f'{url}borrow/', {}, format='json').json()['id']
    assert api(student_a).post(f'{url}return/', {'loan_id_seen': first}, format='json').status_code == 200
    borrower = student_a if new_borrower == 'same' else student_b
    second = api(borrower).post(f'{url}borrow/', {}, format='json').json()['id']
    actor = manager if returner == 'manager' else student_a
    stale = api(actor).post(f'{url}return/', {'loan_id_seen': first, 'note': 'old loan'}, format='json')
    assert (stale.status_code, stale.json()['code']) == (409, 'stale_loan')
    loan = SpecimenLoan.objects.get(pk=second)
    assert loan.returned_at is None and loan.returned_by_id is None and loan.return_note == ''
    assert api(borrower).post(f'{url}return/', {'loan_id_seen': second}, format='json').status_code == 200


@pytest.mark.parametrize('body', [{}, {'loan_id_seen': None}, {'loan_id_seen': 0}, {'loan_id_seen': 'bad'}])
def test_return_requires_seen_loan(api, student_a, manager, body):
    sid = create(api, manager)['id']
    url = f'{URL}{sid}/'
    loan_id = api(student_a).post(f'{url}borrow/', {}, format='json').json()['id']
    response = api(student_a).post(f'{url}return/', body, format='json')
    assert response.status_code == 400 and 'loan_id_seen' in response.json()['errors']
    assert SpecimenLoan.objects.get(pk=loan_id).returned_at is None


@pytest.mark.parametrize('row', [{}, {'size_mm': '2.0'}, {'kind': None}, {'kind': ''}, {'kind': 'invalid'}])
def test_patch_defect_requires_kind_and_preserves_data(api, manager, row):
    sid = create(api, manager)['id']
    specimen = Specimen.objects.get(pk=sid)
    old = list(specimen.defects.values())
    history_count = specimen.history.count()
    response = api(manager).patch(f'{URL}{sid}/', {'name': 'must not save', 'defects': [row]}, format='json')
    assert response.status_code == 400 and 'kind' in response.json()['errors']['defects']['0']
    specimen.refresh_from_db()
    assert specimen.name == BLOCK['name']
    assert list(specimen.defects.values()) == old
    assert specimen.history.count() == history_count


def test_patch_omitted_defects_preserved_and_empty_list_clears(api, manager):
    sid = create(api, manager)['id']
    url = f'{URL}{sid}/'
    assert api(manager).patch(url, {'location': 'B'}, format='json').status_code == 200
    assert Specimen.objects.get(pk=sid).defects.count() == 2
    assert api(manager).patch(url, {'defects': []}, format='json').status_code == 200
    assert Specimen.objects.get(pk=sid).defects.count() == 0
