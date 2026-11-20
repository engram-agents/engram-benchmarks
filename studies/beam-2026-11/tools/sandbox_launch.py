#!/usr/bin/env python3
"""The ONE door through which a BEAM student session is started (design A10). Standard library only. This file is the
study's harness, not shipped product code.

`run_feeder(py, feeder, argv, ...)` turns "run this feeder for a student session" into a wrapped launch and reads its
verdict. Every launcher in this directory that starts a feeder (feed.py, feed2.py, feed4.py: `FEEDERS`) calls it; a
launcher that starts a student any other way is retired (RETIRED-LAUNCHER marker) and a cell searches the tree for strays.

For a student session it
  1. makes a fresh directory holding `claude` (a COPY of student-sandbox.sh) and sandbox-forward.py, and puts it FIRST on
     the PATH it hands the feeder. A copy, not a symlink: the wrapper finds sandbox-forward.py next to the path it was
     started as, a symlink would look beside the link, and a copy cannot change under the run;
  2. chooses this session's SANDBOX_LOG, a path that does not exist before the launch (one log per launch);
  3. hashes the two copies and refuses, before anything starts, if either differs from the expected value (M4b);
  4. builds the feeder's `--env` list: every SANDBOX_* setting the wrapper requires, SANDBOX_LOG and the proctor binds.
     The feeder builds the student's environment from scratch (feed4.py / feed2.py `Student.__init__`), so a SANDBOX_*
     variable that is merely EXPORTED never reaches the wrapper; only an `--env` pair does (a cell shows it);
  5. runs the feeder, then `sandbox-forward.py log-verdict --log <that log>` and compares the launch line's
     wrapper_sha256 and forwarder_sha256 with the expected values (M5).
  6. TEARDOWN (round 2), in every case, whatever the feeder's exit code and even if it raised: reads `scope_unit`,
     `forwarder_pid`, `forwarder_start` and `bridge_sock` from the launch line, runs `systemctl --user stop <scope_unit>`, and
     asserts NOTHING of the launch remains (the scope's own cgroup empty; the forwarder pid gone or a different process, by
     start time; no process anywhere with the bridge socket path in its argv). A leftover is a LaunchStop naming each pid.
     A session whose log has no launch line (the wrapper refused before launching) has nothing to stop.
And BEFORE any launch (`state_dir`, required, no default: one record per launch, written before the session starts and
closed after the teardown passes) it refuses while any earlier record fails those three checks or any user scope unit named
`student-sandbox-*` is active (LaunchRefused naming each unit or pid and how to stop it). The module's stop is the
guarantee: the wrapper's own box teardown on a caller's SIGKILL has been seen to fail (mechanism unproven, filed separately).
A feeder call that starts no student (`--dump-plan`) runs through the same function with no wrapper and no log.

Refusals before anything starts raise LaunchRefused (exit 2 semantics, the message names the reason). A log-verdict
refusal or a launch-line hash mismatch after the session raises LaunchStop (a harness failure) BEFORE the caller can read
any answer of that session; its `.result` holds the feeder's own exit code. `flagged` is a verdict, never a stop.

What the module can and cannot see: it reads the feeder's argv (`--out`, `--env`), the feeder's environment
(BEAM_OLLAMA_URL) and the PATH the feeder's Popen will use. It cannot see a student started by anything else.
"""
import hashlib, ipaddress, itertools, json, os, re, secrets, shutil, signal, subprocess, sys, tempfile, time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
# The single list of student-starting implementations. Every process invocation of one by a launcher goes through
# run_feeder; the no-second-door cell reads this tuple, not a hand list.
FEEDERS = ("feed.py", "feed2.py", "feed4.py")
WRAPPER_SRC = os.path.join(HERE, "student-sandbox.sh")
FORWARDER_SRC = os.path.join(HERE, "sandbox-forward.py")
# Every SANDBOX_* name student-sandbox.sh refuses without (a cell derives this set from the wrapper's own source).
# SANDBOX_MODEL_ALLOW is required unless SANDBOX_MODEL_LEARN=1.
REQUIRED_SANDBOX = ("SANDBOX_SLOT", "SANDBOX_BINARY", "SANDBOX_BINARY_SHA256", "SANDBOX_MODEL_HOST",
                    "SANDBOX_MODEL_PORT", "SANDBOX_PROTECT", "SANDBOX_MODEL_ALLOW")
# Names the module itself sets for each launch; a caller may not supply them.
MODULE_OWNED = ("SANDBOX_LOG", "SANDBOX_RO_BINDS", "SANDBOX_RO_ROOT", "SANDBOX_RW_BINDS", "SANDBOX_RW_ROOT")
# feed.py's OLLAMA_URL: BEAM_OLLAMA_URL, else Ollama's documented default (a cell reads feed.py and requires this).
OLLAMA_DEFAULT = "http://localhost:11434"  # privacy-scan: allow (Ollama's documented default endpoint, as in feed.py)
VERDICT_NOT_FLAGGED = "not-flagged"
VERDICT_FLAGGED_PREFIX = "flagged:"
HEX64 = re.compile(r"[0-9a-f]{64}")
_SEQ = itertools.count(1)


class LaunchRefused(Exception):
    """A named refusal BEFORE anything started (exit 2 semantics). `.leftover_count` is how many leftovers of earlier
    launches the before-launch check found (0 for every other refusal): a caller reports it per run."""
    leftover_count = 0


class LaunchStop(Exception):
    """After the session: log-verdict refused, or the launch line's hashes differ from the expected ones. The caller must
    stop and read no answer of that session. `.result` is the LaunchResult (the feeder's exit code, the log)."""
    def __init__(self, message, result):
        super().__init__(message)
        self.result = result


class LaunchResult:
    def __init__(self, returncode, log=None, verdict=None, wrapper_sha256=None, forwarder_sha256=None):
        self.returncode, self.log, self.verdict = returncode, log, verdict
        self.wrapper_sha256, self.forwarder_sha256 = wrapper_sha256, forwarder_sha256


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_expected(path):
    """The expected-hashes file (no default; the scored run passes the registered one): exactly two lines,
    `wrapper_sha256=<64 hex>` then `forwarder_sha256=<64 hex>` (lower case). Anything else is a named refusal."""
    if not path:
        raise LaunchRefused("the expected-hashes file is not given (the module has no default)")
    try:
        text = open(path, encoding="utf-8").read()
    except (OSError, UnicodeDecodeError) as e:
        raise LaunchRefused(f"the expected-hashes file {path} cannot be read ({type(e).__name__})")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    keys = ("wrapper_sha256", "forwarder_sha256")
    if len(lines) != 2:
        raise LaunchRefused(f"the expected-hashes file {path} is malformed: it must hold exactly the two lines "
                            "wrapper_sha256=<64 hex> and forwarder_sha256=<64 hex>")
    out = {}
    for key, line in zip(keys, lines):
        name, eq, val = line.partition("=")
        if name != key or not eq or not HEX64.fullmatch(val):
            raise LaunchRefused(f"the expected-hashes file {path} is malformed: line {len(out) + 1} must be "
                                f"{key}=<64 lower-case hex>")
        out[key] = val
    return out


def required_names(settings):
    learn = settings.get("SANDBOX_MODEL_LEARN") == "1"
    return tuple(n for n in REQUIRED_SANDBOX if not (learn and n == "SANDBOX_MODEL_ALLOW"))


def check_settings(settings):
    """Refuse a missing or empty required SANDBOX_* setting, and any setting the module owns. Returns a clean copy."""
    for n in required_names(settings):
        if not settings.get(n):
            raise LaunchRefused(f"{n} is not set or is empty (the wrapper requires it; it must be passed to the feeder "
                                "as an --env pair, an exported variable never reaches it)")
    for n in MODULE_OWNED:
        if n in settings:
            raise LaunchRefused(f"{n} is set by the launch module for each launch; the caller may not supply it")
    for n in settings:
        if not n.startswith("SANDBOX_"):
            raise LaunchRefused(f"{n} is not a SANDBOX_* setting")
    return dict(settings)


class Sandbox:
    """What a launch needs besides the feeder call: the SANDBOX_* settings and the expected hashes."""
    def __init__(self, settings, expected_file):
        self.settings = check_settings(settings)
        self.expected = load_expected(expected_file)
        self.expected_file = expected_file


def env_pairs(argv):
    """The `--env KEY=VALUE` pairs in a feeder's argv, in order."""
    out = []
    for i, a in enumerate(argv):
        if a == "--env" and i + 1 < len(argv):
            k, _, v = argv[i + 1].partition("=")
            out.append((k, v))
    return out


def argv_value(argv, flag):
    for i in range(len(argv) - 2, -1, -1):
        if argv[i] == flag:
            return argv[i + 1]
    return None


def model_url(argv, env):
    """The URL the student will use, as the feeder resolves it: an `--env ANTHROPIC_BASE_URL=` pair (the last wins, as in
    Student.__init__), else feed.py's OLLAMA_URL = BEAM_OLLAMA_URL else the default."""
    url = None
    for k, v in env_pairs(argv):
        if k == "ANTHROPIC_BASE_URL":
            url = v
    return url if url is not None else (env.get("BEAM_OLLAMA_URL") or OLLAMA_DEFAULT)


def check_model_url(url, port):
    try:
        u = urllib.parse.urlsplit(url)
        host, uport = u.hostname, u.port
    except ValueError:
        raise LaunchRefused(f"the model URL the student will use is not a URL: {url!r}")
    if uport is None:
        uport = {"http": 80, "https": 443}.get(u.scheme)
    if not host:
        raise LaunchRefused(f"the model URL the student will use has no host, so it is not loopback: {url!r}")
    try:
        loop = host == "localhost" or ipaddress.ip_address(host).is_loopback
    except ValueError:
        loop = False
    if not loop:
        raise LaunchRefused(f"the model URL the student will use ({url}) has a host that is not loopback")
    try:
        want = int(port)
    except ValueError:
        raise LaunchRefused(f"SANDBOX_MODEL_PORT {port!r} is not a number")
    if uport != want:
        raise LaunchRefused(f"the model URL the student will use ({url}) has port {uport}, not SANDBOX_MODEL_PORT {port}")


def resolve_on_path(name, path, cwd):
    """The file Popen([name], env={'PATH': path}, cwd=cwd) would start: the first executable regular file among the PATH
    entries in order (an empty entry is the child's working directory)."""
    for d in path.split(os.pathsep):
        d = d if d else "."
        cand = os.path.join(d if os.path.isabs(d) else os.path.join(cwd, d), name)
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return None


def check_claude_first(wrapper_path, argv, env, feeder):
    """The `claude` the feeder's Popen will find must be the wrapper this launch prepared."""
    path = None
    for k, v in env_pairs(argv):
        if k == "PATH":
            path = v   # an --env PATH replaces the feeder's own (last wins)
    if path is None:
        path = env["PATH"] + ":" + os.path.dirname(os.path.abspath(feeder))   # what Student.__init__ builds
    home = argv_value(argv, "--arm-home")
    cwd = os.path.join(os.path.abspath(home), "work") if home else os.getcwd()
    got = resolve_on_path("claude", path, cwd)
    if got is None or not os.path.samefile(got, wrapper_path):
        raise LaunchRefused(f"the `claude` first on the PATH the feeder will see is {got or 'not found'}, not the sandbox "
                            f"wrapper this launch prepared ({wrapper_path})")


def _prepare_dir():
    d = tempfile.mkdtemp(prefix="sandbox-launch-")
    try:
        w, f = os.path.join(d, "claude"), os.path.join(d, "sandbox-forward.py")
        shutil.copyfile(WRAPPER_SRC, w); os.chmod(w, 0o500)
        shutil.copyfile(FORWARDER_SRC, f); os.chmod(f, 0o400)
    except OSError:
        shutil.rmtree(d, ignore_errors=True)
        raise
    return d


def _fresh_log(log_dir):
    if not os.path.isdir(log_dir):
        raise LaunchRefused(f"the log directory {log_dir} does not exist")
    for _ in range(100):   # bounded: a naming scheme that keeps colliding is a named refusal, never a spin
        p = os.path.join(os.path.abspath(log_dir), f"sandbox-{next(_SEQ)}-{secrets.token_hex(4)}.log")
        if not os.path.lexists(p):
            return p
    raise LaunchRefused(f"no fresh SANDBOX_LOG name was found in {log_dir} after 100 tries")


def read_launch_hashes(log):
    """wrapper_sha256 and forwarder_sha256 from the log's launch line ({} entries missing if the line lacks them)."""
    out = {}
    with open(log, "rb") as f:
        for line in f.read().decode("utf-8", "replace").splitlines():
            if line.startswith("wrapper-launch "):
                for field in ("wrapper_sha256", "forwarder_sha256"):
                    m = re.search(r"(?:^| )%s=([0-9A-Za-z]*)(?: |$)" % field, line)
                    out[field] = m.group(1) if m else None
    return out


def read_verdict(wrapper_dir, log):
    """Run `sandbox-forward.py log-verdict --log LOG` (the copy that ran). Returns (exit code, stdout line, stderr)."""
    r = subprocess.run([sys.executable, "-I", os.path.join(wrapper_dir, "sandbox-forward.py"), "log-verdict", "--log", log],
                       capture_output=True, text=True)
    return r.returncode, r.stdout.rstrip("\n"), r.stderr.strip()


# ------------------------------------------------------------------------------------------------------ teardown (round 2)
# The module's stop is the guarantee that no box or bridge outlives its session (design owner, 2026-11-20): a caller's
# SIGKILL has been seen not to end the box, and the mechanism is unproven. So after every session the module stops the
# launch's scope itself and then checks that NOTHING of the launch remains, by three positive markers the wrapper put on
# the launch line (never by a process-name search): the scope's own cgroup, the forwarder's pid AND start time, and the
# bridge socket path in any process's argv.
UNIT_PREFIX = "student-sandbox-"   # the wrapper names its scope units this way (SCOPE_UNIT in student-sandbox.sh)
LAUNCH_MARKERS = ("scope_unit", "forwarder_pid", "forwarder_start", "bridge_sock")
_SETTLE_S = 3.0   # how long a dying box and forwarder are given before they count as left over
_TERM_S = 3.0     # how long a terminated forwarder is given


class SystemctlError(Exception):
    pass


class LaunchMarkerError(Exception):
    pass


def scope_name(unit):
    """systemctl takes a bare name as a .service; the wrapper's units are scopes (`systemd-run --scope --unit NAME`)."""
    return unit if unit.endswith(".scope") else unit + ".scope"


def _systemctl(*args, timeout=150):
    env = dict(os.environ, XDG_RUNTIME_DIR=os.environ.get("XDG_RUNTIME_DIR") or "/run/user/%d" % os.getuid())
    try:
        return subprocess.run(["systemctl", "--user", *args], env=env, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise SystemctlError(f"`systemctl --user {' '.join(args)}` could not run ({type(e).__name__})")


def read_launch_fields(log):
    """The key=value fields of the log's `wrapper-launch` line, or None when there is no log or no such line."""
    try:
        text = open(log, "rb").read().decode("utf-8", "replace")
    except OSError:
        return None
    for line in text.splitlines():
        if line.startswith("wrapper-launch "):
            return dict(tok.partition("=")[::2] for tok in line.split()[1:] if "=" in tok)
    return None


def launch_markers(fields):
    """The four teardown markers from a launch line's fields, validated; LaunchMarkerError names what is missing."""
    missing = [k for k in LAUNCH_MARKERS if not fields.get(k)]
    if missing:
        raise LaunchMarkerError("the launch line lacks " + ", ".join(missing))
    try:
        pid, start = int(fields["forwarder_pid"]), int(fields["forwarder_start"])
    except ValueError:
        raise LaunchMarkerError("the launch line's forwarder_pid or forwarder_start is not a number")
    if pid <= 0 or start <= 0:
        raise LaunchMarkerError("the launch line's forwarder_pid or forwarder_start is not a real value")
    return {"scope_unit": fields["scope_unit"], "forwarder_pid": pid, "forwarder_start": start,
            "bridge_sock": fields["bridge_sock"]}


def proc_start(pid):
    """/proc/<pid>/stat field 22 (start time, clock ticks since boot): a reused pid has another. None: the process is gone."""
    try:
        fields = open("/proc/%d/stat" % pid).read().rsplit(")", 1)[1].split()
        return None if fields[0] == "Z" else int(fields[19])   # a zombie holds nothing: it is a process that has ended
    except (OSError, IndexError, ValueError):
        return None


def argv_pids(path):
    """Pids (other than this process) that carry `path` as one whole argv element, from /proc."""
    out = []
    for d in os.listdir("/proc"):
        if d.isdigit() and int(d) != os.getpid():
            try:
                if path.encode() in open("/proc/%s/cmdline" % d, "rb").read().split(b"\0"):
                    out.append(int(d))
            except OSError:
                pass
    return out


def unit_pids(unit):
    """The pids in the unit's own cgroup (the cgroup path is read from the unit); [] when the unit is gone."""
    unit = scope_name(unit)
    r = _systemctl("show", "-p", "ControlGroup", "--value", unit)
    if r.returncode != 0:
        raise SystemctlError(f"`systemctl --user show {unit}` failed: {r.stderr.strip()}")
    cg = r.stdout.strip()
    if not cg:
        return []
    try:
        return [int(x) for x in open("/sys/fs/cgroup%s/cgroup.procs" % cg).read().split()]
    except (OSError, ValueError):
        return []


def active_units():
    r = _systemctl("list-units", "--type=scope", "--state=active", "--no-legend", "--plain", UNIT_PREFIX + "*")
    if r.returncode != 0:
        raise SystemctlError(f"`systemctl --user list-units` failed: {r.stderr.strip()}")
    return [l.split()[0] for l in r.stdout.splitlines() if l.strip()]


def leftovers(m):
    """What of the launch described by markers `m` is still there: {pid: [why, ...]}. The three checks of the teardown."""
    left = {}
    for pid in unit_pids(m["scope_unit"]):                                  # (i) the scope's own cgroup
        left.setdefault(pid, []).append(f"still in the cgroup of scope {m['scope_unit']}")
    start = proc_start(m["forwarder_pid"])                                  # (ii) the forwarder: same pid AND same start time
    if start == m["forwarder_start"]:
        left.setdefault(m["forwarder_pid"], []).append("the launch's outer forwarder (same pid and start time) is still alive")
    for pid in argv_pids(m["bridge_sock"]):                                 # (iii) the bridge socket path in any argv
        left.setdefault(pid, []).append(f"its argv carries this launch's bridge_sock {m['bridge_sock']}")
    return left


def _settle(m, secs):
    deadline = time.time() + secs
    while True:
        left = leftovers(m)
        if not left or time.time() >= deadline:
            return left
        time.sleep(0.1)


def _describe(left):
    return "; ".join(f"pid {pid}: " + " and ".join(whys) for pid, whys in sorted(left.items()))


def teardown(m):
    """Stop the launch's scope, then make sure nothing of it remains. Returns what is left ({} when clean)."""
    _systemctl("stop", scope_name(m["scope_unit"]))   # the exit code is not read: a unit that is already gone is exactly the goal
    left = _settle(m, _SETTLE_S)
    pid = m["forwarder_pid"]
    if pid in left and proc_start(pid) == m["forwarder_start"]:   # still the very process the launch started: end it
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.kill(pid, sig)
            except OSError:
                pass
            end = time.time() + _TERM_S
            while proc_start(pid) == m["forwarder_start"] and time.time() < end:
                time.sleep(0.05)
            if proc_start(pid) != m["forwarder_start"]:
                break
        left = _settle(m, _SETTLE_S)
    return left


def _write_record(path, rec):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(rec, f, sort_keys=True)
    os.replace(tmp, path)


def check_before_launch(state_dir):
    """B: refuse to launch while anything earlier is alive. Two positive markers, no process search: (1) every record in
    `state_dir` not marked done is re-checked with the teardown's three checks (a record whose session never wrote a launch
    line has nothing to check and is closed); (2) any active user scope unit named with the wrapper's own prefix."""
    problems, count = [], 0
    try:
        for name in sorted(os.listdir(state_dir)):
            if not name.endswith(".json"):
                continue
            path = os.path.join(state_dir, name)
            try:
                rec = json.load(open(path))
            except (OSError, ValueError):
                problems.append(f"the launch record {name} cannot be read"); count += 1
                continue
            if rec.get("state") == "done":
                continue
            fields = read_launch_fields(rec.get("log", ""))
            if fields is None:
                rec.update(state="done", note="no launch line in the log: the wrapper never launched, nothing to stop")
                _write_record(path, rec)
                continue
            try:
                m = launch_markers(fields)
            except LaunchMarkerError as e:
                problems.append(f"the earlier launch {name}: {e}"); count += 1
                continue
            left = _settle(m, _SETTLE_S)
            if left:
                problems.append(f"the earlier launch {name} left something alive: {_describe(left)} (stop it with: "
                                f"systemctl --user stop {scope_name(m['scope_unit'])}; end a leftover pid you have confirmed is this "
                                "launch's own)")
                count += len(left)
            else:
                rec.update(m, state="done", note="found gone at a later launch")
                _write_record(path, rec)
        for unit in active_units():
            problems.append(f"the scope unit {unit} is active (stop it with: systemctl --user stop {unit})")
            count += 1
    except SystemctlError as e:
        raise LaunchRefused(f"cannot check for leftovers of earlier launches: {e}")
    if problems:
        err = LaunchRefused("refusing to launch while anything of an earlier launch is alive (leftovers found: %d): %s"
                            % (count, " | ".join(problems)))
        err.leftover_count = count
        raise err


def _close_launch(rec_path, rec, log, res):
    """T: after the feeder returned (whatever its exit code). Returns None when the launch is torn down and its record is
    closed, else the LaunchStop that names what remains. A session whose wrapper wrote no launch line (it refused before
    launching) is told apart by exactly that: there is nothing to stop."""
    fields = read_launch_fields(log)
    if fields is None:
        rec.update(state="done", note="no launch line in the log: the wrapper refused before it launched, nothing to stop")
        _write_record(rec_path, rec)
        return None
    try:
        m = launch_markers(fields)
    except LaunchMarkerError as e:
        return LaunchStop(f"teardown: {e}, so the launch's scope and forwarder cannot be checked", res)
    rec.update(m)
    _write_record(rec_path, rec)
    try:
        left = teardown(m)
    except SystemctlError as e:
        return LaunchStop(f"teardown: {e}", res)
    if left:
        return LaunchStop(f"teardown: after `systemctl --user stop {scope_name(m['scope_unit'])}` something of this launch remains: "
                          f"{_describe(left)}", res)
    rec.update(state="done", note="torn down")
    _write_record(rec_path, rec)
    return None


def run_feeder(py, feeder, argv, *, sandbox=None, log_dir=None, log_path=None, state_dir=None, env=None, test_stub=False,
               **run_kw):
    """Run `py -I feeder *argv`. See the module docstring. `sandbox` is a Sandbox for a student session; None only for a
    call that starts no student (`--dump-plan`). `log_dir` is where this session's SANDBOX_LOG is chosen (or `log_path`
    names it; it must not exist). `state_dir` (required for a student session, no default) holds one record per launch.
    `test_stub=True` lets a test substitute a stub script for a feeder (the P1_FEED4 hook, refused outside
    P1_TEST_HOOKS=1): the stub is wrapped like a feeder, so every check still runs on it.
    Extra keyword arguments go to subprocess.run (stdout=...)."""
    if os.path.basename(feeder) not in FEEDERS and not test_stub:
        raise LaunchRefused(f"{feeder} is not one of the feeders {FEEDERS}")
    env = dict(os.environ if env is None else env)
    argv = list(argv)
    if "--dump-plan" in argv:   # starts no student: no wrapper, no log
        return LaunchResult(subprocess.run([py, "-I", feeder, *argv], env=env, **run_kw).returncode)
    if sandbox is None:
        raise LaunchRefused("a feeder call that starts a student needs the sandbox (only --dump-plan runs without it)")
    if not state_dir:
        raise LaunchRefused("a student session needs a state directory for its launch record (the module has no default)")
    for k, _ in env_pairs(argv):
        if k.startswith("SANDBOX_"):
            raise LaunchRefused(f"{k} is passed to the feeder by the launch module only, not by the caller")
    out = argv_value(argv, "--out")
    if not out:
        raise LaunchRefused("the feeder's --out directory is not in its argv (the proctor binds are made from it)")
    out = os.path.abspath(out)
    if log_path is None:
        log_path = _fresh_log(log_dir if log_dir is not None else os.path.dirname(out))
    elif os.path.lexists(log_path):
        raise LaunchRefused(f"SANDBOX_LOG {log_path} already exists (one log per launch)")
    log_path = os.path.abspath(log_path)
    check_model_url(model_url(argv, env), sandbox.settings["SANDBOX_MODEL_PORT"])
    os.makedirs(state_dir, mode=0o700, exist_ok=True)
    check_before_launch(state_dir)   # B: nothing of an earlier launch may be alive
    wdir = _prepare_dir()
    try:
        wrapper = os.path.join(wdir, "claude")
        got = {"wrapper_sha256": sha256_file(wrapper), "forwarder_sha256": sha256_file(os.path.join(wdir, "sandbox-forward.py"))}
        for k in ("wrapper_sha256", "forwarder_sha256"):   # M4b: the files this launch will use, before anything starts
            if got[k] != sandbox.expected[k]:
                raise LaunchRefused(f"{k} of the file this launch would use is {got[k]}, expected {sandbox.expected[k]} "
                                    f"(from {os.path.basename(sandbox.expected_file)})")
        env["PATH"] = wdir + os.pathsep + env["PATH"]
        check_claude_first(wrapper, argv, env, feeder)
        os.makedirs(os.path.join(out, "proctor"), exist_ok=True)
        tools = os.path.dirname(os.path.abspath(feeder))
        pairs = dict(sandbox.settings)
        pairs.update(SANDBOX_LOG=log_path, SANDBOX_RO_BINDS=tools, SANDBOX_RO_ROOT=os.path.dirname(tools),
                     SANDBOX_RW_BINDS=os.path.join(out, "proctor"), SANDBOX_RW_ROOT=out)
        extra = [x for k, v in pairs.items() for x in ("--env", f"{k}={v}")]
        # the record is written BEFORE the session starts, so a caller that is killed leaves it open for the next launch
        rec_path = os.path.join(state_dir, os.path.basename(log_path)[:-len(".log")] + ".json")
        rec = {"state": "open", "log": log_path, "feeder": os.path.basename(feeder)}
        _write_record(rec_path, rec)
        res = LaunchResult(None, log=log_path)
        try:
            res.returncode = subprocess.run([py, "-I", feeder, *argv, *extra], env=env, **run_kw).returncode
        except BaseException as exc:   # a feeder that could not run, or was interrupted: still torn down
            td = _close_launch(rec_path, rec, log_path, res)
            if td is not None and hasattr(exc, "add_note"):
                exc.add_note(str(td))
            raise
        td = _close_launch(rec_path, rec, log_path, res)   # T: the log is final once the launch is torn down
        vs = None
        try:
            rc, line, err = read_verdict(wdir, log_path)
            if rc != 0:
                raise LaunchStop(f"log-verdict refused (exit {rc}): {err or 'no message'}; the session is not read", res)
            if line != VERDICT_NOT_FLAGGED and not line.startswith(VERDICT_FLAGGED_PREFIX):
                raise LaunchStop(f"log-verdict printed an unrecognised line {line!r}; it is not read as not-flagged", res)
            res.verdict = line
            launched = read_launch_hashes(log_path)
            res.wrapper_sha256, res.forwarder_sha256 = launched.get("wrapper_sha256"), launched.get("forwarder_sha256")
            for k in ("wrapper_sha256", "forwarder_sha256"):
                if res.__dict__[k] != sandbox.expected[k]:
                    raise LaunchStop(f"the launch line's {k} is {res.__dict__[k]}, expected {sandbox.expected[k]}: what ran "
                                     "is not what was registered; no answer of this session is read", res)
        except LaunchStop as e:
            vs = e
        if td is not None:
            raise LaunchStop(str(td) + (f"; also: {vs}" if vs else ""), res) from None
        if vs is not None:
            raise vs
        return res
    finally:
        shutil.rmtree(wdir, ignore_errors=True)
