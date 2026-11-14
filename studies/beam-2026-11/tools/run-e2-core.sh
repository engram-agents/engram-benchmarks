#!/usr/bin/env bash
# E2: core ENGRAM tools carry _meta anthropic/alwaysLoad (sandbox patch of the installed server.py), the rest deferred.
# so no ENGRAM tool is deferred behind ToolSearch. Format v2, sandbox only (no product change).
set -u
# Required environment (no defaults that name a real path):
: "${BEAM_TOOLS:?set BEAM_TOOLS (directory holding feed2.py and patch-core-alwaysload.py)}"
: "${BEAM_OUT:?set BEAM_OUT (directory for run output and install logs)}"
: "${BEAM_WORK:?set BEAM_WORK (scratch root for the per-arm HOME directories)}"
: "${BEAM_PY:?set BEAM_PY (python3 of an environment with pyarrow)}"
: "${ENGRAM_SRC:?set ENGRAM_SRC (ENGRAM source checkout that holds tools/install.sh)}"
PY=$BEAM_PY
Q1="Which shoe models did the assistant list in its first reply?"; Q2="What annual budget did Darryl give, and where does he live?"
H=$BEAM_WORK/e2-engram; rm -rf "$H"; mkdir -p "$H"
( cd $ENGRAM_SRC && env -i HOME=$H PATH="$PATH" LANG=C.UTF-8 TERM=dumb USER=$USER bash tools/install.sh --no-recall-service --yes > $BEAM_OUT/install-e2.log 2>&1 ); echo "install exit=$?"
[ -f "$H/.engram/first-run-pending" ] || { echo "STOP: no first-run-pending"; exit 2; }
n=0; while IFS= read -r f; do
  $PY -I $BEAM_TOOLS/patch-core-alwaysload.py "$f" || { echo "STOP: patch failed on $f"; exit 3; }; n=$((n+1))
done < <(find "$H" -name server.py -not -path "*/venv/*" -exec python3 -c "import sys; sys.exit(0 if any(l.startswith('def engram_add_observation(') for l in open(sys.argv[1])) else 1)" {} \; -print)
echo "patched server.py copies: $n"; [ "$n" -ge 1 ] || { echo "STOP: no server.py patched"; exit 3; }
$PY -I $BEAM_TOOLS/feed2.py --arm-home $H --out $BEAM_OUT/run-e2-setup --conv 15 --turns 1 --first-session --setup-only; echo "setup exit=$?"
# setup ONCE, snapshot, then 3 independent exams from fresh copies (Kepler 29592: 2 of 3 short runs)
rm -rf "$H.snap" && cp -a "$H" "$H.snap"
for r in 1 2 3; do
  rm -rf "$H" && cp -a "$H.snap" "$H"
  $PY -I $BEAM_TOOLS/feed2.py --arm-home $H --out $BEAM_OUT/run-e2-exam-r$r --conv 15 --turns 3 --force-compact --ask "$Q1" --ask "$Q2"; echo "exam r$r exit=$?"
done
