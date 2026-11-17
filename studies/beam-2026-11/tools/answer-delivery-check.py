#!/usr/bin/env python3
"""Answer-delivery check (BEAM P1 answering). This file is the study's harness, not shipped product code.

Reads the per-turn JSONL that feed4.py wrote for an answering run (turns.jsonl) and the frozen question file given to
feed4.py --question-file, and prints PASS only if ALL of these hold:
  1. the session_id on every turn equals the resumed session id given with --session;
  2. exactly one compact turn exists and it precedes the first question turn;
  3. every id in the question file appears exactly once, in file order;
  4. there are no other question turns (an id not in the file, or a practice question);
  5. there are no reading turns (exchange or setup): an answering run resumes, compacts, then asks.
Every failure is printed. Exit 0 on PASS, 1 on any failure (including an unreadable input).

usage: answer-delivery-check.py --turns RUN/turns.jsonl --questions QUESTIONS.json --session SESSION_ID
"""
import argparse, json, sys


def load_rows(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except ValueError as e:
                    raise ValueError(f"{path} line {n} is not JSON: {e}")
    return rows


def check(rows, question_ids, session):
    """Return the list of failure strings (empty = PASS)."""
    bad = []
    # rule 1: one session for every turn
    for r in rows:
        if r.get("session_id") != session:
            bad.append(f"session id differs on turn i={r.get('i')} ({r.get('kind')}): "
                       f"{r.get('session_id')!r} != resumed {session!r}")
    kinds = [r.get("kind") for r in rows]
    qpos = [n for n, k in enumerate(kinds) if k == "question"]
    first_q = qpos[0] if qpos else len(rows)
    # rule 2: exactly one compact turn, before the first question
    compacts = [n for n, k in enumerate(kinds) if k == "compact"]
    before = [n for n in compacts if n < first_q]
    if len(before) == 0:
        bad.append("compact missing before the first question" if not compacts else
                   "compact turn comes after a question (none precedes the first question)")
    elif len(before) > 1:
        bad.append(f"{len(before)} compact turns precede the first question (exactly one expected)")
    if len(compacts) > len(before) and before:
        bad.append("extra compact turn after a question")
    # rule 3 and 4: ids once each, in file order; nothing else asked
    wanted = set(question_ids)
    got = [rows[n].get("id") for n in qpos]
    for qid in got:
        if qid not in wanted:
            bad.append(f"other question turn (id {qid!r} is not in the question file)")
    for r in rows:
        if r.get("kind") == "practice-question":
            bad.append(f"other question turn (practice question at i={r.get('i')})")
    for qid in question_ids:
        c = got.count(qid)
        if c == 0:
            bad.append(f"missing id {qid!r}")
        elif c > 1:
            bad.append(f"duplicate id {qid!r} ({c} times)")
    in_file = [q for q in got if q in wanted]
    seen = []
    for q in in_file:
        if q not in seen:
            seen.append(q)
    expect = [q for q in question_ids if q in seen]
    if seen != expect:
        bad.append(f"ids out of file order: delivered {seen}, file order {expect}")
    # rule 5: no reading turns
    for r in rows:
        if r.get("kind") in ("exchange", "setup"):
            bad.append(f"reading turn present (kind {r.get('kind')!r}, i={r.get('i')})")
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", required=True); ap.add_argument("--questions", required=True)
    ap.add_argument("--session", required=True, help="the resumed session id the run was given")
    args = ap.parse_args()
    try:
        rows = load_rows(args.turns)
        with open(args.questions, encoding="utf-8") as f:
            qs = json.load(f)
        ids = [q["id"] for q in qs]
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"FAIL: cannot read inputs: {e}")
        return 1
    bad = check(rows, ids, args.session)
    for b in bad:
        print("FAIL:", b)
    print("PASS" if not bad else f"FAIL ({len(bad)} problem(s))")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
