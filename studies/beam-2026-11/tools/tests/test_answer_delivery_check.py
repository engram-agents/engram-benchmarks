"""Part B cells: answer-delivery-check.py on synthetic turn JSONL. Contract-first: written before the tool."""
import json, os, subprocess, sys
import pytest
from conftest import TOOLS

TOOL = os.path.join(TOOLS, "answer-delivery-check.py")
SESS = "run-session-1"
QS = [{"id": "q1", "question": "one?"}, {"id": "q2", "question": "two?"}, {"id": "q3", "question": "three?"}]


def row(kind, i, qid=None, session=SESS):
    r = {"i": i, "kind": kind, "session_id": session, "result": "x", "exchanges": []}
    if qid is not None:
        r["id"] = qid
    return r


def good():
    return [row("compact", 1)] + [row("question", n + 2, q["id"]) for n, q in enumerate(QS)]


def check(tmp_path, rows, session=SESS, qs=QS):
    t = tmp_path / "turns.jsonl"; t.write_text("".join(json.dumps(r) + "\n" for r in rows))
    q = tmp_path / "q.json"; q.write_text(json.dumps(qs))
    return subprocess.run([sys.executable, TOOL, "--turns", str(t), "--questions", str(q), "--session", session],
                          capture_output=True, text=True)


def test_pass(tmp_path):
    r = check(tmp_path, good())
    assert r.returncode == 0 and r.stdout.strip().splitlines()[-1] == "PASS", (r.stdout, r.stderr)


def fail(tmp_path, rows, word, **kw):
    r = check(tmp_path, rows, **kw)
    assert r.returncode == 1, (r.returncode, r.stdout, r.stderr)
    assert "PASS" not in r.stdout
    assert word in (r.stdout + r.stderr).lower(), (word, r.stdout, r.stderr)


def test_missing_id(tmp_path):
    rows = good(); del rows[2]
    fail(tmp_path, rows, "missing")


def test_duplicated_id(tmp_path):
    rows = good(); rows.insert(3, row("question", 9, "q1"))
    fail(tmp_path, rows, "duplicate")


def test_out_of_order(tmp_path):
    rows = good(); rows[1], rows[2] = rows[2], rows[1]
    fail(tmp_path, rows, "order")


def test_session_id_differs(tmp_path):
    rows = good(); rows[2]["session_id"] = "some-other-session"
    fail(tmp_path, rows, "session")


def test_session_id_none_on_a_turn(tmp_path):
    rows = good(); rows[0]["session_id"] = None
    fail(tmp_path, rows, "session")


def test_session_given_differs_from_all_turns(tmp_path):
    fail(tmp_path, good(), "session", session="not-the-run-session")


def test_compact_missing(tmp_path):
    fail(tmp_path, good()[1:], "compact")


def test_compact_after_a_question(tmp_path):
    rows = good(); rows.insert(2, rows.pop(0))  # q1, compact, q2, q3
    fail(tmp_path, rows, "compact")


def test_two_compacts(tmp_path):
    rows = good(); rows.insert(1, row("compact", 8))
    fail(tmp_path, rows, "compact")


def test_other_question_turn_unknown_id(tmp_path):
    rows = good(); rows.append(row("question", 9, "zzz"))
    fail(tmp_path, rows, "other question")


def test_other_question_turn_practice(tmp_path):
    rows = good(); rows.append(row("practice-question", 9))
    fail(tmp_path, rows, "other question")


def test_reading_turn_present(tmp_path):
    rows = good(); rows.insert(0, row("exchange", 0))
    fail(tmp_path, rows, "reading")


def test_unreadable_turn_file_is_a_failure_not_a_pass(tmp_path):
    q = tmp_path / "q.json"; q.write_text(json.dumps(QS))
    r = subprocess.run([sys.executable, TOOL, "--turns", str(tmp_path / "absent.jsonl"), "--questions", str(q),
                        "--session", SESS], capture_output=True, text=True)
    assert r.returncode == 1 and "PASS" not in r.stdout


def test_empty_turn_file_is_a_failure(tmp_path):
    fail(tmp_path, [], "compact")
