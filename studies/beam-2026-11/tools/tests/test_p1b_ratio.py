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
