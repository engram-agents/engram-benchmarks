#!/usr/bin/env python3
"""Control source check (BEAM P1 answering). This file is the study's harness, not shipped product code.

For each of the three planted-fact control questions, reports WHERE the answer came from, read off the tool calls the
answering session made during that question's turn. It does NOT decide abstention: for the 'none' control it prints
the answer for a human to judge, and fails only if the answer contains a planted token.

Inputs (all written by feed4.py and the planting step):
  --events    events.jsonl, every stream-json event of the run (assistant tool_use blocks, user tool_result blocks,
              one `result` event per turn);
  --turns     turns.jsonl; row k is the k-th `result` event's turn, and a question row carries the item's "id";
  --controls  JSON list of {id, token, channel: "engram"|"folder"|"none", folder_file?, evidence_file?}; exactly one
              control of each channel. The 'none' control's token is the absent (planted nowhere) value.

Per control, on the tool calls of that turn only:
  engram  PASS only if the answer contains the token, at least one ENGRAM read tool call (the tool name is exactly
          mcp__plugin_engram_engram__engram_{query,inspect,get_subgraph,list,list_focused,query_pattern,surface}: the
          server prefix is pinned, a different mcp server never counts) occurred AND its own matching tool_result text
          contains the token, and no other tool touched the folder file or the evidence file (a call naming either
          file, or a non-ENGRAM tool result showing the token);
  folder  PASS only if the answer contains the token, the folder file was READ (a `Read` tool call whose file_path
          equals the folder file after realpath or has its base name; or a tool_result containing the token from a
          call naming the folder file; `stat`, `ls`, Write, Edit never count), no ENGRAM read returned the token, and
          the evidence file was untouched;
  none    FAIL if the answer contains the engram or folder token; otherwise REVIEW (a human judges abstention).
Alignment: row k of turns.jsonl must pair with the k-th `result` event on BOTH its `session_id` (the row's, which
feed4.py logs from the stream's system event, against the result event's own session_id; a row that carries one while
its result event carries none cannot be paired and FAILs) AND its `result` text (an empty result event is read as the
turn's last assistant text, which is what feed4.py logs then); a mismatch on either FAILs the whole check. Bound:
two turns of the SAME session with IDENTICAL result text can still swap undetected (neither field tells them apart);
the check also relies on the stream order, since turn index k is the only other key.
Exit 0 if nothing FAILs, else 1. A match is a case-insensitive substring; a file is 'named' by its full path or its
base name appearing in a call's input.
usage: control-source-check.py --events E --turns T --controls C
"""
import argparse, json, os, re, sys

ENGRAM_SERVER_PREFIX = "mcp__plugin_engram_engram__"  # pinned: the one ENGRAM MCP server the arm's plugin registers
ENGRAM_READ = re.compile(r"^" + re.escape(ENGRAM_SERVER_PREFIX)
                         + r"engram_(query|inspect|get_subgraph|list|list_focused|query_pattern|surface)$")
ENGRAM_ANY = re.compile(r"^" + re.escape(ENGRAM_SERVER_PREFIX) + r"engram_")
NOT_A_READ_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})
NOT_A_READ_BASH = re.compile(r"^\s*(stat|ls)\b")
CHANNELS = ("engram", "folder", "none")


def read_jsonl(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if line.strip():
                try:
                    out.append(json.loads(line))
                except ValueError as e:
                    raise ValueError(f"{path} line {n}: {e}")
    return out


def result_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
    return json.dumps(content)


def segment(events):
    """Split the events into turns: each turn ends with its `result` event. Returns [(calls, answer, session_id of the result event)]; each call is
    {name, input, result}. A trailing run of events with no result event is returned as an unfinished extra turn."""
    turns, calls, by_id, last_text = [], [], {}, ""
    for ev in events:
        t = ev.get("type")
        content = (ev.get("message") or {}).get("content") if isinstance(ev.get("message"), dict) else None
        if t == "assistant" and isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    call = {"name": c.get("name", ""), "input": c.get("input"), "result": ""}
                    by_id[c.get("id")] = call; calls.append(call)
                elif isinstance(c, dict) and c.get("type") == "text":
                    last_text = c.get("text", "")
        elif t == "user" and isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get("type") == "tool_result" and c.get("tool_use_id") in by_id:
                    by_id[c["tool_use_id"]]["result"] += result_text(c.get("content"))
        elif t == "result":
            turns.append((calls, ev.get("result") or last_text or "", ev.get("session_id"))); calls, last_text = [], ""
    if calls:
        turns.append((calls, None, None))
    return turns


def names_file(call, path):
    s = json.dumps(call["input"]) if call["input"] is not None else ""
    return path in s or os.path.basename(path) in s


def has(text, token):
    return token.lower() in (text or "").lower()


def is_folder_read(call, folder_files, token):
    """True if this call READ a folder file: a `Read` of it (realpath equality or base name), or a tool_result holding
    the token from a call that names it. stat, ls, and Write/Edit never count, whatever their result shows."""
    if call["name"] in NOT_A_READ_TOOLS:
        return False
    inp = call["input"] if isinstance(call["input"], dict) else {}
    if call["name"] == "Read":
        got = inp.get("file_path") or inp.get("path") or ""
        for p in folder_files:
            if got and (os.path.realpath(got) == os.path.realpath(p) or os.path.basename(got) == os.path.basename(p)):
                return True
        return False
    if call["name"] == "Bash" and NOT_A_READ_BASH.match(str(inp.get("command", ""))):
        return False
    return any(names_file(call, p) for p in folder_files) and has(call["result"], token)


def judge(ctl, answer, calls, folder_files, evidence_files, all_tokens):
    """Return (verdict, [reasons]) for one control."""
    ch, tok = ctl["channel"], ctl["token"]
    eng_reads = [c for c in calls if ENGRAM_READ.match(c["name"])]
    other = [c for c in calls if not ENGRAM_ANY.match(c["name"])]
    why = []
    if ch == "none":
        for k, t in all_tokens.items():
            if k != "none" and has(answer, t):
                why.append(f"the answer contains the planted {k} token {t!r}")
        return ("FAIL" if why else "REVIEW"), why
    if not has(answer, tok):
        why.append(f"the answer does not contain the token {tok!r}")
    ev_touch = [c for p in evidence_files for c in other if names_file(c, p)]
    if ch == "engram":
        if not eng_reads:
            why.append("no ENGRAM read tool call occurred in this turn")
        elif not [c for c in eng_reads if has(c["result"], tok)]:
            why.append("no ENGRAM read tool call's own result contained the token")
        if [c for p in folder_files for c in other if names_file(c, p)]:
            why.append("a tool call touched the folder file")
        if ev_touch:
            why.append("a tool call touched the evidence file")
        if [c for c in other if has(c["result"], tok)]:
            why.append("a non-ENGRAM tool result showed the token")
    else:  # folder
        if not [c for c in other if is_folder_read(c, folder_files, tok)]:
            why.append("the folder file was not read")
        if [c for c in eng_reads if has(c["result"], tok)]:
            why.append("an ENGRAM read returned the token")
        if ev_touch:
            why.append("a tool call touched the evidence file")
    return ("FAIL" if why else "PASS"), why


def describe(calls):
    if not calls:
        return "  tool calls: none"
    lines = ["  tool calls:"]
    for c in calls:
        kind = "ENGRAM read" if ENGRAM_READ.match(c["name"]) else ("ENGRAM write/other" if ENGRAM_ANY.match(c["name"]) else "other")
        lines.append(f"    [{kind}] {c['name']} {json.dumps(c['input'])[:160]}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", required=True); ap.add_argument("--turns", required=True)
    ap.add_argument("--controls", required=True)
    a = ap.parse_args()
    try:
        events, rows = read_jsonl(a.events), read_jsonl(a.turns)
        with open(a.controls, encoding="utf-8") as f:
            ctls = json.load(f)
        assert isinstance(ctls, list) and all(isinstance(c, dict) for c in ctls)
        for c in ctls:
            c["id"], c["token"], c["channel"]
    except (OSError, ValueError, KeyError, AssertionError) as e:
        print(f"FAIL: cannot read inputs: {type(e).__name__}: {e}")
        return 1
    bad = []
    if sorted(c["channel"] for c in ctls) != sorted(CHANNELS):
        print(f"FAIL: the controls must be exactly one of each channel {list(CHANNELS)}, got {[c['channel'] for c in ctls]}")
        return 1
    segs = segment(events)
    if len(segs) != len(rows) or any(s[1] is None for s in segs):
        print(f"FAIL: events and turns do not align: {len(segs)} turn(s) of events (result events) vs {len(rows)} turn row(s)")
        return 1
    for k, (row, seg) in enumerate(zip(rows, segs)):
        if row.get("session_id") != seg[2] and (row.get("session_id") or seg[2]):
            print(f"FAIL: events and turns do not align: turn row {k + 1} (i={row.get('i')}) carries session_id "
                  f"{row.get('session_id')!r}, the {k + 1}-th result event {seg[2]!r}")
            return 1
        if row.get("result") != seg[1]:
            print(f"FAIL: events and turns do not align: turn row {k + 1} (i={row.get('i')}) carries result text "
                  f"{str(row.get('result'))[:80]!r}, the {k + 1}-th result event {seg[1][:80]!r}")
            return 1
    tokens = {c["channel"]: c["token"] for c in ctls}
    folder_files = [c["folder_file"] for c in ctls if c.get("folder_file")]
    evidence_files = [c["evidence_file"] for c in ctls if c.get("evidence_file")]
    for c in ctls:
        idx = [k for k, r in enumerate(rows) if r.get("kind") == "question" and r.get("id") == c["id"]]
        if not idx:
            print(f"{c['id']}: FAIL no turn carries this control id"); bad.append(c["id"]); continue
        if len(idx) > 1:
            print(f"{c['id']}: FAIL more than one turn carries this control id ({len(idx)})"); bad.append(c["id"]); continue
        calls, answer, _ = segs[idx[0]]
        verdict, why = judge(c, answer, calls, folder_files, evidence_files, tokens)
        print(f"{c['id']}: {verdict} [{c['channel']}] " + ("; ".join(why) if why else
              ("human judgment of abstention required (this tool does not decide it)" if verdict == "REVIEW" else "ok")))
        print(describe(calls))
        if c["channel"] == "none":
            print(f"  ANSWER FOR HUMAN JUDGMENT: {answer!r}")
        if verdict == "FAIL":
            bad.append(c["id"])
    print("RESULT: " + ("no control failed (a human still judges the 'none' answer)" if not bad else f"FAIL {bad}"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
