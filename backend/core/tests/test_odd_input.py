"""Odd ids and query values get an empty list or a client error, never a 500 (issue #48 B6)."""

import pytest

pytestmark = pytest.mark.django_db

NOT_A_NUMBER = "\u00b2"  # passes str.isdigit(), fails int()
TOO_BIG = "99999999999999999999"  # passes int(), overflows PostgreSQL's bigint
NUL = "\x00"  # PostgreSQL cannot compare or store it

CASES = [
    ("/api/projects/abc/tasks/", {}),
    (f"/api/projects/{NOT_A_NUMBER}/milestones/", {}),
    ("/api/reimbursements/", {"owner": NOT_A_NUMBER}),
    ("/api/reimbursements/stats/", {"fund": NOT_A_NUMBER}),
    ("/api/docs/", {"equipment": NOT_A_NUMBER}),
    ("/api/docs/", {"search": NUL}),
    ("/api/docs/", {"tag": NUL}),
    ("/api/achievements/", {"member": NOT_A_NUMBER}),
    ("/api/achievements/", {"search": NUL}),
    ("/api/achievements/export/", {"year": TOO_BIG}),
    ("/api/specimens/", {"status": NUL}),
    ("/api/consumables/", {"expiring_within": NOT_A_NUMBER}),
    # issue #48 S2-S4: the new filters, sorting and code search
    ("/api/equipment/", {"custodian": TOO_BIG}),
    ("/api/equipment/", {"category": NUL}),
    ("/api/specimens/", {"material": NUL}),
    ("/api/consumables/", {"ordering": "nearest_expiry_on" + NUL}),
    ("/api/purchases/", {"fund": NOT_A_NUMBER}),
    ("/api/purchases/", {"search": "PR-9999-99999999999999999999"}),
    ("/api/reimbursements/", {"search": NUL}),
    ("/api/meetings/", {"search": NUL}),
    ("/api/suggestions/specimen.location/", {"search": NUL}),
]


@pytest.mark.parametrize(("url", "query"), CASES)
def test_odd_input_is_not_a_server_error(api, manager, url, query):
    client = api(manager)
    client.raise_request_exception = False
    assert client.get(url, query).status_code < 500


def test_ops_account_list(api, ops):
    client = api(ops)
    client.raise_request_exception = False
    assert client.get("/api/system/accounts/", {"group": NOT_A_NUMBER}).data["results"] == []
    assert client.get("/api/system/accounts/", {"search": NUL}).status_code == 400  # DRF's SearchFilter


def test_a_day_window_of_zero_still_counts(api, manager):
    assert api(manager).get("/api/consumables/", {"expiring_within": "0"}).status_code == 200


def test_a_nul_in_a_hand_written_search_is_a_400(api, manager):
    for url in ("/api/docs/", "/api/achievements/"):
        assert api(manager).get(url, {"search": NUL}).status_code == 400  # as with DRF's SearchFilter elsewhere
