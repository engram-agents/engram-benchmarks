"""Contract tests for score-review. Written before the implementation; numbering follows the spec's cells.

Refusal tests assert exit code 1 AND the word "refused" on stderr, so a missing or crashing script
(exit 2, a traceback) can never satisfy them vacuously. Every refusal test is paired with a positive
control in the same file.
"""
import ast
import hashlib
import inspect
import json
import re

import pytest

from helpers import Store, assert_refused, build_flow, read_jsonl, run



class _Lazy:
    """Import score_review on first use, so a missing module reds each test, not the whole collection."""

    def __getattr__(self, name):
        import score_review
        return getattr(score_review, name)


sr = _Lazy()

INDEPENDENCE = ("all reviewers belong to the team that builds the agent under test. These principles reduce our bias; "
                "they do not make the adjusted score independent.")


# ---------------------------------------------------------------- cell 1 and 2: record

def _base_p1(s, item="i02"):
    return s.vdict(item, s.honest(item), facts=[s.fact(s.oid(item))])


def test_record_valid_is_accepted_control(tmp_path):
    s = Store(tmp_path)
    cp = s.record("i02", 1, "lead", _base_p1(s))
    assert cp.returncode == 0, cp.stderr


def _cases(s):
    item = "i02"
    o, a1, a2 = s.oid(item), s.a1(item), s.a2(item)
    good = s.honest(item)
    letters = {"A": "correct", "B": "correct", "C": "correct"}

    def with_j(j):
        d = _base_p1(s)
        d["judgement"] = j
        d["facts"] = []
        return d

    def with_fact(**kw):
        d = _base_p1(s)
        d["facts"] = [s.fact(o, **kw)]
        return d

    miss_a2 = {k: v for k, v in good.items() if k != a2}
    miss_o = {k: v for k, v in good.items() if k != o}
    bad_val = dict(good)
    bad_val[a1] = "mostly"
    extra_key = dict(good)
    extra_key["zzzz9999"] = "correct"
    bad_fact_key = _base_p1(s)
    bad_fact_key["facts"] = [s.fact("deadbeef")]
    return [
        ("unknown-phase", 4, "lead", _base_p1(s), ()),
        ("phase0", 0, "lead", _base_p1(s), ()),
        ("phase2-by-labels", 2, "expert", with_j(good), ()),
        ("phase1-by-letters", 1, "lead", with_j(letters), ()),
        ("phase3-by-letters", 3, "owner", with_j(letters), ()),
        ("missing-agent-answer", 1, "lead", with_j(miss_a2), ()),
        ("missing-official", 1, "lead", with_j(miss_o), ()),
        ("value-outside", 1, "lead", with_j(bad_val), ()),
        ("extra-key", 1, "lead", with_j(extra_key), ()),
        ("ambiguous-other-p1", 1, "lead", with_j({"ambiguous": "split"}), ()),
        ("ambiguous-other-p2", 2, "expert", with_j({"ambiguous": "maybe"}), ()),
        ("ambiguous-split-in-p1", 1, "lead", with_j({"ambiguous": "reviewers split"}), ()),
        ("ambiguous-plus-keys", 1, "lead", with_j(dict(good, ambiguous="source")), ()),
        ("quote-not-verbatim", 1, "lead", with_fact(quote="north  shelf"), ()),
        ("quote-wrong-message", 1, "lead", with_fact(quote="Tuesday", msg_id=1), ()),
        ("quote-unknown-message", 1, "lead", with_fact(msg_id=99), ()),
        ("bears-on-not-in-judgement", 1, "lead", bad_fact_key, ()),
        ("guesses-outside-phase2", 1, "lead", dict(_base_p1(s), guesses={"official": "A", "arms": {}}), ()),
    ]


@pytest.mark.parametrize("idx", range(18))
def test_record_refuses_and_leaves_file_byte_identical(tmp_path, idx):
    s = Store(tmp_path)
    s.p1("i03")  # a pre-existing valid verdict, so "byte-identical" is a real comparison
    before = s.verdicts.read_bytes()
    name, phase, reviewer, vd, extra = _cases(s)[idx]
    cp = s.record("i02", phase, reviewer, vd, extra=extra)
    assert_refused(cp)
    assert s.verdicts.read_bytes() == before, name


def test_record_refuses_on_absent_file_creates_nothing(tmp_path):
    s = Store(tmp_path)
    assert not s.verdicts.exists()
    d = _base_p1(s)
    d["judgement"] = {"A": "correct", "B": "correct", "C": "correct"}
    assert_refused(s.record("i02", 1, "lead", d))
    assert not s.verdicts.exists()


def test_record_duplicate_needs_supersedes_and_reason(tmp_path):
    s = Store(tmp_path)
    sha1 = s.p1("i02")
    before = s.verdicts.read_bytes()
    vd = s.vdict("i02", s.honest("i02"))
    assert_refused(s.record("i02", 1, "lead", vd))
    assert_refused(s.record("i02", 1, "lead", vd, extra=["--supersedes", sha1]))
    assert_refused(s.record("i02", 1, "lead", vd, extra=["--supersedes", sha1, "--reason", "  "]))
    assert_refused(s.record("i02", 1, "lead", vd, extra=["--supersedes", "0" * 64, "--reason", "typo"]))
    assert s.verdicts.read_bytes() == before
    # the same call done right is accepted (positive control), and the chain is recorded
    cp = s.record("i02", 1, "lead", vd, extra=["--supersedes", sha1, "--reason", "fixed a typo"])
    assert cp.returncode == 0, cp.stderr
    rows = read_jsonl(s.verdicts)
    assert len(rows) == 2 and rows[1]["supersedes"] == sha1 and rows[1]["reason"] == "fixed a typo"
    # a different reviewer for the same (item, phase) is a different key and needs no supersedes
    cp = s.record("i02", 1, "other", vd)
    assert cp.returncode == 0, cp.stderr


def test_record_accepts_and_sha_recomputes(tmp_path):
    s = Store(tmp_path)
    out = s.must_record("i02", 1, "lead", _base_p1(s))
    rows = read_jsonl(s.verdicts)
    assert len(rows) == 1
    r = rows[0]
    body = {k: v for k, v in r.items() if k != "record_sha256"}
    canon = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    assert r["record_sha256"] == hashlib.sha256(canon).hexdigest() == out
    assert r["schema_version"] == 1 and r["phase"] == 1 and r["reviewer"] == "lead"
    assert r["keyed_by"] == "label" and r["supersedes"] is None and r["reason"] is None
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", r["recorded_at"])
    assert sr.canonical_sha(body) == r["record_sha256"]


def test_record_phase2_is_keyed_by_letter(tmp_path):
    s = Store(tmp_path)
    s.packet2("i02")
    s.p2("i02", s.honest("i02"))
    assert read_jsonl(s.verdicts)[0]["keyed_by"] == "letter"


# ---------------------------------------------------------------- cell 3: outcome table

def test_levels_on_a_three_point_scale():
    sc = {"max": 1.0, "min": 0.0}
    assert sr.level_of_scores([1.0, 1.0], sc) == "full"
    assert sr.level_of_scores([0.0, 0.0], sc) == "zero"
    assert sr.level_of_scores([1.0, 0.5], sc) == "partial"
    assert sr.level_of_scores([0.5, 0.5], sc) == "partial"  # all-0.5 is partial, not full and not zero
    assert sr.level_of_scores([1.0, 0.0], sc) == "partial"
    assert sr.level_of_scores([5.0, 5.0], {"max": 5.0, "min": 0.0}) == "full"
    assert sr.level_of_scores([4.0, 5.0], {"max": 5.0, "min": 0.0}) == "partial"


LV = {"x1": "full", "x2": "partial", "x3": "zero"}
OFF = "off0"


def _j(off="correct", **agents):
    base = {OFF: off, "x1": "correct", "x2": "partly", "x3": "wrong"}
    base.update(agents)
    return base


def test_outcome_key_stands():
    assert sr.outcome_for(_j(), OFF, LV) == ("key_stands", [])


@pytest.mark.parametrize("v", ["partly", "wrong"])
def test_outcome_key_wrong(v):
    assert sr.outcome_for(_j(off=v), OFF, LV) == ("key_wrong", [])


def test_outcome_ambiguous_source():
    assert sr.outcome_for({"ambiguous": "source"}, OFF, LV) == ("ambiguous_source", [])
    assert sr.outcome_for({"ambiguous": "reviewers split"}, OFF, LV)[0] == "ambiguous_split"


def test_outcome_grading_error_lists_exactly_the_differing_ids():
    assert sr.outcome_for(_j(x1="wrong"), OFF, LV) == ("grading_error", ["x1"])
    out, flagged = sr.outcome_for(_j(x1="partly", x3="correct"), OFF, LV)
    assert out == "grading_error" and sorted(flagged) == ["x1", "x3"]


def test_outcome_first_match_precedence():
    # ambiguous beats key_wrong (a dict carrying both is invalid input, but first-match must still hold)
    assert sr.outcome_for({"ambiguous": "source", OFF: "wrong"}, OFF, LV)[0] == "ambiguous_source"
    # key_wrong beats grading_error: official wrong AND an agent mis-graded is key_wrong
    assert sr.outcome_for(_j(off="wrong", x1="wrong"), OFF, LV) == ("key_wrong", [])


# ---------------------------------------------------------------- cell 4: routing

LEVELS = {
    "q_full": {"a": "full", "b": "full"},
    "q_partial": {"a": "full", "b": "partial"},
    "q_zero": {"a": "zero", "b": "full"},
}


def _route(levels, p1=None, p2=None, drawn=()):
    return sr.route(levels, p1 or {}, p2 or {}, set(drawn))


def test_routing_each_selection_alone_puts_item_in_phase2():
    lv = {"q_a": {"a": "partial", "b": "full"}, "q_b": {"a": "full"}, "q_c": {"a": "full"}, "q_none": {"a": "full"}}
    r = _route(lv, p1={"q_a": "key_stands", "q_b": "key_wrong", "q_c": "key_stands", "q_none": "key_stands"},
               drawn=["q_c"])
    assert [r[q]["in_phase2"] for q in ("q_a", "q_b", "q_c", "q_none")] == [True, True, True, False]
    assert (r["q_a"]["set_a"], r["q_a"]["set_b"], r["q_a"]["set_c"]) == (True, False, False)
    assert (r["q_b"]["set_a"], r["q_b"]["set_b"], r["q_b"]["set_c"]) == (False, True, False)
    assert (r["q_c"]["set_a"], r["q_c"]["set_b"], r["q_c"]["set_c"]) == (False, False, True)


def test_routing_unquestioned_controls_leave_phase3_and_nothing_else_does():
    lv = {
        "ctl": {"a": "full"},          # full, both stand            -> control, out of phase 3
        "ctl_p2_wrong": {"a": "full"},  # full, p2 says grading_error -> stays
        "partial_ok": {"a": "partial"},  # not full, both stand        -> stays (set a)
        "p1_err": {"a": "full"},        # full, p1 grading_error      -> phases 2 and 3
        "waiting": {"a": "full"},       # drawn, no p2 yet            -> not yet a control
    }
    p1 = {"ctl": "key_stands", "ctl_p2_wrong": "key_stands", "partial_ok": "key_stands",
          "p1_err": "grading_error", "waiting": "key_stands"}
    p2 = {"ctl": "key_stands", "ctl_p2_wrong": "grading_error", "partial_ok": "key_stands", "p1_err": "key_stands"}
    r = _route(lv, p1, p2, drawn=["ctl", "ctl_p2_wrong", "waiting"])
    assert all(r[q]["in_phase2"] for q in lv)
    assert [q for q in lv if r[q]["in_phase3"]] == ["ctl_p2_wrong", "partial_ok", "p1_err", "waiting"]
    assert r["ctl"]["unquestioned_control"] is True
    assert r["p1_err"]["in_phase2"] and r["p1_err"]["in_phase3"]


def test_routing_item_without_phase1_outcome_is_not_in_set_b():
    r = _route({"q": {"a": "full"}})
    assert r["q"]["set_b"] is False and r["q"]["in_phase2"] is False


# ---------------------------------------------------------------- cell 5: agreement

def test_agreement():
    j = {"p": "correct", "x": "partly"}
    assert sr.agree(dict(j), dict(j)) is True
    assert sr.agree(j, {"p": "correct", "x": "wrong"}) is False
    assert sr.agree({"ambiguous": "source"}, {"ambiguous": "source"}) is True
    assert sr.agree({"ambiguous": "source"}, j) is False
    # two grading_error outcomes flagging different answers do not agree
    j1 = {"p": "correct", "x": "wrong", "y": "correct"}
    j2 = {"p": "correct", "x": "correct", "y": "wrong"}
    lv = {"x": "full", "y": "full"}
    assert sr.outcome_for(j1, "p", lv) == ("grading_error", ["x"])
    assert sr.outcome_for(j2, "p", lv) == ("grading_error", ["y"])
    assert sr.agree(j1, j2) is False


# ---------------------------------------------------------------- cell 6: draw

def _draw(s, run_name="r1", n=2, seed="s1", draws=None):
    return run("draw", "--items", s.items, "--grades", s.grades, "--run", run_name, "--n", n, "--seed", seed,
               "--draws", draws or s.draws, "--verdicts", s.verdicts)


def _plan_a():
    return {"i02": {"a1": [0.37, 0.37]}, "i03": {"a1": [0.0, 0.0]}}


def test_draw_is_seeded_and_only_from_outside_set_a(tmp_path):
    s = Store(tmp_path, plan=_plan_a())
    eligible = {"i01", "i04", "i05", "i06"}
    seen = set()
    for k in range(15):
        d1, d2 = tmp_path / ("d1-%d.jsonl" % k), tmp_path / ("d2-%d.jsonl" % k)
        assert _draw(s, seed="seed%d" % k, draws=d1).returncode == 0
        assert _draw(s, seed="seed%d" % k, draws=d2).returncode == 0
        r1, r2 = read_jsonl(d1)[0], read_jsonl(d2)[0]
        assert r1["drawn_item_ids"] == r2["drawn_item_ids"]  # same seed, same draw
        assert set(r1["drawn_item_ids"]) <= eligible and len(r1["drawn_item_ids"]) == 2
        assert set(r1["eligible_item_ids"]) == eligible
        assert (r1["run"], r1["n"], r1["seed"]) == ("r1", 2, "seed%d" % k)
        assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", r1["drawn_at"])
        seen.add(tuple(r1["drawn_item_ids"]))
    assert len(seen) > 1  # different seeds can give different draws


def test_draw_refuses_n_larger_than_eligible(tmp_path):
    s = Store(tmp_path, plan=_plan_a())
    assert_refused(_draw(s, n=5))
    assert not s.draws.exists()
    assert _draw(s, n=4).returncode == 0  # positive control: exactly the eligible count is fine


def test_draw_refuses_once_a_phase1_verdict_exists(tmp_path):
    s = Store(tmp_path, plan=_plan_a())
    assert _draw(s, draws=tmp_path / "ok.jsonl").returncode == 0  # control: no verdicts yet
    s.p1("i01")
    assert_refused(_draw(s))
    assert not s.draws.exists()


def test_draw_refuses_a_second_draw_for_the_same_run(tmp_path):
    s = Store(tmp_path, plan=_plan_a())
    assert _draw(s).returncode == 0
    before = s.draws.read_bytes()
    assert_refused(_draw(s, seed="other"))
    assert s.draws.read_bytes() == before


# ---------------------------------------------------------------- cell 7 and 11: phase-2 packet

def _packet_text(s, item="i02", seed="seedx", chat=False):
    args = ["packet2", "--items", s.items, "--item", item, "--seed", seed, "--keys-dir", s.keys,
            "--out-dir", s.root / "packets" / "phase2"]
    if chat:
        args += ["--chat", s.chat]
    cp = run(*args)
    assert cp.returncode == 0, cp.stderr
    return cp, (s.root / "packets" / "phase2" / ("%s.md" % item)).read_text(encoding="utf-8")


def test_packet2_shows_only_what_phase2_may_see(tmp_path):
    s = Store(tmp_path, plan=_plan_a())
    cp, text = _packet_text(s)
    meta = s.meta["i02"]
    for forbidden in ("RUBRIC-TOKEN", "CATEGORY-TOKEN", "META-TOKEN", "ARM-TOKEN", "0.37", "(official)", "official"):
        assert forbidden not in text, forbidden
    for aid in meta.values():
        assert aid not in text and aid not in cp.stdout
    for tok in ("alpha", "beta", "gamma"):
        assert text.count("text-i02-%s zorp" % tok) == 1
    assert "Question text i02?" in text
    assert text.count("(no messages cited)") == 1
    assert "Answer A" in text and "Answer B" in text and "Answer C" in text
    # printed key hash equals the file's hash
    key_path = s.keys / "i02.json"
    sha = hashlib.sha256(key_path.read_bytes()).hexdigest()
    assert sha in cp.stdout
    key = json.loads(key_path.read_text())
    assert key["item_id"] == "i02" and key["seed"] == "seedx" and key["schema_version"] == 1
    assert sorted(key["letters"].values()) == sorted(meta.values())
    assert sorted(key["letters"]) == ["A", "B", "C"]


def test_packet2_with_chat_prints_cited_message_text(tmp_path):
    s = Store(tmp_path)
    _, text = _packet_text(s, chat=True)
    assert "The synthetic plant sits on the north shelf." in text
    assert "Watering happens every Tuesday." in text
    _, bare = _packet_text(Store(tmp_path / "b"), chat=False)
    assert "north shelf" not in bare


def test_packet2_has_no_option_for_the_other_files(tmp_path):
    s = Store(tmp_path)
    for opt in ("--grades", "--verdicts", "--draws"):
        cp = run("packet2", "--items", s.items, "--item", "i02", "--seed", "s", "--keys-dir", s.keys,
                 "--out-dir", tmp_path / "o", opt, str(s.grades))
        assert cp.returncode == 2 and "unrecognized" in cp.stderr


def test_packet2_does_not_overwrite_an_existing_key(tmp_path):
    s = Store(tmp_path)
    s.packet2("i02")
    before = (s.keys / "i02.json").read_bytes()
    cp = run("packet2", "--items", s.items, "--item", "i02", "--seed", "other", "--keys-dir", s.keys,
             "--out-dir", tmp_path / "o2")
    assert_refused(cp)
    assert (s.keys / "i02.json").read_bytes() == before


def test_cell11_packet_builder_blind_by_construction(tmp_path):
    # (a) only items.jsonl exists on disk: grades, verdicts, draws and keys/ are ABSENT
    s = Store(tmp_path / "full")
    only = tmp_path / "only"
    only.mkdir()
    (only / "items.jsonl").write_bytes(s.items.read_bytes())
    cp = run("packet2", "--items", only / "items.jsonl", "--item", "i02", "--seed", "s", "--keys-dir", only / "keys",
             "--out-dir", only / "packets")
    assert cp.returncode == 0, cp.stderr
    assert (only / "packets" / "i02.md").exists()
    assert not (only / "grades.jsonl").exists() and not (only / "verdicts.jsonl").exists()
    # (b) present, with planted tokens: none may reach the packet or stdout
    plant = tmp_path / "planted"
    plant.mkdir()
    (plant / "items.jsonl").write_bytes(s.items.read_bytes())
    (plant / "grades.jsonl").write_text('{"x": "TOKEN-GRADES"}\n')
    (plant / "verdicts.jsonl").write_text('{"x": "TOKEN-VERDICTS"}\n')
    (plant / "draws.jsonl").write_text('{"x": "TOKEN-DRAWS"}\n')
    (plant / "keys").mkdir()
    (plant / "keys" / "other.json").write_text('{"x": "TOKEN-KEYS"}\n')
    cp = run("packet2", "--items", plant / "items.jsonl", "--item", "i02", "--seed", "s", "--keys-dir", plant / "keys",
             "--out-dir", plant / "packets")
    assert cp.returncode == 0, cp.stderr
    out = (plant / "packets" / "i02.md").read_text() + cp.stdout + cp.stderr
    for t in ("TOKEN-GRADES", "TOKEN-VERDICTS", "TOKEN-DRAWS", "TOKEN-KEYS"):
        assert t not in out
    # (c) structural: the builder module cannot even name those inputs
    import blind_packet
    src = pathlib_text(blind_packet.__file__)
    tree = ast.parse(src)
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        if isinstance(n, ast.ImportFrom):
            mods.add((n.module or "").split(".")[0])
    assert mods <= {"json", "hashlib", "random", "re", "pathlib", "os", "sys", "chatfile"}, mods
    for word in ("grades", "verdicts", "draws", "score_review"):
        assert word not in src.lower(), word
    for fn in (blind_packet.build_packet, blind_packet.write_packet):
        for p in inspect.signature(fn).parameters:
            assert not re.search("grade|verdict|draw|outcome", p), p


def pathlib_text(path):
    import pathlib
    return pathlib.Path(path).read_text(encoding="utf-8")


# ---------------------------------------------------------------- cell 13: opaque, shuffled ids

def _beam_fixture(n=24, seed="fixture-seed"):
    from importers import beam
    questions = []
    for k in range(1, n + 1):
        questions.append({"question_no": k, "question": "Synthetic question %d?" % k, "answer": "Synthetic reply alpha %d" % k,
                          "rubric": ["rubric one %d" % k, "rubric two %d" % k], "cited_ids": [k],
                          "category": "cat%d" % (k % 3), "metadata": {"difficulty": "d%d" % k}})
    agent_rows = []
    for arm in ("armA", "armB"):
        for k in range(1, n + 1):
            agent_rows.append({"question_no": k, "text": "Synthetic reply %s %d" % ({"armA": "beta", "armB": "gamma"}[arm], k), "cited_ids": [k],
                               "rubric_scores": [1.0, 0.0], "arm": arm})
    items, grades, _skipped = beam.build_records(conv="c1", questions=questions, agent_rows=agent_rows, seed=seed,
                                       dataset="synthetic", data_sha256_prefix="0" * 12)
    return items, grades


def test_cell13_ids_and_positions_do_not_predict_official_or_arm():
    items, grades = _beam_fixture()
    assert len(items) >= 20
    gmap = {g["item_id"]: g for g in grades}
    off_ids, off_pos, arm_ids, arm_pos = [], [], [], []
    for it in items:
        g = gmap[it["item_id"]]
        ids = [a["answer_id"] for a in it["answers"]]
        assert len(set(ids)) == len(ids) == 3
        for i in ids:
            assert re.fullmatch(r"[0-9a-f]{8}", i)
        off_ids.append(g["official_id"])
        off_pos.append(ids.index(g["official_id"]))
        armA = [i for i, a in g["arms"].items() if a == "armA"][0]
        arm_ids.append(armA)
        arm_pos.append(ids.index(armA))
        assert ids == sorted(ids)  # list order is by id, so position carries nothing else
    assert len(set(off_ids)) == len(off_ids)  # the official id is never the same string twice
    assert len(set(off_pos)) > 1 and len(set(arm_pos)) > 1 and len(set(arm_ids)) == len(arm_ids)
    # items.jsonl carries no hint of the official answer or of any arm
    blob = json.dumps(items)
    for tok in ("armA", "armB", "official", "rubric", "cat0", "difficulty"):
        assert tok not in blob
    for it in items:
        assert set(it) == {"schema_version", "item_id", "question", "answers"}
        for a in it["answers"]:
            assert set(a) == {"answer_id", "text", "cited_ids"}


def test_cell13_ids_are_reproducible_and_depend_on_seed():
    i1, _ = _beam_fixture(seed="s")
    i2, _ = _beam_fixture(seed="s")
    i3, _ = _beam_fixture(seed="t")
    assert i1 == i2 and i1 != i3


# ---------------------------------------------------------------- cell 14: letter order per item

def test_cell14_letters_vary_per_item_and_are_reproducible(tmp_path):
    ids = ["j%02d" % k for k in range(24)]
    s = Store(tmp_path, item_ids=ids)
    import blind_packet
    gmap = {g["item_id"]: g for g in read_jsonl(s.grades)}
    letters_of_official = []
    for it in ids:
        a = tmp_path / "k1"
        b = tmp_path / "k2"
        blind_packet.write_packet(str(s.items), it, "one-seed", str(a), str(tmp_path / "p1"))
        blind_packet.write_packet(str(s.items), it, "one-seed", str(b), str(tmp_path / "p2"))
        k1 = json.loads((a / ("%s.json" % it)).read_text())["letters"]
        k2 = json.loads((b / ("%s.json" % it)).read_text())["letters"]
        assert k1 == k2  # same seed and item -> same letters
        letters_of_official.append([L for L, aid in k1.items() if aid == gmap[it]["official_id"]][0])
    assert len(set(letters_of_official)) > 1  # not constant over items under one seed
    # the derivation depends on the item id: two items with identical answers still differ across the set
    perms = set()
    for it in ids:
        k = json.loads((tmp_path / "k1" / ("%s.json" % it)).read_text())["letters"]
        perms.add(tuple(sorted(s.meta[it].values()).index(k[L]) for L in "ABC"))
    assert len(perms) > 1


# ---------------------------------------------------------------- cells 8, 9, 12, 15: map, report, export

def test_map_outcomes_routing_and_status(tmp_path):
    s = build_flow(tmp_path)
    o = s.outcomes()
    assert set(o) == set(s.item_ids)
    r = o["i01"]
    assert set(r["phases"]) == {"1"} and r["status"] == "not_reviewed" and r["routing"]["in_phase2"] is False
    r = o["i02"]
    assert r["routing"]["set_a"] and r["routing"]["in_phase3"] and not r["routing"]["unquestioned_control"]
    assert r["phases"]["1"]["outcome"] == r["phases"]["2"]["outcome"] == "key_stands"
    assert r["agreement"]["p1_p2"] is True and r["agreement"]["all"] is True and r["status"] == "settled"
    assert set(r["phases"]["2"]["judgement"]) == set(s.meta["i02"].values())  # re-keyed to answer ids
    r = o["i03"]
    assert r["status"] == "pending" and r["routing"]["phase3_required"] is True
    r = o["i04"]
    assert r["routing"]["set_c"] and r["routing"]["unquestioned_control"] and not r["routing"]["in_phase3"]
    assert r["status"] == "control_settled"
    r = o["i05"]
    assert r["phases"]["1"]["outcome"] == "key_wrong" and r["routing"]["set_b"]
    assert r["status"] == "settled" and r["adjusted"]["method"] == "judge-rerun"
    r = o["i06"]
    assert r["phases"]["1"]["outcome"] == "grading_error" and r["phases"]["1"]["flagged"] == [s.a2("i06")]
    assert r["phases"]["2"]["outcome"] == "key_stands"
    assert r["agreement"]["p1_p2"] is False and r["status"] == "pending"
    assert r["routing"]["in_phase2"] and r["routing"]["in_phase3"]
    assert r["official_levels"] == {s.a1("i06"): "full", s.a2("i06"): "full"}


def _no_letter_pair(text, s):
    for item in s.item_ids:
        k = s.key(item)["letters"] if (s.keys / ("%s.json" % item)).exists() else {}
        for letter, aid in k.items():
            assert '"%s"' % letter not in text, (item, letter)
            assert "%s=%s" % (letter, aid) not in text and "%s: %s" % (letter, aid) not in text


def test_cell8_map_and_report_leak_neither_arms_nor_letters(tmp_path):
    s = build_flow(tmp_path)
    cp, out = s.map()
    assert cp.returncode == 0, cp.stderr
    text = out.read_text()
    assert "ARM-TOKEN" not in text and "armA" not in text
    _no_letter_pair(text, s)
    rep = tmp_path / "report.md"
    cp = run("report", "--items", s.items, "--grades", s.grades, "--verdicts", s.verdicts, "--outcomes", out,
             "--out", rep)
    assert cp.returncode == 0, cp.stderr
    rtext = rep.read_text()
    assert "ARM-TOKEN" not in rtext and "ARM-TOKEN" not in cp.stdout
    _no_letter_pair(rtext, s)
    # positive control: --unblind does render the arms, so the absence above is meaningful
    rep2 = tmp_path / "report-unblind.md"
    cp = run("report", "--items", s.items, "--grades", s.grades, "--verdicts", s.verdicts, "--outcomes", out,
             "--unblind", "--out", rep2)
    assert cp.returncode == 0, cp.stderr
    assert "ARM-TOKEN-ONE" in rep2.read_text()


def test_report_content_and_pending_and_methods(tmp_path):
    s = build_flow(tmp_path)
    cp, out = s.map()
    rep = tmp_path / "report.md"
    cp = run("report", "--items", s.items, "--grades", s.grades, "--verdicts", s.verdicts, "--outcomes", out,
             "--out", rep)
    assert cp.returncode == 0, cp.stderr
    text = rep.read_text()
    assert INDEPENDENCE in text
    assert "text-i05-alpha zorp" in text and "Question text i03?" in text
    assert "pending" in text and "judge-rerun" in text
    for who in ("lead", "expert", "owner"):
        assert who in text
    # the unblind report names the grading method for a grading error once settled
    s.p3("i06", s.honest("i06", a2="wrong"))
    # (p1 flagged a2 as grading error; p3 agrees with p1; p2 does not, so still not settled)
    cp, out = s.map()
    o = {r["item_id"]: r for r in read_jsonl(out)}
    assert o["i06"]["status"] == "disagreement"


def test_report_refuses_stale_outcomes(tmp_path):
    s = build_flow(tmp_path)
    cp, out = s.map()
    rows = read_jsonl(out)
    rows[1]["phases"]["1"]["record_sha256"] = "0" * 64
    out.write_text("".join(json.dumps(r) + "\n" for r in rows))
    cp = run("report", "--items", s.items, "--grades", s.grades, "--verdicts", s.verdicts, "--outcomes", out,
             "--out", tmp_path / "r.md")
    assert_refused(cp)


def test_cell9_merged_fact_list_keeps_every_fact(tmp_path):
    recs = [
        {"phase": 1, "reviewer": "lead", "facts": [{"msg_id": 1, "quote": "a", "bears_on": "x"}] * 2},
        {"phase": 2, "reviewer": "expert", "facts": [{"msg_id": 1, "quote": "a", "bears_on": "x"}] * 3},
        {"phase": 3, "reviewer": "owner", "facts": [{"msg_id": 2, "quote": "b", "bears_on": "y"}]},
    ]
    merged = sr.merge_facts(recs)
    assert len(merged) == 6  # identical facts from two reviewers are NOT deduplicated
    assert sorted((m["phase"], m["reviewer"]) for m in merged) == [(1, "lead")] * 2 + [(2, "expert")] * 3 + [(3, "owner")]
    s = build_flow(tmp_path)
    o = s.outcomes()
    facts = o["i02"]["facts"]
    assert len(facts) == 2 + 3 + 1
    assert sorted(f["reviewer"] for f in facts) == ["expert"] * 3 + ["lead"] * 2 + ["owner"]
    ids = set(s.meta["i02"].values())
    assert all(f["bears_on"] in ids for f in facts)  # phase-2 facts re-keyed from letters


def test_cell12_export_phase3(tmp_path):
    s = build_flow(tmp_path)
    out = tmp_path / "x.json"

    def export(item, path=out):
        return run("export-phase3", "--items", s.items, "--grades", s.grades, "--verdicts", s.verdicts,
                   "--keys-dir", s.keys, "--item", item, "--out", path)

    cp = export("i01")  # phase 1 only
    assert_refused(cp)
    assert not out.exists()
    # phase 2 only: a fresh store with a phase-2 verdict and no phase-1 verdict
    t = Store(tmp_path / "t")
    t.p2("i02", t.honest("i02"))
    cp = run("export-phase3", "--items", t.items, "--grades", t.grades, "--verdicts", t.verdicts,
             "--keys-dir", t.keys, "--item", "i02", "--out", tmp_path / "t.json")
    assert_refused(cp)
    cp = export("i02")
    assert cp.returncode == 0, cp.stderr
    x = json.loads(out.read_text())
    rows = read_jsonl(s.verdicts)
    sha = {r["phase"]: r["record_sha256"] for r in rows if r["item_id"] == "i02"}
    assert x["phase1"]["record_sha256"] == sha[1] and x["phase2"]["record_sha256"] == sha[2]
    ids = set(s.meta["i02"].values())
    assert set(x["phase2"]["judgement"]) == ids and set(x["phase1"]["judgement"]) == ids
    text = out.read_text()
    for L in "ABC":
        assert '"%s"' % L not in text
    assert "ARM-TOKEN" not in text and "guesses" not in text and "letters" not in text
    assert x["official_id"] == s.oid("i02") and "facts" in x and len(x["facts"]) == 5


def test_cell15_no_rekey_without_a_recorded_phase2_verdict(tmp_path):
    s = Store(tmp_path)
    s.p1("i02")
    # a key file exists for i02 but no phase-2 verdict is recorded; the key must not be read or used
    s.keys.mkdir()
    (s.keys / "i02.json").write_text("{this is not json: TOKEN-UNREAD")
    s.p1("i01")
    cp, out = s.map()
    assert cp.returncode == 0, cp.stderr
    r = {x["item_id"]: x for x in read_jsonl(out)}["i02"]
    assert "2" not in r["phases"]
    assert "TOKEN-UNREAD" not in out.read_text()
    assert "refused" in cp.stderr.lower() and "i02" in cp.stderr
    # export refuses for the same item
    cp = run("export-phase3", "--items", s.items, "--grades", s.grades, "--verdicts", s.verdicts,
             "--keys-dir", s.keys, "--item", "i02", "--out", tmp_path / "x.json")
    assert_refused(cp)
    assert not (tmp_path / "x.json").exists()


def test_cell15_a_tampered_phase2_verdict_is_not_rekeyed(tmp_path):
    s = Store(tmp_path)
    s.p1("i02")
    s.p2("i02", s.honest("i02"))
    rows = read_jsonl(s.verdicts)
    rows[1]["judgement"] = {k: "wrong" for k in rows[1]["judgement"]}  # sha no longer recomputes
    s.verdicts.write_text("".join(json.dumps(r) + "\n" for r in rows))
    cp, out = s.map()
    assert_refused(cp)


# ---------------------------------------------------------------- quote-check and importers

def test_quote_check(tmp_path):
    s = Store(tmp_path)
    s.must_record("i02", 1, "lead", s.vdict("i02", s.honest("i02"), facts=[s.fact(s.oid("i02"), quote="no such words")]),
                  chat=False)
    cp = run("quote-check", "--verdicts", s.verdicts, "--chat", s.chat)
    assert cp.returncode == 1 and "no such words" in (cp.stdout + cp.stderr)
    t = Store(tmp_path / "ok")
    t.must_record("i02", 1, "lead", t.vdict("i02", t.honest("i02"), facts=[t.fact(t.oid("i02"))]), chat=False)
    cp = run("quote-check", "--verdicts", t.verdicts, "--chat", t.chat)
    assert cp.returncode == 0, cp.stdout + cp.stderr


def test_import_turns(tmp_path):
    turns = tmp_path / "turns.jsonl"
    rows = [{"turn": 1, "kind": "setup", "result": "ignored"},
            {"turn": 5, "kind": "question", "result": "first answer"},
            {"turn": 6, "kind": "chat", "result": "ignored too"},
            {"turn": 7, "kind": "question", "result": "second answer"}]
    turns.write_text("".join(json.dumps(r) + "\n" for r in rows))
    g = tmp_path / "g.jsonl"
    g.write_text(json.dumps({"question_no": 1, "rubric_scores": [1.0, 0.0]}) + "\n" +
                 json.dumps({"question_no": 3, "rubric_scores": [0.5]}) + "\n")
    out = tmp_path / "a.jsonl"
    cp = run("import-turns", "--turns", turns, "--first-question-turn", 5, "--arm-label", "armX", "--grades", g, "--out", out)
    assert cp.returncode == 0, cp.stderr
    got = read_jsonl(out)
    assert [(r["question_no"], r["text"], r["arm"]) for r in got] == [(1, "first answer", "armX"), (3, "second answer", "armX")]
    assert got[0]["rubric_scores"] == [1.0, 0.0] and got[0]["cited_ids"] == []
    assert "answer_id" not in got[0]


def test_import_beam_parquet(tmp_path):
    pa = pytest.importorskip("pyarrow", reason="pyarrow absent: the parquet importer test is skipped")
    import pyarrow.parquet as pq
    pq_path = tmp_path / "beam.parquet"
    other = {"catx": [{"question": "other?", "ideal_answer": "other", "rubric": ["r"]}]}
    probing = {
        "cat_one": [
            {"question": "Q one?", "ideal_answer": "Reply alpha one", "rubric": ["R1a", "R1b"], "source_chat_ids": [3, 4],
             "difficulty": "hard"},
            {"question": "Q two?", "answer": "Reply alpha two", "rubric": ["R2a"]},
        ],
        "cat_two": [{"question": "Q three?", "ideal_answer": "Reply alpha three", "rubric": ["R3a"],
                     "source_chat_ids": {"x": [7], "y": [8, 9]}}],
    }
    table = pa.table({"conversation_id": ["c9", "c1"], "probing_questions": [json.dumps(other), json.dumps(probing)]})
    pq.write_table(table, pq_path)
    ans = tmp_path / "a.jsonl"
    rows = []
    TOK = {"armA": "beta", "armB": "gamma"}
    for arm in ("armA", "armB"):
        rows += [{"question_no": 1, "text": "Reply %s one" % TOK[arm], "cited_ids": [3], "rubric_scores": [1.0, 0.0], "arm": arm},
                 {"question_no": 2, "text": "Reply %s two" % TOK[arm], "cited_ids": [], "rubric_scores": [1.0], "arm": arm},
                 {"question_no": 3, "text": "Reply %s three" % TOK[arm], "cited_ids": [7], "rubric_scores": [0.0], "arm": arm}]
    ans.write_text("".join(json.dumps(r) + "\n" for r in rows))
    items_out, grades_out = tmp_path / "items.jsonl", tmp_path / "grades.jsonl"
    cp = run("import-beam", "--parquet", pq_path, "--conv", "c1", "--answers", ans, "--seed", "sd",
             "--items-out", items_out, "--grades-out", grades_out)
    assert cp.returncode == 0, cp.stderr
    items, grades = read_jsonl(items_out), read_jsonl(grades_out)
    assert [g["question_no"] for g in grades] == [1, 2, 3]  # dict order, then list order
    assert [g["category"] for g in grades] == ["cat_one", "cat_one", "cat_two"]
    g1, i1 = grades[0], items[0]
    texts = {a["answer_id"]: a for a in i1["answers"]}
    assert texts[g1["official_id"]]["text"] == "Reply alpha one" and texts[g1["official_id"]]["cited_ids"] == [3, 4]
    assert g1["rubric_lines"] == ["R1a", "R1b"] and g1["scale"] == {"max": 1.0, "min": 0.0}
    assert g1["metadata"].get("difficulty") == "hard"
    assert {texts[i]["text"] for i in g1["arms"]} == {"Reply beta one", "Reply gamma one"}
    assert sorted(set(g1["arms"].values())) == ["armA", "armB"]
    assert texts[[i for i, a in g1["arms"].items() if a == "armA"][0]]["cited_ids"] == [3]
    assert [a["cited_ids"] for a in items[2]["answers"] if a["answer_id"] == grades[2]["official_id"]] == [[7, 8, 9]]
    blob = items_out.read_text()
    for tok in ("R1a", "cat_one", "hard", "armA", "official"):
        assert tok not in blob  # items.jsonl holds only what phase 2 may see
    assert g1["source_ref"]["conv"] == "c1" and g1["source_ref"]["data_sha256_prefix"] == \
        hashlib.sha256(pq_path.read_bytes()).hexdigest()[:12]
