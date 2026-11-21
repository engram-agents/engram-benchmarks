"""Tests for build_page.py on synthetic fixtures only. Order: the withhold contract cells (C1..C5), then the port.

Run: python3 -m pytest tools/review-page/tests -q
"""
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(os.path.dirname(HERE), "build_page.py")
sys.path.insert(0, HERE)
import fixtures as fx  # noqa: E402

BLOB = re.compile(r"window\.__BS_DATA__ = (.*?);</script>", re.S)


@pytest.fixture(scope="session")
def bp():
    spec = importlib.util.spec_from_file_location("build_page", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Env:
    """One scratch dir per test plus a runner that calls main(argv) in-process."""

    def __init__(self, bp, tmp_path, capsys):
        self.bp, self.tmp, self.capsys = bp, tmp_path, capsys
        self.data = str(tmp_path / "data")
        self.out = str(tmp_path / "out.html")
        self.answers = str(tmp_path / "answers.json")

    def write(self, data=None, answers=True):
        fx.write_data(self.data, data if data is not None else fx.build_data())
        if answers:
            with open(self.answers, "w", encoding="utf-8") as fh:
                json.dump(fx.answers_file_texts(), fh, ensure_ascii=False)

    def withhold(self, pairs, reason="reason-text"):
        p = str(self.tmp / "withhold.txt")
        with open(p, "w") as fh:
            fh.write("".join(f"{c}:{q}\n" for c, q in pairs))
        return ["--withhold", p, "--withhold-reason", reason]

    def run(self, *extra, base=True):
        argv = (["--data", self.data, "--out", self.out] if base else []) + list(extra)
        try:
            code = self.bp.main(argv)
        except SystemExit as e:
            code = e.code
        cap = self.capsys.readouterr()
        return code, cap.out, cap.err

    def html(self):
        with open(self.out, encoding="utf-8") as fh:
            return fh.read()

    def blob(self):
        return json.loads(BLOB.search(self.html()).group(1))


@pytest.fixture
def env(bp, tmp_path, capsys):
    return Env(bp, tmp_path, capsys)


def rows(blob, name):
    return blob[name]["rows"]


# ----------------------------------------------------------------------------------------------
# withhold cases: (withheld pairs, finding ids the contract says are dropped)
CASES = {
    "one": ({(1, 3)}, {"F2", "F4", "F6"}),
    "two": ({(1, 3), (2, 1)}, {"F2", "F4", "F6"}),
    "all_of_run_A": ({(1, 1), (1, 2), (1, 3), (1, 4)}, {"F1", "F2", "F4", "F6"}),
    "other_conv_same_number": ({(2, 3)}, {"F2", "F5", "F6"}),
}


def withheld_build(env, pairs):
    env.write(fx.build_data())
    code, out, err = env.run(*env.withhold(sorted(pairs)), "--answers-file", env.answers)
    assert code == 0, err
    return env.blob(), env.html()


# ---- C1: every row about a withheld question is gone from every dataset ----
@pytest.mark.parametrize("case", CASES)
def test_c1_answer_rows_removed_and_only_them(env, case):
    pairs, _ = CASES[case]
    blob, _ = withheld_build(env, pairs)
    conv_of = {"RA": 1, "RB": 2}
    got = {(conv_of[r["run_id"]], r["question_no"]) for r in rows(blob, "answers")}
    every = {(spec["conv"], q["n"]) for spec in fx.RUN_SPECS.values() for q in spec["questions"]}
    assert got == every - pairs


@pytest.mark.parametrize("case", CASES)
def test_c1_findings_dropped_when_they_touch_a_withheld_question(env, case):
    pairs, dropped = CASES[case]
    blob, _ = withheld_build(env, pairs)
    ids = {f["finding_id"] for f in rows(blob, "findings")}
    assert ids == {s[0] for s in fx.FINDING_SPECS} - dropped
    # a kept answer row no longer points at a dropped finding
    for a in rows(blob, "answers"):
        linked = {x.strip() for x in a["findings"].split(",") if x.strip()}
        assert not linked & dropped, (a["key"], linked)


def test_c1_categories_and_causes_follow_the_kept_rows(env):
    blob, _ = withheld_build(env, {(1, 1), (1, 3)})  # run A keeps Q2 (beta) and Q4 (beta)
    cats = {(c["run_id"], c["category"]): c for c in rows(blob, "categories")}
    assert ("RA", "alpha_topic") not in cats  # derived only from withheld questions: gone
    assert cats[("RA", "beta_topic")]["n"] == 2
    causes = {(c["run_id"], c["cause"]): c["count"] for c in rows(blob, "causes")}
    assert causes[("RA", "not_stored")] == 1  # Q2 only; Q3's not_stored is withheld
    assert causes[("RA", "over_caution")] == 1  # Q4 only
    assert ("RB", "over_caution") in causes  # other run untouched


def test_c1_answers_file_text_of_withheld_question_not_loaded(env):
    _, html = withheld_build(env, {(1, 3)})
    assert not any(f in html for f in forms(fx.answer_text("RA", 3)))
    assert any(f in html for f in forms(fx.answer_text("RA", 4)))  # the kept question's text is there


# ---- C2: run scores and counts recomputed from the kept rows, labelled over N of M ----
def test_c2_run_scores_recomputed_not_copied(env):
    blob, _ = withheld_build(env, {(1, 3)})  # the shipped run scores are over all 4 questions: a copy would show them
    a = next(r for r in rows(blob, "runs") if r["run_id"] == "RA")
    # kept Q1 = 1.0, Q2 = 0.5 (adjusted 1.0), Q4 = 0.5: official (1+.5+.5)/3 = 66.7, adjusted (1+1+.5)/3 = 83.3
    assert a["official_pct"] == 66.7 and a["adjusted_pct"] == 83.3 and a["adjust_delta"] == 16.6
    assert (a["pass_n"], a["partial_n"], a["fail_n"]) == (1, 2, 0)
    assert (a["asked_back_n"], a["asked_back_justified_n"]) == (2, 1)
    assert (a["questions"], a["questions_total"]) == (3, 4)
    b = next(r for r in rows(blob, "runs") if r["run_id"] == "RB")
    assert (b["questions"], b["questions_total"]) == (4, 4)
    assert b["official_pct"] == 62.5  # (0.75 + 1 + 0.25 + 0.5) / 4, also recomputed over its own kept rows


def test_c2_category_means_recomputed(env):
    blob, _ = withheld_build(env, {(1, 3)})
    c = next(c for c in rows(blob, "categories") if c["run_id"] == "RA" and c["category"] == "alpha_topic")
    assert (c["n"], c["official_pct"], c["adjusted_pct"]) == (1, 100.0, 100.0)  # only Q1 is left
    c = next(c for c in rows(blob, "categories") if c["run_id"] == "RA" and c["category"] == "beta_topic")
    assert (c["n"], c["official_pct"], c["adjusted_pct"]) == (2, 50.0, 75.0)


def test_c2_all_questions_of_a_run_withheld_gives_no_score(env):
    blob, _ = withheld_build(env, CASES["all_of_run_A"][0])
    a = next(r for r in rows(blob, "runs") if r["run_id"] == "RA")
    assert a["official_pct"] is None and a["adjusted_pct"] is None and a["adjust_delta"] is None
    assert (a["questions"], a["questions_total"]) == (0, 4)
    assert (a["pass_n"], a["partial_n"], a["fail_n"], a["asked_back_n"]) == (0, 0, 0, 0)


def test_c2_page_labels_scores_over_n_of_m(env):
    """The label is drawn in the browser from questions_total; check the page code reads it where the scores show."""
    withheld_build(env, {(1, 3)})
    html = env.html()
    assert html.count("questions_total") >= 3  # tile note, scope line, runs table
    assert "of ${" in html or " of " in html


# ---- C3: banner ----
def test_c3_banner_counts_numbers_and_reason(env):
    _, html = withheld_build(env, {(1, 3), (2, 1)})
    assert "2 questions withheld" in html
    assert "conv 1: Q3" in html and "conv 2: Q1" in html
    assert "reason-text" in html


FREE_TEXT_CLAUSE = ("Free text on the questions that remain (notes, findings) is shown as written and is not "
                    "checked for mentions of the withheld questions.")


def test_c3_notice_says_free_text_on_kept_rows_is_not_checked(env):
    _, html = withheld_build(env, {(1, 3)})
    notice = re.search(r'<div class="bs-card" id="withheld-notice".*?</div>', html, re.S).group(0)
    assert FREE_TEXT_CLAUSE in notice
    env.write()
    assert env.run()[0] == 0
    assert "withheld-notice" not in env.html().split("<body>")[1].split("</header>")[0]  # no notice without --withhold
    assert "not checked for mentions" not in env.html().split("<body>")[1].split("</header>")[0]


def test_c3_reason_is_escaped_and_required(env):
    env.write()
    code, _, _ = env.run(*env.withhold([(1, 3)], reason="a <b>bold</b> & claim"))
    assert code == 0
    assert "a &lt;b&gt;bold&lt;/b&gt; &amp; claim" in env.html()
    os.remove(env.out)
    p = str(env.tmp / "withhold.txt")
    code, _, err = env.run("--withhold", p)
    assert code == 2 and "--withhold-reason" in err
    assert not os.path.exists(env.out)


def test_c3_reason_without_withhold_is_refused(env):
    env.write()
    code, _, err = env.run("--withhold-reason", "x")
    assert code == 2 and "--withhold" in err
    assert not os.path.exists(env.out)


# ---- C4: no byte of a withheld question's content survives, tested by generation ----
def _leaf_strings(v, out):
    if isinstance(v, str):
        out.add(v)
        try:
            inner = json.loads(v)
        except ValueError:
            return
        if isinstance(inner, (list, dict)):
            _leaf_strings(inner, out)
    elif isinstance(v, dict):
        for x in v.values():
            _leaf_strings(x, out)
    elif isinstance(v, list):
        for x in v:
            _leaf_strings(x, out)
    elif v is not None and not isinstance(v, bool):
        out.add(str(v))


def forms(s):
    """The ways a string can sit in the output: raw, JSON-escaped once (a field), twice (a JSON field inside a
    JSON field), each with the '</' escape the page applies inside its script block."""
    def esc(x):
        return json.dumps(x, ensure_ascii=False)[1:-1]
    out = set()
    for f in (s, esc(s), esc(esc(s))):
        out.add(f)
        out.add(f.replace("</", "<\\/"))
    return out


def withheld_strings(pairs, dropped):
    """Every string field of every input row about a withheld question: its answer row, its text in the
    answers file, and the finding rows the contract says are derived from it."""
    data = fx.build_data()
    conv_of = {r["run_id"]: r["conv"] for r in data["runs"]["rows"]}
    out = set()
    for a in data["answers"]["rows"]:
        if (conv_of[a["run_id"]], a["question_no"]) in pairs:
            # `grader` is run-level metadata: it stays on the run row even when every question of the run is gone
            _leaf_strings({k: v for k, v in a.items() if k != "grader"}, out)
    for c, n in pairs:
        out.add(fx.answers_file_texts()[f"{c}:{n}"])
    for f in data["findings"]["rows"]:
        if f["finding_id"] in dropped:
            _leaf_strings(f, out)
    return {s for s in out if len(s) > 0}


def find_leaks(html, strings, baseline_html):
    """Strings that are specific to the withheld rows (absent from a build that never had them) and still
    present in `html`. Shared words and enum values (a grade, a mark) are skipped by the baseline filter."""
    leaks = []
    for s in sorted(strings):
        if any(f in baseline_html for f in forms(s)):
            continue
        if any(f in html for f in forms(s)):
            leaks.append(s)
    return leaks


@pytest.mark.parametrize("case", CASES)
def test_c4_no_withheld_content_in_output_by_generation(env, bp, tmp_path, capsys, case):
    pairs, dropped = CASES[case]
    # the baseline: the same tool run on a fixture that never had those questions or findings
    base = Env(bp, tmp_path / "base", capsys)
    (tmp_path / "base").mkdir()
    base.write(fx.build_data(omit=pairs, drop_findings=dropped))
    assert base.run()[0] == 0
    baseline = base.html()
    strings = withheld_strings(pairs, dropped)
    _, html = withheld_build(env, pairs)
    # the check must have something to check: the distinctive strings are in the set and are not baseline words
    checkable = [s for s in strings if not any(f in baseline for f in forms(s))]
    assert any(s.startswith("ANSWERTEXT-") for s in checkable)
    assert any(s.startswith("NOTES-") for s in checkable)
    assert any(s.startswith("RUBRICLINE-") for s in checkable)
    assert len(checkable) >= 5 * len(pairs)
    assert find_leaks(html, strings, baseline) == []


def test_c4_the_leak_check_goes_red_on_a_build_that_keeps_a_withheld_row(env, bp, tmp_path, capsys):
    """Control for the cell above: the same check, pointed at a build that kept the withheld rows, must fire."""
    pairs, dropped = CASES["one"]
    base = Env(bp, tmp_path / "base", capsys)
    (tmp_path / "base").mkdir()
    base.write(fx.build_data(omit=pairs, drop_findings=dropped))
    assert base.run()[0] == 0
    env.write()
    assert env.run()[0] == 0  # no --withhold: the rows are all there
    leaks = find_leaks(env.html(), withheld_strings(pairs, dropped), base.html())
    assert any(s.startswith("NOTES-RA3") for s in leaks)
    assert any(s.startswith("ANSWERTEXT-RA3") for s in leaks)


def test_c4_a_withheld_pair_not_in_the_data_is_refused(env):
    env.write()
    code, _, err = env.run(*env.withhold([(1, 3), (9, 99)]))
    assert code == 2 and "9:99" in err
    assert not os.path.exists(env.out)


@pytest.mark.parametrize("line", ["abc", "1:x", "1", "1:2:3", ":4", "1:0", "-1:2"])
def test_c4_malformed_withhold_line_is_refused(env, line):
    env.write()
    p = str(env.tmp / "w.txt")
    open(p, "w").write(line + "\n")
    code, _, err = env.run("--withhold", p, "--withhold-reason", "r")
    assert code == 2 and line in err
    assert not os.path.exists(env.out)


def test_c4_withhold_file_may_carry_comments_and_blank_lines(env):
    env.write()
    p = str(env.tmp / "w.txt")
    open(p, "w").write("# why\n\n1:3\n  2:1  \n")
    code, _, err = env.run("--withhold", p, "--withhold-reason", "r")
    assert code == 0, err
    assert "2 questions withheld" in env.html()


def test_c4_empty_withhold_file_is_refused(env):
    env.write()
    p = str(env.tmp / "w.txt")
    open(p, "w").write("# nothing\n")
    code, _, err = env.run("--withhold", p, "--withhold-reason", "r")
    assert code == 2 and "no pairs" in err


# ---- C5: without --withhold, today's behaviour ----
def test_c5_recomputed_scores_agree_with_the_precomputed_ones(bp):
    data = fx.build_data()
    got = bp.recompute(data["runs"]["rows"], data["categories"]["rows"], data["causes"]["rows"],
                       data["answers"]["rows"], withheld=set())
    want_runs = [{k: v for k, v in r.items()} for r in data["runs"]["rows"]]
    for g, w in zip(got["runs"], want_runs):
        for k in ("official_pct", "adjusted_pct", "adjust_delta", "pass_n", "partial_n", "fail_n",
                  "asked_back_n", "asked_back_justified_n", "questions"):
            assert g[k] == w[k], (g["run_id"], k)
    assert len(got["runs"]) == len(want_runs)
    assert got["categories"] == data["categories"]["rows"]
    assert got["causes"] == data["causes"]["rows"]


def test_c5_recompute_can_disagree(bp):
    """Control for the cell above: poison one precomputed number and the same comparison must fail."""
    data = fx.build_data(poison_runs=True)
    got = bp.recompute(data["runs"]["rows"], data["categories"]["rows"], data["causes"]["rows"],
                       data["answers"]["rows"], withheld=set())
    assert got["runs"][0]["official_pct"] != data["runs"]["rows"][0]["official_pct"]


def test_c5_without_withhold_every_row_passes_through(env):
    env.write(fx.build_data())
    assert env.run("--answers-file", env.answers)[0] == 0
    blob, html = env.blob(), env.html()
    want = fx.build_data()
    for name in ("runs", "categories", "causes", "answers", "findings"):
        assert rows(blob, name) == want[name]["rows"], name
    assert "withheld" not in html.split("<body>")[1].split("</header>")[0].lower()
    assert "questions_total" in html  # page code present, but no row carries it
    assert all("questions_total" not in r for r in rows(blob, "runs"))


# ---- C6: under --withhold, runs / categories / causes rows carry only their allowed fields ----
# An unknown field on an input row of these three datasets is a summary or a hand-grade column the tool cannot
# vouch for; it is DROPPED silently (a refusal would invite building without --withhold).
UNKNOWN = {"runs": "per_question_summary", "categories": "per_question_note", "causes": "per_question_detail"}


def sentinel_forms(s):
    return {s, json.dumps(s, ensure_ascii=False)[1:-1], json.dumps(s)[1:-1]}


def poisoned(dataset):
    """The fixture with a distinct sentinel (quote and non-ASCII, so its escaped forms differ) in an unknown
    field of EVERY row of `dataset`. Returns (data, [sentinel per row])."""
    data = fx.build_data()
    sents = []
    for i, row in enumerate(data[dataset]["rows"]):
        s = f'SENT-{dataset}-{i}-zq "s" ü'
        row[UNKNOWN[dataset]] = s
        sents.append(s)
    return data, sents


def build_poisoned(env, dataset, pairs):
    data, sents = poisoned(dataset)
    env.write(data)
    code, _, err = env.run(*env.withhold(sorted(pairs)), "--answers-file", env.answers)
    assert code == 0, err
    return env.html(), sents


def allowed_fields(bp):
    """SCHEMA plus the fields recompute() writes, generated: the keys recompute emits from rows that carry only
    SCHEMA fields, joined with SCHEMA."""
    data = fx.build_data()
    got = bp.recompute(data["runs"]["rows"], data["categories"]["rows"], data["causes"]["rows"],
                       data["answers"]["rows"], withheld={(1, 3)})
    return {ds: set(bp.SCHEMA[ds]) | {k for r in got[ds] for k in r} for ds in ("runs", "categories", "causes")}


def test_c6_run_row_unknown_field_is_dropped_under_withhold(env):
    html, sents = build_poisoned(env, "runs", {(1, 3)})
    assert not any(f in html for s in sents for f in sentinel_forms(s))
    assert not any(UNKNOWN["runs"] in r for r in rows(env.blob(), "runs"))


def test_c6_category_row_unknown_field_is_dropped_under_withhold(env):
    # (1,1) and (1,3) are all of RA's alpha_topic questions: that row is derived from withheld rows only
    html, sents = build_poisoned(env, "categories", {(1, 1), (1, 3)})
    assert not any(f in html for s in sents for f in sentinel_forms(s))
    cats = rows(env.blob(), "categories")
    assert any(c["run_id"] == "RA" and c["category"] == "beta_topic" for c in cats)  # a kept row is there, clean
    assert not any(UNKNOWN["categories"] in c for c in cats)


def test_c6_cause_row_unknown_field_is_dropped_under_withhold(env):
    # RA: not_stored is used by withheld Q2 and Q3 only; over_caution is also used by kept Q4
    html, sents = build_poisoned(env, "causes", {(1, 1), (1, 2), (1, 3)})
    assert not any(f in html for s in sents for f in sentinel_forms(s))
    causes = {(c["run_id"], c["cause"]) for c in rows(env.blob(), "causes")}
    assert ("RA", "over_caution") in causes and ("RA", "not_stored") not in causes
    assert not any(UNKNOWN["causes"] in c for c in rows(env.blob(), "causes"))


def test_c6_output_rows_carry_only_the_generated_allowed_fields(env, bp):
    allowed = allowed_fields(bp)
    assert "questions_total" in allowed["runs"]  # the generated set does include what recompute writes
    data = fx.build_data()
    for ds in UNKNOWN:
        for row in data[ds]["rows"]:
            row[UNKNOWN[ds]] = f"x-{ds}"
    env.write(data)
    code, _, err = env.run(*env.withhold([(1, 1), (1, 2), (1, 3)]), "--answers-file", env.answers)
    assert code == 0, err
    blob = env.blob()
    for ds in UNKNOWN:
        assert rows(blob, ds), ds
        for r in rows(blob, ds):
            assert set(r) <= allowed[ds], (ds, set(r) - allowed[ds])


def test_c6_without_withhold_an_unknown_field_passes_through(env):
    data, _ = poisoned("runs")
    env.write(data)
    assert env.run("--answers-file", env.answers)[0] == 0
    assert all(UNKNOWN["runs"] in r for r in rows(env.blob(), "runs"))


# ----------------------------------------------------------------------------------------------
# The port: inputs
@pytest.mark.parametrize("name", ["runs", "categories", "causes", "answers", "findings"])
def test_missing_dataset_file_is_refused_and_named(env, name):
    env.write()
    os.remove(os.path.join(env.data, name + ".json"))
    code, _, err = env.run()
    assert code == 2 and name + ".json" in err
    assert not os.path.exists(env.out)


def test_unparseable_dataset_file_is_refused_and_named(env):
    env.write()
    open(os.path.join(env.data, "causes.json"), "w").write("{not json")
    code, _, err = env.run()
    assert code == 2 and "causes.json" in err
    assert not os.path.exists(env.out)


def test_dataset_without_rows_list_is_refused(env):
    env.write()
    open(os.path.join(env.data, "runs.json"), "w").write(json.dumps({"meta": []}))
    code, _, err = env.run()
    assert code == 2 and "runs.json" in err and "rows" in err


READ_FIELDS = {
    "runs": ["run_id", "conv", "setup_hash", "grader", "official_pct", "adjusted_pct", "adjust_delta", "pass_n",
             "partial_n", "fail_n", "asked_back_n", "asked_back_justified_n"],
    "categories": ["run_id", "category", "label", "n", "official_pct", "adjusted_pct"],
    "causes": ["run_id", "cause", "label", "count"],
    "answers": ["run_id", "key", "question_no", "category", "question", "reference", "official_score",
                "adjusted_score", "grade", "grader", "causes", "asked_back", "ask_justified", "gate_cell",
                "findings", "notes", "rubric", "answer"],
    "findings": ["finding_id", "question_no", "area", "claim_type", "claim", "status", "status_label", "severity",
                 "opened_at", "checks", "verifications", "report_line", "notes"],
}


@pytest.mark.parametrize("name,field", [(n, f) for n, fs in READ_FIELDS.items() for f in fs])
def test_row_missing_a_field_the_page_reads_is_refused(env, name, field):
    data = fx.build_data()
    del data[name]["rows"][0][field]
    env.write(data, answers=False)
    code, _, err = env.run()
    assert code == 2 and name in err and field in err
    assert not os.path.exists(env.out)


def test_bad_rubric_json_or_mark_is_refused(env):
    data = fx.build_data()
    data["answers"]["rows"][0]["rubric"] = "not json"
    env.write(data)
    code, _, err = env.run()
    assert code == 2 and "rubric" in err
    data = fx.build_data()
    data["answers"]["rows"][0]["rubric"] = json.dumps([{"line": "x", "mark": "maybe", "adjusted": None}])
    env.write(data)
    code, _, err = env.run()
    assert code == 2 and "maybe" in err


def test_answer_row_of_an_unknown_run_is_refused(env):
    data = fx.build_data()
    data["answers"]["rows"][0]["run_id"] = "RZ"
    env.write(data)
    code, _, err = env.run()
    assert code == 2 and "RZ" in err


def test_answers_file_supplies_the_answer_text(env):
    env.write(fx.build_data(with_answer=False))
    code, _, err = env.run("--answers-file", env.answers)
    assert code == 0, err
    got = {r["key"]: r["answer"] for r in rows(env.blob(), "answers")}
    assert got["RA:3"] == fx.answer_text("RA", 3) and got["RB:2"] == fx.answer_text("RB", 2)


def test_answers_file_wins_over_an_answer_in_the_row(env):
    env.write(fx.build_data())
    p = str(env.tmp / "a2.json")
    texts = fx.answers_file_texts()
    texts["1:1"] = "FROM-THE-FILE"
    json.dump(texts, open(p, "w"))
    assert env.run("--answers-file", p)[0] == 0
    assert next(r for r in rows(env.blob(), "answers") if r["key"] == "RA:1")["answer"] == "FROM-THE-FILE"


def test_kept_row_with_no_answer_anywhere_is_refused(env):
    env.write(fx.build_data(with_answer=False), answers=False)
    code, _, err = env.run()
    assert code == 2 and "answer" in err and "RA:1" in err
    assert not os.path.exists(env.out)


def test_answers_file_unparseable_or_wrong_shape_is_refused(env):
    env.write(fx.build_data(with_answer=False))
    p = str(env.tmp / "a3.json")
    open(p, "w").write("[1, 2]")
    code, _, err = env.run("--answers-file", p)
    assert code == 2 and "a3.json" in err
    open(p, "w").write(json.dumps({"1-3": "x"}))
    code, _, err = env.run("--answers-file", p)
    assert code == 2 and "1-3" in err
    code, _, err = env.run("--answers-file", str(env.tmp / "nope.json"))
    assert code == 2 and "nope.json" in err


def test_tool_source_has_no_host_path():
    src = open(TOOL, encoding="utf-8").read()
    for bad in ("expanduser", "/home/", "/Users/", "~/", "borges"):
        assert bad not in src, bad


# ---- d3: offline mode ----
FAKE_D3 = b"/* fake d3 for tests */ window.d3 = {};\n"


def test_d3_with_the_wrong_hash_is_refused(env):
    env.write()
    p = str(env.tmp / "d3.min.js")
    open(p, "wb").write(FAKE_D3)
    code, _, err = env.run("--d3", p)
    assert code == 2 and "sha256" in err
    assert not os.path.exists(env.out)


def test_d3_missing_file_is_refused(env):
    env.write()
    code, _, err = env.run("--d3", str(env.tmp / "none.js"))
    assert code == 2 and "none.js" in err


def test_d3_matching_the_pin_is_inlined_and_the_page_makes_no_network_request(env, bp, monkeypatch):
    env.write()
    p = str(env.tmp / "d3.min.js")
    open(p, "wb").write(FAKE_D3)
    monkeypatch.setattr(bp, "D3_SHA256", hashlib.sha256(FAKE_D3).hexdigest())
    code, out, err = env.run("--d3", p)
    assert code == 0, err
    html = env.html()
    assert FAKE_D3.decode().strip() in html
    assert "<script src" not in html and "<link" not in html and "@import" not in html
    assert "http" not in html  # no URL of any kind in the file
    assert "needs network" not in out


def test_without_d3_the_cdn_tag_stays_and_one_line_says_it_needs_network(env):
    env.write()
    code, out, err = env.run()
    assert code == 0, err
    assert '<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"></script>' in env.html()
    lines = [l for l in out.splitlines() if "network" in l]
    assert len(lines) == 1


def test_pinned_hash_is_the_measured_one(bp):
    assert bp.D3_SHA256 == "d6b03aefc9f6c44c7bc78713679c78c295028fa914319119e5cc4b4954855b1c"


# ---- page, title, one-shot CLI ----
def test_title_and_page_markers(env):
    env.write()
    assert env.run("--title", "My <Review>")[0] == 0
    html = env.html()
    assert "<title>My &lt;Review&gt;</title>" in html
    assert '<h1 class="bs-title">My &lt;Review&gt;</h1>' in html
    for marker in ('data-draw="question-list"', 'data-draw="finding-list"', 'data-draw="cat-chart"',
                   "window.dash = dash", "BS.latest"):
        assert marker in html


def test_output_is_valid_utf8_and_blob_has_no_meta(env):
    env.write()
    assert env.run()[0] == 0
    blob = env.blob()
    assert set(blob) == {"runs", "categories", "causes", "answers", "findings"}
    assert all(set(v) == {"rows"} for v in blob.values())


def test_cli_exits_2_on_a_bad_argument_set_and_writes_nothing(tmp_path):
    out = tmp_path / "o.html"
    r = subprocess.run([sys.executable, TOOL, "--data", str(tmp_path / "nodir"), "--out", str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 2 and "nodir" in r.stderr
    assert not out.exists()
    r = subprocess.run([sys.executable, TOOL], capture_output=True, text=True)
    assert r.returncode == 2


def test_cli_smoke_end_to_end(tmp_path):
    d, out = tmp_path / "d", tmp_path / "o.html"
    fx.write_data(str(d), fx.build_data())
    r = subprocess.run([sys.executable, TOOL, "--data", str(d), "--out", str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert out.stat().st_size > 1000


# ----------------------------------------------------------------------------------------------
# Round 2
PAGE = os.path.join(os.path.dirname(HERE), "page.html")
# Which row each variable names inside a draw block of page.html (the fields are then READ from the code).
BLOCK_VARS = {
    "t-run": {"r": "runs"}, "t-official": {"r": "runs"}, "t-adjusted": {"r": "runs"}, "official": {"r": "runs"},
    "adjusted": {"r": "runs"}, "adjusted-note": {"r": "runs"}, "grades": {"r": "runs"},
    "grades-note": {"r": "runs"}, "scope": {"r": "runs"}, "asked": {"r": "runs"}, "asked-note": {"r": "runs"},
    "t-cause": {"r": "runs", "x": "causes"}, "sw0": {}, "sw1": {},
    "cat-chart": {"r": "runs", "x": "categories", "d": "categories"},
    "cause-chart": {"r": "runs", "x": "causes", "d": "causes"},
    "runs-body": {"d": "runs"}, "finding-filters": {}, "finding-list": {"d": "findings"},
    "question-list": {"r": "runs", "d": "answers"},
}


def page_reads():
    """{dataset: {field}} read off page.html: VAR.field inside each draw block, string arguments to runCell,
    BS.mark(..., 'dataset', 'field', ...) pairs, data-field attributes, and the field-name lists the charts loop over."""
    src = open(PAGE, encoding="utf-8").read()
    reads = {n: set() for n in ("runs", "categories", "causes", "answers", "findings")}
    parts = re.split(r"(?=dash\.draw\(')", src)
    seen = set()
    for part in parts:
        m = re.match(r"dash\.draw\('([\w-]+)',", part)
        if not m:
            continue
        name = m.group(1)
        seen.add(name)
        assert name in BLOCK_VARS, f"draw block {name!r} is not mapped in BLOCK_VARS"
        for var, ds in BLOCK_VARS[name].items():
            reads[ds] |= set(re.findall(rf"(?<![\w.]){var}\.(\w+)", part))
            reads[ds] |= set(re.findall(rf"(?<![\w.]){var}\[['\"](\w+)['\"]\]", part))
        for f in re.findall(r"runCell\('(\w+)'", part):
            reads["runs"].add(f)
    for ds, f in re.findall(r"BS\.mark\([^;]*?'(runs|categories|causes|answers|findings)', '(\w+)'", src):
        reads[ds].add(f)
    for f in re.findall(r'<th data-field="(\w+)">', src):
        reads["runs"].add(f)  # the only table carrying data-field is the runs table
    reads["categories"] |= {"official_pct", "adjusted_pct"}  # the chart loops over ['official_pct', 'adjusted_pct']
    assert re.search(r"\['official_pct', 'adjusted_pct'\]\.forEach", src)
    assert seen == set(BLOCK_VARS), set(BLOCK_VARS) - seen
    # names that belong to the dash.data() result objects or to arrays, not to rows
    for ds in reads:
        reads[ds] -= {"status", "data", "length", "columns"} if ds != "findings" else {"data", "length", "columns"}
    return reads


def test_s1_every_field_the_page_reads_is_in_the_schema(bp):
    reads = page_reads()
    assert reads["runs"] >= {"questions", "questions_total", "run_id", "official_pct"}  # the extraction sees them
    for ds, fields in reads.items():
        extra = fields - set(bp.SCHEMA[ds]) - ({"answer", "questions_total"} if ds in ("answers", "runs") else set())
        assert not extra, (ds, sorted(extra))


def test_s1_every_field_the_page_reads_is_in_the_readme_table():
    readme = open(os.path.join(os.path.dirname(HERE), "README.md"), encoding="utf-8").read()
    table = {ln.split("|")[1].strip(): ln for ln in readme.splitlines() if ln.startswith("| `")}
    for ds, fields in page_reads().items():
        row = table[f"`{ds}.json`"]
        for f in fields:
            assert f"`{f}`" in row, (ds, f)


def test_s1_a_runs_row_without_questions_is_refused_and_named(env):
    data = fx.build_data()
    del data["runs"]["rows"][0]["questions"]
    env.write(data)
    code, _, err = env.run()
    assert code == 2 and "runs" in err and "questions" in err
    assert not os.path.exists(env.out)


# ---- S2: the recompute is checked against the scores the input shipped with, on every build ----
def test_s2_agreeing_input_builds(env):
    env.write()
    assert env.run()[0] == 0


@pytest.mark.parametrize("field", ["official_pct", "adjusted_pct"])
def test_s2_a_poisoned_shipped_run_score_is_refused(env, field):
    data = fx.build_data()
    data["runs"]["rows"][0][field] = 99.9
    env.write(data)
    code, _, err = env.run()
    assert code == 2 and "RA" in err and field in err and "99.9" in err
    assert not os.path.exists(env.out)


def test_s2_a_poisoned_shipped_question_score_is_refused(env):
    env.write(fx.build_data(poison_answers=True))
    code, _, err = env.run()
    assert code == 2 and "RA:1" in err and "official_score" in err
    assert not os.path.exists(env.out)


def test_s2_the_check_runs_before_withholding(env):
    """Poison a score of the question that is about to be withheld: the check is over ALL input rows."""
    data = fx.build_data()
    data["answers"]["rows"][2]["official_score"] = 99.9  # RA:3
    env.write(data)
    code, _, err = env.run(*env.withhold([(1, 3)]))
    assert code == 2 and "RA:3" in err


def test_s2_tolerance_is_half_a_unit_of_the_shipped_decimal(env):
    """RA's exact official mean is 54.1667; it ships as 54.2 (0.033 away). 0.05 away still passes, 0.1 away does not."""
    for shipped, want in ((54.2, 0), (54.21, 0), (54.12, 0), (54.3, 2), (54.0, 2)):
        data = fx.build_data()
        data["runs"]["rows"][0]["official_pct"] = shipped
        env.write(data)
        assert env.run()[0] == want, shipped
        if os.path.exists(env.out):
            os.remove(env.out)


# ---- S4: conv is an integer everywhere it appears ----
@pytest.mark.parametrize("bad", ["x", "1.5", "", -1, 1.5, True, None, "-2", " 3"])
def test_s4_bad_conv_in_runs_is_refused(env, bad):
    data = fx.build_data()
    data["runs"]["rows"][0]["conv"] = bad
    env.write(data)
    code, _, err = env.run()
    assert code == 2 and "runs.json" in err and "conv" in err
    assert not os.path.exists(env.out)


def test_s4_bad_conv_in_findings_is_refused(env):
    data = fx.build_data()
    data["findings"]["rows"][0]["conv"] = "one"
    env.write(data)
    code, _, err = env.run()
    assert code == 2 and "findings.json" in err and "conv" in err


def test_s4_a_digit_string_conv_is_normalised_to_int(env):
    data = fx.build_data()
    data["runs"]["rows"][1]["conv"] = "2"
    data["findings"]["rows"][4]["conv"] = "2"  # F5
    env.write(data)
    assert env.run(*env.withhold([(2, 3)]))[0] == 0
    blob = env.blob()
    assert {r["conv"] for r in rows(blob, "runs")} == {1, 2}
    assert all(r["run_id"] != "RB" or r["questions"] == 3 for r in rows(blob, "runs"))
    assert "F5" not in {f["finding_id"] for f in rows(blob, "findings")}


@pytest.mark.parametrize("key", ["x:3", "1:y", "1.0:3", "+1:3", "1:3 "])
def test_s4_bad_answers_file_key_is_refused(env, key):
    env.write(fx.build_data(with_answer=False))
    p = str(env.tmp / "a4.json")
    json.dump({key: "t"}, open(p, "w"))
    code, _, err = env.run("--answers-file", p)
    assert code == 2 and "a4.json" in err


# ---- S5 nit: banner punctuation ----
@pytest.mark.parametrize("reason,want,notwant", [
    ("a reason", "Reason: a reason. Their", "reason.."),
    ("a reason.", "Reason: a reason. Their", "reason.."),
    ("really?", "Reason: really? Their", "?."),
])
def test_s5_banner_punctuation(env, reason, want, notwant):
    env.write()
    assert env.run(*env.withhold([(1, 3)], reason=reason))[0] == 0
    html = env.html()
    assert want in html and notwant not in html


# ----------------------------------------------------------------------------------------------
# Round 3
@pytest.mark.parametrize("opt", ["--withhold", "--answers-file", "--d3"])
def test_r3_an_empty_string_option_is_refused_not_ignored(env, opt):
    """An unset shell variable gives ''. For --withhold that used to withhold nothing, silently."""
    env.write()
    extra = [opt, ""] + (["--withhold-reason", "r"] if opt == "--withhold" else [])
    code, _, err = env.run(*extra)
    assert code == 2 and opt in err
    assert not os.path.exists(env.out)


def test_r3_withhold_with_a_missing_file_or_an_empty_list_is_refused(env):
    env.write()
    code, _, err = env.run("--withhold", str(env.tmp / "absent.txt"), "--withhold-reason", "r")
    assert code == 2 and "absent.txt" in err
    p = str(env.tmp / "empty.txt")
    open(p, "w").write("")
    code, _, err = env.run("--withhold", p, "--withhold-reason", "r")
    assert code == 2 and "no pairs" in err
    assert not os.path.exists(env.out)


def test_r3_a_blank_withhold_reason_is_refused(env):
    env.write()
    code, _, err = env.run(*env.withhold([(1, 3)], reason="  "))
    assert code == 2 and "--withhold-reason" in err
    assert not os.path.exists(env.out)


def _write_raw(env, name, mutate):
    """Write the fixture, then edit one dataset file's TEXT (json.dump writes NaN / Infinity as bare tokens)."""
    env.write()
    p = os.path.join(env.data, name + ".json")
    text = open(p, encoding="utf-8").read()
    new = mutate(text)
    assert new != text
    open(p, "w", encoding="utf-8").write(new)


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity", "1e999"])
@pytest.mark.parametrize("ds,field,old", [
    ("runs", "official_pct", '"official_pct": '), ("answers", "official_score", '"official_score": '),
    ("runs", "pass_n", '"pass_n": '), ("categories", "n", '"n": '), ("causes", "count", '"count": '),
])
def test_r3_non_finite_numbers_are_refused_at_load_and_named(env, ds, field, old, token):
    def mutate(text):
        i = text.index(old) + len(old)
        j = i
        while text[j] not in ",}":
            j += 1
        return text[:i] + token + text[j:]
    _write_raw(env, ds, mutate)
    code, _, err = env.run()
    assert code == 2 and f"{ds}.json" in err
    assert not os.path.exists(env.out)


def test_r3_the_shipped_comparison_itself_fails_on_non_finite(bp):
    """The load check is not the only guard: hand the comparison a NaN directly."""
    data = fx.build_data()
    data["runs"]["rows"][0]["official_pct"] = float("nan")
    with pytest.raises(bp.InputError):
        bp.check_shipped({n: d["rows"] if isinstance(d, dict) else d for n, d in data.items()})
    data = fx.build_data()
    data["answers"]["rows"][0]["adjusted_score"] = float("inf")
    with pytest.raises(bp.InputError):
        bp.check_shipped({n: d["rows"] for n, d in data.items()})


# ---- page reads: every `<identifier>.<field>` in the page's scripts, not only the mapped variables ----
# What a `<identifier>.<member>` read in the page's scripts may be, besides a dataset field. All three lists are
# explicit and were read off the page; a name that is not here and is not a field fails the cell.
# 1. Members of the JSON held INSIDE a row field (the rubric string, the verifications string), which the README
#    documents beside the table: rubric line {line, mark, adjusted}; verification {at, reader, method, result,
#    exchanges_read, speakers_read, evidence, notes}; evidence {exchange, speaker, quote}.
NESTED_FIELDS = {"line", "mark", "adjusted", "at", "reader", "method", "result", "exchanges_read", "speakers_read",
                 "evidence", "exchange", "speaker", "quote"}
# 2. JS built-in and DOM members the page uses.
JS_MEMBERS = {"append", "appendChild", "assign", "ceil", "className", "clientWidth", "clientX", "clientY", "create",
              "createElement", "createTextNode", "data", "dataset", "filter", "forEach", "getBoundingClientRect",
              "getComputedTextLength", "hidden", "id", "lastChild", "left", "length", "max", "min", "node", "onclick",
              "parse", "querySelector", "replaceChildren", "round", "scaleLinear", "selectAll", "setAttribute",
              "style", "textContent", "toFixed", "top", "type", "width"}
# 3. Namespaces the page itself or its libraries define (any member is fine), and the window.BS handle.
JS_OBJECTS = {"BS", "dash", "Math", "d3", "JSON", "Object", "document"}
JS_MEMBERS |= {"BS"}  # window.BS


def script_text():
    src = open(PAGE, encoding="utf-8").read()
    return "\n".join(re.findall(r"<script>(.*?)</script>", src, re.S))


def unknown_dotted_reads(text, known_fields):
    """(identifier, member) pairs read in `text` that are neither a dataset field, a documented JS member, nor a
    member of a documented non-row object."""
    bad = set()
    for ident, member in re.findall(r"(?<![\w.$'\"])([A-Za-z_$][\w$]*)\.([A-Za-z_$][\w$]*)", text):
        if member in known_fields or member in NESTED_FIELDS or member in JS_MEMBERS or ident in JS_OBJECTS:
            continue
        bad.add((ident, member))
    return bad


def test_r3_every_dotted_read_in_the_page_is_a_dataset_field_or_a_documented_builtin(bp):
    known = {f for fields in bp.SCHEMA.values() for f in fields} | {"answer", "questions_total", "conv"}
    text = script_text()
    assert len(text) > 5000  # something was scanned
    assert unknown_dotted_reads(text, known) == set()


def test_r3_the_dotted_read_scan_goes_red_on_a_read_through_an_unmapped_alias(bp):
    known = {f for fields in bp.SCHEMA.values() for f in fields} | {"answer", "questions_total", "conv"}
    text = script_text()
    mutated = text.replace("x.question_no - y.question_no", "x.question_no - y.newfield")
    assert mutated != text, "the sort comparator moved: update this control"
    assert unknown_dotted_reads(mutated, known) == {("y", "newfield")}


# ----------------------------------------------------------------------------------------------
# N1: --official-note. The page draws some labels at run time (d3), so a static check of the built html cannot
# see them. The note therefore lives in the STATIC markup of each section that holds an official column or
# chart, and the set of such sections is GENERATED from page.html here, never listed by hand.
import collections  # noqa: E402
import html as htmllib  # noqa: E402
import itertools  # noqa: E402
from html.parser import HTMLParser  # noqa: E402

# 'Official dataset' / 'Official-dataset' is a findings AREA, not a score label, so it does not count. Both
# patterns match case-INSENSITIVELY: a section whose only label is 'official 71%' or 'adjusted 71%' is in the set.
OFFICIAL_RE = re.compile(r"official_\w+|\bofficial\b(?![- ]dataset)", re.I)
ADJUSTED_RE = re.compile(r"adjusted_\w+|adjust_delta|\badjusted\b", re.I)
MARKER_RE = re.compile(r"__[A-Z]+(?:_[A-Z]+)*__")  # the build's own fill-in markers (__OFFICIAL_NOTE__ ...) are not labels
NOTE_MARKUP = '<p class="bs-k bs-official-note">{}</p>'
INDEP_MARKUP = '<p class="bs-k bs-independence">{}</p>'
INDEP_MARKUP_RE = re.compile(r'<p class="bs-k bs-independence">[^<]*</p>')
VOID = {"br", "hr", "img", "input", "meta", "link"}
# sha256 of the build's output before --official-note existed (build_page.py and page.html at the commit that
# merged the review page), for two builds of the synthetic fixtures. If the page changes on purpose, the new
# output is the new pin; the cell exists so that a build WITHOUT the option can never change by accident.
MAIN_OUTPUT_PINS = {
    "default": "12f3afa8c04e9fb6745a48d38f1e22273a81ece97f5dafcb68df3e1ef3368a46",
    "withhold_title": "98b1e7ab78c30fc973a0f9e19d701695ed58fd222bac9c2c5a537a5f8d68a3dd",
}


class _El:
    def __init__(self, tag, attrs, start, open_text):
        self.tag, self.attrs, self.start, self.open = tag, dict(attrs), start, open_text
        self.end, self.kids = None, []

    @property
    def classes(self):
        return (self.attrs.get("class") or "").split()


class _Tree(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=False)
        self.text = text
        self.root = _El("#root", [], 0, "")
        self.stack = [self.root]
        self._lines = [0] + [m.end() for m in re.finditer("\n", text)]
        self.feed(text)
        self.close()

    def _off(self):
        line, col = self.getpos()
        return self._lines[line - 1] + col

    def handle_starttag(self, tag, attrs):
        el = _El(tag, attrs, self._off(), self.get_starttag_text())
        self.stack[-1].kids.append(el)
        if tag not in VOID:
            self.stack.append(el)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                self.stack[i].end = self.text.index(">", self._off()) + 1
                del self.stack[i:]
                return


def _walk(el):
    for k in el.kids:
        yield k
        yield from _walk(k)


def sections(text):
    """The page's sections as [(key, markup)]: a card, or a top-level block of the page's `.bs` grid that holds
    no card. A container of cards (the tiles row, the two-chart row) is not itself a section; its cards are.
    The key is the section's opening tag text plus its place among the sections that open the same way."""
    tree = _Tree(text)
    root = next(e for e in _walk(tree.root) if e.tag == "div" and e.classes == ["bs"])

    def pick(el):
        if "bs-card" in el.classes:
            return [el]
        if any("bs-card" in d.classes for d in _walk(el)):
            return [s for k in el.kids for s in pick(k)]
        return [el]

    seen = collections.Counter()
    out = []
    for kid in root.kids:
        for el in pick(kid):
            seen[el.open] += 1
            out.append(((el.open, seen[el.open]), text[el.start:el.end]))
    return out


def _page_js(page_text):
    """The page's scripts as one text; whole-line comments are dropped so a comment's wording decides nothing."""
    js = "\n".join(re.findall(r"<script>(.*?)</script>", page_text, re.S))
    return re.sub(r"(?m)^\s*//.*$", "", js)


def helper_code(page_text):
    """The page's shared helper code: every script line before the first draw (the BS.* block, runCell, ...)."""
    js = _page_js(page_text)
    return js[:re.search(r"dash\.draw\('([\w-]+)',", js).start()]


def draw_code(page_text):
    """{draw name: its code} from the page's scripts: from one `dash.draw('<name>',` to the next."""
    js = _page_js(page_text)
    ms = list(re.finditer(r"dash\.draw\('([\w-]+)',", js))
    return {m.group(1): js[m.start():(ms[i + 1].start() if i + 1 < len(ms) else len(js))] for i, m in enumerate(ms)}


def generated_sections(page_text, rx):
    """Keys of the sections of page.html whose markup, or the draw code of a `data-draw` in it, matches `rx`."""
    code = draw_code(page_text)
    hit = []
    for key, markup in sections(page_text):
        names = re.findall(r'data-draw="([\w-]+)"', markup)
        if rx.search(MARKER_RE.sub("", markup + "\n" + "\n".join(code.get(n, "") for n in names))):
            hit.append(key)
    return hit


def missing_from(built, keys, needle):
    """Of the generated section keys, those whose markup in the built page lacks `needle`."""
    have = dict(sections(built))
    return [k for k in keys if k not in have or needle not in have[k]]


def page_html_text():
    with open(PAGE, encoding="utf-8") as fh:
        return fh.read()


NOTE = "Official column graded by the hand-grader; this page is a draft."


def note_build(env, *extra, note=NOTE, pairs=None):
    env.write()
    argv = ["--answers-file", env.answers]
    if note is not None:
        argv += ["--official-note", note]
    if pairs:
        argv += env.withhold(pairs)
    code, out, err = env.run(*argv, *extra)
    assert code == 0, err
    return env.html()


def test_n1_the_generated_set_of_official_sections_is_the_expected_kind():
    keys = generated_sections(page_html_text(), OFFICIAL_RE)
    ids = [k[0] for k in keys]
    assert len(keys) >= 5, keys  # the header, the Official tile, by question type, all runs, every question
    # 'method' is the explanatory note: it names the official score, so a case-insensitive match takes it in
    for want in ('id="top"', 'id="by-category"', 'id="runs"', 'id="questions"', 'id="method"'):
        assert any(want in i for i in ids), (want, ids)
    for notwant in ('id="findings"', 'id="causes"'):  # 'Official dataset' only, or no official column
        assert not any(notwant in i for i in ids), (notwant, ids)


def test_n1_the_set_is_generated_a_new_official_section_joins_it():
    text = page_html_text()
    before = generated_sections(text, OFFICIAL_RE)
    extra = '<section id="added"><h2>Official score per cohort</h2></section>\n  '
    mutated = text.replace('<section id="findings">', extra + '<section id="findings">', 1)
    assert mutated != text
    after = generated_sections(mutated, OFFICIAL_RE)
    assert len(after) == len(before) + 1 and any('id="added"' in k[0] for k in after)
    # a section whose DRAW CODE names an official field, with static markup that does not, joins too
    m2 = text.replace('<section id="findings">', '<section id="added2"><div data-draw="added2"></div></section>\n  <section id="findings">', 1)
    m2 = m2.replace("<script>\n  // Runs table body", "<script>\n  dash.draw('added2', (el) => { el.textContent = BS.latest().official_pct; });\n  // Runs table body", 1)
    assert m2 != text and len(generated_sections(m2, OFFICIAL_RE)) == len(before) + 1


@pytest.mark.parametrize("rx,label", [(OFFICIAL_RE, "official 71%"), (ADJUSTED_RE, "adjusted 71%")])
def test_n1_a_section_labelled_in_lower_case_only_joins_the_set(rx, label):
    text = page_html_text()
    before = generated_sections(text, rx)
    extra = f'<section id="added-lc"><h2>{label}</h2></section>\n  '
    mutated = text.replace('<section id="findings">', extra + '<section id="findings">', 1)
    assert mutated != text
    after = generated_sections(mutated, rx)
    assert len(after) == len(before) + 1 and any('id="added-lc"' in k[0] for k in after)
    # and through draw code: a lower-case label in a draw's code, static markup silent
    m2 = text.replace('<section id="findings">', '<section id="added-lc2"><div data-draw="added-lc2"></div></section>\n  <section id="findings">', 1)
    m2 = m2.replace("<script>\n  // Runs table body", f"<script>\n  dash.draw('added-lc2', (el) => {{ el.textContent = '{label}'; }});\n  // Runs table body", 1)
    assert m2 != text and len(generated_sections(m2, rx)) == len(before) + 1


@pytest.mark.parametrize("area", ["Official dataset", "official dataset", "OFFICIAL-DATASET"])
def test_n1_the_official_dataset_area_stays_out_whatever_its_case(area):
    text = page_html_text()
    before = generated_sections(text, OFFICIAL_RE)
    mutated = text.replace('<section id="findings">', f'<section id="added-area"><h2>{area}</h2></section>\n  <section id="findings">', 1)
    assert mutated != text and generated_sections(mutated, OFFICIAL_RE) == before


def test_n1_the_builds_own_markers_are_not_labels():
    text = page_html_text()
    before = generated_sections(text, OFFICIAL_RE)
    mutated = text.replace('<section id="findings">', '<section id="added-mk"><h2>x</h2>__OFFICIAL_NOTE__</section>\n  <section id="findings">', 1)
    assert mutated != text and generated_sections(mutated, OFFICIAL_RE) == before


# The shared helper code (the BS.* block and the small helpers before the first draw) belongs to no draw's
# code slice, so a label created there would be invisible to the section generators. Its own cell:
def _helper_hits(page_text):
    return [m.group(0) for rx in (OFFICIAL_RE, ADJUSTED_RE) for m in rx.finditer(MARKER_RE.sub("", helper_code(page_text)))]


def test_n1_the_helper_block_holds_no_official_or_adjusted_label():
    text = page_html_text()
    assert len(helper_code(text)) > 500 and "BS.mark" in helper_code(text)  # the block that was meant was read
    assert _helper_hits(text) == []


@pytest.mark.parametrize("label", ["Official", "official 71%", "Adjusted", "adjusted 71%", "official_pct", "adjusted_pct"])
def test_n1_a_label_planted_in_the_helper_block_is_seen(label):
    text = page_html_text()
    mutated = text.replace("  BS.enc = ", f"  BS.planted = '{label}';\n  BS.enc = ", 1)
    assert mutated != text and _helper_hits(mutated) != []


def test_n1_the_official_dataset_area_in_the_helper_block_is_not_a_label():
    text = page_html_text()
    mutated = text.replace("  BS.enc = ", "  BS.planted = 'official dataset';\n  BS.enc = ", 1)
    assert mutated != text and _helper_hits(mutated) == []


def test_n1_the_note_is_in_every_generated_section_when_given(env):
    keys = generated_sections(page_html_text(), OFFICIAL_RE)
    built = note_build(env)
    one = NOTE_MARKUP.format(htmllib.escape(NOTE))
    assert missing_from(built, keys, one) == []
    assert built.count(one) == len(keys)  # once per section, nowhere else


def test_n1_the_note_is_in_every_generated_section_under_withhold_and_title(env):
    keys = generated_sections(page_html_text(), OFFICIAL_RE)
    built = note_build(env, "--title", "T <x>", pairs=[(1, 3)])
    assert missing_from(built, keys, NOTE_MARKUP.format(htmllib.escape(NOTE))) == []


def test_n1_the_coverage_check_goes_red_on_a_section_without_the_note(env):
    keys = generated_sections(page_html_text(), OFFICIAL_RE)
    built = note_build(env)
    one = NOTE_MARKUP.format(htmllib.escape(NOTE))
    broken = built.replace(one, "", 1)  # drop it from the first section only
    assert missing_from(broken, keys, one) == [keys[0]]


@pytest.mark.parametrize("name,extra", [("default", []), ("withhold_title", ["--title", "T <x>"])])
def test_n1_without_the_option_the_page_is_byte_identical_to_main(env, name, extra):
    env.write()
    pairs = env.withhold([(1, 3), (2, 1)]) if name == "withhold_title" else []
    code, _, err = env.run("--answers-file", env.answers, *pairs, *extra)
    assert code == 0, err
    got = env.html()
    assert "official-note" not in got
    # the fixed independence sentence (N2) is the one thing a build adds on its own: take it out, compare
    stripped = INDEP_MARKUP_RE.sub("", got)
    assert hashlib.sha256(stripped.encode("utf-8")).hexdigest() == MAIN_OUTPUT_PINS[name]


def test_n1_the_note_text_appears_nowhere_when_not_given(env):
    built = note_build(env, note=None)
    assert "bs-official-note" not in built and "draft" not in built


def test_n1_the_note_is_escaped_like_the_withhold_reason(env):
    nasty = '<b>& "q" \'x\' __TITLE__ __BANNER__ __OFFICIAL_NOTE__ __INDEPENDENCE__ </div>'
    keys = generated_sections(page_html_text(), OFFICIAL_RE)
    built = note_build(env, note=nasty)
    one = NOTE_MARKUP.format(htmllib.escape(nasty))
    assert missing_from(built, keys, one) == []
    assert built.count(one) == len(keys)
    assert "<b>&" not in built and "&lt;b&gt;&amp;" in built


def template_markers():
    """Every fill-in marker the page template carries, read off page.html (the build fills exactly these)."""
    found = sorted(set(MARKER_RE.findall(page_html_text())))
    assert "__OFFICIAL_NOTE__" in found and "__INDEPENDENCE__" in found, found
    return found


def test_n4_markers_in_title_withhold_reason_and_note_stay_literal_text_where_given(env):
    markers = template_markers()
    sample = " ".join(markers) + ' <i>&"q"'  # every marker the builder fills, and text that needs escaping
    title, reason, note = "T " + sample, "R " + sample, "N " + sample
    env.write()
    code, _, err = env.run("--answers-file", env.answers, "--title", title, *env.withhold([(1, 3)], reason=reason),
                           "--official-note", note)
    assert code == 0, err
    built = env.html()
    esc = {k: htmllib.escape(v) for k, v in (("title", title), ("reason", reason), ("note", note))}
    off_keys = generated_sections(page_html_text(), OFFICIAL_RE)
    adj_keys = generated_sections(page_html_text(), ADJUSTED_RE)
    # each value appears escaped, literally, exactly where it was given
    assert built.count(f"<title>{esc['title']}</title>") == 1
    assert built.count(f'<h1 class="bs-title">{esc["title"]}</h1>') == 1
    assert built.count(f"Reason: {esc['reason']}. Their text") == 1  # the banner adds the closing full stop
    assert built.count(NOTE_MARKUP.format(esc["note"])) == len(off_keys)
    assert missing_from(built, off_keys, NOTE_MARKUP.format(esc["note"])) == []
    assert built.count(indep_markup()) == len(adj_keys) and missing_from(built, adj_keys, indep_markup()) == []
    # nothing was substituted a second time: take out every place a value was given, and no marker is left
    rest = built.replace(f"<title>{esc['title']}</title>", "").replace(f'<h1 class="bs-title">{esc["title"]}</h1>', "")
    rest = rest.replace(f"Reason: {esc['reason']}.", "").replace(NOTE_MARKUP.format(esc["note"]), "")
    assert [m for m in markers if m in rest] == []
    assert "<i>&" not in built  # none of the three values went in unescaped


def test_n1_the_note_is_stripped_of_surrounding_space_like_the_withhold_reason(env):
    built = note_build(env, note="  spaced note \n")
    assert NOTE_MARKUP.format("spaced note") in built


@pytest.mark.parametrize("value", ["", "   ", "\t\n"])
def test_n1_an_empty_or_blank_note_is_refused_named_and_writes_nothing(env, value):
    env.write()
    code, out, err = env.run("--answers-file", env.answers, "--official-note", value)
    assert code == 2 and err.startswith("build_page:") and "--official-note" in err and "empty" in err  # the tool's own refusal, not argparse's
    assert not os.path.exists(env.out)


# ----------------------------------------------------------------------------------------------
# N2: the independence sentence. Fixed text, quoted from SCORE-REVIEW-PRINCIPLES.md section 7, in the static
# markup of every section that holds an adjusted column or chart. No option removes it.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
PRINCIPLES = os.path.join(REPO_ROOT, "SCORE-REVIEW-PRINCIPLES.md")


def principles_sentence():
    """The sentence section 7 says to carry wherever an adjusted score appears: the bold text of the bullet
    that begins 'This sentence, or its equivalent'. Read from the file, never copied here; the line breaks of
    the markdown wrap are single spaces."""
    with open(PRINCIPLES, encoding="utf-8") as fh:
        text = fh.read()
    sec7 = text.split("## 7. What is published", 1)[1].split("\n## ", 1)[0]
    bullet = re.search(r"^- This sentence, or its equivalent.*?(?=^- |\Z)", sec7, re.S | re.M).group(0)
    bold = re.findall(r"\*\*(.+?)\*\*", bullet, re.S)
    assert len(bold) == 1, bold
    return re.sub(r"\s+", " ", bold[0]).strip()


def displayed_sentence():
    s = principles_sentence()
    return s[0].upper() + s[1:]  # the one change allowed: a capital first letter


def indep_markup():
    return INDEP_MARKUP.format(htmllib.escape(displayed_sentence()))


def test_n2_the_principles_file_has_the_sentence_this_cell_reads():
    s = principles_sentence()
    assert s.startswith("all reviewers belong to the team that builds the agent under test.")
    assert s.endswith("they do not make the adjusted score independent.")


def test_n2_the_generated_set_of_adjusted_sections_is_the_expected_kind():
    keys = generated_sections(page_html_text(), ADJUSTED_RE)
    ids = [k[0] for k in keys]
    assert len(keys) >= 5, keys  # the header, the Adjusted tile, by question type, all runs, every question
    for want in ('id="top"', 'id="by-category"', 'id="runs"', 'id="questions"', 'id="method"'):
        assert any(want in i for i in ids), (want, ids)
    for notwant in ('id="findings"', 'id="causes"'):
        assert not any(notwant in i for i in ids), (notwant, ids)


def test_n2_the_set_is_generated_a_new_adjusted_section_joins_it():
    text = page_html_text()
    before = generated_sections(text, ADJUSTED_RE)
    extra = '<section id="added"><h2>Adjusted score per cohort</h2></section>\n  '
    mutated = text.replace('<section id="findings">', extra + '<section id="findings">', 1)
    assert mutated != text and len(generated_sections(mutated, ADJUSTED_RE)) == len(before) + 1


def test_n2_the_sentence_is_in_every_generated_adjusted_section(env):
    keys = generated_sections(page_html_text(), ADJUSTED_RE)
    env.write()
    code, _, err = env.run("--answers-file", env.answers)
    assert code == 0, err
    built = env.html()
    assert missing_from(built, keys, indep_markup()) == []
    assert built.count(indep_markup()) == len(keys)  # once per section, nowhere else


def test_n2_the_coverage_check_goes_red_on_a_section_without_the_sentence(env):
    keys = generated_sections(page_html_text(), ADJUSTED_RE)
    env.write()
    code, _, err = env.run("--answers-file", env.answers)
    assert code == 0, err
    broken = env.html().replace(indep_markup(), "", 1)
    assert missing_from(broken, keys, indep_markup()) == [keys[0]]


def test_n2_the_page_text_is_the_principles_text_exactly(env):
    env.write()
    code, _, err = env.run("--answers-file", env.answers)
    assert code == 0, err
    shown = INDEP_MARKUP_RE.findall(env.html())
    assert shown and set(shown) == {indep_markup()}
    assert htmllib.unescape(shown[0][len('<p class="bs-k bs-independence">'):-len("</p>")]) == displayed_sentence()
    assert displayed_sentence()[1:] == principles_sentence()[1:]  # only the first letter differs


class _Captured(Exception):
    pass


def cli_parser(bp, monkeypatch):
    """The CLI's own argparse parser object. main() builds it locally, so take it at the moment main() hands
    it the argument list: record it, stop before any build."""
    got = []

    def grab(self, *a, **k):
        got.append(self)
        raise _Captured

    with monkeypatch.context() as m:  # undone on exit: the real builds that follow must parse for real
        m.setattr(bp.argparse.ArgumentParser, "parse_args", grab)
        with pytest.raises(_Captured):
            bp.main(["--data", "x", "--out", "y"])
    assert len(got) == 1
    return got[0]


def cli_option_groups(parser):
    """Every option the CLI offers, short AND long, read off the parser's own actions (not its help text),
    grouped as the CLI needs them together. A new option, of either kind, that is in no group fails here, so an
    added option cannot slip past the all-combinations cell below."""
    offered = {o for act in parser._actions for o in act.option_strings} - {"-h", "--help"}
    groups = [("--answers-file",), ("--withhold", "--withhold-reason"), ("--d3",), ("--title",), ("--official-note",)]
    known = {"--data", "--out"} | {o for g in groups for o in g}
    assert offered == known, f"options not in the all-combinations cell: {sorted(offered ^ known)}"
    return groups


def test_n2_the_option_enumeration_reads_the_parser_object_and_sees_every_option(bp, monkeypatch):
    parser = cli_parser(bp, monkeypatch)
    assert {"-h", "--help", "--data", "--out", "--answers-file", "--official-note"} <= {o for a in parser._actions for o in a.option_strings}
    assert len(cli_option_groups(parser)) == 5


@pytest.mark.parametrize("added", [("-z",), ("--zz",), ("-z", "--zz")])
def test_n2_an_option_added_to_the_parser_and_in_no_group_fails_the_enumeration(bp, monkeypatch, added):
    parser = cli_parser(bp, monkeypatch)
    parser.add_argument(*added)  # the cell's own copy of the parser: a short-only option must be caught too
    with pytest.raises(AssertionError, match="options not in the all-combinations cell"):
        cli_option_groups(parser)


def test_n2_every_option_combination_the_cli_offers_still_carries_the_sentence(env, bp, monkeypatch):
    groups = cli_option_groups(cli_parser(bp, monkeypatch))
    d3 = str(env.tmp / "d3.min.js")
    with open(d3, "wb") as fh:
        fh.write(FAKE_D3)
    monkeypatch.setattr(bp, "D3_SHA256", hashlib.sha256(FAKE_D3).hexdigest())
    keys = generated_sections(page_html_text(), ADJUSTED_RE)
    wfile = str(env.tmp / "w.txt")
    with open(wfile, "w") as fh:
        fh.write("1:3\n")
    values = {"--answers-file": env.answers, "--withhold": wfile, "--withhold-reason": "reason-text", "--d3": d3,
             "--title": "T <x>", "--official-note": NOTE}
    env.write()
    n = 0
    for r in range(len(groups) + 1):
        for combo in itertools.combinations(groups, r):
            argv = [x for g in combo for o in g for x in (o, values[o])]
            code, _, err = env.run(*argv)
            assert code == 0, (argv, err)
            built = env.html()
            assert missing_from(built, keys, indep_markup()) == [], argv
            n += 1
    assert n == 2 ** len(groups)  # every subset of the option groups, none skipped


def test_n2_no_option_name_mentions_the_sentence(bp, monkeypatch):
    # the sentence is not switched by anything: no option string of the parser is named for it
    names = [o for a in cli_parser(bp, monkeypatch)._actions for o in a.option_strings]
    assert "--official-note" in names  # the enumeration did read the options
    assert not [o for o in names if re.search(r"independen|sentence", o, re.I)]


def test_n3_the_readme_states_the_note_option_and_the_fixed_sentence_with_its_source():
    with open(os.path.join(os.path.dirname(HERE), "README.md"), encoding="utf-8") as fh:
        readme = re.sub(r"\s+", " ", fh.read())
    assert "--official-note TEXT" in readme
    assert displayed_sentence() in readme  # the sentence itself, as the page shows it
    assert "SCORE-REVIEW-PRINCIPLES.md" in readme and "section 7" in readme
    assert "Pages built before this change lack the independence sentence." in readme
