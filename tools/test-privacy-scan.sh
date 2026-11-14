#!/usr/bin/env bash
# test-privacy-scan.sh: tests for tools/privacy-scan.sh against planted fixtures.
#
# usage: tools/test-privacy-scan.sh
# env:   PRIVACY_SCAN (optional) path to the scanner under test; default is the sibling privacy-scan.sh.
#        It exists so a deliberately broken copy of the scanner can be run through these tests.
#
# Every case builds a throwaway git repo under mktemp -d, so nothing depends on this repo's contents.
# Exit 0 = every case passed; 1 = at least one failed.
set -u

here="$(cd "$(dirname "$0")" && pwd)"
SCAN="${PRIVACY_SCAN:-$here/privacy-scan.sh}"
FIX="$here/privacy-scan-fixtures"
[ -x "$SCAN" ] || { echo "scanner not executable: $SCAN" >&2; exit 2; }
[ -d "$FIX" ] || { echo "fixtures missing: $FIX" >&2; exit 2; }

root="$(mktemp -d)"
trap 'rm -rf "$root"' EXIT
fails=0
n=0

# new_repo <name>: prints the path of a fresh, empty git repo.
new_repo() {
  local d="$root/$1"
  mkdir -p "$d"
  git init -q "$d"
  printf '%s' "$d"
}

# check <case name> <repo dir> <expected rc> <expected stdout>
check() {
  local name="$1" dir="$2" want_rc="$3" want_out="$4" out rc
  n=$((n + 1))
  out="$(cd "$dir" && "$SCAN" 2>/dev/null)"
  rc=$?
  if [ "$rc" = "$want_rc" ] && [ "$out" = "$want_out" ]; then
    echo "PASS  $name"
  else
    echo "FAIL  $name: want rc=$want_rc out=[$want_out]; got rc=$rc out=[$out]"
    fails=$((fails + 1))
  fi
}

# check_args <case name> <repo dir> <expected rc> <expected stdout> <scanner args...>
# Like check, but passes arguments (history mode) and replaces each 12-hex-digit commit label with SHA
# so expected output does not depend on commit ids.
check_args() {
  local name="$1" dir="$2" want_rc="$3" want_out="$4" out rc
  shift 4
  n=$((n + 1))
  out="$(cd "$dir" && "$SCAN" "$@" 2>/dev/null)"
  rc=$?
  out="$(printf '%s' "$out" | sed -E 's/^[0-9a-f]{12}:/SHA:/')"
  if [ "$rc" = "$want_rc" ] && [ "$out" = "$want_out" ]; then
    echo "PASS  $name"
  else
    echo "FAIL  $name: want rc=$want_rc out=[$want_out]; got rc=$rc out=[$out]"
    fails=$((fails + 1))
  fi
}

# fixture_case <case name> <fixture file> <expected rc> <expected stdout>
# Copies the fixture into a fresh repo as sample.txt, adds it, and runs the scanner there.
fixture_case() {
  local d
  d="$(new_repo "$1")"
  cp "$FIX/$2" "$d/sample.txt"
  git -C "$d" add sample.txt
  check "$1" "$d" "$3" "$4"
}

fixture_case home-path home-path.txt 1 "$(printf 'sample.txt:1: home-path\nsample.txt:2: home-path\nsample.txt:3: home-path')"
fixture_case user-temp-path user-temp-path.txt 1 "$(printf 'sample.txt:1: user-temp-path\nsample.txt:2: user-temp-path')"
fixture_case email email.txt 1 "sample.txt:1: email"
fixture_case private-ip private-ip.txt 1 "$(printf 'sample.txt:1: private-ip\nsample.txt:2: private-ip\nsample.txt:3: private-ip\nsample.txt:4: private-ip')"
fixture_case localhost-port localhost-port.txt 1 "$(printf 'sample.txt:1: localhost-port\nsample.txt:2: localhost-port')"
fixture_case windows-user-path windows-user-path.txt 1 "sample.txt:1: windows-user-path"
fixture_case clean clean.txt 0 ""
fixture_case allow-marker allow-marker.txt 0 ""
fixture_case allow-marker-partial allow-marker-partial.txt 1 "sample.txt:2: home-path"

# Round-2 pattern families. Each has a positive fixture; near-misses.txt holds the negatives for all of them.
fixture_case windows-json-drive windows-json-drive.txt 1 "$(printf 'sample.txt:1: windows-user-path\nsample.txt:2: windows-user-path\nsample.txt:3: windows-user-path')"
fixture_case wsl-unc wsl-unc.txt 1 "$(printf 'sample.txt:1: wsl-path\nsample.txt:2: wsl-path\nsample.txt:3: wsl-path')"
fixture_case wsl-mount wsl-mount.txt 1 "sample.txt:1: home-path"
fixture_case json-home-path json-home-path.txt 1 "$(printf 'sample.txt:1: home-path\nsample.txt:2: home-path\nsample.txt:3: home-path\nsample.txt:4: home-path\nsample.txt:5: home-path\nsample.txt:6: home-path')"
fixture_case extra-temp-path extra-temp-path.txt 1 "$(printf 'sample.txt:1: user-temp-path\nsample.txt:2: user-temp-path\nsample.txt:3: user-temp-path\nsample.txt:4: user-temp-path')"
fixture_case extra-private-ip extra-private-ip.txt 1 "$(printf 'sample.txt:1: private-ip\nsample.txt:2: private-ip\nsample.txt:3: private-ip\nsample.txt:4: private-ip')"
fixture_case private-ipv6 private-ipv6.txt 1 "$(printf 'sample.txt:1: private-ipv6\nsample.txt:2: private-ipv6\nsample.txt:3: private-ipv6\nsample.txt:4: private-ipv6')"
fixture_case loopback-v6 loopback-v6.txt 1 "$(printf 'sample.txt:1: localhost-port\nsample.txt:2: localhost-port')"
fixture_case local-hostname local-hostname.txt 1 "$(printf 'sample.txt:1: local-hostname\nsample.txt:2: local-hostname\nsample.txt:3: local-hostname\nsample.txt:4: local-hostname')"
fixture_case near-misses-stay-clean near-misses.txt 0 ""

# Not a git repo: exit 2, never a pass.
d="$root/not-a-repo"; mkdir -p "$d"; cp "$FIX/clean.txt" "$d/sample.txt"
n=$((n + 1))
out="$(cd "$d" && GIT_CEILING_DIRECTORIES="$root" "$SCAN" 2>/dev/null)"; rc=$?
if [ "$rc" = 2 ] && [ -z "$out" ]; then echo "PASS  not-a-git-repo"; else echo "FAIL  not-a-git-repo: rc=$rc out=[$out]"; fails=$((fails + 1)); fi

# A repo with no tracked files: exit 2 (an empty scan is never a pass).
check empty-repo "$(new_repo empty-repo)" 2 ""

# A repo whose only tracked files are exempt: nothing was scanned, so exit 2.
d="$(new_repo only-exempt)"; mkdir -p "$d/tools/privacy-scan-fixtures"
cp "$FIX/home-path.txt" "$d/tools/privacy-scan-fixtures/x.txt"; git -C "$d" add -A
check only-exempt-files "$d" 2 ""

# The exempt paths are exempt, and only those: a clean file beside them passes; the same text
# at any other path is a finding.
d="$(new_repo exempt-paths)"; mkdir -p "$d/tools/privacy-scan-fixtures"
cp "$FIX/home-path.txt" "$d/tools/privacy-scan-fixtures/x.txt"
cp "$FIX/home-path.txt" "$d/tools/privacy-scan.sh"
cp "$FIX/home-path.txt" "$d/tools/test-privacy-scan.sh"
cp "$FIX/clean.txt" "$d/ok.txt"; git -C "$d" add -A
check exempt-paths-pass "$d" 0 ""
d="$(new_repo non-exempt-path)"; mkdir -p "$d/tools"
cp "$FIX/home-path.txt" "$d/tools/other.sh"; git -C "$d" add -A
check non-exempt-path-flagged "$d" 1 "$(printf 'tools/other.sh:1: home-path\ntools/other.sh:2: home-path\ntools/other.sh:3: home-path')"

# Untracked files are not scanned (the contract is `git ls-files`); a tracked clean file passes.
d="$(new_repo untracked-ignored)"; cp "$FIX/clean.txt" "$d/ok.txt"; git -C "$d" add ok.txt
cp "$FIX/home-path.txt" "$d/untracked.txt"
check untracked-not-scanned "$d" 0 ""

# Arguments are a usage error: exit 2.
d="$(new_repo with-arg)"; cp "$FIX/clean.txt" "$d/ok.txt"; git -C "$d" add ok.txt
n=$((n + 1))
out="$(cd "$d" && "$SCAN" --bogus 2>/dev/null)"; rc=$?
if [ "$rc" = 2 ]; then echo "PASS  argument-is-usage-error"; else echo "FAIL  argument-is-usage-error: rc=$rc"; fails=$((fails + 1)); fi

# --- tracked FILENAMES are scanned in the normal mode (the path text itself can leak) ---
d="$(new_repo filename-leak)"; mkdir -p "$d/docs/Users"; cp "$FIX/clean.txt" "$d/docs/Users/bob.txt"; git -C "$d" add -A
check filename-leak-flagged "$d" 1 "docs/Users/bob.txt:0: home-path (filename)"
d="$(new_repo filename-email)"; cp "$FIX/clean.txt" "$d/me@example.org.txt"; git -C "$d" add -A
check filename-email-flagged "$d" 1 "me@example.org.txt:0: email (filename)"
d="$(new_repo filename-clean)"; mkdir -p "$d/docs/notes"; cp "$FIX/clean.txt" "$d/docs/notes/a b.txt"; git -C "$d" add -A
check filename-clean-passes "$d" 0 ""

# --- --history <rev-range>: commit messages, author/committer names and emails ---
NOREPLY='282918144+someone@users.noreply.github.com'
# hcommit <repo> <message> <author name> <author email> <committer name> <committer email>
hcommit() {
  GIT_AUTHOR_NAME="$3" GIT_AUTHOR_EMAIL="$4" GIT_COMMITTER_NAME="$5" GIT_COMMITTER_EMAIL="$6" \
    git -C "$1" commit -q --allow-empty -m "$2"
}
# hrepo <name>: a repo with one clean base commit tagged `base`; prints its path.
hrepo() {
  local d; d="$(new_repo "$1")"
  hcommit "$d" "base commit" Base "$NOREPLY" Base "$NOREPLY"
  git -C "$d" tag base
  printf '%s' "$d"
}

d="$(hrepo hist-clean)"
hcommit "$d" "$(printf 'Add a thing\n\nCo-Authored-By: A Model <noreply@anthropic.com>')" Dev "$NOREPLY" GitHub noreply@github.com
check_args history-clean "$d" 0 "" --history base..HEAD

d="$(hrepo hist-msg-leak)"
hcommit "$d" "$(printf 'Fix it\n\nran in /home/alice/proj and on 192.168.1.5')" Dev "$NOREPLY" Dev "$NOREPLY"
check_args history-message-leak "$d" 1 "$(printf 'SHA:message:3: home-path\nSHA:message:3: private-ip')" --history base..HEAD

d="$(hrepo hist-msg-allow)"
hcommit "$d" "$(printf 'Doc\n\nexample /home/alice/x  # privacy-scan: allow')" Dev "$NOREPLY" Dev "$NOREPLY"
check_args history-message-allow-marker "$d" 0 "" --history base..HEAD

d="$(hrepo hist-msg-email)"
hcommit "$d" "$(printf 'Doc\n\nreach me at someone@example.org')" Dev "$NOREPLY" Dev "$NOREPLY"
check_args history-message-email "$d" 1 "SHA:message:3: email" --history base..HEAD

d="$(hrepo hist-author-email)"
hcommit "$d" "ok message" Dev private@example.org Dev "$NOREPLY"
check_args history-author-email-flagged "$d" 1 "SHA:author-email:1: identity-not-allowed" --history base..HEAD

d="$(hrepo hist-committer-email)"
hcommit "$d" "ok message" Dev "$NOREPLY" Dev private@example.org
check_args history-committer-email-flagged "$d" 1 "SHA:committer-email:1: identity-not-allowed" --history base..HEAD

d="$(hrepo hist-author-name)"
hcommit "$d" "ok message" "Dev /Users/alice" "$NOREPLY" "Dev C:\\Users\\bob" "$NOREPLY"
check_args history-names-flagged "$d" 1 "$(printf 'SHA:author-name:1: home-path\nSHA:committer-name:1: windows-user-path')" --history base..HEAD

d="$(hrepo hist-allowed-id)"
mkdir -p "$d/tools"; printf '%s\n' 'listed@example.org' > "$d/tools/privacy-scan-allowed-identities.txt"; git -C "$d" add -A
hcommit "$d" "ok message" Dev listed@example.org Dev listed@example.org
check_args history-allowed-identity-file "$d" 0 "" --history base..HEAD
# the listed identity is not a finding in the tree scan either (the file that lists it must pass)
check allowed-identity-file-passes-tree-scan "$d" 0 ""

d="$(hrepo hist-allowed-id-exact)"
mkdir -p "$d/tools"; printf '%s\n' 'listed@example.org' > "$d/tools/privacy-scan-allowed-identities.txt"; git -C "$d" add -A
hcommit "$d" "ok message" Dev other-listed@example.org Dev "$NOREPLY"
check_args history-allowed-identity-is-exact "$d" 1 "SHA:author-email:1: identity-not-allowed" --history base..HEAD

d="$(hrepo hist-range-only)"
hcommit "$d" "outside the range /home/alice/x" Dev private@example.org Dev "$NOREPLY"
git -C "$d" tag mid
hcommit "$d" "clean one" Dev "$NOREPLY" Dev "$NOREPLY"
check_args history-range-excludes-older-commits "$d" 0 "" --history mid..HEAD

# History mode refuses to report a pass it did not earn: bad range, empty range, no range, odd range.
d="$(hrepo hist-bad)"
check_args history-bad-range-exit-2 "$d" 2 "" --history nosuchref..HEAD
check_args history-empty-range-exit-2 "$d" 2 "" --history HEAD..HEAD
check_args history-missing-range-exit-2 "$d" 2 "" --history
check_args history-option-like-range-exit-2 "$d" 2 "" --history --all
check_args history-extra-arg-exit-2 "$d" 2 "" --history base..HEAD extra
n=$((n + 1))
d="$root/hist-not-a-repo"; mkdir -p "$d"
out="$(cd "$d" && GIT_CEILING_DIRECTORIES="$root" "$SCAN" --history base..HEAD 2>/dev/null)"; rc=$?
if [ "$rc" = 2 ] && [ -z "$out" ]; then echo "PASS  history-not-a-git-repo"; else echo "FAIL  history-not-a-git-repo: rc=$rc out=[$out]"; fails=$((fails + 1)); fi

echo "$((n - fails))/$n passed"
[ "$fails" -eq 0 ]
