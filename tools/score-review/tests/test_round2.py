"""Round 2 contract tests: the real BEAM shapes (synthetic text, real structure), the criterion data model
(amendments 2 and 3: cells 16-19), and a flow fixture with a line scored exactly half the scale max (R2-5).
Written before the implementation. All text is synthetic.
"""
import hashlib
import json

import pytest

from helpers import Store, assert_refused, build_flow, hid, read_jsonl, run, write_json


def _beam():
    from importers import beam
    return beam


def _one(q, category="cat"):
    return _beam().questions_from_probing({category: [q]})[0]


# ---------------------------------------------------------------- R2-1 / R2-4: one cell per real shape

def test_shape_ideal_response_without_source_chat_ids():
    q = _one({"question": "Q?", "ideal_response": "Synthetic abstention reply", "rubric": ["r1", "r2"]}, "abstention")
    assert q["answer"] == "Synthetic abstention reply" and q["cited_ids"] == []
    assert q["reference_kind"] == "answer" and q["category"] == "abstention"
    assert "ideal_response" not in q["metadata"]


def test_shape_ideal_summary():
    q = _one({"question": "Q?", "ideal_summary": "Synthetic summary text", "rubric": ["r1"], "source_chat_ids": [1, 2]})
    assert q["answer"] == "Synthetic summary text" and q["reference_kind"] == "answer" and q["cited_ids"] == [1, 2]
    assert "ideal_summary" not in q["metadata"]


def test_shape_criterion_with_real_list_fields():
    q = _one({"question": "Q?", "expected_compliance": "Synthetic criterion sentence", "rubric": ["r1"],
              "compliance_indicators": ["ind one", "ind two"], "non_compliance_signs": ["sign one"],
              "conversation_sessions": 3}, "instruction_following")
    assert q["reference_kind"] == "criterion" and q["answer"] == "Synthetic criterion sentence"
    assert q["metadata"]["compliance_indicators"] == ["ind one", "ind two"]
    assert q["metadata"]["non_compliance_signs"] == ["sign one"]
    assert q["metadata"]["conversation_sessions"] == 3  # stored as-is
    assert "expected_compliance" not in q["metadata"]
    assert q["cited_ids"] == []


def test_shape_dict_valued_source_chat_ids_flatten_in_key_order():
    q = _one({"question": "Q?", "ideal_answer": "x", "rubric": ["r"],
              "source_chat_ids": {"second_statement": [50, 51], "first_statement": [4]}})
    assert q["cited_ids"] == [50, 51, 4]  # key order of the dict as given, not sorted


def test_shape_empty_and_missing_id_containers_are_empty_lists():
    base = {"question": "Q?", "ideal_answer": "x", "rubric": ["r"]}
    assert _one(dict(base, source_chat_ids=[]))["cited_ids"] == []
    assert _one(dict(base, source_chat_ids={}))["cited_ids"] == []
    assert _one(dict(base))["cited_ids"] == []
    assert _one(dict(base, source_chat_ids=None))["cited_ids"] == []


def test_shape_rubric_as_dict_of_lists_flattens():
    q = _one({"question": "Q?", "answer": "x", "rubric": {"a": ["r one"], "b": ["r two", "r three"]}})
    assert q["rubric"] == ["r one", "r two", "r three"]


def test_reference_precedence_and_criterion_only_when_nothing_else():
    q = _one({"question": "Q?", "ideal_answer": "first", "answer": "second", "ideal_response": "third",
              "expected_compliance": "crit", "rubric": ["r"]})
    assert q["answer"] == "first" and q["reference_kind"] == "answer"
    assert _one({"question": "Q?", "answer": "second", "ideal_summary": "fourth", "rubric": ["r"]})["answer"] == "second"
    assert _one({"question": "Q?", "ideal_response": "third", "ideal_summary": "fourth", "rubric": ["r"]})["answer"] == "third"
    q = _one({"question": "Q?", "ideal_summary": "fourth", "expected_compliance": "crit", "rubric": ["r"]})
    assert q["answer"] == "fourth" and q["reference_kind"] == "answer"


def test_refuses_an_item_with_no_reference():
    with pytest.raises(_beam().ImportError_) as e:
        _one({"question": "Q?", "rubric": ["r"], "source_chat_ids": [1]})
    assert "reference" in str(e.value) and "question 1" in str(e.value)


def test_refuses_an_item_with_no_rubric_or_question():
    with pytest.raises(_beam().ImportError_):
        _one({"question": "Q?", "ideal_answer": "x"})
    with pytest.raises(_beam().ImportError_):
        _one({"ideal_answer": "x", "rubric": ["r"]})


# ---------------------------------------------------------------- R2-2 (amendment 3): list-valued fields

@pytest.mark.parametrize("field,bad", [
    ("rubric", "just a sentence"),
    ("rubric", "['looks like a list but is a string']"),
    ("rubric", 5),
    ("rubric", [1, 2]),
    ("source_chat_ids", "[100]"),
    ("source_chat_ids", 5),
    ("source_chat_ids", {"a": "x"}),
    ("source_chat_ids", ["a"]),
    ("source_chat_ids", [True]),
    ("compliance_indicators", "just text"),
    ("non_compliance_signs", {"a": "x"}),
])
def test_other_list_field_shapes_are_refused_naming_the_field(field, bad):
    q = {"question": "Q?", "ideal_answer": "x", "rubric": ["r"]}
    q[field] = bad
    with pytest.raises(_beam().ImportError_) as e:
        _one(q)
    assert field in str(e.value)


# ---------------------------------------------------------------- the criterion data model, importer side

def _records(questions_by_cat, arms=("armA", "armB")):
    beam = _beam()
    questions = beam.questions_from_probing(questions_by_cat)
    rows = []
    for q in questions:
        for arm in arms:
            rows.append({"question_no": q["question_no"], "text": "Synthetic agent reply %s %d" % (arm, q["question_no"]),
                         "cited_ids": [], "rubric_scores": [1.0] * len(q["rubric"]), "arm": arm})
    return beam.build_records("c1", questions, rows, "sd", "synthetic", "0" * 12)


MIXED = {
    "abstention": [{"question": "Q1?", "ideal_response": "Synthetic abstention", "rubric": ["a"]}],
    "instruction_following": [{"question": "Q2?", "expected_compliance": "CRITERION-SENTENCE here", "rubric": ["a", "b"],
                               "source_chat_ids": [12], "compliance_indicators": ["ind"]}],
}


def test_criterion_item_holds_only_agent_answers_and_the_reference_lives_in_grades():
    items, grades, _ = _records(MIXED)
    ans_item, crit_item = items
    ans_g, crit_g = grades
    assert len(ans_item["answers"]) == 3 and len(crit_item["answers"]) == 2
    assert crit_g["reference_kind"] == "criterion" and crit_g["official_id"] is None
    assert crit_g["criterion_text"] == "CRITERION-SENTENCE here"
    assert set(crit_g["scores"]) == {a["answer_id"] for a in crit_item["answers"]}
    assert "CRITERION-SENTENCE" not in json.dumps(items)
    assert ans_g["reference_kind"] == "answer" and "criterion_text" not in ans_g
    assert ans_g["official_id"] in {a["answer_id"] for a in ans_item["answers"]}
    assert crit_g["metadata"]["compliance_indicators"] == ["ind"] and crit_g["metadata"]["source_chat_ids"] == [12]


def test_items_carry_no_reference_kind_field_of_either_kind():
    items, _, _ = _records(MIXED)
    for it in items:
        assert set(it) == {"schema_version", "item_id", "question", "answers"}
        for a in it["answers"]:
            assert set(a) == {"answer_id", "text", "cited_ids"}


def test_a_criterion_item_with_one_arm_has_one_answer():
    items, grades, _ = _records(MIXED, arms=("armA",))
    assert len(items[1]["answers"]) == 1 and len(items[0]["answers"]) == 2


def test_import_beam_parquet_with_every_real_shape(tmp_path):
    pa = pytest.importorskip("pyarrow", reason="pyarrow absent: the parquet shape test is skipped")
    import pyarrow.parquet as pq
    probing = {
        "abstention": [{"question": "Qa?", "ideal_response": "Synthetic abstention", "rubric": ["ra1", "ra2"]}],
        "contradiction_resolution": [{"question": "Qc?", "ideal_answer": "Synthetic resolved", "rubric": ["rc"],
                                      "source_chat_ids": {"first_statement": [4], "second_statement": [50]}}],
        "summarization": [{"question": "Qs?", "ideal_summary": "Synthetic summary", "rubric": ["rs"],
                           "source_chat_ids": []}],
        "instruction_following": [{"question": "Qi?", "expected_compliance": "Synthetic criterion", "rubric": ["ri"],
                                   "compliance_indicators": ["one", "two"], "non_compliance_signs": ["sign"],
                                   "conversation_sessions": 2}],
    }
    p = tmp_path / "b.parquet"
    pq.write_table(pa.table({"conversation_id": ["c1"], "probing_questions": [json.dumps(probing)]}), p)
    ans = tmp_path / "a.jsonl"
    ans.write_text("".join(json.dumps({"question_no": n, "text": "Synthetic reply %s %d" % (arm, n), "cited_ids": [],
                                       "rubric_scores": [1.0] * (2 if n == 1 else 1), "arm": arm}) + "\n"
                           for n in (1, 2, 3, 4) for arm in ("armA", "armB")))
    cp = run("import-beam", "--parquet", p, "--conv", "c1", "--answers", ans, "--seed", "sd",
             "--items-out", tmp_path / "i.jsonl", "--grades-out", tmp_path / "g.jsonl")
    assert cp.returncode == 0, cp.stderr
    items, grades = read_jsonl(tmp_path / "i.jsonl"), read_jsonl(tmp_path / "g.jsonl")
    assert [g["reference_kind"] for g in grades] == ["answer", "answer", "answer", "criterion"]
    assert [len(i["answers"]) for i in items] == [3, 3, 3, 2]
    texts = {a["answer_id"]: a for a in items[1]["answers"]}
    assert texts[grades[1]["official_id"]]["cited_ids"] == [4, 50]
    assert grades[3]["metadata"]["compliance_indicators"] == ["one", "two"] and grades[3]["official_id"] is None


# ---------------------------------------------------------------- loaders enforce the grades shape

def _crit_files(tmp_path, **grade_over):
    items = [{"schema_version": 1, "item_id": "k1", "question": "Q?",
              "answers": [{"answer_id": "aa11aa11", "text": "t1", "cited_ids": []}]}]
    g = {"schema_version": 1, "item_id": "k1", "study": "s", "conv": "c", "question_no": 1, "reference_kind": "criterion",
         "official_id": None, "criterion_text": "do the thing", "rubric_lines": ["r"], "scores": {"aa11aa11": [1.0]},
         "scale": {"max": 1.0, "min": 0.0}, "category": None, "metadata": {}, "arms": {"aa11aa11": "x"},
         "source_ref": {}}
    g.update(grade_over)
    ip, gp = tmp_path / "items.jsonl", tmp_path / "grades.jsonl"
    ip.write_text(json.dumps(items[0]) + "\n")
    gp.write_text(json.dumps(g) + "\n")
    return ip, gp


def _packet1(ip, gp):
    return run("packet1", "--items", ip, "--grades", gp, "--item", "k1")


def test_loader_accepts_a_single_answer_criterion_item_control(tmp_path):
    cp = _packet1(*_crit_files(tmp_path))
    assert cp.returncode == 0, cp.stderr
    assert "do the thing" in cp.stdout  # packet1 shows the criterion (phase 1 is not blind)


@pytest.mark.parametrize("over", [
    {"official_id": "aa11aa11"},
    {"criterion_text": None},
    {"criterion_text": ""},
    {"reference_kind": "bogus"},
    {"scores": {}},
])
def test_loader_refuses_a_malformed_criterion_grade(tmp_path, over):
    assert_refused(_packet1(*_crit_files(tmp_path, **over)))


def test_loader_refuses_an_answer_item_with_a_criterion_text_or_no_official(tmp_path):
    ip, gp = _crit_files(tmp_path, reference_kind="answer", official_id=None, scores={"aa11aa11": [1.0]})
    assert_refused(_packet1(ip, gp))
    ip, gp = _crit_files(tmp_path, reference_kind="answer", official_id="aa11aa11", scores={})
    assert_refused(_packet1(ip, gp))  # an answer item with a single answer is no review item


# ---------------------------------------------------------------- R2-5: a line at exactly half the max, in a flow

def test_flow_a_line_at_exactly_half_the_max_is_partial_and_routes_to_phase2(tmp_path):
    s = build_flow(tmp_path)
    o = s.outcomes()["i07"]
    assert o["official_levels"][s.a1("i07")] == "partial"
    assert o["routing"]["set_a"] is True and o["routing"]["in_phase2"] is True
    assert o["routing"]["in_phase3"] is True and o["routing"]["unquestioned_control"] is False
    assert o["phases"]["1"]["outcome"] == "key_stands" and o["phases"]["2"]["outcome"] == "key_stands"


# ================================================================ criterion items: a store and cells 16-19

CRIT_TOKENS = ("CRIT-TEXT-TOKEN", "CRIT-IND-TOKEN", "CRIT-SIGN-TOKEN", "CRIT-RUBRIC-TOKEN", "CRIT-CAT-TOKEN",
               "CRIT-META-TOKEN", "CRIT-ARM-TOKEN")
CHAT = "## msg 1 | user | 2026-01-01\nAlways answer in one short sentence.\n\n## msg 2 | assistant | 2026-01-02\nUnderstood.\n"


class CStore:
    """k1 criterion, both answers full, drawn; k2 criterion, one partial; k3 criterion, one agent answer;
    k4 criterion, only a 2a will be recorded; r1 an answer-type item."""

    def __init__(self, root):
        from pathlib import Path
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.items, self.grades = self.root / "items.jsonl", self.root / "grades.jsonl"
        self.verdicts, self.draws, self.keys = self.root / "verdicts.jsonl", self.root / "draws.jsonl", self.root / "keys"
        self.chat = self.root / "chat.md"
        self.chat.write_text(CHAT)
        plan = {"k1": {"x": [1.0, 1.0], "y": [1.0, 1.0]}, "k2": {"x": [1.0, 1.0], "y": [1.0, 0.5]},
                "k3": {"x": [1.0, 1.0]}, "k4": {"x": [1.0, 1.0], "y": [1.0, 0.5]}}
        self.ids = {}
        irows, grows = [], []
        for item, sc in plan.items():
            ids = {k: hid("cx", item, k) for k in sc}
            self.ids[item] = ids
            answers = [{"answer_id": ids[k], "text": "ctext-%s-%s zorp" % (item, k), "cited_ids": [1] if k == "x" else []}
                       for k in sc]
            answers.sort(key=lambda a: a["answer_id"])
            irows.append({"schema_version": 1, "item_id": item, "question": "Cquestion %s?" % item, "answers": answers})
            grows.append({
                "schema_version": 1, "item_id": item, "study": "fx", "conv": "c1", "question_no": len(grows) + 1,
                "reference_kind": "criterion", "official_id": None, "criterion_text": "CRIT-TEXT-TOKEN comply please",
                "rubric_lines": ["CRIT-RUBRIC-TOKEN one", "CRIT-RUBRIC-TOKEN two"],
                "scores": {ids[k]: v for k, v in sc.items()}, "scale": {"max": 1.0, "min": 0.0},
                "category": "CRIT-CAT-TOKEN",
                "metadata": {"compliance_indicators": ["CRIT-IND-TOKEN a"], "non_compliance_signs": ["CRIT-SIGN-TOKEN b"],
                             "other": "CRIT-META-TOKEN"},
                "arms": {ids[k]: "CRIT-ARM-TOKEN-%s" % k for k in sc}, "source_ref": {}})
        rids = {r: hid("cx", "r1", r) for r in ("official", "x")}
        self.ids["r1"] = rids
        ra = [{"answer_id": rids[r], "text": "rtext-%s zorp" % r, "cited_ids": []} for r in rids]
        ra.sort(key=lambda a: a["answer_id"])
        irows.append({"schema_version": 1, "item_id": "r1", "question": "Rquestion?", "answers": ra})
        grows.append({"schema_version": 1, "item_id": "r1", "study": "fx", "conv": "c1", "question_no": 5,
                      "reference_kind": "answer", "official_id": rids["official"], "rubric_lines": ["R one"],
                      "scores": {rids["x"]: [1.0]}, "scale": {"max": 1.0, "min": 0.0}, "category": None, "metadata": {},
                      "arms": {rids["x"]: "CRIT-ARM-TOKEN-r"}, "source_ref": {}})
        self.items.write_text("".join(json.dumps(r) + "\n" for r in irows))
        self.grades.write_text("".join(json.dumps(r) + "\n" for r in grows))
        self.draws.write_text(json.dumps({"schema_version": 1, "run": "r", "n": 1, "seed": "s", "drawn_item_ids": ["k1"],
                                          "eligible_item_ids": ["k1"], "drawn_at": "2026-01-01T00:00:00Z"}) + "\n")

    def level_j(self, item, **over):
        """Honest label-keyed judgement for a criterion item (levels from the plan), criterion correct."""
        g = {r["item_id"]: r for r in read_jsonl(self.grades)}[item]
        j = {"criterion": "correct"}
        for aid, sc in g["scores"].items():
            j[aid] = "correct" if all(x == 1.0 for x in sc) else ("wrong" if all(x == 0.0 for x in sc) else "partly")
        for k, v in over.items():
            j[self.ids[item][k] if k in self.ids[item] else k] = v
        return j

    def vd(self, item, judgement, step=None, facts=None, guesses=None, fuller=None):
        d = {"item_id": item, "judgement": judgement, "fuller_answer": fuller, "facts": facts or [],
             "guesses": guesses, "minutes_spent": 3, "notes": ""}
        if step is not None:
            d["step"] = step
        return d

    def record(self, item, phase, reviewer, vd, grades=True, extra=()):
        f = write_json(self.root / ("v-%s-%s-%s-%s.json" % (item, phase, vd.get("step"), reviewer)), vd)
        args = ["record", "--verdicts", self.verdicts, "--items", self.items, "--phase", phase, "--reviewer", reviewer,
                "--file", f, "--chat", self.chat]
        if grades:
            args += ["--grades", self.grades]
        return run(*args, *extra)

    def ok(self, *a, **kw):
        cp = self.record(*a, **kw)
        assert cp.returncode == 0, cp.stderr
        return cp.stdout.strip()

    def p1(self, item, judgement=None, reviewer="lead"):
        return self.ok(item, 1, reviewer, self.vd(item, judgement or self.level_j(item)))

    def packet2(self, item, seed="sx"):
        cp = run("packet2", "--items", self.items, "--item", item, "--seed", seed, "--keys-dir", self.keys,
                 "--out-dir", self.root / "packets")
        assert cp.returncode == 0, cp.stderr
        return cp

    def letter(self, item, aid):
        letters = json.loads((self.keys / ("%s.json" % item)).read_text())["letters"]
        return [L for L, v in letters.items() if v == aid][0]

    def has_p1(self, item):
        return any(r["item_id"] == item and r["phase"] == 1 for r in read_jsonl(self.verdicts))

    def r1_p1(self):
        """A phase-1 verdict for the answer-type item r1 (level_j is for criterion items)."""
        r = self.ids["r1"]
        return self.ok("r1", 1, "lead", self.vd("r1", {r["official"]: "correct", r["x"]: "correct"}))

    def p2a(self, item, judgement_by_key, reviewer="expert", guesses_arms=None, fuller="Answer in one sentence (msg 1)."):
        if not self.has_p1(item):  # the order rule (S2): phase 2 follows phase 1
            self.p1(item)
        if not (self.keys / ("%s.json" % item)).exists():
            self.packet2(item)
        j = {self.letter(item, self.ids[item][k]): v for k, v in judgement_by_key.items()}
        g = None
        if guesses_arms is not None:
            g = {"arms": {self.letter(item, self.ids[item][k]): v for k, v in guesses_arms.items()}}
        return self.ok(item, 2, reviewer, self.vd(item, j, step="2a", guesses=g, fuller=fuller))

    def p2b(self, item, value, reviewer="expert", **kw):
        return self.ok(item, 2, reviewer, self.vd(item, {"criterion": value}, step="2b", **kw))

    def export_criterion(self, item, reviewer="expert", out=None):
        out = out or (self.root / ("crit-%s.json" % item))
        return run("export-criterion", "--items", self.items, "--grades", self.grades, "--verdicts", self.verdicts,
                   "--item", item, "--reviewer", reviewer, "--out", out), out

    def map(self):
        out = self.root / "outcomes.jsonl"
        cp = run("map", "--items", self.items, "--grades", self.grades, "--verdicts", self.verdicts,
                 "--keys-dir", self.keys, "--draws", self.draws, "--out", out)
        return cp, out

    def outcomes(self):
        cp, out = self.map()
        assert cp.returncode == 0, cp.stderr
        return {r["item_id"]: r for r in read_jsonl(out)}


# ---------------------------------------------------------------- cell 16: the 2a packet holds no criterion

def test_cell16_2a_packet_contains_no_token_from_the_criterion(tmp_path):
    s = CStore(tmp_path)
    cp = s.packet2("k2")
    text = (tmp_path / "packets" / "k2.md").read_text()
    for tok in CRIT_TOKENS:
        assert tok not in text and tok not in cp.stdout, tok
    for k in ("x", "y"):
        assert text.count("ctext-k2-%s zorp" % k) == 1  # every agent answer exactly once
    assert "Answer A" in text and "Answer B" in text and "Answer C" not in text
    for aid in s.ids["k2"].values():
        assert aid not in text
    assert sorted(json.loads((s.keys / "k2.json").read_text())["letters"].values()) == sorted(s.ids["k2"].values())


def test_cell16_2a_packet_builds_with_grades_verdicts_draws_absent_and_for_a_single_answer(tmp_path):
    s = CStore(tmp_path)
    for p in (s.grades, s.draws):
        p.unlink()
    cp = s.packet2("k3")
    text = (tmp_path / "packets" / "k3.md").read_text()
    assert text.count("ctext-k3-x zorp") == 1 and "Answer A" in text and "Answer B" not in text


# ---------------------------------------------------------------- cell 17: export-criterion needs a 2a by the same reviewer

def test_cell17_export_criterion_refuses_without_a_recorded_2a(tmp_path):
    s = CStore(tmp_path)
    cp, out = s.export_criterion("k2")  # no verdicts file at all
    assert_refused(cp)
    assert not out.exists()
    s.p1("k2", s.level_j("k2"))
    cp, out = s.export_criterion("k2")  # a phase-1 record is not a 2a
    assert_refused(cp)
    assert not out.exists() and "CRIT-TEXT-TOKEN" not in cp.stdout + cp.stderr


def test_cell17_export_criterion_refuses_a_2a_by_another_reviewer(tmp_path):
    s = CStore(tmp_path)
    s.p2a("k2", {"x": "correct", "y": "partly"}, reviewer="expert")
    cp, out = s.export_criterion("k2", reviewer="someone-else")
    assert_refused(cp)
    assert not out.exists()


def test_cell17_export_criterion_refuses_a_2a_whose_hash_does_not_recompute(tmp_path):
    s = CStore(tmp_path)
    s.p2a("k2", {"x": "correct", "y": "partly"})
    rows = read_jsonl(s.verdicts)
    two_a = [r for r in rows if r.get("step") == "2a"][0]
    two_a["notes"] = "edited after the fact"
    s.verdicts.write_text("".join(json.dumps(r) + "\n" for r in rows))
    cp, out = s.export_criterion("k2")
    assert_refused(cp)
    assert not out.exists()


def test_cell17_export_criterion_refuses_for_a_non_criterion_item(tmp_path):
    s = CStore(tmp_path)
    s.r1_p1()
    s.packet2("r1")
    letters = json.loads((s.keys / "r1.json").read_text())["letters"]
    s.ok("r1", 2, "expert", s.vd("r1", {L: "correct" for L in letters}))
    cp, out = s.export_criterion("r1")
    assert_refused(cp)
    assert not out.exists()


def test_cell17_export_criterion_gives_the_criterion_and_nothing_else_after_a_valid_2a(tmp_path):
    s = CStore(tmp_path)
    sha = s.p2a("k2", {"x": "correct", "y": "partly"})
    cp, out = s.export_criterion("k2")
    assert cp.returncode == 0, cp.stderr
    x = json.loads(out.read_text())
    assert x["criterion_text"] == "CRIT-TEXT-TOKEN comply please" and x["item_id"] == "k2"
    assert x["criterion_lists"] == {"compliance_indicators": ["CRIT-IND-TOKEN a"],
                                    "non_compliance_signs": ["CRIT-SIGN-TOKEN b"]}
    text = out.read_text()
    for tok in ("CRIT-RUBRIC-TOKEN", "CRIT-CAT-TOKEN", "CRIT-META-TOKEN", "CRIT-ARM-TOKEN", "1.0", "0.5"):
        assert tok not in text, tok
    assert x["after_2a_record_sha256"] == sha


# ---------------------------------------------------------------- cell 18: record refuses what the 2a/2b rules forbid

def _refused(s, call):
    before = _bytes(s)
    cp = call()
    assert_refused(cp)
    assert _bytes(s) == before
    return cp


def _bytes(s):
    return s.verdicts.read_bytes() if s.verdicts.exists() else None


def test_cell18_a_2b_with_any_key_other_than_criterion_is_refused(tmp_path):
    s = CStore(tmp_path)
    s.p2a("k2", {"x": "correct", "y": "partly"})  # (records the phase-1 verdict first)
    before = s.verdicts.read_bytes()
    x = s.ids["k2"]["x"]
    for j in ({"criterion": "correct", x: "correct"}, {"criterion": "correct", "A": "correct"},
              {x: "correct"}, {"criterion": "correct", "extra": "wrong"}):
        assert_refused(s.record("k2", 2, "expert", s.vd("k2", j, step="2b")))
        assert s.verdicts.read_bytes() == before
    assert_refused(s.record("k2", 2, "expert", s.vd("k2", {"criterion": "mostly"}, step="2b")))
    assert_refused(s.record("k2", 2, "expert", s.vd("k2", {"ambiguous": "source"}, step="2b")))
    assert_refused(s.record("k2", 2, "expert", s.vd("k2", {"criterion": "correct"}, step="2b",
                                                    guesses={"arms": {"A": "x"}})))
    assert s.verdicts.read_bytes() == before
    s.p2b("k2", "correct")  # positive control: the right shape is accepted


def test_cell18_a_2b_needs_a_2a_by_the_same_reviewer(tmp_path):
    s = CStore(tmp_path)
    s.p1("k2")  # the order rule is met, so the refusals below are about the missing 2a
    _refused(s, lambda: s.record("k2", 2, "expert", s.vd("k2", {"criterion": "correct"}, step="2b")))
    s.p2a("k2", {"x": "correct", "y": "partly"}, reviewer="expert")
    _refused(s, lambda: s.record("k2", 2, "other", s.vd("k2", {"criterion": "correct"}, step="2b")))


def test_cell18_step_rules(tmp_path):
    s = CStore(tmp_path)
    s.p1("k2")  # the order rule is met for both items, so each refusal below is about the step
    s.r1_p1()
    s.packet2("k2")
    s.packet2("r1")
    lj = {s.letter("k2", s.ids["k2"]["x"]): "correct", s.letter("k2", s.ids["k2"]["y"]): "partly"}
    for bad in (None, "2c", "1", "2"):  # a criterion item's phase-2 record must say 2a or 2b
        _refused(s, lambda: s.record("k2", 2, "expert", s.vd("k2", lj, step=bad)))
    before = _bytes(s)
    cp = run("record", "--verdicts", s.verdicts, "--items", s.items, "--phase", 2, "--reviewer", "expert",
             "--file", write_json(tmp_path / "nogr.json", s.vd("k2", lj, step="2a")))
    assert cp.returncode != 0 and _bytes(s) == before  # record without --grades cannot know the item's kind
    rl = {L: "correct" for L in json.loads((s.keys / "r1.json").read_text())["letters"]}
    _refused(s, lambda: s.record("r1", 2, "expert", s.vd("r1", rl, step="2a")))  # no steps on answer items
    _refused(s, lambda: s.record("r1", 1, "lead", dict(s.vd("r1", {}, step="2a"))))
    s.ok("r1", 2, "expert", s.vd("r1", rl))  # positive controls
    s.ok("k2", 2, "expert", s.vd("k2", lj, step="2a"))


def test_cell18_judgement_keys_per_phase_for_a_criterion_item(tmp_path):
    for ph in (1, 3):
        s = CStore(tmp_path / ("ph%d" % ph))
        good = s.level_j("k2")
        miss_crit = {k: v for k, v in good.items() if k != "criterion"}
        miss_agent = {k: v for k, v in good.items() if k != s.ids["k2"]["y"]}
        if ph == 3:  # the order rule is met (p1, 2a, 2b recorded), so the refusals are about the judgement keys
            s.p2a("k2", {"x": "correct", "y": "partly"})
            s.p2b("k2", "correct")
        _refused(s, lambda: s.record("k2", ph, "lead", s.vd("k2", miss_crit)))
        _refused(s, lambda: s.record("k2", ph, "lead", s.vd("k2", miss_agent)))
        _refused(s, lambda: s.record("k2", ph, "lead", s.vd("k2", good, step="2a")))
        s.ok("k2", ph, "lead", s.vd("k2", good))  # control: the right keys are accepted
    s = CStore(tmp_path / "answer-item")
    # an answer item still refuses a stray criterion key
    r = s.ids["r1"]
    bad = {r["official"]: "correct", r["x"]: "correct", "criterion": "correct"}
    _refused(s, lambda: s.record("r1", 1, "lead", s.vd("r1", bad)))


def test_cell18_2a_guesses_carry_arms_only(tmp_path):
    s = CStore(tmp_path)
    s.p1("k2")
    s.packet2("k2")
    A, B = s.letter("k2", s.ids["k2"]["x"]), s.letter("k2", s.ids["k2"]["y"])
    lj = {A: "correct", B: "partly"}
    _refused(s, lambda: s.record("k2", 2, "expert", s.vd("k2", lj, step="2a",
                                                               guesses={"official": A, "arms": {A: "x"}})))
    s.ok("k2", 2, "expert", s.vd("k2", lj, step="2a", guesses={"arms": {A: "x", B: "y"}}))
    assert read_jsonl(s.verdicts)[-1]["step"] == "2a"


def test_cell18_supersession_key_includes_the_step(tmp_path):
    s = CStore(tmp_path)
    sha_a = s.p2a("k2", {"x": "correct", "y": "partly"})
    s.p2b("k2", "correct")  # a 2b beside a 2a by the same reviewer is not a duplicate
    letters = json.loads((s.keys / "k2.json").read_text())["letters"]
    lj = {s.letter("k2", s.ids["k2"]["x"]): "correct", s.letter("k2", s.ids["k2"]["y"]): "wrong"}
    again = s.vd("k2", lj, step="2a")
    _refused(s, lambda: s.record("k2", 2, "expert", again))  # duplicate 2a
    _refused(s, lambda: s.record("k2", 2, "expert", again, extra=("--supersedes", sha_a)))  # no reason, a 2b exists
    s.ok("k2", 2, "expert", again, extra=("--supersedes", sha_a, "--reason", "reread message 1"))
    assert len(letters) == 2
    rows = read_jsonl(s.verdicts)
    assert rows[-1]["supersedes"] == sha_a and rows[-1]["reason"] == "reread message 1" and rows[-1]["step"] == "2a"


# ---------------------------------------------------------------- cell 19: map and export-phase3 on criterion items

def _flow(s):
    """k1 (drawn): stands. k2: criterion wrong. k3: one agent answer judged below its level. k4: 2a only."""
    for item in ("k1", "k2", "k3", "k4"):
        j = s.level_j(item)
        if item == "k2":
            j["criterion"] = "wrong"
        s.p1(item, j)
    s.p2a("k1", {"x": "correct", "y": "correct"}, guesses_arms={"x": "CRIT-ARM-TOKEN-x"})
    s.p2b("k1", "correct")
    s.p2a("k2", {"x": "correct", "y": "partly"})
    s.p2b("k2", "wrong")
    s.p2a("k3", {"x": "wrong"})
    s.p2b("k3", "correct")
    s.p2a("k4", {"x": "correct", "y": "partly"})


def test_cell19_map_uses_the_2b_criterion_judgement_in_place_of_the_official_answer(tmp_path):
    s = CStore(tmp_path)
    _flow(s)
    o = s.outcomes()
    k1 = o["k1"]
    assert k1["phases"]["2"]["judgement"]["criterion"] == "correct"
    assert set(k1["phases"]["2"]["judgement"]) == {"criterion"} | set(s.ids["k1"].values())  # re-keyed to ids
    assert k1["phases"]["2"]["outcome"] == "key_stands" and k1["phases"]["1"]["outcome"] == "key_stands"
    assert k1["official_id"] is None and k1["reference_kind"] == "criterion"
    assert k1["routing"]["unquestioned_control"] is True and k1["status"] == "control_settled"
    assert k1["agreement"]["p1_p2"] is True
    k2 = o["k2"]
    assert k2["phases"]["2"]["outcome"] == "key_wrong" and k2["phases"]["1"]["outcome"] == "key_wrong"
    assert k2["agreement"]["p1_p2"] is True and k2["routing"]["in_phase3"] is True and k2["status"] == "pending"
    k3 = o["k3"]
    assert k3["phases"]["2"]["outcome"] == "grading_error" and k3["phases"]["2"]["flagged"] == list(s.ids["k3"].values())
    assert k3["phases"]["1"]["outcome"] == "key_stands" and k3["agreement"]["p1_p2"] is False


def test_cell19_an_item_with_only_a_2a_is_phase2_pending_and_its_key_is_not_used(tmp_path):
    s = CStore(tmp_path)
    _flow(s)
    k4 = s.outcomes()["k4"]
    assert "2" not in k4["phases"] and k4["status"] == "phase2_pending"


def test_cell19_outcomes_hold_no_letter_pair_no_arm_label_and_no_official_guess(tmp_path):
    s = CStore(tmp_path)
    _flow(s)
    cp, out = s.map()
    text = out.read_text()
    assert "CRIT-ARM-TOKEN" not in text and "CRIT-TEXT-TOKEN" not in text and "CRIT-RUBRIC" not in text
    for item in ("k1", "k2", "k3"):
        for L, aid in json.loads((s.keys / ("%s.json" % item)).read_text())["letters"].items():
            assert '"%s"' % L not in text and "%s=%s" % (L, aid) not in text
    assert s.outcomes()["k1"]["phases"]["2"]["official_guess"] is None


def test_cell19_map_merges_the_facts_of_2a_and_2b(tmp_path):
    s = CStore(tmp_path)
    s.p1("k2", s.level_j("k2"))
    s.packet2("k2")
    A = s.letter("k2", s.ids["k2"]["x"])
    fact =lambda b: {"msg_id": 1, "quote": "one short sentence", "bears_on": b, "direction": "supports",
                      "against_own": False}
    s.ok("k2", 2, "expert", s.vd("k2", {A: "correct", s.letter("k2", s.ids["k2"]["y"]): "partly"}, step="2a",
                                 facts=[fact(A)]))
    s.ok("k2", 2, "expert", s.vd("k2", {"criterion": "correct"}, step="2b", facts=[fact("criterion")]))
    facts = s.outcomes()["k2"]["facts"]
    assert len(facts) == 2 and sorted(f["bears_on"] for f in facts) == sorted(["criterion", s.ids["k2"]["x"]])


def test_cell19_export_phase3_for_a_criterion_item(tmp_path):
    s = CStore(tmp_path)
    _flow(s)
    out = tmp_path / "x3.json"

    def export(item):
        return run("export-phase3", "--items", s.items, "--grades", s.grades, "--verdicts", s.verdicts,
                   "--keys-dir", s.keys, "--item", item, "--out", out)

    cp = export("k4")  # 2a without 2b
    assert_refused(cp)
    assert not out.exists()
    cp = export("k2")
    assert cp.returncode == 0, cp.stderr
    x = json.loads(out.read_text())
    rows = [r for r in read_jsonl(s.verdicts) if r["item_id"] == "k2"]
    sha = {(r["phase"], r.get("step")): r["record_sha256"] for r in rows}
    assert x["phase1"]["record_sha256"] == sha[(1, None)]
    assert x["phase2"]["record_sha256"] == sha[(2, "2a")] and x["phase2"]["record_sha256_2b"] == sha[(2, "2b")]
    assert set(x["phase2"]["judgement"]) == {"criterion"} | set(s.ids["k2"].values())
    assert x["phase2"]["judgement"]["criterion"] == "wrong" and x["official_id"] is None
    assert x["criterion_text"] == "CRIT-TEXT-TOKEN comply please"
    text = out.read_text()
    assert "CRIT-ARM-TOKEN" not in text and "guesses" not in text and "letters" not in text
    for L in "AB":
        assert '"%s"' % L not in text


def test_cell19_report_shows_the_criterion_text_and_hides_arms(tmp_path):
    s = CStore(tmp_path)
    _flow(s)
    cp, out = s.map()
    rep = tmp_path / "report.md"
    cp = run("report", "--items", s.items, "--grades", s.grades, "--verdicts", s.verdicts, "--outcomes", out, "--out", rep)
    assert cp.returncode == 0, cp.stderr
    text = rep.read_text()
    assert "CRIT-TEXT-TOKEN comply please" in text and "CRIT-ARM-TOKEN" not in text
    assert "CRIT-RUBRIC-TOKEN" not in text
    # the stale-outcomes guard also covers the 2b record cited by the outcomes
    rows = read_jsonl(out)
    for r in rows:
        if "2" in r["phases"]:
            r["phases"]["2"]["record_sha256_2b"] = "0" * 64
    out.write_text("".join(json.dumps(r) + "\n" for r in rows))
    cp = run("report", "--items", s.items, "--grades", s.grades, "--verdicts", s.verdicts, "--outcomes", out,
             "--out", tmp_path / "r2.md")
    assert_refused(cp)


def test_cell19_phase1_packet_for_a_criterion_item_shows_the_criterion(tmp_path):
    s = CStore(tmp_path)
    cp = run("packet1", "--items", s.items, "--grades", s.grades, "--item", "k2")
    assert cp.returncode == 0, cp.stderr
    assert "CRIT-TEXT-TOKEN comply please" in cp.stdout
    assert "(official)" not in cp.stdout
