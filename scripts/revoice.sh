#!/usr/bin/env bash
# Swap the narration voice and rebuild everything that depends on it.
#
#   ./scripts/revoice.sh Zubenelgenubi [rate]
#
# The previous set is kept under /tmp so a change of mind is a copy, not a
# re-render. 06b-spanish-notice.mp3 is never touched: it is the real notice
# audio at notice rate, not narration.
set -euo pipefail
cd "$(dirname "$0")/.."
V="${1:?usage: revoice.sh <VoiceName> [rate]}"
R="${2:-1.0}"
BK="/tmp/hopscotch-narration-$(grep -oE 'Chirp3-HD-[A-Za-z]+' scripts/narrate.py | head -1 | cut -d- -f3)"

rm -rf "$BK" && cp -r docs/submission/narration "$BK"
echo "  previous set backed up to $BK"

find docs/submission/narration -name '*.mp3' ! -name '06b-spanish-notice.mp3' -delete
sed -i '' "s/VOICE = \"en-US-Chirp3-HD-[A-Za-z]*\"/VOICE = \"en-US-Chirp3-HD-$V\"/" scripts/narrate.py
sed -i '' "s/^RATE = .*/RATE = $R/" scripts/narrate.py

PYTHONPATH=src GOOGLE_CLOUD_PROJECT="${GOOGLE_CLOUD_PROJECT:-kronagent}" \
  .venv/bin/python scripts/narrate.py 2>&1 | grep -vE "fork_posix|ev_poll|^I0" | tail -2
.venv/bin/python scripts/cue_sheet.py
