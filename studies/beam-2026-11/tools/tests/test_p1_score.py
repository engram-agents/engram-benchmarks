"""Contract tests for p1_score.py (BEAM P1 scoring, step 2), written before it.

Contract (P1 rule entry part e, 11-16 correction, rulings 32566/32574/32673-4/32683):
  - Unblind only through the sealed key, whose sha256 must match; refuse if any pooled item is unscored or was served by
    another model, or if the key and the raw scores do not cover the same opaque ids.
  - Per session and question: PRIMARY score = the judge's score on its primary item; a missing answer scores 0 under every
    reading. SENSITIVITY score = the same, except a missing answer with a sensitivity item takes that item's score.
  - Reading (a): correct iff score == 1. Reading (c): the score itself.
  - Accuracy over the COUNTING questions (ids starting F) only; abstention items (A) reported apart.
  - Deciding statistic: mean over exchanges (that hold counting questions) of the within-exchange accuracy difference
    (K3 minus k1), reading (a). Cluster bootstrap over those exchanges, B resamples, numpy default_rng(seed),
    rng.integers(0, E, size=(B, E)), bounds at the 4th and 96th percentiles.
  - Last-position guard: the same statistic restricted to exchanges whose number is a multiple of 3 (round-last at k = 3).
  - Outcome: ACCEPTED iff lower >= -0.10 and guard >= -0.20 and k1 accuracy >= 0.50; WORSE iff upper < 0; else INCONCLUSIVE,
    naming which condition failed. WORSE takes precedence over INCONCLUSIVE; ACCEPTED requires all three.
"""
import json, os, sys
import numpy as np
import pytest
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import p1_score as s

def test_unblind_and_missing_scores_zero_with_sensitivity_substitution():
    key = {"P1": {"session": "K3", "qid": "F01", "kind": "primary"},
           "P2": {"session": "k1", "qid": "F01", "kind": "sensitivity"}}
    raw = {"P1": 1.0, "P2": 0.5}
    per = s.unblind(key, raw, qids=["F01"])
    assert per["K3"]["primary"]["F01"] == 1.0 and per["K3"]["sensitivity"]["F01"] == 1.0
    assert per["k1"]["primary"]["F01"] == 0.0 and per["k1"]["sensitivity"]["F01"] == 0.5
    assert per["k1"]["missing"] == ["F01"]

def test_reading_a_and_c():
    assert s.reading("a", 1.0) == 1.0 and s.reading("a", 0.5) == 0.0 and s.reading("a", 0.0) == 0.0
    assert s.reading("c", 0.5) == 0.5

def test_accuracy_counts_only_F_items():
    scores = {"F01": 1.0, "F02": 0.0, "A01": 1.0}
    assert s.accuracy(scores, "a") == 0.5

def test_exchange_mean_difference():
    ex = {"F01": 1, "F02": 1, "F03": 2}
    k3 = {"F01": 1.0, "F02": 0.0, "F03": 1.0}
    k1 = {"F01": 1.0, "F02": 1.0, "F03": 0.0}
    d, exs = s.exchange_diffs(k3, k1, ex, "a")
    assert exs == [1, 2] and list(d) == [-0.5, 1.0]

def test_bootstrap_matches_the_registered_method():
    d = np.array([-0.5, 1.0, 0.0, 0.25])
    lo, hi = s.bootstrap_bounds(d, boot=1000, seed=42)
    rng = np.random.default_rng(42); idx = rng.integers(0, 4, size=(1000, 4)); bm = d[idx].mean(axis=1)
    elo, ehi = np.percentile(bm, [4, 96])
    assert (lo, hi) == (elo, ehi)

def test_guard_exchanges_are_multiples_of_three():
    assert s.guard_exchanges([1, 2, 3, 6, 7, 9, 45]) == [3, 6, 9, 45]

@pytest.mark.parametrize("lo,hi,guard,k1acc,out", [
    (-0.05, 0.10, -0.10, 0.70, "ACCEPTED"),
    (-0.15, 0.10, -0.10, 0.70, "INCONCLUSIVE"),
    (-0.05, 0.10, -0.25, 0.70, "INCONCLUSIVE"),
    (-0.05, 0.10, -0.10, 0.45, "INCONCLUSIVE"),
    (-0.30, -0.01, -0.10, 0.70, "WORSE"),
    (-0.10, 0.10, -0.20, 0.50, "ACCEPTED"),
])
def test_outcome(lo, hi, guard, k1acc, out):
    o, why = s.outcome(lo, hi, guard, k1acc)
    assert o == out
    if out == "INCONCLUSIVE":
        assert why

def test_refuses_unscored_or_other_model_or_mismatched_ids():
    key = {"P1": {"session": "K3", "qid": "F01", "kind": "primary"}}
    with pytest.raises(s.ScoreRefused):
        s.check_raw(key, [{"opaque_id": "P1", "score": None, "served_by": "claude-sonnet-5-5"}])
    with pytest.raises(s.ScoreRefused):
        s.check_raw(key, [{"opaque_id": "P1", "score": 1.0, "served_by": "claude-opus-5-5"}])
    with pytest.raises(s.ScoreRefused):
        s.check_raw(key, [{"opaque_id": "P2", "score": 1.0, "served_by": "claude-sonnet-5-5"}])
    assert s.check_raw(key, [{"opaque_id": "P1", "score": 0.5, "served_by": "claude-sonnet-5-5-20261001"}]) == {"P1": 0.5}
