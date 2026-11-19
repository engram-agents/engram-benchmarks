#!/usr/bin/python3 -I
"""Bridge forwarder for tools/student-sandbox.sh. Python standard library only; payloads are never logged.

The sandbox has its own network namespace, so the student's model endpoint is carried by two forwarders and a UNIX
socket, and nothing else crosses:

  outer  (host side, started by the wrapper before the box)  UNIX socket  ->  <SANDBOX_MODEL_HOST>:<SANDBOX_MODEL_PORT>
         Records one line per connection to SANDBOX_LOG when set: open/close epoch seconds and bytes each way.
         Exits (and removes its socket and directory) when the watched pid, the wrapper that became the box, is gone.
  inner  (inside the box)  127.0.0.1:<port>  ->  the UNIX socket bind-mounted from outside.
         Forks into the background, then execs the command it was given, so the student is the main process.

  latency / latency-compare   measurement helper (S8): median and max round trip through the bridge vs direct.
  homes   wrapper helper: every account home in the host's account database, resolved, NUL-separated.

Usage (internal): outer --sock S --host H --port P --watch PID [--log FILE]
                  inner --sock S --port P [--unset NAME]... -- CMD [ARG...]
                  latency --host H --port P -n N
                  latency-compare --wrapper PATH -n N      (reads the SANDBOX_* environment, like the wrapper)
"""
import argparse, os, shlex, socket, statistics, subprocess, sys, threading, time

LOCK = threading.Lock()
COUNTER = [0]


def pipe(src, dst, counts, idx):
    """One direction. Counts bytes only."""
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
            counts[idx] += len(data)
    except OSError:
        pass
    finally:
        try:
            dst.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def handle(client, connect, log):
    with LOCK:
        COUNTER[0] += 1
        cid = COUNTER[0]
    t_open = time.time()
    counts = [0, 0]
    err = None
    try:
        upstream = connect()
    except OSError as e:
        upstream = None
        err = type(e).__name__
    if upstream is not None:
        up = threading.Thread(target=pipe, args=(client, upstream, counts, 0), daemon=True)
        down = threading.Thread(target=pipe, args=(upstream, client, counts, 1), daemon=True)
        up.start(); down.start(); up.join(); down.join()
        upstream.close()
    client.close()
    if log:
        line = "fwd-conn id=%d open=%.6f close=%.6f up=%d down=%d" % (cid, t_open, time.time(), counts[0], counts[1])
        if err:
            line += " error=" + err
        try:
            fd = os.open(log, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            try:
                os.write(fd, (line + "\n").encode())
            finally:
                os.close(fd)
        except OSError:
            pass


def serve(listener, connect, log):
    while True:
        try:
            client, _ = listener.accept()
        except OSError:
            return
        threading.Thread(target=handle, args=(client, connect, log), daemon=True).start()


def alive(pid):
    try:
        with open("/proc/%d/stat" % pid) as f:
            state = f.read().rpartition(")")[2].split()[0]
    except (OSError, IndexError):
        return False
    return state not in ("Z", "X")


def run_outer(a):
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    # AF_UNIX paths are limited to ~107 bytes and TMPDIR may be long: bind relative to the socket's directory.
    os.chdir(os.path.dirname(a.sock))
    listener.bind(os.path.basename(a.sock))
    os.chmod(a.sock, 0o600)
    listener.listen(64)

    def connect():
        return socket.create_connection((a.host, a.port), timeout=10)

    threading.Thread(target=serve, args=(listener, connect, a.log), daemon=True).start()
    try:
        while alive(a.watch):
            time.sleep(0.2)
    finally:
        for fn, arg in ((os.unlink, a.sock), (os.rmdir, os.path.dirname(a.sock))):
            try:
                fn(arg)
            except OSError:
                pass
    return 0


def run_inner(a):
    if not a.cmd:
        sys.stderr.write("student-sandbox: inner forwarder given no command\n")
        return 2
    # The exact environment this process was started with: the interpreter may add variables of its own
    # (locale coercion), and the student must receive only what the caller passed.
    with open("/proc/self/environ", "rb") as f:
        env = dict(kv.split(b"=", 1) for kv in f.read().split(b"\0") if b"=" in kv)
    for name in a.unset:
        env.pop(name.encode(), None)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", a.port))
    listener.listen(64)
    r, w = os.pipe()
    if os.fork() == 0:
        os.close(r)
        devnull = os.open(os.devnull, os.O_RDWR)
        for fd in (0, 1, 2):
            os.dup2(devnull, fd)

        def connect():
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(a.sock)
            return s

        os.write(w, b"1")
        os.close(w)
        serve(listener, connect, None)
        os._exit(0)
    os.close(w)
    if os.read(r, 1) != b"1":
        sys.stderr.write("student-sandbox: bridge listener did not start\n")
        return 3
    os.close(r)
    listener.close()
    try:
        os.execve(a.cmd[0], a.cmd, env)
    except OSError as e:
        sys.stderr.write("student-sandbox: cannot exec %s: %s\n" % (a.cmd[0], e.strerror))
        return 127


def run_homes(a):
    import pwd
    homes = {os.path.realpath(u.pw_dir) for u in pwd.getpwall() if u.pw_dir}
    sys.stdout.write("".join(h + "\0" for h in sorted(homes)))
    return 0


def one_request(host, port):
    t0 = time.perf_counter()
    s = socket.create_connection((host, port), timeout=10)
    s.sendall(b"GET /ping HTTP/1.0\r\nHost: bridge-latency\r\n\r\n")
    while s.recv(65536):
        pass
    s.close()
    return (time.perf_counter() - t0) * 1000.0


def measure(host, port, n):
    one_request(host, port)  # warm-up, not counted
    xs = [one_request(host, port) for _ in range(n)]
    return {"n": n, "median_ms": statistics.median(xs), "max_ms": max(xs)}


def fmt(label, m):
    return "%s n=%d median_ms=%.3f max_ms=%.3f" % (label, m["n"], m["median_ms"], m["max_ms"])


def run_latency(a):
    print(fmt("latency", measure(a.host, a.port, a.n)))
    return 0


def run_latency_compare(a):
    host, port = os.environ["SANDBOX_MODEL_HOST"], int(os.environ["SANDBOX_MODEL_PORT"])
    direct = measure(host, port, a.n)
    inside = "%s -I /run/sandbox-forward.py latency --host 127.0.0.1 --port %d -n %d" % (
        "/usr/bin/python3", port, a.n)
    env = dict(os.environ, SANDBOX_TEST="1", SANDBOX_TEST_EXEC=inside)
    r = subprocess.run(["/bin/bash", a.wrapper], env=env, capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.startswith("latency "):
        sys.stderr.write("latency-compare: the boxed measurement failed (exit %d): %s\n" % (r.returncode, r.stderr.strip()))
        return 1
    f = dict(kv.split("=") for kv in r.stdout.split()[1:])
    bridge = {"n": int(f["n"]), "median_ms": float(f["median_ms"]), "max_ms": float(f["max_ms"])}
    print(fmt("direct", direct))
    print(fmt("bridge", bridge))
    print("added n=%d median_ms=%.3f max_ms=%.3f" % (a.n, bridge["median_ms"] - direct["median_ms"],
                                                     bridge["max_ms"] - direct["max_ms"]))
    return 0


def main(argv):
    ap = argparse.ArgumentParser(prog="sandbox-forward.py")
    sub = ap.add_subparsers(dest="mode", required=True)
    o = sub.add_parser("outer")
    o.add_argument("--sock", required=True); o.add_argument("--host", required=True)
    o.add_argument("--port", type=int, required=True); o.add_argument("--watch", type=int, required=True)
    o.add_argument("--log")
    i = sub.add_parser("inner")
    i.add_argument("--sock", required=True); i.add_argument("--port", type=int, required=True)
    i.add_argument("--unset", action="append", default=[])
    i.add_argument("cmd", nargs="*")
    sub.add_parser("homes")
    la = sub.add_parser("latency")
    la.add_argument("--host", required=True); la.add_argument("--port", type=int, required=True)
    la.add_argument("-n", type=int, default=50)
    lc = sub.add_parser("latency-compare")
    lc.add_argument("--wrapper", required=True); lc.add_argument("-n", type=int, default=50)
    a = ap.parse_args(argv)
    return {"outer": run_outer, "inner": run_inner, "latency": run_latency,
            "latency-compare": run_latency_compare, "homes": run_homes}[a.mode](a)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
