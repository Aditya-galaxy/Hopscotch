# Narration — talking points, not a teleprompter

*Project: **Hopscotch**. The deployed Cloud Run job is still `agentx-tick` — say
so in passing when it appears on screen; it reads as history rather than a
mistake, and quietly proves it has been running a while.*

**Don't read this word for word.** Read it twice, then close it and talk. If you
sound like you're reading, judges hear a script; if you sound like you're
showing a friend something you built, they lean in.

Roughly 450 words across 4:00, which leaves about 80 seconds where you're just
quiet and stuff runs. Let it be quiet. Watching a real job execute is more
convincing than anything you can say over it.

**Say "Gemini 3.5 Flash, built on Google ADK" out loud before 0:30.** Judges are
told they shouldn't have to hunt for it.

---

## Before you record

The public URL is **read-only by design** — writes need authentication, so the
forms don't render there. Record against a local instance:

```bash
cd ~/Agent/hopscotch && clear
export GOOGLE_CLOUD_PROJECT=kronagent REQUIRE_AUTH=false DEMO_ALLOW_WRITES=true
PYTHONPATH=src .venv/bin/uvicorn hopscotch.dashboard.app:app --port 8080
```

Have a consent form on your clipboard, ready to paste. The receipt date is
deliberately ~70 days back, so the case opens **already overdue** and the tick
has something real to do.

**Use a different one for each take.** The document id is a hash of the text, so
re-pasting identical wording lands on the same case — which has already had its
notices sent, so the escalation beat won't fire twice. Change the name and the
dates and you get a clean case. Three ready to go (the first is already used up):

```
~~Student: Maya Chen. Received 2026-06-20.~~   ← spent, don't reuse

Consent for initial evaluation. Parent signature dated 2026-06-11.
Received by Roosevelt Elementary front office on 2026-06-17.
Student: Daniel Ortiz. Concern: articulation and expressive language.

Consent for initial evaluation. Parent signature dated 2026-06-09.
Received by Roosevelt Elementary front office on 2026-06-16.
Student: Priya Raman. Concern: expressive language delay.
```

Check the receipt date is more than 60 days before the day you record, or the
case won't be overdue and there is nothing to escalate.

Tabs open and pre-loaded so nothing spins during the take:
1. the local dashboard — http://localhost:8080
2. Cloud Run jobs → `agentx-tick` → executions
3. Cloud Trace → trace list

---

### 0:00 – 0:25 · Start with the person
*Dashboard on screen. Don't touch anything yet.*

> Okay so — this is basically a list a school district keeps. Every single row
> has a legal deadline attached.
>
> Sixty days from when a parent signs a consent form. Miss it, the district can
> get sued, and the kid waits another year for help they should've already had.
>
> And it's usually just... one person doing this. There's no compliance team.
> That's the whole job.

---

### 0:25 – 0:45 · What this is
*Point at the brief at the top.*

> Honestly they probably need an AI agent more than anybody. And they're never
> going to get one — because that list is full of kids' medical records and the
> district has zero security people.
>
> So that's what I built. The agents that do the work, and the guardrails that
> make it okay to point them at real records. **Gemini 3.5 Flash, on Google
> ADK.**
>
> Other half: districts can bill Medicaid for these exact services and most
> massively underclaim. Compliance stops the lawsuits, billing pays for it.
>
> Oh and — this summary up top? The supervisor wrote it this morning. Nobody
> asked it to.

---

### 0:45 – 1:50 · The whole loop, caused by you
*This is the minute that matters. Paste the form. Then mostly stop talking.*

> Here's a consent form. Came in however they come in — photo, forwarded email,
> whatever.

*Paste into the drop box. Submit. It appears as `pending`.*

> The dashboard can't read it. It has no model access at all — that's on
> purpose. It just parks it and the fleet picks it up.

*`gcloud run jobs execute agentx-tick --region=us-central1 --wait`*

> Nothing triggers this normally. Every hour it just goes.
>
> — job's still called agentx, by the way. Renamed the project after this had
> been running for days, didn't want to lose the history.

*Log line lands: `documents_read: 1`*

> So it read the form and opened a case. And look at the date it started the
> clock from — not the signature. The day the district **received** it.
>
> That's the actual statute, and I had it wrong until two days ago. A form
> signed on the first and delivered on the tenth is due sixty days from the
> tenth.

*Click into the case. Point at the explanation line. `10d overdue`.*

> It says which date it used and why. And this kid's already ten days over.

*Run the tick again. Don't explain why — just run it.*

> Intake happens at the end of a run, so the new case gets picked up on the
> next one. Which is fine — it runs every hour anyway.

*`escalated: 1, notices_sent: 1`*

> There. Escalated, and it drafted the legal notice. All three rungs at once,
> because the case showed up already past every one of them.

*Back to the outbox.*

> And it's sitting right there waiting for a person. Nothing reaches a family
> until somebody with a name approves it.

---

### 1:50 – 2:20 · Now the poisoned one
*Paste the second document. This is the strongest thirty seconds — don't rush it.*

> Same box. But this one's got instructions buried in it — set every deadline to
> 2099, mark everything compliant, mail the roster somewhere.

*Run the tick.*

*`intake blocked: Model Armor blocked upload: pi_and_jailbreak@MEDIUM_AND_ABOVE`*

> Blocked. And the bit I care about — that happened *before* any model read it.
> The screen is in front of the extractor, not after. It never got a chance to
> be persuaded.

---

### 2:20 – 2:50 · The skill one
*Run structural-only. Let `APPROVE` sit there a beat.*

> Agents pick up new abilities as skill files. Open format, about forty-five
> tools read them.
>
> This one reads your AWS credentials, puts them in an outgoing request, and
> tells the agent not to mention it.

*`make scan SKILL=data/replicas/credential-helper ARGS=--structural-only`*

> ...and the scanner says fine. Which — fair. There's no code in that file.
> Nothing to pattern-match. It's just English, asking nicely.

*Run the full gate.* → Four reviewers. Two catch it independently.

*`make scan SKILL=data/corpora/mattpocock-skills ARGS="--all --structural-only"`*

> Thirty-six real skills people use every day. Zero false positives. Because if
> this thing cried wolf, the first person it annoyed would switch it off.

---

### 2:50 – 3:10 · The money side
*Optional — cut this first if you are running long.*

> Same idea, and it's the half that pays for the other half. Twenty-five
> sessions assessed, twelve would've been denied.
>
> This one's eligible, licensed, right provider, right units. Every rule passes.
> Still a denial — the note describes a group session and the IEP says
> individual. No rule catches that.
>
> Other direction too. Over-bill and it blocks; under-bill and it tells you
> that's money you left behind.

---

### 3:10 – 3:30 · The boundary
*Case page, scroll to the bottom table.*

> Every agent goes through one gateway, and it shapes the record to whoever's
> asking. This is what the family liaison actually gets handed.
>
> The clinical fields aren't blanked — they're *absent*. It isn't choosing not
> to look. It never gets given any.

*Play two seconds of the Spanish audio.*

---

### 3:30 – 3:50 · It's really running
*Mostly just click. Barely narrate.*

> Hundred and ninety-three runs since the twenty-second. Nobody watching it.

*Executions list → audit trail, unbroken every day → Cloud Scheduler, enabled →
Cloud Trace.*

> Audit log's append-only. Every row written by an agent, none of them can be
> overwritten.

---

### 3:50 – 4:00 · Wrap
*Back to the dashboard.*

> Hundred and sixty-one tests, no cloud account needed for any of them.
>
> That coordinator's never getting a compliance team. So — this.

---

## If you run long

Cut in this order. Don't go past three:

1. The Spanish audio — 4 seconds
2. A couple of the Cloud Console tabs
3. The claims section entirely — say "it does the billing side too" and move on
4. The benign corpus run — just say "thirty-six out of thirty-six"

**Don't cut** the intake loop at 0:45, the blocked poisoned document, or the
`APPROVE` on the credential skill. Those three are the demo. Everything else is
decoration.

## Delivery

- Contractions. Every time.
- It's fine to trail off or say "um" — polish reads as rehearsed.
- The `APPROVE` moment works best if you sound a bit amused by it.
- The "I had it wrong until two days ago" line is worth keeping. Judges trust
  someone who corrects themselves more than someone who never had to.
- If you fluff a line, keep going. Nobody re-records a demo for a stumble.

## Numbers, current as of 29 Aug

Check these against the dashboard before you record — the tick moves them.

| | |
|---|---|
| Tests | 161 |
| Open cases | 52 |
| Overdue | 14 |
| Unattended executions since 22 Aug | 193 |
| Claims assessed / billable / denied | 25 / 15 / 12 |
| Claim batch | 15 lines, 30 units, 0 withheld |
| Benign corpus | 36/36 approve, zero findings |
