#!/usr/bin/env python3
"""BEAM entry gate, criterion 2 (recall after natural compaction, one long run) on setup 8762312e.
Written and committed BEFORE the run, with its controls (gate2_controls.py). Rules as ruled by Kepler
(design owner, Office 30375, 2026-11-15) on Borges's proposal (Office 30373). Desk tooling, not shipped.

Definitions (all read from the run's own transcript and saved store, never from what the student says):
- Reading exchange: a user record carrying the feed's reading-material marker that is NOT flagged
  isCompactSummary (the criterion-1 instrument defect is excluded by construction).
- Natural compaction: a compact_boundary record with compactMetadata.trigger == "auto" during the reading.
  Its position n is the reading exchange in progress (the last one whose user record precedes it).
  A source exchange s lies BEFORE it only if s < n (strict: the exchange in progress is not credited).
- Forced compaction: the proctor's /compact; its boundary has trigger "manual" and is never natural.
- Reading-phase node: a store node whose created_at lies from the first reading exchange's user record to the
  /compact user record. Nodes created from /compact to the first question are listed apart, never counted.
- A node's source exchange: the reading exchange during whose span (its user record to the next one, the
  last one to /compact) the node was created.
- Question: the official probing questions of the conversation, in the feeder's order. Its source exchanges
  come from source_chat_ids through the feeder's own user/assistant pairing.
- Counting question: has an answer (not abstention, has source ids), all source exchanges were read, and all
  lie before the LAST natural compaction. k = natural compactions after its latest source exchange.
- Tool read: a successful student call of engram_query / inspect / get_subgraph / list / surface inside the
  question's own turn (its user record to the next question's), whose result names a reading-phase node.
- Hook delivered: the hook-injected context (hook_additional_context records) in the question's own turn
  names a node whose source exchange is among the question's source exchanges.
- Cells (Kepler 30375): delivered & no tool read = EXCLUDED (hook-delivered); tool read = PASS (whether
  delivered or not, both labelled); neither = FAIL.
- Verdict: counting set after exclusions >= 4 and PASS >= half of it (rounded up) -> MET. Fewer than 4: if the
  exclusions caused it, UNDERSIZED BY HOOK DELIVERY, else UNDERSIZED. Otherwise NOT MET.
- Writing holds (section 5, "as in (1)"): at least two thirds (rounded up) of the reading exchanges carry a
  write whose node id exists in the store after the run. Content is checked by reading a seeded sample.
Usage: analyze_gate2.py RUN_DIR CONV [--sample N]
RUN_DIR holds transcripts/, knowledge-after.db and run/turns.jsonl.
"""
import ast, glob, json, math, os, random, re, sqlite3, sys
from datetime import datetime

MARK = "<<< READING MATERIAL"
QMARK = "The conversation is over. Answer this question"
READ_TOOLS = re.compile(r"engram_(query|inspect|get_subgraph|list|surface)$")
WRITE_TOOLS = re.compile(r"engram_(add_observation|add_observation_batch|derive|add_conjecture)$")
NODE_ID = re.compile(r"\b(?:ob|dv|cj|qu|df|cs|ls|gl|ax|pn|tk|fl|ct)_\d{4}\b")


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def user_text(r):
    c = r.get("message", {}).get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
    return ""


# ---- the rules, one function each, so the controls can mutate exactly one --------------------------------
def is_natural(meta):
    return (meta or {}).get("trigger") == "auto"


def is_reading_node(created, window):
    return window[0] <= created < window[1]


def is_delivered(hook_ids, src, node_ex):
    return any(node_ex.get(i) in src for i in hook_ids)


def before_last_natural(src, naturals):
    return bool(naturals) and max(src) < max(naturals)


# ---- parsing ------------------------------------------------------------------------------------------
def parse(records):
    """One pass in file order. Returns the run's structure."""
    S = {"ex_ts": [], "naturals": [], "manual": [], "auto_after_reading": [], "compact_ts": None,
         "q_ts": [], "writes": {}, "reads": {}, "unruled_reads": {}, "hook": {}, "excluded_summaries": 0}
    phase, ex, q, pending = "pre", 0, 0, {}
    for r in records:
        t = r.get("type")
        if t == "system" and r.get("subtype") == "compact_boundary":
            meta = r.get("compactMetadata")
            if phase == "reading" and is_natural(meta):
                S["naturals"].append(ex)
            elif is_natural(meta):
                S["auto_after_reading"].append((phase, q))
            else:
                S["manual"].append((phase, ex, q))
            continue
        a = r.get("attachment")
        if isinstance(a, dict) and a.get("type") == "hook_additional_context" and phase == "question":
            txt = "\n".join(x for x in (a.get("content") or []) if isinstance(x, str))
            S["hook"].setdefault(q, set()).update(NODE_ID.findall(txt))
            continue
        if t == "user":
            txt = user_text(r)
            if r.get("isCompactSummary"):
                if MARK in txt:
                    S["excluded_summaries"] += 1
            elif MARK in txt and phase in ("pre", "reading"):
                phase, ex = "reading", ex + 1
                S["ex_ts"].append(ts(r["timestamp"]))
            elif txt.strip().startswith("/compact") or "<command-name>/compact</command-name>" in txt:
                if phase == "reading":
                    phase, S["compact_ts"] = "compact", ts(r["timestamp"])
            elif QMARK in txt:
                phase, q = "question", q + 1
                S["q_ts"].append(ts(r["timestamp"]))
            c = r.get("message", {}).get("content")
            if isinstance(c, list):
                for b in c:
                    if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("tool_use_id") in pending:
                        kind, where, name = pending.pop(b["tool_use_id"])
                        body = json.dumps(b.get("content"))
                        ok = not b.get("is_error")
                        if kind == "w":
                            m = NODE_ID.search(body)
                            S["writes"].setdefault(where, []).append((name, m.group(0) if (m and ok) else None))
                        elif kind == "r" and ok:
                            S["reads"].setdefault(where, []).append((name, set(NODE_ID.findall(body))))
                        elif kind == "u" and ok:
                            S["unruled_reads"].setdefault(where, []).append(name)
        elif t == "assistant":
            for b in r.get("message", {}).get("content", []) or []:
                if not isinstance(b, dict) or b.get("type") != "tool_use":
                    continue
                name = b.get("name", "").split("__")[-1]
                if phase == "reading" and WRITE_TOOLS.search(name):
                    pending[b["id"]] = ("w", ex, name)
                elif phase == "question" and READ_TOOLS.search(name):
                    pending[b["id"]] = ("r", q, name)
                elif phase == "question" and name.startswith("engram_"):
                    pending[b["id"]] = ("u", q, name)
    return S


def node_exchanges(nodes, S):
    """nodes: {id: created_at datetime}. Returns (node_ex for reading-phase nodes, forced-compaction ids)."""
    if not S["ex_ts"] or S["compact_ts"] is None:
        return {}, []
    window = (S["ex_ts"][0], S["compact_ts"])
    bounds = S["ex_ts"] + [S["compact_ts"]]
    first_q = S["q_ts"][0] if S["q_ts"] else None
    node_ex, forced = {}, []
    for nid, created in nodes.items():
        if is_reading_node(created, window):
            for e in range(len(S["ex_ts"])):
                if bounds[e] <= created < bounds[e + 1]:
                    node_ex[nid] = e + 1
                    break
            else:                                     # unreachable under the rule as written (window == span)
                node_ex[nid] = len(S["ex_ts"])
        elif created >= S["compact_ts"] and (first_q is None or created < first_q):
            forced.append(nid)
    return node_ex, forced


def judge(S, nodes, questions):
    """questions: list of {cat, src (list of exchange numbers), answer}. Returns rows and verdicts."""
    node_ex, forced = node_exchanges(nodes, S)
    read_n = len(S["ex_ts"])
    rows = []
    for i, qq in enumerate(questions, 1):
        src = set(qq["src"])
        row = {"q": i, "cat": qq["cat"], "src": sorted(src)}
        if qq["cat"] == "abstention" or not src:
            row["status"] = "not counting: no answer or no source ids"
        elif max(src) > read_n:
            row["status"] = f"not counting: a source exchange was not read (read {read_n})"
        elif not before_last_natural(src, S["naturals"]):
            row["status"] = "not counting: a source exchange is not before the last natural compaction"
        else:
            row["k"] = sum(1 for n in S["naturals"] if n > max(src))
            hits = [(name, sorted(ids & set(node_ex))) for name, ids in S["reads"].get(i, [])]
            tool = any(h for _, h in hits)
            hook_ids = S["hook"].get(i, set())
            dlv = is_delivered(hook_ids, src, node_ex)
            row.update(tool_read=tool, delivered=dlv, reads=hits,
                       hook_nodes_from_sources=sorted(x for x in hook_ids if node_ex.get(x) in src))
            row["status"] = ("EXCLUDED (hook-delivered)" if dlv and not tool else
                             "PASS (delivered and read)" if dlv else "PASS (read)" if tool else "FAIL")
        row["unruled_reads"] = S["unruled_reads"].get(i, [])
        rows.append(row)
    counting = [r for r in rows if r["status"].startswith(("PASS", "FAIL", "EXCLUDED"))]
    excluded = [r for r in counting if r["status"].startswith("EXCLUDED")]
    scored = [r for r in counting if not r["status"].startswith("EXCLUDED")]
    passes = sum(1 for r in scored if r["status"].startswith("PASS"))
    if len(scored) < 4:
        verdict = "UNDERSIZED BY HOOK DELIVERY" if len(counting) >= 4 else "UNDERSIZED"
    else:
        verdict = "MET" if passes >= math.ceil(len(scored) / 2) else "NOT MET"
    written = {e for e, ws in S["writes"].items() if any(n and n in nodes for _, n in ws)}
    need = math.ceil(2 * read_n / 3)
    return {"rows": rows, "counting": len(counting), "excluded": len(excluded), "scored": len(scored),
            "passes": passes, "recall_verdict": verdict, "exchanges_read": read_n,
            "exchanges_written": len(written), "writing_needed": need,
            "writing_holds": read_n > 0 and len(written) >= need, "written_set": written,
            "forced_nodes": forced, "reading_nodes": len(node_ex)}


# ---- inputs from a real run ---------------------------------------------------------------------------
def load_run(run_dir):
    starts = []
    for p in glob.glob(os.path.join(run_dir, "transcripts", "**", "*.jsonl"), recursive=True):
        for l in open(p):
            try:
                t = json.loads(l).get("timestamp")
            except Exception:
                continue
            if t:
                starts.append((t, p)); break
    exam = sorted(starts)[-1][1]                      # the run's own session (the snapshot carries the first)
    records = []
    for l in open(exam):
        try:
            records.append(json.loads(l))
        except Exception:
            pass
    db = sqlite3.connect(f"file:{os.path.join(run_dir, 'knowledge-after.db')}?mode=ro", uri=True)
    nodes = {nid: ts(c) for nid, c in db.execute("select id, created_at from nodes")}
    texts = dict(db.execute("select id, claim from nodes"))
    return exam, records, nodes, texts


def load_questions(conv_id):
    import pyarrow.parquet as pq
    here = os.path.expanduser("<HOST PATH REDACTED>")
    sys.path.insert(0, here)
    from feed import exchanges                        # the feeder's own rendering, for the count check
    c = next(x for x in pq.read_table(os.path.join(here, "..", "beam-data", "100K.parquet")).to_pylist()
             if str(x["conversation_id"]) == str(conv_id))
    id2ex, n = {}, 0
    for sess in c["chat"]:
        pending = None
        for m in sess:
            if m["role"] == "user":
                pending = m
            elif m["role"] == "assistant" and pending is not None:
                n += 1; id2ex[pending["id"]] = n; id2ex[m["id"]] = n; pending = None
    assert n == len(exchanges(c)), f"pairing disagrees with the feeder: {n} vs {len(exchanges(c))}"

    def flat(x):
        if x is None: return []
        if isinstance(x, dict): return [i for v in x.values() for i in flat(v)]
        if isinstance(x, list): return [i for v in x for i in flat(v)]
        return [x]
    out = []
    for cat, items in ast.literal_eval(c["probing_questions"]).items():   # the feeder's order
        for it in items:
            src = [id2ex[i] for i in flat(it.get("source_chat_ids")) if i in id2ex]
            out.append({"cat": cat, "src": src, "question": it["question"],
                        "answer": it.get("answer") or it.get("ideal_answer") or it.get("ideal_response")
                        or it.get("expected_compliance") or it.get("ideal_summary")})
    return out, c


def main():
    run_dir, conv = sys.argv[1], sys.argv[2]
    sample_n = int(sys.argv[sys.argv.index("--sample") + 1]) if "--sample" in sys.argv else 20
    exam, records, nodes, texts = load_run(run_dir)
    questions, _ = load_questions(conv)
    S = parse(records)
    R = judge(S, nodes, questions)
    print(f"transcript: {exam}")
    print(f"reading exchanges: {R['exchanges_read']}; compaction-summary records with the marker, excluded: "
          f"{S['excluded_summaries']}")
    print(f"natural compactions at exchanges: {S['naturals']}; manual boundaries: {S['manual']}; "
          f"auto boundaries after the reading: {S['auto_after_reading']}")
    print(f"reading-phase nodes: {R['reading_nodes']}; nodes created at the forced compaction (listed, not "
          f"counted): {R['forced_nodes']}")
    print(f"\nWRITING: {R['exchanges_written']} of {R['exchanges_read']} reading exchanges with a store-confirmed "
          f"write; needed {R['writing_needed']} -> {'HOLDS' if R['writing_holds'] else 'DOES NOT HOLD'}")
    print("\nQUESTIONS")
    for r in R["rows"]:
        extra = (f" k={r['k']} delivered={r['delivered']} tool_read={r['tool_read']} "
                 f"hook-source-nodes={r['hook_nodes_from_sources']} reads={r['reads']}") if "k" in r else ""
        unr = f" unruled engram reads (not counted): {r['unruled_reads']}" if r["unruled_reads"] else ""
        print(f"  Q{r['q']:>2} {r['cat']:25} src={r['src']} -> {r['status']}{extra}{unr}")
    print(f"\nRECALL: counting {R['counting']}, excluded hook-delivered {R['excluded']}, scored {R['scored']}, "
          f"PASS {R['passes']} -> {R['recall_verdict']}")
    crit = "MET" if R["recall_verdict"] == "MET" and R["writing_holds"] else "NOT MET"
    if R["recall_verdict"].startswith("UNDERSIZED"):
        crit = R["recall_verdict"] + " (design owner rules)"
    print(f"GATE CRITERION 2: {crit}")
    # content check for writing: a seeded sample, printed for reading by a person
    rng = random.Random(20261115)
    pool = sorted(R["written_set"])
    print(f"\nCONTENT SAMPLE (seed 20261115, {min(sample_n, len(pool))} of {len(pool)} written exchanges):")
    for e in sorted(rng.sample(pool, min(sample_n, len(pool)))):
        ids = [n for _, n in S["writes"].get(e, []) if n in nodes]
        print(f"  exchange {e}: " + " | ".join(f"{i}: {texts.get(i, '')[:150]}" for i in ids))


if __name__ == "__main__":
    main()
