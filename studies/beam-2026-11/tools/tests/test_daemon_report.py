"""Cells for the recall daemon's report channel (PR 22 fold, the security seat's ruling): the box's supervisor reports to a PIPE, and
a reader OUTSIDE the box writes SANDBOX_LOG. Contract-first: written before the implementation; the contract, P1-P9, is the spec's.

  P1  nothing inside the box holds a descriptor on SANDBOX_LOG: the wrapper makes a pipe, only its write end goes into the box, the
      read end stays with the reader (a small process the wrapper starts, `sandbox-forward.py report-reader`).
  P2  the reader copies to the log ONLY lines that fully match one of a FIXED table of anchored shapes (REPORT_SHAPES, one constant),
      bounded: a longest line (REPORT_MAX_LINE) and a most lines per launch (REPORT_MAX_LINES).
  P3  every dropped line makes ONE marker line of the reader's own, never the dropped content.
  P4  the verdict cannot be fed from the pipe: a verdict-shaped line written from INSIDE the box does not reach the log.
  P5  the supervisor stays non-dumpable (defence in depth); no descriptor on the log is passed to the box any more.
  P6  the supervisor's write never stalls it: non-blocking; a full pipe is a counted drop; the stop path still emits daemon-stop.
  P7  the reader writes under its own prefix (`daemon-report`) with a sequence number and a time; its drop marker carries the same
      prefix and a count; the launch module's parser reads that form and no other.
  P8  a duplicated or out-of-order daemon line is RECORDED, not deduplicated.
  P9  a failed write in the supervisor is counted and surfaces, never swallowed.
Synthetic fixtures only: the stub daemon of test_daemon_prestart.py; no real daemon, no real binary, no model.
"""
import importlib.util, json, os, re, subprocess, sys, threading, time
import pytest
import test_student_sandbox as TSS
from conftest import TOOLS
from test_daemon_prestart import (STUB_DAEMON, build_engram_slot, client_cmd, dcfg, fields, log_line,  # noqa: F401  (dcfg: a fixture)
                                  log_lines, run_daemon, wait_report_closed)
from test_sandbox_launch import SL                                                                    # noqa: F401


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


FW = _load("sandbox_forward_under_test_report", TSS.FWD)
CLOCK = lambda: 1700000000.5        # a fixed clock: two feeds of the same bytes must give byte-identical logs
RE_RLINE = re.compile(r"daemon-report seq=([0-9]+) time=([0-9]+\.[0-9]{6}) (.*)")


def shape(i):
    return FW.REPORT_SHAPES[i]


def sample(sh, override=None):
    event, flds = sh
    override = override or {}
    return " ".join([event] + ["%s=%s" % (k, override.get(k, FW.REPORT_VALUES[v][1])) for k, v in flds])


def reader_for(tmp_path, name="r.log"):
    log = str(tmp_path / name)
    return FW.ReportReader(log, clock=CLOCK), log


def rlines(log):
    return open(log).read().splitlines() if os.path.exists(log) else []


def lines_with(log, word):
    return [l for l in rlines(log) if re.match(r"daemon-report seq=[0-9]+ time=[0-9.]+ " + word, l)]


# ============================================================================================ P2: the fixed table of shapes
PINNED_PATTERNS = [
    r"daemon-ready time=[0-9]{1,12}\.[0-9]{3} pid=[0-9]{1,10} time_to_ready_s=[0-9]{1,6}\.[0-9]{3} rpt_dropped=[0-9]{1,6}",
    r"daemon-not-ready time=[0-9]{1,12}\.[0-9]{3} reason=(?:spawn-failed|timeout|exited-early|signalled) waited_s=[0-9]{1,6}\.[0-9]{3} rpt_dropped=[0-9]{1,6}",
    r"daemon-stop time=[0-9]{1,12}\.[0-9]{3} pid=[0-9]{1,10} outcome=(?:already-gone|term|killed) waited_s=[0-9]{1,6}\.[0-9]{3} rpt_dropped=[0-9]{1,6}",
    r"daemon-fault time=[0-9]{1,12}\.[0-9]{3} kind=sigkill pid=[0-9]{1,10} after_s=[0-9]{1,6}(?:\.[0-9]{1,6})? rpt_dropped=[0-9]{1,6}",
    r"daemon-fault time=[0-9]{1,12}\.[0-9]{3} kind=files-left pid=[0-9]{1,10} files=(?:recall-daemon\.pid,recall-daemon\.sock|recall-daemon\.pid|recall-daemon\.sock) rpt_dropped=[0-9]{1,6}",
]


def test_the_table_of_shapes_is_one_constant_and_is_pinned_here():
    assert len(FW.REPORT_SHAPES) == len(PINNED_PATTERNS) == 5
    assert [FW.report_pattern(sh) for sh in FW.REPORT_SHAPES] == PINNED_PATTERNS, "the grammar table moved: change it HERE on purpose"
    assert FW.REPORT_MAX_LINE == 256 and FW.REPORT_MAX_LINES == 64 and FW.REPORT_MAX_MARKERS == 64
    src = open(TSS.FWD).read()
    assert src.count("REPORT_SHAPES = ") == 1, "the table is defined in one place"


@pytest.mark.parametrize("i", range(5))
def test_each_shape_accepts_its_own_generated_sample(i, tmp_path):
    r, log = reader_for(tmp_path)
    line = sample(shape(i))
    assert len(line) <= FW.REPORT_MAX_LINE
    assert FW.report_shape_ok(line.encode())
    r.push(line.encode() + b"\n")
    assert rlines(log) == ["daemon-report seq=1 time=1700000000.500000 line=" + line]
    assert r.accepted == 1 and r.dropped == 0


def near_misses(sh):
    """Every near-miss of one shape, generated from the table's own fields (never hand-listed per shape)."""
    event, flds = sh
    parts = [(k, FW.REPORT_VALUES[v][1]) for k, v in flds]

    def mk(ev, ps, sep=" "):
        return sep.join([ev] + ["%s=%s" % kv for kv in ps])

    out = {}
    for i, (k, v) in enumerate(parts):
        out["drop-" + k] = mk(event, parts[:i] + parts[i + 1:])
        out["dup-" + k] = mk(event, parts[:i + 1] + parts[i:])
        for tag, bad in (("x", v + "x"), ("empty", ""), ("neg", "-" + v), ("space", v + " "), ("upper", v.upper() + "X")):
            out["value-%s-%s" % (tag, k)] = mk(event, parts[:i] + [(k, bad)] + parts[i + 1:])
        out["key-upper-" + k] = mk(event, parts[:i] + [(k.upper(), v)] + parts[i + 1:])
        out["key-x-" + k] = mk(event, parts[:i] + [(k + "x", v)] + parts[i + 1:])
    for i in range(len(parts) - 1):
        out["swap-%d" % i] = mk(event, parts[:i] + [parts[i + 1], parts[i]] + parts[i + 2:])
    good = mk(event, parts)
    out.update({"extra-field": mk(event, parts + [("extra", "1")]), "trailing-space": good + " ", "leading-space": " " + good,
                "tab-separated": mk(event, parts, "\t"), "double-space": mk(event, parts, "  "), "cr-ending": good + "\r",
                "nul-inside": good.replace(event, event[:3] + "\0" + event[3:]), "upper-event": event.upper(),
                "event-prefix": "x" + good, "event-suffix": event + "x" + good[len(event):], "no-fields": event,
                "empty": "", "only-spaces": "   ", "two-lines-in-one": good + " " + good,
                "unicode-digit": good.replace("=1", "=١", 1) if "=1" in good else good + "١",
                "newline-inside": good.replace(" ", "\n", 1)})
    return {k: v for k, v in out.items() if v != good}


@pytest.mark.parametrize("i", range(5))
def test_every_near_miss_of_a_shape_is_refused_whole_and_marked(i, tmp_path):
    sh = shape(i)
    good = sample(sh)
    misses = near_misses(sh)
    assert len(misses) > 30, "the generator made too few near-misses to mean anything: %d" % len(misses)
    for name, line in misses.items():
        assert not FW.report_shape_ok(line.encode()), "near-miss %r still matches the table: %r" % (name, line)
    assert FW.report_shape_ok(good.encode())                                   # the control: the generator's own good line passes
    r, log = reader_for(tmp_path)
    kept = [(n, l) for n, l in misses.items() if "\n" not in l]                  # a newline inside is two lines: its own cell below
    for n, l in kept:
        r.push(l.encode() + b"\n")
    assert lines_with(log, "line=") == [] and r.accepted == 0
    assert len(lines_with(log, "dropped ")) == len(kept)


def test_a_newline_inside_a_good_line_makes_two_lines_that_are_each_judged(tmp_path):
    r, log = reader_for(tmp_path)
    good = sample(shape(0))
    cut = good.replace(" ", "\n", 1)
    r.push(cut.encode() + b"\n")
    assert r.accepted == 0 and r.dropped == 2 and len(lines_with(log, "dropped ")) == 2


# ----- the bounds
def test_the_longest_line_and_the_most_lines_are_named_bounds_and_excess_is_dropped(tmp_path):
    r, log = reader_for(tmp_path)
    r.push(b"x" * FW.REPORT_MAX_LINE + b"\n")                  # exactly the bound: too long for no shape, so a SHAPE drop
    r.push(b"x" * (FW.REPORT_MAX_LINE + 1) + b"\n")            # one past: a LENGTH drop
    got = [fields(l) for l in lines_with(log, "dropped ")]
    assert [g["reason"] for g in got] == ["shape", "length"]
    assert [g["bytes"] for g in got] == [str(FW.REPORT_MAX_LINE), str(FW.REPORT_MAX_LINE + 1)]
    good = sample(shape(0)).encode() + b"\n"
    r2, log2 = reader_for(tmp_path, "r2.log")
    for _ in range(FW.REPORT_MAX_LINES + 3):
        r2.push(good)
    assert r2.accepted == FW.REPORT_MAX_LINES
    got = [fields(l) for l in lines_with(log2, "dropped ")]
    assert [g["reason"] for g in got] == ["count"] * 3 and [g["bytes"] for g in got] == [str(len(good) - 1)] * 3
    assert len(lines_with(log2, "line=")) == FW.REPORT_MAX_LINES


def test_the_reader_is_chunk_independent_and_holds_no_more_than_the_longest_line(tmp_path):
    stream = b"".join([sample(shape(0)).encode() + b"\n", b"junk\n", b"y" * 5000 + b"\n", sample(shape(2)).encode() + b"\n",
                       sample(shape(1)).encode()])          # the last line is unterminated
    outs = []
    for n, size in enumerate((len(stream), 1, 7, 255, 256, 257, 4096)):
        r, log = reader_for(tmp_path, "c%d.log" % n)
        for i in range(0, len(stream), size):
            r.push(stream[i:i + size])
            assert len(r.buf) <= FW.REPORT_MAX_LINE + 1, "the reader buffered more than the longest line"
        r.finish()
        outs.append(rlines(log))
    assert all(o == outs[0] for o in outs), outs
    assert outs[0][-1].startswith("daemon-report seq=") and " closed " in outs[0][-1]
    assert sum(1 for l in outs[0] if " dropped " in l) == 3        # junk, the 5000-byte line, the unterminated tail


# ============================================================================================ P3: one marker per drop, never the content
def test_every_dropped_line_makes_exactly_one_marker_and_never_its_content(tmp_path):
    r, log = reader_for(tmp_path)
    secret = "SECRET-TOKEN-0451"
    for bad in (secret, "fwd-first-request", "daemon-ready " + secret, "z" * 300 + secret):
        r.push(bad.encode() + b"\n")
    marks = lines_with(log, "dropped ")
    assert len(marks) == 4 and r.dropped == 4
    f = [fields(m) for m in marks]
    assert [x["reason"] for x in f] == ["shape", "shape", "shape", "length"]
    assert [x["count"] for x in f] == ["1", "2", "3", "4"]
    assert [x["bytes"] for x in f] == [str(len(secret)), "17", str(len("daemon-ready " + secret)), str(300 + len(secret))]
    text = open(log).read()
    assert secret not in text and "fwd-first-request" not in text, "dropped content reached the log"


def test_the_markers_are_bounded_and_the_closing_line_still_accounts_for_every_drop(tmp_path):
    r, log = reader_for(tmp_path)
    for i in range(200):
        r.push(b"junk\n")
    r.finish()
    marks = lines_with(log, "dropped ")
    assert len(marks) == FW.REPORT_MAX_MARKERS
    close = fields(lines_with(log, "closed ")[0])
    assert close["dropped"] == "200" and close["markers_suppressed"] == str(200 - FW.REPORT_MAX_MARKERS) and close["accepted"] == "0"


# ============================================================================================ P7: prefix, sequence, time; P8: recorded
def test_the_readers_lines_carry_prefix_sequence_and_time_in_one_unbroken_sequence(tmp_path):
    r, log = reader_for(tmp_path)
    r.push(sample(shape(0)).encode() + b"\n")
    r.push(b"junk\n")
    r.push(sample(shape(2)).encode() + b"\n")
    r.finish()
    got = [RE_RLINE.fullmatch(l) for l in rlines(log)]
    assert all(got), rlines(log)
    assert [int(m.group(1)) for m in got] == [1, 2, 3, 4]               # one counter over accepted lines, markers and the close
    assert {m.group(2) for m in got} == {"1700000000.500000"}
    assert got[1].group(3).startswith("dropped reason=shape bytes=4 count=1")


def test_a_duplicated_and_a_reordered_daemon_line_are_both_recorded_not_deduplicated(tmp_path):
    r, log = reader_for(tmp_path)
    ready, stop = sample(shape(0)), sample(shape(2))
    for line in (stop, ready, ready):                                   # out of order, then a duplicate
        r.push(line.encode() + b"\n")
    assert [RE_RLINE.fullmatch(l).group(3) for l in rlines(log)] == ["line=" + stop, "line=" + ready, "line=" + ready]
    ev = SL.read_daemon_events(log)
    assert [k for k, _ in ev] == ["daemon-stop", "daemon-ready", "daemon-ready"], ev


# ----- the launch module's parser moves with the form
def _log(tmp_path, text, name="m.log"):
    p = tmp_path / name
    p.write_text(text)
    return str(p)


def test_the_module_reads_the_readers_form_and_no_other(tmp_path):
    ready = sample(shape(0))
    good = "daemon-report seq=1 time=1700000000.500000 line=" + ready + "\n"
    assert SL.read_daemon_events(_log(tmp_path, good))[0][0] == "daemon-ready"
    assert SL.read_daemon_events(_log(tmp_path, good))[0][1]["pid"] == FW.REPORT_VALUES["pid"][1]
    for n, bad in enumerate((ready + "\n",                                                                    # the old, unprefixed form
                             "daemon-report time=1700000000.500000 line=" + ready + "\n",                       # no sequence
                             "daemon-report seq=1 line=" + ready + "\n",                                        # no time
                             "daemon-report seq=x time=1700000000.500000 line=" + ready + "\n",
                             "daemon-report seq=1 time=1700000000.5 line=" + ready + "\n",
                             "  daemon-report seq=1 time=1700000000.500000 line=" + ready + "\n",
                             "daemon-report seq=1 time=1700000000.500000 line=fwd-first-request\n")):
        assert SL.read_daemon_events(_log(tmp_path, bad, "b%d.log" % n)) == [], "accepted: %r" % bad
    res = SL.LaunchResult(0)
    why = SL.daemon_verdict("engram", {"daemon": "engram"}, SL.read_daemon_events(_log(tmp_path, ready + "\n", "old.log")), res)
    assert why and "daemon-ready" in why and "neither" in why, why        # an old-form ready line is no ready line at all


def test_a_drop_marker_or_a_supervisor_side_loss_is_a_named_stop_in_the_verdict(tmp_path):
    res = SL.LaunchResult(0)
    ready = ("daemon-ready", {"time_to_ready_s": "1.5", "pid": "9", "rpt_dropped": "0"})
    stop = ("daemon-stop", {"outcome": "term", "pid": "9", "rpt_dropped": "0"})
    assert SL.daemon_verdict("engram", {"daemon": "engram"}, [ready, stop], res) is None
    mark = SL.read_daemon_events(_log(tmp_path, "daemon-report seq=2 time=1700000000.500000 dropped reason=shape bytes=4 count=1\n"))
    assert mark and mark[0][0] == "daemon-report-dropped"
    why = SL.daemon_verdict("engram", {"daemon": "engram"}, [ready, stop] + mark, SL.LaunchResult(0))
    assert why and "dropped" in why and "report" in why, why
    lost = ("daemon-stop", {"outcome": "term", "pid": "9", "rpt_dropped": "2"})
    why = SL.daemon_verdict("engram", {"daemon": "engram"}, [ready, lost], SL.LaunchResult(0))
    assert why and "2" in why and "could not write" in why, why


# ============================================================================================ P6, P9: the supervisor's side
DRIVER = r'''
import argparse, importlib.util, json, os, sys
spec = importlib.util.spec_from_file_location("fw", sys.argv[1])
fw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fw)
a = argparse.Namespace(**json.loads(sys.argv[2]))
sys.exit(fw.run_supervised(a, dict(os.environ)))
'''


def sup_args(tmp_path, wfd, *, mode="ok", delay=0.3, term_s=3.0, cmd=("/bin/sh", "-c", "exit 7")):
    home = str(tmp_path / ".engram")
    os.makedirs(home)
    script = os.path.join(home, "stub-daemon.py")
    open(script, "w").write(STUB_DAEMON)
    open(os.path.join(home, "stub-config"), "w").write("mode=%s delay=%s\n" % (mode, delay))
    line = 'env ENGRAM_HOME="%s" /usr/bin/python3 "%s" "%s" >> "%s/surface-daemon.log" 2>&1 < /dev/null &' % (home, script, home, home)
    return {"report_fd": wfd, "daemon_line": line, "daemon_sock": home + "/recall-daemon.sock", "daemon_pidfile": home + "/recall-daemon.pid",
            "daemon_ready_s": 10.0, "daemon_term_s": term_s, "cmd": list(cmd), "test_report_leak": False}, home


def start_sup(tmp_path, wfd, **kw):
    args, home = sup_args(tmp_path, wfd, **kw)
    drv = tmp_path / "driver.py"
    drv.write_text(DRIVER)
    p = subprocess.Popen(["/usr/bin/python3", "-I", str(drv), TSS.FWD, json.dumps(args)], pass_fds=[wfd],
                         stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return p, home


def fill(wfd):
    """Fill the pipe through a SEPARATE open file description of its write end: O_NONBLOCK is a property of the description, so setting
    it on `wfd` itself would make the supervisor's end non-blocking from here and hide a supervisor that forgot to (mutant M4)."""
    side = os.open("/proc/self/fd/%d" % wfd, os.O_WRONLY | os.O_NONBLOCK)
    n = 0
    try:
        while True:
            n += os.write(side, b"f" * 1023 + b"\n")
    except BlockingIOError:
        return n
    finally:
        os.close(side)


def drain(rfd):
    os.set_blocking(rfd, False)
    out = b""
    try:
        while True:
            chunk = os.read(rfd, 65536)
            if not chunk:
                break
            out += chunk
    except BlockingIOError:
        pass
    return out


def daemon_lines(blob):
    return [l for l in blob.decode().splitlines() if l.startswith("daemon-")]


def test_a_full_pipe_does_not_stall_the_supervisor_and_daemon_stop_still_arrives(tmp_path):
    rfd, wfd = os.pipe()
    try:
        assert fill(wfd) > 0
        t0 = time.time()
        p, home = start_sup(tmp_path, wfd)
        time.sleep(1.2)                                   # the ready line met a full pipe and was dropped; the stop path is now waiting
        got = drain(rfd)
        out, err = p.communicate(timeout=30)
        got += drain(rfd)
        assert p.returncode == 7, (p.returncode, err)    # the supervisor's exit is still the client's
        assert time.time() - t0 < 10
        lines = daemon_lines(got)
        assert [l.split()[0] for l in lines] == ["daemon-stop"], lines          # ready was dropped; stop arrived
        assert fields(lines[0])["rpt_dropped"] == "1" and fields(lines[0])["outcome"] == "term"
        assert "report channel" in err and "not written" in err, err           # the drop is named on stderr too
        assert not os.path.exists(home + "/recall-daemon.pid"), "the daemon was left running by a supervisor that stalled"
    finally:
        os.close(rfd); os.close(wfd)


def test_a_pipe_nobody_drains_costs_the_supervisor_one_bounded_wait_and_never_a_hang(tmp_path):
    rfd, wfd = os.pipe()
    try:
        fill(wfd)
        t0 = time.time()
        p, home = start_sup(tmp_path, wfd)
        out, err = p.communicate(timeout=40)
        took = time.time() - t0
        assert p.returncode == 7, (p.returncode, err)
        assert took < 10 + FW.REPORT_STOP_WAIT_S, took
        assert daemon_lines(drain(rfd)) == []
        assert err.count("not written") == 2, err                     # the ready line and the stop line: both named, both counted
        assert not os.path.exists(home + "/recall-daemon.pid")
    finally:
        os.close(rfd); os.close(wfd)


def test_a_failed_write_is_counted_and_named_not_swallowed(tmp_path):
    rfd, wfd = os.pipe()
    os.close(rfd)                                                   # no reader: every write fails (EPIPE)
    try:
        p, home = start_sup(tmp_path, wfd)
        out, err = p.communicate(timeout=30)
        assert p.returncode == 7, (p.returncode, err)
        assert err.count("not written") == 2 and "report channel" in err, err       # the ready line and the stop line, each named
    finally:
        os.close(wfd)


def test_the_report_object_counts_each_failure_and_carries_the_count_on_the_next_line(tmp_path):
    rfd, wfd = os.pipe()
    try:
        rpt = FW.Report(wfd)
        assert os.get_blocking(wfd) is False                         # P6: the write end is non-blocking
        fill(wfd)
        assert rpt.send("daemon-ready time=1.000 pid=1 time_to_ready_s=0.500") is False and rpt.dropped == 1
        assert rpt.send("daemon-ready time=1.000 pid=1 time_to_ready_s=0.500") is False and rpt.dropped == 2
        drain(rfd)
        assert rpt.send("daemon-stop time=2.000 pid=1 outcome=term waited_s=0.100") is True and rpt.dropped == 2
        line = daemon_lines(drain(rfd))[0]
        assert line.endswith(" rpt_dropped=2") and FW.report_shape_ok(line.encode()), line
        assert FW.Report(None).send("daemon-ready time=1.000 pid=1 time_to_ready_s=0.500") is False   # no channel: nothing to count
    finally:
        os.close(rfd); os.close(wfd)


# ============================================================================================ the wrapper and the box
FAKE_BWRAP_FDS = r'''#!/bin/sh
case "$*" in *" -I -c pass") exit 0 ;; esac
: > "$FAKE_BWRAP_OUT"
for f in /proc/$$/fd/*; do
  n=${f##*/}
  [ "$n" -gt 2 ] 2>/dev/null || continue
  t=$(readlink "$f"); fl=$(sed -n 's/^flags:[[:space:]]*//p' "/proc/$$/fdinfo/$n" 2>/dev/null)
  same=0; [ -e "$f" ] && [ "$f" -ef "$FAKE_LOG" ] && same=1
  echo "FD $n same_as_log=$same flags=$fl target=$t" >> "$FAKE_BWRAP_OUT"
done
exit 99
'''


@TSS.needs_box
def test_p1_the_box_is_handed_no_descriptor_on_the_log_and_only_the_write_end_of_the_pipe(dcfg, tmp_path):
    fdir = tmp_path / "fb"
    fdir.mkdir()
    TSS.make_exe(str(fdir / "bwrap"), FAKE_BWRAP_FDS)
    out = str(tmp_path / "fds")
    r = run_daemon(dcfg, PATH=str(fdir) + ":/usr/bin:/bin", FAKE_BWRAP_OUT=out, FAKE_LOG=dcfg.log)
    assert r.returncode == 99, (r.returncode, r.stderr)
    rx = re.compile(r"FD ([0-9]+) same_as_log=([01]) flags=([0-7]*) target=(.*)")
    rows = [dict(zip(("fd", "same_as_log", "flags", "target"), m.groups())) for m in map(rx.fullmatch, open(out).read().splitlines()) if m]
    assert len(rows) >= 3, "the fake bwrap saw no descriptors at all: the cell proves nothing"
    assert [x["fd"] for x in rows if x["same_as_log"] == "1"] == [], "bwrap is handed a descriptor on SANDBOX_LOG"
    mode = lambda x: int(x["flags"], 8) & 3
    pipes = [x for x in rows if x["target"].startswith("pipe:[")]
    writers = {x["target"] for x in pipes if mode(x) == 1}
    readers = {x["target"] for x in pipes if mode(x) == 0}
    assert len(writers) == 1, "exactly one write-only pipe goes into the box (the report channel): %r" % pipes
    assert not (writers & readers), "the read end of the report pipe goes into the box too"


@TSS.needs_box
def test_the_reader_and_the_wrapper_end_cleanly_and_the_log_is_whole(dcfg):
    r = run_daemon(dcfg)
    assert r.returncode == 7, (r.returncode, r.stderr)
    lines = log_lines(dcfg)
    closes = [l for l in lines if l.startswith("daemon-report ") and " closed " in l]
    assert len(closes) == 1, lines
    c = fields(closes[0])
    assert c["accepted"] == "2" and c["dropped"] == "0" and c["markers_suppressed"] == "0"     # the ready line and the stop line
    seqs = [int(RE_RLINE.fullmatch(l).group(1)) for l in lines if l.startswith("daemon-report ")]
    assert seqs == list(range(1, len(seqs) + 1)), seqs
    assert TSS.wait_gone(dcfg.tmpd), "the reader (or the forwarder) outlived its box"


INJECT = r'''
import http.client, os, sys
port = int(sys.argv[1])
try:                                                       # the endpoint is not there: the forwarder alone sees a connect failure
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    c.request("GET", "/ping")
    c.getresponse().read()
except Exception:
    pass
fd = int(os.environ["SANDBOX_TEST_REPORT_FD"])
for line in (b"fwd-first-request\n",                                                         # the verdict-bearing marker, exactly as the forwarder writes it
             b"fwd-conn id=99 open=1.000000 close=2.000000 up=0 down=0\n",                    # a fabricated measurement
             b"daemon-ready time=1.000 pid=1 time_to_ready_s=0.001 rpt_dropped=0\n"):         # the box's OWN grammar: the stated limit
    os.write(fd, line)
'''


@TSS.needs_box
def test_p4_a_verdict_shaped_line_written_from_inside_the_box_does_not_reach_the_log(dcfg):
    with open(os.path.join(dcfg.slot, "inject.py"), "w") as f:
        f.write(INJECT)
    r = run_daemon(dcfg, exec_="/usr/bin/python3 %s/inject.py %d" % (dcfg.slot, dcfg.model_port), SANDBOX_TEST_REPORT_LEAK="1")
    assert r.returncode == 0, (r.returncode, r.stderr)
    lines = log_lines(dcfg)
    assert "fwd-first-request" not in lines, "a line written into the pipe from inside the box became the verdict marker"
    assert not [l for l in lines if l.startswith("fwd-conn id=99")], "a fabricated measurement reached the log"
    marks = [fields(l) for l in lines if l.startswith("daemon-report ") and " dropped " in l]
    assert [m["reason"] for m in marks] == ["shape", "shape"] and [m["bytes"] for m in marks] == ["17", str(len(b"fwd-conn id=99 open=1.000000 close=2.000000 up=0 down=0"))]
    rc, text, err = FW.log_verdict(dcfg.log)
    assert (rc, text) == (0, FW.VERDICT_FLAGGED), "the verdict is not what the forwarder alone decided: %r %r" % (text, err)
    # the pipe bounds the consequence and does NOT make the box's lines authentic: a line in the box's own grammar IS recorded
    forged = [l for l in lines if l.endswith("line=daemon-ready time=1.000 pid=1 time_to_ready_s=0.001 rpt_dropped=0")]
    assert len(forged) == 1, "the stated limit changed: a forged line in the box's own grammar is expected to be recorded"


@TSS.needs_box
def test_the_leak_knob_is_a_test_mode_knob_only_and_the_client_has_no_report_descriptor_without_it(dcfg):
    probe = 'test -z "${SANDBOX_TEST_REPORT_FD:-}" && ls /proc/self/fd | tr "\\n" " "'
    r = run_daemon(dcfg, exec_=probe)
    assert r.returncode == 0, (r.returncode, r.stderr)
    assert set(r.stdout.split()) <= {"0", "1", "2", "3"}, "the client holds descriptors it was not given: %r" % r.stdout


# ============================================================================================ the reviewer's round-1 findings (R1-R4)
def test_r2_a_ready_event_needs_exactly_one_stop_event(tmp_path):
    ready = ("daemon-ready", {"time_to_ready_s": "1.5", "pid": "9", "rpt_dropped": "0"})
    stop = ("daemon-stop", {"outcome": "term", "pid": "9", "rpt_dropped": "0"})
    ok = lambda ev: SL.daemon_verdict("engram", {"daemon": "engram"}, ev, SL.LaunchResult(0))
    assert ok([ready, stop]) is None
    none = ok([ready])
    assert none and "daemon-stop" in none and "no " in none, none
    two = ok([ready, stop, stop])
    assert two and "daemon-stop" in two and "2" in two, two
    assert ok([stop, ready, stop]) is not None           # a reordered pair is still two stops: recorded, and refused as a count


R1_LINE = ('HOMEV="%s" /bin/sh -c \'sleep 1; exec /usr/bin/python3 "$HOMEV/stub-daemon.py" "$HOMEV"\' >> "%s/surface-daemon.log" 2>&1 < /dev/null &')


def test_r1_a_daemon_still_in_its_fork_to_exec_window_reads_as_starting_not_as_exited(tmp_path):
    """The shell that will exec the daemon has no daemon directory in its argv until it execs: the old identity test read that as
    'exited-early' and the client was never started. The pid's start time pins identity instead."""
    rfd, wfd = os.pipe()
    try:
        args, home = sup_args(tmp_path, wfd, delay=0.2)
        args["daemon_line"] = R1_LINE % (home, home)
        drv = tmp_path / "driver.py"
        drv.write_text(DRIVER)
        p = subprocess.Popen(["/usr/bin/python3", "-I", str(drv), TSS.FWD, json.dumps(args)], pass_fds=[wfd], stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        out, err = p.communicate(timeout=40)
        lines = daemon_lines(drain(rfd))
        assert p.returncode == 7, (p.returncode, err, lines)
        assert [l.split()[0] for l in lines] == ["daemon-ready", "daemon-stop"], lines
        assert fields(lines[1])["outcome"] == "term"
    finally:
        os.close(rfd); os.close(wfd)


def test_r1_identity_is_the_start_time_a_reused_pid_is_not_the_daemon(tmp_path):
    me = os.getpid()
    start = FW.proc_start(me)
    assert isinstance(start, int) and start > 0 and FW.proc_start(2 ** 22 + 12345) is None
    a = type("A", (), {"daemon_sock": str(tmp_path / "x" / "s")})()
    assert FW.daemon_up(me, a, start) is True
    assert FW.daemon_up(me, a, start + 1) is False          # same pid, another start time: another process


def test_r4_a_term_during_the_readiness_wait_stops_the_daemon_and_writes_the_stop_line(tmp_path):
    import signal as _sig
    rfd, wfd = os.pipe()
    try:
        marker = str(tmp_path / "client-ran")
        p, home = start_sup(tmp_path, wfd, mode="never-bind", cmd=("/usr/bin/touch", marker))
        end = time.time() + 20
        while not os.path.exists(home + "/recall-daemon.pid") and time.time() < end:
            time.sleep(0.05)
        time.sleep(0.3)
        p.send_signal(_sig.SIGTERM)
        out, err = p.communicate(timeout=30)
        lines = daemon_lines(drain(rfd))
        assert p.returncode == 128 + _sig.SIGTERM, (p.returncode, err)
        assert not os.path.exists(marker), "the client was started after a signal"
        assert [l.split()[0] for l in lines] == ["daemon-not-ready", "daemon-stop"], lines
        assert fields(lines[0])["reason"] == "signalled" and fields(lines[1])["outcome"] == "term"
        assert TSS.pids_mentioning(home) == [], "the daemon was left running"
    finally:
        os.close(rfd); os.close(wfd)
