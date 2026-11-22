# Tool-capability probe: written expectations (before any run)

Written 2026-11-22 by Borges, before the probe has run even once. Script: probe.py in this directory
(sha256 in the covering message). Orders: Kepler 2026-11-22T19:30Z (cells A and B, his order 4 folded into B), Zephyr 2026-11-22T19:29Z.

## Command

    python3 probe.py --claude <pinned claude-2.1.328 binary> \
        --evidence <study lead's private probe folder>/evidence-<stamp> [--with-cell-c]

Claude Code 2.1.328 is the pinned binary of the P1 answering, P1b and cost-pilot runs. The pre-wrapper runs
also used 2.1.325 (run A, K1/K3/K5; no longer on disk) and 2.1.327 (controls 1-2). One version is measured.

## One change from the cleared design, and why (please read first)

Cell A was specified with "host network". I propose a private network namespace for EVERY cell instead
(`bwrap --unshare-net`: loopback only; checked from inside before the run, outside 1.1.1.1:443 -> errno 101,
the host's own 127.0.0.1:<port> -> errno 111, no DNS). Reason, read in 2.1.328's own code: before fetching,
WebFetch requests `https://api.anthropic.com/api/web/domain_info?domain=<host>` (skipped only by the
setting `skipWebFetchPreflight`). On the host network, cell A's scripted WebFetch would therefore send a
request to an outside address, which Zephyr's condition forbids. In the namespace that request fails at
name resolution and is recorded as the error it produces.

Cost of the change: what Anthropic's domain check would have answered for 127.0.0.1 during the pre-wrapper
runs is NOT measured (Zephyr's condition: the outside question is answered by reading routing and
firewall, never by firing a request). Optional cell C answers the other half (below).

## Set-up common to all cells

- Throwaway HOME per cell under <probe base>-<stamp>/, with `.claude/settings.json` = `{}` (as
  every arm home had). No plugins, no exam material. A directory the probe owns OUTSIDE the home per cell.
- The affected runs' argv: `claude -p --input-format stream-json --output-format stream-json --verbose
  --model qwen3.8:27b-128k --permission-mode bypassPermissions`, feed4's environment (local base URL,
  dummy token, telemetry and updater off). Added for every cell: `--mcp-config` with a 10-line stdio MCP
  server exposing one tool, `mcp__probe__probe_echo`, standing in for ENGRAM's MCP tools (the arm homes had
  ENGRAM as a plugin; installing it is out of scope).
- Stub model on loopback: scripted replies only. Turn 1: WebFetch http://127.0.0.1:T/a-ip; WebFetch
  http://localhost:T/a-localhost; Task (prompt: write one marker in $HOME and one in the outside directory,
  the sub-agent's own Bash call is scripted too); WebSearch "probe query". Turn 2: ToolSearch
  "select:WebFetch"; ToolSearch "select:mcp__probe__probe_echo" (positive control); WebFetch
  http://127.0.0.1:T/turn2-ip. Identical bytes in every cell.
- Target listener on 127.0.0.1:T and [::1]:T; it logs every request. Evidence is the listener's log, the
  stub's log of every request (whole bodies), the marker files, and the tool_result texts in events.jsonl;
  never the transcript's prose.

## Three outcomes kept distinct, per call

1. REFUSED BY THE HARNESS: the tool_result is an error and nothing downstream happens (no listener entry, no
   nested model request, no marker).
2. EXECUTED AND REACHED THE TARGET: the listener logged the GET / the marker exists / the nested request
   arrived at the stub.
3. EXECUTED AND ERRORED BEFORE THE TARGET: an error tool_result whose text names a step past dispatch (for
   WebFetch: the domain check or the connection), no listener entry. The error text is quoted.

## Cell A (the affected runs' flags; private network)

- A-1 WebFetch to 127.0.0.1: outcome 3, text containing "Unable to verify if domain 127.0.0.1 is safe to
  fetch" (the domain check cannot resolve api.anthropic.com). Listener: no entry for /a-ip. Confidence:
  moderate. I read the check and its message, not whether a failed check refuses or proceeds; if it
  proceeds, the listener shows GET /a-ip and the outcome is 2.
- A-2 WebFetch to localhost: outcome 1, refused before the domain check. In 2.1.328 the URL check next to
  WebFetch rejects a hostname with fewer than two dot-separated labels, and "localhost" has one. Confidence:
  moderate (I have not traced that this check is WebFetch's).
- A-3 Task: outcome 2. The stub receives a sub-agent request (its first user message carries the probe's
  prompt); the sub-agent's scripted Bash runs; both markers exist and read PROBE-MARK-A. High confidence.
- A-4 WebSearch: outcome 2 in the harness's sense: a nested request carrying a web_search server tool
  arrives at the STUB (the configured local endpoint), not at any outside address. Whether a local model
  server could act on it is not measured (expected: it cannot).
- Turn 2: ToolSearch for WebFetch reports it available (or already loaded); ToolSearch for the probe MCP
  tool loads it (positive control); WebFetch /turn2-ip as A-1.

## Cell B (cell A plus --disallowedTools naming the OFF set)

The list used: WebSearch, WebFetch, Task, Workflow, SendMessage, ListAgents, TaskStop, CronCreate,
CronDelete, CronList, ScheduleWakeup, Monitor (section 7's web, sub-agent, scheduling, wakeup and monitor
tools as they appear in 2.1.328's init lists; which of Workflow, SendMessage, ListAgents and TaskStop belong
to the OFF set is the design owner's to rule).

- Init record: exactly those twelve names absent compared with cell A's init list; every other name
  identical, including ToolSearch, Skill and mcp__probe__probe_echo.
- B-1, B-2, B-4: outcome 1 ("no such tool" class). Listener: no entry. No nested web_search request.
- B-3 Task: outcome 1; no sub-agent request at the stub; no marker in either place.
- Turn 2: ToolSearch "select:WebFetch" finds nothing to load; the following WebFetch is refused (outcome
  1); ToolSearch for the probe MCP tool still loads it (positive control inside B).

The discriminating result is A-3 writing both markers while B-3 writes none, from the same scripted bytes.
For WebFetch the A/B difference is expected to show in the REFUSAL TEXT (A: domain check; B: no such tool),
not in the listener, because the namespace stops A's domain check. That is the weaker contrast, hence C.

## Turn 3 in every cell (added after Kepler 2026-11-22T19:34Z, before any run): the shell in the background

Scripted: Bash `sleep 3; echo BG-DONE` with `run_in_background: true`, then the turn ends. The probe then sends
NOTHING for 20 seconds and records every stdout line and every stub request in that window.
- Expected: the background call is accepted (Bash is ON in every cell, so the same in B). Confidence: high
  (the parameter is in this version's Bash tool).
- The question that matters: does the completion START A TURN the proctor did not send? Read off the stub's
  log: any model request inside the silence window is such a turn. My lean, low confidence: NO in this mode;
  the completion is held as a notice and delivered with the next proctor message. I have not traced the
  headless delivery path; the 2.1.328 code has several queue-drain paths I did not read through.
- Meaning: if a request arrives in the window, the shell's background option breaks section 7's last clause
  ("no turn starts that the proctor did not send") and Kepler rules on it, TaskStop following. If none
  arrives in 20 s, that is evidence for this version and this mode only, at a 3-second task and a 20-second
  window; a longer-delayed delivery is not excluded.

## Revision after Zephyr's security read (2026-11-22T19:37Z), before any run

- The fetch target is now a RAW TCP recorder on 127.0.0.1:T and [::1]:T (peer and first bytes logged; byte
  0x16 = a TLS ClientHello), in every cell. Reason, Zephyr's read of 2.1.328: WebFetch rewrites http: to https:
  unconditionally and fetches the rewritten URL, so an HTTP listener could never log a GET, and cell C would
  have read as "loopback refused" whatever happened. The summarising-request path in the stub is now
  unreachable and stays unused.
- A-1: high confidence now (Zephyr's read: a failed domain check THROWS), outcome 3 with "Unable to verify if
  domain 127.0.0.1 is safe to fetch". A-2: high confidence (the dotless rule is WebFetch's own and runs before
  the domain check; error code web-fetch-dotless-host), outcome 1. Bound from the same message: it advises using
  Bash with curl, which the student had under bypassPermissions, so this rule never bounded loopback reach.
- C-1 (replaces the earlier C-1): the recorder logs a connection from 127.0.0.1 whose first byte is 0x16 ("the
  fetch step ATTEMPTED the loopback target"); the call then errors at TLS. If no connection is logged, the
  fetch step refused before connecting, a distinct outcome. Confidence: moderate.
- WebFetch to a loopback service in the pre-wrapper runs = THREE conjuncts: (i) the domain check allows the host
  (not measured: read, not fired), (ii) the fetch step attempts loopback (cell C), (iii) the target speaks TLS
  with a certificate the session trusts. A plain-HTTP local service fails at (iii) even if (i) and (ii) hold.
- Turn 3, reported as one of three classes (Zephyr): (i) the background command was terminated at the final
  response (statusMessage says so); (ii) it completed and a model request arrived inside the silence window
  (the answer to Kepler's question is then yes); (iii) it completed, no request, no termination marker (held, or
  delayed). Any request landing after the window, e.g. at stdin close, is classified separately by timestamp. My
  earlier lean (no unsent turn) is withdrawn as unsafe: the binary's own text documents delivery "by starting a
  new turn if you have already replied" for one mode.
- Containment gate, ENFORCED: before anything is bound, if 1.1.1.1:443 connects or api.anthropic.com resolves,
  the run stops (exit 5) with nothing started. The host service port check is informational only. The bwrap argv
  is written into the evidence (outer-argv.json); an evidence path inside the probe base is refused.
- Watchdog 900 s per cell (three turns of up to 240 s plus the 20 s window). The turn-3 criterion is the stub's
  own request log, not stdout (select() on a buffered pipe can miss buffered lines).

## Cell C (optional; NOT the affected runs' configuration)

Cell A with `{"skipWebFetchPreflight": true}` in the throwaway settings. It answers whether WebFetch's fetch
step itself refuses loopback once the domain check is out of the way.
- C-1 (127.0.0.1): outcome 2, listener logs GET /a-ip, and the stub receives WebFetch's summarising request
  carrying the page's marker text (the stub answers it, so "the summarising call succeeds" is a stub's
  answer, not qwen's). Low-to-moderate confidence: I found no loopback guard in the code I read, but I
  did not read the whole fetch path.
- C-2 (localhost): outcome 1, as A-2.
- C-3, C-4: as A.
If the setting is not honoured from user settings, C equals A, and that is recorded.

## What the result can and cannot say about the past

- Task: if A-3 writes both markers, a sub-agent would have worked in the pre-wrapper runs (same flags), with
  the reach of the account (the outside marker shows a write outside the home).
- WebFetch to loopback in the pre-wrapper runs = (Anthropic's domain check allows 127.0.0.1: NOT MEASURED)
  AND (the fetch step does not refuse loopback: cell C). Never stated as more than that.
- Bounds: one harness version (2.1.328), one host; no model (a scripted tool_use takes the dispatch path a
  model's would, Zephyr 2026-11-22T19:29Z); whether qwen would have formed a valid call is not measured (it never did,
  zero uses in 39 logs with tool calls); MCP stand-in rather than ENGRAM's own tools.

## Cleanup, verified and reported

Listener and stub stopped (servers shut down inside the namespace; the namespace ends with the run);
<probe base>-<stamp>/ removed and checked absent; `pgrep -af` for the base path empty before
and after; nothing written under <the host's shared agent directory>. Evidence kept under
<study lead's private probe folder>/evidence-<stamp>/ (events per cell, stderr per cell, the
probe log with the stub's request bodies and the listener's entries).

## Cells B4 and D, REVISED after Zephyr 2026-11-22T19:48Z (before either runs; supersedes the B4/D section written minutes earlier)

FIRST, the finding about the affected runs, which precedes any result of D (Zephyr 2026-11-22T19:48Z item 3): in 2.1.328 the harness
moves a foreground shell command to the background at its timeout ONLY when CLAUDE_AUTO_BACKGROUND_TASKS is set
(`autoBackgroundMs: !o && (s.CLAUDE_AUTO_BACKGROUND_TASKS || e?.armsMoveTimer?.()===!0) ? 120000 : void 0`, Zephyr's read).
No affected run set it (every launcher builds the student environment fresh), so the timeout-move route was OFF BY
DEFAULT in those runs. The armsMoveTimer branch is not read; the variable route is the one measured here.

Names exactly as in the script (the earlier message dropped prefixes; the binary reads only these spellings):
CLAUDE_CODE_DISABLE_BACKGROUND_TASKS, CLAUDE_CODE_DISABLE_CRON, CLAUDE_CODE_DISABLE_WORKFLOWS (the switches);
CLAUDE_AUTO_BACKGROUND_TASKS (the enabling variable, set in BOTH cells); CLAUDE_CODE_AUTO_BACKGROUND_TIMEOUT_MS (asserted
unset; it can only shorten the threshold).

Command: `python3 probe.py --claude <pinned claude-2.1.328 binary> --evidence <new evidence dir> --cells B4,D`
- B4 = cell B (twelve OFF names disallowed) + CLAUDE_AUTO_BACKGROUND_TASKS=1, turns 1-4. CONTROL.
- D  = B4 + CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1 + CLAUDE_CODE_DISABLE_CRON=1 + CLAUDE_CODE_DISABLE_WORKFLOWS=1.
  The switches are the only difference. The exact environment passed is logged per cell.
- Silence: 20 s after turn 3 (before turn 4 is sent), 60 s after turn 4.
- Shell timeout read from 2.1.328: `var a=120000,s=600000` (BASH_DEFAULT_TIMEOUT_MS / BASH_MAX_TIMEOUT_MS unset). Turn 4
  `sleep 150; echo FG-DONE` outlives the 120 000 ms default by 30 s.

Leg 1 (turn 3, background requested): B4 class (ii), as B. D: no unsent turn, reported as PREVENTION (run_in_background
absent from the Bash input_schema in the request) or ENFORCEMENT (present, refused or run in the foreground).
Leg 2 (turn 4, LOAD-BEARING): B4: moved to the background at 120 s (a task record with is_backgrounded true), the turn
ends, and the completion near 150 s starts an UNSENT turn inside the 60 s silence. Moderate confidence (Zephyr's read of
the gate). D: not moved; killed at 120 s with a timeout error in the tool result; no unsent turn. Moderate.
Kepler's condition is met only if D shows no unsent turn on BOTH legs AND B4 shows the hazard on leg 2 (otherwise the
switch is not shown to be what closes it).

Not measured here: by which route the two past foreground calls got task records. Read since: every foreground shell
call uses the session's tasks/ directory (the P1b tasks/ mtimes equal the last Bash result to the millisecond), so a
task record for a foreground call is bookkeeping, not a background move.

## Leg-2 RERUN (Kepler 2026-11-22T19:58Z item 2), written before it runs

Why: in run 20261122T195139Z the control B4 never exercised leg 2. Its turn-4 `sleep 150; echo FG-DONE` was refused at
dispatch by the shell tool's sleep guard (Zephyr's read of 2.1.328, 2026-11-22T19:59Z: threshold 25 s, first segment only, which
must be exactly a sleep). D ran the same bytes and was killed at 120 s, which is no test.

The ONE change: turn 4's command is now `python3 -c 'import time; time.sleep(150)'; echo FG-DONE` (first token not
sleep), byte-identical in both cells; no timeout parameter (the default is what the affected runs had). Cells B4 and D,
turns 1-4, environments, stub, namespace and silence windows exactly as in the 19:51:39Z run. probe.py diff: line 90 and
one comment.

Command: `python3 probe.py --claude <pinned claude-2.1.328 binary> --evidence <new evidence dir> --cells B4,D`

Outcomes, written in advance (the first three are Kepler's):
1. B4 moves the command to the background at about 120 s (a task record with is_backgrounded true, the turn ends) and
   its completion near 150 s starts an UNSENT turn in the 60 s window, while D kills it at 120 s with no unsent turn:
   the switch covers the armed route too. Kepler's condition met on both legs.
2. B4 is killed at 120 s as well: the route did not operate in this mode even with the enabling variable set. Two
   causes give this same observable and this run cannot tell them apart: the variable is not the gate we think, or the
   other conjunct (`!o`, unread; possibly the non-interactive flag) closes the route under `-p` regardless (Zephyr 2026-11-22T19:50Z).
   Then the assert-unset list is unproven as a barrier, and the switch is unshown on leg 2.
3. D moves the command to the background: the switch does not cover the timeout-move route; the assert-unset list is
   the only barrier, and the plan must say so.
4. (Mine, from the run before.) B4 or D refuses the command at dispatch, or it errors before running: instrument fault
   again, leg 2 still unmeasured; I report it as that and change nothing else without Zephyr's read.

My lean: outcome 1 for B4, low-to-moderate confidence. One new fact pushes it either way and I state it rather than
weigh it: in MY OWN interactive session today (installed Claude Code 2.1.329, entrypoint cli, none of the
CLAUDE_AUTO_BACKGROUND_TASKS / CLAUDE_CODE_AUTO_BACKGROUND_* / CLAUDE_CODE_DISABLE_BACKGROUND_TASKS variables set in the
shell's environment) a grep that ran past 120 s was moved to the background with "Command did not complete within its
120s timeout and was moved to the background". So the move happens WITHOUT the enabling variable in an interactive
session of a neighbouring version: the armsMoveTimer branch, or a mode default. Bounds: different version, interactive
not `-p`, and the variable read from my shell child, not from the harness process. Consequence for the plan, whatever
this run says: "off by default in the affected runs" must be stated as a fact about `-p` mode on 2.1.328 (if the
rerun supports it), not as a fact about the variable alone.
D: no move, killed at 120 s, no unsent turn. Moderate.

## Cell U (Kepler 2026-11-22T20:02Z (b), folds 2026-11-22T20:03Z; Zephyr 2026-11-22T20:02:50Z/2026-11-22T20:02:54Z), written before it runs

U = the affected runs' argv and environment, with the two deviations already bounded for cells A, B and C: the scripted
stub endpoint (no model) and the MCP stand-in. NOT the affected runs themselves, and not to be quoted as them.
Print mode, Claude Code 2.1.328, no --disallowedTools, none of the auto-background or disable variables, no switch,
no timeout parameter. It is cell A's entry in the plan table plus turn 4: `"U": dict(disallow=False, turns=(1, 2, 3, 4))`,
nothing else changed in probe.py. Turn 4 is the python nap of the leg-2 rerun.

Run: U alone, after the B4,D leg-2 rerun (already running when U was added) has finished and Zephyr has read the
one-line U diff. The cells are separate sessions with separate homes, so running U in its own invocation changes no
cell's configuration; the reading order is U, then B4, then D (Zephyr 2026-11-22T20:02Z).
Command: `python3 probe.py --claude <pinned claude-2.1.328 binary> --evidence <new evidence dir> --cells U`

FIDELITY CHECK FIRST (turn 3): with nothing disallowed, the background call runs and its completion starts an unsent
turn at about 3 s, as cell A did at 19:38Z. Reported as "U reproduces the affected configuration". If it does NOT
reproduce: STOP, no other conclusion of U is drawn until that is explained. Turns 1-2 should match cell A's rows too
(Task launches and writes both markers; WebFetch to 127.0.0.1 errors at the domain check; localhost refused).

Leg 2 (turn 4), outcomes written in advance:
U1. U moves the python nap to the background at about 120 s and its completion near 150 s starts an UNSENT turn in the
    60 s window: past runs WOULD have had this route open. Then the launcher's assert-unset list protects nothing by
    itself, the switch must carry it, and D quiet on leg 2 is REQUIRED for Kepler's ruling to stand (if D moves too, he
    rules again).
U2. U kills the nap at 120 s (exit 143, "Command timed out after 2m 0s"), no unsent turn: under -p on 2.1.328 with no
    variable the route did not operate; the plan sentence is Zephyr's (route unmeasured in the affected runs before
    this cell; not gated by the variable alone, per the interactive 2.1.328 record).
U3. Refused or errored at dispatch: instrument fault, leg 2 unmeasured for U.

My lean: U2, moderate-low. The interactive 2.1.328 record (INTERACTIVE-MOVE-RECORD.md) shows the move without the
variable in an attended interactive session; Zephyr's read names a second conjunct that may close it in print mode.
That the same version moved my command interactively makes U1 more plausible than I would have said an hour ago.

### Reading matrix for leg 2 (Zephyr 2026-11-22T20:05Z), written before U runs and before the B4/D rerun evidence is read

The statements depend on two cells, U (affected configuration) and B4 (U's environment plus the enabling variable and
the twelve disallowed names), so they are written as a matrix; D is then read against it.

| U (no variable) | B4 (variable set) | meaning |
|---|---|---|
| moves | moves | the move is the print-mode default on 2.1.328; the enabling variable is irrelevant; D quiet on leg 2 is NECESSARY for Kepler's ruling to stand (if D moves, he rules again) |
| killed at 120 s | moves | the variable arms it; D quiet shows the switch closes the armed route (outcome 1 as first meant); the affected runs' route was closed in print mode |
| killed at 120 s | killed at 120 s | outcome 2: the route did not operate under -p on 2.1.328 even with the variable set; two causes, one observable, this run cannot separate them; the assert-unset list is unproven as a barrier |
| moves | killed at 120 s | CONTRADICTION (the baseline moved, the armed cell did not): instrument fault or ordering; stop and explain before writing anything else |

Any cell refused or erroring at dispatch is outcome 4 (instrument fault) for that cell, and its row of the matrix is not
read. The turn-3 fidelity check on U gates the whole matrix (stop rule above).

Correction to my lean paragraph in the leg-2 section above: the interactive session was Claude Code 2.1.328, NOT
2.1.329 (I read `claude --version`, which reports the newest installed binary). INTERACTIVE-MOVE-RECORD.md is the
record; the text above is left as cleared and this line is the correction.

## Cell S (Zephyr 2026-11-22T20:14Z), written before the change and before it runs

Why: no cell yet has the scored launcher's own configuration. The launcher sets the three switches and asserts the
enabling variable UNSET; D measured the switches only WITH the variable set, U has neither, B4 the variable without
switches. So in the launcher's configuration both legs are unmeasured.
S = U's entry plus the three switches: `"S": dict(disallow=False, turns=(1, 2, 3, 4), extra_env=SWITCHES)`; no
--disallowedTools (as U and the affected runs), no enabling variable, no timeout parameter. Bounds as for U: scripted
stub, MCP stand-in, 2.1.328, print mode, one run.
Run: alone, after U's evidence is read and Zephyr has read the S diff (which also fixes the --cells help text to list U
and S).

Expectations:
- Turns 1-2: as cell A/U (nothing disallowed): Task launches and writes both markers; WebFetch to 127.0.0.1 errors at
  the domain check; localhost refused. The three switches are not expected to change these rows; if they do, report it.
- Leg 1 (turn 3): PREVENTION, as D: run_in_background absent from Bash's schema in every request, the call refused at
  input validation, no task, no unsent turn. Confidence moderate-high (schema removal looks like a property of the tool
  definition under the switch; measured so far only with the variable set).
- Leg 2 (turn 4): killed at 120 s (exit 143), no move, no unsent turn. Confidence moderate. If U moves (U1 row of the
  matrix), S quiet is what the launcher needs; if U is killed, S quiet adds less (nothing to close) and the switch's
  coverage of an unarmed print-mode route stays argued from D, not shown.
- Any move or unsent turn in S: the launcher's configuration is NOT covered; report first, nothing else written.
- Init record: skills lack loop, workflow-authoring and deep-research, as D.

---

# Correction, 2026-11-22 (study lead; appended after the security seat's end-to-end read of this file)

The opening of the revised B4/D section ('FIRST, the finding about the affected runs', from Zephyr 2026-11-22T19:48Z item 3) says
the timeout-move route was OFF BY DEFAULT in the affected runs. Its author withdrew that finding before cell U ran
(Zephyr 2026-11-22T20:02Z/2026-11-22T20:04Z), and cell U measured the opposite: in print mode on 2.1.328 a foreground shell command past its
120 s default is moved to the background with no enabling variable set, and its completion starts a turn the proctor
did not send (RESULT.md, cell U). The text above is left as cleared; this section is the correction.
