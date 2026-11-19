"""Contract tests for p1_answers.py (Kepler's ruling, Office 32566, 2026-11-19), written before the implementation.

Contract:
  - Turns are delimited by `result` events, in order; turn i pairs with turns.jsonl row i.
  - TOOL-ENDING (mechanism): the turn's last non-thinking assistant block is a tool_use.
  - Answer of a tool-ending turn = the turn's last text block; if the turn has no text block -> MISSING.
  - Answer of any other question turn = the recorded result (turns.jsonl), as the feeder recorded it.
  - STRING route: recorded result == '[no output]'. A turn where mechanism and string route disagree is listed in
    `disagreements` and is NOT silently resolved: its answer is set by the mechanism, and the flag stays visible.
  - Counts: tool_ending, tool_ending_multi_text (more than one text block), missing, disagreements.
  - Only question turns are answers; the compact turn is skipped. Every question id appears exactly once in the output.
  - The script never prints answer text to stdout.
"""
import json, os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import p1_answers as pa

PH = "[no output]"

def a_text(t, mid="m"): return {"type": "assistant", "message": {"id": mid, "content": [{"type": "text", "text": t}]}}
def a_think(mid="m"): return {"type": "assistant", "message": {"id": mid, "content": [{"type": "thinking", "thinking": "zz"}]}}
def a_tool(mid="m"): return {"type": "assistant", "message": {"id": mid, "content": [{"type": "tool_use", "name": "X", "input": {}}]}}
def u_res(): return {"type": "user", "message": {"content": [{"type": "tool_result", "content": "r"}]}}
def res(r): return {"type": "result", "result": r}

def build(turns):
    """turns: list of (kind, id, events, recorded_result)."""
    ev, rows = [], []
    for i, (kind, qid, evs, rec) in enumerate(turns, 1):
        ev += evs + [res(rec)]
        row = {"i": i, "kind": kind, "result": rec}
        if qid: row["id"] = qid
        rows.append(row)
    return ev, rows

def run(turns):
    ev, rows = build(turns)
    return pa.extract(ev, rows)

def test_normal_turn_answer_is_recorded_result():
    out = run([("compact", None, [], ""), ("question", "F1", [a_think(), a_text("Paris.")], "Paris.")])
    assert out["answers"] == {"F1": {"answer": "Paris.", "route": "recorded", "tool_ending": False, "string_route": False}}
    assert out["counts"]["tool_ending"] == 0 and out["disagreements"] == []

def test_tool_ending_with_placeholder_takes_last_text_block():
    evs = [a_text("first draft", "m1"), a_tool("m1"), u_res(), a_think("m2"), a_text("final words", "m2"), a_tool("m2"), u_res()]
    out = run([("question", "F14", evs, PH)])
    a = out["answers"]["F14"]
    assert a["answer"] == "final words" and a["route"] == "last_text_block" and a["tool_ending"] and a["string_route"]
    assert out["counts"]["tool_ending"] == 1 and out["counts"]["tool_ending_multi_text"] == 1
    assert out["disagreements"] == [] and out["counts"]["missing"] == 0

def test_tool_ending_single_text_block_not_counted_multi():
    out = run([("question", "F2", [a_text("only"), a_tool(), u_res()], PH)])
    assert out["answers"]["F2"]["answer"] == "only" and out["counts"]["tool_ending_multi_text"] == 0

def test_tool_ending_with_no_text_is_missing():
    out = run([("question", "F3", [a_think(), a_tool(), u_res()], PH)])
    assert out["answers"]["F3"]["answer"] is None and out["answers"]["F3"]["route"] == "missing"
    assert out["counts"]["missing"] == 1

def test_string_route_without_mechanism_is_a_logged_disagreement():
    # The student itself typed the brackets as its final text: not tool-ending, but the string matches.
    out = run([("question", "F4", [a_text(PH)], PH)])
    assert out["answers"]["F4"]["route"] == "recorded" and out["answers"]["F4"]["answer"] == PH
    assert out["disagreements"] == [{"id": "F4", "tool_ending": False, "string_route": True}]

def test_mechanism_without_string_route_is_a_logged_disagreement_answered_by_mechanism():
    out = run([("question", "F5", [a_text("said this"), a_tool(), u_res()], "something else")])
    assert out["answers"]["F5"]["answer"] == "said this" and out["answers"]["F5"]["route"] == "last_text_block"
    assert out["disagreements"] == [{"id": "F5", "tool_ending": True, "string_route": False}]

def test_thinking_after_tool_does_not_hide_tool_ending():
    out = run([("question", "F6", [a_text("ans"), a_tool(), u_res(), a_think()], PH)])
    assert out["answers"]["F6"]["tool_ending"] is True

def test_text_after_tool_is_not_tool_ending():
    out = run([("question", "F7", [a_tool(), u_res(), a_text("done")], "done")])
    assert out["answers"]["F7"]["tool_ending"] is False and out["answers"]["F7"]["answer"] == "done"

def test_turn_count_mismatch_refuses():
    ev, rows = build([("question", "F8", [a_text("x")], "x")])
    rows.append({"i": 2, "kind": "question", "id": "F9", "result": "y"})
    try:
        pa.extract(ev, rows); assert False, "should refuse"
    except ValueError as e:
        assert "turn" in str(e)

def test_duplicate_id_refuses():
    try:
        run([("question", "F1", [a_text("a")], "a"), ("question", "F1", [a_text("b")], "b")]); assert False
    except ValueError as e:
        assert "F1" in str(e)

def test_cli_never_prints_answer_text(tmp_path):
    secret = "UNIQUE-ANSWER-TEXT-7731"
    ev, rows = build([("question", "F1", [a_text(secret), a_tool(), u_res()], PH), ("question", "F2", [a_text(secret)], secret)])
    d = tmp_path / "run"; d.mkdir()
    (d / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in ev))
    (d / "turns.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    out = tmp_path / "answers.json"
    p = subprocess.run([sys.executable, os.path.join(HERE, "p1_answers.py"), str(d), str(out)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert secret not in p.stdout and secret not in p.stderr
    data = json.loads(out.read_text())
    assert data["answers"]["F1"]["answer"] == secret and "counts" in data
