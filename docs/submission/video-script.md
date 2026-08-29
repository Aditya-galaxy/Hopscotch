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
2. **The app** — http://localhost:8080/app
3. **Cloud Run job executions** —
   `console.cloud.google.com/run/jobs/details/us-central1/agentx-tick/executions?project=kronagent`
4. **Cloud Scheduler** — `console.cloud.google.com/cloudscheduler?project=kronagent`
5. **Logs Explorer**, pre-run this query so results are on screen:
   ```
   resource.labels.job_name="agentx-tick" AND textPayload:"aiplatform.googleapis.com"
   ```
6. **Cloud Trace** — `console.cloud.google.com/traces/list?project=kronagent`
7. **Firestore data** —
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
**Switch to `localhost:8080/app`.** Point at the brief: the supervisor wrote it
this morning, unprompted.

| Beat | On screen | Seconds |
|---|---|---|
| Paste the consent form into the drop box | row appears as `pending` | 15 |
| Say: this page has **no model access** — it screens and parks; the fleet reads | — | 10 |
| **Press "Run a tick now"** | redirect, "Tick started" | 5 |
| **Cut to Cloud Run executions, hit refresh** | a new execution, running | 20 |
| Back to the app, open the case | deadline computed **from the receipt date** | 20 |
| Press the tick once more | `escalated: 1, notices_sent: 1` | 10 |
| Outbox | notice waiting for a named human | 10 |

Two lines worth saying while this runs:

- The clock starts from the day the district **received** consent, not the day
  the parent signed. That is the statute, and the case page says which date it
  used and why.
- Intake runs at the end of a tick, so the new case is picked up on the next
  one. It runs hourly anyway.

**Then the poisoned document** — paste it, tick, and let this land:

```
intake blocked: Model Armor blocked upload: pi_and_jailbreak@MEDIUM_AND_ABOVE
```

It was refused **before any extractor saw it**. The screen sits in front of the
model, not after, so it never got the chance to be persuaded.

## 2:25 – 3:15 · Running on Google Cloud
The explicit block. Move briskly; four tabs, roughly twelve seconds each.

1. **Cloud Run job executions** — 208 executions, hourly, unbroken since
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

## 3:15 – 3:50 · Why it is allowed near the records
**On screen:** the case page, scrolled to *What this identity may see*.

Every agent reads through one gateway, and it shapes the record to whoever is
asking. The family-facing agent does not receive clinical fields and decline to
use them — it never receives them. Fields above the ceiling are **absent**, not
blanked, so a page that never had them cannot leak them.

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
