"""Coordinator dashboard.

Scanned, not read. Someone opens this between meetings and needs to know in five
seconds what is on fire.

Every section is gated on the caller's scopes, and the caseload is projected
through the SAME field classification that governs agents -- so a liaison
signing in sees exactly what family-agent sees, and the browser cannot become
the way around the boundary. Sections you lack scope for are absent and labelled
as absent, rather than silently empty, because a blank panel reads as "nothing
happening" and that is a different and worse lie.

Writes require authentication. If we cannot say who acted, we do not let them
act.
"""
from __future__ import annotations

import html
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import date

from fastapi import Depends, FastAPI, Form, Header, HTTPException, Request
from fastapi.responses import (FileResponse, HTMLResponse,
                               RedirectResponse, Response)

from ..config import PROJECT_NAME
from ..auth import NotThisRecord, auth_required
from .security import (
    demo_writes_enabled,
    writable,
    SecurityHeaders, read_only, require_same_origin, require_writable,
)

# openapi_url=None as well as the doc UIs. Disabling /docs and /redoc while
# leaving /openapi.json served still hands an attacker the whole route table,
# every parameter name and every response shape.
app = FastAPI(title=f"{PROJECT_NAME} — coordinator",
              docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(SecurityHeaders)

e = html.escape

log = logging.getLogger("hopscotch.dashboard")

_SITE = Path(__file__).resolve().parents[3] / "site"

FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
    'family=Newsreader:opsz,wght@6..72,200;6..72,300;6..72,400&'
    'family=IBM+Plex+Mono:wght@400;500;600&'
    'family=IBM+Plex+Sans:wght@300;400;500;600&display=swap">'
)

CSS = """
/* The application wears the same identity as the landing page -- one black and
   white world, Newsreader for display, Plex for everything operational -- but
   it is NOT the same treatment. A landing page is read top to bottom and can
   afford air; a caseload is scanned and operated, so the type scale is small,
   the rows are dense, and the space is spent on separation rather than drama.
   Committed to a single dark world like the front page, with every colour
   painted explicitly so the page never borrows the host's ground. */
:root{
  --ink:#000000;
  --surface:#0B0B0B;
  --sunk:#141414;
  --raised:#181818;
  --paper:#FFFFFF;
  --soft:#B4B4B2;
  --muted:#828280;
  --rule:#1E1E1E;
  --rule-strong:#333331;
  --serif:"Newsreader",ui-serif,Georgia,"Times New Roman",serif;
  --sans:"IBM Plex Sans",ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0;background:var(--ink);color:var(--paper);
  font-family:var(--sans);font-weight:300;font-size:15px;line-height:1.55;
  -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;
}
/* The ruled column: the landing page's rails, carried across. */
.wrap{max-width:1220px;margin:0 auto;padding:0 clamp(18px,3vw,40px) 88px;
  border-left:1px solid var(--rule);border-right:1px solid var(--rule);
  min-height:100vh}
@media(max-width:760px){.wrap{border-left:0;border-right:0}}
a{color:var(--paper);text-underline-offset:2px}
a:hover{text-decoration-thickness:2px}
:focus-visible{outline:2px solid var(--paper);outline-offset:2px}

/* ---- masthead ----------------------------------------------------------- */
header.top{display:flex;flex-wrap:wrap;gap:14px;align-items:center;
  padding:20px 0 16px;margin-bottom:22px;border-bottom:1px solid var(--rule)}
.brandwrap{display:flex;align-items:center;gap:11px;min-width:0}
.mark{width:28px;height:28px;border-radius:7px;background:var(--paper);
  color:var(--ink);display:grid;place-items:center;flex:none;
  font-family:var(--serif);font-weight:400;font-size:.95rem}
.brand h1{font-family:var(--serif);font-size:1.18rem;margin:0;font-weight:300;
  letter-spacing:-.01em;line-height:1.15}
.brand span{display:block;font-family:var(--mono);font-size:.68rem;
  color:var(--muted);letter-spacing:.05em;margin-top:3px}
h1{font-family:var(--serif);font-weight:300;margin:0}
.whoami{margin-left:auto;display:flex;align-items:center;gap:10px}
.idchip{display:flex;flex-direction:column;align-items:flex-end;line-height:1.3}
.idchip b{font-size:.8rem;font-weight:500}
.idchip span{font-family:var(--mono);font-size:.67rem;color:var(--muted);
  letter-spacing:.04em}
.avatar{width:30px;height:30px;border-radius:50%;flex:none;
  background:transparent;color:var(--paper);border:1px solid var(--rule-strong);
  display:grid;place-items:center;font-family:var(--mono);font-size:.75rem}

/* ---- section headings: the landing page's eyebrow, as a rule ------------- */
h2{font-family:var(--mono);font-size:.68rem;font-weight:600;
  text-transform:uppercase;letter-spacing:.14em;color:var(--muted);
  margin:34px 0 12px;display:flex;align-items:center;gap:12px}
h2::after{content:"";flex:1;height:1px;background:var(--rule)}
h3{font-family:var(--serif);font-size:1.05rem;font-weight:300;margin:22px 0 8px;
  letter-spacing:-.005em}
.sub{color:var(--muted);font-size:.85rem;margin:0 0 14px;max-width:78ch}

/* ---- tiles: severity by weight and rail, never by hue ------------------- */
.tiles{display:grid;gap:1px;background:var(--rule);border:1px solid var(--rule);
  grid-template-columns:repeat(auto-fit,minmax(160px,1fr))}
.tile{background:var(--ink);padding:16px 18px;position:relative}
.tile .n{font-family:var(--serif);font-size:2.05rem;font-weight:300;
  line-height:1.05;letter-spacing:-.02em;font-variant-numeric:tabular-nums;
  color:var(--soft)}
.tile .l{font-family:var(--mono);font-size:.65rem;text-transform:uppercase;
  letter-spacing:.11em;color:var(--muted);margin-top:6px}
/* Overdue is the one thing that must read instantly. With no colour to spend,
   it takes full white, extra weight and a solid rail; a warning takes white
   with a hairline rail; everything else stays dimmed. */
.tile.hot{background:var(--surface)}
.tile.hot::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;
  background:var(--paper)}
.tile.hot .n{color:var(--paper);font-weight:400}
.tile.warn::before{content:"";position:absolute;left:0;top:0;bottom:0;width:1px;
  background:var(--rule-strong)}
.tile.warn .n{color:var(--paper)}

/* ---- tables: dense, ruled, monospaced where it is data ------------------ */
.scroll{overflow-x:auto;border:1px solid var(--rule);background:var(--surface)}
table{width:100%;min-width:680px;border-collapse:collapse;font-size:.845rem}
th{text-align:left;font-family:var(--mono);font-size:.63rem;text-transform:uppercase;
  letter-spacing:.11em;color:var(--muted);padding:10px 13px;font-weight:500;
  border-bottom:1px solid var(--rule);background:var(--sunk);white-space:nowrap}
td{padding:9px 13px;border-bottom:1px solid var(--rule);vertical-align:middle;
  color:var(--soft)}
tr:last-child td{border-bottom:0}
tbody tr:hover{background:var(--sunk)}
tbody tr:hover td{color:var(--paper)}
.mono{font-family:var(--mono);font-variant-numeric:tabular-nums;font-size:.93em;
  color:var(--paper)}

/* ---- pills: fill = urgent, outline = watch, plain = fine ---------------- */
.pill{display:inline-block;padding:2px 9px;border-radius:3px;font-family:var(--mono);
  font-size:.67rem;font-weight:500;white-space:nowrap;letter-spacing:.04em;
  border:1px solid transparent;text-transform:uppercase}
.pill.hot{background:var(--paper);color:var(--ink);font-weight:600}
.pill.warn{border-color:var(--rule-strong);color:var(--paper)}
.pill.ok{color:var(--muted)}

/* ---- the daily brief ---------------------------------------------------- */
.brief{background:var(--surface);border:1px solid var(--rule);
  border-left:2px solid var(--paper);padding:18px 20px}
.brief .hl{font-family:var(--serif);font-size:1.3rem;font-weight:300;
  line-height:1.35;letter-spacing:-.01em;margin-bottom:14px;max-width:68ch}
.brief .grp{margin-top:13px}
.brief .grp h4{margin:0 0 5px;font-family:var(--mono);font-size:.63rem;
  text-transform:uppercase;letter-spacing:.12em;color:var(--muted);font-weight:500}
.brief ul{margin:0;padding-left:16px}
.brief li{font-size:.845rem;color:var(--soft);margin-bottom:3px}
.brief li.more{color:var(--muted);font-style:italic}
.brief .by{margin-top:15px;padding-top:11px;border-top:1px solid var(--rule);
  font-family:var(--mono);font-size:.66rem;color:var(--muted);letter-spacing:.04em}

/* ---- notices ------------------------------------------------------------ */
.banner{border:1px solid var(--rule-strong);border-left:2px solid var(--paper);
  padding:11px 14px;font-size:.82rem;margin-bottom:16px;line-height:1.5;
  background:var(--surface);color:var(--soft)}
.banner b{color:var(--paper)}
.flash{border:1px solid var(--rule-strong);background:var(--surface);
  color:var(--paper);padding:11px 14px;font-size:.85rem;margin:0 0 16px}
.locked{background:var(--surface);border:1px dashed var(--rule-strong);
  padding:15px 17px;color:var(--muted);font-size:.84rem}
.locked code{font-family:var(--mono);background:var(--sunk);padding:1px 5px;
  color:var(--soft)}
.empty{color:var(--muted);font-size:.84rem;padding:20px;text-align:center}

/* ---- forms and buttons -------------------------------------------------- */
.drop{display:flex;flex-direction:column;gap:9px;max-width:840px;margin-bottom:10px}
.stack{display:flex;flex-direction:column;gap:9px;max-width:600px;margin-bottom:10px}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.drop textarea,.stack input,.stack textarea,.fix input{
  font:inherit;font-size:.85rem;padding:9px 11px;border:1px solid var(--rule-strong);
  background:var(--ink);color:var(--paper);width:100%;border-radius:2px}
.drop textarea{min-height:126px;resize:vertical;font-family:var(--mono);
  font-size:.78rem;line-height:1.6}
.drop textarea::placeholder{color:var(--muted)}
.drop textarea:focus,.stack input:focus,.stack textarea:focus{
  outline:1px solid var(--paper);outline-offset:-1px;border-color:var(--paper)}
.field{display:flex;flex-direction:column;gap:5px;flex:1;min-width:150px}
.field>span{font-family:var(--mono);font-size:.63rem;text-transform:uppercase;
  letter-spacing:.11em;color:var(--muted);font-weight:500}
.btn{font-family:var(--sans);font-size:.79rem;font-weight:500;padding:7px 14px;
  border-radius:999px;cursor:pointer;border:1px solid var(--paper);
  background:var(--paper);color:var(--ink);transition:opacity .14s ease}
.btn:hover{opacity:.84}
.btn.ghost{background:transparent;color:var(--paper);border-color:var(--rule-strong)}
.btn.ghost:hover{background:var(--raised);opacity:1;border-color:var(--muted)}
.btn:disabled{opacity:.35;cursor:not-allowed}
form.inline{display:inline}
.fix{display:flex;gap:5px;align-items:center;flex-wrap:wrap;margin-top:6px}
.fix input{font-size:.75rem;padding:4px 7px;max-width:126px;width:auto}
.fixwrap summary{cursor:pointer;font-family:var(--mono);font-size:.66rem;
  color:var(--muted);list-style:none;user-select:none;padding:3px 9px;
  border:1px solid var(--rule-strong);display:inline-block;white-space:nowrap;
  text-transform:uppercase;letter-spacing:.08em}
.fixwrap summary::-webkit-details-marker{display:none}
.fixwrap summary:hover{background:var(--raised);color:var(--paper)}
.fixwrap[open] summary{color:var(--paper);background:var(--raised)}
.hint{font-size:.78rem;color:var(--muted)}\n.nomedia{font-family:var(--mono);font-size:.66rem;color:var(--muted);letter-spacing:.04em;white-space:nowrap}
.actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.tickrow{margin-top:-2px}
.back{font-family:var(--mono);font-size:.7rem;letter-spacing:.08em;
  text-transform:uppercase;color:var(--muted);display:inline-block;
  margin:16px 0 2px;text-decoration:none}
.back:hover{color:var(--paper)}

/* ---- identity switcher -------------------------------------------------- */
.switcher{display:flex;align-items:center;gap:6px;flex-wrap:wrap;
  padding:14px 0 0}
.swlabel{font-family:var(--mono);font-size:.63rem;text-transform:uppercase;
  letter-spacing:.13em;color:var(--muted);margin-right:4px}
.swtab{font-size:.77rem;padding:5px 12px;border:1px solid var(--rule);
  color:var(--muted);background:transparent;text-decoration:none;
  white-space:nowrap;border-radius:999px}
.swtab:hover{border-color:var(--rule-strong);color:var(--paper)}
.swtab.on{background:var(--paper);border-color:var(--paper);color:var(--ink);
  font-weight:500}
.swnote{font-size:.74rem;color:var(--muted);flex-basis:100%;margin-top:6px}

/* ---- the family surface: the one place that keeps some air -------------- */
.tiles.fam{grid-template-columns:repeat(auto-fit,minmax(220px,1fr))}
.tiles.fam .tile{padding:20px 22px}
.tiles.fam .tile .n{font-size:2.3rem;color:var(--paper)}
.letter{background:var(--surface);border:1px solid var(--rule);
  border-left:2px solid var(--rule-strong);padding:18px 20px;margin-bottom:10px}
.letter h3{margin:0 0 4px;font-size:1rem}
.lettermeta{margin:0 0 12px;font-family:var(--mono);font-size:.66rem;
  color:var(--muted);letter-spacing:.04em}
.letterbody{margin:0 0 12px;white-space:pre-wrap;font-size:.9rem;line-height:1.7;
  color:var(--soft);max-width:68ch}
.rights{background:var(--surface);border:1px solid var(--rule);
  border-left:2px solid var(--paper);padding:16px 20px}
.rights p{margin:0 0 10px;font-size:.87rem;color:var(--soft);max-width:72ch}
.rights p:last-child{margin-bottom:0}

/* ---- media -------------------------------------------------------------- */
.media{display:grid;gap:1px;background:var(--rule);border:1px solid var(--rule);
  grid-template-columns:repeat(auto-fit,minmax(280px,1fr))}
.card{background:var(--ink);padding:16px 18px}
.card h3{margin:0 0 4px;font-size:.95rem}
.card p{margin:0 0 11px;color:var(--muted);font-size:.8rem}
video,audio{width:100%;border-radius:2px;filter:grayscale(1)}
footer{margin-top:44px;padding-top:16px;border-top:1px solid var(--rule);
  font-family:var(--mono);color:var(--muted);font-size:.68rem;letter-spacing:.05em}
@media(max-width:640px){
  .wrap{padding-bottom:56px}
  .whoami{margin-left:0;width:100%;justify-content:flex-start}
  .tile .n{font-size:1.75rem}
}
"""


# --- identity ---------------------------------------------------------------

def _plain_page(title: str, body: str, status_note: str = "") -> str:
    """A styled page for the states that are not the happy path.

    A bare unstyled error in an otherwise finished application reads as a seam,
    and this one is reachable by anyone poking at another family's record.
    """
    return f"""<!doctype html><html lang=en><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<meta name=robots content="noindex,nofollow">
<title>{e(title)} — {PROJECT_NAME}</title>{FONTS}<style>{CSS}</style>
<body><div class=wrap>
<header class=top>
  <div class=brandwrap>
    <div class=mark>H</div>
    <div class=brand><h1>{e(title)}</h1><span>{PROJECT_NAME}</span></div>
  </div>
</header>
<p class=sub>{e(body)}</p>
{f'<p class=sub>{e(status_note)}</p>' if status_note else ''}
<p><a class=back href="/">&larr; back to the start</a></p>
<footer>{PROJECT_NAME} &middot; all data synthetic</footer>
</div></body></html>"""


@app.exception_handler(NotThisRecord)
def _not_this_record(request: Request, exc: NotThisRecord):
    """404, deliberately, not 403.

    403 confirms the record exists and merely belongs to someone else, which
    tells a stranger that a given student is enrolled and under evaluation.
    404 tells them nothing. The refusal is still audited server-side.
    """
    log.warning("record-scope refusal: %s", exc)
    return HTMLResponse(_plain_page(
        "No such case",
        "There is no case here for you to read. If you believe there should be, "
        "the district office can tell you."), status_code=404)


DEMO_IDENTITIES: dict[str, tuple[str, str]] = {
    "coordinator": ("coordinator@district.org", "SPED coordinator"),
    "psychologist": ("psych@district.org", "School psychologist"),
    "liaison": ("liaison@district.org", "Family liaison"),
    "business": ("business@district.org", "Business office"),
    "admin": ("admin@district.org", "District administrator"),
    "parent": ("parent@example.com", "Parent"),
}


def _demo_principal(request: Request):
    """The identity being previewed. Only ever called with auth off."""
    from ..auth import Principal, Role

    want = (request.cookies.get("demo_role") or "coordinator").lower()
    if want not in DEMO_IDENTITIES:
        want = "coordinator"
    email, _label = DEMO_IDENTITIES[want]
    bound = request.cookies.get("demo_student") if want == "parent" else None
    if want == "parent" and not bound:
        # A parent must always be bound to exactly one child. Without this the
        # preview would hold a record-scoped role with no record, which now
        # refuses everything -- correct, but it would make the demo look broken
        # rather than making the boundary visible.
        bound = _demo_family_ref()
    return Principal(email=email, role=Role(want), student_ref=bound)


def principal(request: Request, authorization: str = Header(default="")):
    """Resolve the caller.

    Auth is ON unless REQUIRE_AUTH=false is set explicitly, because a missing
    setting must lock people out rather than expose records. When it is off the
    app is read-only and says so.

    With auth off ONLY, a `demo_role` cookie selects which identity to render
    as, so the same records can be shown from a coordinator's, a liaison's, a
    business officer's and a parent's side without five sign-ins. It is read
    only on this branch: once auth is on, the cookie is never consulted and the
    identity comes from a verified Google token, full stop.
    """
    from ..auth import NotAuthenticated, Principal, Role, auth_required, verify

    if not auth_required():
        return _demo_principal(request)
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(401, "sign in required")
    try:
        return verify(token)
    except NotAuthenticated as exc:
        raise HTTPException(401, str(exc)) from exc


def _needs(who, scope: str) -> None:
    from ..auth import NotPermitted
    try:
        who.require(scope)
    except NotPermitted as exc:
        raise HTTPException(403, str(exc)) from exc


# --- write endpoints --------------------------------------------------------

@app.post("/outbox/{item_id}/approve")
def approve_notice(item_id: str, request: Request, who=Depends(principal), _w=Depends(writable)):
    """A named human takes responsibility for contacting a family."""
    _needs(who, "notice.approve")
    from ..delivery import approve
    approve(item_id, approved_by=who.email)
    return RedirectResponse("/app", status_code=303)


@app.post("/outbox/{item_id}/reject")
def reject_notice(item_id: str, request: Request, who=Depends(principal), _w=Depends(writable)):
    _needs(who, "notice.approve")
    from ..delivery import reject
    reject(item_id, rejected_by=who.email)
    return RedirectResponse("/app", status_code=303)


@app.post("/intake")
def drop_document(request: Request, text: str = Form(...),
                  source: str = Form("upload"), who=Depends(principal), _w=Depends(writable)):
    """Accept a consent document. Extraction happens on the fleet, not here.

    This surface has no model access by design, so it records the document and
    the tick screens and reads it. A compromised dashboard cannot call Vertex.
    """
    _needs(who, "case.write")
    from .. import store

    if len(text.strip()) < 40:
        return RedirectResponse("/app?msg=That+does+not+look+like+a+consent+form.",
                                status_code=303)
    store.queue_document(text=text.strip(), source=(source or "upload")[:60],
                         dropped_by=who.email)
    return RedirectResponse(
        "/app?msg=Queued.+The+fleet+screens+and+reads+it+on+the+next+tick.",
        status_code=303)


@app.post("/case/{student_ref}/deliver")
def log_delivery(student_ref: str, request: Request, service: str = Form(...),
                 minutes: int = Form(...), units: int = Form(...),
                 note: str = Form(...), npi: str = Form(...),
                 provider_type: str = Form(...), who=Depends(principal), _w=Depends(writable)):
    """Log a delivered session. Claim readiness assesses it on the next tick."""
    from datetime import date as _date

    from google.cloud import firestore

    from ..config import settings
    from ..schemas import IEPService, ServiceDelivery
    from ..store import client_kwargs

    _needs(who, "case.write")

    today = _date.today()
    delivery = ServiceDelivery(
        student_ref=student_ref, goal_ref="G-3", service_date=today,
        minutes=minutes, units_billed=units, note=note.strip(),
        provider_npi=npi.strip(), provider_type=provider_type.strip(),
        provider_license_expires=_date(today.year + 1, 12, 31))
    iep = IEPService(goal_ref="G-3", service=service.strip(),
                     minutes_per_session=minutes, sessions_per_week=2,
                     provider_type=provider_type.strip(),
                     starts_on=_date(today.year, 1, 1),
                     ends_on=_date(today.year + 1, 6, 30))
    firestore.Client(**client_kwargs()).collection("deliveries").document(
        f"{student_ref}-{today}-G3-ui").set(
        delivery.model_dump(mode="json") | {
            "iep": iep.model_dump(mode="json"),
            "medicaid_eligible": True, "assessed": False})
    return RedirectResponse(
        f"/case/{student_ref}?msg=Session+logged.+Readiness+runs+on+the+next+tick.",
        status_code=303)


def _trigger_tick() -> tuple[bool, str]:
    """Ask the Cloud Run job to run. Shared by the dashboard and the walkthrough.

    Deliberately does NOT run a tick in-process. This service runs as an
    identity with no Vertex or Model Armor access, and executing the fleet here
    would force those permissions back onto it and undo the split. The job has
    them; this only asks it to start.
    """
    from ..config import settings

    project = settings.project_id
    region = os.environ.get("MODEL_ARMOR_LOCATION", "us-central1")
    job = os.environ.get("TICK_JOB_NAME", "agentx-tick")
    try:
        import google.auth
        from google.auth.transport.requests import AuthorizedSession

        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"])
        url = (f"https://run.googleapis.com/v2/projects/{project}/locations/"
               f"{region}/jobs/{job}:run")
        resp = AuthorizedSession(creds).post(url, timeout=30)
        if resp.status_code >= 300:
            return False, str(resp.status_code)
    except Exception as exc:
        return False, type(exc).__name__
    return True, ""


@app.post("/run/tick")
def run_tick_now(request: Request, who=Depends(principal), _w=Depends(writable)):
    """Run a tick now instead of waiting for the hour.

    Triggers the Cloud Run JOB rather than running in-process. This service runs
    as an identity with no Vertex or Model Armor access on purpose; executing
    the fleet here would force those permissions back onto it and undo the
    split. The job has them; this only asks it to start.
    """
    import os

    from ..config import settings

    _needs(who, "case.write")
    ok, detail = _trigger_tick()
    if not ok:
        return RedirectResponse(f"/app?msg=Could+not+start+the+tick:+{detail}",
                                status_code=303)
    return RedirectResponse(
        "/app?msg=Tick+started.+Reload+in+a+moment+to+see+what+it+did.",
        status_code=303)


@app.get("/claims/export.csv")
def export_claims(who=Depends(principal)):
    """The batch a billing vendor ingests. Export is not submission.

    No write guard: this is a GET, and it only ever affected the demo -- with
    authentication on, read_only() is false and the guard passed anyway. All it
    achieved was a dead button on the public deployment. The `claim.export`
    scope below is the actual control.
    """
    from fastapi.responses import Response

    from ..auth import NotPermitted
    from ..claim import current_batch, to_csv

    try:
        who.require("claim.export")
    except NotPermitted as exc:
        raise HTTPException(403, str(exc)) from exc

    body = to_csv(current_batch())
    return Response(
        content=body, media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="claims.csv"',
                 "Cache-Control": "no-store"})


@app.post("/case/{student_ref}/correct")
def correct_case(student_ref: str, request: Request, field: str = Form(...),
                 value: str = Form(...), reason: str = Form(...),
                 who=Depends(principal), _w=Depends(writable)):
    """Overriding the fleet. A reason is required, always."""
    _needs(who, "case.write")
    from datetime import date as _date

    from .. import store
    from ..schemas import Correction

    if not reason.strip():
        raise HTTPException(400, "a correction needs a reason")
    case = store.get_case(student_ref)
    was = (case.deadline.due_on.isoformat()
           if case and case.deadline and field == "due_on" else "")
    try:
        store.apply_correction(student_ref, Correction(
            field=field, value=_date.fromisoformat(value),
            reason=reason.strip(), by=who.email, computed_was=was))
    except (KeyError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return RedirectResponse("/app", status_code=303)


# --- media, authorized ------------------------------------------------------

@app.get("/outbox/{item_id}/audio")
def outbox_audio(item_id: str, who=Depends(principal)):
    """Audio is reached through the outbox item it belongs to, never by filename.

    The previous route served any file in the media directory to anyone who knew
    its name -- no authentication, no authorization. Names were content hashes,
    which is obscurity, not access control.

    No `writable` dependency, because this is a GET. It picked one up when the
    write guard moved onto a dependency and the edit matched every handler
    ending `who=Depends(principal))`, which silently made the spoken notices
    403 on the read-only demo -- the one deployment where anyone listens to
    them. Reading is gated by scope below; writing is what needs the guard.
    """
    from pathlib import Path

    from .. import store
    from ..media import MEDIA_DIR

    for scope in ("case.read_own", "case.read_redacted", "case.read"):
        if scope in who.scopes:
            break
    else:
        scope = "case.read"
    _needs(who, scope)
    item = store.get_outbound(item_id)
    if item is None or not item.audio_path:
        raise HTTPException(404, "no audio for this notice")
    # A parent may hear the letter written to THEM and no one else. Field-level
    # scope cannot express that; the binding is on the record.
    who.require_record(item.student_ref)

    ref = item.audio_path
    if ref.startswith("gs://"):
        # Persisted media. The bucket prefix is fixed here rather than taken
        # from the record, so a tampered audio_path cannot point the dashboard
        # at an arbitrary object.
        from ..media import is_servable, media_bytes

        if not is_servable(ref):
            raise HTTPException(404, "not found")
        try:
            return Response(content=media_bytes(ref), media_type="audio/mpeg")
        except Exception:
            raise HTTPException(404, "not found") from None

    # Local path: still confined to the media directory, because a stored path
    # is data and data can be wrong.
    p = Path(ref).resolve()
    root = MEDIA_DIR.resolve()
    if root != p.parent and root not in p.parents:
        raise HTTPException(404, "not found")
    if not p.is_file():
        raise HTTPException(404, "not found")
    return FileResponse(p, media_type="audio/mpeg")


@app.get("/explainer")
def explainer(who=Depends(principal)):
    """District-wide, identical for every family, so it carries no case data."""
    from ..media import MEDIA_DIR
    p = (MEDIA_DIR / "evaluation-timeline.mp4").resolve()
    if not p.is_file():
        raise HTTPException(404, "not generated")
    return FileResponse(p, media_type="video/mp4")


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


# --- rendering --------------------------------------------------------------

def _flash(msg: str) -> str:
    return f"<div class=flash>{e(msg[:200])}</div>" if msg else ""


def _pill(days: int | None) -> str:
    if days is None:
        return '<span class="pill warn">needs intake</span>'
    if days < 0:
        return f'<span class="pill hot">{abs(days)}d overdue</span>'
    if days <= 7:
        return f'<span class="pill hot">{days}d left</span>'
    if days <= 14:
        return f'<span class="pill warn">{days}d left</span>'
    return f'<span class="pill ok">{days}d left</span>'


def _locked(what: str, scope: str) -> str:
    return (f'<div class=locked>{e(what)} is not visible to your role. '
            f'It requires <code>{e(scope)}</code>.</div>')


def _cases_for(who) -> list[dict]:
    """Caseload, projected through the caller's own scopes.

    Uses the same field classification as the agent gateway, so a person and a
    process asking the same question get the same answer.
    """
    from .. import store
    from ..gateway import project_for_scopes

    rows = []
    for c in store.open_cases():
        view = project_for_scopes(who.scopes, c)
        d = c.deadline
        rows.append({
            "ref": view.get("student_ref", "—"),
            "school": view.get("school_code", "—"),
            "jur": view.get("jurisdiction", "—"),
            "due": d.due_on.isoformat() if d else "—",
            "days": d.days_remaining if d else None,
            "sent": ", ".join(f"T-{r}" for r in sorted(c.escalations_sent, reverse=True)) or "—",
            "corrected": bool(c.corrections),
            "clinical_visible": "referral_reason" in (view.get("consent") or {}),
        })
    return sorted(rows, key=lambda r: (r["days"] is None,
                                       r["days"] if r["days"] is not None else 0))


def _brief_block(who) -> str:
    if "case.read" not in who.scopes:
        return ""
    try:
        from ..brief import latest
        b = latest()
    except Exception:
        b = None
    if b is None:
        return ('<div class=locked>No brief yet — the supervisor writes one on '
                'the first tick of each day.</div>')

    def grp(title, items, cap=5):
        """Show the first few and count the rest.

        A brief that lists all fifteen overdue cases is not a brief -- it pushes
        everything else below the fold and reads as a dump. The full list is the
        caseload table directly underneath; this is the summary above it.
        """
        if not items:
            return ""
        shown, extra = items[:cap], len(items) - cap
        lis = "".join(f"<li>{e(i)}</li>" for i in shown)
        if extra > 0:
            lis += (f'<li class=more>and {extra} more &mdash; '
                    f'all of them in the caseload below</li>')
        return f"<div class=grp><h4>{e(title)}</h4><ul>{lis}</ul></div>"

    return (f"<div class=brief><div class=hl>{e(b.headline)}</div>"
            + grp("needs you today", b.needs_you_today)
            + grp("moved overnight", b.moved_overnight)
            + grp("watch", b.watch)
            + f"<div class=by>{e(b.generated_by)} · {e(b.brief_date)} · "
              f"{b.cases_open} open cases</div></div>")


def _caseload_block(who, cases) -> str:
    if "case.read" not in who.scopes and "case.read_redacted" not in who.scopes:
        return _locked("The caseload", "case.read")

    can_fix = "case.write" in who.scopes and not read_only()
    rows = ""
    for c in cases[:60]:
        fix = ""
        if can_fix:
            field = "consent_signed_on" if c["days"] is None else "due_on"
            label = "Set date" if c["days"] is None else "Override"
            fix = (f"<details class=fixwrap><summary>{label}</summary>"
                   f"<form method=post action='/case/{e(c['ref'])}/correct' class=fix>"
                   f"<input type=hidden name=field value='{field}'>"
                   f"<input type=date name=value required aria-label='new date'>"
                   f"<input type=text name=reason placeholder='reason' required "
                   f"aria-label='reason'>"
                   f"<button class='btn ghost'>Save</button></form></details>")
        flag = ('<span class="pill warn" title="human override">corrected</span> '
                if c["corrected"] else "")
        rows += (f"<tr><td class=mono><a href='/case/{e(c['ref'])}'>{e(c['ref'])}</a></td>"
                 f"<td class=mono>{e(c['school'])}</td>"
                 f"<td class=mono>{e(c['jur'])}</td>"
                 f"<td class=mono>{flag}{e(c['due'])}</td>"
                 f"<td>{_pill(c['days'])}</td><td class=mono>{e(c['sent'])}</td>"
                 f"<td>{fix}</td></tr>")
    rows = rows or "<tr><td colspan=7 class=empty>No open cases.</td></tr>"
    return (f"<div class=scroll><table><tr><th>student</th><th>school</th>"
            f"<th>jurisdiction</th><th>due</th><th>status</th>"
            f"<th>notices sent</th><th></th></tr>{rows}</table></div>")


def _audio_cell(item) -> str:
    """An audio player only when there are bytes behind it.

    Spoken notices are generated by the TICK, inside a Cloud Run job container,
    and written to that container's local disk. The container is then destroyed,
    so the recorded path survives in Firestore while the file does not -- and
    the dashboard, a different container entirely, rendered a player for twenty
    notices that could only ever 404. Offering a control that cannot work is a
    worse promise than offering none, so this checks first and says which.
    """
    from ..media import media_exists

    if not item.audio_path:
        return "<span class=nomedia>text only</span>"
    if not media_exists(item.audio_path):
        return ("<span class=nomedia title='generated inside the tick container "
                "before audio was persisted'>spoken copy not retained</span>")
    return (f"<audio controls preload=none "
            f"src='/outbox/{e(item.id)}/audio'></audio>")


def _outbox_block(who) -> str:
    if "case.read" not in who.scopes and "notice.approve" not in who.scopes:
        return ""
    try:
        from .. import store
        # Newest first: a coordinator works the most recent drafts, and
        # an unordered Firestore scan buried today's notices behind a
        # week of older ones.
        pending = sorted(store.pending_outbound(limit=40),
                         key=lambda o: o.created_at, reverse=True)[:12]
        summary = store.outbox_summary()
    except Exception:
        return ""
    if not summary.get("total"):
        return ""

    may_act = "notice.approve" in who.scopes and not read_only()
    rows = ""
    for i in pending:
        if may_act:
            act = (f"<form method=post action='/outbox/{e(i.id)}/approve' class=inline>"
                   f"<button class=btn>Approve &amp; send</button></form> "
                   f"<form method=post action='/outbox/{e(i.id)}/reject' class=inline>"
                   f"<button class='btn ghost'>Reject</button></form>")
        elif read_only():
            act = '<button class=btn disabled title="read-only deployment">Approve</button>'
        else:
            act = '<span class=empty>no approval scope</span>'
        audio = _audio_cell(i)
        # Jump straight to what this family will see once it is released. The
        # point of the demo is the two sides of one action, so the link belongs
        # on the row where the action happens.
        if not auth_required():
            act += (f" <a class='btn ghost' "
                    f"href='/demo/as/parent?student={e(i.student_ref)}'>"
                    f"View as this family</a>")
        rows += (f"<tr><td class=mono>{e(i.student_ref)}</td>"
                 f"<td>{e(i.notice_type.replace('_',' '))}</td>"
                 f"<td class=mono>{e(i.language)}</td>"
                 f"<td>{e(i.body[:80])}…{audio}</td><td>{act}</td></tr>")
    rows = rows or "<tr><td colspan=5 class=empty>Nothing awaiting approval.</td></tr>"
    counts = " · ".join(f"{v} {k.replace('_',' ')}"
                        for k, v in sorted(summary["by_status"].items()))
    return (f"<h2>Outbox — awaiting a human</h2>"
            f"<p class=sub>The fleet drafts and queues. Nothing reaches a family "
            f"until a named person approves it. <b>{e(counts)}</b></p>"
            f"<div class=scroll><table><tr><th>student</th><th>notice</th>"
            f"<th>language</th><th>preview</th><th></th></tr>{rows}</table></div>")


def _claims_block(who) -> str:
    if "claim.read" not in who.scopes:
        return f"<h2>Medicaid claim readiness</h2>{_locked('Claim readiness', 'claim.read')}"
    try:
        from .. import store
        c = store.readiness_summary()
    except Exception:
        return ""
    if not c.get("assessed"):
        return ""
    rows = "".join(
        f"<tr><td class=mono>{e(str(b.get('student_ref') or ''))}</td>"
        f"<td>{e(b.get('requirement',''))}</td>"
        f"<td>{e((b.get('detail') or '')[:88])}</td></tr>"
        for b in c["blocked"][:12]) or \
        "<tr><td colspan=3 class=empty>Nothing blocked.</td></tr>"
    return (f"<h2>Medicaid claim readiness</h2>"
            f"<p class=sub>Assessed, never submitted. Over-billing blocks; "
            f"under-billing is money left behind.</p>"
            f"<div class=tiles style='margin-bottom:12px'>"
            f"<div class=tile><div class=n>{c['assessed']}</div><div class=l>assessed</div></div>"
            f"<div class=tile><div class=n>{c['billable']}</div><div class=l>billable</div></div>"
            f"<div class='tile {'hot' if c['blocked'] else ''}'><div class=n>{len(c['blocked'])}</div>"
            f"<div class=l>would be denied</div></div>"
            f"<div class='tile {'warn' if c['underbilled_sessions'] else ''}'>"
            f"<div class=n>{c['underbilled_sessions']}</div><div class=l>under-billed</div></div>"
            f"</div><div class=scroll><table><tr><th>student</th><th>requirement</th>"
            f"<th>why</th></tr>{rows}</table></div>")


def _intake_block(who) -> str:
    """Drop a consent form. The fleet reads it; this page never calls a model."""
    if "case.write" not in who.scopes:
        return ""
    from .. import store

    rows = ""
    try:
        for r in store.inbox_recent(limit=6):
            status = r.get("status", "pending")
            cls = {"blocked": "hot", "failed": "hot", "needs_human": "warn",
                   "pending": "warn"}.get(status, "ok")
            ref = r.get("student_ref") or ""
            link = f"<a href='/case/{e(ref)}'>{e(ref)}</a>" if ref else "—"
            rows += (f"<tr><td class=mono>{e((r.get('at') or '')[:16])}</td>"
                     f"<td><span class='pill {cls}'>{e(status)}</span></td>"
                     f"<td class=mono>{link}</td>"
                     f"<td>{e((r.get('detail') or '')[:70])}</td></tr>")
    except Exception:
        pass
    rows = rows or "<tr><td colspan=4 class=empty>Nothing dropped yet.</td></tr>"

    form = ""
    if read_only():
        # Explain the missing form. A heading that says "paste it as it arrived"
        # above no textarea reads as broken rather than as a locked capability,
        # and this is the page a stranger sees first.
        form = ("<div class=locked>The drop box is hidden here because this "
                "public demo is read-only &mdash; an unauthenticated visitor "
                "cannot be held accountable for what they file. The rows below "
                "are real documents the fleet has already processed, including "
                "one Model Armor refused.</div>")
    if not read_only():
        form = (
            "<form method=post action='/intake' class=drop>"
            "<textarea name=text rows=6 required aria-label='consent document' "
            "placeholder='PARENTAL CONSENT FOR INITIAL EVALUATION&#10;"
            "Student ref: stu_0500&#10;School: EL-004&#10;"
            "Parent signature date: 09/14/2026&#10;"
            "Received by district: 09/16/2026&#10;"
            "Reason: Teacher referral, written expression.'></textarea>"
            "<span class=row><button class=btn>Queue for intake</button>"
            "</span></form>"
            "<form method=post action='/run/tick' class='row tickrow'>"
            "<button class='btn ghost'>Run a tick now</button>"
            "<span class=hint>or wait for the hour &mdash; it runs either way</span>"
            "</form>")

    return ("<h2>Drop a consent form</h2>"
            "<p class=sub>Paste it as it arrived — phone-photo OCR noise, "
            "forwarded email, all of it. Model Armor screens it before any model "
            "reads it, and this page has no model access: the fleet does the "
            "reading.</p>"
            f"{form}"
            f"<div class=scroll><table><tr><th>dropped</th><th>status</th>"
            f"<th>case</th><th>detail</th></tr>{rows}</table></div>")


def _claim_batch_block(who) -> str:
    """What is actually billable, coded, and what bundling withheld.

    Readiness says a session would survive an audit. This says what code goes
    on the claim -- and NCCI bundling is checked across the batch, because an
    SLP separately reporting 97530 alongside 92507 is a recoupment finding
    rather than a rejection at submission. It has to be caught before export.
    """
    if "claim.read" not in who.scopes:
        return ""
    try:
        from ..claim import current_batch
        batch = current_batch()
    except Exception:
        return ""
    if not batch.lines:
        return ""

    codes: dict[str, int] = {}
    for line in batch.submittable_lines:
        codes[line.procedure_code] = codes.get(line.procedure_code, 0) + 1
    summary = " · ".join(f"{c} ×{n}" for c, n in sorted(codes.items()))

    blocked = [l for l in batch.lines if not l.submittable]
    blocked_html = ""
    if blocked:
        rows = "".join(
            f"<tr><td class=mono>{e(l.student_ref)}</td>"
            f"<td class=mono>{e(l.procedure_code)}</td>"
            f"<td>{e(l.bundling_conflict[:100])}</td></tr>" for l in blocked)
        blocked_html = (f"<div class=scroll style='margin-top:10px'><table>"
                        f"<tr><th>student</th><th>code</th>"
                        f"<th>withheld because</th></tr>{rows}</table></div>")

    export = ("<form method=get action='/claims/export.csv' style='margin-top:12px'>"
              "<button class=btn>Export CSV for the billing vendor</button></form>"
              if "claim.export" in who.scopes else
              "<p class=muted>Export needs the business or coordinator role.</p>")

    return (f"<h2>Claim batch</h2>"
            f"<p class=sub>Coded and bundling-checked. Nothing is submitted from "
            f"here — the export is what a billing vendor ingests. <b>{e(summary)}</b></p>"
            f"<div class=tiles style='margin-bottom:12px'>"
            f"<div class=tile><div class=n>{len(batch.submittable_lines)}</div>"
            f"<div class=l>submittable lines</div></div>"
            f"<div class=tile><div class=n>{batch.total_units}</div>"
            f"<div class=l>billable units</div></div>"
            f"<div class='tile {'hot' if blocked else ''}'>"
            f"<div class=n>{len(blocked)}</div><div class=l>withheld, NCCI</div></div>"
            f"</div>{blocked_html}{export}")


def _audit_block(who) -> str:
    """The audit trail is the record of what agents did. Coordinators and admins
    only -- it names every student who moved."""
    if "case.write" not in who.scopes:
        return f"<h2>Audit trail</h2>{_locked('The audit trail', 'case.write')}"
    try:
        from google.cloud import firestore

        from ..config import settings
        from ..store import client_kwargs
        db = firestore.Client(**client_kwargs())
        rows_raw = [d.to_dict() for d in
                    db.collection(settings.audit_collection).limit(200).stream()]
        rows_raw.sort(key=lambda r: r.get("at", ""), reverse=True)
    except Exception:
        return ""
    rows = "".join(
        f"<tr><td class=mono>{e((r.get('at') or '')[:19])}</td><td>{e(r.get('event',''))}</td>"
        f"<td class=mono>{e(str(r.get('student_ref') or r.get('agent') or '—'))}</td>"
        f"<td class=mono>{e(str(r.get('rung') or r.get('scope') or r.get('field') or ''))}</td></tr>"
        for r in rows_raw[:25]) or "<tr><td colspan=4 class=empty>No audit rows.</td></tr>"
    return (f"<h2>Audit trail</h2><p class=sub>Append-only. Every row was written "
            f"by an agent, and none can be overwritten.</p>"
            f"<div class=scroll><table><tr><th>when</th><th>event</th>"
            f"<th>subject</th><th>detail</th></tr>{rows}</table></div>")


def _banner() -> str:
    if demo_writes_enabled():
        return ('<div class=banner><b>Local demo — writes enabled without '
                'authentication.</b> DEMO_ALLOW_WRITES is set, so anyone who can '
                'reach this can approve notices and correct deadlines. Correct '
                'for a laptop during a recording; never for anything reachable '
                'from the internet, which sets <b>REQUIRE_AUTH=true</b>.</div>')
    if not read_only():
        return ""
    return ('<div class=banner><b>Read-only public demo.</b> Authentication is '
            'disabled, so writes are refused and every record here is synthetic. '
            'A real deployment sets <b>REQUIRE_AUTH=true</b>, which is the '
            'default in code.</div>')


@app.get("/case/{student_ref}", response_class=HTMLResponse)
def case_detail(student_ref: str, msg: str = "", who=Depends(principal)) -> str:
    """One case: how its deadline was reached, who overrode what, and exactly
    which fields this identity is permitted to see."""
    from .. import store
    from ..gateway import project_for_scopes

    who.require_record(student_ref)
    for scope in ("case.read", "case.read_own", "case.read_redacted"):
        if scope in who.scopes:
            break
    else:
        scope = "case.read"
    _needs(who, scope)
    case = store.get_case(student_ref)
    if case is None:
        raise HTTPException(404, "no such case")

    view = project_for_scopes(who.scopes, case)
    d = case.deadline

    corrections = "".join(
        f"<tr><td class=mono>{e(c.field)}</td><td class=mono>{e(str(c.value))}</td>"
        f"<td>{e(c.reason)}</td><td class=mono>{e(c.by)}</td>"
        f"<td class=mono>{e(c.computed_was or '—')}</td></tr>"
        for c in case.corrections) or (
        "<tr><td colspan=5 class=empty>No corrections. Everything here was "
        "computed by the fleet.</td></tr>")

    sessions = ""
    for row in store.deliveries_for(student_ref)[:10]:
        state = "assessed" if row.get("assessed") else "pending"
        sessions += (f"<tr><td class=mono>{e(str(row.get('service_date')))}</td>"
                     f"<td class=mono>{e(str(row.get('minutes')))}m / "
                     f"{e(str(row.get('units_billed')))}u</td>"
                     f"<td>{e((row.get('note') or '')[:70])}</td>"
                     f"<td class=mono>{e(state)}</td></tr>")
    sessions = sessions or "<tr><td colspan=4 class=empty>No sessions logged.</td></tr>"

    log_form = ""
    if "case.write" in who.scopes and not read_only():
        log_form = (
            f"<h3>Log a session</h3>"
            f"<p class=sub>What a provider records after seeing the student. The "
            f"fleet assesses it against the IEP on the next tick and decides "
            f"whether it would survive an audit.</p>"
            f"<form method=post action='/case/{e(student_ref)}/deliver' class=stack>"
            f"<label class=field><span>Service</span>"
            f"<input name=service value='speech-language therapy, individual' required></label>"
            f"<label class=field><span>Provider type</span>"
            f"<input name=provider_type value='speech-language pathologist' required></label>"
            f"<label class=field><span>Provider NPI</span>"
            f"<input name=npi value='1234567890' required></label>"
            f"<span class=row>"
            f"<label class=field><span>Minutes documented</span>"
            f"<input name=minutes type=number value=30 required></label>"
            f"<label class=field><span>Units billed</span>"
            f"<input name=units type=number value=2 required></label></span>"
            f"<label class=field><span>Session note</span>"
            f"<textarea name=note rows=3 required>"
            f"Individual session. Targeted /r/ in structured phrases, 70% accuracy "
            f"with minimal cueing.</textarea></label>"
            f"<span class=row><button class=btn>Log session</button></span></form>")

    def _leaves(val, prefix="", out=None):
        """Flatten to leaf fields.

        str() of a nested dict is a Python repr truncated mid-key -- unreadable,
        and this table is the clearest proof in the product that the gateway
        withholds fields rather than blanking them. Naming each leaf is the
        whole point: a reader can see `consent.received_on` is present and no
        clinical field is.
        """
        out = [] if out is None else out
        if isinstance(val, dict):
            for k, v in val.items():
                _leaves(v, f"{prefix}.{k}" if prefix else str(k), out)
        elif isinstance(val, (list, tuple)):
            out.append((prefix, ", ".join(str(x) for x in val) if val else "—"))
        else:
            out.append((prefix, "—" if val in (None, "") else str(val)))
        return out

    projected = "".join(
        f"<tr><td class=mono>{e(k)}</td><td class=mono>{e(v[:90])}</td></tr>"
        for k, v in sorted(_leaves(view)))

    return f"""<!doctype html><html lang=en><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<meta name=robots content="noindex,nofollow">
<title>{e(student_ref)} — {PROJECT_NAME}</title>{FONTS}<style>{CSS}</style>
<body><div class=wrap>
{_switcher(who)}
<a class=back href="/app">&larr; caseload</a>
{_banner()}
{_flash(msg)}
<header class=top>
  <div class=brandwrap>
    <div class=mark>H</div>
    <div class=brand><h1>{e(student_ref)}</h1>
      <span>{e(case.school_code)} &middot; {e(case.jurisdiction)}</span></div>
  </div>
  <div class=whoami>
    <div class=idchip><b>{e(who.email)}</b><span>{e(who.role.value)}</span></div>
    <div class=avatar>{e(who.email[:1].upper())}</div>
  </div>
</header>
<p class=sub>Stage: {e(case.stage.value)}</p>
<div class=tiles>
  <div class=tile><div class=n>{e(d.due_on.isoformat()) if d else '—'}</div>
    <div class=l>due</div></div>
  <div class="tile {'hot' if d and d.days_remaining < 0 else ''}">
    <div class=n>{abs(d.days_remaining) if d else '—'}</div>
    <div class=l>{'days overdue' if d and d.days_remaining < 0 else 'days left'}</div></div>
  <div class=tile><div class=n>{len(case.escalations_sent)}</div>
    <div class=l>notices sent</div></div>
  <div class="tile {'warn' if case.corrections else ''}">
    <div class=n>{len(case.corrections)}</div><div class=l>corrections</div></div>
</div>
<h2>How this deadline was reached</h2>
<p class=sub>{e(d.explanation) if d else
  'No clock. The consent date could not be read, so this case needs a human.'}</p>
<h2>Corrections</h2>
<div class=scroll><table><tr><th>field</th><th>set to</th><th>reason</th>
<th>by</th><th>fleet had computed</th></tr>{corrections}</table></div>
<h2>Sessions delivered</h2>
<div class=scroll><table><tr><th>date</th><th>time</th><th>note</th>
<th>claim</th></tr>{sessions}</table></div>
{log_form}
<h2>What this identity may see</h2>
<p class=sub>Fields above your ceiling are <b>absent</b>, not blanked — the
gateway never returns them, so they cannot leak from a page that never had them.</p>
<div class=scroll><table><tr><th>field</th><th>value</th></tr>{projected}</table></div>
<footer>{PROJECT_NAME} · agents on Cloud Run and Agent Engine · all data synthetic</footer>
</div></body></html>"""


def _family_explanation(case, d) -> str:
    """How the date was worked out, in words a parent would use.

    The fleet's own explanation is written for the person who has to defend the
    arithmetic -- "60 calendar days from 2026-06-28. 0 day(s) not counted under
    this rule." A family does not need the rule name or the excluded-day count,
    and putting it in front of them reads as a system talking to itself.
    """
    if d is None:
        return ""
    started = d.clock_started_on.isoformat() if d.clock_started_on else "the date we received it"
    line = (f"We counted from {started}, the day the district received your "
            f"signed consent form &mdash; that is the date the law uses, not "
            f"the date you signed.")
    if d.excluded_days:
        line += (f" {d.excluded_days} days were not counted because school was "
                 f"closed.")
    return f"<p class=sub>{line}</p>"


def _demo_family_ref() -> str | None:
    """Which child an unbound demo parent is shown.

    In a real deployment a parent is bound by PARENT_ASSIGNMENTS and this never
    runs. In the demo, pick the family with a notice waiting so the page has
    something real to show; fall back to any open case.
    """
    from .. import store
    try:
        pend = store.pending_outbound(20)
        if pend:
            return pend[0].student_ref
        for c in store.open_cases():
            return c.student_ref
    except Exception:
        pass
    return None


@app.get("/family", response_class=HTMLResponse)
def family(request: Request, who=Depends(principal)) -> str:
    """What one family sees about their own child, and nothing else.

    A different surface, not a filtered dashboard. A parent does not want a
    caseload; they want to know where their child's evaluation stands, what
    the district owes them, and by when.
    """
    from .. import store
    from ..auth import Role

    if who.role is not Role.PARENT:
        return HTMLResponse(
            "<p>This page is the family view. "
            "<a href='/demo/as/parent'>Preview it as a parent</a>.</p>")

    ref = who.student_ref or _demo_family_ref()
    if ref is None:
        raise HTTPException(404, "no case on file")
    who.require_record(ref)

    case = store.get_case(ref)
    if case is None:
        raise HTTPException(404, "no case on file")

    d = case.deadline
    # Letters the family may actually see, computed BEFORE the tiles so the
    # count and the list cannot contradict each other. The tile used to show
    # len(case.escalations_sent), which counts rungs the fleet FIRED -- so a
    # family with three drafts and no approvals was told three letters had been
    # sent to them, directly above a panel saying nothing had.
    delivered = store.delivered_to_family(ref)

    # Days are recomputed against today rather than read from the stored value,
    # which is only as fresh as the last tick. A parent reading "0 days" on the
    # day before the deadline is being told something false.
    days = (d.due_on - date.today()).days if d else None

    if d is None:
        status_line = ("We have your consent form but could not read the date on "
                       "it clearly. Someone from the district will confirm it "
                       "with you before the clock starts.")
        big, sub = "Being checked", "a person is reviewing the form"
    elif days < 0:
        status_line = (f"By law this evaluation should have been finished by "
                       f"{d.due_on.isoformat()}. It is {abs(days)} "
                       f"days past that date. You do not have to wait quietly — "
                       f"the district owes you an explanation, and you can ask "
                       f"for it in writing.")
        big, sub = f"{abs(days)} days", "past the legal deadline"
    elif days == 0:
        status_line = (f"By law the district must finish this evaluation "
                       f"today, {d.due_on.isoformat()}.")
        big, sub = "Today", "is the legal deadline"
    else:
        status_line = (f"By law the district must finish this evaluation by "
                       f"{d.due_on.isoformat()}.")
        big, sub = (f"{days} days" if days != 1 else "1 day",
                    "until the legal deadline")

    letters = ""
    for o in delivered:
        audio = (f"<audio controls preload=none src='/outbox/{e(o.id)}/audio'></audio>"
                 if o.audio_path else "")
        letters += (f"<article class=letter><h3>{e(o.subject)}</h3>"
                    f"<p class=lettermeta>Sent {e(o.created_at[:10])} &middot; "
                    f"released by {e(o.approved_by or 'the district')}</p>"
                    f"<p class=letterbody>{e(o.body)}</p>{audio}</article>")
    letters = letters or (
        "<div class=locked>Nothing has been sent to you yet. When the district "
        "writes to you, the letter will appear here — and you will be able to "
        "listen to it as well as read it.</div>")

    return f"""<!doctype html><html lang=en><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<meta name=robots content="noindex,nofollow">
<title>Your child&rsquo;s evaluation — {PROJECT_NAME}</title>{FONTS}
<style>{CSS}</style>
<body><div class=wrap>
{_switcher(who)}
{_banner()}
<header class=top>
  <div class=brandwrap>
    <div class=mark>H</div>
    <div class=brand><h1>Your child&rsquo;s evaluation</h1>
      <span>{e(case.school_code)}</span></div>
  </div>
  <div class=whoami>
    <div class=idchip><b>{e(who.email)}</b><span>parent</span></div>
    <div class=avatar>{e(who.email[:1].upper())}</div>
  </div>
</header>

<div class="tiles fam">
  <div class="tile {'hot' if days is not None and days < 0 else ''}">
    <div class=n>{e(big)}</div><div class=l>{e(sub)}</div></div>
  <div class=tile><div class=n>{len(delivered)}</div>
    <div class=l>letters sent to you</div></div>
</div>

<h2>Where things stand</h2>
<p class=sub>{e(status_line)}</p>
{_family_explanation(case, d)}

<h2>Letters from the district</h2>
<p class=sub>Every letter here was written for you and released by a named
person at the district. Nothing reaches you automatically.</p>
{letters}

<h2>What you can ask for</h2>
<div class=rights>
  <p>You have the right to see your child&rsquo;s complete education record,
  including the evaluation itself and the notes behind it. This page is a status
  summary, not the record — ask the district for the full file and they must
  provide it.</p>
  <p>You can ask for anything here in your own language, and you can bring
  someone with you to any meeting.</p>
  <p>If the deadline has passed, you can put a request in writing and ask what
  the district intends to do about it.</p>
</div>

<footer>{PROJECT_NAME} &middot; this is a demonstration and every record is
synthetic &middot; no real family is contacted</footer>
</div></body></html>"""


@app.get("/demo/as/{role}")
def demo_as(role: str, request: Request, student: str = ""):
    """Switch the previewed identity. Refused outright once auth is on.

    This is a demo affordance, not an impersonation feature: it exists so one
    person can show the same records from five sides without five sign-ins. The
    guard is the same one that governs writes -- if the deployment can say who
    you are, it will not let you claim to be someone else.
    """
    from ..auth import auth_required

    if auth_required():
        raise HTTPException(
            403, "identity switching is a demo affordance and is refused when "
                 "authentication is enabled; sign in as the role you need")
    if role not in DEMO_IDENTITIES:
        raise HTTPException(404, "no such demo identity")

    target = "/family" if role == "parent" else "/app"
    resp = RedirectResponse(target, status_code=303)
    resp.set_cookie("demo_role", role, httponly=True, samesite="lax", path="/")
    if role == "parent" and student:
        resp.set_cookie("demo_student", student, httponly=True,
                        samesite="lax", path="/")
    return resp


def _switcher(who) -> str:
    """The identity bar. Rendered only while authentication is off."""
    from ..auth import auth_required

    if auth_required():
        return ""
    current = who.role.value
    tabs = ""
    for key, (_email, label) in DEMO_IDENTITIES.items():
        if key == "parent":
            continue
        on = " on" if key == current else ""
        tabs += f"<a class='swtab{on}' href='/demo/as/{e(key)}'>{e(label)}</a>"
    on = " on" if current == "parent" else ""
    tabs += (f"<a class='swtab{on}' href='/demo/as/parent'>Parent</a>")
    return (f"<div class=switcher><span class=swlabel>Viewing as</span>{tabs}"
            f"<span class=swnote>Same records, different identity. The gateway "
            f"decides what each one is handed.</span></div>")


@app.get("/", response_class=HTMLResponse)
def landing() -> str:
    """The public front door. Static, no Firestore, no models, no identity.

    Served from a file rather than built in Python: it is a marketing page that
    a designer should be able to edit without reading this module, and it must
    render for someone who is not signed in and never will be. The application
    lives at /app.
    """
    page = _SITE / "index.html"
    if not page.exists():
        # The image copies site/ explicitly; if that were ever dropped the
        # front door should say so rather than 500 on a missing file.
        return _plain_page(
            "Landing page not bundled",
            "This image was built without the site/ directory. The application "
            "itself is unaffected and is at /app.")
    return page.read_text(encoding="utf-8")


@app.get("/app", response_class=HTMLResponse)
def index(msg: str = "", who=Depends(principal)) -> str:
    # Every block below is an independent set of Firestore reads. Rendered
    # inline in the f-string they ran one after another, which is most of the
    # page load; they are I/O-bound, so a small pool collapses them to roughly
    # the slowest one. FastAPI already runs this sync endpoint in a worker
    # thread, and the Firestore client is thread-safe and now shared.
    with ThreadPoolExecutor(max_workers=6) as pool:
        f_cases = pool.submit(_cases_for, who)
        f_brief = pool.submit(_brief_block, who)
        f_intake = pool.submit(_intake_block, who)
        f_outbox = pool.submit(_outbox_block, who)
        f_claims = pool.submit(_claims_block, who)
        f_batch = pool.submit(_claim_batch_block, who)
        f_audit = pool.submit(_audit_block, who)

        try:
            cases = f_cases.result()
        except Exception:
            cases = []
        brief_html = f_brief.result()
        intake_html = f_intake.result()
        outbox_html = f_outbox.result()
        claims_html = f_claims.result()
        batch_html = f_batch.result()
        audit_html = f_audit.result()

    overdue = sum(1 for c in cases if c["days"] is not None and c["days"] < 0)
    week = sum(1 for c in cases if c["days"] is not None and 0 <= c["days"] <= 7)
    intake = sum(1 for c in cases if c["days"] is None)
    clinical = any(c["clinical_visible"] for c in cases)

    return f"""<!doctype html><html lang=en><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<meta name=robots content="noindex,nofollow">
<title>{PROJECT_NAME} — special education compliance</title>{FONTS}<style>{CSS}</style>
<body><div class=wrap>
{_switcher(who)}
<header class=top>
  <div class=brandwrap>
    <div class=mark>H</div>
    <div class=brand><h1>{PROJECT_NAME}</h1>
      <span>Special education compliance &middot; Medicaid claiming</span></div>
  </div>
  <div class=whoami>
    <div class=idchip><b>{e(who.email)}</b>
      <span>{e(who.role.value)} &middot;
        {"clinical detail visible" if clinical else "clinical detail withheld"}</span></div>
    <div class=avatar>{e(who.email[:1].upper())}</div>
  </div>
</header>
{_banner()}
{_flash(msg)}
<p class=sub>{date.today().isoformat()} · every row below was written by an
unattended agent, not a person. &nbsp;<a href="/walkthrough">Watch one case from start to finish &rarr;</a></p>
{brief_html}
<h2>At a glance</h2>
<div class=tiles>
  <div class="tile {'hot' if overdue else ''}"><div class=n>{overdue}</div><div class=l>overdue</div></div>
  <div class="tile {'warn' if week else ''}"><div class=n>{week}</div><div class=l>due within 7d</div></div>
  <div class=tile><div class=n>{len(cases)}</div><div class=l>open cases</div></div>
  <div class="tile {'warn' if intake else ''}"><div class=n>{intake}</div><div class=l>needs intake</div></div>
</div>
{intake_html}
<h2>Caseload</h2>
{_caseload_block(who, cases)}
{outbox_html}
{claims_html}
{batch_html}
{audit_html}
<h2>Family-facing media</h2>
<div class=media><div class=card><h3>Evaluation timeline</h3>
<p>Veo 3.1, generated once for the district — the timeline is identical for
every family.</p><video controls muted preload=none src="/explainer"></video></div></div>
<footer>{PROJECT_NAME} · agents on Cloud Run and Agent Engine · all data synthetic</footer>
</div></body></html>"""


# Registered at the end on purpose: walkthrough.py reads CSS and FONTS from this
# module, so it can only be imported once those exist.
from .walkthrough import (TourUnavailable,  # noqa: E402
                          router as _walkthrough_router)

app.include_router(_walkthrough_router)


@app.exception_handler(TourUnavailable)
def _tour_unavailable(request: Request, exc: TourUnavailable):
    """The walkthrough writes, so the public deployment explains rather than refuses."""
    from .walkthrough import unavailable_page

    return HTMLResponse(unavailable_page(), status_code=200)

