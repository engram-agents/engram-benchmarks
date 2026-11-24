#!/usr/bin/env python3
"""BEAM speed pilots: how much the student recorded, and WHERE. This file is the study's harness, not shipped product
code. Read-only: the store is opened with mode=ro and the transcripts are only read.

usage: pilot-record-volume.py --run-dir DIR --start ISO --end ISO --label NAME [--exchanges N]

For the run's store copy (DIR/knowledge-after.db) and the student's session transcripts (DIR/transcripts/**.jsonl),
over the window [start, end] (UTC, compared on the first 19 characters of each timestamp):
  1. ENGRAM: node types created in the window; for observations, the count and the total characters of claim and
     quote, and both per source exchange.
  2. Tool calls by name, per source exchange (the engram tool prefix is dropped).
  3. FILES: every Edit / Write call, grouped by destination (the harness's own auto-memory folder, a temporary
     directory, or other), with the new characters written; and Bash calls that redirect output into a file (any
     '>' or '>>' redirect whose target is not /dev/null, or tee). Only basenames are printed, never a path.
Prints nothing about the host.
"""
import argparse, collections, glob, json, os, re, sqlite3

REDIRECT = re.compile(r"(?<![-=>])(?:\d?>>?|&>)\s*(?!/dev/null|&)([~/$\w][^\s;|&)'\"]*)|\btee\s+(?:-a\s+)?(\S+)")


def in_window(ts, a):
    t = (ts or "").replace(" ", "T")[:19]
    return a.start <= t <= a.end


def store(a):
    db = sqlite3.connect(f"file:{os.path.join(a.run_dir, 'knowledge-after.db')}?mode=ro", uri=True)
    rows = [r for r in db.execute("select type, created_at, coalesce(claim,''), coalesce(quoted_text,'') from nodes")
            if in_window(r[1], a)]
    types = collections.Counter(r[0] for r in rows)
    obs = [r for r in rows if r[0].startswith("observation")]
    claim, quote = sum(len(r[2]) for r in obs), sum(len(r[3]) for r in obs)
    n = a.exchanges
    print(f"ENGRAM, nodes created in the window by type: {dict(sorted(types.items()))}")
    print(f"ENGRAM observations: {len(obs)} ({len(obs) / n:.2f} per source exchange); claim characters {claim} "
          f"({claim / n:.0f} per source exchange, {claim / max(1, len(obs)):.0f} per observation); quote characters "
          f"{quote} ({quote / n:.0f} per source exchange)")


def where(path):
    if "/memory/" in path:
        return "harness auto-memory folder"
    if path.startswith("/tmp/") or "/tmp/" in path:
        return "temporary directory"
    return "other"


def transcripts(a):
    tools, dest, dest_chars, names, redirects = (collections.Counter() for _ in range(5))
    for f in glob.glob(os.path.join(a.run_dir, "transcripts", "**", "*.jsonl"), recursive=True):
        for line in open(f, errors="replace"):
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("type") != "assistant" or not in_window(e.get("timestamp"), a):
                continue
            for b in e.get("message", {}).get("content", []) or []:
                if not (isinstance(b, dict) and b.get("type") == "tool_use"):
                    continue
                name = b.get("name", "").replace("mcp__plugin_engram_engram__", "")
                tools[name] += 1
                i = b.get("input", {}) or {}
                if name in ("Edit", "Write"):
                    p = i.get("file_path", "")
                    w = where(p)
                    dest[w] += 1
                    dest_chars[w] += len(i.get("new_string") or i.get("content") or "")
                    names[(w, os.path.basename(p))] += 1
                elif name == "Bash":
                    for m in REDIRECT.finditer(i.get("command", "")):
                        redirects[os.path.basename(m.group(1) or m.group(2))] += 1
    n = a.exchanges
    print("tool calls per source exchange: " + ", ".join(f"{k} {v / n:.2f}" for k, v in tools.most_common()))
    print(f"Edit/Write calls by destination: {dict(dest) or 'none'}")
    for w in dest:
        print(f"  {w}: {dest[w]} calls ({dest[w] / n:.2f} per source exchange), {dest_chars[w]} new characters "
              f"({dest_chars[w] / n:.0f} per source exchange); files: "
              + ", ".join(f"{b} x{c}" for (ww, b), c in names.most_common() if ww == w))
    print(f"Bash calls redirecting output into a file (not /dev/null): {sum(redirects.values())}"
          + (f"; targets: {dict(redirects.most_common(10))}" if redirects else ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--exchanges", type=int, default=45)
    a = ap.parse_args()
    a.start, a.end = a.start.rstrip("Z")[:19], a.end.rstrip("Z")[:19]
    print(f"== {a.label}: window {a.start}Z to {a.end}Z, {a.exchanges} source exchanges")
    store(a)
    transcripts(a)


if __name__ == "__main__":
    main()
