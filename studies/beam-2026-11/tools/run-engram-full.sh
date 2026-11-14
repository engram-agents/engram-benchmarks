#!/usr/bin/env bash
# ENGRAM arm, full practice sequence (Kepler 29557): fresh install in /var/tmp (no git repo),
# first session as its OWN session, then the exam in a NEW session: 3 exchanges, forced /compact, 2 questions.
set -u
# Required environment (no defaults that name a real path):
: "${BEAM_TOOLS:?set BEAM_TOOLS (directory holding feed2.py and patch-core-alwaysload.py)}"
: "${BEAM_OUT:?set BEAM_OUT (directory for run output and install logs)}"
: "${BEAM_WORK:?set BEAM_WORK (scratch root for the per-arm HOME directories)}"
: "${BEAM_PY:?set BEAM_PY (python3 of an environment with pyarrow)}"
: "${ENGRAM_SRC:?set ENGRAM_SRC (ENGRAM source checkout that holds tools/install.sh)}"
H=$BEAM_WORK/engram-home; PY=$BEAM_PY
rm -rf "$H"; mkdir -p "$H"
( cd $ENGRAM_SRC && env -i HOME=$H PATH="$PATH" LANG=C.UTF-8 TERM=dumb USER=$USER bash tools/install.sh --no-recall-service --yes > $BEAM_OUT/install3.log 2>&1 ); echo "install exit=$?"
grep -c "ok" $BEAM_OUT/install3.log; [ -f "$H/.engram/first-run-pending" ] || { echo "STOP: no first-run-pending"; exit 2; }
$PY -I $BEAM_TOOLS/feed2.py --arm-home $H --out $BEAM_OUT/run-engram-setup --conv 15 --turns 1 --first-session --setup-only; echo "setup exit=$?"
$PY -I $BEAM_TOOLS/feed2.py --arm-home $H --out $BEAM_OUT/run-engram-exam --conv 15 --turns 3 --force-compact --ask "Which shoe models did the assistant list in its first reply?" --ask "What annual budget did Darryl give, and where does he live?"; echo "exam exit=$?"
