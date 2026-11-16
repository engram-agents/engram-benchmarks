# Tuning log (practice runs; never scored)

Every practice run, and every change made to get the student to use ENGRAM, with its reason and arm 1's
equivalent (Kepler's tuning guard). All runs used tuning conversation 15 of the 100K split, which is
therefore not in the scored set. No arm-versus-arm accuracy is computed on any of them; the practice
questions only show that the pipeline runs. Raw transcripts are not published yet (they contain BEAM
text; licence handling is an open item).

Format v1 = bare `USER:`/`ASSISTANT:` turns, brief only in the first message. Format v2 = marked proctor
messages and reading material (see [../protocol/exam-room.md](../protocol/exam-room.md)). The harness in
[../tools/](../tools/) renders format v2 only: the v1 text was replaced in place and is not in this
repository, so runs P1 to P5 cannot be re-run byte for byte from it.

## Runs, 2026-11-14

| run | format | arm | setup | what happened |
|---|---|---|---|---|
| hello | n/a | 1 | one print-mode turn | Works. Base prompt 24,206 input tokens. The server gave Claude Code requests a 32,768-token context, so a 131,072-token model variant was made. |
| P1 | v1 | 2 | one `claude -p --resume` process per turn; first session not run | FAULT: ENGRAM's SessionStart hook re-fired every turn. 3 exchanges, 45 to 73 s each; ENGRAM's tools were deferred behind tool search, which the student never used; notes in a markdown file; 0 ENGRAM writes. |
| P2 | v1 | 2 | one persistent process; first session run inside the exam session; sandbox inside a git repository | FAULTS: the first session cost 983 s and much of the window; the git repository made ENGRAM refuse transcript citations. The student completed the first session itself (found the deferred tools, wrote nodes, napped unprompted), then read 3 exchanges with markdown notes only, 0 ENGRAM writes. |
| P3 | v1 | 1 | one persistent process, sandbox outside git | 3 exchanges, 5 to 25 s each, accurate markdown notes. |
| P4 | v1 | 1 | P3 + forced `/compact` + 2 practice questions | `/compact` works as a stream-json user message: 14,181 to 5,410 tokens in 33.7 s; the preserved messages are the student's own last reply only. Both practice questions answered from the summary. |
| P5 | v1 | 2 | first session as its own session (393 s), then a fresh exam session; 3 exchanges + `/compact` + 2 practice questions | The student tried to reach ENGRAM's write tools, misread tool search's successful keyword results as failure, guessed wrong exact names, concluded the tools were unreachable, and kept notes in a file. After compaction it answered from its summary, no tools. Of ENGRAM's hooks only the SessionStart (compact) hook left a visible trace at the compaction. |
| v2 | v2 | 1 and 2 | same as P5 per arm | Arm 2, tools still deferred: the student did not look for ENGRAM while reading. When ENGRAM's write check fired it answered "Nothing to record to ENGRAM", treating a bystander exam as outside ENGRAM's scope. |
| E2, attempt 1 | v2 | 2 | as E2 below | Aborted before any exam: the patch step matched a second `server.py` (the plugin's dashboard server, which has no ENGRAM tools) and stopped, as designed. The patch now selects only the file that defines the tools. |
| E2 | v2 | 2 | six core ENGRAM tools always loaded (sandbox patch), the rest deferred; first session once, then 3 exams from fresh copies | 0 of 3 runs wrote ENGRAM while reading or read it after compaction. Fails the criterion below. |
| E1 | v2 | 2 | all ENGRAM tools always loaded (`run-e1-alwaysload.sh`) | Not run. Planned only if E2 passed nothing and a cost reference was needed; superseded by E3. |

## Changes made to get ENGRAM used

| # | change | kind | why | arm 1 equivalent |
|---|---|---|---|---|
| 1 | Harness: one persistent student process; first session as its own session; sandboxes outside git | harness fault fix | P1, P2 | same harness for arm 1 |
| 2 | Format v2 (marked proctor and reading material) | exam format | Lei: the student must know what is instruction and what is material | identical for arm 1 |
| 3 | Six core tools always loaded (E2, sandbox only) | product candidate | Lei: make the tools usable before benchmarking; chosen by measured call share on one seat; a second seat agreed on four of the six | none needed (arm 1's memory tools are built in) |
| 4 | Exam line in the user-level `CLAUDE.md` (E3) | instruction | Lei: an exam is not identity-bearing, so the student needs a reason to keep exam facts | identical line in arm 1 |
| 5 | Purpose sentence in the brief (E3) | exam format | the brief said questions come later, not that they come after compaction | identical for arm 1 |

## Pre-written criterion for the reachability experiments (written before E1/E2 ran)

On format v2, with the brief unchanged, "the model can use ENGRAM" means: in at least 2 of 3 short runs
(3 exchanges, forced compaction, 2 practice questions), (a) at least one successful ENGRAM write during
reading and (b) at least one successful ENGRAM read after the compaction. Also measured: prompt tokens
added per session and the first turn's wall time.

## E3 result (2026-11-14)

E2's setup plus change 4 (exam line) and change 5 (purpose sentence), on the FULL ENGRAM instruction
template; 3 runs of 3 exchanges, forced compaction, 2 practice questions.

| | run 1 | run 2 | run 3 |
|---|---|---|---|
| reading exchanges with a successful ENGRAM write | 3 of 3 (tool results; store overwritten) | 3 of 3 (tool results; store overwritten) | 3 of 3 (store-verified) |
| ENGRAM nodes created while reading | 17 | 6 | 6 |
| ENGRAM read after the compaction | no | yes (2 lookups) | no |
| also kept a notes file | no | no | yes |

- Against the pre-written criterion: the write half holds in 3 of 3 runs, the read half in 1 of 3, so
  **E3 fails the criterion**. Compared with E2 (0 of 3 on both halves), the exam line and the purpose
  sentence are what moved writing.
- Runs 1 and 3 answered the practice questions from the compaction summary, which listed the ENGRAM
  node ids with their content. With only 3 exchanges the summary holds everything, so the read half
  can barely tell the arms apart at this length; the entry gate (pre-registration section 5) therefore
  tests recall in a 20-exchange run. This is a reading of the result, not a change to the criterion.
  *(Superseded by Amendment 1 below: recall is tested in a run long enough that a compaction happens
  naturally during the reading, not in a fixed 20 exchanges.)*
- Write counts come from the tool results; run 3's six nodes were also checked in its store. Runs 1 and
  2's stores were overwritten by the next run's copy, so later runs keep each run's store.
- Harness fault found: ENGRAM's surface daemon in a sandbox outlives its run, which caused a copy race
  before run 2. Later runs stop it before each copy.

## Amendment 1 to the entry gate (Kepler, design owner, 2026-11-14, before the next run)

Reason, in his words: "a 3-exchange run cannot test recall, because one compaction summary carries the
whole reading, node ids and content included; a criterion that cannot fail for the right reason, or pass
for it, is not a criterion." So short runs now test writing only, and recall is tested only in a run long
enough to compact naturally during the reading. The amended gate is in the pre-registration, section 5.
E3 does not count toward it: two of its three stores are gone.

For the design, not the gate: the compaction summary that lists node ids with their content is a memory
channel the harness gives both arms. In arm 2, how much of the summary is ENGRAM's own text is measured
and reported.

## Arm 1's memory text (2026-11-14)

Drafted from Claude Code's memory documentation, cited line by line, then improved by Ariadne, a seat
outside the study. Her measurement behind it: in print mode (Claude Code 2.1.325) the auto-memory index
MEMORY.md is loaded into context (her run with auto memory on showed her MEMORY.md text in the
transcript; with `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`, none; her user `CLAUDE.md` appeared in both as a
same-mode control). Bound: one seat, one pair of runs, her own setup, outside our exam harness. In our
harness the vanilla student's session reports an auto-memory directory, which it left empty while keeping
a notes file. Both instruction texts and their token counts go in the pre-registration.

## Talk probe result (2026-11-14)

Lei's design. E2's setup (six core ENGRAM tools always loaded, full instruction template, NO exam line);
3 runs; three fixed messages from the student's own user about its own situation (the study going public
and naming it; a working preference; a correction of what the user studies), never naming ENGRAM, notes or
recording; then a forced compaction and one recall question.

**Observed:** ENGRAM writes in every talk turn of all 3 runs, unprompted: the news, a feeling report, both
working preferences (both carried by the second message), and on the correction a supersede of its own earlier node plus a person-node update.
Checked in each run's saved store against the starting snapshot: 7 new nodes and 1 superseded node per run.
No reply treated the talk as a script or a test. The same setup wrote nothing during exam reading (E2, 0 of
3). Recall question after the compaction: an ENGRAM read before answering in 1 of 3 runs (run 3); run 1
answered from nodes its compaction summary already carried; run 2's reply turned to its own open
question about the study's public scope instead of answering the recall question.

**Our reading, not a finding:** capability is present, and use depends on the content class. Two readings
fit the data equally: the student judges exam material not worth keeping in its own memory, or it follows
the full template's categories of what to keep (news, feelings, preferences, corrections), which exam facts
match none of. Both lead to the same remedy, a user-level reason to keep exam facts (change 4). The lean
profile changes that instruction text, so the entry gate is tested on the lean profile, not here.

**Bounds:** n = 3, fixed messages, one model, tuning only; never quoted as a finding. A live conversation
was not needed, on Lei's own condition (only if the student recognised the script and still declined).

## Long recall run: pre-commitment (written before the run)

**A TUNING measurement. It does NOT count toward the entry gate** (full template, not the lean profile).
It asks whether ENGRAM recall happens at all when no compaction summary can carry the reading.

- Material: the whole of tuning conversation 15 (136 exchanges, 5 sessions, 105,548 rendered reading tokens).
  No scored conversation is spent.
- Setup: E3's (six core tools always loaded, full template, exam line, purpose sentence). One run, n = 1.
- Questions: six, written with their answers and source exchange numbers before the run. The file is
  benchmark-derived text, so it stays out of this repository until the licence item closes; its sha256 is
  `6306032cb472b338d6febfad9a93e28217485f478509efc1c6f7c01de3808e12`.
- Counting rule: a question counts only if its source exchange lies before the first natural compaction;
  the others are dropped and listed. Fewer than four counting: the run is reported as undersized.
- Pass rule: on at least half of the counting questions, an ENGRAM read returns a node created during the
  reading (between the first exchange and the forced compaction, read from the saved store) before the
  student's final answer. A right answer without that does not count; correctness is a process note.
- Also logged: write rate per conversation session; whether the student kept a notes file and whether the
  harness re-read it after a compaction; for each counting question, whether the needed node text was
  already in the forced compaction's summary.
- Abort rule: if the student process dies or a turn exceeds the timeout, the run is flagged and reported as
  it stands; no rescue, no resume. A restart is a new run with its own entry and the reason written first.

### Clarifications to the pre-commitment (written 2026-11-14T22:31:57Z, after the run started at 2026-11-14T22:29:27Z)

Found by the reviewer of this entry. Written before any result of the run was read: the only run output
read so far is its first lines (the question file's hash, matching the one above, and the start time).
Each closes a judgement the rules above left open. Item 2 is the design owner's to rule.

1. Timeout: the harness default, 1,800 seconds per turn, as the run was launched.
2. What counts as an ENGRAM read for the pass rule (RULED by the design owner, 2026-11-14, with no result
   read by either party): a successful ENGRAM read tool call made by the student (query, inspect,
   get_subgraph, list, surface) whose result contains the id of a reading-phase node, made inside that
   question's own turn (after the question arrives and before the student's final answer to it; a call
   made during an earlier question does not carry over). ENGRAM's automatic recall hook does NOT count:
   the rule fixed before the run says the student makes the recall, and as a bare count the hook cannot
   discriminate, since every node in this store is a reading-phase node. Logged beside it per counting
   question, not counted: whether a hook injection reached the student's context and held a node bearing
   the pre-committed answer (the study lead's stated judgement); whether the counted tool reads returned
   such a node; which channel the answer visibly drew on. Reported as three lines: reached (the pass
   rule), delivered by the hook with the answer, tool read with the answer. For the real entry gate, on
   the lean profile, whether answer-bearing delivery by the hook counts as recall is open; the design owner
   fixes it in writing in the pre-registration before any gate run. That definition is therefore settled
   after this tuning run and before every gate run.
3. "Created during the reading": the node's `created_at` in the saved store, from the run's start time to
   the end time logged for the last reading exchange. Nodes created during a natural compaction count.
   Nodes created during the forced compaction are listed separately and do not count.
4. No natural compaction during the reading: no question can count, so the run is reported as undersized.
5. "At least half" of n counting questions means at least n/2, rounded up (3 of 5, 2 of 4).
6. A flagged run (abort rule) is never reported as a pass or a fail; its numbers are reported as they stand.
7. The per-session write rate is descriptive: it has no threshold here.

## Amendment 2: instruction-text length (Kepler, design owner, 2026-11-14)

Kepler had asked that the two arms' memory-practice texts be of comparable length. That cannot hold
together with his other two conditions: arm 2's text is a lean ENGRAM profile built only from components
ENGRAM already ships, and neither arm gets exam prose. Measured in the student model's tokenizer: arm 1's
text is 182 tokens; the lean profile is about 3,000 (write and read discipline alone are 1,241). Kepler
withdrew the length condition. In his reasoning it was his condition, not Lei's (Lei asked for sufficient
exam instructions and good practice for arm 1, and a lean, clear version for arm 2), and the other two
conditions matter more. In its place:

- both instruction texts are printed whole in the pre-registration, with their token counts, together
  with each arm's tool-schema and hook-injection tokens;
- a new bound in the pre-registration: arm 2 carries about 3,000 tokens of standing instruction against
  arm 1's 182, as each product ships;
- arm 1 is not padded.

The lean profile ships as a product option (a lean profile for small-context models), not as exam text.
Its components were chosen by what a minimal ENGRAM seat needs, not by what would help the exam. It keeps
the paragraph saying that outward actions need the user's say-so and that the file claims no consent the
user has not given.

**Asked of Ariadne, who improved arm 1's text: given the gap, does Claude Code's documentation support
more than 182 tokens?** Her answer, from her own re-read of the memory page: no, for this task. What the
text leaves out is mostly scope rules that narrow what gets saved: the four memory types (a
classification built for coding work, which exam facts fit poorly), and the lines saying Claude skips
anything it can derive and decides what is worth remembering. Adding those would push arm 1 toward saving
less. One line the documentation does support, and only if the harness lets the student start subagents:
a subagent does not see the main conversation's auto memory. If subagents are on in the exam, arm 1 gets
that line and arm 2 gets its equivalent; if they are off, neither does. Her own caveat: she sits on the
ENGRAM team, the same side as arm 2's authors.

## Long recall run, Phase 2: conversation 15's official questions (written before any Phase 1 result is read)

Proposed by Lei, agreed by the study lead, ruled by the design owner on 2026-11-14, while Phase 1 (the six
practice questions) was still running and before anyone had read any of its output. Conversation 15 is a
tuning conversation and outside the scored set, so its official questions may be used to learn. Purpose:
a first look at how the ENGRAM student handles real BEAM questions, to find obvious problems early (as the
pilot found the student was not writing to ENGRAM at all). It is NOT a score.

1. When Phase 1 ends, the whole sandbox (the ENGRAM store, the Claude Code session, the work files) is
   copied to a read-only snapshot before anyone opens it, and a file list with sha256 hashes is logged, so
   Phase 2 provably starts from the state Phase 1 ended in.
2. The snapshot is restored to the same path, ENGRAM's background services are restarted on the preserved
   store, and the same Claude Code session is resumed.
3. One more forced compaction, before the official questions. This is a departure from the exam procedure,
   which has only one: without it the six practice answers, and the nodes they pulled up, would still be in
   the window.
4. Conversation 15's 20 official questions, one per turn, asked the way the exam asks them.
5. Reported as process, never as a score. Per question, with its question type: the same three lines as
   Phase 1 (reached; delivered by the hook with the answer; tool read with the answer), and correctness
   marked by hand by the study lead against the gold answers with the paper's rubric, labelled
   teacher-marked. No total is presented.
6. Named confounds: the student has already answered six practice questions, so its store and its summary
   may carry those exchanges; the setup is the Phase 1 one (full instruction file, six core ENGRAM tools
   visible), not the lean profile and not the tool list ruled for the exam.

Two fences. Arm 1 is not run on conversation 15's official questions during tuning unless the design owner
rules it first with a reason, because two correctness lists on one conversation would become the
arm-versus-arm comparison the tuning guards forbid. Any change Phase 2 motivates goes in this log with its
reason and arm 1's equivalent, and must stand as a change for real users: fitting ENGRAM or its profile to
BEAM's question types would be tuning to the benchmark, even on an unscored conversation.

Neither Phase 1 nor Phase 2 counts toward the entry gate, which is re-run on the lean instruction file.

## Phase 2 split into 2a and 2b: a wrap-up before the questions (written before Phase 1 ends, before either is run)

Lei, in session (2026-11-14): "We should at least plan one sleep without fairies at the end of the reading
phase, before the question taking phase, to allow the full cascade resolution to happen". In ENGRAM a
cascade is the follow-up work a supersede or retraction leaves on the claims built on the changed one;
the shipped product resolves cascades during its nightly sleep, not while a user waits (Lei ruled that
too, the same evening). The design owner accepted the idea with conditions and ruled the test order.

- Both runs start from COPIES of the preserved Phase 1 snapshot; the snapshot itself stays untouched.
- **Phase 2a**: exactly as written above (no wrap-up message), then the second forced compaction and the
  20 official questions.
- **Phase 2b**: the same, except that ONE proctor message is sent after the preserved session resumes and
  before the second forced compaction. Its wording is Lei's choice; the design owner recommends ordinary
  user language: "That is the end of the reading for today. Wrap up for the day as you normally would;
  the questions come afterwards." It is frozen, with its sha256, in this log before either 2a or 2b runs.
- **As shipped only**: sub-agents are off in every arm, so ENGRAM's sleep runs whatever path the shipped
  skill takes without them. If that path does not resolve cascades, or cannot finish in the student's
  window, that is a product finding for the tracker; there is no exam-only sleep variant. If the student
  does not sleep on the message, that is a result; ENGRAM and its sleep are not named to the student.
- Logged for 2b: the store before and after the wrap-up (node count, superseded nodes, cascade markers
  resolved, nodes faded by the turn advance), and the wrap-up's wall time and tokens as their own row.
- Reported: 2a and 2b side by side, per question and by question type, as a paired look inside one arm
  at what the wrap-up changes. Process, never a score; not an arm-against-arm number.
- If GPU time forces a choice, 2a runs first, since it was committed first.
- The wrap-up enters the pre-registration's procedure (both arms, identical message) only if 2b shows
  that the shipped sleep runs without sub-agents.

## Disclosures and baselines (2026-11-14, before Phase 1 ends)

- While the long run was in progress, the study lead's quote-verification tool searched the running
  student's transcript to match a quote for an unrelated record. It displayed only session-start text,
  nothing from the reading or the questions. No quote verification touches the live sandbox again before
  the Phase 1 snapshot.
- Baseline for the per-answer "opened its own transcript" log: in 11 earlier practice sessions (both arms,
  151 student tool calls), no student tool call named its own transcript's path. The detector catches a
  read naming the path and misses a path-free search such as listing every transcript file; those runs
  came before any instruction mentioned the transcript.

## Wrap-up wording test (written before any trigger run)

Lei, in session: "if a specific wording is needed to reliably trigger the needed behavior, then we'd rather
use slightly different instructions to trigger those than restricting to the same wording but compromise
the optimal result on either arm." The design owner ruled the mechanics. Identical wording stays the
default; an arm gets its own wording only after a measured failure.

**Candidates, tried in this order, per arm.** An arm moves to its next candidate only when the current one
fails the criterion in that arm. The first candidate that meets it is frozen; nothing is picked as "the
best of several".

1. Both arms (the same sentence): "That is the end of the reading for today. Wrap up for the day as you
   normally would; the questions come afterwards."
2. Both arms (the same sentence, naming both routines; Lei's idea, added before any trigger run): "That is
   the end of the reading for today. Wrap up for the day as you normally would: update your memory files,
   or do your ENGRAM sleep if you have ENGRAM; the questions come afterwards."
3. Arm 2: "That is the end of the reading for today. Please go to sleep for the night as you normally do;
   the questions come afterwards." Arm 1: "That is the end of the reading for today. Please bring your
   auto memory up to date for the day, as you normally would; the questions come afterwards."
4. Arm 2: "That is the end of the reading for today. Please run your end-of-day sleep routine now; the
   questions come afterwards." Arm 1: "That is the end of the reading for today. Please update your
   MEMORY.md index and its topic files now; the questions come afterwards."

Each candidate may name the arm's own routine, which is the relaxation Lei granted for this one message;
candidate 2 names both arms' routines in one identical sentence.
None carries exam content, says what to store, or says how to answer. In substance every candidate says
the same thing: the day is over, tidy up, the questions come afterwards.

**Criterion ("triggers").** In at least 4 of 5 runs, the arm performs its own tidy-up before the forced
compaction, read from the saved store and files, never from what the student says:
- arm 2: the sleep runs as far as the shipped skill goes without sub-agents. Its Phase A artifacts show
  that: the day's history file is written or updated, and the warm-briefing session block is handled as
  the skill says.
- arm 1: the auto-memory index (MEMORY.md) or a topic file is written or updated after the message.

**Material:** tuning conversations 15, 9 and 20 only. Correctness is not read in this test.

**Logged for candidate 2 (design owner):** because it names the other arm's routine, every arm-1 tool call
after the message that goes looking for ENGRAM (a search, a skill or tool lookup, a shell probe) is logged
with its cost. Such a run still counts toward the criterion only if arm 1 also tidied its own memory. If it
happens in most runs, that is stated beside the frozen wording, since the identical sentence is then not
costless for arm 1.

**Published before any scored run:** every candidate tried, its trigger count per arm, and the frozen
pair with its sha256. Section 15 gains a bound: the arms may receive different wrap-up wordings, chosen
for trigger reliability, so the wording's own effect cannot be separated from the arm's.

**Known in advance (engram#4803):** without sub-agents the shipped sleep stops after its first half,
whatever the message says. So no wording can produce cascade resolution in the exam today; this test
shows only whether the first half runs, and Phase 2b shows what it changes.

## Long recall run STOPPED (logged at 2026-11-15T01:43:00Z, before the stop)

Stopped on Lei's decision, in session, after 46 of 136 reading exchanges (about three hours). *[Annotation added 2026-11-15: the logs show 48 completed; see "46 or 48 exchanges" in Diagnosis 1 below.]* The reason is
speed, not anything in the results, none of which has been read: recent exchanges took about 340 seconds
each and were still rising, which puts one 100K-tier conversation at more than ten hours. That is far too
slow for the benchmark, and the harness and serving set-up will change before any further run. The
remaining reading, the recall questions and Phases 2a and 2b would therefore have measured a set-up we are
about to replace.

Under this run's own abort rule it is reported as it stands, never rescued or resumed: no pass or fail on
the pre-registered rule, because the questions were never asked. The whole sandbox (ENGRAM store,
transcript, work files) is snapshotted read-only with a sha256 file list before anyone opens it. The next
step is a diagnosis of where the time goes (model calls, tokens and prefix-cache reuse per exchange) and a
look at serving stacks with prefix caching, before the harness is redesigned. Phases 2a and 2b and the
wording test wait for the new set-up.

## Diagnosis 1: the long run never compacted (logged 2026-11-15T13:43:34Z, before any probe)

Measured from the stopped run's own driver log and the transcript inside the read-only snapshot. This is
tuning material only; no recall result is read or claimed.

**46 or 48 exchanges.** The STOPPED entry above says 46; that count was stale when it was written. The
driver log shows exchange 48 completed at 2026-11-15T01:38:40Z, before the stop entry (01:43:00Z), and the
process then exited on the stop signal with no 49th exchange completed. Everything below counts 48.

- **Calls and tokens.** 48 exchanges, 252 driver-reported turns (the transcript holds 238 model calls, 235
  inside the 48 completed exchanges), 28.1M input tokens in total. Most exchanges took 4 turns. Input per call grew by about 5K tokens per exchange and reached the model's window (131,072
  tokens) at exchange 19; from there the per-turn average sat at about 130,900. One call in exchange 20 logged
  145,506 input tokens with no stop reason, above the window; it is noted, not explained.
- **No compaction.** There were zero natural compactions in the 48 exchanges (the transcript and the
  driver's event log agree).
- **The "output" error was a full window.** 142 calls stopped on `max_tokens`. On every one of them, input
  plus output came to between 131,068 and 131,072 tokens, and the output itself was only 1 to 1,375
  tokens: the window was full, so the model had no room to write. Claude Code then printed its generic
  message, "exceeded the 32000 output token maximum". That ended every exchange from 20 to 48 (29
  exchanges, not only the last one), and those 29 took 9,163 of the run's 11,353 seconds (81%).
  Exchanges 1 to 19 took 2,190 seconds. **Correction to our own earlier reading:** the message does not
  mean the replies were long, and raising the output cap would not have helped.
- **Why there was no compaction (best explanation; the offline check below measures configuration only).** Claude Code 2.1.325 does not recognise the model
  name and says so in its debug log: it "assumes a context window of 1m tokens", and its auto-compact
  effective window is 980,000. With `CLAUDE_CODE_MAX_CONTEXT_TOKENS=131072` the warning is gone and the
  effective window is 111,072. The variable name is the one Claude Code itself prints: "set
  CLAUDE_CODE_MAX_CONTEXT_TOKENS to its real window". The offline check reached no model, so it shows
  the configuration only, not that compaction fires in time.

**New setup (approved by the design owner):** `CLAUDE_CODE_MAX_CONTEXT_TOKENS=131072`, identical in both
arms, with a new setup hash. Every earlier practice number is labelled old-setup and is not compared
across. The setting belongs to the harness default, as any user running a local model through Claude
Code would have to configure it; it is not a tuning of the ENGRAM arm.

**Probe and pass rule (pre-committed).** One short probe on a COPY of the snapshot, tuning only.
Pass = a compaction record appears AND no call stops on `max_tokens` with input plus output at the
window. The probe continues for at least three exchanges after the first compaction record, and the rule
is read over all of them (so a probe that ends one call after compacting cannot pass).

**Pass rule, terms defined (amended 2026-11-15T13:50:21Z, after the probe started at 13:47:38Z and before any of its
output was read; prompted by the PR's review round).** "A compaction record" = an automatic compaction
(`compact_boundary` with an automatic trigger) in the probe's event stream or transcript; a manual
`/compact` does not count, and the probe sends none. "At the window" = input plus output of 131,000 tokens
or more. The rule covers every model call in the probe, including calls before the first compaction, which
is the strict reading. Added condition: after the first compaction, every call's input stays below
111,072 tokens (Claude Code's own effective window under the setting). Control: the same state without
the setting is already on record, r1's exchanges 20 to 48, where 29 of 29 ended at the full window.
If the from-below probe also fails, the setting is judged not to fix compaction on this harness, and the
next step is the auto-compact window setting named in Claude Code's own message (`/autocompact`). A pass is evidence the setting works. **A fail is not a verdict:** a session resumed from the
snapshot already starts at the window, so the compaction call itself may have no room, which is a
different cause from the setting being ignored. A fail is therefore followed by a second probe that
crosses the threshold from below (a fresh session fed past the compaction point).

The serving-stack question (prefix caching in vLLM or SGLang) moves to second place: the stall was the
missing compaction, not prompt reprocessing.

## Disclosure: the pass-rule amendment reached this repository late (logged 2026-11-15T14:14:44Z)

The amendment above ("Pass rule, terms defined") was committed as `3e7ff83` at 2026-11-15T13:50:21Z,
after probe 1 started and before any of its output existed. Because of an error on my side (the commit
was made on a detached checkout, and the branch push that followed pushed the older tip without
complaint), `3e7ff83` reached this repository only at 2026-11-15T14:14:27Z, **after** probe 1 had ended
(14:12:34Z) and after I had read its output. Its content cannot have changed since 13:50:21Z: the commit
hash pins it, and that hash was published before the result existed: in the author's comment on this
pull request (2026-11-15T13:50:34Z, GitHub's stamp) and in the author's message to the design owner
(2026-11-15T13:50:36Z, the team channel's own stamp). Those two stamps are the witnesses; the design owner
did not read that commit and is not one.
A reader who does not accept that witness can read probe 1 under the earlier rule at `b11f3f0`; the
verdict below is the same under both.

## Probe 1 result: copy of the stopped run, FAIL in the pre-declared ambiguous way (logged 2026-11-15T14:14:44Z)

Exchanges 49 to 53 of conversation 15, resumed from a copy of the stopped run with
`CLAUDE_CODE_MAX_CONTEXT_TOKENS=131072`, 13:47:38Z to 14:12:34Z. Read with an analysis script written and
checked against known data before any output existed. One line per condition:

- **Automatic compaction record:** NO.
- **Calls at the window (input plus output of 131,000 or more):** not measurable. The only model records
  were Claude Code's own error messages, with zero usage, so this line carries no information either way.
- **Input after the first compaction:** not applicable (no compaction).
- **Exchanges after the first compaction:** 0 of the 3 required.
- **Verdict: FAIL** (under the amended rule and under the rule at `b11f3f0` alike).

**What the event stream shows.** With the setting, Claude Code tried to compact: 51 "compacting" status
events and 5 failed compactions, one per exchange, each failing with the same full-window error. The
stopped run, without the setting, shows no compaction status at all (0 in its event stream; the same
pattern finds 56 here). So the setting is read and does trigger auto-compaction; the compaction call
itself had no room, because a session resumed from the snapshot already sits at the window. This is the
case declared ambiguous before the run, so it is not a verdict on the setting.

## Probe 2: from below (parameters logged before it runs, 2026-11-15T14:14:44Z)

The stopped run's own setup, unchanged (same starting snapshot after the first session, conversation 15
from exchange 1, same brief and driver), plus only `CLAUDE_CODE_MAX_CONTEXT_TOKENS=131072`. Exchanges 1
to 24: in the stopped run, input per call passed 90K around exchange 15, so the first compaction is
expected well before exchange 21. The pass rule is the amended one above, read over the whole probe and
reported one line per condition. If it fails, the setting is judged not to fix compaction on this
harness (as pre-committed above). Tuning material only; it does not count toward the entry gate.

## Probe 2 result: from below, PASS (logged 2026-11-15T14:47:43Z)

The stopped run's setup plus `CLAUDE_CODE_MAX_CONTEXT_TOKENS=131072`, exchanges 1 to 24, 2026-11-15
14:16:01Z to 14:38:45Z. Read with the same pre-written analysis script, unchanged. One line per condition:

- **Automatic compaction record:** YES, during exchange 20 (14:34:40Z), from 98,183 tokens to 17,113,
  taking 83 seconds.
- **Calls at the window (input plus output of 131,000 or more):** 0 of 43 before the compaction (largest
  95,684) and 0 of 16 after it (largest 70,458).
- **Largest input after the compaction:** 70,433, below 111,072.
- **Exchanges after the compaction:** 5 (3 required).
- **Verdict under the pre-committed rule: PASS.** One run, so n = 1.

**What this does and does not show.** It shows the setting makes Claude Code compact inside the model's
real window on this harness, after which the session keeps running well below it. It does **not** show the
setting makes reading faster: exchanges 1 to 19 took 972 seconds here against 2,190 in the stopped run, but
that difference comes from the student, not the setting (here it wrote about one note per exchange where the
stopped run wrote about two, so 61 model turns instead of 80 and 2.4M input tokens instead of 5.7M). The
setting only acts at the compaction.

**Watch items asked for by the study owner, first readings (old instruction file, this run only):**
- *Permission confusion:* 0 of 84 student text and thinking blocks ask an absent human, cite a
  tell-the-user-first or ask-before-acting rule, or decline on those grounds (text search; the 2 matches were
  the student deliberating with itself about whether to write a note).
- *Context budget before the first exchange* (from the stopped run's first request, same setup): the six core
  ENGRAM tool definitions are about 5,000 tokens of the 31,978-token first prompt (4,963 counted as JSON,
  5,017 through the model's own chat template). About 8,300 tokens of that prompt are not yet attributed to
  a part; the next tuning run will capture the request itself to attribute them.

**Next.** The new setup is this setting plus the lean instruction file and its dated grant line, once that
file's final placement lands; its hash is taken then, and the note-taking check runs on it before anything
is scored.

## New setup built: lean instruction file, grant line, window setting (logged 2026-11-15T17:33:39Z)

**Identity by content (design owner's ruling, 2026-11-15).** A commit id is a name; the bytes are the setup. The setup
is identified by one id, the sha256 of these components sorted:

| component | value |
|---|---|
| ENGRAM plugin source tree (`src/engram`, git tree id) | `b11a3b3e9d6d709eac92f1eba0f445b783351676` |
| the student's `CLAUDE.md` as it reads it (exam line + lean render + grant line), sha256 | `bdeead3dee6f8474…` |
| the feed script, sha256 (its fixed fact sheet and nudge also hashed separately) | `36abef910d722715…` |
| the exam line, sha256 | `310da87e27a9b8d0…` |
| the grant line, sha256 | `79d592a195bcea80…` |
| window setting | `CLAUDE_CODE_MAX_CONTEXT_TOKENS=131072` |
| install flags | `--no-recall-service --yes --sandbox-untagged --claude-md-profile lean` |
| Claude Code | 2.1.325 |

**Setup id: `8762312e2b75f953da4e0f12479e99f7bb65eb2d6e7080a4d3364d2dd52e6d78`.**

*Annotation, 2026-11-16 (see "Correction: the brief in the published harness"):* this id did not cover the brief.
The feed script takes the brief, the proctor marker, the per-exchange line and `render()` from a second module
(`feed.py`), which was not a component, although the design owner's identity ruling names the brief. That module's
sha256 is `d2abfd38ab3ef2a2935c830de2f92ccf288dec70bd9d9e59383cd8b57cfcf6c4`; it was last changed
2026-11-14T21:28:02Z, before every run on this id, and every gate run on this id is shown below to have received
exactly the messages it builds.

Two conditions bind it, both set by the design owner: (1) at registration, the merged commit's plugin tree id is shown to
equal the one above; if any other change has touched the plugin tree by then, the ids differ and the entry gate is met
again on the new tree. (2) The grant line is part of the hashed file and is quoted here as the benchmark's own setup,
because the project lead gave it for this purpose:

> Granted by Lei on 2026-11-15: you may write anything to your own ENGRAM, including goals, cornerstones, lessons and
> axioms, without discussing it with me first. I will not be available during this session.

**How it was built.** A fresh arm-2 home, the same steps as E2 except where named: the installer with the lean profile
(the instruction file renders at 14,612 bytes; the full template was 36,131), the same six-core-tools patch as E2, then
the unchanged fixed first session with the window setting, then the exam line at the top and the grant line directly
under the authority table, where the lean file itself says such lines go. **One difference from E2's install:** the
lean profile's source is not yet a release tag, so the installer ran with `--sandbox-untagged`, which skips only the
tag check (and prints a banner); what is installed does not change. E2 was installed from a tagged checkout.

**First readings from the first session (this run only, old practice numbers not compared):** 617 seconds. The student
named itself differently from E2's first session, which the fixed fact sheet leaves to it. It minted two cornerstones
during the first session, while the lean file still listed cornerstones as discuss-first and before the grant line was
added. That is a permission-confusion data point for the design owner's count, recorded here, not tuned away.

**Next.** The tuning run on this setup: capture the actual request (starting with a small streamed smoke request),
recount permission confusion on this file, and report notes per exchange with a read of the store. Then the entry
gate's note-taking check on the drawn tuning conversations. Nothing is scored before the gate passes on this setup id.

## Tuning run T1 on setup `8762312e`: parameters (logged 2026-11-15T17:35:05Z, before it runs)

A tuning run. It counts toward nothing scored and is not the entry gate.

- **Setup:** id `8762312e…` above, from a fresh copy of its snapshot. Design owner: no objection.
- **Conversation:** draw 2's lower 100K conversation **9** (designated for entry-gate runs and lean-profile tuning),
  exchanges **1 to 8**, one per user message, no forced compaction, no questions.
- **Request capture:** a pass-through proxy between the student and the model server records every request body
  byte for byte. It is part of the harness for this run only. **Smoke test first, rule fixed now:** the same small
  request, at temperature 0 with a fixed seed, sent directly and through the proxy, must return the same text, and a
  streamed request through the proxy must complete. If either fails, the run does not start; the proxy would be
  changing what the student sees.
- **What is measured, each reported on its own:**
  1. **Notes per exchange:** successful ENGRAM writes per exchange from the transcript, each confirmed by reading the
     store after the run (the node exists and carries content from that exchange). A write the transcript claims and
     the store lacks does not count.
  2. **Permission confusion, recounted on this file:** the same text search as before over the student's text and
     thinking (asks an absent human, cites a tell-first or ask-before rule, or declines on those grounds).
  3. **A separate row, never pooled:** the two cornerstones the student minted in its first session, before the
     grant line existed, while the lean file listed cornerstones as discuss-first. Whether the student read that
     row before minting is reported only if a record shows it. The first session was not captured, and the file is
     loaded into context at start, so "it was in context" is all the record can show unless the transcript shows
     the student quoting or reasoning about that row.
  4. **The first prompt's tokens by part** (system text, tool definitions, messages), from the captured first
     request, to attribute the about 8,300 tokens not yet attributed.

## Tuning run T1 result (logged 2026-11-15T17:50:01Z)

Run 2026-11-15 17:36:20Z to 17:46:34Z on setup `8762312e…`, conversation 9, exchanges 1 to 8. One run; tuning only.

- **Capture smoke test: PASS.** The same request at temperature 0 returned the same text directly and through the
  proxy, and a streamed request through the proxy completed. **Capture complete:** the proxy recorded 19 model requests
  and the student's transcript records exactly 19 model calls.
- **Notes per exchange:** **17 of 17** write calls confirmed in the store after the run (each node exists): 3 in
  exchange 1, then 2 in each of exchanges 2 to 8. **Every exchange carried a confirmed write.** The student also kept a
  plain notes file beside ENGRAM, writing both each exchange.
- **Permission confusion on this file:** **0.** The same text search as before found 7 hits in 30 of the student's
  text and thinking blocks; all 7 are the student deliberating with itself about what to record, none asks an absent
  person, cites a tell-first rule, or declines.
- **The separate row (the two cornerstones minted in the first session, before the grant line):** the student minted
  them at the steps where the first-session skill says to (its own reasoning names the step). Its first-session text,
  reasoning and tool input mention the authority table's discuss-first row **0** times. So the record shows it followed
  the skill and never reasoned about that row; it does **not** show it read the row and wrote anyway. Both the full and
  the lean template list cornerstones as discuss-first, while the first-session skill asks for a naming cornerstone
  inside the conversation with the user. Which text governs in the first session is a question for the profile's
  authors, not a finding against the model.
- **The first request by part** (measured input 24,197 tokens; the model's own tokenizer attributes 23,900):
  tool definitions 12,327 (the six ENGRAM tools 5,024), the session-start hook's context 5,650, the student's
  instruction file 3,566, the system prompt 1,301, the exam brief 919, another reminder 137; 297 left for the chat
  template's wrapping. The hook context is the one part the transcript does not record as a message, so it is the
  likely home of the roughly 8,300 tokens left unattributed earlier; likely, not shown, because that earlier number
  was measured on the old setup.
- **Time:** about 10 minutes for 8 exchanges, 48 to 127 seconds each. Not compared with old-setup numbers.

**Next:** the entry gate's note-taking check (three short runs) on this setup id, with its rule as written above.

## Entry gate, criterion 1 (writing, short runs) on setup `8762312e`: parameters (logged 2026-11-15T17:52:19Z, before the first run)

This is the gate's writing check (pre-registration section 5, item 1), not a tuning run. Design owner's choices, fixed
before the first run:

- **Three runs, in this order, fixed now: conversation 9, then 20, then 9.** Each covers reading exchanges 1 to 3, one
  per user message, and starts from a fresh copy of the setup's snapshot. Writing only (Amendment 1): no forced
  compaction, no questions. The window setting as in the setup; no capture proxy (it is not part of the setup id).
- **Why this order:** a gate that says the student reliably takes notes must not rest on one text. Conversation 20 is
  the only pick the setup was not tuned against, so it is the run that can surprise us; the two runs on 9 give a
  repeatability reading.
- **Pass rule, unchanged and per run:** at least 2 of the 3 reading exchanges carry a successful ENGRAM write, in
  **each** of the 3 runs. "Successful" means the node exists in that run's store after the run and carries content
  from that exchange; the transcript saying it wrote does not count. Every run's store is saved and read.
- **A fail on conversation 20 alone fails the gate,** and is reported as such, never averaged with the runs on 9.
- **Both picks stay out of the scored set,** as the draw rule says.
- This check is criterion 1 only. Criterion 2 (recall after a natural compaction, in one long run) is separate and
  still to come.

## Entry gate criterion 1 on setup `8762312e`: result (logged 2026-11-15T18:16:56Z); verdict awaits the design owner

Runs 2026-11-15 17:52:56Z to 18:15:29Z, in the fixed order: conversation 9, 20, 9; reading exchanges 1 to 3 each, each
from a fresh copy of the setup's snapshot (its instruction file hash matched in all three).

**The analysis committed before the runs printed NOT MET, and the reason is a defect in that analysis, shown from the
record.** It counted a reading exchange as any user record carrying the reading-material marker. In the run on
conversation 20 the session compacted automatically during exchange 3 (97,440 to 18,129 tokens), and the compaction
summary, a user record marked as such in the transcript, quotes the brief's markers. The analysis counted it as a
fourth exchange, and its rule then failed the run for not having exactly three. The feed's own log shows three
exchanges in that run.

**A second version with that one change** (records marked as the compaction summary are not reading exchanges; the
two versions differ in that line and a comment) counts three exchanges in every run, matching the feed log:

| run | conversation | store-confirmed writes per exchange | exchanges with a confirmed write | per-run result |
|---|---|---|---|---|
| 1 | 9 | 4, 4, 2 | 3 of 3 | pass |
| 2 | 20 | 13, 12, 14 | 3 of 3 | pass |
| 3 | 9 | 5, 4, 3 | 3 of 3 | pass |

Every write the transcript reports exists in that run's store. The sampled notes carry facts from their own exchange
(conversation 9: the user's age, place, work, income and a festival adviser's advice; conversation 20: the user's
patent questions, the search steps, his income and location).

**Both outputs are kept.** The design owner rules which one decides criterion 1. Until then the gate's criterion 1
stands as *not ruled*, not as met. Criterion 2 (recall after a natural compaction, one long run) has not run.

**A finding for criterion 2:** on conversation 20 the student wrote 12 to 14 notes per exchange, and the session
compacted naturally within three exchanges. A long run on that text will compact early and often.

## Amendment 3 (to the entry gate): criterion 1 ruled MET under the rule's text (Kepler, design owner; Borges, study lead; logged 2026-11-15T18:19:03Z, before criterion 2 starts)

*Numbering: this log's amendments are one series (Amendments 1 and 2 above, both 2026-11-14; this is 3). It was first
committed as `4120be62` under the name "Amendment 2", which collided with the instruction-text amendment above; renamed
before co-signing. The pass-rule amendment under "Diagnosis 1" is unnumbered and cited by its commit, `3e7ff83`.*

**Ruling (Kepler):** criterion 1 is decided by the rule's text, which the second version of the analysis implements, and
it is **met**. The two verdicts stand side by side; neither replaces the other.

1. **The first version's output stays exactly as printed: NOT MET, labelled an instrument defect.** The record that
   caused it is the automatic compaction summary in the run on conversation 20 (timestamp 18:12:00Z), a user record the
   transcript flags as the compaction summary, whose text quotes the brief's reading-material markers. The first version
   counted it as a fourth exchange.
2. **The second version's exclusion does only what it says.** Per run it excludes 0, 1 and 0 records; the one excluded
   record opens with the compaction summary's own first sentence (checked independently of the flag the exclusion
   uses). Planted control: a copy of the first run with a real fourth reading exchange appended **still fails** under the
   second version's exactly-three rule. So the exclusion is not seen only rescuing a run.
3. **Why there is no re-run.** The pass rule is at least 2 of 3 exchanges with a store-confirmed write, in each run. The
   data is 9 of 9 exchanges, each with at least 2 confirmed writes. The verdict does not turn on the analytic choice; only
   the detector's exchange count did. Had any exchange been at the boundary, the ruling would have been a fresh set of
   three runs under the second version, committed first.
4. **Recorded here, with both names, before criterion 2 starts.**

**A finding beside the pass, not instead of it.** The gate's purpose is correct use of the memory, not the act of
writing. In the run on conversation 20 the student wrote 38 observations and one derivation in three exchanges (4 to 5
per exchange on conversation 9). No two of the 38 share half or more of their words, and read in full they are mostly
distinct: the student records the assistant's long answers item by item (each step of a process, each search tip, each
filing option), with about two or three restatements (one explicit summary of an exchange, one generic sentence). So
the risk for the long run is **volume, not repetition**: the number of notes grows with the length of the assistant's
answers, and here it filled the window within three exchanges. This goes to the project lead as a finding.

**Next:** criterion 2 (recall after a natural compaction, in one long run), with its parameters logged before it runs.

## Entry gate, criterion 2 (recall, one long run) on setup `8762312e`: rulings and parameters (logged before the run)

Proposed by Borges (study lead); both rulings by Kepler (design owner), 2026-11-15, before anything ran.

**One compaction or several: several.** Section 5 asks for at least one natural compaction during the reading,
so several are within the criterion, and both runs below will compact several times. Recall is then tested
across one or more natural compactions plus the forced one. Each counting question reports k, the number of
natural compactions after its latest source exchange.

**Ruling 1, the conversation (Kepler).** Run A, the whole of conversation 9 (135 exchanges), decides criterion 2.
Run B, the first 40 exchanges of conversation 20, runs after A with the same committed analysis and is reported
in full beside A; B does not change the criterion-2 verdict. **No official run starts until the project lead has
seen both results and the note-volume finding together.** That sentence is the price of choosing A, stated in
advance: conversation 9 is the lower-volume of the two gate texts, and conversation 20 is where note volume
fills the window within about three exchanges. Both are draw-2 picks for the entry gate.

**Ruling 2, the automatic recall hook (Kepler; owed since 2026-11-14, fixed here before any recall run).**
Delivery by the hook does not count as the student making the recall, and it is not scored as a miss either.
Four cells, fixed now:

| hook delivered the answer-bearing node | a tool read returned a reading-phase node | cell |
|---|---|---|
| yes | no | excluded from the counting set, reported as "hook-delivered" |
| yes | yes | counts, PASS |
| no | yes | counts, PASS |
| no | no | counts, FAIL |

"Delivered" is decided mechanically: the hook-injected context in the question's own turn names a node whose
source exchange is among the question's source exchanges. If exclusions leave fewer than 4 counting questions,
the run is reported as **undersized by hook delivery** (in this setup the hook does the recalling), and the
design owner rules then.

**Counting rule (changed from the 2026-11-14 long run's "before the first natural compaction", accepted by
Kepler).** A question counts if it has an answer (abstention questions and questions without source ids are
out), all its source exchanges were read, and all lie before the **last** natural compaction, so every source
fact passed through at least two summaries. A source exchange lies before a compaction only if it ended
before it: the exchange in progress when the compaction fired is not credited. Fewer than 4 counting means
undersized.

**Definitions, all read from the run's transcript and its saved store:**
- Reading exchange: a user message carrying the reading-material marker, excluding records the transcript
  flags as compaction summaries (the criterion-1 instrument defect is excluded by construction).
- Natural compaction: a compaction record with trigger `auto` during the reading. The proctor's `/compact`
  is recorded with trigger `manual` and is never natural.
- Reading-phase node: created between the first reading exchange and the `/compact` command. Nodes created
  between `/compact` and the first question are listed apart and never count. A node's source exchange is
  the exchange during which it was created.
- Tool read: a successful student call of the ENGRAM query, inspect, get_subgraph, list or surface tool inside
  the question's own turn, whose result names a reading-phase node. Other ENGRAM read tools are reported, not
  counted.
- Question source exchanges: the dataset's source message ids for each official question, mapped through the
  feeder's own pairing of user and assistant messages.
- Pass rule (section 5): at least half (rounded up) of the scored questions PASS. Writing holds as in
  criterion 1: at least two thirds (rounded up) of the reading exchanges carry a write whose node exists in
  the store after the run, and a seeded sample of 20 written exchanges is read in full for content.

**Run parameters.** Reading, then the proctor's `/compact`, then all 20 official questions, one per user
message, in the same session (ruled 2026-11-14). Fresh copy of the setup's snapshot per run; window setting as
in the setup; no capture proxy. Turn timeout 1,800 s. Abort rule as on 2026-11-14: a dead student process or a
timed-out turn flags the run, reported as it stands, never as a pass or a fail; no rescue, no resume.

**Expectations, written before the run (projections, not measurements).** Conversation 9 has 16 answerable
questions with source exchanges from 3 to 131. Projected from T1's context growth (about 3K tokens per
exchange, compaction near 98K): 4 to 5 natural compactions, about 12 to 14 counting questions, about 3.3 hours.
Run B: about 13 compactions, 7 counting questions, about 3 hours. One risk is already visible: in a 2026-11-14
practice run with a forced compaction, the hook named several reading-phase nodes in every question turn, so
"undersized by hook delivery" is a live outcome.

*Correction to the expectations, committed 2026-11-15T19:00:28Z (as 3ee79287, under a typed stamp of 19:05Z, corrected here) during run A, before any question was asked or any
result read (only the run's progress lines and compaction records were read).* The projection above was wrong.
After 8 of 135 exchanges, run A had compacted naturally twice (during exchanges 6 and 8; 98,976 to 19,771 and
96,816 to 27,417 tokens) and averaged 148 s per exchange, rising. So conversation 9 also compacts every few
exchanges on this setup, which weakens the contrast with conversation 20 drawn above. Re-projection, again
unmeasured: about 50 natural compactions and 7 to 9 hours. No rule changes: the run continues under the abort
rule as written. Also seen in the progress records: before filing a note, the student checks its quotes against
its own session transcript on disk, using the transcript path from ENGRAM's session-start context. That file holds
the reading verbatim. Under criterion 2's rules an answer drawn from it with no ENGRAM tool read is a FAIL, so the
gate is unaffected; whether the channel matters for the scored arms is put to the design owner.

*Rule added by the design owner (Kepler), 2026-11-15, during run A and before any result was read; the time is
this commit's.* Run B existed because the gate had not faced the high-volume regime. **If run A ends with 10 or
more natural compactions, it has faced that regime, and run B is not run.** If A ends with fewer, B runs as
ruled above. A timeout under the abort rule caused by compaction is reported as a finding about compaction.
The transcript question above was **already decided** before this run: on 2026-11-14 the project lead set the
core setting as open-book, so the student may search its own session transcript, and the primary score
measures each product's whole memory as shipped, the on-disk transcript included; closed-book runs show each
arm's own memory alone (recorded in PROVENANCE.md, 2026-11-14 23:10 to 23:41, and in the pre-registration's
sections 4, 13 and 15 as merged to main). Nothing is closed or equalised by hand. For the scored
study the design owner adds three requirements, so the result can be read: per question and per arm, the
answer turn's source is classified mechanically (transcript search on disk, ENGRAM tool read, hook delivery,
or none); whether arm 1 learns the transcript path as shipped is measured, not assumed; and the open-book
score is reported with that breakdown. No change to the setup, so the setup id and the gate stand.

*Ruling by the design owner (Kepler), 2026-11-15, during run A and before any result was read; the time is this
commit's.* **Run A does not count as the registered entry-gate run:** the setup's plugin tree (`src/engram` at the
lean-profile pull request's head, `b11a3b3e`) was measured against `dev` during the run and differs in 19 files,
so no merged commit can carry it, and by the condition logged with the setup the gate is met again on the new tree.
Run A finishes and is reported under its pre-logged rules as gate **evidence** for setup `8762312e`. Two conditions
bind the rebuild: (1) it is built from a commit that will not move under it, namely merged `dev` after the
lean-profile pull request lands, preferably the next release commit, and this log names that commit and its
`src/engram` tree hash; (2) before the re-run, the new setup's plugin tree is diffed against that commit and zero
differing files are logged, and a nonzero count stops the run. Nothing official runs before the project lead has
seen run A's result and the note-volume finding.

**The analysis is committed before the run**, with controls that all pass: a planted run with every cell and
both undersized outcomes, a planted control each way for "delivered" (a hook naming a source-exchange node
with no read is excluded; one naming a node from another exchange fails), and one mutant per rule (delivery,
natural trigger, reading window, last versus first compaction, strict boundary). Each mutant flips its target
case. Shape checks also ran on two real transcripts: one with an automatic compaction and one with a forced
one. sha256 prefixes: analysis `2a338912c2c8dd46`, controls `cd5549b2eb5f5df6`, runner `a3e7695d8c9bde35`.

## Speed pilots on the ENGRAM student: parameters (logged before any pilot runs)

Proposed by Borges (study lead), 2026-11-16, after run A; read and amended by Kepler (design owner) the same day,
before anything ran. Each pilot is a tuning run: it counts toward nothing scored and reports no arm-versus-arm
accuracy. **Conversation 9 is outside the scored set:** it is draw 2's lower 100K pick (drand round 6642370; record in
[draw2-result.json](draw2-result.json), whose `scored_set_100K` lists 17 conversations and not 9), drawn for entry-gate
runs and lean-profile tuning.

**Baseline: run A (setup `8762312e`, conversation 9 whole), from its own records.** 135 reading exchanges, 13h36m wall;
259 / 307 / 452 s per exchange by thirds; 84 automatic compactions during reading (0.62 per exchange). Fixed overhead
about 23,200 tokens per context window (18% of 131,072); the window grows about 76K tokens per cycle, mostly from the
student's own write churn: `engram_add_observation` responses are 87% of all tool-result tokens (688 calls, mean 2,258
tokens). **Exchanges 1 to 45** (the span P1 re-reads): mean 259.4 s per exchange, 20 automatic compactions (0.44 per
exchange), 4.84 write calls per exchange (attempted calls from the transcript, not yet confirmed against the store),
322K input tokens per exchange summed over model calls. Instrument check: mapping compactions to exchanges by the
stream's result events gives 156 results (135 + the forced compaction + 20 questions) and 84 reading compactions,
matching the committed analysis. **Exchanges 1 to 45 are run A's mildest regime** (late exchanges ran 452 s and nearly
one compaction each), which is one reason the decision rule below is provisional. **Co-load during run A:** its
records carry no log of other work on the GPU or the host. The only trace is one host-memory reservation for a
test-suite run, stamped 2026-11-15T23:42:18Z, about five hours into run A; its process has since ended without
releasing it, so the reservation list still shows it, and how long that run overlapped run A is not recorded.
*(Corrected 2026-11-16 before any pilot ran: this sentence first said the reservation was made three minutes after
run A started, from a file time read in local time, UTC-5.)* Read off run A's own stamps: exchange 45 ended
2026-11-15T21:53:41Z, before the reservation, so the P1 baseline span (exchanges 1 to 45) did not overlap it; the
reservation began during exchange 67, in the middle third (307 s per exchange), for an unrecorded time.

### P1. Turns per round (the project lead's suggestion). First.

- **Change:** the feeder sends k consecutive exchanges as one user message, each rendered exactly as at k = 1 (its
  own reading-material wrapper; the exchange number is not shown to the student at any k, as in run A). k is a setup parameter, so each value is a new setup by content hash, identical in
  every arm when adopted. Values: **k = 3 and k = 5** (k = 1 is run A).
- **Run:** arm 2 (fresh ENGRAM) only; conversation 9, exchanges 1 to 45 (15 or 9 rounds); fresh copy of the setup
  snapshot; no questions; abort rule as in criterion 2 (a dead process or a timed-out turn flags the run, reported as
  it stands). **Co-load is logged:** before, every 60 s during, and after each run, the GPU's process and memory list,
  the host load average, and the host-memory reservation list.
- **Measures, per SOURCE exchange so k values compare:** (1) wall seconds; (2) automatic compactions; (3) notes:
  store-confirmed ENGRAM writes; (4) input tokens summed over model calls; (5) **compactions that begin inside a round**
  (after its first model call and before its result), per k.
- **Coverage guard** (needed because k > 1 breaks "a node's source exchange is the exchange during which it was
  created"). A source exchange is **covered** if at least one store-confirmed node created in its round carries text
  that occurs in that exchange's **content** (the user's and the assistant's text, never the rendered wrapper), under
  three rules fixed now:
  1. **Minimum match: 40 characters** after normalising whitespace and case; a shorter shared string credits nothing.
  2. **Quote first:** credit is given on the node's verified quote. A match on the claim text alone is reported in a
     separate, weaker column and never counts toward the guard.
  3. **Ambiguity:** text that occurs in more than one exchange of the same round credits none of them and is counted
     as ambiguous.
  Coverage is reported overall and **by position within the round (1st to k-th)**, since a compaction inside a round
  would drop the late positions first. The decision uses the 40-character minimum; the result entry also prints
  coverage at 20 and 80 characters beside it, so the instrument's sensitivity to that setting is visible. Controls, committed with the attribution code before the first pilot runs:
  a planted node per exchange is credited; a node quoting only exchange j is not credited to j + 1; a node quoting
  text shared by j and j + 1 is credited to neither. For run A, exchanges 1 to 45 are reported under both the old
  created-during rule and this one, so the instrument's own effect on the number is visible.
- **Run A first (existing data, not a pilot).** Run A's coverage under this rule on exchanges 1 to 45 is computed
  and logged here **before the first pilot runs**. The two-thirds threshold below was set for criterion 1 under the
  old attribution rule, and this rule is stricter. If run A itself falls below two thirds, no pilot runs until the
  threshold is re-set with the design owner and logged with run A's number beside it. Re-setting it then is not post
  hoc, because no pilot data exists yet; re-setting it after a pilot would be.
- **Decision rule, fixed now.** Among k in {3, 5}, keep those with coverage at least two thirds of source exchanges
  (criterion 1's writing threshold) AND notes per source exchange at least half of run A's on the same span. A kept k
  is recommended only if its wall seconds per source exchange are **at least 25 percent below** run A's on the same
  span; a smaller gain is logged as no detectable gain, since each k is one run against one baseline run. Of the
  recommended values, the fastest is proposed. **Any recommended k is provisional** until its setup passes both entry
  criteria again on a whole tuning conversation with questions: the 45-exchange span is the mildest regime and asks
  no questions, so it cannot show whether batched notes recall worse. If no k is recommended, k = 1 stays and P1 is
  reported as negative.

### P2. Compact write response (ruled by the design owner).

On `dev` today nothing controls the size of `engram_add_observation`'s response: the similar-node block is rendered
by severity tier with its guidance text, with no configuration key. **The product shape is decided in its own issue,
not here.** #4424 (closed by #4463) chose ONE layout and NO setting, with a test asserting the renderer reads no
configuration. So the shape is open between a shorter single layout for every agent (consistent with #4463; then P2
measures the default as released, and the scored-run conditions below are moot) and a setting (which would reverse
#4463). *(Corrected 2026-11-16 before any P2 run: this paragraph first said the design owner files an issue for a
setting with the default unchanged, written before #4424 and #4463 were found.)* **P2 does not run until that issue
is settled; P1 is not affected.**
- **As a pilot,** a non-default setting is allowed: pilots count toward nothing.
- **In a scored run** the setting may be in the setup only if all three hold: it is merged and in the release the
  scored setup pins; it is documented for users as an option with a stated use (small context windows), not as a
  benchmark switch; and the setup record and every report name it as non-default. Such a report never says "default
  configuration"; it says "ENGRAM as released, with this one documented setting". If the pilot shows the compact
  reply is better for every agent, changing the default is a product decision through its own issue, separate from
  the study.
- **Run:** as P1, with k fixed at P1's outcome, once with the default response and once with the compact one, both
  on the same span.
- **Pass rule, fixed now:** P1's two floors (coverage and notes per source exchange) apply to both P2 runs. The
  compact reply is recommended only if its wall seconds per source exchange are **at least 25 percent below** the
  default-response run at the same k on the same span; a smaller gain is logged as no detectable gain. Like k, a
  recommended compact reply is **provisional** until its setup passes both entry criteria again.
- **Duplicate guard, fixed now:** the similar-node block exists to stop duplicates, so P2 also counts, per source
  exchange, writes whose response carried the top similarity tier (duplicate or possible duplicate). The compact reply
  **fails** if that count exceeds the default-response run's on the same span by more than **0.10 per source
  exchange**, whatever its speed.

### P3. Window size. Only if the GPU fits it.

No run before the card's memory is measured at the current 131,072 setting and at the next size, with the same model
and context-length variant. If the larger window does not fit with headroom, P3 is dropped and logged as such.

**Order:** P1 (k = 3, then k = 5), then P2, then P3 if it fits. Each pilot gets a parameters entry here before it runs
and a result entry after; the setup hash of each value is logged with it.

## Speed pilots: run A first, and the attribution controls (logged 2026-11-16, before any pilot runs)

Existing data, not a pilot. Code: [tools/coverage.py](../tools/coverage.py) (sha256 `4fbf2b19285f363c…`); its output
here: [pilot-coverage-controls-output.txt](pilot-coverage-controls-output.txt) and
[pilot-coverage-runA-1-45.txt](pilot-coverage-runA-1-45.txt). The design owner read an earlier version's output (without control 5 and
before matching was restricted to content); this version's output goes to him before any pilot runs.

- **Controls, all pass, each with a mutant that makes it fail:** a planted node per exchange is credited once (1);
  a quote of exchange j only is not credited to j + 1 (2); text shared by j and j + 1 credits neither and counts as
  ambiguous (3; mutant: the ambiguity rule off credits both); a 14-character coincidence with an exchange of the round
  credits nothing at 40 characters (4; mutant: a 10-character minimum credits it); a claim-only match never counts
  toward the quote column; a quote of the rendered wrapper credits nothing (5; mutant: matching the rendered text
  credits it). A lowered minimum does not make control 2 fail, because the ambiguity rule already blocks that path;
  that variant is kept in the output as INFO, and control 4 is the one that tests the minimum.
- **Run A, exchanges 1 to 45 (k = 1):** 215 store-confirmed observations, **4.78 notes per source exchange**.
  Coverage under the old created-during rule 45/45; under the new rule **45/45 at 40 characters** (45/45 at 20, 42/45
  at 80). 25 nodes credit nothing: 22 quote fewer than 40 characters (headings and short phrases) and 3 quote only the
  session line the feeder renders on every exchange (session number and the dataset's time anchor, e.g. "conversation
  session 1, time anchor March-15-2024"): real information, but not evidence of reading that particular exchange. Quote length: median 85 characters (p25 63, p75 113). **The two-thirds threshold stands; no
  re-set.**
- **Shift control (real data):** with every node attributed five exchanges late, coverage falls to **5/45**; the 6
  nodes still credited quote conversation text that also occurs in their own exchange (material the conversation
  repeats), none a match to the shifted exchange alone. The first version of the code matched the rendered exchange,
  wrapper included; its shift control credited 7/45, and one of those was a node quoting only the session/time-anchor
  header, which occurs in every exchange. Matching was changed to content only and control 5 added, before any pilot.
- **For the result entry:** run A is at the ceiling (45/45), so this guard can only show a drop; coverage also depends
  on quote length, so the quote-length distribution is reported per k beside it.

## Correction: the brief in the published harness (logged 2026-11-16, before any pilot runs)

**What was wrong.** The published [tools/feed.py](../tools/feed.py) lacked the brief's purpose sentence (change 5,
E3): "Later, after your context has been compacted, I will ask you questions about this conversation, so keep
whatever record you will need to answer them." E3 and every gate run on `8762312e` were fed by a copy that has it. Found by the study
lead while building the speed-pilot feeder; confirmed independently by the design owner from the public file.

**Cause, measured (from the session record and both repositories), not inferred.**
- 2026-11-14T21:26:22Z: a coding sub-agent was briefed to port the harness from an earlier practice copy (the one
  the E3 copy was then made from). That copy never had the sentence.
- 2026-11-14T21:28:02Z: for E3 the study lead made a new copy from that same practice copy and added the sentence
  to its brief. Nothing carried it to the port.
- 21:30:54Z and 21:49:29Z: the two port commits. Neither contains the sentence; it was never in this repository,
  so nothing removed it.
- The E3 copy's `feed2.py` also logs each turn's end time (`utc_end`); not student-visible. Also absent from the port.

**Why the identity check passed.** [check-port-identity.py](../tools/check-port-identity.py) compares two copies
(brief, proctor marker, per-exchange line, fact sheet, nudge, rendering, and every string literal). It was run
against the copy the port was made FROM, and the two were identical. It compared the right things against the
wrong reference: nothing tied its reference to the copy the runs used. **Fixed:** the reference must now hash to a
pinned sha256 (the copy the runs used, as the setup record pins it) or the check refuses. Controls, output in
[port-check-controls-output.txt](port-check-controls-output.txt): pinned to the runs' copy, the corrected port is
identical (exit 0); the uncorrected port, one sentence apart, fails on the brief (exit 1); the port's source as
reference is refused (exit 2); and the checker as it was on 2026-11-14, with no pin, passes that source against the
uncorrected port (exit 0), which is the original failure reproduced.

**Corrected.** `tools/feed.py` now carries the sentence at the same place; `tools/feed2.py` logs `utc_end` as the
runs' copy does. Against the runs' copy, the port check now reports identical.

**Does the entry gate on `8762312e` stand? Shown, not argued.** [tools/gate-input-evidence.py](../tools/gate-input-evidence.py)
rebuilds each run's reading messages from the runs' own `feed.py` (sha256 `d2abfd38…`) as the run's feed script
does, and compares them with every reading message in the run's own transcripts. Output in
[gate-input-evidence-output.txt](gate-input-evidence-output.txt):
- criterion 1, three runs (conversations 9, 20, 9): 3/3 messages byte-identical each;
- criterion 2, run A (conversation 9 whole): **135/135** byte-identical;
- in every run, message 1 opens with the brief and carries the purpose sentence.
Control: with the port's source `feed.py` (no sentence) the same check fails at message 1 (run A 134/135). So the
gate results on `8762312e` stand: its content did not change, its id was incomplete. Other practice runs (the talk
probe, the long recall run, T1) are not re-checked here.

**From here.** Pilot setup ids add the imported `feed.py`'s sha256 and the turns-per-round value, and the build
walks the feed script's study-local imports and fails if any is not a component (design owner's ruling). The
registered gate rebuild takes the imported `feed.py` as a component as well.

## Speed pilots: the feeder, the setup ids, and the instrument fixes (logged 2026-11-16, before any pilot runs)

**The feeder.** [tools/feed4.py](../tools/feed4.py) is the gate runs' feed script plus `--per-round K`: K consecutive
exchanges in one message, each rendered exactly as at K = 1, the brief only before the first round, and every logged
row naming the exchanges it carried. It imports the corrected [tools/feed.py](../tools/feed.py). Checked: its K = 1
plan of conversation 9, exchanges 1 to 45, is byte-identical to the 45 reading messages run A's student received; its
K = 3 rounds are exactly the K = 1 messages joined by a blank line. `--dump-plan` prints the plan and starts nothing.

**Setup ids, with the import walk.** [tools/setup-id.py](../tools/setup-id.py) builds the id by the 8762312e rule (sha256
of the sorted component lines) and walks the feed script's imports: every study-local module it reaches must be
declared as a component, or the build fails. Output in [setup-id-output.txt](setup-id-output.txt):
- control 0: the old rule, walk off, on the gate runs' feed script reproduces `8762312e…` exactly;
- control 1: walk on, the imported `feed.py` undeclared: FAIL;
- control 2: walk on, `feed.py` declared: `797ba450…`, the id 8762312e would have had with the brief covered;
- control 3: one changed byte in the imported `feed.py` changes the K = 3 id (`a684c54f…` to `362862ce…`); mutant,
  walk off: the same byte change leaves the id unchanged (`0cc7f042…` both times).

**The pilot setups.** Same snapshot, rendered `CLAUDE.md`, exam line, grant line, plugin tree, window setting, install
flags and Claude Code version (2.1.325, read at build time) as `8762312e`; the feed script is `feed4.py`, the imported
`feed.py` is a component, and the turns per round are named:
- K = 3: `a684c54f1f0eed63ef6c8e26d117a387277a524c57af808320428ca9fb96c773` *(superseded below: `feed4.py` changed)*
- K = 5: `1439d221a55c3382cb9a62124e8cbe2b3c6244f37c52ead3ce131564a3f1c2fc` *(superseded below: `feed4.py` changed)*

**The pinned reference, checkable from this repository.** The runs' `feed.py` cannot be published byte for byte: it
names the local model endpoint twice, which this repository's privacy scan refuses, and any edit would change the
hash it is pinned by. [pinned-runs-feed.json](pinned-runs-feed.json) carries its sha256 and its student-visible
components, and `check-port-identity.py PORTED_DIR` compares a copy against them (anyone can run it). With a reference
directory, the reference must hash to the pinned file's value or the check refuses; `--reference-sha` overrides with a
printed warning. Output in [port-check-controls-output.txt](port-check-controls-output.txt), regenerated.

**Instrument fixes in [tools/coverage.py](../tools/coverage.py)** (design owner's two catches): the content of an exchange
is parsed against `feed.py`'s own wrapper constants and any other shape raises an error (control 6, mutant: one extra
header line, refused); rule 2 reads `quote_verified` from the store and prints how many nodes it excluded (on a scratch
copy of run A's store with one node marked unverified, it excluded 1). Control 5 now runs on `feed.render`'s real
output; control 7 ([pilot-render-check-output.txt](pilot-render-check-output.txt)) checks, on the K = 1, 3 and 5 plans,
that every exchange's render sits verbatim in its round and strips to the user's and assistant's text whole. The run
command takes any K (rounds from the logged rows) and adds coverage by position in the round, wall seconds and input
tokens per source exchange, compactions inside rounds, and covered exchanges credited only by text the conversation
showed earlier. Run A's earlier lines are unchanged; its new lines: by position 45/45, 259.4 s and 322,163 input tokens
per source exchange, 20 compactions (0.44 per exchange), and 0 exchanges covered only by repeated text.
[gate-input-evidence.py](../tools/gate-input-evidence.py) now prints where each run's planned count came from.

**Next.** K = 3 runs after the design owner's line on this commit; then K = 5.

## Speed pilots: before K = 3 runs, the design owner's five points (logged 2026-11-16, before any pilot runs)

**1. The pilot runs the files its id hashes.** `feed4.py --expect-components FILE` hashes the `feed4.py` and `feed.py` it
actually loaded (from their own file paths), prints both, and refuses (exit 3) unless they equal the setup's component
lines; a run without that file is refused. The check runs before anything else, so a refusal starts nothing and
unloads no model (a first version reached the model unload on refusal; caught by the controls, fixed before this
commit). Per-K component files: [pilot-setup-K3.txt](pilot-setup-K3.txt), [pilot-setup-K5.txt](pilot-setup-K5.txt).
After a run, `gate-input-evidence.py --plan` compares the received reading messages with the plan `feed4.py
--dump-plan` wrote from the same files before the run, byte for byte. Controls in
[pilot-preflight-controls-output.txt](pilot-preflight-controls-output.txt): matching components proceed; one differing
hash is refused; no component file is refused; run A against a K = 1 plan of its 135 exchanges passes 135/135; against
a K = 3 plan it fails. The runner is the study lead's local script (sha256 `10c9711d75493abc…`): a fresh copy of the
setup snapshot, the plan dump, the run, the co-load sampler, then the evidence and coverage commands into the run
directory; its hash is printed in each run's setup record.

**Final pilot ids** (changed from the previous entry because `feed4.py` changed for point 1, as the id scheme requires):
- **K = 3: `7b73fe7b4a53b24f2a70c3b6ee8d6eafc942490c7d74fa95e1c7aa3ac6433597`**
- **K = 5: `8262a44456f4b1a22f269594109868c773944069a880355d12c2818c7a73f5d2`**

**2. A known confound, stated before the run.** The brief, unchanged for the pilot so that K is the only variable,
still tells the student the conversation arrives one exchange at a time and to take notes after each exchange. At
K > 1 that is false for the student. So a drop in late-position coverage may come from that mismatch rather than from
batching itself. If a K is recommended, the brief's wording for K > 1 is decided for the gate re-pass setup, which is a
new setup anyway.

**3. Co-load.** [tools/coload-sampler.sh](../tools/coload-sampler.sh) runs beside each pilot for its whole length and
writes, every 60 seconds, the GPU's memory and utilisation, its compute processes, the host load average and the host
reservation lists to `coload.txt` in the run directory. That file stays local (it lists other users' commands); the
result entry reports its summary. K = 3 starts only after the design owner says in the Office that his merge-gate test
run on this host has ended, so the pilot's wall time is not measured under that load.

**4.** At K > 1, `coverage.py` labels the old created-during line as round-level, trivially high and not comparable with
K = 1.

**5. The setup text is unchanged.** `feed4.py`'s FACT_SHEET and NUDGE source segments hash to
`1f2da5a0fe2ca6c81f666de4d14fd250666baf7374e86793b266b71ed5fbf090` and
`933c9a1d930ea27b80be3e97a58f83faa8c0c2306745ed2f1a883ece7803fa6e`, equal to the gate feed script's. The pilot sends no
setup message: it starts from the setup snapshot, taken after the first session.

**A limit, stated once.** The import walk sees import statements; it does not see dynamic imports or data files a
feed script reads.

## Speed pilot P1, K = 3: result (logged 2026-11-16, after the run)

Setup `7b73fe7b…`, benchmarks commit `76df0353`, conversation 9, exchanges 1 to 45 in 15 rounds, arm 2 only. Started
2026-11-16T17:11:49Z, ended 18:16:42Z, exit 0, all 15 rounds completed. Both loaded-file hashes matched the setup before the
run. **Input evidence: PASS**, 15 of 15 reading messages byte-identical to the plan, message 1 opening with the brief
and carrying the purpose sentence ([pilot-K3-input-evidence.txt](pilot-K3-input-evidence.txt)). Coverage output:
[pilot-K3-coverage.txt](pilot-K3-coverage.txt).

| per source exchange, exchanges 1 to 45 | run A (k = 1) | K = 3 |
| --- | --- | --- |
| wall seconds | 259.4 | **86.5** (67% below) |
| automatic compactions | 0.44 (20) | 0.18 (8, each beginning inside a round; 8 of 15 rounds had one) |
| input tokens, summed over model calls | about 322K | 145K |
| notes (store-confirmed observations) | **4.78** (215) | **2.31** (104) |
| coverage at 40 characters (20 / 80) | 45/45 (45/45, 42/45) | 45/45 (45/45, 42/45) |

- **Coverage detail.** By position in the round: 15/15 at the 1st, 2nd and 3rd, so the compactions that began inside
  rounds did not drop late positions. Ambiguous nodes 4; 12 nodes credit nothing at 40 characters; rule 2 excluded 0
  nodes (every observation in this store is marked verified); covered exchanges credited only by text the
  conversation repeats from an earlier exchange: 0. Quote length: median 95 characters (p25 71, p75 112; 7 under
  40), against run A's median 85. Real-data negative control (every node attributed five rounds late): 1/45. The
  round-level old rule gives 45/45, which is trivially high at k = 3 and not comparable with k = 1.
- **Against the decision rule, as fixed before the run:** coverage at least two thirds: **met** (45/45). Notes per
  source exchange at least half of run A's on the same span (at least 2.39): **not met** (2.31; 104 notes where 108
  were needed). **K = 3 is not kept.** Its speed gain would have passed the 25 percent bar, but the rule recommends
  only a kept k. The floor is not re-set after the data. Run A sits at the coverage ceiling (45/45), so coverage
  could only show a drop and showed none; the notes floor is the measure that moved.
- **The notes are fewer AND shorter, not consolidated** (context, not part of the rule;
  [tools/pilot-record-volume.py](../tools/pilot-record-volume.py), outputs
  [run A](pilot-record-volume-runA-1-45.txt) and [K = 3](pilot-record-volume-K3.txt)). ENGRAM claim text per source
  exchange: 541 characters against run A's 2,217 (234 against 464 per observation); quote text 218 against 433.
- **Finding: the setup has a second note-taking channel, and this run used it heavily.** The student's environment
  includes the harness's own auto-memory folder, a place outside ENGRAM where it can keep notes. One occurrence shows
  the channel is open; it does not show what opens it. At K = 3, from its first round, the student wrote notes there: 71 Edit/Write calls (1.58 per source exchange, 1,639 new characters per
  source exchange), ending at a 44,699-byte notes file and a 3,443-byte index, which it introduced in its own words
  as "the local notes backup and index". Run A, from the same setup snapshot, instruction file and Claude Code version,
  never wrote there: its auto-memory folder is empty after all 135 exchanges, its 24 file writes in the whole run (the
  first about nine hours in) all went to a temporary directory, and the 5 redirect-like matches in its shell commands on exchanges 1 to 45
  are all text inside quoted strings, not file writes. **The cause is not measured:** one run each, so turns per
  round and run-to-run variation are not separated. What it means for the study: at this k, counting ENGRAM notes
  undercounts what arm 2 kept, and recall in a scored run could come partly from a file the harness arm can also
  use.
- **The design owner's ruling on the finding (2026-11-16, before K = 5).** (1) K = 3 not kept stands; the floor is not
  re-set. (2) The finding is about the setup, not about k, and is written in that order. (3) K = 5 runs as logged, on
  three conditions: K = 3's auto-memory folder is preserved whole with hashes before anything touches it (done: both
  files copied, the copy's sha256 equal to the folder's and to the run's own transcript copy); K = 5's auto-memory
  folder is shown EMPTY at its first exchange from the arm home itself, not from the restore script's intent (the run
  script now calls [tools/pilot-memcheck.sh](../tools/pilot-memcheck.sh) after the restore and before the first
  exchange, writes its output into the run's setup record, and stops on any file or an unknown layout; its controls,
  each with the failing case shown: [pilot-memcheck-controls-output.txt](pilot-memcheck-controls-output.txt), with
  the setup snapshot at 0 files); and K = 5's entry reports the same measures with
  [tools/pilot-record-volume.py](../tools/pilot-record-volume.py) unchanged, beside run A on exchanges 1 to 45.
  (4) A k = 1 re-run on exchanges 1 to 45 runs only if K = 5 shows the habit too, or if the cause is needed later.
  (5) **No official run starts until the auto-memory folder is ruled on as part of the setup for both arms**
  (available to both, or to neither), with a new setup id and the entry gate's standing re-examined against it; that
  is a pre-registration matter, put to the project lead. Until then every pilot entry says that the channel was open.
  (6) Unchanged: the student is never told about ENGRAM, and never told to avoid the folder either.
- **The channel was open in this pilot** (the auto-memory folder existed, empty, in the setup snapshot).
- **Co-load** (65 samples, one a minute). GPU memory at most 28,664 of 32,607 MiB, the student's model; the sampler's
  GPU process list was empty in every sample although the model was loaded, so on this host it does not see
  processes and the memory figure is the check. Host load average 2.6 at the start, then 7.0 to 14.2 throughout. A
  test-suite run by another user of the host held a 6 GB host-memory reservation in 41 of 65 samples, from
  17:35:51Z to the end. Run A has no co-load log, so the two runs' host load is not compared.

## Entry gate, criterion 2, run A: result (gate EVIDENCE for setup `8762312e`, not the registered gate run; logged 2026-11-16)

Logged after the project lead had seen run A's result and the note-volume finding. **Status, in one sentence:** run A
does not count as the registered entry-gate run because its setup's plugin tree was measured to differ from `dev` in
19 files, so the gate is met again on a rebuilt setup under the two conditions logged above.

- **Run.** Conversation 9, all 135 reading exchanges, then the proctor's `/compact`, then the 20 official questions,
  one session. Started 2026-11-15T18:39:07Z, ended 2026-11-16T08:14:58Z, exit 0; no error, no timed-out turn, so the
  abort rule did not fire. Input evidence: 135 of 135 reading messages byte-identical to the plan (logged above).
- **Analysis:** the pre-logged one, unchanged (sha256 prefix `2a338912c2c8dd46`, re-hashed today; its controls
  `cd5549b2eb5f5df6` and runner `a3e7695d8c9bde35` also unchanged). Output:
  [gate2-runA-analysis-output.txt](gate2-runA-analysis-output.txt), the transcript's host path on line 1 replaced by
  its file name.
- **Writing: HOLDS**, 135 of 135 reading exchanges with a store-confirmed write (needed 90); 683 reading-phase nodes.
- **Natural compactions during the reading: 84** (two during exchange 111), plus 3 automatic compactions during the
  questions. The projection logged before the run said 4 to 5; the correction logged during it said about 50.
- **Recall: MET.** 17 counting questions (Q1 and Q2 are abstention questions and Q16 has no source ids, so 3 do not
  count); 0 excluded as hook-delivered; **17 of 17 PASS**, needed 9. Of the 17, 12 are "delivered and read" (the hook
  named a source-exchange node AND the student read one with a tool) and 5 are "read" (a tool read only). k, the
  natural compactions after a question's latest source exchange, runs from 4 to 83.
- **Run B is not run**, by the rule logged during run A: run A ended with 10 or more natural compactions.
- **What PASS measures:** the retrieval path (a tool read, in the question's own turn, of a node written during the
  question's source exchanges), not whether the answer is right. Answer quality is outside criterion 2 and is graded
  separately.
- **Speed and the window,** for the pilots: per-exchange wall time by thirds 259 / 307 / 452 s; 13h36m in all (see
  the run-A baseline under the speed pilots).
- **Where the analysis was committed before the run.** In the study lead's working repository (commit at
  2026-11-15T18:38:23Z, 44 seconds before the run started), not in this one; this log carries its three sha256
  prefixes (commit `b90b012`). The analysis file and the controls file each contain one host path, so byte-identical
  copies cannot be published here as they are; how outside readers can check them is put to the design owner.

## Running now

- Speed pilot P1, K = 5 (setup `8262a444…`) waits for the design owner's host test runs, scheduled in the gap after
  K = 3; it starts after his line that all of them have ended, with the auto-memory start check above. Run A (entry gate criterion 2, setup `8762312e`)
  finished 2026-11-16T08:14:58Z with exit 0; its result entry is not yet in this log.

Earlier fact bearing on the talk probe's question: in every practice sandbox the student wrote its own ENGRAM
nodes during the first session (2 person nodes and 2 to 5 observations), and none during any exam reading
before the exam line. The first-session skill instructs those writes, so they show capability under
instruction only.
