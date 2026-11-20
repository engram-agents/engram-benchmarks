#!/usr/bin/env python3
"""Name a pre-module end state as a PILOT start, on purpose, with one explicit command.

  mark-pre-module-start.py STATE --by NAME

STATE is an end state directory (a home) saved before the sandbox existed, so it has no sandbox verdict record. This command
computes STATE's store content hash with the EXISTING end-state hash helper (protected_store_hash in p1-session.py: no second
hash), prints it, and writes `<STATE>.verdict.txt` by EXCLUSIVE create (O_CREAT | O_EXCL) with exactly these four lines:

  sandbox verdict: none (pre-module state, never wrapped)
  state_sha256=<the store content hash>
  marked_by=<NAME>
  marked_at=<UTC ISO time>

Refusals (exit 2, named, nothing written): the record already exists; the state already has any `sandbox verdict:` line (in
the record beside the path as given or beside its realpath); STATE is not an existing directory; STATE has no readable store;
--by is empty or not printable on one line.

Who runs it: the study lead, per run, naming the state. Nothing calls it automatically. What the record buys: only
`p1-session.py --continue-reading --pilot-pre-module-start` accepts such a state, and only while its store still hashes to
`state_sha256`. The default reader, and so any scored launcher, refuses it. See README.md."""
import argparse, datetime, importlib.util, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
VERDICT_SUFFIX = ".verdict.txt"
NONE_LINE = "sandbox verdict: none (pre-module state, never wrapped)"


def reader():
    """p1-session.py, loaded by path (its file name has a hyphen): the one home of the end-state hash helper."""
    spec = importlib.util.spec_from_file_location("p1_session_for_marking", os.path.join(HERE, "p1-session.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def refuse(msg):
    print(f"REFUSE: {msg}", file=sys.stderr)
    return 2


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("state")
    ap.add_argument("--by", required=True, help="who names this state (the study lead)")
    a = ap.parse_args(argv)
    by = a.by.strip()
    if not by or not by.isprintable():
        return refuse("--by must be a non-empty name on one printable line")
    if not os.path.isdir(a.state):
        return refuse(f"{a.state} is not an existing directory")
    rec = os.path.abspath(a.state) + VERDICT_SUFFIX
    if os.path.lexists(rec):
        return refuse(f"the record {rec} already exists (it is never overwritten)")
    for cand in dict.fromkeys([os.path.abspath(a.state), os.path.realpath(a.state)]):
        try:
            text = open(cand + VERDICT_SUFFIX, encoding="utf-8").read()
        except OSError:
            continue
        if any(l.startswith("sandbox verdict: ") for l in text.splitlines()):
            return refuse(f"the state {a.state} already has a verdict line in {cand}{VERDICT_SUFFIX}")
    p1 = reader()
    try:
        sha = p1.protected_store_hash(a.state)[0]
    except Exception as e:  # noqa: BLE001  no store, an unreadable one: a refusal, nothing written
        return refuse(f"the store content hash of {a.state} cannot be computed ({type(e).__name__}: {e})")
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = f"{NONE_LINE}\nstate_sha256={sha}\nmarked_by={by}\nmarked_at={now}\n"
    try:
        fd = os.open(rec, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666)
    except FileExistsError:
        return refuse(f"the record {rec} already exists (it is never overwritten)")
    except OSError as e:
        return refuse(f"the record {rec} cannot be created: {e}")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(body)
    except BaseException:
        try:
            os.unlink(rec)   # only the file this call created
        except OSError:
            pass
        raise
    print(f"state_sha256={sha}")
    print(f"wrote {rec}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
