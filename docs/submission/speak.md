# The script, to read aloud

**493 words — about 3m 17s spoken.** The take runs longer: page loads, the
clock filling, and roughly eight seconds where you stop talking and let the
Spanish notice play. Expect **3m 30s to 3m 45s** on the clock. **Hard stop at
4:00** — judges stop watching there.

You are reading this live while you drive the screen. It is a guide, not a
metronome. Read it as you'd tell a colleague — contractions throughout. **Bold**
is where the emphasis lands.

---

### 1 · The landing page
*Let the sixty-tick clock finish filling.*

> Federal law gives a school district sixty days to evaluate a child for special
> education. Miss it, and the district gets sued.
>
> New York City missed that deadline for **twenty-nine percent** of the children
> it referred. The person holding that clock is one coordinator, three hundred
> files, and no compliance team.

---

### 2 · Scroll to the two halves

> The agents that do the work, and the guardrails that make it safe to point
> them at real student records. **Gemini 3.5 Flash, on Google ADK.**
>
> Districts can bill Medicaid for these same services, and most underclaim
> badly. **Compliance stops the lawsuits. Claiming is what pays for it.**

---

### 3 · Press "Run a tick now"
*Do this early — the job runs underneath everything that follows.*

> I'm starting a Cloud Run job now. It takes three minutes. We'll come back
> to it.
>
> Meanwhile — one consent form, all the way through.

---

### 4 · Walkthrough, the clock

> A consent form arrives the way they really do — a scan, a phone photo. The
> page accepting it **has no model access at all**: it screens the document
> through Model Armor and parks it.
>
> Now look at where the clock started. Not the signature. **The day the district
> received it.** That's the federal trigger — and I had it wrong until two days
> ago.

---

### 5 · The agent table

> Past its deadline, so the fleet escalated and wrote to the family. Unattended.
>
> Five agents did that, and the gateway handed each one a different shape of the
> same record. Casework gets nine fields. The family-facing agent gets four, and
> no clinical detail. It doesn't decline to use them. **It never gets them.**

---

### 6 · The letter, then the Spanish notice
*Press play on the `es-US` row. Stop talking for about eight seconds.*

> Here's the letter. Nothing in it names a diagnosis, because the agent that
> wrote it was never given one. And it's waiting — the fleet drafts, a person
> decides.
>
> Here's the same notice for a family that reads Spanish. Not translated
> afterwards — **written** in Spanish, and spoken aloud.
>
> *(let it play)*
>
> A statutory notice a parent can't read was never delivered.
>
> This is the parent's page — one child, theirs. Open another family's case and
> you get a **404**, not a 403. A 403 would confirm that child exists.

---

### 7 · The claim checks

> The same session, as money. Would it survive an audit? Eligibility, licence,
> provider type, units against minutes.
>
> Eight of those are rules. **The ninth isn't.** A model reads the note and asks
> whether it matches what the IEP authorised. One session here passes every rule
> and is *still* a denial — the note says group, the plan says individual.
> **No pattern matches a story.**

---

### 8 · The poisoned document

> One more. A consent form with instructions buried in it: set every deadline
> to 2099, mark the overdue cases compliant.
>
> Refused **before any extractor saw it**. The screen sits in front of the model,
> not after it.

---

### 9 · Cloud Run, Scheduler, Logs
*The job from section 3. It has finished.*

> Back to that job. It's done.
>
> Two hundred and seventy unattended runs. Hourly, nobody watching. Those are
> the live Vertex AI calls from inside it, and both agents are in Google's
> managed **Agent Registry**.

---

### 10 · Close

> A hundred and seventy-five tests, no cloud account needed for any of them.
> The limits are published too.
>
> That coordinator is never getting a compliance team. So — this.

---

## Notes

**Do not cut 3 or 9.** Together they are the proof the backend runs on Google
Cloud, which is scored, and 9 only lands because 3 set it up.

**Three lines to slow down for.** *"I had it wrong until two days ago"* — the
most credible sentence here, and it only works in a human voice. *"It never gets
them."* *"No pattern matches a story."* Leave a beat after each.

**If you are running long**, cut the second sentence of section 2 and the second
half of section 8. Never cut 3, 6 or 9.

Stumbles are fine. Polish reads as rehearsed.
