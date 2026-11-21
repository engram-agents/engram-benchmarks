#!/usr/bin/env bash
# RETIRED-LAUNCHER: starts a student outside the sandbox launch module (A10)
echo "RETIRED: pilot-run.sh starts a student outside the sandbox launch module (A10); run p1-session.py (it goes through sandbox_launch.py)" >&2; exit 2
# BEAM speed pilot P1 (turns per round), arm 2 only, conversation 9 exchanges 1-45, no forced compaction, no questions.
# This file is the study's harness, not shipped product code. Parameters are logged on the tuning log before a run.
# It runs the feed4.py / feed.py beside it, at the commit checked out; feed4 refuses unless the files it loaded hash
# to the setup's component file. Co-load is sampled every 60 s into the run directory.
#
# NO HOST PATH IN THIS FILE (design owner's rule, 2026-11-16): every host location comes from the environment, so
# these bytes can be published as they are and the public hash is the real one. Required:
#   BEAM_PY        python with the study's packages
#   BEAM_SNAP      the setup snapshot directory (restored fresh into BEAM_ARM_HOME for every run)
#   BEAM_ARM_HOME  the student's home for the run (an existing one is moved aside, never deleted)
#   BEAM_RUNS_DIR  where run directories are created (one per run, never reused)
#   BEAM_PARQUET   the registered BEAM 100K parquet file
# Optional: BEAM_CLAIMS_DIR, a directory of host-memory reservations listed by the co-load sampler.
# Run the WHOLE script under one GPU lease.   usage: pilot-run.sh K      e.g. pilot-run.sh 5
set -u
K=${1:?usage: pilot-run.sh K}
for v in BEAM_PY BEAM_SNAP BEAM_ARM_HOME BEAM_RUNS_DIR BEAM_PARQUET; do
  [ -n "${!v:-}" ] || { echo "STOP: $v is not set"; exit 2; }
done
export BEAM_PARQUET
T=$(cd "$(dirname "$0")" && pwd); BENCH=$(git -C "$T" rev-parse --show-toplevel); DATA=$T/../data
PY=$BEAM_PY; SNAP=$BEAM_SNAP; H=$BEAM_ARM_HOME; OUT=$BEAM_RUNS_DIR/K$K-conv9; WIN=CLAUDE_CODE_MAX_CONTEXT_TOKENS=131072
COMP=$DATA/pilot-setup-K$K.txt
[ -e "$OUT" ] && { echo "STOP: the run directory for K $K exists"; exit 2; }
[ -f "$COMP" ] || { echo "STOP: no setup component file pilot-setup-K$K.txt"; exit 2; }
[ -z "$(git -C "$BENCH" status --porcelain -- studies/beam-2026-11)" ] || { echo "STOP: the benchmarks clone has uncommitted study files"; exit 2; }
sha256sum "$BEAM_PARQUET" | grep -q '^c0519be25907' || { echo "STOP: parquet is not the registered dataset"; exit 2; }
test "$(sha256sum "$SNAP/.claude/CLAUDE.md" | cut -c1-16)" = "bdeead3dee6f8474" || { echo "STOP: snapshot CLAUDE.md is not the setup's"; exit 2; }
for p in $(ps -u "$(id -u)" -o pid=,command= | grep "$H/.engram/" | grep -v grep | awk '{print $1}'); do kill "$p" 2>/dev/null; done
sleep 2
if [ -e "$H" ]; then A="$H.before-pilot-K$K"; [ -e "$A" ] && { echo "STOP: the moved-aside arm home for K $K exists"; exit 2; }; mv "$H" "$A"; fi
cp -a "$SNAP" "$H" && chmod -R u+w "$H" || { echo "STOP: copy failed"; exit 3; }
mkdir -p "$OUT"
{ echo "pilot P1 K $K conv 9 turns 45 start $(date -u +%FT%TZ)"
  echo "benchmarks commit $(git -C "$BENCH" rev-parse HEAD)"
  grep "SETUP ID" "$COMP"
  for f in "$H/.claude/CLAUDE.md" "$T/feed4.py" "$T/feed.py" "$0" "$T/pilot-memcheck.sh"; do
    echo "$(sha256sum "$f" | cut -d' ' -f1)  $(basename "$f")"; done; } > "$OUT/setup.txt"
# Design owner's condition (2026-11-16, after K = 3): the student's auto-memory folder must be EMPTY at the first
# exchange, shown from the arm home itself. Any file, or an unknown layout, stops the run here.
bash "$T/pilot-memcheck.sh" "$H" >> "$OUT/setup.txt"; mc=$?
[ "$mc" -eq 0 ] || { echo "STOP: auto-memory start state not empty or unknown (memcheck exit $mc), see the run's setup.txt"; exit 2; }
"$PY" -I "$T/feed4.py" --arm-home "$H" --out "$OUT/plan-dump" --conv 9 --start 1 --turns 45 --per-round "$K" \
  --dump-plan --expect-components "$COMP" > "$OUT/plan.json" || { echo "STOP: plan dump failed"; exit 3; }
bash "$T/coload-sampler.sh" "$OUT/coload.txt" 60 ${BEAM_CLAIMS_DIR:+"$BEAM_CLAIMS_DIR"} & SAMPLER=$!
trap 'kill $SAMPLER 2>/dev/null' EXIT
"$PY" -I "$T/feed4.py" --arm-home "$H" --out "$OUT/run" --conv 9 --start 1 --turns 45 --per-round "$K" \
  --env "$WIN" --expect-components "$COMP"; rc=$?
kill $SAMPLER 2>/dev/null
END=$(date -u +%FT%TZ)
echo "pilot P1 K $K end $END exit=$rc" >> "$OUT/setup.txt"
for p in $(ps -u "$(id -u)" -o pid=,command= | grep "$H/.engram/" | grep -v grep | awk '{print $1}'); do kill "$p" 2>/dev/null; done
sleep 2
cp -a "$H/.claude/projects" "$OUT/transcripts" 2>/dev/null
"$PY" -I - "$H/.engram/knowledge.db" "$OUT/knowledge-after.db" <<'EOF'
import sqlite3, sys
s = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True); d = sqlite3.connect(sys.argv[2]); s.backup(d); d.close()
print("store copied")
EOF
START=$(head -1 "$OUT/setup.txt" | grep -o 'start [^ ]*' | cut -d' ' -f2)
"$PY" -I "$T/gate-input-evidence.py" --feed-dir "$T" --plan "$OUT/plan.json" "$OUT" > "$OUT/input-evidence.txt" 2>&1
"$PY" -I "$T/coverage.py" run --run-dir "$OUT" --run-start "$START" --span 45 > "$OUT/coverage.txt" 2>&1
"$PY" -I "$T/pilot-record-volume.py" --run-dir "$OUT" --start "$START" --end "$END" --label "pilot K = $K" \
  > "$OUT/record-volume.txt" 2>&1
echo "== pilot K $K exit=$rc"; cat "$OUT/input-evidence.txt" "$OUT/coverage.txt" "$OUT/record-volume.txt"
exit $rc
