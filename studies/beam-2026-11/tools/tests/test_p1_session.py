"""p1-session.py cells. Contract-first: written before the tool. Synthetic homes and stub scripts only: no student
model, no Ollama, no real arm home, no network. BEAM_PY is this interpreter (stdlib sqlite3 is all it needs).

Test-only hooks the tool honours (they are documented in the tool's docstring and are never set by a real run):
  P1_FEED4            a stub script run in place of feed4.py (the run and the --dump-plan call)
  P1_PLANT_CONTROL    a stub script run in place of plant-control.py
  P1_UTC_STAMP        a fixed stamp for the aside path
  P1_AFTER_COPY_HOOK  a script run (BEAM_PY script SLOT) between the copy and the copy-fidelity check
  P1_TEST_RAISE       KeyboardInterrupt | SystemExit | Exception: raised once, just after the copy has been verified
Every one of them is refused (exit 2) unless P1_TEST_HOOKS=1 is also set; the cells set it through World.env."""
import hashlib, importlib.util, json, os, shutil, sqlite3, subprocess, sys
import pytest
from conftest import TOOLS

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
a = sys.argv[1:]
def arg(n): return a[a.index(n) + 1]
with open(os.environ["STUB_ARGV"], "a") as f:
    f.write(json.dumps(a) + "\n")
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
with open(os.environ["STUB_PLANT_LOG"], "w") as f:
    f.write(json.dumps({"argv": sys.argv[1:], "exe": sys.executable, "prot": os.environ.get("P1_PROTECTED")}))
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
        self.stub = root / "stub-feed4.py"; self.stub.write_text(STUB_FEED4)
        self.plant = root / "stub-plant.py"; self.plant.write_text(STUB_PLANT)
        self.hook = root / "corrupt-hook.py"; self.hook.write_text(CORRUPT_HOOK)
        self.mark = root / "student-ran.txt"
        self.argv_log = root / "stub-argv.jsonl"
        self.plant_log = root / "plant-log.json"
        self.proc = None

    def env(self, **over):
        e = {"PATH": os.environ["PATH"], "BEAM_PY": sys.executable, "BEAM_ARM_HOME": str(self.slot),
             "BEAM_RUNS_DIR": str(self.runs), "P1_PROTECTED": f"{self.pres}:{self.pres2}",
             "P1_FEED4": str(self.stub), "P1_PLANT_CONTROL": str(self.plant), "P1_UTC_STAMP": STAMP,
             "P1_TEST_HOOKS": "1", "STUB_MARK": str(self.mark), "STUB_ARGV": str(self.argv_log), "STUB_PLANT_LOG": str(self.plant_log)}
        e.update({k: v for k, v in over.items() if v is not None})
        for k, v in over.items():
            if v is None:
                e.pop(k, None)
        return e

    def run(self, *extra, label="t1", end=None, drop=(), **envover):
        args = ["--end-state", str(end or self.pres), "--session", SESSION, "--label", label,
                "--question-file", str(self.qfile), "--components", str(self.comps)]
        for a in extra:
            if isinstance(a, tuple):  # ("--question-file", path) replaces the default
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
@pytest.mark.parametrize("var", ["BEAM_PY", "BEAM_ARM_HOME", "BEAM_RUNS_DIR", "P1_PROTECTED"])
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


def test_the_fake_slot_process_is_stopped_before_the_copy(w):
    proc = w.start_fake_process()
    assert w.run().returncode == 0
    assert proc.wait(timeout=10) is not None


def test_a_pre_existing_slot_is_moved_aside_never_deleted(w):
    old = tree(w.slot)
    assert w.run().returncode == 0
    aside = w.root / f"slot.aside-t1-{STAMP}"
    assert tree(aside) == old and (aside / "old.txt").read_text() == "what the slot held before\n"


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


def test_a_write_into_a_protected_store_is_exit_5_and_names_the_home(w):
    target = os.path.join(w.pres2, ".engram", "knowledge.db")
    r = w.run(STUB_ACTION="protected", STUB_TARGET=target)
    assert r.returncode == 5, (r.returncode, r.stdout, r.stderr)
    assert "PROTECTED CHANGED" in r.stdout
    assert changed_homes_printed(r.stdout) == [os.path.realpath(w.pres2)]


def test_a_write_into_the_slot_only_is_exit_0(w):
    r = w.run(STUB_ACTION="slot")
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    assert "PROTECTED CHANGED" not in r.stdout
    c = sqlite3.connect(f"file:{w.slot}/.engram/knowledge.db?mode=ro", uri=True)
    assert c.execute("select count(*) from nodes where id='stub'").fetchone()[0] == 1
    c.close()


def test_a_change_to_a_protected_memory_file_is_exit_5(w):
    """The memory-folder hashes are part of the compare, not only the store."""
    victim = os.path.join(w.pres, ".claude", "projects", "-p", "memory", "a.md")
    # tamper from the after-copy hook, which runs once the run directory exists
    hook = w.root / "tamper-hook.py"
    hook.write_text(f"open({victim!r}, 'a').write('tampered')\n")
    r = w.run(P1_AFTER_COPY_HOOK=str(hook))
    assert r.returncode == 5 and "PROTECTED CHANGED" in r.stdout
    assert changed_homes_printed(r.stdout) == [os.path.realpath(w.pres)]


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


def test_feed4_nonzero_is_exit_3(w):
    r = w.run(STUB_RC="1")
    assert r.returncode == 3 and w.mark.exists()
    assert (w.runs / "p1-t1" / "after-hashes.txt").exists() and (w.runs / "p1-t1" / "setup.txt").exists()


def test_a_failed_delivery_check_is_exit_1(w):
    r = w.run(STUB_SKIPQ="1")
    assert r.returncode == 1, (r.returncode, r.stdout, r.stderr)
    assert "FAIL" in (w.runs / "p1-t1" / "delivery.txt").read_text()


# ------------------------------------------------------------------ step 6: plant
PLANT = ["--plant-builtin", "BuiltinFactAA", "--plant-engram", "EngramFactBB", "--plant-absent", "AbsentFactCC"]


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


def test_a_setup_txt_write_failure_never_replaces_exit_5(w):
    """setup.txt is made a directory by the hook, so writing it raises; the protected change still decides the code."""
    blocker = w.runs / "p1-t1" / "setup.txt"
    hook = tamper_hook(w, extra=f"import os\nos.makedirs({str(blocker)!r})\n")
    r = w.run(P1_AFTER_COPY_HOOK=hook)
    assert r.returncode == 5, (r.returncode, r.stdout, r.stderr)
    assert "PROTECTED CHANGED" in r.stdout and "setup.txt" in r.stderr


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


def test_a_relative_symlink_that_stays_inside_the_end_state_is_fine(w):
    os.symlink("projects", os.path.join(w.pres, ".claude", "rel-link"))  # like a venv's lib64 -> lib
    r = w.run()
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    assert os.readlink(str(w.slot / ".claude" / "rel-link")) == "projects"


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


def test_a_relative_link_that_climbs_and_comes_back_inside_the_end_state_is_fine(w):
    """work/up -> ../.claude/projects climbs one level but never above the end state's own root."""
    os.symlink("../.claude/projects", os.path.join(w.pres, "work", "up"))
    r = w.run()
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    assert os.readlink(str(w.slot / "work" / "up")) == "../.claude/projects"


# ------------------------------------------------------------------ round 4: the after-hash pass itself failing
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
               "P1_UTC_STAMP": "20261118T000000Z"}


@pytest.mark.parametrize("var", sorted(HOOK_VALUES))
def test_a_test_only_hook_without_p1_test_hooks_is_refused_naming_the_variable(w, var):
    kw = {k: None for k in HOOK_VALUES}  # none of the others
    kw["P1_TEST_HOOKS"] = None
    path = {"P1_FEED4": w.stub, "P1_PLANT_CONTROL": w.plant, "P1_AFTER_COPY_HOOK": w.hook}.get(var)
    kw[var] = str(path) if path else HOOK_VALUES[var]
    refusal(w, expect=var, **kw)


def test_no_hook_variable_and_no_gate_is_an_ordinary_run_that_uses_the_real_tools(w):
    """Without any hook the launcher runs the real feed4.py; with no parquet it fails there, not in step 1."""
    kw = {k: None for k in HOOK_VALUES}; kw["P1_TEST_HOOKS"] = None
    r = w.run("--dry-run", **kw)
    assert "P1_TEST_HOOKS" not in r.stderr  # it was not refused for lack of the gate
    assert (w.runs / "p1-t1").exists()


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
