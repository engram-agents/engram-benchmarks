"""Round 8 contract tests: the routing fix (a phase-2 record puts an item in phase 2) and the letters-only `reveal`.

R1 an item is in phase 2 when it is in set (a), (b), (c), forced, or has a phase-2 record; R2 unquestioned_control is
unchanged, so any complete phase-2 outcome other than key_stands is in phase 3 whatever set the item is in.
V  `reveal` prints an item's letters and the sha256 of its key file, only once the item is control_settled or settled,
   and never the key file text or its seed. Written before the implementation. Synthetic data only.
"""
import ast
import hashlib
import json
import pathlib

import pytest

from helpers import SEED, SEED_2, Store, read_jsonl, run  # SEED: a canonical seed that must never leave through any verb
from test_round2 import CStore



def _fixture(root):
    """None of these items is in set (a) (all full) and none is drawn except i05.

    i01 phase 2 key_wrong (pending); i02 phase 2 grading_error (pending); i03 phase 2 key_stands (control_settled);
    i04 no phase-2 record (not_reviewed); i05 drawn, both key_stands (control_settled); i06 key_wrong in all three
    phases (settled). Every key file carries SEED.
    """
    s = Store(root, item_ids=["i01", "i02", "i03", "i04", "i05", "i06"])
    s.write_draws(["i05"])
    for item in s.item_ids:
        j = s.honest(item)
        if item == "i06":
            j[s.oid(item)] = "partly"
        s.p1(item, j)
    for item in ["i01", "i02", "i03", "i05", "i06"]:
        s.packet2(item, seed=SEED)
        j = s.honest(item)
        if item in ("i01", "i06"):
            j[s.oid(item)] = "partly"
        if item == "i02":
            j[s.a1(item)] = "wrong"
        s.p2(item, j)
    j6 = s.honest("i06")
    j6[s.oid("i06")] = "partly"
    s.p3("i06", j6)
    return s


@pytest.fixture
def fx(tmp_path):
    s = _fixture(tmp_path)
    return s, s.outcomes()


# ---------------------------------------------------------------- R. routing

def test_r_a_phase2_key_wrong_in_no_set_is_in_phase3_and_pending(fx):
    _, o = fx
    r = o["i01"]
    assert r["phases"]["2"]["outcome"] == "key_wrong"
    assert not (r["routing"]["set_a"] or r["routing"]["set_b"] or r["routing"]["set_c"] or r["routing"]["forced_phase3"])
    assert r["routing"]["in_phase2"] is True and r["routing"]["in_phase3"] is True
    assert r["routing"]["phase3_required"] is True and r["status"] == "pending"


def test_r_b_phase2_grading_error_in_no_set_is_in_phase3_and_pending(fx):
    _, o = fx
    assert o["i02"]["phases"]["2"]["outcome"] == "grading_error"
    assert o["i02"]["routing"]["in_phase3"] is True and o["i02"]["status"] == "pending"


def test_r_c_phase2_key_stands_in_no_set_is_control_settled(fx):
    _, o = fx
    r = o["i03"]
    assert r["routing"]["in_phase2"] is True and r["routing"]["in_phase3"] is False
    assert r["routing"]["unquestioned_control"] is True and r["status"] == "control_settled"


def test_r_d_no_phase2_record_stays_not_reviewed_and_says_so(fx):
    _, o = fx
    r = o["i04"]
    assert r["status"] == "not_reviewed"  # unchanged behaviour: green before and after the fix
    assert r["routing"]["in_phase2"] is False and r["routing"]["in_phase3"] is False
    assert r["routing"].get("phase2_recorded", False) is False


def test_r_d_phase2_recorded_is_false_in_the_row_of_an_item_with_no_phase2_record(fx):
    _, o = fx
    assert o["i04"]["routing"]["phase2_recorded"] is False


def test_r_e_a_drawn_item_with_both_key_stands_is_control_settled(fx):
    _, o = fx
    r = o["i05"]
    assert r["routing"]["set_c"] is True
    assert r["status"] == "control_settled"


def test_r_phase2_recorded_is_in_every_row_and_true_exactly_where_a_record_exists(fx):
    _, o = fx
    assert {k: v["routing"]["phase2_recorded"] for k, v in o.items()} == {
        "i01": True, "i02": True, "i03": True, "i04": False, "i05": True, "i06": True}


def test_r_f_a_criterion_item_in_no_set_with_only_its_2a_is_in_phase2_and_pending(tmp_path):
    s = CStore(tmp_path)
    s.draws.write_text("")  # k1 (all full) is no longer drawn: it is in no set
    s.p1("k1")
    s.p2a("k1", {"x": "correct", "y": "correct"})
    cp, out = s.map()
    assert cp.returncode == 0, cp.stderr
    r = {x["item_id"]: x for x in read_jsonl(out)}["k1"]
    assert not (r["routing"]["set_a"] or r["routing"]["set_b"] or r["routing"]["set_c"])
    assert r["routing"]["phase2_recorded"] is True and r["routing"]["in_phase2"] is True
    assert r["status"] == "phase2_pending"


def test_r_a_phase2_dispute_always_routes_to_phase3_whatever_set_the_item_is_in():
    import score_review as sr
    full = {"x": {"a": "full"}}
    low = {"x": {"a": "partial"}}
    for levels in (full, low):
        for drawn in (set(), {"x"}):
            for bad in ("key_wrong", "grading_error", "ambiguous_source", "ambiguous_split"):
                rt = sr.route(levels, {"x": "key_stands"}, {"x": bad}, drawn, (), {"x"})["x"]
                assert rt["in_phase3"] is True, (levels, drawn, bad)
    rt = sr.route(full, {"x": "key_stands"}, {"x": "key_stands"}, set(), (), {"x"})["x"]
    assert rt["in_phase3"] is False and rt["unquestioned_control"] is True


def test_r_report_lists_a_phase2_dispute_in_no_set_as_phase3_pending(fx):
    s, _ = fx
    out = s.root / "report.md"
    cp = run("report", "--items", s.items, "--grades", s.grades, "--verdicts", s.verdicts,
             "--outcomes", s.root / "outcomes.jsonl", "--out", out)
    assert cp.returncode == 0, cp.stderr
    text = out.read_text(encoding="utf-8")
    sec = text.split("## Item i01")[1].split("## Item i02")[0]
    assert "Status: **pending**" in sec and "Phase 3: **pending**" in sec
    sec3 = text.split("## Item i03")[1].split("## Item i04")[0]
    assert "Phase 3: **pending**" not in sec3


def test_r_export_phase3_accepts_a_phase2_dispute_in_no_set(fx):
    s, _ = fx
    out = s.root / "p3.json"
    cp = run("export-phase3", "--items", s.items, "--grades", s.grades, "--verdicts", s.verdicts,
             "--keys-dir", s.keys, "--item", "i01", "--out", out)
    assert cp.returncode == 0, cp.stderr
    assert json.loads(out.read_text())["phase2"]["outcome"] == "key_wrong"


# ---------------------------------------------------------------- V. reveal

def _reveal(s, item, draws=True):
    args = ["reveal", "--items", s.items, "--grades", s.grades, "--verdicts", s.verdicts, "--keys-dir", s.keys,
            "--item", item]
    if draws:
        args += ["--draws", s.draws]
    return run(*args)


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_v_a_a_control_settled_item_gives_letters_and_key_sha_and_nothing_else(fx):
    s, _ = fx
    cp = _reveal(s, "i03")
    assert cp.returncode == 0, cp.stderr
    lines = cp.stdout.splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert set(row) == {"item_id", "status", "letters", "key_sha256"}
    assert row["item_id"] == "i03" and row["status"] == "control_settled"
    assert row["letters"] == s.key("i03")["letters"]
    assert row["key_sha256"] == _sha(s.keys / "i03.json")
    assert SEED not in cp.stdout and SEED not in cp.stderr


def test_v_a_a_settled_item_is_revealed_too_and_no_draws_file_is_needed_for_it(fx):
    s, _ = fx
    cp = _reveal(s, "i06", draws=False)
    assert cp.returncode == 0, cp.stderr
    row = json.loads(cp.stdout)
    assert row["status"] == "settled" and row["key_sha256"] == _sha(s.keys / "i06.json")
    assert SEED not in cp.stdout and SEED not in cp.stderr


@pytest.mark.parametrize("item", ["i01", "i02", "i04"])
def test_v_b_a_pending_or_unreviewed_item_is_refused_with_nothing_on_stdout(fx, item):
    s, _ = fx
    cp = _reveal(s, item)
    assert cp.returncode == 1, (cp.returncode, cp.stderr)
    assert cp.stdout == ""
    assert "refused" in cp.stderr and "control_settled" in cp.stderr
    assert SEED not in cp.stderr


def test_v_c_an_unknown_item_is_refused(fx):
    s, _ = fx
    cp = _reveal(s, "nope")
    assert cp.returncode == 1 and cp.stdout == "" and "unknown item" in cp.stderr
    assert SEED not in cp.stderr


def test_v_reveal_writes_nothing(fx):
    s, _ = fx
    before = sorted((str(p), p.read_bytes()) for p in s.root.rglob("*") if p.is_file())
    _reveal(s, "i03")
    _reveal(s, "i01")
    assert sorted((str(p), p.read_bytes()) for p in s.root.rglob("*") if p.is_file()) == before


def test_v_d_the_seed_has_no_path_out_of_map_or_report(fx):
    s, _ = fx
    cp, out = s.map()
    assert cp.returncode == 0 and SEED not in cp.stdout + cp.stderr
    assert SEED not in out.read_text(encoding="utf-8")
    statuses = {r["status"] for r in read_jsonl(out)}
    assert {"settled", "pending", "control_settled"} <= statuses
    rep = s.root / "report.md"
    for extra in ([], ["--unblind", "--keys-dir", s.keys]):
        cp = run("report", "--items", s.items, "--grades", s.grades, "--verdicts", s.verdicts,
                 "--outcomes", out, "--out", rep, *extra)
        assert cp.returncode == 0, cp.stderr
        assert SEED not in cp.stdout + cp.stderr + rep.read_text(encoding="utf-8")


def test_v_reveal_reads_the_key_file_once_so_letters_and_sha_come_from_the_same_bytes(fx, monkeypatch):
    import builtins
    import score_review as sr
    s, _ = fx
    key = str(s.keys / "i03.json")
    opened = []
    real = builtins.open

    def counting(file, *a, **k):
        if str(file) == key:
            opened.append(file)
        return real(file, *a, **k)

    monkeypatch.setattr(builtins, "open", counting)
    ns = type("A", (), dict(items=str(s.items), grades=str(s.grades), verdicts=str(s.verdicts), keys_dir=str(s.keys),
                            draws=str(s.draws), item="i03"))
    # outcomes are computed first (map reads the key of every item with a phase-2 verdict); count only reveal's own reads
    # by comparing with the reads `compute_outcomes` alone makes
    ctx = sr.Ctx(ns.items, ns.grades, ns.verdicts, ns.keys_dir)
    sr.compute_outcomes(ctx, sr.read_jsonl(ns.draws, required=False), lambda m: None)
    base = len(opened)
    del opened[:]
    sr.cmd_reveal(ns)
    assert len(opened) == base + 1, (base, len(opened))


def test_v_cmd_reveal_has_no_open_of_its_own():
    src = (pathlib.Path(sr_path()) ).read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef) and n.name == "cmd_reveal")
    opens = [n for n in ast.walk(fn) if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "open"]
    assert opens == []


def sr_path():
    import score_review
    return score_review.__file__


def _creveal(s, item):
    return run("reveal", "--items", s.items, "--grades", s.grades, "--verdicts", s.verdicts, "--keys-dir", s.keys,
               "--draws", s.draws, "--item", item)


def test_v_a_a_criterion_item_with_its_2a_and_2b_is_revealed_with_the_same_four_keys(tmp_path):
    s = CStore(tmp_path)
    s.packet2("k1", seed=SEED)
    s.p1("k1")
    s.p2a("k1", {"x": "correct", "y": "correct"})
    s.p2b("k1", "correct")
    cp = _creveal(s, "k1")
    assert cp.returncode == 0, cp.stderr
    row = json.loads(cp.stdout)
    assert len(cp.stdout.splitlines()) == 1 and set(row) == {"item_id", "status", "letters", "key_sha256"}
    assert row["status"] == "control_settled" and row["letters"] == json.loads((s.keys / "k1.json").read_text())["letters"]
    assert row["key_sha256"] == _sha(s.keys / "k1.json")
    assert SEED not in cp.stdout + cp.stderr


def test_v_b_a_criterion_item_with_only_its_2a_is_refused_with_nothing_on_stdout(tmp_path):
    s = CStore(tmp_path)
    s.packet2("k4", seed=SEED)
    s.p1("k4")
    s.p2a("k4", {"x": "correct", "y": "partly"})
    cp = _creveal(s, "k4")
    assert cp.returncode == 1 and cp.stdout == ""
    assert "phase2_pending" in cp.stderr and SEED not in cp.stderr


# ---------------------------------------------------------------- canonical seeds: 64 lowercase hex characters

BAD_SEEDS = ["seedx", "A1B2C3D4" * 8, ("a1b2c3d4" * 8)[:-1], ("a1b2c3d4" * 8) + "0", "g1b2c3d4" * 8, ""]


@pytest.mark.parametrize("bad", BAD_SEEDS)
def test_s_packet2_refuses_a_non_canonical_seed_and_never_echoes_it(tmp_path, bad):
    s = Store(tmp_path)
    cp = run("packet2", "--items", s.items, "--item", "i01", "--seed", bad, "--keys-dir", s.keys,
             "--out-dir", tmp_path / "packets")
    assert cp.returncode == 1 and "refused" in cp.stderr and "--seed" in cp.stderr, (cp.returncode, cp.stderr)
    if bad:
        assert bad not in cp.stderr + cp.stdout
    assert not (s.keys / "i01.json").exists() and not (tmp_path / "packets").exists()
    assert s.packet2("i01").returncode == 0  # positive control: the canonical default works


@pytest.mark.parametrize("bad", BAD_SEEDS)
def test_s_import_beam_refuses_a_non_canonical_seed_and_never_echoes_it(tmp_path, bad):
    cp = run("import-beam", "--parquet", tmp_path / "none.parquet", "--conv", "c1", "--answers", tmp_path / "none.jsonl",
             "--seed", bad, "--items-out", tmp_path / "i.jsonl", "--grades-out", tmp_path / "g.jsonl")
    assert cp.returncode == 1 and "refused" in cp.stderr and "--seed" in cp.stderr, (cp.returncode, cp.stderr)
    if bad:
        assert bad not in cp.stderr + cp.stdout
    assert "file not found" not in cp.stderr and not (tmp_path / "i.jsonl").exists()  # refused before any file is read


def test_s_draw_seed_is_public_randomness_and_stays_free_form(tmp_path):
    s = Store(tmp_path)
    cp = run("draw", "--items", s.items, "--grades", s.grades, "--run", "r1", "--n", "1", "--seed", "drand-round-123",
             "--draws", s.draws, "--verdicts", s.verdicts)
    assert cp.returncode == 0, cp.stderr


def test_s_reveal_refuses_a_key_file_whose_seed_is_short_with_nothing_on_stdout(fx):
    import hashlib as _h
    s, _ = fx
    path = s.keys / "i03.json"
    key = json.loads(path.read_text())
    key["seed"] = "seedx"
    path.write_text(json.dumps(key, sort_keys=True) + "\n", encoding="utf-8")
    cp = _reveal(s, "i03")
    assert cp.returncode == 1 and cp.stdout == "" and "refused" in cp.stderr and "i03" in cp.stderr
    assert "seedx" not in cp.stderr
    assert _reveal(s, "i05").returncode == 0  # positive control: a canonical-seed key file is still revealed


def test_s_every_verb_with_a_seed_flag_is_classified_so_a_new_one_forces_a_decision():
    import argparse
    import score_review as sr
    sub = next(a for a in sr.build_parser()._actions if isinstance(a, argparse._SubParsersAction))
    with_seed = {n for n, sp in sub.choices.items() if any("--seed" in a.option_strings for a in sp._actions)}
    secret, public = {"packet2", "import-beam"}, {"draw"}  # draw's seed is the public drand randomness
    assert with_seed == secret | public, with_seed
