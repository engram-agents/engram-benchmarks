"""Part D cells: control-source-check.py on synthetic stream-json events + turn records. Contract-first.

A turn's events are everything up to and including its `result` event; turns.jsonl row k belongs to the k-th result
event (feed4.py's ask() returns at the first result event of each message).

Rule under test (the design owner's ruling of 2026-11-18, clauses (a)-(d)): a planted fact PASSES on REACHABILITY, never on
the answer text. The cells from "P1 REACHABILITY" on are the new contract; the earlier engram/folder cells were rewritten
where they encoded the superseded answer-based rule."""
import json, os, subprocess, sys
import pytest
from conftest import TOOLS

TOOL = os.path.join(TOOLS, "control-source-check.py")
SESS = "s-1"
FOLDER_FILE = "/arm/.claude/projects/-w/memory/reference_note_dd439b25.md"
EVID_FILE = "/ev/9f2c0a7e1b.txt"
T_ENGRAM, T_FOLDER, T_ABSENT = "MN-4K9T", "QX-7Z4R", "ZP-3L8W"
CONTROLS = [
    {"id": "c-engram", "token": T_ENGRAM, "channel": "engram", "evidence_file": EVID_FILE},
    {"id": "c-folder", "token": T_FOLDER, "channel": "folder", "folder_file": FOLDER_FILE, "evidence_file": EVID_FILE},
    {"id": "c-none", "token": T_ABSENT, "channel": "none"},
]
ENG_Q = "mcp__plugin_engram_engram__engram_query"
ENG_I = "mcp__plugin_engram_engram__engram_inspect"
ENG_W = "mcp__plugin_engram_engram__engram_add_observation"


ENG_HIT = f'{{"results":[{{"summary":"{T_ENGRAM}"}}]}}'  # an ENGRAM read result that carries the engram token


def call(name, inp, result):
    return {"name": name, "input": inp, "result": result}


class Run:
    """Builds events.jsonl and turns.jsonl: a compact turn, then one turn per (id, answer, calls)."""
    def __init__(self):
        self.events, self.turns, self.n = [], [], 0

    def turn(self, kind, qid, answer, calls=()):
        self.n += 1
        for k, c in enumerate(calls):
            tid = f"t{self.n}-{k}"
            self.events.append({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": tid, "name": c["name"], "input": c["input"]}]}})
            self.events.append({"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": tid, "content": c["result"]}]}})
        self.events.append({"type": "assistant", "message": {"content": [{"type": "text", "text": answer}]}})
        self.events.append({"type": "result", "result": answer, "session_id": SESS})
        row = {"i": self.n, "kind": kind, "session_id": SESS, "result": answer}
        if qid is not None:
            row["id"] = qid
        self.turns.append(row)
        return self

    def write(self, tmp_path):
        e, t = tmp_path / "events.jsonl", tmp_path / "turns.jsonl"
        e.write_text("".join(json.dumps(x) + "\n" for x in self.events))
        t.write_text("".join(json.dumps(x) + "\n" for x in self.turns))
        return str(e), str(t)


def run_check(tmp_path, run, controls=CONTROLS):
    e, t = run.write(tmp_path)
    c = tmp_path / "controls.json"; c.write_text(json.dumps(controls))
    return subprocess.run([sys.executable, TOOL, "--events", e, "--turns", t, "--controls", str(c)],
                          capture_output=True, text=True)


def good_engram_turn(run):
    return run.turn("question", "c-engram", f"The code is {T_ENGRAM}.",
                    [call(ENG_Q, {"query": "vault code"}, f'{{"results":[{{"id":"ob_1","summary":"code {T_ENGRAM}"}}]}}')])


def good_folder_turn(run):
    return run.turn("question", "c-folder", f"It is {T_FOLDER}.",
                    [call("Read", {"file_path": FOLDER_FILE}, f"---\nname: n\n---\nthe lantern code {T_FOLDER}\n"),
                     call(ENG_Q, {"query": "lantern"}, '{"results":[]}')])


def good_none_turn(run, answer="I have no record of that."):
    return run.turn("question", "c-none", answer, [call(ENG_Q, {"query": "tide gauge"}, '{"results":[]}')])


def good_run():
    r = Run().turn("compact", None, "compacted")
    good_engram_turn(r); good_folder_turn(r); good_none_turn(r)
    return r


def verdicts(out):
    """{control id: first word after the id on its verdict line}"""
    v = {}
    for ln in out.splitlines():
        for cid in ("c-engram", "c-folder", "c-none"):
            if ln.startswith(cid + ":"):
                v[cid] = ln.split(":", 1)[1].split()[0]
    return v


def test_all_three_pass_and_none_is_left_for_a_human(tmp_path):
    r = run_check(tmp_path, good_run())
    assert r.returncode == 0, r.stdout + r.stderr
    v = verdicts(r.stdout)
    assert v == {"c-engram": "PASS", "c-folder": "PASS", "c-none": "REVIEW"}, r.stdout
    assert "I have no record of that." in r.stdout           # the 'none' answer is shown verbatim
    assert "ENGRAM read" in r.stdout and "Read" in r.stdout  # the tool calls of each turn are listed
    assert "human" in r.stdout.lower()


# ---- engram channel
def engram_run(answer=f"The code is {T_ENGRAM}.", calls=None):
    r = Run().turn("compact", None, "ok")
    r.turn("question", "c-engram", answer, calls if calls is not None else
           [call(ENG_Q, {"query": "vault"}, f'{{"results":[{{"summary":"{T_ENGRAM}"}}]}}')])
    good_folder_turn(r); good_none_turn(r)
    return r


def test_engram_answer_lacking_the_token_decides_nothing(tmp_path):
    """Superseded rule: the answer needed the token. Now the answer is reported and decides nothing."""
    r = run_check(tmp_path, engram_run(answer="I do not remember."))
    assert r.returncode == 0 and verdicts(r.stdout)["c-engram"] == "PASS", r.stdout
    assert "I do not remember." in r.stdout


def test_engram_fails_without_any_engram_read_call(tmp_path):
    r = run_check(tmp_path, engram_run(calls=[]))
    assert r.returncode == 1 and verdicts(r.stdout)["c-engram"] == "FAIL" and "engram read" in r.stdout.lower()


def test_an_engram_write_call_is_not_a_read(tmp_path):
    r = run_check(tmp_path, engram_run(calls=[call(ENG_W, {"claim": "x"}, '{"status":"created"}')]))
    assert verdicts(r.stdout)["c-engram"] == "FAIL"


def test_engram_fails_when_a_folder_read_returned_the_engram_token(tmp_path):
    """(c), rewritten: the folder file read is a failure only when that Read RETURNED the token (a read of it that
    does not return the token is the folder control's business, not a second channel for this fact)."""
    r = run_check(tmp_path, engram_run(calls=[
        call(ENG_Q, {"query": "v"}, ENG_HIT), call("Read", {"file_path": FOLDER_FILE}, f"text {T_ENGRAM}")]))
    assert verdicts(r.stdout)["c-engram"] == "FAIL" and "folder" in r.stdout.lower()


def test_engram_evidence_file_read_before_the_first_channel_read_fails(tmp_path):
    """(d), rewritten: opening the evidence file BEFORE the first channel read voids the pass."""
    r = run_check(tmp_path, engram_run(calls=[
        call("Read", {"file_path": EVID_FILE}, T_ENGRAM), call(ENG_Q, {"query": "v"}, ENG_HIT)]))
    assert verdicts(r.stdout)["c-engram"] == "FAIL" and "evidence" in r.stdout.lower()


def test_engram_a_grep_naming_the_evidence_file_before_the_first_channel_read_fails(tmp_path):
    r = run_check(tmp_path, engram_run(calls=[
        call("Bash", {"command": "grep -r code /ev/9f2c0a7e1b.txt"}, "x"), call(ENG_Q, {"query": "v"}, ENG_HIT)]))
    assert verdicts(r.stdout)["c-engram"] == "FAIL"


def test_engram_a_non_engram_tool_result_showing_the_token_neither_passes_nor_fails(tmp_path):
    """Superseded rule: it failed the control. Now only the two channels matter (a)/(c); a Bash result is listed."""
    r = run_check(tmp_path, engram_run(calls=[
        call(ENG_Q, {"query": "v"}, ENG_HIT), call("Bash", {"command": "grep -r code /ev"}, f"/ev/x.txt: {T_ENGRAM}")]))
    assert verdicts(r.stdout)["c-engram"] == "PASS", r.stdout
    assert "Bash" in r.stdout


def test_a_folder_read_in_another_turn_does_not_fail_the_engram_turn(tmp_path):
    # the good run reads the folder file in the FOLDER turn; the engram turn is judged on its own turn's calls only
    r = run_check(tmp_path, good_run())
    assert verdicts(r.stdout)["c-engram"] == "PASS"


# ---- folder channel
def folder_run(answer=f"It is {T_FOLDER}.", calls=None):
    r = Run().turn("compact", None, "ok")
    good_engram_turn(r)
    r.turn("question", "c-folder", answer, calls if calls is not None else
           [call("Read", {"file_path": FOLDER_FILE}, f"x {T_FOLDER}")])
    good_none_turn(r)
    return r


def test_folder_answer_lacking_the_token_decides_nothing(tmp_path):
    r = run_check(tmp_path, folder_run(answer="no idea"))
    assert r.returncode == 0 and verdicts(r.stdout)["c-folder"] == "PASS", r.stdout
    assert "no idea" in r.stdout


def test_folder_fails_when_the_folder_file_was_not_read(tmp_path):
    r = run_check(tmp_path, folder_run(calls=[call("Bash", {"command": "ls /arm"}, "x")]))
    assert verdicts(r.stdout)["c-folder"] == "FAIL" and "not read" in r.stdout.lower()


def test_folder_fails_when_an_engram_read_returned_the_token(tmp_path):
    r = run_check(tmp_path, folder_run(calls=[
        call("Read", {"file_path": FOLDER_FILE}, "x"), call(ENG_I, {"node_id": "ob_1"}, f"claim {T_FOLDER}")]))
    assert verdicts(r.stdout)["c-folder"] == "FAIL" and "engram" in r.stdout.lower()


def test_folder_evidence_file_read_before_the_first_channel_read_fails(tmp_path):
    r = run_check(tmp_path, folder_run(calls=[
        call("Read", {"file_path": EVID_FILE}, "y"), call("Read", {"file_path": FOLDER_FILE}, f"x {T_FOLDER}")]))
    assert verdicts(r.stdout)["c-folder"] == "FAIL" and "evidence" in r.stdout.lower()


def test_a_bash_cat_of_the_folder_file_is_a_channel_read(tmp_path):
    """Superseded by the final rule: only a `Read` was the folder channel (a Bash cat was not). The channel is now named
    by STORAGE: a Bash command naming a path inside the memory folder whose result holds the token is a folder read."""
    r = run_check(tmp_path, folder_run(calls=[
        call("Bash", {"command": "cat /arm/.claude/projects/-w/memory/reference_note_dd439b25.md"}, T_FOLDER)]))
    assert verdicts(r.stdout)["c-folder"] == "PASS", r.stdout


# ---- none channel
@pytest.mark.parametrize("leak", [T_ENGRAM, T_FOLDER, f"{T_ENGRAM} and {T_FOLDER}"])
def test_none_fails_when_the_answer_contains_a_planted_token(tmp_path, leak):
    r = Run().turn("compact", None, "ok"); good_engram_turn(r); good_folder_turn(r)
    good_none_turn(r, answer=f"The gauge reads {leak}")
    out = run_check(tmp_path, r)
    assert out.returncode == 1 and verdicts(out.stdout)["c-none"] == "FAIL", out.stdout


def test_none_never_decides_abstention(tmp_path):
    for ans in ("I don't know.", "It reads 42 metres.", "I guess about nine."):
        r = Run().turn("compact", None, "ok"); good_engram_turn(r); good_folder_turn(r); good_none_turn(r, answer=ans)
        out = run_check(tmp_path, r)
        assert out.returncode == 0 and verdicts(out.stdout)["c-none"] == "REVIEW" and ans in out.stdout


# ---- structure
def test_fails_when_events_and_turns_do_not_align(tmp_path):
    r = good_run(); r.events.pop()  # drop the last result event
    out = run_check(tmp_path, r)
    assert out.returncode == 1 and "align" in out.stdout.lower()


def test_fails_when_a_control_id_has_no_turn(tmp_path):
    r = Run().turn("compact", None, "ok"); good_engram_turn(r); good_none_turn(r)
    out = run_check(tmp_path, r)
    assert out.returncode == 1 and "c-folder" in out.stdout and "no turn" in out.stdout.lower()


def test_fails_when_a_control_id_has_two_turns(tmp_path):
    r = good_run(); good_engram_turn(r)
    out = run_check(tmp_path, r)
    assert out.returncode == 1 and "more than one turn" in out.stdout.lower()


def test_fails_unless_the_controls_are_one_of_each_channel(tmp_path):
    out = run_check(tmp_path, good_run(), controls=CONTROLS[:2])
    assert out.returncode == 1 and "channel" in out.stdout.lower()


def test_fails_on_an_unreadable_input(tmp_path):
    c = tmp_path / "controls.json"; c.write_text(json.dumps(CONTROLS))
    out = subprocess.run([sys.executable, TOOL, "--events", str(tmp_path / "nope"), "--turns", str(tmp_path / "nope2"),
                          "--controls", str(c)], capture_output=True, text=True)
    assert out.returncode == 1


# ================================================================ ROUND 3 (contract-first)
# ---- R3-3: the engram channel needs a pinned-server ENGRAM read whose OWN result holds the token
def test_engram_fails_when_the_engram_read_result_does_not_hold_the_token(tmp_path):
    """False pass 1: an ENGRAM read returned {} and the answer happens to carry the token."""
    r = run_check(tmp_path, engram_run(calls=[call(ENG_Q, {"query": "vault"}, "{}")]))
    assert r.returncode == 1 and verdicts(r.stdout)["c-engram"] == "FAIL", r.stdout
    assert "engram read" in r.stdout.lower() and "token" in r.stdout.lower()


def test_engram_passes_when_a_later_engram_read_holds_the_token(tmp_path):
    r = run_check(tmp_path, engram_run(calls=[call(ENG_Q, {"query": "a"}, "{}"), call(ENG_I, {"node_id": "ob_1"}, ENG_HIT)]))
    assert verdicts(r.stdout)["c-engram"] == "PASS", r.stdout


@pytest.mark.parametrize("name", ["mcp__other__engram_query", "mcp__plugin_engram_other__engram_query",
                                  "engram_query", "mcp__plugin_engram_engram__engram_query_x",
                                  "xmcp__plugin_engram_engram__engram_query"])
def test_engram_fails_when_the_read_is_not_on_the_pinned_server(tmp_path, name):
    """False pass 3: a different mcp server's (or an unprefixed, or a longer) engram_* tool never counts."""
    r = run_check(tmp_path, engram_run(calls=[call(name, {"query": "vault"}, ENG_HIT)]))
    assert verdicts(r.stdout)["c-engram"] == "FAIL", (name, r.stdout)


# ---- R3-3: the folder channel needs a Read of the folder file, or a token-bearing result of a call touching it
@pytest.mark.parametrize("c", [
    call("Bash", {"command": f"stat {FOLDER_FILE}"}, "File: reference_note_dd439b25.md\n Size: 120"),
    call("Write", {"file_path": FOLDER_FILE, "content": "x"}, "File created successfully"),
    call("Edit", {"file_path": FOLDER_FILE, "old_string": "a", "new_string": "b"}, "updated"),
    call("Bash", {"command": f"ls -l {FOLDER_FILE}"}, "-rw-r--r-- 1 u u 120 reference_note_dd439b25.md"),
])
def test_folder_fails_when_the_file_is_only_stat_listed_or_written(tmp_path, c):
    """False pass 2: stat, ls, or a Write/Edit naming the file is not a read."""
    r = run_check(tmp_path, folder_run(calls=[c]))
    assert verdicts(r.stdout)["c-folder"] == "FAIL" and "not read" in r.stdout.lower(), r.stdout


@pytest.mark.parametrize("c", [
    call("Write", {"file_path": FOLDER_FILE, "content": "x"}, f"wrote {T_FOLDER}"),
    call("Edit", {"file_path": FOLDER_FILE, "old_string": "a", "new_string": "b"}, f"snippet {T_FOLDER}"),
])
def test_a_write_or_edit_never_counts_even_when_its_result_shows_the_token(tmp_path, c):
    """A Write/Edit is not a read: its file_path is not a read target (the final rule keeps this)."""
    r = run_check(tmp_path, folder_run(calls=[c]))
    assert verdicts(r.stdout)["c-folder"] == "FAIL", r.stdout


@pytest.mark.parametrize("c", [
    call("Bash", {"command": f"stat {FOLDER_FILE}"}, f"{T_FOLDER}"),
    call("Bash", {"command": f"ls {FOLDER_FILE}"}, f"{T_FOLDER}"),
])
def test_a_stat_or_ls_of_the_folder_whose_result_shows_the_token_is_a_folder_read(tmp_path, c):
    """Superseded by the final rule: stat/ls never counted. A shell listing of the folder is now a channel read."""
    r = run_check(tmp_path, folder_run(calls=[c]))
    assert verdicts(r.stdout)["c-folder"] == "PASS", r.stdout


def test_a_read_of_the_folder_file_without_the_token_in_the_result_does_not_pass(tmp_path):
    """(a): the token must be in THAT call's tool_result; a Read that returned a truncated view reached nothing."""
    r = run_check(tmp_path, folder_run(calls=[call("Read", {"file_path": FOLDER_FILE}, "(truncated view)")]))
    assert verdicts(r.stdout)["c-folder"] == "FAIL" and "token" in r.stdout.lower(), r.stdout


@pytest.mark.parametrize("path", ["/elsewhere/reference_note_dd439b25.md",
                                  "/arm/.claude/projects/-w/memory/../memory/reference_note_dd439b25.md"])
def test_a_read_matches_by_resolved_path_or_basename(tmp_path, path):
    r = run_check(tmp_path, folder_run(calls=[call("Read", {"file_path": path}, f"x {T_FOLDER}")]))
    assert verdicts(r.stdout)["c-folder"] == "PASS", r.stdout


def test_a_read_of_another_file_is_not_a_folder_read(tmp_path):
    """Superseded by the final rule for a file INSIDE the memory folder (it is a folder read, by storage); a file outside it
    still is not."""
    r = run_check(tmp_path, folder_run(calls=[call("Read", {"file_path": "/arm/.claude/projects/-w/memory/MEMORY.md"}, T_FOLDER)]))
    assert verdicts(r.stdout)["c-folder"] == "PASS", r.stdout
    r = run_check(tmp_path, folder_run(calls=[call("Read", {"file_path": "/arm/.claude/projects/-w/other/MEMORY.md"}, T_FOLDER)]))
    assert verdicts(r.stdout)["c-folder"] == "FAIL" and "not read" in r.stdout.lower(), r.stdout


def test_a_grep_tool_result_from_a_call_touching_the_folder_is_a_channel_read(tmp_path):
    """Superseded by the final rule: only `Read` was the folder channel. A Grep whose `path` is inside the folder and whose
    result holds the token is a folder read (and a Glob likewise)."""
    r = run_check(tmp_path, folder_run(calls=[call("Grep", {"pattern": "code", "path": FOLDER_FILE}, f"line 4: {T_FOLDER}")]))
    assert verdicts(r.stdout)["c-folder"] == "PASS", r.stdout
    r = run_check(tmp_path, folder_run(calls=[call("Grep", {"pattern": "code", "path": "/arm/.claude/projects/-w/memory"}, f"a.md:4: {T_FOLDER}")]))
    assert verdicts(r.stdout)["c-folder"] == "PASS", r.stdout
    r = run_check(tmp_path, folder_run(calls=[call("Glob", {"pattern": "*.md", "path": "/arm/.claude/projects/-w/memory"}, f"a.md {T_FOLDER}")]))
    assert verdicts(r.stdout)["c-folder"] == "PASS", r.stdout
    r = run_check(tmp_path, folder_run(calls=[call("Grep", {"pattern": "code", "path": "/arm/.claude/projects/-w/other"}, f"a.md:4: {T_FOLDER}")]))
    assert verdicts(r.stdout)["c-folder"] == "FAIL", r.stdout


# ---- R3-4: a turn row's result text must equal the k-th result event's text
def test_fails_when_a_turn_rows_result_text_is_swapped(tmp_path):
    r = good_run()
    r.turns[1]["result"], r.turns[2]["result"] = r.turns[2]["result"], r.turns[1]["result"]
    out = run_check(tmp_path, r)
    assert out.returncode == 1 and "align" in out.stdout.lower() and "result" in out.stdout.lower(), out.stdout


def test_fails_when_a_turn_row_has_no_result_text_but_its_event_has_one(tmp_path):
    r = good_run(); r.turns[2]["result"] = None
    out = run_check(tmp_path, r)
    assert out.returncode == 1 and "align" in out.stdout.lower()


def test_an_empty_result_event_aligns_with_the_rows_last_assistant_text(tmp_path):
    """feed4 logs `ev.get('result') or last assistant text`; an empty result event must still align with that."""
    r = good_run()
    r.events[-1] = {"type": "result", "result": "", "session_id": SESS}  # the last turn's result event is empty; its assistant text stays
    out = run_check(tmp_path, r)
    assert out.returncode == 0, out.stdout


# ---- R4-3: rows pair with result events by session_id AND result text (identical texts can no longer swap
# across sessions undetected)
def test_fails_when_a_row_session_id_differs_from_its_result_events_session_id(tmp_path):
    r = good_run()
    r.turns[1]["session_id"] = "s-other"  # same result text, different session: text alone would pair them
    out = run_check(tmp_path, r)
    assert out.returncode == 1 and "align" in out.stdout.lower() and "session" in out.stdout.lower(), out.stdout


def test_fails_when_identical_result_texts_come_from_different_sessions_and_are_swapped(tmp_path):
    r = good_run()
    for ev, sess in zip([e for e in r.events if e.get("type") == "result"], ("s-a", "s-b", "s-a", "s-b")):
        ev["session_id"] = sess
    for row, sess in zip(r.turns, ("s-a", "s-b", "s-a", "s-b")):
        row["session_id"] = sess
        row["result"] = "same text"
    for ev in r.events:
        if ev.get("type") == "result":
            ev["result"] = "same text"
    r.turns[0]["session_id"], r.turns[1]["session_id"] = r.turns[1]["session_id"], r.turns[0]["session_id"]
    out = run_check(tmp_path, r)
    assert out.returncode == 1 and "align" in out.stdout.lower() and "session" in out.stdout.lower(), out.stdout


def test_fails_when_a_row_has_a_session_id_but_its_result_event_has_none(tmp_path):
    r = good_run()
    for e in r.events:
        if e.get("type") == "result":
            e.pop("session_id", None)
    out = run_check(tmp_path, r)
    assert out.returncode == 1 and "align" in out.stdout.lower() and "session" in out.stdout.lower(), out.stdout


# ================================================================ P1 REACHABILITY (contract-first, ruling 2026-11-18)
# A planted fact PASSES iff (a) an intended-channel read in a turn after the compaction returned the token in its tool
# RESULT, (b) the student's own query/prompt echo never counts, (c) no read through the other channel returned it in the
# session, (d) the evidence file / run directory was not opened BEFORE that first read (later is noted, not void).
RUN_DIR = "/runs/r-0001"
CONTROLS_RD = [dict(c, run_dir=RUN_DIR) for c in CONTROLS]


def eng_default():
    return [call(ENG_Q, {"query": "vault"}, ENG_HIT)]


def fol_default():
    return [call("Read", {"file_path": FOLDER_FILE}, f"x {T_FOLDER}")]


def reach_run(eng=None, fol=None, eng_answer=f"The code is {T_ENGRAM}.", fol_answer=f"It is {T_FOLDER}.",
              pre=None, mid=None, compact=True):
    """pre: calls in a turn BEFORE the compaction; mid: calls in a question turn AFTER it, before the controls' turns."""
    r = Run()
    if pre is not None:
        r.turn("warmup", None, "w", pre)
    if compact:
        r.turn("compact", None, "compacted")
    if mid is not None:
        r.turn("question", "mid", "m", mid)
    r.turn("question", "c-engram", eng_answer, eng if eng is not None else eng_default())
    r.turn("question", "c-folder", fol_answer, fol if fol is not None else fol_default())
    good_none_turn(r)
    return r


def first_read_line(out):
    return [ln for ln in out.splitlines() if ln.strip().startswith("first intended read:")]


# ---- 1. refusal quoting the token: reach decides, the quote alone never does
def test_a_refusal_quoting_the_token_passes_when_a_channel_read_returned_it(tmp_path):
    r = run_check(tmp_path, reach_run(eng_answer=f'I did not answer "{T_ENGRAM}" because I was not sure.',
                                      fol_answer=f'I will not state "{T_FOLDER}" as the answer.'))
    assert r.returncode == 0 and verdicts(r.stdout)["c-engram"] == "PASS" and verdicts(r.stdout)["c-folder"] == "PASS", r.stdout
    assert f'I did not answer "{T_ENGRAM}"' in r.stdout            # the refusal is reported beside the verdict


def test_a_refusal_quoting_the_engram_token_without_a_channel_read_returning_it_fails(tmp_path):
    """The mutant the ruling names: a quote alone must NOT pass."""
    r = run_check(tmp_path, reach_run(eng=[call(ENG_Q, {"query": "vault"}, "{}")],
                                      eng_answer=f'I did not answer "{T_ENGRAM}" ...'))
    assert r.returncode == 1 and verdicts(r.stdout)["c-engram"] == "FAIL", r.stdout


def test_a_refusal_quoting_the_folder_token_without_a_channel_read_returning_it_fails(tmp_path):
    r = run_check(tmp_path, reach_run(fol=[call("Read", {"file_path": FOLDER_FILE}, "(view)")],
                                      fol_answer=f'I did not answer "{T_FOLDER}" ...'))
    assert r.returncode == 1 and verdicts(r.stdout)["c-folder"] == "FAIL", r.stdout
    r = run_check(tmp_path, reach_run(fol=[], fol_answer=f'I did not answer "{T_FOLDER}" ...'))
    assert verdicts(r.stdout)["c-folder"] == "FAIL", r.stdout


def test_the_output_reports_the_first_intended_read_and_the_answer_excerpt(tmp_path):
    long_answer = "A" * 400
    r = run_check(tmp_path, reach_run(eng_answer=long_answer))
    ln = first_read_line(r.stdout)
    assert len(ln) == 2 and ENG_Q in ln[0] and "Read" in ln[1] and FOLDER_FILE in ln[1], r.stdout
    assert "answer (reported, decides nothing): " + "A" * 300 in r.stdout and "A" * 301 not in r.stdout


# ---- 2/3. (b) the query echo never counts; a stored value outside the echo does
def _echo(token, form):
    if form == "plain":
        q = f"lantern {token} room"
        return {"query": q}, json.dumps({"query": q, "results": []})
    if form == "payload_json":
        q = f"lantern {token} room"
        return {"payload_json": json.dumps({"query": q, "limit": 5})}, json.dumps({"echo": q, "results": []})
    q = f'the "{token}" lantern'           # a quote in the query: the result carries the JSON-escaped form
    return {"query": q}, json.dumps({"query": q, "results": []})


@pytest.mark.parametrize("form", ["plain", "payload_json", "quoted"])
def test_an_echoed_query_does_not_fail_the_folder_control(tmp_path, form):
    inp, res = _echo(T_FOLDER, form)
    r = run_check(tmp_path, reach_run(fol=fol_default() + [call(ENG_Q, inp, res)]))
    assert verdicts(r.stdout)["c-folder"] == "PASS" and r.returncode == 0, r.stdout


@pytest.mark.parametrize("form", ["plain", "payload_json", "quoted"])
def test_an_echoed_query_does_not_pass_the_engram_control(tmp_path, form):
    inp, res = _echo(T_ENGRAM, form)
    r = run_check(tmp_path, reach_run(eng=[call(ENG_Q, inp, res)]))
    assert verdicts(r.stdout)["c-engram"] == "FAIL" and "token" in r.stdout.lower(), r.stdout


def test_a_stored_value_outside_the_echo_counts_for_the_engram_control(tmp_path):
    q = f"vault {T_ENGRAM}"
    res = json.dumps({"query": q, "results": [{"summary": f"code {T_ENGRAM}"}]})
    r = run_check(tmp_path, reach_run(eng=[call(ENG_Q, {"query": q}, res)]))
    assert verdicts(r.stdout)["c-engram"] == "PASS", r.stdout


def test_a_stored_value_outside_the_echo_fails_the_folder_control(tmp_path):
    q = f"lantern {T_FOLDER}"
    res = json.dumps({"query": q, "results": [{"summary": f"lantern code {T_FOLDER}"}]})
    r = run_check(tmp_path, reach_run(fol=fol_default() + [call(ENG_Q, {"query": q}, res)]))
    assert r.returncode == 1 and verdicts(r.stdout)["c-folder"] == "FAIL" and "engram" in r.stdout.lower(), r.stdout


# ---- 4. (c) the other channel returned it in an EARLIER turn of the session
def test_a_folder_read_returning_the_engram_token_in_an_earlier_turn_fails_the_engram_control(tmp_path):
    r = run_check(tmp_path, reach_run(mid=[call("Read", {"file_path": FOLDER_FILE}, f"x {T_ENGRAM}")]))
    assert verdicts(r.stdout)["c-engram"] == "FAIL" and "folder" in r.stdout.lower(), r.stdout


def test_a_folder_read_returning_the_engram_token_before_the_compaction_also_fails_it(tmp_path):
    r = run_check(tmp_path, reach_run(pre=[call("Read", {"file_path": FOLDER_FILE}, f"x {T_ENGRAM}")]))
    assert verdicts(r.stdout)["c-engram"] == "FAIL", r.stdout


def test_a_folder_read_returning_the_engram_token_in_a_later_turn_also_fails_it(tmp_path):
    r = run_check(tmp_path, reach_run(fol=[call("Read", {"file_path": FOLDER_FILE}, f"x {T_FOLDER} {T_ENGRAM}")]))
    assert verdicts(r.stdout)["c-engram"] == "FAIL", r.stdout


def test_an_engram_read_returning_the_folder_token_in_an_earlier_turn_fails_the_folder_control(tmp_path):
    r = run_check(tmp_path, reach_run(mid=[call(ENG_Q, {"query": "n"}, f'{{"results":[{{"summary":"{T_FOLDER}"}}]}}')]))
    assert verdicts(r.stdout)["c-folder"] == "FAIL" and "engram" in r.stdout.lower(), r.stdout


# ---- 5. (d) the evidence file or the run directory opened before / after the first channel read
@pytest.mark.parametrize("opener", [
    call("Read", {"file_path": EVID_FILE}, "y"),
    call("Bash", {"command": "cat 9f2c0a7e1b.txt"}, "y"),             # by base name
    call("Bash", {"command": f"ls {RUN_DIR}"}, "r-0001 listing"),     # the run directory
])
def test_opening_the_evidence_file_or_run_dir_before_the_first_channel_read_fails(tmp_path, opener):
    r = run_check(tmp_path, reach_run(eng=[opener] + eng_default(), fol=[opener] + fol_default()), controls=CONTROLS_RD)
    assert r.returncode == 1, r.stdout
    assert verdicts(r.stdout)["c-engram"] == "FAIL" and verdicts(r.stdout)["c-folder"] == "FAIL", r.stdout
    assert "before" in r.stdout.lower()


@pytest.mark.parametrize("opener", [
    call("Read", {"file_path": EVID_FILE}, "y"),
    call("Bash", {"command": f"ls {RUN_DIR}"}, "r-0001 listing"),
])
def test_opening_the_evidence_file_or_run_dir_after_the_first_channel_read_passes_with_a_note(tmp_path, opener):
    # one opener, in the LAST of the two control turns: stream order puts it after BOTH controls' first channel reads
    r = run_check(tmp_path, reach_run(fol=fol_default() + [opener]), controls=CONTROLS_RD)
    assert r.returncode == 0, r.stdout
    assert verdicts(r.stdout)["c-engram"] == "PASS" and verdicts(r.stdout)["c-folder"] == "PASS", r.stdout
    assert "does not void" in r.stdout.lower() and "after" in r.stdout.lower()


def test_the_evidence_file_opened_in_an_earlier_turn_than_the_first_channel_read_fails(tmp_path):
    r = run_check(tmp_path, reach_run(mid=[call("Read", {"file_path": EVID_FILE}, "y")]))
    assert verdicts(r.stdout)["c-engram"] == "FAIL" and verdicts(r.stdout)["c-folder"] == "FAIL", r.stdout


def test_a_control_without_run_dir_is_still_accepted_and_the_run_dir_is_then_not_watched(tmp_path):
    opener = call("Bash", {"command": f"ls {RUN_DIR}"}, "listing")
    r = run_check(tmp_path, reach_run(eng=[opener] + eng_default(), fol=[opener] + fol_default()))  # CONTROLS: no run_dir
    assert r.returncode == 0 and verdicts(r.stdout)["c-engram"] == "PASS", r.stdout


# ---- 6. other tool kinds: SUPERSEDED by the final rule for a Bash/Grep/Glob that targets the memory folder
def test_a_bash_grep_of_the_folder_returning_the_token_is_a_folder_read(tmp_path):
    """Superseded by the final rule: a Bash grep of the folder 'neither passed nor failed' a folder control. It is now the
    folder channel itself (by storage): it passes the control, reported as the first read."""
    grep = call("Bash", {"command": f"grep -r code {FOLDER_FILE}"}, f"{FOLDER_FILE}: {T_FOLDER}")
    r = run_check(tmp_path, reach_run(fol=[grep]))
    assert verdicts(r.stdout)["c-folder"] == "PASS", r.stdout
    assert any("Bash" in ln and "event" in ln for ln in first_read_line(r.stdout)), r.stdout


def test_a_bash_grep_of_the_folder_returning_the_engram_token_fails_the_engram_control(tmp_path):
    """Superseded by the final rule: it neither passed nor failed. The folder is the OTHER channel for an engram control, and
    a shell grep of it that returns the engram token is an other-channel return (c). ToolSearch is still not a channel."""
    grep = call("Bash", {"command": f"grep -r code {FOLDER_FILE}"}, f"{FOLDER_FILE}: {T_ENGRAM}")
    ts = call("ToolSearch", {"query": "engram"}, T_ENGRAM)
    r = run_check(tmp_path, reach_run(eng=eng_default() + [grep]))
    assert verdicts(r.stdout)["c-engram"] == "FAIL" and "folder" in r.stdout.lower(), r.stdout
    r = run_check(tmp_path, reach_run(eng=eng_default() + [ts]))
    assert verdicts(r.stdout)["c-engram"] == "PASS" and "ToolSearch" in r.stdout, r.stdout


def test_a_bash_grep_whose_path_resolves_inside_the_folder_is_a_folder_read(tmp_path):
    grep = call("Bash", {"command": "grep -r code /arm/.claude/projects/-w/memory/../memory/"}, f"a.md: {T_FOLDER}")
    r = run_check(tmp_path, reach_run(fol=[grep]))
    assert verdicts(r.stdout)["c-folder"] == "PASS", r.stdout
    grep = call("Bash", {"command": "grep -r code /arm/.claude/projects/-w/memory-old/"}, f"a.md: {T_FOLDER}")
    r = run_check(tmp_path, reach_run(fol=[grep]))
    assert verdicts(r.stdout)["c-folder"] == "FAIL", r.stdout       # a sibling directory is not inside the folder


def test_a_bash_naming_a_path_outside_the_folder_whose_result_holds_the_token_is_an_opening_not_a_channel_read(tmp_path):
    """(d'): a file-capable call returning the token from a path outside both channels. Before the first channel read it
    FAILs the fact; after it, a note."""
    outside = call("Bash", {"command": "grep -r lantern /scratch/notes"}, f"/scratch/notes/n.txt: {T_FOLDER}")
    r = run_check(tmp_path, reach_run(fol=[outside] + fol_default()))
    assert verdicts(r.stdout)["c-folder"] == "FAIL" and "before" in r.stdout.lower() and "outside" in r.stdout.lower(), r.stdout
    r = run_check(tmp_path, reach_run(fol=fol_default() + [outside]))
    assert verdicts(r.stdout)["c-folder"] == "PASS" and "does not void" in r.stdout.lower(), r.stdout
    r = run_check(tmp_path, reach_run(fol=[outside]))     # and it is never itself the channel read
    assert verdicts(r.stdout)["c-folder"] == "FAIL", r.stdout


# ---- 7. (a) only a turn after the compaction counts; with no compaction turn the run start is the resume
def test_a_channel_read_only_before_the_compaction_does_not_pass(tmp_path):
    r = run_check(tmp_path, reach_run(pre=[call(ENG_Q, {"query": "v"}, ENG_HIT), call("Read", {"file_path": FOLDER_FILE}, f"x {T_FOLDER}")],
                                      eng=[call(ENG_Q, {"query": "v"}, "{}")], fol=[call("Read", {"file_path": FOLDER_FILE}, "(view)")]))
    assert verdicts(r.stdout)["c-engram"] == "FAIL" and verdicts(r.stdout)["c-folder"] == "FAIL", r.stdout


def test_a_channel_read_in_an_earlier_turn_after_the_compaction_counts(tmp_path):
    r = run_check(tmp_path, reach_run(mid=[call(ENG_Q, {"query": "v"}, ENG_HIT)], eng=[]))
    assert verdicts(r.stdout)["c-engram"] == "PASS", r.stdout


def test_with_no_compaction_turn_the_reads_of_the_run_count(tmp_path):
    r = run_check(tmp_path, reach_run(compact=False))
    assert r.returncode == 0 and verdicts(r.stdout)["c-engram"] == "PASS", r.stdout


# ================================================================ FINAL RULE (contract-first, ruling 2026-11-18, crossings 32237/32269/32271)
# (a) the folder channel is named by STORAGE; (c') the student's own writes into the other channel, made AFTER the first
# intended read, are stripped from other-channel results; (d') only a file-capable call can open the evidence/run dir.
MEM = "/arm/.claude/projects/-w/memory"
ENG_LIST = "mcp__plugin_engram_engram__engram_list"
PROBE_Q = f"probe: lantern code {T_FOLDER}"


def own_obs(claim, node="ob_0042"):
    return call(ENG_W, {"payload_json": json.dumps({"claim": claim})}, json.dumps({"id": node, "status": "created"}))


def list_returning(*summaries):
    return call(ENG_LIST, {}, json.dumps({"results": [{"id": f"ob_{k}", "summary": s} for k, s in enumerate(summaries)]}))


# ---- (c') ENGRAM side: a folder control whose token the student wrote into ENGRAM AFTER its first folder read
def test_c_prime_the_students_own_engram_write_after_its_first_folder_read_does_not_fail_the_folder_control(tmp_path):
    r = run_check(tmp_path, reach_run(fol=fol_default() + [own_obs(PROBE_Q), list_returning(PROBE_Q)]))
    assert r.returncode == 0 and verdicts(r.stdout)["c-folder"] == "PASS", r.stdout
    notes = [ln for ln in r.stdout.splitlines() if ln.strip().startswith("note:")]
    assert len(notes) == 1 and "engram_add_observation" in notes[0] and "turn 3" in notes[0] and "ob_0042" in notes[0], r.stdout


def test_c_prime_mutant_a_preexisting_engram_item_holding_the_token_still_fails(tmp_path):
    """The ruling's mutant: the item existed BEFORE the first folder read (no student write at all)."""
    r = run_check(tmp_path, reach_run(fol=fol_default() + [list_returning(PROBE_Q)]))
    assert verdicts(r.stdout)["c-folder"] == "FAIL" and "engram" in r.stdout.lower(), r.stdout


def test_c_prime_an_engram_return_before_the_first_folder_read_still_fails_even_if_written_later(tmp_path):
    """An other-channel return BEFORE the first intended read is never exempted, even when the student writes the very same
    text afterwards."""
    r = run_check(tmp_path, reach_run(fol=[list_returning(PROBE_Q)] + fol_default() + [own_obs(PROBE_Q), list_returning(PROBE_Q)]))
    assert verdicts(r.stdout)["c-folder"] == "FAIL", r.stdout


def test_c_prime_a_write_before_the_first_folder_read_is_not_stripped(tmp_path):
    r = run_check(tmp_path, reach_run(fol=[own_obs(PROBE_Q)] + fol_default() + [list_returning(PROBE_Q)]))
    assert verdicts(r.stdout)["c-folder"] == "FAIL", r.stdout


def test_c_prime_a_preexisting_item_beside_the_students_own_write_still_fails(tmp_path):
    """The student's write is stripped; a different item that also holds the token (it was there before) survives."""
    r = run_check(tmp_path, reach_run(fol=fol_default() + [own_obs(PROBE_Q),
                                                           list_returning(PROBE_Q, f"older note: {T_FOLDER} was filed last week")]))
    assert verdicts(r.stdout)["c-folder"] == "FAIL", r.stdout


def test_c_prime_a_write_that_does_not_carry_the_token_exempts_nothing(tmp_path):
    r = run_check(tmp_path, reach_run(fol=fol_default() + [own_obs("a probe happened"), list_returning(f"x {T_FOLDER} y")]))
    assert verdicts(r.stdout)["c-folder"] == "FAIL", r.stdout


def test_c_prime_a_read_before_the_write_is_not_exempted_by_it(tmp_path):
    r = run_check(tmp_path, reach_run(fol=fol_default() + [list_returning(PROBE_Q), own_obs(PROBE_Q)]))
    assert verdicts(r.stdout)["c-folder"] == "FAIL", r.stdout


def test_c_prime_every_engram_write_tool_counts_not_only_add_observation(tmp_path):
    for name in ("mcp__plugin_engram_engram__engram_derive", "mcp__plugin_engram_engram__engram_add_conjecture",
                 "mcp__plugin_engram_engram__engram_supersede"):
        w = call(name, {"payload_json": json.dumps({"text": PROBE_Q})}, "{}")
        r = run_check(tmp_path, reach_run(fol=fol_default() + [w, list_returning(PROBE_Q)]))
        assert verdicts(r.stdout)["c-folder"] == "PASS", (name, r.stdout)
    other = call("mcp__other__engram_add_observation", {"claim": PROBE_Q}, "{}")   # not the pinned server: not an ENGRAM write
    r = run_check(tmp_path, reach_run(fol=fol_default() + [other, list_returning(PROBE_Q)]))
    assert verdicts(r.stdout)["c-folder"] == "FAIL", r.stdout


# ---- (c') folder side: an engram control whose token the student Wrote into a memory-folder file AFTER its first ENGRAM read
NOTE_FILE = MEM + "/probe_note.md"
NOTE_BODY = f"---\nname: probe\n---\nprobe: code {T_ENGRAM}\n"
NOTE_CATN = f"     1\t---\n     2\tname: probe\n     3\t---\n     4\tprobe: code {T_ENGRAM}\n"


def test_c_prime_the_students_own_write_into_the_folder_after_its_first_engram_read_does_not_fail_the_engram_control(tmp_path):
    w = call("Write", {"file_path": NOTE_FILE, "content": NOTE_BODY}, "File created successfully")
    rd = call("Read", {"file_path": NOTE_FILE}, NOTE_CATN)
    r = run_check(tmp_path, reach_run(eng=eng_default() + [w, rd]))
    assert r.returncode == 0 and verdicts(r.stdout)["c-engram"] == "PASS", r.stdout
    notes = [ln for ln in r.stdout.splitlines() if ln.strip().startswith("note:")]
    assert any("Write" in n and NOTE_FILE in n and "turn 2" in n for n in notes), r.stdout


def test_c_prime_an_edit_new_string_into_the_folder_counts_too(tmp_path):
    w = call("Edit", {"file_path": NOTE_FILE, "old_string": "old", "new_string": f"probe: code {T_ENGRAM}"}, "updated")
    rd = call("Read", {"file_path": NOTE_FILE}, f"     4\tprobe: code {T_ENGRAM}\n")
    r = run_check(tmp_path, reach_run(eng=eng_default() + [w, rd]))
    assert verdicts(r.stdout)["c-engram"] == "PASS", r.stdout


def test_c_prime_mutant_a_preexisting_folder_file_holding_the_engram_token_still_fails(tmp_path):
    rd = call("Read", {"file_path": NOTE_FILE}, NOTE_CATN)
    r = run_check(tmp_path, reach_run(eng=eng_default() + [rd]))
    assert verdicts(r.stdout)["c-engram"] == "FAIL" and "folder" in r.stdout.lower(), r.stdout


def test_c_prime_a_folder_write_before_the_first_engram_read_is_not_stripped(tmp_path):
    w = call("Write", {"file_path": NOTE_FILE, "content": NOTE_BODY}, "File created successfully")
    rd = call("Read", {"file_path": NOTE_FILE}, NOTE_CATN)
    r = run_check(tmp_path, reach_run(eng=[w] + eng_default() + [rd]))
    assert verdicts(r.stdout)["c-engram"] == "FAIL", r.stdout


def test_c_prime_a_write_outside_the_folder_exempts_nothing(tmp_path):
    w = call("Write", {"file_path": "/elsewhere/probe_note.md", "content": NOTE_BODY}, "ok")
    rd = call("Bash", {"command": f"cat {NOTE_FILE}"}, NOTE_CATN)
    r = run_check(tmp_path, reach_run(eng=eng_default() + [w, rd]))
    assert verdicts(r.stdout)["c-engram"] == "FAIL", r.stdout


# ---- (d') an opening is a file-capable call; a path in an MCP tool's arguments is a mention
def test_d_prime_an_engram_write_naming_the_evidence_path_before_the_first_channel_read_is_a_mention_not_an_opening(tmp_path):
    note = "mcp__plugin_engram_engram__engram_retract"
    eng = [call(ENG_W, {"claim": f"see {EVID_FILE} and {RUN_DIR}"}, "{}"), call(note, {"node_id": EVID_FILE}, "{}")] + eng_default()
    fol = [call("ToolSearch", {"query": EVID_FILE}, "none"), call(ENG_Q, {"query": RUN_DIR}, "{}")] + fol_default()
    r = run_check(tmp_path, reach_run(eng=eng, fol=fol), controls=CONTROLS_RD)
    assert r.returncode == 0, r.stdout
    assert verdicts(r.stdout)["c-engram"] == "PASS" and verdicts(r.stdout)["c-folder"] == "PASS", r.stdout


def test_d_prime_an_engram_result_showing_the_evidence_path_is_a_mention_not_an_opening(tmp_path):
    eng = [call(ENG_Q, {"query": "v"}, json.dumps({"results": [{"summary": f"{T_ENGRAM} in {EVID_FILE}"}]}))]
    r = run_check(tmp_path, reach_run(eng=eng), controls=CONTROLS_RD)
    assert verdicts(r.stdout)["c-engram"] == "PASS", r.stdout


def test_d_prime_mutant_a_real_read_of_the_evidence_file_before_the_first_channel_read_still_fails(tmp_path):
    """The ruling's mutant. (A Bash cat of it, and the run directory, are covered by the parametrized cells above.)"""
    op = call("Read", {"file_path": EVID_FILE}, "y")
    r = run_check(tmp_path, reach_run(eng=[op] + eng_default(), fol=[op] + fol_default()), controls=CONTROLS_RD)
    assert verdicts(r.stdout)["c-engram"] == "FAIL" and verdicts(r.stdout)["c-folder"] == "FAIL" and "before" in r.stdout.lower(), r.stdout


@pytest.mark.parametrize("op", [call("Grep", {"pattern": "x", "path": EVID_FILE}, "x"),
                                call("Glob", {"pattern": RUN_DIR + "/*"}, "a")])
def test_d_prime_other_file_capable_tools_open_too(tmp_path, op):
    r = run_check(tmp_path, reach_run(eng=[op] + eng_default()), controls=CONTROLS_RD)
    assert verdicts(r.stdout)["c-engram"] == "FAIL", r.stdout


def test_d_prime_an_mcp_tool_returning_the_token_is_not_an_opening(tmp_path):
    """Only a file-capable call that returns the token from outside both channels opens; an MCP tool or ToolSearch never
    does (an ENGRAM read returning the engram token is the channel itself)."""
    ts = call("ToolSearch", {"query": "q"}, f"{T_FOLDER} {T_ENGRAM}")
    mcp = call("mcp__other__thing", {"a": "b"}, f"{T_FOLDER} {T_ENGRAM}")
    r = run_check(tmp_path, reach_run(eng=[ts, mcp] + eng_default(), fol=[ts, mcp] + fol_default()))
    assert verdicts(r.stdout)["c-engram"] == "PASS" and verdicts(r.stdout)["c-folder"] == "PASS", r.stdout
