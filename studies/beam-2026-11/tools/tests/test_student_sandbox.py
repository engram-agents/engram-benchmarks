"""Cells for tools/student-sandbox.sh (S1-S8). Synthetic fixtures only: no real data, no student model, no GPU.

The wrapper is the `claude` that feed4 resolves on PATH; these cells drive it through SANDBOX_TEST=1 /
SANDBOX_TEST_EXEC (a probe command run inside the same box, after the same checks and mounts) or through a stub
"pinned binary". No host path literal lives here: every location is generated at test time.
"""
import hashlib, json, os, re, shlex, shutil, signal, socket, socketserver, stat, subprocess, sys, tempfile, threading, time
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


def _box_usable():
    if not sys.platform.startswith("linux") or not _bash4() or not shutil.which("bwrap"):
        return False
    return subprocess.run(["bwrap", "--unshare-all", "--ro-bind", "/", "/", "/usr/bin/true"],
                          capture_output=True).returncode == 0


# The tool is Linux-only. Every cell that runs the wrapper (or its box) skips, with this reason, where the host cannot.
NEEDS_BOX_REASON = "needs Linux, bash 4 or newer, and a working bwrap (unprivileged user namespaces): the sandbox is Linux-only"
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

@pytest.fixture
def fake_bwrap(tmp_path):
    d = tmp_path / "fakebin"
    d.mkdir()
    out = str(tmp_path / "bwrap-called")
    make_exe(str(d / "bwrap"), "#!/bin/sh\necho \"$$ $*\" > \"$FAKE_BWRAP_OUT\"\nexit 99\n")
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
             '#!/bin/sh\necho "$$ $*" > "$FAKE_BWRAP_OUT"\nfd=; dest=\n'
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
                 max_conns=64):
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
    assert [l for l in text.splitlines() if l.startswith("fwd-deny ")] == ["fwd-deny method=DELETE path=/api/delete"], text
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
             "--chdir": (1, None), "--uid": (1, None), "--gid": (1, None)}
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
    make_exe(str(d / "bwrap"), '#!/bin/sh\nprintf "%s\\n" "$@" > "$FAKE_BWRAP_OUT"\nexit 99\n')
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
    assert [l for l in text.splitlines() if l.startswith("fwd-deny ")] == ["fwd-deny method=POST path=/v1/messages"], text
    assert "SECRET" not in text and "frag" not in text


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
    m = re.fullmatch(r"fwd-refuse method=POST path=/v1/messages status=400 bytes_read=(\d+) reason=(.+)", lines[0])
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
                "cap_total": str(64 << 20), "cap_conns": "4"}
TEST_CAPS = {"SANDBOX_TEST_TMP_CAP": "1111111", "SANDBOX_TEST_HOME_RUN_CAP": "2222222",
             "SANDBOX_TEST_MAX_REQUEST": "3333333", "SANDBOX_TEST_MAX_TOTAL": "4444444", "SANDBOX_TEST_MAX_CONNS": "7"}
TEST_CAPS_LOGGED = {"cap_tmp": "1111111", "cap_home_run": "2222222", "cap_request": "3333333", "cap_total": "4444444",
                    "cap_conns": "7"}


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
    for name in ("SANDBOX_TEST_MAX_REQUEST", "SANDBOX_TEST_MAX_TOTAL", "SANDBOX_TEST_MAX_CONNS"):
        for bad in ("0", "-1", "ten", "1.5", "007x"):
            assert_refused(cfg, fake_bwrap, name, **{name: bad})
