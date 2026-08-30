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
    PARENT = "parent"                 # one child's status, and only theirs


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
    # A parent sees their own child's status and the letters actually sent to
    # them. `case.read_own` carries a record-level restriction as well as a
    # field-level one -- see Principal.student_ref.
    Role.PARENT: frozenset({"case.read_own"}),
}


class NotAuthenticated(PermissionError):
    """No valid identity. Distinct from 'identified but not permitted'."""


class NotPermitted(PermissionError):
    """Known person, wrong role."""


# Roles limited to a single record rather than to a set of fields. Everything
# else is bounded by the scope table; these are bounded by a row as well.
RECORD_SCOPED_ROLES = frozenset({Role.PARENT})


class NotThisRecord(PermissionError):
    """Right identity, wrong record.

    Distinct from NotPermitted, which is about a KIND of data. This is about a
    row: a parent holds a perfectly valid scope for evaluation dates and still
    may not read another family's child. Field-level projection cannot express
    that -- it decides what a caller sees, never whose.
    """


@dataclass(frozen=True)
class Principal:
    email: str
    role: Role
    # Set only for identities bound to a single record. None means "not record
    # scoped", which is every staff role: they are limited by FIELD, not by row.
    student_ref: str | None = None

    @property
    def scopes(self) -> frozenset[str]:
        return ROLE_SCOPES[self.role]

    def require_record(self, student_ref: str) -> None:
        """Refuse a record this identity is not bound to.

        Raises rather than filtering, and callers answer 404 rather than 403:
        telling a stranger that a student exists is itself a disclosure.

        Fails CLOSED for record-scoped roles. Returning early on a missing
        binding is correct for staff, who are limited by field rather than by
        row -- but for a parent it inverts the rule: an unbound parent would be
        admitted to every child instead of none. That is precisely the bug this
        method exists to prevent, and it is the shape a missing environment
        variable takes in production.
        """
        if self.role not in RECORD_SCOPED_ROLES:
            return
        if self.student_ref is None:
            raise NotThisRecord(
                f"{self.email} holds the record-scoped role "
                f"'{self.role.value}' with no student binding; refusing every "
                f"record rather than admitting all of them")
        if student_ref != self.student_ref:
            raise NotThisRecord(
                f"{self.email} is bound to {self.student_ref} and may not read "
                f"{student_ref}")

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


def _student_for(email: str) -> str | None:
    """Which child this address belongs to, for parent identities.

    PARENT_ASSIGNMENTS='a@x.com:stu_0042,b@y.com:stu_0043'

    A parent whose address is not listed gets no binding, and a parent with no
    binding is refused outright rather than shown everything -- an unlisted
    parent is a configuration error, and the safe reading of a configuration
    error is "no access".
    """
    for pair in os.environ.get("PARENT_ASSIGNMENTS", "").split(","):
        if ":" in pair:
            who, _, ref = pair.partition(":")
            if who.strip().lower() == email.lower():
                return ref.strip()
    return None


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

        role = _role_for(email)
        bound = _student_for(email) if role is Role.PARENT else None
        if role is Role.PARENT and bound is None:
            raise NotAuthenticated(
                f"{email} is assigned the parent role but bound to no student; "
                "refusing rather than admitting them to every record")
        p = Principal(email=email, role=role, student_ref=bound)
        s.set_attribute("role", p.role.value)
        return p


def auth_required() -> bool:
    """Off only when explicitly disabled, and the dashboard says so on screen.

    Default-on: a misconfiguration should lock people out, not expose records.
    """
    return os.environ.get("REQUIRE_AUTH", "true").lower() != "false"
