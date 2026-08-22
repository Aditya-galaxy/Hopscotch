# AgentX

**An always-on agent fleet that runs a school district's special education
compliance office — and the governance that makes a district allowed to run it.**

Built for the All Things Agentic Hackathon · **Fortified Enterprise Fleet**.

---

## The problem

Federal law gives a district **60 calendar days** from parental consent to
complete a special education evaluation. Roughly twenty states override that
with their own count — 45 school days, 30 business days — and school days pause
across every break on that district's calendar. Miss the deadline and the
district owes compensatory services and faces a due process complaint.

The person holding that clock is usually **one coordinator** tracking two to six
hundred active files across a dozen schools, in a spreadsheet and an inbox.
Consent forms arrive as phone photos. Evaluations come back as unlabeled PDFs.
Every step triggers a legally required parent notice in the family's home
language.

That coordinator needs an autonomous agent more than any executive does. They
will never get one, because the data is minors' clinical records and the
district has no security team.

**AgentX is both halves.**

---

## What it actually does

Every hour, unattended, with nobody watching:

- recomputes every open case's statutory deadline under its own jurisdiction's
  counting rule and the district's school calendar
- escalates at T−14, T−7, T−2 — **once each, ever**, even across ~240 replays
- extracts structure from deliberately messy intake documents, and **refuses to
  guess** when a signature date is illegible
- screens every inbound document through Model Armor before a model reads it
- reviews any new capability an agent tries to load, before it can load it

A person only sees what it could not clear.

---

## Quick start

Nothing below needs cloud credentials.

```bash
make install          # venv + dependencies
make test             # 44 tests, ~1s
make corpora          # fetch the benign skill corpus
make scan SKILL=data/replicas/credential-helper ARGS=--structural-only
```

That last command prints `APPROVE` — for a skill that harvests AWS and GitHub
credentials into an outbound header and tells the agent to hide it. Static
analysis is *correct* that nothing is structurally wrong; it is plain English
with no signature. That is the entire argument for spending a model call.

### With credentials

```bash
cp .env.example .env          # fill GOOGLE_CLOUD_PROJECT
./deploy/probe.sh             # check all seven components before building
./deploy/day1.sh              # project, APIs, budget, Firestore, Model Armor,
                              # least-privilege SA, Cloud Run Job, hourly schedule
make corpus && python scripts/seed_firestore.py
make scan SKILL=data/replicas/credential-helper     # full four-reviewer gate
python scripts/eval_intake.py -n 14                 # extraction accuracy
```

Prototyping needs no billing account — set `GOOGLE_GENAI_USE_VERTEXAI=false`
and a free key from [aistudio.google.com/apikey](https://aistudio.google.com/apikey).

---

## Architecture

Full diagrams, trust boundaries, and the tick sequence:
**[docs/architecture.md](docs/architecture.md)**

| Track requirement | Product | Where |
|---|---|---|
| Agent Registry | Agent Registry | `registry/*.agent.yaml` |
| Agent Runtime | Agent Engine Runtime | `src/agentx/agents/`, `adk_runner.py` |
| Memory Bank | `VertexAiMemoryBankService` | ADK 2.7.1 |
| Agent Identity | Agent Identity (SPIFFE) | `registry/*.agent.yaml` → `spec.identity` |
| Agent Gateway | Agent Gateway | `registry/*.agent.yaml` → `spec.gateway` |
| Model Armor | Model Armor | `src/agentx/armor.py` |
| Observability | OTel → Cloud Trace | `src/agentx/telemetry.py` |
| Infra | Scheduler · Pub/Sub · Cloud Run Jobs · Firestore | `src/agentx/jobs/tick.py` |

**Models.** `gemini-3.5-flash` for workers, `gemini-3.5-pro` in the supervisor
for adjudication only, `gemma-4-26b-a4b-it-maas` for skill triage and clinical
redaction. **Framework:** Google ADK 2.7.1.

---

## The capability gate

Agents gain capability through [Agent Skills](https://agentskills.io), an open
`SKILL.md` format read by ~45 runtimes. Portable by design; provenance absent.

Four reviewers, and they are not redundant:

| Reviewer | Runs on | Catches |
|---|---|---|
| `structural` | local, free | padding, binaries, symlinks, oversized packages |
| `triage` | Gemma | coarse risk band; keeps junk from paid calls |
| `intent` | Gemini 3.5 Flash | what the text *instructs* vs what it claims |
| `injection` | Model Armor | prompt injection, jailbreak framing, malicious URIs |

Model Armor flags `"Ignore previous instructions…"` at HIGH confidence and does
**not** flag the credential replica — that skill never addresses the reading
agent, it just politely instructs harvesting. Intent catches that. Armor
catches what intent might rationalise. Dropping either leaves a hole.

**Self-authored skills are the strictest tier, not the loosest** — see
[the policy table](docs/architecture.md#trust-policy-and-why-it-is-inverted)
for why that inverts what shipping runtimes do.

**Fail closed.** A reviewer that errors or is unwired downgrades the decision.
"We could not check" and "we checked and it was fine" are different answers.

---

## Results

| What | Result |
|---|---|
| Benign corpus (36 real skills) | 36/36 approve, zero findings |
| Credential-exfil replica | REJECT — two reviewers, independently |
| Same replica, structural only | APPROVE — why intent earns its call |
| Intake, legible dates | 12/12 exact |
| Intake, illegible dates | 2/2 correctly unsure |
| Tick idempotency, live on Cloud Run | 12 escalations → replay → still 12 |

---

## Disclosures

**All data is synthetic.** No real student record was used.
`scripts/generate_corpus.py` produces the corpus and ships an answer key.

**The jurisdiction table is illustrative.** The federal 60-calendar-day baseline
is well established; the state variants in `src/agentx/jurisdictions.py` are
simplified stand-ins chosen to exercise all three counting rules. Verify against
current state regulation before this touches a real case. This system assists a
coordinator. It does not replace one and it does not give legal advice.

**Attack replicas are inert.** `data/replicas/` contains hand-authored
reproductions of published attack *patterns* — no live malware, nothing
executable, no downloaded payloads.

**Third-party characterisations are sourced.** Statements about Hermes Agent's
install policy are read from its published source and linked in
[docs/architecture.md](docs/architecture.md).
