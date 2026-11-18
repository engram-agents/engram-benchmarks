#!/usr/bin/env python3
"""Build the frozen P1 question file from the key-fact list (BEAM P1 answering). This file is the study's harness, not
shipped product code.

Reads the key-fact list (item rows `ID | exchange | style | QUESTION || GOLD`, ids F<n> for facts and A<n> for
abstention items; every other line is ignored) and writes a JSON list of {"id", "question"}: the question text only,
never the gold. Items are all rows minus --exclude, in this order: ids sorted lexicographically, then
`random.Random(SEED).shuffle(ids)`. The same inputs give byte-identical JSON.

Refuses (exit 2, nothing written) if sha256(list) is not --expect-sha256, if an id repeats, if an --exclude id is not in
the list, if a row cannot be parsed, if the list has no rows, or if --out already exists (a frozen file is never
overwritten). Prints the item count, the order (one id per line) and the sha256 of the written JSON.

usage: p1-question-file.py --list F --expect-sha256 H [--exclude ID[,ID...]] --seed N --out JSON
"""
import argparse, hashlib, json, os, random, re, sys

ROW_START = re.compile(r"[FA][0-9]+ \| ")
ROW = re.compile(r"([FA][0-9]+) \| (\S+) \| (\S+) \| (\S.*?) \|\| (\S.*)")


def refuse(msg):
    print(f"REFUSE: {msg}", file=sys.stderr)
    sys.exit(2)


def parse_rows(text):
    """[(id, question)] in file order. A line that starts like an item row but does not parse is a refusal."""
    rows = []
    for n, line in enumerate(text.splitlines(), 1):
        if not ROW_START.match(line):
            continue
        m = ROW.fullmatch(line.rstrip())
        if not m:
            refuse(f"line {n} looks like an item row but cannot be parsed: {line[:80]!r}")
        rows.append((m.group(1), m.group(4).strip()))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", required=True); ap.add_argument("--expect-sha256", required=True)
    ap.add_argument("--exclude", default=""); ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    try:
        raw = open(a.list, "rb").read()
    except OSError as e:
        refuse(f"cannot read the list: {e}")
    got = hashlib.sha256(raw).hexdigest()
    if got != a.expect_sha256:
        refuse(f"the list hashes to {got}, not the expected {a.expect_sha256}")
    rows = parse_rows(raw.decode("utf-8"))
    if not rows:
        refuse("the list holds no item rows")
    seen = set()
    for i, _ in rows:
        if i in seen:
            refuse(f"id {i} repeats in the list")
        seen.add(i)
    exclude = [x.strip() for x in a.exclude.split(",") if x.strip()]
    for x in exclude:
        if x not in seen:
            refuse(f"--exclude id {x} is not in the list")
    if os.path.exists(a.out):
        refuse(f"{a.out} already exists (a frozen question file is never overwritten)")
    questions = {i: q for i, q in rows if i not in set(exclude)}
    ids = sorted(questions)
    random.Random(a.seed).shuffle(ids)
    data = (json.dumps([{"id": i, "question": questions[i]} for i in ids], ensure_ascii=False, indent=1) + "\n").encode("utf-8")
    with open(a.out, "xb") as f:
        f.write(data)
    print(f"{len(ids)} items")
    for i in ids:
        print(i)
    print(f"sha256 {hashlib.sha256(data).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
