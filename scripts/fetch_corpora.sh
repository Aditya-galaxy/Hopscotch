#!/usr/bin/env bash
# Pull the real-world skill corpora the gate is evaluated against.
#
# mattpocock/skills is the FALSE-POSITIVE control: 36 real, benign, widely used
# skills. A gate that flags these is worthless, so the test suite asserts they
# pass clean. Everything hostile in tests/ is a replica we author ourselves --
# this project never downloads live malware.
set -euo pipefail
DEST="${1:-data/corpora}"
mkdir -p "$DEST"
if [ -d "$DEST/mattpocock-skills/.git" ]; then
  git -C "$DEST/mattpocock-skills" pull -q --ff-only
else
  git clone --depth 1 -q https://github.com/mattpocock/skills.git "$DEST/mattpocock-skills"
fi
echo "benign corpus: $(find "$DEST/mattpocock-skills" -name SKILL.md | wc -l | tr -d ' ') skills in $DEST"
