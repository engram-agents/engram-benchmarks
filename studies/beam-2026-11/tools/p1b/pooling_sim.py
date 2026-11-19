"""P1b design, requirement (2): what pooling P1's 75 questions with a new stretch does to error rates, CONDITIONAL on
P1 having come out INCONCLUSIVE (it did). Data model and statistic imported from tools/p1-answering-power-clustered.py.
Stage 1 = P1 layout (75 q / 38 exch); stage 2 = layout A (150 q / 76 exch), independent questions, same model.
Decision on the overall bound only (guard and floor ignored here: a stated simplification).
Reports: P(stage 1 INCONCLUSIVE); among those, P(ACCEPTED) by (i) stage 2 alone and (ii) pooled stage 1 + stage 2."""
import importlib.util, math, sys
import numpy as np
from scipy.stats import norm
spec = importlib.util.spec_from_file_location("pw", sys.argv[1]); pw = importlib.util.module_from_spec(spec); spec.loader.exec_module(pw)
P1 = [int(x) for x in "2,3,2,3,2,4,2,1,2,3,3,2,1,3,1,2,1,1,3,1,1,1,2,3,3,3,2,2,1,1,1,2,3,1,3,1,2,1".split(",")]
A = P1 + P1
def draw(rng, counts, p, loss, c, rho):
    E = len(counts); Q = sum(counts); exq = np.repeat(np.arange(E), counts)
    L = np.linalg.cholesky(np.array([[1, c], [c, 1]])); t = np.array([norm.ppf(p), norm.ppf(p - loss)])
    U = rng.standard_normal((E, 2)) @ L.T; V = rng.standard_normal((Q, 2)) @ L.T
    y = (math.sqrt(rho) * U[exq] + math.sqrt(1 - rho) * V) < t
    acc = np.zeros((E, 2)); np.add.at(acc, exq, y); acc /= np.asarray(counts)[:, None]
    return acc[:, 1] - acc[:, 0]
def bounds(rng, d, B=1000):
    bm = d[rng.integers(0, len(d), size=(B, len(d)))].mean(axis=1); return np.percentile(bm, [4, 96])
rng = np.random.default_rng(int(sys.argv[2])); trials = int(sys.argv[3]); p = 0.80
print(f"seed {sys.argv[2]}, trials {trials}, p {p}, margin -0.10, bounds 4/96, stage1 P1 75/38, stage2 A 150/76")
for rho in (0.2, 0.6):
    for D in (0.15, 0.25):
        c = pw.calib_c(p, D)
        for loss in (0.0, 0.10):
            inc = acc2 = accP = 0
            for _ in range(trials):
                d1 = draw(rng, P1, p, loss, c, rho); lo1, hi1 = bounds(rng, d1)
                if lo1 >= -0.10 or hi1 < 0: continue
                inc += 1
                d2 = draw(rng, A, p, loss, c, rho); lo2, _ = bounds(rng, d2); acc2 += lo2 >= -0.10
                loP, _ = bounds(rng, np.concatenate([d1, d2])); accP += loP >= -0.10
            print(f"rho {rho} D {D} loss {loss:.2f}: P(stage1 INCONCLUSIVE) {inc/trials:.3f}; given that, ACCEPTED by stage 2 alone {acc2/max(inc,1):.3f}, by pooled {accP/max(inc,1):.3f}  (n={inc})", flush=True)
