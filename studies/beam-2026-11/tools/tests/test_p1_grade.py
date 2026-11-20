"""Contract tests for p1_grade.py, written before it (BEAM P1 grading, rule part d; rulings 32566/32574/32673-4).

Contract:
  - The pool holds one item per (session, question) with an answer, plus one SENSITIVITY item per missing turn that has a
    sensitivity answer. A missing primary (placeholder_missing, ruled_missing, missing) is never in the pool.
  - An undecided near variant (route near_variant) REFUSES the build: grading waits for a ruling.
  - Pool rows carry only opaque_id, question, gold, answer: no session, no k, no question id, no kind.
  - Opaque ids are unique; the order is a seeded shuffle: the same seed gives the same pool bytes, another seed another order.
  - The key (opaque_id -> session, qid, kind) is a separate file; both files' sha256 are returned before any judge call.
  - The gold file must hash to the frozen value, and every pooled id must have a gold line; else REFUSE.
  - The template must hash to the pinned value before any call; else REFUSE.
"""
import hashlib, json, os, sys
import pytest
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import p1_grade as g

GOLD_MD = "# x\n\n## Items (id | exchange | style | question || gold)\nF01 | ex1 | information_extraction | Q one? || G one.\nF02 | ex1 | information_extraction | Q two? || G two.\nA01 | ex2 | abstention | Q three? || G three.\n"

def ans(route, answer=None, sens=None):
    return {"answer": answer, "route": route, "tool_ending": False, "string_route": False, "sensitivity_answer": sens}

def files(tmp_path, a1, a2, gold=GOLD_MD):
    p = {}
    for name, a in (("K3", a1), ("k1", a2)):
        f = tmp_path / f"{name}.json"; f.write_text(json.dumps({"answers": a, "counts": {}, "disagreements": [], "near_variants": []}))
        p[name] = str(f)
    gf = tmp_path / "gold.md"; gf.write_text(gold)
    qf = tmp_path / "q.json"; qf.write_text(json.dumps([{"id": "F01", "question": "Q one?"}, {"id": "F02", "question": "Q two?"}, {"id": "A01", "question": "Q three?"}]))
    return p, str(gf), str(qf), hashlib.sha256(gold.encode()).hexdigest()

def build(tmp_path, a1, a2, seed=7, gold=GOLD_MD, expect=None):
    p, gf, qf, sha = files(tmp_path, a1, a2, gold)
    return g.build_pool({"K3": p["K3"], "k1": p["k1"]}, qf, gf, expect or sha, seed)

FULL = {"F01": ans("recorded", "a"), "F02": ans("last_text_block", "b"), "A01": ans("recorded", "c")}

def test_pool_size_and_missing_primaries_excluded(tmp_path):
    k1 = dict(FULL); k1["F02"] = ans("placeholder_missing", None, "earlier")
    pool, key = build(tmp_path, FULL, k1)
    assert len(pool) == 3 + 2 + 1  # K3 all three, k1 two answered, one sensitivity item
    kinds = sorted((v["session"], v["qid"], v["kind"]) for v in key.values())
    assert ("k1", "F02", "primary") not in kinds and ("k1", "F02", "sensitivity") in kinds

def test_ruled_missing_also_gives_sensitivity_and_no_primary(tmp_path):
    k1 = dict(FULL); k1["A01"] = ans("ruled_missing", None, "abstain text")
    pool, key = build(tmp_path, FULL, k1)
    kinds = {(v["session"], v["qid"], v["kind"]) for v in key.values()}
    assert ("k1", "A01", "primary") not in kinds and ("k1", "A01", "sensitivity") in kinds

def test_missing_without_sensitivity_answer_adds_nothing(tmp_path):
    k1 = dict(FULL); k1["F01"] = ans("missing", None, None)
    pool, key = build(tmp_path, FULL, k1)
    assert not any(v["session"] == "k1" and v["qid"] == "F01" for v in key.values())

def test_undecided_near_variant_refuses(tmp_path):
    k1 = dict(FULL); k1["F01"] = ans("near_variant", None, None)
    with pytest.raises(g.GradeRefused, match="near_variant"):
        build(tmp_path, FULL, k1)

def test_pool_rows_carry_no_session_or_ids(tmp_path):
    pool, key = build(tmp_path, FULL, FULL)
    for row in pool:
        assert set(row) == {"opaque_id", "question", "gold", "answer"}
    blob = json.dumps(pool)
    for leak in ("K3", "k1", "F01", "F02", "A01", "primary", "sensitivity"):
        assert leak not in blob

def test_opaque_ids_unique_and_seeded_order(tmp_path):
    p1, k1 = build(tmp_path, FULL, FULL, seed=7)
    p2, _ = build(tmp_path, FULL, FULL, seed=7)
    p3, _ = build(tmp_path, FULL, FULL, seed=8)
    assert len({r["opaque_id"] for r in p1}) == len(p1) == len(k1)
    assert json.dumps(p1) == json.dumps(p2)
    assert [r["answer"] for r in p1] != [r["answer"] for r in p3] or [r["opaque_id"] for r in p1] != [r["opaque_id"] for r in p3]

def test_gold_and_question_filled(tmp_path):
    pool, key = build(tmp_path, FULL, FULL)
    for row in pool:
        q = key[row["opaque_id"]]["qid"]
        assert row["gold"] == {"F01": "G one.", "F02": "G two.", "A01": "G three."}[q]
        assert row["question"] == {"F01": "Q one?", "F02": "Q two?", "A01": "Q three?"}[q]

def test_gold_hash_mismatch_refuses(tmp_path):
    with pytest.raises(g.GradeRefused, match="gold"):
        build(tmp_path, FULL, FULL, expect="0" * 64)

def test_missing_gold_line_refuses(tmp_path):
    gold = GOLD_MD.replace("F02 | ex1 | information_extraction | Q two? || G two.\n", "")
    with pytest.raises(g.GradeRefused, match="F02"):
        build(tmp_path, FULL, FULL, gold=gold, expect=hashlib.sha256(gold.encode()).hexdigest())

def test_write_sealed_returns_hashes_of_both_files(tmp_path):
    pool, key = build(tmp_path, FULL, FULL)
    hp, hk = g.write_sealed(pool, key, str(tmp_path / "pool.json"), str(tmp_path / "key.json"))
    assert hp == hashlib.sha256((tmp_path / "pool.json").read_bytes()).hexdigest()
    assert hk == hashlib.sha256((tmp_path / "key.json").read_bytes()).hexdigest()

def test_template_hash_checked_before_any_call(tmp_path):
    t = tmp_path / "t.txt"; t.write_text("not the template <question> <rubric_item> <llm_response>")
    with pytest.raises(g.GradeRefused, match="template"):
        g.load_template(str(t))

def test_fill_prompt_replaces_all_three_slots():
    out = g.fill_prompt("Q:<question> R:<rubric_item> A:<llm_response>", "qq", "gg", "aa")
    assert out == "Q:qq R:gg A:aa"
