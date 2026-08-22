# AgentX

**A fleet of agents that keeps a school district inside the legal clock on
special education evaluations.**

Federal law gives a district 60 calendar days from parental consent to complete
an initial evaluation. Roughly twenty states override that with their own count
— 45 school days, 30 business days — and "school days" pause across every break
on that district's calendar. Miss the deadline and the district owes
compensatory services and is exposed to a due process complaint.

The person holding that clock is usually one special education coordinator,
tracking two to six hundred active files across a dozen schools, in a
spreadsheet and an inbox.

Built for the All Things Agentic Hackathon — **Fortified Enterprise Fleet**.

---

## Why a fleet and not one agent

The work crosses four departments with genuinely different legal access rights.
A school psychologist's clinical findings are data a front-office aide is not
permitted to read. The privilege boundary is not architecture invented to
satisfy a rubric — it is the reason per-agent identity and gateway policy have
to exist here.

| Agent | Department identity | Sees |
|---|---|---|
| `coordinator` | SPED admin, elevated | Routes, validates, owns failure paths |
| `intake-agent` | Front office | Raw inbound documents, no clinical fields |
| `clock-agent` | SPED admin | Dates and jurisdiction only |
| `casework-agent` | School psychology | Full case — and the *narrowest* tool allowlist |
| `family-agent` | Family liaison | Redacted view only |

Note the inversion: `casework-agent` holds the most sensitive data and gets the
fewest tools. `family-agent` reaches the outside world and never sees clinical
text at all — Gemma strips it before the handoff, and the handoff fails closed
if redaction did not run.

## Architecture

| Track requirement | Product | Where |
|---|---|---|
| Agent Registry | Agent Registry | `registry/*.agent.yaml` |
| Agent Runtime | Agent Engine Runtime | `src/agentx/agents/` |
| Memory Bank | `VertexAiMemoryBankService` | *day 5* |
| Agent Identity | Agent Identity (SPIFFE) | `registry/*.agent.yaml` → `spec.identity` |
| Agent Gateway | Agent Gateway | `registry/*.agent.yaml` → `spec.gateway` |
| Model Armor | Model Armor | `src/agentx/guardrails.py` |
| Observability | OTel → Cloud Trace | `src/agentx/telemetry.py` |
| Infra | Scheduler · Pub/Sub · Cloud Run Jobs · Firestore | `src/agentx/jobs/tick.py` |

**Models.** `gemini-3.5-flash` for all workers. `gemini-3.5-pro` in the
supervisor, adjudication only. Gemma for on-path clinical redaction. Chirp and
Veo for the family-facing packet.

## The capability gate

Agents gain capability through [Agent Skills](https://agentskills.io) — a folder
with a `SKILL.md`, an open format originally released by Anthropic and now read
by roughly 45 runtimes. Skills are portable across runtimes by design.
Provenance is not.

Every skill passes one door before Registry signs it and Gateway will load it —
downloaded, imported from another runtime, or written by the agent for itself.

**Two properties are load-bearing:**

*Fail closed.* A reviewer that errors or is not yet wired does not become an
approval. "We could not check" and "we checked and it was fine" are different
answers, and only one is safe to conflate with yes.

*Self-authored capability is the strictest tier, not the loosest.* Shipping
runtimes invert this. Read from Hermes Agent's own `tools/skills_guard.py`, a
**community** skill with any finding is blocked, while the identical content
written by the agent itself is allowed — `agent-created` maps to
`(allow, allow, ask)`, and their comment notes the gate *"only runs when
`skills.guard_agent_created` is enabled — off by default."* Their external
scanning is genuinely good; this is a default, not a flaw. But a community
skill at least had a human author who could be named. A self-authored one may
encode a web page the model read ten minutes earlier, reviewed by nobody.

### Why a model call, and not a bigger rule list

```
$ python -m agentx.skills.cli data/replicas/credential-helper --structural-only
APPROVE   credential-helper                ecfc13fcf54e
          origin=community; verdict=safe
```

That skill instructs the agent to read `~/.aws/credentials`, attach them to an
outbound header, and omit both steps from its summary. It has no shell, no
binary, and no regex-matchable signature — static analysis is *correct* that
nothing is structurally wrong. It is ordinary English, which is precisely what
pattern matching cannot read and what the intent reviewer exists for.

Meanwhile all 36 skills in the real benign corpus pass clean. A gate with false
positives gets disabled by the people it was built to help.

```bash
make corpora
make scan SKILL=data/corpora/mattpocock-skills ARGS="--all --structural-only"
```

### Reviewing hostile text without being hostile-texted

The intent reviewer feeds untrusted instructions to a model, which is the exact
attack it exists to detect. Three mitigations, all tested:

- **Nonce fencing.** Content sits between `--- BEGIN SKILL-<random> ---` markers
  regenerated per call, so a skill cannot close the fence and escape the quotes.
- **Schema-constrained output.** `response_schema` means a successful injection
  still cannot produce free text — only findings in the declared shape.
- **Fail closed.** Unparseable output raises rather than returning "clean", and
  the gate downgrades any decision whose reviewers could not run.

Runs against either backend. Local prototyping needs no billing account:

```bash
export GOOGLE_GENAI_USE_VERTEXAI=false
export GEMINI_API_KEY=...        # free at https://aistudio.google.com/apikey
make scan SKILL=data/replicas/credential-helper
```

## Idempotency

The tick runs hourly and unattended — roughly 240 executions across the build.
Cloud Scheduler is at-least-once and Cloud Run Jobs retry, so "this ran twice"
is a certainty, not a risk.

The naive fix — refusing to re-run — is wrong: a tick that failed halfway must
be safe to retry or a transient Firestore blip strands a case. So the guarantee
is **per-effect, not per-run**. Every side effect derives a deterministic id
from what it *is*, claims it once against a ledger backed by Firestore document
uniqueness, and is a no-op forever after. The claim happens *before* the effect:
a crash in between costs one missed notice that the coordinator sees in the
dashboard, where the reverse would spam a family on every tick for the life of
the case.

Two scopes, deliberately different:

- **Escalations** are claimed once *ever* per student and rung — a T-7 warning
  is a thing that happens one time in a case's life, not once per tick.
- **Dead letters** are claimed per run, so a case that keeps failing keeps
  surfacing to the human queue.

Firing a tight rung also retires every looser one. A case first noticed at T-1
gets the two-day notice only — never 14, then 7, then 2 across three
consecutive ticks.

## Failure tolerance

`src/agentx/supervisor/resilience.py`, four layers in order:

1. **Schema validation** — a worker returning the wrong *shape* is caught
   before anything downstream acts on it.
2. **Bounded retry** — one reformulated attempt. The worker receives the
   attempt number so it can tighten its own prompt rather than replaying the
   call that just failed.
3. **Circuit breaker** — an agent that fails repeatedly stops being called.
4. **Dead letter** — unfinished work lands in a human queue, visibly.

## Run it

```bash
make install
make test        # deadline engine + idempotency, no cloud SDKs needed
make corpus      # 40 synthetic cases
cp .env.example .env   # fill in GOOGLE_CLOUD_PROJECT
make probe       # day-1 provisioning probe
make tick        # one tick against Firestore
```

## Deploy

```bash
gcloud run jobs deploy agentx-tick \
  --source . --region "$GOOGLE_CLOUD_LOCATION" \
  --max-retries 1 --task-timeout 10m
gcloud scheduler jobs create pubsub agentx-daily \
  --schedule "0 7 * * *" --topic agentx-tick --message-body "tick"
```

Cloud Run Jobs scale to zero between ticks. Authenticate every endpoint you
expose — an open URL drains credits, and an unauthenticated endpoint on a
zero-trust project is the kind of thing a reviewer notices.

## Data and legal disclosure

**All data in this repository is synthetic.** No real student record was used.
`scripts/generate_corpus.py` produces the corpus and ships an answer key for
scoring extraction accuracy.

**The jurisdiction table in `src/agentx/jurisdictions.py` is illustrative.**
The federal 60-calendar-day baseline is well established; the state overrides
are simplified stand-ins chosen to exercise all three counting rules. Verify
every entry against current state regulation before this touches a real case.
This system assists a coordinator. It does not replace one, and it does not
give legal advice.

## Status

Scaffold. `NotImplementedError` and `TODO(day-N)` mark what is wired next; the
build plan drives the order. Nothing here silently pretends to work: the
Model Armor stub raises rather than passing text through, and the redaction
gate refuses the handoff rather than leaking.
