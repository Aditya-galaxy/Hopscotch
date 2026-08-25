"""Who is using this, and what may they do.

Agents have identities and scopes. Humans need the same, and for the same
reason: a family liaison should not open a clinical evaluation because they
clicked the wrong link.

Verification is a real Google ID token check -- signature, issuer, audience and
expiry, via google.oauth2. No hand-rolled JWT parsing, and no "trust the header"
shortcut, because that shortcut is how these systems actually get breached.

Roles map onto the SAME scope vocabulary the registry already enforces for
agents, so there is one answer to "may this principal read clinical data",
whether the principal is a person or a process.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum

from .telemetry import span


class Role(str, Enum):
    COORDINATOR = "coordinator"       # the whole caseload, approves notices
    PSYCHOLOGIST = "psychologist"     # clinical detail
    LIAISON = "liaison"               # redacted view, family contact
    BUSINESS = "business"             # claim readiness, no clinical
    ADMIN = "admin"


# Human roles reuse the agent scope vocabulary deliberately.
ROLE_SCOPES: dict[Role, frozenset[str]] = {
    Role.COORDINATOR: frozenset({
        "case.read", "case.write", "notice.approve", "claim.read",
        "claim.export"}),
    Role.PSYCHOLOGIST: frozenset({"case.read_full", "draft.write"}),
    Role.LIAISON: frozenset({"case.read_redacted", "notify.send"}),
    # The business office is the one that actually files. It gets export and
    # nothing that touches a case.
    Role.BUSINESS: frozenset({"claim.read", "claim.export"}),
    Role.ADMIN: frozenset({
        "case.read", "case.write", "notice.approve", "claim.read",
        "claim.export", "registry.publish"}),
}


class NotAuthenticated(PermissionError):
    """No valid identity. Distinct from 'identified but not permitted'."""


class NotPermitted(PermissionError):
    """Known person, wrong role."""


@dataclass(frozen=True)
class Principal:
    email: str
    role: Role

    @property
    def scopes(self) -> frozenset[str]:
        return ROLE_SCOPES[self.role]

    def require(self, scope: str) -> None:
        if scope not in self.scopes:
            raise NotPermitted(
                f"{self.email} ({self.role.value}) may not '{scope}'. "
                f"Permitted: {', '.join(sorted(self.scopes))}")


def _allowed_domains() -> set[str]:
    raw = os.environ.get("ALLOWED_DOMAINS", "")
    return {d.strip().lower() for d in raw.split(",") if d.strip()}


def _role_for(email: str) -> Role:
    """Explicit per-email assignment wins; otherwise the domain default.

    ROLE_ASSIGNMENTS='a@d.org:coordinator,b@d.org:psychologist'
    DEFAULT_ROLE='liaison'   -- least privilege, not most
    """
    for pair in os.environ.get("ROLE_ASSIGNMENTS", "").split(","):
        if ":" in pair:
            who, _, role = pair.partition(":")
            if who.strip().lower() == email.lower():
                return Role(role.strip())
    return Role(os.environ.get("DEFAULT_ROLE", Role.LIAISON.value))


def verify(id_token_str: str) -> Principal:
    """Verify a Google ID token and resolve the caller. Raises, never guesses."""
    from google.auth.transport import requests as ga_requests
    from google.oauth2 import id_token as google_id_token

    audience = os.environ.get("OAUTH_CLIENT_ID")
    if not audience:
        # google-auth documents this precisely: "If None then the audience is
        # not verified." Passing it through would accept a token minted for ANY
        # Google OAuth client -- signature and issuer still check out, so the
        # bypass looks like a successful login. Refuse instead.
        raise NotAuthenticated(
            "OAUTH_CLIENT_ID is unset; refusing to verify a token without "
            "checking who it was issued for")

    with span("auth.verify") as s:
        try:
            claims = google_id_token.verify_oauth2_token(
                id_token_str, ga_requests.Request(), audience)
        except Exception as e:
            s.set_attribute("ok", False)
            raise NotAuthenticated(f"token rejected: {type(e).__name__}") from e

        email = (claims.get("email") or "").lower()
        if not email or not claims.get("email_verified"):
            raise NotAuthenticated("token carries no verified email")

        # An empty allowlist means "nobody is allowed", not "everybody is".
        # The previous form was `if domains and ...`, so an unset ALLOWED_DOMAINS
        # skipped the check entirely and any verified Google account was let in
        # on the default role.
        domains = _allowed_domains()
        if not domains:
            raise NotAuthenticated(
                "ALLOWED_DOMAINS is unset; refusing to admit every Google "
                "account. Set it to the district's mail domain(s).")
        if email.rsplit("@", 1)[-1] not in domains:
            s.set_attribute("ok", False)
            raise NotAuthenticated(f"{email} is outside the permitted domains")

        p = Principal(email=email, role=_role_for(email))
        s.set_attribute("role", p.role.value)
        return p


def auth_required() -> bool:
    """Off only when explicitly disabled, and the dashboard says so on screen.

    Default-on: a misconfiguration should lock people out, not expose records.
    """
    return os.environ.get("REQUIRE_AUTH", "true").lower() != "false"
