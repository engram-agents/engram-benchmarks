#!/usr/bin/env python3
"""Controls for analyze_gate2.py, committed with it BEFORE the criterion-2 run (Kepler 30375: 'commit that
test with a planted control each way'). Desk tooling, not shipped.

Part 1, planted synthetic run (record shapes as Claude Code 2.1.325 writes them, see part 2):
  6 reading exchanges, natural (auto) compactions during exchanges 2 and 4, a compaction summary carrying the
  reading marker after each, the forced /compact in 2.1.325's order (manual boundary, summary, caveat, command
  record stamped at issue time), one node written per exchange 1-5, one node created at the forced compaction.
  Every expected cell is fixed below. Then each rule is mutated alone; a mutant must flip its target cell, and
  the controls print whether anything else moved.
Part 2, real transcripts (shape checks only, no verdicts): the gate-1 run on conversation 20 (one real auto
  compaction) and an 11-14 practice run with a real forced compaction.
Usage: gate2_controls.py
"""
import copy, glob, json, os, sys
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import analyze_gate2 as A   # noqa: E402

T0 = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)
def t(m): return (T0 + timedelta(minutes=m)).isoformat().replace("+00:00", "Z")
def user(text, m, summary=False):
    r = {"type": "user", "timestamp": t(m), "message": {"content": text}}
    if summary: r["isCompactSummary"] = True
    return r
def boundary(trigger, m): return {"type": "system", "subtype": "compact_boundary", "timestamp": t(m), "compactMetadata": {"trigger": trigger}}
def hook(text, m): return {"type": "attachment", "timestamp": t(m), "attachment": {"type": "hook_additional_context", "content": [text]}}
def use(i, name, m): return {"type": "assistant", "timestamp": t(m), "message": {"content": [{"type": "tool_use", "id": i, "name": "mcp__plugin_engram_engram__" + name, "input": {}}]}}
def result(i, body, m, err=False): return {"type": "user", "timestamp": t(m), "message": {"content": [{"type": "tool_result", "tool_use_id": i, "content": body, "is_error": err}]}}

recs, nodes = [], {}
for e in range(1, 7):
    m = 10 * e
    recs.append(user(f"{A.MARK} exchange {e} >>>", m))
    if e <= 5:
        recs += [use(f"w{e}", "engram_add_observation", m + 1), result(f"w{e}", f'{{"observation_id": "ob_000{e}"}}', m + 2)]
        nodes[f"ob_000{e}"] = T0 + timedelta(minutes=m + 2)
    if e in (2, 4):
        recs += [boundary("auto", m + 5), user(f"This session is being continued ... {A.MARK} quoted ...", m + 5, summary=True)]
# forced compaction, 2.1.325 order: boundary, summary, caveat, command record stamped at issue time (70)
recs += [boundary("manual", 71), user(f"This session is being continued ... {A.MARK} ...", 71, summary=True),
         user("<local-command-caveat>The command below was run directly</local-command-caveat>", 70),
         user("<command-name>/compact</command-name> <command-message>compact</command-message>", 70)]
nodes["ob_0099"] = T0 + timedelta(minutes=72)          # created at the forced compaction: never counted
nodes["pn_0001"] = T0 - timedelta(minutes=30)          # first-session node: never a reading-phase node

Q = lambda n: user(f"Proctor: {A.QMARK} about it, from your record and memory: question {n}", 100 + 5 * n)
plan = [  # (category, sources, records inside the question turn, expected cell)
    ("information_extraction", [1], lambda m: [hook("[ob_0001] recalled", m)], "EXCLUDED (hook-delivered)"),
    ("information_extraction", [2], lambda m: [hook("[ob_0005] recalled", m)], "FAIL"),            # non-source node
    ("temporal_reasoning", [3], lambda m: [hook("[ob_0003]", m), use("r3", "engram_query", m), result("r3", "ob_0003 ...", m)], "PASS (delivered and read)"),
    ("knowledge_update", [1, 2], lambda m: [use("r4", "engram_query", m), result("r4", "ob_0099 ...", m)], "FAIL"),  # forced-compaction node only
    ("multi_session_reasoning", [2, 5], lambda m: [use("r5", "engram_query", m), result("r5", "ob_0005", m)], "not counting: a source exchange is not before the last natural compaction"),
    ("event_ordering", [3], lambda m: [use("r6", "engram_inspect", m), result("r6", "ob_0002", m)], "PASS (read)"),
    ("abstention", [], lambda m: [], "not counting: no answer or no source ids"),
    ("preference_following", [1], lambda m: [use("r8", "engram_query_pattern", m), result("r8", "ob_0001", m)], "FAIL"),  # unruled read tool
    ("summarization", [4], lambda m: [], "not counting: a source exchange is not before the last natural compaction"),  # strict s < n
    ("contradiction_resolution", [1], lambda m: [use("r10", "engram_query", m), result("r10", "ob_0001", m, err=True)], "FAIL"),  # failed read
]
questions = []
for n, (cat, src, body, _) in enumerate(plan, 1):
    recs.append(Q(n)); recs += body(100 + 5 * n + 1)
    questions.append({"cat": cat, "src": src, "answer": "x"})
EXPECT = [p[3] for p in plan]


def run(label=None):
    R = A.judge(A.parse(copy.deepcopy(recs)), nodes, questions)
    return [r["status"] for r in R["rows"]], R


fails = 0
got, R = run()
S = A.parse(copy.deepcopy(recs))
print("PART 1, planted run")
checks = [("reading exchanges = 6 (3 compaction summaries with the marker excluded)", R["exchanges_read"] == 6 and S["excluded_summaries"] == 3),
          ("natural compactions at [2, 4]; the forced one is manual", S["naturals"] == [2, 4] and len(S["manual"]) == 1),
          ("reading ends at the /compact command's issue time", S["compact_ts"] == A.ts(t(70))),
          ("forced-compaction node listed apart", R["forced_nodes"] == ["ob_0099"]),
          ("writing: 5 of 6 exchanges, needed 4 -> holds", R["exchanges_written"] == 5 and R["writing_holds"]),
          ("k for question 1 (source 1, naturals 2 and 4) = 2", R["rows"][0].get("k") == 2)]
for n, (g, e) in enumerate(zip(got, EXPECT), 1):
    checks.append((f"Q{n} expected {e!r}", g == e))
checks.append(("verdict: counting 7, excluded 1, scored 6, PASS 2 -> NOT MET", (R["counting"], R["excluded"], R["scored"], R["passes"], R["recall_verdict"]) == (7, 1, 6, 2, "NOT MET")))
for name, ok in checks:
    fails += not ok
    print(f"  {'ok  ' if ok else 'FAIL'} {name}")
if got != EXPECT:
    print("  got:", got)

print("\nMUTANTS (each must flip its target; 'others moved' lists any other question whose cell changed)")
orig = {k: getattr(A, k) for k in ("is_delivered", "is_natural", "is_reading_node", "before_last_natural")}
mutants = [
    ("delivery = any reading-phase node in the hook, sources ignored", "is_delivered",
     lambda hook_ids, src, node_ex: any(i in node_ex for i in hook_ids), 2, "EXCLUDED (hook-delivered)"),
    ("delivery never detected", "is_delivered", lambda hook_ids, src, node_ex: False, 1, "FAIL"),
    ("natural = auto or manual", "is_natural", lambda meta: (meta or {}).get("trigger") in ("auto", "manual"), 5, "PASS (read)"),
    ("reading window runs to the first question", "is_reading_node", lambda created, window: window[0] <= created < A.ts(t(100)), 4, "PASS (read)"),
    ("before the FIRST natural compaction instead of the last", "before_last_natural", lambda src, nat: bool(nat) and max(src) < min(nat), 3, "not counting: a source exchange is not before the last natural compaction"),
    ("non-strict: the exchange in progress counts", "before_last_natural", lambda src, nat: bool(nat) and max(src) <= max(nat), 9, "FAIL"),
]
for label, fn_name, fn, target, want in mutants:
    setattr(A, fn_name, fn)
    try:
        g, _ = run()
    finally:
        for k, v in orig.items(): setattr(A, k, v)
    flipped = g[target - 1] == want and EXPECT[target - 1] != want
    others = [i + 1 for i, (a, b) in enumerate(zip(g, got)) if a != b and i + 1 != target]
    fails += not flipped
    print(f"  {'ok  ' if flipped else 'FAIL'} {label}: Q{target} {EXPECT[target-1]!r} -> {g[target-1]!r}; others moved: {others or 'none'}")

print("\nUNDERSIZED rules")
keep = copy.deepcopy(questions)       # turns stay in place; only categories change, so question i keeps turn i
for i in (5, 7, 9): questions[i]["cat"] = "abstention"          # counting Q1-Q4, Q1 excluded -> 3 scored
_, R2 = run()
ok = (R2["counting"], R2["excluded"], R2["recall_verdict"]) == (4, 1, "UNDERSIZED BY HOOK DELIVERY"); fails += not ok
print(f"  {'ok  ' if ok else 'FAIL'} 4 counting, 1 excluded, 3 scored -> {R2['recall_verdict']}")
questions[0]["cat"] = "abstention"                               # counting Q2-Q4, none excluded
_, R3 = run()
ok = (R3["counting"], R3["excluded"], R3["recall_verdict"]) == (3, 0, "UNDERSIZED"); fails += not ok
print(f"  {'ok  ' if ok else 'FAIL'} 3 counting, none excluded -> {R3['recall_verdict']}")
questions[:] = keep

print("\nPART 2, real 2.1.325 transcripts (shape checks)")
def load(p):
    out = []
    for l in open(p):
        try: out.append(json.loads(l))
        except Exception: pass
    return out
g20 = glob.glob(os.path.join(HERE, "gate1", "run2-conv20", "transcripts", "*", "e3e441a2*.jsonl"))
if g20:
    S = A.parse(load(g20[0]))
    ok = len(S["ex_ts"]) == 3 and S["naturals"] == [3] and S["excluded_summaries"] == 1; fails += not ok
    print(f"  {'ok  ' if ok else 'FAIL'} gate-1 conv 20 run: exchanges {len(S['ex_ts'])}, naturals {S['naturals']}, summaries with marker excluded {S['excluded_summaries']} (expected 3, [3], 1)")
else:
    fails += 1; print("  FAIL gate-1 conv 20 transcript not found")
fr = glob.glob("<HOST PATH REDACTED>")
if fr:
    S = A.parse(load(fr[0]))
    ok = S["compact_ts"] is not None and S["manual"] and not S["naturals"]; fails += not ok
    print(f"  {'ok  ' if ok else 'FAIL'} 11-14 practice run with a forced compaction: exchanges {len(S['ex_ts'])}, naturals {S['naturals']}, "
          f"manual {S['manual']}, reading ends {S['compact_ts']}, questions {len(S['q_ts'])}, hook node ids per question "
          f"{ {k: sorted(v)[:4] for k, v in S['hook'].items()} }")
else:
    fails += 1; print("  FAIL forced-compaction transcript not found")

print(f"\nCONTROLS: {'ALL PASS' if not fails else f'{fails} FAILED'}")
sys.exit(1 if fails else 0)
