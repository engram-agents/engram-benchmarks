"""Shared helpers for the P1 harness cells. Synthetic fixtures only: no real data, no student model, no Ollama."""
import hashlib, json, os, shutil, signal, stat, subprocess, sys, tempfile, time
import pytest

TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _has_pyarrow(py):
    try:
        return subprocess.run([py, "-c", "import pyarrow"], capture_output=True).returncode == 0
    except OSError:
        return False


@pytest.fixture(scope="session")
def arrow_python():
    """A python that has pyarrow: $BEAM_PY, else this interpreter. Cells needing the parquet skip without one."""
    for py in (os.environ.get("BEAM_PY"), sys.executable):
        if py and _has_pyarrow(py):
            return py
    pytest.skip("no python with pyarrow (set BEAM_PY)")


@pytest.fixture(scope="session")
def synthetic_parquet(arrow_python, tmp_path_factory):
    p = tmp_path_factory.mktemp("pq") / "syn.parquet"
    code = (
        "import pyarrow as pa, pyarrow.parquet as pq, sys\n"
        "sess=[]\n"
        "for s in range(2):\n"
        "    m=[]\n"
        "    for i in range(4):\n"
        "        m.append({'role':'user','content':f'user {s}.{i}','time_anchor':'May-01-2024' if i==0 else None})\n"
        "        m.append({'role':'assistant','content':f'asst {s}.{i}','time_anchor':None})\n"
        "    sess.append(m)\n"
        "t=pa.table({'conversation_id':[9],'chat':[sess],'probing_questions':[str({'a':[{'question':'Q one?'},{'question':'Q two?'}]})]})\n"
        "pq.write_table(t, sys.argv[1])\n")
    subprocess.run([arrow_python, "-c", code, str(p)], check=True)
    return str(p)


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f)
    return str(path)


MEMORY_INDEX = ("- [Old pointer](feedback_old.md) \u2014 a pointer kept from before\n"
                "- [Other pointer](feedback_other.md) \u2014 another pointer kept from before\n")

# ---- a synthetic arm home for plant-control.py (no real model, no real preserved home) ----
SEED = (
    "import os, sys\n"
    "home = sys.argv[1]\n"
    "os.environ['ENGRAM_HOME'] = home + '/.engram'; os.environ['HOME'] = home\n"
    "os.environ['ENGRAM_NO_DB_GUARDS'] = '1'; os.environ['ENGRAM_NO_EMBEDDINGS'] = '1'\n"
    "sys.path.insert(0, home + '/.engram/marketplace/plugins/engram')\n"
    "import engram_core; c = engram_core._get_db(); c.close()\n"
    "import engram_epistemic\n"
    "print(engram_epistemic._add_axiom_impl(claim='seed axiom for the synthetic fixture', basis='fixture'))\n")


def engram_plugin_src():
    p = os.environ.get("P1_ENGRAM_PLUGIN")
    if not p or not os.path.isfile(os.path.join(p, "engram_observation.py")):
        pytest.skip("set P1_ENGRAM_PLUGIN to a plugin tree that holds engram_observation.py (an ENGRAM src/engram)")
    return p


@pytest.fixture(scope="session")
def arm_home_template(tmp_path_factory):
    """One synthetic arm home, built once: .claude with a memory folder under a project folder, a work folder, a
    transcript, and .engram with the plugin tree and a seeded knowledge.db. Copied per test."""
    src = engram_plugin_src()
    h = tmp_path_factory.mktemp("armtpl") / "home"
    plug = h / ".engram" / "marketplace" / "plugins" / "engram"
    shutil.copytree(src, plug, ignore=shutil.ignore_patterns("__pycache__", "tests"))
    (h / "work").mkdir()
    proj = h / ".claude" / "projects" / "-synthetic-work"
    (proj / "memory").mkdir(parents=True)
    (proj / "memory" / "MEMORY.md").write_text(MEMORY_INDEX)  # the index the student reads the folder through
    (proj / "session-0001.jsonl").write_text(json.dumps({"type": "user", "message": "an ordinary turn"}) + "\n")
    (h / ".claude" / "plugins" / "memory").mkdir(parents=True)  # a 'memory' dir under plugins/: memcheck excludes it
    r = subprocess.run([sys.executable, "-c", SEED, str(h)], capture_output=True, text=True,
                       env={"PATH": os.environ["PATH"]})
    assert r.returncode == 0 and "ax_0001" in r.stdout, r.stdout + r.stderr
    shutil.rmtree(h / ".engram" / "knowledge.db.setup.lockdir", ignore_errors=True)
    return str(h)


@pytest.fixture
def arm_home(arm_home_template, tmp_path):
    """A disposable copy of the synthetic arm home, marked, with an evidence dir beside it (outside the home)."""
    h = tmp_path / "home"
    shutil.copytree(arm_home_template, h, symlinks=True)
    (h / ".disposable-copy").write_text("")
    (tmp_path / "evidence").mkdir()
    return h


def memory_dir(h):
    return h / ".claude" / "projects" / "-synthetic-work" / "memory"


# A stand-in `systemctl` for hosts that have no systemd (a Mac): the launch module asks `systemctl --user` to stop a scope, to
# show its cgroup and to list units, and this answers as an EMPTY user manager (no units, nothing to stop). The cells that
# need a real user manager (real scopes, real boxes) are marked needs_box and skip there; the others run against this.
STUB_SYSTEMCTL = """#!/bin/sh
case "$*" in
  *is-active*) echo inactive; exit 3 ;;
esac
exit 0
"""


def install_stub_systemctl(dirpath):
    os.makedirs(dirpath, exist_ok=True)
    path = os.path.join(str(dirpath), "systemctl")
    with open(path, "w") as f:
        f.write(STUB_SYSTEMCTL)
    os.chmod(path, 0o755)
    return str(dirpath)


# Cells that run a student session through the launch module start the real student-sandbox.sh's own machinery or its stand-in
# on the host: they read /proc (start times, argv scans) and need bash 4, which a Mac does not have. One named marker, the SAME
# reason string as test_student_sandbox.py's: on such a host they skip BY NAME instead of failing.
LINUX_PROC = sys.platform.startswith("linux") and os.path.isdir("/proc/self")
NEEDS_BOX_REASON = ("needs Linux, bash 4 or newer, and a working bwrap (unprivileged user namespaces), plus a systemd user "
                    "manager that can start a capped scope: the sandbox is Linux-only")
needs_linux_wrapper = pytest.mark.skipif(not LINUX_PROC, reason=NEEDS_BOX_REASON)

# Cells that need only Linux's /proc and prctl, not the wrapper's bwrap or systemd: they read /proc (descriptors, process start
# times) or run the in-box supervisor of sandbox-forward.py, which makes its report descriptor private with prctl(PR_SET_DUMPABLE).
# A Mac has neither /proc nor prctl, so on one the supervisor refuses (exit 5) before it writes a line. One named marker, one reason.
NEEDS_PROC_REASON = ("needs Linux with /proc and prctl: the cell reads /proc (descriptors, process start times) or runs the in-box "
                     "supervisor, which makes its report descriptor private with prctl(PR_SET_DUMPABLE); a Mac has neither")
needs_linux_proc = pytest.mark.skipif(not LINUX_PROC, reason=NEEDS_PROC_REASON)

# An AF_UNIX path may not exceed 107 bytes, and a Mac's $TMPDIR (/var/folders/xx/<long>/T/) plus pytest's own folders is longer than
# that. A cell that binds or connects a socket under a directory of its own builds that directory here: a short REAL path under /tmp
# (real, because the launch module resolves symlinks: /tmp is /private/tmp on a Mac), removed after the cell.
_SHORT_DIRS = []


def short_dir(prefix="b"):
    d = os.path.realpath(tempfile.mkdtemp(prefix=prefix, dir="/tmp"))
    _SHORT_DIRS.append(d)
    return d


def _argv_of(pid):
    """The command line of `pid` as one string ('' when it cannot be read): /proc where there is one, else ps (a Mac)."""
    try:
        with open("/proc/%d/cmdline" % pid, "rb") as f:
            return f.read().replace(b"\0", b" ").decode(errors="replace")
    except OSError:
        pass
    try:
        return subprocess.run(["ps", "-o", "args=", "-p", str(pid)], capture_output=True, text=True).stdout
    except OSError:
        return ""


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def stop_stub_daemons(d):
    """Stop every stub daemon that a cell started under directory `d`, FAILURE OR NOT: the daemon's pid file is read, and only a
    process whose command line still names `d` is killed (a reused pid is never touched), then it is waited for. Returns the pids
    still alive afterwards. The cells' own paths stop the daemon only when they get that far (a supervisor that cannot tell its
    daemon is there, or a cell that fails before the stop, leaves it running, parented to init), so the teardown does it again.

    Why it happens, read off sandbox-forward.py: the supervisor takes the daemon's identity from /proc/<pid>/stat (proc_start), and
    daemon_up needs it. On a host WITHOUT /proc (a Mac; or Linux with /proc masked, the simulation) proc_start is None, so the daemon
    reads as already gone: the readiness wait ends 'exited-early' and the stop path reports 'already-gone' WITHOUT signalling it, and the
    daemon stays running. Production consequence: none, because the study box is Linux-only and always mounts its own /proc
    (student-sandbox.sh, `--proc /proc`); the cells that reach this path are marked needs_linux_proc and do not run on such a host.
    Only the pids named by the cell's own pid file are ever signalled, never a name or a pattern (the host is shared)."""
    left = []
    for root, _dirs, files in os.walk(d):
        if "recall-daemon.pid" not in files:
            continue
        try:
            with open(os.path.join(root, "recall-daemon.pid")) as f:
                pid = int(f.read().strip())
        except (OSError, ValueError):
            continue
        if pid > 1 and _pid_alive(pid) and d in _argv_of(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            end = time.time() + 5
            while _pid_alive(pid) and time.time() < end:
                time.sleep(0.05)
            if _pid_alive(pid):
                left.append(pid)
    return left


def remove_short_dirs():
    """Stop the stub daemons under, then remove, every short dir a cell made. Returns the pids that could not be stopped."""
    left = []
    while _SHORT_DIRS:
        d = _SHORT_DIRS.pop()
        left += stop_stub_daemons(d)
        shutil.rmtree(d, ignore_errors=True)
    return left


@pytest.fixture(autouse=True)
def _short_dirs_are_removed():
    yield
    left = remove_short_dirs()
    assert not left, "stub daemons of this cell are still alive after the teardown: %s" % left


def reader_log_for(path, events=()):
    """A launch log holding exactly the reader's own record of `events` (the form the log's reader writes: one `daemon-report seq=N
    time=T line=<event>` per accepted event, a `dropped` marker per drop, then ONE `closed` line), so the launch module's verdict can
    read the record it requires. `events` is the shape read_daemon_events returns: [(kind, {key: value})]. Returns the path."""
    lines, accepted, dropped = [], 0, 0
    for kind, f in events:
        n = len(lines) + 1
        if kind == "daemon-report-dropped":
            lines.append("daemon-report seq=%d time=1700000000.500000 dropped reason=%s bytes=%s count=%s" % (n, f["reason"], f["bytes"], f["count"]))
            dropped += 1
        else:
            lines.append("daemon-report seq=%d time=1700000000.500000 line=%s %s" % (n, kind, " ".join("%s=%s" % kv for kv in f.items())))
            accepted += 1
    lines.append("daemon-report seq=%d time=1700000000.500000 closed accepted=%d dropped=%d markers_suppressed=0 read_error=none"
                 % (len(lines) + 1, accepted, dropped))
    with open(str(path), "w") as fh:
        fh.write("\n".join(lines) + "\n")
    return str(path)
