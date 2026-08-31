#!/usr/bin/env bash
# Play the narration, or lay it onto a finished screen recording.
#
# The problem this solves: QuickTime's screen recording captures the MICROPHONE,
# not system audio. Play an mp3 through the speakers while recording and you get
# a muffled room recording of it. macOS has no built-in way to capture its own
# output, so the choice is either a virtual audio device (an install, needs a
# password and a reboot) or laying the narration on afterwards, which is what
# `mux` below does and what most screencasts actually do.
set -uo pipefail
cd "$(dirname "$0")/.."
N="docs/submission/narration"

bold() { printf "\n\033[1m%s\033[0m\n" "$1"; }

case "${1:-help}" in

list)
  bold "Sections, with durations"
  T=0
  for f in "$N"/*.mp3; do
    [[ "$f" == *full-narration* ]] && continue
    D=$(afinfo "$f" 2>/dev/null | grep -i "estimated duration" | grep -oE "[0-9]+\.[0-9]+")
    printf "  %-26s %6.1fs\n" "$(basename "$f")" "$D"
    T=$(python3 -c "print($T + $D)")
  done
  python3 -c "t=$T; print(f'\n  total {int(t//60)}m {int(t%60):02d}s')"
  ;;

play)
  # One section at a time. Press return to advance; the point is that YOU set the
  # pace and the screen never has to race the audio.
  bold "Return plays the next section. Ctrl-C stops."
  for f in "$N"/*.mp3; do
    [[ "$f" == *full-narration* ]] && continue
    printf "  next: %s  " "$(basename "$f" .mp3)"
    read -r _
    afplay "$f"
  done
  ;;

full)
  bold "Playing the whole narration"
  afplay "$N/full-narration.mp3"
  ;;

mux)
  # mux <screen-recording.mov> [output.mp4]
  IN="${2:-}"
  OUT="${3:-docs/submission/demo-with-narration.mp4}"
  if [ -z "$IN" ] || [ ! -f "$IN" ]; then
    echo "  usage: $0 mux path/to/screen-recording.mov [out.mp4]"; exit 1
  fi
  VD=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$IN")
  AD=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$N/full-narration.mp3")
  printf "  video %.0fs   narration %.0fs\n" "$VD" "$AD"
  python3 - "$VD" "$AD" <<'PY'
import sys
v, a = float(sys.argv[1]), float(sys.argv[2])
if v < a - 2:
    print(f"  ! the recording is {a - v:.0f}s SHORTER than the narration.")
    print("    The tail will be cut. Re-record a little longer, or trim a section.")
elif v > 240:
    print(f"  ! the recording is {v:.0f}s -- over the 4:00 cap.")
else:
    print("  fits")
PY
  # -shortest so the result cannot exceed the video; the original audio track is
  # dropped rather than mixed, because a room mic under a synth voice sounds worse
  # than either alone.
  ffmpeg -y -loglevel error -i "$IN" -i "$N/full-narration.mp3" \
    -map 0:v:0 -map 1:a:0 -c:v copy -c:a aac -b:a 192k -shortest "$OUT"
  echo "  wrote $OUT  ($(du -h "$OUT" | cut -f1))"
  ;;

*)
  cat <<'EOF'

  narration_play.sh list        durations, so you can pace the screen
  narration_play.sh play        one section at a time, return to advance
  narration_play.sh full        the whole thing, straight through
  narration_play.sh mux REC.mov lay the narration onto a screen recording

  Recording, without installing anything:
    1. QuickTime > File > New Screen Recording. Set the mic to NONE.
    2. Run the demo silently, following the section timings from `list`.
    3. ./scripts/narration_play.sh mux ~/Desktop/recording.mov
    4. Upload the muxed mp4.

  The video stays a single unbroken take -- nothing is spliced, which is what
  "unedited" is about. Only the audio track is laid on.

  If you would rather narrate live in your own voice, do that instead: set the
  mic to your microphone in step 1 and read docs/submission/narration.md. It is
  the better option if you are comfortable speaking.
EOF
  ;;
esac
