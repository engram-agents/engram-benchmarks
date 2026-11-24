"""R1 analyzer (not study code). Reads one evidence dir; prints per cell what RESULT.md needs. Nothing is inferred here:
labels, counts and quoted lines only. Zero model requests in a cell (or a turn) is printed as NOT RUN (Zephyr ADD 1)."""
import json, sys, re, collections
E = sys.argv[1]
log = [json.loads(l) for l in open(f"{E}/probe-log.jsonl")]
print("GATE:", json.dumps([r for r in log if "gate" in r]))
print("REFUSALS (namespace proof):", [r for r in log if "refused" in r])
cells = [c for c in ["MF", "MP", "ME", "AF", "AP", "AE", "WC", "BF", "BP", "BE", "RX"]
         if any(r.get("cell") == c for r in log)]
TURN_RE = re.compile(r"main-turn(\d+)-")
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
