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

`plant-control.py` **ENGRAM-only mode** (P1 control 2 on an end state whose built-in folder is empty): `--builtin-fact` is
optional. Without it the tool plants the ENGRAM fact only and prints `mode: engram-only (no built-in plant)` before any
write (`mode: both channels` otherwise). It writes nothing under any built-in memory folder; a missing `MEMORY.md` or
memory folder is not a refusal; `--question` is refused (exit 2, it only qualifies the index line). A new check,
`memory folders unchanged`, proves the set of memory folders found is the same after the write (a newly created folder
FAILS) and that every entry of every memory folder is the same: files and directories, with type, mode and, for a file,
sha256 (a new empty directory or a chmod FAILS; zero folders is reported as `0 folders, unchanged`; exit 1 on FAIL). The checks that need the built-in fact print `SKIP (no built-in plant)`, never PASS, and do
not change the exit code; all other checks and the exit-3 post-condition run as in the two-channel mode, which is
unchanged when `--builtin-fact` is given.

`control-source-check.py --events E --turns T --controls C`: for the three control questions (one per channel), decides
each planted fact on REACHABILITY, not on the answer (the final rule, design owner's rulings of 2026-11-18). **Design
principle: every approximation errs toward FAIL for the clause it serves; the module docstring applies it as a class rule:
it ENUMERATES the seven exemption sites S1 to S7 (every place something is decided NOT to count), and for each names what
it exempts, the positive known-shape evidence it requires, and that an unknown or off-shape input COUNTS (cells
`test_r3_s1_*` to `test_r3_s7_*`).** An engram/folder fact PASSES iff (a) a read
through its intended channel, named by STORAGE (a pinned ENGRAM read tool; or any call whose target is inside the memory
folder, the folder of the control's `folder_file`: a Read, a Grep/Glob `path`, a Bash command naming a path inside it,
`~` / `$HOME` / `${HOME}` resolved to the home taken from `folder_file`, quote-split words such as `"$HOME"/.claude/...`
joined), in a turn after the compaction returned the token
in that call's tool result, (b) the student's own query text echoed back never counts: for (a) every occurrence of every
string of the call's own input (`payload_json` decoded) is stripped from the result first (a stored value equal to the
query is stripped too, toward FAIL); for (c) and (d') only the top-level `query` field of an `engram_query` / `engram_surface` result is stripped (the
one echo the server is known to produce; an ENGRAM result recorded in Claude Code's envelope `{"result": "<inner JSON as a string>"}`, exactly one key whose value is a string that parses as JSON, is read as its inner object, here and for the created ids of (c'), and no other shape is unwrapped); every other tool, a result that does not parse and a result without that field
is not stripped, so an `engram_list` contains-filter on the token that returns one stored copy is a return, and so is a
query that is exactly the token whose result also holds a stored copy; a Grep, Bash or Read result is never stripped, (c)
no read through the other channel returned the token anywhere in the session (for a folder control the other channel is
every tool of the pinned ENGRAM server except its known writes, the `readOnlyHint=false` ones, so `engram_history` and
`engram_diagnose` count and an unknown tool counts), except (c') a returned item the tool can IDENTIFY as one the student wrote after its first
intended read: for the ENGRAM channel the result is parsed and every dict holding the token must carry the id of a node the
student's own creating tool reported created after that read, under that tool's own key and with status "created"
(`engram_add_observation` `observation_id`, the batch's `results[].observation_id`, `engram_derive` `derivation_id`,
`engram_add_conjecture` `conjecture_id`, `engram_ask` `question_id`, `engram_add_definition` `definition_id`; the keys are
cited to the plugin source in the code), with no token outside those dicts; `engram_supersede`, `engram_contradict`,
`engram_retract` and every other tool create no excusing id, and no bare `id` or generic key is read; for the
folder channel the read must be of a file the student itself created with a Write (absolute path, result "created
successfully") after that read, no earlier call having named it (an Edit/MultiEdit of a file is never excused, a grep of the whole folder is not excused); a `note:` names the
node ids or the file; a pre-existing item, an unparseable result or any other return FAILs, and (d) the evidence file or
the run directory (the optional per-control `run_dir`) was not opened before that first read (opened after it is noted,
not void); an opening is a FILE-CAPABLE call, by default-deny: every call except `ToolSearch`, `TodoWrite`,
`ExitPlanMode`, `EnterPlanMode`, `AskUserQuestion` and any tool of the pinned ENGRAM server (so `Task`, `Agent`,
`WebFetch`, a tool of another MCP server and unknown tools count) that names them or that returns the token from a path outside both channels, while a path in an MCP tool's
arguments is only a mention. The answer is printed beside the verdict and decides nothing: a refusal that quotes the token
passes only if a channel read returned it. Other tool kinds are listed and neither pass nor fail. Stated bound (S7): a folder target the checker cannot resolve (a
relative path, a glob, a variable other than HOME, a subshell path, a Grep with no `path`) is not seen, and a `Task` or
`Agent` subagent that reads the memory folder returns the token with no folder target in this stream, so for the engram
control it is a note at most. It never decides abstention for the `none` control.

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
host path in the file): `BEAM_PY`, `BEAM_ARM_HOME` (the slot), `BEAM_RUNS_DIR`, `BEAM_PARQUET` (the dataset file feed4.py
reads; it must be an existing file whose sha256 starts with the prefix `studies/beam-2026-11/PROVENANCE.md` registers, which the launcher checks in step 1 by streaming the file, as the reading runs' `pilot-run.sh` did; `setup.txt` records the full sha256), `P1_PROTECTED` (the preserved homes, one of
which is `--end-state`). A plant set is either all three of `--plant-builtin --plant-engram --plant-absent` (optionally
`--plant-question`) or exactly `--plant-engram --plant-absent` (engram-only, for control 2: plant-control.py runs without
`--builtin-fact` and writes nothing under any built-in memory folder); any other combination, and `--plant-question`
without `--plant-builtin`, is refused in step 1. `setup.txt` records the plant mode on its own line. Every refusal (exit 2) in step 1 happens before anything is touched: no process killed, no copy,
no directory made. One refusal comes later: step 4 refuses if the aside path already exists, after the slot processes have
been stopped; no protected path is touched either way. It never deletes (an existing slot is moved aside),
hashes the store and the built-in memory files of every protected home before and after, and exits 5 with
`PROTECTED CHANGED` if any differ. The exit-5 guarantee holds whenever the process gets to decide its exit (including
KeyboardInterrupt, SystemExit and other exceptions); a SIGKILL, power loss or machine failure between the copy and the
final check leaves no exit code at all. Outputs under `BEAM_RUNS_DIR/p1-LABEL`: `before-hashes.txt`, `after-hashes.txt`,
`plan.json`, `run/`, `transcripts/`, `delivery.txt`, `setup.txt`. Exit codes: 0 good, 1 delivery check failed, 2 refused,
3 copy, plan check or feed4 failed, 4 plant failed, 5 a protected home changed. The step list, the store-hash method and the
test-only hooks (`P1_FEED4`, `P1_PLANT_CONTROL`, `P1_UTC_STAMP`, `P1_AFTER_COPY_HOOK`, `P1_TEST_RAISE`, `P1_EXPECTED_PARQUET_PREFIX`; the last replaces the registered dataset prefix and `setup.txt` says so on its `dataset check:` line) are in its docstring.

`p1-session.py --continue-reading --start N --through M --per-round K --save-end-state PATH --expect-store-sha256 H [--expect-serving FILE]` (with `--end-state --session --label --components`, no question file, no plant flag; P1b): resumes the end state's session on the disposable copy and feeds READING rounds for exchanges N..M of conversation 9 (`--through` is the last exchange; feed4's `--turns` is the inclusive end index), then saves the resulting home as a new end state with its hashes in `PATH.hashes.txt` (both created exclusively at save time, the saved copy link-checked as the next run will check it, and only paths this run created are ever removed on failure; a failure to prove the protected homes unchanged that is not a difference prints `AFTER-HASHES UNAVAILABLE` and is exit 3, never `PROTECTED CHANGED`). Refuses (exit 2) a start off a round boundary, a partial last round, a store hash that is not the expected one, a save path or hashes path that exists or is equal to, inside or containing any path the launcher creates or protects (the run directory, the aside path, the slot, every protected home; one function, `launcher_paths`, is the single source and a test binds it to what a dry run really creates), and a serving setup that differs from `--expect-serving`; records the model server's version and the model digest in `setup.txt` (so `--dry-run` in this mode also needs a live model server: the serving setup is recorded at start, by design); checks that the continue plan is byte-equal to a full run's messages for the same exchanges before any student run; checks delivery with `reading-delivery-check.py --turns RUN/turns.jsonl --plan PLAN.json --events RUN/events.jsonl --session ID` (the answering check refuses reading turns by design). Cells: `tests/test_p1_continue_reading.py`, `tests/test_reading_delivery_check.py`.

## Student sandbox: `student-sandbox.sh`, `sandbox-forward.py`

A process boundary around the student (both arms). The run script installs `student-sandbox.sh` as a file named `claude` in a directory put FIRST on `PATH`, so `feed4.py`'s `Popen(["claude", ...])` starts it. It checks and prepares outside the box, then `exec`s `bwrap`; from the student's first instruction on, the student and everything it spawns live inside new PID, network, IPC and UTS namespaces. The feeder is not boxed and keeps reading the dataset. It needs `bwrap` (0.9.0 or newer: `--size`, `--ro-bind-fd`, `--ro-bind-data`), `/usr/bin/python3` (standard library only) and unprivileged user namespaces; it never uses `socat`.

| Variable | Meaning |
|---|---|
| `SANDBOX_SLOT` | The benchmark home (the student's `HOME`): an existing directory, bound read-write at its own path. Validated by the class rules below. |
| `SANDBOX_BINARY`, `SANDBOX_BINARY_SHA256` | The pinned Claude Code binary and its full sha256. The binary is opened once, hashed from that open file, and THAT descriptor is bound read-only (`--ro-bind-fd`) at the file's resolved path, as the last mount: the file hashed is the file bound, and nothing mounted before it can shadow it. A mismatch is a refusal. Only the binary file is bound, never its directory (its siblings are invisible). |
| `SANDBOX_RO_BINDS` + `SANDBOX_RO_ROOT`, `SANDBOX_RW_BINDS` + `SANDBOX_RW_ROOT` | Optional extra binds: colon-separated absolute directories, bound read-only / read-write at their own resolved paths. Each ROOT is required with its binds, and every entry must lie inside its root after `realpath` (an allow-list by declared roots, never a list of bad names). Every entry must exist and be a directory. Every extra bind appears on the launch line. |
| `SANDBOX_PROTECT` | REQUIRED. A colon-separated list of absolute paths that must exist (files or directories): the dataset file and the key-list directory. No slot, root or entry may equal one, contain one, or lie inside one. An unset or empty value is a named refusal, as is an entry that is empty, relative or missing. (It replaces the earlier `BEAM_PARQUET` special case: a guard that skips itself when its variable is absent is not a guard.) |
| `SANDBOX_MODEL_HOST`, `SANDBOX_MODEL_PORT` | The model endpoint as the host sees it (a port of 1024 or above: the listener inside the box is unprivileged). Inside, the student keeps using `localhost:<port>` unchanged. |
| `SANDBOX_MODEL_ALLOW` | Required unless `SANDBOX_MODEL_LEARN=1`. Comma-separated `METHOD /path` entries: an exact path, or a prefix when it ends in `*` (for example `POST /v1/messages, GET /v1/models, POST /api/*`). The outer forwarder forwards a request only if it is on the list. |
| `SANDBOX_MODEL_LEARN` | `1` allows every request the forwarder can frame and logs each request's METHOD and PATH only (never a body, never a query string) to `SANDBOX_LOG`, which it then requires. The pilot uses it once to learn the harness's real set; the registered run fixes the list in `SANDBOX_MODEL_ALLOW`. Any other non-empty value is a refusal. |
| `SANDBOX_LOG` | Optional file outside the box: one `wrapper-launch` line per launch (with the masked `/etc` file count), one `fwd-conn` line per bridge connection (open and close epoch seconds, bytes each way; never payloads), one `fwd-deny` line per refused request (METHOD and PATH), and in learn mode one `fwd-req` line per request. |
| `SANDBOX_TEST=1`, `SANDBOX_TEST_EXEC` | Tests only: run that shell command inside the same box instead of the binary, after every check and mount. With `SANDBOX_TEST=1` also: `SANDBOX_TEST_TMP_CAP` / `SANDBOX_TEST_HOME_RUN_CAP` (tmpfs caps in bytes), `SANDBOX_TEST_EXTRA_HOMES` (colon-separated stand-in home directories; it only adds refusals) and `SANDBOX_TEST_ALLOW_BINARY_IN_RW=1` (lifts the refusal of an RW root, RW entry or slot that contains the binary, so the mount order can be tested on its own). None is read outside test mode. |

Class rules, one function for the slot, each root and each entry, generated from the host at run time (no path is named in the launcher): refused when the path is `/`; is equal to or an ancestor of ANY home directory in the account database (all users, not only the invoker) or of the slot; contains the pinned binary (an RW root, RW entry or the slot; an RO root too); is equal to, contains or lies inside a `SANDBOX_PROTECT` path; touches a path the box itself provides (next paragraph); or lies below a home directory through any path component that begins with `.` (dot-directories hold secrets, ssh keys, config and the ENGRAM home). An entry outside its root is refused. The round-2 hand-listed protected paths are gone.

The box's own paths are ONE list in the launcher (`BOX_RO`, `BOX_PSEUDO`, `BOX_SHM`, `BOX_TMPFS_BIG`, `BOX_TMPFS_SMALL`, `BOX_ABSENT`, plus the directory the bridge socket is created in): the `bwrap` argument list is built from those arrays and the refusal reads the same arrays, and the launch line logs them as `box_paths=`. A cell compares that set with the destination paths of the argument list a dry run builds, so a mount added to one without the other goes red. For the system directories (`/usr`, `/bin`, `/sbin`, `/lib*`, `/etc`, `/proc`, `/dev`, `/dev/shm`, `/run`, and `/sys`, which the box leaves out) a slot, root or entry that is equal, inside or an ancestor is refused: a bind there would shadow the box's own mount (a slot of `/etc` re-exposes the host's real `/etc`; one under `/run/user` shows the user's sockets). For the fresh tmpfs directories (`/home`, `/tmp`, `/var/tmp`) and the socket base, only equal or an ancestor is refused: a bind placed beneath a fresh tmpfs shows only what the caller named, and the study's own slots and the tests live under `/tmp`.

Refusals (exit 2, one named line on stderr, nothing started or created): a missing or empty variable, a malformed hash or port or host, a port below 1024, a malformed or missing `SANDBOX_MODEL_ALLOW`, a malformed `SANDBOX_MODEL_LEARN` or learn mode without `SANDBOX_LOG`, a missing, empty, relative or non-existent `SANDBOX_PROTECT` entry, a slot that is not a directory or breaks a class rule, a missing binary, `bwrap` not on `PATH`, a hash mismatch, an extra-bind root or entry that breaks a class rule or lies outside its root, a missing root.

Inside the box: `/home`, `/tmp`, `/var/tmp` and `/run` are fresh tmpfs (capped: `/tmp` and `/var/tmp` 2 GiB each, `/home` and `/run` 64 MiB each); `/dev` is bwrap's own tmpfs (half of host RAM, uncapped by bwrap), so `/dev/shm` is a separate tmpfs with the `/tmp` cap and `/dev` is then remounted read-only, so the study lead's home, other homes, host sockets and the dataset path are invisible; `/usr`, `/bin`, `/sbin`, `/lib*` and `/etc` are visible read-only, plus the slot (read-write), the binary file (read-only) and any validated extra binds. `/opt` is NOT bound: no cell needs it and the real pinned binary runs without it; if the engram arm's stack lives under `/opt` the run script binds it with `SANDBOX_RO_BINDS`. `/etc` stays, minus what names other people: `/etc/passwd` and `/etc/group` are synthetic (root and the invoking uid and gid only; the invoker's home is the slot), `/etc/machine-id` is a fixed zero id, `/etc/hostname` is `sandbox` (the box has its own UTS namespace, so the kernel hostname agrees), and every other readable regular file under `/etc` whose content contains `/home/` or the name of any account with uid 1000 or above (nobody excluded) as a whole word, with any delimiter (a colon, a comma, a space, an equals sign, a quote, a line start; not preceded or followed by a letter or digit) is an empty file. System account names (uid below 1000) are not matched; short names over-mask, which fails closed. The set is found by scanning `/etc` at launch; the launch line carries its COUNT only. Plainly: `/etc` remains readable inside the box, minus the files that name people or agents; the synthetic `passwd` and `group` name the invoking account, by design. Symlinks are not followed (a symlink under `/etc` that resolves into a system directory shows that file as it is), and an overlay applies only where the host file exists. No host process is visible (own `/proc`), `--die-with-parent` and `--unshare-pid` end every descendant with the box, and the environment is exactly what the caller passed minus `SANDBOX_*` (`HOME` is the slot). Anything else the student must reach has to sit under the slot, in a system directory, or be bound explicitly (next paragraph); a path elsewhere is invisible by design.

The proctor channel: `feed4.py` puts its tools directory (where `ask-proctor` lives) on the student's `PATH` and sets `PROCTOR_DIR=<run out>/proctor`; both are outside the slot. The run script therefore sets `SANDBOX_RO_BINDS=<the tools directory>` with `SANDBOX_RO_ROOT=<its parent>`, and `SANDBOX_RW_BINDS=<the proctor directory>` with `SANDBOX_RW_ROOT=<the run's output directory>`, for the same launch, so `ask-proctor` runs from inside the box and writes only into the proctor directory. A cell runs a stub `ask-proctor` from a read-only-bound directory on `PATH` and checks that it writes into the read-write proctor directory on the host.

Network: a new namespace with loopback only. One forwarder inside listens on `127.0.0.1:<SANDBOX_MODEL_PORT>` and relays raw bytes over a UNIX socket bind-mounted from outside; a second, the outer forwarder, started by the wrapper and gone when the box exits, is trusted and is an HTTP request allow-list: it parses HTTP/1.1 requests on each connection (request line and headers; bodies by `Content-Length` or strictly chunked; keep-alive and pipelining, every request checked, not only the first), forwards a request only if its METHOD and decoded path are on `SANDBOX_MODEL_ALLOW`, and answers any other with `403` and a closed connection, so it never reaches the model server. A request it cannot frame (both length and chunked, two different lengths, line folding, a bare CR or LF in the head or in any chunk framing, an unsupported transfer coding) gets `400`, and so does any chunk extension, any whitespace in a chunk-size line, a chunk not ended by CRLF exactly, and any trailer: the last chunk is followed by the empty trailer only. Each piece of chunk framing is checked BEFORE it is forwarded, so none of a refused piece reaches the model server (a cell records the bytes the upstream receives). Only `HTTP/1.1` is served: a request line whose version is anything else (`HTTP/1.0`, `HTTP/2.0`, `HTTP/1.2`, ...) gets `505` and nothing reaches the model server; a request line that is not shaped like HTTP at all gets `400`; `CONNECT`, `Upgrade` and non-origin-form targets get `403`; a path with a `.` or `..` segment, an empty segment, a backslash, a control character or a second layer of percent-encoding never matches. Responses, streamed ones included, are relayed byte for byte. What the allow-list does NOT cover: it decides by method and decoded path only. It does not inspect bodies or query strings, so whatever an allowed request carries reaches the model server, and `SANDBOX_MODEL_ALLOW="POST /*"` allows every POST. Limit: a refusal of the second of two PIPELINED requests is written after the first request's response has been relayed, never in the middle of it. No other loopback port and no external address is reachable.

If the outer forwarder is SIGKILLed it cannot remove its socket directory (`student-sandbox.*` under `TMPDIR`, holding `bridge.sock` and `watch.pid`). That is a small leak by design: the NEXT launch removes every such directory it owns (a real directory owned by the invoker, never a link) whose watched pid is gone, touching only those two files.

Cost (S8): `python3 sandbox-forward.py latency-compare --wrapper PATH/student-sandbox.sh -n N`, with the `SANDBOX_*` variables of a real launch set and a server answering `GET /ping` on the model endpoint (the boxed run lists exactly `GET /ping`, whatever the real launch lists), prints `direct`, `bridge` and `added` lines (median and max milliseconds over N one-connection requests). Cells: `tests/test_student_sandbox.py`; `SANDBOX_TEST_REAL_BINARY` and `SANDBOX_TEST_REAL_BINARY_SHA256` enable one cell that runs a real pinned binary's `--version` through the wrapper.
