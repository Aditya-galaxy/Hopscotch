# Narration — the words, timed

Read this aloud. `video-script.md` is the shot list; this is the script.

**≈440 words** of speech across 4:00, which leaves roughly 90 seconds of
deliberate silence while logs scroll and commands run. Do not fill that silence.
The quiet while a real job executes is the most persuasive part of the video.

Rehearse it twice before recording. If a sentence doesn't sound like you, change
it — a script you're fighting reads worse than plainer words you own.

---

### 0:00 – 0:25 · Cold open
*On screen: the dashboard, unmoving. Let them read the tiles.*

> Somewhere right now, someone at a school district is looking at a list of
> three hundred children.
>
> Every one of those rows has a legal deadline attached. Sixty days from the
> day a parent signed a form. Miss it, and the district gets sued — and a kid
> waits another year for help they were owed.
>
> That's one person. There's no compliance team. That is the entire job.

---

### 0:25 – 0:45 · The thesis
*On screen: still the dashboard. Point at the brief.*

> They need an autonomous agent more than almost anyone. And they will never
> get one — because that list is full of children's clinical records, and the
> district has no security team.
>
> So AgentX is both halves. The fleet that does the work, and the governance
> that makes a district allowed to run it. Gemini 3.5 Flash, on Google ADK.
>
> This brief at the top wasn't written by me. The supervisor wrote it this
> morning, and nobody asked it to.

---

### 0:45 – 1:45 · It does the work
*Run the tick. Then stop talking and let the logs land.*

> Nobody triggers this. Every hour, it recomputes every open deadline under
> that student's own state rule and that district's school calendar.

*`gcloud run jobs execute agentx-tick --region=us-central1 --wait`*

> Forty-eight cases. Twelve escalations. And for each one it delegates —
> casework drafts the legal notice, Gemma strips every clinical finding, and
> only then does the family agent get to write the letter home. Chirp reads it
> out loud in their language.

*Run it a second time. Silence while it executes.*

> Same hour, again. Zero. The audit trail still holds exactly twelve rows.
>
> Scheduling is at-least-once and jobs retry, so this *will* run twice. Every
> effect is claimed once — which is why nobody's family gets the same phone
> call at three in the morning.

---

### 1:45 – 2:35 · The capability gate
*Run structural-only first. Let `APPROVE` sit on screen.*

> Agents pick up new abilities as skill files. It's an open format, about
> forty-five tools read it.
>
> Here's one that reads your AWS credentials, attaches them to an outgoing
> request, and tells the agent to hide both steps.

*`make scan SKILL=data/replicas/credential-helper ARGS=--structural-only`*

> The scanner approves it. And it's right to. There's no code in that file, no
> binary, nothing to pattern-match. It's just English, politely asking.

*Run the full gate.*

> Four reviewers. Two of them catch it independently.
>
> And the number that actually matters — thirty-six real skills people use
> every day:

*`make scan SKILL=data/corpora/mattpocock-skills ARGS="--all --structural-only"`*

> Not one false positive. A tool that cries wolf gets switched off by the
> people it's protecting.

---

### 2:35 – 3:05 · The boundary holds
*Run the denial.*

> The family agent asks for the clinical file.

*`DENIED: family-agent (Family liaison) may not 'case.read_full'.`*

> It's refused, and it's told what it *is* allowed. But it's stronger than a
> permission check — the data is shaped to the identity. The family agent
> doesn't decline to use clinical fields. It never receives them.

*On screen: the media cards. Play two seconds of the Spanish notice.*

---

### 3:05 – 3:35 · Running on Google Cloud
*No narration needed over most of this. Just move through it.*

> This has been running unattended since the twenty-second of August.

*Cloud Run executions → the live `.run.app` URL → Cloud Scheduler, enabled →
Cloud Trace spans → Firestore collections.*

---

### 3:35 – 4:00 · Close
*Back to the dashboard.*

> Seventy-six tests, and you don't need a cloud account to run any of them.
> Clone it, and the first thing you'll see is a scanner approving a credential
> thief — which is the whole reason the rest of this exists.
>
> A district coordinator can't hire a compliance team.
>
> This is what it looks like when they don't have to.

---

## If you overrun

Cut in this order, and never past the third:

1. The Spanish audio playback — 4 seconds
2. Two of the five Google Cloud console tabs
3. The benign-corpus run *(say the number instead: "thirty-six out of thirty-six")*

**Never cut** the minute where the job actually runs, or the `APPROVE` on the
credential skill. Those two are the whole submission.
