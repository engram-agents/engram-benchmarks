#!/usr/bin/env python3
"""public-text-check.py: fail if the repository carries text taken from a benchmark dataset.

usage: tools/public-text-check.py --dataset PATH [--expect-sha256 HEX] [--dataset PATH ...]
       tools/public-text-check.py --dataset PATH ... --history <rev-range>
       tools/public-text-check.py --rows-only [--history <rev-range>]   (row detector only)

Two detectors, keyed to the class of text and not to known members:
  verbatim      a text shares a window of 8 consecutive normalised words (lower-case, runs of
                [a-z0-9']) with ANY string value in ANY column of ANY row of a dataset given with
                --dataset (parquet). Nested values (lists, structs, JSON strings) are walked and every
                string leaf counts. The windows are built from the data at run time; nothing in this
                repository lists dataset text.
  key-fact-row  a line in the study's question-with-gold row grammar (see KEYFACT_RE). Needs no dataset.

Modes (same shape as tools/privacy-scan.sh):
  file mode     every file from `git ls-files`, as it sits in the working tree.
  history mode  every line each commit in <rev-range> ADDS (first parent for a merge), so text added in
                one commit and removed in the next is still found. Lines a commit removes are not scanned.
Files that are not UTF-8 are skipped and counted: `skipped N non-UTF-8 files` on stderr.

Output, one finding per detector per line, and NEVER the matched text (not a window, not an excerpt, not
a hash of one):
  file mode     path:line: verbatim | key-fact-row
  history mode  <12-hex commit>:<path>:added:<line>: verbatim | key-fact-row   (line = line in the new file)

Positive controls, on EVERY invocation, before anything is scanned: one per SOURCE CLASS the check claims to
cover, each planted in a temporary file and run through the real file-scan path (so a pass proves the path
end to end). A miss is exit 3 `CONTROL FAILED: <class>`; nothing is scanned. The classes:
  top-level     a string column's own value
  nested        a string inside a list, a struct or a JSON string (where conversation turns live)
  question      a string under a column or key whose name contains "question" (probing / user questions),
                wherever it sits
  key-fact-row  the row grammar (a synthetic row built at run time)
For the first three, the control is a 12-word window cut at run time from the first leaf of that class in the
loaded dataset, never hard-coded. A dataset with no such leaf is exit 3 `DATASET PROBLEM ... class <class>`.

--expect-sha256 HEX pairs in order with --dataset: a mismatch, an unreadable or an empty dataset is exit 3
with a named line. Without --dataset the verbatim detector cannot run: exit 2 unless --rows-only, which
says `verbatim detector NOT RUN` on stderr.

Exit codes: 0 clean; 1 findings; 2 usage error, not a git repo, bad range, I/O error, or nothing to scan
(an empty scan is never a pass); 3 control failure or dataset problem.

Exempt by path: tools/public-text-check-fixtures/ and the two list files below (they hold shas, paths and
hashes, never text). The `privacy-scan: allow` marker does NOT exempt a line here.

Exempt windows (both modes). tools/public-text-check-exempt-windows.txt lists, one per line,
    <sha256 of the normalised window> -- <reason> -- approved: <seat and reference>
(blank lines and lines starting with # are comments). The normalised window is the 8 lower-cased [a-z0-9']
words joined by single spaces. A verbatim window whose sha256 is listed is not a hit; every OTHER window on
the same line still counts. The exemption is by content hash, never by path. A malformed entry (no reason, no
approved field, a hash that is not 64 hex digits) is exit 2; an entry that matched nothing in the scan is a NOTE
on stderr. A hash is computed only for a window that hits. Adding an entry needs a second seat's read.
`--print-hit-hashes` (a local helper for preparing entries) prints `<path>:<line>: <sha256>` for each verbatim
hit, and never the text; it is the only output that shows a window's hash.

Every run prints its bound on stderr: the window, the exemptions and acknowledgements in force, and the
negative control that justified the window (NEGATIVE_CONTROL).

Acknowledged history (history mode ONLY). Findings that are known and kept by decision are listed in
tools/public-text-check-acknowledged.txt, one per line:
    <full 40-hex commit sha> <path> -- <reason>        (blank lines and lines starting with # are comments)
A finding whose (commit, path) pair is listed is not a finding: it is printed as
`acknowledged: <12-hex>:<path> (<n> lines)`, never with its text, and does not change the exit code. File mode
ignores the list entirely: nothing at a tip is ever exempt. A malformed entry (no reason, no path, a sha that is
not 40 hex digits, a sha that is not a commit here) is exit 2. A listed pair that produced no finding in the
scanned range is a NOTE on stderr, not a failure, because ranges differ between runs. The list is default-deny:
anything not listed, including the same path in another commit, is a finding.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

WINDOW = 8           # consecutive normalised words that make a verbatim hit
CONTROL_WORDS = 12   # words in the positive-control probe
WORD_RE = re.compile(r"[a-z0-9']+")
KEYFACT_RE = re.compile(r"^[AF][0-9]+ \| ex[0-9]+ \|.*\|\|")
EXEMPT_PREFIX = "tools/public-text-check-fixtures/"
ACK_PATH = "tools/public-text-check-acknowledged.txt"
EXEMPT_PATH = "tools/public-text-check-exempt-windows.txt"
# Where and when the window was measured against this repository's own text; a constant, not a computation.
NEGATIVE_CONTROL = ("negative control: this repository's own prose and code, measured on study/beam-tuning-log-2 "
                    "at bc0aca7, 2026-11-19: 2 windows at 8 words (both exempt), 0 at 9")
SHA40_RE = re.compile(r"^[0-9a-fA-F]{40}$")
CONTROL_CLASSES = ("top-level", "nested", "question")
HEX64_RE = re.compile(r"^[0-9a-fA-F]{64}$")
HUNK_RE = re.compile(rb"^@@ -[0-9]+(?:,[0-9]+)? \+([0-9]+)(?:,[0-9]+)? @@")


class UsageError(Exception):
    pass


class AckError(Exception):
    """A malformed entry in one of the two list files; the exit code is 2."""


class DatasetError(Exception):
    """Carries the full line to print; the exit code is 3."""


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise UsageError(message)


# Run state for the exempt-window list; main() resets it. Module-level so detect_verbatim keeps its signature.
EXEMPT = {}          # sha256 of a normalised window -> reason
EXEMPT_USED = set()  # the listed hashes that a scan actually met
HIT_HASHES = []      # (line, sha256) for each verbatim hit, drained by the --print-hit-hashes helper


def norm_words(text):
    return WORD_RE.findall(text.lower())


# ------------------------------------------------------------------ detectors
# Both take `items`: a list of (line number, line text). They return the sorted line numbers that hit.

def detect_verbatim(items, windows):
    words, lines = [], []
    for lineno, text in items:
        for w in norm_words(text):
            words.append(w)
            lines.append(lineno)
    hits = set()
    for i in range(len(words) - WINDOW + 1):
        window = " ".join(words[i:i + WINDOW])
        if hash(window) not in windows:
            continue
        digest = hashlib.sha256(window.encode("utf-8")).hexdigest()  # only for a window that hits
        if digest in EXEMPT:
            EXEMPT_USED.add(digest)
            continue
        hits.add(lines[i])
        HIT_HASHES.append((lines[i], digest))
    return sorted(hits)


def drain_hit_hashes():
    out = sorted(set(HIT_HASHES))
    del HIT_HASHES[:]
    return out


def detect_keyfact(items):
    return sorted({lineno for lineno, text in items if KEYFACT_RE.match(text)})


# ------------------------------------------------------------------ datasets

def walk_leaves(value, nested=False, question=False):
    """Yield (string, nested, question) for every string leaf of a nested value.

    nested: the leaf sits inside a container or inside a string that parsed as JSON.
    question: the leaf sits under a column or key whose name contains "question".
    A string that is itself JSON is walked as well as counted.
    """
    if isinstance(value, str):
        yield value, nested, question
        if value[:1] in ("{", "["):
            try:
                parsed = json.loads(value)
            except (ValueError, RecursionError):
                return
            yield from walk_leaves(parsed, True, question)
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from walk_leaves(k, True, question)
            yield from walk_leaves(v, True, question or (isinstance(k, str) and "question" in k.lower()))
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from walk_leaves(v, True, question)


def classes_of(nested, question):
    return [("nested" if nested else "top-level")] + (["question"] if question else [])


def leaf_is_indexed(nested, question):
    """Which leaves feed the window set. Every one does; the tests and the mutants break exactly this."""
    return True


def load_dataset(path, expect):
    """Return (windows, probes) with one run-time probe per control class. Raise DatasetError (exit 3) on any identity or readability problem."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        raise DatasetError(f"DATASET PROBLEM: {path}: unreadable")
    if expect is not None and h.hexdigest() != expect.lower():
        raise DatasetError(f"DATASET MISMATCH: {path}: sha256 {h.hexdigest()} is not the expected value")
    try:
        import pyarrow.parquet as pq
    except ImportError:
        raise DatasetError(f"DATASET PROBLEM: {path}: pyarrow is not installed")
    windows, probes, nrows = set(), {}, 0
    try:
        pf = pq.ParquetFile(path)
        for batch in pf.iter_batches(batch_size=256):
            for row in batch.to_pylist():
                nrows += 1
                for col, value in row.items():
                    for leaf, nested, question in walk_leaves(value, False, "question" in str(col).lower()):
                        ws = norm_words(leaf)
                        if len(ws) >= CONTROL_WORDS:
                            for cls in classes_of(nested, question):
                                probes.setdefault(cls, " ".join(ws[:CONTROL_WORDS]))  # drawn before indexing
                        if not leaf_is_indexed(nested, question):
                            continue
                        for i in range(len(ws) - WINDOW + 1):
                            windows.add(hash(" ".join(ws[i:i + WINDOW])))
    except Exception:  # any reader failure is "unreadable"; the message is withheld on purpose
        raise DatasetError(f"DATASET PROBLEM: {path}: unreadable")
    if nrows == 0:
        raise DatasetError(f"DATASET PROBLEM: {path}: empty (no rows)")
    for cls in CONTROL_CLASSES:
        if cls not in probes:
            raise DatasetError(f"DATASET PROBLEM: {path}: no leaf of at least {CONTROL_WORDS} words for class {cls}, "
                               "so no positive control can be built")
    return windows, probes


# ------------------------------------------------------------------ git helpers

def git(top, *args):
    return subprocess.run(["git", "-c", "core.quotePath=false", *args], cwd=top, capture_output=True)


def label_safe(s):
    return s.replace("\n", "?").replace("\r", "?")


def is_exempt(path):
    return path.startswith(EXEMPT_PREFIX) or path in (ACK_PATH, EXEMPT_PATH)


def load_exempt(top):
    """{sha256: reason} from the exempt-window list. Raise AckError (exit 2) on a bad entry."""
    full = os.path.join(top, EXEMPT_PATH)
    if not os.path.exists(full):
        return {}
    try:
        with open(full, "rb") as fh:
            text = fh.read().decode("utf-8-sig")
    except (OSError, UnicodeDecodeError):
        raise AckError(f"exempt windows list: cannot read {EXEMPT_PATH} as UTF-8")
    entries = {}
    for n, raw in enumerate(text.split("\n"), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [x.strip() for x in line.split(" -- ")]
        if not HEX64_RE.match(parts[0]):
            raise AckError(f"exempt windows list: line {n}: the hash must be 64 hex digits")
        if len(parts) < 2 or not parts[1]:
            raise AckError(f"exempt windows list: line {n}: no reason "
                           "(expected '<sha256> -- <reason> -- approved: <seat and reference>')")
        approved = parts[-1]
        if len(parts) < 3 or not approved.startswith("approved:") or not approved[len("approved:"):].strip():
            raise AckError(f"exempt windows list: line {n}: no approved field "
                           "(expected '<sha256> -- <reason> -- approved: <seat and reference>')")
        entries[parts[0].lower()] = " -- ".join(parts[1:-1])
    return entries


def load_ack(top):
    """{(full lower-case sha, path): reason} from the acknowledged-history list. Raise AckError on a bad entry."""
    full = os.path.join(top, ACK_PATH)
    if not os.path.exists(full):
        return {}
    try:
        with open(full, "rb") as fh:
            text = fh.read().decode("utf-8-sig")
    except (OSError, UnicodeDecodeError):
        raise AckError(f"acknowledged list: cannot read {ACK_PATH} as UTF-8")
    entries = {}
    for n, raw in enumerate(text.split("\n"), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        head, sep, reason = line.partition(" -- ")
        if not sep or not reason.strip():
            raise AckError(f"acknowledged list: line {n}: no reason (expected '<sha> <path> -- <reason>')")
        parts = head.split(" ", 1)
        if len(parts) < 2 or not parts[1].strip():
            raise AckError(f"acknowledged list: line {n}: no path (expected '<sha> <path> -- <reason>')")
        sha, path = parts[0], parts[1].strip()
        if not SHA40_RE.match(sha):
            raise AckError(f"acknowledged list: line {n}: the sha must be the full 40 hex digits")
        if git(top, "cat-file", "-e", sha + "^{commit}").returncode != 0:
            raise AckError(f"acknowledged list: line {n}: {sha[:12]} is not a commit in this repository")
        entries[(sha.lower(), path)] = reason.strip()
    return entries


def to_items(numbered):
    return [(n, t.rstrip("\r")) for n, t in numbered]


def findings_for(items, windows):
    """[(line, detector)] sorted by line, verbatim before key-fact-row on the same line."""
    found = []
    if windows is not None:
        found += [(n, 0, "verbatim") for n in detect_verbatim(items, windows)]
    found += [(n, 1, "key-fact-row") for n in detect_keyfact(items)]
    return [(n, name) for n, _, name in sorted(found)]


# ------------------------------------------------------------------ the scan

def decode(data):
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None


def scan_file(full, windows):
    """The one file-scan path, used for tracked files and for the controls: (status, findings).

    status is "ok", "unreadable" or "non-utf8"; findings is [(line, detector)].
    """
    try:
        with open(full, "rb") as fh:
            data = fh.read()
    except OSError:
        return "unreadable", []
    text = decode(data)
    if text is None:
        return "non-utf8", []
    return "ok", findings_for(to_items(enumerate(text.split("\n"), 1)), windows)


def plant_and_scan(text, windows):
    """Plant `text` on line 2 of a temporary file and scan that file through scan_file."""
    with tempfile.TemporaryDirectory() as d:
        full = os.path.join(d, "control.txt")
        with open(full, "w", encoding="utf-8") as fh:
            fh.write("filler line\n" + text + "\n")
        return scan_file(full, windows)


def scan_files(top, windows, state):
    r = git(top, "ls-files", "-z")
    if r.returncode != 0:
        print("public-text-check: cannot list tracked files", file=sys.stderr)
        state["io_error"] = True
        return
    for raw in r.stdout.split(b"\0"):
        if not raw:
            continue
        path = os.fsdecode(raw)
        if is_exempt(path):
            continue
        full = os.path.join(top, path)
        if os.path.isdir(full):  # a submodule entry: no file content here
            continue
        drain_hit_hashes()
        status, found = scan_file(full, windows)
        hashes = drain_hit_hashes() if state["print_hashes"] else []
        if status == "unreadable":
            print(f"public-text-check: cannot read tracked file: {label_safe(path)}", file=sys.stderr)
            state["io_error"] = True
            continue
        if status == "non-utf8":
            state["skipped"] += 1
            continue
        state["scanned"] += 1
        for n, name in found:
            print(f"{label_safe(path)}:{n}: {name}")
            state["findings"] += 1
        for n, digest in hashes:
            print(f"{label_safe(path)}:{n}: {digest}")


def added_lines(top, sha, short, state):
    """{path: [(new-file line number, bytes)]} for every line the commit adds; None on a git failure."""
    pr = git(top, "show", "--no-color", "--no-ext-diff", "--no-textconv", "--no-renames",
             "--diff-merges=first-parent", "--name-only", "-z", "--format=", sha)
    dr = git(top, "show", "-a", "--no-color", "--no-ext-diff", "--no-textconv", "--no-renames", "--unified=0",
             "--diff-merges=first-parent", "--format=", sha)
    if pr.returncode != 0 or dr.returncode != 0:
        print(f"public-text-check: cannot read commit {short}", file=sys.stderr)
        state["io_error"] = True
        return None
    plist = [os.fsdecode(p) for p in pr.stdout.split(b"\0") if p]
    out, idx, path, inhdr, cur = {}, -1, None, False, 0
    for line in dr.stdout.split(b"\n"):
        if line.startswith(b"diff --git "):
            idx += 1
            if idx >= len(plist):
                print(f"public-text-check: diff and path list disagree for commit {short}", file=sys.stderr)
                state["io_error"] = True
                return None
            path, inhdr = plist[idx], True
        elif inhdr:
            m = HUNK_RE.match(line)
            if m:
                inhdr, cur = False, int(m.group(1))
        elif line.startswith(b"@@ "):
            m = HUNK_RE.match(line)
            if m:
                cur = int(m.group(1))
        elif line.startswith(b"+"):
            out.setdefault(path, []).append((cur, line[1:]))
            cur += 1
    return out


def scan_history(top, shas, windows, state, ack):
    matched = set()
    for sha in shas:
        short = sha[:12]
        state["scanned"] += 1
        files = added_lines(top, sha, short, state)
        if files is None:
            continue
        for path, numbered in files.items():
            if is_exempt(path):
                continue
            text = decode(b"\n".join(b for _, b in numbered))
            if text is None:
                state["skipped"] += 1
                continue
            items = to_items(zip((n for n, _ in numbered), text.split("\n")))
            drain_hit_hashes()
            found = findings_for(items, windows)
            hashes = drain_hit_hashes() if state["print_hashes"] else []
            if found and (sha.lower(), path) in ack:
                matched.add((sha.lower(), path))
                print(f"acknowledged: {short}:{label_safe(path)} ({len(found)} lines)")
                state["acknowledged"] += 1
                continue
            for n, name in found:
                print(f"{short}:{label_safe(path)}:added:{n}: {name}")
                state["findings"] += 1
            for n, digest in hashes:
                print(f"{short}:{label_safe(path)}:added:{n}: {digest}")
    for sha, path in ack:
        if (sha, path) not in matched:
            print(f"public-text-check: NOTE: acknowledged entry matched no finding in this range: "
                  f"{sha[:12]}:{label_safe(path)}", file=sys.stderr)


# ------------------------------------------------------------------ entry point

def parse(argv):
    p = _Parser(prog="public-text-check.py", allow_abbrev=False, add_help=False)
    p.add_argument("--dataset", action="append", default=[])
    p.add_argument("--expect-sha256", action="append", default=[], dest="expect")
    p.add_argument("--rows-only", action="store_true")
    p.add_argument("--history", default=None)
    p.add_argument("--print-hit-hashes", action="store_true", dest="print_hashes")
    args = p.parse_args(argv)
    if args.history is not None and (not args.history or args.history.startswith("-")):
        raise UsageError("--history needs a revision range")
    if args.rows_only and args.dataset:
        raise UsageError("--rows-only and --dataset contradict each other")
    if not args.rows_only and not args.dataset:
        raise UsageError("no --dataset: the verbatim detector cannot run (use --rows-only for the row detector alone)")
    if args.expect and len(args.expect) != len(args.dataset):
        raise UsageError("--expect-sha256 pairs with --dataset in order: give one for each, or none")
    for e in args.expect:
        if not HEX64_RE.match(e):
            raise UsageError("--expect-sha256 takes 64 hex digits")
    return args


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    EXEMPT.clear()
    EXEMPT_USED.clear()
    del HIT_HASHES[:]
    try:
        args = parse(argv)
    except UsageError as e:
        print(f"public-text-check: {e}", file=sys.stderr)
        print("usage: tools/public-text-check.py (--dataset PATH [--expect-sha256 HEX])... | --rows-only "
              "[--history <rev-range>]", file=sys.stderr)
        return 2

    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if r.returncode != 0:
        print("public-text-check: not inside a git repository; refusing to report a pass", file=sys.stderr)
        return 2
    top = r.stdout.strip()

    shas = []
    if args.history is not None:
        rl = git(top, "rev-list", args.history)
        if rl.returncode != 0:
            print(f"public-text-check: bad revision range: {label_safe(args.history)}", file=sys.stderr)
            return 2
        shas = rl.stdout.decode().split()

    # datasets: identity first, then the positive controls, all before anything is scanned
    loaded = []
    if args.rows_only:
        print("public-text-check: verbatim detector NOT RUN (--rows-only)", file=sys.stderr)
    for i, path in enumerate(args.dataset):
        expect = args.expect[i] if args.expect else None
        if expect is None:
            print(f"public-text-check: dataset identity NOT CHECKED for {path} (no --expect-sha256)", file=sys.stderr)
        try:
            loaded.append(load_dataset(path, expect))
        except DatasetError as e:
            print(str(e), file=sys.stderr)
            return 3
    windows = None
    if loaded:
        windows = set()
        for ds_windows, _ in loaded:
            windows |= ds_windows
    failed = []
    for ds_windows, probes in loaded:
        for cls in CONTROL_CLASSES:
            status, found = plant_and_scan("noise " + probes[cls] + " noise", ds_windows)
            if status == "ok" and (2, "verbatim") in found:
                print(f"public-text-check: control ok: {cls}", file=sys.stderr)
            else:
                failed.append(cls)
    status, found = plant_and_scan("F1 | ex1 | information_extraction | Q? " + "||" + " A.", None)
    if status == "ok" and (2, "key-fact-row") in found:
        print("public-text-check: control ok: key-fact-row", file=sys.stderr)
    else:
        failed.append("key-fact-row")
    if failed:
        for cls in failed:
            print(f"CONTROL FAILED: {cls}", file=sys.stderr)
        print("public-text-check: nothing scanned", file=sys.stderr)
        return 3

    ack = {}
    if args.history is not None:  # file mode never reads the list
        try:
            ack = load_ack(top)
        except AckError as e:
            print(f"public-text-check: {e}", file=sys.stderr)
            return 2
    try:
        exempt = load_exempt(top)
    except AckError as e:
        print(f"public-text-check: {e}", file=sys.stderr)
        return 2
    EXEMPT.update(exempt)  # after the controls: a control is never exempt
    print(f"public-text-check: window {WINDOW} words; exemptions {len(exempt)} (by content hash); "
          f"acknowledged history {len(ack)}; {NEGATIVE_CONTROL}", file=sys.stderr)
    state = {"scanned": 0, "skipped": 0, "findings": 0, "acknowledged": 0, "io_error": False,
             "print_hashes": args.print_hashes}
    if args.history is None:
        scan_files(top, windows, state)
        what = "files"
    else:
        scan_history(top, shas, windows, state, ack)
        what = "commits"
    sys.stdout.flush()
    if windows is not None:
        for digest in exempt:
            if digest not in EXEMPT_USED:
                print(f"public-text-check: NOTE: exempt-window entry matched nothing in this scan: {digest[:12]}",
                      file=sys.stderr)
    print(f"skipped {state['skipped']} non-UTF-8 files", file=sys.stderr)
    if state["io_error"]:
        return 2
    if state["scanned"] == 0:
        print("public-text-check: nothing to scan (empty tracked set, only exempt or non-UTF-8 files, or an "
              "empty range); refusing to report a pass", file=sys.stderr)
        return 2
    if state["findings"]:
        extra = f" ({state['acknowledged']} acknowledged)" if state["acknowledged"] else ""
        print(f"public-text-check: {state['findings']} finding(s) in {state['scanned']} {what}{extra}", file=sys.stderr)
        return 1
    extra = f", {state['acknowledged']} acknowledged" if state["acknowledged"] else ""
    print(f"public-text-check: clean ({state['scanned']} {what}{extra})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
