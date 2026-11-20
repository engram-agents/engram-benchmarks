"""Contract tests for p1b_ratio.py (P1b design addition A2), written before the implementation.

Contract:
  R1. CLI: --k3 PATH --k1 PATH [--start 46 --through 135]; each PATH is a run's turns.jsonl; expected exchange count =
      through - start + 1 (90 at the defaults).
  R2. Counted rows: kind == "exchange" and kind == "compact". Any other kind means the wrong run: exit 2, naming file, row i, kind.
  R3. Refusals (exit 2, naming file and row): is_error true / eof / timeout set; a counted row whose wall_s is missing, not a
      number or <= 0; exchanges of the exchange rows, concatenated in file order, not exactly start..through each once in order;
      an exchange row whose per_round differs from the run's K (3 for --k3, 1 for --k1) or whose list length differs from K;
      an empty file or unreadable JSON.
  R4. Prints per run: rows counted, sum of wall seconds, sum / N, count and sum of compact rows; then R = sum_k3 / sum_k1 to
      4 decimals from the raw sums.
  R5. R <= 0.75 -> speed bar MET (exactly 0.75 is MET); R > 0.75 -> speed bar NOT MET: the study runs at k = 1 whatever the
      answer test says. Then the fixed bound line.
  R6. Exit 0 when computed (either decision); 2 for invalid input.
"""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(HERE, "p1b_ratio.py")

BOUND = "bound: one run per k; R is a single measured ratio, not an interval"
NOT_MET = "speed bar NOT MET: the study runs at k = 1 whatever the answer test says"


def rows_for(k, walls, start=1):
    """Exchange rows, k exchanges per round, one wall per round, numbering from start."""
    out = []
    for r, w in enumerate(walls):
        chunk = list(range(start + r * k, start + (r + 1) * k))
        out.append({"i": r + 1, "kind": "exchange", "wall_s": w, "is_error": False, "eof": None, "timeout": None,
                    "exchanges": chunk, "per_round": k})
    return out


def write(tmp_path, name, rows, raw=None):
    p = tmp_path / name
    p.write_text(raw if raw is not None else "".join(json.dumps(r) + "\n" for r in rows))
    return str(p)


def run(k3, k1, *extra):
    return subprocess.run([sys.executable, TOOL, "--k3", k3, "--k1", k1, *extra], capture_output=True, text=True)


def pair(tmp_path, w3, w1, start=1, n=6):
    a = write(tmp_path, "k3.jsonl", rows_for(3, w3, start))
    b = write(tmp_path, "k1.jsonl", rows_for(1, w1, start))
    return a, b, ["--start", str(start), "--through", str(start + n - 1)]


def good(tmp_path):
    """A valid pair, in its own subdirectory so a test's deliberately bad file in tmp_path is not overwritten."""
    d = tmp_path / "ok"
    d.mkdir(exist_ok=True)
    return pair(d, [60.0, 60.0], [20.0] * 6)


def refused(r, fname, *needles):
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    assert fname in r.stderr, r.stderr
    for n in needles:
        assert n in r.stderr, (n, r.stderr)
    assert "R =" not in r.stdout


def test_ratio_is_plain_ratio_of_sums_and_k3_round_not_split(tmp_path):
    a, b, args = pair(tmp_path, [100.0, 50.0], [20.0] * 6)
    r = run(a, b, *args)
    assert r.returncode == 0, r.stderr
    assert "R = 1.2500" in r.stdout          # 150 / 120, no per-exchange re-weighting
    assert NOT_MET in r.stdout and BOUND in r.stdout
    assert "sum 150.0" in r.stdout and "sum 120.0" in r.stdout
    assert "rows counted 2" in r.stdout and "rows counted 6" in r.stdout
    assert "per exchange 25.0000" in r.stdout and "per exchange 20.0000" in r.stdout


def test_exactly_0_75_is_met(tmp_path):
    a, b, args = pair(tmp_path, [45.0, 45.0], [20.0] * 6)   # 90 / 120
    r = run(a, b, *args)
    assert r.returncode == 0
    assert "R = 0.7500" in r.stdout and "R <= 0.75 -> speed bar MET" in r.stdout and "NOT MET" not in r.stdout
    assert BOUND in r.stdout


def test_just_above_line_is_not_met(tmp_path):
    a, b, args = pair(tmp_path, [45.0, 45.1], [20.0] * 6)
    r = run(a, b, *args)
    assert r.returncode == 0 and NOT_MET in r.stdout


def test_decision_uses_raw_sums_not_rounded(tmp_path):
    # Both print R = 0.7500 to 4 decimals; only the raw ratio tells them apart.
    a, b, args = pair(tmp_path, [45.0, 45.0001], [20.0] * 6)
    r = run(a, b, *args)
    assert "R = 0.7500" in r.stdout and NOT_MET in r.stdout
    a, b, args = pair(tmp_path, [45.0, 44.9999], [20.0] * 6)
    r = run(a, b, *args)
    assert "R = 0.7500" in r.stdout and "speed bar MET" in r.stdout and "NOT MET" not in r.stdout


def test_sums_are_not_rounded_before_dividing(tmp_path):
    # sums 10.04 and 3.33; rounding either sum to 1 decimal moves R at the 4th place.
    a = write(tmp_path, "k3.jsonl", rows_for(3, [5.02, 5.02], 1))
    b = write(tmp_path, "k1.jsonl", rows_for(1, [0.555] * 6, 1))
    r = run(a, b, "--start", "1", "--through", "6")
    assert "R = %.4f" % ((5.02 + 5.02) / (0.555 * 6)) in r.stdout


def test_compact_row_counted_and_reported_apart(tmp_path):
    rows = rows_for(3, [60.0, 60.0], 1)
    rows.insert(1, {"i": 99, "kind": "compact", "wall_s": 30.0, "is_error": False})
    a = write(tmp_path, "k3.jsonl", rows)
    b = write(tmp_path, "k1.jsonl", rows_for(1, [30.0] * 6, 1))
    r = run(a, b, "--start", "1", "--through", "6")
    assert r.returncode == 0, r.stderr
    assert "rows counted 3" in r.stdout and "sum 150.0" in r.stdout
    assert "compact rows 1 sum 30.0" in r.stdout and "compact rows 0 sum 0.0" in r.stdout
    assert "R = 0.8333" in r.stdout      # 150 / 180


def test_defaults_are_46_to_135_and_90(tmp_path):
    a = write(tmp_path, "k3.jsonl", rows_for(3, [30.0] * 30, 46))
    b = write(tmp_path, "k1.jsonl", rows_for(1, [10.0] * 90, 46))
    r = run(a, b)
    assert r.returncode == 0, r.stderr
    assert "R = 1.0000" in r.stdout and "per exchange 10.0000" in r.stdout


def test_refuse_question_row(tmp_path):
    rows = rows_for(3, [60.0, 60.0], 1)
    rows.append({"i": 7, "kind": "question", "wall_s": 5.0, "is_error": False})
    a = write(tmp_path, "k3.jsonl", rows)
    _, b, args = good(tmp_path)
    refused(run(a, b, *args), "k3.jsonl", "row 7", "question")


def test_refuse_other_kinds(tmp_path):
    for kind in ("practice-question", "setup", "mystery"):
        rows = rows_for(3, [60.0, 60.0], 1)
        rows.insert(0, {"i": 0, "kind": kind, "wall_s": 5.0})
        a = write(tmp_path, "k3.jsonl", rows)
        _, b, args = good(tmp_path)
        refused(run(a, b, *args), "k3.jsonl", "row 0", kind)


def test_refuse_wrong_kind_in_k1_file_names_that_file(tmp_path):
    a, _, args = good(tmp_path)
    rows = rows_for(1, [20.0] * 6, 1)
    rows[2]["kind"] = "question"
    b = write(tmp_path, "k1.jsonl", rows)
    refused(run(a, b, *args), "k1.jsonl", "row 3", "question")


def test_refuse_is_error_eof_timeout(tmp_path):
    for field in ("is_error", "eof", "timeout"):
        rows = rows_for(3, [60.0, 60.0], 1)
        rows[1][field] = True
        a = write(tmp_path, "k3.jsonl", rows)
        _, b, args = good(tmp_path)
        refused(run(a, b, *args), "k3.jsonl", "row 2", field)


def test_refuse_bad_wall(tmp_path):
    for bad in (None, "abc", 0, -3.0, True):
        rows = rows_for(3, [60.0, 60.0], 1)
        rows[0]["wall_s"] = bad
        a = write(tmp_path, "k3.jsonl", rows)
        _, b, args = good(tmp_path)
        refused(run(a, b, *args), "k3.jsonl", "row 1", "wall_s")
    rows = rows_for(3, [60.0, 60.0], 1)
    del rows[0]["wall_s"]
    a = write(tmp_path, "k3.jsonl", rows)
    _, b, args = good(tmp_path)
    refused(run(a, b, *args), "k3.jsonl", "row 1", "wall_s")


def test_refuse_bad_wall_on_compact_row(tmp_path):
    rows = rows_for(3, [60.0, 60.0], 1)
    rows.append({"i": 9, "kind": "compact", "wall_s": 0})
    a = write(tmp_path, "k3.jsonl", rows)
    _, b, args = good(tmp_path)
    refused(run(a, b, *args), "k3.jsonl", "row 9", "wall_s")


def test_refuse_missing_round(tmp_path):
    rows = rows_for(3, [60.0, 60.0], 1)
    del rows[1]
    a = write(tmp_path, "k3.jsonl", rows)
    _, b, args = good(tmp_path)
    refused(run(a, b, *args), "k3.jsonl", "exchange")


def test_refuse_duplicate_round(tmp_path):
    rows = rows_for(3, [60.0, 60.0], 1)
    rows.append(dict(rows[1], i=3))
    a = write(tmp_path, "k3.jsonl", rows)
    _, b, args = good(tmp_path)
    refused(run(a, b, *args), "k3.jsonl", "exchange")


def test_refuse_reordered_rounds(tmp_path):
    rows = rows_for(3, [60.0, 60.0], 1)
    rows.reverse()
    a = write(tmp_path, "k3.jsonl", rows)
    _, b, args = good(tmp_path)
    refused(run(a, b, *args), "k3.jsonl", "exchange")


def test_refuse_reordered_rows_k1(tmp_path):
    a, _, args = good(tmp_path)
    rows = rows_for(1, [20.0] * 6, 1)
    rows[2], rows[3] = rows[3], rows[2]
    b = write(tmp_path, "k1.jsonl", rows)
    refused(run(a, b, *args), "k1.jsonl", "exchange")


def test_refuse_wrong_range(tmp_path):
    a, b, _ = good(tmp_path)
    refused(run(a, b, "--start", "2", "--through", "7"), "k3.jsonl", "exchange")


def test_refuse_per_round_mismatch(tmp_path):
    rows = rows_for(3, [60.0, 60.0], 1)
    rows[0]["per_round"] = 1
    a = write(tmp_path, "k3.jsonl", rows)
    _, b, args = good(tmp_path)
    refused(run(a, b, *args), "k3.jsonl", "row 1", "per_round")


def test_refuse_k3_file_passed_as_k1(tmp_path):
    a, _, args = good(tmp_path)
    refused(run(a, a, *args), "k3.jsonl", "per_round")


def test_refuse_list_length_differs_from_k(tmp_path):
    rows = rows_for(3, [60.0, 60.0], 1)
    rows[0]["exchanges"] = [1, 2]
    a = write(tmp_path, "k3.jsonl", rows)
    _, b, args = good(tmp_path)
    refused(run(a, b, *args), "k3.jsonl", "row 1", "exchanges")


def test_refuse_empty_file(tmp_path):
    a = write(tmp_path, "k3.jsonl", [], raw="")
    _, b, args = good(tmp_path)
    refused(run(a, b, *args), "k3.jsonl", "empty")


def test_refuse_unreadable_json(tmp_path):
    a = write(tmp_path, "k3.jsonl", [], raw=json.dumps(rows_for(3, [60.0], 1)[0]) + "\nnot json\n")
    _, b, args = good(tmp_path)
    refused(run(a, b, *args), "k3.jsonl", "JSON")


def test_refuse_missing_file(tmp_path):
    _, b, args = good(tmp_path)
    r = run(str(tmp_path / "nope.jsonl"), b, *args)
    assert r.returncode == 2 and "nope.jsonl" in r.stderr


# ---------------------------------------------------------------------------------------------------------------------
# Post hoc readings (design owner's ruling, 2026-11-20). Descriptive only, never the registered R. Contract:
#   P0. Without the new flags behaviour is unchanged (every test above, plus a pinned full stdout).
#   P1. --posthoc-exclude A-B (repeatable) drops exchanges A..B from BOTH runs. Each range must be whole K = 3 rounds of
#       the run's own range, inside start..through, not overlapping another. A row is excluded only when ALL its exchanges
#       are inside the excluded set; a row partly inside is a refusal. Remaining rows validate as before; an excluded row
#       may carry is_error/eof/timeout. Remaining exchanges are exactly start..through minus the excluded set, in order.
#       Never silent: an EXCLUDED ROWS block lists every excluded row of both files.
#   P2. --posthoc-count-errored counts is_error rows (eof / timeout still refuse); lists them; refuses if none is set.
#   P3. Both flags together: refuse. P4. With a flag: first line is the post hoc banner, no registered decision line, an
#       "R (post hoc) = ...; above 0.75: yes|no" line and the bound line. P5. Exit 0 computed, 2 refusal.
# ---------------------------------------------------------------------------------------------------------------------
BANNER = "POST HOC READING, NOT THE REGISTERED R"
EXC_HEAD = "EXCLUDED ROWS (post hoc, not the registered R)"
CNT_HEAD = "COUNTED ERRORED ROWS (post hoc, not the registered R)"


def ph_pair(tmp_path, w3, w1=None, start=1, n=12, mutate3=None, mutate1=None):
    """Four K=3 rounds vs twelve k=1 rows by default; mutate hooks edit the row lists before writing."""
    r3 = rows_for(3, w3, start)
    r1 = rows_for(1, w1 if w1 is not None else [20.0] * n, start)
    if mutate3:
        mutate3(r3)
    if mutate1:
        mutate1(r1)
    d = tmp_path / "ph"
    d.mkdir(exist_ok=True)
    return write(d, "k3.jsonl", r3), write(d, "k1.jsonl", r1), ["--start", str(start), "--through", str(start + n - 1)]


def lines_of(r):
    return r.stdout.splitlines()


def block_lines(r, head):
    """Lines after `head` up to the next blank line or the end."""
    ls = lines_of(r)
    assert head in ls, (head, r.stdout)
    out = []
    for l in ls[ls.index(head) + 1:]:
        if not l.strip():
            break
        out.append(l)
    return out


def err(row, **flags):
    row.update(flags)


def test_no_flag_stdout_pinned_byte_for_byte(tmp_path):
    a, b, args = pair(tmp_path, [100.0, 50.0], [20.0] * 6)
    r = run(a, b, *args)
    assert r.returncode == 0 and r.stderr == ""
    assert r.stdout == (
        "K=3: rows counted 2 | sum 150.0 | per exchange 25.0000 | compact rows 0 sum 0.0\n"
        "k=1: rows counted 6 | sum 120.0 | per exchange 20.0000 | compact rows 0 sum 0.0\n"
        "R = 1.2500\n"
        "R > 0.75 -> speed bar NOT MET: the study runs at k = 1 whatever the answer test says\n"
        "bound: one run per k; R is a single measured ratio, not an interval\n")


def test_exclude_drops_whole_round_from_both_runs_and_reports_it(tmp_path):
    a, b, args = ph_pair(tmp_path, [60.0, 999.0, 60.0, 60.0],
                         mutate3=lambda rs: err(rs[1], is_error=True),
                         mutate1=lambda rs: err(rs[3], is_error=True))
    r = run(a, b, *args, "--posthoc-exclude", "4-6")
    assert r.returncode == 0, r.stderr
    assert lines_of(r)[0] == BANNER
    assert "R (post hoc) = 1.0000; above 0.75: yes" in r.stdout    # 180 / (9 * 20)
    assert "speed bar" not in r.stdout and "R <= 0.75" not in r.stdout and "R > 0.75" not in r.stdout
    assert "R =" not in r.stdout
    assert BOUND in r.stdout
    assert "rows counted 3" in r.stdout and "rows counted 9" in r.stdout        # per-run summaries kept
    assert "sum 180.0" in r.stdout and "per exchange 20.0000" in r.stdout
    blk = block_lines(r, EXC_HEAD)
    assert len(blk) == 4, blk                                                    # k3 round 2, k1 rows 4, 5, 6
    k3 = [l for l in blk if "k3.jsonl" in l]
    k1 = [l for l in blk if "k1.jsonl" in l]
    assert len(k3) == 1 and len(k1) == 3
    assert "row 2" in k3[0] and "[4, 5, 6]" in k3[0] and "999.0" in k3[0] and "is_error" in k3[0]
    assert "row 4" in k1[0] and "[4]" in k1[0] and "is_error" in k1[0]
    assert "is_error" not in k1[1] and "is_error" not in k1[2]


def test_exclude_below_line_says_no(tmp_path):
    a, b, args = ph_pair(tmp_path, [30.0, 999.0, 30.0, 30.0], mutate3=lambda rs: err(rs[1], is_error=True))
    r = run(a, b, *args, "--posthoc-exclude", "4-6")
    assert r.returncode == 0, r.stderr
    assert "R (post hoc) = 0.5000; above 0.75: no" in r.stdout and "speed bar" not in r.stdout


def test_exclude_is_repeatable_and_lists_every_excluded_row(tmp_path):
    a, b, args = ph_pair(tmp_path, [999.0, 60.0, 60.0, 999.0])
    r = run(a, b, *args, "--posthoc-exclude", "1-3", "--posthoc-exclude", "10-12")
    assert r.returncode == 0, r.stderr
    assert "R (post hoc) = 1.0000; above 0.75: yes" in r.stdout                  # 120 / (6 * 20)
    blk = block_lines(r, EXC_HEAD)
    assert len(blk) == 8 and len([l for l in blk if "k3.jsonl" in l]) == 2


def test_excluded_rows_may_carry_any_flag_and_are_reported(tmp_path):
    a, b, args = ph_pair(tmp_path, [60.0, 999.0, 60.0, 60.0], mutate3=lambda rs: err(rs[1], eof=True),
                         mutate1=lambda rs: err(rs[4], timeout=True))
    r = run(a, b, *args, "--posthoc-exclude", "4-6")
    assert r.returncode == 0, r.stderr
    blk = block_lines(r, EXC_HEAD)
    assert any("k3.jsonl" in l and "eof" in l for l in blk)
    assert any("k1.jsonl" in l and "row 5" in l and "timeout" in l for l in blk)


def test_exclude_still_refuses_a_flag_on_a_non_excluded_row(tmp_path):
    for field in ("is_error", "eof", "timeout"):
        a, b, args = ph_pair(tmp_path, [60.0] * 4, mutate3=lambda rs, f=field: err(rs[0], **{f: True}))
        refused(run(a, b, *args, "--posthoc-exclude", "4-6"), "k3.jsonl", "row 1", field)


def test_exclude_refuses_ranges_not_whole_k3_rounds(tmp_path):
    a, b, args = ph_pair(tmp_path, [60.0] * 4)
    for spec in ("2-4", "1-2", "1-4", "4-5", "5-7"):
        r = run(a, b, *args, "--posthoc-exclude", spec)
        refused(r, "--posthoc-exclude", "whole K = 3 rounds")
        assert BANNER not in r.stdout


def test_exclude_alignment_is_measured_from_the_runs_own_start(tmp_path):
    a, b, args = ph_pair(tmp_path, [60.0] * 4, start=46)         # rounds begin at 46, 49, 52, 55
    ok = run(a, b, *args, "--posthoc-exclude", "49-51")
    assert ok.returncode == 0, ok.stderr
    refused(run(a, b, *args, "--posthoc-exclude", "48-50"), "--posthoc-exclude", "whole K = 3 rounds")
    refused(run(a, b, *args, "--posthoc-exclude", "47-49"), "--posthoc-exclude", "whole K = 3 rounds")


def test_exclude_refuses_out_of_range(tmp_path):
    a, b, args = ph_pair(tmp_path, [60.0] * 4, start=4, n=12)    # exchanges 4..15
    for spec in ("1-3", "16-18", "13-18"):
        refused(run(a, b, *args, "--posthoc-exclude", spec), "--posthoc-exclude", "outside")


def test_exclude_refuses_overlapping_ranges(tmp_path):
    a, b, args = ph_pair(tmp_path, [60.0] * 4)
    refused(run(a, b, *args, "--posthoc-exclude", "1-6", "--posthoc-exclude", "4-6"), "--posthoc-exclude", "overlap")
    refused(run(a, b, *args, "--posthoc-exclude", "4-6", "--posthoc-exclude", "4-6"), "--posthoc-exclude", "overlap")


def test_exclude_refuses_malformed_range(tmp_path):
    a, b, args = ph_pair(tmp_path, [60.0] * 4)
    for spec in ("x", "4", "6-4", "4-", "a-b", "4-6-9"):
        refused(run(a, b, *args, "--posthoc-exclude", spec), "--posthoc-exclude", "refused: ")


def test_exclude_refuses_a_row_partly_inside_the_range(tmp_path):
    def split(rs):                       # round 1 holds 4 (inside 4-6) and 1, 2 (outside); round 2 holds 3, 5, 6
        rs[0]["exchanges"] = [1, 2, 4]
        rs[1]["exchanges"] = [3, 5, 6]
    a, b, args = ph_pair(tmp_path, [60.0] * 4, mutate3=split)
    r = run(a, b, *args, "--posthoc-exclude", "4-6")
    refused(r, "k3.jsonl", "row 1", "partly")
    assert BANNER not in r.stdout


def test_exclude_refuses_when_remaining_exchanges_are_not_exact(tmp_path):
    a, b, args = ph_pair(tmp_path, [60.0] * 4, mutate3=lambda rs: rs.pop(3))      # round 4 missing, not excluded
    refused(run(a, b, *args, "--posthoc-exclude", "4-6"), "k3.jsonl", "exchange")


def test_exclude_leaves_compact_rows_counted(tmp_path):
    a, b, args = ph_pair(tmp_path, [60.0] * 4, mutate3=lambda rs: rs.insert(2, {"i": 99, "kind": "compact", "wall_s": 30.0}))
    r = run(a, b, *args, "--posthoc-exclude", "4-6")
    assert r.returncode == 0, r.stderr
    assert "compact rows 1 sum 30.0" in r.stdout and "rows counted 4" in r.stdout    # 3 rounds + compact
    assert "R (post hoc) = 1.1667; above 0.75: yes" in r.stdout                      # (180 + 30) / 180
    assert all("99" not in l for l in block_lines(r, EXC_HEAD))


def test_count_errored_counts_the_row_and_lists_it(tmp_path):
    a, b, args = ph_pair(tmp_path, [30.0] * 4, mutate3=lambda rs: err(rs[1], is_error=True),
                         mutate1=lambda rs: err(rs[7], is_error=True))
    r = run(a, b, *args, "--posthoc-count-errored")
    assert r.returncode == 0, r.stderr
    assert lines_of(r)[0] == BANNER
    assert "R (post hoc) = 0.5000; above 0.75: no" in r.stdout                       # 120 / 240
    assert "speed bar" not in r.stdout and "R =" not in r.stdout and BOUND in r.stdout
    assert "rows counted 4" in r.stdout and "rows counted 12" in r.stdout
    blk = block_lines(r, CNT_HEAD)
    assert len(blk) == 2, blk
    assert "k3.jsonl" in blk[0] and "row 2" in blk[0] and "[4, 5, 6]" in blk[0] and "30.0" in blk[0]
    assert "k1.jsonl" in blk[1] and "row 8" in blk[1] and "[8]" in blk[1]
    assert EXC_HEAD not in r.stdout


def test_count_errored_above_line_says_yes(tmp_path):
    a, b, args = ph_pair(tmp_path, [90.0] * 4, mutate3=lambda rs: err(rs[0], is_error=True))
    r = run(a, b, *args, "--posthoc-count-errored")
    assert "R (post hoc) = 1.5000; above 0.75: yes" in r.stdout


def test_count_errored_still_refuses_eof_and_timeout(tmp_path):
    for field in ("eof", "timeout"):
        a, b, args = ph_pair(tmp_path, [30.0] * 4, mutate3=lambda rs, f=field: err(rs[2], is_error=True, **{f: True}))
        r = run(a, b, *args, "--posthoc-count-errored")
        refused(r, "k3.jsonl", "row 3", field)
        assert BANNER not in r.stdout
        a, b, args = ph_pair(tmp_path, [30.0] * 4, mutate3=lambda rs: err(rs[0], is_error=True),
                             mutate1=lambda rs, f=field: err(rs[5], **{f: True}))
        refused(run(a, b, *args, "--posthoc-count-errored"), "k1.jsonl", "row 6", field)


def test_count_errored_refuses_when_no_row_is_errored(tmp_path):
    a, b, args = ph_pair(tmp_path, [30.0] * 4)
    refused(run(a, b, *args, "--posthoc-count-errored"), "--posthoc-count-errored", "no row")


def test_count_errored_still_checks_wall_of_an_errored_row(tmp_path):
    a, b, args = ph_pair(tmp_path, [30.0] * 4, mutate3=lambda rs: err(rs[1], is_error=True, wall_s=0))
    refused(run(a, b, *args, "--posthoc-count-errored"), "k3.jsonl", "row 2", "wall_s")


def test_the_two_post_hoc_flags_are_never_mixed(tmp_path):
    a, b, args = ph_pair(tmp_path, [30.0] * 4, mutate3=lambda rs: err(rs[1], is_error=True))
    r = run(a, b, *args, "--posthoc-count-errored", "--posthoc-exclude", "4-6")
    assert r.returncode == 2 and "never mixed" in r.stderr and r.stdout == ""
