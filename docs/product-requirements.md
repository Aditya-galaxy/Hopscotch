# Hopscotch — product and system requirements

Status: **v0.1, demonstration.** Everything marked ✅ is built, deployed and
tested. Everything else is specification.

---

## 1. Problem

Federal law gives a district **60 calendar days** from parental consent to
complete a special education evaluation. Around twenty states override that with
their own count, and "school days" pause across district calendars.

The rule is widely broken, and the breakage is measured:

| | |
|---|---|
| New York City students not evaluated in time | **29.2%** ([NY comptroller](https://www.osc.ny.gov/state-agencies/audits/2019/05/16/compliance-special-education-requirements-evaluations)) |
| District-level compliance spread | **51%–86%** |
| Massachusetts complaints past the 60-day limit | **28%**, averaging **111 days** late ([MA audit](https://www.mass.gov/info-details/department-of-elementary-and-secondary-education-finding-3)) |
| Average pre-hearing settlement | **~$23,800** |
| Contested case exposure | **$80k–$120k** |
| One district, three years | **76 settlements, ~$6M** ([Inquirer](https://www.inquirer.com/education/special-education-programs-philadelphia-region-deficiencies-due-process-settlements-20250805.html)) |

Separately, districts may bill Medicaid for special education services delivered
to eligible students and **most underclaim by hundreds of thousands annually**.
Underclaiming compounds: cost settlement sets future reimbursement baselines.

**The pairing is the product.** Compliance is a painkiller but a cost centre, and
cost centres get cut. Claiming is what funds it.

## 2. Users

| Who | Needs | Cares about |
|---|---|---|
| **SPED compliance coordinator** *(primary)* | Know what needs them today, not what happened | Not missing a deadline; not being blamed |
| School psychologist | Draft notices without retyping case facts | Clinical accuracy; time |
| Family liaison | Reach families in their language | Being understood |
| Business officer | Recover claimable revenue | Audit safety over volume |
| District IT / counsel | Evidence agents cannot leak student data | Auditability; FERPA |

**Non-user:** families are affected but do not operate the system. Nothing is
sold to them and nothing collects data from them.

## 3. Principles

Derived from what building v0 actually taught, not aspiration.

1. **Fail closed, and say why.** An unavailable check downgrades a decision. "We
   could not check" and "we checked and it was fine" are different answers.
2. **Never let a model do arithmetic that carries legal weight.** Deadline maths
   is pure code. Models decide *when to escalate and to whom*.
3. **Shape data to identity, do not merely check permission.** A projection
   cannot leak a field it never returned; a check can be forgotten at a new call
   site.
4. **Report, do not submit.** Claim readiness says what would be denied. It never
   files. Over-claiming is recoupment.
5. **Claim once, ever.** Every side effect is idempotent by construction.
6. **A false positive costs more than it looks.** A tool that cries wolf gets
   switched off by the person it protects.

## 4. Scope

**In:** evaluation-timeline compliance; statutory notices; family communication;
claim readiness; the governance that permits all of it.

**Out, deliberately:** IEP authoring, scheduling, grading, attendance, HR,
anything a SIS already does. Hopscotch is not a system of record — it reads one
and acts on deadlines.

---

## 5. Functional requirements

### Case and clock
- **FR-1** ✅ Compute the statutory deadline under calendar-day, school-day and
  business-day rules, honouring the district calendar.
- **FR-2** ✅ Refuse to start a clock from an unknown consent date; route to a
  human instead.
- **FR-3** ✅ Escalate at T−14/T−7/T−2, firing the *tightest* applicable rung once
  and retiring looser ones.
- **FR-4** ✅ Run unattended on a schedule with no human trigger.
- **FR-5** Ingest consent documents from a live source (Drive, mail, scanner).
  *v0 measures extraction accuracy offline: 12/12 legible, 2/2 correctly unsure.*

### Notices
- **FR-6** ✅ Draft Prior Written Notice, evaluation plans and meeting agendas
  with statutory wording intact.
- **FR-7** ✅ Remove every clinical finding before any family-facing output, and
  refuse the handoff if redaction did not run.
- **FR-8** ✅ Produce the notice as speech in the family's language.
- **FR-9** Deliver notices (mail, SMS, parent portal). **Not implemented.**
- **FR-10** Record delivery and read receipts for the audit trail.

### Governance
- **FR-11** ✅ Publish versioned agent cards; a bump creates a row, not an
  overwrite.
- **FR-12** ✅ Allow discovery by department and by scope.
- **FR-13** ✅ Deny by default; an unregistered agent holds no scopes.
- **FR-14** ✅ Return only fields the caller's identity permits; unclassified
  fields are withheld.
- **FR-15** ✅ Screen every inbound document through inline guardrails.
- **FR-16** ✅ Review any skill before load — downloaded, cross-runtime, or
  self-authored — with self-authored held to the strictest tier.
- **FR-17** ✅ Emit reasoning-chain traces and an append-only audit log.
- **FR-18** Replace name-based authorization with attested identity.

### Claiming
- **FR-19** ✅ Assess claim readiness against eligibility, NPI, licence validity,
  provider type, IEP window, units-versus-minutes, and note presence.
- **FR-20** ✅ Check the session note is consistent with the authorized service.
- **FR-21** ✅ Block over-billing; flag under-billing as unclaimed revenue.
- **FR-22** Ingest service delivery logs at scale.
- **FR-23** Encode state plan billable-service rules per jurisdiction.
- **FR-24** Track random-moment time study participation.

### Coordinator surface
- **FR-25** ✅ Show caseload ordered by urgency, registry, audit trail, media.
- **FR-26** ✅ Produce a daily brief: headline, what needs a human, what moved
  overnight, what to watch.
- **FR-27** Accept coordinator corrections and adapt.
- **FR-28** Answer direct questions about a case.

---

## 6. Non-functional requirements

| | |
|---|---|
| **NFR-1** ✅ | Domain core testable with no cloud SDK. Full suite under 60s. |
| **NFR-2** ✅ | Idempotent under at-least-once scheduling and job retries. |
| **NFR-3** ✅ | Transient failures retry with jittered backoff; permanent failures classified by type, never by message. |
| **NFR-4** ✅ | Scales to zero between ticks. |
| **NFR-5** ✅ | Least-privilege runtime; no Editor role. |
| **NFR-6** ✅ | Every decision reconstructable from the audit trail. |
| **NFR-7** | FERPA review and a signed DPA before any real record. |
| **NFR-8** | Data residency configurable per district. |
| **NFR-9** | Human authentication and role model. |
| **NFR-10** | Multi-tenant isolation. |
| **NFR-11** | 600+ concurrent cases per district; ~13k districts. |

---

## 7. Phases

### Phase 0 — Demonstration ✅
Compliance fleet, governance plane, capability gate, claim readiness, all on
synthetic data. **Exit:** deployed, running unattended, measured results. *Done.*

### Phase 1 — One real district
The unglamorous 90%. FR-5, FR-9, FR-10, NFR-7, NFR-9.

Real ingestion, real delivery, real authentication, one district's actual
calendar and its state's real evaluation rules, FERPA review and a DPA.

**Exit:** one district runs it against live records for a full evaluation cycle
without a compliance incident.
**Risk:** legal review is the long pole and cannot be compressed by engineering.

### Phase 2 — Claiming for real
FR-22 to FR-24, plus submission.

Service delivery integration, eligibility feeds, live credentialing, state plan
rules for one or two states, RMTS tracking. Submission stays behind an explicit
human approval.

**Exit:** the pilot district's claimable revenue rises measurably against its own
prior-year baseline.
**Risk:** state plan variation. Two states is not a product; it is two projects.

### Phase 3 — Sellable
NFR-8, NFR-10, NFR-11, FR-18.

Multi-tenancy, attested identity, data residency, SIS integrations, and the
procurement artefacts districts require. Scale testing at realistic caseloads.

**Exit:** a district that has never spoken to us can buy and onboard.

### Phase 4 — Adjacent workflows
504 plans, Child Find, records requests, translation. Same shape: deadline-driven,
document-heavy, compliance-exposed. Each reuses the clock, the projections and
the audit trail.

**Exit:** second workflow sold into an existing district without new procurement.

---

## 8. Metrics

| Phase | Measure | Why |
|---|---|---|
| 0 | Benign-corpus false positives | A noisy gate gets disabled |
| 0 | Extraction accuracy *and calibration* | Confidently wrong is worse than accurately unsure |
| 1 | On-time evaluation rate, before vs after | The only compliance number that matters |
| 1 | Coordinator hours per case | If it does not give time back, it is not adopted |
| 2 | Claimable revenue vs prior-year baseline | The funding argument |
| 2 | Denials and recoupment | Must trend to zero; over-claiming is the failure mode |
| 3 | Time from first contact to running | Procurement friction is the real barrier |

**The metric that would kill it:** a deadline missed *because* the system was
trusted. One is unacceptable — coordinators must be able to see what it did and
why, which is what the audit trail and the daily brief exist for.

---

## 9. Open questions

1. **Who buys?** The coordinator feels the pain; a business officer or
   superintendent signs. The claiming ROI is the bridge — unproven.
2. **How much state variation is tolerable** before per-state rules become
   per-state products?
3. **Does the daily brief get read**, or does it become another ignored digest?
4. **Will districts accept agents near student records at all**, even governed?
   The whole thesis rests on yes, and it is untested.
5. **Is claim readiness enough**, or do districts want submission — with the
   liability that carries?

The step that answers most of these is not engineering: put Phase 0 in front of
a district compliance coordinator and watch which half they reach for.
