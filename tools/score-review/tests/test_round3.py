"""Round 3 contract tests (PR 7 review round 1 and the principles v0.2 fold): amendments 4 and 5.

B1 cited-messages leak, B2 opaque item ids, S1 one effective reviewer per (item, phase, step), S2 phase order,
S3 packet then key (atomic), S4 one shared predicate, and amendment 4 (a 2a changed after the 2b forces phase 3).
Written before the implementation; all text is synthetic.
"""
import ast
import inspect
import json
import re
import textwrap

import pytest

from helpers import SEED, Store, assert_refused, forge_export, forge_verdict, read_jsonl, run
from test_round2 import CStore

NEUTRAL = "Cited messages: not shown for this item"
NONE_CITE = {"official": [], "a1": [], "a2": []}


def _packet(s, item="i02", chat=False, seed=SEED):
    out = s.root / "packets" / "phase2"
    args = ["packet2", "--items", s.items, "--item", item, "--seed", seed, "--keys-dir", s.keys, "--out-dir", out]
    if chat:
        args += ["--chat", s.chat]
    cp = run(*args)
    assert cp.returncode == 0, cp.stderr
    return (out / ("%s.md" % item)).read_text(encoding="utf-8")


def _bytes(s):
    return s.verdicts.read_bytes() if s.verdicts.exists() else None


# ---------------------------------------------------------------- B1: the cited-messages line must not tell the answers apart

@pytest.mark.parametrize("cited", [
    {"official": [1], "a1": [], "a2": []},      # only the official answer cites: the leak the review reproduced
    {"official": [], "a1": [1, 2], "a2": []},   # only an agent answer cites
    {"official": [1], "a1": [1, 2], "a2": []},  # all but one cite
    {"official": [], "a1": [], "a2": []},       # none cites (agent answers from import-turns; an abstention official)
])
def test_b1_unless_every_answer_cites_no_cited_id_is_shown_for_any_answer(tmp_path, cited):
    s = Store(tmp_path / "x", cited=cited)
    text = _packet(s, chat=True)
    assert text.count(NEUTRAL) == 1 and text.count("Cited messages:") == 1
    assert "(no messages cited)" not in text and "#### msg" not in text
    assert "north shelf" not in text and "Tuesday" not in text  # no cited message text either
    # the packet is exactly the packet of an item where nothing is cited: no per-answer difference survives
    base = _packet(Store(tmp_path / "base", cited=NONE_CITE), chat=True)
    assert text == base


def test_b1_when_every_answer_cites_all_are_listed_in_the_same_form(tmp_path):
    s = Store(tmp_path, cited={"official": [1], "a1": [1, 2], "a2": [2]})
    text = _packet(s, chat=True)
    assert NEUTRAL not in text and "(no messages cited)" not in text
    lines = sorted(l for l in text.splitlines() if l.startswith("Cited messages:"))
    assert lines == ["Cited messages: 1", "Cited messages: 1, 2", "Cited messages: 2"]
    assert "The synthetic plant sits on the north shelf." in text and "Watering happens every Tuesday." in text
    bare = _packet(Store(tmp_path / "b", cited={"official": [1], "a1": [1, 2], "a2": [2]}), chat=False)
    assert "north shelf" not in bare and bare.count("Cited messages:") == 3


def test_b1_the_real_import_shape_shows_no_cited_line_difference(tmp_path):
    """import-beam fills the official answer's cited ids; import-turns leaves the agent answer's empty."""
    from importers import beam
    turns = tmp_path / "turns.jsonl"
    turns.write_text(json.dumps({"turn": 5, "kind": "question", "result": "synthetic agent reply"}) + "\n")
    ans = tmp_path / "a.jsonl"
    cp = run("import-turns", "--turns", turns, "--first-question-turn", 5, "--arm-label", "armX", "--out", ans)
    assert cp.returncode == 0, cp.stderr
    rows = [dict(r, rubric_scores=[1.0]) for r in read_jsonl(ans)]
    qs = [{"question_no": 1, "question": "Synthetic question?", "answer": "synthetic official reply", "rubric": ["r"],
           "cited_ids": [4, 7], "category": "c", "metadata": {}}]
    items, grades, _ = beam.build_records("cv", qs, rows, "sd", "synthetic", "0" * 12)
    assert [a["cited_ids"] for a in items[0]["answers"] if a["answer_id"] == grades[0]["official_id"]] == [[4, 7]]
    p = tmp_path / "items.jsonl"
    p.write_text(json.dumps(items[0]) + "\n")
    cp = run("packet2", "--items", p, "--item", items[0]["item_id"], "--seed", SEED, "--keys-dir", tmp_path / "k",
             "--out-dir", tmp_path / "o")
    assert cp.returncode == 0, cp.stderr
    text = (tmp_path / "o" / ("%s.md" % items[0]["item_id"])).read_text()
    assert NEUTRAL in text and "4, 7" not in text and "Cited messages: 4" not in text
    assert "(no messages cited)" not in text


# ---------------------------------------------------------------- B2: the item id carries neither the conversation nor the question number

CONV = "CONVQZ-PLANT"
QBASE = 73500


def _planted(n=24, conv=CONV, seed="sd"):
    from importers import beam
    questions = [{"question_no": QBASE + k, "question": "Synthetic question about topic zz?",
                  "answer": "Synthetic reply alpha", "rubric": ["rubric one", "rubric two"], "cited_ids": [],
                  "category": "cat%d" % (k % 3), "metadata": {}} for k in range(n)]
    rows = [{"question_no": QBASE + k, "text": "Synthetic reply beta", "cited_ids": [], "rubric_scores": [1.0, 0.0],
             "arm": "armA"} for k in range(n)]
    return beam.build_records(conv=conv, questions=questions, agent_rows=rows, seed=seed, dataset="synthetic",
                              data_sha256_prefix="0" * 12)


def test_b2_item_ids_are_opaque_hex_and_conv_and_question_no_live_only_in_grades(tmp_path):
    items, grades, _ = _planted()
    ids = [it["item_id"] for it in items]
    assert len(set(ids)) == len(ids) >= 20
    assert all(re.fullmatch(r"[0-9a-f]{10}", i) for i in ids), ids[:3]
    assert [(g["conv"], g["question_no"]) for g in grades] == [(CONV, QBASE + k) for k in range(len(ids))]
    # items.jsonl, packets, keys and every file name: neither the conversation nor the question number appears
    ip = tmp_path / "items.jsonl"
    ip.write_text("".join(json.dumps(i) + "\n" for i in items))
    seen = [ip.read_text()]
    for it in items:
        cp = run("packet2", "--items", ip, "--item", it["item_id"], "--seed", SEED, "--keys-dir", tmp_path / "keys",
                 "--out-dir", tmp_path / "packets")
        assert cp.returncode == 0, cp.stderr
        seen.append(cp.stdout)
    for d in (tmp_path / "keys", tmp_path / "packets"):
        for f in d.iterdir():
            seen += [f.name, f.read_text()]
    blob = "\n".join(seen)
    assert CONV not in blob and "CONVQZ" not in blob
    for k in range(len(ids)):
        assert str(QBASE + k) not in blob
    assert not re.search(r"-q\d", blob)


def test_b2_ids_are_not_ordered_by_question_number_or_category_and_depend_on_seed_and_conv():
    items, grades, _ = _planted()
    ids = [g["item_id"] for g in grades]  # in question-number order (items.jsonl is in item-id order)
    assert ids != sorted(ids) and ids != sorted(ids, reverse=True)  # no function of the id gives the question order
    by_id = sorted(range(len(ids)), key=lambda k: ids[k])
    cats = [grades[k]["category"] for k in by_id]
    assert any(cats[i] != cats[i + 1] for i in range(len(cats) - 1))
    assert len({k % 3 for k in by_id[:6]}) > 1  # the id-sorted head holds more than one category
    assert sorted(i["item_id"] for i in _planted(seed="other")[0]) != sorted(ids)
    assert sorted(i["item_id"] for i in _planted(conv="OTHERCONV")[0]) != sorted(ids)
    assert sorted(i["item_id"] for i in _planted()[0]) == sorted(ids)  # reproducible


# ---------------------------------------------------------------- S1: one effective reviewer per (item, phase, step)

def _verdict_for(s, item, phase):
    j = {s.letter_of(item, a): v for a, v in s.honest(item).items()} if phase == 2 else s.honest(item)
    return s.vdict(item, j)


@pytest.mark.parametrize("phase", [1, 2, 3])
def test_s1_a_second_effective_reviewer_is_refused_unless_it_supersedes_with_a_reason(tmp_path, phase):
    s = Store(tmp_path)
    item = "i02"
    if phase >= 2:
        s.p1(item)
        s.packet2(item)
    if phase == 3:
        s.p2(item, s.honest(item))
    first = s.must_record(item, phase, "alice", _verdict_for(s, item, phase))
    vd = _verdict_for(s, item, phase)
    before = _bytes(s)
    assert_refused(s.record(item, phase, "bob", vd))
    assert_refused(s.record(item, phase, "bob", vd, extra=["--supersedes", first]))  # no reason
    assert_refused(s.record(item, phase, "bob", vd, extra=["--supersedes", first, "--reason", "  "]))
    assert_refused(s.record(item, phase, "bob", vd, extra=["--supersedes", "0" * 64, "--reason", "wrong hash"]))
    assert _bytes(s) == before
    # control: the same record done right is accepted, and then there is still ONE effective reviewer, so map copes
    cp = s.record(item, phase, "bob", vd, extra=["--supersedes", first, "--reason", "alice's record had a typo"])
    assert cp.returncode == 0, cp.stderr
    last = read_jsonl(s.verdicts)[-1]
    assert last["reviewer"] == "bob" and last["supersedes"] == first and last["reason"]
    cp, _out = s.map()
    assert cp.returncode == 0, cp.stderr


def test_s1_a_second_reviewer_on_a_criterion_2a_is_refused_and_a_split_2a_2b_pair_is_never_made(tmp_path):
    s = CStore(tmp_path)
    sha_a = s.p2a("k2", {"x": "correct", "y": "partly"}, reviewer="alice")
    lj = {s.letter("k2", s.ids["k2"]["x"]): "correct", s.letter("k2", s.ids["k2"]["y"]): "partly"}
    before = _bytes(s)
    assert_refused(s.record("k2", 2, "bob", s.vd("k2", lj, step="2a")))
    assert _bytes(s) == before
    s.p2b("k2", "correct", reviewer="alice")
    before = _bytes(s)
    # bob may not take over the 2a once alice's 2b is in: that would leave a 2a and a 2b by two reviewers, which
    # map refuses for the whole study
    assert_refused(s.record("k2", 2, "bob", s.vd("k2", lj, step="2a"),
                            extra=("--supersedes", sha_a, "--reason", "taking over")))
    assert _bytes(s) == before
    cp, _ = s.map()
    assert cp.returncode == 0, cp.stderr


# ---------------------------------------------------------------- S2: phases are recorded in order

def test_s2_phase2_needs_a_phase1_record_and_phase3_needs_both(tmp_path):
    s = Store(tmp_path)
    s.packet2("i02")
    jl = {s.letter_of("i02", a): v for a, v in s.honest("i02").items()}
    before = _bytes(s)
    assert_refused(s.record("i02", 2, "expert", s.vdict("i02", jl)))  # no phase 1
    assert_refused(s.record("i02", 3, "owner", s.vdict("i02", s.honest("i02"))))  # neither
    assert _bytes(s) == before
    s.p1("i02")
    before = _bytes(s)
    assert_refused(s.record("i02", 3, "owner", s.vdict("i02", s.honest("i02"))))  # phase 1 but no phase 2
    assert _bytes(s) == before
    s.must_record("i02", 2, "expert", s.vdict("i02", jl))  # control: now in order
    s.must_record("i02", 3, "owner", s.vdict("i02", s.honest("i02")))


def test_s2_phase3_without_a_phase1_is_refused_even_when_a_phase2_exists(tmp_path):
    s = Store(tmp_path)
    s.packet2("i02")
    forge_verdict(s.verdicts, item_id="i02", phase=2, reviewer="expert", keyed_by="letter",
                  judgement={s.letter_of("i02", a): v for a, v in s.honest("i02").items()})
    before = _bytes(s)
    assert_refused(s.record("i02", 3, "owner", s.vdict("i02", s.honest("i02"))))
    assert _bytes(s) == before


def test_s2_criterion_items_need_a_phase1_for_the_2a_and_a_2a_and_2b_for_phase3(tmp_path):
    s = CStore(tmp_path)
    s.packet2("k2")
    A, B = s.letter("k2", s.ids["k2"]["x"]), s.letter("k2", s.ids["k2"]["y"])
    lj = {A: "correct", B: "partly"}
    before = _bytes(s)
    assert_refused(s.record("k2", 2, "expert", s.vd("k2", lj, step="2a")))  # no phase 1
    assert not s.verdicts.exists() or _bytes(s) == before
    # a 2b with no phase 1 (the 2a is forged past the rule): still refused
    forge_verdict(s.verdicts, item_id="k2", phase=2, step="2a", reviewer="expert", keyed_by="letter", judgement=lj)
    forge_export(s, item_id="k2")  # so the refusal is about the missing phase 1, not the missing export
    before = _bytes(s)
    assert_refused(s.record("k2", 2, "expert", s.vd("k2", {"criterion": "correct"}, step="2b")))
    assert _bytes(s) == before
    # phase 3 needs both steps: a phase 1 and a 2a are not enough
    t = CStore(tmp_path / "t")
    t.p2a("k2", {"x": "correct", "y": "partly"})  # records phase 1 first
    before = _bytes(t)
    assert_refused(t.record("k2", 3, "owner", t.vd("k2", t.level_j("k2"))))
    assert _bytes(t) == before
    t.p2b("k2", "correct")
    t.ok("k2", 3, "owner", t.vd("k2", t.level_j("k2")))  # control: p1, 2a and 2b recorded


# ---------------------------------------------------------------- S3: packet first, key last, each atomic

def _tree(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*")) if root.exists() else []


def test_s3_a_failed_packet_write_leaves_neither_packet_nor_key(tmp_path):
    import blind_packet
    s = Store(tmp_path / "s")
    out, keys = tmp_path / "packets", tmp_path / "keys"
    (out / "i02.md").mkdir(parents=True)  # the packet cannot be written over a directory (refused: the path exists)
    with pytest.raises((ValueError, OSError)):
        blind_packet.write_packet(str(s.items), "i02", "sd", str(keys), str(out))
    assert not (keys / "i02.json").exists()
    assert _tree(keys) == []  # no temp file left behind either
    assert _tree(out) == ["i02.md"] and (out / "i02.md").is_dir()
    cp = run("packet2", "--items", s.items, "--item", "i02", "--seed", SEED, "--keys-dir", keys, "--out-dir", out)
    assert_refused(cp)  # the CLI reports it as a refusal, not a traceback
    assert not (keys / "i02.json").exists()


def test_s3_a_failed_key_write_leaves_no_key_and_no_packet(tmp_path, monkeypatch):
    import blind_packet
    s = Store(tmp_path / "s")
    out, keys = tmp_path / "packets", tmp_path / "keys"
    for name in ("replace", "link", "rename"):
        real = getattr(blind_packet.os, name, None)
        if real is None:
            continue

        def failing(src, dst, *a, _real=real, **k):
            if str(dst).endswith(".json"):
                raise OSError("simulated key write failure")
            return _real(src, dst, *a, **k)
        monkeypatch.setattr(blind_packet.os, name, failing)
    with pytest.raises(OSError):
        blind_packet.write_packet(str(s.items), "i02", "sd", str(keys), str(out))
    assert _tree(keys) == [] and _tree(out) == []  # neither file, and no temp file


def test_s3_a_successful_run_leaves_exactly_the_packet_and_the_key(tmp_path):
    s = Store(tmp_path)
    s.packet2("i02")
    assert _tree(s.keys) == ["i02.json"] and _tree(s.root / "packets" / "phase2") == ["i02.md"]
    assert json.loads((s.keys / "i02.json").read_text())["item_id"] == "i02"


def test_s3_a_refused_run_because_a_key_exists_writes_no_packet(tmp_path):
    s = Store(tmp_path)
    s.keys.mkdir()
    (s.keys / "i02.json").write_text("{}")
    cp = run("packet2", "--items", s.items, "--item", "i02", "--seed", SEED, "--keys-dir", s.keys,
             "--out-dir", s.root / "packets" / "phase2")
    assert_refused(cp)
    assert _tree(s.root / "packets") == [] and (s.keys / "i02.json").read_text() == "{}"


# ---------------------------------------------------------------- S4: one named predicate

def _self_calls(fn):
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    return {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and isinstance(n.func.value, ast.Name) and n.func.value.id == "self"}


def test_s4_phase2_and_has_phase2_record_share_one_named_predicate():
    import score_review
    assert "has_phase2_record" in _self_calls(score_review.Ctx.phase2)


def test_s4_the_predicate_and_the_view_agree_in_every_state(tmp_path):
    import score_review
    s = CStore(tmp_path)

    def state(item):
        ctx = score_review.Ctx(str(s.items), str(s.grades), str(s.verdicts), str(s.keys))
        return ctx.has_phase2_record(item), ctx.phase2(item)
    s.verdicts.write_text("")
    assert state("k2") == (False, None) and state("r1") == (False, None)
    s.p2a("k2", {"x": "correct", "y": "partly"})
    has, view = state("k2")
    assert has is True and view is None  # a 2a alone: recorded, but the view is incomplete
    s.p2b("k2", "correct")
    has, view = state("k2")
    assert has is True and view["judgement"]["criterion"] == "correct"
    s.r1_p1()
    s.packet2("r1")
    letters = json.loads((s.keys / "r1.json").read_text())["letters"]
    s.ok("r1", 2, "expert", s.vd("r1", {L: "correct" for L in letters}))
    has, view = state("r1")
    assert has is True and set(view["judgement"]) == set(letters.values())


# ---------------------------------------------------------------- amendment 4: a 2a changed after the 2b forces phase 3

def _lj(s, item, x, y=None):
    j = {s.letter(item, s.ids[item]["x"]): x}
    if y is not None:
        j[s.letter(item, s.ids[item]["y"])] = y
    return j


def _changed_after_2b(s, new_y="partly"):
    """k1 is full on both answers and drawn: left alone it is an unquestioned control."""
    s.p1("k1")
    orig = s.p2a("k1", {"x": "correct", "y": "correct"}, guesses_arms={"x": "CRIT-ARM-TOKEN-x"})
    s.p2b("k1", "correct")
    new = s.ok("k1", 2, "expert", s.vd("k1", _lj(s, "k1", "correct", new_y), step="2a"),
               extra=("--supersedes", orig, "--reason", "reread the instruction after seeing the criterion"))
    return orig, new


def test_a4_a_2a_superseded_after_the_2b_is_never_a_control_and_the_original_2a_is_mapped(tmp_path):
    s = CStore(tmp_path)
    orig, new = _changed_after_2b(s)
    k1 = s.outcomes()["k1"]
    assert k1["routing"]["unquestioned_control"] is False and k1["routing"]["in_phase3"] is True
    assert k1["routing"]["phase3_required"] is True and k1["status"] == "pending"
    y = s.ids["k1"]["y"]
    assert k1["phases"]["2"]["judgement"][y] == "correct"  # the ORIGINAL 2a is the one mapped (the unanchored read)
    assert k1["phases"]["2"]["outcome"] == "key_stands" and k1["phases"]["2"]["flagged"] == []
    assert k1["phases"]["2"]["record_sha256"] == orig
    rev = k1["phases"]["2"]["post_reveal_revision"]
    assert rev["record_sha256"] == new and rev["judgement"][y] == "partly" and "reread the instruction" in rev["reason"]


def test_a4_forced_whatever_the_outcome_even_when_the_changed_2a_says_the_same(tmp_path):
    s = CStore(tmp_path)
    _changed_after_2b(s, new_y="correct")  # re-recorded with an identical judgement
    k1 = s.outcomes()["k1"]
    assert k1["phases"]["2"]["outcome"] == "key_stands" and k1["phases"]["1"]["outcome"] == "key_stands"
    assert k1["routing"]["unquestioned_control"] is False and k1["routing"]["in_phase3"] is True
    assert k1["status"] == "pending"


def test_a4_the_first_2b_is_the_witness_even_when_the_2b_is_itself_superseded_later(tmp_path):
    s = CStore(tmp_path)
    orig, new = _changed_after_2b(s)
    first_2b = [r for r in read_jsonl(s.verdicts) if r.get("step") == "2b"][0]["record_sha256"]
    s.ok("k1", 2, "expert", s.vd("k1", {"criterion": "correct"}, step="2b"),
         extra=("--supersedes", first_2b, "--reason", "restated the criterion verdict"))  # now AFTER the changed 2a
    k1 = s.outcomes()["k1"]
    assert k1["routing"]["unquestioned_control"] is False and k1["routing"]["in_phase3"] is True
    assert k1["phases"]["2"]["record_sha256"] == orig
    assert k1["phases"]["2"]["post_reveal_revision"]["record_sha256"] == new


def test_a4_a_2a_changed_before_the_2b_does_not_force_phase3(tmp_path):
    s = CStore(tmp_path)
    s.p1("k1")
    orig = s.p2a("k1", {"x": "correct", "y": "correct"})
    s.ok("k1", 2, "expert", s.vd("k1", _lj(s, "k1", "correct", "correct"), step="2a"),
         extra=("--supersedes", orig, "--reason", "typo, before the criterion was shown"))
    s.p2b("k1", "correct")
    k1 = s.outcomes()["k1"]
    assert k1["routing"]["unquestioned_control"] is True and k1["routing"]["in_phase3"] is False
    assert k1["status"] == "control_settled"
    out = tmp_path / "x.json"
    cp = run("export-phase3", "--items", s.items, "--grades", s.grades, "--verdicts", s.verdicts, "--keys-dir", s.keys,
             "--item", "k1", "--out", out)
    assert cp.returncode == 0, cp.stderr
    assert "phase2_post_reveal_revision" not in json.loads(out.read_text())


def test_a4_export_phase3_maps_the_original_and_carries_the_post_reveal_revision_rekeyed(tmp_path):
    s = CStore(tmp_path)
    orig, new = _changed_after_2b(s)
    out = tmp_path / "x.json"
    cp = run("export-phase3", "--items", s.items, "--grades", s.grades, "--verdicts", s.verdicts, "--keys-dir", s.keys,
             "--item", "k1", "--out", out)
    assert cp.returncode == 0, cp.stderr
    text = out.read_text()
    x = json.loads(text)
    ids = s.ids["k1"]
    assert x["phase2"]["record_sha256"] == orig and x["phase2"]["judgement"][ids["y"]] == "correct"
    assert x["phase2"]["judgement"]["criterion"] == "correct"
    o = x["phase2_post_reveal_revision"]
    assert o["record_sha256"] == new and o["judgement"] == {ids["x"]: "correct", ids["y"]: "partly"}
    assert "reread the instruction" in o["reason"]
    assert orig in text and new in text
    for L in "AB":
        assert '"%s"' % L not in text
    assert "guesses" not in text and "letters" not in text and "CRIT-ARM-TOKEN" not in text


def test_a4_the_report_names_the_post_reveal_revision_and_the_stale_guard_covers_it(tmp_path):
    s = CStore(tmp_path)
    orig, new = _changed_after_2b(s)
    cp, out = s.map()
    assert cp.returncode == 0, cp.stderr
    rep = tmp_path / "report.md"
    cp = run("report", "--items", s.items, "--grades", s.grades, "--verdicts", s.verdicts, "--outcomes", out, "--out", rep)
    assert cp.returncode == 0, cp.stderr
    text = rep.read_text()
    assert new[:12] in text and "post-reveal revision" in text and "reread the instruction" in text
    rows = read_jsonl(out)
    for r in rows:
        if r["item_id"] == "k1":
            r["phases"]["2"]["post_reveal_revision"]["record_sha256"] = "0" * 64
    out.write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert_refused(run("report", "--items", s.items, "--grades", s.grades, "--verdicts", s.verdicts, "--outcomes", out,
                       "--out", tmp_path / "r2.md"))


def test_a4_check_a_2b_may_carry_the_fuller_criterion_and_item_ambiguity_is_a_2a_matter(tmp_path):
    s = CStore(tmp_path)
    s.p2a("k2", {"x": "correct", "y": "partly"})
    s.p2b("k2", "partly", fuller="The criterion also needs a closing question (msg 1).")
    k2 = s.outcomes()["k2"]
    assert k2["phases"]["2"]["fuller_answer_2b"] == "The criterion also needs a closing question (msg 1)."
    rep = tmp_path / "report.md"
    cp, out = s.map()
    assert run("report", "--items", s.items, "--grades", s.grades, "--verdicts", s.verdicts, "--outcomes", out,
               "--out", rep).returncode == 0
    assert "fuller answer (2b): The criterion also needs a closing question" in rep.read_text()
    # item-level ambiguity: accepted in a 2a, refused in a 2b
    t = CStore(tmp_path / "t")
    t.p1("k3")
    t.packet2("k3")
    t.ok("k3", 2, "expert", t.vd("k3", {"ambiguous": "source"}, step="2a"))
    forge_export(t, item_id="k3")  # so the refusal is about ambiguity in a 2b, not the missing export
    assert_refused(t.record("k3", 2, "expert", t.vd("k3", {"ambiguous": "source"}, step="2b")))
