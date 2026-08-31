# About the project — Devpost story

*(Paste everything below the line into the "About the project" field.)*

---

## Inspiration

Federal law gives a school district **sixty days** from a parent's consent to
complete a special education evaluation. Miss it and the district owes
compensatory services, faces a due process complaint, and lands on a state
corrective action plan.

The person holding that clock is usually **one coordinator** with two to six
hundred active files across a dozen schools, working in a spreadsheet and an
inbox. Consent forms arrive as phone photos. Evaluations come back as unlabeled
PDFs. Every step triggers a legally required notice to a family, in that
family's home language.

New York City's comptroller found the district missed the deadline for **29% of
the children it referred**. A Massachusetts audit found 28%, running an average
of **111 days late**.

That coordinator needs an autonomous agent more than almost anyone — and will
never be given one. The records are minors' clinical files, the district has no
security staff, and a wrong answer is legally expensive. Every vendor who could
serve them is selling to someone easier.

Then there was a second thing. Districts can bill Medicaid for the very services
these deadlines govern, and most underclaim badly — a single New York City audit
found **$431.6 million** unclaimed. The reimbursement requirements are, almost
word for word, what a compliance system already holds: the service is in the
IEP, it was delivered as written, it was documented.

**Compliance alone is a cost centre, and cost centres get cut. Claiming is what
pays for it.** That pairing is the product.

## What it does

Every hour, unattended, with nobody watching, Hopscotch:

- **Recomputes every open statutory deadline** under that student's own
  jurisdiction rule and that district's school calendar — calendar-day,
  school-day and business-day counts, with breaks pausing the clock.
- **Reads consent documents dropped by a coordinator** — phone-photo OCR noise,
  forwarded email, all of it — and returns `null` rather than guessing when a
  date is illegible. The page that accepts the document has *no model access at
  all*: it screens through Model Armor and parks it, and the fleet reads it on
  the next run.
- **Escalates at T−14, T−7 and T−2**, firing the *tightest* applicable rung once
  so a case discovered late gets one accurate notice rather than three.
- **Delegates down a privilege chain.** Casework drafts the statutory notice with
  full clinical access; a separate model strips every clinical finding; the
  gateway hands the family-facing agent a *redacted projection*; it writes the
  parent letter, and Chirp speaks it aloud in the family's language.
- **Queues every notice for a named human.** The fleet drafts. It never decides
  to contact a family.
- **Asks whether each delivered session would survive a Medicaid audit** —
  eligibility, NPI, licence validity on the service date, provider type, the IEP
  window, units against documented minutes — plus whether the session note
  actually describes the authorised service. Over-billing blocks; under-billing
  is surfaced as revenue left behind.
- **Reviews any capability an agent tries to load** before the registry signs it.
- **Writes the coordinator a daily brief.** One live run surfaced *"blocked
  unauthorized scope access attempts from rogue-agent and family-agent"*
  unprompted, having read the gateway denials out of the audit trail.

There are six identities — coordinator, psychologist, liaison, business office,
administrator, parent — and the same records look different to each. A parent
sees one child and no other; another child's case returns **404**, not 403,
because 403 would confirm that child exists.

## How we built it

**Gemini 3.5 Flash** for the workers, **Gemini 3.7 Flash** in the supervisor for
adjudication and the daily brief, **Gemma** for skill triage and clinical
redaction, **Veo** for one cached district explainer, **Chirp3-HD** for spoken
notices. Framework is **Google ADK 2.7.1**.

The shape that mattered most is a **split across two identities**:

- A **Cloud Run Job** (`agentx-tick`) runs the fleet on an hourly Cloud Scheduler
  trigger. It holds Vertex AI and Model Armor permissions.
- A **Cloud Run Service** serves the dashboard, the walkthrough and the family
  view. It has *no* Vertex access whatsoever. When a coordinator presses "run a
  tick now", the service asks the job to start through the Run Admin API — it
  cannot execute a model itself even if it were compromised.

State is **Firestore**. Idempotency is a ledger of deterministic effect IDs where
Firestore's `create()` *is* the dedupe — atomic, so two concurrent executions
cannot both claim the same effect. Cross-session memory is **Vertex AI Agent
Engine** with **Memory Bank**; both engines are listed in Google's managed
**Agent Registry**. Guardrails are **Model Armor**, in front of every inbound
document. Telemetry is OpenTelemetry spans to **Cloud Trace**. Generated audio
persists to **Cloud Storage**.

The enforcement point is a gateway that does two things, and the second is the
one that matters. `authorize()` refuses a call an agent has no scope for.
`project()` **shapes the data to the caller's identity** — the family-facing
agent does not receive clinical fields and decline to use them, it never receives
them. A check can be forgotten at a new call site; a projection cannot leak a
field it never returned.

There is no JavaScript anywhere in the UI. The served CSP is `script-src 'none'`
and a test asserts the application contains no `<script>` tag.

## Challenges we ran into

**The core calculation was legally wrong, and 161 passing tests did not notice.**
The whole product is one date arithmetic, and it keyed the statutory clock off
the parent's *signature*. The statute — 34 CFR §300.301(c)(1)(i) — runs the sixty
days from the day the agency **receives** consent. A form signed on the 1st and
delivered on the 10th was computing a deadline the district is not actually held
to. Every test passed because the tests encoded the same wrong assumption the
code did.

What exposed it was building the *input path*. Pasting a realistic consent form
through the new drop box produced a case the fleet refused to compute, even
though the receipt date was perfectly legible. Chasing that surfaced two more
defects hiding behind it: the tick carried its own duplicate copy of the same
wrong rule as a pre-check, so computable cases sat in "needs human" forever; and
removing that pre-check revealed the handler beneath it had been **unreachable
dead code**, because the supervisor's `call_worker` catches every exception and
converts it to a worker failure. A case state was being reported as an
operational fault.

**A dependency broke production from a clean commit.** The deployment died with
`Invalid database id %28default%29` on a build of *identical source*. Several
code-level fixes did nothing, because it was not a code defect: `requirements.txt`
was unpinned, so two builds of the same commit resolved different packages. Found
by building a clean venv, diffing seven differing packages against the working
environment, then toggling one alone three times — `google-api-core` 2.34.0 fine,
2.35.0 broken, 2.34.0 fine. Now pinned, with a lock file the image installs from.

**`source_document` was classified as administrative.** It is the raw intake
form, verbatim: the child's actual name, the referral reason in the parent's own
words. Every field derived from it is classified individually and one of them is
clinical — so the document is a superset that had been explicitly downgraded
*below* the fail-closed default. The case page was rendering it, name and all, to
an identity whose own header read "clinical detail withheld".

**The parent role failed open.** Record-level scoping — a parent may read one
child and no other — is a different mechanism from field-level projection, and
the first version returned early when a principal had no binding. That is correct
for staff, who are limited by *field* rather than by row, and exactly inverted for
a parent: an unbound parent was admitted to **every** child instead of none.
Caught by clicking another student's case as the demo parent and getting 200. It
is the shape a missing environment variable takes in production.

**Generated audio never survived.** Chirp runs inside the tick's container and
wrote the mp3 to that container's local disk. The container is destroyed when the
job ends, so the path survived in Firestore while the bytes did not — and the
dashboard, a different container entirely, rendered players for twenty notices
that could only ever 404.

**Smaller ones, each costing real time.** Gemini 3.x and Gemma serve only from
the `global` endpoint and 404 regionally even though `models.list()` reports them
present, while Model Armor is strictly regional — so the two need separate
location settings. Gemma treats `response_schema` as a hint rather than a
constraint. Gemini 3.x reasons by default, and a `max_output_tokens` of 120 was
entirely consumed by thinking before any answer appeared. A transient-failure
check substring-matched and retried `ArmorUnavailable` — which means "no template
configured" — three times, because its class name contains "unavailable".

## Accomplishments that we're proud of

**36 out of 36.** The capability gate passed every one of 36 real, widely-used
third-party Agent Skills with zero false positives — while catching a
hand-authored replica that reads AWS credentials, attaches them to an outbound
header, and tells the agent to conceal both steps. That replica passes every
structural check, because there is no code in it. It is ordinary English asking
nicely. **A gate with false positives gets switched off by the person it
protects**, so the number that did not fire is worth as much as the catch.

**More than 260 unattended executions, unbroken since 22 August.** Hourly, on Cloud
Scheduler, with nobody watching — and the audit trail shows escalations on every
single day.

**The projection genuinely withholds.** Computed live against a real case: the
casework agent is handed nine top-level fields and eight consent fields; the
family-facing agent is handed four and *none*.

**Honest limits, published.** No multi-tenancy. No model of the separate IDEA
§300.154 consent to bill Medicaid. Three of four state rules are invented
stand-ins. Agent Identity and Agent Gateway are substituted because the managed
APIs are not offered on a personal Cloud account. All of it is on the landing
page and in the README, because a district's counsel finds it anyway.

## What we learned

**Tests confirm a rule is applied consistently. They never confirm the rule is
right.** One hundred and sixty-one of them passed while the central calculation
computed a deadline the district was not held to. The fastest way to find a
domain error turned out to be making the system accept real input from outside.

**Classify by type, not by message.** Substring-matching an error string retried
a permanent failure three times with backoff. Names are not error semantics.

**Fail closed, and make the failure legible.** An unavailable reviewer downgrades
a decision rather than approving it — "we could not check" and "we checked and it
was fine" are different answers. Separately, a bare `except Exception: return
None` hid a `NameError` for four days: the dashboard reported "no brief yet"
while four briefs sat in Firestore. *No data* and *this code is broken* must not
look the same from outside.

**No pattern matches a story.** The same shape appeared twice, in two unrelated
halves of the product. A skill file that is pure English defeats every structural
check. A Medicaid session that is eligible, licensed, correctly unitised and
properly noted passes every rule check and is *still* a denial — because the note
describes a group session while the IEP authorises individual. That is the
argument for spending a model call, and it is the same argument both times.

**Authorisation is not enough; shape the data.** Field classification fails
closed, and that default immediately caught a real gap the first table missed.

**Enumerating scope names by hand is how privilege gets inverted.** A gate listed
two read scopes and did not mention the third — so the school psychologist, the
one identity with *full* clinical access, saw an empty caseload while the family
liaison saw all fifty-seven.

## What's next for Hopscotch

**Tenant isolation, first, because it gates everything.** Every collection is
global today. One district is fine; two is a breach. It will be enforced at the
gateway — the single funnel every agent already reads through — so it is one
auditable chokepoint rather than twenty call-site checks.

**Medicaid billing consent as a blocking gate.** IDEA §300.154 requires a
parental consent to *bill* that is separate from consent to evaluate. Its absence
is precisely the defect behind federal recoupment findings — **$1.5 billion** in
improper or unsupported school-based claims across four states — so it must block
rather than warn.

**Real ingestion and real rules.** OneRoster for roster, Ed-Fi v6.1's new Special
Education data model for IEP events, real district calendars, and legally
reviewed rules for two launch states. Two states is not a product; it is two
projects, so the third waits until both are proven.

**The paperwork, started now because it is the long pole.** 78% of district
technology officers require SOC 2 Type II, rising to 94% above ten thousand
students — nine to fourteen months and $30–80k, and no amount of engineering
shortens it. A signed data privacy agreement, and a FERPA review.

**Then adjacent workflows.** 504 plans, Child Find, records requests,
translation. Each is the same shape — deadline-driven, document-heavy,
compliance-exposed — and each reuses the gateway, the registry, the audit trail
and the idempotency ledger already built. That governance layer is the price of
admission to student records, it is paid once, and it amortises. A second
workflow sold into an existing district without new procurement is the whole
expansion argument.

**And the thing that would actually validate any of it:** put it in front of a
district compliance coordinator and watch which half they reach for.
