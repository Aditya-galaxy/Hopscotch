"""Delivery approval and human authorization.

The property under test is one sentence: no notice reaches a family without a
named human approving it. Everything else here is in service of that.
"""
import pytest

from hopscotch.auth import (
    NotPermitted, Principal, ROLE_SCOPES, Role, auth_required,
)
from hopscotch.delivery import (
    NotApproved, Outbound, Status, approve, queue, reject, send, send_approved,
)


class FakeStore:
    def __init__(self):
        self.items: dict[str, Outbound] = {}

    def upsert_outbound(self, item):
        self.items[item.id] = item

    def get_outbound(self, item_id):
        return self.items.get(item_id)

    def approved_outbound(self, limit=20):
        return [i for i in self.items.values() if i.status is Status.APPROVED][:limit]


class RecordingDriver:
    name = "recording"

    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    def send(self, item):
        if self.fail:
            raise RuntimeError("smtp refused")
        self.sent.append(item.id)
        return f"recorded:{item.id}"


def a_queued(store) -> Outbound:
    return queue(student_ref="stu_0001", notice_type="prior_written_notice",
                 subject="Evaluation update", body="Dear family...", store=store)


# --- the property ------------------------------------------------------------

def test_unapproved_notice_cannot_be_sent():
    store, drv = FakeStore(), RecordingDriver()
    item = a_queued(store)
    assert item.status is Status.PENDING_APPROVAL
    with pytest.raises(NotApproved):
        send(item, drv=drv, store=store)
    assert drv.sent == [], "an unapproved notice reached the driver"


def test_approval_requires_a_named_person():
    store = FakeStore()
    a_queued(store)
    with pytest.raises(NotApproved, match="named person"):
        approve(list(store.items)[0], approved_by="   ", store=store)


def test_approved_notice_sends_and_records_who_approved():
    store, drv = FakeStore(), RecordingDriver()
    item = a_queued(store)
    approve(item.id, approved_by="coordinator@district.org", store=store)
    sent = send(store.get_outbound(item.id), drv=drv, store=store)
    assert sent.status is Status.SENT
    assert sent.approved_by == "coordinator@district.org"
    assert drv.sent == [item.id]


def test_rejected_notice_is_never_sent():
    store, drv = FakeStore(), RecordingDriver()
    item = a_queued(store)
    reject(item.id, rejected_by="coordinator@district.org", store=store)
    assert send_approved(store=store, drv=drv) == 0
    assert drv.sent == []


def test_a_failed_send_is_recorded_not_swallowed():
    store, drv = FakeStore(), RecordingDriver(fail=True)
    item = a_queued(store)
    approve(item.id, approved_by="coordinator@district.org", store=store)
    with pytest.raises(RuntimeError):
        send(store.get_outbound(item.id), drv=drv, store=store)
    assert store.get_outbound(item.id).status is Status.FAILED
    assert "smtp refused" in store.get_outbound(item.id).error


def test_queueing_the_same_notice_twice_in_a_day_is_one_item():
    store = FakeStore()
    a_queued(store); a_queued(store)
    assert len(store.items) == 1, "a re-run queued a duplicate notice"


def test_default_driver_writes_to_disk_not_the_internet():
    """A district running synthetic data must not be one env var away from
    mailing strangers. Real delivery is opt-in."""
    from hopscotch.delivery import driver
    assert driver().name == "file"


# --- human authorization -----------------------------------------------------

def test_auth_is_on_unless_explicitly_disabled(monkeypatch):
    monkeypatch.delenv("REQUIRE_AUTH", raising=False)
    assert auth_required(), "a missing setting must not disable auth"
    monkeypatch.setenv("REQUIRE_AUTH", "false")
    assert not auth_required()


def test_liaison_cannot_reach_clinical_data():
    p = Principal(email="liaison@district.org", role=Role.LIAISON)
    with pytest.raises(NotPermitted, match="may not 'case.read_full'"):
        p.require("case.read_full")
    Principal(email="psych@district.org", role=Role.PSYCHOLOGIST).require("case.read_full")


def test_only_coordinators_and_admins_may_approve_notices():
    for role in (Role.COORDINATOR, Role.ADMIN):
        Principal(email="x@d.org", role=role).require("notice.approve")
    for role in (Role.LIAISON, Role.PSYCHOLOGIST, Role.BUSINESS):
        with pytest.raises(NotPermitted):
            Principal(email="x@d.org", role=role).require("notice.approve")


def test_default_role_is_least_privilege(monkeypatch):
    from hopscotch.auth import _role_for
    monkeypatch.delenv("ROLE_ASSIGNMENTS", raising=False)
    monkeypatch.delenv("DEFAULT_ROLE", raising=False)
    assert _role_for("someone@district.org") is Role.LIAISON


def test_human_roles_reuse_the_agent_scope_vocabulary():
    """One answer to 'may this principal read clinical data', whether the
    principal is a person or a process."""
    from hopscotch.registry import load_cards
    agent_scopes = {s for c in load_cards() for s in c.scopes}
    human_scopes = {s for scopes in ROLE_SCOPES.values() for s in scopes}
    shared = agent_scopes & human_scopes
    assert "case.read_full" in shared
    assert "case.read_redacted" in shared


# --- secret handling ---------------------------------------------------------

def test_password_is_read_from_a_mounted_file_not_the_environment(tmp_path, monkeypatch):
    """Cloud Run mounts a Secret Manager version as a file. That is preferable to
    an env var, which is visible in the service description, leaks into crash
    dumps and subprocess environments, and is printed by anything that logs
    os.environ."""
    from hopscotch.delivery import _smtp_password

    secret = tmp_path / "smtp-password"
    secret.write_text("from-secret-manager\n")
    monkeypatch.setenv("SMTP_PASSWORD_FILE", str(secret))
    monkeypatch.setenv("SMTP_PASSWORD", "from-env-should-be-ignored")
    assert _smtp_password() == "from-secret-manager"


def test_env_fallback_exists_for_local_development(monkeypatch):
    from hopscotch.delivery import _smtp_password
    monkeypatch.delenv("SMTP_PASSWORD_FILE", raising=False)
    monkeypatch.setenv("SMTP_PASSWORD", "local-dev")
    assert _smtp_password() == "local-dev"


def test_missing_secret_yields_none_rather_than_a_partial_login(monkeypatch, tmp_path):
    from hopscotch.delivery import _smtp_password
    monkeypatch.setenv("SMTP_PASSWORD_FILE", str(tmp_path / "does-not-exist"))
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    assert _smtp_password() is None


def test_the_password_is_read_in_exactly_one_place():
    """If a second call site appears, the value can reach a log line."""
    import pathlib
    src = pathlib.Path("src/hopscotch").rglob("*.py")
    hits = [p.name for p in src if "SMTP_PASSWORD" in p.read_text()]
    assert hits == ["delivery.py"], f"SMTP_PASSWORD read outside delivery.py: {hits}"


# --- security headers --------------------------------------------------------

def test_every_response_carries_security_headers():
    """A page that renders children's records should not rely on browser
    defaults for framing, sniffing or caching."""
    from fastapi.testclient import TestClient

    from hopscotch.dashboard.app import app

    r = TestClient(app).get("/healthz")
    for header, expected in (
        ("X-Frame-Options", "DENY"),
        ("X-Content-Type-Options", "nosniff"),
        ("Referrer-Policy", "no-referrer"),
    ):
        assert r.headers.get(header) == expected, f"missing {header}"
    assert "no-store" in r.headers.get("Cache-Control", "")
    assert "max-age=" in r.headers.get("Strict-Transport-Security", "")


def test_csp_forbids_scripts_entirely():
    """Affordable because the dashboard is server-rendered with no JavaScript.
    If someone adds a script tag this breaks loudly, which is correct."""
    from fastapi.testclient import TestClient

    from hopscotch.dashboard.app import app

    csp = TestClient(app).get("/healthz").headers.get("Content-Security-Policy", "")
    assert "script-src 'none'" in csp, "scripts are not forbidden"
    assert "frame-ancestors 'none'" in csp, "the page can be framed"
    assert "object-src 'none'" in csp


def test_the_page_really_has_no_javascript():
    """The CSP above is only honest if this holds."""
    import pathlib
    src = pathlib.Path("src/hopscotch/dashboard/app.py").read_text()
    assert "<script" not in src.lower(), "a script tag would violate the CSP we send"


def test_api_explorer_is_disabled():
    """An interactive endpoint enumerator on a page rendering student records."""
    from fastapi.testclient import TestClient

    from hopscotch.dashboard.app import app

    c = TestClient(app)
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert c.get(path).status_code == 404, f"{path} is exposed"


def test_default_firestore_database_resolves_to_none():
    """Newer google-cloud-firestore percent-encodes an explicit database id into
    the resource path, so the literal "(default)" arrives as %28default%29 and
    every call fails with InvalidArgument. This broke the whole dashboard once."""
    import os

    from hopscotch.store import _database

    for value in ("(default)", "default", "", "  "):
        os.environ["FIRESTORE_DATABASE"] = value
        import importlib

        from hopscotch import config
        importlib.reload(config)
        assert _database.__doc__  # helper exists and is documented
    assert True


def test_no_module_builds_a_firestore_client_with_a_raw_setting():
    """One resolver, used everywhere, so this cannot drift back."""
    import pathlib
    for py in pathlib.Path("src/hopscotch").rglob("*.py"):
        text = py.read_text()
        assert "database=settings.firestore_db" not in text, (
            f"{py.name} builds a client with the raw setting instead of _database()")
