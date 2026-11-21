#!/usr/bin/env python3
"""Reading-delivery check (BEAM P1b continue-reading). This file is the study's harness, not shipped product code.

answer-delivery-check.py cannot check a reading run (its rule 5 refuses every reading turn, and it wants a compact and
questions), so the continue-reading mode has its own check. It reads the per-turn JSONL feed4.py wrote (turns.jsonl),
the PLAN the launcher checked before the run (plan.json: the feeder's --dump-plan output) and the stream-json event log
(events.jsonl), and prints PASS only if ALL of these hold:
  1. the session_id on every turn equals the resumed session id given with --session;
  2. every turn is a reading turn (kind exchange): no compact, question, setup or practice turn;
  3. the turns are exactly the planned messages: the same count, and turn n carries the exchanges of planned message n,
     so every planned message was delivered once, in plan order;
  4. no turn has is_error, timeout or eof true;
  5. the event stream holds exactly one result event per planned message.
An empty plan is not a pass. Every failure is printed. Exit 0 on PASS, 1 on any failure (including an unreadable input).
What it cannot see: the bytes the student received (turns.jsonl names the exchanges a message carried, not its text); the
plan check before the run is what binds the text.

usage: reading-delivery-check.py --turns RUN/turns.jsonl --plan PLAN.json --events RUN/events.jsonl --session SESSION_ID
"""
import argparse, json, sys


def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except ValueError as e:
                    raise ValueError(f"{path} line {n} is not JSON: {e}")
    return rows


def check(rows, plan, events, session):
    """Return the list of failure strings (empty = PASS)."""
    bad = []
    if not plan:
        return ["the plan is empty (nothing was planned, so nothing can have been delivered)"]
    for r in rows:
        if r.get("session_id") != session:
            bad.append(f"session id differs on turn i={r.get('i')} ({r.get('kind')}): {r.get('session_id')!r} != resumed {session!r}")
    for r in rows:
        if r.get("kind") != "exchange":
            bad.append(f"not a reading turn (kind {r.get('kind')!r}, i={r.get('i')})")
    if len(rows) != len(plan):
        bad.append(f"turn count {len(rows)} differs from the {len(plan)} planned messages")
    else:
        for n, (r, m) in enumerate(zip(rows, plan), 1):
            if r.get("exchanges") != m.get("exchanges"):
                bad.append(f"turn {n} carries exchanges {r.get('exchanges')} but planned message {n} carries {m.get('exchanges')} "
                           "(a round was dropped, repeated or delivered out of order)")
    for r in rows:
        for flag in ("is_error", "timeout", "eof"):
            if r.get(flag):
                bad.append(f"turn i={r.get('i')} has {flag} true (not a delivery)")
    results = sum(1 for e in events if isinstance(e, dict) and e.get("type") == "result")
    if results != len(plan):
        bad.append(f"{results} result events in the stream for {len(plan)} planned messages (exactly one each expected)")
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", required=True); ap.add_argument("--plan", required=True)
    ap.add_argument("--events", required=True)
    ap.add_argument("--session", required=True, help="the resumed session id the run was given")
    args = ap.parse_args()
    try:
        rows = load_jsonl(args.turns); events = load_jsonl(args.events)
        with open(args.plan, encoding="utf-8") as f:
            plan = json.load(f)
        if not isinstance(plan, list) or not all(isinstance(m, dict) for m in plan):
            raise ValueError("the plan must be a JSON list of messages")
    except (OSError, ValueError) as e:
        print(f"FAIL: cannot read inputs: {e}")
        return 1
    bad = check(rows, plan, events, args.session)
    for b in bad:
        print("FAIL:", b)
    print("PASS" if not bad else f"FAIL ({len(bad)} problem(s))")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
