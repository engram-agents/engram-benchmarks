"""p1-question-file.py cells. Contract-first: written before the tool. Synthetic list only (the real frozen list is not
in this branch); same row format as the real one. No student model, no Ollama, no real arm home."""
import hashlib, json, os, random, subprocess, sys
import pytest
from conftest import TOOLS

TOOL = os.path.join(TOOLS, "p1-question-file.py")
SEED = 20261118

ROWS = [
    ("F01", "ex1", "information_extraction", "How old did I say I am?", "You said you are 28 (gold-F01)."),
    ("F02", "ex1", "information_extraction", "Where did I say I am living?", "In Springfield (gold-F02)."),
    ("F03", "ex2", "information_extraction", "What kind of work do I do?", "Producer (gold-F03)."),
    ("F10", "ex5", "information_extraction", "How long have I been dating Tanya?", "2 years (gold-F10)."),
    ("F32", "ex15", "information_extraction", "Which tool did I pick?", "The blue one (gold-F32)."),
    ("F33", "ex15", "information_extraction", "What is my deadline?", "May 5 (gold-F33)."),
    ("F34", "ex16", "information_extraction", "Who is my lead?", "Shawn (gold-F34)."),
    ("F35", "ex16", "information_extraction", "What is the budget?", "$900 (gold-F35)."),
    ("A01", "ex-", "abstention", "What is Bryan's last name?", "No information (gold-A01)."),
    ("A02", "ex-", "abstention", "What does Tanya do for a living?", "No information (gold-A02)."),
    ("A05", "ex-", "abstention", "What is the tuition?", "No information (gold-A05)."),
    ("A09", "ex-", "abstention", "Which car do I own?", "No information (gold-A09)."),
]


def list_text(rows=ROWS, extra=""):
    head = ("# synthetic key-fact list\nCount: 12 questions\n\n## Items (id | exchange | style | question || gold)\n")
    body = "".join(f"{i} | {e} | {s} | {q} || {g}\n" for i, e, s, q, g in rows)
    tail = "\n## Dropped (not in the list)\nF06, F07, F52. Reasons: none, this line must not be parsed as a row.\n"
    return head + body + extra + tail


def write_list(tmp_path, text=None, name="list.md"):
    p = tmp_path / name
    p.write_text(list_text() if text is None else text, encoding="utf-8")
    return p, hashlib.sha256(p.read_bytes()).hexdigest()


def run(listp, sha, out, *extra, seed=SEED):
    cmd = [sys.executable, TOOL, "--list", str(listp), "--expect-sha256", sha, "--seed", str(seed),
           "--out", str(out), *extra]
    return subprocess.run(cmd, capture_output=True, text=True)


def test_sha_mismatch_refuses_and_writes_nothing(tmp_path):
    lp, sha = write_list(tmp_path)
    out = tmp_path / "q.json"
    r = run(lp, "0" * 64, out)
    assert r.returncode == 2 and not out.exists()
    assert sorted(os.listdir(tmp_path)) == ["list.md"]


def test_duplicate_id_refuses(tmp_path):
    lp, sha = write_list(tmp_path, list_text(ROWS + [ROWS[0]]))
    out = tmp_path / "q.json"
    r = run(lp, sha, out)
    assert r.returncode == 2 and not out.exists() and "F01" in (r.stderr + r.stdout)


def test_exclude_id_not_in_list_refuses(tmp_path):
    lp, sha = write_list(tmp_path)
    out = tmp_path / "q.json"
    r = run(lp, sha, out, "--exclude", "F32,F99")
    assert r.returncode == 2 and not out.exists() and "F99" in (r.stderr + r.stdout)


@pytest.mark.parametrize("bad", [
    "F40 | ex9 | information_extraction | A question with no gold marker\n",
    "F41 | ex9 | information_extraction | || a gold with no question\n",
    "F42 | ex9 | information_extraction | A question || \n",
    "A43 | ex- | abstention |\n",
])
def test_unparsable_row_refuses(tmp_path, bad):
    lp, sha = write_list(tmp_path, list_text(extra=bad))
    out = tmp_path / "q.json"
    r = run(lp, sha, out)
    assert r.returncode == 2 and not out.exists()


@pytest.mark.parametrize("bad", [
    "F40 | ex9 | information_extraction | Is it A || or B? || the gold\n",   # two separators: the split is ambiguous
    "F41 | ex9 | information_extraction | A question || a gold || with a second one\n",
])
def test_a_row_with_more_than_one_separator_is_refused_not_truncated(tmp_path, bad):
    lp, sha = write_list(tmp_path, list_text(extra=bad))
    out = tmp_path / "q.json"
    r = run(lp, sha, out)
    assert r.returncode == 2 and not out.exists() and "||" in (r.stderr + r.stdout)


def test_out_already_exists_refuses_and_keeps_it(tmp_path):
    lp, sha = write_list(tmp_path)
    out = tmp_path / "q.json"
    out.write_text("keep me")
    r = run(lp, sha, out)
    assert r.returncode == 2 and out.read_text() == "keep me"


def test_no_rows_refuses(tmp_path):
    lp, sha = write_list(tmp_path, "# nothing here\n")
    out = tmp_path / "q.json"
    r = run(lp, sha, out)
    assert r.returncode == 2 and not out.exists()


def expected_order(ids, seed=SEED):
    ids = sorted(ids)
    random.Random(seed).shuffle(ids)
    return ids


def test_output_is_question_text_only_in_the_specified_order(tmp_path):
    lp, sha = write_list(tmp_path)
    out = tmp_path / "q.json"
    r = run(lp, sha, out, "--exclude", "F32")
    assert r.returncode == 0, r.stderr
    items = json.loads(out.read_bytes())
    want_ids = expected_order([row[0] for row in ROWS if row[0] != "F32"])
    assert [i["id"] for i in items] == want_ids
    by_id = {row[0]: row[3] for row in ROWS}
    assert all(set(i) == {"id", "question"} and i["question"] == by_id[i["id"]] for i in items)
    assert len(items) == len(ROWS) - 1 and "F32" not in want_ids
    # the dropped-ids line of the list is not a row
    assert not {"F06", "F07", "F52"} & set(want_ids)


def test_prints_count_order_and_sha_of_the_written_json(tmp_path):
    lp, sha = write_list(tmp_path)
    out = tmp_path / "q.json"
    r = run(lp, sha, out, "--exclude", "F32")
    lines = r.stdout.splitlines()
    items = json.loads(out.read_bytes())
    assert str(len(items)) in lines[0]
    for i in items:
        assert i["id"] in lines
    assert [l for l in lines if l in {i["id"] for i in items}] == [i["id"] for i in items]
    assert hashlib.sha256(out.read_bytes()).hexdigest() in r.stdout


def test_gold_text_is_never_in_the_output(tmp_path):
    lp, sha = write_list(tmp_path)
    out = tmp_path / "q.json"
    assert run(lp, sha, out).returncode == 0
    text = out.read_text(encoding="utf-8")
    for _, _, _, _, gold in ROWS:
        assert gold not in text
    assert "gold-" not in text


def test_same_inputs_give_byte_identical_json(tmp_path):
    lp, sha = write_list(tmp_path)
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    assert run(lp, sha, a).returncode == 0 and run(lp, sha, b).returncode == 0
    assert a.read_bytes() == b.read_bytes()


def test_a_different_seed_changes_the_order(tmp_path):
    lp, sha = write_list(tmp_path)
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    assert run(lp, sha, a, seed=1).returncode == 0 and run(lp, sha, b, seed=2).returncode == 0
    ia = [i["id"] for i in json.loads(a.read_bytes())]
    ib = [i["id"] for i in json.loads(b.read_bytes())]
    assert ia != ib and sorted(ia) == sorted(ib)
    assert ia == expected_order(ia, 1) and ib == expected_order(ib, 2)


def test_exclude_accepts_a_comma_list(tmp_path):
    lp, sha = write_list(tmp_path)
    out = tmp_path / "q.json"
    assert run(lp, sha, out, "--exclude", "F32,A01").returncode == 0
    ids = [i["id"] for i in json.loads(out.read_bytes())]
    assert "F32" not in ids and "A01" not in ids and len(ids) == len(ROWS) - 2
