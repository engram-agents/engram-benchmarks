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
        _refused(cfg, fake_bwrap, "SANDBOX_RO_ROOT", "dataset", SANDBOX_RO_BINDS=str(d), SANDBOX_RO_ROOT=root, BEAM_PARQUET=p)
        _refused(cfg, fake_bwrap, "SANDBOX_RW_ROOT", "dataset", SANDBOX_RW_BINDS=str(d), SANDBOX_RW_ROOT=root, BEAM_PARQUET=p)
    # control: the same tree is fine when the dataset is elsewhere
    _accepted(cfg, fake_bwrap, SANDBOX_RO_BINDS=str(d), SANDBOX_RO_ROOT=str(d.parent), BEAM_PARQUET=os.path.join(cfg.root, "elsewhere.parquet"))
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
    _refused(cfg, fake_bwrap, "SANDBOX_SLOT", "dataset", BEAM_PARQUET=os.path.join(cfg.slot, "work", "standin.parquet"))
    _refused(cfg, fake_bwrap, "SANDBOX_SLOT", "dataset", BEAM_PARQUET=os.path.join(cfg.slot, "work", "standin.parquet"),
             SANDBOX_SLOT=os.path.join(cfg.slot, "work"))
    _refused(cfg, fake_bwrap, "SANDBOX_SLOT", "binary", SANDBOX_SLOT=cfg.root)
    _refused(cfg, fake_bwrap, "SANDBOX_SLOT", "binary", SANDBOX_SLOT=cfg.bindir)
    _accepted(cfg, fake_bwrap, BEAM_PARQUET=os.path.join(cfg.root, "elsewhere.parquet"))


def test_r2_slot_inside_a_dot_directory_of_a_home(cfg, fake_bwrap, tmp_path):
    fake = tmp_path / "fakehome"
    (fake / ".cfg" / "slot").mkdir(parents=True)
    (fake / "slot").mkdir()
    kw = {"SANDBOX_TEST_EXTRA_HOMES": str(fake)}
    _refused(cfg, fake_bwrap, "SANDBOX_SLOT", "dot-directory", SANDBOX_SLOT=str(fake / ".cfg" / "slot"), **kw)
    _refused(cfg, fake_bwrap, "SANDBOX_SLOT", "dot-directory", SANDBOX_SLOT=str(fake / ".cfg"), **kw)
    _accepted(cfg, fake_bwrap, SANDBOX_SLOT=str(fake / "slot"), **kw)   # a slot under a home is fine when no dot


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
                    BEAM_PARQUET=p, SANDBOX_RO_BINDS=sib, SANDBOX_RO_ROOT=sib)
        assert r.returncode == 0, r.stderr
        assert r.stdout.split() == ["SIBLING-BOUND", "done"], r.stdout
        # binding the home itself must be refused, and must never make the stand-in visible
        r = cfg.run(exec_='test -e "$1" && echo STANDIN-VISIBLE; echo done', args=[p], BEAM_PARQUET=p,
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


def _other_account_names():
    """Account names from the HOST's database at test time, other than root and the invoker."""
    import pwd
    me = pwd.getpwuid(os.getuid()).pw_name
    return sorted({u.pw_name for u in pwd.getpwall()} - {"root", me})


def _name_rx(names):
    import re
    if not names:
        return None
    alt = b"|".join(re.escape(n.encode()) for n in names)
    return re.compile(rb"(?:^|[:,])(?:" + alt + rb")(?=[:,\n]|$)", re.M)


def _host_etc_masked():
    """The class rule, restated independently of the wrapper: every readable regular file under /etc (symlinks not
    followed) whose content contains '/home/' or an account name other than root and the invoker as a whole
    colon/comma-delimited token, except the four files that are replaced by synthetic ones."""
    rx = _name_rx(_other_account_names())
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
names = [n.encode() for n in sys.argv[1:]]
rx = re.compile(rb"(?:^|[:,])(?:" + b"|".join(re.escape(n) for n in names) + rb")(?=[:,\n]|$)", re.M) if names else None
bad = []
for dp, dn, fn in os.walk("/etc"):
    for f in fn:
        p = os.path.join(dp, f)
        if os.path.islink(p) or not os.path.isfile(p) or not os.access(p, os.R_OK):
            continue
        try:
            d = open(p, "rb").read()
        except OSError:
            continue
        if b"/home/" in d or (rx is not None and rx.search(d)):
            bad.append(p)
print("BAD", len(bad))
'''


@needs_box
def test_r4_no_readable_file_under_etc_names_a_home_or_another_account(cfg):
    """Class check from inside the box, against the HOST's account database now."""
    names = _other_account_names()
    assert names, "the host account database lists no account other than root and the invoker"
    pf = os.path.join(cfg.slot, "etcprobe.py")
    open(pf, "w").write(ETC_PROBE)
    r = cfg.run(exec_='%s -I %s "$@"' % (PY, shlex.quote(pf)), args=names)
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == ["BAD", "0"], r.stdout


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
