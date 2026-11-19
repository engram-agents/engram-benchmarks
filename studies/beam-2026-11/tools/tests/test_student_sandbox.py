"""Cells for tools/student-sandbox.sh (S1-S8). Synthetic fixtures only: no real data, no student model, no GPU.

The wrapper is the `claude` that feed4 resolves on PATH; these cells drive it through SANDBOX_TEST=1 /
SANDBOX_TEST_EXEC (a probe command run inside the same box, after the same checks and mounts) or through a stub
"pinned binary". No host path literal lives here: every location is generated at test time.
"""
import hashlib, json, os, shlex, shutil, signal, socket, socketserver, stat, subprocess, sys, tempfile, threading, time
import pytest

TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WRAPPER = os.path.join(TOOLS, "student-sandbox.sh")
FWD = os.path.join(TOOLS, "sandbox-forward.py")
FEED4 = os.path.join(TOOLS, "feed4.py")
PY = "/usr/bin/python3"
# The only names the wrapper itself puts under /run inside the box.
OWN_RUN_NAMES = {"sandbox-bridge.sock", "sandbox-forward.py"}


def _box_usable():
    if not shutil.which("bwrap"):
        return False
    return subprocess.run(["bwrap", "--unshare-all", "--ro-bind", "/", "/", "/usr/bin/true"],
                          capture_output=True).returncode == 0


needs_box = pytest.mark.skipif(not _box_usable(), reason="bwrap or unprivileged user namespaces unavailable")


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

    def set_binary(self, text):
        make_exe(self.binary, text)
        self.sha = sha256_of(self.binary)

    def env(self, test=True, exec_=None, drop=(), **extra):
        e = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": self.slot, "TERM": "dumb", "LANG": "C.UTF-8",
             "ANTHROPIC_BASE_URL": "http://localhost:%d" % self.model_port, "ANTHROPIC_AUTH_TOKEN": "ollama",
             "ANTHROPIC_API_KEY": "", "DISABLE_TELEMETRY": "1", "DISABLE_AUTOUPDATER": "1",
             "PROCTOR_DIR": os.path.join(self.slot, "proctor"), "TMPDIR": self.tmpd,
             "SANDBOX_SLOT": self.slot, "SANDBOX_BINARY": self.binary, "SANDBOX_BINARY_SHA256": self.sha,
             "SANDBOX_MODEL_HOST": "127.0.0.1", "SANDBOX_MODEL_PORT": str(self.model_port)}
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


REQUIRED = ["SANDBOX_SLOT", "SANDBOX_BINARY", "SANDBOX_BINARY_SHA256", "SANDBOX_MODEL_HOST", "SANDBOX_MODEL_PORT"]


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
    host_ro = [p for p in ("/usr", "/etc", "/lib", "/lib64", "/bin", "/sbin", "/opt") if os.path.isdir(p)]
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
                    args=paths, BEAM_PARQUET=p)
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


@needs_box
def test_s3_die_with_parent_when_wrapper_is_killed(cfg):
    mark = "8%d" % (int(time.time() * 1000) % 10**9)
    p = subprocess.Popen(["/bin/bash", WRAPPER], env=cfg.env(exec_='sleep 400.%s' % mark),
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        end = time.time() + 10
        while time.time() < end and not any(b"sleep" in open("/proc/%d/cmdline" % q, "rb").read()
                                           for q in procs_with(".%s" % mark) if os.path.exists("/proc/%d/cmdline" % q)):
            time.sleep(0.05)
        assert procs_with(".%s" % mark), "probe never started"
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
        s.sendall(b"GET / HTTP/1.0\r\n\r\n"); data = b""
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
    assert r.stdout == "to-out\n" and r.stderr == "to-err\n"


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

@needs_box
def test_s8_forwarder_logs_counts_and_timings_never_payloads(cfg, stubs):
    model = stubs("PAYLOAD-MARKER-ZZZ")
    cfg.model_port = model.port
    probe = '%s -I -c \'import socket; s=socket.create_connection(("127.0.0.1",%d)); s.sendall(b"REQUEST-SECRET-QQQ"); d=b""\n' \
            'while True:\n c=s.recv(99)\n if not c: break\n d+=c\nprint(d.decode())\'' % (PY, model.port)
    r = cfg.run(exec_=probe, SANDBOX_LOG=cfg.log)
    assert r.returncode == 0 and "PAYLOAD-MARKER-ZZZ" in r.stdout, r.stderr
    time.sleep(0.5)
    text = open(cfg.log).read()
    assert "PAYLOAD-MARKER-ZZZ" not in text and "REQUEST-SECRET-QQQ" not in text
    conns = [l for l in text.splitlines() if l.startswith("fwd-conn ")]
    assert len(conns) == 1, text
    f = dict(kv.split("=", 1) for kv in conns[0].split()[1:])
    assert float(f["close"]) >= float(f["open"]) > 1e9
    assert int(f["up"]) == len(b"REQUEST-SECRET-QQQ") and int(f["down"]) == len(b"PAYLOAD-MARKER-ZZZ")
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


SHARED = os.path.join("/home", "agents-shared")  # joined so that no host path literal sits in the file


def user_home():
    import pwd
    return os.path.realpath(pwd.getpwuid(os.getuid()).pw_dir)


def test_f2_refusals_entry_shapes(cfg, fake_bwrap, extra):
    f = os.path.join(extra.base, "afile")
    open(f, "w").close()
    nosuch = os.path.join(extra.base, "no-such")
    for val in ("relative/dir", nosuch, f, extra.tools + ":" + nosuch,
                extra.tools + ":", ":" + extra.tools, extra.tools + "::" + extra.secret):
        assert_refused(cfg, fake_bwrap, "SANDBOX_RO_BINDS", SANDBOX_RO_BINDS=val)


def _protected_refused(cfg, fake_bwrap, var, val, **kw):
    fdir, out = fake_bwrap
    r = cfg.run(exec_="true", PATH=fdir + ":/usr/bin:/bin", FAKE_BWRAP_OUT=out, SANDBOX_LOG=cfg.log, **{var: val}, **kw)
    assert r.returncode == 2, (val, r.returncode, r.stderr)
    lines = [l for l in r.stderr.splitlines() if l.strip()]
    assert len(lines) == 1 and var in lines[0] and "protected" in lines[0], r.stderr
    assert not os.path.exists(out) and os.listdir(cfg.tmpd) == [] and not os.path.exists(cfg.log)


def test_f2_refuses_the_filesystem_root(cfg, fake_bwrap):
    _protected_refused(cfg, fake_bwrap, "SANDBOX_RO_BINDS", "/")


def test_f2_refuses_the_invoking_users_home_and_its_ancestors(cfg, fake_bwrap):
    h = user_home()
    assert os.path.isdir(h)
    for e in {h, os.path.dirname(h)}:
        if e != "/":
            _protected_refused(cfg, fake_bwrap, "SANDBOX_RO_BINDS", e)


def test_f2_refuses_home_and_agents_shared(cfg, fake_bwrap):
    if not os.path.isdir(SHARED):
        pytest.skip("no shared agents directory under /home on this host: the entry would be refused as nonexistent, not as protected")
    _protected_refused(cfg, fake_bwrap, "SANDBOX_RO_BINDS", "/home")
    _protected_refused(cfg, fake_bwrap, "SANDBOX_RO_BINDS", SHARED)


def test_f2_refuses_the_slots_parent_and_its_ancestors(cfg, fake_bwrap):
    _protected_refused(cfg, fake_bwrap, "SANDBOX_RO_BINDS", cfg.root)
    _protected_refused(cfg, fake_bwrap, "SANDBOX_RO_BINDS", os.path.dirname(cfg.root))


def test_f2_refuses_the_dataset_directory_and_its_ancestors(cfg, fake_bwrap, tmp_path):
    d = tmp_path / "data" / "inner"
    d.mkdir(parents=True)
    p = str(d / "standin.parquet")
    open(p, "w").close()
    _protected_refused(cfg, fake_bwrap, "SANDBOX_RO_BINDS", str(d), BEAM_PARQUET=p)
    _protected_refused(cfg, fake_bwrap, "SANDBOX_RO_BINDS", str(d.parent), BEAM_PARQUET=p)
    _protected_refused(cfg, fake_bwrap, "SANDBOX_RW_BINDS", str(d), BEAM_PARQUET=p, SANDBOX_RW_ROOT=str(d.parent))


def test_f2_refuses_the_scratch_directories(cfg, fake_bwrap):
    for e in ("/tmp", "/var/tmp"):
        _protected_refused(cfg, fake_bwrap, "SANDBOX_RO_BINDS", e)


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


def test_f2_refuses_an_rw_entry_that_is_the_home(cfg, fake_bwrap):
    _protected_refused(cfg, fake_bwrap, "SANDBOX_RW_BINDS", user_home(), SANDBOX_RW_ROOT=os.path.dirname(user_home()))


@needs_box
def test_f2_ro_bind_is_visible_not_writable_and_its_sibling_is_not(cfg, extra):
    r = cfg.run(exec_='test -x "$1/ask-proctor" && echo TOOL; (touch "$1/x") 2>/dev/null && echo WROTE; '
                      '(: > "$1/ask-proctor") 2>/dev/null && echo CLOBBERED; test -e "$2" && echo SECRET; '
                      'test -e "$3/key" && echo KEY; ls -A "$4"; echo done',
                args=[extra.tools, extra.base + "/secret", extra.secret, extra.base], SANDBOX_RO_BINDS=extra.tools)
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
                SANDBOX_RO_BINDS=extra.tools, SANDBOX_RW_BINDS=extra.proctor + ":" + second, SANDBOX_RW_ROOT=extra.runout)
    assert r.returncode == 0 and r.stdout.strip() == "ok", r.stderr
    assert os.path.exists(os.path.join(extra.proctor, "a")) and os.path.exists(os.path.join(second, "b"))


@needs_box
def test_f2_ask_proctor_works_from_inside(cfg, extra):
    r = cfg.run(exec_='ask-proctor what is this; echo "$PROCTOR_DIR"', PATH=extra.tools + ":/usr/bin:/bin",
                PROCTOR_DIR=extra.proctor, SANDBOX_RO_BINDS=extra.tools, SANDBOX_RW_BINDS=extra.proctor,
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
                    BEAM_PARQUET=p, SANDBOX_RO_BINDS=sib)
        assert r.returncode == 0, r.stderr
        assert r.stdout.split() == ["SIBLING-BOUND", "done"], r.stdout
        # binding the home itself must be refused, and must never make the stand-in visible
        r = cfg.run(exec_='test -e "$1" && echo STANDIN-VISIBLE; echo done', args=[p], BEAM_PARQUET=p,
                    SANDBOX_RO_BINDS=home)
        assert "STANDIN-VISIBLE" not in r.stdout, "the stand-in became visible through an ancestor bind"
        assert r.returncode == 2 and "protected" in r.stderr, (r.returncode, r.stderr)
    finally:
        shutil.rmtree(d, ignore_errors=True)
        shutil.rmtree(sib, ignore_errors=True)


@needs_box
def test_f2_launch_line_logs_every_extra_bind(cfg, extra):
    r = cfg.run(exec_="true", SANDBOX_LOG=cfg.log, SANDBOX_RO_BINDS=extra.tools, SANDBOX_RW_BINDS=extra.proctor,
                SANDBOX_RW_ROOT=extra.runout)
    assert r.returncode == 0, r.stderr
    line = [l for l in open(cfg.log).read().splitlines() if l.startswith("wrapper-launch ")][0]
    assert "ro_binds=" + extra.tools in line and "rw_binds=" + extra.proctor in line, line
