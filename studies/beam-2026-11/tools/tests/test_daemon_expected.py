"""Cells for the arm's STATED daemon expectation (PR 22 fold: K1, K2, and reviewer round 3's two suggestions).

Contract-first: these cells were written, and watched to fail, before the implementation. The contract is the six pins of the
ruling:
  1  run_feeder takes the keyword `daemon_expected`, with NO usable default: a call that starts a student and does not state it is
     a LaunchRefused naming the missing statement. A --dump-plan call starts no box and ignores it.
  2  the allowed values are exactly the strings "engram" and "none"; any other value is a LaunchRefused (never read as "none").
     When the slot-derived value differs from the statement, LaunchRefused BEFORE anything starts, naming the statement, the derived
     value and each of the three paths present/absent. One function computes the paths' presence; daemon_setting is defined from it.
  3  the value placed in SANDBOX_DAEMON is the DERIVED one, never the statement.
  4  daemon_verdict compares the launch line's `daemon=` with the STATED expectation, and does not derive again.
  5  the wrapper takes SANDBOX_DAEMON_EXPECTED (engram|none, module-owned) and writes `daemon_expected=` on the launch line; the
     module passes it on every student launch and fails closed (LaunchStop) if the line's value is not the statement it passed.
     When the wrapper is not told (direct use) the line says `daemon_expected=unstated`: it reads as neither value.
  6  a mismatch refusal is never silent: a named record in state_dir, which check_before_launch does not read as an open launch.
K2 (record only): LaunchResult.daemon_expected and .daemon_stop_outcome; `already-gone` still passes. R3-S1: daemon_verdict's `log`
has no default. R3-S2: a launch whose in-box supervisor exited 6 is a named LaunchStop through run_feeder's verdict.

Stub-feeder cells run everywhere; the cells marked needs_box run the REAL wrapper (test mode) and skip by name without a box. None of
these cells needs pyarrow: the real-box cell uses its own small driver in place of feed4.Student.
"""
import inspect, json, os, re, sys
import pytest
from conftest import TOOLS, reader_log_for, needs_linux_proc
import test_student_sandbox as TSS
from test_student_sandbox import fake_bwrap                                   # noqa: F401  (fixture)
from test_sandbox_launch import mk_sandbox, SL, STUB_ENV                       # noqa: F401
from test_daemon_prestart import (w, build_engram_slot, client_cmd, dcfg, run_daemon, log_line, fields, ARM_LABEL,  # noqa: F401  (w: the module cells' world, on a short root)
                                  wait_report_closed)

PATHS = (".engram/venv/bin/python3", ".engram/marketplace/plugins/engram/hooks/engram-surface-daemon.py", ".engram")
BAD_STATEMENTS = (None, "", "Engram", "ENGRAM", "None", "NONE", "none ", " engram", "engram,none", "yes", "unstated", True, False, 0, 1,
                  b"engram", ["engram"])


def direct(w, mode="ok", env=None, **kw):
    """A student launch through the module with NO default filled in: `daemon_expected` is passed only when the cell passes it."""
    e = w.env(STUB_MODE=mode, STUB_RC="0", **(env or {}))
    return SL.run_feeder(sys.executable, str(w.stub), w.argv(), sandbox=w.sandbox(), env=e, test_stub=True, stub_as="feed2.py",
                         test_env_names=STUB_ENV, log_dir=str(w.logs), state_dir=str(w.state), **kw)


def full_slot(w, **kw):
    build_engram_slot(w.cfg.slot, **kw)


# ======================================================================================== pin 1: no usable default
def test_p1_a_student_call_that_does_not_state_the_expectation_is_refused_by_name(w):
    with pytest.raises(SL.LaunchRefused, match="daemon_expected"):
        direct(w)
    w.assert_nothing_started()
    assert not os.path.exists(str(w.state)) or os.listdir(str(w.state)) == [], "a refusal before the launch left a record"


def test_p1_the_keyword_has_no_default_that_reads_as_a_value():
    p = inspect.signature(SL.run_feeder).parameters["daemon_expected"]
    assert p.kind is inspect.Parameter.KEYWORD_ONLY
    assert p.default not in SL.DAEMON_STATEMENTS and p.default is not True and p.default != "engram" and p.default != "none"


def test_p1_a_plan_dump_starts_no_box_and_ignores_the_statement(w):
    for kw in ({}, {"daemon_expected": "engram"}, {"daemon_expected": "garbage"}, {"daemon_expected": None}):
        r = SL.run_feeder(sys.executable, str(w.stub), w.argv(extra=("--dump-plan",)), env=w.env(), test_stub=True, **kw)
        assert r.returncode == 0
    assert os.listdir(w.logs) == []


# ======================================================================================== pin 2: the two values, and only those
@pytest.mark.parametrize("bad", BAD_STATEMENTS, ids=repr)
def test_p2_every_other_value_is_refused_by_name_and_is_never_read_as_none(w, bad):
    with pytest.raises(SL.LaunchRefused, match="daemon_expected") as e:
        w.launch("ok", daemon_expected=bad)
    assert repr(bad) in str(e.value), "the refusal does not name the value it refused"
    w.assert_nothing_started()


def test_p2_the_two_statements_are_exactly_these():
    assert tuple(SL.DAEMON_STATEMENTS) == ("engram", "none")


@pytest.mark.parametrize("stated,build,derived", [("engram", False, "none"), ("none", True, "engram")])
def test_p2_a_statement_that_differs_from_the_slot_is_refused_before_anything_starts(w, stated, build, derived):
    if build:
        full_slot(w)
    with pytest.raises(SL.LaunchRefused) as e:
        w.launch("ok", daemon_expected=stated)
    msg = str(e.value)
    assert f"daemon_expected={stated!r}" in msg and f"derives {derived}" in msg, msg
    for rel in PATHS:
        assert f"{rel}: {'present' if build else 'absent'}" in msg, (rel, msg)
    w.assert_nothing_started()


@pytest.mark.parametrize("missing", range(3), ids=["no-python", "no-script", "no-engram-dir"])
def test_p2_a_slot_missing_one_path_is_seen_as_missing_and_the_message_says_which(w, missing):
    full_slot(w, python=missing != 0, script=missing != 1, enginedir=missing != 2)
    with pytest.raises(SL.LaunchRefused) as e:
        w.launch("ok", daemon_expected="engram")
    msg = str(e.value)
    assert "derives none" in msg
    present = {rel: os.path.exists(os.path.join(w.cfg.slot, rel)) for rel in PATHS}
    assert not all(present.values())
    for rel, here in present.items():
        assert f"{rel}: {'present' if here else 'absent'}" in msg, (rel, msg)
    w.assert_nothing_started()


def test_p2_one_function_computes_the_paths_and_the_setting_is_defined_from_it(monkeypatch, tmp_path):
    slot = str(tmp_path)
    assert list(SL.daemon_paths(slot)) == list(PATHS) and not any(SL.daemon_paths(slot).values())
    build_engram_slot(slot)
    assert all(SL.daemon_paths(slot).values()) and SL.daemon_setting(slot) == "engram"
    for forced, want in (({p: True for p in PATHS}, "engram"), ({**{p: True for p in PATHS}, PATHS[1]: False}, None)):
        monkeypatch.setattr(SL, "daemon_paths", lambda *a, _f=forced, **k: dict(_f))
        assert SL.daemon_setting("/no/such/slot") == want, "daemon_setting does not take its answer from daemon_paths"


@needs_linux_proc
def test_p2_a_launch_reads_the_slot_once_and_the_verdict_never_derives_again(w, monkeypatch):
    calls = []
    real = SL.daemon_paths
    monkeypatch.setattr(SL, "daemon_paths", lambda *a, **k: calls.append(a) or real(*a, **k))
    monkeypatch.setattr(SL, "daemon_setting", lambda *a, **k: pytest.fail("daemon_setting was called during a launch"))
    assert w.launch("ok", daemon_expected="none").returncode == 0
    assert len(calls) == 1, calls


# ======================================================================================== pin 6: the refusal record
def refuse_once(w, stated="engram"):
    with pytest.raises(SL.LaunchRefused) as e:
        w.launch("ok", daemon_expected=stated)
    return str(e.value)


def test_p6_a_mismatch_leaves_a_named_record_and_the_message_names_its_path(w):
    msg = refuse_once(w)                                        # stated engram, slot bare
    (name,) = os.listdir(str(w.state))
    assert re.fullmatch(r"sandbox-[0-9]+-[0-9a-f]{8}\.json", name), name
    path = os.path.join(str(w.state), name)
    assert path in msg, "the refusal does not name the record's path"
    rec = json.load(open(path))
    assert rec["state"] == "refused" and rec["cause"] == "daemon-mismatch"
    assert rec["daemon_expected"] == "engram" and rec["daemon_derived"] == "none"
    assert rec["paths"] == {rel: False for rel in PATHS}
    assert os.listdir(w.logs) == [], "the refused launch made a log"


def test_p6_the_record_of_the_other_direction_says_what_is_there(w):
    full_slot(w)
    refuse_once(w, "none")
    (name,) = os.listdir(str(w.state))
    rec = json.load(open(os.path.join(str(w.state), name)))
    assert rec["daemon_expected"] == "none" and rec["daemon_derived"] == "engram" and all(rec["paths"].values())


@needs_linux_proc
def test_p6_a_refused_record_does_not_block_the_next_launch_and_is_left_as_it_is(w):
    refuse_once(w)
    (name,) = os.listdir(str(w.state))
    before = open(os.path.join(str(w.state), name)).read()
    assert w.launch("ok", daemon_expected="none").returncode == 0     # the statement now matches the slot
    assert open(os.path.join(str(w.state), name)).read() == before, "the next launch rewrote the refusal record"
    assert len(os.listdir(str(w.state))) == 2


def test_p6_an_open_record_still_blocks_the_next_launch(w):
    os.makedirs(str(w.state), exist_ok=True)
    victim = w.d / "unreadable-log-is-a-directory"
    victim.mkdir()
    with open(os.path.join(str(w.state), "earlier.json"), "w") as f:
        json.dump({"state": "open", "log": str(victim), "feeder": "feed4.py"}, f)
    with pytest.raises(SL.LaunchRefused, match="earlier launch"):
        w.launch("ok", daemon_expected="none")
    w.assert_nothing_started()


def test_p6_a_refusal_whose_record_cannot_be_written_is_still_a_refusal_and_says_so(w):
    os.makedirs(str(w.state), mode=0o700)
    os.chmod(str(w.state), 0o500)
    try:
        if os.access(str(w.state), os.W_OK):
            pytest.skip("this process can write a read-only directory (root)")
        with pytest.raises(SL.LaunchRefused, match="could not be written"):
            w.launch("ok", daemon_expected="engram")
    finally:
        os.chmod(str(w.state), 0o700)
    w.assert_nothing_started()


# ======================================================================================== pin 3 and 5: what is placed, what the line says
@needs_linux_proc
def test_p3_stated_none_on_a_bare_slot_places_no_daemon_and_the_line_says_none(w):
    r = w.launch("ok", daemon_expected="none")
    pairs = w.records()[0]["pairs"]
    assert "SANDBOX_DAEMON" not in pairs and pairs["SANDBOX_DAEMON_EXPECTED"] == "none"
    f = SL.read_launch_fields(r.log)
    assert f["daemon_expected"] == "none" and "daemon" not in f
    assert r.daemon_expected == "none" and r.daemon is None and r.daemon_stop_outcome is None and r.box_label is None


@needs_linux_proc
def test_p3_stated_engram_on_a_full_slot_places_the_derived_value_and_fills_the_result(w):
    full_slot(w)
    r = w.launch("ok", daemon_expected="engram", env={"STUB_DAEMON": "term"})
    pairs = w.records()[0]["pairs"]
    assert pairs["SANDBOX_DAEMON"] == "engram" and pairs["SANDBOX_DAEMON_EXPECTED"] == "engram"
    f = SL.read_launch_fields(r.log)
    assert f["daemon"] == "engram" and f["daemon_expected"] == "engram"
    assert (r.daemon, r.daemon_expected, r.daemon_stop_outcome) == ("engram", "engram", "term")
    assert r.daemon_time_to_ready_s == 1.5 and r.box_label == ARM_LABEL


def test_p3_the_statement_is_passed_on_every_student_launch_and_a_caller_cannot_pass_it(w):
    assert "SANDBOX_DAEMON_EXPECTED" in SL.MODULE_OWNED
    for val in ("engram", "none", "other"):
        with pytest.raises(SL.LaunchRefused, match="SANDBOX_DAEMON_EXPECTED"):
            mk_sandbox(w.settings(SANDBOX_DAEMON_EXPECTED=val), str(w.expected))
    with pytest.raises(SL.LaunchRefused, match="SANDBOX_DAEMON_EXPECTED"):
        w.launch("ok", daemon_expected="none", argv=w.argv(extra=("--env", "SANDBOX_DAEMON_EXPECTED=none")))
    w.assert_nothing_started()


def test_p3_sandbox_daemon_is_set_in_one_place_and_from_the_derived_variable():
    text = open(SL.__file__).read()
    code = [l for l in text.splitlines() if not l.lstrip().startswith("#")]
    sets = [l for l in code if re.search(r"""\[\s*["']SANDBOX_DAEMON["']\s*\]\s*=(?!=)|["']SANDBOX_DAEMON["']\s*:|update\([^)]*SANDBOX_DAEMON\s*=""", l)]
    assert len(sets) == 1 and re.search(r'\]\s*=\s*daemon\s*$', sets[0]), sets          # from `daemon`, the derived variable


# ======================================================================================== pin 4: the verdict compares with the statement
GOOD_EVENTS = [("daemon-ready", {"time_to_ready_s": "1.5", "pid": "9", "rpt_dropped": "0"}),
               ("daemon-stop", {"outcome": "term", "pid": "9", "rpt_dropped": "0"})]


def verdict(tmp_path, stated, line, events=(), name="v.log"):
    res = SL.LaunchResult(0)
    return SL.daemon_verdict(stated, line, list(events), res, log=reader_log_for(tmp_path / name, events)), res


def test_p4_stated_engram_and_a_line_without_a_daemon_is_a_stop(tmp_path):
    why, _ = verdict(tmp_path, "engram", {})
    assert why and "daemon" in why and "engram" in why, why


def test_p4_stated_none_and_a_line_with_a_daemon_is_a_stop(tmp_path):
    why, _ = verdict(tmp_path, "none", {"daemon": "engram"})
    assert why and "daemon=engram" in why and "none" in why, why


def test_p4_the_two_agreeing_cases_pass(tmp_path):
    assert verdict(tmp_path, "none", {})[0] is None
    why, res = verdict(tmp_path, "engram", {"daemon": "engram"}, GOOD_EVENTS)
    assert why is None and res.daemon == "engram" and res.daemon_stop_outcome == "term" and res.daemon_time_to_ready_s == 1.5


@pytest.mark.parametrize("bad", [None, "", "Engram", "engram ", True, "yes"], ids=repr)
def test_p4_a_statement_that_is_not_one_of_the_two_is_refused_by_the_verdict_too(tmp_path, bad):
    why, _ = verdict(tmp_path, bad, {})
    assert why and "daemon_expected" in why, why


def test_p4_the_verdict_does_not_derive_anything_from_the_slot(monkeypatch, tmp_path):
    monkeypatch.setattr(SL, "daemon_setting", lambda *a, **k: pytest.fail("the verdict derived the daemon setting again"))
    monkeypatch.setattr(SL, "daemon_paths", lambda *a, **k: pytest.fail("the verdict read the slot again"))
    assert verdict(tmp_path, "none", {})[0] is None
    assert verdict(tmp_path, "engram", {"daemon": "engram"}, GOOD_EVENTS)[0] is None


def test_p4_run_feeder_hands_the_verdict_the_statement_and_the_log():
    assert inspect.getsource(SL).count("daemon_verdict(daemon_expected, lf, read_daemon_events(log_path), res, log=log_path)") == 1


# ======================================================================================== pin 5: the line's own daemon_expected
@pytest.mark.parametrize("stated,line,build", [("none", "engram", False), ("none", "unstated", False), ("none", "-", False),
                                               ("engram", "none", True), ("engram", "unstated", True), ("engram", "-", True)])
@needs_linux_proc
def test_p5_a_line_whose_daemon_expected_is_not_the_statement_is_a_launch_stop(w, stated, line, build):
    if build:
        full_slot(w)
    env = {"STUB_DAEMON_EXPECTED_LINE": line}
    if build:
        env["STUB_DAEMON"] = "term"
    with pytest.raises(SL.LaunchStop, match="daemon_expected") as e:
        w.launch("ok", daemon_expected=stated, env=env)
    assert e.value.result.daemon_expected == stated and "no answer of this session is read" in str(e.value)


@needs_linux_proc
def test_p5_the_line_that_says_the_statement_passes(w):
    assert w.launch("ok", daemon_expected="none", env={"STUB_DAEMON_EXPECTED_LINE": "none"}).returncode == 0


# ======================================================================================== K2: the stop outcome is recorded
@pytest.mark.parametrize("outcome", ["term", "already-gone"])
@needs_linux_proc
def test_k2_the_stop_outcome_is_read_off_the_one_stop_line_and_already_gone_still_passes(w, outcome):
    full_slot(w)
    r = w.launch("ok", daemon_expected="engram", env={"STUB_DAEMON": outcome})
    assert r.daemon_stop_outcome == outcome and r.returncode == 0


def test_k2_a_killed_daemon_is_still_recorded_when_the_launch_stops_on_it(tmp_path):
    ev = [GOOD_EVENTS[0], ("daemon-stop", {"outcome": "killed", "pid": "9", "rpt_dropped": "0"}),
          ("daemon-fault", {"kind": "sigkill", "pid": "9", "after_s": "20.000"})]
    why, res = verdict(tmp_path, "engram", {"daemon": "engram"}, ev)
    assert why and "SIGKILL" in why and res.daemon_stop_outcome == "killed"


# ======================================================================================== R3-S1: the log is not optional
def test_r3s1_the_log_argument_has_no_default():
    assert inspect.signature(SL.daemon_verdict).parameters["log"].default is inspect.Parameter.empty


@pytest.mark.parametrize("log", [None, ""], ids=repr)
@pytest.mark.parametrize("stated,line", [("none", {}), ("engram", {"daemon": "engram"})])
def test_r3s1_no_log_is_a_refusal_by_name_never_a_silent_skip_of_the_reader_record_check(log, stated, line):
    why = SL.daemon_verdict(stated, line, list(GOOD_EVENTS), SL.LaunchResult(0), log)
    assert why and "log" in why, why


# ======================================================================================== R3-S2: the in-box supervisor exited 6
@needs_linux_proc
def test_r3s2_a_supervisor_that_lost_the_report_channel_ends_as_a_named_stop_through_the_verdict(w):
    full_slot(w)
    with pytest.raises(SL.LaunchStop, match="daemon-ready") as e:
        w.launch("ok", daemon_expected="engram", rc=6, env={"STUB_DAEMON": "lost"})
    assert "neither" in str(e.value) and "no answer of this session is read" in str(e.value)
    assert e.value.result.returncode == 6 and e.value.result.verdict == "not-flagged"      # the verdict ran: this is the daemon stop


# ======================================================================================== the wrapper: SANDBOX_DAEMON_EXPECTED
def wrapper_line(cfg):
    return log_line(cfg, "wrapper-launch")


@TSS.needs_box
@pytest.mark.parametrize("stated", ["engram", "none"])
def test_w_the_launch_line_records_the_statement_with_a_daemon(dcfg, stated):
    r = run_daemon(dcfg, SANDBOX_DAEMON_EXPECTED=stated)
    assert r.returncode == 7, (r.returncode, r.stderr)
    f = fields(wrapper_line(dcfg))
    assert f["daemon"] == "engram" and f["daemon_expected"] == stated                 # the wrapper records, it does not compare


@TSS.needs_box
@pytest.mark.parametrize("stated", ["engram", "none"])
def test_w_the_launch_line_records_the_statement_without_a_daemon(dcfg, stated):
    r = dcfg.run(exec_=client_cmd(dcfg), SANDBOX_LOG=dcfg.log, SANDBOX_DAEMON_EXPECTED=stated)
    assert r.returncode == 7, (r.returncode, r.stderr)
    f = fields(wrapper_line(dcfg))
    assert "daemon" not in f and f["daemon_expected"] == stated and ARM_LABEL not in wrapper_line(dcfg)


@TSS.needs_box
def test_w_a_wrapper_that_was_not_told_says_unstated_with_and_without_a_daemon(dcfg):
    r = run_daemon(dcfg)
    assert r.returncode == 7, (r.returncode, r.stderr)
    assert fields(wrapper_line(dcfg))["daemon_expected"] == "unstated"
    os.unlink(dcfg.log)
    r = dcfg.run(exec_=client_cmd(dcfg), SANDBOX_LOG=dcfg.log)
    assert r.returncode == 7, (r.returncode, r.stderr)
    f = fields(wrapper_line(dcfg))
    assert f["daemon_expected"] == "unstated" and "daemon" not in f


@TSS.needs_box
@pytest.mark.parametrize("val", ["", "Engram", "ENGRAM", "engram ", "None", "1", "unstated", "other"])
def test_w_any_other_value_is_refused_by_the_wrapper_by_name(dcfg, fake_bwrap, val):
    TSS.assert_refused(dcfg, fake_bwrap, "SANDBOX_DAEMON_EXPECTED", SANDBOX_DAEMON_EXPECTED=val)


# ======================================================================================== K2 for real: a daemon that dies mid-session
DRIVER_NO_ARROW = r'''
import os, subprocess, sys
a = sys.argv[1:]
val = lambda f: a[a.index(f) + 1]
home, out = os.path.abspath(val("--arm-home")), val("--out")
env = {"PATH": os.environ["PATH"], "HOME": home, "TERM": "dumb", "LANG": "C.UTF-8",
       "ANTHROPIC_BASE_URL": os.environ["BEAM_OLLAMA_URL"], "ANTHROPIC_AUTH_TOKEN": "ollama", "ANTHROPIC_API_KEY": "",
       "DISABLE_TELEMETRY": "1", "DISABLE_AUTOUPDATER": "1", "PROCTOR_DIR": os.path.join(os.path.abspath(out), "proctor")}
for i, x in enumerate(a):
    if x == "--env":
        k, _, v = a[i + 1].partition("="); env[k] = v
os.makedirs(os.path.join(home, "work"), exist_ok=True)
sys.exit(subprocess.run(["claude", "-p"], cwd=os.path.join(home, "work"), env=env, timeout=120).returncode)
'''

KILL_DAEMON_THEN_EXIT = ("kill $(cat %s/.engram/recall-daemon.pid); i=0; while [ -e %s/.engram/recall-daemon.pid ] && [ $i -lt 100 ]; "
                         "do sleep 0.1; i=$((i+1)); done; exit 7")


@TSS.needs_box
def test_k2_a_daemon_that_dies_mid_session_is_recorded_as_already_gone_and_the_session_still_passes(w):
    full_slot(w)
    driver = w.tools / "driver-no-arrow.py"
    driver.write_text(DRIVER_NO_ARROW)
    slot = w.cfg.slot
    r = SL.run_feeder(sys.executable, str(driver), w.argv(), sandbox=w.sandbox(exec_=KILL_DAEMON_THEN_EXIT % (slot, slot)),
                      log_dir=str(w.logs), state_dir=str(w.state), env=w.env(), test_stub=True, daemon_expected="engram")
    assert r.returncode == 7 and r.verdict == "not-flagged"
    assert (r.daemon, r.daemon_expected, r.daemon_stop_outcome) == ("engram", "engram", "already-gone")
    f = SL.read_launch_fields(r.log)
    assert f["daemon"] == "engram" and f["daemon_expected"] == "engram"
