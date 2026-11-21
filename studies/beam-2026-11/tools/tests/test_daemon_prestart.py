"""Cells for the recall-daemon pre-start (pilot round 3, route (c)): the box starts the arm's own recall daemon BEFORE the
client, gates the client on the daemon's socket, and stops the daemon after the client and before anything is saved.

Contract-first (written before the implementation). The contract, D1-D7, is the spec's:
  D1  SANDBOX_DAEMON: absent = no daemon; `engram` is the only value, anything else a named refusal; module-owned (a caller's
      is refused), set by the module if and only if the slot holds the three fixed paths, in ONE place.
  D2  the daemon starts with the same command the arm's shipped launcher uses (derived, not restated): a cell reads a launcher
      file and compares; the launch line records the sha256 of the daemon script and of the launcher.
  D3  readiness gate: no client until a connect to <slot>/.engram/recall-daemon.sock succeeds; 60 s; loud (LaunchStop); the
      time-to-ready is recorded on a `daemon-ready` log line.
  D4  stop before snapshot: SIGTERM after the client, bounded wait, SIGKILL and a NAMED fault; the session's rc is the client's.
  D5  no new binds.   D6  a slot whose socket path would exceed 107 bytes is refused.   D7  the label.
Synthetic fixtures only: a STUB daemon script in a test slot (writes its pid file, binds after a delay, serves connects, exits on
SIGTERM; variants never bind, exit early, ignore SIGTERM). No real daemon, no real binary, no model.
"""
import importlib.util, os, re, shutil, subprocess, sys, time
import pytest
from conftest import TOOLS
import test_student_sandbox as TSS
from test_student_sandbox import fake_bwrap                 # fixtures reused as they are
from test_sandbox_launch import w, mk_sandbox, SL            # noqa: F401  (w: the module cells' world; SL: the module under test)

WRAPPER_TEXT = open(TSS.WRAPPER).read()
HOOKS = os.path.join(".engram", "marketplace", "plugins", "engram", "hooks")
ARM_LABEL = "the box with the recall daemon"

STUB_DAEMON = r'''
import os, signal, socket, sys, time
home = os.environ.get("ENGRAM_HOME") or sys.argv[1]
cfg = {}
try:
    for tok in open(os.path.join(home, "stub-config")).read().split():
        k, _, v = tok.partition("="); cfg[k] = v
except OSError:
    pass
mode, delay = cfg.get("mode", "ok"), float(cfg.get("delay", "0.3"))
pid_path, sock_name = os.path.join(home, "recall-daemon.pid"), "recall-daemon.sock"
with open(pid_path, "w") as f:                       # the real daemon's order: pid file, bind, listen
    f.write(str(os.getpid()))
def cleanup(*_):
    for p in (pid_path, os.path.join(home, sock_name)):
        try:
            os.unlink(p)
        except OSError:
            pass
    os._exit(0)
signal.signal(signal.SIGTERM, signal.SIG_IGN if mode == "ignore-term" else cleanup)
time.sleep(delay)
if mode == "exit-early":
    sys.exit(3)
if mode == "never-bind":
    while True:
        time.sleep(0.2)
os.chdir(home)
s = socket.socket(socket.AF_UNIX)
s.bind(sock_name)
s.listen(8)
with open(os.path.join(home, "stub-bind-time"), "w") as f:
    f.write(repr(time.time()))
while True:
    c, _ = s.accept()
    c.close()
'''

# A fixture copy of a shipped launcher: only the launch line matters to the cells; it is the line the arm's launcher has today.
LAUNCHER_FIXTURE = '''#!/usr/bin/env bash
# fixture copy of a recall-daemon launcher: the surrounding logic is not the cells' business, the launch line is
ENGRAM_HOME="${ENGRAM_HOME:-$HOME/.engram}"
DAEMON_SCRIPT="$(dirname "$0")/engram-surface-daemon.py"
LOG_PATH="$ENGRAM_HOME/surface-daemon.log"
if true; then
    mkdir -p "$ENGRAM_HOME"
    env ENGRAM_HOME="$ENGRAM_HOME" $HOME/.engram/venv/bin/python3 "$DAEMON_SCRIPT" "$ENGRAM_HOME" >> "$LOG_PATH" 2>&1 < /dev/null &
fi
'''

CLIENT = r'''
import os, socket, sys, time
slot = sys.argv[1]
t = time.time()
s = socket.socket(socket.AF_UNIX)
try:
    s.connect(os.path.join(slot, ".engram", "recall-daemon.sock")); ok = "ok"
except OSError as e:
    ok = "fail:" + type(e).__name__
with open(os.path.join(slot, "client-start"), "w") as f:
    f.write("%r %s\n" % (t, ok))
sys.exit(7)
'''


def build_engram_slot(slot, *, mode="ok", delay=0.3, python=True, script=True, enginedir=True, launcher=True):
    """A synthetic arm install inside `slot`, each of the three fixed paths of D1 optional."""
    eh = os.path.join(slot, ".engram")
    if enginedir:
        os.makedirs(os.path.join(eh, "venv", "bin"), exist_ok=True)
        os.makedirs(os.path.join(slot, HOOKS), exist_ok=True)
        if python:
            os.symlink("/usr/bin/python3", os.path.join(eh, "venv", "bin", "python3"))
        if script:
            TSS.make_exe(os.path.join(slot, HOOKS, "engram-surface-daemon.py"), STUB_DAEMON)
        if launcher:
            TSS.make_exe(os.path.join(slot, HOOKS, "start-engram-daemon.sh"), LAUNCHER_FIXTURE)
        with open(os.path.join(eh, "stub-config"), "w") as f:
            f.write("mode=%s delay=%s\n" % (mode, delay))
    with open(os.path.join(slot, "client.py"), "w") as f:
        f.write(CLIENT)
    return eh


def set_stub(slot, **kw):
    with open(os.path.join(slot, ".engram", "stub-config"), "w") as f:
        f.write(" ".join("%s=%s" % kv for kv in kw.items()) + "\n")


@pytest.fixture
def dcfg(tmp_path_factory):
    """One wrapper configuration whose slot holds the synthetic arm install. The root is short on purpose (the socket path)."""
    c = TSS.Cfg(tmp_path_factory.mktemp("d"))
    build_engram_slot(c.slot)
    yield c
    units, ended = TSS.stop_boxes_of(c.root)
    TSS.CREATED_UNITS.extend(units)
    assert not [u for u in units if u in TSS.active_scope_units()], "a box scope of this cell is still active"
    assert not ended, "processes of this cell outlived it and had to be ended: %s" % ended


def client_cmd(cfg):
    return "/usr/bin/python3 %s/client.py %s" % (cfg.slot, cfg.slot)


def run_daemon(cfg, exec_=None, **kw):
    kw.setdefault("SANDBOX_DAEMON", "engram")
    kw.setdefault("SANDBOX_LOG", cfg.log)
    r = cfg.run(exec_=exec_ or client_cmd(cfg), **kw)
    if kw["SANDBOX_DAEMON"] == "engram" and kw["SANDBOX_LOG"] and log_line(cfg, "wrapper-launch"):
        wait_report_closed(cfg)      # the daemon's lines reach the log through the reader, a moment after the box ends
    return r


def log_lines(cfg):
    return open(cfg.log).read().splitlines() if os.path.exists(cfg.log) else []


def wait_report_closed(cfg, secs=20):
    """The reader's closing line is the sentinel that it has copied everything the box wrote: wait for it (bounded)."""
    end = time.time() + secs
    while time.time() < end:
        if any(l.startswith("daemon-report ") and " closed " in l for l in log_lines(cfg)):
            return True
        time.sleep(0.05)
    return False


def fields(line):
    return dict(tok.partition("=")[::2] for tok in line.split() if "=" in tok)


RE_REPORT_LINE = re.compile(r"daemon-report seq=[0-9]+ time=[0-9]+\.[0-9]{6} line=(.*)")
DAEMON_KINDS = ("daemon-ready", "daemon-not-ready", "daemon-stop", "daemon-fault")


def log_line(cfg, prefix):
    """The first log line that starts with `prefix `. A daemon event is read only as the reader writes it (`daemon-report seq=
    time= line=<event>`): a bare `daemon-ready ...` line in the log is not an event, and is not returned."""
    for l in log_lines(cfg):
        m = RE_REPORT_LINE.fullmatch(l)
        if m:
            l = m.group(1)
        elif l.split(" ", 1)[0] in DAEMON_KINDS:
            continue
        if l.startswith(prefix + " "):
            return l
    return None


def slot_leftovers(cfg):
    eh = os.path.join(cfg.slot, ".engram")
    return [n for n in ("recall-daemon.pid", "recall-daemon.sock") if os.path.lexists(os.path.join(eh, n))]


# ======================================================================================== D1: the one setting
@TSS.needs_box
def test_absent_no_daemon_and_the_launch_line_unchanged(dcfg):
    r = dcfg.run(exec_=client_cmd(dcfg), SANDBOX_LOG=dcfg.log)
    assert r.returncode == 7, (r.returncode, r.stderr)
    assert open(os.path.join(dcfg.slot, "client-start")).read().split()[1].startswith("fail")   # nothing listened
    assert slot_leftovers(dcfg) == [] and not os.path.exists(os.path.join(dcfg.slot, ".engram", "stub-bind-time"))
    lines = log_lines(dcfg)
    assert not [l for l in lines if l.startswith("daemon-")], lines
    launch = log_line(dcfg, "wrapper-launch")
    assert "daemon" not in launch and ARM_LABEL not in launch, launch


@TSS.needs_box
@pytest.mark.parametrize("val", ["other", "", "ENGRAM", "engram ", "none", "1"])
def test_other_values_are_refused_and_never_defaulted(dcfg, fake_bwrap, val):
    TSS.assert_refused(dcfg, fake_bwrap, "SANDBOX_DAEMON", SANDBOX_DAEMON=val)


def test_a_caller_supplied_setting_is_refused_like_the_other_module_owned_names(w):
    assert "SANDBOX_DAEMON" in SL.MODULE_OWNED
    for val in ("engram", "other"):
        with pytest.raises(SL.LaunchRefused, match="SANDBOX_DAEMON"):
            mk_sandbox(w.settings(SANDBOX_DAEMON=val), str(w.expected))
    with pytest.raises(SL.LaunchRefused, match="SANDBOX_DAEMON"):
        w.launch(argv=w.argv(extra=("--env", "SANDBOX_DAEMON=engram")))   # nor through the feeder's argv
    w.assert_nothing_started()


@pytest.mark.parametrize("python", [True, False])
@pytest.mark.parametrize("script", [True, False])
@pytest.mark.parametrize("enginedir", [True, False])
def test_the_module_sets_it_exactly_when_the_three_paths_exist(python, script, enginedir):
    """All 8 present/absent combinations of the three fixed paths, through the module's one function."""
    slot = "/synthetic/slot"
    want = python and script and enginedir
    isfile = lambda p: (p.endswith("/venv/bin/python3") and python) or (p.endswith("/hooks/engram-surface-daemon.py") and script)
    isdir = lambda p: p == slot + "/.engram" and enginedir
    assert SL.daemon_setting(slot, _isfile=isfile, _isdir=isdir) == ("engram" if want else None)


def test_the_module_sets_it_on_the_real_filesystem_and_in_one_place(tmp_path):
    full, bare = tmp_path / "full", tmp_path / "bare"
    full.mkdir(); bare.mkdir()
    build_engram_slot(str(full))
    assert SL.daemon_setting(str(full)) == "engram" and SL.daemon_setting(str(bare)) is None
    os.unlink(str(full / ".engram" / "venv" / "bin" / "python3"))
    os.symlink("/no/such/python", str(full / ".engram" / "venv" / "bin" / "python3"))   # a dangling link is not the file
    assert SL.daemon_setting(str(full)) is None
    code = [l for l in open(SL.__file__).read().splitlines() if not l.lstrip().startswith("#")]
    sets = [l for l in code if re.search(r"""\[\s*["']SANDBOX_DAEMON["']\s*\]\s*=(?!=)|["']SANDBOX_DAEMON["']\s*:|update\([^)]*SANDBOX_DAEMON\s*=""", l)]
    assert len(sets) == 1, sets   # no other way to set it: one place in the code


def test_a_slot_with_the_arm_install_gets_the_setting_from_the_module_alone(w):
    build_engram_slot(w.cfg.slot)
    with pytest.raises(SL.LaunchStop):                                  # the stub feeder writes no daemon lines: see below
        w.launch("ok")
    pairs = w.records()[0]["pairs"]
    assert pairs.get("SANDBOX_DAEMON") == "engram"


def test_a_slot_without_the_arm_install_gets_no_setting_and_no_daemon_check(w):
    assert w.launch("ok").returncode == 0
    assert "SANDBOX_DAEMON" not in w.records()[0]["pairs"]


# ======================================================================================== D6: the socket path
def test_the_socket_length_is_checked_at_the_byte(tmp_path):
    tail = "/.engram/recall-daemon.sock"
    assert SL.DAEMON_SOCKET_MAX == 107
    base = str(tmp_path) + "/s"
    ok = base + "x" * (107 - len(base + tail))
    assert len(ok + tail) == 107
    SL.check_daemon_socket(ok)                                    # 107 bytes: allowed
    with pytest.raises(SL.LaunchRefused, match="107"):
        SL.check_daemon_socket(ok + "x")                          # 108: refused, named
    with pytest.raises(SL.LaunchRefused, match="107"):
        SL.check_daemon_socket(base + "é" * 40)                   # bytes, not characters


def test_a_launch_with_a_slot_too_long_for_the_socket_is_refused_before_anything_starts(w):
    long_slot = os.path.join(w.root, "cfg", "slot", "x" * 80)
    os.makedirs(long_slot)
    build_engram_slot(long_slot)
    with pytest.raises(SL.LaunchRefused, match="107"):
        w.launch("ok", argv=["--arm-home", long_slot, "--out", w.out()],
                 sandbox=w.sandbox(SANDBOX_SLOT=long_slot))
    w.assert_nothing_started()


@TSS.needs_box
def test_the_wrapper_refuses_a_too_long_slot_itself(tmp_path_factory, fake_bwrap):
    root = tmp_path_factory.mktemp("d")
    c = TSS.Cfg(root)
    deep = os.path.join(c.slot, "w" * 90)
    os.makedirs(deep)
    c.slot = deep                                                   # the wrapper's slot is the long one
    build_engram_slot(deep)
    TSS.assert_refused(c, fake_bwrap, "recall-daemon.sock", SANDBOX_DAEMON="engram", HOME=deep, PROCTOR_DIR=deep + "/proctor")


# ======================================================================================== D2: derived, not restated
def launcher_line(text):
    got = [l.strip() for l in text.splitlines() if l.strip().startswith("env ENGRAM_HOME=")]
    assert len(got) == 1, "the launcher must hold exactly one launch line"
    return got[0]


def render(line, home, slot, script, logp):
    return line.replace("$ENGRAM_HOME", home).replace("$HOME", slot).replace("$DAEMON_SCRIPT", script).replace("$LOG_PATH", logp)


def expected_line(launcher_text, slot):
    slot = os.path.realpath(slot)
    home = slot + "/.engram"
    return render(launcher_line(launcher_text), home, slot, slot + "/" + HOOKS + "/engram-surface-daemon.py", home + "/surface-daemon.log")


def matches(launcher_text, slot, built):
    return built == expected_line(launcher_text, slot)


def launchers():
    out = [("fixture", LAUNCHER_FIXTURE)]
    real = os.environ.get("BEAM_ARM_LAUNCHER")      # optional: the arm's own launcher file, when a seat has one to hand
    if real and os.path.isfile(real):
        out.append(("arm", open(real).read()))
    return out


@TSS.needs_box
@pytest.mark.parametrize("which", [n for n, _ in launchers()])
def test_the_wrapper_builds_the_launchers_own_line_and_records_both_hashes(dcfg, which):
    text = dict(launchers())[which]
    r = run_daemon(dcfg)
    assert r.returncode == 7, (r.returncode, r.stderr)
    built = log_line(dcfg, "daemon-command")[len("daemon-command "):]
    assert built.endswith("&") and matches(text, dcfg.slot, built), (built, expected_line(text, dcfg.slot))
    f = fields(log_line(dcfg, "wrapper-launch"))
    script = os.path.join(dcfg.slot, HOOKS, "engram-surface-daemon.py")
    launch = os.path.join(dcfg.slot, HOOKS, "start-engram-daemon.sh")
    assert f["daemon"] == "engram"
    assert f["daemon_script_sha256"] == TSS.sha256_of(script)
    assert f["daemon_launcher_sha256"] == TSS.sha256_of(launch)


def test_the_comparison_reddens_on_one_changed_argument(tmp_path):
    """The comparison is the cell's instrument: it must tell a built line that differs in ONE argument from the launcher's."""
    slot = str(tmp_path)
    good = expected_line(LAUNCHER_FIXTURE, slot)
    assert matches(LAUNCHER_FIXTURE, slot, good)
    for bad in (good.replace(' "' + os.path.realpath(slot) + '/.engram" >>', " >>"),      # the trailing ENGRAM_HOME argument dropped
                good.replace("2>&1", "2>/dev/null"), good.replace(">> ", "> "), good.replace("env ", ""),
                good.replace("< /dev/null &", "&")):
        assert bad != good and not matches(LAUNCHER_FIXTURE, slot, bad)


# ======================================================================================== D3: the readiness gate
@TSS.needs_box
def test_the_client_starts_only_after_the_socket_answers_and_time_to_ready_is_recorded(dcfg):
    set_stub(dcfg.slot, mode="ok", delay=1.0)
    t0 = time.time()
    r = run_daemon(dcfg)
    assert r.returncode == 7, (r.returncode, r.stderr)
    started, ok = open(os.path.join(dcfg.slot, "client-start")).read().split()
    bound = float(open(os.path.join(dcfg.slot, ".engram", "stub-bind-time")).read())
    assert ok == "ok", "the client's own connect failed: it started before the socket answered"
    assert float(started) >= bound
    ready = fields(log_line(dcfg, "daemon-ready"))
    ttr = float(ready["time_to_ready_s"])
    assert 0.9 <= ttr < 30 and int(ready["pid"]) > 0
    assert ready["time"] and float(ready["time"]) >= t0


@TSS.needs_box
def test_the_default_timeouts_are_on_the_launch_line_and_the_label_is_in_the_words_of_the_ruling(dcfg):
    r = run_daemon(dcfg)
    assert r.returncode == 7, (r.returncode, r.stderr)
    launch = log_line(dcfg, "wrapper-launch")
    f = fields(launch)
    assert f["daemon_ready_timeout_s"] == "60" and f["daemon_term_wait_s"] == "20", launch
    assert ARM_LABEL in launch and "caps and peaks are those of " + ARM_LABEL in launch, launch


@TSS.needs_box
@pytest.mark.parametrize("mode,reason", [("never-bind", "timeout"), ("exit-early", "exited-early")])
def test_a_daemon_that_never_becomes_ready_means_no_client_and_a_named_failure(dcfg, mode, reason):
    set_stub(dcfg.slot, mode=mode, delay=0.3)
    t0 = time.time()
    r = run_daemon(dcfg, SANDBOX_TEST_DAEMON_READY_S="3")
    assert not os.path.exists(os.path.join(dcfg.slot, "client-start")), "the client was started without a daemon"
    assert r.returncode == 4, (r.returncode, r.stderr)
    assert "recall daemon" in r.stderr and "did not become ready" in r.stderr and reason in r.stderr, r.stderr
    nr = fields(log_line(dcfg, "daemon-not-ready"))
    assert nr["reason"] == reason
    assert log_line(dcfg, "daemon-ready") is None
    assert (time.time() - t0) < 25
    assert TSS.pids_mentioning(os.path.join(dcfg.slot, ".engram")) == [], "the daemon that never became ready was not stopped"
    if mode == "never-bind":
        assert slot_leftovers(dcfg) == []        # it was sent SIGTERM and cleaned up after itself (an early exit leaves its own pid file)


@TSS.needs_box
def test_the_readiness_timeout_is_a_test_knob_only(dcfg, fake_bwrap):
    TSS.assert_refused(dcfg, fake_bwrap, "SANDBOX_TEST_DAEMON_READY_S", SANDBOX_DAEMON="engram", SANDBOX_TEST_DAEMON_READY_S="0")
    TSS.assert_refused(dcfg, fake_bwrap, "SANDBOX_TEST_DAEMON_TERM_S", SANDBOX_DAEMON="engram", SANDBOX_TEST_DAEMON_TERM_S="x")


# ======================================================================================== D4: stop before the snapshot
@TSS.needs_box
def test_after_the_session_the_daemon_is_gone_with_its_files_and_the_clients_rc_is_the_sessions(dcfg):
    r = run_daemon(dcfg)
    assert r.returncode == 7, (r.returncode, r.stderr)
    assert slot_leftovers(dcfg) == [], "pid file or socket still in the slot after the session"
    assert TSS.pids_mentioning(os.path.join(dcfg.slot, ".engram")) == [], "a process of the slot's engram home is still running"
    stop = fields(log_line(dcfg, "daemon-stop"))
    assert stop["outcome"] == "term" and log_line(dcfg, "daemon-fault") is None


@TSS.needs_box
def test_a_daemon_that_ignores_sigterm_is_killed_and_the_fault_is_named(dcfg):
    set_stub(dcfg.slot, mode="ignore-term", delay=0.3)
    t0 = time.time()
    r = run_daemon(dcfg, SANDBOX_TEST_DAEMON_TERM_S="2")
    assert r.returncode == 7, (r.returncode, r.stderr)            # the session's rc is still the client's
    fault = fields(log_line(dcfg, "daemon-fault"))
    assert fault["kind"] == "sigkill" and int(fault["pid"]) > 0
    assert fields(log_line(dcfg, "daemon-stop"))["outcome"] == "killed"
    assert "SIGKILL" in r.stderr
    assert TSS.pids_mentioning(os.path.join(dcfg.slot, ".engram")) == []
    assert time.time() - t0 < 30


@TSS.needs_box
def test_the_quiescence_check_counts_the_daemon_by_name_and_finds_it_gone(dcfg):
    p1 = _load_p1()
    started = subprocess.Popen(["/bin/sh", "-c", expected_line(LAUNCHER_FIXTURE, dcfg.slot).rstrip("&") + " ; sleep 30"],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        end = time.time() + 10
        while not p1.slot_pids(dcfg.slot) and time.time() < end:
            time.sleep(0.1)
        assert p1.slot_pids(dcfg.slot), "a running daemon of the slot is not counted by name"
    finally:
        started.terminate(); started.wait(timeout=10)
        TSS.stop_boxes_of(dcfg.root)
    end = time.time() + 10
    while p1.slot_pids(dcfg.slot) and time.time() < end:
        time.sleep(0.1)
    assert p1.slot_pids(dcfg.slot) == []
    r = run_daemon(dcfg)
    assert r.returncode == 7 and p1.slot_pids(dcfg.slot) == [], "the session left a process the quiescence check counts"


def _load_p1():
    spec = importlib.util.spec_from_file_location("p1_session_under_test_daemon", os.path.join(TOOLS, "p1-session.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ======================================================================================== the module surfaces it, named
needs_arrow = pytest.mark.usefixtures("arrow_python")


def _real(w, arrow_python, exec_, **settings):
    return SL.run_feeder(arrow_python, str(w.driver), w.argv(), sandbox=w.sandbox(exec_=exec_, **settings), log_dir=str(w.logs),
                         state_dir=str(w.state), env=w.env(), test_stub=True)


def _client(w):
    return client_cmd(w.cfg)


def test_a_session_that_was_to_have_the_daemon_and_has_no_ready_line_is_a_named_stop(w):
    build_engram_slot(w.cfg.slot)
    with pytest.raises(SL.LaunchStop, match="recall daemon") as e:       # the stub feeder's launch line does not even say daemon=
        w.launch("ok")
    assert e.value.result.log
    res = SL.LaunchResult(0)
    why = SL.daemon_verdict("engram", {"daemon": "engram"}, [], res)    # a launch line that says it, and no daemon line at all
    assert why and "daemon-ready" in why and "daemon-not-ready" in why
    assert SL.daemon_verdict("engram", {"daemon": "engram"}, [("daemon-ready", {"time_to_ready_s": "1.5", "pid": "9"}),
                                                              ("daemon-stop", {"outcome": "term", "pid": "9"})], res) is None
    assert res.daemon == "engram" and res.daemon_time_to_ready_s == 1.5 and res.box_label == ARM_LABEL
    assert SL.daemon_verdict(None, {}, [], SL.LaunchResult(0)) is None
    assert "did not ask" in SL.daemon_verdict(None, {"daemon": "engram"}, [], SL.LaunchResult(0))


@TSS.needs_box
@needs_arrow
def test_e2e_ok_through_the_module_with_the_real_wrapper(w, arrow_python):
    build_engram_slot(w.cfg.slot)
    r = _real(w, arrow_python, _client(w))
    assert r.returncode == 7 and r.verdict == "not-flagged"
    assert r.daemon == "engram" and r.daemon_time_to_ready_s > 0 and r.box_label == ARM_LABEL
    assert slot_leftovers(w.cfg) == []
    assert _load_p1().slot_pids(w.cfg.slot) == []                  # the quiescence check, before anything would be saved


@TSS.needs_box
@needs_arrow
@pytest.mark.parametrize("mode,words", [("never-bind", "did not become ready"), ("exit-early", "did not become ready")])
def test_e2e_not_ready_is_a_launch_stop_and_no_client_ran(w, arrow_python, mode, words):
    build_engram_slot(w.cfg.slot, mode=mode)
    with pytest.raises(SL.LaunchStop, match=words) as e:
        _real(w, arrow_python, _client(w), SANDBOX_TEST_DAEMON_READY_S="3")
    assert not os.path.exists(os.path.join(w.cfg.slot, "client-start"))
    assert e.value.result.returncode == 4


@TSS.needs_box
@needs_arrow
def test_e2e_a_sigkill_is_a_launch_stop_naming_the_fault(w, arrow_python):
    build_engram_slot(w.cfg.slot, mode="ignore-term")
    with pytest.raises(SL.LaunchStop, match="SIGKILL") as e:
        _real(w, arrow_python, _client(w), SANDBOX_TEST_DAEMON_TERM_S="2")
    assert e.value.result.returncode == 7


# ======================================================================================== the report channel stays private
PROBE = r'''
import os, sys
slot, suffix = sys.argv[1], sys.argv[2]
mine = open(os.path.join(slot, "control-" + suffix), "w")          # a control: this scanner must see a descriptor of its own
found, control = [], False
for pid in os.listdir("/proc"):
    if not pid.isdigit():
        continue
    d = "/proc/%s/fd" % pid
    try:
        names = os.listdir(d)
    except OSError:
        continue
    for n in names:
        try:
            t = os.readlink(d + "/" + n)
        except OSError:
            continue
        if t.endswith("control-" + suffix):
            control = True
        elif t.endswith(suffix):
            found.append((pid, n, t))
with open(os.path.join(slot, "probe-result"), "w") as f:
    f.write(repr((control, found)))
'''


@TSS.needs_box
def test_no_process_of_the_box_can_reach_the_report_descriptor_through_proc(dcfg):
    """No process the box can see holds a descriptor on SANDBOX_LOG (the report channel is a pipe whose reader is outside the box;
    test_daemon_report.py pins what the wrapper hands the box, which a non-dumpable process hides from this scan)."""
    with open(os.path.join(dcfg.slot, "probe.py"), "w") as f:
        f.write(PROBE)
    r = run_daemon(dcfg, exec_="/usr/bin/python3 %s/probe.py %s %s" % (dcfg.slot, dcfg.slot, os.path.basename(dcfg.log)))
    assert r.returncode == 0, (r.returncode, r.stderr)
    control, found = eval(open(os.path.join(dcfg.slot, "probe-result")).read())
    assert control, "the probe cannot see descriptors at all: the cell proves nothing"
    assert found == [], "a process of the box can see the log descriptor: %s" % (found,)


# ======================================================================================== D5: no new binds
def test_no_bind_was_added_for_the_daemon():
    """The box's bind set is the S3 lists and the argv built from them; the daemon block adds none: the wrapper's daemon code
    holds no --bind / --ro-bind / box-path entry of its own."""
    block = WRAPPER_TEXT[WRAPPER_TEXT.index("DAEMON"):]
    for line in WRAPPER_TEXT.splitlines():
        if "DAEMON" in line:
            assert "--bind" not in line and "--ro-bind" not in line and "BOX_RO+=" not in line and "EXTRA_BINDS+=" not in line, line
    assert "DAEMON" in block
