"""Part C cells: plant-control.py on a synthetic, disposable arm home. Contract-first: written before the tool.

Needs P1_ENGRAM_PLUGIN (an ENGRAM plugin tree that holds engram_observation.py) and a python that can run ENGRAM
(the interpreter running pytest). No student model, no real preserved home."""
import hashlib, json, os, shutil, subprocess, sys
import pytest
from conftest import TOOLS, memory_dir

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


def go(arm_home, tmp_path, *extra, **kw):
    kw.setdefault("protected", "/nonexistent-protected-home")
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
    assert list(memory_dir(arm_home).iterdir()) == []
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
    assert list(memory_dir(arm_home).iterdir()) == []


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
    files = list(memory_dir(arm_home).iterdir())
    assert len(files) == 1 and files[0].suffix == ".md"
    assert BUILTIN in files[0].read_text()
    m = subprocess.run(["bash", MEMCHECK, str(arm_home)], capture_output=True, text=True)
    assert m.returncode == 1  # memcheck exits 1 when any file exists in the memory folder
    assert "auto-memory start state: 1 file(s) in 1 folder(s)" in m.stdout


def test_builtin_file_mirrors_an_existing_files_front_matter(arm_home, tmp_path):
    existing = memory_dir(arm_home) / "feedback_old.md"
    existing.write_text('---\nname: old-note\ndescription: "an old one"\nmetadata: \n  node_type: memory\n'
                        '  type: feedback\n  originSessionId: 7e0097a0-ed6d\n---\nOld body.\n')
    assert go(arm_home, tmp_path).returncode == 0
    new = [p for p in memory_dir(arm_home).iterdir() if p.name != "feedback_old.md"]
    assert len(new) == 1
    text = new[0].read_text()
    assert text.startswith("---\n") and "\nname: " in text and "\ndescription: " in text
    assert "node_type: memory" in text and "metadata:" in text
    assert "7e0097a0" not in text and "old-note" not in text and "an old one" not in text
    assert BUILTIN in text
    assert existing.read_text().endswith("Old body.\n")  # the existing file is untouched


def test_builtin_file_without_existing_files_still_has_front_matter(arm_home, tmp_path):
    assert go(arm_home, tmp_path).returncode == 0
    text = next(memory_dir(arm_home).iterdir()).read_text()
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
    for p in memory_dir(arm_home).iterdir():
        p.unlink()
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
