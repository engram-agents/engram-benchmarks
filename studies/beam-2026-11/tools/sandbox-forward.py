#!/usr/bin/python3 -I
"""Bridge forwarder for tools/student-sandbox.sh. Python standard library only; payloads are never logged.

The sandbox has its own network namespace, so the student's model endpoint is carried by two forwarders and a UNIX
socket, and nothing else crosses:

  outer  (host side, started by the wrapper before the box)  UNIX socket  ->  <SANDBOX_MODEL_HOST>:<SANDBOX_MODEL_PORT>
         TRUSTED, and an HTTP request allow-list: it parses HTTP/1.1 requests on each connection (request line and
         headers; bodies by Content-Length or strictly chunked; keep-alive, several requests per connection) and forwards a
         request only if its METHOD and path are on the list (--allow, "METHOD /path" entries, exact path or a prefix
         ending in "*"). Any other request gets 403 and the connection closes; it never reaches the model server.
         A request that cannot be framed gets 400; CONNECT, Upgrade and non-origin-form targets get 403; an
         `Expect: 100-continue` gets 417 at once; a request line whose version is not exactly HTTP/1.1 gets 505. Chunked
         bodies are framed strictly: CRLF exactly (a bare CR or LF is 400), no chunk extension, no trailer (only the empty
         one), each piece checked before it is forwarded. A client that stops sending inside a request (or never starts one)
         for --read-idle-s seconds gets 408; a response being relayed is never timed.
         Every refusal is ONE log line carrying kind= (framing, cap, rule, or upstream for the bridge's own failure to reach
         the model endpoint, which answers 502) and a reason token unique to its site; see class Refusal.
         Responses, streamed ones included, are relayed byte for byte. --learn allows everything it can frame and
         check and logs each request's METHOD and PATH only (never a body, never a query string), so the harness's
         real set can be learned once and then fixed as the list.
         Records one line per connection to SANDBOX_LOG when set: open/close epoch seconds and bytes each way.
         Exits (and removes its socket and directory) when the watched pid, the wrapper that became the box, is gone.
  inner  (inside the box)  127.0.0.1:<port>  ->  the UNIX socket bind-mounted from outside. A raw relay: it checks
         nothing, because everything it carries passes the outer forwarder's list.
         Forks into the background, then execs the command it was given, so the student is the main process.

  latency / latency-compare   measurement helper (S8): median and max round trip through the bridge vs direct.
  check-allow --text LIST     wrapper helper: validate an allow-list (exit 2 with one reason on stderr).
  seccomp-bpf --out FILE   wrapper helper: write the box's seccomp program (key syscalls EPERM; other arch and x32 killed).
  homes   wrapper helper: every account home in the host's account database, resolved, NUL-separated.
  account-file passwd|group --home H   wrapper helper: the synthetic /etc/passwd or /etc/group of the box (root and the
          invoking uid/gid only; the invoker's home is H).
  etc-scan [--root DIR]   wrapper helper: the readable regular files under /etc (or DIR) that contain /home/ or the name of
          an account with uid >= 1000, as a whole word, NUL-separated.

Usage (internal): outer --sock S --host H --port P --watch PID (--allow LIST | --learn) [--log FILE]
                        --max-request N --max-total N --max-conns N --read-idle-s S [--scope-unit NAME]
                  inner --sock S --port P [--unset NAME]... -- CMD [ARG...]
                  latency --host H --port P -n N
                  latency-compare --wrapper PATH -n N      (reads the SANDBOX_* environment, like the wrapper)
"""
import argparse, os, re, select, shlex, socket, statistics, subprocess, sys, threading, time, urllib.parse

LOCK = threading.Lock()
COUNTER = [0]


def pipe(src, dst, counts, idx, wlock=None, shutdown_dst=True):
    """One direction, raw. Counts bytes only. `wlock` serialises writes to a socket two threads may write."""
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            if wlock is not None:
                with wlock:
                    dst.sendall(data)
            else:
                dst.sendall(data)
            counts[idx] += len(data)
    except OSError:
        pass
    finally:
        if shutdown_dst:
            try:
                dst.shutdown(socket.SHUT_WR)
            except OSError:
                pass


def write_log(log, line):
    if not log:
        return
    try:
        fd = os.open(log, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, (line + "\n").encode())
        finally:
            os.close(fd)
    except OSError:
        pass


def next_id():
    with LOCK:
        COUNTER[0] += 1
        return COUNTER[0]


def conn_line(cid, t_open, counts, err):
    line = "fwd-conn id=%d open=%.6f close=%.6f up=%d down=%d" % (cid, t_open, time.time(), counts[0], counts[1])
    return line + (" error=" + err if err else "")


def handle(client, connect, log):
    """Raw relay (the inner forwarder inside the box: it carries bytes to the UNIX socket and checks nothing)."""
    cid = next_id()
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
    write_log(log, conn_line(cid, t_open, counts, err))


def serve(listener, handler, admit=None):
    """Accept loop. `admit(client)` (the trusted side's connection cap) is called in this thread before a handler
    thread exists; when it returns False it has already answered and closed the client."""
    while True:
        try:
            client, _ = listener.accept()
        except OSError:
            return
        if admit is not None and not admit(client):
            continue
        threading.Thread(target=handler, args=(client,), daemon=True).start()


def connect_upstream(host, port):
    """The model endpoint. create_connection leaves its connect timeout on the socket as a receive timeout; a model
    that is slow to its first byte must not be cut by it, so the timeout applies to the connect only."""
    s = socket.create_connection((host, port), timeout=10)
    s.settimeout(None)
    return s


# ---------------------------------------------------------------- the outer forwarder: an HTTP request allow-list

MAX_HEAD = 64 * 1024
MAX_LINE = 8 * 1024
RE_REQLINE = re.compile(rb"([A-Z]{1,16}) ([\x21-\x7e]+) HTTP/([0-9])\.([0-9])")
RE_NAME = re.compile(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+")
RE_BADCTL = re.compile(rb"[\x00-\x08\x0a-\x1f\x7f]")
RE_LENGTH = re.compile(rb"[0-9]{1,15}")
RE_HEX = re.compile(rb"[0-9A-Fa-f]{1,15}")
RE_BARE = re.compile(rb"(?<!\r)\n|\r(?!\n|$)")
RE_ENTRY_PATH = re.compile(r"/[\x21-\x7e]*")
RESP_CLOSE = b"HTTP/1.1 %d %s\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"


class Refusal(Exception):
    """EVERY place the bridge refuses a request, or fails one for its own side, is one `Refusal(kind, reason, status, detail)`:
    the kind is one of the registered counts (framing, cap, rule) or `upstream` (a harness fault, never a student attempt);
    the reason is a short token that names the site and is unique to it; the status is the one answered. One refusal
    writes one line (refusal_line) and closes the connection, so a request is counted once, by the first refusal made.
    The three arguments are literals at every site: a test reads them out of this source with `ast`."""

    def __init__(self, kind, reason, status, detail=""):
        super().__init__(detail or reason)
        self.kind, self.reason, self.status, self.detail = kind, reason, status, detail or reason


PHRASE = {400: b"Bad Request", 403: b"Forbidden", 408: b"Request Timeout", 413: b"Payload Too Large",
          417: b"Expectation Failed", 502: b"Bad Gateway", 503: b"Service Unavailable",
          505: b"HTTP Version Not Supported"}


def refusal_response(ref):
    """The reply to a refusal: status line, no body, close. The only place the response template is used."""
    return RESP_CLOSE % (ref.status, PHRASE[ref.status])


def refusal_line(ref, method, path, bytes_read):
    """The one log line of a refusal, never a payload. The prefix is readable by kind (rule refusals are denials,
    an upstream fault is a fault, the rest are refusals) but a reader counts by `kind=`. The only place a line is built."""
    prefix = {"rule": "fwd-deny", "upstream": "fwd-fault"}.get(ref.kind, "fwd-refuse")
    return "%s method=%s path=%s status=%d bytes_read=%d kind=%s reason=%s detail=%s" % (
        prefix, method, path, ref.status, bytes_read, ref.kind, ref.reason, ref.detail)


class Budget:
    """The caps of the trusted side. The outer forwarder buffers a whole request before it sends a byte upstream, and a
    student controls what it sends, so every byte buffered is counted: per request (`max_request`, head and body), over
    all connections (`max_total`) and as concurrent connections (`max_conns`). In learn mode it also records the
    largest request, the most concurrent connections and the most buffered bytes seen, so the caps can be set from
    measurement. Counts only, never content."""

    def __init__(self, max_request, max_total, max_conns, log=None, learn=False):
        self.max_request, self.max_total, self.max_conns = max_request, max_total, max_conns
        self.log, self.learn = log, learn
        self.lock = threading.Lock()
        self.total = 0
        self.conns = 0
        self.peak = {"request_bytes": 0, "connections": 0, "total_buffered": 0}
        self.written = None

    def open_conn(self):
        with self.lock:
            if self.conns >= self.max_conns:
                return False
            self.conns += 1
            self.peak["connections"] = max(self.peak["connections"], self.conns)
        self.record()
        return True

    def close_conn(self):
        with self.lock:
            self.conns -= 1

    def reserve(self, n):
        with self.lock:
            if self.total + n > self.max_total:
                return False
            self.total += n
            self.peak["total_buffered"] = max(self.peak["total_buffered"], self.total)
            return True

    def release(self, n):
        with self.lock:
            self.total -= n

    def request_done(self, size):
        with self.lock:
            self.peak["request_bytes"] = max(self.peak["request_bytes"], size)
        self.record()

    def record(self):
        """Learn mode: one line per change of any maximum, so the last such line holds the run's maxima."""
        if not self.learn:
            return
        with self.lock:
            line = "fwd-learn-max request_bytes=%d connections=%d total_buffered=%d" % (
                self.peak["request_bytes"], self.peak["connections"], self.peak["total_buffered"])
            if line == self.written:
                return
            self.written = line
            write_log(self.log, line)

    def refuse_connection(self, client):
        """The 503 for a connection past the cap: one named line, answer, close. Never blocks the accept loop."""
        ref = Refusal("cap", "connection-cap", 503, "connection cap (%d)" % self.max_conns)
        write_log(self.log, refusal_line(ref, "-", "-", 0))   # refused at accept: nothing of a request is known, nothing is invented
        try:
            client.settimeout(1)
            client.sendall(refusal_response(ref))
            client.shutdown(socket.SHUT_WR)
        except OSError:
            pass
        drain_briefly(client, limit=65536)
        client.close()


def parse_allow(text):
    """'METHOD /path' entries, comma-separated; the path is exact, or a prefix when it ends in '*'. Returns a list of
    (method, path-or-prefix, is_prefix); raises ValueError with one reason."""
    if text is None or not text.strip():
        raise ValueError("is empty")
    rules = []
    for raw in text.split(","):
        entry = raw.strip()
        if not entry:
            raise ValueError("has an empty entry")
        parts = entry.split()
        if len(parts) != 2:
            raise ValueError("entry %r is not 'METHOD /path'" % entry)
        method, path = parts
        if not re.fullmatch(r"[A-Z]{1,16}", method):
            raise ValueError("entry %r: the method is not upper-case letters" % entry)
        if not RE_ENTRY_PATH.fullmatch(path) or "?" in path or "#" in path or "*" in path[:-1]:
            raise ValueError("entry %r: the path must start with '/', and '*' may only end it" % entry)
        prefix = path.endswith("*")
        rules.append((method, path[:-1] if prefix else path, prefix))
    return rules


def allowed(rules, method, path):
    for m, p, prefix in rules:
        if m == method and (path.startswith(p) if prefix else path == p):
            return True
    return False


def request_path(target):
    """The decoded path to match. Every target the bridge never matches is a rule refusal at its own site: not origin-form
    (a path-absolute with an optional query: absolute-form, authority-form and asterisk-form are refused), a '#' anywhere
    (a client never sends a fragment, and the whole target is what is forwarded, so the checked string must be the sent
    string), undecodable, a control character or backslash or a second layer of percent-encoding, a '.' or '..'
    segment, an empty segment."""
    if not target.startswith("/"):
        raise Refusal("rule", "target-form", 403, "the target is not origin-form")
    if "#" in target:
        raise Refusal("rule", "fragment", 403, "the target carries a fragment")
    raw = target.split("?", 1)[0]
    try:
        path = urllib.parse.unquote(raw, errors="strict")
    except UnicodeDecodeError:
        raise Refusal("rule", "path-undecodable", 403, "the path does not decode")
    if "%" in path or "\\" in path or any(ord(c) < 0x20 or ord(c) == 0x7F for c in path):
        raise Refusal("rule", "path-encoding", 403, "the path carries a control character, a backslash or a second layer of encoding")
    segs = path.split("/")
    for i, seg in enumerate(segs[1:], 1):
        if seg in (".", "..") or (seg == "" and i != len(segs) - 1):
            raise Refusal("rule", "path-segment", 403, "the path has a dot segment or an empty segment")
    return path


class Reader:
    """Buffered reads from the client, so pipelined requests and partial segments are framed correctly."""

    def __init__(self, sock, idle=None, armed=None):
        self.sock = sock
        self.buf = bytearray()
        self.idle, self.armed = idle, armed

    def wait_readable(self):
        """The idle read timeout (L-S2). It runs only while `armed()`: a request is being read, or the connection has not
        yet carried one. A connection waiting for its NEXT request while the model's response streams is not idle (model
        responses run for minutes), so the clock restarts whenever it is not armed. Polled in short slices because the
        state it depends on changes while this thread waits."""
        step, waited = min(0.25, self.idle), 0.0
        while True:
            if select.select([self.sock], [], [], step)[0]:
                return
            waited = waited + step if self.armed() else 0.0
            if waited >= self.idle:
                raise Refusal("cap", "read-timeout", 408, "no bytes for %gs while a request was being read" % self.idle)

    def fill(self):
        if self.idle is not None:
            self.wait_readable()
        data = self.sock.recv(65536)
        if not data:
            return False
        self.buf += data
        return True

    def read_head(self):
        """The bytes of one request head, through the blank line; None at EOF on a message boundary."""
        while True:
            end = self.buf.find(b"\r\n\r\n")
            scan = bytes(self.buf[:end + 4] if end >= 0 else self.buf)
            if RE_BARE.search(scan):
                raise Refusal("framing", "head-bare-cr-lf", 400, "bare CR or LF in a request head")
            if end >= 0:
                head = bytes(self.buf[:end + 4])
                del self.buf[:end + 4]
                return head
            if len(self.buf) > MAX_HEAD:
                raise Refusal("cap", "head-too-large", 400, "request head too large")
            if not self.fill():
                if self.buf:
                    raise EOFError("connection closed inside a request head")
                return None

    def read_line(self):
        """One line ending in CRLF exactly. A bare LF or a bare CR anywhere in it is refused as soon as it is seen
        (not only when the CRLF finally arrives)."""
        while True:
            i = self.buf.find(b"\n")
            if i >= 0:
                if i == 0 or self.buf[i - 1] != 13 or b"\r" in self.buf[:i - 1]:
                    raise Refusal("framing", "chunk-bare-cr-lf", 400, "bare CR or LF in chunk framing")
                line = bytes(self.buf[:i + 1])
                del self.buf[:i + 1]
                return line
            if b"\r" in self.buf[:-1]:
                raise Refusal("framing", "chunk-bare-cr", 400, "bare CR in chunk framing")
            if len(self.buf) > MAX_LINE:
                raise Refusal("cap", "chunk-line-too-long", 400, "line too long")
            if not self.fill():
                raise EOFError("connection closed inside a request body")

    def read_exact(self, n):
        out = b""
        while len(out) < n:
            out += self.take(n - len(out))
        return out

    def take(self, n):
        """Up to n bytes (at least one), from the buffer first."""
        if not self.buf and not self.fill():
            raise EOFError("connection closed inside a request body")
        data = bytes(self.buf[:n])
        del self.buf[:n]
        return data


def parse_head(head):
    """(method, target, [(lower-case name, value)]) from one request head; a framing Refusal if it cannot be framed."""
    lines = head[:-4].split(b"\r\n")
    m = RE_REQLINE.fullmatch(lines[0])
    if not m:
        raise Refusal("framing", "request-line", 400, "request line")
    if (m.group(3), m.group(4)) != (b"1", b"1"):
        raise Refusal("framing", "version", 505, "only HTTP/1.1")   # a 1.0 message is not chunk-framed: nothing of it is read further
    headers = []
    for l in lines[1:]:
        if l[:1] in (b" ", b"\t"):
            raise Refusal("framing", "obsolete-folding", 400, "obsolete line folding")
        name, sep, value = l.partition(b":")
        if not sep or not RE_NAME.fullmatch(name):
            raise Refusal("framing", "header-line", 400, "header line")
        value = value.strip(b" \t")
        if RE_BADCTL.search(value):
            raise Refusal("framing", "header-control-char", 400, "control character in a header")
        headers.append((name.lower(), value))
    return m.group(1).decode(), m.group(2).decode(), headers


def body_framing(headers):
    """('none', 0) | ('length', n) | ('chunked', 0). Anything ambiguous is a framing Refusal (a smuggling guard)."""
    te = [v for n, v in headers if n == b"transfer-encoding"]
    cl = [v for n, v in headers if n == b"content-length"]
    if te and cl:
        raise Refusal("framing", "both-length-and-te", 400, "both Content-Length and Transfer-Encoding")
    if te:
        if [c.strip().lower() for c in b",".join(te).split(b",")] != [b"chunked"]:
            raise Refusal("framing", "unsupported-te", 400, "unsupported Transfer-Encoding")
        return "chunked", 0
    if cl:
        if any(not RE_LENGTH.fullmatch(v) for v in cl) or len(set(cl)) != 1:
            raise Refusal("framing", "content-length", 400, "Content-Length")
        return "length", int(cl[0])
    return "none", 0


def drain_briefly(sock, limit=None):
    """Discard what the client already sent, so closing does not reset the connection under a reply it has not read.
    `limit` bounds the bytes discarded (the accept loop uses it, so a client that keeps sending cannot hold it)."""
    try:
        sock.settimeout(0.05)
        left = limit
        while True:
            data = sock.recv(65536)
            if not data:
                break
            if left is not None:
                left -= len(data)
                if left <= 0:
                    break
    except OSError:
        pass


def handle_http(client, connect, log, rules, learn, budget, read_idle_s=None):
    """One client connection through the allow-list. Every request on the connection is checked, not only the first.

    NOTHING of a request is sent upstream until the whole request has validated: the request line, the headers, the
    framing and the body are all read into memory first (under the caps in `budget`), and only then are they sent, in
    one piece. A request refused at any stage sends nothing; a request refused after its body was read closes the
    connection and logs one tagged line (see Refusal), never a silent drop."""
    cid = next_id()
    t_open = time.time()
    counts = [0, 0]
    err = None
    wlock = threading.Lock()   # guards the client socket's write side between the relay thread and this one
    state = {"closing": False}
    upstream = None
    down = None
    reply = None               # the refusal to send after every earlier response has been relayed
    cur = {"method": "-", "path": "-", "read": 0, "held": 0}   # the request being read: for the refusal line and the budget
    # the idle read timeout runs while a request is partly read, or before the connection has carried any request
    reader = Reader(client, read_idle_s, lambda: upstream is None or cur["read"] > 0 or bool(reader.buf))

    def relay_down(up):
        pipe(up, client, counts, 1, wlock, shutdown_dst=False)
        with wlock:   # the model server is done: tell the client, unless a refusal is still to be written
            if not state["closing"]:
                try:
                    client.shutdown(socket.SHUT_WR)
                except OSError:
                    pass

    def claim(n):
        """Hold n more bytes of the current request in memory: refused past the per-request cap or the total cap."""
        if cur["held"] + n > budget.max_request:
            raise Refusal("cap", "request-cap", 413, "request cap (%d)" % budget.max_request)
        if not budget.reserve(n):
            raise Refusal("cap", "total-cap", 413, "total cap (%d)" % budget.max_total)
        cur["held"] += n

    def read_exact_buffered(n):
        parts = []
        while n > 0:
            chunk = reader.take(min(n, 65536))
            claim(len(chunk))
            cur["read"] += len(chunk)
            parts.append(chunk)
            n -= len(chunk)
        return b"".join(parts)

    def read_chunked():
        """Strict chunked framing: every size line is hex then CRLF exactly (no extension, no whitespace), every chunk
        ends in CRLF exactly, and the last chunk is followed by the EMPTY trailer only. Returns the raw framed bytes;
        none of them has been sent anywhere."""
        parts = []
        while True:
            line = reader.read_line()
            cur["read"] += len(line)
            if not RE_HEX.fullmatch(line[:-2]):
                raise Refusal("framing", "chunk-size", 400, "chunk size")
            size = int(line[:-2], 16)
            claim(len(line))
            parts.append(line)
            if size == 0:
                tail = reader.read_exact(2)
                cur["read"] += 2
                if tail != b"\r\n":
                    raise Refusal("framing", "trailer", 400, "trailer")
                claim(2)
                parts.append(tail)
                return b"".join(parts)
            if size > budget.max_request - cur["held"]:
                raise Refusal("cap", "chunk-over-cap", 413, "request cap (%d)" % budget.max_request)   # this chunk alone cannot fit
            parts.append(read_exact_buffered(size))
            tail = reader.read_exact(2)
            cur["read"] += 2
            if tail != b"\r\n":
                raise Refusal("framing", "chunk-framing", 400, "chunk framing")
            claim(2)
            parts.append(tail)

    def read_body(kind, n):
        if kind == "length":
            if n > budget.max_request - cur["held"]:
                raise Refusal("cap", "declared-length-over-cap", 413, "request cap (%d)" % budget.max_request)   # declared: refuse before reading it
            return read_exact_buffered(n)
        if kind == "chunked":
            return read_chunked()
        return b""

    try:
        while True:
            cur.update(method="-", path="-", read=0, held=0)
            head = reader.read_head()
            if head is None:
                break
            cur["read"] = len(head)
            method, target, headers = parse_head(head)
            path_raw = target.split("?", 1)[0].split("#", 1)[0] if target.startswith("/") else None
            log_path = (path_raw or "-")[:300]
            cur.update(method=method, path=log_path)
            names = {n for n, _ in headers}
            conn_tokens = b",".join(v.lower().replace(b" ", b"") for n, v in headers if n == b"connection").split(b",")
            framing = body_framing(headers)
            expect = b",".join(v.lower().replace(b" ", b"") for n, v in headers if n == b"expect").split(b",")
            # the rule checks, in this order; each raises its own Refusal
            if method == "CONNECT":
                raise Refusal("rule", "connect", 403, "CONNECT cannot be framed after the switch")
            if b"upgrade" in names or b"upgrade" in conn_tokens:
                raise Refusal("rule", "upgrade", 403, "Upgrade cannot be framed after the switch")
            if b"100-continue" in expect:
                raise Refusal("rule", "expect-continue", 417, "Expect: 100-continue is not served")   # it would wait for a body the head never asked for
            path = request_path(target)
            if not learn and not allowed(rules, method, path):
                raise Refusal("rule", "not-on-allow-list", 403, "method and path are not on the list")
            if learn:
                write_log(log, "fwd-req method=%s path=%s" % (method, log_path))
            claim(len(head))
            body = read_body(*framing)           # the whole request, validated, before any byte goes upstream
            if upstream is None:
                try:
                    upstream = connect()
                except OSError as e:
                    err = type(e).__name__
                    raise Refusal("upstream", "connect-failed", 502, "the model endpoint did not accept the connection (%s)" % err)
                down = threading.Thread(target=relay_down, args=(upstream,), daemon=True)
                down.start()
            upstream.sendall(head + body)
            counts[0] += len(head) + len(body)
            budget.request_done(cur["held"])
            budget.release(cur["held"])
            cur["held"] = 0
    except Refusal as e:
        reply = refusal_response(e)
        write_log(log, refusal_line(e, cur["method"], cur["path"], cur["read"]))
    except (EOFError, OSError):
        pass
    finally:
        budget.release(cur["held"])
        with wlock:
            state["closing"] = True
        if upstream is not None:
            try:
                upstream.shutdown(socket.SHUT_WR)   # the model server finishes what it was sent, then closes
            except OSError:
                pass
            down.join(timeout=30)
            upstream.close()
        if reply is not None:
            with wlock:
                try:
                    client.sendall(reply)
                except OSError:
                    pass
        try:
            client.shutdown(socket.SHUT_WR)
        except OSError:
            pass
        drain_briefly(client)
        client.close()
        write_log(log, conn_line(cid, t_open, counts, err))


def alive(pid):
    """Is the watched pid still there? Signal 0 first, so the framing cells (and this check) run on a Mac seat too.
    ProcessLookupError: gone. PermissionError: it exists and is simply not ours to signal. Signal 0 also succeeds on a
    process that has exited but has not been reaped by its parent, so on Linux /proc/<pid>/stat is read as well, and state
    Z (zombie) or X (dead) counts as gone; where it cannot be read (no /proc), the signal's answer stands."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    if sys.platform.startswith("linux"):
        try:
            with open("/proc/%d/stat" % pid) as f:
                return f.read().rsplit(")", 1)[1].split()[0] not in ("Z", "X", "x")
        except (OSError, IndexError):
            pass
    return True


CGROUP_ROOT = "/sys/fs/cgroup"
CGROUP_POLL_S = 1.0


class CgroupWatch:
    """Reads the box's cgroup counters while the box runs (R7-2). The forwarder lives outside the box for the whole run, and
    the box's scope is collected the moment the box exits, so the counters have to be read before that. The cgroup is found
    from /proc/<watched pid>/cgroup once that pid has moved into the NAMED scope; memory.events (oom_kill, max) and
    pids.events (max) are then read about once a second, and the last values read are kept for the line written at exit.
    An event in the last interval before exit can be missed by the counters (the journal for the unit still records an OOM
    kill)."""

    def __init__(self, unit, pid):
        self.unit, self.pid = unit, pid
        self.base = None
        self.reason = "the watched process never entered the scope %s.scope" % unit
        self.polls = 0
        self.last_poll = None
        self.vals = {"oom_kill": 0, "memory_max_events": 0, "pids_max_events": 0}
        self.next_poll = 0.0

    def find(self):
        try:
            with open("/proc/%d/cgroup" % self.pid) as f:
                for line in f.read().splitlines():
                    path = line.split(":", 2)[-1]
                    if path.rsplit("/", 1)[-1] == self.unit + ".scope":
                        self.base = CGROUP_ROOT + path
                        return
        except OSError as e:
            self.reason = "cannot read the watched process's cgroup: %s" % e.strerror

    @staticmethod
    def counters(path):
        out = {}
        with open(path) as f:
            for line in f:
                k, _, v = line.partition(" ")
                out[k] = int(v)
        return out

    def tick(self):
        now = time.monotonic()
        if self.base is None:
            self.find()
            if self.base is None:
                return
        if now < self.next_poll:
            return
        self.next_poll = now + CGROUP_POLL_S
        try:
            mem = self.counters(self.base + "/memory.events")
            pids = self.counters(self.base + "/pids.events")
        except (OSError, ValueError) as e:
            self.reason = "cannot read the scope's event files: %s" % e
            return
        self.vals = {"oom_kill": mem.get("oom_kill", 0), "memory_max_events": mem.get("max", 0),
                     "pids_max_events": pids.get("max", 0)}
        self.polls += 1
        self.last_poll = now

    def final_line(self):
        if not self.polls:
            return "box-cgroup unavailable reason=%s" % self.reason.replace("\n", " ")
        return "box-cgroup scope=%s oom_kill=%d memory_max_events=%d pids_max_events=%d polls=%d last_poll_age_s=%.1f" % (
            self.unit, self.vals["oom_kill"], self.vals["memory_max_events"], self.vals["pids_max_events"], self.polls,
            time.monotonic() - self.last_poll)


def run_outer(a):
    rules = []
    if not a.learn:
        try:
            rules = parse_allow(a.allow)
        except ValueError as e:
            sys.stderr.write("student-sandbox: refused: --allow %s\n" % e)
            return 2
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    # AF_UNIX paths are limited to ~107 bytes and TMPDIR may be long: bind relative to the socket's directory.
    os.chdir(os.path.dirname(a.sock))
    listener.bind(os.path.basename(a.sock))
    os.chmod(a.sock, 0o600)
    listener.listen(64)

    def connect():
        return connect_upstream(a.host, a.port)

    budget = Budget(a.max_request, a.max_total, a.max_conns, a.log, a.learn)

    def admit(client):
        if budget.open_conn():
            return True
        budget.refuse_connection(client)
        return False

    def handler(client):
        try:
            handle_http(client, connect, a.log, rules, a.learn, budget, a.read_idle_s)
        finally:
            budget.close_conn()

    threading.Thread(target=serve, args=(listener, handler, admit), daemon=True).start()
    watcher = CgroupWatch(a.scope_unit, a.watch) if a.scope_unit else None
    try:
        while alive(a.watch):
            if watcher:
                watcher.tick()
            time.sleep(0.2)
    finally:
        if watcher:
            write_log(a.log, watcher.final_line())     # one line per run, whatever happened: never silent
        for fn, arg in ((os.unlink, a.sock), (os.unlink, os.path.join(os.path.dirname(a.sock), "watch.pid")),
                        (os.unlink, os.path.join(os.path.dirname(a.sock), "sandbox-forward.py")),
                        (os.rmdir, os.path.dirname(a.sock))):
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
        serve(listener, lambda client: handle(client, connect, None))
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


def run_check_allow(a):
    try:
        n = len(parse_allow(a.text))
    except ValueError as e:
        sys.stderr.write("%s\n" % e)
        return 2
    print(n)
    return 0


# ---- the box's seccomp program (round 6, K1). The ONE place it is built: the wrapper asks for it with `seccomp-bpf` and
# hands the bytes to bwrap (--seccomp <fd>); nothing else holds a copy. It keeps the student from reading or writing the
# kernel's keys: a key in the invoking uid's keyring outlives the run and is shared with the host seat. Classic BPF over
# struct seccomp_data { int nr; __u32 arch; ... }. Linux, x86_64 numbers; every other architecture is killed.
AUDIT_ARCH_X86_64 = 0xC000003E
KEY_SYSCALLS = (("add_key", 248), ("request_key", 249), ("keyctl", 250))   # x86_64 numbers
X32_BIT = 0x40000000                         # an x32-ABI call is an x86_64 call with this bit set in its number
RET_KILL_PROCESS, RET_ALLOW = 0x80000000, 0x7FFF0000
RET_EPERM = 0x00050000 | 1                   # SECCOMP_RET_ERRNO | EPERM
LD_ARCH, LD_NR = 4, 0                        # offsets in seccomp_data
BPF_LD_W_ABS, BPF_JEQ_K, BPF_JSET_K, BPF_RET_K = 0x20, 0x15, 0x45, 0x06


def seccomp_program():
    """The program as a list of (code, jt, jf, k). Jump targets are written as verdict names and resolved below, so no
    offset is counted by hand."""
    steps = [
        ("ld", LD_ARCH),                            # A = arch
        ("jeq", AUDIT_ARCH_X86_64, None, "kill"),   # not x86_64: KILL_PROCESS (no other architecture is a way around)
        ("ld", LD_NR),                              # A = syscall number
        ("jset", X32_BIT, "kill", None),            # x32 ABI (bit 30 set): KILL_PROCESS
    ]
    for _name, nr in KEY_SYSCALLS:
        steps.append(("jeq", nr, "eperm", None))    # a key syscall: EPERM
    steps += [("ret", "allow"), ("ret", "eperm"), ("ret", "kill")]
    verdict = {"allow": RET_ALLOW, "eperm": RET_EPERM, "kill": RET_KILL_PROCESS}
    at = {st[1]: i for i, st in enumerate(steps) if st[0] == "ret"}   # the index of each verdict's RET step
    prog = []
    for i, st in enumerate(steps):
        if st[0] == "ld":
            prog.append((BPF_LD_W_ABS, 0, 0, st[1]))
        elif st[0] in ("jeq", "jset"):
            jt = at[st[2]] - i - 1 if st[2] else 0   # None: fall through to the next step
            jf = at[st[3]] - i - 1 if st[3] else 0
            prog.append((BPF_JEQ_K if st[0] == "jeq" else BPF_JSET_K, jt, jf, st[1]))
        else:
            prog.append((BPF_RET_K, 0, 0, verdict[st[1]]))
    return prog


def run_seccomp_bpf(a):
    import struct
    raw = b"".join(struct.pack("=HBBI", *ins) for ins in seccomp_program())
    try:
        with open(a.out, "wb") as f:
            f.write(raw)
    except OSError as e:
        sys.stderr.write("cannot write the seccomp program: %s\n" % e)
        return 2
    return 0


def run_homes(a):
    import pwd
    homes = {os.path.realpath(u.pw_dir) for u in pwd.getpwall() if u.pw_dir}
    sys.stdout.write("".join(h + "\0" for h in sorted(homes)))
    return 0


ETC_SYNTHETIC = ("passwd", "group", "machine-id", "hostname")   # replaced by synthetic content, never masked here
ETC_SCAN_CAP = 64 << 20   # a file larger than this is masked unread: fail closed on content we did not look at


def run_account_file(a):
    import grp, pwd
    me = pwd.getpwuid(os.getuid())
    try:
        gname = grp.getgrgid(os.getgid()).gr_name
    except KeyError:
        gname = me.pw_name
    shell = me.pw_shell if me.pw_shell.startswith("/") else "/bin/sh"
    if a.kind == "passwd":
        rows = ["root:x:0:0:root:/:/bin/sh"]
        if os.getuid() != 0:
            rows.append("%s:x:%d:%d::%s:%s" % (me.pw_name, os.getuid(), os.getgid(), a.home, shell))
    else:
        rows = ["root:x:0:"]
        if os.getgid() != 0:
            rows.append("%s:x:%d:" % (gname, os.getgid()))
    sys.stdout.write("\n".join(rows) + "\n")
    return 0


def people_names():
    """The names of the class of people and agents: every account with uid >= 1000, except 65534 (nobody)."""
    import pwd
    return sorted({u.pw_name for u in pwd.getpwall() if u.pw_uid >= 1000 and u.pw_uid != 65534})


def run_etc_scan(a):
    """Class rule, from the host at launch: a readable regular file under the root (default /etc; symlinks never
    followed) whose content contains the string /home/ or the name of any account with uid >= 1000 (nobody excluded) as
    a WHOLE WORD: not directly preceded or followed by a letter or digit, so any other delimiter counts (a colon, a
    comma, a space, an equals sign, a quote, a line start). System account names (uid < 1000) are not matched. Short names
    over-mask: that fails closed, and the launch line counts the files. Prints the paths, NUL-separated."""
    names = people_names()
    rx = None
    if names:
        rx = re.compile(rb"(?<![A-Za-z0-9])(?:" + b"|".join(re.escape(n.encode()) for n in names) + rb")(?![A-Za-z0-9])")
    skip = {os.path.realpath(os.path.join(a.root, n)) for n in ETC_SYNTHETIC}
    out = []
    for dirpath, dirnames, filenames in os.walk(a.root):
        for f in filenames:
            p = os.path.join(dirpath, f)
            if os.path.islink(p) or not os.path.isfile(p) or not os.access(p, os.R_OK) or os.path.realpath(p) in skip:
                continue
            try:
                if os.path.getsize(p) > ETC_SCAN_CAP:
                    out.append(p)
                    continue
                with open(p, "rb") as fh:
                    data = fh.read()
            except OSError:
                continue
            if b"/home/" in data or (rx is not None and rx.search(data)):
                out.append(p)
    sys.stdout.write("".join(p + "\0" for p in sorted(out)))
    return 0


def one_request(host, port):
    t0 = time.perf_counter()
    s = socket.create_connection((host, port), timeout=10)
    s.sendall(b"GET /ping HTTP/1.1\r\nHost: bridge-latency\r\nConnection: close\r\n\r\n")
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
    # the probe is one request, GET /ping: the boxed run lists exactly that, whatever the real launch lists
    # HOME is the slot, as the wrapper requires of a real launch: the operator's own HOME is not the student's
    env = dict(os.environ, SANDBOX_TEST="1", SANDBOX_TEST_EXEC=inside, SANDBOX_MODEL_ALLOW="GET /ping",
               HOME=os.environ.get("SANDBOX_SLOT", os.environ.get("HOME", "")))
    env.pop("SANDBOX_MODEL_LEARN", None)
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
    o.add_argument("--log"); o.add_argument("--allow"); o.add_argument("--learn", action="store_true")
    o.add_argument("--scope-unit")    # the box's systemd scope name: its cgroup counters are logged at exit
    for flag in ("--max-request", "--max-total", "--max-conns"):   # the caps are the wrapper's: no default lives here
        o.add_argument(flag, type=int, required=True)
    o.add_argument("--read-idle-s", type=float, required=True)     # the idle read timeout while a request is read
    i = sub.add_parser("inner")
    i.add_argument("--sock", required=True); i.add_argument("--port", type=int, required=True)
    i.add_argument("--unset", action="append", default=[])
    i.add_argument("cmd", nargs="*")
    ca = sub.add_parser("check-allow")
    ca.add_argument("--text", required=True)
    sub.add_parser("homes")
    sc = sub.add_parser("seccomp-bpf")
    sc.add_argument("--out", required=True)
    af = sub.add_parser("account-file")
    af.add_argument("kind", choices=("passwd", "group")); af.add_argument("--home", required=True)
    es = sub.add_parser("etc-scan")
    es.add_argument("--root", default="/etc")
    la = sub.add_parser("latency")
    la.add_argument("--host", required=True); la.add_argument("--port", type=int, required=True)
    la.add_argument("-n", type=int, default=50)
    lc = sub.add_parser("latency-compare")
    lc.add_argument("--wrapper", required=True); lc.add_argument("-n", type=int, default=50)
    a = ap.parse_args(argv)
    return {"outer": run_outer, "inner": run_inner, "latency": run_latency,
            "latency-compare": run_latency_compare, "check-allow": run_check_allow, "homes": run_homes,
            "account-file": run_account_file, "etc-scan": run_etc_scan,
            "seccomp-bpf": run_seccomp_bpf}[a.mode](a)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
