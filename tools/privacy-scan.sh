#!/usr/bin/env bash
# privacy-scan.sh: fail if the repository carries a host-specific detail.
#
# usage: tools/privacy-scan.sh                       scan tracked files (content and path names)
#        tools/privacy-scan.sh --history <rev-range> scan commit messages and author/committer
#                                                    names and emails over a range, e.g. origin/main..HEAD
#
# File mode scans every file from `git ls-files`, as it sits in the working tree, plus each tracked
# PATH as text (a file name can leak too). History mode scans, per commit in the range, the message,
# the author and committer names (same patterns), and the author and committer emails (see below).
# Exit 0 = no findings. Exit 1 = findings, printed one per line:
#   file mode     path:line: <pattern-name>              (path findings: path:0: <pattern-name> (filename))
#   history mode  <12-hex commit>:<field>:line: <pattern-name>   field = message | author-name |
#                 committer-name | author-email | committer-email
# Exit 2 = usage or I/O error, including "not a git repo", "bad range" and "nothing to scan"
# (fail closed: an empty scan is never a pass).
#
# Exempt by path (they must contain the patterns): this script, tools/test-privacy-scan.sh and
# everything under tools/privacy-scan-fixtures/. Nothing else is exempt by path.
# Per-line escape: a line containing the literal marker `privacy-scan: allow` is skipped, so a
# deliberate generic mention can stay in the tree where a reader can see it.
# Email exemptions (file and history mode): noreply@anthropic.com, any *@users.noreply.github.com,
# and every address listed one per line in tools/privacy-scan-allowed-identities.txt.
# History mode treats an author or committer email as a finding unless it is a
# *@users.noreply.github.com address, GitHub's own noreply@github.com (the committer of web-UI and
# squash merges), or listed in that file.
set -u

MARKER='privacy-scan: allow'
ALLOWED_FILE='tools/privacy-scan-allowed-identities.txt'

# S matches a path separator as plain `/` or JSON-escaped `\/`.
S='(/|\\/)'

NAMES=(home-path user-temp-path email private-ip private-ipv6 localhost-port windows-user-path wsl-path local-hostname)
RES=(
  # /root needs a path boundary after it, so /rooted and /root_dir stay clean
  "${S}(home|Users)${S}[A-Za-z0-9._-]+|${S}root(\$|[^A-Za-z0-9_-])"
  "${S}var${S}tmp${S}[A-Za-z0-9._-]+|${S}tmp${S}(claude-|pytest-of-)|${S}private${S}var${S}folders${S}"
  '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
  # RFC 1918, CGNAT 100.64.0.0/10, link-local 169.254/16
  '(^|[^0-9.])(10\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}|172\.(1[6-9]|2[0-9]|3[01])\.[0-9]{1,3}\.[0-9]{1,3}|192\.168\.[0-9]{1,3}\.[0-9]{1,3}|100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.[0-9]{1,3}\.[0-9]{1,3}|169\.254\.[0-9]{1,3}\.[0-9]{1,3})([^0-9]|$)'
  # IPv6 unique-local fc00::/7 (fc.. and fd..): needs the colon-separated shape, so hex words and SHAs stay clean
  '(^|[^0-9A-Za-z:])[fF][cCdD][0-9a-fA-F]{2}:[0-9a-fA-F]{0,4}:'
  '(localhost|127\.0\.0\.1):[0-9]+|\[::1\]:[0-9]+'
  # any drive letter, one or two backslashes (two = JSON-escaped)
  '[A-Za-z]:(\\\\|\\)Users(\\\\|\\)'
  # WSL UNC share, one or more backslashes in front
  '\\\\wsl(\$|\.localhost)'
  # hostname shape: labels then .local or .lan, not followed by an identifier character
  '(^|[^A-Za-z0-9._-])[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?(\.[A-Za-z0-9-]+)*\.(local|lan)([^A-Za-z0-9_.-]|\.([^A-Za-z0-9_-]|$)|$)'
)

MODE=files
RANGE=""
if [ "$#" -eq 0 ]; then
  :
elif [ "$#" -eq 2 ] && [ "$1" = "--history" ] && [ -n "$2" ] && [ "${2#-}" = "$2" ]; then
  MODE=history
  RANGE="$2"
else
  echo "usage: tools/privacy-scan.sh [--history <rev-range>]   (run inside the repository)" >&2
  exit 2
fi
if ! top="$(git rev-parse --show-toplevel 2>/dev/null)"; then
  echo "privacy-scan: not inside a git repository; refusing to report a pass" >&2
  exit 2
fi
cd "$top" || { echo "privacy-scan: cannot enter $top" >&2; exit 2; }

tmpd="$(mktemp -d)" || { echo "privacy-scan: cannot create a temp dir" >&2; exit 2; }
trap 'rm -rf "$tmpd"' EXIT

lc() { printf '%s' "$1" | tr 'A-Z' 'a-z'; }

# Allowed identities (one per line, case-insensitive). A missing file means none are allowed.
ALLOWED=""
if [ -e "$ALLOWED_FILE" ]; then
  if [ ! -r "$ALLOWED_FILE" ]; then
    echo "privacy-scan: cannot read $ALLOWED_FILE" >&2
    exit 2
  fi
  while IFS= read -r l || [ -n "$l" ]; do
    l="${l%$'\r'}"
    [ -n "$l" ] && ALLOWED="$ALLOWED
$(lc "$l")"
  done < "$ALLOWED_FILE"
fi
ALLOWED="$ALLOWED
"

is_listed() { case "$ALLOWED" in *"
$(lc "$1")
"*) return 0 ;; esac; return 1; }
email_exempt() {
  case "$1" in noreply@anthropic.com | *@users.noreply.github.com) return 0 ;; esac
  is_listed "$1"
}

findings=0
io_error=0

# scan_one <file on disk> <label> <suffix> <fixed line: 1 = print line 0>
# Applies every pattern; prints `label:line: name<suffix>`.
scan_one() {
  local f="$1" label="$2" suffix="$3" fixed="$4" allowed i out rc hit line match prev m
  allowed=" $(grep -nF -e "$MARKER" -- "$f" | cut -d: -f1 | tr '\n' ' ')"
  for i in "${!NAMES[@]}"; do
    out="$(grep -naoE -e "${RES[$i]}" -- "$f")"
    rc=$?
    if [ "$rc" -gt 1 ]; then
      echo "privacy-scan: grep failed on $label (pattern ${NAMES[$i]})" >&2
      io_error=1
      continue
    fi
    [ -z "$out" ] && continue
    prev=""
    while IFS= read -r hit; do
      line="${hit%%:*}"
      match="${hit#*:}"
      case "$allowed" in *" $line "*) continue ;; esac
      case "${NAMES[$i]}" in
        email) if email_exempt "$match"; then continue; fi ;;
        local-hostname)  # `self.local` and friends are attribute access, not a host
          m="${match##[!A-Za-z0-9]}"
          case "$m" in self.* | this.* | cls.*) continue ;; esac ;;
      esac
      if [ "$line" = "$prev" ]; then continue; fi  # one finding per pattern per line
      prev="$line"
      [ "$fixed" = 1 ] && line=0
      echo "$label:$line: ${NAMES[$i]}$suffix"
      findings=$((findings + 1))
    done <<<"$out"
  done
}

if [ "$MODE" = files ]; then
  scanned=0
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
    printf '%s\n' "$f" > "$tmpd/path"
    scan_one "$tmpd/path" "$f" " (filename)" 1
    scan_one "$f" "$f" "" 0
  done < <(git ls-files -z)
  what="files"
else
  shas="$(git rev-list "$RANGE" 2>/dev/null)" || { echo "privacy-scan: bad revision range: $RANGE" >&2; exit 2; }
  scanned=0
  for sha in $shas; do
    scanned=$((scanned + 1))
    short="${sha:0:12}"
    git log -1 --format=%B "$sha" > "$tmpd/msg" 2>/dev/null || { echo "privacy-scan: cannot read commit $short" >&2; io_error=1; continue; }
    scan_one "$tmpd/msg" "$short:message" "" 0
    for field in author committer; do
      if [ "$field" = author ]; then nf=%an; ef=%ae; else nf=%cn; ef=%ce; fi
      name="$(git log -1 --format=$nf "$sha" 2>/dev/null)" || { io_error=1; continue; }
      email="$(git log -1 --format=$ef "$sha" 2>/dev/null)" || { io_error=1; continue; }
      printf '%s\n' "$name" > "$tmpd/name"
      scan_one "$tmpd/name" "$short:$field-name" "" 0
      case "$email" in
        *@users.noreply.github.com | noreply@github.com) ;;
        *) if ! is_listed "$email"; then
             echo "$short:$field-email:1: identity-not-allowed"
             findings=$((findings + 1))
           fi ;;
      esac
    done
  done
  what="commits"
fi

if [ "$io_error" -ne 0 ]; then
  exit 2
fi
if [ "$scanned" -eq 0 ]; then
  echo "privacy-scan: nothing to scan (empty tracked set or only exempt files, or an empty range); refusing to report a pass" >&2
  exit 2
fi
if [ "$findings" -ne 0 ]; then
  echo "privacy-scan: $findings finding(s) in $scanned $what" >&2
  exit 1
fi
echo "privacy-scan: clean ($scanned $what)" >&2
exit 0
