"""Cells for tools/student-sandbox.sh (S1-S8). Synthetic fixtures only: no real data, no student model, no GPU.

The wrapper is the `claude` that feed4 resolves on PATH; these cells drive it through SANDBOX_TEST=1 /
SANDBOX_TEST_EXEC (a probe command run inside the same box, after the same checks and mounts) or through a stub
"pinned binary". No host path literal lives here: every location is generated at test time.
"""
import hashlib, json, os, re, shlex, shutil, signal, socket, socketserver, stat, struct, subprocess, sys, tempfile, threading, time
import pytest

TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WRAPPER = os.path.join(TOOLS, "student-sandbox.sh")
FWD = os.path.join(TOOLS, "sandbox-forward.py")
FEED4 = os.path.join(TOOLS, "feed4.py")
PY = "/usr/bin/python3"
# The only names the wrapper itself puts under /run inside the box.
OWN_RUN_NAMES = {"sandbox-bridge.sock", "sandbox-forward.py"}


def _bash4():
    """The wrapper is run as /bin/bash and needs bash 4 (descriptor variables, ${var,,}, mapfile -d); macOS ships 3.2."""
    try:
        out = subprocess.run(["/bin/bash", "-c", "echo ${BASH_VERSINFO[0]}"], capture_output=True, text=True).stdout
        return int(out.strip()) >= 4
    except (OSError, ValueError):
        return False


def _scope_usable():
    """The wrapper puts the box in its own systemd user scope (process and memory caps): the host needs a user manager."""
    env = dict(os.environ, XDG_RUNTIME_DIR=os.environ.get("XDG_RUNTIME_DIR") or "/run/user/%d" % os.getuid())
    try:
        return subprocess.run(["systemd-run", "--user", "--scope", "--quiet", "--collect", "-p", "TasksMax=100",
                               "-p", "MemoryMax=100M", "--", "/usr/bin/true"], env=env, capture_output=True,
                              timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _box_usable():
    if not sys.platform.startswith("linux") or not _bash4() or not shutil.which("bwrap"):
        return False
    if subprocess.run(["bwrap", "--unshare-all", "--ro-bind", "/", "/", "/usr/bin/true"],
                      capture_output=True).returncode != 0:
        return False
    return _scope_usable()


# The tool is Linux-only. Every cell that runs the wrapper (or its box) skips, with this reason, where the host cannot.
NEEDS_BOX_REASON = ("needs Linux, bash 4 or newer, and a working bwrap (unprivileged user namespaces), plus a systemd user "
                    "manager that can start a capped scope: the sandbox is Linux-only")
BOX_OK = _box_usable()
needs_box = pytest.mark.skipif(not BOX_OK, reason=NEEDS_BOX_REASON)


@pytest.fixture(autouse=True)
def _wrapper_cells_need_the_box(request):
    """A cell that runs the wrapper uses the `cfg` or `fake_bwrap` fixture; on a host without Linux + bash 4 + bwrap it is
    skipped with the named reason instead of failing. The pure-Python framing and allow-list cells use neither, so
    they run everywhere."""
    if not BOX_OK and {"cfg", "fake_bwrap"} & set(request.fixturenames):
        pytest.skip(NEEDS_BOX_REASON)


def sha256_of(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def make_exe(path, text):
    with open(path, "w") as f:
        f.write(text)
    os.chmod(path, 0o755)
    return str(path)


class Stub(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, marker):
        class H(socketserver.BaseRequestHandler):
            def handle(h):
                h.request.settimeout(5)
                try:
                    h.request.recv(65536)
                    h.request.sendall(marker.encode())
                except OSError:
                    pass
        super().__init__(("127.0.0.1", free_port()), H)
        self.port = self.server_address[1]
        threading.Thread(target=self.serve_forever, daemon=True).start()


@pytest.fixture
def stubs():
    made = []

    def mk(marker):
        s = Stub(marker)
        made.append(s)
        return s
    yield mk
    for s in made:
        s.shutdown()
        s.server_close()


PORT_LO, PORT_N = 41000, 500


def free_port():
    """A free loopback port from a narrow band, so a mutant can cover the whole band cheaply."""
    import random
    ports = list(range(PORT_LO, PORT_LO + PORT_N))
    random.shuffle(ports)
    for port in ports:
        s = socket.socket()
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            continue
        finally:
            s.close()
        return port
    raise RuntimeError("no free port in the test band")


class Cfg:
    """One valid wrapper configuration in a scratch tree."""

    def __init__(self, root, model_port=None):
        self.root = str(root)
        self.slot = os.path.join(self.root, "slot")
        os.makedirs(os.path.join(self.slot, "work"))
        self.bindir = os.path.join(self.root, "pinned")
        os.makedirs(self.bindir)
        self.binary = make_exe(os.path.join(self.bindir, "stubclaude"),
                               "#!/bin/sh\necho \"stub-claude $*\"\n")
        self.sha = sha256_of(self.binary)
        self.model_port = model_port or free_port()
        self.tmpd = os.path.join(self.root, "tmpd")
        os.makedirs(self.tmpd)
        self.log = os.path.join(self.root, "launch.log")
        # the protected paths the run script would pass: a dataset stand-in file and a key-list directory
        self.prot_dir = os.path.join(self.root, "prot")
        os.makedirs(os.path.join(self.prot_dir, "keys"))
        self.prot_file = os.path.join(self.prot_dir, "dataset.parquet")
        open(self.prot_file, "w").close()
        self.prot_keys = os.path.join(self.prot_dir, "keys")

    def set_binary(self, text):
        make_exe(self.binary, text)
        self.sha = sha256_of(self.binary)

    def env(self, test=True, exec_=None, drop=(), **extra):
        e = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": self.slot, "TERM": "dumb", "LANG": "C.UTF-8",
             "ANTHROPIC_BASE_URL": "http://localhost:%d" % self.model_port, "ANTHROPIC_AUTH_TOKEN": "ollama",
             "ANTHROPIC_API_KEY": "", "DISABLE_TELEMETRY": "1", "DISABLE_AUTOUPDATER": "1",
             "PROCTOR_DIR": os.path.join(self.slot, "proctor"), "TMPDIR": self.tmpd,
             "SANDBOX_SLOT": self.slot, "SANDBOX_BINARY": self.binary, "SANDBOX_BINARY_SHA256": self.sha,
             "SANDBOX_MODEL_HOST": "127.0.0.1", "SANDBOX_MODEL_PORT": str(self.model_port),
             "SANDBOX_MODEL_ALLOW": "GET /*, POST /*",
             "SANDBOX_PROTECT": self.prot_file + ":" + self.prot_keys}
        if test:
            e["SANDBOX_TEST"] = "1"
        if exec_ is not None:
            e["SANDBOX_TEST_EXEC"] = exec_
        e.update(extra)
        for k in drop:
            e.pop(k, None)
        return e

    def run(self, exec_=None, args=(), timeout=60, input=None, **kw):
        return subprocess.run(["/bin/bash", WRAPPER, *args], env=self.env(exec_=exec_, **kw), input=input,
                              capture_output=True, text=True, timeout=timeout)


@pytest.fixture
def cfg(tmp_path):
    return Cfg(tmp_path)


def procs_with(marker):
    """Host pids (not this process) whose cmdline carries marker."""
    out = []
    me = os.getpid()
    for d in os.listdir("/proc"):
        if d.isdigit() and int(d) != me:
            try:
                if marker.encode() in open("/proc/%s/cmdline" % d, "rb").read():
                    out.append(int(d))
            except OSError:
                pass
    return out


def wait_gone(marker, secs=8.0):
    end = time.time() + secs
    while time.time() < end:
        if not procs_with(marker):
            return True
        time.sleep(0.1)
    return not procs_with(marker)


# ---------------------------------------------------------------- S1: refuse before anything runs

# The wrapper starts bwrap once before the real exec, to see that bwrap accepts the seccomp program (round 6, K1): a
# command that ends in `-I -c pass`. A stand-in bwrap lets that probe succeed without recording it, so the stand-ins
# below still see only the real launch.
FAKE_PROBE_PASS = 'case "$*" in *" -I -c pass") exit 0 ;; esac\n'

@pytest.fixture
def fake_bwrap(tmp_path):
    d = tmp_path / "fakebin"
    d.mkdir()
    out = str(tmp_path / "bwrap-called")
    make_exe(str(d / "bwrap"), "#!/bin/sh\n" + FAKE_PROBE_PASS + "echo \"$$ $*\" > \"$FAKE_BWRAP_OUT\"\nexit 99\n")
    return str(d), out


REQUIRED = ["SANDBOX_SLOT", "SANDBOX_BINARY", "SANDBOX_BINARY_SHA256", "SANDBOX_MODEL_HOST", "SANDBOX_MODEL_PORT",
            "SANDBOX_MODEL_ALLOW", "SANDBOX_PROTECT"]


def assert_refused(cfg, fake_bwrap, name, **runkw):
    fdir, out = fake_bwrap
    probe_marker = os.path.join(cfg.slot, "probe-ran")
    before = sorted(os.listdir(cfg.slot)) if os.path.isdir(cfg.slot) else None
    r = cfg.run(exec_='touch %s' % shlex.quote(probe_marker), PATH=fdir + ":/usr/bin:/bin",
                FAKE_BWRAP_OUT=out, SANDBOX_LOG=cfg.log, **runkw)
    assert r.returncode == 2, (r.returncode, r.stderr)
    lines = [l for l in r.stderr.splitlines() if l.strip()]
    assert len(lines) == 1 and name in lines[0], r.stderr
    assert not os.path.exists(out), "bwrap was started"
    assert not os.path.exists(probe_marker), "the probe ran"
    assert os.listdir(cfg.tmpd) == [], "wrapper created something under TMPDIR"
    assert not os.path.exists(cfg.log), "the log was created on a refusal"
    if before is not None:
        assert sorted(os.listdir(cfg.slot)) == before, "slot content changed"


@pytest.mark.parametrize("name", REQUIRED)
@pytest.mark.parametrize("how", ["missing", "empty"])
def test_s1_missing_or_empty_env_refuses(cfg, fake_bwrap, name, how):
    kw = {"drop": (name,)} if how == "missing" else {name: ""}
    assert_refused(cfg, fake_bwrap, name, **kw)


@pytest.mark.parametrize("name,val", [
    ("SANDBOX_BINARY_SHA256", "abc123"), ("SANDBOX_BINARY_SHA256", "g" * 64),
    ("SANDBOX_MODEL_PORT", "http"), ("SANDBOX_MODEL_PORT", "0"), ("SANDBOX_MODEL_PORT", "70000"),
    ("SANDBOX_MODEL_PORT", "80"), ("SANDBOX_MODEL_PORT", "1023"),   # privileged: the in-box listener could not bind it
    ("SANDBOX_MODEL_HOST", "bad host;rm"),
])
def test_s1_malformed_env_refuses(cfg, fake_bwrap, name, val):
    assert_refused(cfg, fake_bwrap, name, **{name: val})


def test_s1_slot_not_a_directory_refuses(cfg, fake_bwrap):
    assert_refused(cfg, fake_bwrap, "SANDBOX_SLOT", SANDBOX_SLOT=os.path.join(cfg.root, "no-such-slot"))
    f = os.path.join(cfg.root, "afile")
    open(f, "w").close()
    assert_refused(cfg, fake_bwrap, "SANDBOX_SLOT", SANDBOX_SLOT=f)


def test_s1_binary_missing_refuses(cfg, fake_bwrap):
    assert_refused(cfg, fake_bwrap, "SANDBOX_BINARY", SANDBOX_BINARY=os.path.join(cfg.bindir, "nope"))


def test_s1_hash_mismatch_refuses(cfg, fake_bwrap):
    assert_refused(cfg, fake_bwrap, "SANDBOX_BINARY_SHA256", SANDBOX_BINARY_SHA256="0" * 64)


def test_s1_hash_mismatch_refuses_in_real_mode_too(cfg, fake_bwrap):
    assert_refused(cfg, fake_bwrap, "SANDBOX_BINARY_SHA256", SANDBOX_BINARY_SHA256="f" * 64, test=False)


def test_s1_bwrap_not_on_path_refuses(cfg):
    probe_marker = os.path.join(cfg.slot, "probe-ran")
    r = cfg.run(exec_="touch %s" % shlex.quote(probe_marker), PATH=os.path.join(cfg.root, "no-such-dir"))
    assert r.returncode == 2, (r.returncode, r.stderr)
    lines = [l for l in r.stderr.splitlines() if l.strip()]
    assert len(lines) == 1 and "bwrap" in lines[0], r.stderr
    assert not os.path.exists(probe_marker) and os.listdir(cfg.tmpd) == []


def test_s1_test_exec_is_ignored_without_test_mode(cfg):
    marker = os.path.join(cfg.slot, "probe-ran")
    r = cfg.run(exec_="touch %s" % shlex.quote(marker), test=False, args=("--version",))
    assert r.returncode == 0, r.stderr
    assert "stub-claude --version" in r.stdout
    assert not os.path.exists(marker)


# ---------------------------------------------------------------- shape: exec, PATH resolution

def test_shape_execs_bwrap_with_namespace_flags(cfg, fake_bwrap):
    fdir, out = fake_bwrap
    p = subprocess.Popen(["/bin/bash", WRAPPER, "--version"], env=cfg.env(test=False, PATH=fdir + ":/usr/bin:/bin",
                         FAKE_BWRAP_OUT=out), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    p.communicate(timeout=30)
    assert p.returncode == 99
    pid, _, argv = open(out).read().strip().partition(" ")
    assert int(pid) == p.pid, "the wrapper must exec bwrap (same pid), not run it as a child"
    for flag in ("--die-with-parent", "--unshare-pid", "--unshare-net"):
        assert flag in argv.split(), flag
    assert argv.endswith("--version")
    deadline = time.time() + 8
    while os.listdir(cfg.tmpd) and time.time() < deadline:
        time.sleep(0.1)
    assert os.listdir(cfg.tmpd) == [], "the bridge forwarder did not clean up after the box exited"


def test_shape_is_found_as_claude_on_path(cfg, tmp_path):
    d = tmp_path / "first"
    d.mkdir()
    shutil.copy(WRAPPER, d / "claude")
    shutil.copy(FWD, d / "sandbox-forward.py")
    env = cfg.env(test=False, PATH=str(d) + ":/usr/local/bin:/usr/bin:/bin")
    p = subprocess.run(["claude", "-p", "x y"], env=env, capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    assert "stub-claude -p x y" in p.stdout


def test_shape_feed4_resolves_claude_through_path():
    src = open(FEED4).read()
    assert 'cmd = ["claude"' in src and "subprocess.Popen(cmd" in src


# ---------------------------------------------------------------- S2: filesystem

def host_home_entries():
    """Every directory under /home, from the host at test time. /home may be searchable but not listable for the
    invoking user; then the entries come from the account database (every home directory under /home) plus the
    invoking user's own, so the class is still generated, never hand-listed."""
    try:
        return sorted(os.listdir("/home"))
    except OSError:
        import pwd
        names = {os.path.relpath(u.pw_dir, "/home").split(os.sep)[0] for u in pwd.getpwall()
                 if u.pw_dir.startswith("/home/")}
        return sorted(n for n in names if n and not n.startswith(".."))


@needs_box
def test_s2_home_is_empty_class_check(cfg):
    host_entries = host_home_entries()
    assert host_entries, "no /home entries found on the host to check"
    r = cfg.run(exec_='ls -A /home; for p in "$@"; do test -e "$p" && echo PRESENT "$p"; done; true',
                args=["/home/" + n for n in host_entries])
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "", "visible under /home inside the box: %r" % r.stdout.split()


def _ancestors(p):
    p = os.path.realpath(p)
    out = []
    while p != "/":
        p = os.path.dirname(p)
        out.append(p)
    return out


def _ancestors_and_self(p):
    return [os.path.realpath(p)] + _ancestors(p)


def _under_scratch(p):
    return p in ("/tmp", "/var/tmp") or p.startswith("/tmp/") or p.startswith("/var/tmp/")


def _hidden_host_entries(c):
    """Class check, generated from the host now: every entry of /tmp and /var/tmp, and every sibling along the
    ancestor chains of the slot and the binary dir, other than those ancestors themselves."""
    keep = set(_ancestors_and_self(c.slot)) | set(_ancestors_and_self(c.bindir))
    dirs = {"/tmp", "/var/tmp"} | {a for p in (c.slot, c.bindir) for a in _ancestors(p) if _under_scratch(a)}
    out = []
    for d in sorted(dirs):
        try:
            names = os.listdir(d)
        except OSError:
            continue
        out += [os.path.join(d, n) for n in names if os.path.join(d, n) not in keep]
    return out


def _with_var_tmp_slot(cfg):
    var_slot = tempfile.mkdtemp(dir="/var/tmp")
    os.makedirs(os.path.join(var_slot, "work"))
    c = Cfg.__new__(Cfg)
    c.__dict__.update(cfg.__dict__)
    c.slot = var_slot
    return c


@needs_box
@pytest.mark.parametrize("slot_under", ["tmp", "var-tmp"])
def test_s2_tmp_and_vartmp_are_fresh(cfg, slot_under):
    c = _with_var_tmp_slot(cfg) if slot_under == "var-tmp" else cfg
    try:
        hidden = _hidden_host_entries(c)
        assert hidden, "nothing to check: host /tmp is empty?"
        r = c.run(exec_='for p in "$@"; do test -e "$p" && echo PRESENT "$p"; done; echo done', args=hidden)
        assert r.returncode == 0, r.stderr
        assert r.stdout.split() == ["done"], "host entries visible inside: %r" % r.stdout.split()
    finally:
        if c is not cfg:
            shutil.rmtree(c.slot, ignore_errors=True)


@needs_box
def test_s2_slot_under_vartmp_is_writable_and_binary_dir_visible(cfg):
    c = _with_var_tmp_slot(cfg)
    try:
        r = c.run(exec_='touch "$1/inside" && test -x "$2" && echo ok', args=[c.slot, cfg.binary])
        assert r.returncode == 0 and r.stdout.strip() == "ok", r.stderr
        assert os.path.exists(os.path.join(c.slot, "inside")), "slot is not writable / not the same directory"
    finally:
        shutil.rmtree(c.slot, ignore_errors=True)


@needs_box
def test_s2_binary_file_is_read_only(cfg):
    r = cfg.run(exec_='(: > "$1") 2>/dev/null && echo WROTE; echo done', args=[cfg.binary])
    assert r.stdout.split() == ["done"], r.stdout
    assert open(cfg.binary).read().startswith("#!/bin/sh"), "the host binary changed"


@needs_box
def test_s2_run_is_fresh_tmpfs(cfg):
    host = set(os.listdir("/run"))
    r = cfg.run(exec_='ls -A /run; for p in "$@"; do test -e "/run/$p" && echo PRESENT "$p"; done; true', args=sorted(host))
    assert r.returncode == 0, r.stderr
    names = set(r.stdout.split())
    present = {n for n in names if n not in host}
    leaked = {l.split()[1] for l in r.stdout.splitlines() if l.startswith("PRESENT")} - OWN_RUN_NAMES
    assert not leaked, "host /run entries visible inside: %r" % leaked
    assert present <= OWN_RUN_NAMES, present


@needs_box
def test_s2_slot_writable_everything_else_read_only(cfg):
    host_ro = [p for p in ("/usr", "/etc", "/lib", "/lib64", "/bin", "/sbin") if os.path.isdir(p)]
    r = cfg.run(exec_='touch "$SLOT/w" && echo SLOT-OK; for p in "$@"; do (touch "$p/x" 2>/dev/null) && echo WROTE "$p"; done; echo done',
                args=host_ro, SLOT=cfg.slot)
    assert "SLOT-OK" in r.stdout, r.stderr
    assert os.path.exists(os.path.join(cfg.slot, "w"))
    assert [t for t in r.stdout.split() if t != "SLOT-OK"] == ["done"], r.stdout
    for p in host_ro:
        assert not os.path.exists(os.path.join(p, "x"))


@needs_box
def test_s2_dataset_hidden_inside_and_kept_outside(cfg):
    # stand-in for the dataset under a /home-like directory (the invoking user's home, a temp dir deleted at the
    # end); if the user's home is not under /home, falls back to a directory under /tmp and says so below.
    home = os.path.expanduser("~")
    base = home if os.path.realpath(home).startswith("/home/") and os.access(home, os.W_OK) else None
    d = tempfile.mkdtemp(dir=base, prefix="sandbox-standin-")
    try:
        p = os.path.join(d, "standin.parquet")
        content = b"synthetic stand-in, not benchmark data\n"
        open(p, "wb").write(content)
        paths = [p]
        real = os.environ.get("BEAM_PARQUET")
        if real:
            paths.append(real)  # existence/readability only: contents are never read
        r = cfg.run(exec_='for p in "$@"; do test -e "$p" && echo EXISTS "$p"; test -r "$p" && echo READABLE "$p"; done; echo done',
                    args=paths, SANDBOX_PROTECT=p)
        assert r.returncode == 0, r.stderr
        assert r.stdout.split() == ["done"], "dataset path visible inside: %r" % r.stdout
        assert open(p, "rb").read() == content, "the feeder's own read outside the box must keep working"
        assert os.access(p, os.R_OK)
        if base is None:
            pytest.xfail("stand-in was under /tmp, not /home (home not under /home here)")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------- S3: processes

@needs_box
def test_s3_no_host_process_visible(cfg):
    mark = "sentinel-%d-%f" % (os.getpid(), time.time())
    s = subprocess.Popen([PY, "-c", "import time; time.sleep(120)", mark])
    try:
        deadline = time.time() + 5
        while not procs_with(mark) and time.time() < deadline:
            time.sleep(0.05)
        assert procs_with(mark), "sentinel did not start"
        r = cfg.run(exec_='for d in /proc/[0-9]*; do tr "\\0" " " < $d/cmdline 2>/dev/null; echo; done; test -d /proc/%d && echo $((6*7)); echo done' % s.pid)
        assert r.returncode == 0, r.stderr
        assert mark not in r.stdout and "42" not in r.stdout.splitlines(), "host pid visible"
        assert r.stdout.split()[-1] == "done"
    finally:
        s.kill()
        s.wait()


@needs_box
def test_s3_backgrounded_children_do_not_survive_the_wrapper(cfg):
    mark = "7%d" % (int(time.time() * 1000) % 10**9)
    r = cfg.run(exec_='sleep 300.%s & setsid nohup sleep 301.%s >/dev/null 2>&1 & sleep 0.5; echo started' % (mark, mark))
    assert r.returncode == 0 and "started" in r.stdout, r.stderr
    assert wait_gone(".%s" % mark), "a backgrounded process survived the wrapper's exit: %r" % procs_with(".%s" % mark)


def _sleeper_running(marker):
    for q in procs_with(marker):
        try:
            argv = open("/proc/%d/cmdline" % q, "rb").read().split(b"\0")
        except OSError:
            continue
        if os.path.basename(argv[0]) == b"sleep":
            return True
    return False


@needs_box
def test_s3_die_with_parent_when_wrapper_is_killed(cfg):
    mark = "8%d" % (int(time.time() * 1000) % 10**9)
    p = subprocess.Popen(["/bin/bash", WRAPPER], env=cfg.env(exec_='sleep 400.%s' % mark),
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        # the probe has started only when the REAL sleep process exists: the bwrap process's own command line also
        # carries the marker, and killing the wrapper while bwrap is still setting up proves nothing
        end = time.time() + 15
        while time.time() < end and not _sleeper_running(".%s" % mark):
            time.sleep(0.05)
        assert _sleeper_running(".%s" % mark), "probe never started"
        p.kill()
        p.wait()
        assert wait_gone(".%s" % mark), "boxed processes outlived the killed wrapper: %r" % procs_with(".%s" % mark)
    finally:
        if p.poll() is None:
            p.kill()


# ---------------------------------------------------------------- S4: network

NET_PROBE = r'''
import socket, sys
def attempt(host, port):
    s = socket.socket(); s.settimeout(3)
    try:
        s.connect((host, port))
    except OSError as e:
        return "FAIL:" + type(e).__name__
    # connected: whatever happens next, the endpoint was reachable
    try:
        s.sendall(b"GET / HTTP/1.1\r\nHost: m\r\nConnection: close\r\n\r\n"); data = b""
        while True:
            c = s.recv(4096)
            if not c:
                break
            data += c
        return "OK:" + data.decode(errors="replace").strip()
    except OSError as e:
        return "CONNECTED:" + type(e).__name__
    finally:
        s.close()
for a in sys.argv[1:]:
    h, p = a.rsplit(":", 1)
    print(a, attempt(h, int(p)))
'''


def net_probe(cfg, targets, **kw):
    pf = os.path.join(cfg.slot, "netprobe.py")
    open(pf, "w").write(NET_PROBE)
    r = cfg.run(exec_='%s -I %s "$@"' % (PY, shlex.quote(pf)), args=targets, **kw)
    assert r.returncode == 0, r.stderr
    return dict(l.split(" ", 1) for l in r.stdout.splitlines())


def non_loopback_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))  # no packet is sent by a UDP connect
        ip = s.getsockname()[0]
    except OSError:
        ip = "203.0.113.7"
    finally:
        s.close()
    return ip


@needs_box
def test_s4_model_endpoint_reachable_through_bridge(cfg, stubs):
    model = stubs("MODEL-MARKER")
    cfg.model_port = model.port
    res = net_probe(cfg, ["127.0.0.1:%d" % model.port])
    assert res["127.0.0.1:%d" % model.port] == "OK:MODEL-MARKER"


@needs_box
def test_s4_no_other_loopback_port_and_no_route_out(cfg, stubs):
    model, other = stubs("MODEL-MARKER"), stubs("OTHER-HOST-SERVICE")
    cfg.model_port = model.port
    targets = ["127.0.0.1:%d" % other.port, "127.0.0.1:" + str(free_port()), "127.0.0.2:%d" % model.port,
               "%s:%d" % (non_loopback_ip(), other.port), "192.0.2.1:80", "1.1.1.1:53"]
    res = net_probe(cfg, targets)
    for t in targets:
        assert res[t].startswith("FAIL:"), (t, res[t])
    assert not any("OTHER-HOST-SERVICE" in v for v in res.values())


@needs_box
def test_s4_bridge_only_listens_on_the_model_port(cfg, stubs):
    model = stubs("MODEL-MARKER")
    cfg.model_port = model.port
    probe = ('%s -I -c \'import socket,sys; ports=[]\n'
             'for p in range(1,65536):\n'
             '    s=socket.socket(); s.settimeout(0.05)\n'
             '    # a loopback connect to an ephemeral port can connect the socket to itself: not a listener\n'
             '    if s.connect_ex(("127.0.0.1",p))==0 and s.getsockname()[1]!=p: ports.append(p)\n'
             '    s.close()\n'
             'print(ports)\'') % PY
    r = cfg.run(exec_=probe, timeout=120)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout.strip()) == [model.port]


@needs_box
def test_s4_forwarders_are_gone_after_exit(cfg, stubs):
    model = stubs("MODEL-MARKER")
    cfg.model_port = model.port
    r = cfg.run(exec_="ls /run")
    assert r.returncode == 0 and "sandbox-bridge.sock" in r.stdout.split(), (r.returncode, r.stderr)
    end = time.time() + 8
    while os.listdir(cfg.tmpd) and time.time() < end:
        time.sleep(0.1)
    assert os.listdir(cfg.tmpd) == []
    assert wait_gone(os.path.join(cfg.tmpd, "")), "a bridge forwarder is still running"


# ---------------------------------------------------------------- S5: environment

@needs_box
def test_s5_environment_is_exactly_what_the_caller_passed(cfg):
    cfg.set_binary("#!/usr/bin/python3 -I\nimport os, json\nprint(json.dumps(dict(os.environ)))\n")
    e = cfg.env(test=False, drop=("TMPDIR",), SANDBOX_LOG=cfg.log, SANDBOX_EXTRA="x", KEEP_ME="with=equals and spaces")
    expected = {k: v for k, v in e.items() if not k.startswith("SANDBOX_")}
    host_plant = "SANDBOX_TEST_PLANT_%d" % os.getpid()
    os.environ[host_plant] = "leak"
    try:
        r = subprocess.run(["/bin/bash", WRAPPER], env=e, capture_output=True, text=True, timeout=60)
    finally:
        del os.environ[host_plant]
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout)
    assert got == expected
    assert got["HOME"] == cfg.slot
    assert not [k for k in got if k.startswith("SANDBOX_")]


@needs_box
def test_s5_host_variable_not_passed_is_absent_inside(cfg):
    plant = "HOST_ONLY_PLANT_%d" % os.getpid()
    os.environ[plant] = "leak"
    try:
        r = cfg.run(exec_='env', args=())
    finally:
        del os.environ[plant]
    assert r.returncode == 0, r.stderr
    names = {l.split("=", 1)[0] for l in r.stdout.splitlines() if "=" in l}
    assert plant not in names
    assert not [n for n in names if n.startswith("SANDBOX_")]
    assert ("HOME=" + cfg.slot) in r.stdout.splitlines()


# ---------------------------------------------------------------- S6: exit code and streams

@needs_box
def test_s6_exit_code_passes_through(cfg):
    assert cfg.run(exec_="exit 7").returncode == 7
    assert cfg.run(exec_="exit 0").returncode == 0


@needs_box
def test_s6_streams_pass_through_unbuffered(cfg):
    p = subprocess.Popen(["/bin/bash", WRAPPER], env=cfg.env(exec_="cat"), stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
    try:
        p.stdin.write("first line\n")
        p.stdin.flush()
        got = p.stdout.readline()  # must arrive while stdin is still open
        assert got == "first line\n"
        p.stdin.write("second\n")
        p.stdin.flush()
        assert p.stdout.readline() == "second\n"
        p.stdin.close()
        assert p.wait(timeout=20) == 0
    finally:
        if p.poll() is None:
            p.kill()


@needs_box
def test_s6_stderr_passes_through_separately(cfg):
    r = cfg.run(exec_="echo to-out; echo to-err >&2")
    # in test mode the wrapper prints its own one-line TEST MODE marker before the box starts (C2); the student's
    # stderr is everything else, byte for byte
    own = [l for l in r.stderr.splitlines(True) if "TEST MODE" in l]
    assert len(own) == 1 and r.stdout == "to-out\n" and r.stderr.replace(own[0], "", 1) == "to-err\n", r.stderr
    r = cfg.run(exec_="echo to-out; echo to-err >&2", test=False, SANDBOX_TEST_EXEC="echo not-run")   # not test mode: no marker
    assert "TEST MODE" not in r.stderr


# ---------------------------------------------------------------- S7: the pinned binary runs inside

@needs_box
def test_s7_stub_binary_runs_with_exact_args(cfg):
    r = cfg.run(args=("--version", "a b", "c"), test=False)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "stub-claude --version a b c"


@pytest.mark.skipif(not (os.environ.get("SANDBOX_TEST_REAL_BINARY") and os.environ.get("SANDBOX_TEST_REAL_BINARY_SHA256")),
                    reason="set SANDBOX_TEST_REAL_BINARY and SANDBOX_TEST_REAL_BINARY_SHA256 for the real-binary check")
@needs_box
def test_s7_real_pinned_binary_prints_its_version(cfg):
    cfg.binary = os.environ["SANDBOX_TEST_REAL_BINARY"]
    cfg.sha = os.environ["SANDBOX_TEST_REAL_BINARY_SHA256"]
    r = cfg.run(args=("--version",), test=False)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() != ""


# ---------------------------------------------------------------- S8: cost is measurable

S8_REQ = (b"POST /v1/messages HTTP/1.1\r\nHost: x\r\nConnection: close\r\nContent-Length: 18\r\n\r\nREQUEST-SECRET-QQQ")


@needs_box
def test_s8_forwarder_logs_counts_and_timings_never_payloads(cfg, http_stub):
    model = http_stub()
    cfg.model_port = model.port
    probe = '%s -I -c \'import socket; s=socket.create_connection(("127.0.0.1",%d)); s.sendall(bytes.fromhex("%s")); d=b""\n' \
            'while True:\n c=s.recv(99)\n if not c: break\n d+=c\nprint(d.decode())\'' % (PY, model.port, S8_REQ.hex())
    r = cfg.run(exec_=probe, SANDBOX_LOG=cfg.log, SANDBOX_MODEL_ALLOW="POST /v1/messages")
    assert r.returncode == 0 and "OK:POST:/v1/messages" in r.stdout, r.stderr
    time.sleep(0.5)
    text = open(cfg.log).read()
    assert "OK:POST" not in text and "REQUEST-SECRET-QQQ" not in text
    conns = [l for l in text.splitlines() if l.startswith("fwd-conn ")]
    assert len(conns) == 1, text
    f = dict(kv.split("=", 1) for kv in conns[0].split()[1:])
    assert float(f["close"]) >= float(f["open"]) > 1e9
    assert int(f["up"]) == len(S8_REQ) and int(f["down"]) == len(model.sent[0])
    assert any(l.startswith("wrapper-launch ") for l in text.splitlines())


@needs_box
def test_s8_latency_compare_reports_median_and_max(cfg, stubs):
    model = stubs("PONG")
    cfg.model_port = model.port
    r = subprocess.run([PY, "-I", FWD, "latency-compare", "--wrapper", WRAPPER, "-n", "5"],
                       env=cfg.env(test=False), capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    rows = {l.split()[0]: dict(kv.split("=") for kv in l.split()[1:]) for l in r.stdout.splitlines() if l.strip()}
    for k in ("direct", "bridge", "added"):
        assert set(rows[k]) >= {"median_ms", "max_ms"}, r.stdout
        float(rows[k]["median_ms"]); float(rows[k]["max_ms"])
    assert rows["direct"]["n"] == "5" and rows["bridge"]["n"] == "5"


# ---------------------------------------------------------------- F1: the binary FILE is bound, not its directory

@needs_box
def test_f1_sibling_of_the_binary_is_not_visible(cfg):
    sib = os.path.join(cfg.bindir, "sibling-secret")
    open(sib, "w").write("planted sibling, not benchmark data\n")
    r = cfg.run(exec_='test -x "$1" && echo BIN; test -e "$2" && echo SIBLING; ls -A "$3"; echo done',
                args=[cfg.binary, sib, cfg.bindir])
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == ["BIN", "stubclaude", "done"], r.stdout


@needs_box
def test_f1_stub_binary_still_runs_with_its_sibling_hidden(cfg):
    open(os.path.join(cfg.bindir, "sibling-secret"), "w").write("x")
    r = cfg.run(args=("--version",), test=False)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "stub-claude --version"


@needs_box
def test_f1_binary_given_by_symlink_is_bound_at_its_real_path(cfg, tmp_path):
    link = str(tmp_path / "link-to-claude")
    os.symlink(cfg.binary, link)
    c = Cfg.__new__(Cfg)
    c.__dict__.update(cfg.__dict__)
    c.binary = link
    r = c.run(args=("--version",), test=False)
    assert r.returncode == 0 and r.stdout.strip() == "stub-claude --version", r.stderr


# ---------------------------------------------------------------- F2: explicit, validated extra binds

@pytest.fixture
def extra(tmp_path):
    """tools (RO) with a sibling secret, and a run output directory holding the proctor directory (RW)."""
    class X:
        pass
    x = X()
    x.base = str(tmp_path / "extra")
    x.tools = os.path.join(x.base, "tools")
    x.secret = os.path.join(x.base, "secret")
    x.runout = str(tmp_path / "runout")
    x.proctor = os.path.join(x.runout, "proctor")
    for d in (x.tools, x.secret, x.proctor):
        os.makedirs(d)
    open(os.path.join(x.secret, "key"), "w").write("planted, not a real key\n")
    make_exe(os.path.join(x.tools, "ask-proctor"),
             '#!/bin/sh\necho "question: $*" > "$PROCTOR_DIR/q.txt" && echo asked\n')
    return x


def user_home():
    import pwd
    return os.path.realpath(pwd.getpwuid(os.getuid()).pw_dir)


def account_homes():
    """Every directory that is some account's home in the host's account database, generated now (a class, never a
    hand list). Includes the invoking user's."""
    import pwd
    return sorted({os.path.realpath(u.pw_dir) for u in pwd.getpwall() if u.pw_dir and os.path.isdir(u.pw_dir)})


def _launch(cfg, fake_bwrap, **kw):
    fdir, out = fake_bwrap
    return cfg.run(exec_="true", PATH=fdir + ":/usr/bin:/bin", FAKE_BWRAP_OUT=out, SANDBOX_LOG=cfg.log, **kw), out


def _wait_clean(cfg):
    end = time.time() + 8
    while os.listdir(cfg.tmpd) and time.time() < end:
        time.sleep(0.05)
    assert os.listdir(cfg.tmpd) == [], "the bridge forwarder did not clean up"
    if os.path.exists(cfg.log):
        os.unlink(cfg.log)


def _refused(cfg, fake_bwrap, var, word, **kw):
    """Exit 2, exactly one stderr line that names the offending variable and says why; nothing started or created."""
    r, out = _launch(cfg, fake_bwrap, **kw)
    assert r.returncode == 2, (kw, r.returncode, r.stderr)
    lines = [l for l in r.stderr.splitlines() if l.strip()]
    assert len(lines) == 1 and var in lines[0] and word in lines[0], (var, word, r.stderr)
    assert not os.path.exists(out), "bwrap was started"
    assert os.listdir(cfg.tmpd) == [] and not os.path.exists(cfg.log)


def _accepted(cfg, fake_bwrap, **kw):
    """The positive control of a refusal cell: the configuration passes every check and reaches bwrap."""
    r, out = _launch(cfg, fake_bwrap, **kw)
    assert r.returncode == 99 and os.path.exists(out), (kw, r.returncode, r.stderr)
    os.unlink(out)
    _wait_clean(cfg)


def test_f2_refusals_entry_shapes(cfg, fake_bwrap, extra):
    f = os.path.join(extra.base, "afile")
    open(f, "w").close()
    nosuch = os.path.join(extra.base, "no-such")
    for val in ("relative/dir", nosuch, f, extra.tools + ":" + nosuch,
                extra.tools + ":", ":" + extra.tools, extra.tools + "::" + extra.secret):
        assert_refused(cfg, fake_bwrap, "SANDBOX_RO_BINDS", SANDBOX_RO_BINDS=val, SANDBOX_RO_ROOT=extra.base)


# ---------------------------------------------------------------- R1: allow-list by declared roots

def test_r1_ro_root_is_required_with_ro_binds(cfg, fake_bwrap, extra):
    assert_refused(cfg, fake_bwrap, "SANDBOX_RO_ROOT", SANDBOX_RO_BINDS=extra.tools)
    _accepted(cfg, fake_bwrap, SANDBOX_RO_BINDS=extra.tools, SANDBOX_RO_ROOT=extra.base)


def test_r1_ro_root_must_be_an_existing_directory(cfg, fake_bwrap, extra):
    f = os.path.join(extra.base, "afile")
    open(f, "w").close()
    for val in (os.path.join(extra.base, "no-such"), f, "relative/dir"):
        assert_refused(cfg, fake_bwrap, "SANDBOX_RO_ROOT", SANDBOX_RO_BINDS=extra.tools, SANDBOX_RO_ROOT=val)


def test_r1_descendant_of_a_shared_directory_is_refused(cfg, fake_bwrap, tmp_path):
    """A stand-in for 'a shared directory under a home's parent': the old class rule accepted a DESCENDANT of it."""
    t = tmp_path / "standin"
    own, shared = t / "own" / "tools", t / "shared" / "forum" / "inbox"
    own.mkdir(parents=True)
    shared.mkdir(parents=True)
    _accepted(cfg, fake_bwrap, SANDBOX_RO_BINDS=str(own), SANDBOX_RO_ROOT=str(t / "own"))
    _refused(cfg, fake_bwrap, "SANDBOX_RO_BINDS", "not inside", SANDBOX_RO_BINDS=str(shared), SANDBOX_RO_ROOT=str(t / "own"))
    _refused(cfg, fake_bwrap, "SANDBOX_RW_BINDS", "not inside", SANDBOX_RW_BINDS=str(shared), SANDBOX_RW_ROOT=str(t / "own"))


def test_r1_descendant_of_var_tmp_is_refused(cfg, fake_bwrap, tmp_path):
    vt = tempfile.mkdtemp(dir="/var/tmp")
    own = tmp_path / "own"
    own.mkdir()
    try:
        _refused(cfg, fake_bwrap, "SANDBOX_RO_BINDS", "not inside", SANDBOX_RO_BINDS=vt, SANDBOX_RO_ROOT=str(own))
        _refused(cfg, fake_bwrap, "SANDBOX_RW_BINDS", "not inside", SANDBOX_RW_BINDS=vt, SANDBOX_RW_ROOT=str(own))
        # and /var/tmp itself, as a root, when the slot lives under it
        c = _with_var_tmp_slot(cfg)
        try:
            _refused(c, fake_bwrap, "SANDBOX_RO_ROOT", "slot", SANDBOX_RO_BINDS=vt, SANDBOX_RO_ROOT="/var/tmp")
        finally:
            shutil.rmtree(c.slot, ignore_errors=True)
    finally:
        shutil.rmtree(vt, ignore_errors=True)


def test_r1_entry_outside_its_root_ro_and_rw(cfg, fake_bwrap, extra):
    _refused(cfg, fake_bwrap, "SANDBOX_RO_BINDS", "not inside", SANDBOX_RO_BINDS=extra.secret, SANDBOX_RO_ROOT=extra.tools)
    _refused(cfg, fake_bwrap, "SANDBOX_RW_BINDS", "not inside", SANDBOX_RW_BINDS=extra.secret, SANDBOX_RW_ROOT=extra.runout)


def test_r1_root_is_the_filesystem_root(cfg, fake_bwrap, extra):
    _refused(cfg, fake_bwrap, "SANDBOX_RO_ROOT", "filesystem root", SANDBOX_RO_BINDS=extra.tools, SANDBOX_RO_ROOT="/")
    _refused(cfg, fake_bwrap, "SANDBOX_RW_ROOT", "filesystem root", SANDBOX_RW_BINDS=extra.proctor, SANDBOX_RW_ROOT="/")
    # and an entry that is "/" is refused too (it cannot be inside a sane root)
    _refused(cfg, fake_bwrap, "SANDBOX_RO_BINDS", "filesystem root", SANDBOX_RO_BINDS="/", SANDBOX_RO_ROOT=extra.tools)


def test_r1_root_is_any_account_home_or_an_ancestor_of_one(cfg, fake_bwrap, extra):
    """Class check from the host's own account database (all users, not only the invoker), RO and RW."""
    homes = account_homes()
    assert user_home() in homes
    targets = set(homes)
    for h in homes:
        p = os.path.dirname(h)
        while p != "/":
            targets.add(p)
            p = os.path.dirname(p)
    for t in sorted(targets):
        word = "filesystem root" if t == "/" else "home directory"
        _refused(cfg, fake_bwrap, "SANDBOX_RO_ROOT", word, SANDBOX_RO_BINDS=t, SANDBOX_RO_ROOT=t)
        _refused(cfg, fake_bwrap, "SANDBOX_RW_ROOT", word, SANDBOX_RW_BINDS=t, SANDBOX_RW_ROOT=t)


def test_r1_root_is_another_accounts_home(cfg, fake_bwrap, extra, tmp_path):
    other = tmp_path / "other-account-home"
    (other / "sub").mkdir(parents=True)
    _refused(cfg, fake_bwrap, "SANDBOX_RO_ROOT", "home directory", SANDBOX_RO_BINDS=str(other),
             SANDBOX_RO_ROOT=str(other), SANDBOX_TEST_EXTRA_HOMES=str(other))
    # its ancestor too, and a root inside it is fine (positive control: only the home itself is refused)
    _refused(cfg, fake_bwrap, "SANDBOX_RO_ROOT", "home directory", SANDBOX_RO_BINDS=str(other),
             SANDBOX_RO_ROOT=str(tmp_path), SANDBOX_TEST_EXTRA_HOMES=str(other))
    _accepted(cfg, fake_bwrap, SANDBOX_RO_BINDS=str(other / "sub"), SANDBOX_RO_ROOT=str(other / "sub"),
              SANDBOX_TEST_EXTRA_HOMES=str(other))


def test_r1_root_inside_a_dot_directory_of_a_home(cfg, fake_bwrap, tmp_path):
    fake = tmp_path / "fakehome"
    for d in (".secrets/inner", "visible/inner", "a/.b/c", "dot.in.name/x"):
        (fake / d).mkdir(parents=True)
    kw = {"SANDBOX_TEST_EXTRA_HOMES": str(fake)}
    for d in (".secrets", ".secrets/inner", "a/.b", "a/.b/c"):
        _refused(cfg, fake_bwrap, "SANDBOX_RO_ROOT", "dot-directory", SANDBOX_RO_BINDS=str(fake / d),
                 SANDBOX_RO_ROOT=str(fake / d), **kw)
        _refused(cfg, fake_bwrap, "SANDBOX_RW_ROOT", "dot-directory", SANDBOX_RW_BINDS=str(fake / d),
                 SANDBOX_RW_ROOT=str(fake / d), **kw)
    # controls: a visible directory, and a dot only inside a name, are fine
    _accepted(cfg, fake_bwrap, SANDBOX_RO_BINDS=str(fake / "visible" / "inner"), SANDBOX_RO_ROOT=str(fake / "visible"), **kw)
    _accepted(cfg, fake_bwrap, SANDBOX_RO_BINDS=str(fake / "dot.in.name" / "x"), SANDBOX_RO_ROOT=str(fake / "dot.in.name"), **kw)
    # an entry inside a dot-directory is refused even when the root above it is clean
    (fake / "visible" / ".hid").mkdir()
    _refused(cfg, fake_bwrap, "SANDBOX_RO_BINDS", "dot-directory", SANDBOX_RO_BINDS=str(fake / "visible" / ".hid"),
             SANDBOX_RO_ROOT=str(fake / "visible"), **kw)
    # the same, in the invoking user's real home when it is writable (no host name is spelled here)
    h = user_home()
    if os.access(h, os.W_OK):
        d = tempfile.mkdtemp(dir=h, prefix=".sandbox-dotdir-")
        try:
            _refused(cfg, fake_bwrap, "SANDBOX_RO_ROOT", "dot-directory", SANDBOX_RO_BINDS=d, SANDBOX_RO_ROOT=d)
        finally:
            shutil.rmtree(d, ignore_errors=True)


def test_r1_root_contains_the_dataset_or_the_binary(cfg, fake_bwrap, tmp_path):
    d = tmp_path / "data" / "inner"
    d.mkdir(parents=True)
    p = str(d / "standin.parquet")
    open(p, "w").close()
    for root in (str(d), str(d.parent)):
        _refused(cfg, fake_bwrap, "SANDBOX_RO_ROOT", "protected", SANDBOX_RO_BINDS=str(d), SANDBOX_RO_ROOT=root, SANDBOX_PROTECT=p)
        _refused(cfg, fake_bwrap, "SANDBOX_RW_ROOT", "protected", SANDBOX_RW_BINDS=str(d), SANDBOX_RW_ROOT=root, SANDBOX_PROTECT=p)
    # control: the same tree is fine when the dataset is elsewhere
    _accepted(cfg, fake_bwrap, SANDBOX_RO_BINDS=str(d), SANDBOX_RO_ROOT=str(d.parent))
    _refused(cfg, fake_bwrap, "SANDBOX_RO_ROOT", "binary", SANDBOX_RO_BINDS=cfg.bindir, SANDBOX_RO_ROOT=cfg.bindir)


def test_r1_root_is_an_ancestor_of_the_slot(cfg, fake_bwrap, extra):
    for root in (cfg.slot, cfg.root, os.path.dirname(cfg.root)):
        _refused(cfg, fake_bwrap, "SANDBOX_RO_ROOT", "slot", SANDBOX_RO_BINDS=extra.tools, SANDBOX_RO_ROOT=root)
        _refused(cfg, fake_bwrap, "SANDBOX_RW_ROOT", "slot", SANDBOX_RW_BINDS=extra.proctor, SANDBOX_RW_ROOT=root)


def test_f2_rw_refusals(cfg, fake_bwrap, extra):
    f = os.path.join(extra.base, "afile")
    open(f, "w").close()
    # RW binds need a root, and the root must be a real directory
    assert_refused(cfg, fake_bwrap, "SANDBOX_RW_ROOT", SANDBOX_RW_BINDS=extra.proctor)
    assert_refused(cfg, fake_bwrap, "SANDBOX_RW_ROOT", SANDBOX_RW_BINDS=extra.proctor,
                   SANDBOX_RW_ROOT=os.path.join(extra.base, "no-such"))
    assert_refused(cfg, fake_bwrap, "SANDBOX_RW_ROOT", SANDBOX_RW_BINDS=extra.proctor, SANDBOX_RW_ROOT=f)
    # an RW entry outside the root, including a sibling that merely shares the root's name as a prefix
    assert_refused(cfg, fake_bwrap, "SANDBOX_RW_BINDS", SANDBOX_RW_BINDS=extra.secret, SANDBOX_RW_ROOT=extra.runout)
    prefixed = extra.runout + "-sibling"
    os.makedirs(prefixed)
    assert_refused(cfg, fake_bwrap, "SANDBOX_RW_BINDS", SANDBOX_RW_BINDS=prefixed, SANDBOX_RW_ROOT=extra.runout)
    # a ".." path that resolves outside the root
    assert_refused(cfg, fake_bwrap, "SANDBOX_RW_BINDS", SANDBOX_RW_BINDS=extra.proctor + "/../../extra/secret",
                   SANDBOX_RW_ROOT=extra.runout)
    # a symlink inside the root pointing outside it
    os.symlink(extra.secret, os.path.join(extra.runout, "escape"))
    assert_refused(cfg, fake_bwrap, "SANDBOX_RW_BINDS", SANDBOX_RW_BINDS=os.path.join(extra.runout, "escape"),
                   SANDBOX_RW_ROOT=extra.runout)
    # entry shape
    assert_refused(cfg, fake_bwrap, "SANDBOX_RW_BINDS", SANDBOX_RW_BINDS=os.path.join(extra.runout, "no-such"),
                   SANDBOX_RW_ROOT=extra.runout)


# ---------------------------------------------------------------- R2: the slot is validated by the same class rules

def test_r2_slot_is_the_filesystem_root(cfg, fake_bwrap):
    _refused(cfg, fake_bwrap, "SANDBOX_SLOT", "filesystem root", SANDBOX_SLOT="/")


def test_r2_slot_is_any_account_home_or_an_ancestor_of_one(cfg, fake_bwrap):
    homes = account_homes()
    targets = set(homes)
    for h in homes:
        p = os.path.dirname(h)
        while p != "/":
            targets.add(p)
            p = os.path.dirname(p)
    for t in sorted(targets):
        _refused(cfg, fake_bwrap, "SANDBOX_SLOT", "filesystem root" if t == "/" else "home directory", SANDBOX_SLOT=t)


def test_r2_slot_contains_the_dataset_or_the_binary(cfg, fake_bwrap):
    open(os.path.join(cfg.slot, "work", "standin.parquet"), "w").close()
    _refused(cfg, fake_bwrap, "SANDBOX_SLOT", "protected", SANDBOX_PROTECT=os.path.join(cfg.slot, "work", "standin.parquet"))
    _refused(cfg, fake_bwrap, "SANDBOX_SLOT", "protected", SANDBOX_PROTECT=os.path.join(cfg.slot, "work", "standin.parquet"),
             SANDBOX_SLOT=os.path.join(cfg.slot, "work"))
    _refused(cfg, fake_bwrap, "SANDBOX_SLOT", "binary", SANDBOX_SLOT=cfg.root)
    _refused(cfg, fake_bwrap, "SANDBOX_SLOT", "binary", SANDBOX_SLOT=cfg.bindir)
    _accepted(cfg, fake_bwrap)


def test_r2_slot_inside_a_dot_directory_of_a_home(cfg, fake_bwrap, tmp_path):
    fake = tmp_path / "fakehome"
    (fake / ".cfg" / "slot").mkdir(parents=True)
    (fake / "slot").mkdir()
    kw = {"SANDBOX_TEST_EXTRA_HOMES": str(fake)}
    _refused(cfg, fake_bwrap, "SANDBOX_SLOT", "dot-directory", SANDBOX_SLOT=str(fake / ".cfg" / "slot"), **kw)
    _refused(cfg, fake_bwrap, "SANDBOX_SLOT", "dot-directory", SANDBOX_SLOT=str(fake / ".cfg"), **kw)
    _accepted(cfg, fake_bwrap, SANDBOX_SLOT=str(fake / "slot"), HOME=str(fake / "slot"), **kw)   # under a home is fine when no dot; HOME follows


@needs_box
def test_f2_ro_bind_is_visible_not_writable_and_its_sibling_is_not(cfg, extra):
    r = cfg.run(exec_='test -x "$1/ask-proctor" && echo TOOL; (touch "$1/x") 2>/dev/null && echo WROTE; '
                      '(: > "$1/ask-proctor") 2>/dev/null && echo CLOBBERED; test -e "$2" && echo SECRET; '
                      'test -e "$3/key" && echo KEY; ls -A "$4"; echo done',
                args=[extra.tools, extra.base + "/secret", extra.secret, extra.base], SANDBOX_RO_BINDS=extra.tools, SANDBOX_RO_ROOT=extra.base)
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == ["TOOL", "tools", "done"], r.stdout
    assert not os.path.exists(os.path.join(extra.tools, "x"))


@needs_box
def test_f2_rw_bind_is_writable_and_lands_on_the_host(cfg, extra):
    r = cfg.run(exec_='echo from-inside > "$1/note" && echo ok', args=[extra.proctor],
                SANDBOX_RW_BINDS=extra.proctor, SANDBOX_RW_ROOT=extra.runout)
    assert r.returncode == 0 and r.stdout.strip() == "ok", r.stderr
    assert open(os.path.join(extra.proctor, "note")).read() == "from-inside\n"


@needs_box
def test_f2_both_variables_and_two_entries(cfg, extra):
    second = os.path.join(extra.runout, "second")
    os.makedirs(second)
    r = cfg.run(exec_='test -x "$1/ask-proctor" && touch "$2/a" "$3/b" && echo ok', args=[extra.tools, extra.proctor, second],
                SANDBOX_RO_BINDS=extra.tools, SANDBOX_RO_ROOT=extra.base, SANDBOX_RW_BINDS=extra.proctor + ":" + second, SANDBOX_RW_ROOT=extra.runout)
    assert r.returncode == 0 and r.stdout.strip() == "ok", r.stderr
    assert os.path.exists(os.path.join(extra.proctor, "a")) and os.path.exists(os.path.join(second, "b"))


@needs_box
def test_f2_ask_proctor_works_from_inside(cfg, extra):
    r = cfg.run(exec_='ask-proctor what is this; echo "$PROCTOR_DIR"', PATH=extra.tools + ":/usr/bin:/bin",
                PROCTOR_DIR=extra.proctor, SANDBOX_RO_BINDS=extra.tools, SANDBOX_RO_ROOT=extra.base, SANDBOX_RW_BINDS=extra.proctor,
                SANDBOX_RW_ROOT=extra.runout)
    assert r.returncode == 0, r.stderr
    assert r.stdout.split("\n")[:2] == ["asked", extra.proctor]
    assert open(os.path.join(extra.proctor, "q.txt")).read() == "question: what is this\n"


@needs_box
def test_f2_dataset_stand_in_stays_invisible_when_its_parents_sibling_is_bound(cfg):
    home = user_home()
    if not (home.startswith("/home/") and os.access(home, os.W_OK)):
        pytest.skip("the invoking user's home is not a writable directory under /home here")
    d = tempfile.mkdtemp(dir=home, prefix="sandbox-standin-")
    sib = tempfile.mkdtemp(dir=home, prefix="sandbox-bound-sibling-")
    try:
        p = os.path.join(d, "standin.parquet")
        open(p, "wb").write(b"synthetic stand-in, not benchmark data\n")
        open(os.path.join(sib, "marker"), "w").close()
        r = cfg.run(exec_='test -e "$1/marker" && echo SIBLING-BOUND; test -e "$2" && echo STANDIN-VISIBLE; '
                          'test -e "$3" && echo STANDIN-DIR-VISIBLE; echo done', args=[sib, p, d],
                    SANDBOX_PROTECT=p, SANDBOX_RO_BINDS=sib, SANDBOX_RO_ROOT=sib)
        assert r.returncode == 0, r.stderr
        assert r.stdout.split() == ["SIBLING-BOUND", "done"], r.stdout
        # binding the home itself must be refused, and must never make the stand-in visible
        r = cfg.run(exec_='test -e "$1" && echo STANDIN-VISIBLE; echo done', args=[p], SANDBOX_PROTECT=p,
                    SANDBOX_RO_BINDS=home, SANDBOX_RO_ROOT=home)
        assert "STANDIN-VISIBLE" not in r.stdout, "the stand-in became visible through an ancestor bind"
        assert r.returncode == 2 and "home directory" in r.stderr, (r.returncode, r.stderr)
    finally:
        shutil.rmtree(d, ignore_errors=True)
        shutil.rmtree(sib, ignore_errors=True)


@needs_box
def test_f2_launch_line_logs_every_extra_bind(cfg, extra):
    r = cfg.run(exec_="true", SANDBOX_LOG=cfg.log, SANDBOX_RO_BINDS=extra.tools, SANDBOX_RO_ROOT=extra.base, SANDBOX_RW_BINDS=extra.proctor,
                SANDBOX_RW_ROOT=extra.runout)
    assert r.returncode == 0, r.stderr
    line = [l for l in open(cfg.log).read().splitlines() if l.startswith("wrapper-launch ")][0]
    assert "ro_binds=" + extra.tools in line and "rw_binds=" + extra.proctor in line, line


# ---------------------------------------------------------------- R3: the binary cannot be shadowed; the file hashed is the file bound

@pytest.fixture
def fake_bwrap_fd(tmp_path):
    """A bwrap stand-in that records its argv and, for the binary's --ro-bind-fd, the sha256 of what that fd holds
    AFTER the host path has been replaced by a different file (rename, so the open fd keeps the old inode)."""
    d = tmp_path / "fakebin-fd"
    d.mkdir()
    out = str(tmp_path / "bwrap-fd-called")
    make_exe(str(d / "bwrap"),
             '#!/bin/sh\n' + FAKE_PROBE_PASS + 'echo "$$ $*" > "$FAKE_BWRAP_OUT"\nfd=; dest=\n'
             'while [ $# -gt 0 ]; do if [ "$1" = --ro-bind-fd ]; then fd=$2; dest=$3; fi; shift; done\n'
             'if [ -n "$FAKE_REPLACE" ]; then printf "swapped\\n" > "$FAKE_REPLACE.new" && mv "$FAKE_REPLACE.new" "$FAKE_REPLACE"; fi\n'
             'if [ -n "$fd" ]; then echo "FDSHA=$(sha256sum < /dev/fd/$fd | cut -d" " -f1) FDDEST=$dest" >> "$FAKE_BWRAP_OUT"; fi\n'
             'exit 99\n')
    return str(d), out


def test_r3_binary_is_bound_by_the_fd_that_was_hashed(cfg, fake_bwrap_fd):
    fdir, out = fake_bwrap_fd
    r = cfg.run(exec_="true", PATH=fdir + ":/usr/bin:/bin", FAKE_BWRAP_OUT=out, FAKE_REPLACE=cfg.binary)
    assert r.returncode == 99, r.stderr
    text = open(out).read()
    argv, _, tail = text.partition("\n")
    assert "--ro-bind-fd" in argv.split(), argv
    f = dict(kv.split("=", 1) for kv in tail.split())
    assert f.get("FDSHA") == cfg.sha, "the fd bound is not the file that was hashed: %r" % tail
    assert f.get("FDDEST") == os.path.realpath(cfg.binary)
    assert open(cfg.binary).read() == "swapped\n"  # the host path really was replaced: the fd is the only link to the hashed file
    toks = argv.split()
    path_binds = [toks[i + 1] for i, t in enumerate(toks) if t == "--ro-bind"]
    assert os.path.realpath(cfg.binary) not in path_binds, "the binary is also bound by path"


def test_r3_binary_bind_is_the_last_mount(cfg, fake_bwrap_fd, extra):
    fdir, out = fake_bwrap_fd
    r = cfg.run(exec_="true", PATH=fdir + ":/usr/bin:/bin", FAKE_BWRAP_OUT=out, SANDBOX_RO_BINDS=extra.tools,
                SANDBOX_RO_ROOT=extra.base, SANDBOX_RW_BINDS=extra.proctor, SANDBOX_RW_ROOT=extra.runout)
    assert r.returncode == 99, r.stderr
    toks = open(out).read().partition("\n")[0].split()
    mounts = [i for i, t in enumerate(toks) if t in ("--bind", "--ro-bind", "--ro-bind-fd", "--bind-fd", "--tmpfs", "--ro-bind-try",
                                                     "--ro-bind-data", "--proc", "--dev", "--dir", "--symlink")]
    assert toks[mounts[-1]] == "--ro-bind-fd", "something is mounted after the binary: %r" % toks[mounts[-1]]


def _binary_in(cfg, tmp_path):
    rwroot = tmp_path / "rwroot"
    d = rwroot / "d"
    d.mkdir(parents=True)
    fc2 = str(d / "fc2")
    shutil.copy(cfg.binary, fc2)
    os.chmod(fc2, 0o755)
    c = Cfg.__new__(Cfg)
    c.__dict__.update(cfg.__dict__)
    c.binary = fc2
    return c, rwroot, d


def test_r3_binary_inside_an_rw_entry_or_the_slot_is_refused(cfg, fake_bwrap, tmp_path):
    c, rwroot, d = _binary_in(cfg, tmp_path)
    # the review's measured case: the binary inside an RW entry (refused at the root that contains it, or at the entry)
    _refused(c, fake_bwrap, "SANDBOX_RW_", "binary", SANDBOX_RW_BINDS=str(d), SANDBOX_RW_ROOT=str(rwroot))
    _refused(c, fake_bwrap, "SANDBOX_RW_", "binary", SANDBOX_RW_BINDS=str(d), SANDBOX_RW_ROOT=str(d))
    # and a slot that contains it
    _refused(c, fake_bwrap, "SANDBOX_SLOT", "binary", SANDBOX_SLOT=str(d))
    # control: the same layout with the binary elsewhere is accepted
    _accepted(cfg, fake_bwrap, SANDBOX_RW_BINDS=str(d), SANDBOX_RW_ROOT=str(rwroot))


@needs_box
def test_r3_a_box_write_to_the_binary_path_fails_even_if_it_sits_in_a_writable_bind(cfg, tmp_path):
    """The refusals above make this layout unreachable; the test-only knob lifts them so the ORDER of the mounts is
    tested on its own: the binary bind comes last, so it wins over an RW bind that contains it."""
    c, rwroot, d = _binary_in(cfg, tmp_path)
    fc2 = c.binary
    before = open(fc2).read()
    r = c.run(exec_='(echo POISON >> "$1") 2>/dev/null && echo WROTE; (: > "$1") 2>/dev/null && echo TRUNCATED; touch "$2/sibling" && echo SIBLING-OK; echo done',
              args=[fc2, str(d)], SANDBOX_RW_BINDS=str(d), SANDBOX_RW_ROOT=str(rwroot),
              SANDBOX_TEST_ALLOW_BINARY_IN_RW="1")
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == ["SIBLING-OK", "done"], r.stdout   # the RW bind works; the binary inside it does not
    assert open(fc2).read() == before, "the pinned binary changed on the host"


@needs_box
def test_r3_no_leaked_descriptors_inside(cfg):
    r = cfg.run(exec_="ls /proc/self/fd")
    assert r.returncode == 0, r.stderr
    assert set(r.stdout.split()) <= {"0", "1", "2", "3"}, "the box inherited extra descriptors: %r" % r.stdout.split()


# ---------------------------------------------------------------- R4: /etc stays, minus what names other people

ETC_OVERLAID = ("passwd", "group", "machine-id", "hostname")


def _people_names():
    """Account names with uid >= 1000 (minus 65534), from the HOST's database at test time."""
    import pwd
    return sorted({u.pw_name for u in pwd.getpwall() if u.pw_uid >= 1000 and u.pw_uid != 65534})


def _name_rx(names):
    """Whole word, any delimiter: not preceded or followed by a letter or digit."""
    import re
    if not names:
        return None
    alt = b"|".join(re.escape(n.encode()) for n in names)
    return re.compile(rb"(?<![A-Za-z0-9])(?:" + alt + rb")(?![A-Za-z0-9])")


def _host_etc_masked():
    """Which files the wrapper must have masked, for the mechanics cells (the launch-line count, empty inside): every
    readable regular file under /etc (symlinks not followed) whose content contains '/home/' or the name of an
    account with uid >= 1000 as a whole word, except the four files replaced by synthetic ones. The RULE itself is
    checked by test_r4_no_readable_file_under_etc_names_a_person, which does not use this function."""
    rx = _name_rx(_people_names())
    skip = {os.path.realpath("/etc/" + n) for n in ETC_OVERLAID}
    out = []
    for dp, dn, fn in os.walk("/etc"):
        for f in fn:
            p = os.path.join(dp, f)
            if os.path.islink(p) or not os.path.isfile(p) or not os.access(p, os.R_OK) or os.path.realpath(p) in skip:
                continue
            try:
                d = open(p, "rb").read()
            except OSError:
                continue
            if b"/home/" in d or (rx is not None and rx.search(d)):
                out.append(p)
    return sorted(out)


ETC_PROBE = r'''
import os, re, sys
# argv[1]: a file listing the names, one per line. Prints COUNTS only, never a name or a path.
names = [n for n in open(sys.argv[1]).read().split("\n") if n]
alts = [re.compile(rb"(?<!\w)" + re.escape(n.encode()) + rb"(?!\w)") for n in names]
files = bad_name = bad_home = errors = 0
for dp, dn, fn in os.walk("/etc"):
    for f in fn:
        p = os.path.join(dp, f)
        if not os.path.isfile(p):
            continue
        real = os.path.realpath(p)
        if real != "/etc" and not real.startswith("/etc/"):
            continue                      # a symlink that leaves /etc is not followed
        if not os.access(p, os.R_OK):
            continue
        if real in ("/etc/passwd", "/etc/group"):
            continue                      # synthetic: root and the invoking account only, by design (own cell)
        try:
            d = open(p, "rb").read()
        except OSError:
            errors += 1
            continue
        files += 1
        if b"/home/" in d:
            bad_home += 1
        if any(a.search(d) for a in alts):
            bad_name += 1
print("FILES", files, "BAD_NAME", bad_name, "BAD_HOME", bad_home, "ERRORS", errors, "NAMES", len(names))
'''


@needs_box
def test_r4_no_readable_file_under_etc_names_a_person(cfg):
    """Class check from inside the box. The name set is generated here from the HOST's account database (uid >= 1000,
    minus 65534), not from the wrapper; every readable file under /etc is read and matched as a whole word (any
    delimiter). Counts only are printed."""
    names = _people_names()
    assert names, "the host account database lists no account with uid >= 1000"
    nf = os.path.join(cfg.slot, "names.txt")
    open(nf, "w").write("\n".join(names) + "\n")
    pf = os.path.join(cfg.slot, "etcprobe.py")
    open(pf, "w").write(ETC_PROBE)
    r = cfg.run(exec_='%s -I %s %s' % (PY, shlex.quote(pf), shlex.quote(nf)))
    assert r.returncode == 0, r.stderr
    t = r.stdout.split()
    got = dict(zip(t[0::2], map(int, t[1::2])))
    assert got["FILES"] > 20 and got["NAMES"] == len(names), got
    assert got["BAD_NAME"] == 0 and got["BAD_HOME"] == 0, got


def _etc_scan(root):
    r = subprocess.run([PY, "-I", FWD, "etc-scan", "--root", root], capture_output=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return sorted(os.path.basename(x.decode()) for x in r.stdout.split(b"\0") if x)


def test_r4_scan_masks_a_name_in_any_delimiter_and_only_a_whole_word(tmp_path):
    """The scan helper on a stand-in /etc the test controls (the host /etc is never written)."""
    import pwd
    names = _people_names()
    assert names
    n = names[0]
    system = [u.pw_name for u in pwd.getpwall() if u.pw_uid < 1000 and u.pw_name not in names and u.pw_name != "root"]
    assert system, "no system account (uid < 1000) other than root in the host database"
    root = tmp_path / "etc-standin"
    (root / "sub").mkdir(parents=True)
    planted = {
        "space-delimited": "AllowUsers %s other\n" % n,
        "line-start": "%s ALL=(ALL) ALL\n" % n,
        "key-equals": "owner=%s\n" % n,
        "colon": "x:%s:y\n" % n,
        "quoted": 'user "%s"\n' % n,
        "home-path": "path /home/\n",
    }
    for k, v in planted.items():
        (root / "sub" / k).write_text(v)
    controls = {
        "inside-a-longer-word": "x%sy and %s2 and a%s\n" % (n, n, n),
        "system-account": "%s root\n" % system[0],
        "plain": "nothing to see\n",
    }
    for k, v in controls.items():
        (root / k).write_text(v)
    got = _etc_scan(str(root))
    assert got == sorted(planted), got


@needs_box
def test_r4_passwd_and_group_list_only_root_and_the_invoker(cfg):
    import pwd, grp
    me = pwd.getpwuid(os.getuid())
    r = cfg.run(exec_="cat /etc/passwd; echo ====; cat /etc/group; echo ====; id -un; id -gn; echo $HOME")
    assert r.returncode == 0, r.stderr
    pw, gr, rest = r.stdout.split("====\n")
    rows = [l.split(":") for l in pw.splitlines() if l.strip()]
    assert {x[0] for x in rows} == {"root", me.pw_name}, rows
    mine = [x for x in rows if x[0] == me.pw_name][0]
    assert int(mine[2]) == me.pw_uid and int(mine[3]) == me.pw_gid and mine[5] == cfg.slot, mine
    gnames = {l.split(":")[0] for l in gr.splitlines() if l.strip()}
    gme = grp.getgrgid(os.getgid()).gr_name
    assert gnames <= {"root", gme} and gme in gnames, gnames
    assert "/home/" not in pw + gr
    assert rest.split()[0] == me.pw_name, rest


@needs_box
def test_r4_machine_id_and_hostname_are_fixed(cfg):
    r = cfg.run(exec_='for f in /etc/machine-id /etc/hostname; do if [ -e "$f" ]; then echo "$f"; cat "$f"; fi; done; '
                      'echo KERNEL-HOSTNAME; cat /proc/sys/kernel/hostname')
    assert r.returncode == 0, r.stderr
    out = r.stdout
    if os.path.isfile("/etc/machine-id"):
        assert "/etc/machine-id\n" + "0" * 32 + "\n" in out, out
    if os.path.isfile("/etc/hostname"):
        assert "/etc/hostname\nsandbox\n" in out, out
    assert out.endswith("KERNEL-HOSTNAME\nsandbox\n"), out   # the host's name is not visible through the kernel either


@needs_box
def test_r4_launch_line_counts_masked_files_not_names(cfg):
    masked = _host_etc_masked()
    r = cfg.run(exec_="true", SANDBOX_LOG=cfg.log)
    assert r.returncode == 0, r.stderr
    line = [l for l in open(cfg.log).read().splitlines() if l.startswith("wrapper-launch ")][0]
    f = dict(kv.split("=", 1) for kv in line.split()[1:])
    assert f["etc_masked"] == str(len(masked)), (f["etc_masked"], len(masked))
    for p in masked:
        assert os.path.basename(p) not in line.split(), "a masked file name is in the launch line"


@needs_box
def test_r4_masked_files_are_empty_and_every_other_etc_file_is_unchanged(cfg):
    """Masked files read empty inside; every other readable regular file under /etc is byte-identical to the host's
    (so /etc is genuinely still there for the harness), except the four synthetic ones."""
    masked = set(_host_etc_masked())
    skip = {os.path.realpath("/etc/" + n) for n in ETC_OVERLAID}
    keep = []
    for dp, dn, fn in os.walk("/etc"):
        for f in fn:
            p = os.path.join(dp, f)
            if (not os.path.islink(p) and os.path.isfile(p) and os.access(p, os.R_OK) and p not in masked
                    and os.path.realpath(p) not in skip):
                keep.append(p)
    assert len(keep) > 20 and masked, (len(keep), len(masked))
    listing = os.path.join(cfg.slot, "paths.txt")
    open(listing, "w").write("\n".join(keep + sorted(masked)))
    probe = ('%s -I -c \'import hashlib,sys\n'
             'for p in open(sys.argv[1]).read().split("\\n"):\n'
             '    try: print(hashlib.sha256(open(p,"rb").read()).hexdigest(), p)\n'
             '    except OSError as e: print("ERR", p)\' %s') % (PY, shlex.quote(listing))
    r = cfg.run(exec_=probe, timeout=120)
    assert r.returncode == 0, r.stderr
    got = {l.split(" ", 1)[1]: l.split(" ", 1)[0] for l in r.stdout.splitlines()}
    empty = hashlib.sha256(b"").hexdigest()
    for p in masked:
        assert got[p] == empty, "masked file is not empty inside: " + p
    differ = [p for p in keep if got[p] != sha256_of(p)]
    assert not differ, "%d unmasked /etc files differ inside the box" % len(differ)


@needs_box
def test_r4_opt_is_not_bound(cfg):
    r = cfg.run(exec_='if [ -d /opt ]; then ls -A /opt | wc -l; else echo absent; fi')
    assert r.returncode == 0, r.stderr
    assert r.stdout.split()[0] in ("absent", "0"), "host /opt is visible inside: %r" % r.stdout


# ---------------------------------------------------------------- R5: the model bridge is an HTTP request allow-list

class HttpStub(socketserver.ThreadingTCPServer):
    """A model-server stand-in speaking HTTP/1.1 with keep-alive. Records every request it receives as
    (method, target, exact raw bytes of the request including its body); `sent` holds the exact response bytes."""
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self):
        outer = self
        self.records = []
        self.sent = []
        self.lock = threading.Lock()

        class H(socketserver.StreamRequestHandler):
            def handle(h):
                h.request.settimeout(10)
                try:
                    while h._one():
                        pass
                except (OSError, ValueError):
                    pass

            def _one(h):
                line = h.rfile.readline()
                if not line:
                    return False
                raw, headers = line, {}
                while True:
                    l = h.rfile.readline()
                    raw += l
                    if l in (b"\r\n", b""):
                        break
                    k, _, v = l.decode().partition(":")
                    headers[k.strip().lower()] = v.strip()
                if headers.get("transfer-encoding", "").lower() == "chunked":
                    while True:
                        sz = h.rfile.readline()
                        raw += sz
                        n = int(sz.split(b";")[0], 16)
                        if n:
                            raw += h.rfile.read(n + 2)
                        if n == 0:
                            while True:
                                t = h.rfile.readline()
                                raw += t
                                if t in (b"\r\n", b""):
                                    break
                            break
                elif "content-length" in headers:
                    raw += h.rfile.read(int(headers["content-length"]))
                method, target = line.split()[0].decode(), line.split()[1].decode()
                with outer.lock:
                    outer.records.append((method, target, raw))
                if target.endswith("/stream"):
                    body = b"".join(b"%x\r\n%s\r\n" % (len(c), c) for c in (b"alpha", b"beta-beta", b"g")) + b"0\r\n\r\n"
                    resp = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n" + body
                    with outer.lock:
                        outer.sent.append(resp)
                    for i in range(0, len(resp), 7):
                        h.wfile.write(resp[i:i + 7])
                        h.wfile.flush()
                        time.sleep(0.002)
                    return False
                payload = ("OK:%s:%s" % (method, target)).encode()
                resp = b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\n\r\n%s" % (len(payload), payload)
                with outer.lock:
                    outer.sent.append(resp)
                h.wfile.write(resp)
                h.wfile.flush()
                return headers.get("connection", "").lower() != "close"

        super().__init__(("127.0.0.1", free_port()), H)
        self.port = self.server_address[1]
        threading.Thread(target=self.serve_forever, daemon=True).start()

    def seen(self):
        time.sleep(0.3)   # a request that was wrongly forwarded would have arrived by now
        with self.lock:
            return [(m, t) for m, t, _ in self.records]


class OuterProc:
    """The host-side forwarder run on its own (no box), so the allow-list contract is tested at its own boundary."""

    def __init__(self, stub_port, allow=None, learn=False, log=None, max_request=32 << 20, max_total=64 << 20,
                 max_conns=64, read_idle_s=120):
        self.dir = tempfile.mkdtemp(prefix="sbx-")   # short, so the AF_UNIX path stays well under the limit
        self.sock = os.path.join(self.dir, "b.sock")
        args = [PY, "-I", FWD, "outer", "--sock", self.sock, "--host", "127.0.0.1", "--port", str(stub_port),
                "--watch", str(os.getpid())]
        if allow is not None:
            args += ["--allow", allow]
        if learn:
            args += ["--learn"]
        if log:
            args += ["--log", log]
        # the caps are required arguments (the wrapper owns the numbers); generous here so ordinary cells never meet them
        args += ["--max-request", str(max_request), "--max-total", str(max_total), "--max-conns", str(max_conns)]
        args += ["--read-idle-s", str(read_idle_s)]
        self.p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        end = time.time() + 10
        while not os.path.exists(self.sock) and time.time() < end and self.p.poll() is None:
            time.sleep(0.02)
        assert os.path.exists(self.sock), "the forwarder did not start: %r" % self.p.communicate(timeout=5)[1]

    def connect(self):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect(self.sock)
        return s

    def close(self):
        self.p.terminate()
        try:
            self.p.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            self.p.kill()
        shutil.rmtree(self.dir, ignore_errors=True)


@pytest.fixture
def http_stub():
    made = []

    def mk():
        s = HttpStub()
        made.append(s)
        return s
    yield mk
    for s in made:
        s.shutdown()
        s.server_close()


@pytest.fixture
def outer():
    made = []

    def mk(stub, **kw):
        o = OuterProc(stub.port, **kw)
        made.append(o)
        return o
    yield mk
    for o in made:
        o.close()


def read_response(s):
    """(status, headers, body) of one Content-Length response; body empty when there is none."""
    buf = b""
    while b"\r\n\r\n" not in buf:
        c = s.recv(65536)
        if not c:
            break
        buf += c
    head, _, rest = buf.partition(b"\r\n\r\n")
    lines = head.decode(errors="replace").split("\r\n")
    status = int(lines[0].split()[1]) if lines and len(lines[0].split()) > 1 else 0
    headers = {k.strip().lower(): v.strip() for k, _, v in (l.partition(":") for l in lines[1:])}
    n = int(headers.get("content-length", "0"))
    while len(rest) < n:
        c = s.recv(65536)
        if not c:
            break
        rest += c
    return status, headers, rest[:n]


def at_eof(s):
    try:
        return s.recv(1) == b""
    except (ConnectionResetError, socket.timeout):
        return False


def req(method, target, body=b"", extra=b"", version=b"HTTP/1.1"):
    head = b"%s %s %s\r\nHost: model\r\n" % (method.encode(), target.encode(), version)
    if body:
        head += b"Content-Length: %d\r\n" % len(body)
    return head + extra + b"\r\n" + body


ALLOW = "POST /v1/messages, GET /v1/models, POST /api/*"


def test_r5_an_allowed_post_reaches_the_stub_with_its_body_intact(outer, http_stub):
    stub = http_stub()
    o = outer(stub, allow=ALLOW)
    s = o.connect()
    raw = req("POST", "/v1/messages?beta=1", body=b'{"model":"m","messages":[]}')
    s.sendall(raw)
    status, _, body = read_response(s)
    assert (status, body) == (200, b"OK:POST:/v1/messages?beta=1")
    assert [(m, t) for m, t, _ in stub.records] == [("POST", "/v1/messages?beta=1")]
    assert stub.records[0][2] == raw, "the request was altered on the way"


def test_r5_a_delete_and_a_non_listed_path_get_403_and_never_reach_the_stub(outer, http_stub):
    stub = http_stub()
    o = outer(stub, allow=ALLOW)
    for raw in (req("DELETE", "/api/delete", body=b'{"name":"x"}'),     # method not listed for a listed prefix
                req("POST", "/api/../admin"),                           # dot segments must not slip past a prefix
                req("POST", "/api/%2e%2e/admin"),                       # nor an encoded one
                req("POST", "/api/%252e%252e/admin"),                   # nor a double-encoded one
                req("POST", "//api/x"),                                 # nor an empty segment
                req("POST", "/v1/messages/extra"),                      # exact entries are exact
                req("GET", "/v1/messages"),                             # method must match the entry
                req("POST", "/v1"), req("GET", "/")):
        s = o.connect()
        s.sendall(raw)
        status, _, _ = read_response(s)
        assert status == 403, raw
        assert at_eof(s), "the connection stayed open after a 403: %r" % raw
    assert stub.seen() == []


def test_r5_prefix_entry_matches_beneath_it_only(outer, http_stub):
    stub = http_stub()
    o = outer(stub, allow=ALLOW)
    for target, want in (("/api/chat", 200), ("/api/", 200), ("/api/a/b/c", 200), ("/api", 403), ("/apix", 403)):
        s = o.connect()
        s.sendall(req("POST", target))
        assert read_response(s)[0] == want, target


def test_r5_the_second_request_on_a_keep_alive_connection_is_checked_too(outer, http_stub):
    stub = http_stub()
    o = outer(stub, allow=ALLOW)
    s = o.connect()
    s.sendall(req("POST", "/v1/messages", body=b"{}"))
    assert read_response(s)[0] == 200
    s.sendall(req("POST", "/v1/messages", body=b"{}"))      # a second allowed one on the same connection still works
    assert read_response(s)[0] == 200
    s.sendall(req("DELETE", "/v1/messages"))               # the third is not allowed
    assert read_response(s)[0] == 403
    assert at_eof(s)
    assert stub.seen() == [("POST", "/v1/messages"), ("POST", "/v1/messages")]


def test_r5_pipelined_requests_in_one_segment_are_each_checked(outer, http_stub):
    stub = http_stub()
    o = outer(stub, allow=ALLOW)
    s = o.connect()
    s.sendall(req("GET", "/v1/models") + req("DELETE", "/v1/models") + req("GET", "/v1/models"))
    data = b""
    while True:
        c = s.recv(65536)
        if not c:
            break
        data += c
    assert data.count(b"HTTP/1.1 200") == 1 and data.count(b"HTTP/1.1 403") == 1, data
    assert stub.seen() == [("GET", "/v1/models")]


def test_r5_a_chunked_body_passes_intact(outer, http_stub):
    stub = http_stub()
    o = outer(stub, allow=ALLOW)
    s = o.connect()
    raw = (b"POST /v1/messages HTTP/1.1\r\nHost: model\r\nTransfer-Encoding: chunked\r\n\r\n"
           b"5\r\nhello\r\n6\r\n world\r\n0\r\n\r\n")
    s.sendall(raw[:40])
    time.sleep(0.05)
    s.sendall(raw[40:70])
    time.sleep(0.05)
    s.sendall(raw[70:])
    assert read_response(s)[0] == 200
    assert stub.records[0][2] == raw
    # and a chunked request that is NOT allowed is refused before any of its body is forwarded
    s2 = o.connect()
    s2.sendall(raw.replace(b"POST /v1/messages", b"POST /nope"))
    assert read_response(s2)[0] == 403
    assert stub.seen() == [("POST", "/v1/messages")]


def test_r5_a_large_body_passes_intact(outer, http_stub):
    stub = http_stub()
    o = outer(stub, allow=ALLOW)
    s = o.connect()
    body = bytes(range(256)) * 4096   # 1 MiB
    raw = req("POST", "/v1/messages", body=body)
    s.sendall(raw)
    assert read_response(s)[0] == 200
    assert stub.records[0][2] == raw


def test_r5_a_streamed_response_is_relayed_unchanged(outer, http_stub):
    stub = http_stub()
    o = outer(stub, allow=ALLOW)
    s = o.connect()
    s.sendall(req("POST", "/api/stream"))
    got = b""
    while True:
        c = s.recv(65536)
        if not c:
            break
        got += c
    assert got == stub.sent[0] and b"beta-beta" in got


def test_r5_requests_that_cannot_be_framed_or_checked_are_refused(outer, http_stub):
    stub = http_stub()
    o = outer(stub, allow=ALLOW)
    cases = {
        "both length and chunked": (b"POST /v1/messages HTTP/1.1\r\nHost: m\r\nContent-Length: 2\r\n"
                                    b"Transfer-Encoding: chunked\r\n\r\n2\r\n{}\r\n0\r\n\r\n", 400),
        "two different lengths": (b"POST /v1/messages HTTP/1.1\r\nHost: m\r\nContent-Length: 2\r\nContent-Length: 3\r\n\r\n{}x", 400),
        "bad length": (b"POST /v1/messages HTTP/1.1\r\nHost: m\r\nContent-Length: -1\r\n\r\n", 400),
        "folded header": (b"POST /v1/messages HTTP/1.1\r\nHost: m\r\nX-A: 1\r\n  folded\r\n\r\n", 400),
        "lower-case method": (b"post /v1/messages HTTP/1.1\r\nHost: m\r\n\r\n", 400),
        "not http": (b"REQUEST-SECRET-QQQ\r\n\r\n", 400),
        "bare LF": (b"POST /v1/messages HTTP/1.1\nHost: m\n\n", 400),
        "upgrade": (b"GET /v1/models HTTP/1.1\r\nHost: m\r\nConnection: Upgrade\r\nUpgrade: websocket\r\n\r\n", 403),
        "connect": (b"CONNECT model:443 HTTP/1.1\r\nHost: model\r\n\r\n", 403),
        "absolute form": (b"GET http://model/v1/models HTTP/1.1\r\nHost: model\r\n\r\n", 403),
        "unsupported coding": (b"POST /v1/messages HTTP/1.1\r\nHost: m\r\nTransfer-Encoding: gzip\r\n\r\n", 400),
    }
    for name, (raw, want) in cases.items():
        s = o.connect()
        s.sendall(raw)
        status, _, _ = read_response(s)
        assert status == want, (name, status)
        assert at_eof(s), name
    assert stub.seen() == []


def test_r5_a_connection_that_sends_nothing_reaches_nothing(outer, http_stub):
    stub = http_stub()
    o = outer(stub, allow=ALLOW)
    s = o.connect()
    s.close()
    assert stub.seen() == []


def test_r5_learn_mode_allows_everything_and_logs_method_and_path_only(outer, http_stub, tmp_path):
    stub = http_stub()
    log = str(tmp_path / "learn.log")
    o = outer(stub, learn=True, log=log)
    s = o.connect()
    s.sendall(req("DELETE", "/api/delete?secret-query=QQQ-SECRET", body=b"BODY-SECRET-ZZZ"))
    assert read_response(s)[0] == 200
    s.sendall(req("POST", "/v1/messages?x=1", body=b"BODY-SECRET-ZZZ"))
    assert read_response(s)[0] == 200
    assert stub.seen() == [("DELETE", "/api/delete?secret-query=QQQ-SECRET"), ("POST", "/v1/messages?x=1")]
    time.sleep(0.5)
    text = open(log).read()
    lines = [l for l in text.splitlines() if l.startswith("fwd-req ")]
    assert lines == ["fwd-req method=DELETE path=/api/delete", "fwd-req method=POST path=/v1/messages"], text
    assert "SECRET" not in text and "QQQ" not in text and "BODY" not in text


def test_r5_enforce_mode_logs_denials_by_method_and_path_only(outer, http_stub, tmp_path):
    stub = http_stub()
    log = str(tmp_path / "deny.log")
    o = outer(stub, allow=ALLOW, log=log)
    s = o.connect()
    s.sendall(req("DELETE", "/api/delete?q=QQQ-SECRET", body=b"BODY-SECRET-ZZZ"))
    assert read_response(s)[0] == 403
    time.sleep(0.5)
    text = open(log).read()
    deny = [l for l in text.splitlines() if l.startswith("fwd-deny ")]
    assert len(deny) == 1 and deny[0].startswith("fwd-deny method=DELETE path=/api/delete status=403 "), text
    assert " kind=rule reason=not-on-allow-list " in deny[0], deny
    assert "SECRET" not in text and "QQQ" not in text and not [l for l in text.splitlines() if l.startswith("fwd-req ")]


def test_r5_the_forwarder_refuses_to_start_without_an_allow_list_or_learn_mode(tmp_path):
    for args in ([], ["--allow", ""], ["--allow", "get /x"], ["--allow", "POST x"], ["--allow", "POST /a*b"],
                 ["--allow", "POST /a,,GET /b"], ["--allow", "POST"], ["--allow", "POST /a b"]):
        d = tempfile.mkdtemp(prefix="sbx-")
        try:
            p = subprocess.run([PY, "-I", FWD, "outer", "--sock", os.path.join(d, "b.sock"), "--host", "127.0.0.1",
                                "--port", "9", "--watch", str(os.getpid())] + args, capture_output=True, text=True, timeout=10)
            assert p.returncode == 2 and not os.path.exists(os.path.join(d, "b.sock")), (args, p.returncode, p.stderr)
        finally:
            shutil.rmtree(d, ignore_errors=True)


def test_r5_the_upstream_connection_has_no_idle_timeout(http_stub):
    """A model that is slow to its first byte must not be cut by the connect timeout that create_connection leaves
    on the socket (the bridge cannot use a socket with a 10 s receive timeout)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("sandbox_forward_under_test", FWD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    stub = http_stub()
    s = mod.connect_upstream("127.0.0.1", stub.port)
    try:
        assert s.gettimeout() is None
    finally:
        s.close()


# the wrapper's own contract for the new variables

def test_r5_wrapper_requires_a_wellformed_allow_list(cfg, fake_bwrap):
    assert_refused(cfg, fake_bwrap, "SANDBOX_MODEL_ALLOW", drop=("SANDBOX_MODEL_ALLOW",))
    for val in ("", "   ", ",", "POST", "post /x", "POST x", "POST /a*b", "POST /a,,GET /b", "POST /a b", "POST /a,"):
        assert_refused(cfg, fake_bwrap, "SANDBOX_MODEL_ALLOW", SANDBOX_MODEL_ALLOW=val)
    _accepted(cfg, fake_bwrap, SANDBOX_MODEL_ALLOW="POST /v1/messages, GET /v1/models,POST /api/*")


def test_r5_wrapper_learn_mode_rules(cfg, fake_bwrap):
    fdir, out = fake_bwrap
    # learn mode needs a log to learn into
    r = cfg.run(exec_="true", PATH=fdir + ":/usr/bin:/bin", FAKE_BWRAP_OUT=out, SANDBOX_MODEL_LEARN="1", drop=("SANDBOX_MODEL_ALLOW",))
    assert r.returncode == 2 and "SANDBOX_MODEL_LEARN" in r.stderr and len(r.stderr.splitlines()) == 1, r.stderr
    assert not os.path.exists(out) and os.listdir(cfg.tmpd) == []
    # it is only ever "1"
    for val in ("yes", "true", "2", "0 "):
        assert_refused(cfg, fake_bwrap, "SANDBOX_MODEL_LEARN", SANDBOX_MODEL_LEARN=val)
    # with a log, the allow-list is not required
    r = cfg.run(exec_="true", PATH=fdir + ":/usr/bin:/bin", FAKE_BWRAP_OUT=out, SANDBOX_LOG=cfg.log,
                SANDBOX_MODEL_LEARN="1", drop=("SANDBOX_MODEL_ALLOW",))
    assert r.returncode == 99, r.stderr
    os.unlink(out)
    _wait_clean(cfg)
    # an empty learn flag is off: the allow-list is required again
    assert_refused(cfg, fake_bwrap, "SANDBOX_MODEL_ALLOW", SANDBOX_MODEL_LEARN="", drop=("SANDBOX_MODEL_ALLOW",))


@needs_box
def test_r5_end_to_end_through_the_box(cfg, http_stub):
    stub = http_stub()
    cfg.model_port = stub.port
    probe = ('%s -I -c \'import http.client\n'
             'c = http.client.HTTPConnection("127.0.0.1", %d, timeout=10)\n'
             'c.request("POST", "/v1/messages", body=b"{}", headers={"Content-Type": "application/json"})\n'
             'r = c.getresponse(); print(r.status, r.read().decode())\n'
             'c.request("DELETE", "/api/delete")\n'
             'r = c.getresponse(); print(r.status); r.read()\'') % (PY, stub.port)
    r = cfg.run(exec_=probe, SANDBOX_MODEL_ALLOW="POST /v1/messages")
    assert r.returncode == 0, r.stderr
    assert r.stdout.split("\n")[:2] == ["200 OK:POST:/v1/messages", "403"], r.stdout
    assert stub.seen() == [("POST", "/v1/messages")]


# ---------------------------------------------------------------- R6: tmpfs caps

GIB, MIB = 1 << 30, 1 << 20
SIZE_PROBE = 'for p in /tmp /var/tmp /home /run /dev/shm; do echo "$p $(( $(stat -f -c "%S * %b" "$p") ))"; done'


@needs_box
def test_r6_default_caps_are_2gib_for_tmp_vartmp_and_dev_shm_and_64mib_for_home_and_run(cfg):
    r = cfg.run(exec_=SIZE_PROBE)
    assert r.returncode == 0, r.stderr
    sizes = {l.split()[0]: int(l.split()[1]) for l in r.stdout.splitlines()}
    assert sizes == {"/tmp": 2 * GIB, "/var/tmp": 2 * GIB, "/home": 64 * MIB, "/run": 64 * MIB, "/dev/shm": 2 * GIB}, sizes


@needs_box
@pytest.mark.parametrize("where", ["/tmp", "/var/tmp", "/home", "/run", "/dev/shm"])
def test_r6_a_write_past_the_test_cap_fails_inside(cfg, where):
    r = cfg.run(exec_='dd if=/dev/zero of="$1/small" bs=64k count=4 2>/dev/null && echo SMALL-OK; '
                      'dd if=/dev/zero of="$1/big" bs=64k count=64 2>/dev/null && echo BIG-OK; echo done',
                args=[where], SANDBOX_TEST_TMP_CAP=str(1 * MIB), SANDBOX_TEST_HOME_RUN_CAP=str(1 * MIB))
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == ["SMALL-OK", "done"], r.stdout   # 256 KiB fits, 4 MiB does not


@needs_box
def test_r6_the_cap_override_is_honoured_only_in_test_mode(cfg):
    cfg.set_binary("#!/bin/sh\nstat -f -c '%S * %b' /tmp /home\n")
    r = cfg.run(test=False, SANDBOX_TEST_TMP_CAP=str(1 * MIB), SANDBOX_TEST_HOME_RUN_CAP=str(1 * MIB))
    assert r.returncode == 0, r.stderr
    assert [int(x.split("*")[0]) * int(x.split("*")[1]) for x in r.stdout.splitlines()] == [2 * GIB, 64 * MIB], r.stdout


def test_r6_a_malformed_test_cap_is_refused(cfg, fake_bwrap):
    for var in ("SANDBOX_TEST_TMP_CAP", "SANDBOX_TEST_HOME_RUN_CAP"):
        for val in ("big", "0", "-5", "1e6"):
            assert_refused(cfg, fake_bwrap, var, **{var: val})


# ---------------------------------------------------------------- nits: a stale socket directory is removed by the next launch

def _dead_pid():
    p = subprocess.Popen(["/bin/true"])
    p.wait()
    return p.pid


def _plant(cfg, name, pid=None, sock=True):
    d = os.path.join(cfg.tmpd, name)
    os.mkdir(d)
    if sock:
        open(os.path.join(d, "bridge.sock"), "w").close()
    if pid is not None:
        open(os.path.join(d, "watch.pid"), "w").write("%d\n" % pid)
    return d


def test_nit_the_next_launch_removes_a_stale_socket_directory_and_only_that(cfg, fake_bwrap):
    stale = _plant(cfg, "student-sandbox.stale1", pid=_dead_pid())
    live = _plant(cfg, "student-sandbox.live01", pid=os.getpid())
    nopid = _plant(cfg, "student-sandbox.nopid1")
    junk = _plant(cfg, "student-sandbox.junkpid")
    open(os.path.join(junk, "watch.pid"), "w").write("not-a-pid\n")
    other = _plant(cfg, "someone-elses.dir001", pid=_dead_pid())
    target = os.path.join(cfg.root, "symlink-target")
    os.mkdir(target)
    open(os.path.join(target, "keep"), "w").close()
    open(os.path.join(target, "watch.pid"), "w").write("%d\n" % _dead_pid())
    os.symlink(target, os.path.join(cfg.tmpd, "student-sandbox.linked"))
    afile = os.path.join(cfg.tmpd, "student-sandbox.afile")
    open(afile, "w").close()
    r, out = _launch(cfg, fake_bwrap)
    assert r.returncode == 99, r.stderr
    assert not os.path.exists(stale), "the stale socket directory was not removed"
    for keep in (live, nopid, junk, other, afile, os.path.join(cfg.tmpd, "student-sandbox.linked")):
        assert os.path.exists(keep), "removed something that is not a stale directory of ours: " + keep
    assert sorted(os.listdir(target)) == ["keep", "watch.pid"], "followed a symlink"


def _wait_only(cfg, names):
    """Wait until nothing but the planted entries is left: the launch's own socket directory is cleaned up by its forwarder."""
    end = time.time() + 8
    while set(os.listdir(cfg.tmpd)) - set(names) and time.time() < end:
        time.sleep(0.05)
    assert set(os.listdir(cfg.tmpd)) - set(names) == set(), os.listdir(cfg.tmpd)


def test_nit_a_refused_launch_removes_nothing(cfg, fake_bwrap):
    stale = _plant(cfg, "student-sandbox.stale1", pid=_dead_pid())
    fdir, out = fake_bwrap
    r = cfg.run(exec_="true", PATH=fdir + ":/usr/bin:/bin", FAKE_BWRAP_OUT=out, SANDBOX_BINARY_SHA256="0" * 64)
    assert r.returncode == 2, r.stderr
    assert os.path.exists(stale)


@needs_box
def test_nit_a_forwarder_killed_with_sigkill_leaves_a_directory_that_the_next_launch_removes(cfg):
    mark = "6%d" % (int(time.time() * 1000) % 10**9)
    p = subprocess.Popen(["/bin/bash", WRAPPER], env=cfg.env(exec_="sleep 400.%s" % mark),
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        end = time.time() + 15
        while time.time() < end and not _sleeper_running(".%s" % mark):
            time.sleep(0.05)
        assert _sleeper_running(".%s" % mark), "probe never started"
        fwd = [q for q in procs_with(cfg.tmpd) if q != p.pid]
        assert fwd, "no outer forwarder found"
        for q in fwd:
            os.kill(q, signal.SIGKILL)
        p.kill()
        p.wait()
        assert wait_gone(".%s" % mark)
    finally:
        if p.poll() is None:
            p.kill()
    left = os.listdir(cfg.tmpd)
    assert len(left) == 1 and left[0].startswith("student-sandbox."), left   # the leak the README documents
    r = cfg.run(exec_="true")
    assert r.returncode == 0, r.stderr
    end = time.time() + 8
    while os.listdir(cfg.tmpd) and time.time() < end:
        time.sleep(0.05)
    assert os.listdir(cfg.tmpd) == [], "the stale directory survived the next launch"


# ---------------------------------------------------------------- round 4 (S1, S2): strict framing; HTTP/1.1 only

class RawStub:
    """An upstream that records EVERY byte it receives on each connection and answers nothing; it closes when the
    forwarder shuts down its side. The assertions are on these received bytes, not on the client's status."""

    def __init__(self):
        self.received = []
        self.lock = threading.Lock()
        self.srv = socket.socket()
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("127.0.0.1", free_port()))
        self.srv.listen(16)
        self.port = self.srv.getsockname()[1]
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while True:
            try:
                c, _ = self.srv.accept()
            except OSError:
                return
            threading.Thread(target=self._one, args=(c,), daemon=True).start()

    def _one(self, c):
        c.settimeout(8)
        got = b""
        try:
            while True:
                d = c.recv(65536)
                if not d:
                    break
                got += d
                with self.lock:
                    self.received = [r for r in self.received if r[0] is not c] + [(c, got)]
        except OSError:
            pass
        c.close()

    def bytes_seen(self):
        time.sleep(0.4)
        with self.lock:
            return b"".join(g for _, g in self.received)

    def close(self):
        self.srv.close()


@pytest.fixture
def raw_stub():
    made = []

    def mk():
        s = RawStub()
        made.append(s)
        return s
    yield mk
    for s in made:
        s.close()


CHUNK_HEAD = b"POST /v1/messages HTTP/1.1\r\nHost: m\r\nTransfer-Encoding: chunked\r\n\r\n"

# (name, the bytes after the head, the disallowed bytes that must NEVER reach the upstream)
SMUGGLE = [
    ("bare LF in a chunk-size line, with an extension (the measured shape)",
     b"0;x\n\r\nGET /api/other HTTP/1.1\r\nHost: x\r\n\r\n", [b"0;x", b"GET /api/other"]),
    ("bare LF in a chunk-size line", b"0\nGET /evil HTTP/1.1\r\n\r\n", [b"0\n", b"GET /evil"]),
    ("bare CR in a chunk-size line", b"0\rGET /evil HTTP/1.1\r\n\r\n", [b"0\rG", b"GET /evil"]),
    ("request-shaped trailer", b"0\r\nGET /evil HTTP/1.1\r\n\r\n", [b"GET /evil"]),
    ("a header-shaped trailer", b"0\r\nX-Trailer: t\r\n\r\n", [b"X-Trailer"]),
    ("a chunk extension", b"5;ext=1\r\nhello\r\n0\r\n\r\n", [b";ext"]),
    ("a space after the chunk size", b"5 \r\nhello\r\n0\r\n\r\n", [b"5 \r\n"]),
    ("bare LF as the chunk terminator", b"5\r\nhello\nGET /evil HTTP/1.1\r\n\r\n", [b"GET /evil", b"hello\n"]),
    ("bare CR as the chunk terminator", b"5\r\nhello\rGET /evil HTTP/1.1\r\n\r\n", [b"GET /evil", b"hello\r"]),
]


@pytest.mark.parametrize("name,body,banned", SMUGGLE, ids=[x[0] for x in SMUGGLE])
def test_s1_strict_chunked_framing_refuses_and_the_upstream_receives_none_of_it(outer, raw_stub, name, body, banned):
    stub = raw_stub()
    o = outer(stub, allow=ALLOW)
    s = o.connect()
    s.sendall(CHUNK_HEAD + body)
    status, _, _ = read_response(s)
    assert status == 400, (name, status)
    assert at_eof(s), name
    got = stub.bytes_seen()
    for b in banned:
        assert b not in got, "the upstream received disallowed bytes %r: %r" % (b, got)


def test_s1_strict_framing_still_passes_a_plain_chunked_body_and_the_empty_trailer(outer, raw_stub):
    stub = raw_stub()
    o = outer(stub, allow=ALLOW)
    s = o.connect()
    body = b"5\r\nhello\r\n6\r\n world\r\n0\r\n\r\n"
    s.sendall(CHUNK_HEAD + body)
    got = stub.bytes_seen()
    assert got == CHUNK_HEAD + body, got
    s.close()


def test_s1_a_split_chunk_framing_is_still_framed(outer, raw_stub):
    """Positive control: the strict reader must still work across partial reads (a split CRLF)."""
    stub = raw_stub()
    o = outer(stub, allow=ALLOW)
    s = o.connect()
    raw = CHUNK_HEAD + b"5\r\nhello\r\n0\r\n\r\n"
    for i in range(0, len(raw), 3):
        s.sendall(raw[i:i + 3])
        time.sleep(0.01)
    assert stub.bytes_seen() == raw
    s.close()


VERSIONS = [
    ("HTTP/1.0 with Transfer-Encoding", b"POST /v1/messages HTTP/1.0\r\nHost: m\r\nTransfer-Encoding: chunked\r\n\r\n"
                                        b"5\r\nhello\r\n0\r\n\r\nGET /evil HTTP/1.1\r\nHost: x\r\n\r\n", 505),
    ("HTTP/1.0 plain", b"GET /v1/models HTTP/1.0\r\nHost: m\r\n\r\n", 505),
    ("HTTP/2.0 text", b"GET /v1/models HTTP/2.0\r\nHost: m\r\n\r\n", 505),
    ("HTTP/1.2", b"GET /v1/models HTTP/1.2\r\nHost: m\r\n\r\n", 505),
    ("HTTP/0.9 shape", b"GET /v1/models HTTP/0.9\r\nHost: m\r\n\r\n", 505),
    ("no version", b"GET /v1/models\r\nHost: m\r\n\r\n", 400),
    ("lower-case http", b"GET /v1/models http/1.1\r\nHost: m\r\n\r\n", 400),
]


@pytest.mark.parametrize("name,raw,want", VERSIONS, ids=[x[0] for x in VERSIONS])
def test_s2_only_http_1_1_nothing_else_reaches_the_upstream(outer, raw_stub, name, raw, want):
    stub = raw_stub()
    o = outer(stub, allow=ALLOW + ", GET /v1/models")
    s = o.connect()
    s.sendall(raw)
    status, _, _ = read_response(s)
    assert status == want, (name, status)
    assert at_eof(s), name
    assert stub.bytes_seen() == b"", name


def test_s2_http_1_1_is_still_forwarded(outer, http_stub):
    stub = http_stub()
    o = outer(stub, allow=ALLOW)
    s = o.connect()
    s.sendall(req("GET", "/v1/models"))
    assert read_response(s)[0] == 200


# ---------------------------------------------------------------- round 4 (S6): protected paths are required

def test_s6_protect_unset_or_empty_is_a_named_refusal(cfg, fake_bwrap):
    assert_refused(cfg, fake_bwrap, "SANDBOX_PROTECT", drop=("SANDBOX_PROTECT",))
    assert_refused(cfg, fake_bwrap, "SANDBOX_PROTECT", SANDBOX_PROTECT="")


def test_s6_the_old_dataset_variable_no_longer_stands_in(cfg, fake_bwrap):
    assert_refused(cfg, fake_bwrap, "SANDBOX_PROTECT", drop=("SANDBOX_PROTECT",), BEAM_PARQUET=cfg.prot_file)


def test_s6_protect_entries_must_be_absolute_existing_and_nonempty(cfg, fake_bwrap):
    nosuch = os.path.join(cfg.root, "no-such")
    for val in ("relative/file", nosuch, cfg.prot_file + ":" + nosuch, cfg.prot_file + ":", ":" + cfg.prot_file,
                cfg.prot_file + "::" + cfg.prot_keys):
        assert_refused(cfg, fake_bwrap, "SANDBOX_PROTECT", SANDBOX_PROTECT=val)
    _accepted(cfg, fake_bwrap, SANDBOX_PROTECT=cfg.prot_file)          # a file alone
    _accepted(cfg, fake_bwrap, SANDBOX_PROTECT=cfg.prot_keys)          # a directory alone


def test_s6_a_root_containing_a_protected_file_is_refused(cfg, fake_bwrap, tmp_path):
    t = tmp_path / "ds"
    (t / "inner").mkdir(parents=True)
    f = str(t / "inner" / "data.bin")
    open(f, "w").close()
    for root in (str(t / "inner"), str(t)):
        _refused(cfg, fake_bwrap, "SANDBOX_RO_ROOT", "protected", SANDBOX_RO_BINDS=str(t / "inner"), SANDBOX_RO_ROOT=root,
                 SANDBOX_PROTECT=f)
        _refused(cfg, fake_bwrap, "SANDBOX_RW_ROOT", "protected", SANDBOX_RW_BINDS=str(t / "inner"), SANDBOX_RW_ROOT=root,
                 SANDBOX_PROTECT=f)
    _refused(cfg, fake_bwrap, "SANDBOX_SLOT", "protected", SANDBOX_SLOT=str(t), SANDBOX_PROTECT=f)
    _accepted(cfg, fake_bwrap, SANDBOX_RO_BINDS=str(t / "inner"), SANDBOX_RO_ROOT=str(t / "inner"),
              SANDBOX_PROTECT=cfg.prot_file)   # control: the same root is fine when the protected file is elsewhere


def test_s6_a_root_or_entry_inside_a_protected_directory_is_refused(cfg, fake_bwrap, tmp_path):
    keys = tmp_path / "keylists"
    (keys / "a" / "b").mkdir(parents=True)
    for d in (keys, keys / "a", keys / "a" / "b"):   # the directory itself, and anything beneath it
        _refused(cfg, fake_bwrap, "SANDBOX_RO_ROOT", "protected", SANDBOX_RO_BINDS=str(d), SANDBOX_RO_ROOT=str(d),
                 SANDBOX_PROTECT=str(keys))
        _refused(cfg, fake_bwrap, "SANDBOX_RW_ROOT", "protected", SANDBOX_RW_BINDS=str(d), SANDBOX_RW_ROOT=str(d),
                 SANDBOX_PROTECT=str(keys))
    _refused(cfg, fake_bwrap, "SANDBOX_SLOT", "protected", SANDBOX_SLOT=str(keys / "a"), SANDBOX_PROTECT=str(keys))
    # a symlink does not hide it: a root that is a link to the protected directory resolves to it
    clean = tmp_path / "clean"
    clean.mkdir()
    os.symlink(str(keys), str(clean / "link"))
    _refused(cfg, fake_bwrap, "SANDBOX_RO_ROOT", "protected", SANDBOX_RO_BINDS=str(clean / "link"),
             SANDBOX_RO_ROOT=str(clean / "link"), SANDBOX_PROTECT=str(keys))


# ---------------------------------------------------------------- round 4 (S3): the box's own paths

def _run_user_dir():
    """A directory under /run (the invoking user's runtime directory when it exists; else any directory beneath /run)."""
    d = "/run/user/%d" % os.getuid()
    if os.path.isdir(d):
        return d
    for n in sorted(os.listdir("/run")):
        if os.path.isdir(os.path.join("/run", n)):
            return os.path.join("/run", n)
    pytest.fail("no directory under /run on this host to stand in for a runtime directory")


def _word_for(path):
    """The word the refusal carries: the home rule is checked first, so a path that is (or contains) some account's home
    directory is named by it, and every other box path by the box rule."""
    import pwd
    homes = {os.path.realpath(u.pw_dir) for u in pwd.getpwall() if u.pw_dir}
    path = os.path.realpath(path)
    return "home directory" if any(h == path or h.startswith(path.rstrip("/") + "/") for h in homes) else "provides"


def _a_subdir(root):
    for n in sorted(os.listdir(root)):
        p = os.path.join(root, n)
        if os.path.isdir(p) and not os.path.islink(p):
            return p
    pytest.fail("no real subdirectory under " + root)


def test_s3_slot_may_not_touch_what_the_box_provides(cfg, fake_bwrap):
    # (/home, /tmp and /var/tmp are in the refusal set too, but a slot there is named first by the home, binary or protected
    # rules in this fixture; the equality cell below binds the whole set.)
    for slot in ("/etc", _run_user_dir(), "/run", "/usr", _a_subdir("/usr"), "/proc", "/dev"):
        _refused(cfg, fake_bwrap, "SANDBOX_SLOT", _word_for(slot), SANDBOX_SLOT=slot)
    _refused(cfg, fake_bwrap, "SANDBOX_SLOT", _word_for(_a_subdir("/etc")), SANDBOX_SLOT=_a_subdir("/etc"))


def test_s3_roots_and_entries_may_not_touch_what_the_box_provides(cfg, fake_bwrap):
    etc_sub, share_sub = _a_subdir("/etc"), _a_subdir("/usr/share")
    for root, entry in (("/etc", etc_sub), ("/usr/share", share_sub), ("/usr/share", "/usr/share"), ("/usr", "/usr"),
                        ("/run", _run_user_dir()), ("/dev", "/dev"), ("/proc", "/proc")):
        _refused(cfg, fake_bwrap, "SANDBOX_RO_ROOT", _word_for(root), SANDBOX_RO_BINDS=entry, SANDBOX_RO_ROOT=root)
        _refused(cfg, fake_bwrap, "SANDBOX_RW_ROOT", _word_for(root), SANDBOX_RW_BINDS=entry, SANDBOX_RW_ROOT=root)


def test_s3_an_entry_alone_is_checked_when_its_root_is_clean(cfg, fake_bwrap, tmp_path):
    """The root is a clean tree; the ENTRY resolves (through a link) into the box's own /etc: refused as an entry."""
    clean = tmp_path / "clean"
    clean.mkdir()
    os.symlink(_a_subdir("/etc"), str(clean / "toetc"))
    _refused(cfg, fake_bwrap, "SANDBOX_RO_BINDS", "provides", SANDBOX_RO_BINDS=str(clean / "toetc"), SANDBOX_RO_ROOT=str(clean))
    # control: an ordinary clean entry in a clean root is accepted
    (clean / "ok").mkdir()
    _accepted(cfg, fake_bwrap, SANDBOX_RO_BINDS=str(clean / "ok"), SANDBOX_RO_ROOT=str(clean))


def _argv_dests(toks):
    """The in-box destination paths of an argv (up to the first '--')."""
    arity = {"--ro-bind-try": (2, 1), "--ro-bind": (2, 1), "--bind": (2, 1), "--bind-try": (2, 1), "--ro-bind-data": (2, 1),
             "--ro-bind-fd": (2, 1), "--bind-fd": (2, 1), "--tmpfs": (1, 0), "--proc": (1, 0), "--dev": (1, 0),
             "--remount-ro": (1, 0), "--dir": (1, 0), "--mqueue": (1, 0), "--symlink": (2, 1), "--size": (1, None),
             "--perms": (1, None), "--setenv": (2, None), "--unset": (1, None), "--hostname": (1, None),
             "--chdir": (1, None), "--uid": (1, None), "--gid": (1, None), "--cap-drop": (1, None),
             "--seccomp": (1, None)}
    out, i = [], 0
    while i < len(toks) and toks[i] != "--":
        t = toks[i]
        if t in arity:
            n, di = arity[t]
            if di is not None:
                out.append(toks[i + 1 + di])
            i += 1 + n
        else:
            assert t.startswith("--") and t[2:].replace("-", "").isalpha(), "unrecognised bwrap token %r" % t
            i += 1
    return out


def _inside(root, p):
    return p == root or p.startswith(root.rstrip("/") + "/")


def test_s3_the_refusal_set_is_the_set_of_paths_the_argv_provides(cfg, tmp_path, extra):
    """One source of truth. A dry run builds the argv and logs the box paths the refusal reads; every path the argv
    provides must lie in the refusal set, and every member of the set must be provided by the argv (the two named
    exceptions: a path the box deliberately leaves out, and the directory the bridge socket is created in). A bind added
    to the argv without the refusal, or the reverse, goes red."""
    d = tmp_path / "fakebin-lines"
    d.mkdir()
    fdir, out = str(d), str(tmp_path / "argv-lines")
    make_exe(str(d / "bwrap"), '#!/bin/sh\n' + FAKE_PROBE_PASS + 'printf "%s\\n" "$@" > "$FAKE_BWRAP_OUT"\nexit 99\n')
    r = cfg.run(exec_="true", PATH=fdir + ":/usr/bin:/bin", FAKE_BWRAP_OUT=out, SANDBOX_LOG=cfg.log,
                SANDBOX_RO_BINDS=extra.tools, SANDBOX_RO_ROOT=extra.base, SANDBOX_RW_BINDS=extra.proctor,
                SANDBOX_RW_ROOT=extra.runout)
    assert r.returncode == 99, r.stderr
    toks = open(out).read().split("\n")[:-1]
    dests = _argv_dests(toks)
    line = [l for l in open(cfg.log).read().splitlines() if l.startswith("wrapper-launch ")][0]
    f = dict(kv.split("=", 1) for kv in line.split()[1:])
    members = [m for m in f["box_paths"].split(":") if m]
    assert len(members) >= 10 and all(m.startswith("/") for m in members), members
    caller = {os.path.realpath(x) for x in (cfg.slot, extra.tools, extra.proctor, cfg.binary)}
    stray = [d for d in dests if d not in caller and not any(_inside(m, d) for m in members)]
    assert not stray, "the argv provides paths the refusal set does not cover: %r" % stray
    unprovided = [m for m in members if m not in dests]
    assert sorted(unprovided) == sorted(["/sys", os.path.realpath(cfg.tmpd)]), unprovided
    # the paths the task names are all there
    for need in ("/usr", "/etc", "/proc", "/dev", "/run", "/tmp", "/var/tmp", "/home", "/dev/shm"):
        assert need in members, need


# ---------------------------------------------------------------- round 4 (S4): /dev/shm is capped

@needs_box
def test_s4_dev_shm_has_its_own_capped_tmpfs_and_dev_itself_is_not_writable(cfg):
    r = cfg.run(exec_='dd if=/dev/zero of=/dev/shm/small bs=64k count=4 2>/dev/null && echo SMALL-OK; '
                      'dd if=/dev/zero of=/dev/shm/big bs=64k count=64 2>/dev/null && echo BIG-OK; '
                      '(touch /dev/x) 2>/dev/null && echo DEV-WRITABLE; echo done',
                SANDBOX_TEST_TMP_CAP=str(1 * MIB))
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == ["SMALL-OK", "done"], r.stdout   # 256 KiB fits, 4 MiB does not, /dev itself is read-only


# ---------------------------------------------------------------- round 5 (F1/L1, L3): the checked string is the sent string

def _refused_with_nothing_sent(outer, raw_stub, allow, raw, want=403):
    stub = raw_stub()
    o = outer(stub, allow=allow)
    s = o.connect()
    s.sendall(raw)
    status, _, _ = read_response(s)
    assert status == want, (raw, status)
    assert at_eof(s), raw
    assert stub.bytes_seen() == b"", "the upstream received bytes of a refused request: %r" % raw


# the exact request lines of the colleague review's table (F1), plus the same class
FRAGMENT_LINES = [
    b"POST /v1/messages#/../../api/pull HTTP/1.1",
    b"POST /api/chat#/../../x HTTP/1.1",
    b"POST /v1/messages?a=1#b HTTP/1.1",
    b"POST /v1/messages# HTTP/1.1",
    b"POST /api/x#y HTTP/1.1",
]


@pytest.mark.parametrize("line", FRAGMENT_LINES, ids=[l.decode() for l in FRAGMENT_LINES])
def test_peer_f1_a_request_target_with_a_fragment_is_refused_and_nothing_is_sent(outer, raw_stub, line):
    _refused_with_nothing_sent(outer, raw_stub, ALLOW, line + b"\r\nHost: model\r\nContent-Length: 2\r\n\r\n{}")


@pytest.mark.parametrize("line", [b"OPTIONS * HTTP/1.1", b"POST model:443 HTTP/1.1",
                                  b"POST http://model/v1/messages HTTP/1.1", b"POST v1/messages HTTP/1.1"],
                         ids=["asterisk-form", "authority-form", "absolute-form", "no-leading-slash"])
def test_peer_l1_only_origin_form_targets_are_matched(outer, raw_stub, line):
    _refused_with_nothing_sent(outer, raw_stub, "POST /*, OPTIONS /*", line + b"\r\nHost: model\r\n\r\n")


def test_peer_f1_the_deny_log_line_keeps_its_own_fragment_split(outer, http_stub, tmp_path):
    stub = http_stub()
    log = str(tmp_path / "frag.log")
    o = outer(stub, allow=ALLOW, log=log)
    s = o.connect()
    s.sendall(b"POST /v1/messages?q=SECRET#frag-SECRET HTTP/1.1\r\nHost: model\r\n\r\n")
    assert read_response(s)[0] == 403
    time.sleep(0.5)
    text = open(log).read()
    deny = [l for l in text.splitlines() if l.startswith("fwd-deny ")]
    assert len(deny) == 1 and deny[0].startswith("fwd-deny method=POST path=/v1/messages status=403 "), text
    assert " kind=rule reason=fragment " in deny[0], deny
    assert "SECRET" not in text and "frag-" not in text and "#" not in text    # the fragment's content (the word "fragment" is the reason)


def test_peer_f1_a_target_without_a_fragment_is_still_forwarded_byte_for_byte(outer, raw_stub):
    """Positive control: the fragment refusal must not refuse an ordinary query (and a '%23' stays a plain escaped
    character that decodes to a path the list does not hold)."""
    stub = raw_stub()
    o = outer(stub, allow=ALLOW)
    s = o.connect()
    raw = b"POST /v1/messages?a=1&b=2 HTTP/1.1\r\nHost: model\r\nContent-Length: 2\r\n\r\n{}"
    s.sendall(raw)
    assert stub.bytes_seen() == raw
    s.close()


# L3 (a): a prefix rule matches from the START of the path
@pytest.mark.parametrize("target", ["/zzz/api/x", "/x/api/y", "/a/api/", "/v1/api/chat"])
def test_peer_l3a_a_prefix_rule_does_not_match_a_path_that_merely_contains_the_prefix(outer, raw_stub, target):
    _refused_with_nothing_sent(outer, raw_stub, ALLOW, req("POST", target, body=b"{}"))


def test_peer_l3a_the_prefix_rule_still_matches_from_the_start(outer, http_stub):
    stub = http_stub()
    o = outer(stub, allow=ALLOW)
    s = o.connect()
    s.sendall(req("POST", "/api/chat", body=b"{}"))
    assert read_response(s)[0] == 200


# L3 (b): an empty path segment is refused (a prefix rule is matched, so only the segment rule can refuse these)
@pytest.mark.parametrize("target", ["/api//x", "/api/a//b", "/api///", "/api/a//"])
def test_peer_l3b_an_empty_path_segment_is_refused(outer, raw_stub, target):
    _refused_with_nothing_sent(outer, raw_stub, ALLOW, req("POST", target, body=b"{}"))


def test_peer_l3b_a_trailing_slash_is_not_an_empty_segment(outer, http_stub):
    stub = http_stub()
    o = outer(stub, allow=ALLOW)
    s = o.connect()
    s.sendall(req("POST", "/api/a/", body=b"{}"))
    assert read_response(s)[0] == 200


# L3 (c): the Upgrade header and the Connection token are two independent checks, each with its own cells
def test_peer_l3c_an_upgrade_header_alone_is_refused(outer, raw_stub):
    _refused_with_nothing_sent(outer, raw_stub, ALLOW, b"GET /v1/models HTTP/1.1\r\nHost: m\r\nUpgrade: websocket\r\n\r\n")


@pytest.mark.parametrize("value", [b"upgrade", b"Upgrade", b"UPGRADE", b"keep-alive, Upgrade", b"keep-alive ,upgrade, x",
                                   b"close,UpGrade"])
def test_peer_l3c_a_connection_upgrade_token_alone_is_refused(outer, raw_stub, value):
    _refused_with_nothing_sent(outer, raw_stub, ALLOW, b"GET /v1/models HTTP/1.1\r\nHost: m\r\nConnection: " + value + b"\r\n\r\n")


def test_peer_l3c_other_connection_tokens_still_pass(outer, http_stub):
    stub = http_stub()
    o = outer(stub, allow=ALLOW)
    s = o.connect()
    s.sendall(b"GET /v1/models HTTP/1.1\r\nHost: m\r\nConnection: keep-alive\r\n\r\n")
    assert read_response(s)[0] == 200
    s.sendall(b"GET /v1/models HTTP/1.1\r\nHost: m\r\nConnection: x-upgrade-not, close\r\n\r\n")
    assert read_response(s)[0] == 200


# ---------------------------------------------------------------- round 5 (A, A2): forward nothing until the whole request validates

def _refuse_lines(log):
    time.sleep(0.5)
    return [l for l in open(log).read().splitlines() if l.startswith("fwd-refuse ")]


# framing refusals AFTER a head that the list allows: the upstream must receive NOTHING, not even the head
FRAMING_AFTER_ALLOWED_HEAD = SMUGGLE + [
    ("a valid chunk, then a bad size line", b"5\r\nhello\r\nZZ\r\n0\r\n\r\n", [b"hello"]),
    ("a chunk whose data is not followed by CRLF", b"5\r\nhelloXX0\r\n\r\n", [b"hello"]),
    ("a chunk size that is not hex", b"zz\r\nhello\r\n0\r\n\r\n", [b"zz"]),
]


@pytest.mark.parametrize("name,body,banned", FRAMING_AFTER_ALLOWED_HEAD, ids=[x[0] for x in FRAMING_AFTER_ALLOWED_HEAD])
def test_peer_a_an_allowed_head_with_bad_chunk_framing_sends_nothing_upstream(outer, raw_stub, name, body, banned):
    stub = raw_stub()
    o = outer(stub, allow=ALLOW)
    s = o.connect()
    s.sendall(CHUNK_HEAD + body)
    status, _, _ = read_response(s)
    assert status == 400, (name, status)
    assert at_eof(s), name
    assert stub.bytes_seen() == b"", "the upstream received bytes of a refused request: %r" % stub.bytes_seen()


def test_peer_a_a_client_that_hangs_up_inside_a_body_sends_nothing_upstream(outer, raw_stub):
    stub = raw_stub()
    o = outer(stub, allow=ALLOW)
    s = o.connect()
    s.sendall(b"POST /v1/messages HTTP/1.1\r\nHost: m\r\nContent-Length: 100\r\n\r\n" + b"x" * 10)
    s.shutdown(socket.SHUT_WR)
    assert stub.bytes_seen() == b""
    s.close()


def test_peer_a_a_chunked_client_that_hangs_up_inside_a_chunk_sends_nothing_upstream(outer, raw_stub):
    stub = raw_stub()
    o = outer(stub, allow=ALLOW)
    s = o.connect()
    s.sendall(CHUNK_HEAD + b"a\r\n12345")
    s.shutdown(socket.SHUT_WR)
    assert stub.bytes_seen() == b""
    s.close()


def test_peer_a_an_earlier_valid_request_is_forwarded_and_the_refused_one_after_it_is_not(outer, raw_stub):
    stub = raw_stub()
    o = outer(stub, allow=ALLOW)
    s = o.connect()
    first = req("POST", "/v1/messages", body=b'{"a":1}')
    s.sendall(first + CHUNK_HEAD + b"5\r\nhello\r\nZZ\r\n0\r\n\r\n")
    assert stub.bytes_seen() == first
    s.close()


def test_peer_a_a_valid_request_is_forwarded_whole_after_validation(outer, raw_stub):
    """Positive control: the buffering must not lose or reorder a valid body (Content-Length and chunked)."""
    stub = raw_stub()
    o = outer(stub, allow=ALLOW)
    s = o.connect()
    a = req("POST", "/v1/messages", body=b"y" * 200000)
    b = CHUNK_HEAD + b"5\r\nhello\r\n6\r\n world\r\n0\r\n\r\n"
    s.sendall(a + b)
    assert stub.bytes_seen() == a + b
    s.close()


def test_peer_a_a_refusal_after_the_body_was_read_closes_and_logs_one_line(outer, raw_stub, tmp_path):
    stub = raw_stub()
    log = str(tmp_path / "refuse.log")
    o = outer(stub, allow=ALLOW, log=log)
    s = o.connect()
    body = b"5\r\nhello\r\nZZ\r\n0\r\n\r\n"
    s.sendall(CHUNK_HEAD + body)
    status, _, _ = read_response(s)
    assert status == 400 and at_eof(s)
    lines = _refuse_lines(log)
    assert len(lines) == 1, lines
    m = re.fullmatch(r"fwd-refuse method=POST path=/v1/messages status=400 bytes_read=(\d+) kind=framing reason=chunk-size "
                     r"detail=(.+)", lines[0])
    assert m, lines[0]
    # the head, the one good chunk (size line, data, CRLF) and the bad size line itself (a complete line, consumed)
    assert int(m.group(1)) == len(CHUNK_HEAD) + len(b"5\r\nhello\r\n") + len(b"ZZ\r\n"), m.group(1)
    assert "chunk" in m.group(2)
    assert stub.bytes_seen() == b""


# ---- A2: caps on the trusted side (small test values)

@pytest.mark.parametrize("kind", ["length", "chunked"])
def test_peer_a2_a_request_over_the_per_request_cap_is_413_and_sends_nothing(outer, raw_stub, tmp_path, kind):
    stub = raw_stub()
    log = str(tmp_path / "cap.log")
    o = outer(stub, allow=ALLOW, log=log, max_request=4096)
    s = o.connect()
    if kind == "length":
        raw = req("POST", "/v1/messages", body=b"x" * 10000)
    else:
        raw = CHUNK_HEAD + b"bb8\r\n" + b"x" * 3000 + b"\r\nbb8\r\n" + b"x" * 3000 + b"\r\n0\r\n\r\n"
    s.sendall(raw)
    status, _, _ = read_response(s)
    assert status == 413, status
    assert at_eof(s)
    assert stub.bytes_seen() == b""
    lines = _refuse_lines(log)
    assert len(lines) == 1 and " status=413 " in lines[0] and "request cap" in lines[0], lines


def test_peer_a2_the_per_request_cap_is_exact(outer, http_stub, raw_stub):
    """A request of exactly the cap passes; one byte more is 413 (the head counts toward the cap)."""
    cap = 4096
    base = req("POST", "/v1/messages", body=b"x" * 1000)
    pad = cap - len(base)
    exact = req("POST", "/v1/messages", body=b"x" * (1000 + pad))
    assert len(exact) == cap
    over = req("POST", "/v1/messages", body=b"x" * (1000 + pad + 1))
    stub = http_stub()
    o = outer(stub, allow=ALLOW, max_request=cap)
    s = o.connect()
    s.sendall(exact)
    assert read_response(s)[0] == 200
    s2 = o.connect()
    s2.sendall(over)
    assert read_response(s2)[0] == 413
    assert [(m, t) for m, t, _ in stub.records] == [("POST", "/v1/messages")]


def test_peer_a2_the_total_cap_counts_every_connections_buffered_bytes(outer, raw_stub, tmp_path):
    """Two connections, each under the per-request cap, over the total cap together: the second is the named 413."""
    stub = raw_stub()
    log = str(tmp_path / "total.log")
    o = outer(stub, allow=ALLOW, log=log, max_request=8192, max_total=12000)
    n = 7000
    full = req("POST", "/v1/messages", body=b"x" * n)
    first = o.connect()
    first.sendall(full[:-100])          # this connection now holds ~7000 buffered bytes, waiting for the rest
    time.sleep(0.4)
    second = o.connect()
    second.sendall(full)
    status, _, _ = read_response(second)
    assert status == 413, status
    assert at_eof(second)
    lines = _refuse_lines(log)
    assert len(lines) == 1 and " status=413 " in lines[0] and "total cap" in lines[0], lines
    assert stub.bytes_seen() == b""     # neither request was forwarded: the first is still incomplete
    first.sendall(full[-100:])          # the first completes and is forwarded, once the second released nothing it held
    assert stub.bytes_seen() == full
    first.close()


def test_peer_a2_buffered_bytes_are_released_so_sequential_requests_each_fit_the_total(outer, http_stub):
    stub = http_stub()
    o = outer(stub, allow=ALLOW, max_request=8192, max_total=12000)
    for _ in range(4):
        s = o.connect()
        s.sendall(req("POST", "/v1/messages", body=b"x" * 7000))
        assert read_response(s)[0] == 200
        s.close()
        time.sleep(0.1)


def test_peer_a2_a_refused_request_releases_what_it_had_buffered(outer, http_stub):
    stub = http_stub()
    o = outer(stub, allow=ALLOW, max_request=8192, max_total=12000)
    for _ in range(3):
        s = o.connect()
        s.sendall(CHUNK_HEAD + b"1b58\r\n" + b"x" * 7000 + b"\r\nZZ\r\n")   # 7000 buffered, then a bad size line
        assert read_response(s)[0] == 400
        s.close()
    s = o.connect()
    s.sendall(req("POST", "/v1/messages", body=b"x" * 7000))
    assert read_response(s)[0] == 200


def test_peer_a2_connections_past_the_cap_get_503_and_a_log_line(outer, http_stub, tmp_path):
    stub = http_stub()
    log = str(tmp_path / "conns.log")
    o = outer(stub, allow=ALLOW, log=log, max_conns=2)
    held = [o.connect(), o.connect()]
    time.sleep(0.4)
    third = o.connect()
    third.sendall(req("GET", "/v1/models"))
    status, _, _ = read_response(third)
    assert status == 503, status
    assert at_eof(third)
    lines = _refuse_lines(log)
    assert len(lines) == 1 and " status=503 " in lines[0] and "connection cap" in lines[0], lines
    assert stub.seen() == []
    # a slot comes back when a held connection ends
    held[0].close()
    time.sleep(0.6)
    again = o.connect()
    again.sendall(req("GET", "/v1/models"))
    assert read_response(again)[0] == 200
    held[1].close()


def test_peer_a2_learn_mode_records_the_maxima(outer, http_stub, tmp_path):
    stub = http_stub()
    log = str(tmp_path / "learn-max.log")
    o = outer(stub, learn=True, log=log)
    small = req("POST", "/v1/messages", body=b"x" * 500)
    big = req("POST", "/v1/messages", body=b"x" * 5000)
    s = o.connect()
    s.sendall(small)
    assert read_response(s)[0] == 200
    s.sendall(big)
    assert read_response(s)[0] == 200
    s2 = o.connect()
    s2.sendall(small)
    assert read_response(s2)[0] == 200
    time.sleep(0.5)
    maxes = [l for l in open(log).read().splitlines() if l.startswith("fwd-learn-max ")]
    assert maxes, "no maxima line"
    f = dict(kv.split("=") for kv in maxes[-1].split()[1:])
    assert int(f["request_bytes"]) == len(big), (f, len(big))
    assert int(f["connections"]) == 2, f
    assert int(f["total_buffered"]) == len(big), f
    assert "SECRET" not in open(log).read()


def test_peer_a2_enforce_mode_does_not_record_maxima(outer, http_stub, tmp_path):
    stub = http_stub()
    log = str(tmp_path / "enf.log")
    o = outer(stub, allow=ALLOW, log=log)
    s = o.connect()
    s.sendall(req("POST", "/v1/messages", body=b"x" * 500))
    assert read_response(s)[0] == 200
    s.close()
    time.sleep(0.6)   # the connection's own log line is written when it ends
    text = open(log).read()
    assert "fwd-conn " in text and "fwd-learn-max" not in text


def test_peer_a2_many_small_chunks_that_add_up_past_the_cap_are_413(outer, raw_stub):
    """No single chunk is over the cap; only the running total is."""
    stub = raw_stub()
    o = outer(stub, allow=ALLOW, max_request=4096)
    s = o.connect()
    s.sendall(CHUNK_HEAD + b"".join(b"64\r\n" + b"x" * 100 + b"\r\n" for _ in range(60)) + b"0\r\n\r\n")
    status, _, _ = read_response(s)
    assert status == 413, status
    assert at_eof(s)
    assert stub.bytes_seen() == b""


def test_peer_a2_a_declared_content_length_over_the_cap_is_refused_before_its_body_is_sent(outer, raw_stub):
    stub = raw_stub()
    o = outer(stub, allow=ALLOW, max_request=4096)
    s = o.connect()
    s.sendall(b"POST /v1/messages HTTP/1.1\r\nHost: m\r\nContent-Length: 1000000\r\n\r\n")   # the body never comes
    status, _, _ = read_response(s)
    assert status == 413, status
    assert stub.bytes_seen() == b""


def test_peer_a2_a_declared_chunk_size_over_the_cap_is_refused_before_its_data_is_sent(outer, raw_stub):
    stub = raw_stub()
    o = outer(stub, allow=ALLOW, max_request=4096)
    s = o.connect()
    s.sendall(CHUNK_HEAD + b"100000\r\n")   # a 1 MiB chunk is announced; none of it comes
    status, _, _ = read_response(s)
    assert status == 413, status
    assert stub.bytes_seen() == b""


# ---------------------------------------------------------------- round 5 (B): HOME must equal the slot

def test_peer_b_home_unset_or_empty_is_a_named_refusal(cfg, fake_bwrap):
    _refused(cfg, fake_bwrap, "HOME", "not set", drop=("HOME",))
    _refused(cfg, fake_bwrap, "HOME", "not set", HOME="")


def test_peer_b_home_a_different_directory_is_a_named_refusal(cfg, fake_bwrap, tmp_path):
    other = tmp_path / "elsewhere"
    other.mkdir()
    _refused(cfg, fake_bwrap, "HOME", "slot", HOME=str(other))
    _refused(cfg, fake_bwrap, "HOME", "slot", HOME=os.path.join(cfg.slot, "work"))   # inside the slot is not the slot
    _refused(cfg, fake_bwrap, "HOME", "slot", HOME=os.path.dirname(cfg.slot))        # nor is its parent
    _refused(cfg, fake_bwrap, "HOME", "slot", HOME=str(tmp_path / "no-such-dir"))    # nor a path that does not exist


def test_peer_b_home_that_resolves_to_the_slot_passes(cfg, fake_bwrap, tmp_path):
    link = tmp_path / "slot-link"
    os.symlink(cfg.slot, link)
    _accepted(cfg, fake_bwrap, HOME=str(link))                                       # a symlink to the slot: same realpath
    _accepted(cfg, fake_bwrap, HOME=cfg.slot + "/")                                  # a trailing slash
    _accepted(cfg, fake_bwrap, HOME=os.path.join(cfg.slot, "work", ".."))            # a dot-dot that lands on the slot
    _accepted(cfg, fake_bwrap)                                                       # the plain control


@needs_box
def test_peer_b_the_box_receives_home_exactly_as_the_caller_passed_it(cfg):
    r = cfg.run(exec_='printf "%s" "$HOME"', HOME=cfg.slot + "/")
    assert r.returncode == 0, r.stderr
    assert r.stdout == cfg.slot + "/"


# ---------------------------------------------------------------- round 5 (L2, F3): Linux-only box, platform-free framing

def _load_forwarder():
    import importlib.util
    spec = importlib.util.spec_from_file_location("sandbox_forward_alive_under_test", FWD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_peer_l2_alive_is_true_for_this_process_and_false_for_a_dead_pid():
    mod = _load_forwarder()
    assert mod.alive(os.getpid()) is True
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    assert mod.alive(p.pid) is False


def test_peer_l2_alive_signals_zero_and_does_not_read_proc(monkeypatch):
    """The forwarder's exit check must work where there is no /proc (a Mac seat): it sends signal 0, nothing else."""
    mod = _load_forwarder()
    calls = []
    real_kill, real_open = os.kill, open

    def spy_kill(pid, sig):
        calls.append((pid, sig))
        return real_kill(pid, sig)

    def no_proc(path, *a, **k):
        if str(path).startswith("/proc"):
            raise OSError("no /proc here")
        return real_open(path, *a, **k)

    monkeypatch.setattr(mod.os, "kill", spy_kill)
    monkeypatch.setattr("builtins.open", no_proc)
    assert mod.alive(os.getpid()) is True
    assert calls == [(os.getpid(), 0)], calls


def test_peer_l2_a_permission_error_means_alive_and_a_lookup_error_means_dead(monkeypatch):
    mod = _load_forwarder()

    def deny(pid, sig):
        raise PermissionError

    def gone(pid, sig):
        raise ProcessLookupError

    monkeypatch.setattr(mod.os, "kill", deny)
    assert mod.alive(1) is True        # the process exists, it is only not ours to signal
    monkeypatch.setattr(mod.os, "kill", gone)
    assert mod.alive(1) is False


def test_peer_f3_the_named_skip_says_what_the_box_cells_need():
    """Every box cell skips with this reason when the host cannot run it; it must name all three requirements."""
    for need in ("Linux", "bash 4", "bwrap"):
        assert need in NEEDS_BOX_REASON, (need, NEEDS_BOX_REASON)


# ---------------------------------------------------------------- round 5 (C1, C2): what a run's launch line records

def _launch_fields(cfg, fake_bwrap, **kw):
    """Run to the (fake) bwrap and return (the wrapper-launch line's key=value fields, the wrapper's stderr)."""
    r, out = _launch(cfg, fake_bwrap, **kw)
    assert r.returncode == 99, (r.returncode, r.stderr)
    line = [l for l in open(cfg.log).read().splitlines() if l.startswith("wrapper-launch ")]
    assert len(line) == 1, line
    os.unlink(out)
    _wait_clean(cfg)
    return dict(kv.split("=", 1) for kv in line[0].split()[1:]), r.stderr


def test_peer_c1_the_launch_line_records_the_model_mode_and_the_allow_list_entry_count(cfg, fake_bwrap):
    f, _ = _launch_fields(cfg, fake_bwrap)                                       # the default env lists two entries
    assert (f["model_mode"], f["model_allow_entries"]) == ("allow", "2"), f
    f, _ = _launch_fields(cfg, fake_bwrap, SANDBOX_MODEL_ALLOW="POST /v1/messages, GET /v1/models, POST /api/*")
    assert (f["model_mode"], f["model_allow_entries"]) == ("allow", "3"), f
    f, _ = _launch_fields(cfg, fake_bwrap, SANDBOX_MODEL_LEARN="1", drop=("SANDBOX_MODEL_ALLOW",))
    assert (f["model_mode"], f["model_allow_entries"]) == ("learn", "0"), f      # learn mode: nothing is listed


DEFAULT_CAPS = {"cap_tmp": str(2 << 30), "cap_home_run": str(64 << 20), "cap_request": str(32 << 20),
                "cap_total": str(64 << 20), "cap_conns": "4", "cap_read_idle_s": "120", "cap_tasks": "1024", "cap_memory": str(4 << 30)}
TEST_CAPS = {"SANDBOX_TEST_TMP_CAP": "1111111", "SANDBOX_TEST_HOME_RUN_CAP": "2222222",
             "SANDBOX_TEST_MAX_REQUEST": "3333333", "SANDBOX_TEST_MAX_TOTAL": "4444444", "SANDBOX_TEST_MAX_CONNS": "7",
             "SANDBOX_TEST_READ_IDLE_S": "9", "SANDBOX_TEST_TASKS_MAX": "5555", "SANDBOX_TEST_MEMORY_MAX": "268435456"}
TEST_CAPS_LOGGED = {"cap_tmp": "1111111", "cap_home_run": "2222222", "cap_request": "3333333", "cap_total": "4444444",
                    "cap_conns": "7", "cap_read_idle_s": "9", "cap_tasks": "5555", "cap_memory": "268435456"}


def test_peer_c2_in_test_mode_the_launch_line_logs_every_effective_cap_and_the_marker_is_printed(cfg, fake_bwrap):
    f, err = _launch_fields(cfg, fake_bwrap, **TEST_CAPS)
    assert f["test_mode"] == "1", f
    for k, v in TEST_CAPS_LOGGED.items():
        assert f[k] == v, (k, f)
    marker = [l for l in err.splitlines() if "TEST MODE" in l]
    assert len(marker) == 1 and marker[0].startswith("student-sandbox: "), err


def test_peer_c2_outside_test_mode_the_defaults_apply_the_knobs_are_inert_and_there_is_no_marker(cfg, fake_bwrap):
    f, err = _launch_fields(cfg, fake_bwrap, test=False, **TEST_CAPS)
    assert f["test_mode"] == "0", f
    for k, v in DEFAULT_CAPS.items():
        assert f[k] == v, (k, f)
    assert "TEST MODE" not in err, err


def test_peer_c2_a_malformed_test_cap_is_refused(cfg, fake_bwrap):
    for name in ("SANDBOX_TEST_MAX_REQUEST", "SANDBOX_TEST_MAX_TOTAL", "SANDBOX_TEST_MAX_CONNS", "SANDBOX_TEST_READ_IDLE_S",
                 "SANDBOX_TEST_TASKS_MAX",
                 "SANDBOX_TEST_MEMORY_MAX"):
        for bad in ("0", "-1", "ten", "1.5", "007x"):
            assert_refused(cfg, fake_bwrap, name, **{name: bad})


# ---------------------------------------------------------------- round 5 (C): process and memory caps on the box itself
# The box runs in its own systemd user scope (TasksMax, MemoryMax, MemorySwapMax=0), entered by the wrapper's own
# exec, so the cap covers the box alone: the host uid, the host-side forwarder and the feeder are outside it. Limits are
# SMALL here; the defaults are provisional until the pilot has measured a real run.

FORKER = '''import os, sys, time
# Bounded forker (never a bomb): up to 300 attempts, each child sleeps; counts successes and failures, then waits.
ok = fail = 0
kids = []
for _ in range(300):
    try:
        pid = os.fork()
    except OSError:
        fail += 1
        continue
    if pid == 0:
        time.sleep(30)
        os._exit(0)
    ok += 1
    kids.append(pid)
print("box: forked_ok=%d fork_failed=%d" % (ok, fail), flush=True)
time.sleep(float(sys.argv[1]))
for p in kids:
    try:
        os.kill(p, 9)
    except OSError:
        pass
'''

HOG = '''import os, sys, time, http.client
# argv: bridge port, MiB for the hog child to allocate AND touch. The parent reports how the child ended, then makes one
# request through the bridge (the host-side forwarder must have survived the hog).
port, mib = int(sys.argv[1]), int(sys.argv[2])
pid = os.fork()
if pid == 0:
    m = bytearray(mib << 20)
    for i in range(0, len(m), 4096):
        m[i] = 1
    time.sleep(1)
    os._exit(0)
_, st = os.waitpid(pid, 0)
print("hog: signaled=%s sig=%s" % (os.WIFSIGNALED(st), os.WTERMSIG(st) if os.WIFSIGNALED(st) else 0), flush=True)
try:
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    c.request("GET", "/ping")
    r = c.getresponse()
    r.read()
    print("bridge: %d" % r.status, flush=True)
except Exception as e:
    print("bridge: FAILED %s" % type(e).__name__, flush=True)
'''


def _write_in_slot(cfg, name, text):
    p = os.path.join(cfg.slot, name)
    with open(p, "w") as f:
        f.write(text)
    return p


def _uid_threads():
    """The invoking uid's live thread count right now (counts only), so a reading about a per-uid limit can be placed."""
    n = 0
    for d in os.listdir("/proc"):
        if d.isdigit():
            try:
                if os.stat("/proc/%s" % d).st_uid == os.getuid():
                    n += len(os.listdir("/proc/%s/task" % d))
            except OSError:
                pass
    return n


def _cgroup_of(pid):
    return open("/proc/%d/cgroup" % pid).read().strip().split(":", 2)[2]


def _cg(path, name):
    return open("/sys/fs/cgroup" + path + "/" + name).read().strip()


@needs_box
def test_peer_c_a_fork_bomb_in_the_box_stops_at_the_cap_and_the_host_can_still_fork(cfg):
    """Both directions: the box hits EAGAIN at its own cap, and while it sits at that cap the host uid forks freely."""
    script = _write_in_slot(cfg, "forker.py", FORKER)
    p = subprocess.Popen(["/bin/bash", WRAPPER], env=cfg.env(exec_="%s -I %s 6" % (PY, shlex.quote(script)),
                         SANDBOX_TEST_TASKS_MAX="40"), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        line = p.stdout.readline()
        m = re.fullmatch(r"box: forked_ok=(\d+) fork_failed=(\d+)\n", line)
        assert m, (line, p.stderr.read() if p.poll() is not None else "")
        ok, failed = int(m.group(1)), int(m.group(2))
        # the cap is 40 tasks for the whole box (its own helpers included): some forks succeed, the rest fail
        assert 0 < ok < 40 and failed >= 300 - 40, (ok, failed)
        # the box is at its cap right now; the host uid is not
        threads = _uid_threads()
        kids = [subprocess.Popen(["/bin/sleep", "4"]) for _ in range(25)]
        assert all(k.poll() is None for k in kids), "the host uid could not fork while the box sat at its cap (uid threads=%d)" % threads
        for k in kids:
            k.kill()
            k.wait()
    finally:
        p.kill()
        p.wait()


@needs_box
def test_peer_c_with_a_generous_cap_the_same_forker_is_not_stopped(cfg):
    """Control: the cap is what stops it, not the box."""
    script = _write_in_slot(cfg, "forker.py", FORKER)
    r = cfg.run(exec_="%s -I %s 0.2" % (PY, shlex.quote(script)), SANDBOX_TEST_TASKS_MAX="4000")
    assert r.returncode == 0, r.stderr
    m = re.search(r"box: forked_ok=(\d+) fork_failed=(\d+)", r.stdout)
    assert m and (int(m.group(1)), int(m.group(2))) == (300, 0), r.stdout


@needs_box
def test_peer_c_a_memory_hog_in_the_box_is_killed_and_the_host_side_forwarder_survives(cfg, http_stub):
    stub = http_stub()
    cfg.model_port = stub.port
    script = _write_in_slot(cfg, "hog.py", HOG)
    r = cfg.run(exec_="%s -I %s %d 300" % (PY, shlex.quote(script), stub.port), SANDBOX_TEST_MEMORY_MAX=str(64 << 20))
    assert r.returncode == 0, r.stderr
    assert r.stdout.split("\n")[:2] == ["hog: signaled=True sig=9", "bridge: 200"], r.stdout


@needs_box
def test_peer_c_the_same_allocation_under_a_generous_cap_is_not_killed(cfg, http_stub):
    """Control: 300 MiB survives a 2 GiB cap, so the kill above is the cap's doing."""
    stub = http_stub()
    cfg.model_port = stub.port
    script = _write_in_slot(cfg, "hog.py", HOG)
    r = cfg.run(exec_="%s -I %s %d 300" % (PY, shlex.quote(script), stub.port), SANDBOX_TEST_MEMORY_MAX=str(2 << 30))
    assert r.returncode == 0, r.stderr
    assert r.stdout.split("\n")[:2] == ["hog: signaled=False sig=0", "bridge: 200"], r.stdout


@needs_box
def test_peer_c_the_box_has_its_own_scope_with_the_configured_caps_and_the_forwarder_is_outside_it(cfg):
    mem = 192 << 20
    p = subprocess.Popen(["/bin/bash", WRAPPER], env=cfg.env(exec_="sleep 6", SANDBOX_TEST_TASKS_MAX="123",
                         SANDBOX_TEST_MEMORY_MAX=str(mem)), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        box = None
        end = time.time() + 10
        while time.time() < end:
            try:
                box = _cgroup_of(p.pid)
            except OSError:
                box = None
            if box and box.endswith(".scope") and box != _cgroup_of(os.getpid()):
                break
            time.sleep(0.05)
        assert box and box != _cgroup_of(os.getpid()), "the box did not move into a scope of its own: %r" % box
        # not the runner's cgroup (where a memory limit set around the whole run, e.g. memrun's, lives): its own
        assert (_cg(box, "pids.max"), _cg(box, "memory.max"), _cg(box, "memory.swap.max")) == ("123", str(mem), "0")
        # an OOM kill takes the hog alone: systemd's default (stop) would SIGTERM the whole box
        env = dict(os.environ, XDG_RUNTIME_DIR=os.environ.get("XDG_RUNTIME_DIR") or "/run/user/%d" % os.getuid())
        pol = subprocess.run(["systemctl", "--user", "show", "-p", "OOMPolicy", os.path.basename(box)], env=env,
                             capture_output=True, text=True)
        assert pol.stdout.strip() == "OOMPolicy=continue", (pol.stdout, pol.stderr)
        # the host-side forwarder was started before the exec and stays where it was
        fw = [pid for pid in procs_with(cfg.tmpd) if b"sandbox-forward.py" in open("/proc/%d/cmdline" % pid, "rb").read()
              and b"outer" in open("/proc/%d/cmdline" % pid, "rb").read()]
        assert len(fw) == 1, fw
        assert _cgroup_of(fw[0]) != box, "the host-side forwarder is inside the box's capped scope"
    finally:
        p.kill()
        p.wait()


def test_peer_c_without_a_user_scope_the_wrapper_refuses_before_anything_starts(cfg, fake_bwrap):
    fdir, _ = fake_bwrap
    make_exe(os.path.join(fdir, "systemd-run"), "#!/bin/sh\nexit 1\n")   # a host whose user manager cannot start the scope
    assert_refused(cfg, fake_bwrap, "systemd-run")


# ---------------------------------------------------------------- round 5 (C5): the capability boundary is explicit

def test_peer_c5_the_argv_drops_every_capability_explicitly(cfg, fake_bwrap):
    """The boundary must not rest on bwrap's default. The fake bwrap records its argv, so this cell reads what the
    wrapper asked for, whatever the real bwrap would do by default."""
    fdir, out = fake_bwrap
    r = cfg.run(exec_="true", PATH=fdir + ":/usr/bin:/bin", FAKE_BWRAP_OUT=out)
    assert r.returncode == 99, r.stderr
    toks = open(out).read().strip().partition(" ")[2].split()
    assert "--cap-drop" in toks, toks
    assert toks[toks.index("--cap-drop") + 1] == "ALL", toks
    _wait_clean(cfg)


@needs_box
def test_peer_c5_inside_the_real_box_every_capability_set_reads_zero(cfg):
    """Measured through the REAL wrapper. Note what this cell does not show: the sets are already zero by bwrap's default
    in an unprivileged user namespace, so dropping the explicit --cap-drop leaves this cell green; the argv cell above
    is the one that reddens."""
    r = cfg.run(exec_="grep -E '^Cap(Inh|Prm|Eff|Bnd|Amb):' /proc/self/status")
    assert r.returncode == 0, r.stderr
    sets = dict(l.split(":\t") for l in r.stdout.strip().splitlines())
    assert sorted(sets) == ["CapAmb", "CapBnd", "CapEff", "CapInh", "CapPrm"], sets
    assert all(int(v, 16) == 0 for v in sets.values()), sets


def _chunked_of_exact_size(total):
    """A chunked request (CHUNK_HEAD, one chunk, the last chunk) whose whole length is exactly `total` bytes."""
    for size in range(1, total):
        raw = CHUNK_HEAD + b"%x\r\n" % size + b"x" * size + b"\r\n0\r\n\r\n"
        if len(raw) == total:
            return raw
    raise AssertionError("no chunked request of %d bytes" % total)


def test_peer_a2_the_per_request_cap_is_exact_for_a_chunked_request_too(outer, http_stub, raw_stub):
    """The overflow here is a few bytes of framing (the last chunk's size line and CRLF), which no per-chunk size check
    sees: only the running count of the request's own bytes refuses it."""
    cap = 2048
    exact, over = _chunked_of_exact_size(cap), _chunked_of_exact_size(cap + 1)
    stub = http_stub()
    o = outer(stub, allow=ALLOW, max_request=cap)
    s = o.connect()
    s.sendall(exact)
    assert read_response(s)[0] == 200
    s.close()
    raw = raw_stub()
    o2 = outer(raw, allow=ALLOW, max_request=cap)
    s2 = o2.connect()
    s2.sendall(over)
    status, _, _ = read_response(s2)
    assert status == 413, status
    assert raw.bytes_seen() == b""


@needs_box
def test_peer_a2_the_wrapper_hands_each_effective_cap_to_the_running_forwarder(cfg):
    """The launch line says what the wrapper decided; this reads what the host-side forwarder was actually started with."""
    p = subprocess.Popen(["/bin/bash", WRAPPER], env=cfg.env(exec_="sleep 4", SANDBOX_TEST_MAX_REQUEST="3333333",
                         SANDBOX_TEST_MAX_TOTAL="4444444", SANDBOX_TEST_MAX_CONNS="7",
                         SANDBOX_TEST_READ_IDLE_S="9"),
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        argv = None
        end = time.time() + 10
        while time.time() < end and argv is None:
            for pid in procs_with(cfg.tmpd):
                try:
                    parts = open("/proc/%d/cmdline" % pid, "rb").read().split(b"\0")
                except OSError:
                    continue
                if b"outer" in parts and any(x.endswith(b"sandbox-forward.py") for x in parts):
                    argv = [x.decode() for x in parts]
            time.sleep(0.05)
        assert argv, "no outer forwarder found"
        got = {a: argv[argv.index(a) + 1] for a in ("--max-request", "--max-total", "--max-conns", "--read-idle-s")}
        assert got == {"--max-request": "3333333", "--max-total": "4444444", "--max-conns": "7", "--read-idle-s": "9"}, got
    finally:
        p.kill()
        p.wait()


def test_peer_b_latency_compare_runs_the_boxed_probe_with_the_slot_as_home_whatever_the_operators_home_is(cfg, stubs, tmp_path):
    """The measurement helper runs the wrapper with the operator's own environment; the HOME rule must not turn an
    operator's ordinary HOME into a failed measurement."""
    model = stubs("PONG")
    cfg.model_port = model.port
    elsewhere = tmp_path / "operator-home"
    elsewhere.mkdir()
    r = subprocess.run([PY, "-I", FWD, "latency-compare", "--wrapper", WRAPPER, "-n", "3"],
                       env=cfg.env(test=False, HOME=str(elsewhere)), capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines()[0].startswith("direct ") and any(l.startswith("bridge ") for l in r.stdout.splitlines())


# ---------------------------------------------------------------- round 6 (K): the box may neither read nor write kernel keys

import platform
X86_64_ONLY = pytest.mark.skipif(platform.machine() != "x86_64",
                                 reason="the in-box key probes call the x86_64 syscall numbers (the filter itself kills any "
                                        "other architecture)")
EPERM = 1
SYS_ADD_KEY, SYS_REQUEST_KEY, SYS_KEYCTL = 248, 249, 250       # x86_64 numbers, the probe's own
AUDIT_ARCH_X86_64, AUDIT_ARCH_AARCH64, AUDIT_ARCH_I386 = 0xC000003E, 0xC00000B7, 0x40000003
RET_ALLOW, RET_KILL_PROCESS, RET_EPERM = 0x7FFF0000, 0x80000000, 0x00050000 | EPERM

# The in-box probe: Python ctypes calling syscall(), because the keyctl tool is not installed. Prints "<return> <errno>".
# add_key targets the PROCESS keyring, so a missing filter leaves nothing behind (it dies with the process).
KEY_PROBE = r'''
import ctypes, sys
libc = ctypes.CDLL(None, use_errno=True)
libc.syscall.restype = ctypes.c_long
L, P = ctypes.c_long, ctypes.c_char_p
what, arg = sys.argv[1], sys.argv[2]
if what == "ring":      # keyctl(KEYCTL_GET_KEYRING_ID, <special keyring id>, create=0)
    r = libc.syscall(L(250), L(0), L(int(arg)), L(0))
elif what == "add":     # add_key("user", <description>, "x", 1, KEY_SPEC_PROCESS_KEYRING)
    r = libc.syscall(L(248), P(b"user"), P(arg.encode()), P(b"x"), L(1), L(-2))
elif what == "req":     # request_key("user", <description>, NULL, 0): a lookup that creates nothing
    r = libc.syscall(L(249), P(b"user"), P(arg.encode()), P(None), L(0))
print(r, ctypes.get_errno())
'''
KEY_SPEC_SESSION_KEYRING, KEY_SPEC_USER_KEYRING = -3, -4


def _probe_cmd(what, arg):
    return "%s -I -c %s %s %s" % (PY, shlex.quote(KEY_PROBE), what, shlex.quote(str(arg)))


def _probe_in_box(cfg, what, arg):
    r = cfg.run(exec_=_probe_cmd(what, arg))
    assert r.returncode == 0, r.stderr
    ret, err = r.stdout.split()
    return int(ret), int(err)


def _proc_keys_lines():
    with open("/proc/keys") as f:
        return len(f.read().splitlines())


@needs_box
@X86_64_ONLY
@pytest.mark.parametrize("ring", [KEY_SPEC_SESSION_KEYRING, KEY_SPEC_USER_KEYRING])
def test_k_a_keyctl_is_eperm_inside_the_box(cfg, ring):
    assert _probe_in_box(cfg, "ring", ring) == (-1, EPERM)


@needs_box
@X86_64_ONLY
def test_k_b_add_key_is_eperm_inside_the_box_and_no_host_key_appears(cfg):
    before = _proc_keys_lines()
    assert _probe_in_box(cfg, "add", "sandbox-test-key-%d" % os.getpid()) == (-1, EPERM)
    assert _proc_keys_lines() == before, "the host's /proc/keys changed: a key was created"


@needs_box
@X86_64_ONLY
def test_k_c_request_key_is_eperm_inside_the_box(cfg):
    assert _probe_in_box(cfg, "req", "sandbox-test-no-such-key") == (-1, EPERM)


@X86_64_ONLY
def test_k_d_the_same_keyctl_probe_outside_the_box_is_not_eperm():
    """Positive control: the probe can tell the difference. Outside, the same call answers with a key id or ENOKEY."""
    for ring in (KEY_SPEC_SESSION_KEYRING, KEY_SPEC_USER_KEYRING):
        r = subprocess.run([PY, "-I", "-c", KEY_PROBE, "ring", str(ring)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        ret, err = (int(x) for x in r.stdout.split())
        assert err != EPERM, (ring, r.stdout)


@needs_box
def test_k_e_proc_keys_and_key_users_read_as_zero_bytes_inside_the_box(cfg):
    if not os.path.exists("/proc/keys") or _proc_keys_lines() == 0:
        pytest.skip("this host's /proc/keys is empty or absent: the mask could not be told from its absence")
    r = cfg.run(exec_="for f in /proc/keys /proc/key-users; do if [ -e $f ]; then echo $f $(wc -c < $f); fi; done")
    assert r.returncode == 0, r.stderr
    got = dict(l.split() for l in r.stdout.splitlines())
    assert set(got) == {f for f in ("/proc/keys", "/proc/key-users") if os.path.exists(f)}, got
    assert all(v == "0" for v in got.values()), got


@needs_box
def test_k_f_an_ordinary_syscall_heavy_command_still_works_under_the_filter(cfg):
    code = ("import subprocess, os, socket;"
            "print(open('/etc/hostname').read().strip(), subprocess.run(['/usr/bin/true']).returncode,"
            " os.getpid() > 0, socket.socketpair() is not None)")
    r = cfg.run(exec_="%s -I -c %s" % (PY, shlex.quote(code)))
    assert r.returncode == 0 and r.stdout.strip() == "sandbox 0 True True", (r.stdout, r.stderr)


@needs_box
def test_k_g_the_stub_binary_runs_its_version_command_under_the_filter(cfg):
    r = cfg.run(args=("--version",), test=False)
    assert r.returncode == 0 and r.stdout.strip() == "stub-claude --version", (r.stdout, r.stderr)


@pytest.mark.skipif(not (os.environ.get("SANDBOX_TEST_REAL_BINARY") and os.environ.get("SANDBOX_TEST_REAL_BINARY_SHA256")),
                    reason="set SANDBOX_TEST_REAL_BINARY and SANDBOX_TEST_REAL_BINARY_SHA256 for the real-binary check")
@needs_box
def test_k_g_the_real_pinned_binary_runs_its_version_command_under_the_filter(cfg):
    cfg.binary = os.environ["SANDBOX_TEST_REAL_BINARY"]
    cfg.sha = os.environ["SANDBOX_TEST_REAL_BINARY_SHA256"]
    r = cfg.run(args=("--version",), test=False)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() != ""


# --- the program itself, from the ONE function. The evaluator below only runs a program; it holds no copy of it.

def _seccomp_program(tmp_path, fwd=FWD):
    import struct
    out = str(tmp_path / "filter.bpf")
    r = subprocess.run([PY, "-I", fwd, "seccomp-bpf", "--out", out], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    raw = open(out, "rb").read()
    assert len(raw) % 8 == 0 and 0 < len(raw) // 8 <= 64, len(raw)
    return [struct.unpack("=HBBI", raw[i:i + 8]) for i in range(0, len(raw), 8)]


def _bpf_run(prog, arch, nr):
    """Evaluate a classic BPF seccomp program on seccomp_data{nr, arch}; supports exactly the opcodes it is built from."""
    data = {0: nr, 4: arch}
    a, pc = 0, 0
    for _ in range(len(prog) + 1):
        code, jt, jf, k = prog[pc]
        if code == 0x20:                       # BPF_LD | BPF_W | BPF_ABS
            a, pc = data[k], pc + 1
        elif code == 0x15:                     # BPF_JMP | BPF_JEQ | BPF_K
            pc += 1 + (jt if a == k else jf)
        elif code == 0x45:                     # BPF_JMP | BPF_JSET | BPF_K
            pc += 1 + (jt if a & k else jf)
        elif code == 0x06:                     # BPF_RET | BPF_K
            return k
        else:
            raise AssertionError("opcode %#x is not one this program should use" % code)
    raise AssertionError("program does not terminate")


def test_k1_the_program_refuses_the_three_key_syscalls_with_eperm_and_allows_everything_else(tmp_path):
    prog = _seccomp_program(tmp_path)
    for nr in (SYS_ADD_KEY, SYS_REQUEST_KEY, SYS_KEYCTL):
        assert _bpf_run(prog, AUDIT_ARCH_X86_64, nr) == RET_EPERM, nr
    for nr in (0, 1, 2, 39, 56, 57, 59, 247, 251, 435, 450, 1000):   # read, write, open, getpid, clone, fork, execve, ...
        assert _bpf_run(prog, AUDIT_ARCH_X86_64, nr) == RET_ALLOW, nr


@pytest.mark.parametrize("nr", [SYS_ADD_KEY, SYS_REQUEST_KEY, SYS_KEYCTL])
def test_k1_each_key_syscall_is_refused_on_its_own(tmp_path, nr):
    """One cell per number, so dropping any one of them reddens its own cell."""
    assert _bpf_run(_seccomp_program(tmp_path), AUDIT_ARCH_X86_64, nr) == RET_EPERM


def test_k1_another_architecture_and_the_x32_abi_are_killed(tmp_path):
    prog = _seccomp_program(tmp_path)
    for arch in (AUDIT_ARCH_AARCH64, AUDIT_ARCH_I386, 0, 0xFFFFFFFF):
        for nr in (0, SYS_KEYCTL):
            assert _bpf_run(prog, arch, nr) == RET_KILL_PROCESS, (hex(arch), nr)
    for nr in (0, SYS_KEYCTL, SYS_ADD_KEY, 512):                      # x32: syscall numbers with bit 30 set
        assert _bpf_run(prog, AUDIT_ARCH_X86_64, nr | 0x40000000) == RET_KILL_PROCESS, nr


def test_k1_the_program_starts_by_loading_and_comparing_the_architecture(tmp_path):
    prog = _seccomp_program(tmp_path)
    assert prog[0] == (0x20, 0, 0, 4), prog[0]                         # load seccomp_data.arch (offset 4)
    code, jt, jf, k = prog[1]
    assert (code, jt, k) == (0x15, 0, AUDIT_ARCH_X86_64), prog[1]       # equal: carry on; otherwise jump to a verdict
    assert prog[1 + 1 + jf][0] == 0x06 and prog[1 + 1 + jf][3] == RET_KILL_PROCESS, "an unknown arch does not end in KILL"


def test_k1_the_wrapper_passes_the_program_to_bwrap_as_a_descriptor(cfg, fake_bwrap):
    toks = _launch_argv(cfg, fake_bwrap)
    assert toks.count("--seccomp") == 1, toks
    assert toks[toks.index("--seccomp") + 1].isdigit(), toks


@needs_box
def test_k1_a_program_that_cannot_be_built_is_refused_before_anything_starts(cfg, fake_bwrap, tmp_path):
    """A copy of the wrapper beside a forwarder whose seccomp-bpf mode does not exist: the build fails, so the wrapper
    must refuse (named, exit 2), not start a box without the filter."""
    d = tmp_path / "broken"
    d.mkdir()
    text = open(FWD).read()
    broken = text.replace('sub.add_parser("seccomp-bpf")', 'sub.add_parser("seccomp-bpf-gone")')
    assert broken != text, "the forwarder does not register a seccomp-bpf mode"
    (d / "sandbox-forward.py").write_text(broken)
    shutil.copy(WRAPPER, str(d / "student-sandbox.sh"))
    fdir, out = fake_bwrap
    r = subprocess.run(["/bin/bash", str(d / "student-sandbox.sh")], env=cfg.env(exec_="true", PATH=fdir + ":/usr/bin:/bin",
                       FAKE_BWRAP_OUT=out, SANDBOX_LOG=cfg.log), capture_output=True, text=True, timeout=60)
    lines = [l for l in r.stderr.splitlines() if l.strip()]
    assert r.returncode == 2 and len(lines) == 1 and "seccomp" in lines[0], (r.returncode, r.stderr)
    assert not os.path.exists(out) and os.listdir(cfg.tmpd) == [] and not os.path.exists(cfg.log)


@needs_box
def test_k1_a_bwrap_that_rejects_the_program_is_refused_before_anything_starts(cfg, tmp_path):
    d = tmp_path / "rejecting"
    d.mkdir()
    out = str(tmp_path / "rejecting-called")
    make_exe(str(d / "bwrap"), '#!/bin/sh\ncase "$*" in *--seccomp*) echo "bwrap: Unknown option --seccomp" >&2; exit 1 ;; esac\n'
             'echo started > "$FAKE_BWRAP_OUT"\nexit 99\n')
    r = cfg.run(exec_="true", PATH=str(d) + ":/usr/bin:/bin", FAKE_BWRAP_OUT=out, SANDBOX_LOG=cfg.log)
    lines = [l for l in r.stderr.splitlines() if l.strip()]
    assert r.returncode == 2 and len(lines) == 1 and "seccomp" in lines[0], (r.returncode, r.stderr)
    assert not os.path.exists(out) and os.listdir(cfg.tmpd) == [] and not os.path.exists(cfg.log)


def _launch_argv(cfg, fake_bwrap):
    fdir, out = fake_bwrap
    r = cfg.run(exec_="true", PATH=fdir + ":/usr/bin:/bin", FAKE_BWRAP_OUT=out)
    assert r.returncode == 99, r.stderr
    toks = open(out).read().strip().partition(" ")[2].split()
    _wait_clean(cfg)
    return toks


def test_k2_proc_keys_and_key_users_are_masked_read_only_after_proc(cfg, fake_bwrap):
    toks = _launch_argv(cfg, fake_bwrap)
    proc_at = toks.index("--proc")
    present = [n for n in ("/proc/keys", "/proc/key-users") if os.path.exists(n)]
    assert present, "this host has neither file: nothing to mask"
    for name in present:
        masks = [i for i, t in enumerate(toks) if t.startswith("--ro-bind") and toks[i + 2:i + 3] == [name]]
        assert len(masks) == 1 and masks[0] > proc_at, (name, toks)


# ---------------------------------------------------------------- round 6 (L): /usr/local is not visible in the box

@needs_box
def test_l_usr_local_is_an_empty_directory_inside_the_box(cfg):
    """bwrap cannot remove a directory from a read-only bind of /usr, so /usr/local is an empty tmpfs over it (the
    directory exists, holds nothing). On a host without /usr/local it is simply absent."""
    r = cfg.run(exec_="if [ -d /usr/local ]; then ls -A /usr/local | wc -l; else echo absent; fi")
    assert r.returncode == 0, r.stderr
    assert r.stdout.split()[0] in ("absent", "0"), "host /usr/local is visible inside: %r" % r.stdout


@pytest.mark.skipif(not os.path.isdir("/usr/local") or os.path.islink("/usr/local"),
                    reason="this host has no /usr/local directory to hide")
def test_l_the_argv_covers_usr_local_after_the_usr_bind(cfg, fake_bwrap):
    toks = _launch_argv(cfg, fake_bwrap)
    tm = [i for i, t in enumerate(toks) if t == "--tmpfs" and toks[i + 1] == "/usr/local"]
    usr = [i for i, t in enumerate(toks) if t == "--ro-bind-try" and toks[i + 2] == "/usr"]
    assert len(tm) == 1 and len(usr) == 1 and tm[0] > usr[0], toks


# ---------------------------------------------------------------- round 6 (H): the launch line names what ran

def test_h_the_launch_line_carries_the_sha256_of_the_wrapper_and_the_forwarder_that_ran(cfg, fake_bwrap):
    f, _ = _launch_fields(cfg, fake_bwrap)
    assert f.get("wrapper_sha256") == sha256_of(os.path.realpath(WRAPPER)), f
    assert f.get("forwarder_sha256") == sha256_of(os.path.realpath(FWD)), f


def test_h_the_hashes_are_of_the_files_the_wrapper_resolved_not_of_a_name(cfg, fake_bwrap, tmp_path):
    """A wrapper started through a link, beside a forwarder that is itself a link, reports the hashes of the real files."""
    d = tmp_path / "linked"
    d.mkdir()
    real = tmp_path / "real"
    real.mkdir()
    shutil.copy(WRAPPER, str(real / "student-sandbox.sh"))
    (real / "sandbox-forward.py").write_text(open(FWD).read() + "\n# a different forwarder\n")
    os.symlink(str(real / "student-sandbox.sh"), str(d / "claude"))
    os.symlink(str(real / "sandbox-forward.py"), str(d / "sandbox-forward.py"))
    fdir, out = fake_bwrap
    r = subprocess.run(["/bin/bash", str(d / "claude")], env=cfg.env(exec_="true", PATH=fdir + ":/usr/bin:/bin",
                       FAKE_BWRAP_OUT=out, SANDBOX_LOG=cfg.log), capture_output=True, text=True, timeout=60)
    assert r.returncode == 99, r.stderr
    line = [l for l in open(cfg.log).read().splitlines() if l.startswith("wrapper-launch ")][0]
    f = dict(kv.split("=", 1) for kv in line.split()[1:])
    assert f["wrapper_sha256"] == sha256_of(str(real / "student-sandbox.sh")), f
    assert f["forwarder_sha256"] == sha256_of(str(real / "sandbox-forward.py")), f
    _wait_clean(cfg)


# ---------------------------------------------------------------- round 7 (R7-1): the forwarder that is hashed is the forwarder that runs

def _bound_forwarder_source(toks):
    """The host-side source of the bind whose in-box destination is /run/sandbox-forward.py."""
    hits = [toks[i + 1] for i, t in enumerate(toks) if t == "--ro-bind" and toks[i + 2:i + 3] == ["/run/sandbox-forward.py"]]
    assert len(hits) == 1, toks
    return hits[0]


def test_r7_1_the_box_is_given_a_private_copy_of_the_forwarder_not_the_source_path(cfg, fake_bwrap):
    src = _bound_forwarder_source(_launch_argv(cfg, fake_bwrap))
    assert os.path.realpath(src) != os.path.realpath(FWD), "the source path itself is bound"
    assert os.path.realpath(src).startswith(os.path.realpath(cfg.tmpd) + os.sep), src


def test_r7_1_replacing_the_source_after_the_hash_changes_nothing_that_is_bound(cfg, tmp_path):
    """The hash-then-run gap: a stand-in bwrap replaces the source file, at the moment the box would start, and then
    hashes what it was told to bind. That must still be the file whose hash is on the launch line."""
    d = tmp_path / "gap"
    d.mkdir()
    shutil.copy(WRAPPER, str(d / "student-sandbox.sh"))
    shutil.copy(FWD, str(d / "sandbox-forward.py"))
    b = tmp_path / "gapbin"
    b.mkdir()
    out = str(tmp_path / "gap-out")
    make_exe(str(b / "bwrap"), '#!/bin/sh\n' + FAKE_PROBE_PASS +
             'src=\nwhile [ $# -gt 0 ]; do if [ "$1" = --ro-bind ] && [ "$3" = /run/sandbox-forward.py ]; then src=$2; fi; shift; done\n'
             'printf swapped > "$FAKE_REPLACE.new" && mv "$FAKE_REPLACE.new" "$FAKE_REPLACE"\n'
             'echo "SHA=$(sha256sum < "$src" | cut -d" " -f1)" > "$FAKE_BWRAP_OUT"\nexit 99\n')
    r = subprocess.run(["/bin/bash", str(d / "student-sandbox.sh")],
                       env=cfg.env(exec_="true", PATH=str(b) + ":/usr/bin:/bin", FAKE_BWRAP_OUT=out,
                                   FAKE_REPLACE=str(d / "sandbox-forward.py"), SANDBOX_LOG=cfg.log),
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 99, r.stderr
    f = dict(kv.split("=", 1) for kv in [l for l in open(cfg.log).read().splitlines()
                                         if l.startswith("wrapper-launch ")][0].split()[1:])
    assert open(str(d / "sandbox-forward.py")).read() == "swapped", "the stand-in did not replace the source"
    assert open(out).read().strip() == "SHA=" + f["forwarder_sha256"], (open(out).read(), f["forwarder_sha256"])
    _wait_clean(cfg)


@needs_box
def test_r7_1_the_file_the_box_sees_has_the_hash_on_the_launch_line(cfg):
    r = cfg.run(exec_="%s -I -c %s" % (PY, shlex.quote("import hashlib; print(hashlib.sha256(open('/run/sandbox-forward.py','rb')"
                                                      ".read()).hexdigest())")), SANDBOX_LOG=cfg.log)
    assert r.returncode == 0, r.stderr
    f = dict(kv.split("=", 1) for kv in [l for l in open(cfg.log).read().splitlines()
                                         if l.startswith("wrapper-launch ")][0].split()[1:])
    assert r.stdout.strip() == f["forwarder_sha256"] == sha256_of(FWD), (r.stdout, f["forwarder_sha256"])


def _outer_forwarder_argv(cfg, p):
    end = time.time() + 10
    while time.time() < end:
        for pid in procs_with(cfg.tmpd):
            try:
                parts = open("/proc/%d/cmdline" % pid, "rb").read().split(b"\0")
            except OSError:
                continue
            if b"outer" in parts and any(x.endswith(b"sandbox-forward.py") for x in parts):
                return pid, [x.decode() for x in parts]
        time.sleep(0.05)
    raise AssertionError("no outer forwarder found")


@needs_box
def test_r7_1_the_outer_forwarder_runs_the_copy_not_the_source(cfg):
    p = subprocess.Popen(["/bin/bash", WRAPPER], env=cfg.env(exec_="sleep 4"), stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True)
    try:
        _, argv = _outer_forwarder_argv(cfg, p)
        script = [x for x in argv if x.endswith("sandbox-forward.py")][0]
        assert os.path.realpath(script) != os.path.realpath(FWD), argv
        assert os.path.realpath(script).startswith(os.path.realpath(cfg.tmpd) + os.sep), argv
    finally:
        p.kill()
        p.wait()


@needs_box
def test_r7_1_the_copy_is_gone_when_the_run_ends(cfg):
    r = cfg.run(exec_="true")
    assert r.returncode == 0, r.stderr
    _wait_clean(cfg)


# ---------------------------------------------------------------- round 7 (R7-2): cap hits are visible after the run

def _box_cgroup_line(cfg, secs=15):
    end = time.time() + secs
    while time.time() < end:
        if os.path.exists(cfg.log):
            lines = [l for l in open(cfg.log).read().splitlines() if l.startswith("box-cgroup ")]
            if lines:
                assert len(lines) == 1, lines
                return dict(kv.split("=", 1) for kv in lines[0].split()[1:]), lines[0]
        time.sleep(0.1)
    raise AssertionError("no box-cgroup line in the log: %r" % (open(cfg.log).read() if os.path.exists(cfg.log) else None))


def _launch_line_fields(cfg):
    return dict(kv.split("=", 1) for kv in [l for l in open(cfg.log).read().splitlines()
                                            if l.startswith("wrapper-launch ")][0].split()[1:])


CG_HOG = ("import os\n"
          "pid = os.fork()\n"
          "if pid == 0:\n"
          "    b = bytearray(b'x') * (300 << 20)\n"
          "    os._exit(0)\n"
          "os.waitpid(pid, 0)\n")
CG_BOMB = ("import os, time\n"
           "for i in range(200):\n"
           "    try:\n"
           "        pid = os.fork()\n"
           "    except OSError:\n"
           "        break\n"
           "    if pid == 0:\n"
           "        time.sleep(2)\n"
           "        os._exit(0)\n")


def test_r7_2_the_launch_line_names_the_scope_unit(cfg, fake_bwrap):
    f, _ = _launch_fields(cfg, fake_bwrap)
    assert re.fullmatch(r"student-sandbox-[0-9]+-[0-9a-f]{4,}", f.get("scope_unit", "")), f


@needs_box
def test_r7_2_a_quiet_run_logs_zero_events_and_at_least_one_poll(cfg):
    r = cfg.run(exec_="sleep 3", SANDBOX_LOG=cfg.log)
    assert r.returncode == 0, r.stderr
    f, line = _box_cgroup_line(cfg)
    assert f["scope"] == _launch_line_fields(cfg)["scope_unit"], (f, line)
    assert (f["oom_kill"], f["memory_max_events"], f["pids_max_events"]) == ("0", "0", "0"), line
    assert int(f["polls"]) >= 1 and float(f["last_poll_age_s"]) >= 0, line


@needs_box
def test_r7_2_a_memory_hog_shows_an_oom_kill_on_the_line(cfg):
    r = cfg.run(exec_="%s -I -c %s; sleep 3" % (PY, shlex.quote(CG_HOG)), SANDBOX_LOG=cfg.log,
                SANDBOX_TEST_MEMORY_MAX=str(64 << 20))
    assert r.returncode == 0, r.stderr
    f, line = _box_cgroup_line(cfg)
    assert int(f["oom_kill"]) >= 1 and int(f["memory_max_events"]) >= 1, line


@needs_box
def test_r7_2_a_fork_bomb_shows_a_pids_max_event_on_the_line(cfg):
    r = cfg.run(exec_="%s -I -c %s; sleep 3" % (PY, shlex.quote(CG_BOMB)), SANDBOX_LOG=cfg.log,
                SANDBOX_TEST_TASKS_MAX="40")
    assert r.returncode == 0, r.stderr
    f, line = _box_cgroup_line(cfg)
    assert int(f["pids_max_events"]) >= 1, line


def test_r7_2_a_forwarder_that_never_finds_the_cgroup_says_so(tmp_path):
    """Never silent: a scope that does not exist gives one line that names why."""
    sock_dir = tmp_path / "sd"
    sock_dir.mkdir()
    log = str(tmp_path / "unavail.log")
    watched = subprocess.Popen(["sleep", "2"])
    threading.Thread(target=watched.wait, daemon=True).start()   # reaped at exit: an unreaped child still counts as alive
    try:
        o = subprocess.run([PY, "-I", FWD, "outer", "--sock", str(sock_dir / "bridge.sock"), "--host", "127.0.0.1",
                            "--port", "9", "--watch", str(watched.pid), "--allow", "GET /*", "--max-request", "1000",
                            "--max-total", "1000", "--max-conns", "2", "--read-idle-s", "120", "--scope-unit", "student-sandbox-none-0000",
                            "--log", log], capture_output=True, text=True, timeout=30)
    finally:
        watched.kill()
        watched.wait()
    lines = [l for l in open(log).read().splitlines() if l.startswith("box-cgroup ")]
    assert len(lines) == 1 and lines[0].startswith("box-cgroup unavailable reason="), (lines, o.stderr)


# ---------------------------------------------------------------- round 7 (R7-3, R7-4): no box-only descriptor reaches the forwarder

@needs_box
def test_r7_4_the_outer_forwarder_holds_no_descriptor_meant_for_the_box(cfg):
    p = subprocess.Popen(["/bin/bash", WRAPPER], env=cfg.env(exec_="sleep 4", SANDBOX_LOG=cfg.log),
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        pid, _ = _outer_forwarder_argv(cfg, p)
        end = time.time() + 10
        while time.time() < end and not (os.path.exists(cfg.log) and "wrapper-launch " in open(cfg.log).read()):
            time.sleep(0.05)
        assert int(_launch_line_fields(cfg)["etc_masked"]) > 0, "no /etc mask on this host: the cell could not see a leak of one"
        held = []
        for fd in os.listdir("/proc/%d/fd" % pid):
            if int(fd) > 2:
                target = os.readlink("/proc/%d/fd/%s" % (pid, fd))
                if target == os.devnull or target.endswith("(deleted)"):    # a mask or an overlay: only bwrap may hold them
                    held.append((fd, target))
        assert not held, "the outer forwarder holds descriptors meant for the box: %r" % held
    finally:
        p.kill()
        p.wait()


# ---------------------------------------------------------------- round 8 (T, LURIA): one tagged line per refusal, four registered counts
# Every place the bridge refuses writes EXACTLY ONE line at that place, tagged kind=<framing|cap|rule|upstream>, with a
# reason token that is unique to the site. A request is counted by the FIRST refusal the bridge makes, in the code's own
# order (connection cap, head framing, body-header framing, rule checks, head size cap, then the body in arrival order).

KINDS = {"framing", "cap", "rule", "upstream"}
TAGGED_RE = re.compile(r"(fwd-(?:deny|refuse|fault)) method=(\S+) path=(\S+) status=(\d+|-|unknown) bytes_read=(\d+) "
                       r"kind=(\w+) reason=(\S+) detail=(.*)")
TAGGED_PREFIXES = ("fwd-deny ", "fwd-refuse ", "fwd-fault ")


def tagged_lines(log):
    """Every refusal-or-fault line in the log, parsed; the lines are read after a short settle."""
    time.sleep(0.6)
    out = []
    for l in (open(log).read().splitlines() if os.path.exists(log) else []):
        if l.startswith(TAGGED_PREFIXES) or " kind=" in l:
            m = TAGGED_RE.fullmatch(l)
            assert m, "a refusal line that does not carry the tagged format: %r" % l
            out.append(dict(zip(("prefix", "method", "path", "status", "bytes_read", "kind", "reason", "detail"), m.groups())))
    return out


def _send(s, raw):
    try:
        s.sendall(raw)
    except OSError:
        pass            # the bridge refused before the whole of a large request was sent: the reply is what counts


def _simple(raw):
    def go(o, stub, tmp):
        s = o.connect()
        _send(s, raw)
        return [s]
    return go


def _total_cap(o, stub, tmp):
    full = req("POST", "/v1/messages", body=b"x" * 7000)
    first = o.connect()
    first.sendall(full[:-100])
    time.sleep(0.4)
    second = o.connect()
    _send(second, full)
    return [second, first]


def _connection_cap(o, stub, tmp):
    held = [o.connect(), o.connect()]
    time.sleep(0.4)
    third = o.connect()
    _send(third, req("GET", "/v1/models"))
    return [third] + held


def _upstream_down(o, stub, tmp):
    s = o.connect()
    _send(s, req("GET", "/v1/models"))
    return [s]


class FaultStub:
    """An upstream that fails on purpose. mode 'close-first': accepts and closes at once, reading nothing (a request sent
    to it cannot be written whole); mode 'reset-mid-response': reads the request, sends the start of a response, then
    resets the connection; mode 'stream-big': answers with a very large body, as fast as it is read."""

    def __init__(self, mode):
        self.mode = mode
        self.srv = socket.socket()
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("127.0.0.1", free_port()))
        self.srv.listen(16)
        self.port = self.srv.getsockname()[1]
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while True:
            try:
                c, _ = self.srv.accept()
            except OSError:
                return
            threading.Thread(target=self._one, args=(c,), daemon=True).start()

    def _one(self, c):
        try:
            c.settimeout(8)
            if self.mode == "close-first":
                c.close()           # an ordinary close: the first bytes written to it are answered by a reset
                return
            buf = b""
            while b"\r\n\r\n" not in buf:
                d = c.recv(65536)
                if not d:
                    c.close()
                    return
                buf += d
            if self.mode == "reject-early":
                c.sendall(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 5\r\n\r\nnope!")
                c.close()           # the body is unread: the close is answered by a reset
                return
            if self.mode == "reset-mid-response":
                c.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 1000\r\n\r\npart")
                time.sleep(0.2)
                c.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))   # close sends a reset
                c.close()
            elif self.mode == "stream-big":
                c.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\n\r\n" % (64 << 20))
                chunk = b"y" * 65536
                for _ in range(1024):
                    c.sendall(chunk)
                c.close()
        except OSError:
            pass

    def close(self):
        self.srv.close()


@pytest.fixture
def fault_stub():
    made = []

    def mk(mode):
        s = FaultStub(mode)
        made.append(s)
        return s
    yield mk
    for s in made:
        s.close()


FAULT_STUB_MODE = {"send-failed": "close-first", "upstream-reset": "reset-mid-response", "rejected-early": "reject-early"}


def _send_failed(o, stub, tmp):
    """A request too big to be written whole to an upstream that closed: the connect succeeds, the send does not."""
    s = o.connect()
    s.settimeout(20)
    _send(s, req("POST", "/v1/messages", body=b"x" * (12 << 20)))
    return [s]


def _rejected_early(o, stub, tmp):
    """The endpoint answers 400 from the head and closes with the body unread; the bridge is still sending it."""
    s = o.connect()
    s.settimeout(20)
    _send(s, req("POST", "/v1/messages", body=b"x" * (12 << 20)))
    return [s]


def _upstream_reset(o, stub, tmp):
    s = o.connect()
    s.settimeout(5)
    _send(s, req("GET", "/v1/models"))
    try:
        while s.recv(65536):      # the start of the response, then the end of the connection (EOF or a reset)
            pass
    except OSError:
        pass
    return [s]


CL_HEAD = b"POST /v1/messages HTTP/1.1\r\nHost: m\r\n"
M, P = "POST", "/v1/messages"
# reason: (kind, status, method, path, outer kwargs, driver)
SITE_CASES = {
    "connection-cap": ("cap", 503, "-", "-", dict(max_conns=2), _connection_cap),
    "head-bare-cr-lf": ("framing", 400, "-", "-", {}, _simple(b"GET /v1/models HTTP/1.1\r\nHost: m\nX: y\r\n\r\n")),
    "head-too-large": ("cap", 400, "-", "-", {}, _simple(b"GET /v1/models HTTP/1.1\r\nHost: m\r\nX: " + b"a" * 70000)),
    "request-line": ("framing", 400, "-", "-", {}, _simple(b"HELLO\r\n\r\n")),
    "version": ("framing", 505, "-", "-", {}, _simple(b"GET /v1/models HTTP/1.0\r\nHost: m\r\n\r\n")),
    "obsolete-folding": ("framing", 400, "-", "-", {}, _simple(b"GET /v1/models HTTP/1.1\r\nHost: m\r\n folded\r\n\r\n")),
    "header-line": ("framing", 400, "-", "-", {}, _simple(b"GET /v1/models HTTP/1.1\r\nNoColonHere\r\n\r\n")),
    "header-control-char": ("framing", 400, "-", "-", {}, _simple(b"GET /v1/models HTTP/1.1\r\nX-A: a\x01b\r\n\r\n")),
    "both-length-and-te": ("framing", 400, M, P, {}, _simple(
        CL_HEAD + b"Content-Length: 3\r\nTransfer-Encoding: chunked\r\n\r\n")),
    "unsupported-te": ("framing", 400, M, P, {}, _simple(CL_HEAD + b"Transfer-Encoding: gzip\r\n\r\n")),
    "content-length": ("framing", 400, M, P, {}, _simple(CL_HEAD + b"Content-Length: abc\r\n\r\n")),
    "connect": ("rule", 403, "CONNECT", "-", {}, _simple(b"CONNECT example.invalid:443 HTTP/1.1\r\nHost: m\r\n\r\n")),
    "upgrade": ("rule", 403, "GET", "/v1/models", {}, _simple(
        b"GET /v1/models HTTP/1.1\r\nHost: m\r\nConnection: Upgrade\r\nUpgrade: websocket\r\n\r\n")),
    "expect-continue": ("rule", 417, M, P, {}, _simple(CL_HEAD + b"Content-Length: 5\r\nExpect: 100-continue\r\n\r\n")),
    "target-form": ("rule", 403, "GET", "-", {}, _simple(b"GET http://example.invalid/v1/models HTTP/1.1\r\nHost: m\r\n\r\n")),
    "fragment": ("rule", 403, "GET", "/v1/models", {}, _simple(b"GET /v1/models#frag HTTP/1.1\r\nHost: m\r\n\r\n")),
    "path-undecodable": ("rule", 403, "GET", "/v1/%ff", {}, _simple(b"GET /v1/%ff HTTP/1.1\r\nHost: m\r\n\r\n")),
    "path-encoding": ("rule", 403, "GET", "/v1/%2525", {}, _simple(b"GET /v1/%2525 HTTP/1.1\r\nHost: m\r\n\r\n")),
    "path-segment": ("rule", 403, "GET", "/v1/../x", {}, _simple(b"GET /v1/../x HTTP/1.1\r\nHost: m\r\n\r\n")),
    "not-on-allow-list": ("rule", 403, "DELETE", "/api/delete", {}, _simple(b"DELETE /api/delete HTTP/1.1\r\nHost: m\r\n\r\n")),
    "request-cap": ("cap", 413, M, P, dict(max_request=50), _simple(CL_HEAD + b"Content-Length: 0\r\n\r\n")),
    "declared-length-over-cap": ("cap", 413, M, P, dict(max_request=4096), _simple(req("POST", "/v1/messages", body=b"x" * 10000))),
    "chunk-over-cap": ("cap", 413, M, P, dict(max_request=4096), _simple(
        CHUNK_HEAD + b"bb8\r\n" + b"x" * 3000 + b"\r\nbb8\r\n" + b"x" * 3000 + b"\r\n0\r\n\r\n")),
    "total-cap": ("cap", 413, M, P, dict(max_request=8192, max_total=12000), _total_cap),
    "chunk-size": ("framing", 400, M, P, {}, _simple(CHUNK_HEAD + b"zz\r\nhello\r\n0\r\n\r\n")),
    "trailer": ("framing", 400, M, P, {}, _simple(CHUNK_HEAD + b"0\r\nXX")),
    "chunk-framing": ("framing", 400, M, P, {}, _simple(CHUNK_HEAD + b"5\r\nhelloXX0\r\n\r\n")),
    "chunk-bare-cr-lf": ("framing", 400, M, P, {}, _simple(CHUNK_HEAD + b"5\nhello")),
    "chunk-bare-cr": ("framing", 400, M, P, {}, _simple(CHUNK_HEAD + b"5\rab")),
    "chunk-line-too-long": ("cap", 400, M, P, {}, _simple(CHUNK_HEAD + b"a" * 9000)),
    "read-timeout": ("cap", 408, "-", "-", dict(read_idle_s=1), _simple(b"GET /v1/mo")),
    "connect-failed": ("upstream", 502, "GET", "/v1/models", {}, _upstream_down),
    "send-failed": ("upstream", None, M, P, {}, _send_failed),     # None: no reply is attempted, status=-
    "upstream-reset": ("upstream", None, "-", "-", {}, _upstream_reset),     # None: no reply can be sent, status=-
    "rejected-early": ("upstream", "unknown", M, P, {}, _rejected_early),   # "unknown": the endpoint's own 400 was relayed
}


@pytest.fixture
def dead_port_stub():
    class Dead:
        port = free_port()          # nothing listens here: the upstream connect is refused
    return Dead()


@pytest.mark.parametrize("reason", sorted(SITE_CASES))
def test_t_each_refusal_site_writes_exactly_one_tagged_line(outer, raw_stub, dead_port_stub, fault_stub, tmp_path, reason):
    kind, status, method, path, kw, drive = SITE_CASES[reason]
    if reason == "connect-failed":
        stub = dead_port_stub
    elif reason in FAULT_STUB_MODE:
        stub = fault_stub(FAULT_STUB_MODE[reason])
    else:
        stub = raw_stub()
    log = str(tmp_path / "t.log")
    o = outer(stub, allow=ALLOW, log=log, **kw)
    socks = drive(o, stub, tmp_path)
    if isinstance(status, int):                 # a site that cannot reply (status=- or unknown) has no status of its own to read
        got, _, _ = read_response(socks[0])
        assert got == status, (reason, got)
    if status == "unknown":
        assert read_response(socks[0])[0] == 400    # the endpoint's own answer, relayed intact
    lines = tagged_lines(log)
    assert len(lines) == 1, (reason, lines)
    L = lines[0]
    assert (L["kind"], L["reason"], L["status"], L["method"], L["path"]) == (
        kind, reason, "-" if status is None else str(status), method, path), L
    assert "SECRET" not in L["detail"]
    if reason == "connection-cap":
        assert L["bytes_read"] == "0" and "(2)" in L["detail"], L      # only what is known at accept: nothing invented
    if kind != "upstream":
        assert stub.bytes_seen() == b"", "a refused request reached the upstream"


def test_t_the_prefix_by_kind_is_the_one_the_lines_use():
    """The prefixes stay readable: rule refusals are fwd-deny, upstream faults fwd-fault, the rest fwd-refuse."""
    want = {"rule": "fwd-deny", "upstream": "fwd-fault", "framing": "fwd-refuse", "cap": "fwd-refuse"}
    assert set(k[0] for k in SITE_CASES.values()) == KINDS
    mod = _load_forwarder()
    got = {k: mod.refusal_line(mod.Refusal(k, "x", 400), "-", "-", 0).split(" ", 1)[0] for k in KINDS}
    assert got == want, got


def test_t_the_prefix_matches_the_kind_in_every_line(outer, raw_stub, tmp_path):
    want = {"rule": "fwd-deny", "framing": "fwd-refuse"}
    stub = raw_stub()
    log = str(tmp_path / "p.log")
    o = outer(stub, allow=ALLOW, log=log)
    for raw in (b"DELETE /api/delete HTTP/1.1\r\nHost: m\r\n\r\n", b"HELLO\r\n\r\n"):
        s = o.connect()
        s.sendall(raw)
        read_response(s)
    seen = {L["kind"]: L["prefix"] for L in tagged_lines(log)}
    assert seen == want, seen


# ---- the derived cell: the refusal sites are found by parsing the forwarder's own source, never from a hand list

def _forwarder_tree():
    import ast
    return ast.parse(open(FWD).read())


def _status_set(node):
    """The statuses one `Refusal(...)` site can carry, read from its status argument: a literal, or a conditional
    expression whose two branches are literals (None is 'no reply can be sent', written as status=-). Anything else is
    reported as the single value '?' so a cell fails on it."""
    import ast
    if isinstance(node, ast.Constant) and (node.value is None or isinstance(node.value, int) or node.value == "unknown"):
        return frozenset([node.value])
    if isinstance(node, ast.IfExp):
        a, b = _status_set(node.body), _status_set(node.orelse)
        return frozenset() if "?" in a | b else a | b
    return frozenset(["?"])


def derived_refusal_sites():
    """Every call of `Refusal(kind, reason, status, ...)` in the forwarder, as (lineno, kind, reason, statuses) with the
    literal arguments; kind or reason that is not a literal is reported as None, statuses is a frozenset of int|None."""
    import ast
    sites = []
    for node in ast.walk(_forwarder_tree()):
        if isinstance(node, ast.Call):
            f = node.func
            name = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)
            if name == "Refusal":
                args = {"kind": None, "reason": None, "status": None}
                for key, a in zip(("kind", "reason", "status"), node.args[:3]):
                    args[key] = a
                for kw in node.keywords:
                    if kw.arg in args:
                        args[kw.arg] = kw.value
                lit = lambda a: a.value if isinstance(a, ast.Constant) else None
                st = _status_set(args["status"]) if args["status"] is not None else frozenset(["?"])
                sites.append((node.lineno, lit(args["kind"]), lit(args["reason"]), st))
    return sites


def test_t_derived_every_refusal_site_has_a_kind_a_unique_reason_and_a_mapped_status():
    sites = derived_refusal_sites()
    assert len(sites) >= 30, "the derivation found too few sites to be reading the source: %r" % sites
    for lineno, kind, reason, status in sites:
        assert kind in KINDS, "line %d: refusal site without a registered kind: %r" % (lineno, kind)
        assert isinstance(reason, str) and re.fullmatch(r"[a-z][a-z0-9-]*", reason), "line %d: no reason token" % lineno
        assert status and all(x is None or x == "unknown" or isinstance(x, int) for x in status), "line %d: no literal status" % lineno
    reasons = [r for _, _, r, _ in sites]
    assert len(reasons) == len(set(reasons)), "two sites share a reason: %r" % sorted(
        r for r in set(reasons) if reasons.count(r) > 1)
    mod = _load_forwarder()
    # a status the bridge can return is mapped: it has a phrase, and every phrase belongs to a status some site returns
    replied = {x for _, _, _, st in sites for x in st if isinstance(x, int)}      # None is "no reply can be sent", "unknown" is the endpoint's own answer
    assert replied == set(mod.PHRASE), (sorted(replied), sorted(mod.PHRASE))
    # each site has exactly one kind (it is one literal); a STATUS may carry two kinds, by what the check protects:
    # 400 is framing and, for a size limit, cap
    kinds_by_status = {}
    for _, k, _, st in sites:
        for s in st:
            kinds_by_status.setdefault(s, set()).add(k)
    assert all(kinds_by_status.values())
    assert {s for s, ks in kinds_by_status.items() if len(ks) > 1} <= {400, None}, kinds_by_status


def test_t_derived_the_refusal_response_and_the_refusal_line_each_have_one_writer():
    """A refusal path that builds its own reply or its own line (and so can skip the kind) is found here: the response
    template and the tagged prefixes are used only inside the two functions that own them (refusal_response and
    refusal_line)."""
    import ast
    tree = _forwarder_tree()
    owner = {"RESP_CLOSE": {"refusal_response"}, "fwd-deny": {"refusal_line"}, "fwd-refuse": {"refusal_line"},
             "fwd-fault": {"refusal_line"}}
    found = {k: set() for k in owner}

    class V(ast.NodeVisitor):
        def __init__(self):
            self.fn = [None]

        def visit_FunctionDef(self, n):
            self.fn.append(n.name)
            self.generic_visit(n)
            self.fn.pop()

        def visit_Name(self, n):
            if n.id in found and isinstance(n.ctx, ast.Load):
                found[n.id].add(self.fn[-1])

        def visit_Constant(self, n):
            if isinstance(n.value, str):
                for k in ("fwd-deny", "fwd-refuse", "fwd-fault"):
                    if k in n.value:
                        found[k].add(self.fn[-1])

    V().visit(tree)
    for k, fns in found.items():
        assert fns <= owner[k], "%s is used outside its writer: %r" % (k, sorted(map(str, fns - owner[k])))
        assert fns, "%s is not used anywhere: the derivation is reading nothing" % k


def test_t_derived_every_site_has_a_driving_cell():
    """The per-site cell table covers exactly the sites the source has: a new site without a cell fails here."""
    assert sorted(SITE_CASES) == sorted(r for _, _, r, _ in derived_refusal_sites())
    for reason, (kind, status, *_rest) in SITE_CASES.items():
        derived = [(k, st) for _, k, r, st in derived_refusal_sites() if r == reason]
        assert len(derived) == 1 and derived[0][0] == kind and status in derived[0][1], (reason, derived, kind, status)


# ---- precedence: a request is counted by the FIRST refusal the bridge makes, in the code's order

def test_t_precedence_a_fragment_target_with_an_over_cap_declared_body_is_one_rule_line(outer, raw_stub, tmp_path):
    stub = raw_stub()
    log = str(tmp_path / "prec1.log")
    o = outer(stub, allow=ALLOW, log=log, max_request=4096)
    head = b"POST /v1/messages#x HTTP/1.1\r\nHost: m\r\nContent-Length: 10000\r\n\r\n"
    s = o.connect()
    s.sendall(head + b"x" * 6000)
    assert read_response(s)[0] == 403
    lines = tagged_lines(log)
    assert len(lines) == 1 and (lines[0]["kind"], lines[0]["reason"]) == ("rule", "fragment"), lines
    assert int(lines[0]["bytes_read"]) == len(head), "the body must never be read: %r" % lines   # head only
    assert stub.bytes_seen() == b""


def test_t_precedence_body_header_framing_comes_before_the_rule_checks(outer, raw_stub, tmp_path):
    stub = raw_stub()
    log = str(tmp_path / "prec2.log")
    o = outer(stub, allow=ALLOW, log=log)
    s = o.connect()
    s.sendall(b"CONNECT example.invalid:443 HTTP/1.1\r\nHost: m\r\nContent-Length: 1\r\nTransfer-Encoding: chunked\r\n\r\n")
    assert read_response(s)[0] == 400
    lines = tagged_lines(log)
    assert len(lines) == 1 and (lines[0]["kind"], lines[0]["reason"]) == ("framing", "both-length-and-te"), lines


def test_t_precedence_the_rule_checks_come_before_the_head_size_cap(outer, raw_stub, tmp_path):
    stub = raw_stub()
    log = str(tmp_path / "prec3.log")
    o = outer(stub, allow=ALLOW, log=log, max_request=50)       # the head alone is over the cap, and the method is not listed
    s = o.connect()
    s.sendall(b"DELETE /api/delete HTTP/1.1\r\nHost: model-host-name\r\n\r\n")
    assert read_response(s)[0] == 403
    lines = tagged_lines(log)
    assert len(lines) == 1 and (lines[0]["kind"], lines[0]["reason"]) == ("rule", "not-on-allow-list"), lines


def test_t_precedence_inside_the_body_the_first_to_arrive_is_the_one_line(outer, raw_stub, tmp_path):
    """A bad chunk-size line that arrives BEFORE the cumulative cap is exceeded is framing, not cap."""
    stub = raw_stub()
    log = str(tmp_path / "prec4.log")
    o = outer(stub, allow=ALLOW, log=log, max_request=4096)
    s = o.connect()
    s.sendall(CHUNK_HEAD + b"5\r\nhello\r\nZZ\r\n" + b"fff\r\n" + b"x" * 3000)
    assert read_response(s)[0] == 400
    lines = tagged_lines(log)
    assert len(lines) == 1 and (lines[0]["kind"], lines[0]["reason"]) == ("framing", "chunk-size"), lines


def test_t_a_connect_request_yields_one_line_kind_rule_reason_connect(outer, raw_stub, tmp_path):
    stub = raw_stub()
    log = str(tmp_path / "conn.log")
    o = outer(stub, allow=ALLOW, log=log)
    s = o.connect()
    s.sendall(b"CONNECT example.invalid:443 HTTP/1.1\r\nHost: m\r\n\r\n")
    assert read_response(s)[0] == 403
    lines = tagged_lines(log)
    assert len(lines) == 1 and (lines[0]["kind"], lines[0]["reason"]) == ("rule", "connect"), lines


def test_t_the_upstream_connect_failure_is_not_logged_as_a_student_refusal(outer, dead_port_stub, tmp_path):
    log = str(tmp_path / "up.log")
    o = outer(dead_port_stub, allow=ALLOW, log=log)
    s = o.connect()
    s.sendall(req("GET", "/v1/models"))
    assert read_response(s)[0] == 502
    lines = tagged_lines(log)
    assert [(L["kind"], L["reason"], L["status"]) for L in lines] == [("upstream", "connect-failed", "502")], lines
    text = open(log).read()
    assert not [l for l in text.splitlines() if l.startswith(("fwd-deny ", "fwd-refuse "))], text


# ---- L-S1: Expect: 100-continue is refused at once

def test_l_s1_expect_continue_is_417_promptly_and_nothing_reaches_the_upstream(outer, raw_stub, tmp_path):
    stub = raw_stub()
    log = str(tmp_path / "exp.log")
    o = outer(stub, allow=ALLOW, log=log)
    s = o.connect()
    s.settimeout(3)
    t0 = time.time()
    s.sendall(CL_HEAD + b"Content-Length: 100\r\nExpect: 100-continue\r\n\r\n")      # the body is never sent
    status, _, _ = read_response(s)
    assert status == 417 and time.time() - t0 < 3, (status, time.time() - t0)
    assert at_eof(s)
    assert stub.bytes_seen() == b""
    lines = tagged_lines(log)
    assert [(L["kind"], L["reason"]) for L in lines] == [("rule", "expect-continue")], lines


def test_l_s1_expect_is_matched_as_a_token_in_any_case(outer, raw_stub, tmp_path):
    stub = raw_stub()
    o = outer(stub, allow=ALLOW, log=str(tmp_path / "e2.log"))
    s = o.connect()
    s.sendall(CL_HEAD + b"Content-Length: 100\r\nexpect:  100-Continue \r\n\r\n")
    assert read_response(s)[0] == 417


# ---- L-S2: an idle read timeout while READING A REQUEST (not while relaying a response)

def test_l_s2_a_partial_request_is_cut_by_the_idle_read_timeout(outer, raw_stub, tmp_path):
    stub = raw_stub()
    log = str(tmp_path / "idle.log")
    o = outer(stub, allow=ALLOW, log=log, read_idle_s=1)
    s = o.connect()
    s.sendall(b"POST /v1/messages HTTP/1.1\r\nHost: m\r\nContent-Length: 100\r\n\r\nabc")     # 97 bytes never come
    t0 = time.time()
    assert read_response(s)[0] == 408
    assert 0.8 <= time.time() - t0 < 4, time.time() - t0
    lines = tagged_lines(log)
    assert [(L["kind"], L["reason"], L["status"]) for L in lines] == [("cap", "read-timeout", "408")], lines
    assert stub.bytes_seen() == b""


def test_l_s2_a_connection_that_sends_nothing_is_cut_too(outer, raw_stub, tmp_path):
    stub = raw_stub()
    o = outer(stub, allow=ALLOW, log=str(tmp_path / "idle0.log"), read_idle_s=1)
    s = o.connect()
    assert read_response(s)[0] == 408


class SlowStub:
    """An upstream that answers one request after `delay` seconds: a model response that takes longer than the idle timeout."""

    def __init__(self, delay):
        self.srv = socket.socket()
        self.srv.bind(("127.0.0.1", free_port()))
        self.srv.listen(4)
        self.port = self.srv.getsockname()[1]
        self.delay = delay
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while True:
            try:
                c, _ = self.srv.accept()
            except OSError:
                return
            threading.Thread(target=self._one, args=(c,), daemon=True).start()

    def _one(self, c):
        try:
            c.settimeout(10)
            buf = b""
            while b"\r\n\r\n" not in buf:
                buf += c.recv(65536)
            time.sleep(self.delay)
            c.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
            time.sleep(1)
        except OSError:
            pass
        c.close()


def test_l_s2_a_response_that_outlasts_the_timeout_is_not_cut(outer, tmp_path):
    slow = SlowStub(delay=2.5)
    log = str(tmp_path / "slow.log")
    o = outer(slow, allow=ALLOW, log=log, read_idle_s=1)
    s = o.connect()
    s.settimeout(8)
    s.sendall(req("GET", "/v1/models"))
    status, _, body = read_response(s)
    assert (status, body) == (200, b"ok"), (status, body)
    assert tagged_lines(log) == []


# ---- L-S3: an unreaped zombie is not alive (Linux reads /proc/<pid>/stat)

@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="reads /proc/<pid>/stat: Linux only; elsewhere os.kill stays")
def test_l_s3_a_child_that_exited_but_is_not_reaped_reads_dead():
    mod = _load_forwarder()
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    try:
        end = time.time() + 10
        state = ""
        while time.time() < end:
            state = open("/proc/%d/stat" % p.pid).read().rsplit(")", 1)[1].split()[0]
            if state == "Z":
                break
            time.sleep(0.02)
        assert state == "Z", "the child never became a zombie: %r" % state
        os.kill(p.pid, 0)                     # signal 0 still succeeds on a zombie: this is the defect
        assert mod.alive(p.pid) is False
    finally:
        p.wait()


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux only")
def test_l_s3_a_running_child_reads_alive_and_the_reaped_one_dead():
    mod = _load_forwarder()
    p = subprocess.Popen(["sleep", "5"])
    try:
        assert mod.alive(p.pid) is True
    finally:
        p.kill()
        p.wait()
    assert mod.alive(p.pid) is False


# ---------------------------------------------------------------- round 9 (D, U, K)
# D: the README's per-reason table and its stated check order are derived-checked against the source (never a hand list).
# U: an upstream failure after a successful connect is tagged at its own site, never silent; a client hangup stays untagged.

README = os.path.join(TOOLS, "README.md")


def _readme_text():
    return open(README).read()


def _status_cell(cell):
    """The statuses a README status cell names: three-digit numbers, and a bare '-' for 'no reply can be sent'."""
    return frozenset(int(t) if t[0].isdigit() else (None if t == "-" else t)
                     for t in re.findall(r"\d{3}|unknown|(?<![\w-])-(?![\w-])", cell))


def readme_reason_table():
    """{reason: (kind, frozenset of statuses)} from the README's per-reason table: every row shaped
    `| `reason` | kind | status | site |`. A reason that appears twice is a failure of its own."""
    rows, dup = {}, []
    for line in _readme_text().splitlines():
        m = re.match(r"\| `([a-z][a-z0-9-]*)` \| (framing|cap|rule|upstream) \| ([^|]*?) \| ", line)
        if m:
            if m.group(1) in rows:
                dup.append(m.group(1))
            rows[m.group(1)] = (m.group(2), _status_cell(m.group(3)))
    assert not dup, "a reason is in the README table twice: %r" % dup
    return rows


def readme_order():
    """(steps, ordered, anytime) from the README's order paragraph. `steps` is [(number, [reason tokens])], read from the
    segments `(1) ... (2) ...` of the paragraph that starts "Order, as found in the code"; `ordered` is the set of step
    numbers whose text says "in this order"; `anytime` is the reason tokens of the paragraph that starts "At any point".
    A reason token is a backticked lower-case hyphenated word (a status number or a header name is not one)."""
    paras = _readme_text().split("\n\n")
    order = [p for p in paras if p.startswith("Order, as found in the code")]
    anyp = [p for p in paras if p.startswith("At any point")]
    assert len(order) == 1 and len(anyp) == 1, "the README must state its order and its at-any-point sites, once each"
    tok = lambda t: re.findall(r"`([a-z][a-z0-9-]*)`", t)
    parts = re.split(r"\((\d+)\)", order[0])
    steps = [(int(parts[i]), tok(parts[i + 1])) for i in range(1, len(parts) - 1, 2)]
    ordered = {int(parts[i]) for i in range(1, len(parts) - 1, 2) if "in this order" in parts[i + 1]}
    return steps, ordered, set(tok(anyp[0]))


def derived_request_order():
    """The reasons of the `Refusal(...)` sites in the order the bridge can reach them along ONE request, read from the
    source with `ast`: the entry points are the accept hook and the connection handler, in the order the accept loop
    (`serve`) uses them; from each, the statements are walked in source order and every call of a function defined in
    the forwarder (a module function, a method of a class there, a function nested in the one being walked) is
    expanded in place, at the call, so a helper called from two steps contributes its sites at both.

    WHAT IT CAN SEE: the source order of the sites along that path, with a helper expanded at each call; a site reached
    twice appears twice. WHAT IT CANNOT SEE: which branch a run takes (an `if` body is walked as if taken); data-driven
    order between two checks that read bytes as they arrive (the body's size and framing errors) and inside loops;
    one iteration of the request loop only; a function reached through a callback, a thread target or an attribute
    whose name is not unique among the forwarder's methods (not expanded; a site only such a path reaches is
    reported as unreached and must be classed by the README as at-any-point); and what a library call raises."""
    import ast
    tree = _forwarder_tree()
    mod = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    meth = {}
    for c in tree.body:
        if isinstance(c, ast.ClassDef):
            for m in c.body:
                if isinstance(m, ast.FunctionDef):
                    meth.setdefault(m.name, []).append(m)
    nested = lambda fn: {n.name: n for n in fn.body if isinstance(n, ast.FunctionDef)}
    out = []

    def expand(fn, scope, stack):
        scope = dict(scope, **nested(fn))
        for stmt in fn.body:
            visit(stmt, scope, stack + [fn])

    def visit(n, scope, stack):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            return                           # a definition runs nothing until it is called
        for child in ast.iter_child_nodes(n):
            visit(child, scope, stack)
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name) and f.id == "Refusal":
                out.append(n.args[1].value)
                return
            target = None
            if isinstance(f, ast.Name):
                target = scope.get(f.id) or mod.get(f.id)
            elif isinstance(f, ast.Attribute) and len(meth.get(f.attr, [])) == 1:
                target = meth[f.attr][0]
            if target is not None and target not in stack:
                expand(target, scope, stack)

    run_outer = nested(mod["run_outer"])
    names = sorted((n.lineno, n.col_offset, n.id) for n in ast.walk(mod["serve"])
                   if isinstance(n, ast.Name) and n.id in ("admit", "handler"))
    entries = []
    for _, _, name in names:
        if name not in entries:
            entries.append(name)
    assert entries == ["admit", "handler"], entries
    for name in entries:
        expand(run_outer[name], dict(run_outer), [])
    return out


def test_d1_the_readme_reason_table_equals_the_source_exactly():
    src = {}
    for _, kind, reason, st in derived_refusal_sites():
        src[reason] = (kind, st)
    readme = readme_reason_table()
    assert set(readme) == set(src), ("missing from the README: %r" % sorted(set(src) - set(readme)),
                                     "in the README but not in the source: %r" % sorted(set(readme) - set(src)))
    diff = {r: (readme[r], src[r]) for r in src if readme[r] != src[r]}
    assert not diff, "a row's kind or status differs from the source (README, source): %r" % diff


def test_d2_the_readme_order_agrees_with_the_order_of_the_sites_in_the_source():
    steps, ordered, anytime = readme_order()
    sites = {r for _, _, r, _ in derived_refusal_sites()}
    named = [t for _, toks in steps for t in toks]
    assert [n for n, _ in steps] == list(range(1, len(steps) + 1)), steps
    assert set(named) | anytime == sites, ("in the source, not placed by the README: %r" % sorted(sites - set(named) - anytime),
                                           "in the README, not in the source: %r" % sorted((set(named) | anytime) - sites))
    seq = derived_request_order()
    assert len(seq) >= 20, "the walk found too few sites to be reading the source: %r" % seq
    unreached = sites - set(seq)
    assert unreached <= anytime, "a site the walk cannot reach must be classed at-any-point by the README: %r" % sorted(unreached - anytime)
    # each occurrence goes to the earliest README step, not before the current one, that names its reason; none left = disagree
    cur, placed = 1, []
    for reason in seq:
        if reason in anytime:
            continue
        for n, toks in steps:
            if n >= cur and reason in toks:
                cur = n
                placed.append((n, reason))
                break
        else:
            pytest.fail("the source reaches %r after a later README step than any that names it (current step %d): "
                        "the README order and the source order disagree; walk: %r" % (reason, cur, seq))
    for n, toks in steps:
        if n in ordered:                      # a step the README says is in this order: the same order, token by token
            got = []
            for m, r in placed:
                if m == n and r not in got:
                    got.append(r)
            assert got == toks, "step %d: the README order is %r; the source order is %r" % (n, toks, got)


def test_d3_expect_and_a_path_off_the_list_are_counted_by_the_check_the_readme_says_runs_first(outer, raw_stub, tmp_path):
    steps, ordered, _ = readme_order()
    n, rule_step = next((n, toks) for n, toks in steps if "expect-continue" in toks and "not-on-allow-list" in toks)
    assert n in ordered, "the README must say the rule checks run in this order"
    first = min(("expect-continue", "not-on-allow-list"), key=rule_step.index)
    stub = raw_stub()
    log = str(tmp_path / "d3.log")
    o = outer(stub, allow=ALLOW, log=log)
    s = o.connect()
    s.sendall(b"DELETE /api/delete HTTP/1.1\r\nHost: m\r\nContent-Length: 5\r\nExpect: 100-continue\r\n\r\n")
    read_response(s)
    lines = tagged_lines(log)
    assert [(L["kind"], L["reason"]) for L in lines] == [("rule", first)], (first, lines)
    assert stub.bytes_seen() == b""


# ---- U: after a successful connect

def test_u1_after_response_bytes_were_relayed_the_send_failure_is_one_line_status_dash_and_no_502(outer, tmp_path):
    """The first request is answered (bytes relayed); the upstream then goes away; the next request's send fails: no reply
    is attempted, so the line says status=- and the client gets no 502."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", free_port()))
    srv.listen(4)

    def once():
        c, _ = srv.accept()
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += c.recv(65536)
        c.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
        time.sleep(0.3)
        c.close()
    threading.Thread(target=once, daemon=True).start()

    class Stub:
        port = srv.getsockname()[1]
    log = str(tmp_path / "u1b.log")
    o = outer(Stub, allow=ALLOW, log=log)
    s = o.connect()
    s.settimeout(20)
    s.sendall(req("GET", "/v1/models"))
    assert read_response(s)[:1] == (200,)
    time.sleep(0.8)                                   # the upstream has closed
    _send(s, req("POST", "/v1/messages", body=b"x" * (12 << 20)))
    got = b""
    try:
        while True:
            d = s.recv(65536)
            if not d:
                break
            got += d
    except OSError:
        pass
    srv.close()
    assert b"502" not in got, got
    lines = tagged_lines(log)
    assert [(L["kind"], L["reason"], L["status"]) for L in lines] == [("upstream", "send-failed", "-")], lines


def test_u2_an_upstream_reset_in_the_relay_is_one_tagged_line_status_dash(outer, fault_stub, tmp_path):
    stub = fault_stub("reset-mid-response")
    log = str(tmp_path / "u2.log")
    o = outer(stub, allow=ALLOW, log=log)
    s = o.connect()
    s.settimeout(5)
    s.sendall(req("GET", "/v1/models"))
    try:
        while s.recv(65536):
            pass
    except OSError:
        pass
    s.close()
    lines = tagged_lines(log)
    assert [(L["kind"], L["reason"], L["status"], L["prefix"]) for L in lines] == [
        ("upstream", "upstream-reset", "-", "fwd-fault")], lines


def test_u3_a_client_that_hangs_up_inside_a_request_is_not_tagged(outer, raw_stub, tmp_path):
    stub = raw_stub()
    log = str(tmp_path / "u3a.log")
    o = outer(stub, allow=ALLOW, log=log)
    s = o.connect()
    s.sendall(b"POST /v1/messages HTTP/1.1\r\nHost: m\r\nContent-Length: 100\r\n\r\nabc")
    s.close()
    assert tagged_lines(log) == []
    assert stub.bytes_seen() == b""


def test_u3_a_client_that_hangs_up_while_a_response_streams_is_not_tagged(outer, fault_stub, tmp_path):
    stub = fault_stub("stream-big")
    log = str(tmp_path / "u3b.log")
    o = outer(stub, allow=ALLOW, log=log)
    s = o.connect()
    s.settimeout(10)
    s.sendall(req("GET", "/v1/models"))
    got = 0
    while got < 200000:
        got += len(s.recv(65536))
    s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))   # hang up with a reset, mid-response
    s.close()
    assert tagged_lines(log) == []


# ---- K: the README states the limits

def test_k_the_readme_states_the_truncation_limit_and_the_keep_alive_bound():
    text = _readme_text()
    assert "closes CLEANLY in the middle of a response" in text and "indistinguishable from a normal close" in text
    assert "does not run while a connection waits for its next request" in text and "can fill the connection cap" in text
    assert "before its first request" in text and "reason=read-timeout" in text


# ---------------------------------------------------------------- round 10 (C, PL, P): upstream lines classified by the harness-fault principle
# An event is a harness fault only if the student cannot cause it. Every upstream line is counted and read by hand; the ONE
# flag is the log-level verdict (`log-verdict`): a connect failure in a launch whose log never recorded a request going
# upstream. The marker is a positive line, `fwd-first-request`, written once per launch.

MARKER = "fwd-first-request"
FLAGGED = "flagged: endpoint unreachable, nothing reached it"


def verdict(log):
    r = subprocess.run([PY, "-I", FWD, "log-verdict", "--log", log], capture_output=True, text=True, timeout=30)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


LAUNCH_PREFIX = "wrapper-launch "


def launch_line(log):
    """The ONE helper that gives a log its launch line (what student-sandbox.sh writes at launch, minimal): `log-verdict`
    wants exactly one line starting `wrapper-launch ` per log, and a log made by the forwarder alone has none. Appends,
    as the wrapper does."""
    with open(log, "a") as f:
        f.write(LAUNCH_PREFIX + "time=0 pid=0 test=1\n")


def refused_count(n):
    return "student-sandbox: refused: log-verdict: expected exactly one line starting 'wrapper-launch ', found %d" % n


def log_lines(log):
    time.sleep(0.6)
    return open(log).read().splitlines() if os.path.exists(log) else []


def rst_close(c):
    c.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
    c.close()


def read_until(c, marker=b"\r\n\r\n"):
    buf = b""
    while marker not in buf:
        d = c.recv(65536)
        if not d:
            break
        buf += d
    return buf


OK200 = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok"
REJECT400 = b"HTTP/1.1 400 Bad Request\r\nContent-Length: 5\r\n\r\nnope!"


class FnStub:
    """An endpoint whose every accepted connection runs `fn(c)`. one_shot: the listener is closed as soon as the first
    connection is accepted, so a LATER connect is refused (an endpoint that accepts one connection, then stops)."""

    def __init__(self, fn, one_shot=False):
        self.fn, self.one_shot = fn, one_shot
        self.srv = socket.socket()
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("127.0.0.1", free_port()))
        self.srv.listen(16)
        self.port = self.srv.getsockname()[1]
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while True:
            try:
                c, _ = self.srv.accept()
            except OSError:
                return
            if self.one_shot:
                self.srv.close()
            threading.Thread(target=self._run, args=(c,), daemon=True).start()
            if self.one_shot:
                return

    def _run(self, c):
        try:
            c.settimeout(8)
            self.fn(c)
        except OSError:
            pass

    def close(self):
        try:
            self.srv.close()
        except OSError:
            pass


@pytest.fixture
def fn_stub():
    made = []

    def mk(fn, one_shot=False):
        s = FnStub(fn, one_shot)
        made.append(s)
        return s
    yield mk
    for s in made:
        s.close()


def _answer_and_close(c):
    read_until(c)
    c.sendall(OK200)
    time.sleep(0.2)
    c.close()


def _upstream_tagged(lines):
    return [(L["reason"], L["status"]) for L in lines if L["kind"] == "upstream"]


# ---- C1: the marker, the verdict

def test_r10_c1a_the_marker_is_written_once_per_launch_across_two_connections(outer, fn_stub, tmp_path):
    stub = fn_stub(_answer_and_close)
    log = str(tmp_path / "m1.log")
    o = outer(stub, allow=ALLOW, log=log)
    for _ in range(2):
        s = o.connect()
        s.sendall(req("GET", "/v1/models"))
        assert read_response(s)[0] == 200
        s.close()
    assert [l for l in log_lines(log) if l.startswith(MARKER)] == [MARKER]


def test_r10_c1_one_request_reached_the_endpoint_then_a_connect_fails_is_counted_not_flagged(outer, fn_stub, tmp_path):
    """The security seat's case: an endpoint that accepts one connection and then stops listening."""
    stub = fn_stub(_answer_and_close, one_shot=True)
    log = str(tmp_path / "m2.log")
    launch_line(log)
    o = outer(stub, allow=ALLOW, log=log)
    a = o.connect()
    a.sendall(req("GET", "/v1/models"))
    assert read_response(a)[0] == 200
    time.sleep(0.4)
    b = o.connect()
    b.sendall(req("GET", "/v1/models"))
    assert read_response(b)[0] == 502
    lines = log_lines(log)
    assert [l for l in lines if l.startswith(MARKER)] == [MARKER], lines
    assert _upstream_tagged(tagged_lines(log)) == [("connect-failed", "502")]
    assert verdict(log) == (0, "not-flagged", "")


def test_r10_c1_an_endpoint_down_from_the_start_is_flagged(outer, dead_port_stub, tmp_path):
    log = str(tmp_path / "m3.log")
    launch_line(log)
    o = outer(dead_port_stub, allow=ALLOW, log=log)
    s = o.connect()
    s.sendall(req("GET", "/v1/models"))
    assert read_response(s)[0] == 502
    lines = log_lines(log)
    assert not [l for l in lines if l.startswith(MARKER)], lines
    assert _upstream_tagged(tagged_lines(log)) == [("connect-failed", "502")]
    assert verdict(log) == (0, FLAGGED, "")


@pytest.mark.parametrize("kind", ["missing", "empty", "directory"])
def test_r10_c1c_a_log_that_is_missing_empty_or_unreadable_is_a_named_refusal(tmp_path, kind):
    log = str(tmp_path / "v.log")
    if kind == "empty":
        open(log, "w").close()
    elif kind == "directory":
        os.mkdir(log)
    rc, out, err = verdict(log)
    assert rc == 2 and out == "" and err.startswith("student-sandbox: refused:") and "log" in err, (rc, out, err)


@pytest.mark.parametrize("name,text,want", [
    ("only-connect-failed", "fwd-fault method=- path=- status=502 bytes_read=0 kind=upstream reason=connect-failed detail=x\n", FLAGGED),
    ("marker-and-connect-failed", MARKER + "\nfwd-fault method=- path=- status=502 bytes_read=0 kind=upstream reason=connect-failed detail=x\n", "not-flagged"),
    ("no-connect-failed", "fwd-conn id=1 open=1.0 close=2.0 up=0 down=0\n", "not-flagged"),
    ("another-upstream-line-only", "fwd-fault method=- path=- status=- bytes_read=0 kind=upstream reason=upstream-reset detail=x\n", "not-flagged"),
    ("a-path-cannot-fake-the-reason", "fwd-deny method=GET path=/kind=upstream status=403 bytes_read=0 kind=rule reason=not-on-allow-list detail=reason=connect-failed\n", "not-flagged"),
])
def test_r10_c1c_the_verdict_reads_line_kinds_and_reasons_only(tmp_path, name, text, want):
    log = str(tmp_path / (name + ".log"))
    open(log, "w").write(text)
    launch_line(log)
    assert verdict(log) == (0, want, ""), name


# ---- C2: rejected-early

@pytest.mark.parametrize("size", [12 << 20])
def test_r10_c2_a_big_body_rejected_early_is_one_rejected_early_line_not_flagged(outer, fn_stub, tmp_path, size):
    """The security seat's minting case: the endpoint answers 400 from the head and closes with the body unread."""
    def rejecting(c):
        read_until(c)
        c.sendall(REJECT400)
        time.sleep(0.2)             # the response is relayed before the close is answered by a reset
        c.close()
    stub = fn_stub(rejecting)
    log = str(tmp_path / "c2.log")
    launch_line(log)
    o = outer(stub, allow=ALLOW, log=log)
    s = o.connect()
    s.settimeout(20)
    raw = req("POST", "/v1/messages", body=b"x" * size)
    _send(s, raw)
    assert read_response(s) == (400, {"content-length": "5"}, b"nope!")     # the endpoint's own answer, intact
    lines = tagged_lines(log)
    assert [(L["kind"], L["reason"], L["status"], L["method"], L["path"]) for L in lines] == [
        ("upstream", "rejected-early", "unknown", "POST", "/v1/messages")], lines
    d = lines[0]["detail"]
    assert "attempted=%d" % len(raw) in d and re.search(r"sent=\d+", d) and "relayed=%d" % len(REJECT400) in d, d
    assert verdict(log) == (0, "not-flagged", "")


def test_r10_c2_at_256k_the_send_may_complete_before_the_reset_and_the_line_is_still_one_unflagged_upstream_line(outer, fn_stub, tmp_path):
    """Measured: a 256 KiB body fits the kernel's buffers, so the send COMPLETES before the endpoint's reset arrives and the
    relay (not the send site) sees the failure after the 400 was relayed: that is `upstream-reset`, not `rejected-early`.
    Either way the student cannot make it a flag: one counted line, and the verdict stays not-flagged."""
    def rejecting(c):
        read_until(c)
        c.sendall(REJECT400)
        time.sleep(0.2)
        c.close()
    stub = fn_stub(rejecting)
    log = str(tmp_path / "c2c.log")
    launch_line(log)
    o = outer(stub, allow=ALLOW, log=log)
    s = o.connect()
    s.settimeout(20)
    _send(s, req("POST", "/v1/messages", body=b"x" * (256 << 10)))
    assert read_response(s) == (400, {"content-length": "5"}, b"nope!")
    lines = _upstream_tagged(tagged_lines(log))
    assert len(lines) == 1 and lines[0][0] in ("rejected-early", "upstream-reset"), lines
    assert verdict(log) == (0, "not-flagged", "")


def test_r10_c2_a_64k_body_the_endpoint_does_not_fail_on_writes_no_upstream_line(outer, fn_stub, tmp_path):
    def rejecting(c):
        read_until(c)
        c.sendall(REJECT400)
        time.sleep(0.2)
        c.close()
    stub = fn_stub(rejecting)
    log = str(tmp_path / "c2b.log")
    o = outer(stub, allow=ALLOW, log=log)
    s = o.connect()
    s.settimeout(20)
    _send(s, req("POST", "/v1/messages", body=b"x" * (64 << 10)))
    assert read_response(s)[0] == 400
    s.close()
    assert _upstream_tagged(tagged_lines(log)) == []


# ---- C4 and PL: what the relay knows of the request being sent

def test_r10_c4_a_reset_before_the_request_is_sent_and_no_response_is_send_failed_not_upstream_reset(outer, fn_stub, tmp_path):
    def resetting(c):
        read_until(c)
        rst_close(c)                # no response, a reset while the rest of the request is still being sent
    stub = fn_stub(resetting)
    log = str(tmp_path / "c4.log")
    o = outer(stub, allow=ALLOW, log=log)
    s = o.connect()
    s.settimeout(20)
    _send(s, req("POST", "/v1/messages", body=b"x" * (12 << 20)))
    try:
        while s.recv(65536):
            pass
    except OSError:
        pass
    assert _upstream_tagged(tagged_lines(log)) == [("send-failed", "-")]


def test_r10_pl_a_second_request_whose_send_fails_with_no_response_to_it_is_send_failed(outer, fn_stub, tmp_path):
    """The response counter is per connection: the first request's response must not make the second's failure rejected-early."""
    def first_ok_then_reset(c):
        read_until(c)
        c.sendall(OK200)
        c.recv(65536)               # the second request begins to arrive
        rst_close(c)
    stub = fn_stub(first_ok_then_reset)
    log = str(tmp_path / "pl.log")
    o = outer(stub, allow=ALLOW, log=log)
    s = o.connect()
    s.settimeout(20)
    s.sendall(req("GET", "/v1/models"))
    assert read_response(s)[0] == 200
    _send(s, req("POST", "/v1/messages", body=b"x" * (12 << 20)))
    try:
        while s.recv(65536):
            pass
    except OSError:
        pass
    assert _upstream_tagged(tagged_lines(log)) == [("send-failed", "-")]


# ---- P1: our own FIN is not the endpoint's fault; P3: one upstream line per connection

def test_r10_p1_an_endpoint_that_resets_in_answer_to_our_own_fin_writes_no_upstream_line(outer, fn_stub, tmp_path):
    def reset_on_fin(c):
        read_until(c)
        c.sendall(OK200)
        while c.recv(65536):        # until our FIN
            pass
        rst_close(c)
    stub = fn_stub(reset_on_fin)
    log = str(tmp_path / "p1.log")
    o = outer(stub, allow=ALLOW, log=log)
    s = o.connect()
    s.sendall(req("GET", "/v1/models"))
    assert read_response(s)[0] == 200
    s.close()                       # the bridge now shuts the endpoint's side: that FIN is ours
    assert _upstream_tagged(tagged_lines(log)) == []


def test_r10_p3_an_endpoint_that_both_resets_and_fails_the_send_gives_exactly_one_upstream_line(outer, fault_stub, tmp_path):
    stub = fault_stub("reset-mid-response")
    log = str(tmp_path / "p3.log")
    o = outer(stub, allow=ALLOW, log=log)
    s = o.connect()
    s.settimeout(10)
    s.sendall(req("GET", "/v1/models"))
    try:
        while s.recv(65536):        # the partial response, then the end: the relay writes upstream-reset
            pass
    except OSError:
        pass
    time.sleep(0.5)
    _send(s, req("POST", "/v1/messages", body=b"x" * 100))     # the next request on the same connection: its send fails
    time.sleep(0.5)
    assert _upstream_tagged(tagged_lines(log)) == [("upstream-reset", "-")]


def test_r10_the_readme_states_the_status_definition_the_flag_rule_and_the_pipelining_limit():
    text = _readme_text()
    for needle in ("`status=unknown`", "`log-verdict`", "`fwd-first-request`", "section 14", "PIPELINES", "what the client received for this request"):
        assert needle in text, needle
    assert "unreachable-at-start" not in text


def test_r10_c1a_a_connect_followed_by_a_send_that_moves_no_bytes_writes_no_marker(tmp_path):
    """The marker means a request's bytes were WRITTEN upstream. An endpoint that accepts and resets before any byte is
    taken (the connect succeeds, the first send raises, nothing moved) is not 'reached': no marker; the line is
    `send-failed`, there is no connect-failed line, so log-verdict says not-flagged. Driven in-process through the
    `connect` seam so the zero-bytes outcome is deterministic (a real loopback reset races the first send)."""
    mod = _load_forwarder()

    class ResettingEndpoint:
        def send(self, data):
            raise ConnectionResetError("reset before any byte was taken")

        def recv(self, n):
            return b""

        def shutdown(self, how):
            pass

        def close(self):
            pass

    log = str(tmp_path / "zero.log")
    launch_line(log)
    a, b = socket.socketpair()
    a.settimeout(10)
    budget = mod.Budget(1 << 20, 1 << 22, 4, log, False)
    t = threading.Thread(target=mod.handle_http, args=(b, ResettingEndpoint, log, mod.parse_allow(ALLOW), False, budget, 30,
                                                       mod.Launch()), daemon=True)
    t.start()
    a.sendall(req("GET", "/v1/models"))
    t.join(10)
    assert not t.is_alive()
    lines = log_lines(log)
    assert not [l for l in lines if l.startswith(MARKER)], lines
    assert _upstream_tagged(tagged_lines(log)) == [("send-failed", "-")]
    assert verdict(log) == (0, "not-flagged", "")
    a.close()


# ---------------------------------------------------------------- follow-up to round 10: one log per launch; verdict matching; reset limits
# L: `log-verdict` counts launches (the wrapper APPENDS to SANDBOX_LOG, so two launches on one log merge: the first launch's
# marker would hide the second's unreachable endpoint). V: the verdict's line matching is pinned against imitation. R: the
# reset limits that are stated, and the one deferred write, are pinned.

def test_followup_l_a_two_launches_on_one_log_are_refused_not_merged(outer, fn_stub, dead_port_stub, tmp_path):
    """Launch 1 reaches a live endpoint (marker written); launch 2, on the SAME log, finds the endpoint dead. Merged, the
    first launch's marker hid the second's unreachable endpoint (the round-10 head printed `not-flagged` here)."""
    live = fn_stub(_answer_and_close)
    log = str(tmp_path / "la.log")
    launch_line(log)
    o1 = outer(live, allow=ALLOW, log=log)
    a = o1.connect()
    a.sendall(req("GET", "/v1/models"))
    assert read_response(a)[0] == 200
    a.close()
    launch_line(log)
    o2 = outer(dead_port_stub, allow=ALLOW, log=log)
    b = o2.connect()
    b.sendall(req("GET", "/v1/models"))
    assert read_response(b)[0] == 502
    lines = log_lines(log)
    assert [l for l in lines if l.startswith(MARKER)] == [MARKER], lines
    assert _upstream_tagged(tagged_lines(log)) == [("connect-failed", "502")]
    assert verdict(log) == (2, "", refused_count(2))


def test_followup_l_b_a_log_written_by_the_forwarder_alone_has_no_launch_line_and_is_refused(outer, fn_stub, tmp_path):
    stub = fn_stub(_answer_and_close)
    log = str(tmp_path / "lb.log")
    o = outer(stub, allow=ALLOW, log=log)
    s = o.connect()
    s.sendall(req("GET", "/v1/models"))
    assert read_response(s)[0] == 200
    log_lines(log)
    assert verdict(log) == (2, "", refused_count(0))


CF_LINE = "fwd-fault method=- path=- status=502 bytes_read=0 kind=upstream reason=connect-failed detail=x"


@pytest.mark.parametrize("name,extra,want", [
    ("one-launch-and-a-dead-endpoint-from-the-start", [CF_LINE], FLAGGED),
    ("one-launch-marker-then-a-later-connect-failed", [MARKER, CF_LINE], "not-flagged"),
])
def test_followup_l_c_exactly_one_launch_line_gives_the_round_10_verdicts(tmp_path, name, extra, want):
    log = str(tmp_path / (name + ".log"))
    launch_line(log)
    open(log, "a").write("".join(l + "\n" for l in extra))
    assert verdict(log) == (0, want, ""), name


def test_followup_l_d_a_refused_request_whose_path_carries_the_launch_token_is_not_a_second_launch(outer, dead_port_stub, tmp_path):
    """A client cannot make a launch line: its path is logged raw after `method=`, never at the start of a line. (A raw
    space cannot be in a request target, so the token is carried as `wrapper-launch%20`.)"""
    log = str(tmp_path / "ld.log")
    launch_line(log)
    o = outer(dead_port_stub, allow=ALLOW, log=log)
    s = o.connect()
    s.sendall(req("GET", "/wrapper-launch%20x"))
    assert read_response(s)[0] == 403
    lines = log_lines(log)
    assert [L["path"] for L in tagged_lines(log)] == ["/wrapper-launch%20x"], lines
    assert verdict(log) == (0, "not-flagged", "")


@pytest.mark.parametrize("impostor", [" wrapper-launch x", "wrapper-launchx", "wrapper-launch"])
def test_followup_l_e_only_the_token_and_one_space_at_column_zero_counts(tmp_path, impostor):
    log = str(tmp_path / "le.log")
    launch_line(log)
    open(log, "a").write(impostor + "\n")
    assert verdict(log) == (0, "not-flagged", "")


def test_followup_v_a_a_real_request_imitating_a_connect_failed_line_keeps_its_path_verbatim_and_does_not_flag(outer, dead_port_stub, tmp_path):
    """Through the bridge, endpoint dead and the request refused by rule (not on the allow-list, 403): the logged path
    keeps `%20` verbatim, and the line is not a connect-failed line, so nothing flags."""
    log = str(tmp_path / "va.log")
    launch_line(log)
    o = outer(dead_port_stub, allow=ALLOW, log=log)
    s = o.connect()
    imitation = "/v1/models%20kind=upstream%20reason=connect-failed"
    s.sendall(req("GET", imitation))
    assert read_response(s)[0] == 403
    lines = tagged_lines(log)
    assert [(L["kind"], L["reason"], L["path"]) for L in lines] == [("rule", "not-on-allow-list", imitation)], lines
    assert verdict(log) == (0, "not-flagged", "")


def test_followup_v_b_a_connect_failed_shape_with_text_before_it_is_not_a_connect_failed_line(tmp_path):
    log = str(tmp_path / "vb.log")
    launch_line(log)
    open(log, "a").write("noise " + CF_LINE + "\n")
    assert verdict(log) == (0, "not-flagged", "")


def test_followup_v_c_a_request_refused_with_the_marker_text_in_its_path_is_not_the_marker(outer, dead_port_stub, tmp_path):
    log = str(tmp_path / "vc.log")
    launch_line(log)
    o = outer(dead_port_stub, allow=ALLOW, log=log)
    s = o.connect()
    s.sendall(req("GET", "/fwd-first-request"))
    assert read_response(s)[0] == 403
    t = o.connect()
    t.sendall(req("GET", "/v1/models"))
    assert read_response(t)[0] == 502
    lines = log_lines(log)
    assert [l for l in lines if "fwd-first-request" in l and l != MARKER], lines     # the raw path IS in the log
    assert not [l for l in lines if l == MARKER], lines
    assert verdict(log) == (0, FLAGGED, "")


def test_followup_r1_a_client_that_half_closes_hides_a_later_upstream_reset_the_stated_limit(outer, fn_stub, tmp_path):
    """Pins a limit stated in the README, in force since round 10: once the bridge has sent its own FIN upstream (the client
    half-closed), a later reset from the endpoint is not logged, because our FIN could have provoked it. Descriptive only:
    nothing flags on it. The stub resets only after it has seen that FIN, so the order is deterministic."""
    def reset_after_our_fin(c):
        read_until(c)
        c.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\nhalf")
        while c.recv(65536):        # until the bridge's own FIN
            pass
        rst_close(c)
    stub = fn_stub(reset_after_our_fin)
    log = str(tmp_path / "r1.log")
    launch_line(log)
    o = outer(stub, allow=ALLOW, log=log)
    s = o.connect()
    s.settimeout(10)
    s.sendall(req("GET", "/v1/models"))
    s.shutdown(socket.SHUT_WR)
    try:
        while s.recv(65536):
            pass
    except OSError:
        pass
    assert _upstream_tagged(tagged_lines(log)) == []
    assert verdict(log) == (0, "not-flagged", "")


def test_followup_r2_a_reset_the_relay_sees_while_a_request_is_being_sent_is_written_once_by_the_send_site(tmp_path):
    """The parked reset: the relay sees the endpoint fail while the current request has not finished being sent, so it
    parks the failure; the send site writes the `upstream-reset` line after the send completes. Driven in-process through
    the `connect` seam: the endpoint's recv raises as soon as the send has begun, and the send then finishes."""
    mod = _load_forwarder()
    begun = threading.Event()

    class ParkingEndpoint:
        def send(self, data):
            begun.set()             # the relay's recv now fails while this send is still active
            time.sleep(0.4)         # time for the relay to park the failure
            return len(data)

        def recv(self, n):
            begun.wait(10)
            raise ConnectionResetError("reset while the request was being sent")

        def shutdown(self, how):
            pass

        def close(self):
            pass

    log = str(tmp_path / "r2.log")
    launch_line(log)
    a, b = socket.socketpair()
    a.settimeout(10)
    budget = mod.Budget(1 << 20, 1 << 22, 4, log, False)
    t = threading.Thread(target=mod.handle_http, args=(b, ParkingEndpoint, log, mod.parse_allow(ALLOW), False, budget, 30,
                                                       mod.Launch()), daemon=True)
    t.start()
    a.sendall(req("GET", "/v1/models"))
    a.shutdown(socket.SHUT_WR)
    t.join(10)
    assert not t.is_alive()
    assert _upstream_tagged(tagged_lines(log)) == [("upstream-reset", "-")]
    assert verdict(log) == (0, "not-flagged", "")
    a.close()


def test_followup_the_readme_states_one_log_per_launch_and_the_two_reset_limits():
    text = _readme_text()
    for needle in ("one log per launch", "exactly one line starting `wrapper-launch `", "harness setup error",
                   "a half-closing client hides a real mid-response reset", "the marker write is swallowed", "full disk"):
        assert needle in text, needle
