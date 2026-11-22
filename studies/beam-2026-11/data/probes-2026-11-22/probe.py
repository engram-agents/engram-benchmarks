#!/usr/bin/env python3
"""Tool-capability probe (BEAM audit F row 5, Kepler 2026-11-22T19:30Z / Zephyr 2026-11-22T19:29Z). Not study code; never shipped.

Question: in the configuration the pre-wrapper runs had (permissions bypassed, no tool option), would WebFetch
and Task have WORKED if the model had called them; does WebFetch refuse loopback; and does --disallowedTools
naming section 7's OFF set refuse the same calls (cell B), drop exactly those tools from the init list, and keep
an OFF tool from coming back through ToolSearch.

No model. A stub Anthropic endpoint returns SCRIPTED assistant turns (tool_use blocks); dispatch of a scripted
tool_use is the same code path a model's would take. Safe by construction: the whole probe runs inside
`bwrap --unshare-net` (a private network namespace with loopback only: no outside address, no host service is
reachable), with a throwaway HOME per cell, no plugins, no exam material.

Usage (outer):  python3 probe.py --claude <pinned claude-2.1.328 binary> --evidence <dir>
The outer process re-executes itself inside bwrap with --inner.
"""
import argparse, json, os, shutil, socket, subprocess, sys, threading, time, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

OFF_SET = ["WebSearch", "WebFetch", "Task", "Workflow", "SendMessage", "ListAgents", "TaskStop",
           "CronCreate", "CronDelete", "CronList", "ScheduleWakeup", "Monitor"]
SUB_MARK = "PROBE-SUBAGENT-PROMPT"
TARGET_MARK = "PROBE-TARGET-CONTENT"
STATE = {"cell": None, "outside": None, "log": None, "tport": None}
LOCK = threading.Lock()


def log(rec):
    with LOCK:
        STATE["log"].write(json.dumps(rec) + "\n"); STATE["log"].flush()


# ---------------- target listener (the fetch target; loopback only) ----------------
# RAW TCP recorder (Zephyr 2026-11-22T19:37Z item 1): 2.1.328's WebFetch rewrites http: to https: unconditionally before it
# fetches, so an HTTP listener could never see a GET. The recorder logs every connection's peer and first bytes
# (0x16 = a TLS ClientHello: the fetch step ATTEMPTED the loopback target), then closes. No TLS is offered.
def raw_target(family, host):
    srv = socket.socket(family, socket.SOCK_STREAM); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, STATE["tport"] or 0)); srv.listen(16)
    if not STATE["tport"]:
        STATE["tport"] = srv.getsockname()[1]

    def loop():
        while True:
            try:
                c, peer = srv.accept()
            except OSError:
                return
            c.settimeout(3)
            try:
                first = c.recv(64)
            except OSError as e:
                first = f"<recv error {e}>".encode()
            log({"who": "target", "cell": STATE["cell"], "t": time.time(), "family": "v6" if family == socket.AF_INET6 else "v4",
                 "peer": peer[0], "first_bytes_hex": first[:16].hex(), "first_byte_is_tls_handshake": first[:1] == b"\x16"})
            c.close()
    threading.Thread(target=loop, daemon=True).start()
    return srv


# ---------------- stub model (Anthropic Messages API, scripted) ----------------
def texts_of(msg):
    c = msg.get("content")
    if isinstance(c, str):
        return [c]
    return [b.get("text", "") for b in c or [] if isinstance(b, dict) and b.get("type") == "text"]


def tool_results(msg):
    c = msg.get("content")
    return [b for b in (c if isinstance(c, list) else []) if isinstance(b, dict) and b.get("type") == "tool_result"]


def plan_main(turn):
    t = STATE["tport"]
    if turn == 1:
        return [("WebFetch", {"url": f"http://127.0.0.1:{t}/a-ip", "prompt": "Summarise the page."}),
                ("WebFetch", {"url": f"http://localhost:{t}/a-localhost", "prompt": "Summarise the page."}),
                ("Task", {"description": "probe marker", "subagent_type": "general-purpose",
                          "prompt": f"{SUB_MARK} write the two marker files."}),
                ("WebSearch", {"query": "probe query"})]
    if turn == 2:
        return [("ToolSearch", {"query": "select:WebFetch", "max_results": 5}),
                ("ToolSearch", {"query": "select:mcp__probe__probe_echo", "max_results": 5}),
                ("WebFetch", {"url": f"http://127.0.0.1:{t}/turn2-ip", "prompt": "Summarise the page."})]
    if turn == 3:  # Kepler 2026-11-22T19:34Z: can the shell run in the background, and does completion start an unsent turn?
        return [("Bash", {"command": "sleep 3; echo BG-DONE", "description": "background probe",
                          "run_in_background": True})]
    if turn == 4:  # Kepler 2026-11-22T19:44Z, cell D: a LONG foreground command, past the shell tool's default 120 s timeout
        return [("Bash", {"command": "python3 -c 'import time; time.sleep(150)'; echo FG-DONE", "description": "long foreground probe"})]
    return []


def decide(req):
    msgs = req.get("messages") or []
    tools = req.get("tools") or []
    tool_types = [x.get("type", "") for x in tools]
    users = [m for m in msgs if m.get("role") == "user"]
    user_texts = " ".join(t for m in users for t in texts_of(m))
    if any(tt.startswith("web_search") for tt in tool_types):
        return ("text", "PROBE: no search performed by the stub.", "websearch-nested")
    if TARGET_MARK in json.dumps(msgs):
        if not tools:
            return ("text", "PROBE SUMMARY of the target page.", "webfetch-summary")
    if SUB_MARK in user_texts:
        if any(tool_results(m) for m in users):
            return ("text", "SUBAGENT DONE", "subagent-final")
        cmd = (f"echo PROBE-MARK-{STATE['cell']} > \"$HOME/probe-marker-home\"; "
               f"echo PROBE-MARK-{STATE['cell']} > \"{STATE['outside']}/probe-marker-outside\"")
        return ("tool", ("Bash", {"command": cmd, "description": "write probe markers"}), "subagent-bash")
    if not tools:
        return ("text", "OK", "aux-no-tools")
    turn = None; after = []
    for i, m in enumerate(msgs):
        if m.get("role") == "user":
            for tx in texts_of(m):
                if "PROBE TURN 1" in tx: turn, after = 1, msgs[i + 1:]
                if "PROBE TURN 2" in tx: turn, after = 2, msgs[i + 1:]
                if "PROBE TURN 3" in tx: turn, after = 3, msgs[i + 1:]
                if "PROBE TURN 4" in tx: turn, after = 4, msgs[i + 1:]
    if turn is None:
        return ("text", "OK", "main-unrecognised")
    step = sum(len(tool_results(m)) for m in after if m.get("role") == "user")
    plan = plan_main(turn)
    if step < len(plan):
        return ("tool", plan[step], f"main-turn{turn}-step{step}")
    return ("text", f"TURN {turn} DONE", f"main-turn{turn}-end")


def sse(handler, events):
    handler.send_response(200); handler.send_header("Content-Type", "text/event-stream"); handler.end_headers()
    for ev in events:
        handler.wfile.write(f"event: {ev['type']}\ndata: {json.dumps(ev)}\n\n".encode()); handler.wfile.flush()


class Model(BaseHTTPRequestHandler):
    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        try:
            return json.loads(raw or b"{}")
        except ValueError:
            return {"_raw": raw.decode("utf-8", "replace")}

    def do_POST(self):
        req = self._body()
        path = self.path.split("?")[0]
        if path.endswith("/count_tokens"):
            log({"who": "model", "cell": STATE["cell"], "t": time.time(), "path": self.path, "kind": "count_tokens"})
            out = json.dumps({"input_tokens": len(json.dumps(req)) // 4}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(out); return
        if not path.endswith("/messages"):
            log({"who": "model", "cell": STATE["cell"], "t": time.time(), "path": self.path, "kind": "unknown-post"})
            self.send_response(404); self.end_headers(); return
        kind, payload, label = decide(req)
        mid = "msg_" + uuid.uuid4().hex[:20]
        log({"who": "model", "cell": STATE["cell"], "t": time.time(), "path": self.path, "label": label,
             "stream": bool(req.get("stream")), "n_messages": len(req.get("messages") or []),
             "tool_names": [x.get("name") or x.get("type") for x in req.get("tools") or []], "request": req})
        model = req.get("model", "stub")
        if kind == "text":
            block = {"type": "text", "text": payload}; stop = "end_turn"
        else:
            name, inp = payload
            block = {"type": "tool_use", "id": "toolu_" + uuid.uuid4().hex[:20], "name": name, "input": inp}; stop = "tool_use"
        usage = {"input_tokens": len(json.dumps(req)) // 4, "output_tokens": 8}
        if not req.get("stream"):
            out = json.dumps({"id": mid, "type": "message", "role": "assistant", "model": model, "content": [block],
                              "stop_reason": stop, "stop_sequence": None, "usage": usage}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(out); return
        start = dict(block); evs = [{"type": "message_start", "message": {"id": mid, "type": "message", "role": "assistant", "model": model,
                                     "content": [], "stop_reason": None, "stop_sequence": None, "usage": {**usage, "output_tokens": 0}}}]
        if block["type"] == "text":
            start["text"] = ""; delta = {"type": "text_delta", "text": block["text"]}
        else:
            start["input"] = {}; delta = {"type": "input_json_delta", "partial_json": json.dumps(block["input"])}
        evs += [{"type": "content_block_start", "index": 0, "content_block": start},
                {"type": "content_block_delta", "index": 0, "delta": delta},
                {"type": "content_block_stop", "index": 0},
                {"type": "message_delta", "delta": {"stop_reason": stop, "stop_sequence": None}, "usage": {"output_tokens": 8}},
                {"type": "message_stop"}]
        sse(self, evs)

    def do_GET(self):
        log({"who": "model", "cell": STATE["cell"], "t": time.time(), "path": self.path, "kind": "get"})
        self.send_response(404); self.end_headers()

    def log_message(self, *a):
        pass


MCP_SERVER = r'''
import json, sys
for line in sys.stdin:
    m = json.loads(line); i = m.get("id"); meth = m.get("method")
    if i is None: continue
    if meth == "initialize":
        r = {"protocolVersion": m["params"].get("protocolVersion", "2024-11-05"), "capabilities": {"tools": {}},
             "serverInfo": {"name": "probe", "version": "0"}}
    elif meth == "tools/list":
        r = {"tools": [{"name": "probe_echo", "description": "Echo for the probe.",
                        "inputSchema": {"type": "object", "properties": {"x": {"type": "string"}}}}]}
    elif meth == "tools/call":
        r = {"content": [{"type": "text", "text": "probe echo"}]}
    else:
        r = {}
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": i, "result": r}) + "\n"); sys.stdout.flush()
'''


def silence(p, evf, cell, secs, tag):
    """The proctor sends nothing for `secs`; every stdout line and every stub request in the window is recorded. A model
    request here is a turn the proctor did not send. The criterion is the stub's own request log (select() on a buffered
    text pipe can miss buffered lines)."""
    import select
    t0 = time.time(); log({"who": "probe", "cell": cell, "t": t0, "silence_window_start": secs, "after": tag})
    while time.time() - t0 < secs:
        r, _, _ = select.select([p.stdout], [], [], 1.0)
        if r:
            line = p.stdout.readline()
            if not line:
                break
            evf.write(line); evf.flush(); log({"who": "probe", "cell": cell, "t": time.time(), "silence_stdout": line[:300]})
    log({"who": "probe", "cell": cell, "t": time.time(), "silence_window_end": True, "after": tag})


def run_cell(cell, claude, base, mport, ev_dir, disallow, settings="{}", extra_env=None, turns=(1, 2, 3)):
    home = os.path.join(base, f"home-{cell}"); outside = os.path.join(base, f"outside-{cell}")
    os.makedirs(os.path.join(home, ".claude"), exist_ok=True); os.makedirs(os.path.join(home, "work")); os.makedirs(outside)
    with open(os.path.join(home, ".claude", "settings.json"), "w") as f:
        f.write(settings)  # cells A and B: "{}", as the arm homes had (no permissions key); cell C: preflight off
    mcp_py = os.path.join(base, "mcp_probe.py")
    mcp_cfg = os.path.join(base, f"mcp-{cell}.json")
    json.dump({"mcpServers": {"probe": {"command": sys.executable, "args": [mcp_py]}}}, open(mcp_cfg, "w"))
    STATE["cell"] = cell; STATE["outside"] = outside
    env = {"PATH": os.path.dirname(claude) + ":" + os.environ["PATH"], "HOME": home, "TERM": "dumb", "LANG": "C.UTF-8",
           "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{mport}", "ANTHROPIC_AUTH_TOKEN": "ollama", "ANTHROPIC_API_KEY": "",
           "DISABLE_TELEMETRY": "1", "DISABLE_AUTOUPDATER": "1"}
    env.update(extra_env or {})
    # built fresh, never inherited: CLAUDE_CODE_AUTO_BACKGROUND_TIMEOUT_MS is unset by construction; assert and log it
    assert "CLAUDE_CODE_AUTO_BACKGROUND_TIMEOUT_MS" not in env  # it can only SHORTEN the move threshold (Zephyr 2026-11-22T19:48Z)
    log({"who": "probe", "cell": cell, "t": time.time(), "env_passed": env})
    cmd = [claude, "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
           "--model", "qwen3.8:27b-128k", "--permission-mode", "bypassPermissions", "--mcp-config", mcp_cfg]
    if disallow:
        cmd += ["--disallowedTools", ",".join(OFF_SET)]
    log({"who": "probe", "cell": cell, "t": time.time(), "argv": cmd})
    evf = open(os.path.join(ev_dir, f"events-{cell}.jsonl"), "w")
    p = subprocess.Popen(cmd, cwd=os.path.join(home, "work"), env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=open(os.path.join(ev_dir, f"stderr-{cell}.log"), "w"), text=True, bufsize=1)
    watchdog = threading.Timer(900,lambda: (log({"who": "probe", "cell": cell, "t": time.time(), "watchdog_kill": True}), p.kill()))
    watchdog.start()  # a silent process would block readline forever; the watchdog ends the cell instead
    for n in turns:
        if n == 4:
            silence(p, evf, cell, 20, "turn 3")  # turn 3's own window, before turn 4 is sent
        p.stdin.write(json.dumps({"type": "user", "message": {"role": "user", "content": f"PROBE TURN {n}"}}) + "\n"); p.stdin.flush()
        t0 = time.time()
        while True:
            line = p.stdout.readline()
            if not line:
                log({"who": "probe", "cell": cell, "t": time.time(), "turn": n, "eof": True}); break
            evf.write(line); evf.flush()
            try:
                if json.loads(line).get("type") == "result":
                    break
            except ValueError:
                pass
            if time.time() - t0 > 240:
                log({"who": "probe", "cell": cell, "t": time.time(), "turn": n, "timeout": True}); break
    # Silence window after the last turn: 20 s after turn 3, 60 s after turn 4 (a 150 s python nap that the harness moved to
    # the background at its 120 s timeout would finish about 30 s after the timeout).
    silence(p, evf, cell, 60 if turns[-1] == 4 else 20, f"turn {turns[-1]}")
    try:
        p.stdin.close(); p.wait(timeout=60)
    except Exception:
        p.kill(); p.wait()
    watchdog.cancel()
    log({"who": "probe", "cell": cell, "t": time.time(), "exit": p.returncode})

    def read(path):
        return open(path).read().strip() if os.path.exists(path) else None
    marks = {"home": read(os.path.join(home, "probe-marker-home")),
             "outside": read(os.path.join(outside, "probe-marker-outside"))}
    log({"who": "probe", "cell": cell, "t": time.time(), "markers": marks})
    return marks


def inner(a):
    base = a.base; ev = a.evidence
    STATE["log"] = open(os.path.join(ev, "probe-log.jsonl"), "w")
    # CONTAINMENT GATE (Zephyr 2026-11-22T19:37Z item 4): enforced, not logged. Before anything is bound or started.
    s = socket.socket(); s.settimeout(3); rc_ext = s.connect_ex(("1.1.1.1", 443)); s.close()
    dns_err = None
    try:
        resolved = socket.getaddrinfo("api.anthropic.com", 443)
    except OSError as e:
        resolved = None; dns_err = str(e)
    log({"who": "probe", "gate": {"outside_connect_errno": rc_ext, "api_anthropic_resolves": bool(resolved),
                                  "dns_error": None if resolved else dns_err}})
    if rc_ext == 0 or resolved:
        log({"who": "probe", "gate": "FAILED: an outside path exists; nothing started"}); STATE["log"].close(); return 5
    s = socket.socket(); s.settimeout(2)
    log({"who": "probe", "informational_host_service_port_errno": s.connect_ex(("127.0.0.1", "<port>"))}); s.close()
    open(os.path.join(base, "mcp_probe.py"), "w").write(MCP_SERVER)
    ms = ThreadingHTTPServer(("127.0.0.1", 0), Model); mport = ms.server_address[1]
    t4 = raw_target(socket.AF_INET, "127.0.0.1"); tport = STATE["tport"]
    servers = [ms]; raws = [t4]
    try:
        raws.append(raw_target(socket.AF_INET6, "::1"))
    except OSError as e:
        log({"who": "probe", "ipv6_target": f"not bound: {e}"})
    threading.Thread(target=ms.serve_forever, daemon=True).start()
    log({"who": "probe", "ports": {"model": mport, "target": tport}})
    SWITCHES = {"CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1", "CLAUDE_CODE_DISABLE_CRON": "1",
                "CLAUDE_CODE_DISABLE_WORKFLOWS": "1"}  # Kepler 2026-11-22T19:44Z item 1
    ENABLE = {"CLAUDE_AUTO_BACKGROUND_TASKS": "1"}  # NOT set in any affected run; set here to exercise the move
    plan = {"A": dict(disallow=False), "B": dict(disallow=True),
            "C": dict(disallow=False, settings='{"skipWebFetchPreflight": true}'),  # NOT the affected configuration
            # B4 and D both set CLAUDE_AUTO_BACKGROUND_TASKS, so the switches are the only difference between them.
            # The earlier comment here said the move happens ONLY with that variable: WITHDRAWN (Zephyr 2026-11-22T20:02Z/2026-11-22T20:04Z;
            # an interactive 2.1.328 session moved a 120 s command with it unset, INTERACTIVE-MOVE-RECORD.md).
            # Cell U (no variable) measures the print-mode default.
            "B4": dict(disallow=True, turns=(1, 2, 3, 4), extra_env=ENABLE),
            "D": dict(disallow=True, turns=(1, 2, 3, 4), extra_env={**ENABLE, **SWITCHES}),
            "U": dict(disallow=False, turns=(1, 2, 3, 4)),  # Kepler 2026-11-22T20:02Z (b): A's argv/env + turn 4; no variable, no switch
            "S": dict(disallow=False, turns=(1, 2, 3, 4), extra_env=SWITCHES)}  # Zephyr 2026-11-22T20:14Z: U + the three switches, no variable (the launcher's own configuration)
    cells = a.cells.split(",") if a.cells else (["A", "B"] + (["C"] if a.with_cell_c else []))
    res = {c: run_cell(c, a.claude, base, mport, ev, **plan[c]) for c in cells}
    for s in servers:
        s.shutdown(); s.server_close()
    for r in raws:
        r.close()
    log({"who": "probe", "done": res}); STATE["log"].close()
    return 0


def outer(a):
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    base = f"<probe base>-{stamp}"; ev = os.path.abspath(a.evidence)
    if (ev + "/").startswith(base + "/"):
        print("REFUSE: the evidence path is inside the probe base, which is removed at the end"); return 2
    os.makedirs(base); os.makedirs(ev, exist_ok=True)
    print(f"probe base {base}; evidence {ev}", flush=True)
    argv = ["bwrap", "--dev-bind", "/", "/", "--unshare-net", "--die-with-parent", "--",
            sys.executable, os.path.abspath(__file__), "--inner", "--claude", a.claude,
            "--base", base, "--evidence", ev] + (["--with-cell-c"] if a.with_cell_c else []) + (["--cells", a.cells] if a.cells else [])
    json.dump({"bwrap_argv": argv, "probe_sha256_note": "see the covering message"}, open(os.path.join(ev, "outer-argv.json"), "w"))
    rc = subprocess.call(argv)
    print(f"inner exit {rc}", flush=True)
    # cleanup, then verify it
    left = subprocess.run(["pgrep", "-af", base], capture_output=True, text=True).stdout.strip()
    shutil.rmtree(base, ignore_errors=True)
    after = subprocess.run(["pgrep", "-af", base], capture_output=True, text=True).stdout.strip()
    print(json.dumps({"processes_before_cleanup": left, "processes_after": after, "base_exists": os.path.exists(base)}))
    return rc


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--claude", required=True); ap.add_argument("--evidence", required=True)
    ap.add_argument("--inner", action="store_true"); ap.add_argument("--base")
    ap.add_argument("--with-cell-c", action="store_true", help="add cell C (A with WebFetch's preflight off)")
    ap.add_argument("--cells", help="comma list from A,B,C,B4,D,U,S (overrides the default A,B[,C])")
    a = ap.parse_args()
    sys.exit(inner(a) if a.inner else outer(a))
