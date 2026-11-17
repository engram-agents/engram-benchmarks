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
| `grades.jsonl` | rubric, scores, scale, category, metadata, **which id is the official answer** (or, for a criterion item, the criterion text), **which arm produced each answer** | phase-1 packet, `draw`, `map`, `report`, `export-phase3`; never the phase-2 builder |
| `keys/<item>.json` | the letter key for one item's phase-2 packet | `map` and `export-phase3` (the key-holder runs them); `report --unblind --keys-dir` |
| `verdicts.jsonl` | every phase's verdicts | `map`, `report`, `export-phase3`, `draw` (existence check); never the phase-2 builder |
| `draws.jsonl` | the control draw (set c) | `map`; never the phase-2 builder |
| `packets/phase2/<item>.md` | the standalone phase-2 packet | the phase-2 reviewer receives only these files |

The phase-2 builder is `blind_packet.py`. Its functions take the items file, an item id, a seed, an output location and
(optionally) a chat file, and nothing else; the module imports only `json`, `hashlib`, `random`, `re`, `os`, `sys`,
`glob` (to find a killed run's temporary files) and the chat parser, and names no other study file. `packet2` has no `--grades`, `--verdicts` or `--draws` option. The
tests plant a distinctive token in each of those files and assert it never reaches a packet, and run the builder with
those files absent from disk.

## items.jsonl

One line per question. Nothing is graded and nothing is labelled official.

```json
{"schema_version": 1, "item_id": "3fa9c21b07", "question": "Where does the plant sit?",
 "answers": [
   {"answer_id": "1f3a9c20", "text": "On the north shelf.", "cited_ids": [4, 9]},
   {"answer_id": "b7720de1", "text": "By the window.", "cited_ids": []},
   {"answer_id": "e0c4417a", "text": "North shelf, per message 4.", "cited_ids": [4]}]}
```

**Item ids are opaque.** `import-beam` sets `item_id` to the first 10 hex digits of
`sha256("<seed>|<conv>|<question_no>")`. The conversation and the question number live only in `grades.jsonl`
(`conv`, `question_no`): a positional id such as `<conv>-q07` maps deterministically to the question's category in
BEAM's flattened order, which phase 2 must not see. The id appears in `items.jsonl`, `keys/`, the packet title and every
packet file name, so none of those carries the conversation or the question number. `import-beam` writes the rows of
`items.jsonl` sorted by `item_id` (question order is category order), and no code pairs items with grades, verdicts or
keys by row position: every join is by `item_id`, and the files are read in item-id order whatever order their rows are in.

**Custody of the import seed.** Item ids are `sha256(seed|conv|question_no)[:10]`, so anyone holding the import seed can
recompute every id from the public conversation id and the question numbers, and so read each item's position and with it
its category. The import seed (written `<secret-seed>` in these docs) therefore lives only with `grades.jsonl` and the
key holder, the non-reviewing seat. It is never in a phase-2 packet or in any file handed to the phase-2 reviewer, and it
is not reused as the `draw` seed (logged in `draws.jsonl`) or the `packet2` seed (stored in each key file). The
neutral-by-construction claim for item ids holds only while the import seed stays confined this way.

**Answer ids are opaque and per item.** Each id is the first 8 hex digits of
`sha256("<seed>|<item_id>|<original_index>")`, where `original_index` is 0 for the official answer and 1, 2, ... for the
agent answers in the order the answers file lists them. The `answers` list is then sorted by id. An id therefore carries
no meaning, is not stable across items, and neither the id nor the list position says which answer is official or which
arm produced it. An item holds one or more answers: an answer-type item has the official answer plus at least one agent
answer; a **criterion-type item holds only agent answers** (see "Criterion items" below), because the criterion is not an
answer and must not reach the phase-2 builder, which renders whatever `answers` holds. `import-beam --seed <secret-seed>` sets the seed; the same seed gives the same ids. An id is lowercase letters and
digits and is never `official` or `ambiguous`.

## grades.jsonl

One line per question.

```json
{"schema_version": 1, "item_id": "3fa9c21b07", "study": "BEAM", "conv": "c1", "question_no": 7,
 "official_id": "1f3a9c20",
 "rubric_lines": ["says north shelf", "cites message 4"],
 "scores": {"b7720de1": [0.0, 0.0], "e0c4417a": [1.0, 1.0]},
 "scale": {"max": 1.0, "min": 0.0},
 "category": "knowledge update", "metadata": {"difficulty": "hard"},
 "arms": {"b7720de1": "arm-x", "e0c4417a": "arm-y"},
 "source_ref": {"dataset": "BEAM", "data_sha256_prefix": "0123456789ab", "conv": "c1"}}
```

**Reference kind.** `reference_kind` is `"answer"` (the reference is a text the benchmark calls the ideal answer: the first present
of `ideal_answer`, `answer`, `ideal_response`, `ideal_summary`) or `"criterion"` (instruction- and preference-following items,
where the benchmark gives no answer, only `expected_compliance`). `reference_kind` lives only here, never in `items.jsonl`.
An answer-type grade has `official_id` (one of the item's answers) and no `criterion_text`. A criterion-type grade has
`official_id: null` and `criterion_text` (the `expected_compliance` text); the criterion lists (`compliance_indicators`,
`non_compliance_signs`) stay in `metadata`, as lists, and the item's `source_chat_ids` (if any) in `metadata.source_chat_ids`.
`load_grades` enforces exactly this. A grades file written before this field existed reads as `"answer"`.

`scores` holds the benchmark's grade for each **agent** answer, one score per rubric line; the official answer is the key
and carries none. `arms` is rendered only by `report --unblind`.

## verdicts.jsonl (append-only)

One line per recorded verdict. `record` validates, stamps `recorded_at` and `record_sha256`, and appends; a refusal
leaves the file byte-identical.

```json
{"schema_version": 1, "item_id": "3fa9c21b07", "phase": 1, "reviewer": "lead", "recorded_at": "2026-01-02T03:04:05Z",
 "keyed_by": "label",
 "judgement": {"1f3a9c20": "correct", "b7720de1": "wrong", "e0c4417a": "correct"},
 "fuller_answer": null,
 "facts": [{"msg_id": 4, "quote": "the plant is on the north shelf", "bears_on": "1f3a9c20",
            "direction": "supports", "against_own": false}],
 "guesses": null, "minutes_spent": 6, "notes": "", "supersedes": null, "reason": null,
 "record_sha256": "<64 hex>"}
```

- **Keys.** Phases 1 and 3 key the judgement by answer id (`keyed_by: "label"`); on a criterion item they add one key,
  `criterion`, beside the agent answer ids. Phase 2 keys it by letter (`A`, `B`, ...; `keyed_by: "letter"`).
- **`step`** is `null` except for phase 2 of a criterion item, where it is `"2a"` or `"2b"` (see "Criterion items"). The verdict
  file may carry `step`; `record` takes `--grades` so it knows each item's kind, and refuses a step on an answer item or a
  phase-2 record without one on a criterion item. Values are `correct`, `partly` or `wrong`. The item as a whole may instead be
  `{"ambiguous": "source"}`; phase 3 may also write `{"ambiguous": "reviewers split"}`.
- **Facts.** `bears_on` must be a key of the same judgement. With `--chat`, `quote` must be a verbatim substring of
  message `msg_id`; `quote-check` re-runs that check over a whole file.
- **Guesses** (phase 2 only; on a criterion item, in the 2a record only, as `{"arms": {...}}` with no official guess):
  `{"official": "<letter>", "arms": {"<letter>": "<arm name>"}}`. They name letters and arms,
  so `map` converts only the official guess (to an answer id and a hit flag) and `export-phase3` drops guesses entirely.
- **`record_sha256`** is the sha256 of the record without that field, serialised as canonical JSON: keys sorted, separators
  `,` and `:` with no spaces, non-ASCII characters not escaped, UTF-8.
- **Supersession.** One effective verdict per (item, phase, step), whoever the reviewer. A second record for the same
  triple, by the same reviewer or by another, is accepted only with `--supersedes <record_sha256 of the current one>` and a
  non-empty `--reason`; both are stored. Superseded records stay in the file. `record` also refuses a record that would
  leave a criterion item's 2a and 2b with different reviewers. So a verdicts file written through `record` never holds two
  effective reviewers for one (item, phase, step), and `map` (which supports one and refuses otherwise) never meets two.
- **Order.** `record` refuses phase 2 for an item with no recorded phase-1 verdict, and phase 3 for an item without both
  a phase-1 and a phase-2 verdict (a criterion item: its phase 1, its 2a and its 2b). Order is also witnessed outside the
  tool, by the git commit of each phase's verdicts (see "Procedure").
- `fuller_answer` is expected whenever the official answer is judged not correct; `record` cannot check it (it never reads
  grades), so `report` prints it where present.

## draws.jsonl

```json
{"schema_version": 1, "run": "pilot-1", "n": 2, "seed": "s1", "drawn_item_ids": ["9b04d7e1aa", "e41a6b7c05"],
 "eligible_item_ids": ["9b04d7e1aa", "58c2e0f3d9", "e41a6b7c05"], "drawn_at": "2026-01-02T03:04:05Z"}
```

`draw` samples from the items outside set (a) (items where every agent answer has full official score), seeded by the
`--seed` string alone. It refuses if any phase-1 verdict exists for an item in `--items` (the draw is fixed before any
phase-1 outcome exists), if the run was already drawn, or if `--n` exceeds the eligible count.

## keys/<item>.json

```json
{"schema_version": 1, "item_id": "3fa9c21b07", "seed": "<packet-seed>", "letters": {"A": "e0c4417a", "B": "1f3a9c20", "C": "b7720de1"}}
```

Letters map to **answer ids** (the packet builder cannot know which is official). `packet2` writes the packet first and the
key last, each through a temporary file and a hard link (which fails rather than overwrite), so a failure leaves neither a
key without its packet nor a half-written file. It never overwrites a packet or a key: an existing one is refused before
anything is written, and, because the packet is placed the same way, a packet that exists when the key stage fails is always
this run's own and is removed. It prints the key's sha256; publish that hash before the phase-2 read. **Crash residue:** a run killed between staging and linking leaves
`<item>.md.tmp-<pid>` beside the packet or `<item>.json.tmp-<pid>` beside the key. `packet2` refuses to run while one of
those sits beside the outputs it would write, naming the file, so the residue is seen rather than silent; the operator
checks it and removes it by hand. A temporary file of another item does not block this one. **The letter order is derived from
`(seed, item_id)`**: `random.Random("<seed>\x1f<item_id>")` shuffles the id-sorted answer list, so one seed gives a different
order for every item and the same seed and item always give the same letters.

**The key file itself is published only at settlement** (after phase 3, or after phase 2 for an unquestioned control), and
every reveal is logged with its time (principles 5a).

**Re-keying happens only after the phase-2 verdict is recorded.** `map` and `export-phase3` re-key an item's phase-2
judgement to answer ids only when that item's phase-2 verdict is in `verdicts.jsonl` with a `record_sha256` that recomputes.
For an item without one, `export-phase3` refuses, and `map` does not read the key file at all, writes the item without a
phase-2 entry, and says on stderr (`refused: ...`) if a key file is present. A verdict whose hash does not recompute makes
`map` refuse.

## Criterion items (instruction- and preference-following)

A criterion is visibly not an answer, so an A/B blind between "official" and agent answers cannot hold. For
`reference_kind = "criterion"` items phase 2 is two steps, enforced by the tool:

- **2a.** `packet2` as for any item. `items.jsonl` holds only the agent answers, so the packet shows the question, the chat and
  the agent answers under letters, and no criterion (the criterion text lives only in `grades.jsonl`, which `packet2` cannot
  read). The reviewer judges each lettered answer. `fuller_answer` states what a complying answer must do and the message id
  that sets the instruction or preference. `record --phase 2` stores it with `step: "2a"`; a 2a may carry an arm guess
  (`{"arms": ...}`), never an official-answer guess.
- **2b.** `export-criterion --items I --grades G --verdicts V --item ID --reviewer R --out X.json` refuses unless a phase-2
  `step: "2a"` record by that reviewer exists for the item (every record's `record_sha256` must recompute). Before it writes
  the file it appends an **export record** to the verdicts file (below), then writes only
  `criterion_text`, `criterion_lists` (from metadata), the item id, the reviewer, the time and the 2a record's hash. The
  reviewer then records `step: "2b"`, whose judgement has exactly one key, `criterion`: `correct`, `partly` or `wrong`.
  `record` refuses a 2b carrying any other key (an agent-answer judgement, a letter, `ambiguous`) or a guess, and refuses a 2b
  without a 2a by the same reviewer.
- **The export record.** The reveal is an event in the verdict store, not an inference from the 2b: `export-criterion`
  appends `{"schema_version": 1, "kind": "export_2b", "item_id", "reviewer", "exported_at", "after_2a_record_sha256",
  "record_sha256"}` (the effective 2a it was made after; the hash is computed like a verdict's) through the same single
  append as `record`, before it releases the criterion. It is not a verdict: it has no `phase`, and nothing counts it as a
  reviewer's phase record (`effective`, the one-reviewer rule, the order rule, `has_phase2_record`, `draw`, the arm-guess
  statistic). A second export for the same item and reviewer is allowed and recorded; the first one is the boundary. A
  tampered export record makes every reader refuse, like a tampered verdict.
- **Changing a 2a** needs a new 2a with `--supersedes` and `--reason` (the supersession key includes the step). What it
  does depends on the file order against the reviewer's FIRST export record. **Before the export** it is an ordinary
  correction: the latest 2a is the one mapped and nothing is forced. **After the export** (before or after the 2b record)
  the criterion has been shown and the item is the anchored case: the ORIGINAL 2a, the one named by that export's
  `after_2a_record_sha256` (the unanchored second read), is the one mapped; the later 2a is carried beside it as
  `post_reveal_revision` (`reviewer`, `record_sha256`, `judgement`, `fuller_answer`, `facts`, `reason`) and shown in the
  report labelled "post-reveal revision"; and the item is **forced into the phase-3 set whatever the outcomes**, never an
  unquestioned control (`routing.forced_phase3`). `map` carries the revision under `phases["2"].post_reveal_revision`,
  `export-phase3` carries it, re-keyed to answer ids, as `phase2_post_reveal_revision` beside the original in `phase2`, and
  its facts join the merged list marked `post_reveal: true`.
- **Where things live.** The arm guess is in the 2a record only (a 2b with `guesses` is refused). Item-level `ambiguous` is a 2a
  matter only (a 2b with it is refused). A 2b may carry `fuller_answer` (the fuller criterion) when its judgement is not
  `correct`; `map` and `report` carry it as `fuller_answer_2b`.
- **Phases 1 and 3** are not blind: they judge `criterion` plus the agent answer ids directly. `packet1` and `report` print
  the criterion text where they print the official answer for an answer-type item.
- **Mapping.** `map` and `export-phase3` build a criterion item's phase-2 view only once both the 2a and the 2b are
  recorded: the 2b `criterion` judgement stands in the official answer's place in outcome rows 2-4, beside the 2a judgements
  re-keyed to answer ids. With only a 2a, the item is `phase2_pending`. Routing and agreement are unchanged (levels are
  agent-answer-only). `official_id` is `null` and there is no official-answer guess.

## Limits of the phase-2 blind

- **Item kind.** A packet without an official answer tells the reviewer the item's kind (the reviewer can see the item is not
  an A/B).
- **Answer count.** With one agent answer (single-arm data) there is no A/B at all, only an unanchored read of that answer.
  A criterion item shows one answer fewer than an answer-type item, which is a count signal of the same kind.
- **The cited-messages line.** The benchmark's reference answer cites messages and an agent's answer (from `import-turns`)
  cannot, so a per-answer cited line would name the official answer. The rule: `packet2` lists cited ids (and, with `--chat`,
  their text) **only if every answer in the item has a non-empty cited list**, in the same form under each answer;
  otherwise it lists none for any answer and prints one neutral line, `Cited messages: not shown for this item`. Residual
  limit: when every answer does cite, the packet shows each list, and the lists themselves may differ in length or in
  which messages they name.

## outcomes.jsonl (written by `map`, regenerated, never hand-edited)

One line per item: `official_id`, `official_levels`, `routing` (`set_a`, `set_b`, `set_c`, `in_phase2`, `in_phase3`,
`unquestioned_control`, `phase3_required`, `forced_phase3`), `reference_kind`, `phases` (per recorded phase: `reviewer`,
`record_sha256`, answer-id-keyed `judgement`, `outcome`, `flagged`, `fuller_answer`; phase 2 adds `official_guess`, and for a
criterion item `record_sha256_2b`, `fuller_answer_2b` and, when its 2a was revised after the criterion export, `post_reveal_revision`), `agreement`
(`p1_p2`, `all`), `status`,
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
   Commit the verdicts. For a criterion item, that record is the 2a; the key-holder then runs `export-criterion` for the
   same reviewer, hands out only its output, and records the returned 2b (see "Criterion items").
5. The key-holder runs `map`, then `export-phase3` for each phase-3 item. Phase 3 records `record --phase 3`.
6. `report` (without `--unblind` until the adjusted set is frozen) renders the log.

## Known limits

- Free text (`fuller_answer`, `notes`) is not scanned: a phase-2 reviewer who writes a letter inside prose carries that
  letter through to the report. `export-phase3` leaves out phase-2 `notes` and `guesses` for this reason.
- A fact's `quote` is checked as a verbatim substring of the message body, with surrounding whitespace trimmed.
- One effective reviewer per item per phase and step: enforced when recording (see "Supersession"), and again by `map`.
  Once one reviewer has recorded both steps of a criterion item, no other reviewer can redo either step (the split-pair
  guard); the only way out is hand-editing the append-only file.