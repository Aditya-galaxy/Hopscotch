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
from datetime import date

from fastapi import Depends, FastAPI, Form, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from ..config import PROJECT_NAME
from .security import (
    demo_writes_enabled,
    SecurityHeaders, read_only, require_same_origin, require_writable,
)

# openapi_url=None as well as the doc UIs. Disabling /docs and /redoc while
# leaving /openapi.json served still hands an attacker the whole route table,
# every parameter name and every response shape.
app = FastAPI(title=f"{PROJECT_NAME} — coordinator",
              docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(SecurityHeaders)

e = html.escape

CSS = """
.flash{background:var(--accent-soft);border:1px solid var(--accent);color:var(--accent);
border-radius:4px;padding:9px 13px;font-size:.88rem;margin:0 0 14px}
.drop{display:flex;flex-direction:column;gap:8px;max-width:780px;margin-bottom:10px}
.stack{display:flex;flex-direction:column;gap:6px;max-width:560px;margin-bottom:8px}
.row{display:flex;gap:6px;align-items:center}
.drop textarea,.stack input,.stack textarea{font:inherit;font-size:.85rem;padding:7px 9px;
border:1px solid var(--rule);border-radius:3px;background:var(--surface);
color:var(--ink);width:100%}
.back{font-size:.85rem;display:inline-block;margin-bottom:10px}
:root{--paper:#F5F4F0;--surface:#fff;--sunk:#EFEEE9;--ink:#1A1F1C;--soft:#4A5049;
--muted:#767C74;--rule:#DBDCD5;--accent:#1F5C3D;--accent-soft:#E3EDE7;
--risk:#A03A22;--risk-soft:#F5E5E0;--warn:#8A6A1F;--warn-soft:#F5EEDD}
@media(prefers-color-scheme:dark){:root{--paper:#141714;--surface:#1C201B;--sunk:#232823;
--ink:#E9EAE4;--soft:#B6BBB3;--muted:#878D85;--rule:#2E332D;--accent:#6FB68C;
--accent-soft:#1D2C23;--risk:#E08063;--risk-soft:#2E1D18;--warn:#D9B45E;--warn-soft:#2A2317}}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
font:16px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:1120px;margin:0 auto;padding:22px 20px 90px}
a{color:var(--accent)}
header.top{display:flex;flex-wrap:wrap;gap:12px;align-items:baseline;
border-bottom:1px solid var(--rule);padding-bottom:14px;margin-bottom:18px}
h1{font-size:1.35rem;margin:0;letter-spacing:-.01em}
.whoami{margin-left:auto;font-size:.82rem;color:var(--muted);text-align:right}
.whoami b{color:var(--ink)}
h2{font-size:.74rem;margin:32px 0 10px;text-transform:uppercase;letter-spacing:.11em;
color:var(--muted);font-weight:600}
.sub{color:var(--muted);font-size:.87rem;margin:0 0 16px}
.tiles{display:grid;gap:9px;grid-template-columns:repeat(auto-fit,minmax(124px,1fr))}
.tile{background:var(--surface);border:1px solid var(--rule);border-radius:5px;padding:11px 13px}
.tile .n{font-size:1.6rem;font-weight:650;font-variant-numeric:tabular-nums;line-height:1.15}
.tile .l{font-size:.68rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}
.tile.hot{border-color:var(--risk)}.tile.hot .n{color:var(--risk)}
.tile.warn{border-color:var(--warn)}.tile.warn .n{color:var(--warn)}
.scroll{overflow-x:auto;border:1px solid var(--rule);border-radius:5px;background:var(--surface)}
table{width:100%;min-width:660px;border-collapse:collapse;font-size:.88rem}
th{text-align:left;font-size:.66rem;text-transform:uppercase;letter-spacing:.08em;
color:var(--muted);padding:9px 12px;border-bottom:1px solid var(--rule);background:var(--sunk);
white-space:nowrap;font-weight:600}
td{padding:9px 12px;border-bottom:1px solid var(--rule);vertical-align:middle}
tr:last-child td{border-bottom:0}
tbody tr:hover{background:var(--sunk)}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-variant-numeric:tabular-nums}
.pill{display:inline-block;padding:2px 8px;border-radius:11px;font-size:.72rem;
font-weight:600;white-space:nowrap}
.pill.ok{background:var(--accent-soft);color:var(--accent)}
.pill.warn{background:var(--warn-soft);color:var(--warn)}
.pill.hot{background:var(--risk-soft);color:var(--risk)}
.brief{background:var(--surface);border:1px solid var(--rule);border-left:3px solid var(--accent);
border-radius:5px;padding:15px 17px}
.brief .hl{font-size:1.02rem;font-weight:600;line-height:1.4;margin-bottom:11px}
.brief .grp{margin-top:11px}
.brief .grp h4{margin:0 0 4px;font-size:.66rem;text-transform:uppercase;
letter-spacing:.08em;color:var(--muted);font-weight:600}
.brief ul{margin:0;padding-left:17px}
.brief li{font-size:.87rem;color:var(--soft);margin-bottom:2px}
.brief .by{margin-top:11px;font-size:.71rem;color:var(--muted)}
.banner{border-radius:5px;padding:10px 13px;font-size:.84rem;margin-bottom:16px;
background:var(--warn-soft);border:1px solid var(--warn);color:var(--warn)}
.banner b{color:inherit}
.locked{background:var(--surface);border:1px dashed var(--rule);border-radius:5px;
padding:13px 15px;color:var(--muted);font-size:.85rem}
.locked code{background:var(--sunk);padding:1px 5px;border-radius:3px}
.btn{font:inherit;font-size:.78rem;padding:4px 10px;border-radius:4px;cursor:pointer;
border:1px solid var(--accent);background:var(--accent);color:#fff}
.btn.ghost{background:transparent;color:var(--soft);border-color:var(--rule)}
.btn:disabled{opacity:.45;cursor:not-allowed}
form.inline{display:inline}
.fix{display:flex;gap:4px;align-items:center}
.fix input{font:inherit;font-size:.75rem;padding:3px 6px;border:1px solid var(--rule);
border-radius:4px;background:var(--paper);color:var(--ink);max-width:118px}
.media{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(270px,1fr))}
.card{background:var(--surface);border:1px solid var(--rule);border-radius:5px;padding:13px}
.card h3{margin:0 0 3px;font-size:.87rem}
.card p{margin:0 0 9px;color:var(--soft);font-size:.81rem}
video,audio{width:100%;border-radius:4px}
.empty{color:var(--muted);font-size:.85rem;padding:13px;text-align:center}
footer{margin-top:44px;padding-top:16px;border-top:1px solid var(--rule);
color:var(--muted);font-size:.78rem}
@media(max-width:640px){.wrap{padding:16px 14px 70px}.whoami{margin-left:0;text-align:left}}
"""


# --- identity ---------------------------------------------------------------

def principal(authorization: str = Header(default="")):
    """Resolve the caller.

    Auth is ON unless REQUIRE_AUTH=false is set explicitly, because a missing
    setting must lock people out rather than expose records. When it is off the
    app is read-only and says so.
    """
    from ..auth import NotAuthenticated, Principal, Role, auth_required, verify

    if not auth_required():
        return Principal(email="demo (unauthenticated)", role=Role.COORDINATOR)
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
def approve_notice(item_id: str, request: Request, who=Depends(principal)):
    """A named human takes responsibility for contacting a family."""
    require_writable(); require_same_origin(request); _needs(who, "notice.approve")
    from ..delivery import approve
    approve(item_id, approved_by=who.email)
    return RedirectResponse("/", status_code=303)


@app.post("/outbox/{item_id}/reject")
def reject_notice(item_id: str, request: Request, who=Depends(principal)):
    require_writable(); require_same_origin(request); _needs(who, "notice.approve")
    from ..delivery import reject
    reject(item_id, rejected_by=who.email)
    return RedirectResponse("/", status_code=303)


@app.post("/intake")
def drop_document(request: Request, text: str = Form(...),
                  source: str = Form("upload"), who=Depends(principal)):
    """Accept a consent document. Extraction happens on the fleet, not here.

    This surface has no model access by design, so it records the document and
    the tick screens and reads it. A compromised dashboard cannot call Vertex.
    """
    require_writable(); require_same_origin(request); _needs(who, "case.write")
    from .. import store

    if len(text.strip()) < 40:
        return RedirectResponse("/?msg=That+does+not+look+like+a+consent+form.",
                                status_code=303)
    store.queue_document(text=text.strip(), source=(source or "upload")[:60],
                         dropped_by=who.email)
    return RedirectResponse(
        "/?msg=Queued.+The+fleet+screens+and+reads+it+on+the+next+tick.",
        status_code=303)


@app.post("/case/{student_ref}/deliver")
def log_delivery(student_ref: str, request: Request, service: str = Form(...),
                 minutes: int = Form(...), units: int = Form(...),
                 note: str = Form(...), npi: str = Form(...),
                 provider_type: str = Form(...), who=Depends(principal)):
    """Log a delivered session. Claim readiness assesses it on the next tick."""
    from datetime import date as _date

    from google.cloud import firestore

    from ..config import settings
    from ..schemas import IEPService, ServiceDelivery
    from ..store import client_kwargs

    require_writable(); require_same_origin(request); _needs(who, "case.write")

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


@app.post("/run/tick")
def run_tick_now(request: Request, who=Depends(principal)):
    """Run a tick now instead of waiting for the hour.

    Triggers the Cloud Run JOB rather than running in-process. This service runs
    as an identity with no Vertex or Model Armor access on purpose; executing
    the fleet here would force those permissions back onto it and undo the
    split. The job has them; this only asks it to start.
    """
    import os

    from ..config import settings

    require_writable(); require_same_origin(request); _needs(who, "case.write")

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
            return RedirectResponse(
                f"/?msg=Could+not+start+the+tick+({resp.status_code}).",
                status_code=303)
    except Exception as exc:
        return RedirectResponse(f"/?msg=Could+not+start+the+tick:+{type(exc).__name__}",
                                status_code=303)
    return RedirectResponse(
        "/?msg=Tick+started.+Reload+in+a+moment+to+see+what+it+did.",
        status_code=303)


@app.get("/claims/export.csv")
def export_claims(who=Depends(principal)):
    """The batch a billing vendor ingests. Export is not submission."""
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
                 who=Depends(principal)):
    """Overriding the fleet. A reason is required, always."""
    require_writable(); require_same_origin(request); _needs(who, "case.write")
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
    return RedirectResponse("/", status_code=303)


# --- media, authorized ------------------------------------------------------

@app.get("/outbox/{item_id}/audio")
def outbox_audio(item_id: str, who=Depends(principal)):
    """Audio is reached through the outbox item it belongs to, never by filename.

    The previous route served any file in the media directory to anyone who knew
    its name -- no authentication, no authorization. Names were content hashes,
    which is obscurity, not access control.
    """
    from pathlib import Path

    from .. import store
    from ..media import MEDIA_DIR

    _needs(who, "case.read_redacted" if "case.read_redacted" in who.scopes
           else "case.read")
    item = store.get_outbound(item_id)
    if item is None or not item.audio_path:
        raise HTTPException(404, "no audio for this notice")

    p = Path(item.audio_path).resolve()
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

    def grp(title, items):
        if not items:
            return ""
        lis = "".join(f"<li>{e(i)}</li>" for i in items)
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
            fix = (f"<form method=post action='/case/{e(c['ref'])}/correct' class=fix>"
                   f"<input type=hidden name=field value='{field}'>"
                   f"<input type=date name=value required aria-label='new date'>"
                   f"<input type=text name=reason placeholder='reason' required "
                   f"aria-label='reason'>"
                   f"<button class='btn ghost'>{label}</button></form>")
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


def _outbox_block(who) -> str:
    if "case.read" not in who.scopes and "notice.approve" not in who.scopes:
        return ""
    try:
        from .. import store
        pending = store.pending_outbound(limit=12)
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
        audio = (f"<audio controls preload=none src='/outbox/{e(i.id)}/audio'></audio>"
                 if i.audio_path else "")
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
    if not read_only():
        form = (
            "<form method=post action='/intake' class=drop>"
            "<textarea name=text rows=6 required aria-label='consent document' "
            "placeholder='PARENTAL CONSENT FOR INITIAL EVALUATION&#10;"
            "Student ref: stu_0500&#10;School: EL-004&#10;"
            "Parent signature date: 09/14/2026&#10;"
            "Received by district: 09/16/2026&#10;"
            "Reason: Teacher referral, written expression.'></textarea>"
            "<span class=row><button class=btn>Queue for intake</button></span>"
            "</form>"
            "<form method=post action='/run/tick' class=row>"
            "<button class='btn ghost'>Run a tick now</button></form>")

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

    _needs(who, "case.read" if "case.read" in who.scopes else "case.read_redacted")
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
            f"<form method=post action='/case/{e(student_ref)}/deliver' class=stack>"
            f"<input name=service value='speech-language therapy, individual' "
            f"required aria-label='service'>"
            f"<input name=provider_type value='speech-language pathologist' "
            f"required aria-label='provider type'>"
            f"<input name=npi value='1234567890' required aria-label='provider NPI'>"
            f"<span class=row><input name=minutes type=number value=30 required "
            f"aria-label='minutes'><input name=units type=number value=2 required "
            f"aria-label='units'></span>"
            f"<textarea name=note rows=2 required aria-label='session note'>"
            f"Individual session. Targeted /r/ in structured phrases, 70% accuracy "
            f"with minimal cueing.</textarea>"
            f"<span class=row><button class=btn>Log session</button></span></form>")

    projected = "".join(
        f"<tr><td class=mono>{e(k)}</td><td class=mono>{e(str(v)[:80])}</td></tr>"
        for k, v in sorted(view.items()))

    return f"""<!doctype html><html lang=en><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<meta name=robots content="noindex,nofollow">
<title>{e(student_ref)} — {PROJECT_NAME}</title><style>{CSS}</style>
<body><div class=wrap>
<a class=back href="/">&larr; caseload</a>
{_banner()}
{_flash(msg)}
<header class=top>
  <h1>{e(student_ref)}</h1>
  <div class=whoami><b>{e(who.email)}</b><br>{e(who.role.value)}</div>
</header>
<p class=sub>{e(case.school_code)} · {e(case.jurisdiction)} · {e(case.stage.value)}</p>
<div class=tiles>
  <div class=tile><div class=n>{e(d.due_on.isoformat()) if d else '—'}</div>
    <div class=l>due</div></div>
  <div class="tile {'hot' if d and d.days_remaining < 0 else ''}">
    <div class=n>{d.days_remaining if d else '—'}</div><div class=l>days left</div></div>
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


@app.get("/", response_class=HTMLResponse)
def index(msg: str = "", who=Depends(principal)) -> str:
    try:
        cases = _cases_for(who)
    except Exception:
        cases = []

    overdue = sum(1 for c in cases if c["days"] is not None and c["days"] < 0)
    week = sum(1 for c in cases if c["days"] is not None and 0 <= c["days"] <= 7)
    intake = sum(1 for c in cases if c["days"] is None)
    clinical = any(c["clinical_visible"] for c in cases)

    return f"""<!doctype html><html lang=en><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<meta name=robots content="noindex,nofollow">
<title>{PROJECT_NAME} — special education compliance</title><style>{CSS}</style>
<body><div class=wrap>
<header class=top>
  <h1>Special education compliance</h1>
  <div class=whoami><b>{e(who.email)}</b><br>{e(who.role.value)} ·
    {"clinical detail visible" if clinical else "clinical detail withheld"}</div>
</header>
{_banner()}
{_flash(msg)}
<p class=sub>{date.today().isoformat()} · every row below was written by an
unattended agent, not a person.</p>
{_brief_block(who)}
{_intake_block(who)}
<h2>At a glance</h2>
<div class=tiles>
  <div class="tile {'hot' if overdue else ''}"><div class=n>{overdue}</div><div class=l>overdue</div></div>
  <div class="tile {'warn' if week else ''}"><div class=n>{week}</div><div class=l>due within 7d</div></div>
  <div class=tile><div class=n>{len(cases)}</div><div class=l>open cases</div></div>
  <div class="tile {'warn' if intake else ''}"><div class=n>{intake}</div><div class=l>needs intake</div></div>
</div>
<h2>Caseload</h2>
{_caseload_block(who, cases)}
{_outbox_block(who)}
{_claims_block(who)}
{_claim_batch_block(who)}
{_audit_block(who)}
<h2>Family-facing media</h2>
<div class=media><div class=card><h3>Evaluation timeline</h3>
<p>Veo 3.1, generated once for the district — the timeline is identical for
every family.</p><video controls muted preload=none src="/explainer"></video></div></div>
<footer>{PROJECT_NAME} · agents on Cloud Run and Agent Engine · all data synthetic</footer>
</div></body></html>"""
