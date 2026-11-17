"""Part D cells: control-source-check.py on synthetic stream-json events + turn records. Contract-first.

A turn's events are everything up to and including its `result` event; turns.jsonl row k belongs to the k-th result
event (feed4.py's ask() returns at the first result event of each message)."""
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
        self.events.append({"type": "result", "result": answer})
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


def test_engram_fails_when_the_answer_lacks_the_token(tmp_path):
    r = run_check(tmp_path, engram_run(answer="I do not remember."))
    assert r.returncode == 1 and verdicts(r.stdout)["c-engram"] == "FAIL" and "token" in r.stdout.lower()


def test_engram_fails_without_any_engram_read_call(tmp_path):
    r = run_check(tmp_path, engram_run(calls=[]))
    assert r.returncode == 1 and verdicts(r.stdout)["c-engram"] == "FAIL" and "engram read" in r.stdout.lower()


def test_an_engram_write_call_is_not_a_read(tmp_path):
    r = run_check(tmp_path, engram_run(calls=[call(ENG_W, {"claim": "x"}, '{"status":"created"}')]))
    assert verdicts(r.stdout)["c-engram"] == "FAIL"


def test_engram_fails_when_the_folder_file_was_read(tmp_path):
    r = run_check(tmp_path, engram_run(calls=[
        call(ENG_Q, {"query": "v"}, "{}"), call("Read", {"file_path": FOLDER_FILE}, "text")]))
    # the folder file is named on the folder control; the engram control must still not touch it
    assert verdicts(r.stdout)["c-engram"] == "FAIL" and "folder file" in r.stdout.lower()


def test_engram_fails_when_the_evidence_file_was_read(tmp_path):
    r = run_check(tmp_path, engram_run(calls=[
        call(ENG_Q, {"query": "v"}, "{}"), call("Read", {"file_path": EVID_FILE}, T_ENGRAM)]))
    assert verdicts(r.stdout)["c-engram"] == "FAIL" and "evidence" in r.stdout.lower()


def test_engram_fails_when_a_grep_touched_the_evidence_file_by_name(tmp_path):
    r = run_check(tmp_path, engram_run(calls=[
        call(ENG_Q, {"query": "v"}, "{}"), call("Bash", {"command": "grep -r code /ev/9f2c0a7e1b.txt"}, "x")]))
    assert verdicts(r.stdout)["c-engram"] == "FAIL"


def test_engram_fails_when_a_non_engram_tool_result_shows_the_token(tmp_path):
    r = run_check(tmp_path, engram_run(calls=[
        call(ENG_Q, {"query": "v"}, "{}"), call("Bash", {"command": "grep -r code /ev"}, f"/ev/x.txt: {T_ENGRAM}")]))
    assert verdicts(r.stdout)["c-engram"] == "FAIL"


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


def test_folder_fails_when_the_answer_lacks_the_token(tmp_path):
    r = run_check(tmp_path, folder_run(answer="no idea"))
    assert verdicts(r.stdout)["c-folder"] == "FAIL" and "token" in r.stdout.lower()


def test_folder_fails_when_the_folder_file_was_not_read(tmp_path):
    r = run_check(tmp_path, folder_run(calls=[call("Bash", {"command": "ls /arm"}, "x")]))
    assert verdicts(r.stdout)["c-folder"] == "FAIL" and "not read" in r.stdout.lower()


def test_folder_fails_when_an_engram_read_returned_the_token(tmp_path):
    r = run_check(tmp_path, folder_run(calls=[
        call("Read", {"file_path": FOLDER_FILE}, "x"), call(ENG_I, {"node_id": "ob_1"}, f"claim {T_FOLDER}")]))
    assert verdicts(r.stdout)["c-folder"] == "FAIL" and "engram" in r.stdout.lower()


def test_folder_fails_when_the_evidence_file_was_touched(tmp_path):
    r = run_check(tmp_path, folder_run(calls=[
        call("Read", {"file_path": FOLDER_FILE}, "x"), call("Read", {"file_path": EVID_FILE}, "y")]))
    assert verdicts(r.stdout)["c-folder"] == "FAIL" and "evidence" in r.stdout.lower()


def test_a_folder_read_by_grep_of_the_file_name_counts_as_read(tmp_path):
    r = run_check(tmp_path, folder_run(calls=[
        call("Bash", {"command": "cat /arm/.claude/projects/-w/memory/reference_note_dd439b25.md"}, T_FOLDER)]))
    assert verdicts(r.stdout)["c-folder"] == "PASS"


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
