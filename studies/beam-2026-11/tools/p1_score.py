#!/usr/bin/env python3
"""BEAM P1 grading, step 2 of 2: unblind the judge's raw scores through the sealed key and apply the registered rule.

Rule: P1 rule entry part e, the 11-16 correction (exchange as the unit, cluster bootstrap 4th/96th percentiles, three
outcomes), the pre-log 80731986, and the design owner's rulings 32566, 32574, 32673-4 and 32683 (a question is correct
iff the judge gives its gold line 1; reading (c), the raw score, is secondary and never decides; missing answers score 0
under every reading; the sensitivity score substitutes the earlier text block's grade for each missing answer).
Statistic and bootstrap lines are taken from tools/p1-answering-power-clustered.py, the simulation that set the rule.

Usage: p1_score.py --key K --key-sha256 H --raw judge-raw.jsonl --gold final.md --gold-sha256 H --boot 1000 --seed S
"""
import argparse, hashlib, json, math, re, sys
import numpy as np

MODEL = "claude-sonnet-5-5"
MARGIN, GUARD, FLOOR = -0.10, -0.20, 0.50
LO_PCT, HI_PCT = 4.0, 96.0


class ScoreRefused(Exception):
    pass


def check_raw(key, records):
    raw = {}
    for r in records:
        if r.get("score") is None:
            raise ScoreRefused(f"{r['opaque_id']}: unscored ({r.get('reason')})")
        if not str(r.get("served_by", "")).startswith(MODEL):
            raise ScoreRefused(f"{r['opaque_id']}: served by {r.get('served_by')}")
        raw[r["opaque_id"]] = float(r["score"])
    if set(raw) != set(key):
        raise ScoreRefused(f"key and raw scores cover different ids: {sorted(set(key) ^ set(raw))[:10]}")
    return raw


def unblind(key, raw, qids):
    per = {}
    for sess in sorted({v["session"] for v in key.values()}):
        prim = {v["qid"]: raw[o] for o, v in key.items() if v["session"] == sess and v["kind"] == "primary"}
        sens_items = {v["qid"]: raw[o] for o, v in key.items() if v["session"] == sess and v["kind"] == "sensitivity"}
        missing = sorted(q for q in qids if q not in prim)
        primary = {q: prim.get(q, 0.0) for q in qids}
        sensitivity = {q: (prim[q] if q in prim else sens_items.get(q, 0.0)) for q in qids}
        per[sess] = {"primary": primary, "sensitivity": sensitivity, "missing": missing}
    return per


def reading(r, score):
    return (1.0 if score == 1.0 else 0.0) if r == "a" else float(score)


def accuracy(scores, r):
    f = [reading(r, v) for q, v in scores.items() if q.startswith("F")]
    return sum(f) / len(f)


def exchange_diffs(k3, k1, ex_of, r, only=None):
    exs = sorted({ex_of[q] for q in k3 if q.startswith("F") and (only is None or ex_of[q] in only)})
    d = []
    for e in exs:
        qs = [q for q in k3 if q.startswith("F") and ex_of[q] == e]
        d.append(sum(reading(r, k3[q]) for q in qs) / len(qs) - sum(reading(r, k1[q]) for q in qs) / len(qs))
    return np.array(d), exs


def bootstrap_bounds(d, boot, seed):
    rng = np.random.default_rng(seed)
    E = len(d)
    idx = rng.integers(0, E, size=(boot, E)); bm = d[idx].mean(axis=1)
    lo, hi = np.percentile(bm, [LO_PCT, HI_PCT])
    return lo, hi


def guard_exchanges(exs):
    return [e for e in exs if e % 3 == 0]


def outcome(lo, hi, guard, k1acc):
    if hi < 0:
        return "WORSE", "the upper bound is below zero"
    fails = []
    if lo < MARGIN: fails.append(f"overall lower bound {lo:+.4f} < {MARGIN:+.2f}")
    if guard < GUARD: fails.append(f"last-position guard {guard:+.4f} < {GUARD:+.2f}")
    if k1acc < FLOOR: fails.append(f"k=1 accuracy {k1acc:.4f} < validity floor {FLOOR:.2f}")
    if not fails:
        return "ACCEPTED", ""
    return "INCONCLUSIVE", "; ".join(fails)


def newcombe10_lower(a, b, c, d, z=1.6449):
    """Copied from tools/p1-answering-power-clustered.py (printed beside the verdict, decides nothing)."""
    def wilson(x, n):
        p = x / n; den = 1 + z * z / n; cen = p + z * z / (2 * n)
        half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)); return (cen - half) / den, (cen + half) / den
    n = a + b + c + d; p1 = (a + b) / n; p2 = (a + c) / n
    l1, u1 = wilson(a + b, n); l2, u2 = wilson(a + c, n)
    den = (a + b) * (c + d) * (a + c) * (b + d)
    phi = 0.0 if den == 0 else (a * d - b * c) / math.sqrt(den)
    dl = math.sqrt(max(0.0, (p1 - l1) ** 2 - 2 * phi * (p1 - l1) * (u2 - p2) + (u2 - p2) ** 2))
    return (p1 - p2) - dl


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", required=True); ap.add_argument("--key-sha256", required=True)
    ap.add_argument("--raw", required=True); ap.add_argument("--gold", required=True); ap.add_argument("--gold-sha256", required=True)
    ap.add_argument("--boot", type=int, default=1000); ap.add_argument("--seed", type=int, required=True)
    a = ap.parse_args(argv)
    try:
        kb = open(a.key, "rb").read()
        if _sha(kb) != a.key_sha256:
            raise ScoreRefused(f"key sha256 {_sha(kb)} != {a.key_sha256}")
        gb = open(a.gold, "rb").read()
        if _sha(gb) != a.gold_sha256:
            raise ScoreRefused(f"gold sha256 {_sha(gb)} != {a.gold_sha256}")
        key = json.loads(kb)
        raw = check_raw(key, [json.loads(l) for l in open(a.raw) if l.strip()])
    except ScoreRefused as e:
        print(f"REFUSED: {e}", file=sys.stderr); return 3
    ex_of = {}
    for line in gb.decode("utf-8").splitlines():
        m = re.match(r"^([AF]\d+) \| ex(\d+) \|", line)
        if m: ex_of[m.group(1)] = int(m.group(2))
    qids = sorted({v["qid"] for v in key.values()})
    per = unblind(key, raw, qids)
    F = [q for q in qids if q.startswith("F")]; A = [q for q in qids if q.startswith("A")]
    print(f"raw sha256 {_sha(open(a.raw, 'rb').read())}; key {a.key_sha256[:16]}; {len(raw)} scores; {len(F)} counting, {len(A)} abstention")
    for variant in ("primary", "sensitivity"):
        print(f"\n=== {variant.upper()} ===")
        k3, k1 = per["K3"][variant], per["k1"][variant]
        for sess, sc in (("K3", k3), ("k1", k1)):
            cnt = {v: sum(1 for q in F if sc[q] == v) for v in (0.0, 0.5, 1.0)}
            acnt = {v: sum(1 for q in A if sc[q] == v) for v in (0.0, 0.5, 1.0)}
            print(f"{sess}: accuracy (a) {accuracy(sc, 'a'):.4f}  (c) {accuracy(sc, 'c'):.4f}  counting 0/0.5/1 = {cnt[0.0]}/{cnt[0.5]}/{cnt[1.0]}"
                  f"  missing {per[sess]['missing']}  | abstention (a) {sum(reading('a', sc[q]) for q in A)}/{len(A)}  0/0.5/1 = {acnt[0.0]}/{acnt[0.5]}/{acnt[1.0]}")
        for r in ("a", "c"):
            d, exs = exchange_diffs(k3, k1, ex_of, r)
            lo, hi = bootstrap_bounds(d, a.boot, a.seed)
            gex = guard_exchanges(exs)
            gd, _ = exchange_diffs(k3, k1, ex_of, r, only=set(gex))
            gq = [q for q in F if ex_of[q] in set(gex)]
            gq_diff = (sum(reading(r, k3[q]) for q in gq) - sum(reading(r, k1[q]) for q in gq)) / len(gq)
            o, why = outcome(lo, hi, gd.mean(), accuracy(k1, r))
            tag = "DECIDES" if (variant == "primary" and r == "a") else "reported, does not decide"
            print(f"reading ({r}) [{tag}]: {len(exs)} exchanges; mean diff {d.mean():+.4f}; bootstrap B={a.boot} seed {a.seed} "
                  f"4th/96th = [{lo:+.4f}, {hi:+.4f}]; guard {len(gq)} questions in {len(gex)} exchanges: exchange-mean {gd.mean():+.4f}, "
                  f"question-level {gq_diff:+.4f}; k1 acc {accuracy(k1, r):.4f} -> {o}{(' (' + why + ')') if why else ''}")
            if r == "a":
                y3 = {q: reading('a', k3[q]) for q in F}; y1 = {q: reading('a', k1[q]) for q in F}
                both = sum(1 for q in F if y3[q] and y1[q]); only3 = sum(1 for q in F if y3[q] and not y1[q])
                only1 = sum(1 for q in F if y1[q] and not y3[q]); neither = len(F) - both - only3 - only1
                print(f"  paired table: both {both}, K3 only {only3}, k1 only {only1}, neither {neither}; D (discordant share) {(only3 + only1) / len(F):.4f}; "
                      f"Newcombe question-level lower {newcombe10_lower(both, only3, only1, neither):+.4f} (beside, decides nothing)")
                keep = [q for q in F if q not in ("F37", "F48")]
                k3w = {q: k3[q] for q in keep}; k1w = {q: k1[q] for q in keep}
                dw, exw = exchange_diffs(k3w, k1w, ex_of, "a"); low, hiw = bootstrap_bounds(dw, a.boot, a.seed)
                gw, _ = exchange_diffs(k3w, k1w, ex_of, "a", only=set(guard_exchanges(exw)))
                ow, whyw = outcome(low, hiw, gw.mean(), accuracy(k1w, "a"))
                print(f"  without F37, F48 (sensitivity read, never the verdict): mean {dw.mean():+.4f} [{low:+.4f}, {hiw:+.4f}] guard {gw.mean():+.4f} -> {ow}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
