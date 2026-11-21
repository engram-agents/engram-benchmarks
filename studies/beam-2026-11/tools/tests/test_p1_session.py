"""p1-session.py cells. Contract-first: written before the tool. Synthetic homes and stub scripts only: no student
model, no Ollama, no real arm home, no network. BEAM_PY is this interpreter (stdlib sqlite3 is all it needs).

Test-only hooks the tool honours (they are documented in the tool's docstring and are never set by a real run):
  P1_FEED4            a stub script run in place of feed4.py (the run and the --dump-plan call)
  P1_PLANT_CONTROL    a stub script run in place of plant-control.py
  P1_UTC_STAMP        a fixed stamp for the aside path
  P1_AFTER_COPY_HOOK  a script run (BEAM_PY script SLOT) between the copy and the copy-fidelity check
  P1_TEST_RAISE       KeyboardInterrupt | SystemExit | Exception: raised once, just after the copy has been verified
Every one of them is refused (exit 2) unless P1_TEST_HOOKS=1 is also set; the cells set it through World.env."""
import hashlib, importlib.util, json, os, re, shutil, sqlite3, subprocess, sys
import pytest
from conftest import TOOLS, install_stub_systemctl, needs_linux_wrapper

TOOL = os.path.join(TOOLS, "p1-session.py")
SESSION = "11111111-2222-3333-4444-555555555555"
STAMP = "20261118T120000Z"

_spec = importlib.util.spec_from_file_location("p1_session_under_test", TOOL)
P1S = importlib.util.module_from_spec(_spec)
if os.path.exists(TOOL):  # before the tool exists the cells fail on the missing file, not on the import
    _spec.loader.exec_module(P1S)


# ------------------------------------------------------------------ synthetic homes
def make_db(path, rows=(("n1", "alpha"), ("n2", "beta"))):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    c = sqlite3.connect(path)
    c.execute("create table nodes (id text, claim text)")
    c.execute("create table counters (k integer primary key autoincrement, v text)")
    c.execute("create virtual table notes_fts using fts5(body)")
    c.executemany("insert into nodes values (?, ?)", rows)
    c.execute("insert into counters (v) values ('x')")
    c.execute("insert into notes_fts (body) values ('hello fts world')")
    c.commit(); c.close()


def make_home(path, memory=True, db=True, claude=True, venv=True):
    path = str(path)
    os.makedirs(path)
    if db:
        make_db(os.path.join(path, ".engram", "knowledge.db"))
    if venv:
        os.makedirs(os.path.join(path, ".engram", "venv", "bin"), exist_ok=True)
        os.symlink(sys.executable, os.path.join(path, ".engram", "venv", "bin", "python"))
    if claude:
        proj = os.path.join(path, ".claude", "projects", "-p")
        os.makedirs(proj)
        with open(os.path.join(proj, "session-1.jsonl"), "w") as f:
            f.write(json.dumps({"type": "user", "message": "a turn"}) + "\n")
        if memory:
            os.makedirs(os.path.join(proj, "memory", "sub"))
            for rel, text in (("MEMORY.md", "- [a](a.md)\n"), ("a.md", "note a\n"), ("sub/b.md", "note b\n")):
                with open(os.path.join(proj, "memory", rel), "w") as f:
                    f.write(text)
    os.makedirs(os.path.join(path, "work"), exist_ok=True)
    return path


def tree(p):
    """{relpath: sha256 | 'link:<target>' | 'dir'} for everything under p (links recorded, not followed); None if absent."""
    p = str(p)
    if not os.path.lexists(p):
        return None
    out = {}
    for dp, dns, fns in os.walk(p):
        for n in dns + fns:
            full = os.path.join(dp, n); rel = os.path.relpath(full, p)
            if os.path.islink(full):
                out[rel] = "link:" + os.readlink(full)
            elif os.path.isdir(full):
                out[rel] = "dir"
            else:
                out[rel] = hashlib.sha256(open(full, "rb").read()).hexdigest()
    return out


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


STUB_FEED4 = r'''
import json, os, sqlite3, sys

# What the module appends to a feeder's argv for a student session: `--env SANDBOX_*=...` pairs. The cells that pin "the
# caller's arguments" see the argv WITHOUT them (the pairs are recorded separately, in STUB_SBX_LOG, and pinned by the
# sandbox cells below).
def caller_argv(a):
    out, i = [], 0
    while i < len(a):
        if a[i] == "--env" and i + 1 < len(a) and a[i + 1].startswith("SANDBOX_"):
            i += 2
            continue
        out.append(a[i]); i += 1
    return out


def emulate_wrapper(a):
    """A stub starts no student, so it writes what the real wrapper would log: ONE launch line carrying the sha256 of the
    `claude` and sandbox-forward.py that sit first on its PATH (the files the module prepared), plus the marker. The
    module's pre-launch and post-session checks run for real on it. STUB_SANDBOX picks a variant."""
    import hashlib
    pairs = {}
    for i, x in enumerate(a):
        if x == "--env":
            k, _, v = a[i + 1].partition("="); pairs[k] = v
    if os.environ.get("STUB_SBX_LOG"):
        with open(os.environ["STUB_SBX_LOG"], "a") as f:
            f.write(json.dumps(pairs) + "\n")
    if os.environ.get("STUB_PATH_LOG"):   # the PATH this feeder was actually handed
        with open(os.environ["STUB_PATH_LOG"], "a") as f:
            f.write(os.environ["PATH"] + "\n")
    if os.environ.get("STUB_ENV_LOG"):    # the NAMES of the environment it was handed (the initial block)
        with open(os.environ["STUB_ENV_LOG"], "a") as f:
            f.write(json.dumps(sorted(kv.split("=", 1)[0] for kv in open("/proc/self/environ", "rb").read().decode().split("\0") if "=" in kv)) + "\n")
    log = pairs.get("SANDBOX_LOG")
    mode = os.environ.get("STUB_SANDBOX", "ok")
    if not log or mode == "nolaunch":
        return
    first = os.environ["PATH"].split(":")[0]
    sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
    W, F = sha(os.path.join(first, "claude")), sha(os.path.join(first, "sandbox-forward.py"))
    if mode == "badwrapper":
        W = "0" * 64
    me = os.getpid()   # the stub stands in for the forwarder too: it is gone when the module looks (its start time is real)
    start = open("/proc/%d/stat" % me).read().rsplit(")", 1)[1].split()[19]
    sock = os.path.join(os.path.dirname(log), "bridge-%d.sock" % me)
    pfx = pairs.get("SANDBOX_TEST_UNIT_PREFIX", "student-sandbox-")
    line = (f"wrapper-launch time=1 pid=2 wrapper_sha256={W} forwarder_sha256={F} scope_unit={pfx}{me}-{me:x} "
            f"forwarder_pid={me} forwarder_start={start} bridge_sock={sock} model=h:1 "
            f"test_mode=1 test_exec=0 cap_tmp=2147483648 cap_tasks=1024 cap_memory=4294967296")
    CF = "fwd-fault method=POST path=/x status=502 bytes_read=0 kind=upstream reason=connect-failed detail=refused"
    body = [line, CF] if mode == "unreachable" else [line, "fwd-first-request"]
    with open(log, "a") as f:
        f.write("".join(l + "\n" for l in body))

a = sys.argv[1:]
def arg(n): return a[a.index(n) + 1]
with open(os.environ["STUB_ARGV"], "a") as f:
    f.write(json.dumps(caller_argv(a)) + "\n")
if os.environ.get("STUB_RAW"):
    open(os.environ["STUB_RAW"], "a").write(json.dumps(a) + "\n")
qs = json.load(open(arg("--question-file")))
sess = arg("--resume")
if "--dump-plan" in a:
    plan = [{"kind": "compact", "exchanges": [], "text": "/compact"}] + [
        {"kind": "question", "exchanges": [], "text": "Q " + q["question"], "id": q["id"]} for q in qs]
    mode = os.environ.get("STUB_PLAN")
    if mode == "swap":
        plan[1], plan[2] = plan[2], plan[1]
    elif mode == "extra":
        plan.append({"kind": "practice-question", "exchanges": [], "text": "x"})
    elif mode == "nocompact":
        plan = plan[1:]
    json.dump(plan, sys.stdout)
    sys.exit(0)
with open(os.environ["STUB_MARK"], "a") as f:
    f.write("student run\n")
emulate_wrapper(a)
out = arg("--out"); os.makedirs(out, exist_ok=True)
rows = [{"i": 1, "kind": "compact", "session_id": sess, "is_error": False}]
asked = qs[:-1] if os.environ.get("STUB_SKIPQ") else qs
rows += [{"i": n + 2, "kind": "question", "id": q["id"], "session_id": sess, "is_error": False} for n, q in enumerate(asked)]
with open(os.path.join(out, "turns.jsonl"), "w") as f:
    f.write("".join(json.dumps(r) + "\n" for r in rows))
act = os.environ.get("STUB_ACTION")
db = {"slot": os.path.join(arg("--arm-home"), ".engram", "knowledge.db"),
      "protected": os.environ.get("STUB_TARGET", "")}.get(act)
if db:
    c = sqlite3.connect(db); c.execute("insert into nodes values ('stub', 'a stub row')"); c.commit(); c.close()
sys.exit(int(os.environ.get("STUB_RC", "0")))
'''

STUB_PLANT = r'''
import json, os, sys
# orig_argv[0] = the interpreter path the launcher passed; sys.executable is the child's own resolution (differs through symlinks)
with open(os.environ["STUB_PLANT_LOG"], "w") as f:
    f.write(json.dumps({"argv": sys.argv[1:], "exe": getattr(sys, "orig_argv", [sys.executable])[0], "prot": os.environ.get("P1_PROTECTED")}))
sys.exit(int(os.environ.get("STUB_PLANT_RC", "0")))
'''

CORRUPT_HOOK = r'''
import sqlite3, sys
c = sqlite3.connect(sys.argv[1] + "/.engram/knowledge.db")
c.execute("update nodes set claim = 'corrupt' where id = 'n1'"); c.commit(); c.close()
'''


class World:
    def __init__(self, root):
        self.root = root
        self.pres = make_home(root / "preserved-a")
        self.pres2 = make_home(root / "preserved-b", memory=False)  # a protected home with no memory folder
        self.slot = root / "slot"
        self.slot.mkdir()
        (self.slot / "old.txt").write_text("what the slot held before\n")
        self.runs = root / "runs"; self.runs.mkdir()
        self.qfile = root / "questions.json"
        self.qfile.write_text(json.dumps([{"id": "F02", "question": "Q two?"}, {"id": "A01", "question": "Q a1?"},
                                          {"id": "F01", "question": "Q one?"}]))
        self.comps = root / "components.txt"; self.comps.write_text("SETUP ID test\n")
        self.parquet = root / "syn.parquet"; self.parquet.write_bytes(b"PAR1 stand-in: not the registered dataset")
        # the stand-in's own prefix, injected through the test-only hook (the real constant accepts only the registered one)
        self.parquet_prefix = P1S.file_sha256(self.parquet)[:12]
        self.stub = root / "stub-feed4.py"; self.stub.write_text(STUB_FEED4)
        self.plant = root / "stub-plant.py"; self.plant.write_text(STUB_PLANT)
        self.hook = root / "corrupt-hook.py"; self.hook.write_text(CORRUPT_HOOK)
        self.mark = root / "student-ran.txt"
        self.argv_log = root / "stub-argv.jsonl"
        self.sbx_log = root / "stub-sandbox-pairs.jsonl"
        # the launch module asks `systemctl --user` to stop and list scopes: on a host with no systemd (a Mac) the cells run against
        # a stand-in that answers as an empty user manager, so they keep running there
        self.path = os.environ["PATH"]
        if shutil.which("systemctl") is None:
            self.path = install_stub_systemctl(root / "stub-systemctl-bin") + os.pathsep + self.path
        self.unit_prefix = "p1sbxt%s-" % os.urandom(3).hex()   # this world's own scope-name prefix (hermetic cells)
        # the sandbox input of a real run: the expected hashes are those of the files in this tree, the settings are
        # placeholders (a stub starts no student, so nothing executes them) with the port of feed.py's default model URL
        self.expected = root / "sandbox-expected.txt"
        self.expected.write_text("wrapper_sha256=%s\nforwarder_sha256=%s\n" % (
            sha(os.path.join(TOOLS, "student-sandbox.sh")), sha(os.path.join(TOOLS, "sandbox-forward.py"))))
        self.plant_log = root / "plant-log.json"
        self.proc = None

    def env(self, **over):
        e = {"PATH": self.path, "BEAM_PY": sys.executable, "BEAM_ARM_HOME": str(self.slot),
             "BEAM_RUNS_DIR": str(self.runs), "BEAM_PARQUET": str(self.parquet), "P1_PROTECTED": f"{self.pres}:{self.pres2}",
             "P1_FEED4": str(self.stub), "P1_PLANT_CONTROL": str(self.plant), "P1_UTC_STAMP": STAMP,
             "P1_EXPECTED_PARQUET_PREFIX": self.parquet_prefix,
             "P1_TEST_HOOKS": "1", "STUB_MARK": str(self.mark), "STUB_ARGV": str(self.argv_log), "STUB_PLANT_LOG": str(self.plant_log),
             "STUB_SBX_LOG": str(self.sbx_log), "STUB_RAW": str(self.root / "stub-raw.jsonl"),
             "STUB_PATH_LOG": str(self.root / "stub-path.txt"), "STUB_ENV_LOG": str(self.root / "stub-env.json"),
             "SANDBOX_BINARY": "/placeholder/claude", "SANDBOX_BINARY_SHA256": "b" * 64, "SANDBOX_MODEL_HOST": "127.0.0.1",
             "SANDBOX_MODEL_PORT": "11434", "SANDBOX_MODEL_ALLOW": "POST /v1/messages", "SANDBOX_PROTECT": str(self.pres),
             # test mode and this run's own scope-name prefix: the before-launch scan sees only this run's units (hermetic)
             "SANDBOX_TEST": "1", "SANDBOX_TEST_UNIT_PREFIX": self.unit_prefix}
        e.update({k: v for k, v in over.items() if v is not None})
        for k, v in over.items():
            if v is None:
                e.pop(k, None)
        return e

    def run(self, *extra, label="t1", end=None, drop=(), **envover):
        args = ["--end-state", str(end or self.pres), "--session", SESSION, "--label", label,
                "--question-file", str(self.qfile), "--components", str(self.comps), "--expect-sandbox", str(self.expected)]
        for a in extra:
            if isinstance(a, tuple) and a[1] is None:  # ("--expect-sandbox", None) leaves the flag out
                i = args.index(a[0]); del args[i:i + 2]
            elif isinstance(a, tuple):  # ("--question-file", path) replaces the default
                args[args.index(a[0]) + 1] = a[1]
            else:
                args.append(a)
        env = self.env(**envover)
        for d in drop:
            env.pop(d, None)
        return subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True, env=env)

    def start_fake_process(self):
        """A process whose command line holds <slot>/.engram/ : the loop must stop it (or, on a refusal, not touch it)."""
        self.proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)",
                                      os.path.join(str(self.slot), ".engram", "marker")])
        return self.proc

    def pres_path(self):
        return __import__("pathlib").Path(self.pres)

    def snapshot(self):
        return {"slot": tree(self.slot), "pres": tree(self.pres), "pres2": tree(self.pres2),
                "root": sorted(os.listdir(self.root))}

    def assert_untouched(self, before, label="t1"):
        assert self.snapshot() == before, "something under the slot, the protected homes or the root changed"
        assert not (self.runs / f"p1-{label}").exists() and os.listdir(self.runs) == []
        assert not self.mark.exists() and not self.argv_log.exists() and not self.plant_log.exists()
        assert not self.sbx_log.exists()
        assert self.proc is None or self.proc.poll() is None, "the fake slot process was killed by a refusal"


@pytest.fixture
def w(tmp_path):
    world = World(tmp_path)
    yield world
    if world.proc is not None and world.proc.poll() is None:
        world.proc.kill()
    if world.proc is not None:
        world.proc.wait()


def refusal(w, *extra, label="t1", expect=None, **kw):
    """Run once; require exit 2 (and the expected words in the message) and that NOTHING was touched."""
    w.start_fake_process()
    before = w.snapshot()
    r = w.run(*extra, label=label, **kw)
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    if expect:
        assert expect in r.stdout + r.stderr, (expect, r.stdout, r.stderr)
    w.assert_untouched(before, label)
    return r


# ------------------------------------------------------------------ step 1: every refusal, with nothing touched
@pytest.mark.parametrize("var", ["BEAM_PY", "BEAM_ARM_HOME", "BEAM_RUNS_DIR", "BEAM_PARQUET", "P1_PROTECTED"])
def test_refuses_a_missing_environment_variable_naming_it(w, var):
    refusal(w, expect=var, drop=(var,))


def test_refuses_an_end_state_that_is_not_protected(w):
    other = make_home(w.root / "unlisted-home")
    refusal(w, end=other, expect="P1_PROTECTED")


def test_refuses_a_symlink_to_an_unprotected_home_as_the_end_state(w):
    """The end state is judged by realpath: a link to a home that is not protected is not protected."""
    other = make_home(w.root / "unlisted-home")
    link = w.root / "link-to-other"; link.symlink_to(other)
    refusal(w, end=link, expect="P1_PROTECTED")


def test_refuses_a_protected_entry_that_does_not_exist(w):
    refusal(w, P1_PROTECTED=f"{w.pres}:{w.root / 'no-such-home'}", expect="no-such-home")


def test_refuses_a_slot_equal_to_a_protected_path(w):
    refusal(w, BEAM_ARM_HOME=str(w.pres), expect="slot")


def test_refuses_a_slot_inside_a_protected_path(w):
    refusal(w, BEAM_ARM_HOME=str(w.pres) + "/work/inner-slot", expect="slot")


def test_refuses_a_slot_that_contains_a_protected_path(w):
    inner = make_home(w.slot / "inner-home")  # the slot now holds a protected home
    refusal(w, end=inner, P1_PROTECTED=f"{inner}:{w.pres2}", expect="slot")


def test_refuses_a_slot_reaching_a_protected_path_through_a_symlink(w):
    link = w.root / "slot-link"; link.symlink_to(w.pres)
    refusal(w, BEAM_ARM_HOME=str(link), expect="slot")


def test_refuses_when_the_run_directory_exists(w):
    (w.runs / "p1-t1").mkdir()
    w.start_fake_process()
    before = w.snapshot(); runs_before = tree(w.runs)
    r = w.run()
    assert r.returncode == 2 and "p1-t1" in r.stdout + r.stderr
    assert w.snapshot() == before and tree(w.runs) == runs_before and w.proc.poll() is None
    assert not w.mark.exists()


def test_refuses_an_end_state_without_a_store(w):
    bad = make_home(w.root / "no-db", db=False)
    refusal(w, end=bad, P1_PROTECTED=f"{bad}:{w.pres2}", expect="knowledge.db")


def test_refuses_an_end_state_without_a_claude_folder(w):
    bad = make_home(w.root / "no-claude", claude=False)
    refusal(w, end=bad, P1_PROTECTED=f"{bad}:{w.pres2}", expect=".claude")


def test_refuses_a_missing_question_file(w):
    refusal(w, ("--question-file", str(w.root / "absent.json")), expect="question")


def test_refuses_a_missing_components_file(w):
    refusal(w, ("--components", str(w.root / "absent.txt")), expect="components")


@pytest.mark.parametrize("flags", [
    ["--plant-builtin", "BuiltinFactAA"],                                      # one fact only
    ["--plant-builtin", "BuiltinFactAA", "--plant-engram", "EngramFactBB"],    # no --plant-absent
    ["--plant-absent", "AbsentFactCC"],                                        # no builtin, no engram
    ["--plant-question", "What is it?"],                                       # a question alone plants nothing
])
def test_refuses_a_partial_plant_set(w, flags):
    refusal(w, *flags, expect="plant")


def test_refuses_planting_when_the_end_state_has_no_venv_python(w):
    bad = make_home(w.root / "no-venv", venv=False)
    refusal(w, "--plant-builtin", "BuiltinFactAA", "--plant-engram", "EngramFactBB", "--plant-absent", "AbsentFactCC",
            end=bad, P1_PROTECTED=f"{bad}:{w.pres2}", expect="venv")


@pytest.mark.parametrize("label", ["../escape", "a b", "x/y", ""])
def test_refuses_a_label_outside_the_charset(w, label):
    refusal(w, label=label, expect="label")


def test_refuses_when_the_aside_path_already_exists(w):
    """Step 4's own refusal, checked up front so nothing (no process) is touched before it."""
    aside = w.root / f"slot.aside-t1-{STAMP}"
    aside.mkdir()
    w.start_fake_process()
    before = w.snapshot()
    r = w.run()
    assert r.returncode == 2 and "aside" in r.stdout + r.stderr
    assert w.snapshot() == before and w.proc.poll() is None and not (w.runs / "p1-t1").exists()


# ------------------------------------------------------------------ the happy path and its artifacts
@needs_linux_wrapper
def test_clean_run_exits_0_and_writes_every_artifact(w):
    r = w.run()
    assert r.returncode == 0, (r.stdout, r.stderr)
    run = w.runs / "p1-t1"
    for name in ("before-hashes.txt", "after-hashes.txt", "plan.json", "delivery.txt", "setup.txt", "run/turns.jsonl"):
        assert (run / name).exists(), name
    assert "PASS" in (run / "delivery.txt").read_text()
    assert (run / "transcripts").is_dir()
    assert (run / "before-hashes.txt").read_text() == (run / "after-hashes.txt").read_text()
    assert (w.slot / ".disposable-copy").exists()
    assert (w.slot / ".engram" / "knowledge.db").exists() and not (w.slot / "old.txt").exists()
    assert "PROTECTED CHANGED" not in r.stdout
    # the student run got exactly the spec's arguments
    calls = [json.loads(l) for l in w.argv_log.read_text().splitlines()]
    dump = [c for c in calls if "--dump-plan" in c]; real = [c for c in calls if "--dump-plan" not in c]
    assert len(dump) == 1 and len(real) == 1
    a = real[0]
    for flag, val in (("--arm-home", str(w.slot)), ("--out", str(run / "run")), ("--conv", "9"), ("--turns", "0"),
                      ("--resume", SESSION), ("--question-file", str(w.qfile)),
                      ("--env", "CLAUDE_CODE_MAX_CONTEXT_TOKENS=131072"), ("--expect-components", str(w.comps))):
        assert a[a.index(flag) + 1] == val, flag
    assert "--force-compact" in a
    assert [x for x in dump[0] if x not in ("--dump-plan",)][:2] == ["--arm-home", str(w.slot)]


@needs_linux_wrapper
def test_before_hashes_cover_every_protected_home_by_the_store_hash_and_the_memory_files(w):
    assert w.run().returncode == 0
    text = (w.runs / "p1-t1" / "before-hashes.txt").read_text()
    for home in (w.pres, w.pres2):
        h, ntab, nrows = P1S.store_content_hash(os.path.join(home, ".engram", "knowledge.db"))
        assert os.path.realpath(home) in text and h in text and f"tables={ntab}" in text and f"rows={nrows}" in text
    mem = os.path.join(w.pres, ".claude", "projects", "-p", "memory")
    for rel in ("MEMORY.md", "a.md", os.path.join("sub", "b.md")):
        assert sha(os.path.join(mem, rel)) in text and rel in text
    assert "3 files" in text and "0 files" in text


@needs_linux_wrapper
def test_setup_txt_first_line_is_the_commit_then_the_hashes_and_exit_codes(w):
    assert w.run().returncode == 0
    lines = (w.runs / "p1-t1" / "setup.txt").read_text().splitlines()
    head = subprocess.run(["git", "-C", TOOLS, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    assert lines[0] == head
    body = "\n".join(lines)
    for f in (TOOL, str(w.stub), os.path.join(TOOLS, "feed.py"), str(w.qfile), str(w.comps),
              os.path.join(TOOLS, "answer-delivery-check.py"), os.path.join(TOOLS, "plant-control.py")):
        assert sha(f) in body, f
    assert "start" in body and "end" in body and "exit" in body


@needs_linux_wrapper
def test_the_fake_slot_process_is_stopped_before_the_copy(w):
    proc = w.start_fake_process()
    assert w.run().returncode == 0
    assert proc.wait(timeout=10) is not None


@needs_linux_wrapper
def test_a_pre_existing_slot_is_moved_aside_never_deleted(w):
    old = tree(w.slot)
    assert w.run().returncode == 0
    aside = w.root / f"slot.aside-t1-{STAMP}"
    assert tree(aside) == old and (aside / "old.txt").read_text() == "what the slot held before\n"


@needs_linux_wrapper
def test_an_absent_slot_is_fine_and_nothing_is_moved(w):
    shutil.rmtree(w.slot)
    assert w.run().returncode == 0
    assert [n for n in os.listdir(w.root) if "aside" in n] == []


def test_dry_run_stops_before_the_student_and_still_proves_the_protected_homes(w):
    r = w.run("--dry-run")
    assert r.returncode == 0, (r.stdout, r.stderr)
    run = w.runs / "p1-t1"
    assert (run / "plan.json").exists() and (run / "after-hashes.txt").exists() and (run / "setup.txt").exists()
    assert not w.mark.exists() and not (run / "run").exists() and not (run / "delivery.txt").exists()


# ------------------------------------------------------------------ protected-change detection (the mutation target)
def changed_homes_printed(stdout):
    return [l[len("changed home: "):] for l in stdout.splitlines() if l.startswith("changed home: ")]


@needs_linux_wrapper
def test_a_write_into_a_protected_store_is_exit_5_and_names_the_home(w):
    target = os.path.join(w.pres2, ".engram", "knowledge.db")
    r = w.run(STUB_ACTION="protected", STUB_TARGET=target)
    assert r.returncode == 5, (r.returncode, r.stdout, r.stderr)
    assert "PROTECTED CHANGED" in r.stdout
    assert changed_homes_printed(r.stdout) == [os.path.realpath(w.pres2)]


@needs_linux_wrapper
def test_a_write_into_the_slot_only_is_exit_0(w):
    r = w.run(STUB_ACTION="slot")
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    assert "PROTECTED CHANGED" not in r.stdout
    c = sqlite3.connect(f"file:{w.slot}/.engram/knowledge.db?mode=ro", uri=True)
    assert c.execute("select count(*) from nodes where id='stub'").fetchone()[0] == 1
    c.close()


@needs_linux_wrapper
def test_a_change_to_a_protected_memory_file_is_exit_5(w):
    """The memory-folder hashes are part of the compare, not only the store."""
    victim = os.path.join(w.pres, ".claude", "projects", "-p", "memory", "a.md")
    # tamper from the after-copy hook, which runs once the run directory exists
    hook = w.root / "tamper-hook.py"
    hook.write_text(f"open({victim!r}, 'a').write('tampered')\n")
    r = w.run(P1_AFTER_COPY_HOOK=str(hook))
    assert r.returncode == 5 and "PROTECTED CHANGED" in r.stdout
    assert changed_homes_printed(r.stdout) == [os.path.realpath(w.pres)]


@needs_linux_wrapper
def test_exit_5_overrides_a_feed4_failure(w):
    target = os.path.join(w.pres2, ".engram", "knowledge.db")
    r = w.run(STUB_ACTION="protected", STUB_TARGET=target, STUB_RC="1")
    assert r.returncode == 5 and "PROTECTED CHANGED" in r.stdout


# ------------------------------------------------------------------ steps 5, 7, 8, 9 failures
def test_a_corrupted_copy_is_exit_3_with_both_hashes_and_no_student_run(w):
    r = w.run(P1_AFTER_COPY_HOOK=str(w.hook))
    assert r.returncode == 3, (r.returncode, r.stdout, r.stderr)
    h, _, _ = P1S.store_content_hash(os.path.join(w.pres, ".engram", "knowledge.db"))
    c, _, _ = P1S.store_content_hash(os.path.join(w.slot, ".engram", "knowledge.db"))
    assert h != c and h in r.stdout and c in r.stdout
    assert not w.mark.exists() and not w.argv_log.exists()
    assert (w.runs / "p1-t1" / "after-hashes.txt").exists()  # the protected homes are still proved on this path


@pytest.mark.parametrize("mode", ["swap", "extra", "nocompact"])
def test_a_plan_that_is_not_compact_then_the_questions_in_order_is_exit_3(w, mode):
    r = w.run(STUB_PLAN=mode)
    assert r.returncode == 3, (r.returncode, r.stdout, r.stderr)
    assert not w.mark.exists()


@needs_linux_wrapper
def test_feed4_nonzero_is_exit_3(w):
    r = w.run(STUB_RC="1")
    assert r.returncode == 3 and w.mark.exists()
    assert (w.runs / "p1-t1" / "after-hashes.txt").exists() and (w.runs / "p1-t1" / "setup.txt").exists()


@needs_linux_wrapper
def test_a_failed_delivery_check_is_exit_1(w):
    r = w.run(STUB_SKIPQ="1")
    assert r.returncode == 1, (r.returncode, r.stdout, r.stderr)
    assert "FAIL" in (w.runs / "p1-t1" / "delivery.txt").read_text()


# ------------------------------------------------------------------ step 6: plant
PLANT = ["--plant-builtin", "BuiltinFactAA", "--plant-engram", "EngramFactBB", "--plant-absent", "AbsentFactCC"]


@needs_linux_wrapper
def test_plant_runs_plant_control_with_the_slots_venv_python_and_the_run_evidence_dir(w):
    r = w.run(*PLANT, "--plant-question", "What is it?")
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    log = json.loads(w.plant_log.read_text())
    a = log["argv"]
    for flag, val in (("--home", str(w.slot)), ("--builtin-fact", "BuiltinFactAA"), ("--engram-fact", "EngramFactBB"),
                      ("--absent-fact", "AbsentFactCC"), ("--question", "What is it?"),
                      ("--evidence-dir", str(w.runs / "p1-t1" / "plant-evidence"))):
        assert a[a.index(flag) + 1] == val, flag
    assert log["exe"].endswith(os.path.join(".engram", "venv", "bin", "python")) and log["exe"].startswith(str(w.slot))
    assert log["prot"] == f"{w.pres}:{w.pres2}"


@needs_linux_wrapper
def test_plant_without_a_question_passes_no_question_flag(w):
    assert w.run(*PLANT).returncode == 0
    assert "--question" not in json.loads(w.plant_log.read_text())["argv"]


def test_plant_failure_is_exit_4_and_no_student_run(w):
    r = w.run(*PLANT, STUB_PLANT_RC="1")
    assert r.returncode == 4 and not w.mark.exists()
    assert (w.runs / "p1-t1" / "after-hashes.txt").exists()


def test_plant_exit_3_protected_changed_is_launcher_exit_5(w):
    r = w.run(*PLANT, STUB_PLANT_RC="3")
    assert r.returncode == 5 and not w.mark.exists()


def test_a_dry_run_still_plants(w):
    assert w.run(*PLANT, "--dry-run").returncode == 0 and w.plant_log.exists() and not w.mark.exists()


# ------------------------------------------------------------------ the store content hash
def reference_chash(path):
    """The exact method that produced the logged values (the spec's code, copied)."""
    c = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    virt = {r[0] for r in c.execute("select name from sqlite_master where type='table' and sql like 'CREATE VIRTUAL%'")}
    tabs = [r[0] for r in c.execute("select name from sqlite_master where type='table' order by name") if r[0] not in virt]
    h = hashlib.sha256(); n = 0
    for t in tabs:
        rows = sorted(repr(r) for r in c.execute(f'select * from "{t}"')); n += len(rows)
        h.update(t.encode()); [h.update(r.encode()) for r in rows]
    c.close(); return h.hexdigest(), len(tabs), n


def test_hash_equals_the_logged_methods_code_byte_for_byte(tmp_path):
    db = str(tmp_path / "k.db"); make_db(db)
    assert P1S.store_content_hash(db) == reference_chash(db)


def test_virtual_table_is_excluded_and_its_shadow_tables_and_sqlite_sequence_are_included(tmp_path):
    db = str(tmp_path / "k.db"); make_db(db)
    c = sqlite3.connect(db)
    names = {r[0] for r in c.execute("select name from sqlite_master where type='table'")}
    virt = {r[0] for r in c.execute("select name from sqlite_master where type='table' and sql like 'CREATE VIRTUAL%'")}
    c.close()
    assert virt == {"notes_fts"} and {"notes_fts_data", "notes_fts_idx", "sqlite_sequence"} <= names
    _, ntab, _ = P1S.store_content_hash(db)
    assert ntab == len(names) - 1  # every table but the one virtual table: shadow tables and sqlite_sequence count


def test_a_change_only_in_the_virtual_tables_shadow_rows_moves_the_hash(tmp_path):
    db = str(tmp_path / "k.db"); make_db(db)
    before = P1S.store_content_hash(db)
    c = sqlite3.connect(db); c.execute("insert into notes_fts (body) values ('another document')"); c.commit(); c.close()
    assert P1S.store_content_hash(db)[0] != before[0]


def test_a_one_row_change_moves_the_hash_and_row_order_does_not(tmp_path):
    a, b, c3 = (str(tmp_path / n) for n in ("a.db", "b.db", "c.db"))
    make_db(a, rows=(("n1", "alpha"), ("n2", "beta")))
    make_db(b, rows=(("n2", "beta"), ("n1", "alpha")))      # same rows, other insertion order
    make_db(c3, rows=(("n1", "alpha"), ("n2", "betA")))     # one value changed
    ha, hb, hc = (P1S.store_content_hash(p)[0] for p in (a, b, c3))
    assert ha == hb and ha != hc


def test_the_hash_opens_the_store_read_only(tmp_path):
    db = str(tmp_path / "k.db"); make_db(db)
    before = tree(tmp_path)
    P1S.store_content_hash(db)
    assert tree(tmp_path) == before


# ------------------------------------------------------------------ round 2: hashing a protected home writes nothing
def bytes_and_mtimes(root):
    """{relpath: (sha256 | 'link:<target>', mtime_ns)} for every file and link under root (links not followed)."""
    out = {}
    for dp, dns, fns in os.walk(str(root)):
        for n in fns:
            full = os.path.join(dp, n)
            st = os.lstat(full)
            out[os.path.relpath(full, str(root))] = (
                "link:" + os.readlink(full) if os.path.islink(full) else sha(full), st.st_mtime_ns)
    return out


@pytest.fixture
def wal_home(tmp_path):
    """A protected-style home whose store is in WAL mode with -wal (holding uncheckpointed rows) and -shm present. A
    second connection is kept open so the three files stay on disk, as they do beside a store a live process had open."""
    h = make_home(tmp_path / "wal-home")
    db = os.path.join(h, ".engram", "knowledge.db")
    keeper = sqlite3.connect(db)
    keeper.execute("pragma journal_mode=wal")
    keeper.execute("pragma wal_autocheckpoint=0")
    keeper.execute("insert into nodes values ('w1', 'a row that lives only in the wal')")
    keeper.commit()
    assert os.path.exists(db + "-wal") and os.path.exists(db + "-shm")
    yield h
    keeper.close()


def test_protected_store_hash_leaves_every_byte_and_mtime_under_engram_alone(wal_home):
    eng = os.path.join(wal_home, ".engram")
    before = bytes_and_mtimes(eng)
    assert {"knowledge.db", "knowledge.db-wal", "knowledge.db-shm"} <= set(before)
    h, t, n = P1S.protected_store_hash(wal_home)
    assert bytes_and_mtimes(eng) == before


def test_protected_store_hash_sees_the_rows_that_live_only_in_the_wal(wal_home, tmp_path):
    """The copy carries -wal and -shm with the db, so the hash is the hash of what a reader of the live store sees."""
    h, t, n = P1S.protected_store_hash(wal_home)
    plain = str(tmp_path / "plain.db"); make_db(plain)
    h0, _, n0 = P1S.store_content_hash(plain)
    assert n == n0 + 1 and h != h0  # the extra wal-only row is in the count and the hash


def test_protected_store_hash_matches_the_in_place_method_on_an_ordinary_store(tmp_path):
    h = make_home(tmp_path / "plain-home")
    assert P1S.protected_store_hash(h) == P1S.store_content_hash(os.path.join(h, ".engram", "knowledge.db"))


def test_protected_store_hash_removes_its_temporary_copy(wal_home):
    import tempfile
    before = set(os.listdir(tempfile.gettempdir()))
    P1S.protected_store_hash(wal_home)
    assert set(os.listdir(tempfile.gettempdir())) == before


def test_the_whole_before_record_of_a_protected_home_writes_nothing(wal_home):
    """home_record is what before-hashes and after-hashes call: the store AND the memory-folder walk, read-only."""
    before = bytes_and_mtimes(wal_home)
    assert any("memory" in k for k in before)
    rec = P1S.home_record(wal_home)
    assert "memory 3 files" in rec and "tables=" in rec
    assert bytes_and_mtimes(wal_home) == before


@needs_linux_wrapper
def test_the_launcher_leaves_a_wal_mode_protected_home_untouched_bytes_and_mtimes(w):
    keeper = sqlite3.connect(os.path.join(w.pres, ".engram", "knowledge.db"))
    try:
        keeper.execute("pragma journal_mode=wal"); keeper.execute("pragma wal_autocheckpoint=0")
        keeper.execute("insert into nodes values ('w1', 'wal only')"); keeper.commit()
        before = bytes_and_mtimes(w.pres)
        r = w.run()
        assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
        assert bytes_and_mtimes(w.pres) == before
    finally:
        keeper.close()


# ------------------------------------------------------------------ round 3: steps 10 and 11 run on EVERY exit path
def tamper_hook(w, extra=""):
    """A P1_AFTER_COPY_HOOK that writes into a protected home's memory file (so a protected change is on record)."""
    victim = os.path.join(w.pres, ".claude", "projects", "-p", "memory", "a.md")
    hook = w.root / "tamper-hook2.py"
    hook.write_text(f"open({victim!r}, 'a').write('tampered')\n" + extra)
    return str(hook)


@pytest.mark.parametrize("raised", ["KeyboardInterrupt", "SystemExit", "Exception"])
def test_an_interruption_or_error_mid_run_with_a_protected_change_is_still_exit_5(w, raised):
    r = w.run(P1_AFTER_COPY_HOOK=tamper_hook(w), P1_TEST_RAISE=raised)
    assert r.returncode == 5, (raised, r.returncode, r.stdout, r.stderr)
    assert "PROTECTED CHANGED" in r.stdout and changed_homes_printed(r.stdout) == [os.path.realpath(w.pres)]
    run = w.runs / "p1-t1"
    assert (run / "after-hashes.txt").exists() and (run / "setup.txt").exists()
    assert (run / "before-hashes.txt").read_text() != (run / "after-hashes.txt").read_text()
    assert not w.mark.exists()  # the interruption came before the student run


def test_an_unexpected_exception_alone_is_exit_3_with_the_after_artifacts(w):
    r = w.run(P1_TEST_RAISE="Exception")
    assert r.returncode == 3 and "PROTECTED CHANGED" not in r.stdout
    assert (w.runs / "p1-t1" / "after-hashes.txt").exists() and (w.runs / "p1-t1" / "setup.txt").exists()


@pytest.mark.parametrize("raised", ["KeyboardInterrupt", "SystemExit"])
def test_an_interruption_alone_still_writes_the_after_artifacts_and_does_not_exit_0(w, raised):
    r = w.run(P1_TEST_RAISE=raised)
    assert r.returncode not in (0, 5), (raised, r.returncode)
    assert (w.runs / "p1-t1" / "after-hashes.txt").exists() and (w.runs / "p1-t1" / "setup.txt").exists()


@needs_linux_wrapper
def test_a_setup_txt_write_failure_never_replaces_exit_5(w):
    """setup.txt is made a directory by the hook, so writing it raises; the protected change still decides the code."""
    blocker = w.runs / "p1-t1" / "setup.txt"
    hook = tamper_hook(w, extra=f"import os\nos.makedirs({str(blocker)!r})\n")
    r = w.run(P1_AFTER_COPY_HOOK=hook)
    assert r.returncode == 5, (r.returncode, r.stdout, r.stderr)
    assert "PROTECTED CHANGED" in r.stdout and "setup.txt" in r.stderr


@needs_linux_wrapper
def test_a_setup_txt_write_failure_alone_is_reported_on_stderr(w):
    blocker = w.runs / "p1-t1" / "setup.txt"
    hook = w.root / "block-setup.py"; hook.write_text(f"import os\nos.makedirs({str(blocker)!r})\n")
    r = w.run(P1_AFTER_COPY_HOOK=str(hook))
    assert "setup.txt" in r.stderr and r.returncode != 5


# ------------------------------------------------------------------ round 3: symlinks inside the end state
def test_refuses_an_end_state_with_a_symlink_into_another_protected_home(w):
    os.symlink(os.path.join(w.pres2, "work"), os.path.join(w.pres, "work", "link-to-b"))
    refusal(w, expect="symlink")


def test_refuses_an_end_state_with_a_symlink_to_a_path_that_contains_a_protected_home(w):
    os.symlink(str(w.root), os.path.join(w.pres, "work", "link-up"))
    refusal(w, expect="symlink")


def test_refuses_an_absolute_symlink_back_into_the_end_state_itself(w):
    """After cp -a the copy would still point at the preserved original, so the student could write to it."""
    os.symlink(os.path.join(w.pres, ".claude"), os.path.join(w.pres, "work", "link-to-self"))
    refusal(w, expect="symlink")


@needs_linux_wrapper
def test_a_relative_symlink_that_stays_inside_the_end_state_is_fine(w):
    os.symlink("projects", os.path.join(w.pres, ".claude", "rel-link"))  # like a venv's lib64 -> lib
    r = w.run()
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    assert os.readlink(str(w.slot / ".claude" / "rel-link")) == "projects"


@needs_linux_wrapper
def test_a_symlink_to_an_unrelated_outside_path_proceeds_and_the_count_is_printed(w):
    outside = w.root / "unrelated-outside"; outside.mkdir()
    os.symlink(str(outside), os.path.join(w.pres, "work", "link-out"))
    r = w.run()
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    # the venv's python link (to the interpreter) and this one point outside the end state
    assert "symlinks pointing outside the end state: 2" in r.stdout


# ------------------------------------------------------------------ round 4: out-and-back links, judged from the COPY's side
def test_refuses_the_out_and_back_relative_link(w):
    """E/work/x -> ../../E/real: lexically it re-enters E, but in the copy (a sibling of E) it resolves to the
    ORIGINAL E/real, a protected path."""
    (w.pres_path() / "real").write_text("original")
    os.symlink("../../" + os.path.basename(w.pres) + "/real", os.path.join(w.pres, "work", "x"))
    refusal(w, expect="symlink")


def test_refuses_a_chain_of_relative_links_whose_second_hop_leaves_the_end_state(w):
    os.symlink("l2", os.path.join(w.pres, "work", "l1"))  # the first hop stays inside
    os.symlink("../../" + os.path.basename(w.pres2) + "/work", os.path.join(w.pres, "work", "l2"))  # the second leaves
    refusal(w, expect="symlink")


@needs_linux_wrapper
def test_a_relative_link_that_climbs_and_comes_back_inside_the_end_state_is_fine(w):
    """work/up -> ../.claude/projects climbs one level but never above the end state's own root."""
    os.symlink("../.claude/projects", os.path.join(w.pres, "work", "up"))
    r = w.run()
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    assert os.readlink(str(w.slot / "work" / "up")) == "../.claude/projects"


# ------------------------------------------------------------------ round 4: the after-hash pass itself failing
@needs_linux_wrapper
def test_a_failing_after_hash_pass_is_exit_5_with_every_protected_home_listed(w):
    """No protected home changed, but the proof could not be written (after-hashes.txt is made a directory), so the
    launcher must not claim the homes are fine."""
    blocker = w.runs / "p1-t1" / "after-hashes.txt"
    hook = w.root / "block-after.py"; hook.write_text(f"import os\nos.makedirs({str(blocker)!r})\n")
    r = w.run(P1_AFTER_COPY_HOOK=str(hook))
    assert r.returncode == 5, (r.returncode, r.stdout, r.stderr)
    assert "PROTECTED CHANGED: 2 home(s)" in r.stdout
    assert sorted(changed_homes_printed(r.stdout)) == sorted([os.path.realpath(w.pres), os.path.realpath(w.pres2)])
    assert "after-hash" in r.stderr


# ------------------------------------------------------------------ round 4: test-only hooks are gated behind P1_TEST_HOOKS=1
HOOK_VALUES = {"P1_TEST_RAISE": "Exception", "P1_FEED4": "stub", "P1_PLANT_CONTROL": "plant", "P1_AFTER_COPY_HOOK": "hook",
               "P1_UTC_STAMP": "20261118T000000Z", "P1_EXPECTED_PARQUET_PREFIX": "000000000000"}


@pytest.mark.parametrize("var", sorted(HOOK_VALUES))
def test_a_test_only_hook_without_p1_test_hooks_is_refused_naming_the_variable(w, var):
    kw = {k: None for k in HOOK_VALUES}  # none of the others
    kw["P1_TEST_HOOKS"] = None
    path = {"P1_FEED4": w.stub, "P1_PLANT_CONTROL": w.plant, "P1_AFTER_COPY_HOOK": w.hook}.get(var)
    kw[var] = str(path) if path else HOOK_VALUES[var]
    if var == "P1_EXPECTED_PARQUET_PREFIX":
        kw[var] = w.parquet_prefix  # the value that WOULD pass the check if the hook were honoured
    refusal(w, expect=var, **kw)


def test_no_hook_variable_and_no_gate_is_refused_at_step_1_on_the_stand_in_parquet_not_for_the_missing_gate(w):
    """Without any hook the launcher uses the real constant: the stand-in parquet is refused for its hash, not for the gate."""
    kw = {k: None for k in HOOK_VALUES}; kw["P1_TEST_HOOKS"] = None
    r = refusal(w, "--dry-run", expect=P1S.REGISTERED_PARQUET_PREFIX, **kw)
    assert "P1_TEST_HOOKS" not in r.stderr  # it was not refused for lack of the gate


# ------------------------------------------------------------------ round 4: the printed status is the real status
def test_a_re_raised_system_exit_prints_the_code_the_process_exits_with(w):
    r = w.run(P1_TEST_RAISE="SystemExit")
    last = [l for l in r.stdout.splitlines() if l.startswith("exit ")][-1]
    assert last == f"exit {r.returncode}", (last, r.returncode)


# ------------------------------------------------------------------ round 5: any relative link that climbs above the root
def test_refuses_the_reviewers_relative_link_to_a_sibling_protected_home(w):
    """E/lnk -> ../q, slot a sibling, q protected: in the copy it would resolve beside the slot."""
    q = make_home(w.root / "q")
    os.symlink("../q", os.path.join(w.pres, "lnk"))
    refusal(w, P1_PROTECTED=f"{w.pres}:{w.pres2}:{q}", expect="symlink")


def test_refuses_a_relative_link_that_climbs_even_to_an_unrelated_outside_path(w):
    """Step 1 cannot judge where it lands once copied (it resolves relative to the slot's location)."""
    (w.root / "unrelated-outside").mkdir()
    os.symlink("../../unrelated-outside", os.path.join(w.pres, "work", "lnk"))
    refusal(w, expect="climb")


@needs_linux_wrapper
def test_a_relative_link_to_an_absolute_link_outside_that_does_not_climb_is_allowed(w):
    """The real homes' venvs: python -> python3 (relative, does not climb) where python3 -> an interpreter (absolute)."""
    b = os.path.join(w.pres, ".engram", "venv", "bin")
    os.symlink("python", os.path.join(b, "python3.12"))  # relative; the link it names is the absolute one to the interpreter
    r = w.run()
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    assert os.readlink(str(w.slot / ".engram" / "venv" / "bin" / "python3.12")) == "python"


# ------------------------------------------------------------------ round 5: BEAM_RUNS_DIR is judged like the slot
def test_refuses_a_runs_dir_that_is_a_protected_home(w):
    refusal(w, BEAM_RUNS_DIR=str(w.pres), expect="BEAM_RUNS_DIR")


def test_refuses_a_runs_dir_that_is_a_symlink_to_a_protected_home(w):
    link = w.root / "runs-link"; link.symlink_to(w.pres)
    refusal(w, BEAM_RUNS_DIR=str(link), expect="BEAM_RUNS_DIR")


def test_refuses_a_runs_dir_inside_a_protected_home(w):
    refusal(w, BEAM_RUNS_DIR=os.path.join(w.pres, "work", "runs"), expect="BEAM_RUNS_DIR")


def test_refuses_a_runs_dir_that_contains_a_protected_home(w):
    refusal(w, BEAM_RUNS_DIR=str(w.root), expect="BEAM_RUNS_DIR")


def test_refuses_a_runs_dir_inside_the_slot(w):
    refusal(w, BEAM_RUNS_DIR=str(w.slot / "runs"), expect="BEAM_RUNS_DIR")


def test_refuses_a_runs_dir_equal_to_the_slot(w):
    refusal(w, BEAM_RUNS_DIR=str(w.slot), expect="BEAM_RUNS_DIR")


# ------------------------------------------------------------------ the three-channel path: the planned actions, compared mechanically
# EQUIVALENCE CELL (Kepler's condition on the channel-subset change). The launcher's plan for a three-channel plant
# (--plant-builtin, --plant-engram, --plant-absent, --plant-question) is recorded by two recorder scripts standing in
# for plant-control.py and feed4.py through the test hooks: each appends {tool, argv, exe, P1_PROTECTED} to ONE log
# (exe = the interpreter path exactly as the launcher passed it, from sys.orig_argv), so
# the ORDER of the three invocations is recorded too (plant-control, the feed4 plan dump, the feed4 run), then runs the
# existing stub of that tool. The run-specific parts (temp root, slot, run dir, files) are replaced by stable
# placeholders; the record is compared with a GOLDEN file captured from the launcher BEFORE the subset change
# (tests/golden_three_channel_plan.json). A later change to the launcher must leave this cell green.
GOLDEN_PLAN = os.path.join(TOOLS, "tests", "golden_three_channel_plan.json")

RECORDER = r'''
import json, os, runpy, sys
label, stub = {LABEL!r}, {STUB!r}
with open(os.environ["STUB_REC_LOG"], "a") as f:
    argv = sys.argv[1:]
    for i in range(len(argv) - 2, -1, -1):   # the module's own `--env SANDBOX_*` pairs are not the caller's arguments
        if argv[i] == "--env" and argv[i + 1].startswith("SANDBOX_"):
            del argv[i:i + 2]
    f.write(json.dumps({{"tool": label, "argv": argv, "exe": getattr(sys, "orig_argv", [sys.executable])[0],
                        "prot": os.environ.get("P1_PROTECTED")}}) + "\n")
runpy.run_path(stub, run_name="__main__")
'''


def normalized_plan_record(w, log_path):
    """The recorded invocations with every run-specific path replaced by a placeholder (longest path first)."""
    subs = [(str(w.runs / "p1-t1"), "<RUNDIR>"), (str(w.slot), "<SLOT>"), (str(w.qfile), "<QUESTION_FILE>"),
            (str(w.comps), "<COMPONENTS_FILE>"), (str(w.pres2), "<PROTECTED_B>"), (str(w.pres), "<PROTECTED_A>"),
            (sys.executable, "<BEAM_PY>"), (str(w.root), "<ROOT>")]
    subs.sort(key=lambda kv: -len(kv[0]))

    def norm(x):
        if isinstance(x, str):
            for old, new in subs:
                x = x.replace(old, new)
        return x
    return [{k: ([norm(e) for e in v] if isinstance(v, list) else norm(v)) for k, v in json.loads(line).items()}
            for line in open(log_path).read().splitlines()]


def record_three_channel_run(w):
    log = w.root / "recorder-log.jsonl"
    for name, label, stub in (("rec-plant.py", "plant-control", w.plant), ("rec-feed4.py", "feed4", w.stub)):
        (w.root / name).write_text(RECORDER.format(LABEL=label, STUB=str(stub)))
    r = w.run(*PLANT, "--plant-question", "What is it?", P1_PLANT_CONTROL=str(w.root / "rec-plant.py"),
              P1_FEED4=str(w.root / "rec-feed4.py"), STUB_REC_LOG=str(log))
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    return normalized_plan_record(w, log)


@needs_linux_wrapper
def test_the_three_channel_plan_is_identical_to_the_golden_captured_before_the_subset_change(w):
    got = record_three_channel_run(w)
    assert [g["tool"] for g in got] == ["plant-control", "feed4", "feed4"]  # plant, plan dump, student run
    assert os.path.isfile(GOLDEN_PLAN), "no golden yet; the record to capture is:\n" + json.dumps(got, indent=2, sort_keys=True)
    assert got == json.load(open(GOLDEN_PLAN)), json.dumps(got, indent=2, sort_keys=True)


# ------------------------------------------------------------------ the channel subset (control 2) and BEAM_PARQUET (contract-first)
# A plant set is valid as EITHER --plant-builtin + --plant-engram + --plant-absent (the three-channel plant, unchanged:
# see the equivalence cell above) OR exactly --plant-engram + --plant-absent (ENGRAM only: plant-control is called
# without --builtin-fact and without --question). Every other subset is refused in step 1, before anything is touched.
ENGRAM_ONLY = ["--plant-engram", "EngramFactBB", "--plant-absent", "AbsentFactCC"]


@needs_linux_wrapper
def test_engram_plus_absent_is_accepted_and_plant_control_is_called_without_builtin_fact_or_question(w):
    r = w.run(*ENGRAM_ONLY)
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    log = json.loads(w.plant_log.read_text())
    a = log["argv"]
    assert "--builtin-fact" not in a and "--question" not in a
    for flag, val in (("--home", str(w.slot)), ("--engram-fact", "EngramFactBB"), ("--absent-fact", "AbsentFactCC"),
                      ("--evidence-dir", str(w.runs / "p1-t1" / "plant-evidence"))):
        assert a[a.index(flag) + 1] == val, flag
    assert len(a) == 8  # --home --engram-fact --absent-fact --evidence-dir, each with its value, and nothing else
    assert log["prot"] == f"{w.pres}:{w.pres2}" and w.mark.exists()  # same environment, and the student run follows


# ONE CELL PER REFUSED SUBSET (Kepler's condition): the seven subsets, each refused in step 1 with nothing touched.
REFUSED_SUBSETS = {
    "builtin+engram": ["--plant-builtin", "BuiltinFactAA", "--plant-engram", "EngramFactBB"],
    "builtin+absent": ["--plant-builtin", "BuiltinFactAA", "--plant-absent", "AbsentFactCC"],
    "engram-only": ["--plant-engram", "EngramFactBB"],
    "absent-only": ["--plant-absent", "AbsentFactCC"],
    "builtin-only": ["--plant-builtin", "BuiltinFactAA"],
    "question-only": ["--plant-question", "What is it?"],
    "question+engram+absent": [*ENGRAM_ONLY, "--plant-question", "What is it?"],
}


@pytest.mark.parametrize("name", list(REFUSED_SUBSETS))
def test_every_other_plant_subset_is_refused_in_step_1_with_nothing_touched(w, name):
    r = refusal(w, *REFUSED_SUBSETS[name], expect="plant")
    assert "--plant-engram" in r.stderr and "--plant-absent" in r.stderr  # the message names the valid sets


def test_a_question_without_a_builtin_plant_is_refused_by_name(w):
    r = refusal(w, *ENGRAM_ONLY, "--plant-question", "What is it?", expect="--plant-question")
    assert "--plant-builtin" in r.stderr


@pytest.mark.parametrize("flag", ["--plant-engram", "--plant-absent"])
def test_a_blank_fact_in_an_engram_only_plant_is_refused(w, flag):
    flags = list(ENGRAM_ONLY)
    flags[flags.index(flag) + 1] = "   "
    refusal(w, *flags, expect="plant")


def test_refuses_an_engram_only_plant_when_the_end_state_has_no_venv_python(w):
    bad = make_home(w.root / "no-venv", venv=False)
    refusal(w, *ENGRAM_ONLY, end=bad, P1_PROTECTED=f"{bad}:{w.pres2}", expect="venv")


def test_an_engram_only_plant_failure_is_exit_4_and_exit_3_is_exit_5_with_no_student_run(w):
    r = w.run(*ENGRAM_ONLY, STUB_PLANT_RC="1")
    assert r.returncode == 4 and not w.mark.exists()
    r2 = w.run(*ENGRAM_ONLY, STUB_PLANT_RC="3", label="t2")
    assert r2.returncode == 5 and not w.mark.exists()


def test_a_dry_run_still_plants_engram_only(w):
    assert w.run(*ENGRAM_ONLY, "--dry-run").returncode == 0
    assert w.plant_log.exists() and not w.mark.exists()


@pytest.mark.parametrize("plant, mode", [
    ([], "plant mode: none"),
    (ENGRAM_ONLY, "plant mode: engram-only (no built-in plant)"),
    (PLANT, "plant mode: both channels"),
])
@needs_linux_wrapper
def test_setup_txt_records_the_plant_mode_on_its_own_line(w, plant, mode):
    assert w.run(*plant).returncode == 0
    lines = (w.runs / "p1-t1" / "setup.txt").read_text().splitlines()
    assert lines.count(mode) == 1 and [l for l in lines if l.startswith("plant mode:")] == [mode]


# BEAM_PARQUET: feed4 needs it in the environment, so the launcher requires it in step 1 (and, as it does for every
# other environment variable, names it). It must name an existing FILE. The launcher hashes it in step 1 against the registered prefix (PROVENANCE.md).
def test_beam_parquet_is_a_required_environment_variable():
    assert "BEAM_PARQUET" in P1S.REQUIRED_ENV


def test_refuses_a_beam_parquet_that_names_a_missing_path(w):
    refusal(w, BEAM_PARQUET=str(w.root / "no-such.parquet"), expect="BEAM_PARQUET")


def test_refuses_a_beam_parquet_that_is_a_directory(w):
    refusal(w, BEAM_PARQUET=str(w.root), expect="BEAM_PARQUET")


def test_the_registered_prefix_is_the_one_stated_in_provenance_md():
    """Read at test time from the document the constant cites, so the constant cannot drift from it."""
    text = open(os.path.join(TOOLS, "..", "PROVENANCE.md")).read()
    stated = re.findall(r"parquet sha256 prefix `([0-9a-f]{12})`", text)
    assert stated == [P1S.REGISTERED_PARQUET_PREFIX], stated


@needs_linux_wrapper
def test_setup_txt_says_which_dataset_check_ran_the_override(w):
    assert w.run().returncode == 0
    lines = (w.runs / "p1-t1" / "setup.txt").read_text().splitlines()
    assert "dataset check: test-only override (P1_TEST_HOOKS)" in lines, lines


def test_setup_txt_says_which_dataset_check_ran_the_registered_prefix(w):
    """Without the hook the real check applies; a stand-in cannot pass it, so call the recorder directly."""
    assert P1S.dataset_check_line({}) == f"dataset check: registered prefix {P1S.REGISTERED_PARQUET_PREFIX}"
    assert P1S.dataset_check_line({"P1_EXPECTED_PARQUET_PREFIX": "x", "P1_TEST_HOOKS": "1"}) \
        == "dataset check: test-only override (P1_TEST_HOOKS)"


def test_write_setup_records_whatever_dataset_check_line_returns(tmp_path, monkeypatch):
    """Binds the CALL: setup.txt must carry dataset_check_line's answer, not a line write_setup builds itself."""
    from types import SimpleNamespace
    q = tmp_path / "q.json"; q.write_text("{}")
    comp = tmp_path / "components.json"; comp.write_text("{}")
    rundir = tmp_path / "rundir"; rundir.mkdir()
    sentinel = "dataset check: SENTINEL-7f3a91c2"
    monkeypatch.setattr(P1S, "dataset_check_line", lambda env: sentinel)
    a = SimpleNamespace(question_file=str(q), components=str(comp))
    c = {"plant_mode": "none", "parquet_sha256": "0" * 64, "rundir": str(rundir)}
    P1S.write_setup(a, c, [], "2026-11-18T00:00:00Z", 0)
    lines = (rundir / "setup.txt").read_text().splitlines()
    assert sentinel in lines, lines


def test_refuses_a_beam_parquet_whose_bytes_do_not_hash_to_the_expected_prefix(w):
    """Step 1, nothing touched: the launcher verifies the dataset like the reading runs did (pilot-run.sh)."""
    w.parquet.write_bytes(b"some other dataset")
    refusal(w, expect=w.parquet_prefix)


def test_the_real_constant_is_the_only_prefix_accepted_without_the_hook(w):
    kw = {"P1_EXPECTED_PARQUET_PREFIX": None}
    refusal(w, expect=P1S.REGISTERED_PARQUET_PREFIX, **kw)


@needs_linux_wrapper
def test_a_parquet_matching_the_expected_prefix_runs_and_setup_txt_records_its_full_sha256(w):
    assert w.run().returncode == 0
    full = P1S.file_sha256(w.parquet)  # the launcher's own function
    lines = (w.runs / "p1-t1" / "setup.txt").read_text().splitlines()
    assert [l for l in lines if full in l and "BEAM_PARQUET" in l], lines


def test_the_docstring_names_both_plant_sets_and_beam_parquet():
    doc = " ".join(open(TOOL, encoding="utf-8").read().split('"""')[1].split())
    for phrase in ("BEAM_PARQUET", "--plant-engram --plant-absent", "engram-only"):
        assert phrase in doc, phrase


# ------------------------------------------------------------------ the sandbox launch module (design A10; the design owner's ruling)
# Every student session goes through sandbox_launch.py. The stub feeder stands in for feed4.py and writes the log line the
# wrapper would (emulate_wrapper), so the module's pre-launch and post-session checks run for real; STUB_SANDBOX picks a
# variant. How the P1_FEED4 hook interacts with the wrapper (a decision recorded in the handoff): the stub is run by the
# module exactly as feed4.py would be, wrapped, with every check live; only the wrapper's own log line is emulated.
SB_NAMES = ["SANDBOX_BINARY", "SANDBOX_BINARY_SHA256", "SANDBOX_MODEL_HOST", "SANDBOX_MODEL_PORT", "SANDBOX_MODEL_ALLOW",
            "SANDBOX_PROTECT"]


def raw_calls(w):
    return [json.loads(l) for l in open(w.root / "stub-raw.jsonl")]


def pairs_of(argv):
    return {x.partition("=")[0]: x.partition("=")[2] for i, x in enumerate(argv[1:], 1) if argv[i - 1] == "--env"}


def setup_text(w):
    return (w.runs / "p1-t1" / "setup.txt").read_text()


def test_sb_a_real_run_without_expect_sandbox_is_refused_in_step_1(w):
    refusal(w, ("--expect-sandbox", None), expect="--expect-sandbox")


def test_sb_a_dry_run_needs_no_expect_sandbox_and_says_so_in_setup_txt(w):
    r = w.run("--dry-run", ("--expect-sandbox", None))
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "sandbox: not used (--dry-run" in setup_text(w)


@pytest.mark.parametrize("text,word", [("", "malformed"), ("wrapper_sha256=abc\nforwarder_sha256=def\n", "malformed")])
def test_sb_a_malformed_expected_file_is_refused_in_step_1(w, text, word):
    w.expected.write_text(text)
    refusal(w, expect=word)


def test_sb_a_missing_expected_file_is_refused_in_step_1(w):
    refusal(w, ("--expect-sandbox", str(w.root / "no-such-file")), expect="cannot be read")


@pytest.mark.parametrize("name", SB_NAMES)
def test_sb_a_missing_sandbox_setting_is_refused_in_step_1_naming_it(w, name):
    refusal(w, expect=name, **{name: None})


def test_sb_a_slot_setting_that_is_not_the_slot_is_refused(w):
    refusal(w, expect="SANDBOX_SLOT", SANDBOX_SLOT=str(w.root / "elsewhere"))


def test_sb_a_model_url_off_the_sandbox_port_is_refused_in_step_1(w):
    refusal(w, expect="port", BEAM_OLLAMA_URL="http://127.0.0.1:%d" % (int(w.env()["SANDBOX_MODEL_PORT"]) + 1))


@needs_linux_wrapper
def test_sb_both_feed4_invocations_go_through_the_module_the_plan_dump_unwrapped_and_the_session_wrapped(w):
    r = w.run()
    assert r.returncode == 0, (r.stdout, r.stderr)
    calls = raw_calls(w)
    dump = [c for c in calls if "--dump-plan" in c]; real = [c for c in calls if "--dump-plan" not in c]
    assert len(dump) == 1 and len(real) == 1
    assert not any(x.startswith("SANDBOX_") for x in dump[0])
    pairs = pairs_of(real[0])
    for n in SB_NAMES + ["SANDBOX_SLOT", "SANDBOX_LOG", "SANDBOX_RO_BINDS", "SANDBOX_RO_ROOT", "SANDBOX_RW_BINDS", "SANDBOX_RW_ROOT"]:
        assert pairs.get(n), n
    assert pairs["SANDBOX_SLOT"] == str(w.slot)
    assert os.path.dirname(pairs["SANDBOX_LOG"]) == str(w.runs / "p1-t1")
    assert pairs["SANDBOX_RW_ROOT"] == str(w.runs / "p1-t1" / "run") and pairs["SANDBOX_RW_BINDS"] == pairs["SANDBOX_RW_ROOT"] + "/proctor"


@needs_linux_wrapper
def test_sb_setup_txt_records_the_log_the_verdict_verbatim_and_the_launch_line_hashes(w):
    assert w.run().returncode == 0
    text = setup_text(w); lines = text.splitlines()
    (logline,) = [l for l in lines if l.startswith("sandbox log: ")]
    name = logline.split(": ", 1)[1]
    assert os.path.isfile(w.runs / "p1-t1" / name) and name.startswith("sandbox-") and name.endswith(".log")
    assert "sandbox verdict: not-flagged" in lines
    assert f"sandbox launch-line wrapper_sha256: {sha(os.path.join(TOOLS, 'student-sandbox.sh'))}" in lines
    assert f"sandbox launch-line forwarder_sha256: {sha(os.path.join(TOOLS, 'sandbox-forward.py'))}" in lines
    assert f"sandbox expected-hashes file: {w.expected.name} (sha256 {sha(w.expected)})" in lines
    assert f"{sha(os.path.join(TOOLS, 'sandbox_launch.py'))}  sandbox_launch.py" in lines
    assert "feed4 override (P1_FEED4)" in text      # the hook is on record, and the stub was wrapped all the same


@needs_linux_wrapper
def test_sb_flagged_is_recorded_verbatim_not_a_stop(w):
    r = w.run(STUB_SANDBOX="unreachable")
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "sandbox verdict: flagged: endpoint unreachable, nothing reached it" in setup_text(w).splitlines()
    assert (w.runs / "p1-t1" / "delivery.txt").exists()


@needs_linux_wrapper
def test_sb_a_log_verdict_refusal_is_exit_3_with_a_stop_line_and_no_answer_is_read(w):
    r = w.run(STUB_SANDBOX="nolaunch")
    assert r.returncode == 3, (r.stdout, r.stderr)
    assert "STOP: sandbox launch module" in r.stdout and "log-verdict refused" in r.stdout
    run = w.runs / "p1-t1"
    assert not (run / "delivery.txt").exists() and not (run / "transcripts").exists()   # nothing of the session was read
    assert (run / "after-hashes.txt").exists() and "final exit 3" in setup_text(w)       # the protected-home proof still ran
    assert "sandbox verdict: none" in setup_text(w)


@needs_linux_wrapper
def test_sb_a_launch_line_hash_that_differs_is_exit_3_naming_it_and_no_answer_is_read(w):
    r = w.run(STUB_SANDBOX="badwrapper")
    assert r.returncode == 3, (r.stdout, r.stderr)
    assert "STOP: sandbox launch module" in r.stdout and "wrapper_sha256" in r.stdout and "0" * 64 in r.stdout
    assert not (w.runs / "p1-t1" / "delivery.txt").exists() and not (w.runs / "p1-t1" / "transcripts").exists()


@pytest.mark.parametrize("which", ["wrapper", "forwarder"])
def test_sb_a_pre_launch_hash_mismatch_refuses_before_the_student_starts(w, which):
    w.expected.write_text("wrapper_sha256=%s\nforwarder_sha256=%s\n" % (
        "0" * 64 if which == "wrapper" else sha(os.path.join(TOOLS, "student-sandbox.sh")),
        "0" * 64 if which == "forwarder" else sha(os.path.join(TOOLS, "sandbox-forward.py"))))
    r = w.run()
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert f"{which}_sha256" in r.stdout and not w.mark.exists() and not w.sbx_log.exists()
    assert [p.name for p in (w.runs / "p1-t1").iterdir() if p.name.startswith("sandbox-")] == []   # no log was made


@needs_linux_wrapper
def test_sb_a_leftover_of_an_earlier_launch_refuses_the_session_and_the_count_is_recorded(w):
    """Round 2: the launch module refuses while anything of an earlier launch is alive. p1-session gives it the state
    directory <BEAM_RUNS_DIR>/sandbox-launches/ and records how many leftovers it found."""
    helper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    try:
        start = open("/proc/%d/stat" % helper.pid).read().rsplit(")", 1)[1].split()[19]
        log = w.root / "earlier.log"
        log.write_text("wrapper-launch time=1 pid=2 wrapper_sha256=%s forwarder_sha256=%s scope_unit=%s1-aa "
                       "forwarder_pid=%d forwarder_start=%s bridge_sock=%s model=h:1\n"
                       % ("a" * 64, "b" * 64, w.unit_prefix, helper.pid, start, w.root / "earlier.sock"))
        state = w.runs / "sandbox-launches"; state.mkdir()
        (state / "earlier.json").write_text(json.dumps({"log": str(log), "state": "open"}))
        r = w.run()
        assert r.returncode == 2, (r.stdout, r.stderr)
        assert str(helper.pid) in r.stdout and not w.mark.exists()
        assert "sandbox leftovers found at launch: 1" in setup_text(w).splitlines()
    finally:
        helper.kill(); helper.wait()


# ---- L1 (the colleague reviewer's read): a test-mode setting reaches the module only under the existing P1_TEST_HOOKS=1 rule
def test_l1_a_test_mode_setting_reaches_the_module_only_under_p1_test_hooks(w):
    import types
    a = types.SimpleNamespace(expect_sandbox=str(w.expected), continue_reading=False, session=SESSION,
                              question_file=str(w.qfile), components=str(w.comps))
    c = {"slot": str(w.slot), "rundir": str(w.runs / "p1-x")}
    env, slot_real = w.env(), os.path.realpath(w.slot)
    assert P1S.sandbox_input(a, env, slot_real, c).allow_test is True            # hooks on: a test run, said explicitly
    no_hooks = {k: v for k, v in env.items() if k != "P1_TEST_HOOKS"}
    with pytest.raises(P1S.Refusal, match="SANDBOX_TEST"):                       # a real run: refused, named, before anything starts
        P1S.sandbox_input(a, no_hooks, slot_real, c)
    real = {k: v for k, v in no_hooks.items() if not k.startswith("SANDBOX_TEST")}
    assert P1S.sandbox_input(a, real, slot_real, c).allow_test is False


@needs_linux_wrapper
def test_l1_the_caps_and_the_test_flags_of_the_launch_line_are_written_to_setup_txt(w):
    assert w.run().returncode == 0
    lines = setup_text(w).splitlines()
    for want in ("sandbox launch-line cap_tasks: 1024", "sandbox launch-line cap_memory: 4294967296",
                 "sandbox launch-line cap_tmp: 2147483648", "sandbox launch-line test_mode: 1", "sandbox launch-line test_exec: 0"):
        assert want in lines, want


@needs_linux_wrapper
def test_b_setup_txt_carries_the_built_path_on_one_line_equal_to_the_path_the_feeder_was_handed(w):
    assert w.run().returncode == 0
    handed = (w.root / "stub-path.txt").read_text().splitlines()
    assert len(handed) == 1                                             # the student run only: the plan dumps are unwrapped
    lines = [l for l in setup_text(w).splitlines() if l.startswith("sandbox feeder PATH: ")]
    assert lines == ["sandbox feeder PATH: " + handed[0]]
    first, *rest = handed[0].split(":")
    assert rest == list(P1S.SL.FEEDER_SYSTEM_DIRS)                  # wrapper directory first, then the fixed list


@needs_linux_wrapper
def test_e3_the_environment_the_feeder_got_is_built_and_its_names_are_in_setup_txt(w):
    """A5, the positive cell at the launcher: a real run's launch SUCCEEDS under the built environment; the names recorded in
    setup.txt are the names the feeder was actually handed; they are the pinned literal's names that the caller set (here only
    BEAM_PARQUET), PATH, and the stub's own STUB_* steering names, and a variable of the caller's that is not listed is absent."""
    r = w.run(NODE_OPTIONS="--no-warnings", BASH_ENV="/nonexistent/rc")
    assert r.returncode == 0, (r.stdout, r.stderr)
    (names,) = [json.loads(l) for l in (w.root / "stub-env.json").read_text().splitlines()]
    assert "NODE_OPTIONS" not in names and "BASH_ENV" not in names
    assert [n for n in names if not n.startswith("STUB_")] == ["BEAM_PARQUET", "PATH"]
    (line,) = [l for l in setup_text(w).splitlines() if l.startswith("sandbox feeder environment names: ")]
    assert line == "sandbox feeder environment names: " + ", ".join(names)
