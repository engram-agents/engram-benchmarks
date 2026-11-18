#!/usr/bin/env python3
"""Control source check (BEAM P1 answering). This file is the study's harness, not shipped product code.

For each of the planted-fact control questions (three, or two in the two-control session below), decides whether the planted fact was REACHABLE through its intended
channel, read off the tool calls of the whole answering session. The answer text is never used to pass or fail an
engram/folder control: it is printed beside the verdict for a human (answered / refused / abstained decides nothing; this
tool never classifies a refusal). For the 'none' control it prints the answer for a human to judge, and fails only if the
answer contains a planted token.

Inputs (all written by feed4.py and the planting step):
  --events    events.jsonl, every stream-json event of the run (assistant tool_use blocks, user tool_result blocks,
              one `result` event per turn);
  --turns     turns.jsonl; row k is the k-th `result` event's turn, and a question row carries the item's "id" (a row of
              kind "compact" is the compaction turn);
  --controls  JSON list of {id, token, channel: "engram"|"folder"|"none", folder_file?, memory_dir?, evidence_file?, run_dir?}.
              The 'none' control's token is the absent (planted nowhere) value. `run_dir` is an optional per-control field
              (a control file without it is accepted unchanged); the run directories of all controls are watched together,
              like the evidence files.

ACCEPTED CONTROL SETS (exactly two; the design owner's ruling on control 2, narrow form: "engram + absent only, every other
subset still refused"):
  (i)  {engram, folder, none}, one control of each channel: read exactly as before, and `memory_dir` is not allowed in it.
  (ii) {engram, none}, one each, where the engram control carries `memory_dir`: the ABSOLUTE path of the student's built-in
       memory folder, with a `/.claude/` segment (the student's home is the part before it, as for a folder_file). It need
       not exist on disk (compared by realpath of the string, as every path here). There is no folder control and no folder
       token: the folder channel is then the directory `memory_dir`, and wherever the folder is derived (the folder
       directories, the home for S7's `~` / `$HOME`, S8's in-folder test) it comes from `memory_dir` instead of the
       directory of a folder_file; the absent folder token is handled explicitly (the none control's token check runs over
       the tokens that exist, the engram token only), and an absent folder token never makes anything PASS that would
       otherwise fail.
Every other set is REFUSED, exit 1, with a message naming the set received: {engram}, {folder}, {none}, {folder, none},
{engram, folder}, an empty list, a duplicated channel, (ii) without `memory_dir` or with a relative one, one with no
`/.claude/` segment (or none after a home: `/.claude/...`) or one that is not a string, and `memory_dir` given on a
three-channel set or on any control but the engram one (two sources for the folder: refuse rather than choose).

Design principle (PR 8 reviewer rounds 2 and 3). Every approximation this instrument makes errs toward FAIL for the clause
it serves: where it cannot tell, a fact fails rather than passes.

The class rule (round 3). Rounds 2 and 3 each found the next member of ONE class: a place where the instrument decides that
something DOES NOT COUNT (an echo, the student's own write, a mention, a non-target) on a heuristic that a stream outside the
heuristic's assumption turns into a false PASS. So:
  1. ENUMERATE every exemption site: every code path whose effect is that a token occurrence, a call or a write is NOT counted
     against a fact, or NOT counted as an opening or as an other-channel read. For each, the list below names (a) what it
     exempts, (b) the POSITIVE, KNOWN-SHAPE evidence it requires, (c) what happens when that evidence is absent or the shape
     is unknown: it COUNTS, toward FAIL. No exemption rests on "this tool usually does not X".
  2. Each site has test cells (tests/, `test_r3_sN_*`) that feed it an unknown or off-shape input and assert it counts.

KNOWN RESULT SHAPES. S2 and S3 read fields of an ENGRAM tool result, which is recorded in the stream in one of two shapes: the
bare inner JSON object (the shape of the fixtures and of the server's own return), or the ENVELOPE Claude Code records for an
MCP tool: a JSON object with exactly one key "result" whose value is a string holding the inner JSON,
`{"result": "{\\"status\\": \\"created\\", ...}"}` (measured on a real session record). `unwrap_envelope` recognises exactly
that envelope and `parse_result` applies it; the inner value is what S2 and S3 read. Any other shape (a second key, another
key name, a `result` that is not a string, a `result` string that is not JSON) is NOT unwrapped: it is read as it parses,
so S2 strips no echo and S3 reports no id (they count, toward FAIL).

EXEMPTION SITES (the full list; read the rule text below for the clauses they serve)
  S1 (a)'s strip-all. Exempts: an occurrence of a string leaf of the call's own input from counting as the intended-channel
     read. Evidence: the occurrence equals or lies inside such a leaf. Unknown: it is removed all the same, so the fact
     FAILs (the safe direction for (a): over-stripping can only fail the fact).
  S2 the echo strip of (c) and (d'). Exempts: the echo of the student's query from counting as an other-channel return or
     an opening. Evidence: the call is engram_query or engram_surface of the pinned server, the result parses as a JSON
     object, and it has a top-level string field `query` (both tools echo it: engram_query.py:3237 tiered, :3199 debug;
     :2843 and :2611 for surface). Only the value of that one field is removed. Unknown: no echo is removed, the return
     counts. Every other tool is unknown, `engram_list` included (its structured result carries stored nodes and no echo of
     its filter, engram_query.py:3802-3817), and so is a result that does not parse or has no top-level `query`. (a) keeps
     S1.
  S3 (c') ENGRAM side, the student's own node. Exempts: a returned node from counting as a return of the other channel.
     Evidence: the node's id was REPORTED CREATED by a creating tool of the pinned server, under that tool's own key and with
     the same result's `status` "created", before the read and after the first intended read: engram_add_observation ->
     observation_id (engram_observation.py:2176); engram_add_observation_batch -> each item of the top-level `results` list
     that reports status "created", its observation_id (items are the single call's result, engram_observation.py:2808);
     engram_derive -> derivation_id (engram_derive.py:335); engram_add_conjecture -> conjecture_id (engram_epistemic.py:575);
     engram_ask -> question_id (engram_derive.py:775); engram_add_definition -> definition_id (engram_epistemic.py:448).
     Not creating, so no id: engram_supersede (pure-wire: its `new_node_id` is the caller's input echoed back, server.py:7359-
     7361, :7410, engram_revision.py:3857; the replacement is created by the tool that came first), engram_contradict (its
     `conflicts.node_a/node_b` `id`s are two EXISTING nodes, engram_derive.py:597-600, and its `contradiction_id` names the
     contradiction node, not a node the student claims), engram_retract, engram_resolve, engram_add_edge, engram_link_about
     and every other tool. No bare `id` key, no generic key. Unknown: an unknown tool, a result that does not parse, is not
     a JSON object, has no status "created", or whose key is absent, not a string or nested, reports no id; the return
     counts. A read result is excused only if every dict with an `id` that holds the token carries such an id and no token
     lies outside those dicts (after S2).
  S4 (c') FOLDER side, the student's own file. Exempts: a read of a file from counting as a return of the other channel.
     Evidence: a `Write` call with an absolute `file_path` whose result REPORTS the file "created successfully" (an
     overwrite is reported "updated"), after the first intended read, no earlier call having named the file (full path or
     base name); the read comes after the Write and every in-folder path it targets is such a file. An Edit or MultiEdit
     never creates; a write through Bash is not recognized. Unknown: a Write whose result does not say created, a relative
     path, any other tool: no creation, the return counts.
  S5 (d') FILE-CAPABLE. Exempts: a call from being an opening (a path in its arguments or its results is then a mention).
     Evidence: the call is one of NOT_FILE_CAPABLE (ToolSearch, TodoWrite, ExitPlanMode, EnterPlanMode, AskUserQuestion), or
     a tool of the PINNED ENGRAM server (prefix mcp__plugin_engram_engram__). Unknown: every other call is file-capable (Read,
     Bash, Grep, Glob, NotebookRead, LS, Task, Agent, WebFetch, Write, Edit, a tool of any other MCP server, any tool this
     file has never heard of): it opens if it names the evidence file or the run directory, or returns the token whose PATH
     OF ORIGIN is outside both channels (S8) or unknown.
  S6 which ENGRAM tools are the other channel of a folder control. Exempts: a call to the pinned server from being a read of
     the ENGRAM channel. Evidence: the tool is a KNOWN write, that is, declared readOnlyHint=false by the server's @mcp.tool
     annotations (ENGRAM_KNOWN_WRITES: its result is the student's own act, not a read of the graph). Unknown: every other
     tool of the pinned server counts as an ENGRAM read for (c), the pinned read tools, the other readOnlyHint=true tools
     (engram_history, engram_diagnose, engram_stats, engram_cascade_frontier, ...) and a tool the list has never heard of.
     (a) is narrower on purpose: the intended ENGRAM channel is the pinned list ENGRAM_READ only (unknown: it does not pass).
  S7 folder-target recognition in a shell command, and the one residual toward PASS. Exempts: a call from being a read of the
     folder channel. Evidence: a Read/NotebookRead file_path, a Grep/Glob path, or an absolute path word of a Bash command
     that resolves (realpath) inside the folder, with `~`, `$HOME`, `${HOME}` resolved to the home taken from the
     folder_file and adjacent quoted and unquoted segments of one shell word joined (`"$HOME"/.claude/...`, `'~'/...`).
     Unknown: a target the checker cannot resolve is NOT seen. That is inherent in a rule that names the folder channel by
     its target, and the ONE place a PASS can hide a folder return for an engram control: a relative path, a glob, a variable
     other than HOME, a path built by a subshell, a Grep with no `path`, and a Task or Agent
     subagent that reads the memory folder (the subagent's own reads are not in this stream; for the engram control that is a
     note at most, for the folder control the call is not a folder read either).

  S8 the path of origin of a token a call OUTSIDE the folder returned (design owner's conformance ruling, 2026-11-18). A call
     whose target is not inside the memory folder is not a folder read; it is an opening only if the token came from a path
     outside both channels. Exempts: such a call from being an opening, only when EVERY occurrence of the token in its
     result is attributed to a path inside the folder. Evidence: the call is a Bash or a Grep call (the tools whose results
     print `path:line:text` or `path:text`), the line holding the occurrence starts with an ABSOLUTE path, then `:`, the
     token lies in the text after that colon, and the path resolves (realpath) inside the folder. A Read's origin is its own
     absolute `file_path`. An occurrence whose printed path resolves outside the folder is an opening; an occurrence with no
     such printed path (no path, a relative path, a context-line `path-N-text`, the token only in the path, any other tool)
     has NO path of origin: it is read as an opening, which errs toward FAIL, with its own message. One mixed result with a
     single such occurrence opens. The in-folder case prints a note, never a fail. Residual toward PASS: Bash output that
     merely LOOKS like `<in-folder path>:text` (an echo, a file whose content has that shape) is read as that path.

The rule (design owner's ruling, 2026-11-18, final form). An engram/folder fact PASSES iff
  (a) a read through the INTENDED channel, in a turn after both the resume and the compaction, returned the planted token
      in the tool RESULT. The channel is named by its STORAGE. engram = a call to one of the pinned ENGRAM read tools (the
      tool name is exactly mcp__plugin_engram_engram__engram_{query,inspect,get_subgraph,list,list_focused,query_pattern,
      surface}: the server prefix is pinned, a different mcp server never counts); folder = ANY call whose TARGET is inside
      the student's memory folder (the directory of the control's folder_file; realpath compare): a Read/NotebookRead
      file_path, a Grep/Glob path (or an absolute Glob pattern), a Bash command with an absolute path word that resolves
      inside it (a grep, cat, ls or stat of it); see S7 for the shell forms resolved and the bound. A `Read` of a file with
      a folder_file's base name counts wherever it sits (kept from bfab5a3); Write/Edit and MCP tools have no read target.
      The token must be in THAT call's own result after S1's stripping. "After the resume" is the run itself (the events
      file is the resumed session's); "after the compaction" is every turn after the LAST turn row of kind "compact" (no
      such row: every turn). Any such turn counts, not only the control's own;
  (b) a token present only in the student's own query or prompt text never counts. For (a), `strip_strings` (S1) removes
      EVERY occurrence of every string leaf of the call's own input (each JSON string leaf of the tool_use input, plus the
      leaves of any string that is itself JSON, e.g. `payload_json`, decoded; matched case-insensitively, also in its
      JSON-escaped spelling, replaced by a NUL so neighbours never splice into a token). Bound: a stored value that equals
      (or contains, as a whole leaf) the query string, or a one-character leaf, is removed too: a false negative toward
      FAIL. For (c) and (d') only S2 removes anything: a query that is exactly the token, with a store that returned it too,
      leaves the stored occurrence and the return COUNTS, and a Grep, Bash, Read or Glob result is never stripped;
  (c) no read through the OTHER channel returned it in that session (all turns, before or after the compaction): for an
      engram control a folder-channel read (as in (a)) returning the token, for a folder control an ENGRAM call returning it
      (S6; both after S2). Calls of other kinds (ToolSearch, other MCP tools, writes) neither pass nor fail a control under
      (a)/(c); they are listed. Exception (c'): the returned item is one the student itself wrote in the session AFTER the
      first intended read that returned the token, and the tool IDENTIFIES it, never by its text: for a folder control the
      node ids of S3, for an engram control the files of S4. The returning read must come after the write. Writes BEFORE the
      first intended read never excuse anything, an other-channel return before it is never excused, and a pre-existing item
      holding the token still FAILs. When the exception is what prevented a FAIL, a `note:` names the node id(s) with the
      write (tool, turn), or the file path with its Write (turn). The check relies on the tool result's shape, so a result
      the channel reshapes is read as unparseable: a false negative toward FAIL;
  (d) the evidence file or the run directory opened BEFORE the first read that satisfies (a) FAILs, in stream order
      across the whole session (the satisfying call itself naming it counts as before: the conservative side); opened
      AFTER it is only noted. (d') An OPENING is a FILE-CAPABLE call (S5) that EITHER names the evidence file or the run
      directory ('named' = its full path or its base name appearing in the call's input, `~` / `$HOME` / `${HOME}`
      expanded and quote-split words joined as in S7) OR returns the token while its target is NOT inside the memory folder
      and the token's path of origin is outside both channels or not printed (S8; nothing is echo-stripped there). A token
      such a call returns from a path PRINTED inside the memory folder is neither a folder read nor an opening: a note.
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
# S2: the pinned tools that hand the student's query back, in a top-level string field `query` (engram_query.py:3237 tiered,
# :3199 debug; :2843 surface, :2611 surface no-match). engram_list does not (engram_query.py:3802-3817): it is NOT here.
ENGRAM_ECHO_TOOLS = frozenset(ENGRAM_SERVER_PREFIX + n for n in ("engram_query", "engram_surface"))
ECHO_KEY = "query"


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


class MemoryDir(str):
    """An entry of `folder_files` that is already the memory DIRECTORY (set (ii)'s `memory_dir`), not a file inside it. Every
    other entry is a folder_file, whose directory is the folder. home_of (the `/.claude/` split) reads both alike."""


def home_of(folder_files):
    """The student's home: the part of a folder_file's (or the memory_dir's) path before "/.claude/" (None if none has one)."""
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


def fold_quotes(s):
    """S7: join the adjacent quoted and unquoted segments of one shell word (`"$HOME"/.claude/x`, `'~'/x`) by dropping the quote
    characters, also the backslash-escaped quote of a JSON dump. Only ever an ADDITIONAL candidate beside the raw text."""
    return re.sub(r'\\"|["\']', "", s)


def names_file(call, path, home=None):
    """(d') 'named': the path or its base name appears in the call's input (`~` / `$HOME` / `${HOME}` expanded, quote-split
    words joined)."""
    s = json.dumps(call["input"]) if call["input"] is not None else ""
    return (path in s or os.path.basename(path) in s or path in expand_home(s, home)
            or path in expand_home(fold_quotes(s), home))


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


def obj_holds(x, tok):
    """True if a parsed JSON value holds the token in its serialization (keys included) or in any string leaf (decoded)."""
    out = []
    string_leaves(x, out)
    return has(json.dumps(x, ensure_ascii=False), tok) or any(has(v, tok) for v in out)


def without_echo(call, obj):
    """S2: the parsed result with the one KNOWN echo removed: the top-level string `query` of engram_query / engram_surface.
    Anything else (another tool, a result that is not an object, no top-level string `query`) is returned unchanged."""
    if call["name"] in ENGRAM_ECHO_TOOLS and isinstance(obj, dict) and isinstance(obj.get(ECHO_KEY), str):
        return {**obj, ECHO_KEY: None}
    return obj


def returns_token(call, tok):
    """The call's result holds the token for (c) and (d'), after S2's echo removal. A result that does not parse, a tool that
    is not a known echo tool and a result without the known echo field are not stripped at all (toward FAIL)."""
    raw = call["result"] or ""
    if not has(raw, tok):
        return False
    if call["name"] not in ENGRAM_ECHO_TOOLS:
        return True
    obj = parse_result(raw)
    if not (isinstance(obj, dict) and isinstance(obj.get(ECHO_KEY), str)):
        return True
    return obj_holds(without_echo(call, obj), tok)


# ---- the folder channel is named by STORAGE (rule (a)): any call whose target is inside the memory folder
# (d'): file-capable by DEFAULT-DENY. Every call can return file content except these and any "mcp__" tool, so a tool this
# file has never heard of (Task, Agent, WebFetch, a new one) counts as file-capable, toward FAIL.
NOT_FILE_CAPABLE = frozenset({"ToolSearch", "TodoWrite", "ExitPlanMode", "EnterPlanMode", "AskUserQuestion"})
CREATE_TOOLS = frozenset({"Write"})   # (c') folder side: only a Write creates a file; an Edit/MultiEdit never does
BASH_ABS_PATH = re.compile(r"(?<![\w.~/-])/[^\s'\"`;|&<>()=:,]*")   # an absolute path word of a shell command
# S3 (c') ENGRAM side: the tools that CREATE a node, each with the key its own success result reports the new id under (the
# success result is the one with "status": "created"). Read from the pinned plugin source:
#   engram_add_observation        observation_id   engram_observation.py:2176
#   engram_add_observation_batch  results[].observation_id, one per item  engram_observation.py:2808 (item = the line above)
#   engram_derive                 derivation_id    engram_derive.py:335
#   engram_add_conjecture         conjecture_id    engram_epistemic.py:575
#   engram_ask                    question_id      engram_derive.py:775
#   engram_add_definition         definition_id    engram_epistemic.py:448
# Deliberately NOT here: engram_supersede (pure-wire: `new_node_id` is the caller's input echoed back, server.py:7359-7361,
# :7410, engram_revision.py:3857), engram_contradict (`conflicts.node_a/node_b` carry the `id` of two EXISTING nodes,
# engram_derive.py:597-600; its `contradiction_id` names the contradiction node), engram_retract, engram_resolve,
# engram_add_edge, engram_link_about, and every unknown tool. No bare `id` and no generic key.
CREATING_KEYS = {"engram_add_observation": "observation_id", "engram_add_observation_batch": "observation_id",
                 "engram_derive": "derivation_id", "engram_add_conjecture": "conjecture_id", "engram_ask": "question_id",
                 "engram_add_definition": "definition_id"}
BATCH_TOOL = "engram_add_observation_batch"
CREATED_FILE_RESULT = re.compile(r"\bcreated successfully\b", re.IGNORECASE)   # S4: what a Write reports for a NEW file
# S6: the pinned server's KNOWN writes: the @mcp.tool entries of server.py that declare readOnlyHint=false (49 of 64 tools on
# the plugin this was read from). Their results are the student's own act, so they are not a read of the ENGRAM channel; every
# other tool of the server (the readOnlyHint=true ones and any unknown one) counts as an ENGRAM read for (c). The cell
# `test_r3_s6_the_known_write_list_...` checks this list against the plugin tree named by P1_ENGRAM_PLUGIN.
ENGRAM_KNOWN_WRITES = frozenset("""
engram_add_observation engram_requote engram_add_observation_batch engram_cascade_start_unblock engram_cascade_end_unblock
engram_cascade_resolve engram_checkpoint engram_nap engram_advance_turn engram_reflect engram_add_axiom engram_add_definition
engram_add_conjecture engram_add_goal engram_deactivate_goal engram_activate_goal engram_add_person engram_update_person
engram_add_special_moment engram_set_trust_tier engram_set_person_lineage engram_add_trust_signal engram_add_cornerstone
engram_outgrow_cornerstone engram_link_about engram_remove_edge engram_add_edge engram_retype_edge engram_goal_tension
engram_add_lesson engram_lesson_register_incident engram_update_lesson engram_register_exemplar engram_add_task
engram_update_task engram_report_feeling engram_derive engram_contradict engram_ask engram_resolve engram_supersede
engram_retract engram_focus engram_unfocus engram_focus_save engram_focus_load engram_focus_swap engram_focus_delete_set
engram_set_recall_summaries
""".split())


def file_capable(name):
    """S5: not file-capable only the named harness tools and the tools of the PINNED ENGRAM server; every other call, a tool
    of another MCP server included, is file-capable (default-deny)."""
    return not (name.startswith(ENGRAM_SERVER_PREFIX) or name in NOT_FILE_CAPABLE)


def folder_dirs(folder_files):
    return [os.path.realpath(p if isinstance(p, MemoryDir) else os.path.dirname(p)) for p in folder_files]


def inside(path, dirs):
    rp = os.path.realpath(path)
    return any(rp == d or rp.startswith(d + os.sep) for d in dirs)


def folder_target_paths(call, folder_files):
    """The paths, as the call wrote them, that the call TARGETS inside the memory folder (the directory of a control's
    folder_file; realpath compare): Read/NotebookRead file_path; Grep/Glob path (a Glob pattern that is itself absolute
    too); a Bash command's absolute path words (`~`, `$HOME`, `${HOME}` expanded to the home taken from the folder_file,
    adjacent quoted and unquoted segments of a word joined).
    A `Read` of a file whose base name is a folder_file's counts as well (the bfab5a3 matching). Write/Edit and MCP tools
    have no read target. An empty list = the call is not in the folder channel."""
    inp = call["input"] if isinstance(call["input"], dict) else {}
    dirs = folder_dirs(folder_files)
    n = call["name"]
    if n in ("Read", "NotebookRead"):
        got = inp.get("file_path") or inp.get("path") or inp.get("notebook_path") or ""
        ok = bool(got) and (inside(got, dirs) or (n == "Read" and any(os.path.basename(got) == os.path.basename(p)
                                                                       for p in folder_files if not isinstance(p, MemoryDir))))
        return [got] if ok else []
    if n in ("Grep", "Glob"):
        cands = [inp.get("path")] + ([inp.get("pattern")] if n == "Glob" and str(inp.get("pattern", "")).startswith("/") else [])
        return [c for c in cands if isinstance(c, str) and c and inside(c, dirs)]
    if n == "Bash":
        cmd = inp.get("command")
        if not isinstance(cmd, str):
            return []
        home = home_of(folder_files)
        words = BASH_ABS_PATH.findall(expand_home(cmd, home)) + BASH_ABS_PATH.findall(expand_home(fold_quotes(cmd), home))
        return [m for m in dict.fromkeys(words) if inside(m, dirs)]
    return []


def folder_target(call, folder_files):
    return bool(folder_target_paths(call, folder_files))


def intended(ch, call, folder_files):
    return bool(ENGRAM_READ.match(call["name"])) if ch == "engram" else folder_target(call, folder_files)


def engram_counts_as_read(name):
    """S6: a call of the pinned server is a read of the ENGRAM channel unless it is a KNOWN write."""
    return name.startswith(ENGRAM_SERVER_PREFIX) and name[len(ENGRAM_SERVER_PREFIX):] not in ENGRAM_KNOWN_WRITES


def other_channel(ch, call, folder_files):
    return folder_target(call, folder_files) if ch == "engram" else engram_counts_as_read(call["name"])


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


def unwrap_envelope(outer):
    """The ONE known envelope: Claude Code records an ENGRAM MCP tool result as `{"result": "<inner JSON as a string>"}`.
    `outer` is the plain json.loads of the result text. Returns the inner JSON value iff `outer` is a dict with exactly the
    one key "result" whose value is a string that itself parses as JSON; anything else (two keys, another key, a `result`
    that is not a string, a string that is not JSON) is returned unchanged. No other shape is unwrapped."""
    if isinstance(outer, dict) and len(outer) == 1 and isinstance(outer.get("result"), str):
        try:
            return json.loads(outer["result"], strict=False)
        except (ValueError, RecursionError):
            pass
    return outer


def parse_result(text):
    """A tool result as a decoded JSON value (the known envelope unwrapped), or None if it does not parse. Every site that
    reads a field of an ENGRAM tool result (S2 echo, S3 created ids and the returned nodes) goes through here."""
    try:
        return deep_decode(unwrap_envelope(json.loads(text, strict=False)))
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


def created_ids(call):
    """S3: the ids a creating tool of the pinned server reports CREATED in its own result (CREATING_KEYS): a JSON object
    whose `status` is "created" and whose creation key is a string; for the batch, each item of the top-level `results`
    list that reports the same. Any other tool, shape or status: no id."""
    name = call["name"]
    key = CREATING_KEYS.get(name[len(ENGRAM_SERVER_PREFIX):]) if name.startswith(ENGRAM_SERVER_PREFIX) else None
    obj = parse_result(call["result"] or "") if key else None
    if not isinstance(obj, dict):
        return set()
    items = [obj]
    if name[len(ENGRAM_SERVER_PREFIX):] == BATCH_TOOL:
        items = obj.get("results") if isinstance(obj.get("results"), list) else []
    return {it[key] for it in items if isinstance(it, dict) and it.get("status") == "created" and isinstance(it.get(key), str)}


def excused_node_ids(call, tok, later_ids):
    """(c'), ENGRAM as the other channel: the set of excused node ids of an ENGRAM result that holds the token, or None if
    the return counts. Excused only if the result parses, every dict with an `id` whose string values hold the token has the
    id of a node the student wrote later (`later_ids`), and no occurrence of the token lies outside those dicts (after S2)."""
    obj = parse_result(call["result"] or "")
    if obj is None:
        return None
    obj = without_echo(call, obj)
    holders = [d for d in walk_dicts(obj) if isinstance(d.get("id"), str) and dict_holds(d, tok)]
    if not holders or not {d["id"] for d in holders} <= later_ids:
        return None
    if obj_holds(without_dicts(obj, {id(d) for d in holders}), tok):
        return None
    return {d["id"] for d in holders}


def created_files(flat, first_i, folder_files):
    """(c') FOLDER as the other channel: {realpath: (index, path as written)} of the files the student itself CREATED with a
    Write after the first intended read (flat index > first_i), no call before that Write naming the file. An Edit or a
    MultiEdit is never a creation (the file may already have held the token). S4: the Write has an absolute path and its
    result says "created successfully" (an overwrite is reported "updated"); anything else is no creation."""
    home, out = home_of(folder_files), {}
    for i, (_, c) in enumerate(flat):
        fp = c["input"].get("file_path") if isinstance(c["input"], dict) else None
        if (i <= first_i or c["name"] not in CREATE_TOOLS or not isinstance(fp, str) or not os.path.isabs(fp)
                or not CREATED_FILE_RESULT.search(c["result"] or "")):
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


ORIGIN_LINE = re.compile(r"^(/[^:\n]*):(.*)$")   # S8: a printed `path:line:text` / `path:text` (absolute path, first colon)


def token_origins(c, tok, folder_files):
    """S8: where the token a call returned CAME FROM, one entry per occurrence-bearing line: "in" (an absolute printed path
    inside the memory folder), "out" (an absolute printed path outside it), "none" (no known-shape printed path: unknown).
    A Read is its own origin (its absolute file_path); only Bash and Grep results are read for printed `path:...` lines;
    every other tool, a relative path and any other line shape is "none" (counts, toward FAIL)."""
    dirs = folder_dirs(folder_files)
    inp = c["input"] if isinstance(c["input"], dict) else {}
    if c["name"] in ("Read", "NotebookRead"):
        fp = inp.get("file_path") or inp.get("path") or inp.get("notebook_path")
        if isinstance(fp, str) and os.path.isabs(fp):
            return ["in" if inside(fp, dirs) else "out"]
        return ["none"]
    out = []
    for line in (c["result"] or "").splitlines():
        if not has(line, tok):
            continue
        m = ORIGIN_LINE.match(line) if c["name"] in ("Bash", "Grep") else None
        if m and has(m.group(2), tok):
            out.append("in" if inside(m.group(1), dirs) else "out")
        else:
            out.append("none")
    return out or ["none"]   # the token is in the result but on no line this reads (a multi-line token): unknown


def opening(c, tok, folder_files, opener_paths):
    """(d'): 'named' if a FILE-CAPABLE call (default-deny, see NOT_FILE_CAPABLE) names the evidence file / run directory
    (full path or base name); for a call whose target is NOT inside the memory folder and that returns the token (nothing
    echo-stripped: S2), by the token's path of origin (S8): 'outside' if any occurrence came from a printed path outside both
    channels, 'unprinted' if none did but one has no printed path (read as an opening: toward FAIL), 'infolder' if EVERY
    occurrence came from a printed in-folder path (neither a folder read nor an opening: only a note); None otherwise (an
    MCP tool, ToolSearch and the like only mention)."""
    if not file_capable(c["name"]):
        return None
    home = home_of(folder_files)
    if any(names_file(c, p, home) for p in opener_paths):
        return "named"
    if not folder_target(c, folder_files) and returns_token(c, tok):
        origins = set(token_origins(c, tok, folder_files))
        return "outside" if "out" in origins else ("unprinted" if "none" in origins else "infolder")
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
    # (c) and its exception (c'): the other channel returned the token (after S2) unless the returned item is
    # IDENTIFIED as one the student wrote after its first intended read
    ewrites, created = [], {}
    if first_i is not None and ch == "folder":
        ewrites = [(i, ti, c, created_ids(c)) for i, (ti, c) in enumerate(flat) if i > first_i]
    elif first_i is not None:
        created = created_files(flat, first_i, folder_files)
    returned, excused = False, {}
    for j, (_, c) in enumerate(flat):
        if not other_channel(ch, c, folder_files) or not returns_token(c, tok):
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
    kinds = [opening(c, tok, folder_files, opener_paths) for _, c in flat]
    for i, k in enumerate(kinds):  # S8: a call outside the folder that returned the token from a PRINTED in-folder path
        if k == "infolder":
            notes.append(f"(turn {flat[i][0] + 1}, {flat[i][1]['name']}) returned the token from an "
                         "in-folder path through a call outside the folder: not a folder read, not an opening")
    opens = [(i, k) for i, k in enumerate(kinds) if k and k != "infolder"]  # (d')
    if opens and first_i is not None:
        i, kind = opens[0]
        ti, c = flat[i]
        what = ("the evidence file or the run directory was opened" if kind == "named" else
                "a call outside the folder returned the token (no path of origin printed; read as an opening, which errs toward FAIL)"
                if kind == "unprinted" else
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


def check_control_set(ctls):
    """None if `ctls` is one of the two accepted sets (see the module docstring), else the reason it is refused."""
    chs = sorted(c["channel"] for c in ctls)
    if chs == sorted(CHANNELS):
        return ("`memory_dir` is not allowed on a three-channel set (two sources for the folder)"
                if any("memory_dir" in c for c in ctls) else None)
    if chs != ["engram", "none"]:
        return "not an accepted set of channels"
    if any("memory_dir" in c for c in ctls if c["channel"] != "engram"):
        return "`memory_dir` belongs on the engram control only"
    md = next(c for c in ctls if c["channel"] == "engram").get("memory_dir")
    if not isinstance(md, str) or not os.path.isabs(md) or md.find("/.claude/") <= 0:
        return "the engram control needs `memory_dir`: an absolute path with a /.claude/ segment after a home"
    return None


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
    refusal = check_control_set(ctls)
    if refusal:
        print(f"FAIL: the controls must be one of two sets, {{engram, folder, none}} one each, or {{engram, none}} one each with "
              f"an absolute `memory_dir` (a /.claude/ path) on the engram control; {refusal}; got {[c['channel'] for c in ctls]}")
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
    # set (i): the folder is the directory of the folder control's folder_file; set (ii): the engram control's memory_dir
    folder_files = ([c["folder_file"] for c in ctls if c.get("folder_file")] if "folder" in tokens else
                    [MemoryDir(c["memory_dir"]) for c in ctls if c["channel"] == "engram"])
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
