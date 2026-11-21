# review-page: a human-review page for benchmark results

`build_page.py` turns five result row files into ONE html file a person can read: run scores, scores by
question type, why points were lost, the possible problems found in the data with their checks, and every
question with its rubric marks and the student's full answer.

**This directory holds no data.** No result rows, no answer text, no benchmark text, no keys, no host paths.
The tool reads the files you give it on the command line and writes the page where you tell it. Its tests use
invented fixtures only.

```
python3 tools/review-page/build_page.py --data DIR --out FILE.html \
    [--answers-file PATH] [--withhold FILE --withhold-reason TEXT] [--d3 PATH] [--title TEXT]
```

Exit 0 on success. Exit 2 on any bad input (named on stderr), with nothing written. Python 3, standard
library only. Tests: `python3 -m pytest tools/review-page/tests -q`.

## Inputs

`--data DIR` holds five files, each `{"rows": [...], "meta": [...]}`. `meta` is optional and is not copied
into the page. A missing file, an unparseable file, a file without a `rows` list, or a row missing a field
the page reads (or holding it as the wrong type) is refused, naming the file, the row index and the field.

The fields below are the ones `page.html` reads, taken from its code. `str` = string, `num` = number,
`int` = integer.

| file | one row is | fields the page reads |
|---|---|---|
| `runs.json` | one scored run | `run_id` str, `conv` (any), `setup_hash` str, `grader` str, `official_pct` num, `adjusted_pct` num, `adjust_delta` num, `pass_n`, `partial_n`, `fail_n`, `asked_back_n`, `asked_back_justified_n` num. The page shows the LAST row as "the latest run". |
| `categories.json` | one run x question type | `run_id`, `category`, `label` str, `n`, `official_pct`, `adjusted_pct` num |
| `causes.json` | one run x cause of lost points | `run_id`, `cause` (key), `label` str, `count` num |
| `answers.json` | one answered question | `run_id`, `key` (`run_id:question_no`), `category`, `question`, `reference` (the official answer), `grade` (`pass`, `partial` or `fail`), `grader`, `causes` (cause LABELS joined by `; `), `asked_back` (`yes`/`no`), `ask_justified`, `findings` (finding ids joined by `, `), `notes`, `rubric` str; `question_no` int; `official_score`, `adjusted_score` num; `gate_cell` (any); `answer` (the student's text, from the row or from `--answers-file`). `rubric` is a JSON string `[{"line": str, "mark": "yes"\|"partial"\|"no", "adjusted": mark or null}]`. |
| `findings.json` | one possible problem | `finding_id`, `area`, `claim_type`, `claim`, `status`, `status_label`, `severity`, `opened_at` (ISO time), `report_line`, `notes` str; `question_no` int or null; `checks` num; `verifications` str, a JSON list of `{at, reader, method, result, exchanges_read, speakers_read, evidence: [{exchange, speaker, quote}], notes}`. `area` is one of `Official dataset`, `Our student`, `Our harness` (the page's filter chips). Optional: `conv`, used only by `--withhold` (below). |

A conversation id lives on `runs.json` (`conv`); an answer row finds its conv through its `run_id`.

`--answers-file PATH`: a JSON object `{"<conv>:<question_no>": "<full answer text>"}`. When given, its text
fills each answer row's `answer`, and wins over one already in the row. Every kept row must end up with an
answer text, or the build is refused. Extra keys are ignored.

`--title TEXT` sets the page heading and the document title (default `BEAM Scorecard`).

## Withhold contract (`--withhold FILE --withhold-reason TEXT`)

For publishing or sharing a page without some questions' content. `FILE` lists `conv:question_no` pairs, one
per line (blank lines and `#` comments allowed). `--withhold-reason` is required with `--withhold`, and refused
without it. A pair that matches no answer row in the data is refused and named, so a typo cannot pass
silently.

1. **Every row about a withheld question is removed from every dataset the page carries:** its answer row,
   its answer text (from the row or from `--answers-file`), its grade, rubric and notes. Question numbers are
   per conversation: `1:3` removes question 3 of conversation 1 only. A **finding is dropped whole** when it
   touches a withheld question, that is, when its own `question_no` equals a withheld question number (in the
   finding's `conv` if it has one; **in every conv if it has none**, which can drop a finding that was about a
   kept conversation: over-removal is the safe direction), or when a withheld answer row lists it in
   `findings`. A finding is not partly redacted, because that needs a guess about which words carry content.
   Kept answer rows lose any dropped finding id from their `findings` list. A category or cause row whose
   questions are all withheld disappears.
2. **Run scores and every per-category and per-cause count are recomputed from the kept answer rows,**
   never copied from the input's precomputed fields: question score = mean of its rubric lines (`yes` 1,
   `partial` 0.5, `no` 0; the adjusted score uses a line's `adjusted` mark where it has one); run score =
   mean over the kept questions, as a percentage rounded to one decimal. Each run row then carries
   `questions` (N, kept) and `questions_total` (M, that run's answer rows in the input), and the page labels
   the scores "over N of M questions". A run with no kept question shows "—" for its scores.
3. **A banner** at the top names how many questions are withheld, their numbers (not secret; their content
   is) and the reason text. The reason is shown as given: do not put withheld content in it.
4. **No byte of a withheld question's content survives in the file.** The tests check this by generation:
   for each withheld question they take every string of every input row about it (answer row, including
   the parsed rubric lines; its `--answers-file` text; the finding rows the rule above drops) and assert none
   occurs in the output, in its raw, JSON-escaped and doubly-escaped forms. Strings a build without those
   questions also contains (a grade, a mark, a shared word) are excluded by comparing against that build, so
   the check is about content specific to the withheld rows. A second cell points the same check at a build that
   kept the rows and must find them. The tool also never loads a withheld question's text into the output.
5. **Without `--withhold` the page is today's page:** every row is passed through untouched (a test compares
   the recomputation with the precomputed scores on a fixture and they agree).

Not covered, by design: the check looks at rows about the withheld questions. A kept row that quotes a
withheld question in its own free text (a note on another question, say) is not detected.

## Offline mode (`--d3 PATH`)

Without `--d3`, the page loads d3 from a CDN tag and the tool prints one line saying the page needs
network access to draw its charts. With `--d3`, the file is checked against a sha256 pinned in the code and
inlined: the output is ONE self-contained file with no `<script src>`, no `<link>`, no import. A hash
mismatch is refused.

- Upstream URL: `https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js`
- Pinned sha256: `d6b03aefc9f6c44c7bc78713679c78c295028fa914319119e5cc4b4954855b1c` (279,633 bytes)
- How it was measured: on 2026-11-21 (UTC) the file was downloaded once from that URL with `curl` and
  hashed with `sha256sum`. As a cross-check the same version was downloaded from a second CDN
  (`https://cdn.jsdelivr.net/npm/d3@7.8.5/dist/d3.min.js`) and gave the same size and hash. The file's
  own comment banner mentions the d3 project URL; that is text inside the library, not a request.

## What the page shows

A headline sentence and four tiles for the latest run (official score, adjusted score, pass/partial/fail,
how often the student asked the user back); bars by question type and by cause; a table of all runs; the
possible problems with every check and its evidence, filterable by area; and every question of the latest
run with the official answer, the rubric marks, the grade and the student's full answer. Official score =
the dataset's answers as given. Adjusted = marks re-rated against a corrected answer where a finding has
been confirmed. The page's own "How the scores and statuses work" note says the same.

## Files

- `build_page.py`: the CLI (the checks, the withhold logic, the recomputation, the page assembly).
- `page.html`: the page body (markup, styles, scripts). It reads data through a small `dash` shim that
  `build_page.py` inlines; `__TITLE__` and `__BANNER__` are filled by the build.
- `tests/`: `fixtures.py` (a tiny invented two-run, eight-question dataset) and `test_build_page.py`.
