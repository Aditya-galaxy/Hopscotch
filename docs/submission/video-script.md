# Demo video — the 4:00 plan

**4:00 hard cap. Public on YouTube, not unlisted.**

**The judging criteria ask for a "live, unedited demo" — 30% of the score.** No
cuts, no splices, no sped-up sections. This document is built around a single
continuous take; the trick that makes it possible is triggering the Cloud Run
job at 0:55 and returning to it at 2:25, so the wait happens underneath the
demo instead of interrupting it.

This document is the shot plan and the timing budget.
[narration.md](narration.md) is the companion: the words, in your voice, not to
be read aloud verbatim.

## The four things that must be in it

| # | Required | Where it lands | Cuttable? |
|---|---|---|---|
| 1 | The problem | 0:00–0:30 | No |
| 2 | Value proposition | 0:30–0:55 | No |
| 3 | The app in action | 0:55–2:25 | No |
| 4 | **Backend running on Google Cloud** | woven throughout + 2:25–3:15 | **No** |

Requirement 4 is the one demos usually fail, by parking a console montage at
3:40 where it reads as an afterthought and gets cut when the take runs long.
**Here it is load-bearing instead:** the `.run.app` URL is in the address bar
from the first second, and at 1:55 you press a button in the app that *causes* a
Cloud Run Job execution you then watch appear in the console. That is not a tour
of a dashboard — it is the backend doing work on camera.

---

## Before you record

```bash
cd ~/Agent/hopscotch && ./scripts/demo.sh --tabs
```

That preflights, prints a fresh consent form with dates that make the case
overdue, opens every console tab below, and serves the app locally.

**Record against the deployed URL for everything except the write steps.** The
public site is read-only by design, so the drop box does not render there; the
local instance is for the paste-and-tick sequence. Both look identical, so cut
between them freely — but say once, out loud, that writes need authentication
and the public demo refuses them. That is a feature, and judges notice it.

### Tabs, in this order

1. **The product** — https://agentx-dashboard-dijsyl2kwq-uc.a.run.app
2. **The walkthrough** — http://localhost:8080/walkthrough  *(the spine of the demo)*
3. **The dashboard** — http://localhost:8080/app
   *(the identity switcher sits at the very top of every staff page)*
4. **Cloud Run job executions** —
   `console.cloud.google.com/run/jobs/details/us-central1/agentx-tick/executions?project=kronagent`
5. **Cloud Scheduler** — `console.cloud.google.com/cloudscheduler?project=kronagent`
6. **Logs Explorer**, pre-run this query so results are on screen:
   ```
   resource.labels.job_name="agentx-tick" AND textPayload:"aiplatform.googleapis.com"
   ```
7. **Cloud Trace** — `console.cloud.google.com/traces/list?project=kronagent`
8. **Firestore data** —
   `console.cloud.google.com/firestore/databases/-default-/data?project=kronagent`

### Two warnings

- **Check the console account first.** The CLI here is authenticated as
  `brightflame.team@gmail.com`, and Model Armor read is **denied** for that
  identity. Model Armor works at runtime — the tick job's own service account
  has the permission and you will see it block a document — but do not plan to
  film the Model Armor console page without opening it first. If it errors,
  show the blocked log line instead; it is better evidence anyway.
- **Your email is on screen** in the console avatar, top right, on every tab.

---

## 0:00 – 0:30 · The problem
**On screen:** the landing page, deployed. Let the 60-tick clock finish its fill.
Make sure the `.run.app` URL is legible in the address bar — requirement 4
starts here, silently.

Sixty days from a parent's signature to complete a special education evaluation.
Miss it and the district owes compensatory services and faces a due process
complaint. The person holding that clock is one coordinator with a spreadsheet
and no compliance team.

> Say **"Gemini 3.5 Flash, built on Google ADK"** out loud before 0:30. Judges
> are told they should not have to hunt for it.

## 0:30 – 0:55 · Value proposition
**On screen:** scroll to *"Compliance is a cost centre. Cost centres get cut."*
and the two halves.

Compliance alone is a cost centre, and cost centres get cut. Districts can bill
Medicaid for the very services these deadlines govern, and most underclaim
badly — one New York City audit found $431.6 million unclaimed. Same records,
same student, second question. **Compliance stops the lawsuits; claiming is what
pays for it.** That pairing is the product.

## 0:55 – 2:25 · The app in action

> **The rules say: "We want a live, unedited demo."** That is 30% of the score,
> and it kills the earlier plan in this document, which told you to cut during
> the tick. There are no cuts now. The whole take is continuous.

**Two facts make an unedited take possible.** A tick takes 157–190 seconds, so
you cannot wait for one on camera. But the **guided walkthrough renders every
screen instantly** from records the fleet has already worked — and the tick you
trigger runs in the background while you keep talking.

So the shape is: **start the job early, narrate over it, come back to it.**

### The one continuous take

| Time | Do this | Say this |
|---|---|---|
| 0:55 | On the dashboard, press **Run a tick now** | "That just asked a Cloud Run job to start. It takes about three minutes — we'll come back to it." |
| 1:00 | Go to `/walkthrough`, click through steps 1–4 | The form arrives · screened before anything reads it · the clock starts from **receipt** · overdue, so it wrote to the family |
| 1:45 | Step 5 — the fleet | Five agents, and the gateway hands each a different shape of the record. casework gets 9 fields, family-agent gets 4 and no consent block at all |
| 2:00 | Steps 6–7 | A person releases the letter. The family sees their own child and nothing else — another child returns **404**, not 403 |
| 2:15 | Steps 8–9 | This session as a claim line, nine checks; then the district view, where 12 of 26 would be denied |

Nothing above waits on anything. Every screen is served from Firestore in
milliseconds.

### If you want the write path on camera as well

Do it on the **local** instance, where the buttons act instead of narrate — but
only the fast ones. Filing a document and approving a notice are instant. Do
**not** press "Run the fleet" and wait; that is what the background job at 0:55
is for.

## 2:25 – 3:15 · Running on Google Cloud
**Now go back to the job you started at 0:55.** It has had two and a half
minutes and will have finished. This is the strongest thing in the video: an
execution the judge watched you trigger, completing on Google Cloud, in one
unbroken take.

Then move briskly; four tabs, roughly twelve seconds each.

1. **Cloud Run job executions** — 235+ executions, hourly, unbroken since
   22 August. Nobody watching. *This is the single most convincing frame in the
   video; give it the longest beat.*
2. **Cloud Scheduler** — `agentx-hourly`, `0 * * * *`, **ENABLED**, last run
   on the hour.
3. **Logs Explorer** — the `aiplatform.googleapis.com` POST lines. These are the
   live Vertex AI calls: Gemini 3.5 Flash doing the work, from inside the job.
4. **Cloud Trace** — spans for `job.tick` and `supervisor.call_worker`.
   *Optional:* **Firestore** — the `cases`, `inbox`, `outbox`, `audit`
   collections holding the state you just watched change.

Close the block on the deployed `.run.app` tab so the URL is the last thing on
screen.

## 3:15 – 3:50 · Every side of one record
**On screen:** the identity switcher at the top of the dashboard. This is the
strongest thirty seconds in the video after the blocked document — the whole
governance thesis, shown rather than described.

Click along the row and let each land for four or five seconds:

| Identity | What changes on screen |
|---|---|
| **SPED coordinator** | the whole caseload, the outbox, the audit trail |
| **School psychologist** | clinical detail, but no outbox and no audit trail |
| **Family liaison** | redacted view; the audit trail names students, so it is withheld |
| **Business office** | claim readiness in full — and *"the caseload is not visible to your role; it requires `case.read`"* |
| **Parent** | a different surface entirely: one child, the deadline in plain words, the letters actually sent |

> Same records. Different identity. The gateway decides what each one is handed
> — and it is the *same* scope table the agents go through.

**The beat worth staging:** from the coordinator's outbox, press **Approve**,
then click **"View as this family"** on that same row. Before approval the
parent's page says nothing has been sent. After it, the letter is there, in
plain language, with audio, marked *released by* a named person. One action,
both sides.

A parent cannot open another child's case — that returns **404**, not 403,
because 403 would confirm the student exists.

If time allows, the capability gate — a skill file that reads AWS credentials,
hides the fact, and passes every structural check:

```bash
make scan SKILL=data/replicas/credential-helper ARGS=--structural-only   # APPROVE
```

Then the full gate catches it, and **36 of 36** real skills pass clean. A gate
with false positives gets switched off by the person it protects.

## 3:50 – 4:00 · Close
Back to the landing page.

161 tests, none of which need a cloud account. Every record synthetic. That
coordinator is never getting a compliance team — so, this.

---

## If you run long

Cut in this order, and stop at three:

1. Firestore tab (step 4 above, the optional half)
2. The capability-gate scan at 3:15 — say "36 out of 36" over the case page
3. Cloud Trace
4. The second tick — pre-stage the overdue case before recording and narrate it

**Never cut:** the button-press that creates a Cloud Run execution, the
executions list, the Scheduler showing ENABLED, or the blocked document. Those
are requirement 4 and the differentiator, in that order.

## If something fails live

| Fails | Do this instead |
|---|---|
| Tick is slow to appear | Keep talking; refresh once. Executions take ~5s to register |
| Model Armor console errors | Show the blocked log line — stronger evidence anyway |
| A model call times out | Say so, and point at the fail-closed design: an unavailable reviewer downgrades rather than approves |
| Paste lands on an existing case | Use one of the spare consent forms — the doc id is a hash of the text |

## Delivery

- Contractions, every time. Trailing off is fine; polish reads as rehearsed.
- Terminal at 18pt minimum, browser zoom 125–150%. The screen is 2560×1600 and
  YouTube will downscale to 1080p — untreated, the terminal becomes mush.
- Do Not Disturb **on**. A notification banner means re-recording.
- The `APPROVE` on the credential skill works best if you sound a little amused.
- Keep the line about having had the statute wrong until two days ago. Judges
  trust someone who corrects themselves.

---

## Required deliverables — checked against the rules page

| Required | Status |
|---|---|
| Category | Fortified Enterprise Fleet |
| Hosted project URL | `https://agentx-dashboard-dijsyl2kwq-uc.a.run.app` — live, no credentials |
| Text description | `docs/submission/devpost.md` — features, technologies, data sources, findings |
| Code repository | github.com/Aditya-galaxy/Hopscotch |
| Spin-up instructions in README | "Quick start" section — `make install`, `make test`, `./scripts/demo.sh` |
| **Architecture diagram** | `docs/diagrams/01-system-overview.png` — shows frontend, backend, database, and where Gemini sits |
| ~4-min demo video | **the only outstanding item** |

**Repository access, if it stays private.** The rules say share it with
`testing@devpost.com` *and* `cloudhackathons@google.com`. `devposttesting` has
accepted; **`googlecloudhackathons` is still pending** — if they do not accept
before the deadline, Google's judges cannot open the repo, the hosted URL, or
anything the video points at. Flipping the repo public removes that risk
entirely and is the safer move.

**Deadline: 31 August 2026, 5:00pm PDT.**

