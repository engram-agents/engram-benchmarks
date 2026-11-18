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
  P1_PROTECTED    colon-separated preserved-home paths; every entry must exist; --end-state must be one of them

usage: p1-session.py --end-state PATH --session ID --label NAME --question-file F --components F
                     [--plant-builtin T --plant-engram T --plant-absent T [--plant-question TEXT]] [--dry-run]

Steps (every refusal in step 1 happens before anything is touched: no process killed, no copy, no directory made):
 1 refusals, exit 2: a test-only hook variable set without P1_TEST_HOOKS=1; a relative symlink in the end state that
   climbs above its root; a symlink in the end state resolving to, inside or above a protected path (a relative link
   that stays inside the end state is fine; the count of links pointing outside it is printed); BEAM_RUNS_DIR equal
   to, inside or containing a protected path, or equal to or inside the slot; an env var missing; a label outside
   [A-Za-z0-9._-]; a P1_PROTECTED entry that does not exist;
   --end-state (by realpath) not one of P1_PROTECTED; the slot equal to, inside or containing a protected path; the run
   directory exists; the end state lacks .engram/knowledge.db or .claude/; the question file or components file
   missing or malformed; a partial plant set (any plant flag without all of --plant-builtin, --plant-engram,
   --plant-absent); planting when the end state has no .engram/venv/bin/python; the aside path already exists.
 2 before-hashes.txt: for EVERY protected home, the store content hash (store_content_hash below) and the sha256 of
   every file under its built-in memory folders (.claude/projects/*/memory/**).
 3 stop processes whose command line contains <slot>/.engram/ (SIGTERM; the processes of this launcher are exempt).
 4 an existing slot is moved to <slot>.aside-<label>-<UTC stamp> (never deleted).
 5 cp -a end state -> slot; create <slot>/.disposable-copy; the slot's store hash must equal the end state's (else exit 3,
   both printed).
 6 plant (only with plant flags): plant-control.py with the slot's own ENGRAM venv python, P1_PROTECTED exported, the
   evidence dir <rundir>/plant-evidence (outside the student's home). Its exit 3 (a protected entry changed) is exit 5;
   any other nonzero is exit 4; either way no student run.
 7 feed4.py --dump-plan with the step-8 arguments -> plan.json; it must be exactly [compact, q1..qN] in file order.
 8 unless --dry-run: feed4.py --arm-home <slot> --out <rundir>/run --conv 9 --turns 0 --resume ID --force-compact
   --question-file F --env CLAUDE_CODE_MAX_CONTEXT_TOKENS=131072 --expect-components C
 9 (not on --dry-run) stop slot processes; copy <slot>/.claude/projects to <rundir>/transcripts;
   answer-delivery-check.py -> delivery.txt.
10 after-hashes.txt, same method for every protected home; ANY difference prints `changed home: <path>` and
   `PROTECTED CHANGED: n home(s)` and is exit 5. Steps 10 and 11 run on every exit path after the run directory exists.
11 setup.txt: first line the benchmarks commit id, then the sha256 of this script, feed4.py, feed.py, the question file,
   the components file, answer-delivery-check.py and plant-control.py, start/end UTC, and each step's exit code.
Exit codes: 0 all good; 1 delivery check failed; 2 refused; 3 copy, plan check or feed4 failed; 4 plant failed;
5 a protected home changed (overrides every other code).

A protected home's store is never opened with sqlite: it is hashed from a byte copy of knowledge.db, -wal and -shm in a
temporary directory (protected_store_hash), because even a read-only sqlite connection writes -shm read marks. The memory
folders are only read. Only the disposable slot copy is hashed in place.

TEST-ONLY HOOKS (never set in a real run; each is documented in tests/test_p1_session.py). Setting any of them without
P1_TEST_HOOKS=1 is refused in step 1 (exit 2), so a stray variable can never silently change a real run:
  P1_FEED4            run this script in place of feed4.py (the plan dump and the run)
  P1_PLANT_CONTROL    run this script in place of plant-control.py
  P1_UTC_STAMP        a fixed stamp for the aside path
  P1_AFTER_COPY_HOOK  `BEAM_PY -I HOOK SLOT`, run between the copy and the copy-fidelity check
  P1_TEST_RAISE       KeyboardInterrupt | SystemExit | Exception: raised once, just after the copy has been verified
"""
import argparse, datetime, hashlib, json, os, re, shutil, sqlite3, subprocess, sys, tempfile, time, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
REQUIRED_ENV = ("BEAM_PY", "BEAM_ARM_HOME", "BEAM_RUNS_DIR", "P1_PROTECTED")
TEST_HOOKS = ("P1_FEED4", "P1_PLANT_CONTROL", "P1_UTC_STAMP", "P1_AFTER_COPY_HOOK", "P1_TEST_RAISE")
LABEL = re.compile(r"[A-Za-z0-9._-]+")
WINDOW = "CLAUDE_CODE_MAX_CONTEXT_TOKENS=131072"


class Refusal(Exception):
    pass


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


def step1(a):
    env = os.environ
    for v in REQUIRED_ENV:
        if not env.get(v):
            raise Refusal(f"{v} is not set")
    for hook in TEST_HOOKS:
        if env.get(hook) and env.get("P1_TEST_HOOKS") != "1":
            raise Refusal(f"{hook} is a test-only hook and is refused unless P1_TEST_HOOKS=1 is also set "
                          "(a stray variable must never change a real run)")
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
    rundir = os.path.join(env["BEAM_RUNS_DIR"], f"p1-{a.label}")
    if os.path.lexists(rundir):
        raise Refusal(f"the run directory {rundir} exists (run directories are never reused)")
    if not os.path.isfile(os.path.join(end, ".engram", "knowledge.db")):
        raise Refusal("the end state has no .engram/knowledge.db")
    if not os.path.isdir(os.path.join(end, ".claude")):
        raise Refusal("the end state has no .claude/ folder")
    outside = check_end_state_links(end, prot)
    if not os.path.isfile(a.question_file):
        raise Refusal(f"the question file {a.question_file} is missing")
    qids = load_questions(a.question_file)
    if not os.path.isfile(a.components):
        raise Refusal(f"the components file {a.components} is missing")
    facts = (a.plant_builtin, a.plant_engram, a.plant_absent)
    plant = any(x is not None for x in facts + (a.plant_question,))
    if plant and not all(x and x.strip() for x in facts):
        raise Refusal("a plant needs all of --plant-builtin, --plant-engram and --plant-absent (a partial plant set)")
    venv_py = os.path.join(end, ".engram", "venv", "bin", "python")
    if plant and not os.path.exists(venv_py):
        raise Refusal("planting needs the end state's .engram/venv/bin/python, which is missing")
    for hook in ("P1_FEED4", "P1_PLANT_CONTROL", "P1_AFTER_COPY_HOOK"):
        if env.get(hook) and not os.path.isfile(env[hook]):
            raise Refusal(f"{hook} is set to a file that does not exist")
    for need in ("feed4.py", "feed.py", "answer-delivery-check.py", "plant-control.py"):
        if not os.path.isfile(os.path.join(HERE, need)):
            raise Refusal(f"{need} is missing beside this script")
    stamp = env.get("P1_UTC_STAMP") or datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    aside = f"{slot}.aside-{a.label}-{stamp}"
    if os.path.lexists(slot) and os.path.lexists(aside):
        raise Refusal(f"the aside path {aside} already exists")
    return {"outside_links": outside, "protected": prot, "end": end, "slot": slot, "rundir": rundir, "qids": qids, "plant": plant,
            "aside": aside, "py": env["BEAM_PY"]}


# ----------------------------------------------------------------------------------------------------------- the run
def feed4_args(a, c, out):
    return ["--arm-home", c["slot"], "--out", out, "--conv", "9", "--turns", "0", "--resume", a.session,
            "--force-compact", "--question-file", a.question_file, "--env", WINDOW,
            "--expect-components", a.components]


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
               "--builtin-fact", a.plant_builtin, "--engram-fact", a.plant_engram, "--absent-fact", a.plant_absent,
               "--evidence-dir", os.path.join(rundir, "plant-evidence")]
        if a.plant_question is not None:
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
        drc = subprocess.run([py, "-I", os.path.join(HERE, "answer-delivery-check.py"), "--turns",
                              os.path.join(rundir, "run", "turns.jsonl"), "--questions", a.question_file,
                              "--session", a.session], stdout=f, stderr=subprocess.STDOUT).returncode
    print(open(os.path.join(rundir, "delivery.txt")).read(), end="")
    steps.append(("9 after the run (delivery check)", drc))
    return 3 if frc else (1 if drc else 0)


def write_setup(a, c, steps, start, rc):
    r = subprocess.run(["git", "-C", HERE, "rev-parse", "HEAD"], capture_output=True, text=True)
    lines = [r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else "unknown (no git commit id)"]
    for label, path in (("p1-session.py", os.path.abspath(__file__)), ("feed4.py", os.path.join(HERE, "feed4.py")),
                        ("feed.py", os.path.join(HERE, "feed.py")), (os.path.basename(a.question_file), a.question_file),
                        (os.path.basename(a.components), a.components),
                        ("answer-delivery-check.py", os.path.join(HERE, "answer-delivery-check.py")),
                        ("plant-control.py", os.path.join(HERE, "plant-control.py"))):
        lines.append(f"{file_sha256(path)}  {label}")
    for hook, label in (("P1_FEED4", "feed4 override"), ("P1_PLANT_CONTROL", "plant-control override")):
        if os.environ.get(hook):
            lines.append(f"{file_sha256(os.environ[hook])}  {label} ({hook}): {os.path.basename(os.environ[hook])}")
    lines.append(f"start {start}")
    lines.append(f"end {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    lines += [f"step {name}: exit {code}" for name, code in steps]
    lines.append(f"final exit {rc}")
    with open(os.path.join(c["rundir"], "setup.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--end-state", required=True); ap.add_argument("--session", required=True)
    ap.add_argument("--label", required=True); ap.add_argument("--question-file", required=True)
    ap.add_argument("--components", required=True)
    ap.add_argument("--plant-builtin"); ap.add_argument("--plant-engram"); ap.add_argument("--plant-absent")
    ap.add_argument("--plant-question"); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    start = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    steps = []
    try:
        c = step1(a)
        before = records(c["protected"], tolerant=False)
        c["before_store"] = protected_store_hash(c["end"])
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
    changed = []
    try:
        after = records(c["protected"], tolerant=True)
        with open(os.path.join(c["rundir"], "after-hashes.txt"), "w") as f:
            f.write("".join(after[h] for h in c["protected"]))
        changed = changed_homes(before, after)
        steps.append(("10 after-hashes", 5 if changed else 0))
    except BaseException as e:  # noqa: BLE001
        print(f"ERROR: the after-hash step failed ({type(e).__name__}: {e}); treating the protected homes as changed",
              file=sys.stderr)
        changed = list(before); steps.append(("10 after-hashes", "failed"))
    if changed:
        for h in changed:
            print(f"changed home: {h}")
        print(f"PROTECTED CHANGED: {len(changed)} home(s)")
        rc = 5
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
