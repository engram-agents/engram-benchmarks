"""Round 6 contract tests (PR 7 colleague read): amendment 9.

A9-1 the blinding builder refuses an item whose answer ids are not distinct (and the other malformed answer lists);
A9-2 load_item reads the whole file and refuses a duplicate item row or a row that is not an object with an item_id;
A9-3 every validating regex is anchored with fullmatch, so a trailing newline is refused; A9-4 the second discriminating
cell for the four rules a colleague found held by one cell each. Written before the implementation. Synthetic data only.
"""
import json
import pathlib

import pytest

from helpers import Store, assert_refused, run

import blind_packet
import score_review as sr


def _answers(*ids, cited=None):
    return [{"answer_id": i, "text": "text-%s zorp" % i, "cited_ids": cited or []} for i in ids]


def _write_items(root, rows):
    root = pathlib.Path(root)
    root.mkdir(parents=True, exist_ok=True)
    p = root / "items.jsonl"
    p.write_text("".join((r if isinstance(r, str) else json.dumps(r)) + "\n" for r in rows), encoding="utf-8")
    return p


def _item(item_id="d1", answers=None, **over):
    row = {"schema_version": 1, "item_id": item_id, "question": "Question %s?" % item_id,
           "answers": answers if answers is not None else _answers("x1", "y2", "z3")}
    row.update(over)
    return row


def _snapshot(root):
    """Every path under root with its size: a refusal must leave no packet, no key, no temp file."""
    root = pathlib.Path(root)
    return sorted((str(p.relative_to(root)), p.stat().st_size if p.is_file() else -1) for p in root.rglob("*"))


def _packet2(root, items, item="d1", seed="s"):
    root = pathlib.Path(root)
    return run("packet2", "--items", items, "--item", item, "--seed", seed, "--keys-dir", root / "keys",
               "--out-dir", root / "packets" / "phase2")


def _refused_with_nothing_written(root, items, item="d1", must_say=None):
    before = _snapshot(root)
    cp = _packet2(root, items, item)
    assert_refused(cp)
    if must_say:
        assert must_say in cp.stderr.lower(), cp.stderr
    assert _snapshot(root) == before


# ---------------------------------------------------------------- A9-1

def test_a9_1_the_reported_x1_x1_y2_item_is_refused_and_nothing_is_written(tmp_path):
    items = _write_items(tmp_path, [_item(answers=_answers("x1", "x1", "y2"))])
    _refused_with_nothing_written(tmp_path, items, must_say="distinct")
    assert not (tmp_path / "keys").exists() and not (tmp_path / "packets").exists()


def test_a9_1_distinct_ids_are_accepted_positive_control(tmp_path):
    items = _write_items(tmp_path, [_item()])
    cp = _packet2(tmp_path, items)
    assert cp.returncode == 0, cp.stderr
    key = json.loads((tmp_path / "keys" / "d1.json").read_text())
    assert sorted(key["letters"].values()) == ["x1", "y2", "z3"]


def test_a9_1_an_item_with_no_answers_is_refused(tmp_path):
    items = _write_items(tmp_path, [_item(answers=[])])
    _refused_with_nothing_written(tmp_path, items, must_say="answer")


def test_a9_1_an_item_with_no_answers_field_is_refused_not_a_traceback(tmp_path):
    row = _item()
    del row["answers"]
    items = _write_items(tmp_path, [row])
    _refused_with_nothing_written(tmp_path, items, must_say="answer")


def test_a9_1_an_answer_missing_its_id_is_refused(tmp_path):
    answers = _answers("x1", "y2") + [{"text": "no id here", "cited_ids": []}]
    items = _write_items(tmp_path, [_item(answers=answers)])
    _refused_with_nothing_written(tmp_path, items, must_say="answer_id")


def test_a9_1_an_answer_with_an_empty_or_non_string_id_is_refused(tmp_path):
    for k, bad in enumerate(["", None, 7]):
        root = tmp_path / ("c%d" % k)
        answers = _answers("x1", "y2") + [{"answer_id": bad, "text": "t", "cited_ids": []}]
        items = _write_items(root, [_item(answers=answers)])
        _refused_with_nothing_written(root, items, must_say="answer_id")


def test_a9_1_more_answers_than_letters_is_refused_with_nothing_written(tmp_path):
    ids = ["a%02d" % k for k in range(27)]
    items = _write_items(tmp_path, [_item(answers=_answers(*ids))])
    _refused_with_nothing_written(tmp_path, items, must_say="letter labels")


def test_a9_1_exactly_as_many_answers_as_letters_is_accepted(tmp_path):
    ids = ["a%02d" % k for k in range(26)]
    items = _write_items(tmp_path, [_item(answers=_answers(*ids))])
    assert _packet2(tmp_path, items).returncode == 0


def test_a9_1_build_packet_itself_refuses_so_no_caller_can_skip_the_check():
    with pytest.raises(ValueError):
        blind_packet.build_packet(_item(answers=_answers("x1", "x1", "y2")), "s")


# ---------------------------------------------------------------- A9-2

def test_a9_2_a_duplicate_item_row_with_different_answers_is_refused_and_nothing_is_written(tmp_path):
    items = _write_items(tmp_path, [_item(), _item(answers=_answers("p1", "q2"))])
    _refused_with_nothing_written(tmp_path, items, must_say="more than one row")


def test_a9_2_an_identical_duplicate_item_row_is_refused_too(tmp_path):
    items = _write_items(tmp_path, [_item(), _item()])
    _refused_with_nothing_written(tmp_path, items, must_say="more than one row")


def test_a9_2_a_single_row_per_item_is_accepted_positive_control(tmp_path):
    items = _write_items(tmp_path, [_item("d0"), _item("d1"), _item("d2")])
    assert _packet2(tmp_path, items).returncode == 0


def test_a9_2_a_row_that_is_not_an_object_or_has_no_item_id_is_refused_even_after_the_match(tmp_path):
    for k, bad in enumerate(['[1, 2]', '"text"', '7', 'null', json.dumps({"question": "no id"}),
                             json.dumps({"item_id": 5})]):
        root = tmp_path / ("c%d" % k)
        items = _write_items(root, [_item(), bad])  # the bad row sits AFTER the requested item: a first-match read misses it
        _refused_with_nothing_written(root, items, must_say="row")


def test_a9_2_a_row_that_is_not_json_is_refused_with_a_message(tmp_path):
    items = _write_items(tmp_path, [_item(), "{not json"])
    _refused_with_nothing_written(tmp_path, items)


# ---------------------------------------------------------------- A9-3

BAD_TOKENS = ["good\n", "good\nextra"]


@pytest.mark.parametrize("bad", BAD_TOKENS)
def test_a9_3_blind_packet_refuses_an_item_id_with_a_newline(tmp_path, bad):
    items = _write_items(tmp_path, [_item(bad)])  # the file really holds that id, so only the validator can refuse it
    with pytest.raises(ValueError):
        blind_packet.load_item(str(items), bad)
    ok = _write_items(tmp_path / "ok", [_item("good")])
    assert blind_packet.load_item(str(ok), "good")["item_id"] == "good"


@pytest.mark.parametrize("bad", BAD_TOKENS)
def test_a9_3_packet2_from_the_cli_refuses_an_item_id_with_a_newline(tmp_path, bad):
    items = _write_items(tmp_path, [_item(bad)])
    _refused_with_nothing_written(tmp_path, items, item=bad, must_say="plain token")
    ok = _write_items(tmp_path / "ok", [_item("good")])
    assert _packet2(tmp_path / "ok", ok, item="good").returncode == 0


@pytest.mark.parametrize("bad", BAD_TOKENS)
def test_a9_3_the_items_loader_refuses_an_item_id_with_a_newline(tmp_path, bad):
    items = _write_items(tmp_path, [_item(bad)])
    with pytest.raises(sr.UserError):
        sr.load_items(str(items))
    ok = _write_items(tmp_path / "ok", [_item("good")])
    assert "good" in sr.load_items(str(ok))


@pytest.mark.parametrize("bad", BAD_TOKENS)
def test_a9_3_the_items_loader_refuses_an_answer_id_with_a_newline(tmp_path, bad):
    items = _write_items(tmp_path, [_item("i1", answers=_answers("good", bad))])
    with pytest.raises(sr.UserError):
        sr.load_items(str(items))
    ok = _write_items(tmp_path / "ok", [_item("i1", answers=_answers("good", "fine"))])
    assert "i1" in sr.load_items(str(ok))


@pytest.mark.parametrize("bad", BAD_TOKENS)
def test_a9_3_record_refuses_a_reviewer_name_with_a_newline(tmp_path, bad):
    s = Store(tmp_path)
    item = "i02"
    cp = s.record(item, 1, bad, s.vdict(item, s.honest(item), facts=[s.fact(s.oid(item))]))
    assert_refused(cp)
    assert "reviewer" in cp.stderr.lower()
    assert not s.verdicts.exists() or s.verdicts.read_text() == ""
    s.must_record(item, 1, "good", s.vdict(item, s.honest(item), facts=[s.fact(s.oid(item))]))  # positive control


def test_a9_3_no_validating_regex_in_the_tool_is_matched_with_match():
    """The class, not the instances: a ^...$ pattern used through .match accepts a trailing newline."""
    import ast
    import re
    tool = pathlib.Path(sr.__file__).resolve().parent
    offenders = []
    for path in sorted(tool.glob("*.py")) + sorted((tool / "importers").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ("match", "search")):
                offenders.append("%s:%d" % (path.name, node.lineno))
    assert offenders == [], offenders
    assert re.fullmatch(r"x", "x")  # keeps the import honest


# ---------------------------------------------------------------- A9-4: a second cell for each single-cell rule

def test_a9_4_control_rule_a_phase2_outcome_other_than_key_stands_keeps_the_item_in_phase3():
    lv = {"ok": {"a": "full"}, "p2_key_wrong": {"a": "full"}, "p2_amb_source": {"a": "full"},
          "p2_amb_split": {"a": "full"}}
    p1 = {k: "key_stands" for k in lv}
    p2 = {"ok": "key_stands", "p2_key_wrong": "key_wrong", "p2_amb_source": "ambiguous_source",
          "p2_amb_split": "ambiguous_split"}
    r = sr.route(lv, p1, p2, set(lv))
    assert r["ok"]["unquestioned_control"] is True and r["ok"]["in_phase3"] is False
    for k in ("p2_key_wrong", "p2_amb_source", "p2_amb_split"):
        assert r[k]["unquestioned_control"] is False and r[k]["in_phase3"] is True, k


def test_a9_4_agreement_is_symmetric_and_needs_both_or_neither_ambiguous():
    j = {"p": "correct", "x": "partly"}
    amb = {"ambiguous": "source"}
    assert sr.agree(j, amb) is False and sr.agree(amb, j) is False  # either side alone is not agreement
    assert sr.agree(amb, {"ambiguous": "reviewers split"}) is True
    assert sr.agree(j, {"p": "correct"}) is False and sr.agree({"p": "correct"}, j) is False  # a missing answer differs
    assert sr.agree(j, {"x": "partly", "p": "correct"}) is True  # key order is not content


def test_a9_4_every_arrangement_of_three_answers_is_reachable_and_roughly_even():
    item = _item("shuf", answers=_answers("x1", "y2", "z3"))
    counts = {}
    for seed in range(300):
        order = tuple(a["answer_id"] for a in blind_packet.letter_order(item, "seed-%d" % seed))
        counts[order] = counts.get(order, 0) + 1
    assert len(counts) == 6, counts
    assert min(counts.values()) >= 20, counts  # 300 seeds over 6 arrangements: 50 expected each


def test_a9_4_the_letter_order_depends_on_the_item_id_for_one_seed_and_identical_answers():
    answers = _answers("x1", "y2", "z3", "w4")
    differing = 0
    for k in range(40):
        a = tuple(x["answer_id"] for x in blind_packet.letter_order(_item("ia%d" % k, answers=answers), "fixed"))
        b = tuple(x["answer_id"] for x in blind_packet.letter_order(_item("ib%d" % k, answers=answers), "fixed"))
        differing += a != b
    assert differing >= 20, differing  # 24 arrangements: two independent draws differ about 23 times in 24
    one = _item("same", answers=answers)
    assert blind_packet.letter_order(one, "fixed") == blind_packet.letter_order(dict(one), "fixed")
