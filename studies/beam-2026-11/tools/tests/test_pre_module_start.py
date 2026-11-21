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
from conftest import TOOLS, needs_linux_wrapper
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


TOOL_NAME = "mark-pre-module-start"
# files that may name the command: the command itself, and p1-session.py only in its comments/help (never a call)
MAY_NAME_IT = {"mark-pre-module-start.py", "p1-session.py"}


def mentions_outside_allowed(texts):
    """{file: text} -> the files that name the command at all and are neither markdown nor allow-listed. A name anywhere
    in a file (split over two lines, built by concatenation of its two halves is NOT seen) is a failure, because a
    launcher that runs the command has to spell the name somewhere."""
    return sorted(f for f, t in texts.items() if TOOL_NAME in t and f not in MAY_NAME_IT and not f.endswith(".md"))


def tracked_tool_texts():
    r = subprocess.run(["git", "-C", TOOLS, "ls-files", "-z", "--", "."], capture_output=True, check=True)
    out = {}
    for rel in r.stdout.decode().split("\0"):
        if not rel or rel.split("/")[0] == "tests":
            continue
        try:
            out[rel] = open(os.path.join(TOOLS, rel), encoding="utf-8").read()
        except (OSError, UnicodeDecodeError):
            pass
    return out


def test_t7_no_tracked_tool_file_names_the_command_but_the_command_and_p1_session():
    texts = tracked_tool_texts()
    assert "mark-pre-module-start.py" in texts and "p1-session.py" in texts     # the population is not empty
    assert mentions_outside_allowed(texts) == []


def test_t7_the_scan_sees_a_call_split_over_two_lines_and_p1_session_never_runs_it():
    split = 'MARKER = os.path.join(HERE, "mark-pre-module-start.py")\nsubprocess.run([sys.executable, MARKER])\n'
    assert mentions_outside_allowed({"launcher.py": split, "README.md": split, "mark-pre-module-start.py": split}) == ["launcher.py"]
# The exact mentions of the command's name that p1-session.py may carry: its comment on PRE_MODULE_VERDICT and the --pilot flag's
# help string. Any other mention, a call split over two lines included, fails.
P1_ALLOWED_MENTIONS = [
    'PRE_MODULE_VERDICT = "none (pre-module state, never wrapped)"   # the line mark-pre-module-start.py writes',
    'help="PILOTS ONLY: allow --end-state to be a pre-module state marked by mark-pre-module-start.py")',
]


def p1_mentions(text):
    return [l.strip() for l in text.splitlines() if TOOL_NAME in l]


def test_t7_p1_session_names_the_command_in_exactly_the_two_allowed_places():
    assert p1_mentions(tracked_tool_texts()["p1-session.py"]) == [m.strip() for m in P1_ALLOWED_MENTIONS]


def test_t7_a_third_mention_in_p1_session_including_a_split_call_fails_the_cell():
    real = tracked_tool_texts()["p1-session.py"]
    split = real + '\nM = os.path.join(HERE, "mark-pre-module-start.py")\nsubprocess.run([sys.executable, M])\n'
    assert p1_mentions(split) != [m.strip() for m in P1_ALLOWED_MENTIONS]


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


# ------------------------------------------------------------------------------------------- 3. round 2 (reviewer's round 1)
def rewrite_record(s, fn):
    lines = open(record_of(s)).read().splitlines()
    open(record_of(s), "w").write("\n".join(fn(lines)) + "\n")


def test_r1_a_pre_module_line_beside_another_verdict_line_is_refused_even_with_the_flag(w):
    s = marked_copy(w, "mixed")
    rewrite_record(s, lambda ls: ls + ["sandbox verdict: not-flagged"])     # no flagged line: only the mixed-record rule can refuse
    cr_refusal(w, over=over_for(s), extra=(FLAG,), expect="beside another verdict line", P1_PROTECTED=prot(w, s))


@pytest.mark.parametrize("second", ["right", "wrong"])
def test_r1_exactly_one_state_sha256_line_is_required(w, second):
    s = marked_copy(w, "twohash")
    right = [l for l in open(record_of(s)).read().splitlines() if l.startswith("state_sha256=")][0]
    extra = right if second == "right" else "state_sha256=" + "0" * 64
    rewrite_record(s, lambda ls: ls + [extra])
    cr_refusal(w, over=over_for(s), extra=(FLAG,), expect="exactly one `state_sha256=` line", P1_PROTECTED=prot(w, s))


def test_r1_an_ordinary_not_flagged_run_carries_no_pilot_line(w, ollama):
    r = cr_run(w, ollama_url=ollama["url"])
    assert r.returncode == 0, (r.stdout, r.stderr)
    text = "\n".join(setup_lines(w))
    assert "pilot, pre-module start" not in text and "pre-module start state_sha256" not in text


def test_r1_the_flag_alone_does_not_label_a_run_a_pilot(w, ollama):
    """The flag is an allowance, not a label: a state that was never marked (it has an ordinary not-flagged record) runs with
    the flag set and setup.txt must not say pilot."""
    r = cr_run(w, extra=(FLAG,), ollama_url=ollama["url"])
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "pilot, pre-module start" not in "\n".join(setup_lines(w))


FLAG_LINE = "pilot flag passed: --pilot-pre-module-start"


@needs_linux_wrapper
def test_f2_the_flag_on_an_ordinary_wrapped_state_is_recorded_in_setup_txt(w, ollama):
    """Round 5: whenever the flag is passed, setup.txt carries one line saying so, whether or not the state is pre-module
    (the state here has an ordinary not-flagged record), so a later ingest can refuse a scored run on the flag itself."""
    r = cr_run(w, extra=(FLAG,), ollama_url=ollama["url"])
    assert r.returncode == 0, (r.stdout, r.stderr)
    lines = setup_lines(w)
    assert lines.count(FLAG_LINE) == 1
    assert "pilot, pre-module start" not in lines      # the flag line is not the pre-module label


@needs_linux_wrapper
def test_f2_without_the_flag_setup_txt_carries_no_flag_line(w, ollama):
    r = cr_run(w, ollama_url=ollama["url"])
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "--pilot-pre-module-start" not in "\n".join(setup_lines(w))


def test_r2_what_the_hash_binds_is_the_store_only_and_the_wording_says_so(w):
    s = marked_copy(w, "bound")
    # a memory file edit does NOT change the knowledge.db content hash: the check does not see it (the limit, pinned)
    mem = next(os.path.join(dp, f) for dp, _, fs in os.walk(str(s / ".claude")) for f in fs if f.endswith("a.md"))
    open(mem, "a").write("edited after marking\n")
    assert P1S._end_state_verdict(str(s), True)[0] is None
    # and the refusal for a store change says what it hashed
    c = sqlite3.connect(str(s / ".engram" / "knowledge.db"))
    c.execute("insert into nodes values ('late', 'changed')"); c.commit(); c.close()
    why = P1S._end_state_verdict(str(s), True)[0]
    assert "knowledge.db" in why and "store" in why and "not covered" in why


def test_r3_the_flag_is_refused_in_answering_mode_and_an_abbreviation_of_it_is_not_accepted(w):
    r = cr_run(w, over={"--continue-reading": None, "--start": None, "--through": None, "--per-round": None,
                        "--save-end-state": None, "--expect-store-sha256": None, "--question-file": str(w.comps)},
               extra=(FLAG,))
    assert r.returncode == 2 and "only valid with --continue-reading" in r.stdout + r.stderr
    s = marked_copy(w, "abbrev")
    r = cr_run(w, over=over_for(s), extra=("--pilot-pre",), P1_PROTECTED=prot(w, s))
    out = r.stdout + r.stderr
    # argparse's own refusal, not the pre-module reader's: the abbreviation never reached the allowance
    assert r.returncode == 2 and "unrecognized arguments: --pilot-pre" in out and "REFUSE" not in out, (r.returncode, out)
    assert not os.path.lexists(str(w.saved))


def test_r4_the_record_is_not_world_writable_whatever_the_umask(w):
    s = copy_end_state(w, "pre", None)
    r = subprocess.run([sys.executable, MARK, str(s), "--by", "x"], capture_output=True, text=True, preexec_fn=lambda: os.umask(0))
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert (os.stat(record_of(s)).st_mode & 0o777) == 0o644


def test_r5_the_readme_names_no_internal_crossing_number_and_states_the_scored_launchers_must():
    text = open(os.path.join(TOOLS, "README.md"), encoding="utf-8").read()
    assert "crossing" not in text.lower().split("a pre-module end state is a pilot start only")[1]
    assert "knowledge.db" in text.split("A pre-module end state is a PILOT start only")[1]
    assert "must refuse a run whose" in text and "pilot, pre-module start" in text.split("must refuse a run whose")[1][:200]
