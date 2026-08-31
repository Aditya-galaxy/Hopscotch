"""Regenerate the recording cue sheet from the narration actually on disk.

Timings are measured, never estimated: Chirp does not pace a long script the
way it paces one sentence, so a projection from a sample is worth very little.
Run this after any change of voice or rate.

    .venv/bin/python scripts/cue_sheet.py
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

N = Path("docs/submission/narration")
OUT = Path("docs/submission/CUE-SHEET.md")

# tab number, and what to do while that section plays
WHAT: dict[str, tuple[str, str]] = {
    "01-problem":          ("1", "Landing page — let the 60-tick clock fill"),
    "02-what-this-is":     ("1", "Scroll: the two halves, then 'Compliance is a cost centre'"),
    "03-run-the-fleet":    ("3", "**Press 'Run a tick now'.** Do not wait for it"),
    "04-the-clock":        ("2", "Begin → File it → next → next. Land on the clock"),
    "05-the-fleet":        ("2", "Step 3 escalation, then step 4, the agent table"),
    "06a-the-letter":      ("2", "Step 5 — read the letter, **press Approve**"),
    "06b-spanish-notice":  ("3", "**Press play on the `es-US` row**"),
    "06c-the-parent-page": ("2", "Step 6, the parent page"),
    "07-the-money":        ("2", "Steps 7 and 8 — the claim checks"),
    "08-refused":          ("2", "Step 9 — file the poisoned form, land on the block"),
    "09-google-cloud":     ("4,5,6", "**Executions** — your job has finished. Scheduler. Vertex logs"),
    "10-close":            ("1", "Back to the landing page"),
}


def duration(path: Path) -> float:
    out = subprocess.run(["afinfo", str(path)], capture_output=True, text=True).stdout
    return float(re.search(r"estimated duration: ([\d.]+)", out).group(1))


def clock(t: float) -> str:
    return f"{int(t // 60)}:{int(t % 60):02d}"


def main() -> int:
    voice = "unknown"
    m = re.search(r'VOICE = "en-US-Chirp3-HD-([A-Za-z]+)"',
                  Path("scripts/narrate.py").read_text())
    if m:
        voice = m.group(1)

    t, rows = 0.0, []
    for p in sorted(N.glob("[0-9][0-9]*.mp3")):
        tab, what = WHAT.get(p.stem, ("?", "—"))
        d = duration(p)
        rows.append(f"| **{clock(t)}** | `{p.stem}` | {d:.0f}s | {tab} | {what} |")
        t += d

    # The mux uses -shortest, so the video must outlast the narration -- but it
    # must also come in under the 4:00 cap. Those two squeeze together once the
    # narration passes about 3m45s, and a naive "narration + 10s" then advises
    # a video that would be disqualified for length.
    CAP = 240
    if t + 10 <= CAP - 2:
        tail = (f"Record at least **{clock(t + 10)}**. The mux uses `-shortest`, "
                f"so a video\nshorter than the narration loses its tail.")
    else:
        tail = (f"**Tight margin.** The narration is {clock(t)} and the cap is 4:00, "
                f"so the video\nhas to land between **{clock(t + 3)}** and "
                f"**3:58** -- long enough that the mux does not\nclip the tail, "
                f"short enough to stay under the limit. If that feels too fine, "
                f"a\nshorter voice buys margin: `./scripts/revoice.sh Enceladus` "
                f"is 3:38.")

    OUT.write_text(f"""# Cue sheet — {voice}, {clock(t)}

Play `docs/submission/narration/full-narration.mp3` **once, straight through**.
The recording captures no audio, so it is only there to pace you — you never
touch the terminal after starting it. Keep this on your phone, not on the
screen you are recording.

| Cue | Section | Len | Tab | Do |
|---|---|---|---|---|
""" + "\n".join(rows) + f"""
| **{clock(t)}** | *(ends)* | — | — | Keep recording ~10s more, then stop |

{tail}

**Tabs:** 1 landing page · 2 `/walkthrough` · 3 `/app` · 4 Cloud Run executions ·
5 Scheduler · 6 Logs Explorer.

**The two cues that carry the score.** `03-run-the-fleet` and `09-google-cloud`
are the same Cloud Run job, started and then revisited — that pairing is the
proof the backend really runs on Google Cloud, and Demo & Production Readiness
is 30%. Never cut either.

**`06b-spanish-notice` is real audio.** Ten seconds of the actual notice, spliced
into the narration track because the screen recording is silent and the parent's
audio would otherwise never be heard. Press play on the `es-US` row as it starts
so the picture matches the sound. A second of drift does not matter.
""")
    print(f"  {voice}, {clock(t)} — cue sheet written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
