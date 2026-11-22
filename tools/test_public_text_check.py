"""Tests for tools/public-text-check.py, written against its contract (P1-P7) before the code.

Run:  python3 -m pytest -q tools/        (needs pyarrow; a missing pyarrow is a failure, never a skip)
env:  PUBLIC_TEXT_CHECK  path of the checker under test; default is the sibling public-text-check.py.
      It exists so a deliberately broken copy (a mutant) can be run through these cells.

Every dataset here is SYNTHETIC and built by the tests. No benchmark text appears in this file.
Key-fact rows are assembled at run time so this file never contains a line the row detector matches.
"""
import hashlib
import importlib.util
import json
import os
import re
import subprocess
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

HERE = Path(__file__).resolve().parent
TOOL = Path(os.environ.get("PUBLIC_TEXT_CHECK", HERE / "public-text-check.py"))

# Invented sentences, 12+ words each.
S1 = "the quixotic marmot of lower zandria polished seventeen brass lanterns before the grand harvest feast began"
S2 = "a patient glassblower named orsolya mapped every tidal cave beneath the northern lighthouse during winter"
S3 = "velvet thunderclouds gathered above the orchard while tomasz catalogued forgotten bicycle bells for the museum"
S4 = "seven restless cartographers argued softly about whether granite rivers could remember their own mountains"
S5 = "an unhurried ferryman taught the lighthouse owls to whistle the old harbour anthem every single dawn"
S6 = "two weary lamplighters compared the colour of every evening they had politely ignored last autumn"
S7 = "the cheerful archivist wondered which forgotten staircase led down to the humming copper cellar"
FILL = "qqq zzz www"
W = 8  # the window, in words


def words(s):
    return re.findall(r"[a-z0-9']+", s.lower())


def window(s, start, n):
    return " ".join(words(s)[start:start + n])


def row_text(kind="F"):
    # built at run time: a literal row would be a finding in this very file
    return f"{kind}1 | ex1 | information_extraction | Why? " + "||" + " Because."


@pytest.fixture()
def tool():
    spec = importlib.util.spec_from_file_location("public_text_check_under_test", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def write_dataset(path, rows_override=None):
    table = pa.table({
        "id": [1, 2],
        "prompt": [S1, "short one"],
        "answer": [S2, "no"],
        "conversation": [[{"role": "user", "content": S3}, {"role": "assistant", "content": "fine"}], []],
        "user_questions": [[{"messages": [[S6]], "time_anchor": "x"}], []],
        "probing_questions": [S7, "no"],
        "tags": [[S5, "x"], ["y"]],
        "blob": [json.dumps({"turns": [{"text": S4}]}), "{}"],
    })
    pq.write_table(rows_override if rows_override is not None else table, str(path))
    return Path(path)


def write_min_dataset(path, top=S5 + " tail"):
    """A small dataset that has a leaf of every control class (top-level, nested, question)."""
    pq.write_table(pa.table({
        "top": [top],
        "chat": [[{"content": S2}]],
        "user_questions": [[{"messages": [[S6]]}]],
    }), str(path))
    return Path(path)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.fixture()
def dataset(tmp_path):
    return write_dataset(tmp_path / "ds.parquet")


GITENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.org",  # privacy-scan: allow (synthetic identity for throwaway test repos)
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.org",  # privacy-scan: allow (synthetic identity for throwaway test repos)
    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
}


def git(repo, *args):
    env = dict(os.environ, **GITENV)
    r = subprocess.run(["git", "-C", str(repo), *args], env=env, capture_output=True, text=True, check=True)
    return r.stdout.strip()


def new_repo(tmp_path, name="repo"):
    d = tmp_path / name
    d.mkdir()
    git(d, "init", "-q")
    return d


def put(repo, rel, content):
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        p.write_bytes(content)
    else:
        p.write_text(content, encoding="utf-8")


def commit(repo, msg="c"):
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


def repo_with(tmp_path, files, name="repo"):
    r = new_repo(tmp_path, name)
    for rel, content in files.items():
        put(r, rel, content)
    commit(r)
    return r


def run(tool, monkeypatch, capsys, repo, *argv):
    monkeypatch.chdir(repo)
    capsys.readouterr()
    rc = tool.main(list(argv))
    cap = capsys.readouterr()
    return rc, cap.out, cap.err


def ds_args(dataset, with_sha=True):
    a = ["--dataset", str(dataset)]
    if with_sha:
        a += ["--expect-sha256", sha256(dataset)]
    return a


CLEAN = "nothing of interest here, just an ordinary line of repository prose.\n"


# ---------------------------------------------------------------- P1(a) verbatim detector

def test_p1a_top_level_string_hit(tool, monkeypatch, capsys, tmp_path, dataset):
    r = repo_with(tmp_path, {"a.md": CLEAN + f"{FILL} {window(S1, 3, 10)} {FILL}\n"})
    rc, out, _ = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert rc == 1
    assert out.splitlines() == ["a.md:2: verbatim"]


def test_p1a_nested_struct_hit(tool, monkeypatch, capsys, tmp_path, dataset):
    r = repo_with(tmp_path, {"a.md": f"{window(S3, 2, 10)}\n"})
    rc, out, _ = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert (rc, out.splitlines()) == (1, ["a.md:1: verbatim"])


def test_p1a_list_of_strings_hit(tool, monkeypatch, capsys, tmp_path, dataset):
    r = repo_with(tmp_path, {"a.md": f"{window(S5, 0, 10)}\n"})
    rc, out, _ = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert (rc, out.splitlines()) == (1, ["a.md:1: verbatim"])


def test_p1a_json_string_leaf_hit(tool, monkeypatch, capsys, tmp_path, dataset):
    r = repo_with(tmp_path, {"a.md": f"{window(S4, 1, 10)}\n"})
    rc, out, _ = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert (rc, out.splitlines()) == (1, ["a.md:1: verbatim"])


def test_p1a_normalisation_case_and_punctuation(tool, monkeypatch, capsys, tmp_path, dataset):
    text = window(S2, 0, 10).upper().replace(" ", ",  ") + "!\n"
    r = repo_with(tmp_path, {"a.md": text})
    rc, out, _ = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert (rc, out.splitlines()) == (1, ["a.md:1: verbatim"])


def test_p1a_window_edge_seven_words_no_hit(tool, monkeypatch, capsys, tmp_path, dataset):
    seven = window(S1, 2, W - 1)
    r = repo_with(tmp_path, {"a.md": f"{FILL} {seven} {FILL}\n"})
    rc, out, _ = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert (rc, out) == (0, "")


def test_p1a_window_edge_eight_words_hit(tool, monkeypatch, capsys, tmp_path, dataset):
    r = repo_with(tmp_path, {"a.md": f"{FILL} {window(S1, 2, W)} {FILL}\n"})
    rc, out, _ = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert (rc, out.splitlines()) == (1, ["a.md:1: verbatim"])


def test_p1a_window_crosses_a_line_wrap_reports_first_line(tool, monkeypatch, capsys, tmp_path, dataset):
    w = words(S1)[3:3 + W]
    r = repo_with(tmp_path, {"a.md": " ".join(w[:4]) + "\n" + " ".join(w[4:]) + "\n"})
    rc, out, _ = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert rc == 1
    assert out.splitlines()[0] == "a.md:1: verbatim"


def test_p1a_one_finding_per_line(tool, monkeypatch, capsys, tmp_path, dataset):
    r = repo_with(tmp_path, {"a.md": window(S1, 0, 14) + "\n"})  # five overlapping windows, one line
    rc, out, _ = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert (rc, out.splitlines()) == (1, ["a.md:1: verbatim"])


def test_p1a_unrelated_text_is_clean(tool, monkeypatch, capsys, tmp_path, dataset):
    r = repo_with(tmp_path, {"a.md": CLEAN})
    rc, out, _ = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert (rc, out) == (0, "")


# ---------------------------------------------------------------- P1(b) key-fact row detector

def test_p1b_row_hit_needs_no_dataset(tool, monkeypatch, capsys, tmp_path):
    r = repo_with(tmp_path, {"k.md": CLEAN + row_text("F") + "\n" + row_text("A") + "\n"})
    rc, out, _ = run(tool, monkeypatch, capsys, r, "--rows-only")
    assert (rc, out.splitlines()) == (1, ["k.md:2: key-fact-row", "k.md:3: key-fact-row"])


@pytest.mark.parametrize("line", [
    "F1 | ex1 | information_extraction | Why? Because.",   # no double bar
    " " + "F1 | ex1 | x | y " + "||" + " z",                # not at line start
    "f1 | ex1 | x | y " + "||" + " z",                       # wrong case
    "F1 | note | x | y " + "||" + " z",                      # not an ex id
    "G1 | ex1 | x | y " + "||" + " z",                       # wrong prefix letter
    "F | ex1 | x | y " + "||" + " z",                        # no number
])
def test_p1b_near_misses_are_clean(tool, monkeypatch, capsys, tmp_path, line):
    r = repo_with(tmp_path, {"k.md": line + "\n"})
    rc, out, _ = run(tool, monkeypatch, capsys, r, "--rows-only")
    assert (rc, out) == (0, "")


# ---------------------------------------------------------------- P2 never print matched text

def test_p2_output_never_contains_dataset_text(tool, monkeypatch, capsys, tmp_path, dataset):
    r = repo_with(tmp_path, {
        "a.md": f"{window(S1, 0, 12)}\n{window(S3, 0, 12)}\n{row_text()}\n",
        "b.md": f"{window(S5, 0, 11)}\n",
    })
    rc, out, err = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert rc == 1
    assert sorted(out.splitlines()) == sorted([
        "a.md:1: verbatim", "a.md:2: verbatim", "a.md:3: key-fact-row", "b.md:1: verbatim"])
    seen = " ".join(words(out + "\n" + err))
    for s in (S1, S2, S3, S4, S5):
        ws = words(s)
        for i in range(len(ws) - W + 1):
            assert " ".join(ws[i:i + W]) not in seen
    assert not re.search(r"\b(quixotic|marmot|glassblower|thunderclouds)\b", out + err)


def test_p2_history_output_shape_and_no_leak(tool, monkeypatch, capsys, tmp_path, dataset):
    r = repo_with(tmp_path, {"a.md": CLEAN})
    base = git(r, "rev-parse", "HEAD")
    put(r, "n.md", f"{CLEAN}{window(S1, 0, 12)}\n")
    sha = commit(r)
    rc, out, err = run(tool, monkeypatch, capsys, r, *ds_args(dataset), "--history", f"{base}..HEAD")
    assert (rc, out.splitlines()) == (1, [f"{sha[:12]}:n.md:added:2: verbatim"])
    assert window(S1, 0, W) not in " ".join(words(out + err))


# ---------------------------------------------------------------- P3 modes

def test_p3_file_mode_reads_the_working_tree_of_tracked_files(tool, monkeypatch, capsys, tmp_path, dataset):
    r = repo_with(tmp_path, {"a.md": CLEAN})
    put(r, "a.md", CLEAN + window(S1, 0, 10) + "\n")  # modified, not committed
    put(r, "untracked.md", window(S2, 0, 10) + "\n")   # untracked: never scanned
    rc, out, _ = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert (rc, out.splitlines()) == (1, ["a.md:2: verbatim"])


def test_p3_non_utf8_files_are_skipped_and_counted(tool, monkeypatch, capsys, tmp_path, dataset):
    r = repo_with(tmp_path, {"ok.md": CLEAN, "bin.dat": b"\xff\xfe\x00\x81bad", "bin2.dat": b"\xc3\x28"})
    rc, out, err = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert (rc, out) == (0, "")
    assert "skipped 2 non-UTF-8 files" in err


def test_p3_history_finds_text_added_then_removed(tool, monkeypatch, capsys, tmp_path, dataset):
    r = repo_with(tmp_path, {"a.md": CLEAN})
    base = git(r, "rev-parse", "HEAD")
    put(r, "leak.md", f"{CLEAN}{window(S2, 0, 10)}\n{row_text()}\n")
    leak = commit(r, "adds")
    git(r, "rm", "-q", "leak.md")
    commit(r, "removes")
    # head tree is clean ...
    rc, out, _ = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert (rc, out) == (0, "")
    # ... history is not
    rc, out, _ = run(tool, monkeypatch, capsys, r, *ds_args(dataset), "--history", f"{base}..HEAD")
    assert rc == 1
    assert out.splitlines() == [f"{leak[:12]}:leak.md:added:2: verbatim", f"{leak[:12]}:leak.md:added:3: key-fact-row"]


def test_p3_history_does_not_flag_the_removing_commit(tool, monkeypatch, capsys, tmp_path, dataset):
    r = repo_with(tmp_path, {"a.md": CLEAN, "leak.md": window(S1, 0, 10) + "\n"})
    before = git(r, "rev-parse", "HEAD")
    git(r, "rm", "-q", "leak.md")
    commit(r, "removes")
    rc, out, _ = run(tool, monkeypatch, capsys, r, *ds_args(dataset), "--history", f"{before}..HEAD")
    assert (rc, out) == (0, "")


def test_p3_history_skips_and_counts_non_utf8(tool, monkeypatch, capsys, tmp_path, dataset):
    r = repo_with(tmp_path, {"a.md": CLEAN})
    base = git(r, "rev-parse", "HEAD")
    put(r, "b.dat", b"\xff\xfe\x00\x81bad")
    put(r, "c.md", CLEAN)
    commit(r)
    rc, out, err = run(tool, monkeypatch, capsys, r, *ds_args(dataset), "--history", f"{base}..HEAD")
    assert (rc, out) == (0, "")
    assert "skipped 1 non-UTF-8 files" in err


# ---------------------------------------------------------------- P4 positive controls

def test_p4_controls_pass_on_a_clean_run(tool, monkeypatch, capsys, tmp_path, dataset):
    r = repo_with(tmp_path, {"a.md": CLEAN})
    rc, out, err = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert (rc, out) == (0, "")
    assert "CONTROL FAILED" not in err


def test_p4_broken_verbatim_detector_exits_3_and_scans_nothing(tool, monkeypatch, capsys, tmp_path, dataset):
    r = repo_with(tmp_path, {"a.md": f"{window(S1, 0, 10)}\n{row_text()}\n"})
    monkeypatch.setattr(tool, "detect_verbatim", lambda *a, **k: [])
    rc, out, err = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert rc == 3
    for cls in ("top-level", "nested", "question"):
        assert f"CONTROL FAILED: {cls}" in err
    assert out == ""


def test_p4_broken_row_detector_exits_3_and_scans_nothing(tool, monkeypatch, capsys, tmp_path, dataset):
    r = repo_with(tmp_path, {"a.md": f"{window(S1, 0, 10)}\n{row_text()}\n"})
    monkeypatch.setattr(tool, "detect_keyfact", lambda *a, **k: [])
    rc, out, err = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert rc == 3
    assert "CONTROL FAILED: key-fact-row" in err
    assert out == ""


def test_p4_row_control_runs_with_rows_only_too(tool, monkeypatch, capsys, tmp_path):
    r = repo_with(tmp_path, {"a.md": CLEAN})
    monkeypatch.setattr(tool, "detect_keyfact", lambda *a, **k: [])
    rc, out, err = run(tool, monkeypatch, capsys, r, "--rows-only")
    assert rc == 3 and "CONTROL FAILED: key-fact-row" in err and out == ""


def test_p4_control_runs_before_the_empty_scan_check(tool, monkeypatch, capsys, tmp_path, dataset):
    r = new_repo(tmp_path)  # nothing tracked: would be exit 2, but a failed control outranks it
    monkeypatch.setattr(tool, "detect_verbatim", lambda *a, **k: [])
    rc, _, err = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert rc == 3 and "CONTROL FAILED: top-level" in err


def test_p4_dataset_with_no_12_word_string_cannot_make_a_control(tool, monkeypatch, capsys, tmp_path):
    ds = write_dataset(tmp_path / "short.parquet", pa.table({"q": ["only a few words", "tiny"]}))
    r = repo_with(tmp_path, {"a.md": CLEAN})
    rc, out, err = run(tool, monkeypatch, capsys, r, *ds_args(ds))
    assert rc == 3 and out == ""
    assert "DATASET PROBLEM" in err and str(ds) in err


def test_p4_control_probe_comes_from_the_data(tool, monkeypatch, capsys, tmp_path):
    # a dataset whose only long string is S5: the control must still pass, so it is built from the data, not a fixed phrase
    ds = write_min_dataset(tmp_path / "other.parquet", top=S5)
    r = repo_with(tmp_path, {"a.md": CLEAN})
    rc, _, err = run(tool, monkeypatch, capsys, r, *ds_args(ds))
    assert rc == 0 and "CONTROL FAILED" not in err


# ---------------------------------------------------------------- P4 widened: one control per source class

CLASSES = ("top-level", "nested", "question", "key-fact-row")


def test_p4_each_class_reports_its_control_on_a_clean_run(tool, monkeypatch, capsys, tmp_path, dataset):
    r = repo_with(tmp_path, {"a.md": CLEAN})
    rc, _, err = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert rc == 0
    for cls in CLASSES:
        assert f"control ok: {cls}" in err


def test_p4_controls_go_through_the_real_scan_path(tool, monkeypatch, capsys, tmp_path, dataset):
    r = repo_with(tmp_path, {"a.md": CLEAN})
    real, calls = tool.scan_file, []
    monkeypatch.setattr(tool, "scan_file", lambda path, windows: (calls.append(path), real(path, windows))[1])
    rc, _, _ = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert rc == 0
    assert len(calls) == 3 + 1 + 1  # three dataset-class controls, the row control, the one tracked file
    assert all(not str(c).startswith(str(r)) for c in calls[:4])  # the controls ran on temporary files


@pytest.mark.parametrize("missing,cols", [
    ("top-level", {"chat": [[{"content": S2}]], "user_questions": [[{"messages": [[S6]]}]]}),
    ("nested", {"top": [S5], "user_questions": [S6]}),
    ("question", {"top": [S5], "chat": [[{"content": S2}]]}),
])
def test_p4_dataset_without_a_class_exits_3_naming_it(tool, monkeypatch, capsys, tmp_path, missing, cols):
    ds = tmp_path / "d.parquet"
    pq.write_table(pa.table(cols), str(ds))
    r = repo_with(tmp_path, {"a.md": CLEAN})
    rc, out, err = run(tool, monkeypatch, capsys, r, *ds_args(ds))
    assert rc == 3 and out == ""
    assert f"DATASET PROBLEM: {ds}" in err and f"class {missing}" in err


def test_p4_skipping_nested_leaves_turns_only_the_nested_control_red(tool, monkeypatch, capsys, tmp_path, dataset):
    # the defect of an earlier sweep: it never walked the nested conversation turns
    r = repo_with(tmp_path, {"a.md": f"{window(S3, 0, 10)}\n"})
    monkeypatch.setattr(tool, "leaf_is_indexed", lambda nested, question: not nested)
    rc, out, err = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert rc == 3 and out == ""
    assert "CONTROL FAILED: nested" in err
    assert "CONTROL FAILED: top-level" not in err
    assert "control ok: top-level" in err


def test_p4_skipping_question_leaves_turns_only_the_question_control_red(tool, monkeypatch, capsys, tmp_path, dataset):
    r = repo_with(tmp_path, {"a.md": CLEAN})
    monkeypatch.setattr(tool, "leaf_is_indexed", lambda nested, question: not question)
    rc, _, err = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert rc == 3 and "CONTROL FAILED: question" in err
    assert "CONTROL FAILED: top-level" not in err and "CONTROL FAILED: nested" not in err


def test_p4_question_class_is_found_wherever_it_sits(tool, monkeypatch, capsys, tmp_path):
    # a question column that is a plain top-level string, and one that is a JSON string inside another column
    ds = tmp_path / "d.parquet"
    pq.write_table(pa.table({
        "top": [S5],
        "chat": [[{"content": S2}]],
        "blob": [json.dumps({"probing_questions": [S7]})],
    }), str(ds))
    r = repo_with(tmp_path, {"a.md": f"{window(S7, 0, 10)}\n"})
    rc, out, err = run(tool, monkeypatch, capsys, r, *ds_args(ds))
    assert rc == 1 and out.splitlines() == ["a.md:1: verbatim"]
    assert "control ok: question" in err


# ---------------------------------------------------------------- P5 dataset identity

def test_p5_hash_mismatch_exits_3_with_a_named_line(tool, monkeypatch, capsys, tmp_path, dataset):
    r = repo_with(tmp_path, {"a.md": CLEAN})
    rc, out, err = run(tool, monkeypatch, capsys, r, "--dataset", str(dataset), "--expect-sha256", "0" * 64)
    assert rc == 3 and out == ""
    assert f"DATASET MISMATCH: {dataset}" in err


def test_p5_hash_match_is_accepted_case_insensitively(tool, monkeypatch, capsys, tmp_path, dataset):
    r = repo_with(tmp_path, {"a.md": CLEAN})
    rc, _, _ = run(tool, monkeypatch, capsys, r, "--dataset", str(dataset), "--expect-sha256", sha256(dataset).upper())
    assert rc == 0


def test_p5_missing_dataset_exits_3(tool, monkeypatch, capsys, tmp_path):
    r = repo_with(tmp_path, {"a.md": CLEAN})
    missing = tmp_path / "nope.parquet"
    rc, out, err = run(tool, monkeypatch, capsys, r, "--dataset", str(missing))
    assert rc == 3 and out == ""
    assert f"DATASET PROBLEM: {missing}" in err


def test_p5_not_a_parquet_file_exits_3(tool, monkeypatch, capsys, tmp_path):
    bad = tmp_path / "bad.parquet"
    bad.write_bytes(b"this is not parquet")
    r = repo_with(tmp_path, {"a.md": CLEAN})
    rc, _, err = run(tool, monkeypatch, capsys, r, "--dataset", str(bad))
    assert rc == 3 and f"DATASET PROBLEM: {bad}" in err


def test_p5_empty_dataset_exits_3(tool, monkeypatch, capsys, tmp_path):
    ds = tmp_path / "empty.parquet"
    pq.write_table(pa.table({"q": pa.array([], type=pa.string())}), str(ds))
    r = repo_with(tmp_path, {"a.md": CLEAN})
    rc, _, err = run(tool, monkeypatch, capsys, r, "--dataset", str(ds))
    assert rc == 3 and f"DATASET PROBLEM: {ds}" in err


def test_p5_no_dataset_is_a_usage_error(tool, monkeypatch, capsys, tmp_path):
    r = repo_with(tmp_path, {"a.md": CLEAN})
    rc, out, _ = run(tool, monkeypatch, capsys, r)
    assert (rc, out) == (2, "")


def test_p5_rows_only_says_verbatim_not_run(tool, monkeypatch, capsys, tmp_path):
    r = repo_with(tmp_path, {"a.md": CLEAN})
    rc, _, err = run(tool, monkeypatch, capsys, r, "--rows-only")
    assert rc == 0 and "verbatim detector NOT RUN" in err


def test_p5_rows_only_with_a_dataset_is_a_usage_error(tool, monkeypatch, capsys, tmp_path, dataset):
    r = repo_with(tmp_path, {"a.md": CLEAN})
    rc, _, _ = run(tool, monkeypatch, capsys, r, "--rows-only", *ds_args(dataset))
    assert rc == 2


def test_p5_unpaired_expect_sha256_is_a_usage_error(tool, monkeypatch, capsys, tmp_path, dataset):
    r = repo_with(tmp_path, {"a.md": CLEAN})
    rc, _, _ = run(tool, monkeypatch, capsys, r, "--dataset", str(dataset), "--expect-sha256", sha256(dataset),
                   "--expect-sha256", sha256(dataset))
    assert rc == 2
    rc, _, _ = run(tool, monkeypatch, capsys, r, "--dataset", str(dataset), "--expect-sha256", "not-hex")
    assert rc == 2


def test_p5_two_datasets_pair_in_order(tool, monkeypatch, capsys, tmp_path, dataset):
    other = write_min_dataset(tmp_path / "o.parquet")
    r = repo_with(tmp_path, {"a.md": f"{window(S5, 0, 10)}\n"})
    ok = ["--dataset", str(dataset), "--expect-sha256", sha256(dataset), "--dataset", str(other),
          "--expect-sha256", sha256(other)]
    rc, out, _ = run(tool, monkeypatch, capsys, r, *ok)
    assert rc == 1  # S5 is in both datasets
    swapped = ["--dataset", str(dataset), "--expect-sha256", sha256(other), "--dataset", str(other),
               "--expect-sha256", sha256(dataset)]
    rc, _, err = run(tool, monkeypatch, capsys, r, *swapped)
    assert rc == 3 and "DATASET MISMATCH" in err


# ---------------------------------------------------------------- P6 exit codes

def test_p6_empty_repo_is_2(tool, monkeypatch, capsys, tmp_path, dataset):
    rc, out, _ = run(tool, monkeypatch, capsys, new_repo(tmp_path), *ds_args(dataset))
    assert (rc, out) == (2, "")


def test_p6_not_a_git_repo_is_2(tool, monkeypatch, capsys, tmp_path, dataset):
    d = tmp_path / "plain"
    d.mkdir()
    (d / "a.md").write_text(CLEAN)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    rc, _, _ = run(tool, monkeypatch, capsys, d, *ds_args(dataset))
    assert rc == 2


def test_p6_bad_range_is_2(tool, monkeypatch, capsys, tmp_path, dataset):
    r = repo_with(tmp_path, {"a.md": CLEAN})
    rc, _, _ = run(tool, monkeypatch, capsys, r, *ds_args(dataset), "--history", "nosuchref..HEAD")
    assert rc == 2


def test_p6_empty_range_is_2(tool, monkeypatch, capsys, tmp_path, dataset):
    r = repo_with(tmp_path, {"a.md": CLEAN})
    rc, out, _ = run(tool, monkeypatch, capsys, r, *ds_args(dataset), "--history", "HEAD..HEAD")
    assert (rc, out) == (2, "")


def test_p6_only_non_utf8_files_is_2(tool, monkeypatch, capsys, tmp_path, dataset):
    r = repo_with(tmp_path, {"b.dat": b"\xff\xfe\x00\x81"})
    rc, _, err = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert rc == 2 and "skipped 1 non-UTF-8 files" in err


def test_p6_usage_errors_are_2(tool, monkeypatch, capsys, tmp_path, dataset):
    r = repo_with(tmp_path, {"a.md": CLEAN})
    for argv in (["--bogus"], ["--rows-only", "stray"], ["--history"], ["--rows-only", "--history", ""]):
        rc, _, _ = run(tool, monkeypatch, capsys, r, *argv)
        assert rc == 2, argv


def test_p6_clean_is_0_and_hits_are_1(tool, monkeypatch, capsys, tmp_path):
    clean = repo_with(tmp_path, {"a.md": CLEAN}, "clean")
    rc, _, err = run(tool, monkeypatch, capsys, clean, "--rows-only")
    assert rc == 0 and "clean" in err
    dirty = repo_with(tmp_path, {"a.md": row_text() + "\n"}, "dirty")
    rc, _, err = run(tool, monkeypatch, capsys, dirty, "--rows-only")
    assert rc == 1 and "1 finding" in err


# ---------------------------------------------------------------- P7 exemptions

def test_p7_only_the_fixtures_directory_is_exempt_by_path(tool, monkeypatch, capsys, tmp_path, dataset):
    leak = f"{window(S1, 0, 10)}\n{row_text()}\n"
    r = repo_with(tmp_path, {"ok.md": CLEAN, "tools/public-text-check-fixtures/x.txt": leak})
    rc, out, _ = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert (rc, out) == (0, "")
    r2 = repo_with(tmp_path, {"ok.md": CLEAN, "tools/other-fixtures/x.txt": leak}, "r2")
    rc, out, _ = run(tool, monkeypatch, capsys, r2, *ds_args(dataset))
    assert rc == 1
    assert out.splitlines() == ["tools/other-fixtures/x.txt:1: verbatim", "tools/other-fixtures/x.txt:2: key-fact-row"]


def test_p7_exempt_files_alone_are_an_empty_scan(tool, monkeypatch, capsys, tmp_path, dataset):
    r = repo_with(tmp_path, {"tools/public-text-check-fixtures/x.txt": CLEAN})
    rc, _, _ = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert rc == 2


def test_p7_history_skips_the_fixtures_directory(tool, monkeypatch, capsys, tmp_path, dataset):
    r = repo_with(tmp_path, {"a.md": CLEAN})
    base = git(r, "rev-parse", "HEAD")
    put(r, "tools/public-text-check-fixtures/x.txt", window(S1, 0, 10) + "\n")
    put(r, "b.md", CLEAN)
    commit(r)
    rc, out, _ = run(tool, monkeypatch, capsys, r, *ds_args(dataset), "--history", f"{base}..HEAD")
    assert (rc, out) == (0, "")


def test_p7_privacy_scan_allow_marker_does_not_exempt(tool, monkeypatch, capsys, tmp_path, dataset):
    marker = "privacy-scan: allow"
    r = repo_with(tmp_path, {"a.md": f"{window(S1, 0, 10)} {marker}\n{row_text()} {marker}\n"})
    rc, out, _ = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert (rc, out.splitlines()) == (1, ["a.md:1: verbatim", "a.md:2: key-fact-row"])


# ---------------------------------------------------------------- this repository itself

def test_this_repository_has_no_key_fact_rows(tool, monkeypatch, capsys):
    top = subprocess.run(["git", "-C", str(HERE), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if top.returncode != 0:
        pytest.skip("not inside a git repository")
    rc, out, _ = run(tool, monkeypatch, capsys, top.stdout.strip(), "--rows-only")
    assert (rc, out) == (0, "")


# ---------------------------------------------------------------- P10 acknowledged history

ACK = "tools/public-text-check-acknowledged.txt"


def leak_repo(tmp_path, name="repo"):
    """A repo whose one commit after `base` adds a file with a verbatim hit (line 2) and a row (line 3)."""
    r = repo_with(tmp_path, {"a.md": CLEAN}, name)
    base = git(r, "rev-parse", "HEAD")
    put(r, "leak.md", f"{CLEAN}{window(S1, 0, 10)}\n{row_text()}\n")
    return r, base, commit(r, "adds")


def write_ack(r, *lines):
    put(r, ACK, "\n".join(lines) + "\n")


def hist(tool, monkeypatch, capsys, r, dataset, base):
    return run(tool, monkeypatch, capsys, r, *ds_args(dataset), "--history", f"{base}..HEAD")


def test_p10_listed_pair_is_acknowledged_not_a_finding(tool, monkeypatch, capsys, tmp_path, dataset):
    r, base, leak = leak_repo(tmp_path)
    write_ack(r, "# comment", "", f"{leak} leak.md -- known and kept by decision")
    rc, out, err = hist(tool, monkeypatch, capsys, r, dataset, base)
    assert rc == 0
    assert out.splitlines() == [f"acknowledged: {leak[:12]}:leak.md (2 lines)"]
    assert "clean" in err
    seen = " ".join(words(out + "\n" + err))
    assert window(S1, 0, 10) not in seen


def test_p10_file_mode_ignores_the_list_entirely(tool, monkeypatch, capsys, tmp_path, dataset):
    r, _, leak = leak_repo(tmp_path)  # leak.md is at the tip
    write_ack(r, f"{leak} leak.md -- known and kept by decision")
    rc, out, _ = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert (rc, out.splitlines()) == (1, ["leak.md:2: verbatim", "leak.md:3: key-fact-row"])
    write_ack(r, "garbage that would be refused in history mode")
    rc, out, _ = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert rc == 1 and len(out.splitlines()) == 2


def test_p10_same_path_in_a_different_commit_is_still_a_finding(tool, monkeypatch, capsys, tmp_path, dataset):
    r, base, first = leak_repo(tmp_path)
    git(r, "rm", "-q", "leak.md")
    commit(r, "removes")
    put(r, "leak.md", f"{window(S2, 0, 10)}\n")
    second = commit(r, "adds again")
    write_ack(r, f"{first} leak.md -- known and kept by decision")
    rc, out, _ = hist(tool, monkeypatch, capsys, r, dataset, base)
    assert rc == 1
    assert out.splitlines() == [f"{second[:12]}:leak.md:added:1: verbatim", f"acknowledged: {first[:12]}:leak.md (2 lines)"]


def test_p10_other_path_in_the_listed_commit_is_still_a_finding(tool, monkeypatch, capsys, tmp_path, dataset):
    r, base, leak = leak_repo(tmp_path)
    put(r, "other.md", f"{window(S2, 0, 10)}\n")
    second = commit(r, "adds other")
    write_ack(r, f"{leak} leak.md -- known and kept by decision")
    rc, out, _ = hist(tool, monkeypatch, capsys, r, dataset, base)
    assert rc == 1 and f"{second[:12]}:other.md:added:1: verbatim" in out.splitlines()


@pytest.mark.parametrize("what,line", [
    ("no reason", "{sha} leak.md"),
    ("empty reason", "{sha} leak.md -- "),
    ("short sha", "{short} leak.md -- reason"),
    ("non-hex sha", "{nonhex} leak.md -- reason"),
    ("not a commit", "{absent} leak.md -- reason"),
    ("no path", "{sha} -- reason"),
])
def test_p10_refusals_exit_2(tool, monkeypatch, capsys, tmp_path, dataset, what, line):
    r, base, leak = leak_repo(tmp_path)
    line = line.format(sha=leak, short=leak[:12], nonhex="g" * 40, absent="0" * 40)
    write_ack(r, line)
    rc, out, err = hist(tool, monkeypatch, capsys, r, dataset, base)
    assert rc == 2, what
    assert out == "" and "acknowledged list: line 1" in err


def test_p10_a_pair_with_no_finding_in_the_range_is_a_note_not_a_failure(tool, monkeypatch, capsys, tmp_path, dataset):
    r, base, leak = leak_repo(tmp_path)
    put(r, "fine.md", CLEAN)
    clean_commit = commit(r, "clean")
    write_ack(r, f"{leak} leak.md -- known and kept by decision", f"{clean_commit} fine.md -- reason")
    rc, out, err = hist(tool, monkeypatch, capsys, r, dataset, base)
    assert rc == 0
    assert out.splitlines() == [f"acknowledged: {leak[:12]}:leak.md (2 lines)"]
    assert f"NOTE: acknowledged entry matched no finding in this range: {clean_commit[:12]}:fine.md" in err


def test_p10_controls_run_before_the_list_is_read(tool, monkeypatch, capsys, tmp_path, dataset):
    r, base, leak = leak_repo(tmp_path)
    write_ack(r, "{} leak.md".format(leak))  # would be a refusal
    monkeypatch.setattr(tool, "detect_verbatim", lambda *a, **k: [])
    rc, _, err = hist(tool, monkeypatch, capsys, r, dataset, base)
    assert rc == 3 and "CONTROL FAILED: top-level" in err


def test_p10_the_list_file_is_exempt_from_the_detectors_by_path(tool, monkeypatch, capsys, tmp_path, dataset):
    r = repo_with(tmp_path, {"a.md": CLEAN})
    base = git(r, "rev-parse", "HEAD")
    put(r, ACK, f"# {window(S1, 0, 10)}\n")
    commit(r, "adds the list")
    rc, out, err = hist(tool, monkeypatch, capsys, r, dataset, base)
    assert rc == 0, err
    # file mode never reads the list, so a row-shaped line there is exempt by path alone
    put(r, ACK, f"# {window(S1, 0, 10)}\n{row_text()}\n")
    commit(r, "edits the list")
    rc, out, _ = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert (rc, out) == (0, "")


def test_p10_the_shipped_list_is_well_formed(tool, monkeypatch, capsys):
    top = subprocess.run(["git", "-C", str(HERE), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if top.returncode != 0 or not (Path(top.stdout.strip()) / ACK).exists():
        pytest.skip("no shipped list here")
    rc, _, err = run(tool, monkeypatch, capsys, top.stdout.strip(), "--rows-only", "--history", "HEAD~1..HEAD")
    assert "acknowledged list" not in err


# ---------------------------------------------------------------- P12 exemption by content hash, P13 the stated bound

EX = "tools/public-text-check-exempt-windows.txt"
APPROVED = "approved: test seat (ref 1)"
BOUND = ("window 8 words; exemptions {n} (by content hash); acknowledged history {m}; negative control: this "
         "repository's own prose and code (every tracked file outside "
         "studies/beam-2026-11/data/), measured on the merge of study/beam-tuning-log-2 3f0904ee "
         "with main 8e6d522b, 2026-11-22: at 8 words every in-scope hit is a hash-exempted window; "
         "4 lines at 9, 2 at 10, 2 at 12, all web boilerplate in tools/review-page")


def wsha(text):
    return hashlib.sha256(" ".join(words(text)).encode()).hexdigest()


def ex_line(text, reason="a measured false positive", approved=APPROVED):
    return f"{wsha(text)} -- {reason} -- {approved}"


def write_ex(r, *lines):
    put(r, EX, "\n".join(lines) + "\n")


def test_p11_the_window_is_eight_words(tool):
    assert tool.WINDOW == 8


def test_p12_a_listed_window_is_not_a_hit_in_file_mode(tool, monkeypatch, capsys, tmp_path, dataset):
    r = repo_with(tmp_path, {"a.md": f"{FILL} {window(S1, 2, W)} {FILL}\n"})
    write_ex(r, "# comment", "", ex_line(window(S1, 2, W)))
    rc, out, _ = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert (rc, out) == (0, "")


def test_p12_a_listed_window_is_not_a_hit_in_history_mode(tool, monkeypatch, capsys, tmp_path, dataset):
    r = repo_with(tmp_path, {"a.md": CLEAN})
    base = git(r, "rev-parse", "HEAD")
    put(r, "b.md", f"{FILL} {window(S1, 2, W)} {FILL}\n")
    commit(r)
    write_ex(r, ex_line(window(S1, 2, W)))
    rc, out, _ = hist(tool, monkeypatch, capsys, r, dataset, base)
    assert (rc, out) == (0, "")


def test_p12_the_exemption_is_by_content_not_by_whole_line(tool, monkeypatch, capsys, tmp_path, dataset):
    # a second, unlisted window on the same line still counts
    r = repo_with(tmp_path, {"a.md": f"{window(S1, 0, W)} {FILL} {window(S2, 0, W)}\n"})
    write_ex(r, ex_line(window(S1, 0, W)))
    rc, out, _ = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert (rc, out.splitlines()) == (1, ["a.md:1: verbatim"])
    write_ex(r, ex_line(window(S1, 0, W)), ex_line(window(S2, 0, W)))
    rc, out, _ = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert (rc, out) == (0, "")


def test_p12_the_exemption_is_by_content_not_by_file(tool, monkeypatch, capsys, tmp_path, dataset):
    # a listed window in a file does not exempt the rest of that file, nor the same window... only that window
    r = repo_with(tmp_path, {"a.md": f"{window(S1, 0, W)}\n{CLEAN}{window(S2, 0, W)}\n"})
    write_ex(r, ex_line(window(S1, 0, W)))
    rc, out, _ = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert (rc, out.splitlines()) == (1, ["a.md:3: verbatim"])


def test_p12_an_unlisted_hash_exempts_nothing(tool, monkeypatch, capsys, tmp_path, dataset):
    r = repo_with(tmp_path, {"a.md": f"{window(S1, 0, W)}\n"})
    write_ex(r, f"{'0' * 64} -- some reason -- {APPROVED}")
    rc, out, _ = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert (rc, out.splitlines()) == (1, ["a.md:1: verbatim"])


@pytest.mark.parametrize("what,line", [
    ("no reason", "{h}"),
    ("no approved field", "{h} -- a reason"),
    ("empty approved", "{h} -- a reason -- approved:"),
    ("approved without the label", "{h} -- a reason -- somebody"),
    ("empty reason", "{h} --  -- approved: x"),
    ("short hash", "{short} -- a reason -- approved: x"),
    ("non-hex hash", "{nonhex} -- a reason -- approved: x"),
])
def test_p12_refusals_exit_2(tool, monkeypatch, capsys, tmp_path, dataset, what, line):
    r = repo_with(tmp_path, {"a.md": CLEAN})
    h = wsha(window(S1, 0, W))
    write_ex(r, line.format(h=h, short=h[:40], nonhex="g" * 64))
    rc, out, err = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert rc == 2, what
    assert out == "" and "exempt windows list: line 1" in err


def test_p12_a_refusal_applies_in_history_mode_too(tool, monkeypatch, capsys, tmp_path, dataset):
    r, base, _ = leak_repo(tmp_path)
    write_ex(r, "not a valid entry")
    rc, _, err = hist(tool, monkeypatch, capsys, r, dataset, base)
    assert rc == 2 and "exempt windows list" in err


def test_p12_an_entry_that_matched_nothing_is_a_note(tool, monkeypatch, capsys, tmp_path, dataset):
    r = repo_with(tmp_path, {"a.md": CLEAN})
    write_ex(r, ex_line(window(S1, 0, W)))
    rc, out, err = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert (rc, out) == (0, "")
    assert f"NOTE: exempt-window entry matched nothing in this scan: {wsha(window(S1, 0, W))[:12]}" in err


def test_p12_a_used_entry_makes_no_note(tool, monkeypatch, capsys, tmp_path, dataset):
    r = repo_with(tmp_path, {"a.md": f"{window(S1, 0, W)}\n"})
    write_ex(r, ex_line(window(S1, 0, W)))
    _, _, err = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert "NOTE" not in err


def test_p12_the_list_file_is_exempt_by_path(tool, monkeypatch, capsys, tmp_path, dataset):
    r = repo_with(tmp_path, {"a.md": CLEAN})
    write_ex(r, f"# {window(S1, 0, W)}")
    commit(r, "adds the list")
    rc, out, _ = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert (rc, out) == (0, "")


def test_p12_controls_run_before_the_list_is_read(tool, monkeypatch, capsys, tmp_path, dataset):
    r = repo_with(tmp_path, {"a.md": CLEAN})
    write_ex(r, "garbage")
    monkeypatch.setattr(tool, "detect_verbatim", lambda *a, **k: [])
    rc, _, err = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert rc == 3 and "CONTROL FAILED: top-level" in err


def test_p12_print_hit_hashes_prints_hashes_never_text(tool, monkeypatch, capsys, tmp_path, dataset):
    r = repo_with(tmp_path, {"a.md": f"{FILL} {window(S1, 0, W)} {FILL}\nplain\n{window(S2, 1, W)}\n"})
    rc, out, err = run(tool, monkeypatch, capsys, r, *ds_args(dataset), "--print-hit-hashes")
    assert rc == 1
    lines = out.splitlines()
    assert f"a.md:1: {wsha(window(S1, 0, W))}" in lines
    assert f"a.md:3: {wsha(window(S2, 1, W))}" in lines
    assert not re.search(r"\b(quixotic|marmot|glassblower)\b", out + err)
    # a normal run prints no hash at all
    rc, out, err = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert not re.search(r"[0-9a-f]{64}", out + err)


def test_p12_print_hit_hashes_skips_exempt_windows_and_works_in_history(tool, monkeypatch, capsys, tmp_path, dataset):
    r = repo_with(tmp_path, {"a.md": CLEAN})
    base = git(r, "rev-parse", "HEAD")
    put(r, "b.md", f"{window(S1, 0, W)}\n{window(S2, 0, W)}\n")
    sha = commit(r)
    write_ex(r, ex_line(window(S1, 0, W)))
    rc, out, _ = run(tool, monkeypatch, capsys, r, *ds_args(dataset), "--history", f"{base}..HEAD", "--print-hit-hashes")
    assert rc == 1
    assert f"{sha[:12]}:b.md:added:2: {wsha(window(S2, 0, W))}" in out.splitlines()
    assert wsha(window(S1, 0, W)) not in out


def test_p12_the_shipped_exempt_list_is_well_formed(tool, monkeypatch, capsys):
    top = subprocess.run(["git", "-C", str(HERE), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if top.returncode != 0 or not (Path(top.stdout.strip()) / EX).exists():
        pytest.skip("no shipped list here")
    _, _, err = run(tool, monkeypatch, capsys, top.stdout.strip(), "--rows-only")
    assert "exempt windows list" not in err
    header = (Path(top.stdout.strip()) / EX).read_text()
    assert "second seat" in header.lower()


def test_p13_every_run_states_its_bound(tool, monkeypatch, capsys, tmp_path, dataset):
    r = repo_with(tmp_path, {"a.md": CLEAN})
    rc, _, err = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert rc == 0
    assert "public-text-check: " + BOUND.format(n=0, m=0) in err.splitlines()


def test_p13_counts_are_the_lists_in_force(tool, monkeypatch, capsys, tmp_path, dataset):
    r, base, leak = leak_repo(tmp_path)
    write_ex(r, ex_line(window(S3, 0, W)), ex_line(window(S4, 0, W)))
    write_ack(r, f"{leak} leak.md -- known and kept by decision")
    _, _, err = hist(tool, monkeypatch, capsys, r, dataset, base)
    assert "public-text-check: " + BOUND.format(n=2, m=1) in err.splitlines()
    # file mode never reads the acknowledged list
    _, _, err = run(tool, monkeypatch, capsys, r, *ds_args(dataset))
    assert "public-text-check: " + BOUND.format(n=2, m=0) in err.splitlines()


def test_p13_rows_only_states_its_bound_too(tool, monkeypatch, capsys, tmp_path):
    r = repo_with(tmp_path, {"a.md": CLEAN})
    _, _, err = run(tool, monkeypatch, capsys, r, "--rows-only")
    assert "public-text-check: " + BOUND.format(n=0, m=0) in err.splitlines()
