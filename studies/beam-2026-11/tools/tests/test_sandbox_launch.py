"""Cells for tools/sandbox_launch.py (the one door through which a student session starts) and for the retired practice
launchers. Contract-first: the cells state the contract of the spec (design A10 and the design owner's rulings on it);
synthetic fixtures only, no real data, no student model, no Ollama, no host path.

Two kinds of cell. Most use a STUB FEEDER that stands in for feed4.py: it records what the module handed it (argv, PATH,
the `--env` pairs) and writes the log lines the real wrapper would (a launch line carrying the sha256 of the `claude` and
sandbox-forward.py that sit first on its PATH, so the module's own comparison is real). The cells marked `needs_box` run
the REAL wrapper (SANDBOX_TEST=1, a stub pinned binary) through the REAL feed4.Student, on a host that has bwrap.
"""
import ast, hashlib, importlib.util, json, os, re, shutil, subprocess, sys
import pytest
from conftest import TOOLS, install_stub_systemctl, needs_linux_wrapper
import test_student_sandbox as TSS

MOD = os.path.join(TOOLS, "sandbox_launch.py")
_spec = importlib.util.spec_from_file_location("sandbox_launch_under_test", MOD)
SL = importlib.util.module_from_spec(_spec)
if os.path.exists(MOD):  # before the module exists the cells fail on the missing file, not on the import
    _spec.loader.exec_module(SL)

def mk_sandbox(settings, expected, **kw):
    """The cells are TEST runs: they say so explicitly (allow_test=True). A real run's Sandbox is built without it."""
    return SL.Sandbox(settings, expected, allow_test=True, **kw)


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
prefix = pairs.get("SANDBOX_TEST_UNIT_PREFIX", "student-sandbox-")
unit = os.environ.get("STUB_UNIT") or f"{prefix}{me}-{me:x}"
if mode == "zerostart":              # the wrapper writes forwarder_start=0 when the forwarder died before its start time was read
    fstart = "0"
if os.environ.get("STUB_REALSCOPE"):  # a REAL transient scope with a process in it, which only the module's stop can end
    import subprocess, time
    env2 = dict(os.environ, XDG_RUNTIME_DIR=os.environ.get("XDG_RUNTIME_DIR") or "/run/user/%d" % os.getuid())
    subprocess.Popen(["systemd-run", "--user", "--scope", "--quiet", "--unit", unit, "--", "sleep", "120"], env=env2,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    for _ in range(200):
        r = subprocess.run(["systemctl", "--user", "is-active", unit + ".scope"], env=env2, capture_output=True, text=True)
        if r.stdout.strip() == "active":
            break
        time.sleep(0.1)
line = (f"wrapper-launch time=1 pid=2 wrapper_sha256={W} forwarder_sha256={F} scope_unit={unit} "
        f"forwarder_pid={fpid} forwarder_start={fstart} bridge_sock={sock} model=h:1 "
        f"test_mode={1 if mode == 'testline' or pairs.get('SANDBOX_TEST') == '1' else 0} test_exec={1 if mode == 'testline' else 0} "
        f"cap_tmp=2147483648 cap_tasks=1024 cap_memory=4294967296")
if mode == "nomarker":
    line = line.replace(f"forwarder_start={fstart} ", "")
if mode == "nounit":
    line = line.replace(f"scope_unit={unit} ", "")
CF = "fwd-fault method=POST path=/x status=502 bytes_read=0 kind=upstream reason=connect-failed detail=refused"
body = {"ok": [line, "fwd-first-request"], "unreachable": [line, CF], "nolaunch": [], "nowrapper": ["fwd-first-request"], "two": [line, line, "fwd-first-request"],
        "badwrapper": [line, "fwd-first-request"], "badforwarder": [line, "fwd-first-request"],
        "plant": [line, "fwd-first-request"], "nomarker": [line, "fwd-first-request"],
        "zerostart": [line, "fwd-first-request"], "testline": [line, "fwd-first-request"], "rostate": [line, "fwd-first-request"], "nounit": [line, "fwd-first-request"], "reuse-same": [line, "fwd-first-request"], "reuse-diff": [line, "fwd-first-request"]}[mode]
if log and mode != "nolaunch":
    with open(log, "a") as f:
        f.write("".join(l + "\n" for l in body))
if mode == "rostate":   # the state directory becomes unwritable mid-run: the module's record write at teardown fails
    os.chmod(os.environ["STATE_DIR"], 0o500)
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
        return mk_sandbox(self.settings(**over), str(self.expected))

    def out(self):
        self.n += 1
        return str(self.d / f"out{self.n}")

    def env(self, **over):
        e = dict(os.environ, REC=str(self.rec), STATE_DIR=str(self.state),
                 BEAM_OLLAMA_URL="http://localhost:%d" % self.cfg.model_port)
        e.update(over)
        return e

    def argv(self, out=None, extra=()):
        return ["--arm-home", self.cfg.slot, "--out", out or self.out(), *extra]

    def launch(self, mode="ok", *, feeder=None, argv=None, sandbox=None, rc=0, env=None, **kw):
        kw.setdefault("log_dir", str(self.logs))
        kw.setdefault("state_dir", str(self.state))
        kw.setdefault("stub_as", "feed2.py")    # the module cells' stub stands in for feed2 (its option set is the broader one)
        e = self.env(STUB_MODE=mode, STUB_RC=str(rc), **(env or {}))
        return SL.run_feeder(sys.executable, str(feeder or self.stub), argv if argv is not None else self.argv(),
                             sandbox=sandbox if sandbox is not None else self.sandbox(), env=e, test_stub=True, **kw)

    def records(self):
        return [json.loads(l) for l in self.rec.read_text().splitlines()] if self.rec.exists() else []

    def assert_nothing_started(self):
        assert not self.rec.exists(), "a feeder process was started"
        assert os.listdir(self.logs) == [], "a log was created"


@pytest.fixture
def w(tmp_path, monkeypatch):
    """The module stops and checks the launch's scope through `systemctl --user`. On a host with no systemctl (a Mac) the pure
    cells still run, against a stub systemctl that answers as an empty user manager; only the cells that need a REAL user
    manager (real scopes and boxes) are marked `needs_box` and skip there."""
    if shutil.which("systemctl") is None:
        stub = install_stub_systemctl(tmp_path / "stub-systemctl-bin")
        monkeypatch.setenv("PATH", stub + os.pathsep + os.environ.get("PATH", ""))
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
        mk_sandbox(s, str(w.expected))
    w.assert_nothing_started()


def test_m3_learn_mode_does_not_need_the_allow_list_but_still_needs_the_rest(w):
    s = w.settings(SANDBOX_MODEL_LEARN="1"); s.pop("SANDBOX_MODEL_ALLOW")
    mk_sandbox(s, str(w.expected))
    s.pop("SANDBOX_PROTECT")
    with pytest.raises(SL.LaunchRefused, match="SANDBOX_PROTECT"):
        mk_sandbox(s, str(w.expected))


def test_m3_the_module_owns_the_log_and_the_binds(w):
    for n in SL.MODULE_OWNED:
        with pytest.raises(SL.LaunchRefused, match=n):
            mk_sandbox(w.settings(**{n: "/x"}), str(w.expected))
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


@needs_linux_wrapper
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
@needs_linux_wrapper
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
@needs_linux_wrapper
def test_m2_the_wrapper_directory_holds_a_copy_of_the_wrapper_and_the_forwarder_first_on_the_path(w):
    r = w.launch()
    (rec,) = w.records()
    assert rec["path"].split(":")[0] == rec["path0"] and rec["path"].endswith(os.environ["PATH"])
    assert rec["claude_is_link"] is False                          # a copy, not a symlink (the wrapper looks beside itself)
    assert rec["claude_sha"] == TSS.sha256_of(TSS.WRAPPER) and rec["fwd_sha"] == TSS.sha256_of(TSS.FWD)
    assert r.returncode == 0 and not os.path.exists(rec["path0"]), "the wrapper directory is removed after the launch"


@needs_linux_wrapper
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
@needs_linux_wrapper
def test_m4a_every_launch_gets_a_fresh_log_that_did_not_exist(w):
    r1, r2 = w.launch(), w.launch()
    assert r1.log != r2.log and os.path.exists(r1.log) and os.path.exists(r2.log)
    assert [x["log_existed"] for x in w.records()] == [False, False]
    assert sorted(os.listdir(w.logs)) == sorted(os.path.basename(x) for x in (r1.log, r2.log))


@needs_linux_wrapper
def test_m4b_log_verdict_runs_after_every_session_both_arms_setup_included(w):
    """A setup session is just another student session through the module: three sessions, three verdicts."""
    results = [w.launch(), w.launch(argv=w.argv(extra=("--first-session", "--setup-only"))), w.launch("unreachable")]
    assert [r.verdict for r in results] == [NOT_FLAGGED, NOT_FLAGGED, FLAGGED]
    assert len({r.log for r in results}) == 3


@needs_linux_wrapper
def test_m4c_a_log_verdict_refusal_stops_with_its_text_and_is_never_not_flagged(w):
    with pytest.raises(SL.LaunchStop, match="log-verdict refused .*cannot read the log") as e:
        w.launch("nolaunch")                  # the log is missing: the refusal's own text is carried
    assert e.value.result.verdict is None and e.value.result.returncode == 0
    with pytest.raises(SL.LaunchStop, match="expected exactly one line starting 'wrapper-launch ', found 0"):
        w.launch("nowrapper")                 # a log the forwarder wrote alone: no launch line
    with pytest.raises(SL.LaunchStop, match="found 2"):
        w.launch("two")                       # a log merged from two launches is refused too


@needs_linux_wrapper
def test_m4c_flagged_is_a_verdict_not_a_stop(w):
    r = w.launch("unreachable")
    assert r.verdict == FLAGGED


@needs_linux_wrapper
def test_m4d_the_verdict_line_is_copied_verbatim(w):
    assert w.launch().verdict == "not-flagged"
    assert w.launch("unreachable").verdict == "flagged: endpoint unreachable, nothing reached it"


@needs_linux_wrapper
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
@needs_linux_wrapper
def test_m5_a_launch_line_hash_that_differs_stops_before_the_answers_are_handed_on(w, mode, which):
    with pytest.raises(SL.LaunchStop) as e:
        w.launch(mode)
    msg = str(e.value)
    assert which in msg and "0" * 64 in msg and TSS.sha256_of(TSS.WRAPPER if mode == "badwrapper" else TSS.FWD) in msg
    assert e.value.result.verdict == NOT_FLAGGED   # the verdict ran; the hash is what stopped it


@needs_linux_wrapper
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


# ====================================================================================== D1: no second door (F2: classify)
# An allow-list that fails closed, not a search for invocation patterns: every file in the tools tree (any extension, any
# shebang, outside tests/) whose text mentions a feeder (feed, feed2, feed4) or the word `claude` must be exactly one of: the
# module; a feeder in FEEDERS; a file carrying the RETIRED-LAUNCHER marker in its first three lines; or a file listed in the
# module's NON_LAUNCHERS dict with its one-line reason. A new or changed file that mentions them and is in none of these fails,
# naming the file. A "consumer:" entry (a file that starts students only through the module) must also really call
# run_feeder( and name sandbox_launch: the OLD p1-session.py, which started feed4 directly, does neither.
# What this cannot see: a feeder or `claude` name assembled at run time (string concatenation, read from a variable, an
# environment value), a file outside this directory, and a launcher that lives in a file already listed (the list is the gate:
# a reviewer reads every line added to NON_LAUNCHERS).
MENTION = re.compile(r"\bfeed(?:2|4)?\b|\bclaude\b")


class ToolsTreeUnavailable(Exception):
    """The population of the gate (the tracked files of the tools tree) could not be read: a named refusal, never an empty list."""


def tracked_tools_files(tools_dir):
    """The population of the gate: the files TRACKED by git under `tools_dir` (`git ls-files`), outside the top-level tests/ and
    any __pycache__. Tracked files are exactly what the gate means; a working-tree walk also sees what tools leave behind
    (pytest writes .pytest_cache/ into this directory, holding node ids that contain `claude`), which made the gate green on a
    fresh checkout and red on every later run. FAILS CLOSED: git missing, `tools_dir` not in a git checkout, or no tracked file
    is a named ToolsTreeUnavailable, never a silently empty population."""
    try:
        r = subprocess.run(["git", "-C", tools_dir, "ls-files", "-z", "--", "."], capture_output=True)
    except OSError as e:
        raise ToolsTreeUnavailable(f"git cannot be run ({type(e).__name__}), so the tracked files of {tools_dir} are unknown")
    if r.returncode != 0:
        raise ToolsTreeUnavailable(f"`git ls-files` failed in {tools_dir} (exit {r.returncode}: {r.stderr.decode('utf-8', 'replace').strip()}): "
                                   "not a git checkout, so the tracked files are unknown")
    files = [f for f in r.stdout.decode("utf-8").split("\0") if f]
    files = [f for f in files if f.split("/")[0] != "tests" and "__pycache__" not in f.split("/")]
    if not files:
        raise ToolsTreeUnavailable(f"`git ls-files` lists no file under {tools_dir} outside tests/: an empty population is not a pass")
    return files


def tools_tree_violations(tools_dir, feeders, non_launchers, files=None):
    """[(relative file, why)] for every file of the population that mentions a feeder or `claude` and is in no category. The
    population is `files` (relative paths) or, by default, the tracked files of `tools_dir` (tracked_tools_files). A scratch tree
    built outside git (the cells that restore or plant a file) supplies its own list: see scratch_violations."""
    out = []
    for rel in sorted(tracked_tools_files(tools_dir) if files is None else files):
        path = os.path.join(tools_dir, rel)
        try:
            text = open(path, "rb").read().decode("utf-8", "replace")
        except OSError as e:   # `git ls-files` lists the INDEX: a tracked file gone or unreadable on disk cannot be judged
            out.append((rel, f"in the population (tracked) but cannot be judged: {type(e).__name__} reading it"))
            continue
        if not MENTION.search(text):
            continue
        if rel == "sandbox_launch.py" or rel in feeders:
            continue
        if any("RETIRED-LAUNCHER" in l for l in text.splitlines()[:3]):
            continue
        if rel in non_launchers:
            if non_launchers[rel].startswith("consumer:") and not ("run_feeder(" in text and "sandbox_launch" in text):
                out.append((rel, "listed as a consumer of the launch module but does not call run_feeder( through it"))
            continue
        out.append((rel, "mentions a feeder or `claude` and is the module, a feeder, retired, or listed in NON_LAUNCHERS: none"))
    return out


def scratch_violations(d, feeders, non_launchers):
    """The gate on a SCRATCH tree (outside git): its population is every file in the scratch directory, which _copy_tools filled
    from the tracked list only, plus whatever the cell restored or planted."""
    files = [os.path.relpath(os.path.join(r, f), d) for r, _, fs in os.walk(d) for f in fs]
    return tools_tree_violations(d, feeders, non_launchers, files=files)


def test_d1_every_file_that_mentions_a_feeder_or_claude_is_classified():
    assert tools_tree_violations(TOOLS, SL.FEEDERS, SL.NON_LAUNCHERS) == []


def test_d1_non_launchers_has_no_stale_entry_and_every_entry_has_a_reason():
    for rel, reason in SL.NON_LAUNCHERS.items():
        path = os.path.join(TOOLS, rel)
        assert os.path.isfile(path), f"{rel} is listed in NON_LAUNCHERS but does not exist"
        assert MENTION.search(open(path, "rb").read().decode("utf-8", "replace")), f"{rel} no longer mentions a feeder or claude: drop it"
        assert isinstance(reason, str) and len(reason.split()) >= 3 and "\n" not in reason, rel
        assert rel not in SL.FEEDERS and "RETIRED-LAUNCHER" not in "".join(open(path).read().splitlines()[:3]), rel


def _copy_tools(tmp_path):
    """A scratch copy of the TRACKED files of the tools tree (never the working tree's leftovers)."""
    dst = tmp_path / "tools-copy"
    for rel in tracked_tools_files(TOOLS):
        os.makedirs(os.path.dirname(dst / rel), exist_ok=True)
        shutil.copyfile(os.path.join(TOOLS, rel), dst / rel)
        shutil.copymode(os.path.join(TOOLS, rel), dst / rel)
    return str(dst)


def _scratch_git_tools(tmp_path):
    """A scratch copy of the tracked files that IS a git checkout (index only, no commit), for the cells about the population."""
    d = _copy_tools(tmp_path)
    subprocess.run(["git", "init", "-q", d], check=True)
    subprocess.run(["git", "-C", d, "add", "-A"], check=True)
    return d


# the launcher this PR replaced: p1-session.py as it was at f1cefc32, which started feed4 through a variable-held path
OLD_P1_SESSION_EXTRACT = '''
import os, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
def work(py, a, c, rundir):
    feed4 = os.environ.get("P1_FEED4") or os.path.join(HERE, "feed4.py")
    frc = subprocess.run([py, "-I", feed4, *feed4_args(a, c, os.path.join(rundir, "run"))]).returncode
    return frc
'''


def old_p1_session():
    """The real p1-session.py at f1cefc32 when the repository's history is there, else the extract above."""
    r = subprocess.run(["git", "-C", TOOLS, "show", "f1cefc32:studies/beam-2026-11/tools/p1-session.py"], capture_output=True)
    return r.stdout.decode("utf-8") if r.returncode == 0 and r.stdout else OLD_P1_SESSION_EXTRACT


def test_d1_the_old_p1_session_restored_into_a_scratch_tree_is_flagged_by_name(tmp_path):
    """The door the old pattern search was blind to: p1-session.py as it was before this PR, in a scratch copy of the tree."""
    d = _copy_tools(tmp_path)
    assert scratch_violations(d, SL.FEEDERS, SL.NON_LAUNCHERS) == []
    open(os.path.join(d, "p1-session.py"), "w").write(old_p1_session())
    found = scratch_violations(d, SL.FEEDERS, SL.NON_LAUNCHERS)
    assert [f[0] for f in found] == ["p1-session.py"] and "run_feeder" in found[0][1], found


@pytest.mark.parametrize("name,text", [
    ("new-setsid.sh", "#!/usr/bin/env bash\nsetsid claude -p hi\n"),
    ("new-nohup.sh", "#!/usr/bin/env bash\nnohup claude -p hi &\n"),
    ("new-launcher", "#!/usr/bin/env python3\nimport feed4\nfeed4.main()\n"),                       # extensionless, python shebang
    ("new-from-import.py", "from feed4 import Student\n"),
    ("new-runpy.py", "import runpy\nrunpy.run_path('feed4.py', run_name='__main__')\n"),
    ("new-plain.sh", "#!/usr/bin/env bash\n$PY -I $BEAM_TOOLS/feed4.py --out x\n"),
    ("new-claude.py", "import subprocess\nsubprocess.Popen(['claude', '-p'])\n"),
    ("notes.txt", "run claude here\n"),                                                            # any extension
])
def test_d1_a_new_file_that_mentions_a_feeder_or_claude_and_is_in_no_category_is_flagged_by_name(tmp_path, name, text):
    d = _copy_tools(tmp_path)
    open(os.path.join(d, name), "w").write(text)
    found = scratch_violations(d, SL.FEEDERS, SL.NON_LAUNCHERS)
    assert [f[0] for f in found] == [name], found


def test_d1_the_marker_in_the_first_three_lines_classifies_and_the_fourth_line_does_not(tmp_path):
    d = _copy_tools(tmp_path)
    open(os.path.join(d, "x.sh"), "w").write("#!/usr/bin/env bash\n# RETIRED-LAUNCHER: x\nexit 2\n$PY -I feed4.py\n")
    assert scratch_violations(d, SL.FEEDERS, SL.NON_LAUNCHERS) == []
    open(os.path.join(d, "y.sh"), "w").write("#!/usr/bin/env bash\n\n\n# RETIRED-LAUNCHER: y\n$PY -I feed4.py\n")
    assert [f[0] for f in scratch_violations(d, SL.FEEDERS, SL.NON_LAUNCHERS)] == ["y.sh"]


def test_d1_a_file_that_does_not_mention_a_feeder_or_claude_needs_no_entry(tmp_path):
    d = _copy_tools(tmp_path)
    open(os.path.join(d, "other.py"), "w").write("print('hello')\n")
    assert scratch_violations(d, SL.FEEDERS, SL.NON_LAUNCHERS) == []


def test_d1_the_search_reads_the_feeder_list_from_the_module_not_a_hand_list(tmp_path):
    d = _copy_tools(tmp_path)
    open(os.path.join(d, "feed9.py"), "w").write("# a feeder-looking file\nclaude = 1\n")
    assert [f[0] for f in scratch_violations(d, SL.FEEDERS, SL.NON_LAUNCHERS)] == ["feed9.py"]
    assert scratch_violations(d, SL.FEEDERS + ("feed9.py",), SL.NON_LAUNCHERS) == []


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


def test_r_the_marker_is_what_the_classification_reads_removing_one_flags_that_file(tmp_path):
    d = _copy_tools(tmp_path)
    p = os.path.join(d, "pilot-run.sh")
    text = open(p).read()
    open(p, "w").write(text.replace("# RETIRED-LAUNCHER", "# retired-launcher"))
    assert [f[0] for f in scratch_violations(d, SL.FEEDERS, SL.NON_LAUNCHERS)] == ["pilot-run.sh"]


# ====================================================================================================== ROUND 2
# No box or bridge outlives its session (teardown finding, 2026-11-20; the design owner's and the security seat's rulings). W: the launch line carries the per-launch markers. T: teardown after every session. B: refuse to launch
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
                      'SL.run_feeder(c["py"], c["feeder"], c["argv"], sandbox=SL.Sandbox(c["settings"], c["expected"], allow_test=True),\n'
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
        assert f["scope_unit"].startswith(TSS.RUN_UNIT_PREFIX)     # named under the test-only prefix (F3)
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


@needs_linux_wrapper
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


@needs_linux_wrapper
def test_t_a_pid_that_is_a_different_process_is_not_the_forwarder_and_is_left_alone(w):
    """PID REUSE: the launch line names a live pid, but its start time is not the recorded one."""
    h = _helper()
    try:
        r = w.launch("reuse-diff", env={"HELPER_PID": str(h.pid)})
        assert r.returncode == 0 and h.poll() is None, "an unrelated process was ended"
    finally:
        h.kill(); h.wait()


@needs_linux_wrapper
def test_t_the_forwarder_that_is_still_the_same_process_is_terminated(w):
    h = _helper()
    try:
        r = w.launch("reuse-same", env={"HELPER_PID": str(h.pid)})
        assert r.returncode == 0
        assert h.wait(timeout=10) is not None           # it was terminated by the module
    finally:
        if h.poll() is None:
            h.kill(); h.wait()


@needs_linux_wrapper
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


@needs_linux_wrapper
def test_t_a_normal_session_closes_its_record_with_the_launch_fields(w):
    w.launch()
    (rec,) = records_in(w.state)
    assert rec["state"] == "done" and rec["scope_unit"].startswith(TSS.RUN_UNIT_PREFIX) and rec["forwarder_start"]


# ---------------------------------------------------------------------------------------------------- B: the before-launch refusal
def test_b_a_state_directory_is_required_for_a_student_session(w):
    with pytest.raises(SL.LaunchRefused, match="state directory"):
        w.launch(state_dir=None)
    w.assert_nothing_started()


def _open_record(w, f_pid, f_start, name="launch-earlier"):
    log = w.d / (name + ".log")
    sock = str(w.d / (name + ".sock"))
    log.write_text("wrapper-launch time=1 pid=2 wrapper_sha256=%s forwarder_sha256=%s scope_unit=%s1-aa "
                   "forwarder_pid=%d forwarder_start=%d bridge_sock=%s model=h:1\n" % ("a" * 64, "b" * 64, TSS.RUN_UNIT_PREFIX, f_pid, f_start, sock))
    w.state.mkdir(exist_ok=True)
    (w.state / (name + ".json")).write_text(json.dumps({"log": str(log), "state": "open"}))


@needs_linux_wrapper
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


@needs_linux_wrapper
def test_b_an_earlier_launch_whose_pid_was_reused_by_another_process_does_not_refuse(w):
    h = _helper()
    try:
        _open_record(w, h.pid, start_ticks(h.pid) + 1)
        assert w.launch().returncode == 0
    finally:
        h.kill(); h.wait()


@needs_linux_wrapper
def test_b_an_open_record_whose_session_never_wrote_a_launch_line_is_closed_and_does_not_refuse(w):
    w.state.mkdir()
    (w.state / "launch-x.json").write_text(json.dumps({"log": str(w.d / "never-written.log"), "state": "open"}))
    assert w.launch().returncode == 0
    assert [r["state"] for r in records_in(w.state)] == ["done", "done"]


@TSS.needs_box
def test_b_an_active_scope_unit_with_the_wrappers_prefix_refuses_the_next_launch_naming_it(w):
    unit = "%sbtest-%s" % (TSS.RUN_UNIT_PREFIX, os.urandom(4).hex())   # under this run's prefix (a real student-sandbox-* unit would break other seats' runs)
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


# ====================================================================================================== ROUND 3
# F1 teardown always stops a known scope; F3 hermetic cells (a unit prefix per test run); F4 fail closed; F6 nits.
import subprocess as _sp


def real_scope(unit):
    """A harmless transient scope (a `sleep`) named `unit`, started by the test, outside any launch."""
    env = dict(os.environ, XDG_RUNTIME_DIR=os.environ.get("XDG_RUNTIME_DIR") or "/run/user/%d" % os.getuid())
    p = _sp.Popen(["systemd-run", "--user", "--scope", "--quiet", "--unit", unit, "--", "sleep", "120"], env=env,
                  stdin=_sp.DEVNULL, stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
    end = time.time() + 20
    while unit_state(unit) != "active" and time.time() < end:
        time.sleep(0.1)
    assert unit_state(unit) == "active"
    return p


def unique_unit(prefix):
    return "%s%d-%s" % (prefix, os.getpid(), os.urandom(4).hex())


def unit_gone(unit):
    return unit_state(unit) != "active" and TSS.scope_procs(unit) == []


# ---------------------------------------------------------------------------------------------------- F1
@TSS.needs_box
def test_f1_a_forwarder_marker_of_zero_still_stops_the_scope_and_the_stop_says_check_ii_did_not_run(w):
    """The wrapper writes forwarder_start=0 if the forwarder died after binding. The scope is known (scope_unit is on the
    line): it is stopped FIRST, and the STOP says check (ii) could not run (never read as clean)."""
    unit = unique_unit(TSS.RUN_UNIT_PREFIX)
    try:
        with pytest.raises(SL.LaunchStop) as e:
            w.launch("zerostart", env={"STUB_REALSCOPE": "1", "STUB_UNIT": unit})
        assert "check (ii)" in str(e.value) and "forwarder_start" in str(e.value) and "could not run" in str(e.value)
        assert unit_gone(unit), "the scope of a launch whose forwarder marker is 0 was not stopped"
    finally:
        TSS._systemctl("stop", scope_of(unit))    # by name, the unit being this cell's own (a stub made it)


@TSS.needs_box
def test_f1_a_record_that_cannot_be_written_does_not_stop_the_scope_from_being_stopped(w):
    unit = unique_unit(TSS.RUN_UNIT_PREFIX)
    try:
        with pytest.raises(SL.LaunchStop) as e:
            w.launch("rostate", env={"STUB_REALSCOPE": "1", "STUB_UNIT": unit})
        assert "could not be written" in str(e.value) and "the scope was stopped" in str(e.value)
        assert unit_gone(unit), "the scope was not stopped when the record write failed"
    finally:
        os.chmod(w.state, 0o700)
        TSS._systemctl("stop", scope_of(unit))


@needs_linux_wrapper
def test_f1_a_launch_line_without_a_scope_unit_is_a_named_stop(w):
    with pytest.raises(SL.LaunchStop, match="no scope_unit"):
        w.launch("nounit")


# ---------------------------------------------------------------------------------------------------- F3
@TSS.needs_box
def test_f3_a_unit_under_another_prefix_does_not_affect_a_cell_under_its_own(w):
    """A harmless scope under a SECOND unique test prefix stands in for another seat's student-sandbox-* unit (a real
    student-sandbox-* unit would break other seats' runs). A launch under this run's own prefix is unaffected."""
    other = unique_unit("ssbxo%s-" % os.urandom(3).hex())
    p = real_scope(other)
    try:
        assert w.launch().returncode == 0
    finally:
        TSS._systemctl("stop", scope_of(other)); p.wait(timeout=60)


@TSS.needs_box
def test_f3_the_scan_under_a_given_prefix_refuses_on_a_unit_under_that_prefix(w):
    pre = "ssbxo%s-" % os.urandom(3).hex()
    other = unique_unit(pre)
    p = real_scope(other)
    w.state.mkdir()
    try:
        with pytest.raises(SL.LaunchRefused) as e:
            SL.check_before_launch(str(w.state), pre)
        assert other in str(e.value)
        SL.check_before_launch(str(w.state), TSS.RUN_UNIT_PREFIX)           # the run's own prefix does not see it
    finally:
        TSS._systemctl("stop", scope_of(other)); p.wait(timeout=60)


def test_f3_a_prefix_override_is_refused_outside_test_mode_and_when_malformed(w):
    with pytest.raises(SL.LaunchRefused, match="SANDBOX_TEST=1"):
        mk_sandbox(w.settings(SANDBOX_TEST=None, SANDBOX_TEST_UNIT_PREFIX="mine-"), str(w.expected))
    for bad in ("", "no-dash", "has space-", "-x-"):
        with pytest.raises(SL.LaunchRefused, match="not a prefix"):
            mk_sandbox(w.settings(SANDBOX_TEST_UNIT_PREFIX=bad), str(w.expected))
    assert mk_sandbox(w.settings(SANDBOX_TEST_UNIT_PREFIX="mine-"), str(w.expected)).prefix == "mine-"
    assert mk_sandbox(w.settings(SANDBOX_TEST=None, SANDBOX_TEST_UNIT_PREFIX=None), str(w.expected)).prefix == "student-sandbox-"


# ---------------------------------------------------------------------------------------------------- F4
def _cp(out, rc=0):
    return _sp.CompletedProcess(["systemctl"], rc, stdout=out, stderr="")


def test_f4_an_unreadable_cgroup_procs_while_the_unit_exists_is_not_clean(monkeypatch):
    monkeypatch.setattr(SL, "_systemctl", lambda *a, **k: _cp("/no-such-cgroup-for-the-test\n"))
    with pytest.raises(SL.SystemctlError, match="cgroup.procs"):
        SL.unit_pids("x-1-aa")


def test_f4_a_unit_that_vanished_between_the_two_reads_is_empty(monkeypatch):
    answers = iter(["/no-such-cgroup-for-the-test\n", "\n"])
    monkeypatch.setattr(SL, "_systemctl", lambda *a, **k: _cp(next(answers)))
    assert SL.unit_pids("x-1-aa") == []


def test_f4_the_unit_scan_includes_every_unit_under_the_prefix_that_is_not_inactive(monkeypatch):
    listing = ("p-1-aa.scope loaded active running d\np-2-bb.scope loaded deactivating stop-sigterm d\n"
               "p-3-cc.scope loaded activating start d\np-4-dd.scope loaded inactive dead d\n"
               "p-5-ee.scope loaded failed failed d\nq-9-ff.scope loaded active running other-prefix\n")
    asked = []
    monkeypatch.setattr(SL, "_systemctl", lambda *a, **k: (asked.append(a), _cp(listing))[1])
    monkeypatch.setattr(SL, "unit_pids", lambda u: [123] if u.startswith("p-5") else [])
    assert SL.active_units("p-") == ["p-1-aa.scope", "p-2-bb.scope", "p-3-cc.scope", "p-5-ee.scope"]
    assert "--all" in asked[0] and "p-*" in asked[0]            # what is queried: every scope under the prefix, any state
    monkeypatch.setattr(SL, "unit_pids", lambda u: [])
    assert "p-5-ee.scope" not in SL.active_units("p-")           # a failed unit with no processes holds nothing


@pytest.mark.parametrize("unit", ["dbus.service", "user.slice", "student-sandbox-1-aa.scope", "x-1-ZZ", "{prefix}1-aa;rm"])
@needs_linux_wrapper
def test_f4_a_scope_unit_that_is_not_a_name_this_wrapper_makes_is_a_named_stop_and_is_never_stopped(w, monkeypatch, unit):
    unit = unit.replace("{prefix}", TSS.RUN_UNIT_PREFIX)
    calls, real = [], SL._systemctl
    monkeypatch.setattr(SL, "_systemctl", lambda *a, **k: (calls.append(a), real(*a, **k))[1])
    with pytest.raises(SL.LaunchStop, match="not a unit this wrapper makes"):
        w.launch(env={"STUB_UNIT": unit})
    assert not [c for c in calls if c[0] == "stop"], calls


def test_f4_a_recorded_scope_unit_that_is_not_a_wrapper_name_is_refused_not_acted_on(w, monkeypatch):
    log = w.d / "earlier.log"
    log.write_text("wrapper-launch time=1 pid=2 scope_unit=dbus.service forwarder_pid=1 forwarder_start=1 bridge_sock=/x/y.sock\n")
    w.state.mkdir()
    (w.state / "launch-earlier.json").write_text(json.dumps({"log": str(log), "state": "open"}))
    calls, real = [], SL._systemctl
    monkeypatch.setattr(SL, "_systemctl", lambda *a, **k: (calls.append(a), real(*a, **k))[1])
    with pytest.raises(SL.LaunchRefused, match="not a unit this wrapper makes"):
        w.launch()
    assert not [c for c in calls if c[0] in ("stop", "kill")]


# ---------------------------------------------------------------------------------------------------- F6
def test_f6_a_caller_environment_with_no_path_is_a_named_refusal_not_a_keyerror(w):
    with pytest.raises(SL.LaunchRefused, match="no PATH"):
        SL.run_feeder(sys.executable, str(w.stub), w.argv(), sandbox=w.sandbox(), log_dir=str(w.logs),
                      state_dir=str(w.state), env={"HOME": str(w.d)}, test_stub=True)
    w.assert_nothing_started()


# ---------------------------------------------------------------------------------------------------- F7: default-deny argv
# argparse accepts `--opt=value` and any unambiguous prefix (`--en`, `--ou`, `--arm-hom`) for the same option, but the module's
# guards read only the exact `--flag VALUE` spelling. FEEDER_OPTIONS names what a launcher may pass; anything else is refused.
def test_f7_the_feeders_parsers_really_accept_those_spellings_so_the_class_is_real():
    for f in ("feed2.py", "feed4.py"):
        src = open(os.path.join(TOOLS, f)).read()
        assert "ap = argparse.ArgumentParser()" in src and "allow_abbrev" not in src, f    # defaults: abbreviations accepted


@pytest.mark.parametrize("feeder", sorted(SL.FEEDER_OPTIONS) if os.path.exists(MOD) else [])
def test_f7_every_option_in_feeder_options_is_declared_by_that_feeder_with_that_arity(feeder):
    """The DERIVED cell against drift in the other direction: read by text (importing feed4 needs pyarrow)."""
    src = open(os.path.join(TOOLS, feeder)).read()
    for opt, arity in SL.FEEDER_OPTIONS[feeder].items():
        lines = [l for l in src.splitlines() if 'add_argument("%s"' % opt in l]
        assert len(lines) == 1, f"{feeder} has no single add_argument({opt!r}) call"
        assert ("store_true" in lines[0]) == (arity == 0), f"{feeder} {opt}: the dict says arity {arity}, the source says otherwise"


def test_f7_feeder_options_covers_every_feeder_and_the_module_s_own_env_pairs():
    assert set(SL.FEEDER_OPTIONS) == set(SL.FEEDERS)
    for f in ("feed2.py", "feed4.py"):
        assert SL.FEEDER_OPTIONS[f]["--env"] == 1       # the module passes the SANDBOX_* settings as --env pairs


def test_f7_the_argv_p1_session_really_passes_is_accepted_unchanged():
    """p1-session.py's argv builders (the answering run, the continue-reading run, both plan dumps) pass the allow-list."""
    spec = importlib.util.spec_from_file_location("p1s_for_f7", os.path.join(TOOLS, "p1-session.py"))
    p1 = importlib.util.module_from_spec(spec); spec.loader.exec_module(p1)
    import types
    c = {"slot": "/s", "rundir": "/r"}
    answering = types.SimpleNamespace(continue_reading=False, session="id", question_file="q.json", components="c.txt")
    cont = types.SimpleNamespace(continue_reading=True, session="id", start=4, through=9, per_round=3, components="c.txt")
    full = ["--arm-home", "/s", "--out", "/o", "--conv", "9", "--start", "1", "--turns", "9", "--per-round", "3",
            "--expect-components", "c.txt"]
    for argv in (p1.feed4_args(answering, c, "/o"), p1.feed4_args(cont, c, "/o"),
                 p1.feed4_args(answering, c, "/o") + ["--dump-plan"], full + ["--dump-plan"]):
        SL.check_argv_options(argv, SL.FEEDER_OPTIONS["feed4.py"], "feed4.py")


def evil_claude(w):
    d = w.d / "evil"; d.mkdir()
    TSS.make_exe(str(d / "claude"), "#!/bin/sh\nexit 0\n")
    return str(d)


@pytest.mark.parametrize("make,token", [
    (lambda w: ("--something", "x"), "--something"),
    (lambda w: ("--env=PATH=%s:/usr/bin" % evil_claude(w),), "--env=PATH="),
    (lambda w: ("--env=ANTHROPIC_BASE_URL=http://example.org:80",), "--env=ANTHROPIC_BASE_URL"),
    (lambda w: ("--en", "PATH=%s:/usr/bin" % evil_claude(w)), "--en"),
    (lambda w: ("--e", "FOO=1"), "--e"),
    (lambda w: ("--out=%s" % (w.d / "other-out"),), "--out="),
    (lambda w: ("--ou", str(w.d / "other-out")), "--ou"),
    (lambda w: ("--arm-hom", str(w.d / "other-home")), "--arm-hom"),
    (lambda w: ("--arm-home=%s" % (w.d / "other-home"),), "--arm-home="),
    (lambda w: ("--dump",), "--dump"),
    (lambda w: ("-e", "PATH=x"), "-e"),
    (lambda w: ("--",), "--"),
    (lambda w: ("stray",), "stray"),
])
def test_f7_a_token_that_is_not_an_allowed_option_or_its_value_is_refused_naming_it(w, make, token):
    with pytest.raises(SL.LaunchRefused) as e:
        w.launch(argv=w.argv(extra=make(w)))
    assert repr(token) in str(e.value) or token in str(e.value), (token, str(e.value))
    w.assert_nothing_started()


@needs_linux_wrapper
def test_f7_a_value_that_looks_like_an_option_and_an_option_with_no_value_are_refused(w):
    with pytest.raises(SL.LaunchRefused, match="looks like an option"):
        w.launch(argv=w.argv(extra=("--env", "--env=PATH=/x")))
    with pytest.raises(SL.LaunchRefused, match="has no value"):
        w.launch(argv=w.argv() + ["--env"])
    w.assert_nothing_started()
    assert w.launch(argv=w.argv(extra=("--turns", "-1"))).returncode == 0       # a plain negative number is a value


@needs_linux_wrapper
def test_f7_the_exact_allowed_options_are_accepted(w):
    r = w.launch(argv=w.argv(extra=("--env", "CLAUDE_CODE_MAX_CONTEXT_TOKENS=131072", "--ask", "a question",
                                    "--force-compact", "--first-session")))
    assert r.returncode == 0
    (rec,) = w.records()
    assert "CLAUDE_CODE_MAX_CONTEXT_TOKENS=131072" in rec["argv"]


def test_f7_a_dump_plan_call_with_the_exact_spelling_runs_unwrapped_and_an_abbreviation_is_refused(w):
    assert SL.run_feeder(sys.executable, str(w.stub), w.argv(extra=("--dump-plan",)), env=w.env(), test_stub=True).returncode == 0
    with pytest.raises(SL.LaunchRefused, match="'--dump-p'"):
        SL.run_feeder(sys.executable, str(w.stub), w.argv(extra=("--dump-p",)), env=w.env(), test_stub=True)


def test_f7_the_test_stub_obeys_the_allow_list_of_the_feeder_it_stands_in_for(w):
    with pytest.raises(SL.LaunchRefused, match="'--first-session'"):    # a feed2 option, not a feed4 one
        SL.run_feeder(sys.executable, str(w.stub), w.argv(extra=("--first-session",)), sandbox=w.sandbox(),
                      log_dir=str(w.logs), state_dir=str(w.state), env=w.env(), test_stub=True)
    w.assert_nothing_started()


@needs_linux_wrapper
def test_f7_an_option_a_launcher_needs_that_is_not_in_the_dict_is_refused_loudly_by_design(w, monkeypatch):
    monkeypatch.setitem(SL.FEEDER_OPTIONS["feed2.py"], "--new-option", 1)
    assert w.launch(argv=w.argv(extra=("--new-option", "x"))).returncode == 0     # added to the dict: accepted


# ---------------------------------------------------------------------------------------------------- the launch line, one parser
def test_f7_both_launch_line_readers_take_the_same_first_line(w):
    log = w.d / "two.log"
    log.write_text("wrapper-launch a=1 wrapper_sha256=%s forwarder_sha256=%s scope_unit=x\n"
                   "wrapper-launch wrapper_sha256=%s forwarder_sha256=%s scope_unit=y\n" % ("1" * 64, "2" * 64, "3" * 64, "4" * 64))
    assert SL.read_launch_fields(str(log))["scope_unit"] == "x"
    assert SL.read_launch_hashes(str(log)) == {"wrapper_sha256": "1" * 64, "forwarder_sha256": "2" * 64}
    assert SL.read_launch_hashes(str(w.d / "no-such.log")) == {}


# ====================================================================================================== ROUND 4
# The gate's population is the TRACKED files (`git ls-files`), not a walk of the working tree: pytest writes .pytest_cache/ into
# the tools directory, with node ids that contain `claude`, so a walk was green on a fresh checkout and red on every later run.
def test_r4_a_pytest_cache_left_in_the_checkout_does_not_change_the_gate(tmp_path):
    d = _scratch_git_tools(tmp_path)
    before = tools_tree_violations(d, SL.FEEDERS, SL.NON_LAUNCHERS)
    assert before == []
    cache = os.path.join(d, ".pytest_cache", "v", "cache")
    os.makedirs(cache)
    open(os.path.join(cache, "nodeids"), "w").write('["tests/test_x.py::test_claude_and_feed4_launcher"]\n')
    open(os.path.join(cache, "lastfailed"), "w").write('{"tests/test_x.py::test_claude": true}\n')
    assert tools_tree_violations(d, SL.FEEDERS, SL.NON_LAUNCHERS) == before      # the second run equals the first


def test_r4_the_real_checkout_gives_the_same_answer_whatever_pytest_left_in_it():
    """Run as CI runs it, WITH pytest's cache enabled: whatever the cache holds, the gate sees the tracked files only."""
    assert ".pytest_cache" not in " ".join(tracked_tools_files(TOOLS))
    assert tools_tree_violations(TOOLS, SL.FEEDERS, SL.NON_LAUNCHERS) == []


def test_r4_an_untracked_new_launcher_is_not_in_the_population_and_a_tracked_one_is(tmp_path):
    """The README limit: the gate covers TRACKED files. An untracked file is invisible until it is added."""
    d = _scratch_git_tools(tmp_path)
    open(os.path.join(d, "new-launcher.sh"), "w").write("#!/usr/bin/env bash\nsetsid claude -p hi\n")
    assert "new-launcher.sh" not in tracked_tools_files(d) and tools_tree_violations(d, SL.FEEDERS, SL.NON_LAUNCHERS) == []
    subprocess.run(["git", "-C", d, "add", "new-launcher.sh"], check=True)
    assert [v[0] for v in tools_tree_violations(d, SL.FEEDERS, SL.NON_LAUNCHERS)] == ["new-launcher.sh"]


def test_r4_git_unavailable_or_not_a_checkout_or_empty_is_a_named_refusal_never_an_empty_list(tmp_path, monkeypatch):
    d = _scratch_git_tools(tmp_path)
    monkeypatch.setenv("PATH", "")                                   # git cannot be run
    with pytest.raises(ToolsTreeUnavailable, match="git cannot be run"):
        tracked_tools_files(d)
    with pytest.raises(ToolsTreeUnavailable):
        tools_tree_violations(d, SL.FEEDERS, SL.NON_LAUNCHERS)
    monkeypatch.undo()
    plain = tmp_path / "not-a-checkout"; plain.mkdir()
    (plain / "x.py").write_text("print(1)\n")
    with pytest.raises(ToolsTreeUnavailable, match="not a git checkout"):
        tracked_tools_files(str(plain))
    outer = tmp_path / "outer"; outer.mkdir()                        # a plain dir INSIDE some other git checkout
    subprocess.run(["git", "init", "-q", str(outer)], check=True)
    inner = outer / "inner"; inner.mkdir()
    (inner / "x.py").write_text("print(1)\n")
    subprocess.run(["git", "-C", str(outer), "add", "-A"], check=True)
    (inner / "untracked.py").write_text("print(2)\n")                # inner holds a tracked file: still fine; remove it for the empty case
    subprocess.run(["git", "-C", str(outer), "rm", "-q", "--cached", "inner/x.py"], check=True)
    with pytest.raises(ToolsTreeUnavailable, match="no file"):       # answers for the OUTER repo, which tracks nothing here: empty
        tracked_tools_files(str(inner))


def test_r4_a_tracked_file_that_is_gone_or_unreadable_on_disk_is_a_named_violation(tmp_path):
    d = _scratch_git_tools(tmp_path)
    os.unlink(os.path.join(d, "coverage.py"))                         # in the index, gone from disk
    os.chmod(os.path.join(d, "setup-id.py"), 0o000)                   # in the index, unreadable
    try:
        found = dict(tools_tree_violations(d, SL.FEEDERS, SL.NON_LAUNCHERS))
    finally:
        os.chmod(os.path.join(d, "setup-id.py"), 0o644)
    assert "cannot be judged" in found["coverage.py"] and "cannot be judged" in found["setup-id.py"], found


def test_r4_the_population_of_a_planted_copy_is_the_copys_not_the_outer_repos(tmp_path):
    """A scratch tree must never silently enumerate the outer repository: a sentinel present only in the copy is listed, and a
    file present only in the outer repo (here: removed from the copy) is not."""
    d = _copy_tools(tmp_path)
    os.unlink(os.path.join(d, "coverage.py"))                         # tracked in the OUTER repo, absent from the copy
    open(os.path.join(d, "sentinel-only-in-the-copy.txt"), "w").write("claude\n")
    subprocess.run(["git", "init", "-q", d], check=True)
    subprocess.run(["git", "-C", d, "add", "-A"], check=True)
    listed = tracked_tools_files(d)
    assert "sentinel-only-in-the-copy.txt" in listed and "coverage.py" not in listed
    assert "coverage.py" in tracked_tools_files(TOOLS)                # (the outer repo does track it)
    # and the explicit-list route used by the planted-tree cells never touches git at all
    assert tools_tree_violations(d, SL.FEEDERS, SL.NON_LAUNCHERS, files=["sentinel-only-in-the-copy.txt"])[0][0] == \
        "sentinel-only-in-the-copy.txt"


# ---------------------------------------------------------------------------------------------------- L1: a stray test mode
# A REAL run (a Sandbox built without allow_test) refuses every SANDBOX_TEST* setting before anything starts, and after every
# session reads test_mode= and test_exec= off the launch line: anything but 0 is a LaunchStop. The caps are recorded.
def real_sandbox(w, **over):
    settings = {k: v for k, v in w.settings().items() if k not in ("SANDBOX_TEST", "SANDBOX_TEST_UNIT_PREFIX")}
    settings.update(over)
    return SL.Sandbox(settings, str(w.expected))


@pytest.mark.parametrize("name,val", [("SANDBOX_TEST", "1"), ("SANDBOX_TEST_EXEC", "true"), ("SANDBOX_TEST_MAX_REQUEST", "10"),
                                      ("SANDBOX_TEST_TASKS_MAX", "5"), ("SANDBOX_TEST_ALLOW_BINARY_IN_RW", "1"),
                                      ("SANDBOX_TEST_UNIT_PREFIX", "x-")])
def test_l1_a_real_run_refuses_every_test_mode_setting_named_before_anything_starts(w, name, val):
    with pytest.raises(SL.LaunchRefused, match=name):
        real_sandbox(w, **{name: val})
    w.assert_nothing_started()


def test_l1_a_test_run_that_says_so_explicitly_may_pass_them(w):
    s = w.settings(SANDBOX_TEST_EXEC="true", SANDBOX_TEST_MAX_REQUEST="10", SANDBOX_TEST_ALLOW_BINARY_IN_RW="1")
    assert mk_sandbox(s, str(w.expected)).allow_test is True
    assert SL.Sandbox(w.settings(SANDBOX_TEST=None, SANDBOX_TEST_UNIT_PREFIX=None), str(w.expected)).allow_test is False


@needs_linux_wrapper
def test_l1_a_launch_line_with_test_mode_1_in_a_real_run_is_a_launch_stop_and_a_clean_one_passes(w, monkeypatch):
    monkeypatch.setattr(SL, "active_units", lambda prefix=None: [])     # a real run scans the real prefix host-wide: keep the cell hermetic
    with pytest.raises(SL.LaunchStop, match="test_mode=1 test_exec=1"):
        w.launch("testline", sandbox=real_sandbox(w))
    r = w.launch("ok", sandbox=real_sandbox(w))
    assert r.returncode == 0 and r.test_mode == "0" and r.test_exec == "0"


@needs_linux_wrapper
def test_l1_a_launch_line_that_lacks_the_test_flags_is_not_read_as_clean_in_a_real_run(w, monkeypatch):
    monkeypatch.setattr(SL, "active_units", lambda prefix=None: [])
    real = SL.read_launch_fields
    monkeypatch.setattr(SL, "read_launch_fields", lambda log: {k: v for k, v in (real(log) or {}).items()
                                                                if k not in ("test_mode", "test_exec")} or None)
    with pytest.raises(SL.LaunchStop, match="test_mode=None"):
        w.launch("ok", sandbox=real_sandbox(w))


@needs_linux_wrapper
def test_l1_the_caps_on_the_launch_line_are_returned_for_the_record(w):
    r = w.launch()
    assert r.caps == {"cap_memory": "4294967296", "cap_tasks": "1024", "cap_tmp": "2147483648"}


# ---------------------------------------------------------------------------------------------------- L2: the model URL pattern
@pytest.mark.parametrize("url", [
    "http://evil.com\\@127.0.0.1:%d/v1",            # Python's urlsplit: host 127.0.0.1; the WHATWG parser of a Node student: evil.com
    "http://user@127.0.0.1:%d", "http://user:pw@localhost:%d/v1", "http://127.0.0.1:%d/%%2e%%2e/x", "http://127.0.0.1:%d/v1?x=1",
    "http://127.0.0.1:%d/v1#frag", "https://127.0.0.1:%d", "HTTP://127.0.0.1:%d", "http://127.0.0.1:%d/a b", " http://127.0.0.1:%d",
    "http://127.0.0.1:%d/v1 ", "http://127.0.0.1:%d\\v1", "http://127.0.0.1.evil.com:%d", "http://localhost.evil.com:%d",
    "http://127.0.0.1:%d/a\\b",                                 # a backslash in the PATH class
    "http://127.0.0.2:%d", "http://[::2]:%d", "http://localhost\x40evil.com:%d", "http://127.0.0.1", "http://127.0.0.1:",
])
def test_l2_a_model_url_outside_the_strict_pattern_is_refused(w, url):
    url = url.replace("%%", "\0").replace("%d", str(w.cfg.model_port)).replace("\0", "%")
    with pytest.raises(SL.LaunchRefused, match="strict form"):
        SL.check_model_url(url, w.cfg.model_port)
    with pytest.raises(SL.LaunchRefused):
        w.launch(env={"BEAM_OLLAMA_URL": url})
    w.assert_nothing_started()


@pytest.mark.parametrize("url", ["http://127.0.0.1:%d", "http://127.0.0.1:%d/v1", "http://localhost:%d/", "http://[::1]:%d/a/b-c_d.e~f"])
def test_l2_a_url_in_the_strict_pattern_on_the_sandbox_port_is_accepted(w, url):
    SL.check_model_url(url % w.cfg.model_port, w.cfg.model_port)


def test_l2_the_default_url_is_accepted_on_its_own_port_and_a_wrong_port_is_refused():
    SL.check_model_url(SL.OLLAMA_DEFAULT, SL.OLLAMA_DEFAULT.rsplit(":", 1)[1])
    with pytest.raises(SL.LaunchRefused, match="not SANDBOX_MODEL_PORT"):
        SL.check_model_url(SL.OLLAMA_DEFAULT, "1234")


# ---------------------------------------------------------------------------------------------------- L3: no systemctl
def test_l3_the_stub_systemctl_answers_as_an_empty_user_manager(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", install_stub_systemctl(tmp_path / "bin"))      # only the stub is on the PATH
    assert SL.active_units("x-") == [] and SL.unit_pids("x-1-aa") == []
    assert SL._systemctl("stop", "x-1-aa.scope").returncode == 0
    assert SL._systemctl("is-active", "x-1-aa.scope").stdout.strip() == "inactive"


# ====================================================================================================== ROUND 5
# L-S2: cells for what a mutation survived in the colleague's review (each has a mutant that reddens it).
def test_s2_a_setting_that_is_not_a_sandbox_name_is_refused(w):
    s = w.settings(); s["FOO_BAR"] = "1"
    with pytest.raises(SL.LaunchRefused, match="FOO_BAR"):
        mk_sandbox(s, str(w.expected))


def test_s2_an_empty_path_entry_is_the_childs_working_directory_exactly_as_popen_resolves_it(w):
    """The rule: an EMPTY PATH entry is the child's working directory (`<arm-home>/work`), a relative entry is relative to it;
    first match in order wins. A cell runs the real Popen with the same PATH and cwd to show they agree."""
    cwd, other = w.d / "cwd", w.d / "other"
    (cwd / "rel").mkdir(parents=True); other.mkdir()
    for d in (cwd, cwd / "rel", other):
        TSS.make_exe(str(d / "claude"), "#!/bin/sh\necho %s\n" % d.name)
    for path, want in ((":" + str(other), cwd), (str(other) + ":", other), ("rel:" + str(other), cwd / "rel"),
                       (str(other) + ":" + "", other)):
        got = SL.resolve_on_path("claude", path, str(cwd))
        assert got == str(want / "claude"), (path, got)
        out = _sp.run(["claude"], env={"PATH": path}, cwd=str(cwd), capture_output=True, text=True).stdout.strip()
        assert out == want.name, (path, out)                       # what Popen really started


def test_s2_launch_markers_with_a_non_positive_pid_or_start_is_refused():
    good = {"scope_unit": "u", "forwarder_pid": "5", "forwarder_start": "7", "bridge_sock": "/s"}
    assert SL.launch_markers(good)["forwarder_pid"] == 5
    for k, v in (("forwarder_pid", "0"), ("forwarder_pid", "-3"), ("forwarder_start", "0"), ("forwarder_start", "-1")):
        with pytest.raises(SL.LaunchMarkerError, match="not a real value"):
            SL.launch_markers({**good, k: v})


def test_s2_a_missing_log_directory_is_refused_named(w):
    missing = str(w.d / "no-such-log-dir")
    with pytest.raises(SL.LaunchRefused, match="log directory"):
        SL._fresh_log(missing)
    with pytest.raises(SL.LaunchRefused, match="log directory"):
        w.launch(log_dir=missing)
    w.assert_nothing_started()


@pytest.mark.parametrize("stub_as", ["feed2.py", "feed4.py"])
def test_s2_a_real_feeder_option_that_is_not_in_the_dict_is_refused(w, stub_as):
    assert "--model" not in SL.FEEDER_OPTIONS[stub_as]
    with pytest.raises(SL.LaunchRefused, match="'--model'"):
        w.launch(argv=w.argv(extra=("--model", "some-model")), stub_as=stub_as)
    w.assert_nothing_started()
