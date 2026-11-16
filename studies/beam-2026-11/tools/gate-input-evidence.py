#!/usr/bin/env python3
"""BEAM: show, byte for byte, that each gate run's student received the messages its own feed.py builds.
This file is the study's harness, not shipped product code.

usage: BEAM_PARQUET=<100K parquet> gate_input_evidence.py --feed-dir DIR RUN_DIR [RUN_DIR ...]
       gate_input_evidence.py --feed-dir DIR --plan PLAN.json RUN_DIR    (a pilot round run: compare with its plan)

For each RUN_DIR (holding setup.txt, whose first line names 'conv C' and the turn count, and the student's session
transcripts under transcripts/): rebuild the reading messages from feed.py in --feed-dir exactly as the run's feeder
(feed3.py) does -- message 1 = BRIEF + blank line + exchange 1, then one rendered exchange per message -- and compare
them with every reading message in the run's transcripts, in order. Also checks that message 1 carries the brief,
and the brief carries the purpose sentence. Prints feed.py's sha256 once. Exit 0 = every run matches.
"""
import argparse, glob, hashlib, json, os, re, sys

PURPOSE = ("Later, after your context has been compacted, I will ask you questions about this conversation, so\n"
           "keep whatever record you will need to answer them.")


def received(run_dir, begin):
    """Reading messages the student received, in order, from its own session transcripts (compaction summaries and
    meta records excluded; a message is a reading message if it carries the reading-material marker)."""
    msgs = []
    for f in glob.glob(os.path.join(run_dir, "transcripts", "**", "*.jsonl"), recursive=True):
        for line in open(f, errors="replace"):
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("type") != "user" or e.get("isCompactSummary") or e.get("isMeta"):
                continue
            c = e.get("message", {}).get("content")
            if isinstance(c, str) and begin in c:
                msgs.append((e.get("timestamp", ""), c))
    msgs.sort(key=lambda m: m[0])
    return [c for _, c in msgs]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--feed-dir", required=True)
    ap.add_argument("--turns-if-unrecorded", type=int,
                    help="planned exchange count for runs whose setup.txt does not record it (from their run script)")
    ap.add_argument("--plan", help="a feed4 --dump-plan JSON: compare the run's received reading messages with its "
                    "exchange-round texts, byte for byte (one RUN_DIR)")
    ap.add_argument("runs", nargs="+")
    a = ap.parse_args()
    sys.path.insert(0, a.feed_dir)
    import feed
    import pyarrow.parquet as pq
    src = open(os.path.join(a.feed_dir, "feed.py"), "rb").read()
    print(f"feed.py sha256 {hashlib.sha256(src).hexdigest()}; purpose sentence in BRIEF: {PURPOSE in feed.BRIEF}")
    if a.plan:
        if len(a.runs) != 1:
            sys.exit("--plan takes exactly one RUN_DIR")
        planned = [p["text"] for p in json.load(open(a.plan)) if p["kind"] == "exchange"]
        got = received(a.runs[0], feed.BEGIN)
        same = sum(1 for x, y in zip(got, planned) if x == y)
        first_ok = bool(got) and got[0].startswith(feed.BRIEF + "\n\n") and PURPOSE in got[0]
        good = len(got) == len(planned) == same and first_ok
        print(f"{'PASS' if good else 'FAIL'}  {os.path.basename(os.path.normpath(a.runs[0]))}: {len(got)} reading "
              f"messages received, {len(planned)} planned rounds, {same} byte-identical; message 1 opens with the brief "
              f"and carries the purpose sentence: {first_ok}; plan sha256 "
              f"{hashlib.sha256(open(a.plan, 'rb').read()).hexdigest()[:16]}")
        print("RESULT:", "the run matches its plan" if good else "MISMATCH")
        return 0 if good else 1
    parquet = os.environ.get("BEAM_PARQUET") or sys.exit("set BEAM_PARQUET to the BEAM 100K parquet file")
    rows = pq.read_table(parquet).to_pylist()
    ok = PURPOSE in feed.BRIEF
    for run in a.runs:
        head = open(os.path.join(run, "setup.txt")).readline()
        conv = re.search(r"\bconv (\d+)", head).group(1)
        turns = int(m.group(1)) if (m := re.search(r"\bturns (\d+)", head)) else None
        exs = feed.exchanges(next(c for c in rows if str(c["conversation_id"]) == conv))
        got = received(run, feed.BEGIN)
        n = turns or a.turns_if_unrecorded
        count_from = "setup.txt" if turns else "--turns-if-unrecorded (the run script's value)"
        if not n:
            sys.exit(f"{run}: setup.txt records no turn count; pass --turns-if-unrecorded from its run script")
        want = [feed.BRIEF + "\n\n" + exs[0]] + exs[1:n]
        same = sum(1 for x, y in zip(got, want) if x == y)
        first_ok = bool(got) and got[0].startswith(feed.BRIEF + "\n\n") and PURPOSE in got[0]
        good = len(got) == len(want) == same and first_ok
        ok &= good
        print(f"{'PASS' if good else 'FAIL'}  {os.path.basename(os.path.normpath(run))}: conversation {conv}, "
              f"{len(got)} reading messages received, {len(want)} planned, {same} byte-identical; "
              f"message 1 opens with the brief and carries the purpose sentence: {first_ok}; "
              f"planned count from {count_from}")
        if not good:
            i = next((i for i, (x, y) in enumerate(zip(got, want)) if x != y), None)
            if i is not None:
                print(f"      first difference at message {i + 1}")
    print("RESULT:", "every run matches" if ok else "MISMATCH")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
