"""Part A cells: feed4.py --question-file. Contract-first: written before the implementation."""
import hashlib, json, os, subprocess, sys
import pytest
from conftest import TOOLS, write_json

FEED4 = os.path.join(TOOLS, "feed4.py")
QS = [{"id": "c1", "question": "What is the first thing?"}, {"id": "a2", "question": "Second thing?"},
      {"id": "b3", "question": "Third thing?"}]  # ids deliberately NOT sorted: file order is the contract


def run_feed4(arrow_python, parquet, tmp_path, *extra, env_extra=None, expect=None):
    env = {"PATH": os.environ["PATH"], "BEAM_PARQUET": parquet,
           "BEAM_OLLAMA_URL": "http://127.0.0.1:9"}  # privacy-scan: allow (discard-port stub: nothing listens, no model is reached)
    env.update(env_extra or {})
    cmd = [arrow_python, "-I", FEED4, "--arm-home", str(tmp_path / "home"), "--out", str(tmp_path / "out"),
           "--conv", "9", *extra]
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def plan_of(r):
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def prefix(arrow_python):
    """The constants feed4.py uses, read from feed.py by a python that can import it (it imports pyarrow)."""
    code = f"import sys,json; sys.path.insert(0,{TOOLS!r}); import feed; print(json.dumps([feed.PROCTOR, feed.QUESTION_PREFIX]))"
    return json.loads(subprocess.run([arrow_python, "-I", "-c", code], capture_output=True, text=True,
                                     check=True, env={"PATH": os.environ["PATH"], "BEAM_PARQUET": "x"}).stdout)


def test_plan_is_compact_then_questions_in_file_order(arrow_python, synthetic_parquet, tmp_path):
    qf = write_json(tmp_path / "q.json", QS)
    r = run_feed4(arrow_python, synthetic_parquet, tmp_path, "--turns", "0", "--resume", "SESS", "--force-compact",
                  "--question-file", qf, "--dump-plan")
    plan = plan_of(r)
    P, QP = prefix(arrow_python)
    assert [p["kind"] for p in plan] == ["compact", "question", "question", "question"]
    assert plan[0]["text"] == "/compact"
    for p, q in zip(plan[1:], QS):
        assert p["text"] == P + " " + QP + q["question"]
        assert p["id"] == q["id"]
        assert p["exchanges"] == []
    assert not any(p["kind"] == "exchange" for p in plan)  # no reading messages


def test_each_question_exactly_once(arrow_python, synthetic_parquet, tmp_path):
    qf = write_json(tmp_path / "q.json", QS)
    plan = plan_of(run_feed4(arrow_python, synthetic_parquet, tmp_path, "--turns", "0", "--resume", "S",
                             "--force-compact", "--question-file", qf, "--dump-plan"))
    assert sorted(p["id"] for p in plan if p["kind"] == "question") == sorted(q["id"] for q in QS)


@pytest.mark.parametrize("name,payload,extra,word", [
    ("with --questions", QS, ["--questions", "2"], "--questions"),
    ("with --ask", QS, ["--ask", "a practice question"], "--ask"),
    ("duplicate ids", [{"id": "x", "question": "a"}, {"id": "x", "question": "b"}], [], "duplicate"),
    ("empty question", [{"id": "x", "question": "a"}, {"id": "y", "question": "   "}], [], "empty"),
    ("not a list", {"id": "x", "question": "a"}, [], "list"),
    ("item not an object", ["just a string"], [], "object"),
    ("missing id", [{"question": "a"}], [], "id"),
    ("missing question", [{"id": "x"}], [], "question"),
    ("id not a string", [{"id": 7, "question": "a"}], [], "id"),
    ("question not a string", [{"id": "x", "question": 5}], [], "question"),
    ("empty list", [], [], "empty"),
])
def test_refusals_exit_2(arrow_python, synthetic_parquet, tmp_path, name, payload, extra, word):
    qf = write_json(tmp_path / "q.json", payload)
    r = run_feed4(arrow_python, synthetic_parquet, tmp_path, "--turns", "0", "--resume", "S", "--force-compact",
                  "--question-file", qf, "--dump-plan", *extra)
    assert r.returncode == 2, (name, r.returncode, r.stderr)
    assert r.stdout == ""  # nothing planned
    # the refusal must come from the question-file check, not from argparse not knowing the flag
    assert "unrecognized arguments" not in r.stderr and "--question-file" in r.stderr, r.stderr
    assert word in r.stderr.lower(), r.stderr


@pytest.mark.parametrize("name,extra,word", [
    ("without --resume", [], "--resume"),
    ("with --setup-only", ["--resume", "S", "--setup-only"], "--setup-only"),
    ("with --first-session", ["--resume", "S", "--first-session"], "--first-session"),
])
def test_question_file_requires_resume_and_refuses_setup_flags(arrow_python, synthetic_parquet, tmp_path, name, extra, word):
    """R2-1: answering always resumes the run's own session; setup phases have no business with a frozen list."""
    qf = write_json(tmp_path / "q.json", QS)
    r = run_feed4(arrow_python, synthetic_parquet, tmp_path, "--turns", "0", "--force-compact",
                  "--question-file", qf, "--dump-plan", *extra)
    assert r.returncode == 2, (name, r.returncode, r.stderr)
    assert r.stdout == ""
    assert "unrecognized arguments" not in r.stderr and "--question-file" in r.stderr and word in r.stderr, r.stderr


@pytest.mark.parametrize("name,extra,word", [
    ("--turns 3", ["--turns", "3"], "--turns"),
    ("--start 2", ["--turns", "0", "--start", "2"], "--start"),
    ("--start 0", ["--turns", "0", "--start", "0"], "--start"),  # R4-4: compared exactly, not as a truthiness test
    ("--start -1", ["--turns", "0", "--start=-1"], "--start"),
])
def test_question_file_refuses_a_reading_window(arrow_python, synthetic_parquet, tmp_path, name, extra, word):
    """R3-6: an answering run reads nothing, so --turns other than 0 or --start other than its default is refused."""
    qf = write_json(tmp_path / "q.json", QS)
    r = run_feed4(arrow_python, synthetic_parquet, tmp_path, "--resume", "S", "--force-compact",
                  "--question-file", qf, "--dump-plan", *extra)
    assert r.returncode == 2, (name, r.returncode, r.stderr)
    assert r.stdout == ""
    assert "unrecognized arguments" not in r.stderr and "--question-file" in r.stderr and word in r.stderr, r.stderr


def test_question_file_accepts_the_explicit_defaults(arrow_python, synthetic_parquet, tmp_path):
    qf = write_json(tmp_path / "q.json", QS)
    r = run_feed4(arrow_python, synthetic_parquet, tmp_path, "--turns", "0", "--start", "1", "--resume", "S",
                  "--force-compact", "--question-file", qf, "--dump-plan")
    assert r.returncode == 0, r.stderr


def test_refusal_not_json_and_missing_file(arrow_python, synthetic_parquet, tmp_path):
    bad = tmp_path / "bad.json"; bad.write_text("{not json")
    for path in (str(bad), str(tmp_path / "absent.json")):
        r = run_feed4(arrow_python, synthetic_parquet, tmp_path, "--turns", "0", "--resume", "S",
                      "--question-file", path, "--dump-plan")
        assert r.returncode == 2, r.stderr
        assert "unrecognized arguments" not in r.stderr and "--question-file" in r.stderr, r.stderr


def test_refusal_happens_before_any_model_unload(arrow_python, synthetic_parquet, tmp_path):
    """A real (non-dump) invocation with a bad file must refuse without the unload call that main()'s wrapper makes."""
    qf = write_json(tmp_path / "q.json", [{"id": "x", "question": ""}])
    comp = tmp_path / "components.txt"
    comp.write_text("".join(
        f"{hashlib.sha256(open(p, 'rb').read()).hexdigest()}  {n}\n"
        for n, p in (("feed4.py", FEED4), ("imported module: feed.py", os.path.join(TOOLS, "feed.py")))))
    r = run_feed4(arrow_python, synthetic_parquet, tmp_path, "--turns", "0", "--resume", "S", "--question-file", qf,
                  "--expect-components", str(comp))
    assert r.returncode == 2, r.stderr
    assert "unload" not in r.stdout.lower() and "unload" not in r.stderr.lower()


# ---- default behaviour: byte-identical plan; golden hashes were taken from the pre-change feed4.py ----
GOLDEN = os.path.join(os.path.dirname(__file__), "golden_default_plans.json")

DEFAULT_CASES = {
    "K1": ["--start", "1", "--turns", "8", "--per-round", "1"],
    "K3": ["--start", "1", "--turns", "8", "--per-round", "3"],
    "full": ["--start", "1", "--turns", "8", "--per-round", "3", "--force-compact", "--questions", "2", "--ask", "x"],
}


@pytest.mark.parametrize("case", sorted(DEFAULT_CASES))
def test_default_dump_plan_is_byte_identical(arrow_python, synthetic_parquet, tmp_path, case):
    golden = json.load(open(GOLDEN))
    r = run_feed4(arrow_python, synthetic_parquet, tmp_path, *DEFAULT_CASES[case], "--dump-plan")
    assert r.returncode == 0, r.stderr
    assert hashlib.sha256(r.stdout.encode()).hexdigest() == golden[case]
    assert '"id"' not in r.stdout  # the new key must not appear in default plans


# ---- the turn record: a fake `claude` speaking stream-json stands in for the student (no model) ----
FAKE = '''#!/usr/bin/env python3
import json, os, sys
argv = sys.argv[1:]
sid = argv[argv.index("--resume") + 1] if "--resume" in argv else "fresh-session"
open(os.path.join(os.environ["HOME"], "fake.log"), "a").write(json.dumps({"argv": argv}) + "\\n")
for line in sys.stdin:
    msg = json.loads(line)
    open(os.path.join(os.environ["HOME"], "fake.log"), "a").write(json.dumps({"msg": msg["message"]["content"]}) + "\\n")
    print(json.dumps({"type": "system", "session_id": sid}), flush=True)
    print(json.dumps({"type": "result", "result": "ok", "usage": {}, "num_turns": 1, "is_error": False}), flush=True)
'''


def test_turn_records_carry_kind_and_id_and_resume(arrow_python, synthetic_parquet, tmp_path):
    bindir = tmp_path / "bin"; bindir.mkdir()
    fake = bindir / "claude"; fake.write_text(FAKE); fake.chmod(0o755)
    log = tmp_path / "home" / "fake.log"
    qf = write_json(tmp_path / "q.json", QS)
    comp = tmp_path / "components.txt"
    comp.write_text("".join(
        f"{hashlib.sha256(open(p, 'rb').read()).hexdigest()}  {n}\n"
        for n, p in (("feed4.py", FEED4), ("imported module: feed.py", os.path.join(TOOLS, "feed.py")))))
    r = run_feed4(arrow_python, synthetic_parquet, tmp_path, "--turns", "0", "--resume", "RUN-SESSION",
                  "--force-compact", "--question-file", qf, "--expect-components", str(comp),
                  env_extra={"PATH": f"{bindir}:{os.environ['PATH']}"})
    assert r.returncode == 0, r.stderr
    rows = [json.loads(l) for l in open(tmp_path / "out" / "turns.jsonl")]
    assert [x["kind"] for x in rows] == ["compact", "question", "question", "question"]
    assert [x.get("id") for x in rows[1:]] == [q["id"] for q in QS]
    assert "id" not in rows[0]
    assert {x["session_id"] for x in rows} == {"RUN-SESSION"}
    seen = [json.loads(l) for l in open(log)]
    assert "--resume" in seen[0]["argv"] and seen[0]["argv"][seen[0]["argv"].index("--resume") + 1] == "RUN-SESSION"
    msgs = [s["msg"] for s in seen if "msg" in s]
    assert msgs[0] == "/compact" and len(msgs) == 4
