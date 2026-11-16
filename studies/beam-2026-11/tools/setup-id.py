#!/usr/bin/env python3
"""BEAM setup identity by content. This file is the study's harness, not shipped product code.

The setup id is the sha256 of its component lines, sorted, newline-joined, with a trailing newline (the rule that
produced setup 8762312e). Components: the plugin source tree id, the student's rendered CLAUDE.md, the feed script
and its FACT_SHEET / NUDGE source segments, every study-local module the feed script imports (the import walk), the
exam line, the grant line, the window setting, the install flags, the Claude Code version, and the turns per round.

THE IMPORT WALK (design owner's ruling, 2026-11-16). Setup 8762312e did not cover the brief: the feed script imported
it from a second module that was not a component. So the build walks the feed script's imports (recursively, through
every module it finds) and resolves each name to a .py file in the module directories (the script's own directory
plus any --module-dir). Every module found that way must be declared with --module, or the build FAILS. A module
that is declared is hashed into the id, so one changed byte in it changes the id.

usage: setup-id.py --feed-script F --claude-md F --exam-line F --grant-line-file F --plugin-tree ID
                   --window SETTING --install-flags FLAGS --claude-code VERSION
                   [--turns-per-round K] [--module F ...] [--module-dir D ...] [--no-walk]
--no-walk exists only for the control (it reproduces the old, blind behaviour). Prints the components and the id.
"""
import argparse, ast, hashlib, os, sys


def sha(b):
    return hashlib.sha256(b).hexdigest()


def segment(src, name):
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and getattr(node.targets[0], "id", "") == name:
            return ast.get_source_segment(src, node)
    return None


def imported_names(path):
    names = set()
    for node in ast.walk(ast.parse(open(path, encoding="utf-8").read())):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.add(node.module.split(".")[0])
    return names


def walk(script, dirs):
    """Every study-local module reachable from script: a name that resolves to <dir>/<name>.py in one of dirs."""
    found, todo = {}, [os.path.abspath(script)]
    while todo:
        cur = todo.pop()
        for name in sorted(imported_names(cur)):
            for d in dirs:
                cand = os.path.abspath(os.path.join(d, name + ".py"))
                if os.path.isfile(cand) and cand != os.path.abspath(script):
                    if cand not in found.values():
                        found[name] = cand
                        todo.append(cand)
                    break
    return found


def main():
    ap = argparse.ArgumentParser()
    for f in ("--feed-script", "--claude-md", "--exam-line", "--grant-line-file", "--plugin-tree", "--window",
              "--install-flags", "--claude-code"):
        ap.add_argument(f, required=True)
    ap.add_argument("--turns-per-round", type=int)
    ap.add_argument("--module", action="append", default=[])
    ap.add_argument("--module-dir", action="append", default=[])
    ap.add_argument("--no-walk", action="store_true")
    a = ap.parse_args()
    script = a.feed_script
    src = open(script, encoding="utf-8").read()
    base = os.path.basename(script)
    declared = {os.path.abspath(m) for m in a.module}
    if not a.no_walk:
        dirs = [os.path.dirname(os.path.abspath(script))] + a.module_dir
        found = walk(script, dirs)
        missing = sorted(p for p in found.values() if p not in declared)
        if missing:
            print("FAIL: the feed script imports study-local module(s) that are not setup components: "
                  + ", ".join(os.path.basename(p) for p in missing) + " (declare each with --module)")
            return 1
        print("import walk: " + (", ".join(f"{n} -> {os.path.basename(p)}" for n, p in sorted(found.items()))
                                 or "no study-local imports"))
    else:
        print("import walk: OFF (control only)")
    lines = [f"{sha(open(script, 'rb').read())}  {base}"]
    for name in ("FACT_SHEET", "NUDGE"):
        seg = segment(src, name)
        if seg is not None:
            lines.append(f"{sha(seg.encode())}  {base}:{name} (source segment)")
    for m in sorted(declared):
        lines.append(f"{sha(open(m, 'rb').read())}  imported module: {os.path.basename(m)}")
    lines.append(f"{sha(open(a.claude_md, 'rb').read())}  .claude/CLAUDE.md")
    lines.append(f"{sha(open(a.exam_line, 'rb').read())}  exam-line.txt")
    grant = open(a.grant_line_file, encoding="utf-8").read().rstrip("\n")
    lines.append(f"{sha(grant.encode())}  grant-line (no trailing newline)")
    lines.append(f"claude code:  {a.claude_code}")
    lines.append(f"install flags:      {a.install_flags}")
    lines.append(f"plugin src tree:    {a.plugin_tree}")
    lines.append(f"window setting:     {a.window}")
    if a.turns_per_round is not None:
        lines.append(f"turns per round:    {a.turns_per_round}")
    lines.sort()
    print("components:")
    print("\n".join(lines))
    text = "\n".join(lines) + "\n"
    print(f"SETUP ID (sha256 of the sorted components): {sha(text.encode())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
