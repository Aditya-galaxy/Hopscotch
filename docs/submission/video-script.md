# Demo video — the 4:00 plan

**4:00 hard cap; only the first four minutes are judged. Public on YouTube, not
unlisted.** Narrate it live — an AI voiceover beats silence, but your own voice
beats both.

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
**Use the walkthrough, not the dashboard.** `localhost:8080/walkthrough` is
eight screens with one button each, following a single consent form all the way
through. It exists precisely so this minute is a story rather than a tour, and
every step performs the real action.

| Step | Screen | What you say |
|---|---|---|
| 0 | The form arrives | This is how work actually arrives — a scan, a photo. **This page has no model access at all.** It screens and parks; the fleet reads. |
| 1 | Screened first | Model Armor sees it before any extractor does. The screen is *in front of* the model. |
| 2 | The clock starts | Look where it counted from — the day the district **received** consent, not the day the parent signed. That's the statute. Already 14 days overdue. |
| 3 | It writes to the family | Escalated unattended. Three agents touched this letter and each was handed **less** than the last. |
| 4 | A person decides | Read the letter. Nothing names a diagnosis, because the agent that wrote it was never given one. Press **Approve**. |
| 5 | What the family receives | Their own page, their own child. Play the audio. A parent opening another child's case gets **404** — 403 would confirm the child exists. |
| 6 | The same session, as money | 25 assessed, 12 would be denied. One passes every rule and is still a denial, because the note says *group* and the IEP says *individual*. |
| 7 | What it refuses | File the poisoned form. It never reaches an extractor. |

### The timing problem, and how to handle it

**A tick takes 157–190 seconds.** Measured across four executions, not
estimated. Steps 1 and 2 each trigger one, so running the walkthrough live end
to end costs about six minutes — more than the whole video.

So: **do a complete dry run before you record.** Click all eight steps, let both
ticks finish, and leave the case in place. Then record a second pass, where
every screen already has its data and renders instantly. On the two "Run the
fleet" clicks, cut — and cut *to the Cloud Run executions tab*, which is where
requirement 4 gets paid anyway. The execution you are pointing at is the one
your click just started.

Do not try to fill three minutes of dead air by talking. Cut.

## 2:25 – 3:15 · Running on Google Cloud
The explicit block. Move briskly; four tabs, roughly twelve seconds each.

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
