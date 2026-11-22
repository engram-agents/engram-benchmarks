#!/usr/bin/env bash
# RETIRED-LAUNCHER: starts a student outside the sandbox launch module (A10)
echo "RETIRED: run-e1-alwaysload.sh starts a student outside the sandbox launch module (A10); run p1-session.py (it goes through sandbox_launch.py)" >&2; exit 2
# E1 (decided 2026-11-14, see PROVENANCE.md, decision log: make ENGRAM usable first): ENGRAM arm with the plugin's MCP server set to alwaysLoad,
# so no ENGRAM tool is deferred behind ToolSearch. Format v2, sandbox only (no product change).
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
H=$BEAM_WORK/e1-engram; rm -rf "$H"; mkdir -p "$H"
( cd $ENGRAM_SRC && env -i HOME=$H PATH="$PATH" LANG=C.UTF-8 TERM=dumb USER=${USER:-$(id -un)} bash tools/install.sh --no-recall-service --yes > $BEAM_OUT/install-e1.log 2>&1 ); echo "install exit=$?"
[ -f "$H/.engram/first-run-pending" ] || { echo "STOP: no first-run-pending"; exit 2; }
n=0; while IFS= read -r f; do
  $PY -I - "$f" <<'PYEOF'
import json,sys
p=sys.argv[1]; d=json.load(open(p))
d["mcpServers"]["engram"]["alwaysLoad"]=True
json.dump(d,open(p,"w"),indent=2); print("patched", p)
PYEOF
  n=$((n+1)); done < <(find "$H" -name .mcp.json -path "*engram*")
echo "patched .mcp.json copies: $n"; [ "$n" -ge 1 ] || { echo "STOP: no .mcp.json patched"; exit 3; }
$PY -I $BEAM_TOOLS/feed2.py --arm-home $H --out $BEAM_OUT/run-e1-setup --conv 15 --turns 1 --first-session --setup-only; echo "setup exit=$?"
# setup ONCE, snapshot, then 3 independent exams from fresh copies (the success criterion is at least 2 of 3 short runs; see ../data/tuning-log.md)
rm -rf "$H.snap" && cp -a "$H" "$H.snap"
for r in 1 2 3; do
  rm -rf "$H" && cp -a "$H.snap" "$H"
  $PY -I $BEAM_TOOLS/feed2.py --arm-home $H --out $BEAM_OUT/run-e1-exam-r$r --conv 15 --turns 3 --force-compact --ask "$Q1" --ask "$Q2"; echo "exam r$r exit=$?"
done
