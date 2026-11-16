#!/usr/bin/env python3
"""Check that a ported copy of the exam harness shows the student exactly what a reference copy shows.
This file is the study's harness, not shipped product code.

usage: check-port-identity.py --reference-sha SHA256 REFERENCE_DIR PORTED_DIR

--reference-sha is REQUIRED: the sha256 of the feed.py the runs actually used, as the setup record pins it. The
check refuses (exit 2) a reference whose feed.py has any other hash. Added 2026-11-16: on 2026-11-14 this check
passed against the copy the port was made FROM, while the runs used a later copy with one more sentence in the
brief; comparing two files proves nothing about which file ran.

Each directory holds feed.py and feed2.py. Per directory (in its own subprocess, so the two copies
never share the module name `feed`) this computes sha256 of:
  BRIEF, PROCTOR, TURN_LINE, FACT_SHEET, NUDGE, the question prompt prefix, render(...) and
  exchanges(...) on a fixed synthetic conversation built in memory (the real dataset is never read);
and then compares them. It also compares every string literal in the two source files as a MULTISET,
in both directions: a literal (or a copy of a duplicated literal) present in the reference but missing
from the ported copy fails, and so does a literal the port has beyond the reference. Docstrings are
left out, and so are the host-configuration literals the port replaces (HOST_CONFIG_*) and the few
literals the port legitimately adds (PORT_ADDS, below). That comparison is what covers
student-visible text assembled inside main() ("/compact", ...).
The question prompt prefix is one named constant in the port (feed.QUESTION_PREFIX). The reference
spells it as literals at three sites (LEGACY_QUESTION_FRAGMENTS); those literals must be
present there, and the two copies are then compared through the prefix hash.
Exit 0 = identical, 1 = differs, 2 = usage/IO error.
"""
import ast, collections, hashlib, json, os, subprocess, sys, types

# Literals the port may replace, because they name host configuration or a host path.
HOST_CONFIG_MARKERS = ("localhost", "beam-data", "100K.parquet")
HOST_CONFIG_EXACT = {".."}  # the path-join fragment of the removed default data path

# The question prompt prefix as the reference spells it: literal fragments, per file and per site.
# What a student receives is feed.py: PREFIX + question; feed2.py: PROCTOR + " " + PREFIX + question.
QUESTION_PREFIX_TEXT = "The conversation is over. Answer this question about it, from your record and memory:\n\n"
LEGACY_QUESTION_FRAGMENTS = {  # (implicit string concatenation is one literal to ast)
    "feed.py": [QUESTION_PREFIX_TEXT],
    "feed2.py": [" " + QUESTION_PREFIX_TEXT] * 2,
}

# Literals the port legitimately adds (counted: a second copy is reported). The env-var names and the
# data_path() message replace the removed hard-coded data path; the two " " are the joins in
# PROCTOR + " " + QUESTION_PREFIX at feed2's two question sites; QUESTION_PREFIX_TEXT is the constant itself.
PORT_ADDS = {
    "feed.py": collections.Counter({
        "BEAM_OLLAMA_URL": 1, "BEAM_PARQUET": 1,
        "set BEAM_PARQUET to the path of the BEAM 100K parquet file": 1,
        "/api/generate": 1,  # in the reference this is part of a host-config literal (the full endpoint URL)
        QUESTION_PREFIX_TEXT: 1,
    }),
    "feed2.py": collections.Counter({" ": 2}),
}


def sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def synthetic_conversation():
    return {"chat": [
        [{"role": "user", "content": "u1 line one\nline two", "time_anchor": "January-01-2024"},
         {"role": "assistant", "content": "a1 reply"},
         {"role": "user", "content": "u2"},
         {"role": "assistant", "content": "a2 reply"}],
        [{"role": "user", "content": "u3", "time_anchor": "March-05-2024"},
         {"role": "assistant", "content": "a3 reply"},
         {"role": "assistant", "content": "orphan assistant message, no pending user"}],
    ]}


def emit(directory):
    """Child mode: import the copy in DIRECTORY and print its hashes as JSON."""
    if "pyarrow" not in sys.modules:
        try:
            import pyarrow.parquet  # noqa: F401
        except ImportError:  # the check never reads parquet; a stub lets the modules import
            pa = types.ModuleType("pyarrow"); pq = types.ModuleType("pyarrow.parquet")
            pa.parquet = pq; sys.modules["pyarrow"] = pa; sys.modules["pyarrow.parquet"] = pq
    sys.path.insert(0, os.path.abspath(directory))
    import feed, feed2  # noqa: E401
    legacy = not hasattr(feed, "QUESTION_PREFIX")  # the reference layout: no named constant
    out = {
        "BRIEF": sha(feed.BRIEF), "PROCTOR": sha(feed.PROCTOR),
        "TURN_LINE": sha(feed.TURN_LINE), "FACT_SHEET": sha(feed2.FACT_SHEET), "NUDGE": sha(feed2.NUDGE),
        "QUESTION_PREFIX": sha(QUESTION_PREFIX_TEXT if legacy else feed.QUESTION_PREFIX),
        "feed2.BRIEF is feed.BRIEF": feed2.BRIEF is feed.BRIEF,
        "feed2 uses feed's QUESTION_PREFIX": legacy or feed2.QUESTION_PREFIX is feed.QUESTION_PREFIX,
        "render": sha(feed.render(7, 2, "March-05-2024", "user text\nmore", "assistant text")),
        "exchanges": sha(json.dumps(feed.exchanges(synthetic_conversation()))),
        "_legacy_question_prefix": legacy,
    }
    print(json.dumps(out))


def literals(path):
    """Multiset (Counter) of the non-docstring string literals of a source file."""
    tree = ast.parse(open(path).read())
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str)):
                docs.add(id(node.body[0].value))
    return collections.Counter(
        n.value for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs
        and n.value not in HOST_CONFIG_EXACT and not any(m in n.value for m in HOST_CONFIG_MARKERS))


def main(argv):
    if len(argv) == 3 and argv[1] == "--emit":
        emit(argv[2]); return 0
    if len(argv) != 5 or argv[1] != "--reference-sha":
        print(__doc__, file=sys.stderr); return 2
    pinned, ref, port = argv[2].lower(), argv[3], argv[4]
    try:
        got = hashlib.sha256(open(os.path.join(ref, "feed.py"), "rb").read()).hexdigest()
    except OSError as e:
        print(f"cannot read the reference feed.py: {e}", file=sys.stderr); return 2
    if got != pinned:
        print(f"REFUSE: the reference feed.py has sha256 {got}, not the pinned {pinned} (the copy the runs used)",
              file=sys.stderr)
        return 2
    print(f"reference feed.py sha256 {got} == pinned")
    results = []
    for d in (ref, port):
        for f in ("feed.py", "feed2.py"):
            if not os.path.isfile(os.path.join(d, f)):
                print(f"missing {os.path.join(d, f)}", file=sys.stderr); return 2
        p = subprocess.run([sys.executable, "-B", "-I", os.path.abspath(__file__), "--emit", d],
                           capture_output=True, text=True)
        if p.returncode != 0:
            print(f"could not load {d}: {p.stderr[-800:]}", file=sys.stderr); return 2
        results.append(json.loads(p.stdout))
    bad = 0
    for k in results[0]:
        if k.startswith("_"):
            continue
        same = results[0][k] == results[1].get(k)
        print(f"{'same  ' if same else 'DIFFER'}  {k}")
        bad += not same
    for f in ("feed.py", "feed2.py"):
        sides = []
        for d, res in ((ref, results[0]), (port, results[1])):
            lits = literals(os.path.join(d, f))
            if res["_legacy_question_prefix"]:
                # The reference's fragments must be there (else the reference changed), then they leave the
                # comparison: the question prefix is compared through its hash above.
                frag = collections.Counter(LEGACY_QUESTION_FRAGMENTS[f])
                if frag - lits:
                    print(f"DIFFER  {os.path.join(d, f)}: the question prefix fragments are not as expected: "
                          f"{sorted(map(repr, (frag - lits).elements()))}")
                    bad += 1
                lits = lits - frag
            sides.append(lits)
        missing = sides[0] - sides[1]
        # The allowance exists only against a reference that predates the port's additions.
        allowed = PORT_ADDS[f] if results[0]["_legacy_question_prefix"] else collections.Counter()
        extra = (sides[1] - sides[0]) - allowed
        for s in sorted(missing.elements()):
            print(f"DIFFER  {f}: literal (or one copy of it) missing from the port: {s[:90]!r}")
        for s in sorted(extra.elements()):
            print(f"DIFFER  {f}: literal (or one extra copy) only in the port: {s[:90]!r}")
        n = sum(missing.values()) + sum(extra.values())
        bad += n
        print(f"{'same  ' if not n else 'DIFFER'}  {f}: string literals match as a multiset")
    print("RESULT:", "identical" if not bad else f"{bad} difference(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
