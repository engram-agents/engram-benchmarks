#!/usr/bin/env python3
"""Control source check (BEAM P1 answering). This file is the study's harness, not shipped product code.

For each of the three planted-fact control questions, decides whether the planted fact was REACHABLE through its intended
channel, read off the tool calls of the whole answering session. The answer text is never used to pass or fail an
engram/folder control: it is printed beside the verdict for a human (answered / refused / abstained decides nothing; this
tool never classifies a refusal). For the 'none' control it prints the answer for a human to judge, and fails only if the
answer contains a planted token.

Inputs (all written by feed4.py and the planting step):
  --events    events.jsonl, every stream-json event of the run (assistant tool_use blocks, user tool_result blocks,
              one `result` event per turn);
  --turns     turns.jsonl; row k is the k-th `result` event's turn, and a question row carries the item's "id" (a row of
              kind "compact" is the compaction turn);
  --controls  JSON list of {id, token, channel: "engram"|"folder"|"none", folder_file?, evidence_file?, run_dir?}; exactly
              one control of each channel. The 'none' control's token is the absent (planted nowhere) value. `run_dir` is
              an optional per-control field (a control file without it is accepted unchanged); the run directories of all
              controls are watched together, like the evidence files.

The rule (design owner's ruling, 2026-11-18). An engram/folder fact PASSES iff
  (a) a read through the INTENDED channel, in a turn after both the resume and the compaction, returned the planted token
      in the tool RESULT. engram = a call to one of the pinned ENGRAM read tools (the tool name is exactly
      mcp__plugin_engram_engram__engram_{query,inspect,get_subgraph,list,list_focused,query_pattern,surface}: the server
      prefix is pinned, a different mcp server never counts); folder = a `Read` whose file_path equals the folder file
      after realpath or has its base name. The token must be in THAT call's own result after (b)'s stripping. "After the
      resume" is the run itself (the events file is the resumed session's); "after the compaction" is every turn after
      the LAST turn row of kind "compact" (no such row: every turn). Any such turn counts, not only the control's own;
  (b) a token present only in the student's own query or prompt text never counts. Before the token is searched for in a
      tool result, every string value of that call's own input is removed from the result (each JSON string leaf of the
      tool_use input, plus the leaves of any string that is itself JSON, e.g. `payload_json`, decoded; matched
      case-insensitively, also in its JSON-escaped spelling, and replaced by a NUL so neighbours never splice into a
      token). Bound: a stored value that happens to equal (or contain, as a whole leaf) the student's query string, or a
      one-character leaf, is removed too: a false negative toward FAIL, the safe direction;
  (c) no read through the OTHER channel returned it in that session (all turns, before or after the compaction): for an
      engram control a `Read` of the folder file returning the token, for a folder control an ENGRAM read returning it
      (both after stripping). Tool calls of other kinds (Bash grep or cat, Grep, ToolSearch, writes) neither pass nor fail
      a control under (a)/(c); they are listed;
  (d) the evidence file or the run directory ('named' = its full path or its base name appearing in a call's input, any
      tool) opened BEFORE the first read that satisfies (a) FAILs, in stream order across the whole session (the
      satisfying call itself naming it counts as before: the conservative side); opened AFTER it is only noted.
none: FAIL if the answer contains the engram or folder token, else REVIEW (a human judges abstention).
Alignment: row k of turns.jsonl must pair with the k-th `result` event on BOTH its `session_id` (the row's, which
feed4.py logs from the stream's system event, against the result event's own session_id; a row that carries one while
its result event carries none cannot be paired and FAILs) AND its `result` text (an empty result event is read as the
turn's last assistant text, which is what feed4.py logs then); a mismatch on either FAILs the whole check. Bound:
two turns of the SAME session with IDENTICAL result text can still swap undetected (neither field tells them apart);
the check also relies on the stream order, since turn index k is the only other key.
Per control it prints `C: PASS|FAIL [channel] reason`, the control turn's tool calls, `first intended read: <tool> <input>`,
and `answer (reported, decides nothing): <first 300 chars>`. Exit 0 if nothing FAILs, else 1. A match is a
case-insensitive substring.
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


def string_leaves(x, out):
    """Collect every string value of a JSON-ish input, descending into dicts/lists and into strings that are
    themselves JSON objects/arrays (a `payload_json`), which are decoded."""
    if isinstance(x, str):
        out.append(x)
        if x.strip()[:1] in ("{", "["):
            try:
                string_leaves(json.loads(x), out)
            except ValueError:
                pass
    elif isinstance(x, dict):
        for v in x.values():
            string_leaves(v, out)
    elif isinstance(x, (list, tuple)):
        for v in x:
            string_leaves(v, out)


def stripped_result(call):
    """The call's tool_result text with the call's own input echoed out (rule (b)): each string leaf of the input, raw and
    in its JSON-escaped spelling, longest first, case-insensitively, replaced by a NUL."""
    text = call["result"] or ""
    leaves = []
    string_leaves(call["input"], leaves)
    forms = set()
    for v in leaves:
        if v:
            forms.add(v)
            forms.add(json.dumps(v)[1:-1])
            forms.add(json.dumps(v, ensure_ascii=False)[1:-1])
    for f in sorted(forms, key=len, reverse=True):
        text = re.sub(re.escape(f), "\0", text, flags=re.IGNORECASE)
    return text


def is_folder_read(call, folder_files):
    """True if this call is a `Read` of a folder file (realpath equality or base name). Only `Read` is the folder channel."""
    if call["name"] != "Read":
        return False
    inp = call["input"] if isinstance(call["input"], dict) else {}
    got = inp.get("file_path") or inp.get("path") or ""
    return any(got and (os.path.realpath(got) == os.path.realpath(p) or os.path.basename(got) == os.path.basename(p))
               for p in folder_files)


def intended(ch, call, folder_files):
    return bool(ENGRAM_READ.match(call["name"])) if ch == "engram" else is_folder_read(call, folder_files)


def judge(ctl, answer, flat, last_compact, folder_files, opener_paths, all_tokens):
    """Return (verdict, [reasons], [notes], first) for one control. `flat` is every tool call of the session in stream
    order as (turn index, call); `last_compact` the index of the last compaction turn (-1 if none); `first` is
    (turn index, call) of the first read satisfying (a), or None. The answer text is used only by the none control."""
    ch, tok = ctl["channel"], ctl["token"]
    why, notes = [], []
    if ch == "none":
        for k, t in all_tokens.items():
            if k != "none" and has(answer, t):
                why.append(f"the answer contains the planted {k} token {t!r}")
        return ("FAIL" if why else "REVIEW"), why, notes, None
    first_i = next((i for i, (ti, c) in enumerate(flat) if ti > last_compact and intended(ch, c, folder_files)
                    and has(stripped_result(c), tok)), None)
    if first_i is None:  # (a), with (b)'s stripping
        in_scope = [c for ti, c in flat if ti > last_compact and intended(ch, c, folder_files)]
        if ch == "engram":
            why.append("no ENGRAM read tool call occurred in a turn after the compaction" if not in_scope else
                       "no ENGRAM read tool call's own result contained the token (the student's own query echo stripped)")
        else:
            why.append("the folder file was not read (no Read of it in a turn after the compaction)" if not in_scope else
                       "no Read of the folder file returned the token (the student's own input echo stripped)")
    if ch == "engram":  # (c)
        if [c for _, c in flat if is_folder_read(c, folder_files) and has(stripped_result(c), tok)]:
            why.append("a Read of the folder file returned the token in this session (the other channel)")
    elif [c for _, c in flat if ENGRAM_READ.match(c["name"]) and has(stripped_result(c), tok)]:
        why.append("an ENGRAM read returned the token in this session (the other channel)")
    opens = [i for i, (_, c) in enumerate(flat) if any(names_file(c, p) for p in opener_paths)]  # (d)
    if opens and first_i is not None:
        ti, c = flat[opens[0]]
        if opens[0] <= first_i:
            why.append(f"the evidence file or the run directory was opened before the first intended read (turn {ti + 1}, {c['name']})")
        else:
            notes.append(f"the evidence file or the run directory was opened after the first intended read "
                         f"(turn {ti + 1}, {c['name']}): does not void the pass")
    return ("FAIL" if why else "PASS"), why, notes, (flat[first_i] if first_i is not None else None)


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
    opener_paths = [c[k] for c in ctls for k in ("evidence_file", "run_dir") if c.get(k)]
    flat = [(ti, call) for ti, seg in enumerate(segs) for call in seg[0]]
    last_compact = max((k for k, r in enumerate(rows) if r.get("kind") == "compact"), default=-1)
    for c in ctls:
        idx = [k for k, r in enumerate(rows) if r.get("kind") == "question" and r.get("id") == c["id"]]
        if not idx:
            print(f"{c['id']}: FAIL no turn carries this control id"); bad.append(c["id"]); continue
        if len(idx) > 1:
            print(f"{c['id']}: FAIL more than one turn carries this control id ({len(idx)})"); bad.append(c["id"]); continue
        calls, answer, _ = segs[idx[0]]
        verdict, why, notes, first = judge(c, answer, flat, last_compact, folder_files, opener_paths, tokens)
        print(f"{c['id']}: {verdict} [{c['channel']}] " + ("; ".join(why) if why else
              ("human judgment of abstention required (this tool does not decide it)" if verdict == "REVIEW" else
               f"reachable: {first[1]['name']} in turn {first[0] + 1} returned the token")))
        print(describe(calls))
        if c["channel"] == "none":
            print(f"  ANSWER FOR HUMAN JUDGMENT: {answer!r}")
        else:
            print("  first intended read: " + (f"{first[1]['name']} {json.dumps(first[1]['input'])[:160]} (turn {first[0] + 1})"
                                              if first else "none"))
            print("  answer (reported, decides nothing): " + answer[:300].replace("\n", " "))
            for n in notes:
                print(f"  note: {n}")
        if verdict == "FAIL":
            bad.append(c["id"])
    others = [(ti, c) for ti, c in flat if not ENGRAM_ANY.match(c["name"]) and c["name"] != "Read"]
    if others:
        print("other-kind tool calls in the session (neither pass nor fail a control under (a)/(c)):")
        for ti, c in others[:40]:
            print(f"  turn {ti + 1}: {c['name']} {json.dumps(c['input'])[:100]}")
        if len(others) > 40:
            print(f"  ... and {len(others) - 40} more")
    print("RESULT: " + ("no control failed (a human still judges the 'none' answer)" if not bad else f"FAIL {bad}"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
