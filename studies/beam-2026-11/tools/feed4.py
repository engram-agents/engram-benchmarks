#!/usr/bin/env python3
"""BEAM exam-room driver v4: feed3 + --per-round K (speed pilot P1). This file is the study's harness, not shipped
product code.

K consecutive exchanges go in one user message, each rendered exactly as at K = 1 (its own reading-material wrapper;
no exchange number is shown at any K); the brief comes only before the first round; every row logged to turns.jsonl
names the exchanges it carried. At K = 1 its messages are byte-identical to the feeder the gate runs used (checked
against run A's transcripts). --dump-plan prints the planned messages as JSON and starts nothing.

ONE persistent Claude Code process per run (claude -p, stream-json in and out), so SessionStart fires once, as in an
ordinary session. Phases, all in the same session: setup (--first-session: the fixed fact sheet, then a fixed nudge
until first-run-pending clears), reading (the brief + K exchanges per user message; the student ends with NEXT),
compact (--force-compact: the proctor sends /compact), questions (--questions N, one probing question per message).
env: BEAM_PARQUET (required) path to the BEAM 100K parquet file; BEAM_OLLAMA_URL (optional) Ollama endpoint.
"""
import argparse, ast, json, os, subprocess, sys, time
import pyarrow.parquet as pq

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from feed import BRIEF, PROCTOR, QUESTION_PREFIX, OLLAMA_URL, data_path, exchanges, unload  # noqa: E402

FACT_SHEET = PROCTOR + """ Hello. I am the proctor of a memory study, and you are being set up for it. Please run
your first-session setup now. Everything you need from me is here, so you do not need to ask me
anything:
- Call me Proctor. I run a study of how agents remember long conversations.
- Please choose your own name.
- What brought me to ENGRAM: to see how well an agent remembers a long conversation it watches.
- Transcript retention: no, leave my settings alone.
- The model you run on is qwen3.8:27b (provider: Alibaba Qwen, via Ollama). Record that as your family.
- Your auto-compact window is 131072 tokens.
- Decline every optional service (persistent recall service, viz service, forum).
- I have no questions about how ENGRAM works.
Finish the setup completely, then say SETUP DONE."""
NUDGE = (PROCTOR + " Please continue the setup using only the information I already gave you. Decline anything "
         "optional. When the setup is complete, say SETUP DONE.")


class Student:
    def __init__(self, args):
        home = os.path.abspath(args.arm_home)
        env = {"PATH": os.environ["PATH"] + ":" + HERE, "HOME": home, "TERM": "dumb", "LANG": "C.UTF-8",
               "ANTHROPIC_BASE_URL": OLLAMA_URL, "ANTHROPIC_AUTH_TOKEN": "ollama",
               "ANTHROPIC_API_KEY": "", "DISABLE_TELEMETRY": "1", "DISABLE_AUTOUPDATER": "1",
               "PROCTOR_DIR": os.path.abspath(os.path.join(args.out, "proctor"))}
        for kv in args.env:
            k, _, v = kv.partition("="); env[k] = v
        os.makedirs(os.path.join(home, "work"), exist_ok=True)
        cmd = ["claude", "-p", "--input-format", "stream-json", "--output-format", "stream-json",
               "--verbose", "--model", args.model, "--permission-mode", "bypassPermissions"]
        if args.resume:
            cmd += ["--resume", args.resume]  # v3
        self.p = subprocess.Popen(cmd, cwd=os.path.join(home, "work"), env=env, stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=open(os.path.join(args.out, "stderr.log"), "a"),
                                  text=True, bufsize=1)
        self.events = open(os.path.join(args.out, "events.jsonl"), "a")
        self.session_id = None

    def ask(self, text, timeout):
        msg = {"type": "user", "message": {"role": "user", "content": text}}
        self.p.stdin.write(json.dumps(msg) + "\n"); self.p.stdin.flush()
        t0 = time.time(); tools = []; last_text = ""
        while True:
            line = self.p.stdout.readline()
            if not line:
                return {"eof": True, "wall_s": round(time.time() - t0, 1), "tools": tools}
            self.events.write(line); self.events.flush()
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("type") == "system" and ev.get("session_id"):
                self.session_id = ev["session_id"]
            if ev.get("type") == "assistant":
                for c in ev.get("message", {}).get("content", []) or []:
                    if c.get("type") == "tool_use":
                        tools.append(c.get("name"))
                    elif c.get("type") == "text":
                        last_text = c.get("text", "")
            if ev.get("type") == "result":
                ev["_wall_s"] = round(time.time() - t0, 1); ev["_tools"] = tools; ev["_last_text"] = last_text
                return ev
            if time.time() - t0 > timeout:
                return {"timeout": True, "wall_s": round(time.time() - t0, 1), "tools": tools}

    def close(self):
        try:
            self.p.stdin.close(); self.p.wait(timeout=120)
        except Exception:  # noqa: BLE001
            self.p.kill()


def check_loaded(path):
    """Refuse unless the feed4.py and feed.py actually loaded (their own file paths) hash to the setup's lines."""
    import hashlib, re, feed as _feed
    if not path:
        print("REFUSE: a run needs --expect-components (the setup's component file)", file=sys.stderr); return 3
    want = {}
    for line in open(path, encoding="utf-8"):
        m = re.fullmatch(r"([0-9a-f]{64})  (feed4\.py|imported module: feed\.py)", line.rstrip("\n"))
        if m:
            want["feed4.py" if m.group(2) == "feed4.py" else "feed.py"] = m.group(1)
    got = {"feed4.py": hashlib.sha256(open(os.path.abspath(__file__), "rb").read()).hexdigest(),
           "feed.py": hashlib.sha256(open(os.path.abspath(_feed.__file__), "rb").read()).hexdigest()}
    for k in ("feed4.py", "feed.py"):
        print(f"loaded {k}: {got[k]}  (setup: {want.get(k, 'MISSING')})", file=sys.stderr, flush=True)
    if any(want.get(k) != got[k] for k in got):
        print("REFUSE: the loaded feeder does not match the setup's components", file=sys.stderr); return 3
    return 0


def load_question_file(path):
    """--question-file: a JSON list of {"id": str, "question": str}. Returns the list, or raises ValueError naming
    the defect. The ids must be unique, every question non-empty, and the list non-empty."""
    try:
        with open(path, encoding="utf-8") as f:
            items = json.load(f)
    except (OSError, ValueError) as e:
        raise ValueError(f"cannot read {path} as JSON: {e}")
    if not isinstance(items, list):
        raise ValueError("the file must be a JSON list of {id, question} objects")
    if not items:
        raise ValueError("the list is empty (nothing to deliver)")
    seen = set()
    for n, it in enumerate(items, 1):
        if not isinstance(it, dict):
            raise ValueError(f"item {n} is not an object")
        if not isinstance(it.get("id"), str) or not it["id"].strip():
            raise ValueError(f"item {n} has no string id")
        if not isinstance(it.get("question"), str):
            raise ValueError(f"item {n} has no string question")
        if not it["question"].strip():
            raise ValueError(f"item {n} (id {it['id']!r}) has an empty question")
        if it["id"] in seen:
            raise ValueError(f"duplicate id {it['id']!r}")
        seen.add(it["id"])
    return items


def check_question_args(ap, args):
    """Refuse (argparse error, exit 2) every unsafe use of --question-file, before any student process or unload."""
    if not args.question_file:
        return None
    if args.questions:
        ap.error("--question-file cannot be combined with --questions (dataset questions)")
    if args.ask:
        ap.error("--question-file cannot be combined with --ask (practice questions)")
    if not args.resume:
        ap.error("--question-file requires --resume SESSION (answering resumes the run's own session)")
    if args.setup_only:
        ap.error("--question-file cannot be combined with --setup-only")
    if args.first_session:
        ap.error("--question-file cannot be combined with --first-session")
    if args.turns != 0:
        ap.error("--question-file requires --turns 0 (an answering run reads nothing)")
    if args.start != ap.get_default("start"):
        ap.error("--question-file cannot be combined with --start (an answering run reads nothing)")
    try:
        return load_question_file(args.question_file)
    except ValueError as e:
        ap.error(f"--question-file: {e}")


def build_parser():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm-home", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--conv", type=int, required=True); ap.add_argument("--turns", type=int, required=True)
    ap.add_argument("--questions", type=int, default=0)
    ap.add_argument("--first-session", action="store_true"); ap.add_argument("--setup-rounds", type=int, default=12)
    ap.add_argument("--setup-only", action="store_true", help="run only the first session (with --first-session), then exit")
    ap.add_argument("--ask", action="append", default=[], help="PRACTICE ONLY: a proctor-written question asked after the compaction (never scored)")
    ap.add_argument("--force-compact", action="store_true")
    ap.add_argument("--model", default="qwen3.8:27b-128k"); ap.add_argument("--turn-timeout", type=int, default=1800)
    ap.add_argument("--resume", default=""); ap.add_argument("--start", type=int, default=1)  # v3
    ap.add_argument("--env", action="append", default=[], help="extra KEY=VALUE for the student (e.g. a harness setting)")
    ap.add_argument("--per-round", type=int, default=1, help="v4: consecutive exchanges per user message (K)")
    ap.add_argument("--dump-plan", action="store_true", help="v4: print the planned messages as JSON and exit")
    ap.add_argument("--expect-components", help="v4: the setup's component file (setup-id.py output); the run "
                    "refuses unless the feed4.py and feed.py it loaded hash to the lines there (required to run)")
    ap.add_argument("--question-file", help="a JSON list of {id, question}: delivered in file order, once each, after "
                    "the optional /compact (use with --resume SESSION --turns 0); refused with --questions or --ask")
    return ap


def main():
    ap = build_parser()
    args = ap.parse_args()
    qitems = check_question_args(ap, args)
    os.makedirs(args.out, exist_ok=True)
    conv = next(c for c in pq.read_table(data_path()).to_pylist() if str(c["conversation_id"]) == str(args.conv))
    exs = exchanges(conv)[args.start - 1: args.turns]  # v3: 1-based start
    plan = []
    if args.first_session:
        plan.append(("setup", FACT_SHEET, []))
    if args.setup_only:
        # The first session is its OWN session; the exam starts in a fresh process
        # (a new session, no --resume) on the same home, with the graph carried over.
        exs = []
    ids = list(range(args.start, args.start + len(exs)))
    for r in range(0, len(exs), args.per_round):  # v4: K exchanges per round, each rendered as at K = 1
        body = "\n\n".join(exs[r: r + args.per_round])
        if r == 0 and args.start == 1:
            body = BRIEF + "\n\n" + body  # v3: brief only at the true start
        plan.append(("exchange", body, ids[r: r + args.per_round]))
    if args.force_compact:
        plan.append(("compact", "/compact", []))
    if args.questions:
        q = ast.literal_eval(conv["probing_questions"])
        for k, item in [(k, it) for k, v in q.items() for it in v][: args.questions]:
            plan.append(("question", PROCTOR + " " + QUESTION_PREFIX + item["question"], []))
    for qtext in args.ask:
        plan.append(("practice-question", PROCTOR + " " + QUESTION_PREFIX + qtext, []))
    for it in qitems or []:
        plan.append(("question", PROCTOR + " " + QUESTION_PREFIX + it["question"], [], it["id"]))
    pending = os.path.join(os.path.abspath(args.arm_home), ".engram", "first-run-pending")
    if args.dump_plan:  # v4: print the exact messages and stop, before any student process starts
        json.dump([{"kind": p[0], "exchanges": p[2], "text": p[1], **({"id": p[3]} if len(p) > 3 else {})}
                   for p in plan], sys.stdout); return 0
    st = Student(args); log = open(os.path.join(args.out, "turns.jsonl"), "a"); rc = 0
    try:
        i = 0
        for kind, text, carried, *qid in plan:
            rounds = 0
            while True:
                i += 1
                ev = st.ask(text, args.turn_timeout)
                u = ev.get("usage", {}) or {}
                row = {"i": i, "kind": kind, "utc_end": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(), "wall_s": ev.get("_wall_s", ev.get("wall_s")),
                       "is_error": ev.get("is_error"), "num_turns": ev.get("num_turns"),
                       "in_tok": u.get("input_tokens"), "out_tok": u.get("output_tokens"),
                       "tools": ev.get("_tools", ev.get("tools")), "eof": ev.get("eof"), "timeout": ev.get("timeout"),
                       "session_id": st.session_id, "result": ev.get("result") or ev.get("_last_text"),
                       "exchanges": carried, "per_round": args.per_round, **({"id": qid[0]} if qid else {})}
                log.write(json.dumps(row) + "\n"); log.flush()
                print(f"{i} {kind}: wall {row['wall_s']}s in {row['in_tok']} out {row['out_tok']} "
                      f"tools {row['tools']} | {str(row['result'] or '')[-160:]!r}", flush=True)
                if row["eof"] or row["timeout"]:
                    print("STOP: student process ended or timed out", file=sys.stderr); rc = 1; break
                if kind == "setup" and os.path.exists(pending) and rounds < args.setup_rounds:
                    rounds += 1; text = NUDGE; continue
                break
            if rc:
                break
            if kind == "setup":
                print(f"setup: first-run-pending {'STILL PRESENT' if os.path.exists(pending) else 'cleared'}", flush=True)
    finally:
        st.close()
    return rc


if __name__ == "__main__":
    _model = next((sys.argv[i + 1] for i, a in enumerate(sys.argv[:-1]) if a == "--model"), "qwen3.8:27b-128k")
    # v4: the loaded-file check runs FIRST, outside the unload wrapper, so a refusal touches nothing (no model unload).
    _exp = next((sys.argv[i + 1] for i, a in enumerate(sys.argv[:-1]) if a == "--expect-components"), None)
    if _exp or "--dump-plan" not in sys.argv:
        _rc = check_loaded(_exp)
        if _rc:
            sys.exit(_rc)
    if "--dump-plan" in sys.argv:  # v4: a dry plan dump never touches the model server
        sys.exit(main())
    _ap = build_parser(); check_question_args(_ap, _ap.parse_args())  # a refused --question-file touches nothing (no unload)
    try:
        rc = main()
    finally:
        unload(_model)
    sys.exit(rc)
