import io
import json
import os
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


def test_refresh_asks_github_again(api, ops, github):
    api(ops).get(URL)
    api(ops).get(URL, {"refresh": "1"})
    assert github.calls == 2


@pytest.fixture
def agent(settings, tmp_path):
    """run/update/ as the backend sees it, with scripts/update-agent.sh alive."""
    settings.UPDATE_DIR = tmp_path
    (tmp_path / "request").mkdir()
    (tmp_path / "status").mkdir()
    (tmp_path / "status" / "agent").touch()
    return tmp_path


UPDATE = "/api/system/update/"


def test_update_leaves_a_request_for_the_agent(api, ops, github, settings, agent):
    settings.APP_VERSION = "v0.2.9"
    assert api(ops).get(URL).data["agent"] is True
    r = api(ops).post(UPDATE, {"target": "v0.3.0"}, format="json")
    assert r.status_code == 202 and r.data["target"] == "v0.3.0"
    assert [p.name for p in (agent / "request").iterdir()] == ["v0.3.0"]
    r = api(ops).post(UPDATE, {"target": "v0.3.0"}, format="json")
    assert (r.status_code, r.data["code"]) == (409, "updating")


@pytest.mark.parametrize(
    "current, target",
    [
        ("v0.3.0", "v0.3.0"),  # already running it
        ("v0.2.9", "v0.2.9"),  # not the newest release
        ("v0.2.9", "../../etc/x"),
        ("local", "v0.3.0"),  # built from source: update.sh cannot tell what it would replace
    ],
)
def test_update_only_to_the_newest_release(api, ops, github, settings, agent, current, target):
    settings.APP_VERSION = current
    r = api(ops).post(UPDATE, {"target": target}, format="json")
    assert (r.status_code, r.data["code"]) == (409, "not_latest")
    assert not any((agent / "request").iterdir())


def test_update_needs_the_agent_and_ops(api, ops, manager, github, settings, agent):
    settings.APP_VERSION = "v0.2.9"
    assert api(manager).post(UPDATE, {"target": "v0.3.0"}, format="json").status_code == 403
    os.utime(agent / "status" / "agent", (0, 0))  # stopped long ago
    assert api(ops).get(URL).data["agent"] is False
    r = api(ops).post(UPDATE, {"target": "v0.3.0"}, format="json")
    assert (r.status_code, r.data["code"]) == (409, "no_agent")
    assert not any((agent / "request").iterdir())


def test_parse_version():
    assert views.parse_version("v1.20.3") == (1, 20, 3)
    for tag in ("local", "1.2.3", "v1.2", "v1.2.3-rc1", None):
        assert views.parse_version(tag) is None
