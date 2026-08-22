# Devpost submission text

**Category:** Fortified Enterprise Fleet
**Project start date:** 22 August 2026 (matches first commit)
**Google SDK used:** Google ADK 2.7.1
**Repository:** https://github.com/Aditya-galaxy/AgentX
**Hosted project:** https://agentx-dashboard-761390104675.us-central1.run.app
(public, read-only, all data synthetic — no credentials needed)

---

## Inspiration

Federal law gives a school district 60 calendar days from a parent's signature
to complete a special education evaluation. About twenty states override that
with their own count — 45 school days, 30 business days — and school days pause
across every break on the district's calendar. Miss the deadline and the
district owes compensatory services and faces a due process complaint.

The person holding that clock is usually one coordinator tracking two to six
hundred active files across a dozen schools, in a spreadsheet and an inbox.

They need an autonomous agent more than any executive does. They will never get
one, because the data is minors' clinical records and the district has no
security team. Capability stopped being the blocker in 2026 — governance is.
AgentX is both halves.

## What it does

Every hour, unattended, with nobody watching, AgentX:

- recomputes every open case's statutory deadline under its own jurisdiction's
  counting rule and the district's school calendar
- escalates at T−14, T−7, T−2 — **once each, ever**, across hundreds of replays
- extracts structure from deliberately messy intake documents, and returns
  `null` rather than guessing when a signature date is illegible
- screens every inbound document through Model Armor before a model reads it
- reviews any new capability an agent tries to load, before it can load it
- strips clinical findings, speaks the notice in the family's language, and
  shows them the timeline

A person only sees what it could not clear.

## How we built it

Three layers.

**The operational fleet** — five ADK agents. A supervisor on Gemini 3.5 Pro that
validates every worker return against a schema, retries once, circuit-breaks at
three, and dead-letters to a human queue. Four workers on Gemini 3.5 Flash.

**The governance plane** — per-agent SPIFFE identity, a gateway that denies by
default, Model Armor on anything from outside the district, and OpenTelemetry
reasoning chains a district lawyer could read.

**The capability gate** — every skill an agent tries to load, whether
downloaded, imported across runtimes, or written by the agent for itself,
passes four reviewers before the registry will sign it.

The deadline arithmetic is pure Python and never delegated to a model. An agent
decides *when to escalate and to whom*; it restates a computed date and is
instructed never to recompute one. A hallucinated statutory date is a lawsuit.

## Technologies used

**Models:** `gemini-3.5-flash` (workers, intent review) · `gemini-3.5-pro`
(supervisor adjudication only) · `gemma-4-26b-a4b-it-maas` (skill triage,
clinical redaction) · `veo-3.1-fast-generate-001` (one cached explainer) ·
**Chirp3-HD** (spoken notices)

**Framework:** Google ADK 2.7.1 (`LlmAgent`, `run_async`,
`VertexAiMemoryBankService`)

**Google Cloud:** Cloud Run Jobs · Cloud Run · Cloud Scheduler ·
Firestore · Vertex AI · Vertex AI Agent Engine · Memory Bank · **Model Armor** ·
Cloud Trace · Cloud Build

**Data sources:** All synthetic. `scripts/generate_corpus.py` produces the case
corpus with an answer key. The benign skill corpus is
[mattpocock/skills](https://github.com/mattpocock/skills), 36 real skills, used
as a false-positive control. Attack replicas in `data/replicas/` are inert
hand-authored reproductions of published attack *patterns* — no live malware.

## Challenges we ran into

**Gemini 3.x and Gemma are served only from the `global` endpoint.** A regional
call 404s even though `models.list()` reports the model present in that region.
ADK builds its own client from `GOOGLE_CLOUD_LOCATION`, so that variable has to
be the model location — while Model Armor is strictly regional and needs its
own.

**Gemma treats `response_schema` as a hint, not a constraint.** It invented
fields and answered `"Medium"` for an enum of `none/low/high`, where Gemini
enforces the schema. Triage now asks for one word and parses text — a format a
small model can actually hit.

**The escalation ladder was walking every rung.** A case first seen six days out
fired the 14-day, then 7-day, then 2-day notice across three consecutive ticks —
three notices to one family for one deadline. Found by writing idempotency
tests, which forced the question of what "already sent" means.

**Every agent card published with exactly one scope.** A shell loop collapsed
`a,b,c` into a single YAML list item, so `coordinator` held one scope literally
named `case.read case.write worker.invoke`. It parsed, it published, and it
authorized nothing correctly.

## Accomplishments we're proud of

The measured results, all reproducible from the README:

| | |
|---|---|
| Benign corpus, 36 real skills | 36/36 approve, **zero findings** |
| Credential-exfil replica | REJECT — two reviewers, independently |
| Same replica, structural review only | **APPROVE** |
| Intake, legible consent dates | 12/12 exact |
| Intake, illegible dates | 2/2 correctly unsure |
| Tick idempotency, live on Cloud Run | 12 escalations → replay → still 12 |

That third row is the whole argument. Static analysis is *correct* that nothing
is structurally wrong with a skill that reads `~/.aws/credentials` and tells the
agent to hide it. It's ordinary English. That's what a model call is for.

## What we learned

**Fail closed, everywhere, and make the failure legible.** A reviewer that
errors downgrades the decision rather than approving — "we could not check" and
"we checked and it was fine" are different answers. A missing dependency in the
container surfaced as `memory write skipped: package required` rather than
silence, which is the only reason we found it.

**Classify by type, not by message.** Our transient-failure check substring
matched, and retried `ArmorUnavailable` — which means "no template configured" —
three times with backoff, because its class name contains "unavailable". Names
are not error semantics.

**Authorization isn't enough; shape the data.** `family-agent` doesn't receive
clinical fields and decline to use them. It never receives them. A check can be
forgotten at a new call site; a projection cannot leak a field it never
returned. Field classification fails closed, so a field added later is withheld
until someone classifies it.

**The most permissive policy sits on the least reviewed capability.** Read from
a shipping runtime's own source: a community skill with any finding is blocked,
while identical content the agent wrote for itself is allowed, with the gate off
by default. AgentX inverts that.

## What's next

Wire the gate into a live runtime's skill-load path rather than reviewing a
directory. Widen the benign corpus beyond one author. And have a district
compliance coordinator actually use it, which is the only test that counts.
