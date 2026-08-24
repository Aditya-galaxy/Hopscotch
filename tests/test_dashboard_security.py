"""Security properties of the coordinator surface.

Each test corresponds to something the audit actually found, so a regression
here means a real hole reopened rather than a style change.
"""
import pytest
from fastapi.testclient import TestClient

from hopscotch.auth import Principal, Role
from hopscotch.dashboard.app import app, principal
from hopscotch.dashboard.security import HEADERS


def client_as(role: Role, *, monkeypatch, auth_on=True):
    monkeypatch.setenv("REQUIRE_AUTH", "true" if auth_on else "false")
    app.dependency_overrides[principal] = lambda: Principal(
        email=f"{role.value}@district.org", role=role)
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.clear()


# --- the leak that was live --------------------------------------------------

def test_audio_cannot_be_fetched_by_filename():
    """The old route served any file in the media directory to anyone who knew
    its name -- no authentication, verified returning 200 and 165KB to an
    anonymous request. Filenames were content hashes, which is obscurity, not
    access control. That route no longer exists."""
    c = TestClient(app)
    for path in ("/media/notice-en-US-0c2cc76e4427328e.mp3",
                 "/media/anything.mp3", "/media/../../etc/passwd"):
        assert c.get(path).status_code == 404, f"{path} is still reachable"


def test_audio_requires_authentication(monkeypatch):
    monkeypatch.setenv("REQUIRE_AUTH", "true")
    assert TestClient(app).get("/outbox/anything/audio").status_code == 401


def test_index_requires_authentication(monkeypatch):
    monkeypatch.setenv("REQUIRE_AUTH", "true")
    assert TestClient(app).get("/").status_code == 401


# --- role-scoped rendering ---------------------------------------------------

def test_a_liaison_is_not_shown_the_audit_trail(monkeypatch):
    """The audit trail names every student who moved. It needs case.write."""
    body = client_as(Role.LIAISON, monkeypatch=monkeypatch).get("/").text
    assert "case.write" in body, "no explanation of what is hidden"
    assert "Append-only. Every row" not in body


def test_a_coordinator_is_shown_the_audit_trail(monkeypatch):
    body = client_as(Role.COORDINATOR, monkeypatch=monkeypatch).get("/").text
    assert "Audit trail" in body


def test_a_liaison_cannot_see_claim_readiness(monkeypatch):
    body = client_as(Role.LIAISON, monkeypatch=monkeypatch).get("/").text
    assert "claim.read" in body


def test_the_header_states_whether_clinical_detail_is_visible(monkeypatch):
    """A person should know what they are looking at without guessing."""
    liaison = client_as(Role.LIAISON, monkeypatch=monkeypatch).get("/").text
    assert "clinical detail withheld" in liaison
    assert "liaison" in liaison


# --- read-only when nobody is accountable -----------------------------------

def test_writes_are_refused_when_authentication_is_off(monkeypatch):
    """A public demo must not accept an approval from a stranger. If we cannot
    say who acted, we do not let them act."""
    c = client_as(Role.COORDINATOR, monkeypatch=monkeypatch, auth_on=False)
    for path in ("/outbox/x/approve", "/outbox/x/reject"):
        assert c.post(path).status_code == 403, f"{path} accepted a write"
    assert c.post("/case/stu_0001/correct",
                  data={"field": "due_on", "value": "2026-12-01",
                        "reason": "x"}).status_code == 403


def test_the_read_only_banner_is_shown(monkeypatch):
    body = client_as(Role.COORDINATOR, monkeypatch=monkeypatch,
                     auth_on=False).get("/").text
    assert "Read-only public demo" in body
    assert "REQUIRE_AUTH=true" in body


def test_a_liaison_cannot_approve_a_notice(monkeypatch):
    c = client_as(Role.LIAISON, monkeypatch=monkeypatch)
    assert c.post("/outbox/x/approve").status_code == 403


# --- transport --------------------------------------------------------------

def test_security_headers_are_present():
    r = TestClient(app).get("/healthz")
    for h in ("Content-Security-Policy", "X-Frame-Options",
              "X-Content-Type-Options", "Referrer-Policy", "Cache-Control"):
        assert h in r.headers, f"{h} missing"
    assert "script-src 'none'" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Cache-Control"] == "no-store", "student data may be cached"


def test_cross_origin_writes_are_refused(monkeypatch):
    c = client_as(Role.COORDINATOR, monkeypatch=monkeypatch)
    r = c.post("/outbox/x/approve", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_api_docs_are_not_exposed():
    c = TestClient(app)
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert c.get(path).status_code == 404, f"{path} is exposed"
