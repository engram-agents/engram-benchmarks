# score-review: record formats and procedure

`score_review.py` implements the three-phase review of `SCORE-REVIEW-PRINCIPLES.md` (v0.1). Everything is files:
JSON Lines, append-only for verdicts. Python 3.11+, standard library only; `pyarrow` is imported lazily and only by
`import-beam`. Every record carries `"schema_version": 1`. Every timestamp is UTC ISO-8601 with a `Z`, read from the
clock when the record is written, never taken from an argument.

Run the tests with `python -m pytest tools/score-review/tests` (the BEAM parquet test skips, and says so, when
`pyarrow` is not installed). All fixtures are synthetic; no benchmark text is committed anywhere.

## Blinding by construction: records are split by audience

Nothing the phase-2 reviewer must not see lives in a file the phase-2 path reads.

| file | holds | read by |
|---|---|---|
| `items.jsonl` | only what phase 2 may see: question, answer texts under opaque ids, cited message ids | everything |
| `grades.jsonl` | rubric, scores, scale, category, metadata, **which id is the official answer**, **which arm produced each answer** | phase-1 packet, `draw`, `map`, `report`, `export-phase3`; never the phase-2 builder |
| `keys/<item>.json` | the letter key for one item's phase-2 packet | `map` and `export-phase3` (the key-holder runs them); `report --unblind --keys-dir` |
| `verdicts.jsonl` | every phase's verdicts | `map`, `report`, `export-phase3`, `draw` (existence check); never the phase-2 builder |
| `draws.jsonl` | the control draw (set c) | `map`; never the phase-2 builder |
| `packets/phase2/<item>.md` | the standalone phase-2 packet | the phase-2 reviewer receives only these files |

The phase-2 builder is `blind_packet.py`. Its functions take the items file, an item id, a seed, an output location and
(optionally) a chat file, and nothing else; the module imports only `json`, `hashlib`, `random`, `re`, `os`, `sys`
and the chat parser, and names no other study file. `packet2` has no `--grades`, `--verdicts` or `--draws` option. The
tests plant a distinctive token in each of those files and assert it never reaches a packet, and run the builder with
those files absent from disk.

## items.jsonl

One line per question. Nothing is graded and nothing is labelled official.

```json
{"schema_version": 1, "item_id": "c1-q07", "question": "Where does the plant sit?",
 "answers": [
   {"answer_id": "1f3a9c20", "text": "On the north shelf.", "cited_ids": [4, 9]},
   {"answer_id": "b7720de1", "text": "By the window.", "cited_ids": []},
   {"answer_id": "e0c4417a", "text": "North shelf, per message 4.", "cited_ids": [4]}]}
```

**Answer ids are opaque and per item.** Each id is the first 8 hex digits of
`sha256("<seed>|<item_id>|<original_index>")`, where `original_index` is 0 for the official answer and 1, 2, ... for the
agent answers in the order the answers file lists them. The `answers` list is then sorted by id. An id therefore carries
no meaning, is not stable across items, and neither the id nor the list position says which answer is official or which
arm produced it. `import-beam --seed` sets the seed; the same seed gives the same ids. An id is lowercase letters and
digits and is never `official` or `ambiguous`.

## grades.jsonl

One line per question.

```json
{"schema_version": 1, "item_id": "c1-q07", "study": "BEAM", "conv": "c1", "question_no": 7,
 "official_id": "1f3a9c20",
 "rubric_lines": ["says north shelf", "cites message 4"],
 "scores": {"b7720de1": [0.0, 0.0], "e0c4417a": [1.0, 1.0]},
 "scale": {"max": 1.0, "min": 0.0},
 "category": "knowledge update", "metadata": {"difficulty": "hard"},
 "arms": {"b7720de1": "arm-x", "e0c4417a": "arm-y"},
 "source_ref": {"dataset": "BEAM", "data_sha256_prefix": "0123456789ab", "conv": "c1"}}
```

`scores` holds the benchmark's grade for each **agent** answer, one score per rubric line; the official answer is the key
and carries none. `arms` is rendered only by `report --unblind`.

## verdicts.jsonl (append-only)

One line per recorded verdict. `record` validates, stamps `recorded_at` and `record_sha256`, and appends; a refusal
leaves the file byte-identical.

```json
{"schema_version": 1, "item_id": "c1-q07", "phase": 1, "reviewer": "lead", "recorded_at": "2026-01-02T03:04:05Z",
 "keyed_by": "label",
 "judgement": {"1f3a9c20": "correct", "b7720de1": "wrong", "e0c4417a": "correct"},
 "fuller_answer": null,
 "facts": [{"msg_id": 4, "quote": "the plant is on the north shelf", "bears_on": "1f3a9c20",
            "direction": "supports", "against_own": false}],
 "guesses": null, "minutes_spent": 6, "notes": "", "supersedes": null, "reason": null,
 "record_sha256": "<64 hex>"}
```

- **Keys.** Phases 1 and 3 key the judgement by answer id (`keyed_by: "label"`). Phase 2 keys it by letter (`A`, `B`, ...;
  `keyed_by: "letter"`). Values are `correct`, `partly` or `wrong`. The item as a whole may instead be
  `{"ambiguous": "source"}`; phase 3 may also write `{"ambiguous": "reviewers split"}`.
- **Facts.** `bears_on` must be a key of the same judgement. With `--chat`, `quote` must be a verbatim substring of
  message `msg_id`; `quote-check` re-runs that check over a whole file.
- **Guesses** (phase 2 only): `{"official": "<letter>", "arms": {"<letter>": "<arm name>"}}`. They name letters and arms,
  so `map` converts only the official guess (to an answer id and a hit flag) and `export-phase3` drops guesses entirely.
- **`record_sha256`** is the sha256 of the record without that field, serialised as canonical JSON: keys sorted, separators
  `,` and `:` with no spaces, non-ASCII characters not escaped, UTF-8.
- **Supersession.** One effective verdict per (item, phase, reviewer). A second record for the same triple is accepted only
  with `--supersedes <record_sha256 of the current one>` and a non-empty `--reason`; both are stored. Superseded records
  stay in the file. `map` supports one reviewer per item per phase and refuses otherwise.
- `fuller_answer` is expected whenever the official answer is judged not correct; `record` cannot check it (it never reads
  grades), so `report` prints it where present.

## draws.jsonl

```json
{"schema_version": 1, "run": "pilot-1", "n": 2, "seed": "s1", "drawn_item_ids": ["c1-q02", "c1-q09"],
 "eligible_item_ids": ["c1-q02", "c1-q05", "c1-q09"], "drawn_at": "2026-01-02T03:04:05Z"}
```

`draw` samples from the items outside set (a) (items where every agent answer has full official score), seeded by the
`--seed` string alone. It refuses if any phase-1 verdict exists for an item in `--items` (the draw is fixed before any
phase-1 outcome exists), if the run was already drawn, or if `--n` exceeds the eligible count.

## keys/<item>.json

```json
{"schema_version": 1, "item_id": "c1-q07", "seed": "pilot-seed", "letters": {"A": "e0c4417a", "B": "1f3a9c20", "C": "b7720de1"}}
```

Letters map to **answer ids** (the packet builder cannot know which is official). `packet2` writes the file, never
overwrites one, and prints its sha256; publish that hash before the phase-2 read. **The letter order is derived from
`(seed, item_id)`**: `random.Random("<seed>\x1f<item_id>")` shuffles the id-sorted answer list, so one seed gives a different
order for every item and the same seed and item always give the same letters.

**The key file itself is published only at settlement** (after phase 3, or after phase 2 for an unquestioned control), and
every reveal is logged with its time (principles 5a).

**Re-keying happens only after the phase-2 verdict is recorded.** `map` and `export-phase3` re-key an item's phase-2
judgement to answer ids only when that item's phase-2 verdict is in `verdicts.jsonl` with a `record_sha256` that recomputes.
For an item without one, `export-phase3` refuses, and `map` does not read the key file at all, writes the item without a
phase-2 entry, and says on stderr (`refused: ...`) if a key file is present. A verdict whose hash does not recompute makes
`map` refuse.

## outcomes.jsonl (written by `map`, regenerated, never hand-edited)

One line per item: `official_id`, `official_levels`, `routing` (`set_a`, `set_b`, `set_c`, `in_phase2`, `in_phase3`,
`unquestioned_control`, `phase3_required`), `phases` (per recorded phase: `reviewer`, `record_sha256`, answer-id-keyed
`judgement`, `outcome`, `flagged`, `fuller_answer`; phase 2 adds `official_guess`), `agreement` (`p1_p2`, `all`), `status`,
`adjusted` (`method` and a per-answer entry), `facts` (the merged fact list). It contains no letter, no letter-to-answer
pair and no arm label.

`status` values: `phase1_pending`, `not_reviewed` (outside phase 2, keeps its official grade), `phase2_pending`,
`control_settled` (unquestioned control, keeps its official grade), `pending` (phase 3 required and absent), `settled`
(phases 1, 2 and 3 agree), `disagreement` (phase 3 recorded but the three do not agree: the three discuss once, and a
remaining split is recorded as a phase-3 `reviewers split`), `ambiguous_split`.

## Rules implemented

- **Levels.** A rubric line is met when its score equals `scale.max`. An answer is `full` if every line is met, `zero` if
  every line equals `scale.min`, else `partial`. correct = full, partly = partial, wrong = zero.
- **Outcome, first matching row:** ambiguous judgement -> `ambiguous_source` (or `ambiguous_split` for phase 3's
  `reviewers split`); official judged partly or wrong -> `key_wrong`; official correct and every agent answer's judgement
  level equals its official level -> `key_stands`; otherwise `grading_error` for exactly the answers whose level differs.
- **Routing.** Phase-2 set = (a) an agent answer below full official score, or (b) a phase-1 outcome other than
  `key_stands`, or (c) a drawn item. Phase-3 set = phase-2 set minus unquestioned controls (every agent answer full and
  both the phase-1 and phase-2 outcome `key_stands`); an item not yet reviewed in phase 2 is not yet a control.
- **Agreement** between phases is identical answer-id-keyed judgements, or both ambiguous. Two grading errors that flag
  different answers do not agree. Whether two settled answers differ on a load-bearing point is the project lead's call in
  phase 3; the script compares only the judgements.
- **Adjusted entry.** `key_wrong` settled: `judge-rerun` pending. `grading_error` settled: `hand-regrade` pending for the
  flagged answers. The tool records the method; the re-scoring itself is done outside it.

## Procedure

1. `import-beam` (or `import-turns` then `import-beam`) writes `items.jsonl` and `grades.jsonl`. `draw` fixes the control
   sample before any phase-1 verdict exists.
2. Phase 1: `packet1` shows the teacher the item; `record --phase 1`.
3. **Commit each phase's verdicts (git) before the next phase's packets are handed out.** The commit is the outside
   witness of the order; the design depends on phase 2 never seeing phase 1 and phase 3 seeing both only after both are
   committed.
4. Phase 2: the key-holder runs `packet2` for each item in the phase-2 set (in a random order) and hands out only the files
   in `packets/phase2/`. The reviewer returns a verdict JSON keyed by letters; the study lead runs `record --phase 2`.
   Commit the verdicts.
5. The key-holder runs `map`, then `export-phase3` for each phase-3 item. Phase 3 records `record --phase 3`.
6. `report` (without `--unblind` until the adjusted set is frozen) renders the log.

## Known limits

- Free text (`fuller_answer`, `notes`) is not scanned: a phase-2 reviewer who writes a letter inside prose carries that
  letter through to the report. `export-phase3` leaves out phase-2 `notes` and `guesses` for this reason.
- A fact's `quote` is checked as a verbatim substring of the message body, with surrounding whitespace trimmed.
- One effective reviewer per item per phase.
