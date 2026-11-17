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


def dummy(tmp_path):
    """A real, unrelated directory standing in for a preserved home (R3-2: P1_PROTECTED entries must exist)."""
    d = tmp_path / "preserved-dummy"; d.mkdir(exist_ok=True)
    return str(d)


def go(arm_home, tmp_path, *extra, **kw):
    kw.setdefault("protected", dummy(tmp_path))
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
    r = go(arm_home, tmp_path, protected=f"{dummy(tmp_path)}:{tmp_path}")
    assert r.returncode == 2 and "P1_PROTECTED" in r.stderr + r.stdout
    untouched(arm_home)


def test_refuses_when_p1_protected_is_unset(arm_home, tmp_path):
    r = go(arm_home, tmp_path, protected=None)
    assert r.returncode == 2 and "P1_PROTECTED" in r.stderr + r.stdout
    untouched(arm_home)


def test_refuses_evidence_dir_inside_work(arm_home, tmp_path):
    ev = arm_home / "work" / "notes"; ev.mkdir()
    r = run_tool(arm_home, ev, protected=dummy(tmp_path))
    assert r.returncode == 2 and "work" in (r.stderr + r.stdout).lower()
    untouched(arm_home)
    assert list(ev.iterdir()) == []


def test_refuses_evidence_dir_reached_through_a_symlink_into_work(arm_home, tmp_path):
    (arm_home / "work" / "notes").mkdir()
    link = tmp_path / "linked"; link.symlink_to(arm_home / "work" / "notes")
    r = run_tool(arm_home, link, protected=dummy(tmp_path))
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
                          env={"PATH": os.environ["PATH"], "P1_PROTECTED": dummy(tmp_path)})


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
        "PATH": os.environ["PATH"], "P1_PROTECTED": dummy(tmp_path), "ENGRAM_NO_EMBEDDINGS": "1"})
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



# ================================================================ ROUND 3 (contract-first)
def snap(root):
    """{path: content hash | ('link', target) | 'dir'} for everything under root (symlinks are recorded, not followed)."""
    out = {}
    for r, ds, fs in os.walk(root):
        for n in ds + fs:
            q = os.path.join(r, n)
            if os.path.islink(q):
                out[q] = ("link", os.readlink(q))
            elif os.path.isfile(q):
                out[q] = hashlib.sha256(open(q, "rb").read()).hexdigest()
            else:
                out[q] = "dir"
    return out


def plant(home, ev, protected):
    return run_tool(home, ev, "--no-embeddings", protected=protected)


def said(r):
    return r.stderr + r.stdout


# ---- R3-2: every P1_PROTECTED entry must exist
def test_refuses_when_a_protected_entry_does_not_exist(arm_home, tmp_path):
    r = go(arm_home, tmp_path, protected=f"{dummy(tmp_path)}:/nonexistent-protected-home")
    assert r.returncode == 2 and "does not exist" in said(r) and "/nonexistent-protected-home" in said(r), said(r)
    untouched(arm_home)
    assert not os.listdir(tmp_path / "evidence")


def test_refuses_when_the_only_protected_entry_does_not_exist(arm_home, tmp_path):
    r = go(arm_home, tmp_path, protected="/nonexistent-protected-home")
    assert r.returncode == 2 and "does not exist" in said(r), said(r)
    untouched(arm_home)


# ---- R3-1: a protected path INSIDE the home (the under(p, home) branch)
def test_refuses_when_a_protected_path_is_inside_the_home(arm_home, tmp_path):
    inside = arm_home / "preserved-inside"; inside.mkdir()
    r = go(arm_home, tmp_path, protected=str(inside))
    assert r.returncode == 2 and "P1_PROTECTED" in said(r), said(r)
    untouched(arm_home)
    assert not os.listdir(tmp_path / "evidence")


# ---- R3-1: a symlink that carries a write target into a protected dir
def test_refuses_a_memory_dir_that_is_a_symlink_into_a_protected_dir(arm_home, tmp_path):
    prot = tmp_path / "preserved"; (prot / "memory").mkdir(parents=True)
    (prot / "memory" / "MEMORY.md").write_text(MEMORY_INDEX)
    m = memory_dir(arm_home); shutil.rmtree(m); m.symlink_to(prot / "memory")
    before = snap(prot)
    r = plant(arm_home, tmp_path / "evidence", str(prot))
    assert r.returncode == 2 and "P1_PROTECTED" in said(r) and "memory" in said(r), said(r)
    assert snap(prot) == before
    assert not os.listdir(tmp_path / "evidence") and table_counts(arm_home)["nodes"] == 1


def test_refuses_an_engram_dir_that_is_a_symlink_into_a_protected_dir(arm_home, tmp_path):
    prot = tmp_path / "preserved"; prot.mkdir()
    shutil.move(str(arm_home / ".engram"), str(prot / ".engram"))
    (arm_home / ".engram").symlink_to(prot / ".engram")
    before = snap(prot)
    r = plant(arm_home, tmp_path / "evidence", str(prot))
    assert r.returncode == 2 and "P1_PROTECTED" in said(r), said(r)
    assert snap(prot) == before
    assert not os.listdir(tmp_path / "evidence")


@pytest.mark.parametrize("ev_kind", ["inside", "link", "ancestor"])
def test_refuses_an_evidence_dir_under_or_above_a_protected_dir(arm_home, tmp_path, ev_kind):
    root = tmp_path / "evroot"; prot = root / "preserved"; prot.mkdir(parents=True)
    ev = {"inside": prot / "evidence", "link": tmp_path / "evlink", "ancestor": root}[ev_kind]
    if ev_kind == "link":
        ev.symlink_to(prot)
    before = snap(root)
    r = plant(arm_home, ev, str(prot))
    assert r.returncode == 2 and "P1_PROTECTED" in said(r) and "evidence" in said(r).lower(), said(r)
    assert snap(root) == before  # nothing created under, or beside, the protected dir
    untouched(arm_home)


# ---- R3-1: every write target must resolve UNDER the home (a symlink out of it, to a dir that is not protected)
def _relocate(path, outside):
    """Move `path` (a file or dir) to `outside` and leave an absolute symlink behind."""
    shutil.move(str(path), str(outside))
    os.symlink(str(outside), str(path))


@pytest.mark.parametrize("target", ["memdir", "index", "note", "engramdir", "db", "wal", "shm", "plugin"])
def test_refuses_a_write_target_that_resolves_outside_the_home(arm_home, tmp_path, target):
    out = tmp_path / "outside"; out.mkdir()
    eng = arm_home / ".engram"
    note = hashlib.sha256(BUILTIN.encode()).hexdigest()[:8]
    if target == "memdir":
        _relocate(memory_dir(arm_home), out / "memory")
    elif target == "index":
        _relocate(memory_dir(arm_home) / "MEMORY.md", out / "MEMORY.md")
    elif target == "note":
        os.symlink(str(out / "note.md"), str(memory_dir(arm_home) / f"reference_note_{note}.md"))  # dangling
    elif target == "engramdir":
        _relocate(eng, out / ".engram")
    elif target == "db":
        _relocate(eng / "knowledge.db", out / "knowledge.db")
    elif target in ("wal", "shm"):
        (out / target).write_text("")
        os.symlink(str(out / target), str(eng / f"knowledge.db-{target}"))
    elif target == "plugin":
        _relocate(eng / "marketplace" / "plugins" / "engram", out / "engram")
    before = snap(out)
    r = plant(arm_home, tmp_path / "evidence", dummy(tmp_path))
    assert r.returncode == 2 and "outside the home" in said(r), (target, said(r))
    assert snap(out) == before, target  # nothing was written through the link
    assert not os.listdir(tmp_path / "evidence")


# ---- R3-1: a hard link is the same inode as another copy: refuse
def test_refuses_a_hardlinked_copy_of_a_protected_home(arm_home, tmp_path):
    disposable = tmp_path / "disposable"
    subprocess.run(["cp", "-al", str(arm_home), str(disposable)], check=True)  # cp -al: every file hard-linked
    before = snap(arm_home)
    r = plant(disposable, tmp_path / "evidence", str(arm_home))
    assert r.returncode == 2 and "st_nlink" in said(r), said(r)
    assert snap(arm_home) == before
    assert not os.listdir(tmp_path / "evidence")


@pytest.mark.parametrize("which", ["index", "memfile", "db", "wal", "shm"])
def test_refuses_when_one_file_has_a_second_hard_link(arm_home, tmp_path, which):
    eng = arm_home / ".engram"
    if which == "index":
        victim = memory_dir(arm_home) / "MEMORY.md"
    elif which == "memfile":
        victim = memory_dir(arm_home) / "stray.md"; victim.write_text("---\nname: s\n---\nbody\n")
    elif which == "db":
        victim = eng / "knowledge.db"
    else:
        victim = eng / f"knowledge.db-{which}"; victim.write_text("")
    os.link(victim, tmp_path / "second-name")
    idx = (memory_dir(arm_home) / "MEMORY.md").read_text()
    r = plant(arm_home, tmp_path / "evidence", dummy(tmp_path))
    assert r.returncode == 2 and "st_nlink" in said(r) and victim.name in said(r), said(r)
    assert (memory_dir(arm_home) / "MEMORY.md").read_text() == idx
    assert not [p for p in memory_dir(arm_home).iterdir() if p.name.startswith("reference_note_")]
    assert not os.listdir(tmp_path / "evidence") and table_counts(arm_home)["nodes"] == 1


# ---- R3-1: the real layout is ACCEPTED: .engram/tools and .engram/hooks are absolute symlinks into the home's own plugin dir
def test_a_home_whose_engram_tools_is_an_absolute_symlink_into_itself_is_accepted(arm_home, tmp_path):
    plug = arm_home / ".engram" / "marketplace" / "plugins" / "engram"
    assert (plug / "tools").is_dir()
    for name in ("tools", "hooks"):
        if (plug / name).is_dir():
            os.symlink(str(plug / name), str(arm_home / ".engram" / name))  # ABSOLUTE, pointing inside the home
    assert os.path.isabs(os.readlink(arm_home / ".engram" / "tools"))
    r = go(arm_home, tmp_path)
    assert r.returncode == 0, said(r)
    assert len(notes(arm_home)) == 1


# ---- R3-7: the ImportError branch, and the 'imported from outside the arm home' check
def test_refuses_when_a_plugin_module_exists_but_cannot_be_imported(arm_home, tmp_path):
    (arm_home / ".engram" / "marketplace" / "plugins" / "engram" / "engram_query.py").write_text("def broken(:\n")
    r = go(arm_home, tmp_path)
    assert r.returncode == 2 and "cannot be imported" in said(r), said(r)
    untouched(arm_home)
    assert not os.listdir(tmp_path / "evidence")


PREIMPORT = (
    "import os, runpy, sys\n"
    "outside, scratch, tool = sys.argv[1:4]\n"
    "os.environ['ENGRAM_HOME'] = scratch; os.environ['ENGRAM_NO_DB_GUARDS'] = '1'; os.environ['ENGRAM_NO_EMBEDDINGS'] = '1'\n"
    "sys.path.insert(0, outside)\n"
    "import engram_core, engram_observation, engram_query\n"  # cached BEFORE the tool inserts the arm home's plugin
    "sys.argv = [tool] + sys.argv[4:]\n"
    "runpy.run_path(tool, run_name='__main__')\n")


def test_refuses_when_the_engram_modules_come_from_outside_the_arm_home(arm_home, tmp_path):
    outside = os.environ["P1_ENGRAM_PLUGIN"]
    scratch = tmp_path / "scratch-engram"; scratch.mkdir()
    cmd = [sys.executable, "-c", PREIMPORT, outside, str(scratch), TOOL,
           "--home", str(arm_home), "--builtin-fact", BUILTIN, "--engram-fact", ENGRAM, "--absent-fact", ABSENT,
           "--evidence-dir", str(tmp_path / "evidence"), "--no-embeddings"]
    r = subprocess.run(cmd, capture_output=True, text=True,
                       env={"PATH": os.environ["PATH"], "P1_PROTECTED": dummy(tmp_path)})
    assert r.returncode == 2 and "not from the arm home's plugin" in said(r), said(r)
    untouched(arm_home)



# ================================================================ ROUND 4 (contract-first)
# R4-1: ENGRAM's own in-process write also writes outside the listed targets (telemetry, anchoring_advisory.jsonl,
# the setup lockdir, plugin __pycache__). A generic scan of the whole home runs before any write or import.
def protected_dir(tmp_path):
    prot = tmp_path / "preserved"; prot.mkdir()
    (prot / "keep.jsonl").write_text("preserved line\n")
    (prot / "telemetry").mkdir(); (prot / "telemetry" / "t.jsonl").write_text("t\n")
    return prot


def refused_and_untouched(arm_home, tmp_path, prot, expect="P1_PROTECTED"):
    before = snap(prot)
    r = plant(arm_home, tmp_path / "evidence", str(prot))
    assert r.returncode == 2 and expect in said(r), said(r)
    assert snap(prot) == before  # the protected dir is byte-for-byte unchanged
    assert not os.listdir(tmp_path / "evidence")
    assert table_counts(arm_home)["nodes"] == 1
    return r


def test_refuses_a_telemetry_dir_symlinked_into_a_protected_dir(arm_home, tmp_path):
    prot = protected_dir(tmp_path)
    (arm_home / ".engram" / "telemetry").symlink_to(prot / "telemetry")
    refused_and_untouched(arm_home, tmp_path, prot)


def test_refuses_a_plugin_pycache_symlinked_into_a_protected_dir(arm_home, tmp_path):
    prot = protected_dir(tmp_path); (prot / "pc").mkdir()
    plug = arm_home / ".engram" / "marketplace" / "plugins" / "engram"
    shutil.rmtree(plug / "__pycache__", ignore_errors=True)  # the fixture's seeding run left one behind
    (plug / "__pycache__").symlink_to(prot / "pc")
    refused_and_untouched(arm_home, tmp_path, prot)


def test_refuses_anchoring_advisory_hard_linked_to_a_protected_file(arm_home, tmp_path):
    prot = protected_dir(tmp_path)
    os.link(prot / "keep.jsonl", arm_home / ".engram" / "anchoring_advisory.jsonl")
    refused_and_untouched(arm_home, tmp_path, prot, expect="same inode")


def test_refuses_a_symlink_deep_in_an_unrelated_subdir_pointing_into_a_protected_dir(arm_home, tmp_path):
    prot = protected_dir(tmp_path)
    deep = arm_home / "work" / "a" / "b" / "c"; deep.mkdir(parents=True)
    (deep / "innocent-looking").symlink_to(prot / "telemetry")
    refused_and_untouched(arm_home, tmp_path, prot)


def test_refuses_a_file_symlink_into_a_protected_dir(arm_home, tmp_path):
    prot = protected_dir(tmp_path)
    (arm_home / ".engram" / "note.jsonl").symlink_to(prot / "keep.jsonl")  # a FILE symlink
    refused_and_untouched(arm_home, tmp_path, prot)


def test_refuses_a_symlink_to_an_ancestor_of_a_protected_dir(arm_home, tmp_path):
    prot = protected_dir(tmp_path)
    (arm_home / "work" / "up").symlink_to(tmp_path)  # tmp_path is an ANCESTOR of the protected dir
    refused_and_untouched(arm_home, tmp_path, prot)


def test_a_symlink_out_of_the_home_to_an_unprotected_dir_is_allowed(arm_home, tmp_path):
    """NEGATIVE: venv and model caches are links out of the home to dirs that are not protected."""
    prot = protected_dir(tmp_path)
    cache = tmp_path / "hf-cache"; cache.mkdir(); (cache / "model.bin").write_text("weights")
    (arm_home / ".engram" / "hf-cache").symlink_to(cache)
    (arm_home / "work" / "venv-link").symlink_to(cache)
    before = snap(cache)
    r = plant(arm_home, tmp_path / "evidence", str(prot))
    assert r.returncode == 0, said(r)
    assert snap(cache) == before
    assert len(notes(arm_home)) == 1


def test_a_hard_link_to_a_protected_file_nested_under_the_engram_dir_is_refused(arm_home, tmp_path):
    """A nested file nobody listed (here a telemetry file) that is the same inode as a protected file."""
    prot = protected_dir(tmp_path)
    tel = arm_home / ".engram" / "telemetry"; tel.mkdir()
    os.link(prot / "telemetry" / "t.jsonl", tel / "t.jsonl")
    refused_and_untouched(arm_home, tmp_path, prot, expect="same inode")


def test_bytecode_is_not_written_into_the_plugin_dir(arm_home, tmp_path):
    plug = arm_home / ".engram" / "marketplace" / "plugins" / "engram"
    for d in list(plug.rglob("__pycache__")):  # the fixture's seeding run left some behind
        shutil.rmtree(d)
    assert not list(plug.rglob("*.pyc"))
    r = go(arm_home, tmp_path)
    assert r.returncode == 0, said(r)
    assert not list(plug.rglob("*.pyc")) and not list(plug.rglob("__pycache__"))


# ---- R4-2 (a): a P1_PROTECTED entry that is itself an alias (symlink) path; the memory dir links into the real dir
def test_refuses_when_the_protected_entry_is_an_alias_symlink_path(arm_home, tmp_path):
    real = tmp_path / "real-preserved"; (real / "memory").mkdir(parents=True)
    (real / "memory" / "MEMORY.md").write_text(MEMORY_INDEX)
    alias = tmp_path / "alias-preserved"; alias.symlink_to(real)
    m = memory_dir(arm_home); shutil.rmtree(m); m.symlink_to(real / "memory")
    before = snap(real)
    r = plant(arm_home, tmp_path / "evidence", str(alias))
    assert r.returncode == 2 and "P1_PROTECTED" in said(r), said(r)
    assert snap(real) == before


# ---- R4-2 (b): the content-addressed evidence file pre-planted as a symlink into a protected dir
def test_refuses_an_evidence_file_pre_planted_as_a_symlink_into_a_protected_dir(arm_home, tmp_path):
    prot = protected_dir(tmp_path)
    ev = tmp_path / "evidence"
    epath = ev / (hashlib.sha256((ENGRAM + "\n").encode()).hexdigest() + ".txt")
    epath.symlink_to(prot / "keep.jsonl")
    before = snap(prot)
    r = plant(arm_home, ev, str(prot))
    assert r.returncode == 2 and "evidence file" in said(r), said(r)
    assert snap(prot) == before
    assert (prot / "keep.jsonl").read_text() == "preserved line\n"
    untouched(arm_home)


def test_the_scan_does_not_follow_a_link_out_of_the_home_into_a_foreign_tree(arm_home, tmp_path):
    """The scan is of the home's own tree: a model cache outside it that itself holds a link to a protected dir is not
    walked (nothing the tool or ENGRAM writes lives there). Kills a followlinks=True walk."""
    prot = protected_dir(tmp_path)
    cache = tmp_path / "hf-cache"; cache.mkdir()
    (cache / "stale-link").symlink_to(prot / "telemetry")
    (arm_home / ".engram" / "hf-cache").symlink_to(cache)
    before = snap(prot)
    r = plant(arm_home, tmp_path / "evidence", str(prot))
    assert r.returncode == 0, said(r)
    assert snap(prot) == before


# ================================================================ ROUND 5 (contract-first)
# The class: a write under HOME that reaches a protected INODE or directory. The hazard is tested exactly: the set of
# (st_dev, st_ino) of every regular file under every P1_PROTECTED entry, against every entry of the HOME walk and every
# symlink's resolved target. Ways a write can get there, and the cell for each:
#   1. a hard link to a protected file, anywhere under HOME: test_refuses_a_hard_link_to_a_protected_file_anywhere_...
#   2. a symlink to a protected file or dir: R4 cells, test_refuses_a_dangling_symlink_into_a_protected_dir
#   3. a symlink to an in-home hard link of a protected file: ..._round4_blocker_layout, ..._nested_in_home_dir,
#      ..._chain_of_symlinks_...
#   4. a symlinked dir leading to (2) or (3): R4 dir cells, test_refuses_a_dir_symlink_to_an_in_home_dir_...
#   5. a symlink to a file OUTSIDE the home that is a hard link of a protected file: ..._outside_file_...
#   6. a protected entry that is itself a file: test_a_protected_entry_that_is_a_file_...
#   7. a directory the walk cannot read (a hole in the scan): test_refuses_when_a_directory_under_the_home_cannot_...
def hard_link_in_home(arm_home, prot, where):
    dest = arm_home / where
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.link(prot / "keep.jsonl", dest)
    return dest


def test_refuses_the_round4_blocker_layout(arm_home, tmp_path):
    """Reproduced in the round-4 review: a hard link of a protected file under work/, and a symlink under .engram to
    it. ENGRAM's write followed the symlink and grew the protected file."""
    prot = protected_dir(tmp_path)
    adv = hard_link_in_home(arm_home, prot, "work/adv.jsonl")
    (arm_home / ".engram" / "anchoring_advisory.jsonl").symlink_to(adv)  # ABSOLUTE, resolves inside the home
    assert os.path.isabs(os.readlink(arm_home / ".engram" / "anchoring_advisory.jsonl"))
    refused_and_untouched(arm_home, tmp_path, prot, expect="same inode")


@pytest.mark.parametrize("where", ["work/adv.jsonl", ".claude/projects/-synthetic-work/stray.jsonl", "top-level.jsonl",
                                   "work/a/b/deep.jsonl", ".engram/telemetry/t.jsonl"])
def test_refuses_a_hard_link_to_a_protected_file_anywhere_under_the_home(arm_home, tmp_path, where):
    prot = protected_dir(tmp_path)
    hard_link_in_home(arm_home, prot, where)
    refused_and_untouched(arm_home, tmp_path, prot, expect="same inode")


def test_refuses_a_symlink_to_a_hard_linked_file_in_a_nested_in_home_dir(arm_home, tmp_path):
    prot = protected_dir(tmp_path)
    hl = hard_link_in_home(arm_home, prot, "work/x/y/z/hl.jsonl")
    (arm_home / ".engram" / "telemetry").mkdir()
    (arm_home / ".engram" / "telemetry" / "e.jsonl").symlink_to(hl)
    refused_and_untouched(arm_home, tmp_path, prot, expect="same inode")


def test_refuses_a_chain_of_symlinks_that_ends_at_an_in_home_hard_link(arm_home, tmp_path):
    prot = protected_dir(tmp_path)
    hl = hard_link_in_home(arm_home, prot, "work/hl.jsonl")
    (arm_home / "work" / "hop1").symlink_to(hl)
    (arm_home / ".engram" / "hop2.jsonl").symlink_to(arm_home / "work" / "hop1")
    refused_and_untouched(arm_home, tmp_path, prot, expect="same inode")


def test_refuses_a_dir_symlink_to_an_in_home_dir_holding_a_hard_link(arm_home, tmp_path):
    prot = protected_dir(tmp_path)
    hard_link_in_home(arm_home, prot, "work/realdir/hl.jsonl")
    (arm_home / ".engram" / "telemetry").symlink_to(arm_home / "work" / "realdir")  # a dir symlink, inside the home
    refused_and_untouched(arm_home, tmp_path, prot, expect="same inode")


def test_refuses_a_symlink_to_an_outside_file_that_is_a_hard_link_of_a_protected_file(arm_home, tmp_path):
    """The target is outside the home and outside every protected tree, so the realpath test is silent; only the inode
    of the resolved file gives it away."""
    prot = protected_dir(tmp_path)
    outside = tmp_path / "unprotected"; outside.mkdir()
    os.link(prot / "keep.jsonl", outside / "alias.jsonl")
    (arm_home / ".engram" / "anchoring_advisory.jsonl").symlink_to(outside / "alias.jsonl")
    refused_and_untouched(arm_home, tmp_path, prot, expect="same inode")


def test_refuses_a_dangling_symlink_into_a_protected_dir(arm_home, tmp_path):
    prot = protected_dir(tmp_path)
    (arm_home / ".engram" / "not-yet.jsonl").symlink_to(prot / "telemetry" / "will-be-created.jsonl")
    refused_and_untouched(arm_home, tmp_path, prot)


def test_a_protected_entry_that_is_a_file_has_its_inode_protected(arm_home, tmp_path):
    f = tmp_path / "preserved-file.jsonl"; f.write_text("preserved\n")
    os.link(f, arm_home / "work" / "alias.jsonl")
    r = plant(arm_home, tmp_path / "evidence", str(f))
    assert r.returncode == 2 and "same inode" in said(r), said(r)
    assert f.read_text() == "preserved\n"


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads any directory")
def test_refuses_when_a_directory_under_the_home_cannot_be_read(arm_home, tmp_path):
    """An unreadable directory is a part of the home the scan did not see: refuse rather than skip it silently."""
    prot = protected_dir(tmp_path)
    d = arm_home / "work" / "sealed"; d.mkdir(); (d / "f").write_text("x")
    d.chmod(0)
    try:
        refused_and_untouched(arm_home, tmp_path, prot, expect="cannot be read")
    finally:
        d.chmod(0o700)


# ---- NEGATIVE cells: the exact test must not refuse what is harmless
def test_an_in_home_file_with_a_second_link_outside_every_protected_tree_is_allowed(arm_home, tmp_path):
    prot = protected_dir(tmp_path)
    other = tmp_path / "unprotected"; other.mkdir()
    for where in ("work/shared.txt", ".engram/telemetry/t2.jsonl"):
        (arm_home / where).parent.mkdir(parents=True, exist_ok=True)
        (arm_home / where).write_text("shared\n")
        os.link(arm_home / where, other / where.replace("/", "_"))
    (arm_home / ".engram" / "via-link.jsonl").symlink_to(arm_home / "work" / "shared.txt")  # a link to such a file
    before = snap(prot)
    r = plant(arm_home, tmp_path / "evidence", str(prot))
    assert r.returncode == 0, said(r)
    assert snap(prot) == before
    assert len(notes(arm_home)) == 1


def test_a_link_out_to_an_unprotected_cache_dir_holding_a_file_is_allowed(arm_home, tmp_path):
    prot = protected_dir(tmp_path)
    cache = tmp_path / "model-cache"; cache.mkdir(); (cache / "w.bin").write_text("weights")
    (arm_home / ".engram" / "cache").symlink_to(cache)
    (arm_home / "work" / "cache-file").symlink_to(cache / "w.bin")
    before = snap(cache)
    r = plant(arm_home, tmp_path / "evidence", str(prot))
    assert r.returncode == 0, said(r)
    assert snap(cache) == before


# ---- unit cell on the scan itself (the (st_dev, st_ino) key)
def load_tool():
    import importlib.util
    spec = importlib.util.spec_from_file_location("plant_control_under_test", TOOL)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def test_the_inode_key_includes_the_device(tmp_path, monkeypatch):
    """Same st_ino on a DIFFERENT st_dev is a different file. Two filesystems are not available to a cell, so the
    device number of one file is faked (stat and lstat of that one path); with the real numbers the same layout is
    refused, so the cell proves the device is part of the key."""
    m = load_tool()
    prot = tmp_path / "prot"; prot.mkdir(); (prot / "k").write_text("k")
    home = tmp_path / "home"; home.mkdir()
    os.link(prot / "k", home / "alias")
    keys = m.protected_inodes([str(prot)])
    with pytest.raises(SystemExit) as e:
        m.refuse_unsafe_home_scan(str(home), [str(prot)], keys)
    assert e.value.code == 2  # the real layout: refused
    real_stat, real_lstat = os.stat, os.lstat

    def fake(fn):
        def inner(path, *a, **k):
            st = fn(path, *a, **k)
            if os.fspath(path) == str(home / "alias"):
                f = list(st); f[2] = st.st_dev + 1  # st_dev
                return os.stat_result(f)
            return st
        return inner
    monkeypatch.setattr(os, "stat", fake(real_stat)); monkeypatch.setattr(os, "lstat", fake(real_lstat))
    m.refuse_unsafe_home_scan(str(home), [str(prot)], keys)  # same ino, other dev: allowed (no SystemExit)
