#!/usr/bin/env python3
"""BEAM P1 answering: the answer of each question turn, per the design owner's conformance ruling (Office 32566,
2026-11-19; tuning log entry 'the answer of a turn that ends on a tool call').

Usage: p1_answers.py <session run dir holding events.jsonl and turns.jsonl> <out.json>

A tool-ending turn (its last non-thinking assistant block is a tool_use) is answered by its last text block, or is
MISSING if it has none. Every other question turn is answered by the result the feeder recorded. The string route
(recorded result == '[no output]') is computed beside the mechanism; turns where they disagree are listed, never
resolved silently. Answer text goes only to <out.json>; stdout carries ids and counts.
"""
import json, os, sys

PLACEHOLDER = "[no output]"


def split_turns(events):
    turns, cur = [], []
    for ev in events:
        if ev.get("type") == "result":
            turns.append(cur); cur = []
        else:
            cur.append(ev)
    return turns  # events after the last result (none in a finished session) are ignored


def blocks(turn_events):
    out = []
    for ev in turn_events:
        if ev.get("type") != "assistant":
            continue
        for c in (ev.get("message") or {}).get("content") or []:
            t = c.get("type")
            if t in ("text", "tool_use"):
                out.append((t, c.get("text", "") if t == "text" else None))
    return out


def extract(events, rows):
    turns = split_turns(events)
    if len(turns) != len(rows):
        raise ValueError(f"turn count mismatch: {len(turns)} result-delimited turns in the event stream, {len(rows)} rows in turns.jsonl")
    answers, dis = {}, []
    counts = {"question_turns": 0, "tool_ending": 0, "tool_ending_multi_text": 0, "missing": 0, "disagreements": 0}
    for row, tev in zip(rows, turns):
        if row.get("kind") != "question":
            continue
        qid = row["id"]
        if qid in answers:
            raise ValueError(f"duplicate question id {qid}")
        counts["question_turns"] += 1
        bl = blocks(tev)
        texts = [x for t, x in bl if t == "text"]
        tool_ending = bool(bl) and bl[-1][0] == "tool_use"
        recorded = row.get("result")
        string_route = recorded == PLACEHOLDER
        if tool_ending:
            counts["tool_ending"] += 1
            if len(texts) > 1:
                counts["tool_ending_multi_text"] += 1
            if texts:
                ans, route = texts[-1], "last_text_block"
            else:
                ans, route = None, "missing"
                counts["missing"] += 1
        else:
            ans, route = recorded, "recorded"
            if not (recorded or "").strip():
                ans, route = None, "missing"
                counts["missing"] += 1
        if tool_ending != string_route:
            dis.append({"id": qid, "tool_ending": tool_ending, "string_route": string_route})
        answers[qid] = {"answer": ans, "route": route, "tool_ending": tool_ending, "string_route": string_route}
    counts["disagreements"] = len(dis)
    return {"answers": answers, "counts": counts, "disagreements": dis}


def main(argv):
    if len(argv) != 3:
        print(__doc__.strip().splitlines()[2], file=sys.stderr); return 2
    d, outp = argv[1], argv[2]
    load = lambda p: [json.loads(l) for l in open(p) if l.strip()]
    res = extract(load(os.path.join(d, "events.jsonl")), load(os.path.join(d, "turns.jsonl")))
    with open(outp, "w") as f:
        json.dump(res, f, indent=1, sort_keys=True)
    print("counts", json.dumps(res["counts"], sort_keys=True))
    print("tool_ending ids", sorted(k for k, v in res["answers"].items() if v["tool_ending"]))
    print("missing ids", sorted(k for k, v in res["answers"].items() if v["route"] == "missing"))
    print("disagreements", json.dumps(res["disagreements"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
