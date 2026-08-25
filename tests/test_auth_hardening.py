"""Regressions for two findings from the security review.

Both were the same mistake in different clothes: a missing setting meant "skip
the check" rather than "refuse". A control that disables itself when
unconfigured is worse than no control, because it looks like it is working.
"""
import pytest
from fastapi import HTTPException

from hopscotch.auth import NotAuthenticated, verify
from hopscotch.dashboard.security import require_same_origin


class FakeRequest:
    def __init__(self, **headers):
        self.headers = {k.lower(): v for k, v in headers.items()}


# --- finding 1: audience and domain must fail closed -------------------------

def test_missing_client_id_refuses_rather_than_skipping_audience(monkeypatch):
    """google-auth: "If None then the audience is not verified." Passing None
    through accepted a token minted for ANY Google OAuth client."""
    monkeypatch.delenv("OAUTH_CLIENT_ID", raising=False)
    with pytest.raises(NotAuthenticated, match="OAUTH_CLIENT_ID is unset"):
        verify("any.token.value")


def test_missing_domain_allowlist_admits_nobody(monkeypatch):
    """An empty allowlist means nobody, not everybody. The old form was
    `if domains and ...`, so unset meant every verified Google account got in
    on the default role."""
    monkeypatch.setenv("OAUTH_CLIENT_ID", "client.apps.googleusercontent.com")
    monkeypatch.delenv("ALLOWED_DOMAINS", raising=False)
    monkeypatch.setattr(
        "google.oauth2.id_token.verify_oauth2_token",
        lambda *a, **k: {"email": "attacker@gmail.com", "email_verified": True})
    with pytest.raises(NotAuthenticated, match="ALLOWED_DOMAINS is unset"):
        verify("token")


def test_a_permitted_domain_still_authenticates(monkeypatch):
    """The fix must not lock out legitimate users."""
    monkeypatch.setenv("OAUTH_CLIENT_ID", "client.apps.googleusercontent.com")
    monkeypatch.setenv("ALLOWED_DOMAINS", "district.org")
    monkeypatch.delenv("ROLE_ASSIGNMENTS", raising=False)
    monkeypatch.setattr(
        "google.oauth2.id_token.verify_oauth2_token",
        lambda *a, **k: {"email": "coord@district.org", "email_verified": True})
    assert verify("token").email == "coord@district.org"


def test_an_outside_domain_is_still_refused(monkeypatch):
    monkeypatch.setenv("OAUTH_CLIENT_ID", "client.apps.googleusercontent.com")
    monkeypatch.setenv("ALLOWED_DOMAINS", "district.org")
    monkeypatch.setattr(
        "google.oauth2.id_token.verify_oauth2_token",
        lambda *a, **k: {"email": "attacker@gmail.com", "email_verified": True})
    with pytest.raises(NotAuthenticated, match="outside the permitted domains"):
        verify("token")


# --- finding 2: origin comparison must be exact ------------------------------

HOST = "dash.run.app"


def test_a_lookalike_host_is_refused(monkeypatch):
    """https://dash.run.app.evil.example genuinely begins with
    https://dash.run.app, which is why startswith() was the wrong comparison."""
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    req = FakeRequest(host=HOST, origin=f"https://{HOST}.evil.example")
    with pytest.raises(HTTPException) as e:
        require_same_origin(req)
    assert e.value.status_code == 403


def test_a_referer_with_a_path_on_a_lookalike_host_is_refused(monkeypatch):
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    req = FakeRequest(host=HOST, referer=f"https://{HOST}.evil.example/page")
    with pytest.raises(HTTPException):
        require_same_origin(req)


def test_the_real_origin_still_passes(monkeypatch):
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    require_same_origin(FakeRequest(host=HOST, origin=f"https://{HOST}"))


def test_a_referer_carrying_a_path_still_passes(monkeypatch):
    """Referer includes a path; it must be reduced to an origin before
    comparison or every legitimate form post breaks."""
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    require_same_origin(FakeRequest(host=HOST, referer=f"https://{HOST}/case/stu_1"))


def test_a_configured_allowed_origin_is_normalised(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://portal.district.org/somewhere")
    require_same_origin(FakeRequest(host=HOST, origin="https://portal.district.org"))


def test_non_browser_clients_are_unaffected():
    """No Origin and no Referer cannot be a CSRF; those clients are not browsers."""
    require_same_origin(FakeRequest(host=HOST))
