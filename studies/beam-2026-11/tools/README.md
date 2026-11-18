# Study harness (tools)

These files are the harness of the BEAM 2026-11 study: they feed a BEAM conversation to a Claude
Code "student" running a local model, one exchange at a time, and record every turn. They are
research scripts, not product code. The run scripts are kept as the record of how the practice
runs were executed.

## Requirements

- Python 3 with `pyarrow` (the scripts that read the dataset).
- Claude Code (`claude` on `PATH`).
- Ollama serving the model (default endpoint `http://localhost:11434`; override with `BEAM_OLLAMA_URL`).  <!-- privacy-scan: allow (Ollama's documented default endpoint) -->
- The BEAM 100K parquet file from Hugging Face. It is not redistributed in this repository.
- For the ENGRAM arm only: a checkout of the ENGRAM source that holds `tools/install.sh`.

## Environment variables

| Variable | Used by | Meaning |
|---|---|---|
| `BEAM_PARQUET` | `feed.py`, `feed2.py` | Path to the BEAM 100K parquet file. Required. |
| `BEAM_OLLAMA_URL` | `feed.py`, `feed2.py`, `vanilla-hello.sh` | Ollama endpoint. Optional; default is Ollama's own default endpoint (see Requirements above). |
| `PROCTOR_DIR` | `ask-proctor` | Question/answer exchange directory. Set by the feeders for the student (`<out>/proctor`). Required. |
| `PROCTOR_TIMEOUT` | `ask-proctor` | Seconds to wait for an answer. Optional; default 900. |
| `BEAM_TOOLS` | run scripts | Directory holding `feed2.py` and `patch-core-alwaysload.py` (this directory). |
| `BEAM_OUT` | run scripts | Directory for run output (`run-*` subdirectories) and install logs. |
| `BEAM_WORK` | run scripts | Scratch root; each arm gets its own HOME below it (for example `$BEAM_WORK/e2-engram`). Deleted and recreated by the scripts. Must be outside any git repository: the run scripts refuse otherwise, because inside a git work tree ENGRAM refused the student's transcript citations in practice. |
| `BEAM_PY` | run scripts | Python interpreter that has `pyarrow`. |
| `ENGRAM_SRC` | run scripts (ENGRAM arm) | ENGRAM source checkout; `tools/install.sh` is run from it. |
| `BEAM_HELLO_DIR` | `vanilla-hello.sh` | Scratch directory that already holds `work/`, `cc-home/` and `eh/`; outputs are written into it. |
| `MODEL`, `TAG` | `vanilla-hello.sh` | Model name (default `qwen3.8:27b`) and a suffix for the output file names. |

The run output directories (`runs/`, `run-*`) hold full transcripts; keep them out of version
control (the repository `.gitignore` covers `runs/`).

## Scope of this harness

The harness renders **exam format v2 only** (the proctor marker, the reading-material delimiters and
the relabelled speakers; see `../protocol/exam-room.md`). Two parts of the planned E3 design are not in it yet:
E3's brief sentence, and the user-level exam line that both arms are to receive. The run scripts record the
practice runs that were executed; they do not run E3.

## `feed.py`

The per-turn `--resume` driver used for the early practice runs, and the single source of the exam
brief and of how a conversation is rendered. It holds the exam brief (`BRIEF`), the proctor marker
(`PROCTOR`), the per-exchange line (`TURN_LINE`), the question prompt prefix (`QUESTION_PREFIX`),
`render()` and `exchanges()` (which turn a BEAM conversation into one prompt per user/assistant
exchange), and `unload()` (asks Ollama to unload the model so a resident model does not block the
next run's GPU reservation). As a program it feeds one conversation to a Claude Code session, one
exchange per `claude -p` call (`--resume` after the first), and optionally asks probing questions.

- Inputs: `--arm-home DIR --out DIR --conv N --turns K [--questions Q] [--model M] [--turn-timeout S]`; `BEAM_PARQUET`.
- Outputs: `<out>/turns.jsonl` (one summary line per turn); progress on stdout.

## `feed2.py`

The driver used by every run script. One persistent Claude Code process per run
(`--input-format stream-json --output-format stream-json`), so session-start hooks fire once. It
imports `BRIEF`, `PROCTOR`, `QUESTION_PREFIX`, `exchanges` and `unload` from `feed.py`, so the two
files must stay in one directory. It holds `FACT_SHEET` and `NUDGE` (the fixed setup texts). Phases in one session: optional first-session setup (a fixed fact sheet, then a
fixed nudge per further question), reading (brief plus one exchange per message; the student ends
each with NEXT), optional `/compact`, then probing questions and any proctor-written practice
questions.

- Inputs: `--arm-home DIR --out DIR --conv N --turns K [--questions Q] [--first-session] [--setup-only] [--setup-rounds R] [--force-compact] [--ask TEXT ...] [--model M] [--turn-timeout S] [--env KEY=VALUE ...]`; `BEAM_PARQUET`.
- Outputs: `<out>/events.jsonl` (every stream event), `<out>/turns.jsonl` (per-turn summary), `<out>/stderr.log`.

## `ask-proctor`

The escalation command available to the student inside the exam room, for problems with the exam
environment only (never benchmark content). It writes the question to `$PROCTOR_DIR`, waits for an
answer file written by the proctor, prints it, and appends every question and answer to
`$PROCTOR_DIR/log.tsv` with UTC times. The feeders put this directory on the student's `PATH`.

- Inputs: the question as arguments; `PROCTOR_DIR`; optional `PROCTOR_TIMEOUT`.
- Outputs: `$PROCTOR_DIR/q-<id>.txt`, `$PROCTOR_DIR/log.tsv`; exit 3 on timeout.

## `patch-core-alwaysload.py`

Sandbox-only patch used by the E2 run. Marks six ENGRAM tools (`engram_add_observation`,
`engram_inspect`, `engram_query`, `engram_derive`, `engram_supersede`, `engram_checkpoint`) as
`anthropic/alwaysLoad` by inserting one `meta=` line after each tool's `@mcp.tool(` decorator in an
installed copy of `server.py`, so Claude Code does not defer them behind tool search.

- Input: path to a `server.py` copy (argument 1). Patches it in place.
- Output: one line per tool; exit 1 unless all six were patched exactly once.

## Run scripts

All five fail at once, with a message, if a required variable is unset. Each deletes and recreates
its HOME directories under `$BEAM_WORK`, so give it a scratch location outside any git repository.

- `run-engram-full.sh`: ENGRAM arm, full practice sequence. Fresh install, first session as its own session, then the exam in a new session (3 exchanges, forced `/compact`, 2 questions).
- `run-v2-both.sh`: format-v2 repeat, vanilla arm then ENGRAM arm (3 exchanges, forced `/compact`, 2 practice questions, same text in both arms).
- `run-e1-alwaysload.sh`: ENGRAM arm with the plugin's MCP server set to `alwaysLoad` (patch applied to `.mcp.json`); setup once, snapshot, three independent exams.
- `run-e2-core.sh`: ENGRAM arm with only the six core tools patched to `alwaysLoad` via `patch-core-alwaysload.py`; setup once, snapshot, three independent exams.
- `vanilla-hello.sh`: smoke test of vanilla Claude Code on the local model in an isolated HOME (see `BEAM_HELLO_DIR`).

Outputs (all but the last go under `$BEAM_OUT`): install logs and `run-*` directories as produced
by `feed2.py`; `vanilla-hello.sh` writes `vanilla-hello<TAG>.json` and `.err` into `$BEAM_HELLO_DIR`.

If a GPU reservation wrapper is needed on your host, put it in front of `$PY -I $BEAM_TOOLS/feed2.py`
yourself; the scripts here run the commands exactly as the practice runs did.

## `check-port-identity.py`

Checks that a ported copy of `feed.py`/`feed2.py` shows the student exactly what a reference copy
shows: sha256 of the brief, proctor marker, per-exchange line, setup fact sheet and nudge, and of
`render()` and `exchanges()` output on a small synthetic conversation, the question prompt prefix, plus
a comparison of every string literal in the source as a multiset in both directions (so a change to one
of two copies of a duplicated literal, or an extra literal in the port, is reported). Usage: `check-port-identity.py PORTED_DIR` compares a copy's student-visible components with the committed pin in `data/pinned-runs-feed.json` (anyone can run it); `check-port-identity.py REFERENCE_DIR PORTED_DIR` runs the full comparison and refuses (exit 2) a reference whose feed.py does not hash to the pinned sha256; `--reference-sha` overrides the pin with a printed warning. Exit 0 =
identical.

## `feed4.py`, `setup-id.py`, `coverage.py`, `gate-input-evidence.py`

`feed4.py`: the gate runs' feed script plus `--per-round K` (speed pilot P1) and `--dump-plan`. `setup-id.py`: the
setup id by content, with the import walk (every study-local module the feed script imports must be a component).
`coverage.py`: the pilots' note-coverage attribution, its controls, and the per-run measures. `gate-input-evidence.py`:
shows, byte for byte, that a run's student received the messages its own `feed.py` builds. Each file's docstring has
its usage; the tuning log has their outputs.

## Answering harness (P1): `--question-file`, `answer-delivery-check.py`, `plant-control.py`, `control-source-check.py`

`feed4.py --question-file F` delivers a frozen list (a JSON list of `{"id", "question"}`) in file order, once each, after
the optional `/compact`, one message per item (`PROCTOR + " " + QUESTION_PREFIX + question`). An answering run is
`--resume SESSION --turns 0 --force-compact --question-file F`; `--dump-plan` shows exactly `[compact, q1..qN]`. It is
refused (exit 2, before any student process or model unload) without `--resume`, with `--setup-only`,
`--first-session`, `--questions` or `--ask`, with duplicate ids, an empty
question, an empty list, or a file that is not a list of such objects. Each question's turn record carries
`"kind": "question"` and its `"id"`. Without the flag the plan and the turn records are unchanged.

`answer-delivery-check.py --turns RUN/turns.jsonl --questions F --session SESSION`: PASS (exit 0) only if every turn
carries the resumed session id, exactly one compact turn precedes the first question, every id of F appears once in file
order, and there are no other question turns and no reading turns. Each failure is printed; exit 1 on any.

`plant-control.py --home COPY --builtin-fact T --engram-fact T --absent-fact T --evidence-dir DIR`: the two-channel
control, for a **disposable copy** of an arm home only (refuses without `COPY/.disposable-copy`, under `P1_PROTECTED`,
with an evidence dir inside `COPY/work`, or with a fact shorter than 6 characters). The built-in fact goes in as one
markdown file in the arm's memory folder; the ENGRAM fact through `engram_observation._add_observation_impl` (what the
`engram_add_observation` tool calls), imported in-process from the copy's own plugin, with its evidence file in DIR. It
also lists the note in the folder's `MEMORY.md` by one neutral appended line in the format of an existing line (exit 2 if
there is no `MEMORY.md`; `--question TEXT` exits 2 if that line holds a content word of the question); the observation is
embedded by default through the copy's own embedder (`--no-embeddings` opts out; exit 2 if the model cannot load). It
then checks read-back, that no fact is in any transcript, cross-absence between the two channels, that the absent fact
is nowhere, and the per-table row counts before and after. Run it with the python of the copy's ENGRAM venv. Exit codes: 0 all checks pass, 1 a check failed, 2 refused, **3 a `P1_PROTECTED` entry changed during the run** (a snapshot of every protected entry is compared with a re-walk on every exit path after the pre-write scan; each changed path is printed, then `PROTECTED CHANGED: n path(s)`; this overrides 0, 1 and 2, and a clean run prints `protected unchanged: ...`). It reports a write, it cannot undo one.

`control-source-check.py --events E --turns T --controls C`: for the three control questions (one per channel), reports
from the turn's own tool calls where the answer came from; it never decides abstention for the `none` control.

Cells: `tests/` (`pytest`; `BEAM_PY` = a python with pyarrow, `P1_ENGRAM_PLUGIN` = an ENGRAM plugin tree for the plant
cells). Synthetic fixtures only: no student model, no Ollama, no real arm home.

## Session launcher (P1): `p1-question-file.py`, `p1-session.py`

`p1-question-file.py --list F --expect-sha256 H [--exclude ID[,ID]] --seed N --out JSON`: builds the frozen question
file from the key-fact list (rows `ID | exchange | style | QUESTION || GOLD`). The question text only, never the gold; ids
sorted, then `random.Random(N).shuffle`; byte-identical for the same inputs; prints the count, the order and the JSON's
sha256. Exit 2, nothing written, on a wrong list hash, a repeated id, an `--exclude` id not in the list, an unparsable
row, or an existing `--out`.

`p1-session.py --end-state PATH --session ID --label NAME --question-file F --components F [--plant-builtin T
--plant-engram T --plant-absent T [--plant-question TEXT]] [--dry-run]`: answers the question file on a disposable copy of
a preserved end-state home, placed at the arm-home slot path so the run's session resumes. Environment (all required, no
host path in the file): `BEAM_PY`, `BEAM_ARM_HOME` (the slot), `BEAM_RUNS_DIR`, `P1_PROTECTED` (the preserved homes, one of
which is `--end-state`). It refuses (exit 2) before touching anything, never deletes (an existing slot is moved aside),
hashes the store and the built-in memory files of every protected home before and after, and exits 5 with
`PROTECTED CHANGED` if any differ. Outputs under `BEAM_RUNS_DIR/p1-LABEL`: `before-hashes.txt`, `after-hashes.txt`,
`plan.json`, `run/`, `transcripts/`, `delivery.txt`, `setup.txt`. Exit codes: 0 good, 1 delivery check failed, 2 refused,
3 copy, plan check or feed4 failed, 4 plant failed, 5 a protected home changed. The step list, the store-hash method and the
test-only hooks (`P1_FEED4`, `P1_PLANT_CONTROL`, `P1_UTC_STAMP`, `P1_AFTER_COPY_HOOK`) are in its docstring.
