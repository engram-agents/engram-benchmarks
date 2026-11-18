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

Design principle (PR 8 reviewer round 2). Every approximation this instrument makes errs toward FAIL for the clause it
serves: where it cannot tell, a fact fails rather than passes. The echo strip is therefore strip-ALL for (a) (where
over-stripping fails the fact) and strip-ONCE for (c) and (d') (where over-stripping would hide a real return and pass it);
(c') excuses a return only when it can IDENTIFY the returned item as one the student wrote, never by matching text.

The rule (design owner's ruling, 2026-11-18, final form). An engram/folder fact PASSES iff
  (a) a read through the INTENDED channel, in a turn after both the resume and the compaction, returned the planted token
      in the tool RESULT. The channel is named by its STORAGE. engram = a call to one of the pinned ENGRAM read tools (the
      tool name is exactly mcp__plugin_engram_engram__engram_{query,inspect,get_subgraph,list,list_focused,query_pattern,
      surface}: the server prefix is pinned, a different mcp server never counts); folder = ANY call whose TARGET is inside
      the student's memory folder (the directory of the control's folder_file; realpath compare): a Read/NotebookRead
      file_path, a Grep/Glob path (or an absolute Glob pattern), a Bash command with an absolute path word that resolves
      inside it (a grep, cat, ls or stat of it). In a Bash command `~`, `$HOME` and `${HOME}` resolve to the student's
      home, taken from the folder_file's path (the part before "/.claude/"); with no such part they are not resolved.
      Bound: a relative path, a glob, a variable other than HOME or a path built by a subshell in a Bash command cannot be
      resolved, so it is not seen (toward FAIL for a folder control; for an engram control it can hide a folder return:
      the one remaining approximation toward PASS, stated); a `Read` of a file with a folder_file's base name counts
      wherever it sits (kept from bfab5a3); Write/Edit and MCP tools have no read target. The token must be in THAT call's
      own result after (b)'s strip-ALL stripping. "After the resume" is the run itself (the events file is the resumed
      session's); "after the compaction" is every turn after the LAST turn row of kind "compact" (no such row: every turn).
      Any such turn counts, not only the control's own;
  (b) a token present only in the student's own query or prompt text never counts. The echo of the student's input is
      removed from a tool result before the token is searched for, by two functions. For (a), `strip_strings` removes EVERY
      occurrence of every string leaf of the call's own input (each JSON string leaf of the tool_use input, plus the
      leaves of any string that is itself JSON, e.g. `payload_json`, decoded; matched case-insensitively, also in its
      JSON-escaped spelling, replaced by a NUL so neighbours never splice into a token). Bound: a stored value that equals
      (or contains, as a whole leaf) the query string, or a one-character leaf, is removed too: a false negative toward
      FAIL, the safe direction for (a). For (c) and (d') `strip_echo_once` removes each leaf AT MOST ONCE per occurrence of
      that leaf in the input (a decoded `payload_json` leaf is consumed together with the whole payload string when that
      is what the result echoes): a query that is exactly the token, with a store that returned it too, leaves the stored
      occurrence and the return COUNTS. A leaf that is not itself the token and only overlaps a token occurrence is never
      removed there (a query "7Z" cannot blank part of the token). Only the result of an `mcp__` tool is stripped, because
      only a structured tool hands its query back: a Grep, Bash, Read or Glob does not echo its input, so a Grep whose
      pattern is the token and whose one result line holds it is a return (nothing is removed from such a result). Bounds:
      a tool that echoes its input more than once per result leaves an extra echo, which also errs toward FAIL here; and
      an `mcp__` result in which the token appears exactly once, with a leaf equal to the token, is read as the echo (the
      one place this strip errs toward PASS: an echo-only result must not fail (c));
  (c) no read through the OTHER channel returned it in that session (all turns, before or after the compaction): for an
      engram control a folder-channel read (as in (a)) returning the token, for a folder control an ENGRAM read returning
      it (both after `strip_echo_once`). Calls of other kinds (ToolSearch, other MCP tools, writes) neither pass nor fail a
      control under (a)/(c); they are listed. Exception (c'): the returned item is one the student itself wrote in the
      session AFTER the first intended read that returned the token, and the tool IDENTIFIES it, never by its text.
      Other channel = ENGRAM (a folder control): the ids the student's own ENGRAM writes created after that read (the
      pinned server's non-read calls; the ids their results report under the keys id, observation_id, derivation_id,
      result_node_id, conjecture_id, question_id, definition_id, tension_id, contradiction_id; a key that only REFERS to a
      node, such as target_id or superseded_id, is not read). The result is parsed as JSON (JSON inside a JSON string is
      decoded recursively); every dict with an `id` whose string values hold the token must have the id of one of those
      later-written nodes (written before this read), and no occurrence of the token may lie outside those dicts (they are
      removed from the serialized result, `strip_echo_once` is applied to what remains). Anything else, including a result
      that does not parse or a write whose result reports no id, counts as a return. Other channel = FOLDER (an engram
      control): the read must be of a file the student itself CREATED with a Write after that read, no call before that
      Write having named the file (full path or base name in its input), and the read coming after the Write; every
      in-folder path the read targets must be such a file (a grep of the whole folder is never excused). An Edit or a
      MultiEdit is NEVER a creation (the file may already have held the token), and a write through Bash (`echo > file`) is
      not recognized as a write. Writes BEFORE the first intended read never excuse anything, an other-channel return before
      it is never excused, and a pre-existing item holding the token still FAILs. When the exception is what prevented a
      FAIL, a `note:` names the node id(s) with the write (tool, turn), or the file path with its Write (turn). The check
      relies on the tool result's shape, so a result the channel reshapes is read as unparseable: a false negative toward
      FAIL;
  (d) the evidence file or the run directory opened BEFORE the first read that satisfies (a) FAILs, in stream order
      across the whole session (the satisfying call itself naming it counts as before: the conservative side); opened
      AFTER it is only noted. (d') An OPENING is a FILE-CAPABLE call that EITHER names the evidence file or the run
      directory ('named' = its full path or its base name appearing in the call's input, `~` / `$HOME` / `${HOME}`
      expanded as above) OR returns the token (after `strip_echo_once`) while its target is NOT inside the memory folder (a
      path outside both channels). FILE-CAPABLE is by default-deny: every call is file-capable (Read, Bash, Grep, Glob,
      NotebookRead, LS, Task, Agent, WebFetch, Write, Edit and any tool this file has never heard of) EXCEPT the calls in
      NOT_FILE_CAPABLE (ToolSearch, TodoWrite, ExitPlanMode, EnterPlanMode, AskUserQuestion) and any name starting with
      "mcp__" (ENGRAM and every other MCP tool): a path in the arguments or results of those is a mention, never an
      opening. Bound: an MCP tool that can itself read files is treated as a mention (the rule's wording), the one place a
      PASS can hide an opening.
none: FAIL if the answer contains the engram or folder token, else REVIEW (a human judges abstention).
Alignment: row k of turns.jsonl must pair with the k-th `result` event on BOTH its `session_id` (the row's, which
feed4.py logs from the stream's system event, against the result event's own session_id; a row that carries one while
its result event carries none cannot be paired and FAILs) AND its `result` text (an empty result event is read as the
turn's last assistant text, which is what feed4.py logs then); a mismatch on either FAILs the whole check. Bound:
two turns of the SAME session with IDENTICAL result text can still swap undetected (neither field tells them apart);
the check also relies on the stream order, since turn index k is the only other key.
Per control it prints `C: PASS|FAIL [channel] reason`, the control turn's tool calls, `first intended read: <tool> <input>
(turn, event: the 1-based position of its tool_use in events.jsonl)`,
and `answer (reported, decides nothing): <first 300 chars>`. Exit 0 if nothing FAILs, else 1. A match is a
case-insensitive substring.
usage: control-source-check.py --events E --turns T --controls C
"""
import argparse, json, os, re, sys

ENGRAM_SERVER_PREFIX = "mcp__plugin_engram_engram__"  # pinned: the one ENGRAM MCP server the arm's plugin registers
ENGRAM_READ = re.compile(r"^" + re.escape(ENGRAM_SERVER_PREFIX)
                         + r"engram_(query|inspect|get_subgraph|list|list_focused|query_pattern|surface)$")
ENGRAM_ANY = re.compile(r"^" + re.escape(ENGRAM_SERVER_PREFIX) + r"engram_")
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
    for n, ev in enumerate(events):
        t = ev.get("type")
        content = (ev.get("message") or {}).get("content") if isinstance(ev.get("message"), dict) else None
        if t == "assistant" and isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    call = {"name": c.get("name", ""), "input": c.get("input"), "result": "", "ev": n}
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


def home_of(folder_files):
    """The student's home: the part of a folder_file's path before "/.claude/" (None if no folder_file has one)."""
    for p in folder_files:
        i = p.find("/.claude/")
        if i > 0:
            return p[:i]
    return None


def expand_home(s, home):
    """`~`, `$HOME` and `${HOME}` in a shell text resolved to the student's home (not `~user`, not `$HOMEX`)."""
    if not home:
        return s
    s = re.sub(r"\$\{HOME\}|\$HOME(?!\w)", lambda m: home, s)
    return re.sub(r"(?<![\w$~./-])~(?=/|$|[\s'\"`;|&<>()])", lambda m: home, s)


def names_file(call, path, home=None):
    """(d') 'named': the path or its base name appears in the call's input (`~` / `$HOME` / `${HOME}` expanded)."""
    s = json.dumps(call["input"]) if call["input"] is not None else ""
    return path in s or os.path.basename(path) in s or path in expand_home(s, home)


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


def strip_strings(text, strings):
    """Rule (a)'s strip-ALL: remove EVERY occurrence of every string in `strings` from `text`: raw and in its JSON-escaped
    spelling, longest first, case-insensitively, each replaced by a NUL (so neighbours never splice into a token)."""
    forms = set()
    for v in strings:
        if v:
            forms.add(v)
            forms.add(json.dumps(v)[1:-1])
            forms.add(json.dumps(v, ensure_ascii=False)[1:-1])
    for f in sorted(forms, key=len, reverse=True):
        text = re.sub(re.escape(f), "\0", text, flags=re.IGNORECASE)
    return text


def stripped_result(call):
    """The call's tool_result text with the call's own input echoed out, strip-ALL (rule (a)): each string leaf of the
    input, every occurrence. Only (a) uses it: over-stripping there fails the fact."""
    leaves = []
    string_leaves(call["input"], leaves)
    return strip_strings(call["result"] or "", leaves)


def leaf_nodes(x):
    """The string leaves of a JSON-ish input as a forest of (string, children): a string that is itself JSON (a
    `payload_json`) carries its decoded leaves as its children."""
    if isinstance(x, str):
        kids = []
        if x.strip()[:1] in ("{", "["):
            try:
                kids = leaf_nodes(json.loads(x))
            except ValueError:
                pass
        return [(x, kids)]
    if isinstance(x, dict):
        return [n for v in x.values() for n in leaf_nodes(v)]
    if isinstance(x, (list, tuple)):
        return [n for v in x for n in leaf_nodes(v)]
    return []


def remove_once(text, s, token):
    """Remove ONE occurrence of `s` (raw or JSON-escaped, case-insensitive) from `text`, the first one eligible; returns
    (text, removed). A leaf that does not itself contain the token is never taken from a spot that overlaps a token
    occurrence: a short query cannot blank part of a stored token."""
    spans = [m.span() for m in re.finditer(re.escape(token), text, re.IGNORECASE)] if token else []
    whole = token.lower() in s.lower()
    best = None
    for f in {x for x in (s, json.dumps(s)[1:-1], json.dumps(s, ensure_ascii=False)[1:-1]) if x}:
        for m in re.finditer(re.escape(f), text, re.IGNORECASE):
            a, b = m.span()
            if whole or not any(a < tb and ta < b for ta, tb in spans):
                if best is None or a < best[0]:
                    best = (a, b)
                break
    if best is None:
        return text, False
    return text[:best[0]] + "\0" + text[best[1]:], True


def strip_echo_once(text, nodes, token):
    """Rules (c) and (d')'s echo strip: remove each input string leaf AT MOST ONCE per occurrence of that leaf in the input
    (`nodes` = leaf_nodes(input)). When a payload string is found its decoded leaves are not removed again (one echo);
    when it is not, they are tried. A query that is exactly the token, with a store that returned it too, leaves the stored
    occurrence behind, so the return counts. Bound: a tool that echoes its input more than once per result leaves an extra
    echo, which also errs toward FAIL here."""
    for s, kids in sorted(nodes, key=lambda n: -len(n[0])):
        if not s:
            continue
        text, gone = remove_once(text, s, token)
        if not gone and kids:
            text = strip_echo_once(text, kids, token)
    return text


def echo_once_result(call, token):
    """The result for (c) and (d'). Only an `mcp__` tool is a structured tool that can hand its query back, so only its
    result is echo-stripped. A file or shell tool (Grep, Bash, Read, Glob, ...) does not echo its input: its single
    occurrence of a token that equals the pattern is the file's content, so nothing is removed (toward FAIL)."""
    if not call["name"].startswith("mcp__"):
        return call["result"] or ""
    return strip_echo_once(call["result"] or "", leaf_nodes(call["input"]), token)


# ---- the folder channel is named by STORAGE (rule (a)): any call whose target is inside the memory folder
# (d'): file-capable by DEFAULT-DENY. Every call can return file content except these and any "mcp__" tool, so a tool this
# file has never heard of (Task, Agent, WebFetch, a new one) counts as file-capable, toward FAIL.
NOT_FILE_CAPABLE = frozenset({"ToolSearch", "TodoWrite", "ExitPlanMode", "EnterPlanMode", "AskUserQuestion"})
CREATE_TOOLS = frozenset({"Write"})   # (c') folder side: only a Write creates a file; an Edit/MultiEdit never does
BASH_ABS_PATH = re.compile(r"(?<![\w.~/-])/[^\s'\"`;|&<>()=:,]*")   # an absolute path word of a shell command
# (c') ENGRAM side: result keys that report a node the write CREATED (a key that only refers to one, such as target_id,
# superseded_id, node_id or evidence_id, is not here)
CREATED_ID_KEYS = frozenset({"id", "observation_id", "derivation_id", "result_node_id", "conjecture_id", "question_id",
                             "definition_id", "tension_id", "contradiction_id"})


def file_capable(name):
    return not (name.startswith("mcp__") or name in NOT_FILE_CAPABLE)


def folder_dirs(folder_files):
    return [os.path.realpath(os.path.dirname(p)) for p in folder_files]


def inside(path, dirs):
    rp = os.path.realpath(path)
    return any(rp == d or rp.startswith(d + os.sep) for d in dirs)


def folder_target_paths(call, folder_files):
    """The paths, as the call wrote them, that the call TARGETS inside the memory folder (the directory of a control's
    folder_file; realpath compare): Read/NotebookRead file_path; Grep/Glob path (a Glob pattern that is itself absolute
    too); a Bash command's absolute path words (`~`, `$HOME`, `${HOME}` expanded to the home taken from the folder_file).
    A `Read` of a file whose base name is a folder_file's counts as well (the bfab5a3 matching). Write/Edit and MCP tools
    have no read target. An empty list = the call is not in the folder channel."""
    inp = call["input"] if isinstance(call["input"], dict) else {}
    dirs = folder_dirs(folder_files)
    n = call["name"]
    if n in ("Read", "NotebookRead"):
        got = inp.get("file_path") or inp.get("path") or inp.get("notebook_path") or ""
        ok = bool(got) and (inside(got, dirs) or (n == "Read" and any(os.path.basename(got) == os.path.basename(p)
                                                                       for p in folder_files)))
        return [got] if ok else []
    if n in ("Grep", "Glob"):
        cands = [inp.get("path")] + ([inp.get("pattern")] if n == "Glob" and str(inp.get("pattern", "")).startswith("/") else [])
        return [c for c in cands if isinstance(c, str) and c and inside(c, dirs)]
    if n == "Bash":
        cmd = inp.get("command")
        if not isinstance(cmd, str):
            return []
        return [m for m in BASH_ABS_PATH.findall(expand_home(cmd, home_of(folder_files))) if inside(m, dirs)]
    return []


def folder_target(call, folder_files):
    return bool(folder_target_paths(call, folder_files))


def intended(ch, call, folder_files):
    return bool(ENGRAM_READ.match(call["name"])) if ch == "engram" else folder_target(call, folder_files)


def other_channel(ch, call, folder_files):
    return folder_target(call, folder_files) if ch == "engram" else bool(ENGRAM_READ.match(call["name"]))


# ---- (c') the exception identifies the written ITEM: an ENGRAM node id, or a file the student created
def deep_decode(x):
    """A parsed JSON value with every string that is itself a JSON object/array decoded, recursively."""
    if isinstance(x, str):
        if x.strip()[:1] in ("{", "["):
            try:
                return deep_decode(json.loads(x, strict=False))
            except ValueError:
                return x
        return x
    if isinstance(x, dict):
        return {k: deep_decode(v) for k, v in x.items()}
    if isinstance(x, list):
        return [deep_decode(v) for v in x]
    return x


def parse_result(text):
    """A tool result as a decoded JSON value, or None if it does not parse."""
    try:
        return deep_decode(json.loads(text, strict=False))
    except (ValueError, RecursionError):
        return None


def walk_dicts(x):
    if isinstance(x, dict):
        yield x
        for v in x.values():
            yield from walk_dicts(v)
    elif isinstance(x, list):
        for v in x:
            yield from walk_dicts(v)


def dict_holds(d, tok):
    out = []
    string_leaves(d, out)
    return any(has(s, tok) for s in out)


def without_dicts(x, drop):
    """A copy of x with every dict whose identity is in `drop` replaced by None."""
    if isinstance(x, dict):
        return None if id(x) in drop else {k: without_dicts(v, drop) for k, v in x.items()}
    if isinstance(x, list):
        return [without_dicts(v, drop) for v in x]
    return x


def created_ids(result):
    """The ids a write's result reports as created (CREATED_ID_KEYS)."""
    out = set()
    for d in walk_dicts(parse_result(result)):
        for k, v in d.items():
            if k in CREATED_ID_KEYS:
                out.update(x for x in (v if isinstance(v, list) else [v]) if isinstance(x, str))
    return out


def excused_node_ids(call, tok, later_ids):
    """(c'), ENGRAM as the other channel: the set of excused node ids of an ENGRAM read result that holds the token, or None
    if the return counts. Excused only if the result parses, every dict with an `id` whose string values hold the token has
    the id of a node the student wrote later (`later_ids`), and no occurrence of the token lies outside those dicts."""
    obj = parse_result(call["result"] or "")
    if obj is None:
        return None
    holders = [d for d in walk_dicts(obj) if isinstance(d.get("id"), str) and dict_holds(d, tok)]
    if not holders or not {d["id"] for d in holders} <= later_ids:
        return None
    rest = json.dumps(without_dicts(obj, {id(d) for d in holders}), ensure_ascii=False)
    if has(strip_echo_once(rest, leaf_nodes(call["input"]), tok), tok):
        return None
    return {d["id"] for d in holders}


def created_files(flat, first_i, folder_files):
    """(c') FOLDER as the other channel: {realpath: (index, path as written)} of the files the student itself CREATED with a
    Write after the first intended read (flat index > first_i), no call before that Write naming the file. An Edit or a
    MultiEdit is never a creation (the file may already have held the token)."""
    home, out = home_of(folder_files), {}
    for i, (_, c) in enumerate(flat):
        fp = c["input"].get("file_path") if isinstance(c["input"], dict) else None
        if i <= first_i or c["name"] not in CREATE_TOOLS or not isinstance(fp, str) or not fp:
            continue
        rp = os.path.realpath(fp)
        if rp not in out and not any(names_file(c2, fp, home) for _, c2 in flat[:i]):
            out[rp] = (i, fp)
    return out


def excused_files(call, j, created, folder_files):
    """(c') folder side: the (path, write index) pairs if the read at flat index j targets ONLY files the student created
    earlier with a Write, else None."""
    paths = folder_target_paths(call, folder_files)
    got = [created.get(os.path.realpath(p)) for p in paths]
    if not paths or any(g is None or g[0] >= j for g in got):
        return None
    return sorted(set(got))


def opening(c, tok, folder_files, opener_paths):
    """(d'): 'named' if a FILE-CAPABLE call (default-deny, see NOT_FILE_CAPABLE) names the evidence file / run directory
    (full path or base name), 'outside' if one returns the token (after strip_echo_once) from a path outside both channels;
    None otherwise (an MCP tool, ToolSearch and the like only mention)."""
    if not file_capable(c["name"]):
        return None
    home = home_of(folder_files)
    if any(names_file(c, p, home) for p in opener_paths):
        return "named"
    if not folder_target(c, folder_files) and has(echo_once_result(c, tok), tok):
        return "outside"
    return None


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
    if first_i is None:  # (a), with (b)'s strip-all
        in_scope = [c for ti, c in flat if ti > last_compact and intended(ch, c, folder_files)]
        if ch == "engram":
            why.append("no ENGRAM read tool call occurred in a turn after the compaction" if not in_scope else
                       "no ENGRAM read tool call's own result contained the token (the student's own query echo stripped)")
        else:
            why.append("the folder file was not read (no call into the memory folder in a turn after the compaction)" if not in_scope else
                       "the folder file was not read through a call whose result held the token (the student's own input echo stripped)")
    # (c) and its exception (c'): the other channel returned the token (after strip_echo_once) unless the returned item is
    # IDENTIFIED as one the student wrote after its first intended read
    ewrites, created = [], {}
    if first_i is not None and ch == "folder":
        ewrites = [(i, ti, c, created_ids(c["result"] or "")) for i, (ti, c) in enumerate(flat)
                   if i > first_i and ENGRAM_ANY.match(c["name"]) and not ENGRAM_READ.match(c["name"])]
    elif first_i is not None:
        created = created_files(flat, first_i, folder_files)
    returned, excused = False, {}
    for j, (_, c) in enumerate(flat):
        if not other_channel(ch, c, folder_files) or not has(echo_once_result(c, tok), tok):
            continue
        if ch == "folder":
            later = {}
            for i, ti, w, ids in ewrites:
                if i < j:
                    for nid in ids:
                        later.setdefault(nid, f"{w['name']}, turn {ti + 1}")
            got = excused_node_ids(c, tok, set(later)) if later else None
            if got:
                excused.update({nid: later[nid] for nid in got})
                continue
        elif first_i is not None:
            got = excused_files(c, j, created, folder_files)
            if got:
                excused.update({fp: f"{flat[i][1]['name']}, turn {flat[i][0] + 1}" for i, fp in got})
                continue
        returned = True
    if returned:
        why.append("a call into the memory folder (Read, Grep, Glob or a shell command) returned the token in this session (the other channel)"
                   if ch == "engram" else "an ENGRAM read returned the token in this session (the other channel)")
    if excused and not returned:
        what = ("only inside node(s) the student itself wrote after its first intended read" if ch == "folder" else
                "only from file(s) the student itself created with a Write after its first intended read")
        notes.append(f"(c') the other channel returned the token {what}, so it does not count against the fact: "
                     + "; ".join(f"{k} ({v})" for k, v in sorted(excused.items())))
    opens = [(i, k) for i, (_, c) in enumerate(flat) for k in [opening(c, tok, folder_files, opener_paths)] if k]  # (d')
    if opens and first_i is not None:
        i, kind = opens[0]
        ti, c = flat[i]
        what = ("the evidence file or the run directory was opened" if kind == "named" else
                "a file-capable call returned the token from a path outside both channels")
        if i <= first_i:
            why.append(f"{what} before the first intended read (turn {ti + 1}, {c['name']})")
        else:
            notes.append(f"{what} after the first intended read (turn {ti + 1}, {c['name']}): does not void the pass")
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
            print("  first intended read: " + (f"{first[1]['name']} {json.dumps(first[1]['input'])[:160]} (turn {first[0] + 1}, event {first[1]['ev'] + 1})"
                                              if first else "none"))
            print("  answer (reported, decides nothing): " + answer[:300].replace("\n", " "))
            for n in notes:
                print(f"  note: {n}")
        if verdict == "FAIL":
            bad.append(c["id"])
    others = [(ti, c) for ti, c in flat if not ENGRAM_ANY.match(c["name"]) and c["name"] != "Read"]
    if others:
        print("other-kind tool calls in the session (listed for the human; one marked [folder channel] targets the memory "
              "folder and is a folder read, the rest neither pass nor fail a control):")
        for ti, c in others[:40]:
            mark = " [folder channel]" if folder_target(c, folder_files) else ""
            print(f"  turn {ti + 1}: {c['name']}{mark} {json.dumps(c['input'])[:100]}")
        if len(others) > 40:
            print(f"  ... and {len(others) - 40} more")
    print("RESULT: " + ("no control failed (a human still judges the 'none' answer)" if not bad else f"FAIL {bad}"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
