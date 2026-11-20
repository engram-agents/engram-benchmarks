#!/usr/bin/env python3
"""BEAM P1b speed ratio R (design addition A2 and its stop line).

Usage: p1b_ratio.py --k3 PATH --k1 PATH [--start 46 --through 135]

Each PATH is a run's turns.jsonl. Reading rows only: `exchange` rows plus any `compact` row (compaction counts wherever it
falls). Any other kind means the wrong run and is refused. R = (sum of the K = 3 run's wall seconds) / (sum of the k = 1
run's wall seconds), both over the same N = through - start + 1 exchanges, so the N cancels and a K = 3 round's wall is
never split. Decision, mechanical: R <= 0.75 -> speed bar MET; R > 0.75 -> NOT MET and the study runs at k = 1.
Exit 0 when computed (either decision), 2 for invalid input (a refusal names the file and the row).
"""
import argparse, json, os, sys

LINE = 0.75
BOUND = "bound: one run per k; R is a single measured ratio, not an interval"


class Refusal(Exception):
    pass


def _is_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and x == x and abs(x) != float("inf")


def load_run(path, k, start, through):
    """Validate one run's turns.jsonl; return its counted-row summary. Raises Refusal."""
    name = os.path.basename(path)
    try:
        with open(path) as f:
            lines = [l for l in f if l.strip()]
    except OSError as e:
        raise Refusal(f"{name}: cannot read file ({e.strerror or e})")
    if not lines:
        raise Refusal(f"{name}: empty file")
    total = ex_sum = cp_sum = 0.0
    counted = cp_n = 0
    exchanges = []
    for n, line in enumerate(lines, 1):
        try:
            row = json.loads(line)
        except ValueError:
            raise Refusal(f"{name}: line {n}: unreadable JSON")
        if not isinstance(row, dict):
            raise Refusal(f"{name}: line {n}: unreadable JSON (row is not an object)")
        label = f"{name}: row {row.get('i', n)}"
        kind = row.get("kind")
        if kind not in ("exchange", "compact"):
            raise Refusal(f"{label}: kind {kind!r} is not a reading row (wrong run)")
        for flag in ("is_error", "eof", "timeout"):
            if row.get(flag):
                raise Refusal(f"{label}: {flag} is set")
        w = row.get("wall_s")
        if not _is_number(w) or w <= 0:
            raise Refusal(f"{label}: wall_s {w!r} is missing, not a number, or <= 0")
        if kind == "exchange":
            exs = row.get("exchanges")
            if row.get("per_round") != k:
                raise Refusal(f"{label}: per_round {row.get('per_round')!r} differs from this run's K = {k}")
            if not isinstance(exs, list) or len(exs) != k:
                raise Refusal(f"{label}: exchanges {exs!r} does not hold exactly K = {k} exchanges")
            exchanges.extend(exs)
        else:
            cp_n += 1
            cp_sum += w
        counted += 1
        total += w
    want = list(range(start, through + 1))
    if exchanges != want:
        raise Refusal(f"{name}: exchange rows carry {len(exchanges)} exchanges {exchanges[:3]}..{exchanges[-3:]}, "
                      f"not exactly {start}..{through} ({len(want)}) each once, in order")
    return {"rows": counted, "sum": total, "n": len(want), "compact_n": cp_n, "compact_sum": cp_sum}


def ratio(k3, k1):
    return k3["sum"] / k1["sum"]


def decision(r):
    if r <= LINE:
        return "R <= 0.75 -> speed bar MET"
    return "R > 0.75 -> speed bar NOT MET: the study runs at k = 1 whatever the answer test says"


def _show(label, s):
    print(f"{label}: rows counted {s['rows']} | sum {round(s['sum'], 4)} | per exchange {s['sum'] / s['n']:.4f} "
          f"| compact rows {s['compact_n']} sum {round(s['compact_sum'], 4)}")


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--k3", required=True)
    ap.add_argument("--k1", required=True)
    ap.add_argument("--start", type=int, default=46)
    ap.add_argument("--through", type=int, default=135)
    try:
        a = ap.parse_args(argv[1:])
    except SystemExit as e:
        return 2 if e.code else 0
    if a.through < a.start:
        print("refused: --through is below --start", file=sys.stderr)
        return 2
    try:
        s3 = load_run(a.k3, 3, a.start, a.through)
        s1 = load_run(a.k1, 1, a.start, a.through)
    except Refusal as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    r = ratio(s3, s1)
    _show("K=3", s3)
    _show("k=1", s1)
    print(f"R = {r:.4f}")
    print(decision(r))
    print(BOUND)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
