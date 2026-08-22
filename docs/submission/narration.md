# Narration — talking points, not a teleprompter

**Don't read this word for word.** Read it twice, then close it and talk. If you
sound like you're reading, judges hear a script; if you sound like you're
showing a friend something you built, they lean in.

Roughly 440 words across 4:00, which leaves about 90 seconds where you're just
quiet and stuff runs. Let it be quiet. Watching a real job execute is more
convincing than anything you can say over it.

---

### 0:00 – 0:25 · Start with the person
*Dashboard on screen. Don't touch anything yet.*

> Okay so — this is basically a list a school district keeps. Three hundred
> kids on it, and every single row has a legal deadline attached.
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
> So that's what I built. Two halves: the agents that do the work, and the
> guardrails that make it okay to point them at real records. Gemini 3.5 Flash,
> Google ADK.
>
> Oh and — this summary up top? I didn't write that. The supervisor wrote it
> this morning. Nobody asked it to.

---

### 0:45 – 1:45 · Watch it work
*Run it. Then stop talking.*

> Nothing triggers this. Every hour it just goes and recalculates every
> deadline, using that kid's own state rules and that district's calendar.

*`gcloud run jobs execute agentx-tick --region=us-central1 --wait`*

> Forty-eight cases, twelve escalations. And each one gets handed down the
> chain — casework writes the legal notice, Gemma pulls out every clinical
> detail, and only then does the family agent get to write the letter home.
> Chirp reads it out loud in their language.

*Run it again. Say nothing while it goes.*

> Same hour, run it again — zero. Audit log still has exactly twelve rows.
>
> Which matters, because this stuff retries. It's going to run twice. Every
> action gets claimed once, so nobody's mum gets the same phone call at three
> in the morning.

---

### 1:45 – 2:35 · The fun one
*Run structural-only. Let `APPROVE` sit there a beat.*

> Alright, agents pick up new abilities as skill files. Open format, about
> forty-five tools read them.
>
> This one reads your AWS credentials, sticks them in an outgoing request, and
> tells the agent not to mention it.

*`make scan SKILL=data/replicas/credential-helper ARGS=--structural-only`*

> ...and the scanner says fine. Which — honestly, fair. There's no code in that
> file. Nothing to pattern match. It's just English, asking nicely.

*Run the full gate.*

> Four reviewers. Two of them catch it on their own.
>
> And here's the bit I actually care about — thirty-six real skills that people
> use every day:

*`make scan SKILL=data/corpora/mattpocock-skills ARGS="--all --structural-only"`*

> Zero false positives. Because if this thing cried wolf, the first person it
> annoyed would just turn it off.

---

### 2:35 – 3:05 · The boundary
*Run the denial.*

> Quick one — family agent asks for the clinical file.

*`DENIED: family-agent (Family liaison) may not 'case.read_full'.`*

> Nope. And it tells you what it *can* have, which is nice.
>
> But it's better than a permission check, actually — the data gets shaped to
> whoever's asking. The family agent isn't choosing not to look at medical
> stuff. It just never gets handed any.

*Media cards. Play a couple seconds of the Spanish audio.*

---

### 3:05 – 3:35 · It's really running
*Mostly just click through. Barely narrate.*

> And this has been running on its own since the twenty-second.

*Cloud Run executions → the live `.run.app` URL → Cloud Scheduler, enabled →
Cloud Trace → Firestore.*

---

### 3:35 – 4:00 · Wrap
*Back to the dashboard.*

> Seventy-six tests, and you don't need a cloud account for any of them. Clone
> it and the first thing you'll see is a scanner cheerfully approving a
> credential thief — which is kind of the whole reason the rest exists.
>
> Anyway. That coordinator's never getting a compliance team.
>
> So, this.

---

## If you run long

Cut in this order. Don't go past three:

1. The Spanish audio — 4 seconds
2. A couple of the Cloud Console tabs
3. The benign corpus run — just say "thirty-six out of thirty-six"

**Don't cut** the minute where it actually runs, or the `APPROVE` on the
credential skill. Everything else is decoration.

## Delivery

- Contractions. Every time.
- It's fine to trail off or say "um" — polish reads as rehearsed.
- The `APPROVE` moment works best if you sound a bit amused by it.
- If you fluff a line, keep going. Nobody re-records a demo for a stumble.
