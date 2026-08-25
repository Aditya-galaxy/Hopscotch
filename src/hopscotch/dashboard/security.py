"""Transport and request-level protections for the coordinator surface.

Three things, each fixing something the audit actually found:

  headers      no CSP, HSTS, frame or sniff protection existed at all
  read_only    with auth disabled, anyone could POST an approval or a
               correction. A public demo must not accept writes from strangers.
  same_origin  a cheap CSRF guard. Bearer-token auth is not cookie-replayable,
               but the read-only demo and any future cookie session would be.
"""
from __future__ import annotations

import os
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware

# No inline script anywhere in this app, so the policy can be strict. Styles are
# a single inline block, hence 'unsafe-inline' for style-src only.
CSP = ("default-src 'self'; script-src 'none'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data:; media-src 'self'; form-action 'self'; "
       "frame-ancestors 'none'; base-uri 'none'; object-src 'none'")

HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Cache-Control": "no-store",   # student data must not sit in a proxy cache
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
}


class SecurityHeaders(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        resp = await call_next(request)
        for k, v in HEADERS.items():
            resp.headers.setdefault(k, v)
        return resp


def read_only() -> bool:
    """True when writes must be refused.

    Tied to authentication: if we cannot say WHO is acting, we must not let them
    act. That makes the public demo safe by construction rather than by
    remembering to lock each endpoint.

    DEMO_ALLOW_WRITES is a deliberate, narrow escape hatch for recording a demo
    on a local machine, where the operator IS the only caller. It only has any
    effect when authentication is already off, it is never set on the deployed
    service, and the page carries a louder banner while it is on -- so it cannot
    be enabled quietly. Anything reachable from the internet should use
    REQUIRE_AUTH=true instead.
    """
    from ..auth import auth_required

    if auth_required():
        return False
    return os.environ.get("DEMO_ALLOW_WRITES", "").lower() != "true"


def demo_writes_enabled() -> bool:
    from ..auth import auth_required
    return not auth_required() and not read_only()


def require_writable() -> None:
    if read_only():
        raise HTTPException(
            403, "This deployment is read-only. Writes require authentication "
                 "(REQUIRE_AUTH=true); an unauthenticated caller cannot be held "
                 "accountable for approving a notice to a family.")


def require_same_origin(request: Request) -> None:
    """Reject cross-site form posts. Absent Origin and Referer is allowed only
    for non-browser clients, which cannot be CSRF'd."""
    origin = request.headers.get("origin") or ""
    referer = request.headers.get("referer") or ""
    if not origin and not referer:
        return
    host = request.headers.get("host", "")
    allowed = os.environ.get("ALLOWED_ORIGINS", "").split(",")
    candidates = {f"https://{host}", f"http://{host}"} | {
        f"{urlsplit(a.strip()).scheme}://{urlsplit(a.strip()).netloc}"
        for a in allowed if a.strip()}
    # Compare the parsed ORIGIN, never a string prefix. startswith() would
    # accept https://<host>.evil.example, because that genuinely does begin
    # with https://<host> -- and the Referer fallback made it worse, since a
    # full referring URL carries a path after the host.
    parts = urlsplit(origin or referer)
    src_origin = f"{parts.scheme}://{parts.netloc}"
    if src_origin not in candidates:
        raise HTTPException(403, "cross-origin request refused")
