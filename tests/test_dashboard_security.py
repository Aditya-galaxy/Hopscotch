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
    assert TestClient(app).get("/app").status_code == 401


# --- role-scoped rendering ---------------------------------------------------

def test_a_liaison_is_not_shown_the_audit_trail(monkeypatch):
    """The audit trail names every student who moved. It needs case.write."""
    body = client_as(Role.LIAISON, monkeypatch=monkeypatch).get("/app").text
    assert "case.write" in body, "no explanation of what is hidden"
    assert "Append-only. Every row" not in body


def test_a_coordinator_is_shown_the_audit_trail(monkeypatch):
    body = client_as(Role.COORDINATOR, monkeypatch=monkeypatch).get("/app").text
    assert "Audit trail" in body


def test_a_liaison_cannot_see_claim_readiness(monkeypatch):
    body = client_as(Role.LIAISON, monkeypatch=monkeypatch).get("/app").text
    assert "claim.read" in body


def test_the_header_states_whether_clinical_detail_is_visible(monkeypatch):
    """A person should know what they are looking at without guessing."""
    liaison = client_as(Role.LIAISON, monkeypatch=monkeypatch).get("/app").text
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
                     auth_on=False).get("/app").text
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


# --- the public front door ---------------------------------------------------

def test_the_landing_page_is_public_and_needs_no_identity(monkeypatch):
    """/ is marketing, not application. It must render for someone who is not
    signed in and never will be, even with authentication switched on."""
    monkeypatch.setenv("REQUIRE_AUTH", "true")
    r = TestClient(app).get("/")
    assert r.status_code == 200
    assert "Sixty days from" in r.text


def test_the_landing_page_is_actually_bundled():
    """The image copies site/ as its own COPY line, and a page served from disk
    fails in the container while working perfectly on a laptop. Assert the file
    is where the app looks for it, and that the fallback is not what shipped.
    """
    r = TestClient(app).get("/")
    assert "not bundled in this image" not in r.text
    assert "/app" in r.text, "the demo link must point at the application"


def test_the_landing_page_grants_no_script_capability():
    """Admitting the font hosts must not have opened script execution."""
    r = TestClient(app).get("/")
    csp = r.headers["content-security-policy"]
    assert "script-src 'none'" in csp
    assert "fonts.googleapis.com" in csp and "fonts.gstatic.com" in csp
    assert "<script" not in r.text.lower()


def test_no_write_ever_redirects_onto_the_landing_page():
    """Post-redirect-GET must land back in the application.

    When the dashboard moved from / to /app, four of these redirects sat on
    continuation lines and were missed, so a successful intake bounced the
    coordinator onto the marketing page with a success message they could not
    act on. Cheap to assert, easy to break again.
    """
    import re
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "src/hopscotch/dashboard/app.py"
    bad = re.findall(r'RedirectResponse\(\s*f?"/(?:\?|"|,)', src.read_text())
    assert not bad, f"redirect targets the landing page: {bad}"


# --- the family surface and record-level scoping -----------------------------

def _as(role, monkeypatch, student=None):
    monkeypatch.setenv("REQUIRE_AUTH", "false")
    c = TestClient(app)
    c.cookies.set("demo_role", role)
    if student:
        c.cookies.set("demo_student", student)
    return c


def test_a_parent_cannot_open_another_familys_case(monkeypatch):
    """The boundary this whole role exists for.

    Field-level projection decides WHAT a caller sees and can never express
    WHOSE. A parent holds a legitimate scope for evaluation dates and still may
    not read another child's.
    """
    c = _as("parent", monkeypatch, student="stu_0001")
    assert c.get("/case/stu_0001").status_code == 200
    assert c.get("/case/stu_0017").status_code == 404


def test_the_refusal_is_404_not_403(monkeypatch):
    """403 confirms the record exists and belongs to someone else, which tells
    a stranger a named student is enrolled and under evaluation."""
    c = _as("parent", monkeypatch, student="stu_0001")
    assert c.get("/case/stu_0017").status_code == 404


def test_an_unbound_parent_is_refused_every_record_not_all_of_them(monkeypatch):
    """The fail-open that was actually there: require_record returned early on
    a missing binding, which is right for staff and inverted for a parent."""
    from hopscotch.auth import NotThisRecord, Principal, Role

    p = Principal(email="p@example.com", role=Role.PARENT, student_ref=None)
    try:
        p.require_record("stu_0001")
        raise AssertionError("an unbound parent was admitted to a record")
    except NotThisRecord:
        pass


def test_a_parent_is_shown_no_clinical_field(monkeypatch):
    from hopscotch.auth import Principal, Role
    from hopscotch.gateway import project_for_scopes
    from hopscotch.schemas import Case, CaseStage, ConsentEvent
    from datetime import date

    case = Case(student_ref="stu_x", school_code="EL-1", jurisdiction="US_FEDERAL",
                stage=CaseStage.CONSENT_RECEIVED,
                consent=ConsentEvent(student_ref="stu_x", school_code="EL-1",
                                     jurisdiction="US_FEDERAL",
                                     received_on=date(2026, 6, 1),
                                     referral_reason="clinical narrative here",
                                     confidence=0.9, source_document="raw form"))
    view = project_for_scopes(Principal(email="p@e.com", role=Role.PARENT,
                                        student_ref="stu_x").scopes, case)
    consent = view.get("consent", {})
    assert "referral_reason" not in consent
    assert "source_document" not in consent
    assert "received_on" in consent, "a parent must still see their own dates"


def test_identity_switching_is_refused_once_auth_is_on(monkeypatch):
    """It is a demo affordance, not an impersonation feature."""
    monkeypatch.setenv("REQUIRE_AUTH", "true")
    assert TestClient(app).get("/demo/as/parent",
                               follow_redirects=False).status_code == 403


def test_no_audio_player_is_offered_without_bytes_behind_it():
    """A control that cannot work is a worse promise than no control.

    Chirp runs inside the tick's own container and used to write to its local
    disk, so twenty notices carried a path whose file had never existed in the
    dashboard's container. The player rendered; it could only ever 404.
    """
    from hopscotch.dashboard.app import _audio_cell

    class Item:
        id = "abc"
        student_ref = "stu_x"
        audio_path = "data/media/does-not-exist-anywhere.mp3"

    assert "<audio" not in _audio_cell(Item())
    Item.audio_path = None
    assert "<audio" not in _audio_cell(Item())
    assert "text only" in _audio_cell(Item())


def test_a_refused_walkthrough_write_answers_403_not_200(monkeypatch):
    """The four tour writes are writes, and a refused write must say so.

    They returned 200 with an explanation page, which is right for a reader
    following a link and wrong for a POST: anyone probing the endpoints saw 200
    and would conclude the document had been filed. Nothing was ever written --
    the guard ran first -- but the status contradicted the behaviour.
    """
    monkeypatch.setenv("REQUIRE_AUTH", "false")
    c = TestClient(app)
    for path in ("/walkthrough/0/do", "/walkthrough/1/do",
                 "/walkthrough/5/do", "/walkthrough/9/do"):
        assert c.post(path).status_code == 403, path
    # the reader's page is not an error
    assert c.get("/walkthrough").status_code == 200


def test_the_most_privileged_reader_is_not_locked_out(monkeypatch):
    """case.read_full is the HIGHEST read scope and was locked out of the
    caseload, because the gate listed scope names by hand and did not mention
    it. A psychologist saw an empty caseload while a liaison saw a full one."""
    from hopscotch.auth import Principal, Role
    from hopscotch.dashboard.app import _read_scope

    psych = Principal(email="p@d.org", role=Role.PSYCHOLOGIST)
    assert _read_scope(psych) == "case.read_full"
    for role in (Role.COORDINATOR, Role.LIAISON, Role.ADMIN, Role.PARENT):
        assert _read_scope(Principal(email="x@d.org", role=role)) is not None, role
    # the business office holds no read scope over cases, only over claims
    assert _read_scope(Principal(email="b@d.org", role=Role.BUSINESS)) is None
