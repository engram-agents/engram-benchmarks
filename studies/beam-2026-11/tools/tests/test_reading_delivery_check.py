"""reading-delivery-check.py cells (P1b C8). Contract-first: written before the tool existed.

Contract: PASS (exit 0) only if ALL hold, every failure printed, exit 1 on any failure or unreadable input:
  1. the session_id on every turn equals the resumed session id;
  2. every turn is a reading turn (kind exchange): no compact, question, setup or practice turn;
  3. the turns carry exactly the planned messages: same count, each turn's exchanges equal the planned message's
     exchanges, in plan order, each planned message once;
  4. no turn has is_error, timeout or eof true;
  5. the event stream holds exactly one result event per planned message."""
import json, os, subprocess, sys
import pytest
from conftest import TOOLS

TOOL = os.path.join(TOOLS, "reading-delivery-check.py")
SID = "sess-1"
PLAN = [{"kind": "exchange", "exchanges": [4, 5, 6], "text": "a"}, {"kind": "exchange", "exchanges": [7, 8, 9], "text": "b"}]


def rows_for(plan=PLAN, **over):
    return [dict({"i": n + 1, "kind": "exchange", "session_id": SID, "is_error": False, "exchanges": m["exchanges"]}, **over)
            for n, m in enumerate(plan)]


def run(tmp_path, rows=None, plan=PLAN, results=None, session=SID, raw_turns=None):
    t, p, e = tmp_path / "turns.jsonl", tmp_path / "plan.json", tmp_path / "events.jsonl"
    t.write_text(raw_turns if raw_turns is not None else "".join(json.dumps(r) + "\n" for r in (rows if rows is not None else rows_for())))
    p.write_text(json.dumps(plan))
    n = len(plan) if results is None else results
    e.write_text("".join(json.dumps({"type": "assistant"}) + "\n" + json.dumps({"type": "result"}) + "\n" for _ in range(n)))
    return subprocess.run([sys.executable, TOOL, "--turns", str(t), "--plan", str(p), "--events", str(e), "--session", session],
                          capture_output=True, text=True)


def test_a_complete_ordered_run_passes(tmp_path):
    r = run(tmp_path)
    assert r.returncode == 0 and r.stdout.strip().endswith("PASS"), r.stdout


def test_a_wrong_session_id_fails(tmp_path):
    rows = rows_for(); rows[1]["session_id"] = "other"
    r = run(tmp_path, rows)
    assert r.returncode == 1 and "session id differs" in r.stdout


def test_a_missing_round_fails(tmp_path):
    r = run(tmp_path, rows_for()[:1])
    assert r.returncode == 1 and "turn count" in r.stdout


def test_a_duplicated_round_fails(tmp_path):
    rows = rows_for(); rows.append(dict(rows[1], i=3))
    r = run(tmp_path, rows)
    assert r.returncode == 1 and "turn count" in r.stdout


def test_rounds_out_of_plan_order_fail(tmp_path):
    r = run(tmp_path, list(reversed(rows_for())))
    assert r.returncode == 1 and "out of order" in r.stdout


def test_a_turn_with_the_wrong_exchanges_fails(tmp_path):
    rows = rows_for(); rows[0]["exchanges"] = [4, 5]
    r = run(tmp_path, rows)
    assert r.returncode == 1 and "exchanges" in r.stdout


@pytest.mark.parametrize("kind", ["compact", "question", "setup", "practice-question"])
def test_a_non_reading_turn_fails(tmp_path, kind):
    rows = rows_for(); rows[1]["kind"] = kind
    r = run(tmp_path, rows)
    assert r.returncode == 1 and "not a reading turn" in r.stdout


@pytest.mark.parametrize("flag", ["is_error", "timeout", "eof"])
def test_an_errored_timed_out_or_eof_turn_fails(tmp_path, flag):
    rows = rows_for(); rows[0][flag] = True
    r = run(tmp_path, rows)
    assert r.returncode == 1 and flag in r.stdout


@pytest.mark.parametrize("n", [1, 3])
def test_a_result_count_other_than_one_per_message_fails(tmp_path, n):
    r = run(tmp_path, results=n)
    assert r.returncode == 1 and "result events" in r.stdout


def test_an_unreadable_input_fails_not_crashes(tmp_path):
    r = run(tmp_path, raw_turns="not json\n")
    assert r.returncode == 1 and "FAIL: cannot read inputs" in r.stdout


def test_an_empty_plan_is_not_a_pass(tmp_path):
    r = run(tmp_path, rows=[], plan=[])
    assert r.returncode == 1 and "empty" in r.stdout
