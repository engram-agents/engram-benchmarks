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

echo "$((n - fails))/$n passed"
[ "$fails" -eq 0 ]
