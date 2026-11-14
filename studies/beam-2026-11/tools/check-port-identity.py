#!/usr/bin/env python3
"""Check that a ported copy of the exam harness shows the student exactly what a reference copy shows.
This file is the study's harness, not shipped product code.

usage: check-port-identity.py REFERENCE_DIR PORTED_DIR

Each directory holds feed.py and feed2.py. Per directory (in its own subprocess, so the two copies
never share the module name `feed`) this computes sha256 of:
  BRIEF, PROCTOR, TURN_LINE, FACT_SHEET, NUDGE, render(...) and exchanges(...) on a fixed synthetic
  conversation built in memory (the real dataset is never read);
and then compares them. It also compares every string literal in the two source files: a literal
present in the reference but missing from the ported copy fails the check, unless it is a docstring or
one of the host-configuration literals that the port is allowed to replace. That literal comparison is
what covers student-visible text assembled inside main() (the question prefix, "/compact", ...).
Exit 0 = identical, 1 = differs, 2 = usage/IO error.
"""
import ast, hashlib, json, os, subprocess, sys, types

# Literals the port may drop, because they name host configuration or a host path.
HOST_CONFIG_MARKERS = ("localhost", "beam-data", "100K.parquet")
HOST_CONFIG_EXACT = {".."}  # the path-join fragment of the removed default data path


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
    out = {
        "BRIEF": sha(feed.BRIEF), "PROCTOR": sha(feed.PROCTOR),
        "TURN_LINE": sha(feed.TURN_LINE), "FACT_SHEET": sha(feed2.FACT_SHEET), "NUDGE": sha(feed2.NUDGE),
        "feed2.BRIEF is feed.BRIEF": feed2.BRIEF is feed.BRIEF,
        "render": sha(feed.render(7, 2, "March-05-2024", "user text\nmore", "assistant text")),
        "exchanges": sha(json.dumps(feed.exchanges(synthetic_conversation()))),
    }
    print(json.dumps(out))


def literals(path):
    tree = ast.parse(open(path).read())
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str)):
                docs.add(id(node.body[0].value))
    return {n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs}


def main(argv):
    if len(argv) == 3 and argv[1] == "--emit":
        emit(argv[2]); return 0
    if len(argv) != 3:
        print(__doc__, file=sys.stderr); return 2
    ref, port = argv[1], argv[2]
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
        same = results[0][k] == results[1].get(k)
        print(f"{'same  ' if same else 'DIFFER'}  {k}")
        bad += not same
    for f in ("feed.py", "feed2.py"):
        dropped = sorted(s for s in literals(os.path.join(ref, f)) - literals(os.path.join(port, f))
                         if s not in HOST_CONFIG_EXACT and not any(m in s for m in HOST_CONFIG_MARKERS))
        for s in dropped:
            print(f"DIFFER  {f}: literal missing from the port: {s[:90]!r}")
        bad += len(dropped)
        print(f"{'same  ' if not dropped else 'DIFFER'}  {f}: every non-host string literal survives")
    print("RESULT:", "identical" if not bad else f"{bad} difference(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
