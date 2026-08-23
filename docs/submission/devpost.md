# Devpost submission text

**Project:** Hopscotch — a numbered sequence you move through in order, without
skipping a square, which is what a special education case does.

**In one line:** an agent fleet that keeps a school district inside the legal
clock on special education evaluations, and recovers the Medicaid money that
pays for it. *The compliance half is built and deployed. Of the claiming half, claim
**readiness** is built and tested; claim **submission** and its data feeds are
not.*

**Category:** Fortified Enterprise Fleet
**Project start date:** 22 August 2026 (matches first commit)
**Google SDK used:** Google ADK 2.7.1
**Repository:** https://github.com/Aditya-galaxy/Hopscotch
**Hosted project:** https://agentx-dashboard-761390104675.us-central1.run.app
(public, read-only, all data synthetic — no credentials needed)

---

## Features and functionality

Every hour, unattended, with nobody watching:

- **Recomputes every open statutory deadline** under that student's own
  jurisdiction rule and the district's school calendar — calendar-day,
  school-day and business-day counts, with breaks pausing the clock.
- **Escalates at T−14, T−7, T−2**, firing the *tightest* applicable rung once
  and retiring looser ones, so a case discovered late gets one accurate notice
  rather than three.
- **Extracts structure from messy intake documents** — phone photos, skewed
  scans, forwarded email — and returns `null` rather than guessing when a
  signature date is illegible.
- **Delegates down a privilege chain.** The gateway authorizes `casework-agent`
  for full clinical access to draft the statutory notice, Gemma strips every
  clinical finding, the gateway hands `family-agent` a *redacted projection*, it
  writes the parent letter, and Chirp speaks it in the family's language.
- **Queues every notice for a named human.** The fleet drafts; it never decides
  to contact a family. Nothing sends without an approver on the record.
- **Assesses Medicaid claim readiness** on delivered services — eligibility,
  NPI, licence validity on the service date, provider type, IEP window, units
  against documented minutes — plus whether the session note actually describes
  the authorized service. Over-billing blocks; under-billing is surfaced as
  unclaimed revenue.
- **Reviews any capability an agent tries to load** — downloaded, imported from
  another runtime, or written by the agent for itself — before the registry will
  sign it and the gateway will load it.
- **Writes the coordinator a daily brief**: one headline, what needs a human
  today, what moved overnight, what to watch. A live run surfaced *"blocked
  unauthorized scope access attempts from rogue-agent and family-agent"*
  unprompted, having read the gateway denials out of the audit trail.

A person only sees what it could not clear.

## Technologies used

**Models.** `gemini-3.5-flash` (workers, intent review, narrative consistency) ·
`gemini-3.7-flash` (supervisor: adjudication and the daily brief) ·
`gemma-4-26b-a4b-it-maas` (skill triage, clinical redaction) ·
`veo-3.1-fast-generate-001` (one cached district explainer) · **Chirp3-HD**
(spoken notices).

**Framework.** Google ADK 2.7.1 — `LlmAgent`, `run_async`,
`VertexAiMemoryBankService`.

**Google Cloud.** Cloud Run Jobs (the unattended clock) · Cloud Run (dashboard) ·
Cloud Scheduler · Firestore · Vertex AI · Vertex AI Agent Engine · Memory Bank ·
**Model Armor** · Cloud Trace · Cloud Build · Cloud Text-to-Speech.

**Also.** FastAPI, Pydantic, OpenTelemetry, Google Identity (OIDC) for human
authentication.

## Other data sources used

**All case data is synthetic.** No real student record was used at any point.
`scripts/generate_corpus.py` produces the case corpus with an answer key, and
`scripts/seed_deliveries.py` produces service logs in the proportions real
audits report.

**[mattpocock/skills](https://github.com/mattpocock/skills)** — 36 real,
widely-used Agent Skills, used as the false-positive control for the capability
gate. Not modified, not vendored.

**Published compliance data**, cited in the repo: NY State Comptroller audit
(29.2% of NYC referrals not evaluated in time), Massachusetts state audit (28% of
complaints past the 60-day limit, averaging 111 days late), AASA settlement
costs, and school-based Medicaid claiming guidance from state Medicaid agencies.

**Attack replicas are inert.** `data/replicas/` contains hand-authored
reproductions of *published attack patterns* — no live malware, nothing
executable, no downloaded payloads.

## Findings and learnings

**Static analysis approved a credential harvester, and it was right to.** A
skill that reads `~/.aws/credentials`, attaches them to an outbound header, and
tells the agent to conceal both steps passes every structural check — no shell,
no binary, no signature. It is ordinary English. That single result is the
argument for spending a model call, and the same shape appears on the Medicaid
side: a session that is eligible, licensed, correctly unitised and properly
noted passes every rule check and is still a denial, because the note describes
a *group* session while the IEP authorizes *individual*. **No pattern matches a
story.**

**The number that matters is the one that didn't fire.** 36 of 36 real skills
passed clean. A gate with false positives gets switched off by the person it
protects, so that measurement is worth as much as the catch.

**Fail closed, and make the failure legible.** An unavailable reviewer downgrades
a decision rather than approving — "we could not check" and "we checked and it
was fine" are different answers. A missing container dependency surfaced as
`memory write skipped: package required` rather than silence, which is the only
reason it was found.

**Classify by type, not by message.** The transient-failure check substring
matched, and retried `ArmorUnavailable` — which means "no template configured" —
three times with backoff, because its class name contains "unavailable". Names
are not error semantics.

**Authorization is not enough; shape the data.** `family-agent` does not receive
clinical fields and decline to use them. It never receives them. A check can be
forgotten at a new call site; a projection cannot leak a field it never
returned. Field classification fails closed, and that default immediately caught
a real gap the first table missed.

**Read the reasoning, not just the policy.** A shipping runtime allows
self-authored skills more freely than downloaded ones, and its stated reason is
sound: an agent with terminal access could run the code anyway. That argument
breaks exactly where governance begins — once an agent's authority is narrower
than "run anything", a self-authored skill is no longer something it could have
done regardless. And a command runs once; a skill reloads forever.

**Three deployment bugs shared one shape:** installed locally, absent from
`requirements.txt`, working on my machine and failing in the container. A test
now parses every import in `src/` and asserts each is declared.

**And four claims in my own documentation turned out to be aspirational** — a
Pub/Sub path that was never wired, a model ID that 404s, SPIFFE identity that is
really a name lookup, and delivery that stopped at disk. Each was written early
as intent and never revisited once the code went elsewhere. Two are now built;
two are corrected in the docs. Writing the architecture before the code is
useful. Not re-reading it afterwards is how a submission becomes untrue.

## Honest limits

Stated plainly because several read as implemented from the architecture alone.
(One that is *not* a limit: the deployed Cloud Run resources are named
`agentx-*` from an earlier name. Renaming them would have created new resources
with no execution history, and the unbroken hourly record since 22 August is
the evidence of unattended operation.)
Agent identity is **registry-declared, not attested** — cards carry distinct
`spiffe_id` values but authorization resolves agents by name, so what the
gateway enforces is a scope table, not zero-trust. **Nothing is delivered**:
`notify.send` is a declared scope with no implementation, so notices are drafted,
redacted, and voiced to disk but never sent. Documents are not ingested in
production — `intake-agent` runs from the eval harness where its accuracy is
measured. The three state rules are invented stand-ins; only the federal 60-day
baseline is accurate. And there is no user login, multi-tenancy, SIS
integration, FERPA review, or DPA.

What is real: it runs unattended on Google Cloud, the deadline arithmetic is
correct and tested, the gate's numbers are measured against real corpora, and
the projection genuinely withholds clinical fields rather than asking an agent
not to look at them.

## What's next

**Close the loop that doesn't exist yet.** `notify.send` is a declared scope with
no implementation — notices are drafted, redacted and voiced, then stop. Real
delivery, real SIS integration, and real district calendars are the unglamorous
90% between this and something a district could use.

**Then school-based Medicaid claiming**, which is what makes it a business
rather than a cost centre.

Districts can bill Medicaid for special education services delivered to eligible
students, and most underclaim badly. The reimbursement requirements are, almost
word for word, what this system already holds: *the need for the service must be
documented in the student's IEP; the services must be delivered in accordance
with the IEP; the services must be properly documented.* Same student, same IEP,
same coordinator — a second question asked of records the fleet already governs.

The amounts are meaningful — hundreds of thousands annually for a single
district — and they compound, because cost settlement sets future reimbursement
baselines, so underclaiming one year lowers the ceiling for the next.

That pairing is the point. Compliance is a painkiller: it stops lawsuits,
settlements and state findings. But painkillers are cost centres, and cost
centres get cut. Claiming is the revenue argument. Together the pitch stops
being *"please find budget"* and becomes *"we stop the lawsuits, and we find the
money that pays for us."*

The architecture does not change to support it. The statutory clock, the
identity-shaped projections, the audit trail and the capability gate all stay;
the new work is state-by-state Medicaid state plan rules, which vary
considerably more than the evaluation-timeline rules do.

**And the thing that would actually validate any of this:** put it in front of a
district compliance coordinator and watch which parts they ignore.
