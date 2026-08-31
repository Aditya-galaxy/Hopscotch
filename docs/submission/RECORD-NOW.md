# Record the video — your own voice

Everything is built, deployed and verified. The only thing missing is you
reading [`speak.md`](speak.md) out loud over the demo. **493 words, about
3m 17s spoken** — expect 3m 30s to 3m 45s on the clock once page loads and the
Spanish notice are in. One continuous take.

---

## A · Before you press record  (5 min)

1. **Do Not Disturb on.** A notification banner is the one fault you cannot fix
   afterwards.
2. **Display → 1920×1200.** You record at 2560×1600 and YouTube downsamples to
   1080p, which turns small type to mush. Dropping the resolution makes
   everything natively larger — it beats browser zoom because it scales the
   terminal and the Cloud console too.
3. `Cmd+Shift+B` to hide the bookmarks bar. Close every other window.
4. **Check the Cloud console avatar, top right** — your email shows on every
   console tab.
5. **System Settings → Privacy & Security → Screen Recording**, confirm
   QuickTime is enabled. Granting it forces a QuickTime restart, which you do
   not want to discover with the take queued up.
6. **Do NOT restart `demo.sh`.** The running server has a warm case with a
   notice waiting for approval; a restart picks a different student and can
   land on one whose notice already went out. Just check it is alive:
   ```bash
   curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/app
   ```

### Tabs — Safari, left to right

| # | Tab |
|---|---|
| 1 | `https://agentx-dashboard-dijsyl2kwq-uc.a.run.app` — the deployed landing page |
| 2 | `http://localhost:8080/walkthrough` |
| 3 | `http://localhost:8080/app` — **scrolled to the outbox row marked `es-US`** |
| 4 | Cloud Run → `agentx-tick` → **Executions** |
| 5 | Cloud Scheduler |
| 6 | Logs Explorer, query already run |

Put [`speak.md`](speak.md) on your **phone**. Nothing you read from should be
on the screen you are recording.

---

## B · Record

**QuickTime → File → New Screen Recording → Record Entire Screen.**
Set the microphone to **your own mic**.

Record the whole screen, not a window and not a tab: you move between six tabs
and window capture goes stale the moment you leave. Visible tab-switching is
also what reads as live, which is what the criterion asks for.

**No mux, no narration file, no terminal.** You talk, you click, you stop.

**Aim to finish between 3:30 and 3:45.** Hard cap is 4:00 — judges stop watching
there, and they said so.

---

## C · The take

Read from `speak.md`. Ten sections, and the screen work for each:

| § | Tab | Do |
|---|---|---|
| 1 | 1 | Landing page. Let the 60-tick clock finish filling |
| 2 | 1 | Scroll to the two halves, then "Compliance is a cost centre" |
| 3 | 3 | **Press "Run a tick now."** Say you'll come back to it. Do not wait |
| 4 | 2 | Begin → File it with the district → next → next. Land on the clock |
| 5 | 2 | Step 3, the escalation. Then step 4, the agent table |
| 6 | 2 | Step 5 — read the letter, **press Approve**. Then step 6, the parent page |
| — | 3 | **Play the `es-US` row.** Stop talking and let ~8 seconds of it run |
| 7 | 2 | Steps 7 and 8, the claim checks |
| 8 | 2 | Step 9 — file the poisoned form, land on the block |
| 9 | 4,5,6 | **Executions** — the job from §3 has finished. Scheduler. Vertex logs |
| 10 | 1 | Back to the landing page to close |

**§3 and §9 are the same Cloud Run job**, started and revisited. That pairing is
the proof the backend really runs on Google Cloud, and Demo & Production
Readiness is 30% of the score. Never cut either.

**The Spanish moment.** Your mic is live, so when you press play on the `es-US`
row it gets picked up through your speakers. Stop narrating and let it run —
about eight seconds is plenty. Room audio is fine here; it is obviously live,
which is the point.

**Three lines to slow down for.** *"I had it wrong until two days ago"* — the
most credible sentence in the script, and it only works in a human voice.
*"It never gets them."* *"No pattern matches a story."* Leave a beat after each.

**Stumbles are fine.** A real pause, a fumbled word, trailing off slightly —
that is what live sounds like, and they asked for live. Do not restart the take
for one. Only three faults are worth a retake: a notification banner, audio that
did not record, or the Google Cloud section missing.

---

## D · Check the file

```bash
afinfo ~/Desktop/*.mov | grep -i duration
```

Under **4:00**. Then watch it once, all the way through, listening — confirm
your audio actually recorded and nothing private is on screen.

---

## E · Upload  (do not leave this late)

YouTube processing runs from minutes to hours.

1. Upload to YouTube, **Public** — unlisted is disallowed.
2. Title: `Hopscotch — an agent fleet that keeps a school district's legal clock`
3. Paste the link into Devpost's **Video demo link** field.

---

## F · Submit

| Field | Value |
|---|---|
| Category | Fortified Enterprise Fleet |
| Start date | `08-21-26` |
| Hosted URL | `https://agentx-dashboard-dijsyl2kwq-uc.a.run.app` |
| Repo | `https://github.com/Aditya-galaxy/Hopscotch` (public) |
| Elevator pitch | 195-char version in `devpost.md` |
| About the project | paste [`about.md`](about.md) below its `---` |
| Architecture diagram | `docs/diagrams/01-system-overview.png` |
| Thumbnail | `docs/submission/thumbnail.png` |
| Image gallery | the ten in `docs/submission/gallery/`, captions in `CAPTIONS.md` |
| Built with | the 17 core tags |
| Try it out | `/walkthrough`, the repo, `/app` |

**Then stop.** Judging runs to about 8 October and the repo is public — no edits
after you submit.
