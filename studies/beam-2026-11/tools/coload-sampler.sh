#!/usr/bin/env bash
# Co-load sampler for the BEAM speed pilots. This file is the study's harness, not shipped product code.
# Every INTERVAL seconds (until killed), appends to OUT_FILE: a UTC timestamp, the GPU's memory and utilisation,
# the GPU's compute processes, the host load average, and the entries of each DIR given (e.g. a host's memory or
# GPU reservation lists). Run it in the background for the whole pilot run; the run script kills it at the end.
# usage: coload-sampler.sh OUT_FILE INTERVAL [DIR ...]
set -u
OUT=${1:?usage: coload-sampler.sh OUT_FILE INTERVAL [DIR ...]}; IV=${2:?interval in seconds}; shift 2
while true; do
  {
    echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv,noheader 2>&1 | sed 's/^/gpu: /'
    nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader 2>&1 | sed 's/^/gpu-app: /'
    echo "loadavg: $(cat /proc/loadavg)"
    for d in "$@"; do
      for f in "$d"/*; do [ -e "$f" ] && echo "entry: $(basename "$d")/$(basename "$f"): $(head -c 160 "$f" | tr '\n' ' ')"; done
    done
  } >> "$OUT"
  sleep "$IV"
done
