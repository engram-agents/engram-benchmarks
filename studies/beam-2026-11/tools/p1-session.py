#!/usr/bin/env python3
"""P1 answering / control session launcher (BEAM P1). This file is the study's harness, not shipped product code.

Answers the frozen question file on a DISPOSABLE COPY of a preserved end-state home. Claude Code keys the session file
and its built-in memory folder by the cwd path, so the copy must sit at the arm-home SLOT path (the path the run used)
to `--resume` the run's session. The preserved homes are irreplaceable references: nothing may write to them, and this
launcher proves that (a content hash of every protected home before and after) instead of assuming it.

NO HOST PATH IN THIS FILE: every host location comes from the environment. Required (refused with exit 2, naming the
missing one):
  BEAM_PY         python for feed4.py and the checks
  BEAM_ARM_HOME   the SLOT: the arm-home path the run used; an existing one is moved aside, never deleted
  BEAM_RUNS_DIR   where run directories are created (<BEAM_RUNS_DIR>/p1-<label>, never reused)
  BEAM_PARQUET    the BEAM dataset file feed4.py reads from the environment; it must name an existing FILE whose sha256 starts
                  with the registered prefix (PROVENANCE.md registers the dataset; the reading runs' own script,
                  tools/pilot-run.sh, refused the same way). The launcher streams the file through sha256 in step 1
  P1_PROTECTED    colon-separated preserved-home paths; every entry must exist; --end-state must be one of them

usage: p1-session.py --end-state PATH --session ID --label NAME --question-file F --components F
                     [--plant-builtin T --plant-engram T --plant-absent T [--plant-question TEXT]] [--dry-run]
       or, for an ENGRAM-only plant (control 2):  ... [--plant-engram T --plant-absent T] [--dry-run]

A plant set is valid as EITHER all three of --plant-builtin --plant-engram --plant-absent (both channels; optionally
--plant-question) OR exactly --plant-engram --plant-absent without --plant-builtin (engram-only: plant-control.py is
called without --builtin-fact and without --question, and writes nothing under any built-in memory folder). Any other
combination is refused in step 1, and --plant-question is refused without --plant-builtin.

Steps (every refusal in step 1 happens before anything is touched: no process killed, no copy, no directory made):
 1 refusals, exit 2: BEAM_PARQUET unset, not an existing file, or not hashing to the registered prefix; a test-only hook variable set without P1_TEST_HOOKS=1; a relative symlink in the end state that
   climbs above its root; a symlink in the end state resolving to, inside or above a protected path (a relative link
   that stays inside the end state is fine; the count of links pointing outside it is printed); BEAM_RUNS_DIR equal
   to, inside or containing a protected path, or equal to or inside the slot; an env var missing; a label outside
   [A-Za-z0-9._-]; a P1_PROTECTED entry that does not exist;
   --end-state (by realpath) not one of P1_PROTECTED; the slot equal to, inside or containing a protected path; the run
   directory exists; the end state lacks .engram/knowledge.db or .claude/; the question file or components file
   missing or malformed; any plant flags that are neither all three of --plant-builtin --plant-engram --plant-absent
   nor exactly --plant-engram --plant-absent (a partial plant set), or --plant-question without --plant-builtin;
   planting when the end state has no .engram/venv/bin/python; the aside path already exists.
 2 before-hashes.txt: for EVERY protected home, the store content hash (store_content_hash below) and the sha256 of
   every file under its built-in memory folders (.claude/projects/*/memory/**).
 3 stop processes whose command line contains <slot>/.engram/ (SIGTERM; the processes of this launcher are exempt).
 4 an existing slot is moved to <slot>.aside-<label>-<UTC stamp> (never deleted).
 5 cp -a end state -> slot; create <slot>/.disposable-copy; the slot's store hash must equal the end state's (else exit 3,
   both printed).
 6 plant (only with plant flags): plant-control.py with the slot's own ENGRAM venv python, P1_PROTECTED exported, the
   evidence dir <rundir>/plant-evidence (outside the student's home); in engram-only mode without --builtin-fact. Its exit 3 (a protected entry changed) is exit 5;
   any other nonzero is exit 4; either way no student run.
 7 feed4.py --dump-plan with the step-8 arguments -> plan.json; it must be exactly [compact, q1..qN] in file order.
 8 unless --dry-run: feed4.py --arm-home <slot> --out <rundir>/run --conv 9 --turns 0 --resume ID --force-compact
   --question-file F --env CLAUDE_CODE_MAX_CONTEXT_TOKENS=131072 --expect-components C
 9 (not on --dry-run) stop slot processes; copy <slot>/.claude/projects to <rundir>/transcripts;
   answer-delivery-check.py -> delivery.txt.
10 after-hashes.txt, same method for every protected home; ANY difference prints `changed home: <path>` and
   `PROTECTED CHANGED: n home(s)` and is exit 5. Steps 10 and 11 run on every exit path after the run directory exists.
11 setup.txt: first line the benchmarks commit id, then the sha256 of this script, feed4.py, feed.py, the question file,
   the components file, answer-delivery-check.py and plant-control.py, the plant mode on its own line (`plant mode: none`,
   `plant mode: both channels` or `plant mode: engram-only (no built-in plant)`), the FULL sha256 of BEAM_PARQUET (`<sha256>  BEAM_PARQUET`), which dataset check ran (`dataset check: registered
   prefix <prefix>` or `dataset check: test-only override (P1_TEST_HOOKS)`), start/end UTC, and each step's exit code.
CONTINUE READING (--continue-reading): the same launcher, steps and protected-home proof, but it feeds READING rounds instead
of asking questions, then saves the resulting home as a new preserved end state:
  p1-session.py --end-state PATH --session ID --label NAME --components F --continue-reading --start N --through M
                --per-round K --save-end-state PATH --expect-store-sha256 H [--expect-serving FILE] [--dry-run]
  Mutually exclusive with --question-file and every plant flag; --start --through --per-round --save-end-state and
  --expect-store-sha256 are then required, and none of the continue flags is accepted without it. Feeds exchanges N..M of
  conversation 9 through feed4.py --resume ID --start N --turns M --per-round K (feed4's --turns is an INCLUSIVE END INDEX).
  Step 1 also refuses (exit 2): K < 1; N < 2; M < N; (N - 1) % K != 0; (M - N + 1) % K != 0; the end state's store content
  hash (protected_store_hash) differs from --expect-store-sha256; --save-end-state, or PATH.hashes.txt, already exists, or
  PATH, or PATH.hashes.txt, is equal to, inside or containing ANY path the launcher creates or protects (launcher_paths():
  the run directory, or the first missing ancestor of it, the aside path, the slot, every protected home, the end state;
  after resolving `..` and the symlinks of existing ancestors), or PATH's parent directory is missing; --expect-serving FILE differs from the
  recorded serving lines. Then it records the serving setup (GET <BEAM_OLLAMA_URL, else the default>/api/version, and
  /api/tags for the digest of feed4's default model) as three `serving:` lines in setup.txt; a server that does not answer, or
  does not list the model, is exit 3 with `SERVING RECORD FAILED` and nothing touched. Optional env: BEAM_OLLAMA_URL.
  Step 7 dumps the continue plan and a FULL run's plan (--start 1 --turns M --per-round K, no resume): the continue plan
  must hold exactly (M - N + 1) / K reading messages carrying exchanges N..M in order, no compaction, no question, and be
  byte-equal to the full plan's messages for those exchanges (a resume must add nothing); else exit 3, no student run.
  Step 8 is feed4.py --arm-home <slot> --out <rundir>/run --conv 9 --resume ID --start N --turns M --per-round K --env
  CLAUDE_CODE_MAX_CONTEXT_TOKENS=131072 --expect-components C (no --force-compact, no questions). Step 9's delivery check
  is reading-delivery-check.py (answer-delivery-check.py refuses reading turns by design). After a run with feed4 exit 0
  and the delivery check passing, the slot's CONTENTS are COPIED (cp -a, never moved) into --save-end-state, a directory made
  at that moment with os.mkdir (no exist_ok) beside a hashes file made with O_CREAT | O_EXCL: if either exists by then
  (step 1 ran hours earlier) the run is exit 3 with a `STOP: <path> appeared after step 1` line and nothing of the caller's
  is touched. The copy is checked the way the next run will check it (check_end_state_links on the saved copy), hashed the
  way the protected homes are (store content hash from a temporary copy, memory files), and the hashes go to setup.txt and
  PATH.hashes.txt; on any failure ONLY the paths this run created are removed, with a `saved end state removed:` line. The
  saved end state is not in the before set; steps 10 and 11 run as before, so the originals (the end state included) are
  proved byte-equal. In this mode a step-10 failure that is not a difference (the after-hashes cannot be computed or
  written, for example the run directory was removed) prints `AFTER-HASHES UNAVAILABLE: <reason>` and is exit 3, never
  `PROTECTED CHANGED`; the answering mode keeps its pinned behaviour (an unprovable pass counts as every home changed).
Exit codes: 0 all good; 1 delivery check failed; 2 refused; 3 copy, plan check, feed4 or (continue-reading) the save or the
after-hashes proof failed; 4 plant failed; 5 a protected home changed (overrides every other code).

A protected home's store is never opened with sqlite: it is hashed from a byte copy of knowledge.db, -wal and -shm in a
temporary directory (protected_store_hash), because even a read-only sqlite connection writes -shm read marks. The memory
folders are only read. Only the disposable slot copy is hashed in place.

TEST-ONLY HOOKS (never set in a real run; each is documented in tests/test_p1_session.py). Setting any of them without
P1_TEST_HOOKS=1 is refused in step 1 (exit 2), so a stray variable can never silently change a real run:
  P1_FEED4            run this script in place of feed4.py (the plan dump and the run)
  P1_PLANT_CONTROL    run this script in place of plant-control.py
  P1_UTC_STAMP        a fixed stamp for the aside path
  P1_AFTER_COPY_HOOK  `BEAM_PY -I HOOK SLOT`, run between the copy and the copy-fidelity check
  P1_EXPECTED_PARQUET_PREFIX  the sha256 prefix BEAM_PARQUET must have, in place of the registered one (setup.txt says so)
  P1_TEST_RAISE       KeyboardInterrupt | SystemExit | Exception: raised once, just after the copy has been verified
"""
import argparse, datetime, hashlib, http.client, json, os, re, shutil, sqlite3, subprocess, sys, tempfile, time, traceback
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REQUIRED_ENV = ("BEAM_PY", "BEAM_ARM_HOME", "BEAM_RUNS_DIR", "BEAM_PARQUET", "P1_PROTECTED")
TEST_HOOKS = ("P1_FEED4", "P1_PLANT_CONTROL", "P1_UTC_STAMP", "P1_AFTER_COPY_HOOK", "P1_TEST_RAISE",
              "P1_EXPECTED_PARQUET_PREFIX")
# The registered dataset's sha256 prefix: studies/beam-2026-11/PROVENANCE.md ("parquet sha256 prefix") and the reading
# runs' own check in tools/pilot-run.sh. A test reads PROVENANCE.md and requires this constant to equal it.
REGISTERED_PARQUET_PREFIX = "c0519be25907"
LABEL = re.compile(r"[A-Za-z0-9._-]+")
WINDOW = "CLAUDE_CODE_MAX_CONTEXT_TOKENS=131072"
# The model server feed4.py talks to (feed.py's OLLAMA_URL) and the model it runs when --model is not given (feed4.py's
# --model default); the continue-reading mode records the server's version and this model's digest. A test reads
# feed4.py and requires SERVING_MODEL to equal its default.
OLLAMA_DEFAULT = "http://localhost:11434"  # privacy-scan: allow (Ollama's documented default endpoint, as in feed.py)
SERVING_MODEL = "qwen3.8:27b-128k"
CONTINUE_ONLY = ("start", "through", "per_round", "save_end_state", "expect_store_sha256", "expect_serving")
PLANT_SETS = ("the valid plant sets are --plant-builtin --plant-engram --plant-absent (both channels), or exactly "
              "--plant-engram --plant-absent (engram-only)")


class Refusal(Exception):
    pass


class ServingFailed(Exception):
    """The model server did not give the serving record (exit 3, before anything is touched)."""


# --------------------------------------------------------------------------------------------- the store content hash
def store_content_hash(path):
    """The STORE CONTENT HASH: the exact method that produced the logged values, kept in this one function. Every
    non-virtual table (shadow tables of FTS/vec and sqlite_sequence are ordinary tables, so they count) in name order;
    for each, the name then every row's repr, rows sorted by their repr string, no separators. Returns
    (sha256 hex, table count, row count). The store is opened read-only."""
    c = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    virt = {r[0] for r in c.execute("select name from sqlite_master where type='table' and sql like 'CREATE VIRTUAL%'")}
    tabs = [r[0] for r in c.execute("select name from sqlite_master where type='table' order by name") if r[0] not in virt]
    h = hashlib.sha256(); n = 0
    for t in tabs:
        rows = sorted(repr(r) for r in c.execute(f'select * from "{t}"')); n += len(rows)
        h.update(t.encode()); [h.update(r.encode()) for r in rows]
    c.close(); return h.hexdigest(), len(tabs), n


def protected_store_hash(home):
    """store_content_hash of a PROTECTED home's store, read from a temporary COPY, so nothing under the protected home is
    written. Opening a WAL-mode store with sqlite writes read marks into its -shm file even on a read-only connection
    (measured: the -shm mtime moved), so the originals are never opened with sqlite: knowledge.db and, if present,
    knowledge.db-wal and knowledge.db-shm are copied byte for byte into a fresh temporary directory, the copy is
    hashed, and the directory is removed. Returns the same (sha256 hex, table count, row count)."""
    src = os.path.join(home, ".engram", "knowledge.db")
    tmp = tempfile.mkdtemp(prefix="p1-store-")
    try:
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(src + suffix):
                shutil.copyfile(src + suffix, os.path.join(tmp, "knowledge.db" + suffix))
        return store_content_hash(os.path.join(tmp, "knowledge.db"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------------------------------------ hashing the homes
def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def expected_parquet_prefix(env):
    """The registered prefix, or the gated test-only override (step 1 has already refused the override without the gate)."""
    return env.get("P1_EXPECTED_PARQUET_PREFIX") or REGISTERED_PARQUET_PREFIX


def dataset_check_line(env):
    if env.get("P1_EXPECTED_PARQUET_PREFIX"):
        return "dataset check: test-only override (P1_TEST_HOOKS)"
    return f"dataset check: registered prefix {REGISTERED_PARQUET_PREFIX}"


def memory_files(home):
    """[(relative path, sha256 | 'link:<target>')] sorted by path: every file under .claude/projects/*/memory/** (links
    are recorded, never followed)."""
    out = []
    proj = os.path.join(home, ".claude", "projects")
    if os.path.isdir(proj):
        for d in sorted(os.listdir(proj)):
            mem = os.path.join(proj, d, "memory")
            if os.path.isdir(mem) and not os.path.islink(mem):
                for dp, dns, fns in os.walk(mem):
                    for fn in fns:
                        full = os.path.join(dp, fn)
                        out.append((os.path.relpath(full, home),
                                    "link:" + os.readlink(full) if os.path.islink(full) else file_sha256(full)))
    return sorted(out)


def home_record(home):
    """The text block for one protected home (store hash line, then the memory-file hashes)."""
    lines = [f"home {home}"]
    db = os.path.join(home, ".engram", "knowledge.db")
    if os.path.exists(db):
        h, t, n = protected_store_hash(home)
        lines.append(f"store tables={t} rows={n} sha256={h}")
    else:
        lines.append("store ABSENT")
    files = memory_files(home)
    lines.append(f"memory {len(files)} files")
    lines += [f"{d}  {rel}" for rel, d in files]
    return "\n".join(lines) + "\n"


def records(homes, tolerant):
    """{home: block}. tolerant (the after pass): an unreadable home becomes its own block, so it counts as changed."""
    out = {}
    for h in homes:
        try:
            out[h] = home_record(h)
        except Exception as e:  # noqa: BLE001
            if not tolerant:
                raise Refusal(f"cannot hash the protected home {h}: {e}")
            out[h] = f"home {h}\nUNREADABLE {type(e).__name__}: {e}\n"
    return out


def changed_homes(before, after):
    """The protected homes whose block differs between the two passes (a home missing from `after` is changed)."""
    return [h for h in before if after.get(h) != before[h]]


# ------------------------------------------------------------------------------------------------------- processes
def under(path, root):
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


# The ONE place that says which paths this launcher creates, moves, writes into or protects for an invocation. Everything
# a caller chooses (--save-end-state, and the PATH.hashes.txt beside it) must be disjoint from every one of them; the
# naming rules of the run directory and the aside path live here too, so step 1 and the checks cannot drift apart. A test
# binds this set to what a real dry run creates (a path main() starts creating without being listed here goes red).
CREATED_ROLES = ("run directory", "aside path", "slot")


def run_dir_path(runs, label):
    return os.path.join(runs, f"p1-{label}")


def aside_path(slot, label, stamp):
    return f"{slot}.aside-{label}-{stamp}"


def launcher_paths(slot, runs, label, stamp, end, prot):
    """[(role, realpath)]: the paths created (CREATED_ROLES: the run directory, or the first missing ancestor of it when
    BEAM_RUNS_DIR does not exist yet, since os.makedirs creates the whole chain; the aside path an existing slot is moved
    to; the slot recreated by the copy) and the paths protected (every protected home, the end state among them), each
    resolved with os.path.realpath. Anything the launcher writes under them (plan dumps, run output, transcripts,
    setup.txt, plant evidence) is inside the run directory or the slot. The temporary directories of protected_store_hash
    are random names made by tempfile.mkdtemp (exclusive by construction) and are not listed."""
    top = os.path.abspath(run_dir_path(runs, label))
    while not os.path.lexists(os.path.dirname(top)):
        top = os.path.dirname(top)
    out = [("run directory", os.path.realpath(top)), ("aside path", os.path.realpath(aside_path(slot, label, stamp))),
           ("slot", os.path.realpath(slot))]
    out += [("protected home", os.path.realpath(p)) for p in prot]
    out.append(("end state", os.path.realpath(end)))
    return out


def refuse_overlap(what, path, paths):
    """Refusal unless `path`, after resolving `..` and the symlinks of its existing ancestors, is disjoint from every
    path in `paths`: not equal to, not inside, not containing any of them."""
    real = os.path.realpath(path)
    for role, p in paths:
        if under(real, p) or under(p, real):
            raise Refusal(f"{what} {path} is equal to, inside, or containing the {role} {p}")


def slot_pids(slot):
    needles = {slot.rstrip(os.sep) + "/.engram/", os.path.realpath(slot).rstrip(os.sep) + "/.engram/"}
    r = subprocess.run(["ps", "-u", str(os.getuid()), "-ww", "-o", "pid=,command="], capture_output=True, text=True)
    pids = []
    for line in r.stdout.splitlines():
        pid, _, cmd = line.strip().partition(" ")
        if pid.isdigit() and any(n in cmd for n in needles) and int(pid) not in (os.getpid(), os.getppid()):
            pids.append(int(pid))
    return pids


def stop_slot_processes(slot):
    """Same loop as pilot-run.sh: SIGTERM every process of this user whose command line holds <slot>/.engram/, then
    wait up to 2 s for them to go."""
    pids = slot_pids(slot)
    for p in pids:
        try:
            os.kill(p, 15)
        except OSError:
            pass
    deadline = time.time() + 2
    while pids and time.time() < deadline and slot_pids(slot):
        time.sleep(0.1)
    left = slot_pids(slot)
    print(f"stopped {len(pids)} slot process(es)" + (f"; still listed: {left}" if left else ""))
    return len(pids)


# --------------------------------------------------------------------------------------------------- step 1: refuse
def load_questions(path):
    try:
        items = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise Refusal(f"the question file cannot be read as JSON: {e}")
    if not isinstance(items, list) or not items:
        raise Refusal("the question file must be a non-empty JSON list of {id, question}")
    ids = []
    for it in items:
        if not (isinstance(it, dict) and isinstance(it.get("id"), str) and isinstance(it.get("question"), str)):
            raise Refusal("the question file must be a JSON list of {id, question} objects")
        ids.append(it["id"])
    if len(set(ids)) != len(ids):
        raise Refusal("the question file has a duplicate id")
    return ids


def check_end_state_links(end, prot):
    """Walk the end state without following links. The rule is judged from the COPY's side: after cp -a, where does
    each link resolve, relative to the slot?
      - a RELATIVE link whose path, taken from the link's own directory, climbs above the end state's root (the
        normalized path is '..' or starts with '../') is refused whatever it points at: in the copy it resolves
        relative to the slot's location, which step 1 cannot judge from the original (E/a/x -> ../../E/real would land
        on the ORIGINAL E/real from a slot beside E);
      - any other relative link whose realpath is inside the end state is allowed (a venv's lib64 -> lib);
      - every other link (absolute, or a relative one that is not inside the end state) is refused if its realpath is
        equal to, inside, or containing a protected path, because cp -a keeps the link text and the student could
        write through it into a preserved home. An absolute link back into the end state is refused for that reason.
    Returns the count of symlinks that point outside the end state (informational: plugin venvs link to system
    interpreters)."""
    outside = 0
    for dp, dns, fns in os.walk(end, followlinks=False):
        for n in dns + fns:
            full = os.path.join(dp, n)
            if not os.path.islink(full):
                continue
            target = os.path.realpath(full)
            in_end = under(target, end)
            if not in_end:
                outside += 1
            text = os.readlink(full)
            if not os.path.isabs(text):
                from_root = os.path.normpath(os.path.join(os.path.relpath(dp, end), text))
                if from_root == ".." or from_root.startswith(".." + os.sep):
                    raise Refusal(f"the end state holds a relative symlink ({os.path.relpath(full, end)} -> {text}) "
                                  "that climbs above the end state's root; in the copy it would resolve relative to "
                                  "the slot's location, which cannot be judged here")
                if in_end:
                    continue  # stays inside the end state, so in the copy it stays inside the slot
            for p in prot:
                if under(target, p) or under(p, target):
                    raise Refusal(f"the end state holds a symlink ({os.path.relpath(full, end)}) that resolves to "
                                  f"{target}, which is equal to, inside, or containing the protected path {p}")
    return outside


def fetch_json(url):
    with urllib.request.urlopen(url, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def serving_record(env):
    """The serving setup the run will use (design A7): the model server's version (GET <url>/api/version, the URL feed4.py
    uses: BEAM_OLLAMA_URL, else the default), the model name feed4.py runs by default, and that model's digest (GET
    <url>/api/tags, the entry whose name equals it). Three `serving: ...` lines. A server that does not answer, or that
    does not list the model, is ServingFailed, never a silent skip."""
    base = (env.get("BEAM_OLLAMA_URL") or OLLAMA_DEFAULT).rstrip("/")
    try:
        version = fetch_json(base + "/api/version")["version"]
        models = fetch_json(base + "/api/tags")["models"]
        digest = next((m["digest"] for m in models if m.get("name") == SERVING_MODEL), None)
    except (OSError, http.client.HTTPException, ValueError, KeyError, TypeError, AttributeError) as e:
        raise ServingFailed(f"cannot read the model server at {base}: {type(e).__name__}: {e}")
    if not isinstance(version, str) or not version:
        raise ServingFailed(f"the model server at {base} gave no version string")
    if not isinstance(digest, str) or not digest:
        raise ServingFailed(f"the model {SERVING_MODEL} is not listed (with a digest) by {base}/api/tags")
    return [f"serving: ollama version {version}", f"serving: model {SERVING_MODEL}", f"serving: model digest {digest}"]


def continue_step1(a, env, end, paths):
    """The continue-reading refusals (exit 2, before anything is touched), then the serving record (ServingFailed = exit 3,
    also before anything is touched). Returns the fields the later steps need."""
    if a.per_round < 1:
        raise Refusal(f"--per-round must be at least 1 (got {a.per_round})")
    if a.start < 2:
        raise Refusal(f"--start must be at least 2 (got {a.start}): exchange 1 carries the brief, which only a full run sends")
    if a.through < a.start:
        raise Refusal(f"--through must not be below start (--through {a.through}, --start {a.start})")
    if (a.start - 1) % a.per_round:
        raise Refusal(f"--start {a.start} is not on a round boundary: (start - 1) must be a multiple of --per-round {a.per_round}")
    if (a.through - a.start + 1) % a.per_round:
        raise Refusal(f"exchanges {a.start}..{a.through} would end in a partial last round at --per-round {a.per_round}: "
                      "(through - start + 1) must be a multiple of --per-round")
    got = protected_store_hash(end)[0]
    if got != a.expect_store_sha256:
        raise Refusal(f"the end state's store content hash {got} differs from --expect-store-sha256 {a.expect_store_sha256}")
    save = os.path.abspath(a.save_end_state)
    hashes = save + ".hashes.txt"
    if os.path.lexists(save):
        raise Refusal(f"--save-end-state {save} already exists (a saved end state is never overwritten)")
    if os.path.lexists(hashes):
        raise Refusal(f"the hashes file {hashes} already exists (it is written beside --save-end-state and never overwritten)")
    refuse_overlap("--save-end-state", save, paths)  # the save path and the hashes path against EVERY path the launcher makes or protects
    refuse_overlap("the hashes file", hashes, paths)
    if not os.path.isdir(os.path.dirname(save)):
        raise Refusal(f"the parent directory of --save-end-state {save} does not exist (the copy would fail after the run)")
    expect_serving = None
    if a.expect_serving is not None:
        try:
            expect_serving = [l for l in open(a.expect_serving, encoding="utf-8").read().splitlines() if l.strip()]
        except OSError as e:
            raise Refusal(f"--expect-serving {a.expect_serving} cannot be read: {e}")
    serving = serving_record(env)
    if expect_serving is not None and expect_serving != serving:
        raise Refusal(f"the recorded serving setup differs from --expect-serving {a.expect_serving}\n  recorded: {serving}\n  expected: {expect_serving}")
    return {"save": save, "hashes": hashes, "serving": serving}


def step1(a):
    env = os.environ
    for v in REQUIRED_ENV:
        if not env.get(v):
            raise Refusal(f"{v} is not set")
    if not os.path.isfile(env["BEAM_PARQUET"]):
        raise Refusal(f"BEAM_PARQUET {env['BEAM_PARQUET']} is not an existing file (feed4.py reads the dataset from it)")
    for hook in TEST_HOOKS:
        if env.get(hook) and env.get("P1_TEST_HOOKS") != "1":
            raise Refusal(f"{hook} is a test-only hook and is refused unless P1_TEST_HOOKS=1 is also set "
                          "(a stray variable must never change a real run)")
    parquet_sha = file_sha256(env["BEAM_PARQUET"])
    want = expected_parquet_prefix(env)
    if not parquet_sha.startswith(want):
        raise Refusal(f"BEAM_PARQUET {env['BEAM_PARQUET']} has sha256 {parquet_sha}, which does not start with the "
                      f"expected dataset prefix {want} (PROVENANCE.md registers the dataset)")
    if not LABEL.fullmatch(a.label):
        raise Refusal(f"the label {a.label!r} is outside the charset [A-Za-z0-9._-] (one or more characters)")
    protected = [p for p in env["P1_PROTECTED"].split(":") if p]
    if not protected:
        raise Refusal("P1_PROTECTED holds no path")
    prot = []
    for p in protected:
        if not os.path.exists(p):
            raise Refusal(f"the P1_PROTECTED entry {p} does not exist (refusing to guess what is protected)")
        prot.append(os.path.realpath(p))
    end = os.path.realpath(a.end_state)
    if end not in prot:
        raise Refusal(f"--end-state {a.end_state} is not one of the P1_PROTECTED entries (it must be a protected home)")
    slot = os.path.abspath(env["BEAM_ARM_HOME"])
    slot_real = os.path.realpath(slot)
    for p in prot:
        if under(slot_real, p) or under(p, slot_real):
            raise Refusal(f"the slot {slot} is equal to, inside, or contains the protected path {p}")
    runs_real = os.path.realpath(env["BEAM_RUNS_DIR"])
    for p in prot:
        if under(runs_real, p) or under(p, runs_real):
            raise Refusal(f"BEAM_RUNS_DIR {env['BEAM_RUNS_DIR']} is equal to, inside, or containing the protected path {p}")
    if under(runs_real, slot_real):
        raise Refusal(f"BEAM_RUNS_DIR {env['BEAM_RUNS_DIR']} is equal to or inside the slot {slot}")
    rundir = run_dir_path(env["BEAM_RUNS_DIR"], a.label)
    if os.path.lexists(rundir):
        raise Refusal(f"the run directory {rundir} exists (run directories are never reused)")
    if not os.path.isfile(os.path.join(end, ".engram", "knowledge.db")):
        raise Refusal("the end state has no .engram/knowledge.db")
    if not os.path.isdir(os.path.join(end, ".claude")):
        raise Refusal("the end state has no .claude/ folder")
    outside = check_end_state_links(end, prot)
    if a.continue_reading:
        qids = []
    else:
        if not os.path.isfile(a.question_file):
            raise Refusal(f"the question file {a.question_file} is missing")
        qids = load_questions(a.question_file)
    if not os.path.isfile(a.components):
        raise Refusal(f"the components file {a.components} is missing")
    facts = (a.plant_builtin, a.plant_engram, a.plant_absent)
    plant = any(x is not None for x in facts + (a.plant_question,))
    plant_mode = "none"
    if plant:
        given = [bool(x and x.strip()) for x in facts]
        if a.plant_question is not None and a.plant_builtin is None:
            raise Refusal(f"--plant-question needs --plant-builtin (it only qualifies the built-in plant); {PLANT_SETS}")
        if all(given):
            plant_mode = "both channels"
        elif a.plant_builtin is None and given[1] and given[2]:
            plant_mode = "engram-only (no built-in plant)"
        else:
            raise Refusal(f"the plant flags are a partial plant set; {PLANT_SETS}")
    venv_py = os.path.join(end, ".engram", "venv", "bin", "python")
    if plant and not os.path.exists(venv_py):
        raise Refusal("planting needs the end state's .engram/venv/bin/python, which is missing")
    for hook in ("P1_FEED4", "P1_PLANT_CONTROL", "P1_AFTER_COPY_HOOK"):
        if env.get(hook) and not os.path.isfile(env[hook]):
            raise Refusal(f"{hook} is set to a file that does not exist")
    for need in ("feed4.py", "feed.py", "answer-delivery-check.py", "plant-control.py") + (
            ("reading-delivery-check.py",) if a.continue_reading else ()):
        if not os.path.isfile(os.path.join(HERE, need)):
            raise Refusal(f"{need} is missing beside this script")
    stamp = env.get("P1_UTC_STAMP") or datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    aside = aside_path(slot, a.label, stamp)
    if os.path.lexists(slot) and os.path.lexists(aside):
        raise Refusal(f"the aside path {aside} already exists")
    c = {"outside_links": outside, "protected": prot, "end": end, "slot": slot, "rundir": rundir, "qids": qids, "plant": plant, "plant_mode": plant_mode,
         "parquet_sha256": parquet_sha, "aside": aside, "py": env["BEAM_PY"], "created": []}
    if a.continue_reading:
        c.update(continue_step1(a, env, end, launcher_paths(slot, env["BEAM_RUNS_DIR"], a.label, stamp, end, prot)))
    return c


# ----------------------------------------------------------------------------------------------------------- the run
def feed4_args(a, c, out):
    if a.continue_reading:
        return ["--arm-home", c["slot"], "--out", out, "--conv", "9", "--resume", a.session, "--start", str(a.start),
                "--turns", str(a.through), "--per-round", str(a.per_round), "--env", WINDOW, "--expect-components", a.components]
    return ["--arm-home", c["slot"], "--out", out, "--conv", "9", "--turns", "0", "--resume", a.session,
            "--force-compact", "--question-file", a.question_file, "--env", WINDOW,
            "--expect-components", a.components]


def check_continue_plan(cont, full, a):
    """None if the continue plan is right, else the reason. --turns is feed4's INCLUSIVE END INDEX, so the plan must hold
    exactly (through - start + 1) / per-round reading messages carrying exchanges start..through in order, no compaction and
    no question, and each must be byte-equal to the message a FULL run (same per-round, from exchange 1, no resume) sends
    for the same exchanges (design A1 b): a resume must add nothing."""
    N, M, K = a.start, a.through, a.per_round
    if not (isinstance(cont, list) and all(isinstance(m, dict) for m in cont)):
        return "the continue plan is not a list of messages"
    for m in cont:
        if m.get("kind") != "exchange":
            return f"the continue plan holds a {m.get('kind')!r} message (only reading messages are allowed: no compaction, no question)"
    if len(cont) != (M - N + 1) // K:
        return f"the continue plan has {len(cont)} messages, expected {(M - N + 1) // K}"
    want = [list(range(N + i * K, N + (i + 1) * K)) for i in range((M - N + 1) // K)]
    if [m.get("exchanges") for m in cont] != want:
        return f"the continue plan's exchanges are {[m.get('exchanges') for m in cont]}, expected {want}"
    if not (isinstance(full, list) and all(isinstance(m, dict) for m in full)):
        return "the full-run plan is not a list of messages"
    ref = full[(N - 1) // K: M // K]
    if cont != ref:
        return f"the continue plan is not byte-equal to the full run's messages for exchanges {N}..{M} (a resume must add nothing)"
    return None


def remove_saved(c):
    """Remove what THIS run created at the save path and the hashes path (c["created"], recorded at the moment of each
    exclusive create), saying so. A path this run did not create is never removed, whatever its name."""
    gone = False
    for path in c.get("created", []):
        if os.path.lexists(path):
            shutil.rmtree(path) if os.path.isdir(path) and not os.path.islink(path) else os.unlink(path)
            gone = True
    c["created"] = []
    if gone:
        c["saved_removed"] = f"saved end state removed: {c['save']}"
        print(c["saved_removed"])


def save_end_state(a, c, steps):
    """C6: copy (cp -a, never a move) the slot's contents to --save-end-state, hash the copy the way the protected homes are
    hashed, write the hashes to PATH.hashes.txt and keep the lines for setup.txt. Both paths are created EXCLUSIVELY here
    (os.mkdir without exist_ok; O_CREAT | O_EXCL), because step 1 ran hours earlier and a caller-chosen path may exist
    now: if either does, exit 3 and nothing of the caller's is touched. Any later failure removes only what this run
    created (c["created"])."""
    step = "9b save the end state"
    left = slot_pids(c["slot"])  # quiescence: the stop step's grace period has passed; a live slot process could still write
    if left:
        steps.append((step, 3))
        print(f"STOP: slot process(es) {left} still running after the stop step's grace period; nothing saved")
        return 3
    hashes_file = None

    def fail(code, msg):
        steps.append((step, code)); print(msg)
        if hashes_file is not None:
            hashes_file.close()
        remove_saved(c)
        return 3

    try:
        os.mkdir(c["save"]); c["created"].append(c["save"])
        hashes_file = os.fdopen(os.open(c["hashes"], os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666), "w")
        c["created"].append(c["hashes"])
    except FileExistsError as e:
        return fail(3, f"STOP: {e.filename} appeared after step 1 (it exists now); this run never overwrites or removes a path "
                       "it did not create; nothing saved")
    except OSError as e:
        return fail(3, f"STOP: cannot create the save path or its hashes file ({type(e).__name__}: {e}); nothing saved")
    try:
        r = subprocess.run(["cp", "-a", "--", os.path.join(c["slot"], "."), c["save"]])  # the slot's CONTENTS into the directory made above
        if r.returncode:
            return fail(r.returncode, "STOP: copying the slot to --save-end-state failed")
        marker = os.path.join(c["save"], ".disposable-copy")  # a preserved end state is not a disposable copy
        if os.path.lexists(marker):
            os.unlink(marker)
        want, got = protected_store_hash(c["slot"]), protected_store_hash(c["save"])
        if got[0] != want[0]:
            return fail(3, f"STOP: the saved copy's store differs from the slot's\n  slot:  sha256={want[0]} tables={want[1]} rows={want[2]}"
                           f"\n  saved: sha256={got[0]} tables={got[1]} rows={got[2]}")
        check_end_state_links(c["save"], c["protected"])  # the check the NEXT run's step 1 will make on this end state
        rec = home_record(c["save"])
        hashes_file.write(rec); hashes_file.close()
    except Refusal as e:
        return fail(3, f"STOP: the saved end state would be refused by the next run ({e})")
    except Exception as e:  # noqa: BLE001
        return fail(3, f"STOP: hashing the saved end state failed ({type(e).__name__}: {e})")
    c["saved_lines"] = [f"saved end state: {c['save']}", "saved end state: .disposable-copy marker removed (the slot keeps its own)"] + rec.splitlines()
    print("".join(l + "\n" for l in c["saved_lines"]), end="")
    steps.append((step, 0))
    return 0


def work(a, c, steps):
    """Steps 3 to 9. Returns the exit code (0 = all good); records each step's own exit code in `steps`."""
    slot, rundir, py = c["slot"], c["rundir"], c["py"]
    feed4 = os.environ.get("P1_FEED4") or os.path.join(HERE, "feed4.py")
    plant_tool = os.environ.get("P1_PLANT_CONTROL") or os.path.join(HERE, "plant-control.py")
    stop_slot_processes(slot); steps.append(("3 stop slot processes", 0))
    if os.path.lexists(slot):
        if os.path.lexists(c["aside"]):
            steps.append(("4 move the slot aside", 2)); print(f"REFUSE: the aside path {c['aside']} exists"); return 2
        os.rename(slot, c["aside"])
        print(f"moved the existing slot aside: {c['aside']}")
    steps.append(("4 move the slot aside", 0))
    r = subprocess.run(["cp", "-a", "--", c["end"], slot])
    if r.returncode:
        steps.append(("5 copy", r.returncode)); print("STOP: the copy failed"); return 3
    for dp, dns, fns in os.walk(slot):
        for n in dns + fns:
            full = os.path.join(dp, n)
            if not os.path.islink(full):
                os.chmod(full, os.stat(full).st_mode | 0o200)
    open(os.path.join(slot, ".disposable-copy"), "a").close()
    if os.environ.get("P1_AFTER_COPY_HOOK"):
        subprocess.run([py, "-I", os.environ["P1_AFTER_COPY_HOOK"], slot])
    want = c["before_store"]
    got = store_content_hash(os.path.join(slot, ".engram", "knowledge.db"))
    if got[0] != want[0]:
        print(f"STOP: the copy's store differs from the end state's\n  end state: sha256={want[0]} tables={want[1]} rows={want[2]}"
              f"\n  slot copy: sha256={got[0]} tables={got[1]} rows={got[2]}")
        steps.append(("5 copy and fidelity check", 3)); return 3
    print(f"copy verified: tables={got[1]} rows={got[2]} sha256={got[0]}")
    steps.append(("5 copy and fidelity check", 0))
    raised = os.environ.get("P1_TEST_RAISE")
    if raised:
        raise {"KeyboardInterrupt": KeyboardInterrupt, "SystemExit": SystemExit}.get(raised, RuntimeError)("injected")
    if c["plant"]:
        cmd = [os.path.join(slot, ".engram", "venv", "bin", "python"), plant_tool, "--home", slot,
               *(["--builtin-fact", a.plant_builtin] if a.plant_builtin is not None else []),
               "--engram-fact", a.plant_engram, "--absent-fact", a.plant_absent,
               "--evidence-dir", os.path.join(rundir, "plant-evidence")]
        if a.plant_question is not None:  # step 1 refused a question without --plant-builtin
            cmd += ["--question", a.plant_question]
        pr = subprocess.run(cmd, env=dict(os.environ, P1_PROTECTED=os.environ["P1_PROTECTED"])).returncode
        steps.append(("6 plant", pr))
        if pr:
            print(f"STOP: plant-control exited {pr}; no student run")
            return 5 if pr == 3 else 4
    else:
        steps.append(("6 plant", 0))
    plan_path = os.path.join(rundir, "plan.json")
    with open(plan_path, "w") as f:
        pr = subprocess.run([py, "-I", feed4, *feed4_args(a, c, os.path.join(rundir, "plan-dump")), "--dump-plan"],
                            stdout=f).returncode
    if pr:
        steps.append(("7 plan dump", pr)); print(f"STOP: the plan dump exited {pr}"); return 3
    if a.continue_reading:
        full_path = os.path.join(rundir, "plan-full.json")
        with open(full_path, "w") as f:  # a FULL run's plan for the same K, from exchange 1, no resume: the comparison
            pr = subprocess.run([py, "-I", feed4, "--arm-home", slot, "--out", os.path.join(rundir, "plan-dump-full"),
                                 "--conv", "9", "--start", "1", "--turns", str(a.through), "--per-round", str(a.per_round),
                                 "--expect-components", a.components, "--dump-plan"], stdout=f).returncode
        if pr:
            steps.append(("7 plan dump", pr)); print(f"STOP: the full-run plan dump exited {pr}"); return 3
        try:
            why = check_continue_plan(json.load(open(plan_path)), json.load(open(full_path)), a)
        except (OSError, ValueError) as e:
            why = f"a plan dump is not readable JSON ({e})"
        if why:
            steps.append(("7 plan check", 3)); print(f"STOP: the continue plan is wrong: {why}"); return 3
        ok = True
    else:
        try:
            plan = json.load(open(plan_path))
            ok = (isinstance(plan, list) and len(plan) == 1 + len(c["qids"]) and plan[0].get("kind") == "compact"
                  and [p.get("kind") for p in plan[1:]] == ["question"] * len(c["qids"])
                  and [p.get("id") for p in plan[1:]] == c["qids"])
        except (OSError, ValueError, AttributeError):
            ok = False
        if not ok:
            steps.append(("7 plan check", 3)); print("STOP: the plan is not exactly [compact, q1..qN] in the question file's order"); return 3
    steps.append(("7 plan check", 0))
    if a.dry_run:
        steps.append(("8 student run", "skipped (--dry-run)")); steps.append(("9 after the run", "skipped (--dry-run)"))
        return 0
    frc = subprocess.run([py, "-I", feed4, *feed4_args(a, c, os.path.join(rundir, "run"))]).returncode
    steps.append(("8 student run", frc))
    stop_slot_processes(slot)
    proj = os.path.join(slot, ".claude", "projects")
    if os.path.isdir(proj):
        shutil.copytree(proj, os.path.join(rundir, "transcripts"), symlinks=True)
    with open(os.path.join(rundir, "delivery.txt"), "w") as f:
        if a.continue_reading:  # answer-delivery-check.py refuses reading turns by design, so reading has its own check
            drc = subprocess.run([py, "-I", os.path.join(HERE, "reading-delivery-check.py"), "--turns",
                                  os.path.join(rundir, "run", "turns.jsonl"), "--plan", plan_path, "--events",
                                  os.path.join(rundir, "run", "events.jsonl"), "--session", a.session],
                                 stdout=f, stderr=subprocess.STDOUT).returncode
        else:
            drc = subprocess.run([py, "-I", os.path.join(HERE, "answer-delivery-check.py"), "--turns",
                                  os.path.join(rundir, "run", "turns.jsonl"), "--questions", a.question_file,
                                  "--session", a.session], stdout=f, stderr=subprocess.STDOUT).returncode
    print(open(os.path.join(rundir, "delivery.txt")).read(), end="")
    steps.append(("9 after the run (delivery check)", drc))
    if a.continue_reading and not frc and not drc:
        return save_end_state(a, c, steps)
    return 3 if frc else (1 if drc else 0)


def write_setup(a, c, steps, start, rc):
    cont = getattr(a, "continue_reading", False)  # a bare namespace from an older caller has no such field
    r = subprocess.run(["git", "-C", HERE, "rev-parse", "HEAD"], capture_output=True, text=True)
    lines = [r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else "unknown (no git commit id)"]
    qfile = [] if cont else [(os.path.basename(a.question_file), a.question_file)]  # no question file when continuing
    for label, path in (("p1-session.py", os.path.abspath(__file__)), ("feed4.py", os.path.join(HERE, "feed4.py")),
                        ("feed.py", os.path.join(HERE, "feed.py")), *qfile,
                        (os.path.basename(a.components), a.components),
                        ("answer-delivery-check.py", os.path.join(HERE, "answer-delivery-check.py")),
                        ("plant-control.py", os.path.join(HERE, "plant-control.py"))):
        lines.append(f"{file_sha256(path)}  {label}")
    if cont:
        lines.append(f"{file_sha256(os.path.join(HERE, 'reading-delivery-check.py'))}  reading-delivery-check.py")
    for hook, label in (("P1_FEED4", "feed4 override"), ("P1_PLANT_CONTROL", "plant-control override")):
        if os.environ.get(hook):
            lines.append(f"{file_sha256(os.environ[hook])}  {label} ({hook}): {os.path.basename(os.environ[hook])}")
    lines.append(f"plant mode: {c['plant_mode']}")
    lines.append(f"{c['parquet_sha256']}  BEAM_PARQUET")
    lines.append(dataset_check_line(os.environ))
    if cont:
        lines.append("mode: continue-reading")
        lines.append(f"continue range: exchanges {a.start}..{a.through} at per-round {a.per_round}")
        lines.append(f"expect-store-sha256: {a.expect_store_sha256} (matched the end state)")
        lines += c["serving"]
        if a.expect_serving is not None:
            lines.append(f"{file_sha256(a.expect_serving)}  expect-serving file {os.path.basename(a.expect_serving)} (matched)")
    lines.append(f"start {start}")
    lines.append(f"end {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    lines += [f"step {name}: exit {code}" for name, code in steps]
    if cont:
        lines += c.get("saved_lines", [])
        if c.get("saved_removed"):
            lines.append(c["saved_removed"])
    lines.append(f"final exit {rc}")
    with open(os.path.join(c["rundir"], "setup.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--end-state", required=True); ap.add_argument("--session", required=True)
    ap.add_argument("--label", required=True); ap.add_argument("--question-file")  # required unless --continue-reading
    ap.add_argument("--components", required=True)
    ap.add_argument("--plant-builtin"); ap.add_argument("--plant-engram"); ap.add_argument("--plant-absent")
    ap.add_argument("--plant-question"); ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--continue-reading", action="store_true")
    ap.add_argument("--start", type=int); ap.add_argument("--through", type=int); ap.add_argument("--per-round", type=int)
    ap.add_argument("--save-end-state"); ap.add_argument("--expect-store-sha256"); ap.add_argument("--expect-serving")
    a = ap.parse_args(argv)
    if a.continue_reading:
        for flag, val in (("--question-file", a.question_file), ("--plant-builtin", a.plant_builtin),
                          ("--plant-engram", a.plant_engram), ("--plant-absent", a.plant_absent),
                          ("--plant-question", a.plant_question)):
            if val is not None:
                ap.error(f"--continue-reading cannot be combined with {flag}")
        for flag, val in (("--start", a.start), ("--through", a.through), ("--per-round", a.per_round),
                          ("--save-end-state", a.save_end_state), ("--expect-store-sha256", a.expect_store_sha256)):
            if val is None:
                ap.error(f"--continue-reading requires {flag}")
    else:
        if a.question_file is None:
            ap.error("the following arguments are required: --question-file")
        for name in CONTINUE_ONLY:
            if getattr(a, name) is not None:
                ap.error(f"--{name.replace('_', '-')} is only valid with --continue-reading")
    start = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    steps = []
    try:
        c = step1(a)
        before = records(c["protected"], tolerant=False)
        c["before_store"] = protected_store_hash(c["end"])
    except ServingFailed as e:  # nothing has been touched yet: the serving record is read in step 1
        print(f"SERVING RECORD FAILED: {e}", file=sys.stderr)
        return 3
    except (Refusal, sqlite3.Error, OSError) as e:  # nothing has been touched yet: an unreadable input is a refusal
        print(f"REFUSE: {e}", file=sys.stderr)
        return 2
    steps.append(("1 refusals", 0))
    print(f"symlinks pointing outside the end state: {c['outside_links']}")
    os.makedirs(c["rundir"])
    pending = None
    try:
        with open(os.path.join(c["rundir"], "before-hashes.txt"), "w") as f:
            f.write("".join(before[h] for h in c["protected"]))
        print("".join(before[h] for h in c["protected"]), end="")
        steps.append(("2 before-hashes", 0))
        rc = work(a, c, steps)
    except BaseException as e:  # noqa: BLE001  KeyboardInterrupt and SystemExit too: steps 10 and 11 still run
        pending = e
        traceback.print_exc()
        steps.append((f"unexpected {type(e).__name__}", 3))
        rc = 3
    # Steps 10 and 11 on EVERY exit path after the run directory exists. Each guards its own failure so that a failure
    # in one never skips the other and never replaces exit 5.
    changed, unavailable = [], None
    try:
        after = records(c["protected"], tolerant=True)
        changed = changed_homes(before, after)
        with open(os.path.join(c["rundir"], "after-hashes.txt"), "w") as f:
            f.write("".join(after[h] for h in c["protected"]))
        steps.append(("10 after-hashes", 5 if changed else 0))
    except BaseException as e:  # noqa: BLE001
        if a.continue_reading:
            # A failure to compute or write the proof is not a difference in a protected home: it gets its own line and the
            # launcher's own exit 3, and only a real difference found by the comparison is "PROTECTED CHANGED" (exit 5).
            unavailable = f"{type(e).__name__}: {e}"
            steps.append(("10 after-hashes", 5 if changed else 3))
        else:  # the answering mode stays byte-for-byte as pinned: an unprovable pass is treated as every home changed
            print(f"ERROR: the after-hash step failed ({type(e).__name__}: {e}); treating the protected homes as changed",
                  file=sys.stderr)
            changed = list(before); steps.append(("10 after-hashes", "failed"))
    if unavailable is not None:
        print(f"AFTER-HASHES UNAVAILABLE: {unavailable}; the protected homes could not be re-checked "
              "(this is not a finding that anything changed)")
        if not changed and rc in (0, 1):
            rc = 3
    if changed:
        for h in changed:
            print(f"changed home: {h}")
        print(f"PROTECTED CHANGED: {len(changed)} home(s)")
        rc = 5
    if rc and a.continue_reading and c["created"]:  # a saved end state exists only after a fully good run; only what this run created is removed
        try:
            remove_saved(c)
        except BaseException as e:  # noqa: BLE001
            print(f"ERROR: the saved end state {c['save']} could not be removed ({type(e).__name__}: {e})", file=sys.stderr)
    try:
        write_setup(a, c, steps, start, rc)
    except BaseException as e:  # noqa: BLE001
        print(f"ERROR: setup.txt could not be written ({type(e).__name__}: {e})", file=sys.stderr)
    reraise = pending is not None and rc != 5 and not isinstance(pending, Exception)
    if reraise and isinstance(pending, SystemExit):  # print the status the process will really have
        shown = 0 if pending.code is None else (pending.code if isinstance(pending.code, int) else 1)
        print(f"exit {shown}")
    elif reraise:
        print(f"exit: interrupted ({type(pending).__name__}), the process ends by that interruption")
    else:
        print(f"exit {rc}")
    if reraise:
        raise pending  # an interruption with nothing protected changed keeps its own exit behaviour
    return rc


if __name__ == "__main__":
    sys.exit(main())
