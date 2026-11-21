#!/usr/bin/env bash
# RETIRED-LAUNCHER: starts a student outside the sandbox launch module (A10)
echo "RETIRED: run-engram-full.sh starts a student outside the sandbox launch module (A10); run p1-session.py (it goes through sandbox_launch.py)" >&2; exit 2
# ENGRAM arm, full practice sequence: fresh install under $BEAM_WORK (which must be outside any git repo),
# first session as its OWN session, then the exam in a NEW session: 3 exchanges, forced /compact, 2 questions.
set -u
# Required environment (no defaults that name a real path):
: "${BEAM_TOOLS:?set BEAM_TOOLS (directory holding feed2.py and patch-core-alwaysload.py)}"
: "${BEAM_OUT:?set BEAM_OUT (directory for run output and install logs)}"
: "${BEAM_WORK:?set BEAM_WORK (scratch root for the per-arm HOME directories)}"
: "${BEAM_PY:?set BEAM_PY (python3 of an environment with pyarrow)}"
: "${ENGRAM_SRC:?set ENGRAM_SRC (ENGRAM source checkout that holds tools/install.sh)}"
# The sandbox must sit outside any git work tree: inside one, ENGRAM refused the student's transcript
# citations in practice, which would change what the arm can do.
mkdir -p "$BEAM_WORK"
if git -C "$BEAM_WORK" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "STOP: BEAM_WORK ($BEAM_WORK) is inside a git work tree; choose a scratch directory outside any repository" >&2
  exit 2
fi
H=$BEAM_WORK/engram-home; PY=$BEAM_PY
rm -rf "$H"; mkdir -p "$H"
( cd $ENGRAM_SRC && env -i HOME=$H PATH="$PATH" LANG=C.UTF-8 TERM=dumb USER=${USER:-$(id -un)} bash tools/install.sh --no-recall-service --yes > $BEAM_OUT/install3.log 2>&1 ); echo "install exit=$?"
grep -c "ok" $BEAM_OUT/install3.log; [ -f "$H/.engram/first-run-pending" ] || { echo "STOP: no first-run-pending"; exit 2; }
$PY -I $BEAM_TOOLS/feed2.py --arm-home $H --out $BEAM_OUT/run-engram-setup --conv 15 --turns 1 --first-session --setup-only; echo "setup exit=$?"
$PY -I $BEAM_TOOLS/feed2.py --arm-home $H --out $BEAM_OUT/run-engram-exam --conv 15 --turns 3 --force-compact --ask "Which shoe models did the assistant list in its first reply?" --ask "What annual budget did Darryl give, and where does he live?"; echo "exam exit=$?"
