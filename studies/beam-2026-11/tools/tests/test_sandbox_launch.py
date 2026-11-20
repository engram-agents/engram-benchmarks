"""Cells for tools/sandbox_launch.py (the one door through which a student session starts) and for the retired practice
launchers. Contract-first: the cells state the contract of the spec (design A10, team crossings 33592, 33600, 33601,
33605); synthetic fixtures only, no real data, no student model, no Ollama, no host path.

Two kinds of cell. Most use a STUB FEEDER that stands in for feed4.py: it records what the module handed it (argv, PATH,
the `--env` pairs) and writes the log lines the real wrapper would (a launch line carrying the sha256 of the `claude` and
sandbox-forward.py that sit first on its PATH, so the module's own comparison is real). The cells marked `needs_box` run
the REAL wrapper (SANDBOX_TEST=1, a stub pinned binary) through the REAL feed4.Student, on a host that has bwrap.
"""
import ast, hashlib, importlib.util, json, os, re, shutil, subprocess, sys
import pytest
from conftest import TOOLS
import test_student_sandbox as TSS

MOD = os.path.join(TOOLS, "sandbox_launch.py")
_spec = importlib.util.spec_from_file_location("sandbox_launch_under_test", MOD)
SL = importlib.util.module_from_spec(_spec)
if os.path.exists(MOD):  # before the module exists the cells fail on the missing file, not on the import
    _spec.loader.exec_module(SL)

NOT_FLAGGED = "not-flagged"
FLAGGED = "flagged: endpoint unreachable, nothing reached it"

STUB = r'''
import hashlib, json, os, sys
a = sys.argv[1:]
pairs = {}
for i, x in enumerate(a):
    if x == "--env":
        k, _, v = a[i + 1].partition("="); pairs[k] = v
first = os.environ["PATH"].split(":")[0]
claude, fwd = os.path.join(first, "claude"), os.path.join(first, "sandbox-forward.py")
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest() if os.path.isfile(p) else None
log = pairs.get("SANDBOX_LOG")
with open(os.environ["REC"], "a") as f:
    f.write(json.dumps({"argv": a, "pairs": pairs, "path": os.environ["PATH"], "path0": first,
                        "claude_is_link": os.path.islink(claude), "claude_sha": sha(claude), "fwd_sha": sha(fwd),
                        "log_existed": bool(log) and os.path.exists(log)}) + "\n")
if "--dump-plan" in a:
    print("[]"); sys.exit(0)
mode = os.environ.get("STUB_MODE", "ok")
W, F = sha(claude), sha(fwd)
if mode == "badwrapper": W = "0" * 64
if mode == "badforwarder": F = "0" * 64
me = os.getpid()
start_of = lambda pid: open("/proc/%d/stat" % pid).read().rsplit(")", 1)[1].split()[19]
fpid, fstart = me, start_of(me)      # the stub stands in for the forwarder too: it is gone when the module looks
if mode == "reuse-same":             # a live process that IS what the launch line names (same pid, same start time)
    fpid = int(os.environ["HELPER_PID"]); fstart = start_of(fpid)
if mode == "reuse-diff":             # the pid is alive but is a different process (same pid, another start time)
    fpid = int(os.environ["HELPER_PID"]); fstart = str(int(start_of(fpid)) + 1)
sock = os.path.join(os.path.dirname(log), "bridge-%d.sock" % me) if log else ""
line = (f"wrapper-launch time=1 pid=2 wrapper_sha256={W} forwarder_sha256={F} scope_unit=student-sandbox-stub-{me} "
        f"forwarder_pid={fpid} forwarder_start={fstart} bridge_sock={sock} model=h:1")
if mode == "nomarker":
    line = line.replace(f"forwarder_start={fstart} ", "")
CF = "fwd-fault method=POST path=/x status=502 bytes_read=0 kind=upstream reason=connect-failed detail=refused"
body = {"ok": [line, "fwd-first-request"], "unreachable": [line, CF], "nolaunch": [], "nowrapper": ["fwd-first-request"], "two": [line, line, "fwd-first-request"],
        "badwrapper": [line, "fwd-first-request"], "badforwarder": [line, "fwd-first-request"],
        "plant": [line, "fwd-first-request"], "nomarker": [line, "fwd-first-request"], "reuse-same": [line, "fwd-first-request"], "reuse-diff": [line, "fwd-first-request"]}[mode]
if log and mode != "nolaunch":
    with open(log, "a") as f:
        f.write("".join(l + "\n" for l in body))
if mode == "plant":   # a survivor OUTSIDE any scope: its argv carries this launch's bridge socket path
    import subprocess
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", sock], start_new_session=True)
    with open(os.environ["REC"], "a") as f:
        f.write(json.dumps({"planted": p.pid}) + "\n")
sys.exit(int(os.environ.get("STUB_RC", "0")))
'''

DRIVER = r'''
import argparse, os, sys
sys.path.insert(0, %r)
import feed4
a = sys.argv[1:]
val = lambda f: a[a.index(f) + 1]
ns = argparse.Namespace(arm_home=val("--arm-home"), out=val("--out"), model="m", resume=None,
                        env=[a[i + 1] for i, x in enumerate(a) if x == "--env"])
os.makedirs(ns.out, exist_ok=True)
st = feed4.Student(ns)
if os.environ.get("DRIVER_DETACH"):   # return while the box is still running: the feeder is gone, its student is not
    import time
    log = [x.partition("=")[2] for x in a if x.startswith("SANDBOX_LOG=")][0]
    for _ in range(300):
        if os.path.exists(log) and "wrapper-launch " in open(log).read():
            os._exit(0)
        time.sleep(0.1)
    os._exit(3)
sys.exit(st.p.wait(timeout=90))
''' % TOOLS


class World:
    def __init__(self, root):
        self.root = root
        self.cfg = TSS.Cfg(root / "cfg")
        self.d = root / "d"; self.tools = self.d / "tools"; self.tools.mkdir(parents=True)
        self.logs = self.d / "logs"; self.logs.mkdir()
        self.stub = self.tools / "stub-feeder.py"; self.stub.write_text(STUB)
        self.driver = self.tools / "driver-feeder.py"; self.driver.write_text(DRIVER)
        self.rec = self.d / "rec.jsonl"
        self.expected = self.d / "expected.txt"
        self.write_expected()
        self.state = self.d / "state"       # the module's per-launch records (a state directory the caller supplies)
        self.n = 0

    def write_expected(self, wrapper=None, forwarder=None):
        self.expected.write_text("wrapper_sha256=%s\nforwarder_sha256=%s\n" % (
            wrapper or TSS.sha256_of(TSS.WRAPPER), forwarder or TSS.sha256_of(TSS.FWD)))

    def settings(self, exec_=None, **over):
        s = {k: v for k, v in self.cfg.env(exec_=exec_).items() if k.startswith("SANDBOX_")}
        s.update(over)
        return {k: v for k, v in s.items() if v is not None}

    def sandbox(self, **over):
        return SL.Sandbox(self.settings(**over), str(self.expected))

    def out(self):
        self.n += 1
        return str(self.d / f"out{self.n}")

    def env(self, **over):
        e = dict(os.environ, REC=str(self.rec), BEAM_OLLAMA_URL="http://localhost:%d" % self.cfg.model_port)
        e.update(over)
        return e

    def argv(self, out=None, extra=()):
        return ["--arm-home", self.cfg.slot, "--out", out or self.out(), *extra]

    def launch(self, mode="ok", *, feeder=None, argv=None, sandbox=None, rc=0, env=None, **kw):
        kw.setdefault("log_dir", str(self.logs))
        kw.setdefault("state_dir", str(self.state))
        e = self.env(STUB_MODE=mode, STUB_RC=str(rc), **(env or {}))
        return SL.run_feeder(sys.executable, str(feeder or self.stub), argv if argv is not None else self.argv(),
                             sandbox=sandbox if sandbox is not None else self.sandbox(), env=e, test_stub=True, **kw)

    def records(self):
        return [json.loads(l) for l in self.rec.read_text().splitlines()] if self.rec.exists() else []

    def assert_nothing_started(self):
        assert not self.rec.exists(), "a feeder process was started"
        assert os.listdir(self.logs) == [], "a log was created"


@pytest.fixture
def w(tmp_path):
    if shutil.which("systemctl") is None:
        pytest.skip("the module stops and checks the launch's scope through `systemctl --user`: a Linux/systemd host is needed")
    world = World(tmp_path)
    yield world
    # these cells leave nothing behind: any box of this cell (attributed by its scratch root, as in test_student_sandbox)
    units, ended = TSS.stop_boxes_of(str(tmp_path))
    TSS.CREATED_UNITS.extend(units)
    assert not ended, "processes of this cell outlived it and had to be ended: %s" % ended


# ====================================================================================== H: the expected-hashes file
def test_h_the_expected_file_is_two_lines_of_64_hex(w):
    assert SL.load_expected(str(w.expected)) == {"wrapper_sha256": TSS.sha256_of(TSS.WRAPPER),
                                                 "forwarder_sha256": TSS.sha256_of(TSS.FWD)}


H64 = "a" * 64
@pytest.mark.parametrize("text", [
    "", "wrapper_sha256=%s\n" % H64, "forwarder_sha256=%s\nwrapper_sha256=%s\n" % (H64, H64),
    "wrapper_sha256=%s\nforwarder_sha256=%s\nextra=1\n" % (H64, H64), "wrapper_sha256=%s\nforwarder_sha256=%s\n" % (H64, H64[:63]),
    "wrapper_sha256=%s\nforwarder_sha256=%s\n" % (H64, "A" * 64), "wrapper_sha256=%s\nforwarder_sha256=zz\n" % H64,
    "wrapper_sha256 %s\nforwarder_sha256=%s\n" % (H64, H64), "\nwrapper_sha256=%s\nforwarder_sha256=%s\n" % (H64, H64)])
def test_h_a_malformed_expected_file_is_a_named_refusal(w, text):
    w.expected.write_text(text)
    with pytest.raises(SL.LaunchRefused, match="malformed"):
        SL.load_expected(str(w.expected))
    with pytest.raises(SL.LaunchRefused, match="malformed"):
        w.sandbox()
    w.assert_nothing_started()


def test_h_a_missing_or_unnamed_expected_file_is_a_named_refusal(w):
    with pytest.raises(SL.LaunchRefused, match="cannot be read"):
        SL.load_expected(str(w.d / "no-such-file"))
    with pytest.raises(SL.LaunchRefused, match="not given"):
        SL.load_expected(None)   # the module has no default: the scored run passes the registered file


# ====================================================================================== M3: refusals before anything starts
@pytest.mark.parametrize("name", SL.REQUIRED_SANDBOX if os.path.exists(MOD) else [])
@pytest.mark.parametrize("how", ["missing", "empty"])
def test_m3_a_missing_required_setting_is_a_named_refusal(w, name, how):
    s = w.settings()
    if how == "missing":
        s.pop(name)
    else:
        s[name] = ""
    with pytest.raises(SL.LaunchRefused, match=name):
        SL.Sandbox(s, str(w.expected))
    w.assert_nothing_started()


def test_m3_learn_mode_does_not_need_the_allow_list_but_still_needs_the_rest(w):
    s = w.settings(SANDBOX_MODEL_LEARN="1"); s.pop("SANDBOX_MODEL_ALLOW")
    SL.Sandbox(s, str(w.expected))
    s.pop("SANDBOX_PROTECT")
    with pytest.raises(SL.LaunchRefused, match="SANDBOX_PROTECT"):
        SL.Sandbox(s, str(w.expected))


def test_m3_the_module_owns_the_log_and_the_binds(w):
    for n in SL.MODULE_OWNED:
        with pytest.raises(SL.LaunchRefused, match=n):
            SL.Sandbox(w.settings(**{n: "/x"}), str(w.expected))
    with pytest.raises(SL.LaunchRefused, match="SANDBOX_LOG"):
        w.launch(argv=w.argv(extra=("--env", "SANDBOX_LOG=/x")))   # nor may a caller smuggle one in through the argv
    w.assert_nothing_started()


def test_m3_a_log_path_that_already_exists_is_refused(w):
    p = w.logs / "taken.log"; p.write_text("wrapper-launch earlier\n")
    with pytest.raises(SL.LaunchRefused, match="already exists"):
        w.launch(log_path=str(p))
    assert not w.rec.exists() and p.read_text() == "wrapper-launch earlier\n"


def test_m3_a_claude_first_on_the_path_that_is_not_the_wrapper_is_refused(w):
    other = w.d / "other"; other.mkdir()
    TSS.make_exe(str(other / "claude"), "#!/bin/sh\nexit 0\n")
    with pytest.raises(SL.LaunchRefused, match="not the sandbox wrapper"):
        w.launch(argv=w.argv(extra=("--env", "PATH=%s:/usr/bin" % other)))
    w.assert_nothing_started()


def test_m3_a_path_override_that_keeps_the_wrapper_first_is_fine_and_no_claude_at_all_is_refused(w):
    with pytest.raises(SL.LaunchRefused, match="not found"):
        w.launch(argv=w.argv(extra=("--env", "PATH=/nonexistent-dir")))
    w.assert_nothing_started()
    assert w.launch().returncode == 0    # the positive control: the module's own PATH passes the same check


def test_m3_the_resolution_is_the_one_popen_makes_not_a_lookalike(w):
    """resolve_on_path picks the first executable regular FILE named claude, in order: a directory named claude, or a
    non-executable file, earlier on the path is skipped as Popen skips it."""
    a, b, c = (w.d / n for n in "abc")
    for d in (a, b, c):
        d.mkdir()
    (a / "claude").mkdir()
    (b / "claude").write_text("x"); os.chmod(b / "claude", 0o644)
    TSS.make_exe(str(c / "claude"), "#!/bin/sh\n")
    assert SL.resolve_on_path("claude", "%s:%s:%s" % (a, b, c), str(w.d)) == str(c / "claude")


@pytest.mark.parametrize("url,why", [
    ("http://localhost:{other}", "port"), ("http://127.0.0.1:%d", "ok"), ("http://[::1]:%d", "ok"), ("http://localhost", "port"),
    ("http://example.org:%d", "not loopback"), ("http://203.0.113.5:%d", "not loopback"), ("localhost:%d", "not loopback"),
])
def test_m3_the_model_url_must_be_loopback_on_the_sandbox_port(w, url, why):
    url = url.replace("{other}", str(w.cfg.model_port + 1))
    url = url % w.cfg.model_port if "%d" in url else url
    env = {"BEAM_OLLAMA_URL": url}
    if why == "ok":
        assert w.launch(env=env).returncode == 0
    else:
        with pytest.raises(SL.LaunchRefused, match=why):
            w.launch(env=env)
        w.assert_nothing_started()


def test_m3_the_model_url_follows_the_feeder_resolution_env_then_default_and_an_env_pair_wins(w):
    port = w.cfg.model_port
    assert SL.model_url([], {}) == SL.OLLAMA_DEFAULT
    u = lambda n: "http://localhost:" + str(n)
    assert SL.model_url([], {"BEAM_OLLAMA_URL": u(5)}) == u(5)
    assert SL.model_url(["--env", "ANTHROPIC_BASE_URL=" + u(7), "--env", "ANTHROPIC_BASE_URL=" + u(8)],
                        {"BEAM_OLLAMA_URL": u(5)}) == u(8)
    with pytest.raises(SL.LaunchRefused, match="port"):    # the env pair is what Student.__init__ uses: it is checked
        w.launch(argv=w.argv(extra=("--env", "ANTHROPIC_BASE_URL=" + u(port + 1))))
    w.assert_nothing_started()


def test_m3_the_default_url_and_the_env_name_are_feed_pys(w):
    src = open(os.path.join(TOOLS, "feed.py")).read()
    m = re.search(r'OLLAMA_URL = os\.environ\.get\("BEAM_OLLAMA_URL", "([^"]+)"\)', src)
    assert m and m.group(1) == SL.OLLAMA_DEFAULT


def test_m3_the_path_the_feeder_builds_is_what_the_module_assumes(w):
    for f in ("feed2.py", "feed4.py"):
        src = open(os.path.join(TOOLS, f)).read()
        assert '"PATH": os.environ["PATH"] + ":" + HERE' in src and "ANTHROPIC_BASE_URL\": OLLAMA_URL" in src, f
        assert 'for kv in args.env:' in src and 'env[k] = v' in src, f


# ====================================================================================== M1: one function, FEEDERS
def test_m1_feeders_are_the_three_implementations():
    assert SL.FEEDERS == ("feed.py", "feed2.py", "feed4.py")
    assert all(os.path.isfile(os.path.join(TOOLS, f)) for f in SL.FEEDERS)


def test_m1_a_dump_plan_call_runs_through_the_function_without_a_wrapper_and_creates_no_log(w):
    r = SL.run_feeder(sys.executable, str(w.stub), w.argv(extra=("--dump-plan",)), env=w.env(), test_stub=True)
    assert r.returncode == 0 and r.log is None and r.verdict is None
    (rec,) = w.records()
    assert rec["pairs"] == {} and rec["path"] == os.environ["PATH"]    # no SANDBOX_* pair, the PATH untouched
    assert os.listdir(w.logs) == [] and not os.path.exists(w.argv()[3])


def test_m1_a_session_without_a_sandbox_is_refused_and_so_is_a_name_that_is_not_a_feeder(w):
    with pytest.raises(SL.LaunchRefused, match="needs the sandbox"):
        SL.run_feeder(sys.executable, str(w.stub), w.argv(), env=w.env(), test_stub=True)
    with pytest.raises(SL.LaunchRefused, match="not one of the feeders"):
        SL.run_feeder(sys.executable, str(w.stub), w.argv(extra=("--dump-plan",)), env=w.env())
    w.assert_nothing_started()


# ====================================================================================== M2: what a session gets
def test_m2_the_wrapper_directory_holds_a_copy_of_the_wrapper_and_the_forwarder_first_on_the_path(w):
    r = w.launch()
    (rec,) = w.records()
    assert rec["path"].split(":")[0] == rec["path0"] and rec["path"].endswith(os.environ["PATH"])
    assert rec["claude_is_link"] is False                          # a copy, not a symlink (the wrapper looks beside itself)
    assert rec["claude_sha"] == TSS.sha256_of(TSS.WRAPPER) and rec["fwd_sha"] == TSS.sha256_of(TSS.FWD)
    assert r.returncode == 0 and not os.path.exists(rec["path0"]), "the wrapper directory is removed after the launch"


def test_m2_the_feeder_gets_every_required_setting_the_log_and_the_proctor_binds_as_env_pairs(w):
    out = w.out()
    w.launch(argv=w.argv(out))
    (rec,) = w.records()
    pairs = rec["pairs"]
    for n, v in w.settings().items():
        assert pairs[n] == v, n
    for n in SL.REQUIRED_SANDBOX:
        assert pairs[n]
    assert pairs["SANDBOX_RO_BINDS"] == str(w.tools) and pairs["SANDBOX_RO_ROOT"] == str(w.d)
    assert pairs["SANDBOX_RW_BINDS"] == os.path.join(out, "proctor") and pairs["SANDBOX_RW_ROOT"] == out
    assert os.path.isdir(os.path.join(out, "proctor"))
    assert os.path.dirname(pairs["SANDBOX_LOG"]) == str(w.logs)


# ====================================================================================== M4: after the session
def test_m4a_every_launch_gets_a_fresh_log_that_did_not_exist(w):
    r1, r2 = w.launch(), w.launch()
    assert r1.log != r2.log and os.path.exists(r1.log) and os.path.exists(r2.log)
    assert [x["log_existed"] for x in w.records()] == [False, False]
    assert sorted(os.listdir(w.logs)) == sorted(os.path.basename(x) for x in (r1.log, r2.log))


def test_m4b_log_verdict_runs_after_every_session_both_arms_setup_included(w):
    """A setup session is just another student session through the module: three sessions, three verdicts."""
    results = [w.launch(), w.launch(argv=w.argv(extra=("--first-session", "--setup-only"))), w.launch("unreachable")]
    assert [r.verdict for r in results] == [NOT_FLAGGED, NOT_FLAGGED, FLAGGED]
    assert len({r.log for r in results}) == 3


def test_m4c_a_log_verdict_refusal_stops_with_its_text_and_is_never_not_flagged(w):
    with pytest.raises(SL.LaunchStop, match="log-verdict refused .*cannot read the log") as e:
        w.launch("nolaunch")                  # the log is missing: the refusal's own text is carried
    assert e.value.result.verdict is None and e.value.result.returncode == 0
    with pytest.raises(SL.LaunchStop, match="expected exactly one line starting 'wrapper-launch ', found 0"):
        w.launch("nowrapper")                 # a log the forwarder wrote alone: no launch line
    with pytest.raises(SL.LaunchStop, match="found 2"):
        w.launch("two")                       # a log merged from two launches is refused too


def test_m4c_flagged_is_a_verdict_not_a_stop(w):
    r = w.launch("unreachable")
    assert r.verdict == FLAGGED


def test_m4d_the_verdict_line_is_copied_verbatim(w):
    assert w.launch().verdict == "not-flagged"
    assert w.launch("unreachable").verdict == "flagged: endpoint unreachable, nothing reached it"


def test_m4_a_feeder_failure_is_carried_with_the_verdict_not_hidden(w):
    r = w.launch(rc=3)
    assert r.returncode == 3 and r.verdict == NOT_FLAGGED
    with pytest.raises(SL.LaunchStop) as e:
        w.launch("nolaunch", rc=3)
    assert e.value.result.returncode == 3


# ====================================================================================== M4b: the pre-launch hash check
@pytest.mark.parametrize("which", ["wrapper", "forwarder"])
def test_m4b_a_mismatched_file_refuses_before_any_student_process_and_no_launch_line(w, which):
    bad = "0" * 64
    w.write_expected(**{which: bad})
    with pytest.raises(SL.LaunchRefused) as e:
        w.launch()
    msg = str(e.value)
    real = TSS.sha256_of(TSS.WRAPPER if which == "wrapper" else TSS.FWD)
    assert f"{which}_sha256" in msg and real in msg and bad in msg     # named, with both values
    w.assert_nothing_started()                                          # no process, and the log path does not exist


# ====================================================================================== M5: the launch-line hashes
@pytest.mark.parametrize("mode,which", [("badwrapper", "wrapper_sha256"), ("badforwarder", "forwarder_sha256")])
def test_m5_a_launch_line_hash_that_differs_stops_before_the_answers_are_handed_on(w, mode, which):
    with pytest.raises(SL.LaunchStop) as e:
        w.launch(mode)
    msg = str(e.value)
    assert which in msg and "0" * 64 in msg and TSS.sha256_of(TSS.WRAPPER if mode == "badwrapper" else TSS.FWD) in msg
    assert e.value.result.verdict == NOT_FLAGGED   # the verdict ran; the hash is what stopped it


def test_m5_a_matching_launch_line_passes_and_the_hashes_are_returned(w):
    r = w.launch()
    assert r.wrapper_sha256 == TSS.sha256_of(TSS.WRAPPER) and r.forwarder_sha256 == TSS.sha256_of(TSS.FWD)


# ====================================================================================== E: exported is not passed
needs_arrow = pytest.mark.usefixtures("arrow_python")


@TSS.needs_box
@needs_arrow
def test_e_an_exported_setting_never_reaches_the_wrapper_through_a_real_student(w, arrow_python, tmp_path):
    """feed4.Student builds the student's environment from scratch: SANDBOX_* variables EXPORTED in the caller's
    environment are dropped, so the wrapper (started as `claude`) refuses, naming the first one it did not get."""
    d = tmp_path / "wd"; d.mkdir()
    shutil.copy(TSS.WRAPPER, d / "claude"); shutil.copy(TSS.FWD, d / "sandbox-forward.py")
    out = str(tmp_path / "e-out"); os.makedirs(out)
    env = dict(os.environ, **w.settings(), PATH="%s:%s" % (d, os.environ["PATH"]), BEAM_OLLAMA_URL="http://localhost:%d" % w.cfg.model_port)
    r = subprocess.run([arrow_python, "-I", str(w.driver), "--arm-home", w.cfg.slot, "--out", out], env=env,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert "SANDBOX_SLOT is not set or is empty" in open(os.path.join(out, "stderr.log")).read()


@TSS.needs_box
@needs_arrow
def test_e_the_modules_own_launch_through_the_same_real_student_reaches_the_box(w, arrow_python):
    """The companion: the same real Student, started by the module, gets the settings as `--env` pairs, passes every
    check of the real wrapper, runs the test command in the box, and the launch line is logged and verified."""
    r = SL.run_feeder(arrow_python, str(w.driver), w.argv(), sandbox=w.sandbox(exec_="true"), log_dir=str(w.logs), state_dir=str(w.state),
                      env=w.env(), test_stub=True)
    assert r.returncode == 0 and r.verdict == NOT_FLAGGED
    assert r.wrapper_sha256 == TSS.sha256_of(TSS.WRAPPER) and r.forwarder_sha256 == TSS.sha256_of(TSS.FWD)
    line = [l for l in open(r.log) if l.startswith("wrapper-launch ")]
    assert len(line) == 1 and "ro_binds=" in line[0] and str(w.tools) in line[0]


# ====================================================================================== D2: the required set
def wrapper_required_names():
    src = open(TSS.WRAPPER).read()
    m = re.search(r"^for n in ((?:SANDBOX_[A-Z0-9_]+ ?)+); do\n\s*\[ -n \"\$\{!n:-\}\" \] \|\| refuse", src, re.M)
    assert m, "the S1 loop of student-sandbox.sh has a new shape: update this derivation"
    names = set(m.group(1).split())
    # the one conditional requirement: SANDBOX_MODEL_ALLOW unless SANDBOX_MODEL_LEARN=1
    assert 'refuse "SANDBOX_MODEL_ALLOW is not set or is empty"' in src
    return names | {"SANDBOX_MODEL_ALLOW"}


def test_d2_the_modules_required_set_equals_the_set_the_wrapper_refuses_without():
    assert set(SL.REQUIRED_SANDBOX) == wrapper_required_names()
    assert len(set(SL.REQUIRED_SANDBOX)) == len(SL.REQUIRED_SANDBOX)


# ====================================================================================== D1: no second door
def _is_shell(path):
    if path.endswith(".sh"):
        return True
    try:
        first = open(path, errors="replace").readline()
    except OSError:
        return False
    return first.startswith("#!") and re.search(r"\b(ba|z|da)?sh\b", first) is not None


FEEDER_RE = r"feed[0-9]?\.py"
SH_FEEDER = re.compile(r"(\$\{?\w+\}?|\"\$\{?\w+\}?\"|python3?)\s+(-\S+\s+)*\S*" + FEEDER_RE)
SH_CLAUDE = re.compile(r"(^|[;&|(]|\bthen\b|\bdo\b|\btimeout\s+\S+|\bexec\b|\benv\s+(\S+=\S*\s+)*)\s*claude(\s|$)")
PY_CALLS = {"run", "Popen", "call", "check_call", "check_output", "system", "popen", "execv", "execve", "execvp", "execvpe",
            "execl", "execle", "execlp", "execlpe", "spawnv", "spawnl", "spawnvp", "spawnlp"}


def _strings(node):
    for n in ast.walk(node):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            yield n.value


def _py_sites(path, feeders):
    tree = ast.parse(open(path, encoding="utf-8").read())
    sites = []
    fre = re.compile(r"(^|[/\s])(%s)(\s|$)" % "|".join(re.escape(f) for f in feeders))
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            f = n.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
            if name in PY_CALLS:
                for s in _strings(ast.Module(body=[ast.Expr(a) for a in list(n.args) + [k.value for k in n.keywords]], type_ignores=[])):
                    if fre.search(s) or s == "claude" or re.match(r"\s*claude\s", s):
                        sites.append((n.lineno, "process call naming %r" % s))
        if isinstance(n, (ast.Name, ast.Attribute)):
            if (n.id if isinstance(n, ast.Name) else n.attr) == "Student":
                sites.append((n.lineno, "a use of Student"))
        if isinstance(n, ast.ImportFrom) and any(a.name == "Student" for a in n.names):
            sites.append((n.lineno, "imports Student"))
    return sites


def _sh_sites(path):
    sites = []
    for i, line in enumerate(open(path, errors="replace").read().splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        if SH_FEEDER.search(line):
            sites.append((i, "shell invocation of a feeder"))
        elif SH_CLAUDE.search(line):
            sites.append((i, "shell call of claude"))
    return sites


def student_starters(tools_dir, feeders):
    """Every site in the tools tree (outside tests/) that starts a student and is neither the launch module, a feeder
    implementation, nor a file carrying the RETIRED-LAUNCHER marker within its first three lines. SEES: Python process
    calls (subprocess.*, os.system/exec*/spawn*) with a feeder name or `claude` as an argument string, any use or import
    of a feeder's Student, shell lines that run a feeder through an interpreter or call `claude` at a command position.
    DOES NOT SEE: a feeder path or the name `claude` assembled by string concatenation or read from a variable, a launcher
    in another directory or language, a call through an alias, a student started by a program the tools tree does not
    name. Those are the limits of a search, which is why the launchers are retired by marker and the module refuses a
    session that did not come through it."""
    found = []
    for name in sorted(os.listdir(tools_dir)):
        path = os.path.join(tools_dir, name)
        if not os.path.isfile(path) or name == "sandbox_launch.py" or name in feeders:
            continue
        if name.endswith(".py"):
            sites = _py_sites(path, feeders)
        elif _is_shell(path):
            sites = _sh_sites(path)
        else:
            continue
        if sites and any("RETIRED-LAUNCHER" in l for l in open(path, errors="replace").read().splitlines()[:3]):
            continue
        found += [(name, ln, why) for ln, why in sites]
    return found


def test_d1_no_second_door_in_the_tools_tree():
    assert student_starters(TOOLS, SL.FEEDERS) == []


def _copy_tools(tmp_path):
    dst = tmp_path / "tools-copy"
    shutil.copytree(TOOLS, dst, ignore=shutil.ignore_patterns("tests", "__pycache__"))
    return str(dst)


@pytest.mark.parametrize("name,text,why", [
    ("new-launcher.py", "import subprocess\nsubprocess.run(['py', '-I', 'feed4.py', '--out', 'x'])\n", "process call naming"),
    ("new-launcher2.py", "import subprocess, os\nsubprocess.Popen([os.path.join(HERE, 'feed2.py')])\n", "process call naming"),
    ("new-claude.py", "import subprocess\nsubprocess.Popen(['claude', '-p'])\n", "process call naming 'claude'"),
    ("new-student.py", "import feed4\nstudent = feed4.Student(None)\n", "Student"),
    ("new-launcher.sh", "#!/usr/bin/env bash\n$PY -I $BEAM_TOOLS/feed4.py --out x\n", "shell invocation"),
    ("new-launcher2.sh", "#!/usr/bin/env bash\n\"$PY\" -I \"$T/feed.py\" --out x\n", "shell invocation"),
    ("new-claude.sh", "#!/usr/bin/env bash\nset -u\ntimeout 60 claude -p hi\n", "shell call of claude"),
])
def test_d1_the_search_finds_a_planted_unretired_launcher(tmp_path, name, text, why):
    d = _copy_tools(tmp_path)
    assert student_starters(d, SL.FEEDERS) == [], "the copy must start clean"
    open(os.path.join(d, name), "w").write(text)
    found = student_starters(d, SL.FEEDERS)
    assert found and all(f[0] == name for f in found) and any(why in f[2] for f in found), found


def test_d1_a_planted_launcher_with_the_marker_in_its_first_three_lines_is_passed_and_the_fourth_line_is_not(tmp_path):
    d = _copy_tools(tmp_path)
    open(os.path.join(d, "x.sh"), "w").write("#!/usr/bin/env bash\n# RETIRED-LAUNCHER: x\nexit 2\n$PY -I feed4.py\n")
    assert student_starters(d, SL.FEEDERS) == []
    open(os.path.join(d, "y.sh"), "w").write("#!/usr/bin/env bash\n\n\n# RETIRED-LAUNCHER: y\n$PY -I feed4.py\n")
    assert [f[0] for f in student_starters(d, SL.FEEDERS)] == ["y.sh"]


def test_d1_a_launcher_that_uses_only_the_module_is_not_a_second_door(tmp_path):
    d = _copy_tools(tmp_path)
    open(os.path.join(d, "ok.py"), "w").write("import sandbox_launch\nsandbox_launch.run_feeder('py', 'feed4.py', [])\n")
    assert student_starters(d, SL.FEEDERS) == []


def test_d1_the_search_reads_the_feeder_list_from_the_module_not_a_hand_list(tmp_path):
    d = _copy_tools(tmp_path)
    open(os.path.join(d, "g.py"), "w").write("import subprocess\nsubprocess.run(['py', 'feed9.py'])\n")
    assert student_starters(d, SL.FEEDERS) == []
    assert [f[0] for f in student_starters(d, SL.FEEDERS + ("feed9.py",))] == ["g.py"]


# ====================================================================================== R: the retired launchers
RETIRED = ("pilot-run.sh", "run-engram-full.sh", "run-v2-both.sh", "run-e2-core.sh", "run-e1-alwaysload.sh", "vanilla-hello.sh")


@pytest.mark.parametrize("name", RETIRED)
def test_r_a_retired_launcher_carries_the_marker_and_refuses_at_once(name, tmp_path):
    path = os.path.join(TOOLS, name)
    lines = open(path).read().splitlines()
    assert lines[0].startswith("#!") and lines[1] == "# RETIRED-LAUNCHER: starts a student outside the sandbox launch module (A10)"
    assert lines[2].startswith('echo "RETIRED:') and lines[2].endswith("exit 2")
    work = tmp_path / "w"; work.mkdir()
    env = {"PATH": os.environ["PATH"], "HOME": str(work)}
    r = subprocess.run(["bash", path, "5"], cwd=work, env=env, capture_output=True, text=True, timeout=30)
    assert r.returncode == 2 and "RETIRED" in r.stderr and r.stdout == ""
    assert os.listdir(work) == []     # it created nothing


def test_r_the_marker_is_what_the_search_reads_removing_one_makes_the_search_and_that_files_cell_fail(tmp_path):
    d = _copy_tools(tmp_path)
    p = os.path.join(d, "pilot-run.sh")
    text = open(p).read().replace("# RETIRED-LAUNCHER", "# retired-launcher")
    open(p, "w").write(text)
    found = student_starters(d, SL.FEEDERS)
    assert found and {f[0] for f in found} == {"pilot-run.sh"}


# ====================================================================================================== ROUND 2
# No box or bridge outlives its session (teardown finding, 2026-11-20; design owner crossings 33620 and 33624, security
# seat 33623). W: the launch line carries the per-launch markers. T: teardown after every session. B: refuse to launch
# while anything earlier is alive. K1-K3 and Z(a): the cells. The cells that start a real box leave nothing behind (the `w`
# fixture stops any box attributed to its scratch root, and asserts nothing had to be ended).
import itertools, signal, stat, time


def launch_fields(log):
    """The key=value fields of the log's wrapper-launch line, or None."""
    if not os.path.exists(log):
        return None
    for line in open(log).read().splitlines():
        if line.startswith("wrapper-launch "):
            return dict(t.partition("=")[::2] for t in line.split()[1:] if "=" in t)
    return None


def wait_fields(log, secs=40):
    end = time.time() + secs
    while time.time() < end:
        f = launch_fields(log)
        if f and f.get("bridge_sock"):
            return f
        time.sleep(0.1)
    raise AssertionError("no wrapper-launch line in %s within %ss" % (log, secs))


def start_ticks(pid):
    """/proc/<pid>/stat field 22 (start time in clock ticks since boot), or None when the process is gone."""
    try:
        return int(open("/proc/%d/stat" % pid).read().rsplit(")", 1)[1].split()[19])
    except (OSError, IndexError, ValueError):
        return None


def argv_pids(path):
    """Pids (not this process) with `path` as one whole argv element: an independent scan of /proc, not the module's."""
    out = []
    for d in os.listdir("/proc"):
        if d.isdigit() and int(d) != os.getpid():
            try:
                if path.encode() in open("/proc/%s/cmdline" % d, "rb").read().split(b"\0"):
                    out.append(int(d))
            except OSError:
                pass
    return out


def scope_of(unit):
    """systemctl takes a bare name as a .service; the wrapper's units are scopes."""
    return unit if unit.endswith(".scope") else unit + ".scope"


def unit_state(unit):
    return TSS._systemctl("is-active", scope_of(unit)).stdout.strip()


def records_in(state):
    return [json.load(open(p)) for p in sorted(state.glob("*.json"))]


def real_caller(w, arrow_python, exec_, detach=False):
    """A SEPARATE process that runs the module with the real feed4.Student over the real wrapper (test mode, the box runs
    `exec_`), so a test can SIGKILL the caller."""
    script = w.d / "caller.py"
    script.write_text('import importlib.util, json, os, sys\n'
                      'spec = importlib.util.spec_from_file_location("sandbox_launch", sys.argv[1])\n'
                      'SL = importlib.util.module_from_spec(spec); spec.loader.exec_module(SL)\n'
                      'c = json.load(open(sys.argv[2]))\n'
                      'SL.run_feeder(c["py"], c["feeder"], c["argv"], sandbox=SL.Sandbox(c["settings"], c["expected"]),\n'
                      '              log_dir=c["log_dir"], state_dir=c["state_dir"], env=c["env"], test_stub=True)\n')
    cj = w.d / "caller.json"
    cj.write_text(json.dumps({"py": arrow_python, "feeder": str(w.driver), "argv": w.argv(), "settings": w.settings(exec_=exec_),
                              "expected": str(w.expected), "log_dir": str(w.logs), "state_dir": str(w.state),
                              "env": w.env(**({"DRIVER_DETACH": "1"} if detach else {}))}))
    return subprocess.Popen([sys.executable, str(script), MOD, str(cj)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def real_launch(w, arrow_python, exec_, detach=False):
    return SL.run_feeder(arrow_python, str(w.driver), w.argv(), sandbox=w.sandbox(exec_=exec_), log_dir=str(w.logs),
                         state_dir=str(w.state), env=w.env(**({"DRIVER_DETACH": "1"} if detach else {})), test_stub=True)


# ---------------------------------------------------------------------------------------------------- W: the launch line
@TSS.needs_box
def test_w_the_launch_line_carries_the_forwarders_real_pid_start_time_and_socket_path(w):
    log = str(w.d / "w.log")
    p = subprocess.Popen(["/bin/bash", TSS.WRAPPER], env=w.cfg.env(exec_="sleep 30", SANDBOX_LOG=log),
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        f = wait_fields(log)
        pid, sock = int(f["forwarder_pid"]), f["bridge_sock"]
        argv = open("/proc/%d/cmdline" % pid, "rb").read().split(b"\0")
        assert b"outer" in argv and argv[argv.index(b"--sock") + 1] == sock.encode(), argv   # THE forwarder, and its socket
        assert start_ticks(pid) == int(f["forwarder_start"])
        assert stat.S_ISSOCK(os.stat(sock).st_mode) and sock.startswith(w.cfg.tmpd)
        assert f["scope_unit"].startswith("student-sandbox-")
    finally:
        TSS._systemctl("stop", scope_of(launch_fields(log)["scope_unit"])) if launch_fields(log) else None
        p.wait(timeout=60)


@TSS.needs_box
def test_w_the_socket_path_is_unique_per_launch(w):
    socks = []
    for i in range(2):
        log = str(w.d / ("w%d.log" % i))
        r = w.cfg.run(exec_="true", SANDBOX_LOG=log)
        assert r.returncode == 0, r.stderr
        socks.append(launch_fields(log)["bridge_sock"])
    assert socks[0] != socks[1]


# ---------------------------------------------------------------------------------------------------- T and K
@TSS.needs_box
@needs_arrow
def test_k2_after_a_normal_session_the_scope_cgroup_is_empty_and_the_forwarder_gone(w, arrow_python):
    r = real_launch(w, arrow_python, "true")
    f = launch_fields(r.log)
    assert unit_state(f["scope_unit"]) != "active" and TSS.scope_procs(f["scope_unit"]) == []
    pid, start = int(f["forwarder_pid"]), int(f["forwarder_start"])
    assert start_ticks(pid) != start          # gone, or a different process
    assert argv_pids(f["bridge_sock"]) == []
    (rec,) = records_in(w.state)
    assert rec["state"] == "done"


@TSS.needs_box
@needs_arrow
def test_k2_a_session_whose_feeder_returned_while_the_box_still_runs_is_torn_down(w, arrow_python):
    """The feeder goes away at once; its student (`sleep`) does not. The module's stop is what ends it."""
    r = real_launch(w, arrow_python, "sleep 120", detach=True)
    assert r.returncode == 0
    f = launch_fields(r.log)
    assert unit_state(f["scope_unit"]) != "active" and TSS.scope_procs(f["scope_unit"]) == []
    assert start_ticks(int(f["forwarder_pid"])) != int(f["forwarder_start"])
    assert argv_pids(f["bridge_sock"]) == []


@TSS.needs_box
@needs_arrow
def test_k1_a_killed_caller_leaves_a_session_the_next_launch_refuses_naming_it_until_it_is_stopped(w, arrow_python):
    caller = real_caller(w, arrow_python, "sleep 120")
    try:
        log = None
        end = time.time() + 40
        while log is None and time.time() < end:
            logs = [p for p in w.logs.glob("*.log") if launch_fields(str(p))]
            log = str(logs[0]) if logs else None
            time.sleep(0.1)
        assert log, "the session never launched"
        f = wait_fields(log)
        caller.kill(); caller.wait(timeout=30)           # the caller's SIGKILL: no teardown of its own can run
        unit = f["scope_unit"]
        assert unit_state(unit) == "active", "the premise: the box outlived its killed caller"
        with pytest.raises(SL.LaunchRefused) as e:
            w.launch()                                     # the NEXT launch
        assert unit in str(e.value) and "systemctl --user stop" in str(e.value)
        assert w.records() == []                           # nothing was started
        assert TSS._systemctl("stop", scope_of(unit)).returncode == 0
        assert w.launch().returncode == 0                  # after the stop it launches
    finally:
        if caller.poll() is None:
            caller.kill()


def test_k3_a_survivor_outside_the_scope_that_carries_the_bridge_socket_is_found_and_named(w):
    """Z(a): a process started OUTSIDE any unit whose argv carries this launch's bridge_sock path. The after-check names it;
    until it is gone the next launch refuses naming it too."""
    planted = None
    try:
        with pytest.raises(SL.LaunchStop) as e:
            w.launch("plant")
        planted = [r["planted"] for r in w.records() if "planted" in r][0]
        log = str(next(w.logs.glob("*.log")))
        sock = launch_fields(log)["bridge_sock"]
        assert str(planted) in str(e.value) and sock in str(e.value) and "bridge_sock" in str(e.value)
        assert [r["state"] for r in records_in(w.state)] == ["open"]       # not marked done
        with pytest.raises(SL.LaunchRefused, match=str(planted)):
            w.launch()                                                      # B names the same survivor
    finally:
        if planted:
            try:
                os.kill(planted, signal.SIGKILL)
            except OSError:
                pass
    deadline = time.time() + 5
    while start_ticks(planted) is not None and time.time() < deadline:
        time.sleep(0.05)
    assert w.launch().returncode == 0
    assert all(r["state"] == "done" for r in records_in(w.state))


def _helper():
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])


def test_t_a_pid_that_is_a_different_process_is_not_the_forwarder_and_is_left_alone(w):
    """PID REUSE: the launch line names a live pid, but its start time is not the recorded one."""
    h = _helper()
    try:
        r = w.launch("reuse-diff", env={"HELPER_PID": str(h.pid)})
        assert r.returncode == 0 and h.poll() is None, "an unrelated process was ended"
    finally:
        h.kill(); h.wait()


def test_t_the_forwarder_that_is_still_the_same_process_is_terminated(w):
    h = _helper()
    try:
        r = w.launch("reuse-same", env={"HELPER_PID": str(h.pid)})
        assert r.returncode == 0
        assert h.wait(timeout=10) is not None           # it was terminated by the module
    finally:
        if h.poll() is None:
            h.kill(); h.wait()


def test_t_a_launch_line_that_lacks_a_marker_is_a_named_stop(w):
    with pytest.raises(SL.LaunchStop, match="forwarder_start"):
        w.launch("nomarker")


def test_t_runs_in_a_finally_a_feeder_that_raised_is_still_torn_down_and_the_record_closed(w):
    with pytest.raises(FileNotFoundError):
        SL.run_feeder("/nonexistent-python", str(w.stub), w.argv(), sandbox=w.sandbox(), log_dir=str(w.logs),
                      state_dir=str(w.state), env=w.env(), test_stub=True)
    (rec,) = records_in(w.state)
    assert rec["state"] == "done" and "no launch line" in rec["note"]


def test_t_a_session_with_no_launch_line_has_nothing_to_stop_and_is_told_apart_by_the_missing_line(w):
    with pytest.raises(SL.LaunchStop, match="log-verdict refused"):
        w.launch("nolaunch")
    (rec,) = records_in(w.state)
    assert rec["state"] == "done" and "no launch line" in rec["note"]


def test_t_a_normal_session_closes_its_record_with_the_launch_fields(w):
    w.launch()
    (rec,) = records_in(w.state)
    assert rec["state"] == "done" and rec["scope_unit"].startswith("student-sandbox-") and rec["forwarder_start"]


# ---------------------------------------------------------------------------------------------------- B: the before-launch refusal
def test_b_a_state_directory_is_required_for_a_student_session(w):
    with pytest.raises(SL.LaunchRefused, match="state directory"):
        w.launch(state_dir=None)
    w.assert_nothing_started()


def _open_record(w, f_pid, f_start, name="launch-earlier"):
    log = w.d / (name + ".log")
    sock = str(w.d / (name + ".sock"))
    log.write_text("wrapper-launch time=1 pid=2 wrapper_sha256=%s forwarder_sha256=%s scope_unit=student-sandbox-none-1 "
                   "forwarder_pid=%d forwarder_start=%d bridge_sock=%s model=h:1\n" % ("a" * 64, "b" * 64, f_pid, f_start, sock))
    w.state.mkdir(exist_ok=True)
    (w.state / (name + ".json")).write_text(json.dumps({"log": str(log), "state": "open"}))


def test_b_an_earlier_launch_whose_forwarder_is_still_alive_refuses_the_next_naming_the_pid(w):
    h = _helper()
    try:
        _open_record(w, h.pid, start_ticks(h.pid))
        with pytest.raises(SL.LaunchRefused) as e:
            w.launch()
        assert str(h.pid) in str(e.value) and "forwarder" in str(e.value)
        w.assert_nothing_started()
    finally:
        h.kill(); h.wait()
    assert w.launch().returncode == 0
    assert all(r["state"] == "done" for r in records_in(w.state))


def test_b_an_earlier_launch_whose_pid_was_reused_by_another_process_does_not_refuse(w):
    h = _helper()
    try:
        _open_record(w, h.pid, start_ticks(h.pid) + 1)
        assert w.launch().returncode == 0
    finally:
        h.kill(); h.wait()


def test_b_an_open_record_whose_session_never_wrote_a_launch_line_is_closed_and_does_not_refuse(w):
    w.state.mkdir()
    (w.state / "launch-x.json").write_text(json.dumps({"log": str(w.d / "never-written.log"), "state": "open"}))
    assert w.launch().returncode == 0
    assert [r["state"] for r in records_in(w.state)] == ["done", "done"]


@TSS.needs_box
def test_b_an_active_scope_unit_with_the_wrappers_prefix_refuses_the_next_launch_naming_it(w):
    unit = "student-sandbox-btest-%s" % os.urandom(4).hex()
    p = subprocess.Popen(["systemd-run", "--user", "--scope", "--quiet", "--unit", unit, "--", "sleep", "120"],
                         env=dict(os.environ, XDG_RUNTIME_DIR=os.environ.get("XDG_RUNTIME_DIR") or "/run/user/%d" % os.getuid()))
    try:
        end = time.time() + 20
        while unit_state(unit) != "active" and time.time() < end:
            time.sleep(0.1)
        assert unit_state(unit) == "active"
        with pytest.raises(SL.LaunchRefused) as e:
            w.launch()
        assert unit in str(e.value) and "systemctl --user stop %s" % scope_of(unit) in str(e.value)
        w.assert_nothing_started()
    finally:
        TSS._systemctl("stop", scope_of(unit))
        p.wait(timeout=60)
    assert w.launch().returncode == 0


# ---------------------------------------------------------------------------------------------------- small folds
def test_fresh_log_is_bounded_and_then_a_named_refusal(w, monkeypatch):
    monkeypatch.setattr(SL, "_SEQ", itertools.repeat(1))
    monkeypatch.setattr(SL.secrets, "token_hex", lambda n: "aa")
    (w.logs / "sandbox-1-aa.log").write_text("")
    with pytest.raises(SL.LaunchRefused, match="fresh"):
        SL._fresh_log(str(w.logs))


def test_the_vanilla_hello_retired_line_names_the_module_not_p1_session():
    line = open(os.path.join(TOOLS, "vanilla-hello.sh")).read().splitlines()[2]
    assert "sandbox_launch.py" in line and "p1-session.py" not in line
