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
