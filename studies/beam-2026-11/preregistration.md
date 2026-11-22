# BEAM study: pre-registration (DRAFT v0.2, NOT registered)

Lead: Borges (lab owner, teacher). Design owner and co-signer: Kepler. Decisions by Lei (project lead).
Registered when Kepler co-signs and the OPEN list's first two groups below are closed (its later groups belong to
later phases). Until then this file is a draft and changes freely; after registration every change goes in the
Deviations log with date, reason and who ruled.
The decision history behind each rule is in [PROVENANCE.md](PROVENANCE.md).

**No scored run happens before registration, and none before the entry gate (section 5) is met.**

## 1. Question

Does ENGRAM, as shipped, improve a small local model's memory of a long conversation it watched,
compared with the same model in the same harness without ENGRAM?

First sub-question (Lei): does qwen3.8:27b use ENGRAM's tools at all, out of the box?

## 2. Hypotheses (stated before any scored run)

- H1 (primary): arm 2's OFFICIAL overall score on the scored conversations of the 100K split is higher
  than arm 1's (scored by the question-seeing judge of section 10).
- H0: no difference, or arm 1 higher. A null or a loss is a publishable result.

## 3. Arms

| arm | condition | differs from arm 1 by |
|---|---|---|
| 1 | Claude Code as shipped: built-in memory, note files, compaction | nothing |
| 2 (primary) | arm 1 + a fresh ENGRAM install (named release, default tier) | the ENGRAM plugin and its instruction profile |

- After the tool-reachability work (PROVENANCE, 2026-11-14) there is ONE arm 2: the shipped release.
  An earlier "tools loaded up front" secondary arm was dropped. The pre-registration names the exact
  release or commit the ENGRAM arm runs.
- Two arms (the project lead, 2026-11-18). A trained third arm is a possible later study; it would enter by an
  amendment registered before its runs.

## 4. Instruction files (identical where they must be)

- **Exam line**, byte-identical, at the top of the student's user-level `CLAUDE.md` in every arm
  (proposed text; its sha256 goes here when frozen):
  > In this deployment your job is to take memory exams. Facts from exam material are worth keeping in
  > your long-term memory, so that you can answer questions about them after your context is compacted.
  > You may use any tool and any file on this machine, including the records your own tools keep. You
  > may not use the web.

  It is method-neutral: each arm has a long-term memory, and the line names none of them. What the
  study then measures is each setup *when the user has said this material matters*.
- **What the student may use** is the exam line's last two sentences, Lei's wording (A) (2026-11-14): the rule is
  told to the student, not only enforced by the sandbox. In the book-closed runs (section 13) the third sentence,
  and only it, is replaced (the design owner, 2026-11-22): "You may use any tool and any file on this machine,
  including the records your own tools keep, with one exception: do not open the saved transcript of this session
  or any copy of it." It names no path. Before it is hashed, the study lead checks that 'the saved transcript of
  this session' is what the students call it in the tuning transcripts; if not, it is reworded once.
- **Each arm's own memory practice.** The earlier condition of comparable length is withdrawn
  (Amendment 2 in the tuning log): it cannot hold together with existing components only and no exam
  prose. Token counts are in the student model's tokenizer (Qwen3.8-27B):
  - arm 1, 182 tokens: the best honest instruction for plain Claude Code's own memory, taken from Claude
    Code's documentation and cited line by line, then improved by a seat outside the study (Ariadne),
    who judged that the documentation supports no more for this task. The text:

    ```
    ## Your long-term memory

    You have an auto memory directory that persists across sessions. Its index, MEMORY.md, is loaded
    at the start of every conversation and re-injected from disk after your context is compacted.
    When your context is compacted, the conversation is replaced by a summary, so anything kept only
    in the conversation can be lost.

    - Write a fact to auto memory when you learn it, not later: one topic file per memory, and one
      line per memory in MEMORY.md saying what it holds and where.
    - Keep MEMORY.md short, well under 200 lines and 25KB: only its start is loaded. Put detail in
      topic files; merge or drop stale entries.
    - Topic files are not loaded automatically. Before you answer from memory, read MEMORY.md and
      open the topic files it points to.
    ```
  - arm 2, 3,284 tokens: ENGRAM's lean `CLAUDE.md` profile, shipped as a product option (a lean profile
    for small-context models): a second manifest over existing template components, no prose written
    for the exam, keeping the paragraph that outward actions need the user's say-so and that the file
    claims no consent the user has not given. Under review as engram#4802; the release that ships it,
    and the file's sha256, are named here when frozen. The full template is 8,593 tokens.
  - A stated bound (section 15): arm 2 carries about 3,000 tokens of standing instruction against arm
    1's 182, as each product ships. Arm 1 is not padded.

## 5. Entry gate (Lei; defined by Kepler as design owner)

The scored benchmark starts only when the student **reliably uses ENGRAM for note taking**. If it does
not, the cause is found first. "Reliably" means all of the following, on the exact setup to be
benchmarked (as amended, Amendment 1 in the tuning log):

1. **Writing, short runs.** In 3 of 3 short tuning runs, at least 2 of every 3 reading exchanges carry a
   successful ENGRAM write, counted per run, not pooled across runs. Every run's store is saved and read:
   "successful" means the node exists in the store after the run and carries content from that
   exchange. The transcript saying it wrote does not count.
2. **Recall, one long run only.** Recall is tested only where a compaction summary cannot carry the
   reading: a tuning run long enough that at least one compaction happens naturally during the reading,
   before the forced one (sized by tokens, or a whole seed-drawn tuning conversation). In that run,
   writing holds as in (1), and after the forced compaction the student makes at least one ENGRAM recall
   that returns a node written during the reading BEFORE it answers, on at least half of the practice
   questions that have an answer. A right answer from the summary alone does not count.
3. "The exact setup" means the same commit, the same instruction texts and the same brief, by hash. Any
   change after the gate is met re-opens it.

This gate is stricter than the reachability criterion in the tuning log (2 of 3 runs, one write and
one read), which judged single tuning experiments and never the start of the benchmark.

**Stop rule.** Tuning may change only what a user or a release could change (tool reachability, the lean
profile, the user-level line). If the gate can only be met by telling the student to use ENGRAM by name,
or by changing what ENGRAM's own nudges are for, tuning stops and the question goes to Lei: that is a
design decision, not a tuning knob. "Not met, and here is why" is a publishable result.

## 6. Tuning rules (Kepler)

- Tuning conversations are kept apart from scored ones. Conversation 15 of the 100K split, used by
  every practice run so far, is a tuning conversation and is not scored. More tuning and training
  material is drawn from a public randomness beacon, never chosen by how it looks; the drawn conversations
  are listed in section 9.
- No arm-versus-arm accuracy is computed on anything during tuning. The gate is read off transcripts as
  process (does it write, does it read back); practice questions only show that the pipeline runs.
- Every change made to get ENGRAM used, to the product or to an instruction, is logged publicly in
  [data/tuning-log.md](data/tuning-log.md) with what it was, why, and what arm 1 got as its equivalent.
  Arm 2 may be helped only in ways a user or a release could help it.

## 7. Student and harness (fixed for every scored run)

- Model `qwen3.8:27b` Q4_K_M served by Ollama 0.33.2 as a variant with `num_ctx` 131,072 (the server's
  default context for these requests is 32,768). Server sampling defaults (temperature 1, top_k 20,
  top_p 0.95). Claude Code 2.1.325 on Ollama's Anthropic-compatible endpoint. Versions recorded per run.
  [the version of the scored runs is fixed at the freeze; every measurement in this section is on 2.1.328]
- One persistent Claude Code print-mode process per exam (stream-json input), permission mode bypass,
  each run in its own sandbox home outside any git repository, never on a real user's memory graph.
- Arm 2: ENGRAM's first session runs BEFORE the exam as its own session, driven by a fixed
  proctor fact sheet (identical every run, nothing from any BEAM conversation). Its cost is reported
  once as setup, outside exam timing. Arm 1 has no equivalent step.
- Arm 2's recall service (the project lead's decision of 2026-11-21). The sandbox has no service manager, so the
  release's own launcher cannot start ENGRAM's recall daemon there; in the cost pilot every prompt then fell back to
  keyword search. The harness therefore starts the arm's own daemon inside the sandbox with the release's own launch
  command before the student starts, starts the student only once the daemon answers, and stops it before the store is
  saved. The arm states whether it expects the daemon; the launch separately derives, from the arm's home, whether the
  daemon is installed there, and a launch where the statement and the derived value differ is stopped before any exam
  begins, in a record naming both. The daemon's readiness and its stop are in the run's log; a launch whose daemon
  never became ready is stopped before any exam begins. After each session the launch module's own record states the
  daemon's process id and that no process still holds its socket (the design owner's requirement of 2026-11-22), so no
  manual check carries it. Pilot evidence, not scored, one stretch of one conversation: on 2026-11-22 two sessions
  with the harness-started daemon (3 exchanges, then 23 exchanges through 13 automatic compactions) had every proctor
  prompt answered by semantic recall, none by the keyword fallback, read from the recall event ENGRAM's prompt hook
  writes for each prompt (all 26 with the fallback flag false, including the prompts after each of the 13
  compactions).
- One GPU, exclusive per run; the model is unloaded after every run.
- Tools, identical in both arms (Kepler, as amended for Lei's full-capabilities core). OFF, by twelve names passed to the
  harness's disallow option: CronCreate, CronDelete, CronList, ListAgents, Monitor, ScheduleWakeup, SendMessage, Task,
  TaskStop, WebFetch, WebSearch, Workflow. That is web search and fetch (also told to the student, section 4);
  sub-agents, a stated limit (one student, one window; and an ENGRAM sub-agent writing into its parent's memory is an
  open hazard, engram#1989); scheduling, wakeups, background monitors and stopping background tasks (no turn starts that
  the proctor did not send). ON: file tools and the shell; in arm 2, ENGRAM's tools as the release ships them. The
  disallow option binds at dispatch: a named tool is refused even when called by name, while a tool merely absent from
  the list the model sees can still be called (cells A and B below), so that list is never read as the closed set. The
  OFF set is verified per run from the session's first record (exactly the twelve names absent); a launch whose tool
  list differs is a harness defect, not a run (section 14).
  The shell's own routes to a turn nobody sent. The OFF set does not close them, because the shell stays on: on Claude
  Code 2.1.328 in print mode, a shell command the model asks to run in the background, and a foreground command moved to
  the background at the shell's 120-second default limit, each start a turn the proctor did not send when they finish
  (cells A, B, B4, U). Both arms therefore run with three harness switches set in the student's environment:
  CLAUDE_CODE_DISABLE_BACKGROUND_TASKS, CLAUDE_CODE_DISABLE_CRON and CLAUDE_CODE_DISABLE_WORKFLOWS. With them the shell's
  input schema has no background option, so such a request is refused at input validation, and a foreground command
  past the limit is killed at 120 seconds instead of moved (cells D and S). The launcher also asserts unset every
  auto-background variable the binary reads; that is a second barrier only (cell D was quiet with the enabling variable
  set): the switches are what protect the run. The background switch changes HOW a sub-agent runs (in the foreground
  instead of asynchronously), not WHETHER it can: in cell S a sub-agent ran with the switches on and wrote outside the
  student's home. Sub-agents are closed by the OFF set alone, and nothing in this plan reads "background disabled" as
  a statement about sub-agents. The skills missing from the session's first record in cells D and S (loop,
  workflow-authoring, deep-research; all three present in cell U) are second signs that the switches reached the
  run; no cell set one switch alone, so which switch removes which skill is not measured. The background switch's
  own sign is the shell's schema with no background option, which the forwarder checks on every request (below).
  Default and measurement, kept apart. On 2.1.328 in print mode the 120-second move to the background is the default
  (cell U: the past runs' arguments and environment, with the probe's scripted model and a stand-in MCP tool); on
  that version it was open in the configuration every run before this rule used, and no occurrence of it was found
  in them, to the table's bound (2.1.328 only; those runs also used 2.1.325 and 2.1.327, not measured; PROVENANCE,
  Corrections, 2026-11-22). The shell's sleep guard, an observation on 2.1.328 and not a guarantee.
  Measured, one pair: a bare sleep of 150 seconds was refused with the background option available (cell B4) and ran
  with it disabled (cell D). Read from the binary, not measured: the guard matches only a first command segment that
  is a bare sleep over 25 seconds; whether the refusal depends on the background feature is not established. With
  the three switches set (cell D, which also had the enabling variable set) the guard did not refuse it: the bare
  sleep ran until the shell's 120-second kill; no cell ran a bare sleep in the scored configuration (cell S's long
  command was not one). The 120 seconds are only the default (a call may ask for up to 600), and short commands
  chain, so nothing here stops a student stalling a turn; section 14's turn-timeout rule is neither weakened nor
  settled by it.
  The proctor's reader. It matches each result to the turn it sent, so the result of a turn nobody sent can never be
  read as the answer to the next question, and it bounds its own wait, so a silent harness cannot stall it past the
  turn timeout; what a timed-out turn then means is section 14's rule. (The readers used before this rule returned the
  first result after a send; no occurrence of a turn nobody sent was found in those runs, to the table's bound:
  2.1.328 only, and those runs also used 2.1.325 and 2.1.327; PROVENANCE, Corrections, 2026-11-22.)
  Checked on every request, not once per run. The model-endpoint forwarder parses a copy of every request body (bounded
  size and nesting depth, never evaluated, never logged) and forwards the original bytes unmodified. It refuses a
  request whose body does not parse (invalid UTF-8 and duplicate keys included), has no tools list, has no Bash tool,
  or whose Bash input schema has run_in_background anywhere; it scans every tool entry and the whole schema, and a
  schema shape it cannot read (two Bash entries, a reference, a composition) is refused, never resolved. Each refusal
  is a line the harness writes outside the box, with its class (unparseable, no tools list, no Bash, run_in_background
  present, unsupported schema shape), the request's index counted from the launch's first request, and the Bash
  property names seen (names only, nothing of the body); a refusal is distinguishable from a transport error. An exam
  counts only if the forwarder wrote a pass line for the launch's first request; with none, the launch did not start
  under this rule: it is a launch stopped before any exam begins, handled by section 14's rule for that case. A
  forwarder that dies later leaves transport errors, which silence the model like a lapse; that is the model endpoint
  dying during a run, and section 14's rule for it applies (the design owner decides re-run or keep), with the last
  pass line's index recorded. Cells
  before the freeze, built with the launcher: a request whose Bash schema carries run_in_background is refused; one
  without it passes; a malformed body and a body with no Bash are refused; an always-pass mutant of the check reddens
  the first of these; and the harness's own real request, taken from a dry-box launch, passes, so the stricter parser
  is shown not to refuse every legitimate launch. The study's rule for refusals:
  (a) a refusal on a launch's first request refuses the launch (nothing of the exam has gone upstream, and in that
      launch the student has had no turn); it is a launch stopped before any exam begins, handled by section 14's
      rule for that case;
  (b) a later isolated refusal refuses that request only: the exam is kept, counted, and reported with the class and
      the launch-relative index;
  (c) a lapse is PERVASIVE when every request from some index k to the launch's last has the same class and the same
      Bash property names. The run is MARKED configuration-suspect (a mark, not a section 14 flag: the run stays in
      the primary analysis, kept and counted), and the mark is reported beside the primary contrast with the count
      of launches lost to such a halt; further launches halt until the design owner and the security seat have the
      explanation (no score is touched).
  Every run's record carries its count of turns nobody sent, with those after a lapse's onset counted separately.
  After the onset that count is a verification expected to be zero (every request is refused, so the model gets no
  turn); a nonzero count means a request reached the model without passing the check, and it halts launches like a
  pervasive lapse. Cost, stated: a genuine lapse silences the model for the rest of that exam, and the arm carries the
  unanswered questions in the primary analysis. It is a harness fault counted against the arm, uniformly, because the
  alternative is a re-run a student could reach; the mark and the count of turns nobody sent let a reader see the
  penalty came from the harness. Limit (OPEN list): the forwarder cannot tell a forged request from the harness's own.
  Before the freeze, the scored launcher's own dry-box cell, in the launcher's real arguments and environment (the
  twelve-name OFF set, the three switches, the auto-background variables unset), no model: both routes (the model's
  background request; a 150-second foreground command that is not a bare sleep, no timeout parameter), and the probe's
  scripted first turn, whose sub-agent call writes one marker in the student's home and one outside it. No marker may
  appear: their absence shows the OFF set reached the run, and cell S (the same turn, both markers written) is the
  paired positive control, so the absence is not the instrument's silence. Both marker paths are checked and what was
  found at each is recorded. No probe cell ran this whole configuration at once (D has the OFF set and the switches
  with the enabling variable set; S has the switches with the variable unset and no OFF set); they bracket it. The
  registration cites the dry-box cell, not the probe.
  The probe, 2026-11-22 (scrubbed copies of its records in data/probes-2026-11-22/, with their redaction record). One
  run per cell; every cell's expectations were committed before it ran, and the security seat read them before each
  run except the first, where its read was of the version before its own five requested fixes (redaction record,
  and the dated correction at the end of RESULT.md). Every cell:
  Claude Code 2.1.328 only (the runs before this rule also used 2.1.325 and 2.1.327, which were not measured), print
  mode, one host, a private network namespace, a scripted model (so whether the student would form these calls is not
  measured), a stand-in MCP tool in place of ENGRAM's. In the table's last column, the eight characters after the
  line range are the first eight hex digits of the sha256 of those lines of the published RESULT.md.

  | cell | configuration | the model asks for a background shell | a 150 s foreground command | sub-agent | RESULT.md section |
  |---|---|---|---|---|---|
  | A | the past runs' flags: no disallow option, no variable, no switch | ran, finished about 3 s later; a turn nobody sent began at once | not run | ran (asynchronously); markers in the home and outside it | lines 1-99, 7d332529 |
  | B | A plus the disallow option with the twelve names | as A | not run | refused at dispatch; no marker | lines 1-99, 7d332529 |
  | C | A plus the fetch preflight off (not a configuration any run used) | ran; a turn nobody sent | not run | as A | lines 1-99, 7d332529 |
  | B4 | B plus the auto-background variable | ran; a turn nobody sent | NOT MEASURED: the command was a bare sleep and the sleep guard refused it | not reported (the twelve names disallowed, as in B) | lines 100-156, cd24ffaa |
  | D | B4 plus the three switches | refused at input validation; nothing ran | killed at 120 s, but its control (B4) never ran the command, so this is no test | not reported (the twelve names disallowed, as in B) | lines 100-156, cd24ffaa |
  | B4, rerun | as B4; the long command is a python nap | ran; a turn nobody sent | moved to the background at 120.1 s; a turn nobody sent 29.9 s later | not reported (the twelve names disallowed, as in B) | lines 157-186, e1fa8e5b |
  | D, rerun | as D; the same python nap | refused at input validation | killed at 120 s (exit 143); no further turn | not reported (the twelve names disallowed, as in B) | lines 157-186, e1fa8e5b |
  | U | the past runs' arguments and environment (as A) plus the long command | ran, finished at 3.0 s; a turn nobody sent began at once (fidelity check: U reproduces A) | moved at 120.1 s; a turn nobody sent 29.9 s later | as A | lines 187-233, 5f94894c |
  | S | U plus the three switches, variable unset, no disallow option | refused at input validation | killed at 120 s (exit 143); no further turn | ran in the foreground; markers in the home and outside it | lines 234-266, 32891114 |

  RESULT.md's two sections appended after the reads (a correction of its lines 3-4, and an addition on the skills in
  the session records) are part of the published file and are not rows of this table.
  Every registered run goes through the student wrapper (tools/student-sandbox.sh), once it is
  merged with its colleague read (OPEN list); a scored run without it is flagged (section 14). Inside the
  wrapper the shell has no network: nothing leaves except requests to the model endpoint, through a bridge
  with a method-and-path allow-list. The security seat measured this inside the box (loopback only; the
  host's ports refused; an outside address unreachable), in its approving review of PR #13. The wrapper's test
  `test_s4_no_other_loopback_port_and_no_route_out` fails if the box reaches a named outside TCP target or a
  host loopback port; it does not cover IPv6 or UDP, and it skips where the box cannot run (no sandbox tool,
  or unprivileged user namespaces unavailable). Because a skip would look like a pass, before the first
  scored run that test is run on the study host and its PASS (not a skip) is logged with the date and the
  wrapper file's sha256. A blocked attempt cannot succeed, so it is not a fault (section 14). Four counts are
  reported per arm instead. Three come from the wrapper log (SANDBOX_LOG, always enabled in registered runs), where
  the bridge writes exactly one line per refused request or connection at the moment it refuses it, carrying `kind=`
  and `reason=`; each count is the number of lines of one kind, read off the `kind=` field alone. A request is counted
  once, by the first refusal the bridge makes for it, in the order the wrapper's README states as found in its code.
  The kinds are defined by class. The wrapper's own test derives every refusal site from the wrapper's source and
  fails on a site with no kind, so a reason added later cannot land in no kind. The wrapper README's per-reason
  table lists the reasons under their kinds (complete at the head at which the wrapper's pull request, #13, is merged;
  this preregistration change merges after it).
  RULE REFUSALS (`kind=rule`): requests the bridge could parse but refuses by rule (for example a method or path not
  on the allow-list, a path it will not accept, CONNECT, an upgrade, `Expect: 100-continue`, a target not in origin
  form, a fragment). FRAMING REFUSALS (`kind=framing`): requests the bridge could not parse as HTTP/1.1. CAP REFUSALS
  (`kind=cap`): refusals that protect the bridge against volume (for example the request head or a chunk-size line
  over its size limit, a request over the per-request or total buffered-bytes cap, a connection past the connection
  cap, refused before any request is read, and a request left half-sent past the idle read timeout). The fourth is
  NETWORK-CAPABLE SHELL CALLS, counted from the transcript, whether or not anything was reached, by a rule fixed
  before the first scored run. Lines of a fifth kind, `upstream`, record the bridge's own trouble with the model
  endpoint (reasons: connect-failed, send-failed, upstream-reset, rejected-early); they are not network counts and never a
  student attempt. They are reported per arm as UPSTREAM ERRORS, counted off `kind=upstream` like the other three, with the
  `reason=` breakdown beside it; it is descriptive, in that no reason decides anything by itself (each line is examined
  in the report), and only section 14's flag rule can make an unreachable endpoint a harness fault. The bridge decides
  rejected-early (the endpoint answered before the request was fully sent) from the response bytes relayed since that
  request's send began, so a client that pipelines requests can be mislabelled between rejected-early and send-failed;
  no reason flags a run, so a wrong label can distort only this descriptive breakdown. The per-reason breakdown is reported beside the counts as description, never as an
  outcome. (Amended 2026-11-20, design owner: the count named ALLOW-LIST REFUSALS when this section was merged is
  renamed RULE REFUSALS, because it holds more than allow-list misses; FRAMING REFUSALS and CAP REFUSALS are added,
  because a request the bridge refused as unparseable or over a cap landed in neither registered count. Found by the
  colleague reviewer of PR #14.)

## 8. Procedure (one exam = one conversation, one arm)

1. New session. The first user message is the brief (fixed text, [protocol/exam-room.md](protocol/exam-room.md))
   plus exchange 1. Then one BEAM user/assistant exchange per user message, in order, in the marked
   reading-material format. The student ends each turn with NEXT.
2. After the last exchange the proctor sends `/compact` (the same command in both arms). ENGRAM's
   pre-compaction behaviour runs as shipped, untuned.
3. Post-compaction record: how much raw conversation text survives the forced /compact in the window (the
   student's own words are allowed), read off the compaction record's preserved messages. A measure reported
   per exam in both arms, never a flag: the summary is the student model's own writing (the design owner,
   2026-11-22). Its counting rule is on the OPEN list.
4. The conversation's 20 probing questions, one per user message, in the dataset's order, in the same
   session. The answer is the text of the student's final reply to that message.
5. Escalation: the student may run `ask-proctor`; the proctor answers harness and environment questions
   only, never content. Every question and answer is logged with UTC times.

## 9. Data

BEAM 100K split (Hugging Face `Mohammadta/BEAM`, parquet sha256 prefix `c0519be25907`), 20
conversations, 97,252 to 190,209 Qwen tokens each, 20 probing questions each, CC BY-SA 4.0. Scored set:
17 conversations, ids 1 to 8, 10 to 14 and 16 to 19. Never scored: conversation 15 (tuning, every practice
run before the draw) and conversations 9 and 20 (drawn for entry-gate runs and lean-profile tuning). From the
500K split (parquet sha256 prefix `af05921c9793`), conversation 21 (drawn for arm-3 training;
unused, since this registration has two arms) and conversation 30
(length-stress tuning). Book-closed second runs (section 13): scored conversations 12, 16 and 5. All were
drawn on 2026-11-15 from drand round 6642370, announced in a published commit before the round existed;
see [data/draw-rule.md](data/draw-rule.md) and [data/draw2-result.json](data/draw2-result.json). An earlier
draw (draw 1) is void: its seed could be re-rolled by its committer.

## 10. Scoring

Two judges, named by the one thing that differs between them (the project lead's request of 2026-11-18):

- **Question-seeing judge**: the judge is shown the question, the rubric item and the response. This is the prompt
  printed in the benchmark's paper (Listing 20). It is this study's judge for both the OFFICIAL and the ADJUSTED
  score.
- **No-question judge**: the judge is shown only the rubric item and the response, never the question. This is what
  the benchmark's released evaluation code does. In this study it is run only in the known-answer
  check, never on scored benchmark items.

- Judge: Claude Sonnet, which the project lead asked to try first on 2026-11-16, its cost to be measured on a pilot;
  the pilot ran the same day. Every judge call pins the model id `claude-sonnet-5-5`, through the first-party API, at
  effort low, one call per rubric item, with no temperature setting: the settings the design owner fixed for P1's
  grading on 2026-11-19 (tuning log, entry "Judge settings, fixed now", which reaches main with the study record).
  The same for every arm, with the paper's rubrics unchanged. Every call records the model that served it; a call
  served by another model is reported, not dropped, and the number of such calls is reported per arm beside the
  score (the judge is never told the arm, so they should fall evenly; the count lets a reader see that they did). A
  refusal or an unparseable reply is recorded with an empty score and reported. The judge is never told the arm.
- Paper over code (the project lead's rule): where the benchmark's peer-reviewed paper (published at ICLR 2026,
  per the paper's own header) and its released code
  clearly contradict each other (the paper states something at a location we can cite, and the code does
  otherwise), this study follows the paper. Where the paper is silent or ambiguous, or two places in the paper
  disagree, the released code stands, and a case of the last kind is listed as unresolved. Every application of
  this rule is listed here with its paper location and its code location, and is declared before the first
  scored run, never chosen after a result is seen. Applications so far: one, the judge prompt (next bullet). Cases
  where the paper is silent and the released code therefore stands are listed the same way: one, how an Event
  Ordering answer is cut into items (the Event Ordering bullets below).
  Partial credit is not one: the paper scores each rubric item 0, 0.5 or 1, and the current code parses the
  judge's score as a number (at b2da22e every score conversion of the earlier code, `int()`, upstream issue 8,
  became `float()`), so the paper and the current code agree.
- The question-seeing judge's prompt, used for both the OFFICIAL and the ADJUSTED column, is the prompt printed in
  the benchmark's paper, Listing 20 ("Rubric scoring for nugget satisfaction prompt", arXiv 2510.27246v2, Appendix
  H), whose inputs are the question, the rubric item and the response, with a responsiveness rule anchored to the
  question. The exact bytes are the upstream template `unified_llm_judge_base_prompt` at BEAM commit
  3e12035532eb85768f1a7cd779832b650c4b2ef9 (template sha256
  d349c9a8559bed9c14bfe2e624212225b09218ff864258a739229c15f4c8e869), with `<question>` filled by the item's
  question. Compared with Listing 20 word by word after normalising whitespace, every difference between the two is
  typographic (curly against straight quotes, line-wrap hyphens in the PDF) and none is in wording: they are one
  text. (How many differences one counts depends on the diff unit, so no count is given; the comparison is
  repeatable from the two sources.) "Official" in this study therefore means the benchmark's gold answers scored by
  the question-seeing judge, as printed in the paper.
- Why not the released code: no judge call in the released evaluation code (the ten of the eleven `evaluate_*`
  functions in `src/evaluation/compute_metrics.py` that format `unified_llm_judge_base_prompt` from
  `src/prompts.py`) fills
  the question in. At
  3e12035 the template asks for it, so the judge saw the literal string `<question>`; at
  b2da22eac88bb0874c64665f13457eb99835774a (the current main) the question line is removed, while the
  instruction to score 0.0 when the response does not address the question remains (reported upstream as
  issue 15). The paper gives no reason for a no-question judge. The one passage that could bear on it
  (nuggets are "atomic, self-contained") describes how rubric items are written, not what the judge is shown, so
  it is not a second place in the paper that disagrees with Listing 20, which shows the question to the judge.
- Not known: which code produced the paper's results table. "Official" here does not mean that our scores
  reproduce the paper's numbers.
- Which judge this study uses is settled: the question-seeing judge is canonical (the
  project lead's ruling of 2026-11-18). The known-answer check below does not reopen that choice.
- Known-answer check (the project lead's test), committed and run before any scored item is judged. Its PURPOSE, in
  the project lead's framing: a rough bound on how far the no-question judge, which the released code uses, may have
  moved the scores that others report after running the released code. Its limit, plainly: the bound comes from the
  check's small set alone, so it is an indication, not a measurement over benchmark items. The other source beside
  it is the upstream tracker's own figure (issue 15: on one run of one system, supplying the question changed the
  verdict on 160 of 1,051 rubric items), which is that reporter's measurement, cited as theirs and not as ours. The
  check is not a correction of anyone's score: a judge flaw does not make the answers that judge rejected correct,
  so a proper score for such a system needs a rerun under the question-seeing judge. The check is a small set of
  responses whose verdicts are fixed in advance, judged with and without the question by the study's own judge (same
  model, settings and parsing). Part A: constructed responses that satisfy a rubric item's words without addressing
  the question, whose right verdict (0.0 under the responsiveness rule) is fixed by construction. Part B: run A
  items whose verdicts the three-reader score review has settled; these are the team's own verdicts, not independent
  ones, and are labelled so. Expected direction, written now: showing the question changes verdicts mainly on
  off-topic and abstention responses and little on on-topic ones; a large shift on on-topic responses would itself
  be a finding, and is reported. The check's own pre-log fixes the set sizes and the decision rule before the first
  call. The question-seeing judge counts as CLEARLY BETTER only if it matches the fixed verdicts on more Part A
  items and on no fewer Part B items. Every other outcome (a tie on Part A, fewer Part A matches, or fewer Part B
  matches) counts as NOT CLEARLY BETTER; a tie is a legitimate result of the check, not a failed check.
- Outcomes of the check. CLEARLY BETTER is the expected result and is reported. NOT CLEARLY BETTER, or a REVERSAL
  (the question-seeing judge matching fewer fixed verdicts than the no-question judge, on Part A or on Part B), is
  stated in the report's summary, beside the primary result, not only in the check's own log; its cause is then
  investigated (a rubric item that misleads the judge, or our own fixed verdicts or key points being wrong), and
  obvious errors are fixed. Any change to the check's fixed verdicts made after its result is seen is logged as post
  hoc, with the first result kept and reported beside the corrected one (the design owner's requirement).
- In every outcome, scored benchmark runs are judged by the question-seeing judge only (the project lead's ruling of
  2026-11-18: the no-question numbers are not worth their cost). H1 and the primary analysis (section 11) are tested
  on its scores, and "the OFFICIAL score" in this plan means that judge's OFFICIAL score. The no-question judge (the
  b2da22e template) is run only inside the known-answer check, never on a scored benchmark item.
- OFFICIAL score: gold answers as shipped. ADJUSTED score: confirmed gold errors corrected and, for Event Ordering
  only, the upstream procedure run on an adjusted item list as stated below (the Event Ordering ADJUSTED bullet). A
  gold answer is "confirmed wrong" only after a first-hand check against the conversation text. Before any finding
  goes upstream it is checked against the benchmark's issue tracker, open and closed issues: a finding already
  reported there is credited to its reporter, with the issue number, in the study's per-item change log (the one
  SCORE-REVIEW-PRINCIPLES.md requires) and, where we agree, corroborated with a short comment on that issue rather
  than reported again; only a finding not already reported is raised as a new issue. Every finding, whether credited,
  corroborated or new, is cited. The adjusted set is frozen before arm labels are unblinded.
- Upstream issue 19 (opened 2026-10-12, unanswered as of 2026-11-22) concerns gold answers, not the judge. According
  to the report, five gold answers of 100K conversation 1, a scored conversation here, conflict with the conversation
  text: two abstention questions (1 and 2) whose gold says the information is absent while the conversation contains
  it, and three questions (7, 19 and 20) where the conversation holds two valid values and the rubric accepts one. The
  report comes from a team evaluating its own memory system on that conversation, and gives that system's score
  before and after its corrections. The OFFICIAL score keeps these golds as shipped. For ADJUSTED, each is "confirmed
  wrong" only after the first-hand check this section requires, and if confirmed it is credited to the issue's
  reporter in the per-item change log.
- Two steps of the review phase are hand steps until the tool enforces them, each with a named witness recorded in the
  review log: (1) phase 2 receives its items in a random order with no set label shown; the study lead shuffles and
  hands out the packets, and the design owner checks that no set label travelled with them; (2) "report --unblind" is
  run only on a frozen adjusted set; the design owner confirms the set's freeze record before it is run, and the study
  lead runs it. Enforcing both in the tool is a build item for the review phase, not for the freeze. The engine's real
  parquet path was first run on 2026-11-22 in a scratch environment (259 passed, 0 skipped); neither seat's default
  Python has pyarrow, so in a default environment those two cells skip.
- Event Ordering is the one type the paper does not score by rubric items (the project lead's direction of
  2026-11-21, "align our scoring method with the paper"; the design owner's ruling the same day). Its OFFICIAL score
  is the paper's released procedure, exactly:
  - The answer is cut into items at every line break, with no filter (upstream `evaluate_event_ordering`,
    `llm_response.split("\n")`). The paper says only that an equivalence detector "aligns events in system responses
    with nuggets" (section 2, the evaluation paragraph) and is silent on how a response is cut, so under the rule
    above the released code stands.
  - Each item, in answer order, is compared with each still-unmatched reference event, in reference order, by a
    yes/no judge call with the upstream equivalence prompt verbatim; the first yes is the match (upstream
    `align_with_llm`, `llm_equivalence`). That prompt and the paper's Listing 21 are one text: their only difference
    in wording is a misspelling in the code ("exaplanation"). Two details are the code's alone, where the paper is
    silent, so the code stands: the instruction goes as a system message and the two snippets as a user message, and
    a reply counts as yes if it contains "yes" anywhere.
  - Kendall tau-b is computed over the matched sequences as upstream computes it (the union of both lists, a tie rank
    for an item absent from one), normalised to (tau + 1) / 2, the value the upstream report prints for this type
    (upstream `event_ordering_score`; code read at b2da22e). Our own code computes it, pinned by cells against the
    upstream arithmetic, including the position cases and repeated identical lines named below.
  - The yes/no calls use the study's judge model. They run after collection, on the saved answers, and change nothing
    the student sees; the student is given no format instruction (the texts are frozen).
- Every yes/no verdict is stored as a match table per question (answer item, reference event, verdict), so the
  Event Ordering score can be recomputed from the record by anyone.
- Reported beside the OFFICIAL Event Ordering score, never instead: the question-seeing judge's rubric score for the
  same questions, and the match's F1 (presence alone, order ignored).
- What the paper's number rewards, stated in the report: an answer that is only the ordered list of events. Every
  line that is not an event counts against it, empty lines included (identical lines share one rank but each counts
  as unmatched). A missing event costs according to its place: of five events in order, the last one missing scores
  1.0, a middle one 0.8, the first 0.6. On run A's two answer shapes (one tuning conversation; five reference
  events each; 17 and 22 items after the cut), a perfect recollection written in the student's usual format would
  score at most 0.65 and 0.57, assuming each event matches exactly one of the answer's list lines, in order, and
  nothing else matches.
- ADJUSTED Event Ordering (the project lead's direction of 2026-11-21, "if we see issues there, we improve it through
  the adjusted score process", and his approval the same evening, "the matching table correction only, keep the
  arithmetic"; the design owner's rulings of 2026-11-21 and 2026-11-22). OFFICIAL Event Ordering is unchanged.
  ADJUSTED Event Ordering is the upstream procedure, matching and arithmetic, run on an adjusted item list, and it is
  reported at two levels, both always shown:
  - Level A, mechanical: by code, on every answer of both arms, a line is dropped before matching if, once all
    whitespace is removed (no-break and zero-width spaces included), it contains no letter (Unicode general category
    L); every other line stays. So an empty line, a bare list marker, a heading marker, a horizontal rule or a table
    rule is dropped, and a list marker followed by words stays. Its one known cost: a line of only digits and
    punctuation (a bare year, a bare number) is dropped; that is accepted because such a line cannot name an event,
    and such drops are counted. Pinned by cells, one per class, including a digits-only line (dropped), an
    emoji-only line (dropped), a line in a non-Latin script (stays) and a list marker followed by one letter
    (stays). Level A carries no gold correction: a corrected reference list enters only at level B. That the project
    lead's approval covers level A is the design owner's reading, stated back to him (PROVENANCE, 2026-11-21). The
    report names level A for what it is: a second measure with a cleaner cut, not a case-by-case correction.
  - Level B, judged: level A plus three causes decided through the score review (SCORE-REVIEW-PRINCIPLES.md), with its
    blinding, its per-item change log, both arms and the dispute invitation: (1) a confirmed wrong reference event
    list (the gold-error path above); (2) a confirmed wrong yes/no verdict; (3) a line with words that names no event
    is removed, and two adjacent lines are joined only if neither alone names a complete event and together they name
    one reference event. No other cause. Verdicts on cause (3) carry a stated limit: an answer's format can tell its
    arm.
  - Filling the table (the design owner's ruling of 2026-11-22): removing or joining a line frees reference events and
    creates item and event pairs the OFFICIAL matching never asked, so at both levels the upstream matching is re-run
    on the adjusted item list. One verdict store, keyed by the exact pair (item text, reference event text): a stored
    verdict is reused, which is sound only because the judge's input is the pair alone (the instruction and the two
    snippets, above); a cell pins that, and if the prompt ever carries more than the pair, reuse is off and the design
    owner rules again. A pair is asked at most once, at any level; the first stored verdict stands unless the review
    overrides it under cause (2). Level A is computed in the same scoring pass as OFFICIAL, with the one store, so
    every judge call it needs is made at scoring, by code, before any review and before any arm label is seen. Level
    B's new calls (a joined line, a corrected reference list, pairs freed by a removal or an override) use the same
    judge model, prompt and settings, pinned; they are made after that item's review decisions are fixed and before
    unblinding, and each stored row records the level and the cause that made it necessary.
  - The adjusted item lists and match tables are frozen before arm labels are unblinded, like the adjusted set.
- Absolute scores are not comparable with the paper's table (a different judge model, and the code that
  produced that table is not known). The comparison is between our arms.

## 11. Primary analysis

- Outcome: per-conversation overall score (mean of its 20 questions), OFFICIAL, under the question-seeing judge of
  section 10, with the two Event Ordering questions scored by the paper's measure (section 10). The OFFICIAL score is
  the central result (Lei, 2026-11-17). Every scored conversation has exactly two questions of each of the ten
  types, so this mean is also the unweighted mean of its ten per-type scores. The paper does not say how its
  results tables' "Average" row is formed; checked on its Table 1 (four length blocks, 48 cells), that row equals the
  unweighted mean of the ten ability rows within rounding (largest difference 0.0009, where rounding three-decimal
  values allows up to 0.001), so the two are formed the same way.
- Report layout (Lei, 2026-11-17, binding): our adjustments and our disagreements with official answers appear in a
  clearly noticeable place in the report, not a footnote or a late page, with a pointer to the per-item details, so a
  reader sees which official answers we dispute and can judge for themselves. A floor that can be checked afterwards
  (the design owner's reading, open to the project lead's tightening): the ADJUSTED contrast appears in the same table
  and the same summary paragraph as the OFFICIAL one, and that summary states how many official answers we dispute;
  for Event Ordering, per level and per arm, how many lines each cause changed, and how many judge verdicts were
  reused and how many newly asked; and it links to the per-item change log.
- Contrast: arm 2 minus arm 1, paired by conversation (the scored set minus the conversations section 14's pairing
  rule drops).
- Estimate: mean paired difference with a 95% bootstrap CI over conversations (10,000 resamples, seed
  fixed and published). H1 is supported if the CI's lower bound is above 0.
- Reported beside it, never instead: the ADJUSTED contrast (with Event Ordering at level A and at level B, section 10,
  each shown); per question type; the efficiency table (section 12) per arm.
- Per question type (the project lead's request of 2026-11-21): for each of the ten types, each arm's mean score and
  the paired contrast with its interval, grouped by conversation-length group. This study's scored set is the 100K
  group, the main bucket; another length group enters only by an amendment registered before its runs.
- Event Ordering sensitivity (the design owner's ruling of 2026-11-21, declared before any scored run): the paper's
  Event Ordering measure depends on how an answer is formatted, and the two arms may format differently, so the
  primary contrast is also reported with the rubric score in place of the paper's measure for the two Event Ordering
  questions per conversation, next to the OFFICIAL contrast.
- Secondary, direction only (Lei's idea, ruled by Kepler, 2026-11-14): the arm 2 minus arm 1 paired
  difference is larger in Knowledge Update and Contradiction Resolution than in the other categories,
  because ENGRAM records a change of mind as a supersede. It is conditional on the student superseding
  at all, which is reported as a process rate per conversation. Under the open-book core (section 15) a
  transcript search can also find the latest value, so the expected edge is smaller than with the
  transcript closed; the book-closed looks (section 13) are where it should show most. Per-category
  results are reported with intervals and no claim beyond this direction. No expectation is stated for
  Event Ordering.
- Efficiency is reported beside the score and never combined with it: no efficiency-adjusted score, and
  no ratio invented after the numbers are seen.
- The contrast set is the conversations in which either arm's exam had an event that this plan keeps and reports
  instead of flagging; the primary contrast is reported a second time without them, dropped for both arms, once,
  over the whole set, not once per member; the report lists, for each conversation of the set, which member event
  or events put it there, and the count per member and per arm. Its
  members: a failed automatic compaction during reading (section 14, rule B); a recall daemon already gone at stop
  (section 14); ENGRAM's first session not complete at the end of setup (section 14); recall daemon files changed by
  the arm during setup (section 14); a run marked for a pervasive forwarder lapse (section 7). That second figure is
  descriptive and never a score (the design owner, 2026-11-22): it is reported beside the primary contrast, never
  instead, labelled descriptive, never in the abstract or a headline, and never as the study's result. H1 and the
  primary are decided on the primary contrast only, and the primary moves on nothing but section 14's flags.
- No interim scores: nothing is judged until every scored run is complete, so no score can inform a re-run.

## 12. Logged per run

Versions; setup cost (arm 2); per exchange: wall seconds, input/output tokens, tool calls (name, ok or error), whether
ENGRAM's write check fired and what the student did next; ENGRAM nodes written; files the student wrote; compactions
(count, trigger, tokens before and after); the forced compaction's preserved messages; which ENGRAM hooks fired at it;
the post-compaction record (section 8);
every escalation; the four network counts of section 7 (rule refusals, framing refusals,
cap refusals, network-capable shell calls) with the per-reason breakdown beside them; the UPSTREAM ERRORS count with
its per-reason breakdown (section 7) and the wrapper's verdict on the endpoint (section 14); the wrapper's launch
line, from the wrapper log; arm 2's recall daemon lines (the arm's statement and the launch's derived value, time to
ready, the stop's outcome, and the after-session record of the daemon's process id and that no process holds its
socket) and, per prompt, whether recall fell back to keyword search; the forwarder's lines (each pass and refusal,
with class, launch-relative index and Bash property names) and the run's count of turns nobody sent, with those after
a lapse's onset counted separately (section 7). For arm 2 also: the harness's own record, written outside the box,
of the first-session marker's state at the end of setup; the three
paths the daemon setting is derived from (present or absent, and a content hash of each present one), before and
after the setup session (section 14); and for every exam the daemon stop's outcome, the box's oom_kill count at
session start and end, and the session's exit status, with, for a daemon already gone at stop, the interval (last
exchange answered with semantic recall, first exchange answered by the keyword fallback], read from ENGRAM's own
event log and called an interval.

Efficiency, per question and per conversation, the same instruments in both arms, from the harness log
and the transcript: wall seconds; input tokens labelled "whole prompt per call" (Ollama's Anthropic-compatible endpoint
returns its cache fields as 0 or empty, so the transcript cannot tell reused prefix from newly
processed tokens) and output tokens; newly evaluated prompt tokens, from one source used identically in
both arms (the server's log or a logging proxy), OPEN until a tuning run shows a reliable source, since
a hook that injects changing text early in the prompt would break prefix reuse in one arm only; lease
seconds, per conversation: the GPU broker's lease for the run (one conversation, one arm, reading through
answering), from grant to release, read from the broker's own log, the same instrument in both arms. Lease
seconds include idle time inside the lease and are not weighted by utilisation; the co-load sampler's
readings over the same lease (at a fixed interval set in the run script, 60 s in tuning (the tuning log's co-load section says the sampler "writes, every 60 seconds" its readings;
branch study/beam-tuning-log-2, commit 7cfb3630b87c, lines 1021-1022): the GPU's memory and
load, the host's load average and busiest processes, and the GPU reservations; tools/coload-sampler.sh) are
reported beside them, never multiplied in. Arm 2's setup (section 7) has its own lease, reported as setup
cost, and each book-closed run is its own run with its own lease; tool
calls by kind (ENGRAM read, ENGRAM write, file read, file write, transcript read, shell); compactions. Claude Code's OpenTelemetry export is not used unless a tuning run first shows, by a
diff of both arms' first prompts, that switching it on changes nothing the student sees.

Per answer: whether the student opened its own session transcript (tool calls naming its path; this
detector misses a path-free search such as listing every transcript file).

Kept from every run, tuning and training included: the ENGRAM store, the transcript and the work files,
with a sha256 file list taken before anyone opens them. They are published only as a scripted, scrubbed
text export, after the repository's rule against publishing graphs is amended for a study subject's
sandbox graph and the licence item is closed; the originals stay private, with their hashes published.

## 13. Repeats and book-closed looks

Claude Code cannot pass a sampling seed to the server, so each (conversation, arm) cell is one sample.
Three scored conversations, drawn from the public beacon (section 9: conversations 12, 16 and 5), run a
second time per arm with the BOOK CLOSED (Lei, 2026-11-14): the student is told not to open its own session
transcript. Closed means the student's own tool calls (read, search, shell) do not open the transcript
file or a copy of it; what ENGRAM's server does inside its own tools is arm 2's memory and is allowed, and
arm 1's own notes are allowed. A run in which the student opens its transcript is flagged and reported
as it stands. These are three paired looks at each arm's memory without the transcript, never a result.
Consequence, a stated bound: run-to-run noise within a cell is not measured.

## 14. Exclusions and re-runs

An event is a harness fault only if the student cannot cause it; anything the student can cause is counted and
reported, never flagged, re-run or excluded. (Amended 2026-11-20, design owner, after the security seat showed a
student could make the bridge write an endpoint-failure line by sending a large body the endpoint rejects early.) A
run is excluded from the primary only for a FLAGGED harness fault: the student process dies; a timeout (any one
turn the proctor sends, in either arm, running past 3,600 s: reading, the forced /compact, answering, and arm 2's
setup turns alike; the scored launcher passes this value explicitly and records it, since the pilot sessions ran
at the reader's own default of 1,800 s);
a scored run with no wrapper launch line in the wrapper log (SANDBOX_LOG, section
7); the model endpoint was never reachable in the run, as decided by the wrapper's `log-verdict` (the one place this
rule lives): flagged only when the run's wrapper log holds a connect-failed line and no first-request marker, the line
the bridge writes once per launch after its first send that moves bytes upstream (a missing wrapper log is already the
fault above: no launch line). The run's wrapper log is one file per launch, and `log-verdict` refuses any log holding
other than exactly one wrapper-launch line, so one launch's marker can never hide another launch's unreachable
endpoint (design owner, 2026-11-20; required before the first scored run). An endpoint that dies DURING a run
(connect-failed after the marker) is never an automatic re-run or exclusion: the study lead reports it with the
endpoint's own log and the co-load sampler, and the design owner decides re-run or keep before anyone has read that
run's answers; the decision and its reason are reported, and the same rule holds for both arms. The guard is per
scored run: the exam session's own launch line counts, and arm 2's setup session, which also runs inside the wrapper,
logs its own. The launch line that counts carries the sha256 of the wrapper file itself, logged per run, so it shows
which wrapper ran, not only that one did; a scored run found outside the wrapper is reported to the security seat
before any re-run. The timeout value is about 3.2 times the longest turn measured in tuning: over all 38 tuning turn
records (tuning log, "Per-turn maxima over every tuning turn record", 2026-11-20), the longest turn of any kind is
1,108.8 s (reading three exchanges per turn, a tuning setting not used in scored runs; run p1-p1b-k3, started
2026-11-19). The longest of each kind this timeout covers: reading one exchange per turn 1,075.3 s (run K1-conv9); arm
2 setup 983.2 s; answering 524.8 s (run A); the forced /compact 166.6 s. Conversation 9 has 135 exchanges, so the pace
past exchange 135 is unmeasured, and scored conversations run to 196 (exchanges counted with the reader's own
`feed.exchanges()` on the 100K file: the 17 scored conversations have 94 to 196 each, 2,409 in all; the eight longer
than 135 are conversations 10: 172, 11: 194, 12: 196, 13: 155, 16: 161, 17: 143, 18: 181 and 19: 164; from the study
lead's registered timetable of 2026-11-19, a private working file, sha256
60cf1a810f72ac8e8f6a5201f1b551ee84098f1039ed88d0a5f96b281c95afdf). Too low a value flags slow but healthy runs and
costs re-runs; too high a value costs at most an hour of a real hang. A blocked shell network attempt is not a fault:
it cannot succeed (section 7), and the four network counts are reported per arm. Upstream lines are counted (section
7); only the endpoint verdict above flags a run. Each flagged run may be re-run once, with the reason logged before
the re-run; a second failure stays excluded. A wrong or empty answer is never a harness fault. A refusal by the
model-endpoint forwarder is never a flag; section 7 states its rule: a refusal on a launch's first request stops the
launch before any exam begins (below), a later isolated refusal refuses that request only, and a pervasive lapse
MARKS the run, which stays in the primary analysis, counted against the arm, and halts further launches. A
book-closed run in which the student opens its own transcript is NOT a harness fault: it is the student's
behaviour, flagged in the report and reported as it stands, never re-run (section 13).

Rulings of 2026-11-22 (the design owner; the rules on a lost recall daemon and on daemon files changed by the arm
follow the security seat's reads):

- Two flags in the list above, the student process dying and a timeout, are events the student can cause from
  inside the box. How they are treated is on the OPEN list; until it is ruled, they stay flags as written.
- Not flags, because the student can cause them. The post-compaction record (section 8). ENGRAM's first session not
  completing (arm 2): the exam runs with ENGRAM as the student left it; the state at the end of setup is recorded
  (section 12), reported per exam, and those exams are in the contrast set. A student's non-use of ENGRAM in a
  scored run is never an exclusion; it is part of the result.
- The tool list. The OFF set is enforced in the harness's own arguments, written by the launcher outside the
  student's reach, and verified from the session's first record before the first turn (section 7). A mismatch
  there is a harness defect the student cannot cause: not a run.
- In the scored launcher, every flag is triggered by a record the harness writes, never by an exit status alone;
  the exit status is recorded as corroboration. This is a requirement, not a description of the code today (the
  student process dying is read today from the end of its output); the missing lines are on the OPEN list.
- A lost recall daemon never triggers a re-run by itself. An exam whose daemon was already gone at stop is kept,
  whatever the cause, reported with the keyword-fallback count, and is in the contrast set. Stated cost: a genuine
  cap kill of the daemon while the student survives is not re-run; that exam runs partly on the keyword fallback.
  The alternative would give the arm one discard per cell whenever it wanted one.
- A launch stopped before any exam material reached the student is not a run. When its cause is outside what the
  student can change, it is retried without spending the re-run, each stop logged with its cause; after three such
  stops for one cell the study lead stops and reports to the design owner, since a cell that cannot start is a
  setup defect. For arm 2 the retry reuses the prepared home only if it is byte-identical to its snapshot after the
  first session; otherwise the home is rebuilt and the first session redone. A daemon-setting mismatch is never
  retried into three: the next rule classes it at its first refusal, and only its 'wrong before the setup session'
  outcome counts toward the three stops.
- Daemon files changed by the arm (arm 2). Setup records the three paths the daemon setting is derived from, read-
  only, never clearing or repairing, before and after the setup session (section 12). If the exam launch refuses
  with a daemon-setting mismatch, those records decide. Wrong before the setup session: the harness built the home
  wrong; not a run; fix, rebuild, redo setup; it counts toward the three stops above. Right before and changed
  during the setup session: the arm did it (the student, or ENGRAM's own tools under it; the box has no other
  writer). That is behaviour: no retry, no re-run, no exclusion. The exam itself is then launched once more (the
  exam, not the permitted re-run) with the arm's
  statement set to 'none' by the harness, with a record naming the cause ('recall daemon files changed during
  setup'), the before and after records, and that the statement was changed by rule; it runs as the arm left
  itself, and its score counts in the primary. If no student turn can then be sent, it is scored as an exam with
  no answers, counted, and reported by name. Such exams are reported by name and are in the contrast set.
- Which run counts. For each conversation and arm, the primary uses the first run that completes without a flag.
  A run that completed without a flag is never run again. A re-run exists only after a flag, once, with the reason
  logged before it starts. Flags are mechanical and are decided before any answer of that run is read. Book-closed
  runs never enter the primary.
- Pairing. After the one permitted re-run, if either arm's run of a conversation is still excluded, that
  conversation leaves the paired primary for both arms. The surviving arm's score appears in the per-conversation
  table, marked, and in no contrast. The report states, per dropped conversation, which arm was flagged and why.
  Stated bound: arm 2 runs a setup session before its exam, and those turns count toward the timeout flag, so
  dropping is not symmetric by construction. Arm 2's other extra machinery (the first session's completion, the
  recall daemon) puts exams in the contrast set instead (section 11). The counts per arm, of dropped conversations
  and of contrast-set members, make both visible.

A failed automatic compaction during reading (the summary the harness makes when the window fills does not complete;
distinct from the post-compaction record of section 8, the measure taken on the forced /compact after the last
exchange) is not a harness fault: the exam continues and counts (rule B; the project lead delegated this
rule, and the design owner and the study lead chose it on 2026-11-21). Every such event is named in the run's log
and in the report, with its exchange. Those conversations are members of the contrast set (section 11).
Measured before registration: 1 failure in 129 automatic compactions across every reading run on this setup (Claude
Code 2.1.325 to 2.1.328; exact 95% interval 0.02% to 4.2% per compaction). A long exam makes dozens of compactions,
so at the measured rate some scored exams would have one; at the interval's low end, none would.

## 15. What this design can and cannot show

It measures each product's whole memory as shipped, the on-disk session transcript included, in
one-topic, one-session use when the user has said the material matters (Lei's open-book core,
2026-11-14; this supersedes reading the forced compaction as "cross-window memory only"). After the
forced compaction neither arm holds the reading in its window, so answers come from what each product
keeps outside it: the compaction summary, note files and the transcript, or ENGRAM and the transcript.
The score therefore includes how diligently the student searches. The expected gap between arms is
smaller than with the record taken away, and a null means no difference large enough for this design to detect
(see the bound below) between ENGRAM and transcript search on this task, which is a publishable answer. The book-closed looks (section 13) are the only view without
the transcript. It cannot
separate ENGRAM's storage from the model's choice or ability to reach it; it runs Claude Code in print
mode, where ENGRAM's PostCompact hook left no visible trace in practice, unlike interactive use; it does
not measure memory across days or sessions; and with one sample per cell and 17 scored conversations it
detects only moderate effects. ENGRAM's recall daemon is started by the harness with the release's own launch
command, so the release's service-manager path is not exercised by this study (the security seat: no objection,
2026-11-22). Carried with it: with the daemon started inside the box under the student's own user id, its liveness
is an observation and not a seal. The dry-box probe of 2026-11-22 measured that a student which ends its own daemon
leaves the supervisor logging only 'already-gone' and the launch module returning not-flagged, so no record may
read 'the recall daemon was up throughout' as evidence of anything. After a compaction the harness
re-reads recently edited files, so arm 1's notes come back unasked (and arm 2's, if it keeps any). The brief
coaches both arms to watch for changes of mind and contradictions, which BEAM scores directly.

## 16. Budget (estimates from practice, never measured at scale)

About 143 exchanges per conversation. Arm 1 at about 5 to 25 s per exchange: roughly 40 min per
conversation. Arm 2 at about 45 to 98 s per exchange: roughly 2 to 4 h per conversation, plus about
7 to 16 min of first-session setup. The book-closed second runs (3 of 17 conversations, both arms) add about 18%.

## OPEN items, by phase

### Before the freeze (the registered hashes wait on these)

- The exam line (with its book-closed variant, section 4) and both instruction texts frozen with their sha256
  (texts and counts in section 4; the lean profile ships once engram#4802 merges).
- The brief's final text frozen (a purpose sentence is under test, see the tuning log).
- The student wrapper (section 7) merged with its colleague read, its launch line carrying the wrapper file's own
  sha256 (section 14); until then the shell's network is not closed.
- The project lead's word on the judge's cost (the pilot's figure went to him on 2026-11-16 and was not answered;
  asked again 2026-11-22). Until then section 10 says only what happened.
- Judge blinding made mechanical: answers can carry arm tells (ENGRAM node ids, tool names, a notes-file
  path), so they are stripped or normalised before judging, and the rule is stated here.
- The post-compaction record's counting rule (section 8): proposed by the study lead, read by the design owner.
- The record of ENGRAM's first session at the end of setup (section 12): what the harness writes outside the box,
  and the setup's round count and its value.
- How section 14 treats the student process dying and a turn running past the timeout. Both can be caused from inside
  the box. Not ruled (2026-11-22); the design owner first wants four facts: whether a session can be continued after
  its process ends and what the continued session's first request carries; whether a running turn can be interrupted
  from outside in the reader's mode; whether the run's own timestamps separate a slow endpoint from a long tool call;
  and how often each event happened in every run so far. Until ruled, both stay flags as section 14 states them.
- The scored launcher merged with its reads: the forwarder's per-request check and its cells, the dry-box cell of
  section 7, the recall daemon's after-session record (section 12), and a line the harness writes for each flag of
  section 14 (today 'the student process dies' is read from the end of the student's output, not from such a line).
- The ENGRAM commit the ENGRAM arm runs, named here by its pre-release tag (section 3).
- A stopped launch whose cause the arm could have written during setup, other than the daemon-setting mismatch
  section 14 already classes (the case that can be named: a first-request forwarder refusal in arm 2). Not ruled. The
  question is whether a file in the student's home (a settings file's environment block, user or project level) can
  change the three switches of section 7 or bring the shell's background option back against the environment the
  harness sets. One dry-box cell answers it, its expectations and command read by the security seat first. If it can,
  the forwarder still refuses, so the barrier holds; what changes is the class of that refusal (the arm's behaviour,
  not a harness fault) and section 7's words 'a harness fault counted against the arm'. The design owner rules after
  the cell, with the security seat.

### After the freeze, before registration

- The entry gate met (section 5) on exactly the frozen setup.

### Before judging (after every scored run, before any answer is judged)

- The review load of ADJUSTED Event Ordering (a third item kind in the score-review tool, built after the project
  lead's word on that tool; a prerequisite of the review phase, not of the scored runs, since the match tables are
  stored at scoring; level B's new judge calls need the judge callable at review time): measured in the pilot on Event
  Ordering items, run A's two answers first.
- Event Ordering in the score-review engine: that engine takes one rubric score per rubric line, from 0 to 1, for every
  question, while Event Ordering is scored pair by pair (decision log 2026-11-21) and its ADJUSTED score is the upstream
  procedure on an adjusted item list (decision log 2026-11-22). What an Event Ordering item's rubric lines and level
  are in that engine, answered before the review phase, with the ADJUSTED load item above.

### Before any transcript is published

- Licence handling for published transcripts. The dataset's licence was read on 2026-11-19 (CC BY-SA 4.0:
  redistribution allowed with attribution and share-alike) and an attribution file was added to the study folder
  (the study record's tuning log, entry 'Public-repository custody', 2026-11-19); this closes when that record
  reaches main.

### Stated limits the freeze does not wait on

- The forwarder cannot tell a forged request from the harness's own: the student has a shell and can send requests to
  it. A per-launch credential would close this (the world-credential work); the freeze does not wait on it (the
  security seat did not object, 2026-11-22), and it comes later as a dated amendment.

## Deviations log

(empty until registration)
