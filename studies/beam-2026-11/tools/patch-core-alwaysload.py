#!/usr/bin/env python3
"""E2 sandbox patch (this file is the study's harness, not shipped product code; it patches a sandbox copy, never a repo): give ENGRAM's core tools _meta anthropic/alwaysLoad so Claude Code
keeps them visible while the rest stay deferred. Inserts one meta= line after the @mcp.tool( line that
decorates each core def. Prints one line per tool; exits 1 unless every core tool was patched once."""
import sys
CORE = ["engram_add_observation", "engram_inspect", "engram_query", "engram_derive", "engram_supersede", "engram_checkpoint"]  # by measured call share on one seat (ob_7473)
META = '    meta={"anthropic/alwaysLoad": True},\n'
path = sys.argv[1]
lines = open(path).read().splitlines(keepends=True)
done = 0
for name in CORE:
    idx = next((i for i, l in enumerate(lines) if l.startswith(f"def {name}(")), None)
    if idx is None:
        print(f"MISSING def {name}"); continue
    j = idx - 1
    while j >= 0 and not lines[j].startswith("@mcp.tool("):
        j -= 1
    if j < 0 or "anthropic/alwaysLoad" in "".join(lines[j:idx]):
        print(f"SKIP {name} (decorator not found or already patched)"); continue
    lines.insert(j + 1, META); done += 1
    print(f"patched {name} at decorator line {j + 1}")
open(path, "w").write("".join(lines))
print(f"{done}/{len(CORE)} core tools patched in {path}")
sys.exit(0 if done == len(CORE) else 1)
