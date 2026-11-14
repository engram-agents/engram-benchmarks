#!/usr/bin/env bash
# privacy-scan.sh: fail if any tracked file carries a host-specific detail.
#
# usage: tools/privacy-scan.sh        (run inside the repository; takes no arguments)
#
# Scans every file from `git ls-files` (tracked files), as they sit in the working tree.
# Exit 0 = no findings. Exit 1 = findings, printed one per line as `path:line: <pattern-name>`.
# Exit 2 = usage or I/O error, including "not a git repo" and "nothing to scan" (fail closed:
# an empty scan is never a pass).
#
# Exempt by path (they must contain the patterns): this script, tools/test-privacy-scan.sh and
# everything under tools/privacy-scan-fixtures/. Nothing else is exempt by path.
# Per-line escape: a line containing the literal marker `privacy-scan: allow` is skipped, so a
# deliberate generic mention can stay in the tree where a reader can see it.
set -u

MARKER='privacy-scan: allow'

NAMES=(home-path user-temp-path email private-ip localhost-port windows-user-path)
RES=(
  '/home/[A-Za-z0-9._-]+|/Users/[A-Za-z0-9._-]+|/root/'
  '/var/tmp/[A-Za-z0-9._-]+|/tmp/claude-'
  '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
  '(^|[^0-9.])(10\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}|172\.(1[6-9]|2[0-9]|3[01])\.[0-9]{1,3}\.[0-9]{1,3}|192\.168\.[0-9]{1,3}\.[0-9]{1,3})([^0-9]|$)'
  '(localhost|127\.0\.0\.1):[0-9]+'
  '[Cc]:\\Users\\'
)

if [ "$#" -ne 0 ]; then
  echo "usage: tools/privacy-scan.sh   (no arguments; run inside the repository)" >&2
  exit 2
fi
if ! top="$(git rev-parse --show-toplevel 2>/dev/null)"; then
  echo "privacy-scan: not inside a git repository; refusing to report a pass" >&2
  exit 2
fi
cd "$top" || { echo "privacy-scan: cannot enter $top" >&2; exit 2; }

scanned=0
findings=0
io_error=0
while IFS= read -r -d '' f; do
  case "$f" in
    tools/privacy-scan.sh | tools/test-privacy-scan.sh | tools/privacy-scan-fixtures/*) continue ;;
  esac
  if [ -d "$f" ]; then continue; fi  # a submodule entry: no file content here
  if [ ! -r "$f" ]; then
    echo "privacy-scan: cannot read tracked file: $f" >&2
    io_error=1
    continue
  fi
  scanned=$((scanned + 1))
  allowed=" $(grep -nF -e "$MARKER" -- "$f" | cut -d: -f1 | tr '\n' ' ')"
  for i in "${!NAMES[@]}"; do
    out="$(grep -naoE -e "${RES[$i]}" -- "$f")"
    rc=$?
    if [ "$rc" -gt 1 ]; then
      echo "privacy-scan: grep failed on $f (pattern ${NAMES[$i]})" >&2
      io_error=1
      continue
    fi
    [ -z "$out" ] && continue
    prev=""
    while IFS= read -r hit; do
      line="${hit%%:*}"
      match="${hit#*:}"
      case "$allowed" in *" $line "*) continue ;; esac
      if [ "${NAMES[$i]}" = email ]; then
        case "$match" in
          noreply@anthropic.com | *@users.noreply.github.com) continue ;;
        esac
      fi
      if [ "$line" = "$prev" ]; then continue; fi  # one finding per pattern per line
      prev="$line"
      echo "$f:$line: ${NAMES[$i]}"
      findings=$((findings + 1))
    done <<<"$out"
  done
done < <(git ls-files -z)

if [ "$io_error" -ne 0 ]; then
  exit 2
fi
if [ "$scanned" -eq 0 ]; then
  echo "privacy-scan: no files to scan (empty tracked set or only exempt files); refusing to report a pass" >&2
  exit 2
fi
if [ "$findings" -ne 0 ]; then
  echo "privacy-scan: $findings finding(s) in $scanned file(s)" >&2
  exit 1
fi
echo "privacy-scan: clean ($scanned files)" >&2
exit 0
