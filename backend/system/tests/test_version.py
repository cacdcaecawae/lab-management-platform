import io
import json
import urllib.error

import pytest
from django.core.cache import cache

from system import views

pytestmark = pytest.mark.django_db
URL = "/api/system/version/"


@pytest.fixture
def github(monkeypatch):
    """Stands in for api.github.com: set .body (a release) or .error; .calls counts the requests."""

    class GitHub:
        body = {"tag_name": "v0.3.0", "html_url": "https://github.com/x/y/releases/tag/v0.3.0"}
        error = None
        calls = 0

    def urlopen(request, timeout):
        GitHub.calls += 1
        if GitHub.error:
            raise GitHub.error
        return io.BytesIO(json.dumps(GitHub.body).encode())

    cache.delete(views.RELEASE_CACHE)
    monkeypatch.setattr(views.urllib.request, "urlopen", urlopen)
    return GitHub


def test_only_ops(api, github, student_a, manager, advisor):
    for user in (None, student_a, manager, advisor):
        assert api(user).get(URL).status_code == 403
    assert github.calls == 0


@pytest.mark.parametrize(
    "current, update",
    [("v0.2.9", True), ("v0.3.0", False), ("v0.10.0", False), ("local", False)],
)
def test_newer_release_is_offered(api, ops, github, settings, current, update):
    settings.APP_VERSION = current
    data = api(ops).get(URL).data
    assert (data["current"], data["latest"], data["update_available"], data["error"]) == (current, "v0.3.0", update, "")
    assert data["url"].endswith("/v0.3.0")


def test_cached_between_requests(api, ops, github):
    api(ops).get(URL)
    api(ops).get(URL)
    assert github.calls == 1


@pytest.mark.parametrize(
    "error, message",
    [
        (urllib.error.HTTPError("u", 404, "Not Found", {}, None), ""),  # no release yet: nothing to report
        (urllib.error.HTTPError("u", 403, "rate limited", {}, None), "GitHub 返回 403"),
        (urllib.error.URLError("timed out"), "连不上 GitHub：timed out"),
    ],
)
def test_github_failures_do_not_break_the_page(api, ops, github, settings, error, message):
    settings.APP_VERSION = "v0.1.0"
    github.error = error
    r = api(ops).get(URL)
    assert r.status_code == 200
    assert (r.data["latest"], r.data["update_available"], r.data["error"]) == (None, False, message)


def test_parse_version():
    assert views.parse_version("v1.20.3") == (1, 20, 3)
    for tag in ("local", "1.2.3", "v1.2", "v1.2.3-rc1", None):
        assert views.parse_version(tag) is None
