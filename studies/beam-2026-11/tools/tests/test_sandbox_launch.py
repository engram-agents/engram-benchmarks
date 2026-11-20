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
line = f"wrapper-launch time=1 pid=2 wrapper_sha256={W} forwarder_sha256={F} model=h:1"
CF = "fwd-fault method=POST path=/x status=502 bytes_read=0 kind=upstream reason=connect-failed detail=refused"
body = {"ok": [line, "fwd-first-request"], "unreachable": [line, CF], "nolaunch": [], "nowrapper": ["fwd-first-request"], "two": [line, line, "fwd-first-request"],
        "badwrapper": [line, "fwd-first-request"], "badforwarder": [line, "fwd-first-request"]}[mode]
if log and mode != "nolaunch":
    with open(log, "a") as f:
        f.write("".join(l + "\n" for l in body))
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
    return World(tmp_path)


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
    r = SL.run_feeder(arrow_python, str(w.driver), w.argv(), sandbox=w.sandbox(exec_="true"), log_dir=str(w.logs),
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
