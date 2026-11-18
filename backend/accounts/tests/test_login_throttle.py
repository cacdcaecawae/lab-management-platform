import pytest
from rest_framework.test import APIClient

from conftest import PASSWORD

pytestmark = pytest.mark.django_db

# As Nginx sends it ($proxy_add_x_forwarded_for): the address it saw comes last. REST_FRAMEWORK NUM_PROXIES = 1.
NAT = {"HTTP_X_FORWARDED_FOR": "10.0.0.1"}  # e.g. the campus NAT shared by the whole group
ELSEWHERE = {"HTTP_X_FORWARDED_FOR": "10.0.0.2"}


def attempt(client, username, password="wrong", address=NAT):
    return client.post("/api/auth/login/", {"username": username, "password": password}, format="json", **address)


def test_login_is_limited_per_account_and_address(student_a, student_b):
    client = APIClient()
    assert [attempt(client, "s_a").status_code for _ in range(5)] == [403] * 5
    r = attempt(client, "s_a", PASSWORD)  # 6th try for this account from this address, even with the right password
    assert r.status_code == 429 and r.data["code"] == "throttled"
    assert attempt(client, "s_b", PASSWORD).status_code == 200  # other accounts behind the same address still log in
    assert attempt(APIClient(), " S_A ").status_code == 429  # same account however it is typed
    # Failing on someone's (predictable) student number does not lock them out from where they are.
    assert attempt(APIClient(), "s_a", PASSWORD, ELSEWHERE).status_code == 200
    # A client cannot claim a fresh address: Nginx appends the real one and only the last entry counts.
    assert attempt(APIClient(), "s_a", PASSWORD, {"HTTP_X_FORWARDED_FOR": "1.2.3.4, 10.0.0.1"}).status_code == 429
