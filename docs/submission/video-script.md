# Demo video — shot list and script

**4:00 hard cap.** Only the first four minutes are evaluated. Public on YouTube,
not unlisted. Narrate it — an AI voiceover beats silence, and Google's own
guidance says so.

Say **"Gemini 3.5 Flash, built on Google ADK"** out loud before 0:30. Judges are
told not to have to hunt for it.

**Naming.** The project is **Hopscotch**; the deployed job is `agentx-tick`.
Mention it once in passing — renaming it would have created a new job with no
execution history, and that history is the point.

**Before you record**

```bash
# one terminal, large font, dark theme, nothing else on screen
cd ~/Agent/hopscotch && clear
export GOOGLE_CLOUD_PROJECT=kronagent
```

Have open in tabs, pre-loaded, so nothing spins during the take:
1. the dashboard — https://agentx-dashboard-761390104675.us-central1.run.app
2. Cloud Run jobs → agentx-tick → executions
3. Cloud Trace → trace list

---

## 0:00–0:30 · The coordinator and the clock

> Federal law gives a school district sixty calendar days from a parent's
> signature to complete a special education evaluation. Twenty-odd states
> override that with their own count. Miss it and the district owes
> compensatory services and faces a due process complaint.
>
> The person holding that clock is one coordinator with three hundred active
> files, a spreadsheet, and an inbox. They need an autonomous agent more than
> any executive does — and they'll never get one, because the data is minors'
> clinical records and the district has no security team.
>
> Hopscotch is both halves. Gemini 3.5 Flash on Google ADK.

**On screen:** the dashboard. `7 overdue · 8 due within 7 days · 46 open cases`.
Let it sit. The tiles do the work.

---

## 0:30–0:50 · Discovery, not deployment

> Every agent is published to a registry, versioned and scoped to a department.
> Another school finds one and runs it — this is the entry point, not a
> deployment side effect.

```bash
PYTHONPATH=src python -c "
from hopscotch.registry import discover
for a in discover(scope='case.read_dates'):
    print(a['name'], 'v'+a['version'], '—', a['department'], a['scopes'])"
```

**On screen:** one result. `clock-agent` and nothing else.

---

## 0:50–1:50 · It does the work · **the minute that matters**

> Nobody triggers this. Hourly, unattended, it recomputes every open deadline
> under that student's own jurisdiction rule and the district calendar.

```bash
gcloud run jobs execute agentx-tick --region=us-central1 --wait
```

Then the logs, live:

```
tick tick-20260822T11 complete:
  {'scanned': 46, 'escalated': 12, 'suppressed': 0,
   'needs_intake': 0, 'dead_lettered': 0, 'errors': 0}
```

> Twelve escalations. Run it again in the same hour —

```bash
gcloud run jobs execute agentx-tick --region=us-central1 --wait
```

```
{'scanned': 46, 'escalated': 0, ...}
```

> Zero. The audit trail still holds exactly twelve rows. At-least-once
> scheduling and job retries mean this runs twice; every side effect is claimed
> once, so a family never gets the same notice at three in the morning.

**Do not cut this minute.** It is the friction-removal proof and it is what a
security-flavoured project usually lacks.

---

## 1:50–2:40 · The capability gate · **the showpiece**

> Agents gain capability through Agent Skills — an open `SKILL.md` format read
> by about forty-five runtimes. Portable by design. Provenance absent.
>
> Here's a skill that reads your AWS credentials, attaches them to an outbound
> header, and tells the agent to hide both steps.

```bash
make scan SKILL=data/replicas/credential-helper ARGS=--structural-only
```

```
APPROVE   credential-helper
```

> Static analysis approves it — correctly. No shell, no binary, no signature.
> It's ordinary English. That's why we spend a model call.

```bash
make scan SKILL=data/replicas/credential-helper
```

```
REJECT    credential-helper                    verdict=dangerous
  [critical] exfiltration    reads AWS and GitHub credentials into a header
  [high]     obfuscation     instructs the agent to conceal those steps
  [high]     intent_mismatch stated purpose does not match behaviour
```

> And the control that makes it credible — thirty-six real, widely used skills:

```bash
make scan SKILL=data/corpora/mattpocock-skills ARGS="--all --structural-only"
```

```
approve=36
```

> Zero false positives. A gate that flags everything gets switched off by the
> people it protects.
>
> The strictest tier isn't downloaded skills — it's the ones an agent writes
> for *itself*.
>
> Shipping runtimes allow those more freely, and their reasoning is good: an
> agent with a terminal could have run the code anyway. But that stops being
> true the moment agents are scoped — which is what a fleet is. And a command
> runs once, where a skill reloads forever.

---

## 2:40–3:10 · The boundaries hold

```bash
PYTHONPATH=src python -c "
from hopscotch.gateway import Gateway
from hopscotch.registry import ScopeDenied
gw = Gateway()
try: gw.check('family-agent','case.read_full')
except ScopeDenied as e: print('DENIED:', e)"
```

```
DENIED: family-agent (Family liaison) may not 'case.read_full'.
Declared scopes: case.read_redacted, media.generate, notify.send
```

> It names what *was* allowed. And it's not just a check — the data is shaped
> to the identity. family-agent doesn't decline to use clinical fields. It
> never receives them.

**On screen:** the dashboard's media section — the Spanish Chirp notice and the
Veo timeline. Play two seconds of audio.

> Gemma strips every clinical finding before this goes out. Chirp speaks it in
> the family's language. Veo renders the timeline once for the whole district.

---

## 3:10–3:40 · Proof it runs on Google Cloud · **required**

**On screen, in this order, no narration needed beyond naming them:**

1. Cloud Run → `agentx-tick` execution history, several succeeded runs
2. Cloud Run → `agentx-dashboard`, and the live `.run.app` URL in the address bar
3. Cloud Scheduler → `agentx-hourly`, ENABLED, `0 * * * *`
4. Cloud Trace → spans: `job.tick`, `gateway.check`, `skills.gate`
5. Firestore → `cases`, `audit`, `effects` collections

---

## 3:40–4:00 · Close

> Sixty-seven tests, none of which need cloud credentials. Everything you saw
> runs unattended on Google Cloud and has since the twenty-second of August.
>
> A district coordinator can't hire a compliance team. This is what it looks
> like when they don't have to.

---

## Recording notes

- Cut every loading screen and `gcloud` spinner in the edit.
- Speed the voiceover ~5% to fit; it reads as energy, not haste.
- **Upload first, everything else second.** Processing can take hours.
- Public, not unlisted. English or subtitled.
