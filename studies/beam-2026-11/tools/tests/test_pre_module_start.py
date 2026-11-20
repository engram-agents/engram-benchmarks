"""Cells for the pre-module pilot start: tools/mark-pre-module-start.py (the one command that writes the record) and the
pilot-only switch in p1-session.py's continue-reading reader (`--pilot-pre-module-start`). Contract-first: written before
either existed. Synthetic end states only (built under each cell's tmp dir by the shared fixtures): no real preserved
state, no student model, no real model server.

Contract: the command computes the state's store content hash with the EXISTING helper, prints it, and writes
`<STATE>.verdict.txt` by exclusive create with exactly four lines; it refuses (exit 2, named, nothing written) an existing
record, a state that already has a verdict line, a state that is not a directory, an empty --by. The default reader (what a
scored launcher calls) refuses the pre-module line; continue-reading accepts it only with the flag, re-hashes the state
against the record, and writes `pilot, pre-module start` into setup.txt. A state with no line at all is refused everywhere."""
import os, re, sqlite3, subprocess, sys
import pytest
from conftest import TOOLS
from test_p1_session import P1S
from test_p1_continue_reading import (w, ollama, cr_run, cr_refusal, setup_lines, store_sha, copy_end_state)  # noqa: F401  (fixtures)

MARK = os.path.join(TOOLS, "mark-pre-module-start.py")
NONE_LINE = "sandbox verdict: none (pre-module state, never wrapped)"
FLAG = "--pilot-pre-module-start"
ISO = re.compile(r"^marked_at=\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")


def mark(state, by="the-study-lead", extra=()):
    return subprocess.run([sys.executable, MARK, str(state), "--by", by, *extra], capture_output=True, text=True)


def record_of(state):
    return str(state) + ".verdict.txt"


def marked_copy(w, name="pre"):
    """A copy of the synthetic end state with NO record, then marked by the command."""
    s = copy_end_state(w, name, None)
    r = mark(s)
    assert r.returncode == 0, (r.stdout, r.stderr)
    return s


def over_for(state, **more):
    o = {"--end-state": str(state), "--expect-store-sha256": store_sha(state)}
    o.update(more)
    return o


def prot(w, s):
    return f"{w.pres}:{w.pres2}:{s}"


# ------------------------------------------------------------------------------------------- 1. the command
def test_t1_the_command_writes_exactly_the_four_lines_and_prints_the_hash(w):
    s = copy_end_state(w, "pre", None)
    r = mark(s, by="Lei")
    assert r.returncode == 0, (r.stdout, r.stderr)
    raw = open(record_of(s)).read()
    lines = raw.splitlines()
    want = P1S.protected_store_hash(str(s))[0]            # the EXISTING end-state hash helper
    assert len(lines) == 4 and raw.endswith("\n")
    assert lines[0] == NONE_LINE
    assert lines[1] == f"state_sha256={want}"
    assert lines[2] == "marked_by=Lei"
    assert ISO.match(lines[3]), lines[3]
    assert want in r.stdout


@pytest.mark.parametrize("planted", ["foreign bytes, no verdict line\n", "sandbox verdict: not-flagged\n"])
def test_t2_an_existing_record_is_refused_and_survives_byte_identical(w, planted):
    s = copy_end_state(w, "pre", planted)
    r = mark(s)
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert "already exists" in r.stdout + r.stderr
    assert open(record_of(s)).read() == planted


def test_t3_a_state_that_already_has_a_verdict_line_is_refused_and_nothing_is_written(w):
    """The verdict line sits in the record beside the REAL path; the command is called through a symlink, so the record
    beside the path as given does not exist: only the check for 'any verdict line' (not the exists check) can refuse."""
    s = copy_end_state(w, "real-state", "sandbox verdict: not-flagged\n")
    link = w.root / "via-link"
    os.symlink(str(s), str(link))
    r = mark(link)
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert "verdict line" in r.stdout + r.stderr
    assert not os.path.lexists(record_of(link))
    assert open(record_of(s)).read() == "sandbox verdict: not-flagged\n"


@pytest.mark.parametrize("kind", ["missing", "file"])
def test_t4_a_state_that_is_not_an_existing_directory_is_refused(w, kind):
    p = w.root / "nostate"
    if kind == "file":
        p.write_text("not a directory")
    r = mark(p)
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert "not an existing directory" in r.stdout + r.stderr
    assert not os.path.lexists(record_of(p))


@pytest.mark.parametrize("by", ["", "   ", "a\nb"])
def test_t5_an_empty_or_multiline_by_is_refused_and_nothing_is_written(w, by):
    s = copy_end_state(w, "pre", None)
    r = mark(s, by=by)
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert "--by" in r.stdout + r.stderr
    assert not os.path.lexists(record_of(s))


def test_t6_a_directory_with_no_store_is_refused_and_nothing_is_written(tmp_path):
    d = tmp_path / "empty-dir"; d.mkdir()
    r = mark(d)
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert not os.path.lexists(record_of(d))


def test_t7_nothing_calls_the_command_automatically():
    """No tool file (outside tests/, the command itself, markdown) mentions it on a line that also runs something."""
    runners = re.compile(r"subprocess|Popen|os\.system|exec|bash |python")
    for dp, dn, fn in os.walk(TOOLS):
        dn[:] = [d for d in dn if d not in ("tests", "__pycache__")]
        for f in fn:
            if f == "mark-pre-module-start.py" or f.endswith(".md"):
                continue
            try:
                text = open(os.path.join(dp, f), encoding="utf-8").read()
            except (OSError, UnicodeDecodeError):
                continue
            bad = [l for l in text.splitlines() if "mark-pre-module-start" in l and runners.search(l)]
            assert not bad, (f, bad)


# ------------------------------------------------------------------------------------------- 2. the pilot-only switch
def test_s1_the_default_reader_refuses_a_marked_state_by_name(w):
    s = marked_copy(w)
    why = P1S.end_state_verdict_problem(str(s))           # what a scored launcher calls: no allowance
    assert why and "pre-module" in why


def test_s2_p1_session_without_the_flag_refuses_the_line(w):
    s = marked_copy(w)
    cr_refusal(w, over=over_for(s), expect="pre-module", P1_PROTECTED=prot(w, s))


def test_s3_with_the_flag_it_starts_and_setup_txt_carries_the_pilot_line_and_the_hash(w, ollama):
    s = marked_copy(w)
    r = cr_run(w, over=over_for(s, **{"--save-end-state": str(w.root / "saved-next")}), extra=(FLAG,),
               ollama_url=ollama["url"], P1_PROTECTED=prot(w, s))
    assert r.returncode == 0, (r.stdout, r.stderr)
    lines = setup_lines(w)
    assert "pilot, pre-module start" in lines
    assert f"pre-module start state_sha256: {store_sha(s)}" in lines


def test_s4_a_state_changed_after_marking_is_refused_even_with_the_flag(w):
    s = marked_copy(w)
    c = sqlite3.connect(str(s / ".engram" / "knowledge.db"))
    c.execute("insert into nodes values ('late', 'changed after marking')"); c.commit(); c.close()
    # --expect-store-sha256 is the NEW hash: only the record's state_sha256 can refuse this
    cr_refusal(w, over=over_for(s), extra=(FLAG,), expect="changed after", P1_PROTECTED=prot(w, s))


@pytest.mark.parametrize("with_flag", [False, True])
def test_s5_a_state_with_no_line_at_all_is_still_refused(w, with_flag):
    s = copy_end_state(w, "noline", None)
    cr_refusal(w, over=over_for(s), extra=(FLAG,) if with_flag else (), expect="no verdict line", P1_PROTECTED=prot(w, s))


def test_s6_the_flag_without_continue_reading_is_refused(w):
    r = cr_run(w, over={"--continue-reading": None, "--start": None, "--through": None, "--per-round": None,
                        "--save-end-state": None, "--expect-store-sha256": None, "--question-file": str(w.comps)},
               extra=(FLAG,))
    assert r.returncode == 2 and FLAG in r.stdout + r.stderr, (r.returncode, r.stdout, r.stderr)


def test_s7_the_flag_does_not_weaken_the_other_refusals(w):
    flagged = copy_end_state(w, "fl", "sandbox verdict: flagged: endpoint unreachable, nothing reached it\n")
    cr_refusal(w, over=over_for(flagged), extra=(FLAG,), expect="FLAGGED verdict", P1_PROTECTED=prot(w, flagged))
    s = marked_copy(w, "nohash")
    text = open(record_of(s)).read().splitlines()
    open(record_of(s), "w").write("\n".join(l for l in text if not l.startswith("state_sha256=")) + "\n")
    cr_refusal(w, over=over_for(s), extra=(FLAG,), expect="state_sha256", P1_PROTECTED=prot(w, s))


def test_s8_the_scored_door_does_not_know_the_flag():
    """The launch module (what a scored launcher calls) carries neither the flag nor the allowance."""
    text = open(os.path.join(TOOLS, "sandbox_launch.py"), encoding="utf-8").read().lower()
    assert "pre-module" not in text and "pre_module" not in text and "pilot-pre" not in text
