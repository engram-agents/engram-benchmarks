"""R1 analyzer (not study code). Reads one evidence dir; prints per cell what RESULT.md needs. Nothing is inferred here:
labels, counts and quoted lines only. Zero model requests in a cell (or a turn) is printed as NOT RUN (Zephyr ADD 1)."""
import json, sys, re, collections
E = sys.argv[1]
log = [json.loads(l) for l in open(f"{E}/probe-log.jsonl")]
print("GATE:", json.dumps([r for r in log if "gate" in r]))
print("REFUSALS (namespace proof):", [r for r in log if "refused" in r])
cells = list(dict.fromkeys(r["cell"] for r in log if r.get("cell")))  # every cell in the log, in run order (no hand list)
TURN_RE = re.compile(r"main-turn(\d+)-")

def wide_option(req):
    """The forwarder's written rule (plan section 7), not a variant of it (Zephyr 2026-11-23T22:12Z item 2): every tool entry is
    scanned; run_in_background ANYWHERE in a Bash entry's whole input schema counts; a shape the forwarder cannot read
    (not exactly one Bash entry; a $ref; allOf/anyOf/oneOf) is reported as 'shape' (the forwarder refuses it).
    Returns (has_bash, option_anywhere, shape_problem)."""
    tools = req.get("tools") or []
    bash = [t for t in tools if isinstance(t, dict) and t.get("name") == "Bash"]
    blob = json.dumps([t.get("input_schema") for t in bash])
    shape = len(bash) > 1 or any(k in blob for k in ('"$ref"', '"allOf"', '"anyOf"', '"oneOf"'))
    return bool(bash), "run_in_background" in blob, shape

for c in cells:
    print("\n================ CELL", c)
    rs = [r for r in log if r.get("cell") == c]
    for r in rs:
        if "settings_files" in r:
            print("settings_files (INTENT, what the script wrote):", json.dumps(r["settings_files"]))
            print("etc_claude_code listing at launch:", r.get("etc_claude_code_listing"))
        if "env_passed" in r:
            print("env_passed (selected):", {k: v for k, v in r["env_passed"].items() if "CLAUDE_CODE" in k or "PROBE" in k or "AUTO" in k})
        if "argv" in r:
            print("argv has --managed-settings:", "--managed-settings" in r["argv"])
        if r.get("file_records"):
            print(f"file records ({r['file_records']}):")
            for x in r["records"]:
                print("   ", json.dumps(x))
        if "exit" in r: print("exit:", r["exit"])
        if r.get("watchdog_kill") or r.get("timeout") or r.get("eof"): print("ANOMALY:", json.dumps(r))
    reqs = [r for r in rs if r.get("who") == "model" and "request" in r]
    if not reqs:
        print("MODEL REQUESTS: 0 -> CELL NOT RUN (never S-like or U-like)")
    per_turn = collections.Counter(); opt = collections.Counter(); bash_n = 0
    for r in reqs:
        m = TURN_RE.search(r.get("label") or ""); t = int(m.group(1)) if m else None
        per_turn[t] += 1
        bash = [x for x in (r["request"].get("tools") or []) if x.get("name") == "Bash"]
        if bash:
            bash_n += 1
            props = (bash[0].get("input_schema") or {}).get("properties", {})
            opt[(t, "run_in_background" in props)] += 1
    print(f"model requests: {len(reqs)}; carrying Bash: {bash_n}")
    wide = [wide_option(r["request"]) for r in reqs]
    print(f"WIDE predicate (forwarder's rule): option anywhere in a Bash schema = {sum(1 for w in wide if w[1])} of "
          f"{sum(1 for w in wide if w[0])} Bash-carrying; unreadable shape = {sum(1 for w in wide if w[2])}; "
          f"NARROW (first Bash entry's properties) = {sum(v for (t, o), v in opt.items() if o)}")
    print("requests per turn label (None = not a main-turn label):", dict(per_turn))
    for t in sorted({k[0] for k in opt}, key=lambda v: (v is None, v)):
        print(f"  turn {t}: Bash schema run_in_background True={opt[(t, True)]} False={opt[(t, False)]}")
    labels = [r.get("label") for r in reqs]
    print("labels in order:", labels)
    wins = []; cur = None
    for r in rs:
        if "silence_window_start" in r: cur = [r["t"], None, r["after"]]
        if r.get("silence_window_end") and cur: cur[1] = r["t"]; wins.append(cur); cur = None
    for a, b, tag in wins:
        print(f"silence after {tag}: {round(b - a, 1)} s, model requests inside: {[r.get('label') for r in reqs if a <= r['t'] <= b]}")
    ev = [json.loads(l) for l in open(f"{E}/events-{c}.jsonl") if l.strip().startswith("{")]
    for e in ev:
        if e.get("type") == "user":
            for b in (e.get("message", {}).get("content") or []):
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    txt = b.get("content"); txt = json.dumps(txt) if not isinstance(txt, str) else txt
                    print("tool_result:", txt[:400].replace("\n", " | "))
        if e.get("type") == "system" and e.get("subtype") not in (None, "init"):
            print("system event:", json.dumps(e)[:300])
        if e.get("type") == "result":
            print("result event: subtype", e.get("subtype"), "| is_error", e.get("is_error"), "|", str(e.get("result"))[:80])
    st = open(f"{E}/stderr-{c}.log").read().splitlines()
    print(f"stderr lines: {len(st)}")
    for h in st[:40]: print("  stderr:", h[:300])
    if len(st) > 40: print(f"  stderr: ... {len(st) - 40} more lines NOT PRINTED")
    evs = open(f"{E}/events-{c}.jsonl").read()
    for pat in [r"managed.settings", r"policy", r"not yet approved", r"left out of the policy tier", r"only honored from",
                r"[Ii]nvalid settings", r"settings validation"]:
        n = len(re.findall(pat, evs))
        if n: print(f"events match /{pat}/: {n}")

# ---- follow-up additions (send-window attribution; C4 compaction control) ----
print("\n\n================ SEND-WINDOW ATTRIBUTION (requests assigned to the latest proctor send before them)")
for c in cells:
    rs = [r for r in log if r.get("cell") == c]
    sends = [(r["t"], r["turn_sent"], r.get("content")) for r in rs if "turn_sent" in r]
    if not sends:
        print(c, ": no send log (older probe)"); continue
    reqs = [r for r in rs if r.get("who") == "model" and "request" in r]
    win = collections.OrderedDict((i, [0, 0, 0]) for i in range(len(sends)))  # requests, with option, carrying Bash
    for r in reqs:
        i = max([k for k, s in enumerate(sends) if s[0] <= r["t"]], default=None)
        if i is None: continue
        hb, op, shp = wide_option(r["request"])
        win[i][0] += 1
        if hb:
            win[i][2] += 1
            if op: win[i][1] += 1
    print(c, "(WIDE predicate) " + " | ".join(f"send#{k} {sends[k][2]!r}: req={v[0]} bash={v[2]} option={v[1]}" for k, v in win.items()))
    tot = sum(v[0] for v in win.values())
    print(f"   CONTROL sum: per-send req sum={tot} vs cell total={len(reqs)} -> {'MATCH' if tot == len(reqs) else 'MISMATCH'}")
    # CONTROL per turn (Zephyr 2026-11-23T22:14Z): label-based per-turn counts (request count AND wide option count) vs send-window
    # counts, computed here, not left to a reader. In a cell with a compaction (turn 8), requests made during it carry the
    # label of turn 7 (the latest PROBE TURN marker) but fall in send 8's window, so turns 7 and 8 are compared as a pair.
    lab = collections.Counter(); lab_opt = collections.Counter()
    for r in reqs:
        m = TURN_RE.search(r.get("label") or ""); t = int(m.group(1)) if m else None
        lab[t] += 1; lab_opt[t] += 1 if wide_option(r["request"])[1] else 0
    by_turn = collections.Counter(); by_turn_opt = collections.Counter()
    for k, v in win.items():
        by_turn[sends[k][1]] += v[0]; by_turn_opt[sends[k][1]] += v[1]
    has8 = any(s_[1] == 8 for s_ in sends)
    groups = [(7, 8)] if has8 else []
    singles = [t for t in sorted(by_turn) if not (has8 and t in (7, 8))]
    for g in [(t,) for t in singles] + groups:
        a = sum(by_turn[t] for t in g); b = sum(lab[t] for t in g)
        ao = sum(by_turn_opt[t] for t in g); bo = sum(lab_opt[t] for t in g)
        ok = (a == b and ao == bo)
        print(f"   CONTROL turn{'s' if len(g) > 1 else ''} {'+'.join(map(str, g))}: send-window req={a} option(wide)={ao} | "
              f"label req={b} option(wide)={bo} -> {'MATCH' if ok else 'MISMATCH'}")
    if lab.get(None):
        print(f"   requests with no main-turn label (not compared): {lab[None]}")
    # shape caveat (Zephyr 2026-11-23T22:14Z): quote what matched before anything is called unreadable
    for r in reqs:
        hb, op, shp = wide_option(r["request"])
        if shp:
            bash = [t for t in (r["request"].get("tools") or []) if isinstance(t, dict) and t.get("name") == "Bash"]
            blob = json.dumps([t.get("input_schema") for t in bash])
            hits = [blob[max(0, i - 60):i + 40] for k_ in ('"$ref"', '"allOf"', '"anyOf"', '"oneOf"') for i in [blob.find(k_)] if i >= 0]
            print(f"   SHAPE FLAG on {r.get('label')}: bash entries={len(bash)}; matched text: {hits}")
    ev = [json.loads(l) for l in open(f"{E}/events-{c}.jsonl") if l.strip().startswith("{")]
    cb = [e for e in ev if e.get("type") == "system" and e.get("subtype") == "compact_boundary"]
    # stream-json spells it compact_metadata; transcripts spell it compactMetadata. Read both and say which was found
    # (the first version read only the camelCase key and printed [None] for a manual compaction: an instrument slip).
    trig = [((e.get('compact_metadata') or e.get('compactMetadata') or {}).get('trigger'),
             'compact_metadata' if 'compact_metadata' in e else ('compactMetadata' if 'compactMetadata' in e else 'NO METADATA KEY')) for e in cb]
    print(f"   compact_boundary events: {len(cb)}; (trigger, key): {trig}")
    to = [r for r in rs if r.get("timeout")]
    if to: print("   TURN TIMEOUTS:", [(r.get('turn')) for r in to])
