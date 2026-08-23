"""Coordinator dashboard.

Scanned, not read. A coordinator opens this between meetings and needs to know
in five seconds what is on fire. So: overdue first, deadline countdowns encoded
as colour and number, and the audit trail visible rather than buried -- because
an agent that acted on a case without the coordinator being able to see why is
exactly the thing districts are right to refuse.
"""
from __future__ import annotations

import html
from datetime import date

from fastapi import Depends, FastAPI, Form, Header, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from ..config import PROJECT_NAME
from ..registry import discover

app = FastAPI(title=f"{PROJECT_NAME} — coordinator")


def principal(authorization: str = Header(default="")):
    """Resolve the caller.

    Auth is ON unless REQUIRE_AUTH=false is set explicitly -- a missing setting
    must lock people out rather than expose records. The public demo sets it to
    false deliberately, and the page says so, because every record in it is
    invented.
    """
    from ..auth import (NotAuthenticated, Principal, Role, auth_required, verify)

    if not auth_required():
        return Principal(email="demo@hopscotch.invalid", role=Role.COORDINATOR)
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(401, "sign in required")
    try:
        return verify(token)
    except NotAuthenticated as e:
        raise HTTPException(401, str(e)) from e

CSS = """
:root{--paper:#F5F4F0;--surface:#fff;--ink:#1A1F1C;--soft:#4A5049;--muted:#767C74;
--rule:#DBDCD5;--accent:#1F5C3D;--accent-soft:#E3EDE7;--risk:#A03A22;--risk-soft:#F5E5E0;
--warn:#8A6A1F;--warn-soft:#F5EEDD}
@media(prefers-color-scheme:dark){:root{--paper:#141714;--surface:#1C201B;--ink:#E9EAE4;
--soft:#B6BBB3;--muted:#878D85;--rule:#2E332D;--accent:#6FB68C;--accent-soft:#1D2C23;
--risk:#E08063;--risk-soft:#2E1D18;--warn:#D9B45E;--warn-soft:#2A2317}}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);
font:16px/1.55 ui-sans-serif,system-ui,-apple-system,sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:28px 22px 80px}
h1{font-size:1.5rem;margin:0 0 2px;letter-spacing:-.01em}
h2{font-size:1rem;margin:34px 0 12px;text-transform:uppercase;letter-spacing:.1em;
color:var(--muted);font-weight:600}
.sub{color:var(--muted);font-size:.9rem;margin-bottom:20px}
.tiles{display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(130px,1fr))}
.tile{background:var(--surface);border:1px solid var(--rule);border-radius:4px;padding:12px 14px}
.tile .n{font-size:1.7rem;font-weight:650;font-variant-numeric:tabular-nums;line-height:1.1}
.tile .l{font-size:.72rem;text-transform:uppercase;letter-spacing:.09em;color:var(--muted)}
.tile.hot .n{color:var(--risk)} .tile.warn .n{color:var(--warn)}
.scroll{overflow-x:auto;border:1px solid var(--rule);border-radius:4px;background:var(--surface)}
table{width:100%;min-width:640px;border-collapse:collapse;font-size:.9rem}
th{text-align:left;font-size:.68rem;text-transform:uppercase;letter-spacing:.09em;
color:var(--muted);padding:9px 12px;border-bottom:1px solid var(--rule);background:var(--paper)}
td{padding:9px 12px;border-bottom:1px solid var(--rule);vertical-align:top;white-space:nowrap}
tr:last-child td{border-bottom:0}
.mono{font-family:ui-monospace,SFMono-Regular,monospace;font-variant-numeric:tabular-nums}
.pill{display:inline-block;padding:1px 8px;border-radius:10px;font-size:.74rem;font-weight:600}
.pill.ok{background:var(--accent-soft);color:var(--accent)}
.pill.warn{background:var(--warn-soft);color:var(--warn)}
.pill.hot{background:var(--risk-soft);color:var(--risk)}
.media{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(280px,1fr))}
.card{background:var(--surface);border:1px solid var(--rule);border-radius:4px;padding:14px}
.card h3{margin:0 0 4px;font-size:.9rem}.card p{margin:0 0 10px;color:var(--soft);font-size:.84rem}
video,audio{width:100%;border-radius:3px}
.banner{background:var(--warn-soft);border:1px solid var(--warn);color:var(--warn);
border-radius:4px;padding:9px 13px;font-size:.85rem;margin-bottom:14px}
.banner code{background:transparent;color:inherit}
.btn{font:inherit;font-size:.8rem;padding:4px 10px;border-radius:3px;cursor:pointer;
border:1px solid var(--accent);background:var(--accent);color:#fff}
.btn.ghost{background:transparent;color:var(--muted);border-color:var(--rule)}
.muted{color:var(--muted);font-size:.8rem}
.fix{display:flex;gap:4px}
.fix input{font:inherit;font-size:.76rem;padding:3px 6px;border:1px solid var(--rule);
border-radius:3px;background:var(--paper);color:var(--ink);max-width:120px}
.empty{color:var(--muted);font-size:.88rem;padding:14px;background:var(--surface);
border:1px dashed var(--rule);border-radius:4px}
.brief{background:var(--surface);border:1px solid var(--rule);border-left:3px solid var(--accent);
border-radius:4px;padding:16px 18px;margin-bottom:20px}
.brief .hl{font-size:1.05rem;font-weight:600;margin-bottom:12px;line-height:1.4}
.brief .grp{margin-top:12px}
.brief .grp h4{margin:0 0 5px;font-size:.68rem;text-transform:uppercase;
letter-spacing:.09em;color:var(--muted);font-weight:600}
.brief ul{margin:0;padding-left:17px}.brief li{font-size:.88rem;color:var(--soft);margin-bottom:3px}
.brief .by{margin-top:12px;font-size:.72rem;color:var(--muted)}
"""


def _auth_banner() -> str:
    from ..auth import auth_required
    if auth_required():
        return ""
    return ("<div class=banner><b>Authentication disabled</b> — this is a public "
            "demo and every record in it is synthetic. Set "
            "<code>REQUIRE_AUTH=true</code> for a real deployment; it is the "
            "default in code.</div>")


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


def _cases() -> list[dict]:
    from .. import store
    rows = []
    for c in store.open_cases():
        d = c.deadline
        rows.append({
            "ref": c.student_ref, "school": c.school_code,
            "jur": c.jurisdiction, "stage": c.stage.value,
            "due": d.due_on.isoformat() if d else "—",
            "days": d.days_remaining if d else None,
            "sent": ", ".join(f"T-{r}" for r in sorted(c.escalations_sent, reverse=True)) or "—",
            "corrected": bool(c.corrections),
        })
    return sorted(rows, key=lambda r: (r["days"] is not None, r["days"] if r["days"] is not None else 0))


def _audit(limit: int = 25) -> list[dict]:
    from google.cloud import firestore
    from ..config import settings
    db = firestore.Client(project=settings.project_id or None,
                          database=settings.firestore_db)
    rows = [d.to_dict() for d in db.collection(settings.audit_collection).limit(200).stream()]
    return sorted(rows, key=lambda r: r.get("at", ""), reverse=True)[:limit]


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.post("/outbox/{item_id}/approve")
def approve_notice(item_id: str, who=Depends(principal)):
    """A named human takes responsibility. The fleet cannot call this."""
    from ..auth import NotPermitted
    from ..delivery import approve
    try:
        who.require("notice.approve")
    except NotPermitted as e:
        raise HTTPException(403, str(e)) from e
    approve(item_id, approved_by=who.email)
    return RedirectResponse("/", status_code=303)


@app.post("/outbox/{item_id}/reject")
def reject_notice(item_id: str, who=Depends(principal)):
    from ..auth import NotPermitted
    from ..delivery import reject
    try:
        who.require("notice.approve")
    except NotPermitted as e:
        raise HTTPException(403, str(e)) from e
    reject(item_id, rejected_by=who.email)
    return RedirectResponse("/", status_code=303)


@app.post("/case/{student_ref}/correct")
def correct_case(student_ref: str, field: str = Form(...), value: str = Form(...),
                 reason: str = Form(...), who=Depends(principal)):
    """A coordinator overriding the fleet. Requires a reason, always."""
    from datetime import date as _date

    from ..auth import NotPermitted
    from ..schemas import Correction
    from .. import store

    try:
        who.require("case.write")
    except NotPermitted as e:
        raise HTTPException(403, str(e)) from e
    if not reason.strip():
        raise HTTPException(400, "a correction needs a reason")

    case = store.get_case(student_ref)
    was = (case.deadline.due_on.isoformat()
           if case and case.deadline and field == "due_on" else "")
    try:
        store.apply_correction(student_ref, Correction(
            field=field, value=_date.fromisoformat(value),
            reason=reason.strip(), by=who.email, computed_was=was))
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e)) from e
    return RedirectResponse("/", status_code=303)


@app.get("/media/{name}")
def media(name: str):
    from ..media import MEDIA_DIR
    p = (MEDIA_DIR / name).resolve()
    if not p.is_file() or MEDIA_DIR.resolve() not in p.parents:
        return HTMLResponse("not found", status_code=404)
    return FileResponse(p)


def _outbox_html(who) -> str:
    """Notices waiting on a person. Nothing here has been sent."""
    e = html.escape
    try:
        from .. import store
        pending = store.pending_outbound(limit=10)
        summary = store.outbox_summary()
    except Exception:
        return ""
    if not summary.get("total"):
        return ""

    can_approve = "notice.approve" in who.scopes
    rows = ""
    for i in pending:
        buttons = (
            f"<form method=post action='/outbox/{e(i.id)}/approve' style='display:inline'>"
            f"<button class=btn>Approve &amp; send</button></form> "
            f"<form method=post action='/outbox/{e(i.id)}/reject' style='display:inline'>"
            f"<button class='btn ghost'>Reject</button></form>"
            if can_approve else "<span class=muted>read-only</span>")
        rows += (f"<tr><td class='mono'>{e(i.student_ref)}</td>"
                 f"<td>{e(i.notice_type.replace('_',' '))}</td>"
                 f"<td class='mono'>{e(i.language)}</td>"
                 f"<td>{e(i.body[:90])}…</td><td>{buttons}</td></tr>")
    rows = rows or "<tr><td colspan=5 class='empty'>nothing awaiting approval</td></tr>"
    counts = " · ".join(f"{v} {k.replace('_',' ')}"
                        for k, v in sorted(summary["by_status"].items()))

    return (f"<h2>Outbox — awaiting a human</h2>"
            f"<p class=sub>The fleet drafts and queues. Nothing reaches a family "
            f"until a named person approves it. <b>{e(counts)}</b></p>"
            f"<div class=scroll><table><tr><th>student</th><th>notice</th>"
            f"<th>language</th><th>preview</th><th></th></tr>{rows}</table></div>")


def _claims_html() -> str:
    """The revenue half, on screen. Blocked claims first -- those are denials
    waiting to happen; the under-billed count is money already left behind."""
    e = html.escape
    try:
        from .. import store
        c = store.readiness_summary()
    except Exception:
        return ""
    if not c.get("assessed"):
        return ""

    rows = "".join(
        f"<tr><td class='mono'>{e(str(b.get('student_ref') or ''))}</td>"
        f"<td>{e(b.get('requirement',''))}</td>"
        f"<td>{e((b.get('detail') or '')[:90])}</td></tr>"
        for b in c["blocked"][:12]) or \
        "<tr><td colspan=3 class='empty'>nothing blocked</td></tr>"

    return (f"<h2>Medicaid claim readiness</h2>"
            f"<div class=tiles style='margin-bottom:14px'>"
            f"<div class=tile><div class=n>{c['assessed']}</div>"
            f"<div class=l>sessions assessed</div></div>"
            f"<div class=tile><div class=n>{c['billable']}</div>"
            f"<div class=l>billable</div></div>"
            f"<div class=\"tile {'hot' if c['blocked'] else ''}\">"
            f"<div class=n>{len(c['blocked'])}</div>"
            f"<div class=l>would be denied</div></div>"
            f"<div class=\"tile {'warn' if c['underbilled_sessions'] else ''}\">"
            f"<div class=n>{c['underbilled_sessions']}</div>"
            f"<div class=l>under-billed</div></div></div>"
            f"<div class=scroll><table><tr><th>student</th><th>requirement</th>"
            f"<th>why</th></tr>{rows}</table></div>")


def _brief_html() -> str:
    """The brief, or an honest absence. Never a fabricated one."""
    e = html.escape
    try:
        from ..brief import latest
        b = latest()
    except Exception:
        b = None
    if b is None:
        return ('<div class=empty>No brief yet — the supervisor writes one on '
                'the first tick of each day.</div>')

    def grp(title: str, items: list[str]) -> str:
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


@app.get("/", response_class=HTMLResponse)
def index(who=Depends(principal)) -> str:
    e = html.escape
    try:
        cases = _cases()
    except Exception as ex:
        cases = []
        case_err = str(ex)[:120]
    else:
        case_err = ""

    overdue = sum(1 for c in cases if c["days"] is not None and c["days"] < 0)
    week = sum(1 for c in cases if c["days"] is not None and 0 <= c["days"] <= 7)
    intake = sum(1 for c in cases if c["days"] is None)

    can_write = "case.write" in who.scopes
    rows = ""
    for c in cases[:40]:
        fix = ""
        if can_write:
            field = "consent_signed_on" if c["days"] is None else "due_on"
            label = "Set consent date" if c["days"] is None else "Override"
            fix = (f"<form method=post action='/case/{e(c['ref'])}/correct' class=fix>"
                   f"<input type=hidden name=field value='{field}'>"
                   f"<input type=date name=value required>"
                   f"<input type=text name=reason placeholder='reason' required>"
                   f"<button class='btn ghost'>{label}</button></form>")
        flag = ("<span class='pill warn' title='human override'>corrected</span> "
                if c.get("corrected") else "")
        rows += (f"<tr><td class='mono'>{e(c['ref'])}</td><td class='mono'>{e(c['school'])}</td>"
                 f"<td class='mono'>{e(c['jur'])}</td><td class='mono'>{flag}{e(c['due'])}</td>"
                 f"<td>{_pill(c['days'])}</td><td class='mono'>{e(c['sent'])}</td>"
                 f"<td>{fix}</td></tr>")
    rows = rows or "<tr><td colspan=7 class='empty'>no open cases</td></tr>"

    try:
        agents = discover()
    except Exception:
        agents = []
    areg = "".join(
        f"<tr><td class='mono'>{e(a.get('name',''))}</td><td class='mono'>v{e(a.get('version',''))}</td>"
        f"<td>{e(a.get('department',''))}</td><td class='mono'>{e(', '.join(a.get('scopes') or []))}</td></tr>"
        for a in agents) or "<tr><td colspan=4 class='empty'>registry empty</td></tr>"

    try:
        aud = _audit()
    except Exception:
        aud = []
    arows = "".join(
        f"<tr><td class='mono'>{e((r.get('at') or '')[:19])}</td>"
        f"<td>{e(r.get('event',''))}</td><td class='mono'>{e(str(r.get('student_ref') or r.get('agent') or '—'))}</td>"
        f"<td class='mono'>{e(str(r.get('rung') or r.get('scope') or ''))}</td></tr>"
        for r in aud) or "<tr><td colspan=4 class='empty'>no audit rows</td></tr>"

    from ..media import MEDIA_DIR
    vid = (MEDIA_DIR / "evaluation-timeline.mp4").exists()
    auds = sorted(p.name for p in MEDIA_DIR.glob("notice-*.mp3")) if MEDIA_DIR.exists() else []
    players = "".join(
        f"<div class='card'><h3>{e(n.split('-')[1])} notice</h3>"
        f"<p>Chirp3-HD, spoken for families who will not read the letter.</p>"
        f"<audio controls src='/media/{e(n)}'></audio></div>" for n in auds)
    video = (f"<div class='card'><h3>Evaluation timeline</h3>"
             f"<p>Veo 3.1. Generated once for the district, cached — the timeline "
             f"is identical for every family.</p>"
             f"<video controls muted src='/media/evaluation-timeline.mp4'></video></div>"
             if vid else "")

    return f"""<!doctype html><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>{PROJECT_NAME} — coordinator</title><style>{CSS}</style>
<div class=wrap>
<h1>Special education compliance</h1>
{_auth_banner()}
<div class=sub>{date.today().isoformat()} · every row below was updated by an
unattended agent, not a person{f" · <b>{e(case_err)}</b>" if case_err else ""}</div>
{_brief_html()}
<div class=tiles>
  <div class="tile {'hot' if overdue else ''}"><div class=n>{overdue}</div><div class=l>overdue</div></div>
  <div class="tile {'warn' if week else ''}"><div class=n>{week}</div><div class=l>due within 7d</div></div>
  <div class=tile><div class=n>{len(cases)}</div><div class=l>open cases</div></div>
  <div class="tile {'warn' if intake else ''}"><div class=n>{intake}</div><div class=l>needs intake</div></div>
  <div class=tile><div class=n>{len(agents)}</div><div class=l>agents published</div></div>
</div>
<h2>Caseload</h2>
<div class=scroll><table><tr><th>student</th><th>school</th><th>jurisdiction</th><th>due</th><th>status</th><th>notices sent</th><th></th></tr>{rows}</table></div>
<h2>Agent registry</h2>
<div class=scroll><table><tr><th>agent</th><th>version</th><th>department</th><th>scopes</th></tr>{areg}</table></div>
<h2>Audit trail</h2>
<div class=scroll><table><tr><th>when</th><th>event</th><th>subject</th><th>detail</th></tr>{arows}</table></div>
{_outbox_html(who)}
{_claims_html()}
<h2>Family-facing media</h2>
<div class=media>{video}{players or "<div class=empty>no audio generated yet</div>"}</div>
</div>"""
