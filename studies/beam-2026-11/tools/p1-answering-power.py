#!/usr/bin/env python3
"""BEAM speed pilot P1, answering rule: how often the paired non-inferiority rule passes, by simulation.

This file is the study's harness, not shipped product code. Each question's paired outcome (k right?, k = 1 right?) is
drawn from an exact joint distribution: with base accuracy P1 for k = 1, a true loss L for k, and a discordant share D
(the share of questions the two runs answer differently), the cells are
    only k right      b = (D - L) / 2
    only k = 1 right  c = (D + L) / 2
    both right        a = P1 - c
    both wrong        d = 1 - a - b - c
The rule passes when the one-sided 95 percent lower bound of acc(k) - acc(k=1), by Newcombe's paired score interval
(1998, method 10, two-sided 90 percent), is at or above -MARGIN.  usage: p1-answering-power.py [--trials N] [--seed S]
"""
import argparse, math, random

def wilson(x, n, z):
    p = x / n; den = 1 + z * z / n; cen = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (cen - half) / den, (cen + half) / den

def newcombe10_lower(a, b, c, d, z):
    n = a + b + c + d; p1 = (a + b) / n; p2 = (a + c) / n
    l1, u1 = wilson(a + b, n, z); l2, u2 = wilson(a + c, n, z)
    den = (a + b) * (c + d) * (a + c) * (b + d)
    phi = 0.0 if den == 0 else (a * d - b * c) / math.sqrt(den)   # Newcombe 1998 method 10 (no continuity correction)
    dl = math.sqrt(max(0.0, (p1 - l1) ** 2 - 2 * phi * (p1 - l1) * (u2 - p2) + (u2 - p2) ** 2))
    return (p1 - p2) - dl

def pass_rate(n, p_base, loss, disc, margin, trials, rng, z=1.6449):
    b = (disc - loss) / 2; c = (disc + loss) / 2; a = p_base - c; d = 1 - a - b - c
    assert min(a, b, c, d) >= 0, "infeasible cell"
    cum = [a, a + b, a + b + c]
    hits = 0
    for _ in range(trials):
        A = B = C = D = 0
        for _ in range(n):
            u = rng.random()
            if u < cum[0]: A += 1
            elif u < cum[1]: B += 1
            elif u < cum[2]: C += 1
            else: D += 1
        if newcombe10_lower(A, B, C, D, z) >= -margin: hits += 1
    return hits / trials

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=4000); ap.add_argument("--seed", type=int, default=20261116)
    ap.add_argument("--n", default="90,80,30,18", help="comma-separated question counts")
    ap.add_argument("--disc", default="0.15,0.25,0.35", help="comma-separated discordant shares D")
    ap.add_argument("--loss", default="0,0.05,0.10,0.15", help="comma-separated true losses")
    ap.add_argument("--margin", default="0.10", help="comma-separated margins")
    ap.add_argument("--base", type=float, default=0.75)
    a = ap.parse_args(); rng = random.Random(a.seed)
    fl = lambda t: [float(x) for x in t.split(",")]
    ns = [int(x) for x in a.n.split(",")]
    print(f"TABLE seed {a.seed}, trials {a.trials} per cell, base accuracy {a.base}, margins {a.margin}")
    for n in ns:
        for disc in fl(a.disc):
            cells = []
            for loss in fl(a.loss):
                for m in fl(a.margin):
                    cells.append(f"loss {loss:.2f} m{round(m*100)} {pass_rate(n, a.base, loss, disc, m, a.trials, rng):.3f}")
            print(f"n={n:3d} D={disc:.2f} | " + " | ".join(cells), flush=True)

if __name__ == "__main__":
    main()
