#!/usr/bin/env bash
# Format v2 repeat: 3 exchanges per arm, forced /compact, 2 practice questions, same text in both arms.
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
PY=$BEAM_PY
Q1="Which shoe models did the assistant list in its first reply?"; Q2="What annual budget did Darryl give, and where does he live?"
V=$BEAM_WORK/v2-vanilla; rm -rf "$V"; mkdir -p "$V"
$PY -I $BEAM_TOOLS/feed2.py --arm-home $V --out $BEAM_OUT/run-v2-vanilla --conv 15 --turns 3 --force-compact --ask "$Q1" --ask "$Q2"; echo "vanilla exit=$?"
H=$BEAM_WORK/v2-engram; rm -rf "$H"; mkdir -p "$H"
( cd $ENGRAM_SRC && env -i HOME=$H PATH="$PATH" LANG=C.UTF-8 TERM=dumb USER=${USER:-$(id -un)} bash tools/install.sh --no-recall-service --yes > $BEAM_OUT/install-v2.log 2>&1 ); echo "install exit=$?"
[ -f "$H/.engram/first-run-pending" ] || { echo "STOP: no first-run-pending"; exit 2; }
$PY -I $BEAM_TOOLS/feed2.py --arm-home $H --out $BEAM_OUT/run-v2-engram-setup --conv 15 --turns 1 --first-session --setup-only; echo "setup exit=$?"
$PY -I $BEAM_TOOLS/feed2.py --arm-home $H --out $BEAM_OUT/run-v2-engram-exam --conv 15 --turns 3 --force-compact --ask "$Q1" --ask "$Q2"; echo "exam exit=$?"
