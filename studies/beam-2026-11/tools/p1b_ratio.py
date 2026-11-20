#!/usr/bin/env python3
"""BEAM P1b speed ratio R (design addition A2 and its stop line).

Usage: p1b_ratio.py --k3 PATH --k1 PATH [--start 46 --through 135]
       [--posthoc-exclude A-B ... | --posthoc-count-errored]

Each PATH is a run's turns.jsonl. Reading rows only: `exchange` rows plus any `compact` row (compaction counts wherever it
falls). Any other kind means the wrong run and is refused. R = (sum of the K = 3 run's wall seconds) / (sum of the k = 1
run's wall seconds), both over the same N = through - start + 1 exchanges, so the N cancels and a K = 3 round's wall is
never split. Decision, mechanical: R <= 0.75 -> speed bar MET; R > 0.75 -> NOT MET and the study runs at k = 1.
Exit 0 when computed (either decision), 2 for invalid input (a refusal names the file and the row).

Two DESCRIPTIVE post hoc readings exist beside the registered R, labelled "post hoc, not the registered R", neither primary,
never mixed, and never printing the registered decision line. The registered R itself still refuses a record with an error row.
  --posthoc-exclude A-B (repeatable): drop exchanges A..B from BOTH runs; each range must be whole K = 3 rounds of the run's
      own range; a row is dropped only when all its exchanges are inside; every dropped row is listed.
  --posthoc-count-errored: count a row with is_error set instead of refusing it (eof and timeout still refuse); each is listed.
"""
import argparse, json, os, re, sys

LINE = 0.75
BOUND = "bound: one run per k; R is a single measured ratio, not an interval"


class Refusal(Exception):
    pass


def _is_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and x == x and abs(x) != float("inf")


FLAGS = ("is_error", "eof", "timeout")
POSTHOC = "post hoc, not the registered R"


def load_run(path, k, start, through, excluded=frozenset(), count_errored=False):
    """Validate one run's turns.jsonl; return its counted-row summary. Raises Refusal.

    `excluded` is the post hoc exchange set: a row whose exchanges all fall inside it is listed, not summed (its flags are
    reported, not refused); a row partly inside is refused. `count_errored` counts is_error rows (listed); eof and timeout
    still refuse."""
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
    dropped, errored = [], []
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
        set_flags = [f for f in FLAGS if row.get(f)]
        is_dropped = False
        peek = row.get("exchanges")
        if excluded and kind == "exchange" and isinstance(peek, list) and peek:
            inside = [e in excluded for e in peek]
            if all(inside):
                is_dropped = True
            elif any(inside):
                raise Refusal(f"{label}: exchanges {peek!r} lie partly inside the excluded ranges (it would split a round)")
        if not is_dropped:
            for flag in FLAGS:
                if row.get(flag) and not (flag == "is_error" and count_errored):
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
            if is_dropped:
                dropped.append({"file": name, "i": row.get("i", n), "exchanges": exs, "wall_s": w, "flags": set_flags})
                continue
            exchanges.extend(exs)
        else:
            cp_n += 1
            cp_sum += w
        if "is_error" in set_flags and count_errored:
            errored.append({"file": name, "i": row.get("i", n), "exchanges": row.get("exchanges"), "wall_s": w,
                            "flags": set_flags})
        counted += 1
        total += w
    want = [e for e in range(start, through + 1) if e not in excluded]
    if exchanges != want:
        scope = f"{start}..{through}" + (" minus the excluded ranges" if excluded else "")
        raise Refusal(f"{name}: exchange rows carry {len(exchanges)} exchanges {exchanges[:3]}..{exchanges[-3:]}, "
                      f"not exactly {scope} ({len(want)}) each once, in order")
    return {"rows": counted, "sum": total, "n": len(want), "compact_n": cp_n, "compact_sum": cp_sum,
            "dropped": dropped, "errored": errored}


def parse_exclusions(specs, start, through):
    """Validate --posthoc-exclude ranges; return the set of excluded exchanges. Raises Refusal."""
    out = set()
    for spec in specs:
        tag = f"--posthoc-exclude {spec}"
        m = re.fullmatch(r"(\d+)-(\d+)", spec)
        if not m:
            raise Refusal(f"{tag}: not of the form A-B")
        a, b = int(m.group(1)), int(m.group(2))
        if b < a:
            raise Refusal(f"{tag}: B is below A")
        if a < start or b > through:
            raise Refusal(f"{tag}: outside the run's range {start}..{through}")
        if (a - start) % 3 or (b - a + 1) % 3:
            raise Refusal(f"{tag}: not whole K = 3 rounds of the run's range (needs (A - {start}) % 3 == 0 and a length "
                          f"divisible by 3)")
        rng = set(range(a, b + 1))
        if rng & out:
            raise Refusal(f"{tag}: overlaps another --posthoc-exclude range")
        out |= rng
    return out


def ratio(k3, k1):
    return k3["sum"] / k1["sum"]


def decision(r):
    if r <= LINE:
        return "R <= 0.75 -> speed bar MET"
    return "R > 0.75 -> speed bar NOT MET: the study runs at k = 1 whatever the answer test says"


def _list_rows(head, rows, with_flags):
    print(head)
    for r in rows:
        tail = f" | flags {', '.join(r['flags']) or 'none'}" if with_flags else ""
        print(f"{r['file']}: row {r['i']} | exchanges {r['exchanges']} | wall_s {r['wall_s']}{tail}")
    print()


def _show(label, s):
    print(f"{label}: rows counted {s['rows']} | sum {round(s['sum'], 4)} | per exchange {s['sum'] / s['n']:.4f} "
          f"| compact rows {s['compact_n']} sum {round(s['compact_sum'], 4)}")


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--k3", required=True)
    ap.add_argument("--k1", required=True)
    ap.add_argument("--start", type=int, default=46)
    ap.add_argument("--through", type=int, default=135)
    ap.add_argument("--posthoc-exclude", action="append", default=[], metavar="A-B")
    ap.add_argument("--posthoc-count-errored", action="store_true")
    try:
        a = ap.parse_args(argv[1:])
    except SystemExit as e:
        return 2 if e.code else 0
    if a.through < a.start:
        print("refused: --through is below --start", file=sys.stderr)
        return 2
    if a.posthoc_exclude and a.posthoc_count_errored:
        print("refused: --posthoc-exclude and --posthoc-count-errored are two readings, never mixed", file=sys.stderr)
        return 2
    try:
        excluded = parse_exclusions(a.posthoc_exclude, a.start, a.through)
        s3 = load_run(a.k3, 3, a.start, a.through, excluded, a.posthoc_count_errored)
        s1 = load_run(a.k1, 1, a.start, a.through, excluded, a.posthoc_count_errored)
        if a.posthoc_count_errored and not (s3["errored"] or s1["errored"]):
            raise Refusal("--posthoc-count-errored: no row has is_error set, so the flag would be meaningless")
    except Refusal as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    r = ratio(s3, s1)
    if a.posthoc_exclude or a.posthoc_count_errored:
        print("POST HOC READING, NOT THE REGISTERED R")
        if a.posthoc_exclude:
            _list_rows(f"EXCLUDED ROWS ({POSTHOC})", s3["dropped"] + s1["dropped"], True)
        else:
            _list_rows(f"COUNTED ERRORED ROWS ({POSTHOC})", s3["errored"] + s1["errored"], False)
        _show("K=3", s3)
        _show("k=1", s1)
        print(f"R (post hoc) = {r:.4f}; above {LINE}: {'yes' if r > LINE else 'no'}")
        print(BOUND)
        return 0
    _show("K=3", s3)
    _show("k=1", s1)
    print(f"R = {r:.4f}")
    print(decision(r))
    print(BOUND)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
