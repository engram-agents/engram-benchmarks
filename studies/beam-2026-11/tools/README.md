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
of two copies of a duplicated literal, or an extra literal in the port, is reported). Usage: `check-port-identity.py --reference-sha SHA256 REFERENCE_DIR PORTED_DIR`; the reference's feed.py must hash to the pinned sha256 of the copy the runs used, or the check refuses (exit 2). Exit 0 =
identical.
