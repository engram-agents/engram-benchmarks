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
    assert out["answers"] == {"F1": {"answer": "Paris.", "route": "recorded", "tool_ending": False, "string_route": False, "sensitivity_answer": None}}
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
    # Ruling 2 (Office 32574): such a reply is empty in substance -> missing; the disagreement stays listed.
    out = run([("question", "F4", [a_text(PH)], PH)])
    assert out["answers"]["F4"]["route"] == "placeholder_missing" and out["answers"]["F4"]["answer"] is None
    assert out["disagreements"] == [{"id": "F4", "tool_ending": False, "string_route": True}]

# ---- Ruling 2 (Kepler, Office 32574, 2026-11-19) ----

def test_placeholder_final_text_is_missing_with_sensitivity_answer():
    evs = [a_text("draft one", "m1"), a_tool("m1"), u_res(), a_text("real answer", "m2"), a_think("m3"), a_text(PH, "m3")]
    out = run([("question", "F14", evs, PH)])
    a = out["answers"]["F14"]
    assert a["answer"] is None and a["route"] == "placeholder_missing"
    assert a["sensitivity_answer"] == "real answer"
    assert out["counts"]["missing"] == 1 and out["counts"]["placeholder"] == 1

def test_placeholder_after_whitespace_strip():
    out = run([("question", "F15", [a_text("x"), a_text("  [no output]\n")], "  [no output]\n")])
    assert out["answers"]["F15"]["route"] == "placeholder_missing" and out["answers"]["F15"]["sensitivity_answer"] == "x"

def test_placeholder_without_earlier_text_has_no_sensitivity_answer():
    out = run([("question", "F16", [a_text(PH)], PH)])
    assert out["answers"]["F16"]["answer"] is None and out["answers"]["F16"]["sensitivity_answer"] is None

def test_near_variant_is_listed_and_not_decided():
    out = run([("question", "F17", [a_text("earlier"), a_text("No output.")], "No output.")])
    a = out["answers"]["F17"]
    assert a["route"] == "near_variant" and a["answer"] is None
    assert out["near_variants"] == [{"id": "F17", "class": "no output", "length": 10}]
    assert out["counts"]["near_variant"] == 1 and out["counts"]["missing"] == 0

# Kepler 32578: the widening, one cell per added word, one for the punctuation-only case.
import pytest
@pytest.mark.parametrize("text,cls", [
    ("No content", "no content"), ("[no response]", "no response"), ("No answer.", "no answer"),
    ("None", "none"), ("NULL", "null"), ("(empty)", "empty"), ("N/A", "n/a"),
])
def test_widened_near_variant_words(text, cls):
    out = run([("question", "F20", [a_text(text)], text)])
    a = out["answers"]["F20"]
    assert a["route"] == "near_variant" and a["answer"] is None
    assert out["near_variants"] == [{"id": "F20", "class": cls, "length": len(text.strip())}]

def test_punctuation_only_final_text_is_a_near_variant():
    out = run([("question", "F21", [a_text("earlier"), a_text(" ... ")], " ... ")])
    assert out["answers"]["F21"]["route"] == "near_variant"
    assert out["near_variants"] == [{"id": "F21", "class": "no letters or digits", "length": 3}]

def test_exact_placeholder_is_not_a_near_variant():
    out = run([("question", "F22", [a_text(PH)], PH)])
    assert out["near_variants"] == [] and out["answers"]["F22"]["route"] == "placeholder_missing"

def test_word_inside_a_sentence_stays_an_answer():
    for t in ("None of the three options fit.", "The box was empty when she opened it.", "N/A on the form means unknown."):
        out = run([("question", "F23", [a_text(t)], t)])
        assert out["answers"]["F23"]["route"] == "recorded" and out["near_variants"] == []

def test_answer_mentioning_no_output_in_a_sentence_is_an_answer():
    t = "The script gave no output, so the meeting moved to 4 PM."
    out = run([("question", "F18", [a_text(t)], t)])
    assert out["answers"]["F18"]["route"] == "recorded" and out["answers"]["F18"]["answer"] == t
    assert out["near_variants"] == []

def test_normal_turn_has_no_sensitivity_answer_field_value():
    out = run([("question", "F19", [a_text("Paris.")], "Paris.")])
    assert out["answers"]["F19"].get("sensitivity_answer") is None

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

def test_cli_missing_ids_line_includes_placeholder_turns(tmp_path):
    ev, rows = build([("question", "F1", [a_text("earlier"), a_text(PH)], PH), ("question", "F2", [a_tool(), u_res()], PH),
                      ("question", "F3", [a_text("ok")], "ok")])
    d = tmp_path / "run"; d.mkdir()
    (d / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in ev))
    (d / "turns.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    p = subprocess.run([sys.executable, os.path.join(HERE, "p1_answers.py"), str(d), str(tmp_path / "a.json")], capture_output=True, text=True)
    line = [l for l in p.stdout.splitlines() if l.startswith("missing ids")][0]
    assert "'F1'" in line and "'F2'" in line and "'F3'" not in line
