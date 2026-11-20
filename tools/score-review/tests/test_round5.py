"""Round 5 contract tests (PR 7 review round 3): amendment 8.

A8-1 a 2b needs its export record (same item, same reviewer, earlier in the file); A8-2 the arm-guess statistic reads
the mapped 2a; A8-3 the original named by an export must be this reviewer's 2a for this item; A8-4 a malformed export
record refuses with a message; A4g (draw guard) made discriminating. Written before the implementation. Synthetic.
"""
import pytest

from helpers import assert_refused, forge_export, forge_verdict, read_jsonl, run
from test_round2 import CStore
from test_round4 import _lj

def _2b(s, item="k1", reviewer="expert"):
    return s.record(item, 2, reviewer, s.vd(item, {"criterion": "correct"}, step="2b"))


# ---------------------------------------------------------------- A8-1

def test_a8_1_a_2b_with_no_export_is_refused_and_the_file_is_untouched(tmp_path):
    s = CStore(tmp_path)
    s.p2a("k1", {"x": "correct", "y": "correct"})
    before = s.verdicts.read_bytes()
    cp = _2b(s)
    assert_refused(cp)
    assert "export" in cp.stderr.lower()
    assert s.verdicts.read_bytes() == before


def test_a8_1_the_reported_sequence_cannot_be_built_2b_then_supersede(tmp_path):
    s = CStore(tmp_path)
    s.p1("k1")
    orig = s.p2a("k1", {"x": "correct", "y": "correct"})
    assert_refused(_2b(s))  # the 2b that used to be accepted without an export
    s.ok("k1", 2, "expert", s.vd("k1", _lj(s, "k1", "correct", "partly"), step="2a"),
         extra=("--supersedes", orig, "--reason", "reread"))
    assert not any(r.get("step") == "2b" for r in read_jsonl(s.verdicts))


def test_a8_1_a_2b_after_an_export_by_another_reviewer_is_refused(tmp_path):
    s = CStore(tmp_path)
    s.p2a("k1", {"x": "correct", "y": "correct"})
    forge_export(s, reviewer="other", after_2a_record_sha256="1" * 64)  # another reviewer's export for this item
    before = s.verdicts.read_bytes()
    cp = _2b(s)
    assert_refused(cp)
    assert "export" in cp.stderr.lower()
    assert s.verdicts.read_bytes() == before


def test_a8_1_a_2b_after_an_export_for_another_item_is_refused(tmp_path):
    s = CStore(tmp_path)
    s.p2a("k1", {"x": "correct", "y": "correct"})
    s.p2a("k2", {"x": "correct", "y": "partly"})
    cp, _ = s.export_criterion("k2")
    assert cp.returncode == 0
    assert_refused(_2b(s, "k1"))


def test_a8_1_a_2b_after_the_reviewers_own_export_is_accepted_and_a_2b_supersede_too(tmp_path):
    s = CStore(tmp_path)
    s.p2a("k1", {"x": "correct", "y": "correct"})
    cp, _ = s.export_criterion("k1")
    assert cp.returncode == 0
    first = s.ok("k1", 2, "expert", s.vd("k1", {"criterion": "correct"}, step="2b"))
    s.ok("k1", 2, "expert", s.vd("k1", {"criterion": "partly"}, step="2b"),
         extra=("--supersedes", first, "--reason", "reread"))  # the export is earlier in the file: still accepted


# ---------------------------------------------------------------- A8-2

def test_a8_2_arm_guess_statistic_reads_the_mapped_original_2a(tmp_path):
    s = CStore(tmp_path)
    s.p1("k1")
    orig = s.p2a("k1", {"x": "correct", "y": "correct"}, guesses_arms={"x": "CRIT-ARM-TOKEN-x"})  # a correct guess
    cp, _ = s.export_criterion("k1")
    assert cp.returncode == 0
    letter = s.letter("k1", s.ids["k1"]["x"])
    s.ok("k1", 2, "expert", s.vd("k1", _lj(s, "k1", "correct", "partly"), step="2a",
                                  guesses={"arms": {letter: "CRIT-ARM-TOKEN-y"}}),  # the revision guesses wrong
         extra=("--supersedes", orig, "--reason", "reread"))
    s.ok("k1", 2, "expert", s.vd("k1", {"criterion": "correct"}, step="2b"))
    cp, out = s.map()
    assert cp.returncode == 0, cp.stderr
    rep = tmp_path / "r.md"
    cp = run("report", "--items", s.items, "--grades", s.grades, "--verdicts", s.verdicts, "--outcomes", out,
             "--out", rep, "--unblind", "--keys-dir", s.keys)
    assert cp.returncode == 0, cp.stderr
    assert "Arm guessed correctly: 1 of 1" in rep.read_text()


# ---------------------------------------------------------------- A8-3

def _forged_anchor(s, variant):
    """k1: a real 2a, then a forged hash-valid export naming `variant`, a forged 2b, then a real supersede of the 2a."""
    s.p1("k1")
    orig = s.p2a("k1", {"x": "correct", "y": "correct"})
    if variant == "other_item":
        named = s.p2a("k2", {"x": "correct", "y": "partly"})
    elif variant == "a_2b_record":
        named = forge_verdict(s.verdicts, item_id="k1", phase=2, step="2b", reviewer="expert",
                              judgement={"criterion": "correct"})
    else:
        raise AssertionError(variant)
    forge_export(s, after_2a_record_sha256=named)
    if variant != "a_2b_record":
        forge_verdict(s.verdicts, item_id="k1", phase=2, step="2b", reviewer="expert",
                      judgement={"criterion": "correct"})
    s.ok("k1", 2, "expert", s.vd("k1", _lj(s, "k1", "correct", "partly"), step="2a"),
         extra=("--supersedes", orig, "--reason", "reread"))


@pytest.mark.parametrize("variant", ["other_item", "a_2b_record"])
def test_a8_3_an_export_naming_a_record_that_is_not_this_reviewers_2a_for_this_item_is_refused(tmp_path, variant):
    s = CStore(tmp_path)
    _forged_anchor(s, variant)
    cp, _ = s.map()
    assert_refused(cp)
    assert "not this reviewer's 2a for this item" in cp.stderr and "Traceback" not in cp.stderr


def test_a8_3_an_export_naming_another_reviewers_2a_is_refused(tmp_path):
    s = CStore(tmp_path)
    s.p1("k1")
    other = forge_verdict(s.verdicts, item_id="k1", phase=2, step="2a", reviewer="other", judgement={})
    forge_export(s, after_2a_record_sha256=other)
    forge_verdict(s.verdicts, item_id="k1", phase=2, step="2a", reviewer="expert", judgement={}, supersedes=other,
                  reason="x")
    forge_verdict(s.verdicts, item_id="k1", phase=2, step="2b", reviewer="expert", judgement={"criterion": "correct"})
    cp, _ = s.map()
    assert_refused(cp)
    assert "not this reviewer's 2a for this item" in cp.stderr and "Traceback" not in cp.stderr


# ---------------------------------------------------------------- A8-4

@pytest.mark.parametrize("field", ["reviewer", "after_2a_record_sha256", "item_id"])
def test_a8_4_a_malformed_export_record_refuses_with_a_message_not_a_traceback(tmp_path, field):
    s = CStore(tmp_path)
    s.p1("k1")
    orig = s.p2a("k1", {"x": "correct", "y": "correct"})
    forge_export(s, drop=(field,), after_2a_record_sha256=orig)
    forge_verdict(s.verdicts, item_id="k1", phase=2, step="2b", reviewer="expert", judgement={"criterion": "correct"})
    cp, _ = s.map()
    assert_refused(cp)
    assert "Traceback" not in cp.stderr and "export" in cp.stderr.lower()
    cp = _2b(s)
    assert_refused(cp)
    assert "Traceback" not in cp.stderr


# ---------------------------------------------------------------- A4g, made discriminating

def test_a4g_draw_ignores_an_export_record_that_has_no_phase_and_does_not_count_it_as_a_phase1_verdict(tmp_path):
    """Only an export record is in the store: no phase-1 verdict exists, so the draw must go through. (A draw that
    reads a missing `phase` as phase 1 refuses here; one that does not guard the lookup crashes.)"""
    s = CStore(tmp_path)
    forge_export(s, item_id="k2")
    cp = run("draw", "--items", s.items, "--grades", s.grades, "--verdicts", s.verdicts, "--draws", tmp_path / "d2.jsonl",
             "--run", "r2", "--n", "0", "--seed", "s")
    assert cp.returncode == 0, cp.stderr
    assert "Traceback" not in cp.stderr


# ---------------------------------------------------------------- the boundary is the reviewer's own export

def test_a8_an_export_by_another_reviewer_is_not_the_boundary_for_this_reviewers_supersede(tmp_path):
    s = CStore(tmp_path)
    s.p1("k1")
    orig = s.p2a("k1", {"x": "correct", "y": "correct"})
    forge_export(s, reviewer="other", after_2a_record_sha256=orig)  # another reviewer was shown the criterion first
    new = s.ok("k1", 2, "expert", s.vd("k1", _lj(s, "k1", "correct", "partly"), step="2a"),
               extra=("--supersedes", orig, "--reason", "reread"))  # expert has seen nothing yet: an ordinary correction
    cp, _ = s.export_criterion("k1")
    assert cp.returncode == 0, cp.stderr
    s.ok("k1", 2, "expert", s.vd("k1", {"criterion": "correct"}, step="2b"))
    k1 = s.outcomes()["k1"]
    assert k1["phases"]["2"]["record_sha256"] == new and "post_reveal_revision" not in k1["phases"]["2"]
    assert k1["routing"]["forced_phase3"] is False
