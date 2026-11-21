"""p1-session.py --continue-reading cells (P1b contract C1 to C8). Contract-first: written before the mode existed.
Synthetic homes and stub scripts only: no student model, no real model server, no real preserved home. The serving
record is read from a stub HTTP server on a loopback port the OS picks; the real-feeder cells (C3) run the real
feed4.py --dump-plan on the synthetic parquet and need a python with pyarrow ($BEAM_PY), else they skip.

Test-only hooks used (documented in the tool's docstring, refused unless P1_TEST_HOOKS=1): P1_FEED4, P1_UTC_STAMP,
P1_EXPECTED_PARQUET_PREFIX. The stub feeder below honours feed4's --turns semantics (an INCLUSIVE END INDEX: it
slices exchanges[start - 1: turns]) and a few mutant behaviours chosen by STUB_PLAN / STUB_DROP / STUB_RC / STUB_ACTION."""
import hashlib, json, os, re, shutil, socket, subprocess, sys, tempfile, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest
from conftest import TOOLS, needs_linux_wrapper
from test_p1_session import (P1S, TOOL, SESSION, STAMP, World, bytes_and_mtimes, make_home, tree)

K_DEFAULT = dict(start="4", through="9", per_round="3")  # exchanges 4..9 = 2 rounds of 3; (4-1)%3 == 0, 6%3 == 0
MODEL = "qwen3.8:27b-128k"  # feed4's default --model; a cell below reads feed4.py to keep this equal

STUB_FEED4_CR = r'''
import json, os, subprocess, sys

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
start, turns, K = int(arg("--start")), int(arg("--turns")), int(arg("--per-round"))  # turns = inclusive END index
resume = "--resume" in a
def plan():
    exs = list(range(start, turns + 1))  # the same slice feed4 takes: exchanges[start - 1: turns]
    out = []
    for r in range(0, len(exs), K):
        grp = exs[r: r + K]
        body = "\n\n".join(f"EX{n}" for n in grp)
        if r == 0 and start == 1:
            body = "BRIEF\n\n" + body
        out.append({"kind": "exchange", "exchanges": grp, "text": body})
    return out
if "--dump-plan" in a:
    p = plan(); mode = os.environ.get("STUB_PLAN") if resume else None
    if mode == "preamble":
        p[0]["text"] = "RESUMED SESSION NOTE\n\n" + p[0]["text"]
    elif mode == "compact":
        p.append({"kind": "compact", "exchanges": [], "text": "/compact"})
    elif mode == "question":
        p.append({"kind": "question", "exchanges": [], "text": "Q", "id": "x"})
    elif mode == "short":
        p = p[:-1]
    elif mode == "shifted":  # same texts, exchanges labelled one too high
        for m in p:
            m["exchanges"] = [e + 1 for e in m["exchanges"]]
    elif mode == "reordered":
        p.reverse()
    json.dump(p, sys.stdout); sys.exit(0)
with open(os.environ["STUB_MARK"], "a") as f:
    f.write("student run\n")
emulate_wrapper(a)
out = arg("--out"); os.makedirs(out, exist_ok=True)
p = plan()
rows = [{"i": n + 1, "kind": "exchange", "session_id": arg("--resume"), "is_error": False, "exchanges": m["exchanges"],
         "per_round": K} for n, m in enumerate(p)]
if os.environ.get("STUB_DROP"):
    rows = rows[:-1]
with open(os.path.join(out, "turns.jsonl"), "w") as f:
    f.write("".join(json.dumps(r) + "\n" for r in rows))
with open(os.path.join(out, "events.jsonl"), "w") as f:
    for r in rows:
        f.write(json.dumps({"type": "assistant"}) + "\n" + json.dumps({"type": "result"}) + "\n")
act = os.environ.get("STUB_ACTION")
if act == "protected":
    import sqlite3
    c = sqlite3.connect(os.environ["STUB_TARGET"] + "/.engram/knowledge.db")
    c.execute("insert into nodes values ('stub', 'a stub row')"); c.commit(); c.close()
if act == "survivor":  # a process that ignores SIGTERM and whose command line holds <slot>/.engram/ outlives the stop steps
    import time  # the child writes the pid file only AFTER it ignores SIGTERM, so the launcher's stop step cannot beat it
    subprocess.Popen([sys.executable, "-c", "import os, signal, sys, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                      "open(sys.argv[2], 'w').write(str(os.getpid())); time.sleep(60)",
                      a[a.index("--arm-home") + 1] + "/.engram/survivor", os.environ["STUB_PIDFILE"]], start_new_session=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # not the test's pipes
    for _ in range(100):
        if os.path.exists(os.environ["STUB_PIDFILE"]) and open(os.environ["STUB_PIDFILE"]).read():
            break
        time.sleep(0.05)
sys.exit(int(os.environ.get("STUB_RC", "0")))
'''


# ------------------------------------------------------------------------------------------- a stub model server
@pytest.fixture
def ollama():
    # the NON-matching entry comes first, so a digest taken from models[0] is wrong and the C5 cell sees it
    state = {"version": "0.9.9", "models": [{"name": "other:1b", "digest": "sha256:ffff"},
                                            {"name": MODEL, "digest": "sha256:abc123def456"}], "hits": []}

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            state["hits"].append(self.path)
            if self.path == "/api/version":
                body = {"version": state["version"]}
            elif self.path == "/api/tags":
                body = {"models": state["models"]}
            else:
                self.send_response(404); self.end_headers(); return
            data = json.dumps(body).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    host, port = srv.server_address
    state["url"] = f"http://{host}:{port}"
    yield state
    srv.shutdown(); srv.server_close()


def dead_url():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); host, port = s.getsockname(); s.close()
    return f"http://{host}:{port}"


# ----------------------------------------------------------------------------------------------------- the world
@pytest.fixture
def w(tmp_path):
    world = World(tmp_path)
    world.cr_stub = tmp_path / "stub-feed4-cr.py"; world.cr_stub.write_text(STUB_FEED4_CR)
    world.saved = tmp_path / "saved-end"
    # the start state's own record (design owner's ruling on F5): a verdict line beside it. Without one the reader refuses.
    open(str(world.pres) + ".verdict.txt", "w").write("sandbox verdict: not-flagged\n")
    yield world
    if world.proc is not None and world.proc.poll() is None:
        world.proc.kill()
    if world.proc is not None:
        world.proc.wait()


def store_sha(home):
    return P1S.protected_store_hash(str(home))[0]


def cr_args(w, over=None):
    d = {"--end-state": str(w.pres), "--session": SESSION, "--label": "t1", "--components": str(w.comps),
         "--continue-reading": True, "--start": K_DEFAULT["start"], "--through": K_DEFAULT["through"],
         "--per-round": K_DEFAULT["per_round"], "--save-end-state": str(w.saved),
         "--expect-store-sha256": store_sha(w.pres), "--expect-sandbox": str(w.expected)}
    for k, v in (over or {}).items():
        if v is None:
            d.pop(k, None)
        else:
            d[k] = v
    out = []
    for k, v in d.items():
        out += [k] if v is True else [k, v]
    return out


def cr_run(w, over=None, extra=(), ollama_url=None, **envover):
    e = w.env(P1_FEED4=str(w.cr_stub), **envover)
    if ollama_url:
        e["BEAM_OLLAMA_URL"] = ollama_url
        e["SANDBOX_MODEL_PORT"] = ollama_url.rsplit(":", 1)[1]   # the module refuses a model URL off the sandbox port
    return subprocess.run([sys.executable, TOOL, *cr_args(w, over), *extra], capture_output=True, text=True, env=e)


def cr_refusal(w, over=None, extra=(), expect=None, ollama_url=None, pre_existing=False, **envover):
    """Exit 2, the expected words, and NOTHING touched: protected homes and the end state byte-equal (bytes and mtimes)."""
    w.start_fake_process()
    before = w.snapshot()
    bm = {h: bytes_and_mtimes(h) for h in (w.pres, w.pres2)}
    r = cr_run(w, over, extra, ollama_url=ollama_url, **envover)
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    if expect:
        assert expect in r.stdout + r.stderr, (expect, r.stdout, r.stderr)
    w.assert_untouched(before)
    assert {h: bytes_and_mtimes(h) for h in (w.pres, w.pres2)} == bm
    if not pre_existing:  # the cells that plant the save path / hashes file themselves expect them to stay as planted
        assert not w.saved.exists() and not os.path.lexists(str(w.saved) + ".hashes.txt")
    return r


def setup_lines(w, label="t1"):
    return open(w.runs / f"p1-{label}" / "setup.txt").read().splitlines()


def argv_calls(w):
    return [json.loads(l) for l in open(w.argv_log)]


# =============================================================================================================== C1
def test_c1_continue_reading_is_refused_with_a_question_file(w):
    cr_refusal(w, extra=("--question-file", str(w.qfile)), expect="--continue-reading cannot be combined with --question-file")


@pytest.mark.parametrize("flags", [["--plant-builtin", "x"], ["--plant-engram", "x"], ["--plant-absent", "x"],
                                   ["--plant-question", "x"]])
def test_c1_continue_reading_is_refused_with_every_plant_flag(w, flags):
    cr_refusal(w, extra=flags, expect=f"--continue-reading cannot be combined with {flags[0]}")


@pytest.mark.parametrize("flag", ["--start", "--through", "--per-round", "--save-end-state", "--expect-store-sha256"])
def test_c1_continue_reading_requires_each_of_its_flags_naming_it(w, flag):
    cr_refusal(w, over={flag: None}, expect=f"--continue-reading requires {flag}")


@pytest.mark.parametrize("flag,val", [("--start", "4"), ("--through", "9"), ("--per-round", "3"),
                                      ("--save-end-state", "x"), ("--expect-store-sha256", "x"),
                                      ("--expect-serving", "x")])
def test_c1_the_continue_flags_are_refused_without_continue_reading(w, flag, val):
    w.start_fake_process(); before = w.snapshot()
    r = w.run(flag, val)
    assert r.returncode == 2 and f"{flag} is only valid with --continue-reading" in r.stderr + r.stdout, (r.returncode, r.stderr)
    w.assert_untouched(before)


def test_c1_without_continue_reading_the_question_file_is_still_required(w):
    args = ["--end-state", str(w.pres), "--session", SESSION, "--label", "t1", "--components", str(w.comps)]
    r = subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True, env=w.env())
    assert r.returncode == 2 and "the following arguments are required: --question-file" in r.stderr


# =============================================================================================================== C2
@pytest.mark.parametrize("start,through,k,words", [
    ("5", "10", "3", "round boundary"),          # (5-1) % 3 != 0
    ("4", "8", "3", "partial last round"),       # (8-4+1) % 3 != 0
    ("1", "9", "3", "start must be at least 2"),
    ("0", "9", "3", "start must be at least 2"),
    ("4", "3", "1", "through must not be below start"),
    ("4", "9", "0", "per-round must be at least 1"),
    ("4", "9", "-3", "per-round must be at least 1")])
def test_c2_refuses_a_bad_range_with_its_own_reason(w, start, through, k, words):
    cr_refusal(w, over={"--start": start, "--through": through, "--per-round": k}, expect=words)


def test_c2_refuses_a_store_hash_that_differs_from_expected(w):
    r = cr_refusal(w, over={"--expect-store-sha256": "0" * 64}, expect="--expect-store-sha256")
    assert store_sha(w.pres) in r.stdout + r.stderr  # both hashes are shown


def test_c2_refuses_a_save_path_that_exists(w):
    w.saved.mkdir()
    cr_refusal(w, expect="already exists", pre_existing=True)


def test_c2_refuses_a_hashes_file_that_exists(w):
    open(str(w.saved) + ".hashes.txt", "w").write("x")
    cr_refusal(w, expect="hashes", pre_existing=True)


def test_c2_refuses_a_save_path_inside_a_protected_home(w):
    cr_refusal(w, over={"--save-end-state": str(w.pres2) + "/work/saved"}, expect="protected")


def test_c2_refuses_a_save_path_inside_the_end_state(w):
    cr_refusal(w, over={"--save-end-state": str(w.pres) + "/work/saved"}, expect="protected")


def test_c2_refuses_a_save_path_through_a_symlink_into_a_protected_home(w):
    link = w.root / "lnk"; link.symlink_to(w.pres2)
    cr_refusal(w, over={"--save-end-state": str(link) + "/saved"}, expect="protected")


def test_c2_refuses_a_save_path_inside_the_slot(w):
    cr_refusal(w, over={"--save-end-state": str(w.slot) + "/saved"}, expect="slot")


def test_c2_refuses_a_save_path_whose_parent_does_not_exist(w):
    cr_refusal(w, over={"--save-end-state": str(w.root / "no-dir" / "saved")}, expect="parent")


def test_c2_refuses_an_expect_serving_file_that_differs(w, ollama):
    exp = w.root / "expect-serving.txt"
    exp.write_text("serving: ollama version 0.1.0\nserving: model " + MODEL + "\nserving: model digest sha256:abc123def456\n")
    cr_refusal(w, over={"--expect-serving": str(exp)}, ollama_url=ollama["url"], expect="--expect-serving")


# =============================================================================================================== C3
def test_c3_an_honest_feeder_passes_the_plan_check_and_the_plan_is_kept(w, ollama):
    r = cr_run(w, extra=("--dry-run",), ollama_url=ollama["url"])
    assert r.returncode == 0, (r.stdout, r.stderr)
    plan = json.load(open(w.runs / "p1-t1" / "plan.json"))
    assert [m["exchanges"] for m in plan] == [[4, 5, 6], [7, 8, 9]] and all(m["kind"] == "exchange" for m in plan)
    assert "step 7 plan check: exit 0" in setup_lines(w)


def test_c3_the_dumps_use_the_inclusive_end_index_and_a_full_run_comparison(w, ollama):
    cr_run(w, extra=("--dry-run",), ollama_url=ollama["url"])
    dumps = [c for c in argv_calls(w) if "--dump-plan" in c]
    assert len(dumps) == 2
    cont = next(c for c in dumps if "--resume" in c); full = next(c for c in dumps if "--resume" not in c)
    def val(c, f): return c[c.index(f) + 1]
    assert (val(cont, "--resume"), val(cont, "--start"), val(cont, "--turns"), val(cont, "--per-round")) == (SESSION, "4", "9", "3")
    assert (val(full, "--start"), val(full, "--turns"), val(full, "--per-round")) == ("1", "9", "3")
    for c in dumps:
        assert "--force-compact" not in c and "--question-file" not in c and "--questions" not in c


@pytest.mark.parametrize("mode", ["preamble", "compact", "question", "short", "shifted", "reordered"])
def test_c3_a_mutant_feeder_fails_the_plan_check_with_exit_3_and_no_student_run(w, ollama, mode):
    r = cr_run(w, ollama_url=ollama["url"], STUB_PLAN=mode)
    assert r.returncode == 3, (r.returncode, r.stdout, r.stderr)
    assert "STOP: the continue plan" in r.stdout
    assert not w.mark.exists(), "a student run started after a failed plan check"
    assert "step 7 plan check: exit 3" in setup_lines(w)
    assert not w.saved.exists()


# the real feeder: feed4.py --dump-plan on the synthetic parquet (8 exchanges: 2 sessions of 4), conv 9
def comps_for_real(w):
    lines = [f"{hashlib.sha256(open(os.path.join(TOOLS, n), 'rb').read()).hexdigest()}  {label}"
             for n, label in (("feed4.py", "feed4.py"), ("feed.py", "imported module: feed.py"))]
    p = w.root / "real-components.txt"; p.write_text("\n".join(lines) + "\n")
    return str(p)


def real_dump(arrow_python, parquet, *extra):
    env = {"PATH": os.environ["PATH"], "BEAM_PARQUET": parquet, "BEAM_OLLAMA_URL": dead_url()}
    out = tempfile.mkdtemp(prefix="p1c-dump-")
    r = subprocess.run([arrow_python, "-I", os.path.join(TOOLS, "feed4.py"), "--arm-home", out + "/slot", "--out", out + "/out",
                        "--conv", "9", *extra, "--dump-plan"], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def real_world(w, arrow_python, synthetic_parquet):
    """The launcher over the REAL feed4.py (no P1_FEED4) and the synthetic parquet."""
    prefix = P1S.file_sha256(synthetic_parquet)[:12]
    return dict(BEAM_PY=arrow_python, BEAM_PARQUET=synthetic_parquet, P1_EXPECTED_PARQUET_PREFIX=prefix, P1_FEED4=None)


def real_run(w, arrow_python, synthetic_parquet, ollama, over=None, extra=("--dry-run",)):
    over = dict(over or {}); over.setdefault("--components", comps_for_real(w))
    e = w.env(**real_world(w, arrow_python, synthetic_parquet)); e["BEAM_OLLAMA_URL"] = ollama["url"]
    return subprocess.run([sys.executable, TOOL, *cr_args(w, over), *extra], capture_output=True, text=True, env=e)


@pytest.mark.parametrize("start,through,k", [(3, 8, 2), (5, 8, 4), (2, 7, 1)])
def test_c3_the_real_feeder_continue_plan_equals_the_full_plans_exchanges_n_to_m(w, ollama, arrow_python, synthetic_parquet,
                                                                                 start, through, k):
    over = {"--start": str(start), "--through": str(through), "--per-round": str(k)}
    r = real_run(w, arrow_python, synthetic_parquet, ollama, over)
    assert r.returncode == 0, (r.stdout, r.stderr)
    cont = json.load(open(w.runs / "p1-t1" / "plan.json"))
    full = real_dump(arrow_python, synthetic_parquet, "--start", "1", "--turns", str(through), "--per-round", str(k))
    resumed = real_dump(arrow_python, synthetic_parquet, "--resume", SESSION, "--start", str(start), "--turns", str(through),
                        "--per-round", str(k))
    assert cont == resumed
    assert len(cont) == (through - start + 1) // k
    assert [e for m in cont for e in m["exchanges"]] == list(range(start, through + 1))
    assert cont == full[(start - 1) // k: through // k]          # byte-equal messages, same rounds
    assert all(m["kind"] == "exchange" for m in cont)


def test_c3_a_wrong_turns_count_instead_of_the_end_index_is_visible_on_the_real_feeder(arrow_python, synthetic_parquet):
    """The mistake the first spec made: --turns (M-N+1) with --start N selects nothing (feed4 slices [N-1:turns])."""
    wrong = real_dump(arrow_python, synthetic_parquet, "--resume", SESSION, "--start", "5", "--turns", "4", "--per-round", "2")
    right = real_dump(arrow_python, synthetic_parquet, "--resume", SESSION, "--start", "5", "--turns", "8", "--per-round", "2")
    assert wrong == [] and [m["exchanges"] for m in right] == [[5, 6], [7, 8]]


# =============================================================================================================== C4
@needs_linux_wrapper
def test_c4_the_run_is_feed4_with_exactly_the_contract_arguments(w, ollama):
    r = cr_run(w, ollama_url=ollama["url"])
    assert r.returncode == 0, (r.stdout, r.stderr)
    runs = [c for c in argv_calls(w) if "--dump-plan" not in c]
    assert len(runs) == 1
    assert runs[0] == ["--arm-home", str(w.slot), "--out", str(w.runs / "p1-t1" / "run"), "--conv", "9", "--resume", SESSION,
                       "--start", "4", "--turns", "9", "--per-round", "3", "--env", "CLAUDE_CODE_MAX_CONTEXT_TOKENS=131072",
                       "--expect-components", str(w.comps)]
    assert w.mark.read_text() == "student run\n"


@needs_linux_wrapper
def test_c4_the_slot_is_a_copy_of_the_end_state_and_the_end_state_is_not_opened_for_writing(w, ollama):
    before = bytes_and_mtimes(w.pres)
    r = cr_run(w, ollama_url=ollama["url"])
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert os.path.exists(w.slot / ".disposable-copy") and bytes_and_mtimes(w.pres) == before


# =============================================================================================================== C5
@needs_linux_wrapper
def test_c5_setup_txt_records_the_server_version_the_model_and_its_digest(w, ollama):
    r = cr_run(w, ollama_url=ollama["url"])
    assert r.returncode == 0, (r.stdout, r.stderr)
    lines = setup_lines(w)
    assert "serving: ollama version 0.9.9" in lines
    assert f"serving: model {MODEL}" in lines
    assert f"serving: model digest sha256:abc123def456" in lines   # the entry whose name matches, not the other one


def test_c5_the_default_model_recorded_is_the_one_feed4_uses():
    src = open(os.path.join(TOOLS, "feed4.py")).read()
    m = re.search(r'"--model", default="([^"]+)"', src)
    assert m and m.group(1) == P1S.SERVING_MODEL == MODEL


@needs_linux_wrapper
def test_c5_an_expect_serving_file_equal_to_the_record_is_accepted(w, ollama):
    exp = w.root / "expect-serving.txt"
    exp.write_text("serving: ollama version 0.9.9\nserving: model " + MODEL + "\nserving: model digest sha256:abc123def456\n")
    r = cr_run(w, over={"--expect-serving": str(exp)}, ollama_url=ollama["url"])
    assert r.returncode == 0, (r.stdout, r.stderr)


def test_c5_a_server_that_does_not_answer_is_exit_3_with_a_named_line_and_nothing_touched(w):
    w.start_fake_process(); before = w.snapshot()
    r = cr_run(w, ollama_url=dead_url())
    assert r.returncode == 3, (r.returncode, r.stdout, r.stderr)
    assert "SERVING RECORD FAILED" in r.stdout + r.stderr
    w.assert_untouched(before)
    assert not w.saved.exists()


def test_c5_a_model_missing_from_the_tags_is_exit_3_with_a_named_line(w, ollama):
    ollama["models"] = [{"name": "other:1b", "digest": "sha256:ffff"}]
    r = cr_run(w, ollama_url=ollama["url"])
    assert r.returncode == 3 and "SERVING RECORD FAILED" in r.stdout + r.stderr and MODEL in r.stdout + r.stderr
    assert not w.mark.exists()


# =============================================================================================================== C6
@needs_linux_wrapper
def test_c6_a_good_run_saves_a_copy_of_the_slot_and_hashes_it(w, ollama):
    r = cr_run(w, ollama_url=ollama["url"])
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert w.saved.is_dir() and w.slot.is_dir(), "the slot must still exist: the save is a copy, never a move"
    slot_tree = tree(w.slot); assert slot_tree.pop(".disposable-copy") is not None  # the one intended difference (R2)
    assert tree(w.saved) == slot_tree
    sha_saved = P1S.protected_store_hash(str(w.saved))[0]
    hashes = open(str(w.saved) + ".hashes.txt").read()
    assert hashes == P1S.home_record(str(w.saved)) and f"sha256={sha_saved}" in hashes
    assert "a.md" in hashes  # the auto-memory file hashes ride along
    sl = open(w.runs / "p1-t1" / "setup.txt").read()
    assert f"saved end state: {w.saved}" in sl and hashes in sl


@pytest.mark.parametrize("name,envover,code", [("feed4 failed", {"STUB_RC": "1"}, 3), ("delivery failed", {"STUB_DROP": "1"}, 1)])
@needs_linux_wrapper
def test_c6_a_failed_run_creates_no_saved_end_state(w, ollama, name, envover, code):
    r = cr_run(w, ollama_url=ollama["url"], **envover)
    assert r.returncode == code, (r.returncode, r.stdout, r.stderr)
    assert not w.saved.exists() and not os.path.lexists(str(w.saved) + ".hashes.txt")


def test_c6_a_dry_run_saves_nothing(w, ollama):
    assert cr_run(w, extra=("--dry-run",), ollama_url=ollama["url"]).returncode == 0
    assert not w.saved.exists() and not os.path.lexists(str(w.saved) + ".hashes.txt")


@needs_linux_wrapper
def test_c6_a_saved_end_state_is_removed_with_a_line_when_a_protected_home_changed(w, ollama):
    r = cr_run(w, ollama_url=ollama["url"], STUB_ACTION="protected", STUB_TARGET=str(w.pres2))
    assert r.returncode == 5, (r.stdout, r.stderr)
    assert not w.saved.exists() and not os.path.lexists(str(w.saved) + ".hashes.txt")
    assert f"saved end state removed: {w.saved}" in r.stdout and f"saved end state removed: {w.saved}" in setup_lines(w)


# =============================================================================================================== C7
@needs_linux_wrapper
def test_c7_after_equals_before_and_the_saved_end_state_is_not_in_the_before_set(w, ollama):
    bm = {h: bytes_and_mtimes(h) for h in (w.pres, w.pres2)}
    r = cr_run(w, ollama_url=ollama["url"])
    assert r.returncode == 0, (r.stdout, r.stderr)
    run = w.runs / "p1-t1"
    before, after = (run / "before-hashes.txt").read_text(), (run / "after-hashes.txt").read_text()
    assert before == after and f"home {w.pres}\n" in before and f"home {w.pres2}\n" in before
    assert str(w.saved) not in before and str(w.saved) not in after
    assert {h: bytes_and_mtimes(h) for h in (w.pres, w.pres2)} == bm


@needs_linux_wrapper
def test_c7_a_write_into_the_end_state_during_a_continue_run_is_exit_5_naming_it(w, ollama):
    r = cr_run(w, ollama_url=ollama["url"], STUB_ACTION="protected", STUB_TARGET=str(w.pres))
    assert r.returncode == 5, (r.stdout, r.stderr)
    assert f"changed home: {w.pres}" in r.stdout and "PROTECTED CHANGED: 1 home(s)" in r.stdout


# =============================================================================================================== C8
@needs_linux_wrapper
def test_c8_a_reading_run_that_dropped_a_round_is_exit_1_from_the_reading_delivery_check(w, ollama):
    r = cr_run(w, ollama_url=ollama["url"], STUB_DROP="1")
    assert r.returncode == 1 and "FAIL" in (w.runs / "p1-t1" / "delivery.txt").read_text()
    assert any("reading-delivery-check.py" in l for l in setup_lines(w))
    assert any("step 9 after the run (delivery check): exit 1" == l for l in setup_lines(w))


def test_c8_the_question_delivery_check_is_unchanged_and_still_refuses_reading_turns():
    src = open(os.path.join(TOOLS, "answer-delivery-check.py")).read()
    assert "no reading turns" in src and 'r.get("kind") in ("exchange", "setup")' in src


# ======================================================================================================= round 2 (R1-R6)
FAKE_CP = """#!{py}
import os, subprocess, sys
real, target, mode = os.environ["REAL_CP"], os.environ.get("FAKE_CP_TARGET"), os.environ.get("FAKE_CP_MODE")
if not target or sys.argv[-1] != target:
    os.execv(real, [real] + sys.argv[1:])
if mode == "fail":  # a copy that dies half way: a partial tree is left behind
    os.makedirs(target, exist_ok=True); open(os.path.join(target, "partial"), "w").write("x"); sys.exit(1)
rc = subprocess.call([real] + sys.argv[1:])
db = os.path.join(target, ".engram", "knowledge.db")
if mode == "mutate":  # the copy finishes but its store is not the slot's
    import sqlite3
    c = sqlite3.connect(db); c.execute("insert into nodes values ('copy', 'not in the slot')"); c.commit(); c.close()
elif mode == "corrupt":  # the copy finishes but its store cannot be read
    open(db, "wb").write(b"not a database")
sys.exit(rc)
"""


def fake_cp_env(w, mode):
    d = w.root / "fakebin"; d.mkdir(exist_ok=True)
    f = d / "cp"; f.write_text(FAKE_CP.format(py=sys.executable)); f.chmod(0o755)
    return dict(PATH=f"{d}:{w.path}", REAL_CP=shutil.which("cp"), FAKE_CP_TARGET=str(w.saved), FAKE_CP_MODE=mode)


def no_saved(w):
    return (not os.path.lexists(str(w.saved)) and not os.path.lexists(str(w.saved) + ".hashes.txt")
            and not os.path.lexists(str(w.saved) + ".verdict.txt"))


# ---- R1: quiescence before the save, and the saved copy's store hash against the slot's
@needs_linux_wrapper
def test_r1_a_live_slot_process_at_save_time_refuses_the_save_naming_the_pids_and_creates_nothing(w, ollama):
    pidfile = w.root / "survivor.pid"
    try:
        r = cr_run(w, ollama_url=ollama["url"], STUB_ACTION="survivor", STUB_PIDFILE=str(pidfile))
        pid = int(pidfile.read_text())
        assert r.returncode == 3, (r.returncode, r.stdout, r.stderr)
        assert "STOP:" in r.stdout and str(pid) in r.stdout and "still running" in r.stdout
        assert no_saved(w)
        assert "step 9b save the end state: exit 3" in setup_lines(w)
    finally:
        if pidfile.exists():
            try:
                os.kill(int(pidfile.read_text()), 9)
            except OSError:
                pass


@needs_linux_wrapper
def test_r1_a_saved_copy_whose_store_hash_differs_from_the_slots_is_removed_with_a_line_exit_3(w, ollama):
    r = cr_run(w, ollama_url=ollama["url"], **fake_cp_env(w, "mutate"))
    assert r.returncode == 3, (r.returncode, r.stdout, r.stderr)
    assert "differs from the slot" in r.stdout and no_saved(w)
    assert f"saved end state removed: {w.saved}" in r.stdout and f"saved end state removed: {w.saved}" in setup_lines(w)
    assert "step 9b save the end state: exit 3" in setup_lines(w)


# ---- R2: a preserved end state carries no disposable marker
@needs_linux_wrapper
def test_r2_the_saved_end_state_has_no_marker_the_slot_keeps_its_own_and_setup_says_so(w, ollama):
    r = cr_run(w, ollama_url=ollama["url"])
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert not os.path.lexists(w.saved / ".disposable-copy") and os.path.isfile(w.slot / ".disposable-copy")
    assert any(".disposable-copy" in l and "removed" in l for l in setup_lines(w))


@needs_linux_wrapper
def test_r2_plant_control_refuses_the_saved_end_state_on_its_missing_marker(w, ollama):
    from test_plant_control import run_tool
    assert cr_run(w, ollama_url=ollama["url"]).returncode == 0
    r = run_tool(w.saved, w.root / "ev")  # the real tool, no P1_PROTECTED: a marker refusal comes first and writes nothing
    assert r.returncode == 2 and ".disposable-copy marker" in r.stderr, (r.returncode, r.stderr)


# ---- R3: the save-failure branches
@needs_linux_wrapper
def test_r3_a_failing_copy_is_exit_3_leaves_no_saved_path_and_says_it_removed_the_partial_one(w, ollama):
    r = cr_run(w, ollama_url=ollama["url"], **fake_cp_env(w, "fail"))
    assert r.returncode == 3, (r.returncode, r.stdout, r.stderr)
    assert "copying the slot to --save-end-state failed" in r.stdout and no_saved(w)
    assert f"saved end state removed: {w.saved}" in setup_lines(w)
    assert "step 9b save the end state: exit 1" in setup_lines(w)  # a copy failure records cp's own exit code, like step 5


@needs_linux_wrapper
def test_r3_a_saved_store_that_cannot_be_hashed_is_exit_3_with_no_saved_path_and_a_removal_line(w, ollama):
    r = cr_run(w, ollama_url=ollama["url"], **fake_cp_env(w, "corrupt"))
    assert r.returncode == 3, (r.returncode, r.stdout, r.stderr)
    assert "hashing the saved end state failed" in r.stdout and no_saved(w)
    assert f"saved end state removed: {w.saved}" in setup_lines(w)
    assert "step 9b save the end state: exit 3" in setup_lines(w)


# ---- R5: the save path against the aside path
@pytest.mark.parametrize("suffix", ["", "/saved"])
def test_r5_a_save_path_equal_to_or_inside_the_aside_path_is_refused_at_step_1(w, suffix):
    aside = f"{w.slot}.aside-t1-{STAMP}"
    cr_refusal(w, over={"--save-end-state": aside + suffix}, expect="the aside path")


# ======================================================================================================= round 3 (R7-R10)
def hook_script(w, name, body):
    p = w.root / name; p.write_text("import os, shutil, sys\n" + body); return str(p)


def root_ids(root):
    """{(path, inode)} for everything under root, links not followed: a path that is new, or is the same name on a new inode
    (the slot, which is moved aside and recreated), counts as created."""
    out = set()
    for dp, dns, fns in os.walk(str(root)):
        for n in dns + fns:
            full = os.path.join(dp, n); out.add((full, os.lstat(full).st_ino))
    return out


def minimal_roots(paths):
    return {p for p in paths if not any(q != p and P1S.under(p, q) for q in paths)}


# ---- R7: the save and hashes paths are disjoint from EVERY path the launcher creates, moves, writes into or protects
def test_r7_a_save_path_equal_to_the_run_directory_is_refused_at_step_1_and_nothing_is_touched(w, ollama):
    cr_refusal(w, over={"--save-end-state": str(w.runs / "p1-t1")}, ollama_url=ollama["url"], expect="run directory")


def test_r7_a_label_that_makes_the_hashes_path_equal_the_run_directory_is_refused(w, ollama):
    cr_refusal(w, over={"--label": "x.hashes.txt", "--save-end-state": str(w.runs / "p1-x")}, ollama_url=ollama["url"],
               expect="run directory")


def test_r7_a_save_path_inside_the_run_directory_is_refused_for_that_reason(w, ollama):
    cr_refusal(w, over={"--save-end-state": str(w.runs / "p1-t1" / "saved")}, ollama_url=ollama["url"], expect="run directory")


def test_r7_a_save_path_containing_the_run_directory_is_refused(w, ollama):
    outer = w.root / "outer"  # BEAM_RUNS_DIR does not exist yet, so the run would create outer/runs/p1-t1 beneath the save path
    cr_refusal(w, over={"--save-end-state": str(outer)}, ollama_url=ollama["url"], expect="run directory",
               BEAM_RUNS_DIR=str(outer / "runs"))


def test_r7_a_symlinked_ancestor_that_resolves_to_the_run_directory_is_refused(w, ollama):
    link = w.root / "lnk"; link.symlink_to(w.runs)  # lnk/p1-t1 IS runs/p1-t1 once links are resolved
    cr_refusal(w, over={"--save-end-state": str(link / "p1-t1")}, ollama_url=ollama["url"], expect="run directory")


def test_r7_a_symlinked_ancestor_that_resolves_into_the_run_directory_is_refused(w, ollama):
    link = w.root / "lnk"; link.symlink_to(w.runs / "p1-t1")  # dangling now: the run directory is made later
    cr_refusal(w, over={"--save-end-state": str(link / "saved")}, ollama_url=ollama["url"], expect="run directory")


def launcher_paths_for(w):
    prot = [os.path.realpath(w.pres), os.path.realpath(w.pres2)]
    return P1S.launcher_paths(str(w.slot), str(w.runs), "t1", STAMP, os.path.realpath(w.pres), prot), prot


def test_r7_the_path_set_equals_what_main_really_creates_in_a_dry_run(w, ollama, tmp_path_factory):
    """The binding cell: the function's CREATED set is exactly the roots of everything a dry run creates (the run directory,
    the aside path, the slot recreated), and its PROTECTED set is the protected homes, byte-equal afterwards. A path main() starts
    creating without the function being told, or a path the function lists that main() never makes, goes red here."""
    paths, prot = launcher_paths_for(w)
    created = {os.path.realpath(p) for role, p in paths if role in P1S.CREATED_ROLES}
    protects = {os.path.realpath(p) for role, p in paths if role not in P1S.CREATED_ROLES}
    assert protects == set(prot)
    (w.root / "tmp").mkdir()
    before, bm = root_ids(w.root), {h: bytes_and_mtimes(h) for h in (w.pres, w.pres2)}
    elsewhere = tmp_path_factory.mktemp("elsewhere")  # the stub feeder's own argv log is test scaffolding, kept out of the walk
    r = cr_run(w, extra=("--dry-run",), ollama_url=ollama["url"], STUB_ARGV=str(elsewhere / "argv.jsonl"), TMPDIR=str(w.root / "tmp"))
    assert r.returncode == 0, (r.stdout, r.stderr)
    new = {p for p, _ in root_ids(w.root) - before}
    assert {os.path.realpath(p) for p in minimal_roots(new)} == created
    assert {h: bytes_and_mtimes(h) for h in (w.pres, w.pres2)} == bm


def test_r7_the_function_lists_the_first_missing_ancestor_of_the_run_directory_when_the_runs_directory_is_absent(w):
    paths = P1S.launcher_paths(str(w.slot), str(w.root / "no" / "runs"), "t1", STAMP, str(w.pres), [os.path.realpath(w.pres)])
    assert os.path.realpath(w.root / "no") in {os.path.realpath(p) for role, p in paths if role in P1S.CREATED_ROLES}


# ---- R8: every create under a caller-chosen path is exclusive, and removal touches only what this run created
def plant_hook(w, name, body):
    return hook_script(w, name, "save = os.environ['R8_SAVE']\n" + body)


@needs_linux_wrapper
def test_r8_a_save_path_planted_after_step_1_is_exit_3_and_the_planted_path_is_byte_identical(w, ollama):
    hook = plant_hook(w, "plant-save.py", "os.makedirs(os.path.join(save, 'mine'))\nopen(os.path.join(save, 'mine', 'f'), 'w').write('planted')\n")
    r = cr_run(w, ollama_url=ollama["url"], P1_AFTER_COPY_HOOK=hook, R8_SAVE=str(w.saved))
    assert r.returncode == 3, (r.returncode, r.stdout, r.stderr)
    assert "appeared after step 1" in r.stdout and str(w.saved) in r.stdout
    assert tree(w.saved) == {"mine": "dir", os.path.join("mine", "f"): hashlib.sha256(b"planted").hexdigest()}
    assert not os.path.lexists(str(w.saved) + ".hashes.txt")  # nothing of this run's was left either
    assert "step 9b save the end state: exit 3" in setup_lines(w)


@needs_linux_wrapper
def test_r8_a_hashes_path_planted_after_step_1_is_exit_3_and_the_planted_file_is_byte_identical(w, ollama):
    hook = plant_hook(w, "plant-hashes.py", "open(save + '.hashes.txt', 'w').write('planted')\n")
    r = cr_run(w, ollama_url=ollama["url"], P1_AFTER_COPY_HOOK=hook, R8_SAVE=str(w.saved))
    assert r.returncode == 3, (r.returncode, r.stdout, r.stderr)
    assert "appeared after step 1" in r.stdout and str(w.saved) + ".hashes.txt" in r.stdout
    assert open(str(w.saved) + ".hashes.txt").read() == "planted"
    assert not os.path.lexists(str(w.saved)), "the save directory THIS run created is removed; the planted file is not"
    assert f"saved end state removed: {w.saved}" in setup_lines(w)


@needs_linux_wrapper
def test_r8_a_failure_after_a_successful_create_removes_exactly_the_created_paths(w, ollama):
    (w.root / "saved-end.keep").write_text("a neighbour\n"); (w.root / "saved-end.hashes.txt.keep").write_text("another\n")
    before = sorted(os.listdir(w.root))
    r = cr_run(w, ollama_url=ollama["url"], **fake_cp_env(w, "mutate"))
    assert r.returncode == 3 and no_saved(w)
    aside = f"{w.slot.name}.aside-t1-{STAMP}"
    new = set(os.listdir(w.root)) - set(before)  # the aside, the fake cp's dir and the stubs' own marker files; nothing near the save path
    assert aside in new and not [n for n in new if n.startswith("saved-end")]
    assert set(before) <= set(os.listdir(w.root))
    assert (w.root / "saved-end.keep").read_text() == "a neighbour\n" and (w.root / "saved-end.hashes.txt.keep").read_text() == "another\n"
    assert f"saved end state removed: {w.saved}" in r.stdout


def test_r8_remove_saved_removes_only_what_this_run_created(tmp_path):
    save, hashes = tmp_path / "s", tmp_path / "s.hashes.txt"
    save.mkdir(); (save / "f").write_text("x"); hashes.write_text("planted")
    c = {"save": str(save), "hashes": str(hashes), "created": [str(save)]}
    P1S.remove_saved(c)
    assert not save.exists() and hashes.read_text() == "planted"
    assert c["saved_removed"] == f"saved end state removed: {save}"
    c2 = {"save": str(save), "hashes": str(hashes), "created": []}  # nothing created: nothing removed, no line
    P1S.remove_saved(c2)
    assert hashes.read_text() == "planted" and "saved_removed" not in c2


def test_r8_the_hashes_file_is_created_exclusively_and_the_save_directory_with_os_mkdir():
    import ast
    src = open(os.path.join(TOOLS, "p1-session.py")).read()
    assert "os.O_CREAT | os.O_EXCL" in src and "os.mkdir(" in src
    for node in ast.walk(ast.parse(src)):  # no create under a caller-chosen path may tolerate an existing one
        if isinstance(node, ast.keyword) and node.arg == "exist_ok":
            raise AssertionError("exist_ok is used somewhere in the launcher")


# ---- R9: a failure to prove the protected homes unchanged is not "PROTECTED CHANGED"
def test_r9_a_run_directory_removed_mid_run_is_reported_on_its_own_line_and_never_as_protected_changed(w, ollama):
    hook = hook_script(w, "rm-rundir.py", "shutil.rmtree(os.environ['R9_RUNDIR'])\n")
    bm = {h: bytes_and_mtimes(h) for h in (w.pres, w.pres2)}
    r = cr_run(w, ollama_url=ollama["url"], P1_AFTER_COPY_HOOK=hook, R9_RUNDIR=str(w.runs / "p1-t1"))
    out = r.stdout + r.stderr
    assert "PROTECTED CHANGED" not in out and "changed home" not in out
    assert "AFTER-HASHES UNAVAILABLE" in out and "not a finding that anything changed" in out
    assert r.returncode == 3, (r.returncode, out)
    assert {h: bytes_and_mtimes(h) for h in (w.pres, w.pres2)} == bm and no_saved(w)


@needs_linux_wrapper
def test_r9_an_after_hashes_file_that_cannot_be_written_is_the_same_own_line_in_continue_mode(w, ollama):
    hook = hook_script(w, "block-after.py", "os.makedirs(os.path.join(os.environ['R9_RUNDIR'], 'after-hashes.txt'))\n")
    r = cr_run(w, ollama_url=ollama["url"], P1_AFTER_COPY_HOOK=hook, R9_RUNDIR=str(w.runs / "p1-t1"))
    assert "PROTECTED CHANGED" not in r.stdout + r.stderr and "AFTER-HASHES UNAVAILABLE" in r.stdout + r.stderr
    assert r.returncode == 3, (r.returncode, r.stdout, r.stderr)
    assert "step 10 after-hashes: exit 3" in setup_lines(w)


@needs_linux_wrapper
def test_r9_a_real_change_is_still_exit_5_even_when_the_proof_file_cannot_be_written(w, ollama):
    hook = hook_script(w, "block-after.py", "os.makedirs(os.path.join(os.environ['R9_RUNDIR'], 'after-hashes.txt'))\n")
    r = cr_run(w, ollama_url=ollama["url"], P1_AFTER_COPY_HOOK=hook, R9_RUNDIR=str(w.runs / "p1-t1"),
               STUB_ACTION="protected", STUB_TARGET=str(w.pres2))
    assert r.returncode == 5 and f"changed home: {w.pres2}" in r.stdout and "PROTECTED CHANGED: 1 home(s)" in r.stdout


# ---- R10: the saved copy is checked the way the next run will check it
@needs_linux_wrapper
def test_r10_an_absolute_symlink_to_a_protected_home_in_the_slot_is_exit_3_and_no_saved_end_state_remains(w, ollama):
    hook = hook_script(w, "plant-link.py", "os.symlink(os.environ['R10_TARGET'], os.path.join(sys.argv[1], 'evil-link'))\n")
    bm = {h: bytes_and_mtimes(h) for h in (w.pres, w.pres2)}
    r = cr_run(w, ollama_url=ollama["url"], P1_AFTER_COPY_HOOK=hook, R10_TARGET=str(w.pres2))
    assert r.returncode == 3, (r.returncode, r.stdout, r.stderr)
    assert "evil-link" in r.stdout and "next run" in r.stdout and no_saved(w)
    assert "step 9b save the end state: exit 3" in setup_lines(w)
    assert {h: bytes_and_mtimes(h) for h in (w.pres, w.pres2)} == bm


# ------------------------------------------------------------------ the sandbox launch module (the reading session is a student session too)
@needs_linux_wrapper
def test_sb_c_continue_reading_records_the_sandbox_lines(w, ollama):
    r = cr_run(w, ollama_url=ollama["url"])
    assert r.returncode == 0, (r.stdout, r.stderr)
    lines = setup_lines(w)
    assert "sandbox verdict: not-flagged" in lines and any(l.startswith("sandbox log: sandbox-") for l in lines)


@needs_linux_wrapper
def test_sb_c_a_log_verdict_refusal_is_exit_3_and_no_end_state_is_saved(w, ollama):
    r = cr_run(w, ollama_url=ollama["url"], STUB_SANDBOX="nolaunch")
    assert r.returncode == 3, (r.stdout, r.stderr)
    assert "STOP: sandbox launch module" in r.stdout
    assert not w.saved.exists() and not os.path.lexists(str(w.saved) + ".hashes.txt")
    assert not (w.runs / "p1-t1" / "delivery.txt").exists()


# ------------------------------------------------------------------ F5 (design owner's ruling, option C): a FLAGGED continue-reading
# session still saves its end state, but only under a QUARANTINE name, with its verdict line beside it; and the reader refuses
# by name AND by content. The rule: a flagged session saves to <--save-end-state>.flagged (hashes: .flagged.hashes.txt, record:
# .flagged.verdict.txt). The end state's own record is the file <end state>.verdict.txt beside it, holding `sandbox verdict: ...`.
FLAGGED_LINE = "flagged: endpoint unreachable, nothing reached it"


def flagged_run(w, ollama, **kw):
    r = cr_run(w, ollama_url=ollama["url"], STUB_SANDBOX="unreachable", **kw)
    assert r.returncode == 0, (r.stdout, r.stderr)     # a flagged verdict is recorded, not a stop
    return r


def copy_end_state(w, name, record):
    """A copy of the preserved end state at a new protected path, with `record` as its verdict record (None: no record)."""
    dst = w.root / name
    subprocess.run(["cp", "-a", "--", str(w.pres), str(dst)], check=True)
    if record is not None:
        open(str(dst) + ".verdict.txt", "w").write(record)
    return dst


def start_from(w, path, label="t2", **kw):
    return cr_run(w, over={"--end-state": str(path), "--label": label, "--save-end-state": str(w.root / "saved-next")},
                  P1_PROTECTED=f"{w.pres}:{w.pres2}:{path}", **kw)


@needs_linux_wrapper
def test_f5_a_flagged_session_saves_the_end_state_only_under_the_quarantine_name_and_says_why_in_words(w, ollama):
    flagged_run(w, ollama)
    q = str(w.saved) + ".flagged"
    assert not os.path.lexists(str(w.saved)) and not os.path.lexists(str(w.saved) + ".hashes.txt")   # no reusable state
    assert os.path.isdir(q) and os.path.isfile(q + ".hashes.txt")
    assert f"sandbox verdict: {FLAGGED_LINE}" in open(q + ".verdict.txt").read().splitlines()        # the verdict, beside it
    text = " ".join(setup_lines(w))
    assert "QUARANTINED" in text and "FLAGGED" in text and "excluded" in text and "endpoint was unreachable" in text


@needs_linux_wrapper
def test_f5_evidence_is_kept_the_log_the_verdict_and_the_transcript_stay_and_only_the_clean_state_path_is_absent(w, ollama):
    flagged_run(w, ollama)
    run = w.runs / "p1-t1"
    logs = [p for p in run.iterdir() if p.name.startswith("sandbox-") and p.name.endswith(".log")]
    assert len(logs) == 1 and "wrapper-launch " in logs[0].read_text()
    assert f"sandbox verdict: {FLAGGED_LINE}" in setup_lines(w)
    assert (run / "transcripts").is_dir() and (run / "delivery.txt").exists()
    assert not os.path.lexists(str(w.saved))


@needs_linux_wrapper
def test_f5_a_clean_session_saves_under_the_clean_name_with_its_not_flagged_record(w, ollama):
    r = cr_run(w, ollama_url=ollama["url"])
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert w.saved.is_dir() and not os.path.lexists(str(w.saved) + ".flagged")
    assert "sandbox verdict: not-flagged" in open(str(w.saved) + ".verdict.txt").read().splitlines()
    assert "QUARANTINED" not in " ".join(setup_lines(w))


def test_f5_reader_a_quarantine_name_is_refused_by_name(w):
    q = copy_end_state(w, "old.flagged", "sandbox verdict: not-flagged\n")      # a clean record: only the NAME can refuse it
    cr_refusal(w, over={"--end-state": str(q)}, expect="quarantine name", P1_PROTECTED=f"{w.pres}:{w.pres2}:{q}")


def test_f5_reader_a_flagged_verdict_in_the_record_is_refused_by_content(w):
    s = copy_end_state(w, "cleanname", f"sandbox verdict: {FLAGGED_LINE}\n")    # a clean name: only the CONTENT can refuse it
    cr_refusal(w, over={"--end-state": str(s)}, expect="FLAGGED verdict", P1_PROTECTED=f"{w.pres}:{w.pres2}:{s}")


@pytest.mark.parametrize("record", [None, "", "run record: p1-x/setup.txt\n"])
def test_f5_reader_an_end_state_with_no_verdict_line_is_refused(w, record):
    s = copy_end_state(w, "noverdict", record)
    cr_refusal(w, over={"--end-state": str(s)}, expect="no verdict line", P1_PROTECTED=f"{w.pres}:{w.pres2}:{s}")


def test_f5_reader_an_unrecognised_verdict_is_refused(w):
    s = copy_end_state(w, "odd", "sandbox verdict: something else\n")
    cr_refusal(w, over={"--end-state": str(s)}, expect="unrecognised verdict", P1_PROTECTED=f"{w.pres}:{w.pres2}:{s}")


@needs_linux_wrapper
def test_f5_a_rename_does_not_launder_a_quarantined_end_state(w, ollama):
    """A flagged session's end state is renamed to a clean name, together with its record: the flagged verdict in the record
    still refuses it (by content). Renamed alone, without its record, it has no verdict line and is refused too."""
    flagged_run(w, ollama)
    q = str(w.saved) + ".flagged"
    clean = w.root / "looks-clean"
    os.rename(q, clean)
    os.rename(q + ".verdict.txt", str(clean) + ".verdict.txt")
    r = start_from(w, clean)
    assert r.returncode == 2 and "FLAGGED verdict" in r.stdout + r.stderr, (r.stdout, r.stderr)
    assert not (w.runs / "p1-t2").exists()                         # refused before anything was touched
    alone = w.root / "renamed-alone"
    os.rename(clean, alone)                                         # the record stays behind under the old name
    r = start_from(w, alone, label="t3")
    assert r.returncode == 2 and "no verdict line" in r.stdout + r.stderr, (r.stdout, r.stderr)


# ---- F5 (C), exclusive create under the caller-derived quarantine path: nothing foreign is overwritten or removed
def test_f5_a_foreign_file_at_the_quarantine_path_is_refused_and_survives_byte_identical(w, ollama):
    foreign = str(w.saved) + ".flagged"
    open(foreign, "w").write("mine, not yours")
    r = cr_run(w, ollama_url=ollama["url"], STUB_SANDBOX="unreachable")
    assert r.returncode == 2 and "already exists" in r.stdout + r.stderr and foreign in r.stdout + r.stderr, (r.stdout, r.stderr)
    assert open(foreign).read() == "mine, not yours"
    assert not (w.runs / "p1-t1").exists() and not os.path.lexists(str(w.saved))     # refused before anything was touched


@pytest.mark.parametrize("name,body,planted", [
    ("dir", "os.makedirs(os.path.join(save + '.flagged', 'mine'))\nopen(os.path.join(save + '.flagged', 'mine', 'f'), 'w').write('planted')\n", ""),
    ("hashes", "open(save + '.flagged.hashes.txt', 'w').write('planted')\n", ".hashes.txt"),
    ("verdict", "open(save + '.flagged.verdict.txt', 'w').write('planted')\n", ".verdict.txt"),
])
@needs_linux_wrapper
def test_f5_a_foreign_path_appearing_between_the_check_and_the_write_survives_and_only_this_runs_creates_are_removed(
        w, ollama, name, body, planted):
    hook = plant_hook(w, f"plant-{name}.py", body)
    r = cr_run(w, ollama_url=ollama["url"], STUB_SANDBOX="unreachable", P1_AFTER_COPY_HOOK=hook, R8_SAVE=str(w.saved))
    assert r.returncode == 3, (r.returncode, r.stdout, r.stderr)
    assert "appeared after step 1" in r.stdout
    q = str(w.saved) + ".flagged"
    if name == "dir":
        assert tree(q) == {"mine": "dir", os.path.join("mine", "f"): hashlib.sha256(b"planted").hexdigest()}
        assert not os.path.lexists(q + ".hashes.txt") and not os.path.lexists(q + ".verdict.txt")
    else:
        assert open(q + planted).read() == "planted"
        # what THIS run created at the quarantine paths (recorded at each exclusive create) is gone, the planted path is not
        mine = [x for x in (q, q + ".hashes.txt", q + ".verdict.txt") if x != q + planted]
        assert not any(os.path.lexists(x) for x in mine), mine
    assert not os.path.lexists(str(w.saved))


# ------------------------------------------------------------------ round 5 (security seat, review 6000327021)
# Z1: every path a flagged save creates is checked against the paths the launcher makes or protects, not only for existence.
# The quarantine paths are suffixes of the save path, so the only overlap that is not also an existing path is with a path that
# does not exist yet: the run directory (made after step 1). A label that ends in the suffix makes them equal.
@pytest.mark.parametrize("which", ["hashes", "verdict"])
def test_z1_a_quarantine_path_equal_to_a_launcher_path_is_refused_named(w, which):
    label = f"x.flagged.{which}.txt"
    save = w.runs / "p1-x"
    r = cr_refusal(w, over={"--label": label, "--save-end-state": str(save)}, expect=f"quarantine {which}")
    assert "run directory" in r.stdout + r.stderr


# Z2: the save step's directory gets an explicit mode (0700), not the umask default and not the slot's own mode (cp -a copies it).
@needs_linux_wrapper
@pytest.mark.parametrize("stub_sandbox,suffix", [("ok", ""), ("unreachable", ".flagged")])
def test_z2_the_saved_end_state_directory_is_0700_even_under_umask_0(w, ollama, stub_sandbox, suffix):
    import stat as _stat
    old = os.umask(0)
    try:
        r = cr_run(w, ollama_url=ollama["url"], STUB_SANDBOX=stub_sandbox)
    finally:
        os.umask(old)
    assert r.returncode == 0, (r.stdout, r.stderr)
    saved = str(w.saved) + suffix
    assert _stat.S_IMODE(os.stat(saved).st_mode) == 0o700
