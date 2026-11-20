#!/usr/bin/env bash
# BEAM pilots: the student's auto-memory start state, read from the arm home itself (design owner's condition,
# 2026-11-16). This file is the study's harness, not shipped product code.
# Lists every directory named 'memory' under ARM_HOME/.claude (the plugin cache excluded) and every file in each, with
# sha256 (no host path is printed: the project folder's name shows as <project>, files by basename). Prints 'auto-memory start state: N file(s) in M folder(s)'. Exit 0 only if N = 0; exit 1 if any file exists;
# exit 2 if ARM_HOME/.claude is missing or no memory folder is found at all (an unknown layout is not "empty").
# usage: pilot-memcheck.sh ARM_HOME
set -u
H=${1:?usage: pilot-memcheck.sh ARM_HOME}
[ -d "$H/.claude" ] || { echo "auto-memory start state: UNKNOWN, no .claude folder in the arm home"; exit 2; }
mapfile -t DIRS < <(find "$H/.claude" -type d -name memory -not -path "*/plugins/*" | sort)
[ "${#DIRS[@]}" -gt 0 ] || { echo "auto-memory start state: UNKNOWN, no memory folder under .claude"; exit 2; }
N=0
for d in "${DIRS[@]}"; do
  echo "folder: $(printf '%s' "${d#$H/}" | sed 's|projects/[^/]*/|projects/<project>/|')"
  while IFS= read -r f; do N=$((N + 1)); echo "  file: $(sha256sum "$f" | cut -c1-16) $(wc -c < "$f") bytes $(basename "$f")"; done < <(find "$d" -type f | sort)
done
echo "auto-memory start state: $N file(s) in ${#DIRS[@]} folder(s)"
[ "$N" -eq 0 ]
