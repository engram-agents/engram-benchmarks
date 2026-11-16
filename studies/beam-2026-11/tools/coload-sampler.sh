#!/usr/bin/env bash
# Co-load sampler for the BEAM speed pilots. This file is the study's harness, not shipped product code.
# Every INTERVAL seconds (until killed), appends to OUT_FILE: a UTC timestamp, the GPU's memory and utilisation,
# the GPU's compute processes, the host load average, the top processes by CPU over a 2-second window (owner, %CPU,
# short command name only, no arguments or paths), and the entries of each DIR given (e.g. a host's memory or GPU
# reservation lists). An entry whose content starts with a process id is marked [live] or [dead] by whether that
# process exists now: a reservation file can outlive its job (instrument change, 2026-11-16, design owner's ruling).
# Run it in the background for the whole pilot run; the run script kills it at the end.
# usage: coload-sampler.sh OUT_FILE INTERVAL [DIR ...]
set -u
OUT=${1:?usage: coload-sampler.sh OUT_FILE INTERVAL [DIR ...]}; IV=${2:?interval in seconds}; shift 2
while true; do
  {
    echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv,noheader 2>&1 | sed 's/^/gpu: /'
    nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader 2>&1 | sed 's/^/gpu-app: /'
    echo "loadavg: $(cat /proc/loadavg)"
    # second iteration of top = CPU use over the last 2 s (the first iteration is since process start)
    top -b -n 2 -d 2 -o %CPU -w 200 2>/dev/null | awk '/^top -/{n++} n==2 && $1 ~ /^[0-9]+$/ {print "cpu: " $2 " " $9 "% " $12}' | head -n 6
    for d in "$@"; do
      for f in "$d"/*; do
        [ -e "$f" ] || continue
        pid=$(head -c 20 "$f" | awk '{print $1; exit}')
        if [[ "$pid" =~ ^[0-9]+$ ]]; then if [ -d "/proc/$pid" ]; then st="[live] "; else st="[dead] "; fi; else st=""; fi
        echo "entry: $(basename "$d")/$(basename "$f"): ${st}$(head -c 160 "$f" | tr '\n' ' ')"
      done
    done
  } >> "$OUT"
  sleep "$IV"
done
