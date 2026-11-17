"""Part C cells: plant-control.py on a synthetic, disposable arm home. Contract-first: written before the tool.

Needs P1_ENGRAM_PLUGIN (an ENGRAM plugin tree that holds engram_observation.py) and a python that can run ENGRAM
(the interpreter running pytest). No student model, no real preserved home."""
import hashlib, json, os, re, shutil, subprocess, sys
import pytest
from conftest import TOOLS, MEMORY_INDEX, memory_dir

TOOL = os.path.join(TOOLS, "plant-control.py")
MEMCHECK = os.path.join(TOOLS, "pilot-memcheck.sh")
BUILTIN = "Zorvath keeps the amber key under the QX-7Z4R lantern"
ENGRAM = "The Quillfeather vault opens with code MN-4K9T"
ABSENT = "Harbor Nine's tide gauge reads ZP-3L8W"

READ = (
    "import os, sys\n"
    "home, q = sys.argv[1], sys.argv[2]\n"
    "os.environ['ENGRAM_HOME'] = home + '/.engram'; os.environ['HOME'] = home; os.environ['ENGRAM_NO_EMBEDDINGS'] = '1'\n"
    "sys.path.insert(0, home + '/.engram/marketplace/plugins/engram')\n"
    "import engram_query\n"
    "print(engram_query._query_impl(query=q, refresh_recall=False))\n")


def run_tool(home, ev, *extra, protected=None, builtin=BUILTIN, engram=ENGRAM, absent=ABSENT, marker=True):
    env = {"PATH": os.environ["PATH"]}
    if protected is not None:
        env["P1_PROTECTED"] = protected
    cmd = [sys.executable, TOOL, "--home", str(home), "--builtin-fact", builtin, "--engram-fact", engram,
           "--absent-fact", absent, "--evidence-dir", str(ev), *extra]
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def notes(arm_home):
    """The planted note file(s): everything in the memory folder except the index and pre-existing files."""
    return [p for p in memory_dir(arm_home).iterdir() if p.name not in ("MEMORY.md", "feedback_old.md")]


def go(arm_home, tmp_path, *extra, **kw):
    kw.setdefault("protected", "/nonexistent-protected-home")
    if not kw.pop("embeddings", False):
        extra = (*extra, "--no-embeddings")  # most cells are about the files, not the embedder (R2-3 has its own)
    return run_tool(arm_home, tmp_path / "evidence", *extra, **kw)


def engram_search(home, q):
    r = subprocess.run([sys.executable, "-c", READ, str(home), q], capture_output=True, text=True,
                       env={"PATH": os.environ["PATH"]})
    assert r.returncode == 0, r.stderr
    return json.dumps(json.loads(r.stdout)["results"])  # the result rows only: the output echoes the query


def anywhere(home, text, skip_dirs=()):
    """True if text (utf-8 bytes) is in any file under home (db and wal included), skipping the given dirs."""
    needle = text.encode()
    for root, dirs, files in os.walk(home):
        if any(os.path.abspath(root).startswith(os.path.abspath(s)) for s in skip_dirs):
            continue
        for f in files:
            if needle in open(os.path.join(root, f), "rb").read():
                return os.path.join(root, f)
    return None


def table_counts(home):
    import sqlite3
    c = sqlite3.connect(f"file:{home}/.engram/knowledge.db?mode=ro", uri=True)
    out = {}
    for (n,) in c.execute("select name from sqlite_master where type='table'"):
        try:
            out[n] = c.execute(f'select count(*) from "{n}"').fetchone()[0]
        except Exception:  # noqa: BLE001
            pass
    return out


# ---------------------------------------------------------------- refusals (exit 2, nothing written)
def untouched(arm_home):
    assert [p.name for p in memory_dir(arm_home).iterdir()] == ["MEMORY.md"]
    assert (memory_dir(arm_home) / "MEMORY.md").read_text() == MEMORY_INDEX
    assert table_counts(arm_home)["nodes"] == 1  # only the fixture's seed axiom


def test_refuses_without_the_disposable_marker(arm_home, tmp_path):
    (arm_home / ".disposable-copy").unlink()
    r = go(arm_home, tmp_path)
    assert r.returncode == 2 and ".disposable-copy" in r.stderr + r.stdout
    untouched(arm_home)


def test_refuses_a_home_under_p1_protected(arm_home, tmp_path):
    r = go(arm_home, tmp_path, protected=f"/somewhere/else:{tmp_path}")
    assert r.returncode == 2 and "P1_PROTECTED" in r.stderr + r.stdout
    untouched(arm_home)


def test_refuses_when_p1_protected_is_unset(arm_home, tmp_path):
    r = go(arm_home, tmp_path, protected=None)
    assert r.returncode == 2 and "P1_PROTECTED" in r.stderr + r.stdout
    untouched(arm_home)


def test_refuses_evidence_dir_inside_work(arm_home, tmp_path):
    ev = arm_home / "work" / "notes"; ev.mkdir()
    r = run_tool(arm_home, ev, protected="/nonexistent-protected-home")
    assert r.returncode == 2 and "work" in (r.stderr + r.stdout).lower()
    untouched(arm_home)
    assert list(ev.iterdir()) == []


def test_refuses_evidence_dir_reached_through_a_symlink_into_work(arm_home, tmp_path):
    (arm_home / "work" / "notes").mkdir()
    link = tmp_path / "linked"; link.symlink_to(arm_home / "work" / "notes")
    r = run_tool(arm_home, link, protected="/nonexistent-protected-home")
    assert r.returncode == 2 and "work" in (r.stderr + r.stdout).lower()
    untouched(arm_home)
    assert list((arm_home / "work" / "notes").iterdir()) == []


@pytest.mark.parametrize("which", ["builtin", "engram", "absent"])
def test_refuses_a_fact_shorter_than_six_characters(arm_home, tmp_path, which):
    r = go(arm_home, tmp_path, **{which: "QX-7Z"})  # 5 characters
    assert r.returncode == 2 and "6" in r.stderr + r.stdout
    untouched(arm_home)


def test_a_six_character_fact_is_accepted_by_the_length_rule(arm_home, tmp_path):
    r = go(arm_home, tmp_path, builtin="QX-7Z4")  # exactly 6: must not be refused for length
    assert r.returncode == 0, r.stderr + r.stdout


def test_refuses_facts_that_contain_one_another(arm_home, tmp_path):
    r = go(arm_home, tmp_path, builtin=ENGRAM + " twice")
    assert r.returncode == 2 and "contain" in (r.stderr + r.stdout).lower()
    untouched(arm_home)


def test_refuses_when_there_is_no_memory_folder(arm_home, tmp_path):
    shutil.rmtree(memory_dir(arm_home))
    r = go(arm_home, tmp_path)
    assert r.returncode == 2 and "memory" in (r.stderr + r.stdout).lower()
    assert not os.listdir(tmp_path / "evidence")  # nothing was written anywhere
    assert table_counts(arm_home)["nodes"] == 1


def test_refuses_when_the_plugin_cannot_be_imported(arm_home, tmp_path):
    shutil.rmtree(arm_home / ".engram" / "marketplace")
    r = go(arm_home, tmp_path)
    assert r.returncode == 2 and "plugin" in (r.stderr + r.stdout).lower()
    untouched(arm_home)


# ---------------------------------------------------------------- the plant, and what it must look like
def test_plant_passes_and_prints_the_checks(arm_home, tmp_path):
    r = go(arm_home, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    out = r.stdout
    for label in ("built-in file", "engram observation", "transcript leak", "cross-absence", "absent fact",
                  "row counts before", "row counts after"):
        assert label in out.lower(), (label, out)
    assert "FAIL" not in out


def test_builtin_file_is_where_pilot_memcheck_finds_it(arm_home, tmp_path):
    assert go(arm_home, tmp_path).returncode == 0
    files = notes(arm_home)
    assert len(files) == 1 and files[0].suffix == ".md"
    assert BUILTIN in files[0].read_text()
    m = subprocess.run(["bash", MEMCHECK, str(arm_home)], capture_output=True, text=True)
    assert m.returncode == 1  # memcheck exits 1 when any file exists in the memory folder
    assert "auto-memory start state: 2 file(s) in 1 folder(s)" in m.stdout  # the index and the planted note


def test_builtin_file_mirrors_an_existing_files_front_matter(arm_home, tmp_path):
    existing = memory_dir(arm_home) / "feedback_old.md"
    existing.write_text('---\nname: old-note\ndescription: "an old one"\nmetadata: \n  node_type: memory\n'
                        '  type: feedback\n  originSessionId: 7e0097a0-ed6d\n---\nOld body.\n')
    assert go(arm_home, tmp_path).returncode == 0
    new = notes(arm_home)
    assert len(new) == 1
    text = new[0].read_text()
    assert text.startswith("---\n") and "\nname: " in text and "\ndescription: " in text
    assert "node_type: memory" in text and "metadata:" in text
    assert "7e0097a0" not in text and "old-note" not in text and "an old one" not in text
    assert BUILTIN in text
    assert existing.read_text().endswith("Old body.\n")  # the existing file is untouched


def test_builtin_file_without_existing_files_still_has_front_matter(arm_home, tmp_path):
    assert go(arm_home, tmp_path).returncode == 0
    text = notes(arm_home)[0].read_text()
    assert text.startswith("---\nname: ") and "\n---\n" in text


def test_engram_fact_is_written_through_engrams_own_code(arm_home, tmp_path):
    before = table_counts(arm_home)
    assert go(arm_home, tmp_path).returncode == 0
    after = table_counts(arm_home)
    assert after["nodes"] == before["nodes"] + 2  # the observation and its evidence node
    found = engram_search(arm_home, ENGRAM)
    assert ENGRAM in found and "ob_" in found  # read back by a SEPARATE process through ENGRAM's own read code


def test_the_evidence_file_is_outside_the_work_folder_and_holds_the_fact(arm_home, tmp_path):
    assert go(arm_home, tmp_path).returncode == 0
    files = list((tmp_path / "evidence").iterdir())
    assert len(files) == 1 and ENGRAM in files[0].read_text()
    assert hashlib.sha256(files[0].read_bytes()).hexdigest() == files[0].stem  # content-addressed archive file
    assert not str(files[0].resolve()).startswith(str((arm_home / "work").resolve()))


def test_the_engram_fact_is_not_in_the_memory_folder_and_the_builtin_fact_not_in_the_store(arm_home, tmp_path):
    assert go(arm_home, tmp_path).returncode == 0
    assert anywhere(arm_home / ".claude", ENGRAM) is None
    assert anywhere(arm_home / ".engram", BUILTIN) is None
    assert BUILTIN not in engram_search(arm_home, BUILTIN)


def test_the_absent_fact_is_planted_nowhere(arm_home, tmp_path):
    assert go(arm_home, tmp_path).returncode == 0
    assert anywhere(arm_home, ABSENT) is None
    assert anywhere(tmp_path / "evidence", ABSENT) is None
    assert ABSENT not in engram_search(arm_home, ABSENT)


# ---------------------------------------------------------------- the checks must be able to fail
def transcript(arm_home):
    return arm_home / ".claude" / "projects" / "-synthetic-work" / "session-0001.jsonl"


@pytest.mark.parametrize("fact_name,fact", [("builtin", BUILTIN), ("engram", ENGRAM), ("absent", ABSENT)])
def test_transcript_leak_check_fails_when_a_fact_is_in_a_transcript(arm_home, tmp_path, fact_name, fact):
    with open(transcript(arm_home), "a") as f:
        f.write(json.dumps({"type": "assistant", "message": f"as I recall: {fact}"}) + "\n")
    r = go(arm_home, tmp_path)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "FAIL" in r.stdout and "transcript" in r.stdout.lower()


def test_transcript_leak_check_reads_every_jsonl_under_the_home(arm_home, tmp_path):
    other = arm_home / ".engram" / "sessions"; other.mkdir()
    (other / "x.jsonl").write_text(json.dumps({"m": ENGRAM.upper()}) + "\n")  # case differs: still a leak
    r = go(arm_home, tmp_path)
    assert r.returncode == 1 and "transcript" in r.stdout.lower()


def test_cross_absence_fails_when_the_engram_fact_is_in_the_memory_folder(arm_home, tmp_path):
    (memory_dir(arm_home) / "stray.md").write_text(f"---\nname: s\n---\n{ENGRAM}\n")
    r = go(arm_home, tmp_path)
    assert r.returncode == 1 and "FAIL" in r.stdout and "cross-absence" in r.stdout.lower()


def test_cross_absence_fails_when_the_builtin_fact_is_already_in_the_store(arm_home, tmp_path):
    first = go(arm_home, tmp_path, engram=BUILTIN, builtin="Some other invented sentence VX-1Q2W")
    assert first.returncode == 0, first.stdout + first.stderr  # plants BUILTIN's text as the engram fact
    shutil.rmtree(tmp_path / "evidence"); (tmp_path / "evidence").mkdir()
    for p in notes(arm_home):
        p.unlink()
    (memory_dir(arm_home) / "MEMORY.md").write_text(MEMORY_INDEX)
    r = go(arm_home, tmp_path)  # now BUILTIN is also in the store, where only the ENGRAM fact may be
    assert r.returncode == 1 and "FAIL" in r.stdout and "cross-absence" in r.stdout.lower()


def test_absent_fact_check_fails_when_the_absent_fact_is_in_a_channel(arm_home, tmp_path):
    (memory_dir(arm_home) / "stray.md").write_text(f"---\nname: s\n---\n{ABSENT}\n")
    r = go(arm_home, tmp_path)
    assert r.returncode == 1 and "absent fact" in r.stdout.lower() and "FAIL" in r.stdout


def test_row_count_check_fails_when_a_table_outside_the_allowed_set_changes(arm_home, tmp_path):
    r = go(arm_home, tmp_path, "--allowed-tables", "nodes")  # the observation write also adds edges, edit_history...
    assert r.returncode == 1 and "FAIL" in r.stdout and "row counts" in r.stdout.lower()


def test_row_counts_are_printed_per_table_before_and_after(arm_home, tmp_path):
    out = go(arm_home, tmp_path).stdout
    assert "nodes" in out and "edges" in out and "edit_history" in out
    before = out.lower().index("row counts before"); after = out.lower().index("row counts after")
    assert before < after and "nodes 1" in out[before:after] and "nodes 3" in out[after:]


def test_row_count_compare_unit():
    import importlib.util
    spec = importlib.util.spec_from_file_location("plant_control", TOOL)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    assert mod.changed_tables({"nodes": 1, "x": 2}, {"nodes": 3, "x": 2}, {"nodes"}) == []
    assert mod.changed_tables({"nodes": 1, "x": 2}, {"nodes": 3, "x": 3}, {"nodes"}) == ["x"]
    assert mod.changed_tables({"nodes": 1}, {"nodes": 1, "new_table": 0}, {"nodes"}) == ["new_table"]
    assert mod.changed_tables({"nodes": 1, "gone": 1}, {"nodes": 1}, {"nodes"}) == ["gone"]


# ================================================================ ROUND 2 (contract-first)
INDEX_LINE = re.compile(r"^- \[Reference note\]\((reference_note_[0-9a-f]{8}\.md)\) — a stored reference note$")


def index_lines(arm_home):
    return (memory_dir(arm_home) / "MEMORY.md").read_text().splitlines()


# ---- R2-2: the MEMORY.md index line
def test_one_neutral_index_line_is_appended_in_the_format_of_the_existing_lines(arm_home, tmp_path):
    assert go(arm_home, tmp_path).returncode == 0
    lines = index_lines(arm_home)
    assert lines[:2] == MEMORY_INDEX.splitlines()  # the existing lines are untouched
    assert len(lines) == 3
    m = INDEX_LINE.match(lines[2])
    assert m, lines[2]
    assert [p.name for p in notes(arm_home)] == [m.group(1)]  # the link names the planted file
    assert (memory_dir(arm_home) / "MEMORY.md").read_text().endswith("\n")


def test_the_index_line_mirrors_another_bullet_and_separator_style(arm_home, tmp_path):
    (memory_dir(arm_home) / "MEMORY.md").write_text("* [Alpha](a.md): first hook\n* [Beta](b.md): second hook")  # no final newline
    assert go(arm_home, tmp_path).returncode == 0
    lines = index_lines(arm_home)
    assert lines[:2] == ["* [Alpha](a.md): first hook", "* [Beta](b.md): second hook"]
    assert len(lines) == 3 and re.fullmatch(r"\* \[Reference note\]\(reference_note_[0-9a-f]{8}\.md\): a stored reference note", lines[2]), lines


def test_the_index_line_has_a_default_shape_when_the_index_is_empty(arm_home, tmp_path):
    (memory_dir(arm_home) / "MEMORY.md").write_text("")
    assert go(arm_home, tmp_path).returncode == 0
    assert [INDEX_LINE.fullmatch(l) is not None for l in index_lines(arm_home)] == [True]


def test_no_fact_text_is_in_the_index(arm_home, tmp_path):
    assert go(arm_home, tmp_path).returncode == 0
    idx = (memory_dir(arm_home) / "MEMORY.md").read_text().lower()
    for fact in (BUILTIN, ENGRAM, ABSENT):
        assert fact.lower() not in idx
    for token in ("QX-7Z4R", "MN-4K9T", "ZP-3L8W"):
        assert token.lower() not in idx


def test_the_absent_fact_gets_no_index_line_and_no_file(arm_home, tmp_path):
    assert go(arm_home, tmp_path).returncode == 0
    assert len(index_lines(arm_home)) == len(MEMORY_INDEX.splitlines()) + 1  # one line, for the built-in note only
    assert len(notes(arm_home)) == 1
    assert "harbor" not in (memory_dir(arm_home) / "MEMORY.md").read_text().lower()
    assert anywhere(arm_home / ".claude", ABSENT) is None


def test_refuses_when_there_is_no_memory_index(arm_home, tmp_path):
    (memory_dir(arm_home) / "MEMORY.md").unlink()
    r = go(arm_home, tmp_path)
    assert r.returncode == 2 and "MEMORY.md" in r.stderr + r.stdout
    assert list(memory_dir(arm_home).iterdir()) == []  # no note was invented either
    assert not os.listdir(tmp_path / "evidence") and table_counts(arm_home)["nodes"] == 1


@pytest.mark.parametrize("name", ["builtin", "engram", "absent"])
def test_the_index_check_fails_when_a_fact_is_in_the_index(arm_home, tmp_path, name):
    fact = {"builtin": BUILTIN, "engram": ENGRAM, "absent": ABSENT}[name]
    (memory_dir(arm_home) / "MEMORY.md").write_text(MEMORY_INDEX + f"- [Stray](s.md) — {fact}\n")
    r = go(arm_home, tmp_path)
    assert r.returncode == 1 and "FAIL" in r.stdout and "index" in r.stdout.lower()


# ---- the control question's content words must not be in the index line
@pytest.mark.parametrize("question,word", [
    ("What does the stored note say about the lantern?", "stored"),
    ("Which REFERENCE was kept?", "reference"),
    ("Where is the note?", "note"),
])
def test_refuses_when_the_neutral_line_would_contain_a_question_word(arm_home, tmp_path, question, word):
    r = go(arm_home, tmp_path, "--question", question)
    assert r.returncode == 2 and word in (r.stderr + r.stdout).lower() and "question" in (r.stderr + r.stdout).lower()
    untouched(arm_home)
    assert not os.listdir(tmp_path / "evidence") and table_counts(arm_home)["nodes"] == 1


def test_a_question_with_no_shared_content_word_is_accepted(arm_home, tmp_path):
    # 'what', 'the' are stopwords; 'is', 'of' and 'qx' are 3 characters or fewer; 'lantern' appears nowhere in the line
    r = go(arm_home, tmp_path, "--question", "What is the colour of the lantern at QX?")
    assert r.returncode == 0, r.stdout + r.stderr
    assert len(index_lines(arm_home)) == 3


def test_stopwords_and_short_words_do_not_count_as_question_words(arm_home, tmp_path):
    # 'a' (1 char) is in the line's own text, and 'for', 'and', 'what', 'the' are stopwords or short: none may refuse
    r = go(arm_home, tmp_path, "--question", "a for the and what")
    assert r.returncode == 0, r.stdout + r.stderr


def test_the_content_word_rule_unit():
    import importlib.util
    spec = importlib.util.spec_from_file_location("plant_control", TOOL)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    assert mod.content_words("What is the STORED note, QX-7Z4R's lantern?") == {"stored", "note", "lantern"}
    assert mod.content_words("a an the for and") == set()
    assert mod.content_words("abc xyz") == set()  # 3 characters or fewer


# ---- R2-3: embeddings on by default, through the arm's own embedding path (a stub embedder stands in for the model)
STUB = (
    "import os, runpy, sys\n"
    "home, ev, mode, tool = sys.argv[1:5]\n"
    "os.environ['ENGRAM_HOME'] = home + '/.engram'; os.environ['HOME'] = home\n"
    "os.environ['ENGRAM_EVIDENCE_ARCHIVE'] = os.path.realpath(ev)\n"
    "sys.path.insert(0, home + '/.engram/marketplace/plugins/engram')\n"
    "import engram_core\n"
    "class Stub:\n"
    "    _revive_cooldown = {}\n"
    "    def is_available(self): return mode != 'off'\n"
    "    def embed(self, text, model_name):\n"
    "        return None if mode == 'broken' else [((i * 7) % 13) / 13.0 for i in range(384)]\n"
    "    def revive(self, *a, **k): return None\n"
    "    def cosine_similarity(self, a, b): return 0.0\n"
    "engram_core._embedder = Stub()\n"
    "sys.argv = [tool] + sys.argv[5:]\n"
    "runpy.run_path(tool, run_name='__main__')\n")


def run_stub(arm_home, tmp_path, mode, *extra):
    """Run the tool with ENGRAM's embedder replaced by a stub (mode ok | broken | off), imported from the home's plugin."""
    cmd = [sys.executable, "-c", STUB, str(arm_home), str(tmp_path / "evidence"), mode, TOOL,
           "--home", str(arm_home), "--builtin-fact", BUILTIN, "--engram-fact", ENGRAM, "--absent-fact", ABSENT,
           "--evidence-dir", str(tmp_path / "evidence"), *extra]
    return subprocess.run(cmd, capture_output=True, text=True,
                          env={"PATH": os.environ["PATH"], "P1_PROTECTED": "/nonexistent-protected-home"})


def embedded(arm_home):
    import sqlite3
    c = sqlite3.connect(f"file:{arm_home}/.engram/knowledge.db?mode=ro", uri=True)
    try:
        return [r[0] for r in c.execute("select id from nodes where id like 'ob_%' and embedding is not null")]
    finally:
        c.close()


def test_embeddings_are_on_by_default_and_the_tool_says_so(arm_home, tmp_path):
    r = run_stub(arm_home, tmp_path, "ok")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "embeddings: ON" in r.stdout and "embeddings: OFF" not in r.stdout
    assert len(embedded(arm_home)) == 1  # the planted observation carries an embedding
    assert "FAIL" not in r.stdout and "embedded" in r.stdout.lower()


def test_no_embeddings_opts_out_and_the_tool_says_so(arm_home, tmp_path):
    r = go(arm_home, tmp_path)  # go() passes --no-embeddings
    assert r.returncode == 0, r.stdout + r.stderr
    assert "embeddings: OFF" in r.stdout and "embeddings: ON" not in r.stdout
    assert embedded(arm_home) == []


@pytest.mark.parametrize("mode", ["broken", "off"])
def test_exits_2_when_the_embedder_cannot_load_and_plants_nothing(arm_home, tmp_path, mode):
    r = run_stub(arm_home, tmp_path, mode)
    assert r.returncode == 2 and "embed" in (r.stderr + r.stdout).lower()
    untouched(arm_home)
    assert not os.listdir(tmp_path / "evidence") and table_counts(arm_home)["nodes"] == 1


def test_an_inherited_no_embeddings_variable_is_not_silently_honoured_by_default(arm_home, tmp_path):
    cmd = [sys.executable, TOOL, "--home", str(arm_home), "--builtin-fact", BUILTIN, "--engram-fact", ENGRAM,
           "--absent-fact", ABSENT, "--evidence-dir", str(tmp_path / "evidence")]
    r = subprocess.run(cmd, capture_output=True, text=True, env={
        "PATH": os.environ["PATH"], "P1_PROTECTED": "/nonexistent-protected-home", "ENGRAM_NO_EMBEDDINGS": "1"})
    assert r.returncode == 2 and "embed" in (r.stderr + r.stdout).lower()
    untouched(arm_home)


def test_the_real_embedding_model_path_when_it_can_load(arm_home, tmp_path):
    """Not a stub: the arm's own embedder. Skipped (not passed) when this host cannot load the model."""
    r = go(arm_home, tmp_path, embeddings=True)
    if r.returncode == 2 and "embed" in (r.stderr + r.stdout).lower():
        pytest.skip("the embedding model cannot load on this host: " + (r.stderr + r.stdout).strip()[-200:])
    assert r.returncode == 0, r.stdout + r.stderr
    assert "embeddings: ON" in r.stdout and len(embedded(arm_home)) == 1


# ---- R2-4: the store reads must not change recall counters
def recall_counts(arm_home):
    import sqlite3
    c = sqlite3.connect(f"file:{arm_home}/.engram/knowledge.db?mode=ro", uri=True)
    try:
        return dict(c.execute("select id, recall_count from nodes"))
    finally:
        c.close()


def test_the_checks_read_the_store_without_changing_recall_counters(arm_home, tmp_path):
    """The read-back and cross-absence reads find the planted observation: with refresh_recall=True each hit would
    bump its recall_count. The counter must be exactly what the write left (0), for every node."""
    before = recall_counts(arm_home)
    assert go(arm_home, tmp_path).returncode == 0
    after = recall_counts(arm_home)
    obs = [k for k in after if k.startswith("ob_")]
    assert len(obs) == 1
    assert all(v in (0, None) for v in after.values()), after
    assert {k: v for k, v in after.items() if k in before} == before
