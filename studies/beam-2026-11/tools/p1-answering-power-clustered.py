#!/usr/bin/env python3
"""BEAM speed pilot P1, answering rule with the EXCHANGE as the cluster: pass rates by simulation.

This file is the study's harness, not shipped product code. Needs numpy and scipy (run it with an interpreter that has
them; the study's run interpreter does not). Questions sit in exchanges; facts from one exchange share whether the student
noted that exchange, so they are not independent. Model (Gaussian copula): for run r in {k=1, k}, exchange e, question q,
    X[r,e,q] = sqrt(RHO) * U[r,e] + sqrt(1 - RHO) * V[r,e,q]
RHO is the within-exchange correlation of the latent score. U and V are each correlated across the two runs at C, chosen so
that at equal accuracy P the share of questions the two runs answer differently equals D. A question is correct when
X < norm.ppf(P_r), with P_k1 = P and P_k = P - LOSS.
Deciding statistic (design owner's proposal, 2026-11-16): the mean over exchanges of (accuracy at k - accuracy at k = 1)
within the exchange; cluster bootstrap over exchanges (B resamples, seeded); pass if the 5th percentile >= -MARGIN.
WORSE (design owner's ruling): the one-sided 95 percent UPPER bound (95th percentile) is below zero.
Reported beside it, not deciding: Newcombe's question-level paired interval (method 10) on the same data.
usage: p1-answering-power-clustered.py [--trials N] [--boot B] [--seed S] [--counts n1,n2,...]
--counts: questions per exchange, one positive integer per exchange that has questions (default: 20 x 3 + 25 x 2).
"""
import argparse, math
from collections import Counter
import numpy as np
from scipy.stats import norm, multivariate_normal
from scipy.optimize import brentq

def calib_c(p, d):
    t = norm.ppf(p)
    f = lambda c: 2 * (p - multivariate_normal(mean=[0, 0], cov=[[1, c], [c, 1]]).cdf([t, t])) - d
    return brentq(f, -0.99, 0.999)

def newcombe10_lower(a, b, c, d, z=1.6449):
    def wilson(x, n):
        p = x / n; den = 1 + z * z / n; cen = p + z * z / (2 * n)
        half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)); return (cen - half) / den, (cen + half) / den
    n = a + b + c + d; p1 = (a + b) / n; p2 = (a + c) / n
    l1, u1 = wilson(a + b, n); l2, u2 = wilson(a + c, n)
    den = (a + b) * (c + d) * (a + c) * (b + d)
    phi = 0.0 if den == 0 else (a * d - b * c) / math.sqrt(den)
    dl = math.sqrt(max(0.0, (p1 - l1) ** 2 - 2 * phi * (p1 - l1) * (u2 - p2) + (u2 - p2) ** 2))
    return (p1 - p2) - dl

def cell(rng, counts, p, loss, d, rho, margin, trials, boot, lo_pct=5.0, hi_pct=95.0, method="percentile"):
    c = calib_c(p, d); E = len(counts); Q = int(sum(counts)); ex_of_q = np.repeat(np.arange(E), counts)
    cov = np.array([[1, c], [c, 1]]); L = np.linalg.cholesky(cov)
    t = np.array([norm.ppf(p), norm.ppf(p - loss)])  # run 0 = k1, run 1 = k
    pass_cl = pass_nc = worse = 0
    for _ in range(trials):
        U = rng.standard_normal((E, 2)) @ L.T; V = rng.standard_normal((Q, 2)) @ L.T
        X = math.sqrt(rho) * U[ex_of_q] + math.sqrt(1 - rho) * V
        y = X < t                                             # (Q, 2) booleans
        acc = np.zeros((E, 2)); np.add.at(acc, ex_of_q, y); acc /= np.asarray(counts)[:, None]
        dex = acc[:, 1] - acc[:, 0]
        idx = rng.integers(0, E, size=(boot, E)); res = dex[idx]; bm = res.mean(axis=1)
        if method == "studentized":
            # bootstrap-t over exchanges: t* = (mean* - mean) / (sd* / sqrt(E)); one-sided 95% bounds from t* quantiles
            m0 = dex.mean(); se0 = dex.std(ddof=1) / math.sqrt(E)
            sd_b = res.std(axis=1, ddof=1); ok = sd_b > 0
            tb = (bm[ok] - m0) / (sd_b[ok] / math.sqrt(E))
            if se0 == 0 or tb.size == 0:
                lo = hi = m0
            else:
                t_hi, t_lo = np.percentile(tb, [95, 5])
                lo, hi = m0 - t_hi * se0, m0 - t_lo * se0
        else:
            lo, hi = np.percentile(bm, [lo_pct, hi_pct])
        if lo >= -margin: pass_cl += 1
        if hi < 0: worse += 1                                 # one-sided 95% UPPER bound below zero: WORSE
        a = int(np.sum(y[:, 0] & y[:, 1])); b = int(np.sum(y[:, 1] & ~y[:, 0])); cc = int(np.sum(y[:, 0] & ~y[:, 1])); dd = Q - a - b - cc
        if newcombe10_lower(a, b, cc, dd) >= -margin: pass_nc += 1
    return pass_cl / trials, pass_nc / trials, worse / trials

def parse_counts(text):
    try:
        vals = [int(x) for x in text.split(",")]
    except ValueError:
        raise argparse.ArgumentTypeError(f"--counts needs comma-separated integers, got {text!r}")
    if not vals or any(v <= 0 for v in vals):
        raise argparse.ArgumentTypeError(f"--counts entries must be positive integers, got {text!r}")
    return vals

def layout(counts):
    m = Counter(counts)
    return " + ".join(f"{m[k]} x {k}" for k in sorted(m, reverse=True))

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--trials", type=int, default=2000); ap.add_argument("--boot", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=20261120); ap.add_argument("--p", type=float, default=0.75); ap.add_argument("--margin", type=float, default=0.10)
    ap.add_argument("--lo-pct", type=float, default=5.0, help="percentile for the lower bound (ACCEPTED)"); ap.add_argument("--hi-pct", type=float, default=95.0, help="percentile for the upper bound (WORSE)")
    ap.add_argument("--method", choices=["percentile", "studentized"], default="percentile")
    ap.add_argument("--counts", type=parse_counts, default=[3] * 20 + [2] * 25, help="comma-separated questions per exchange (default: 20 x 3 + 25 x 2)")
    a = ap.parse_args(); rng = np.random.default_rng(a.seed)
    counts = a.counts   # default 45 exchanges, 110 questions (the per-clause yield of the first third, about 2.4 per exchange)
    print(f"TABLE seed {a.seed}, trials {a.trials} per cell, bootstrap {a.boot}, base accuracy {a.p}, margin {a.margin}, "
          f"{len(counts)} exchanges, {sum(counts)} questions ({layout(counts)}), " + (f"bounds at percentiles {a.lo_pct}/{a.hi_pct}" if a.method == "percentile" else "studentized (bootstrap-t) bounds") + " (nominal one-sided 95%)")
    print("each cell: ACCEPTED-by-bound rate (clustered, deciding) / question-level Newcombe pass rate (beside it) / WORSE rate (clustered upper bound < 0)")
    for rho in (0.2, 0.6):
        for d in (0.15, 0.25, 0.35):
            out = []
            for loss in (0.0, 0.05, 0.10):
                pc, pn, pw = cell(rng, counts, a.p, loss, d, rho, a.margin, a.trials, a.boot, a.lo_pct, a.hi_pct, a.method)
                out.append(f"loss {loss:.2f}: {pc:.3f} / {pn:.3f} / worse {pw:.3f}")
            print(f"rho={rho:.1f} D={d:.2f} | " + " | ".join(out), flush=True)

if __name__ == "__main__":
    main()
