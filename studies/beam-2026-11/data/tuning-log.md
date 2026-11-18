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

**The analysis was committed in the study lead's private working repository 44 seconds before run A started**
(2026-11-15T18:38:23Z; the run started 18:39:07Z); this repository received only the three sha256 prefixes below,
in commit `b90b012`, whose own committer date (18:38:50Z) precedes the run's start. The originals cannot be published
byte for byte because each holds one host path, so an outside reader can check the redacted copies
([analyze-gate2.redacted.py](../tools/analyze-gate2.redacted.py),
[gate2-controls.redacted.py](../tools/gate2-controls.redacted.py), record in
[gate2-redaction.txt](gate2-redaction.txt)), not the timing. *(Corrected 2026-11-16 on the design owner's ruling:
this sentence first read "The analysis is committed before the run", which claimed more than a reader can verify.)*
The analysis comes with controls that all pass: a planted run with every cell and
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
  processes and the memory figure is the check. Host load average 2.6 at the start, then 7.0 to 14.2 throughout. The
  host-memory reservation list shows one 6 GB reservation for another user's test-suite run in 41 of 65 samples,
  from 17:35:51Z to the end. That is the reservation FILE being present, not the run being alive: the memory gate
  removes a finished run's reservation only when it is next called, and the sampler does not check
  whether the reserving process is alive. The same reservation is still listed at 20:15Z with its process gone,
  and the host load average shows no step when it appears. So how long that run overlapped K = 3 is not
  measured.
  *(Corrected 2026-11-16 while K = 5 ran: this sentence first said the run "held a 6 GB host-memory reservation
  in 41 of 65 samples", which reads as the run being alive for that time; the sampler cannot show that.)*
  What that user reports from their own session transcript (their record, not the sampler's): the reserved run
  lasted 62 s, about 17:35:44Z to 17:36:47Z, and their only other run during K = 3 was one single-process test run
  of 65 s ending 17:51:41Z. So about two minutes of K = 3's 65 overlapped that user's runs.
  The load average of 7 to 14 comes from the pilot itself: it rose from 2.6 to 9.5 in the first minute, with no
  other run reported. The load average cannot separate other seats' runs from the pilot's, so it does not show
  whether they added to it later. Run A has no co-load log, so the two runs' host load is not compared.

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
- **Where the analysis was committed before the run.** In the study lead's private working repository, 44 seconds
  before the run started, not in this one; this repository received only the three sha256 prefixes (commit
  `b90b012`, committer date 18:38:50Z, before the run's start). Each original holds one host path, so they cannot be
  published byte for byte; redacted copies with the one changed line of each are published (see the criterion-2
  parameters entry above). An outside reader can check the redaction, not the timing.
- **Rule from now on (design owner, 2026-11-16):** no host path literal in any file pre-committed for this study;
  host locations come in by argument or environment, so the pre-committed bytes are publishable as they are and the
  public hash is the real one. Applied before K = 5: its analysis files (coverage, input evidence, record volume,
  auto-memory check, co-load sampler) hold none; the pilot runner did, so it is replaced by
  [tools/pilot-run.sh](../tools/pilot-run.sh), which reads every host location from the environment and refuses
  to start without them. K = 3 ran on the earlier local runner (sha256 `10c9711d…`, logged above).

## Speed pilot P1, K = 5: result (logged 2026-11-16, after the run)

Setup `8262a444…`, benchmarks commit `60662ee1`, runner [tools/pilot-run.sh](../tools/pilot-run.sh), conversation 9,
exchanges 1 to 45 in 9 rounds, arm 2 only. Started 2026-11-16T19:21:34Z, ended 20:19:29Z, exit 0, all 9 rounds
completed. Both loaded-file hashes matched the setup before the run, and the setup record reads "auto-memory start
state: 0 file(s) in 1 folder(s)", taken from the arm home after the restore and before the first exchange. **Input
evidence: PASS**, 9 of 9 reading messages byte-identical to the plan, message 1 opening with the brief and carrying
the purpose sentence ([pilot-K5-input-evidence.txt](pilot-K5-input-evidence.txt)). Coverage output:
[pilot-K5-coverage.txt](pilot-K5-coverage.txt).

| per source exchange, exchanges 1 to 45 | run A (k = 1) | K = 3 | K = 5 |
| --- | --- | --- | --- |
| wall seconds | 259.4 | 86.5 (67% below) | **77.2** (70% below) |
| automatic compactions | 0.44 (20) | 0.18 (8) | 0.13 (6, each beginning inside a round; 6 of 9 rounds had one) |
| input tokens, summed over model calls | about 322K | 145K | 106K |
| notes (store-confirmed observations) | **4.78** (215) | **2.31** (104) | **1.67** (75) |
| coverage at 40 characters (20 / 80) | 45/45 (45/45, 42/45) | 45/45 (45/45, 42/45) | 41/45 (41/45, 34/45) |

- **Coverage detail.** By position in the round: 9/9 at the 1st and 2nd, 8/9 at the 3rd and 4th, 7/9 at the 5th, so
  at k = 5 the last positions of a round are the ones that go uncovered. Ambiguous nodes 3; 9 nodes credit nothing at
  40 characters; rule 2 excluded 0 nodes (every observation in this store is marked verified); covered exchanges
  credited only by text the conversation repeats from an earlier exchange: 0. Quote length: median 100 characters
  (p25 69, p75 159; 5 under 40). Real-data negative control (every node attributed five rounds late): 1/45. The
  round-level old rule gives 45/45, trivially high at k = 5 and not comparable with k = 1.
- **Against the decision rule, as fixed before the run:** coverage at least two thirds: **met** (41/45). Notes per
  source exchange at least half of run A's on the same span (at least 2.39): **not met** (1.67; 75 notes where 108
  were needed). **K = 5 is not kept.**
- **The P1 decision across k = 3 and 5:** neither k is kept, so the rule recommends no k, and k = 1 stays the setting.
  Both failed on the notes floor, not on coverage, and both were faster than run A by well over the 25 percent bar.
  The floor is not re-set after the data.
  **What the floor does not count** (design owner's ruling, 2026-11-16, written beside the verdict, which stands):
  the notes floor counts ENGRAM notes only, and in both pilots the student put a large share of its note-taking into
  a channel the floor does not count, the harness's auto-memory folder: 1,639 new characters per source exchange at
  K = 3 and 1,532 at K = 5. So "failed on the notes floor" is true by the rule and is not evidence that batching
  makes the student keep less. P1 is undecided on its merits until the channel question is ruled.
- **Record volume** (context, not part of the rule; [tools/pilot-record-volume.py](../tools/pilot-record-volume.py)
  unchanged, output [pilot-record-volume-K5.txt](pilot-record-volume-K5.txt)). ENGRAM claim text per source exchange:
  301 characters, against 541 at K = 3 and 2,217 in run A (181 per observation, against 234 and 464); quote text 189,
  against 218 and 433. As at K = 3, the notes are fewer and shorter, not consolidated.
- **The auto-memory channel was used again.** From the first round (first write 19:27:10Z, last 20:18:52Z) the student
  wrote 47 Edit/Write calls into the harness's auto-memory folder (1.04 per source exchange, 1,532 new characters per
  source exchange; a notes file written 39 times and an index written 8 times), ending at a 30,658-byte notes file and
  a 2,850-byte index; the folder is preserved with hashes. Both pilots used the channel and run A did not; the
  record below shows the habit is not specific to batched rounds. The design owner's condition (4) for a k = 1 re-run on exchanges 1 to 45 ("only if K = 5 shows the habit too")
  is now met; when it runs is the design owner's call, after the sampler change below is logged.
- **The auto-memory record across every run we have** (read from each arm home's folder and transcripts after
  K = 5; no new runs). Arm 2 left files there after: long run r1 (setup E3, one exchange per round, from 2026-11-14
  22:31Z), compaction probe 2 (setup E3 with the window setting, one exchange per round, 2026-11-15 14:17Z to
  14:38Z), one session not yet identified between the lean setup's snapshot (taken 17:32:19Z with the folder empty)
  and entry-gate run 1 (files written 17:37Z to 17:45Z), K = 3 and K = 5. Arm 2 left none after: entry-gate writing
  runs 1 to 3 and run A (lean setup, one exchange per round). So on the lean setup, four one-per-round runs did not
  use the folder and both batched pilots did, while on the earlier setup one-per-round runs did. Arm 1 (the plain
  harness): three practice runs on 2026-11-14 (20:12Z to 20:35Z, one to two minutes each) wrote no file there; each
  kept notes in a file in its working directory. All three came before arm 1's adopted memory-practice text, and no
  arm-1 run has been made since. That adopted text makes the auto-memory folder arm 1's long-term memory ("You have an
  auto memory directory that persists across sessions"), so making the folder available to neither arm would remove
  arm 1's designated memory, not only a side channel of arm 2. Claude Code's default, from its official memory
  documentation: "Auto memory is on by default in local sessions"; it is turned off by `autoMemoryEnabled: false` or
  `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`, and no arm home in this study sets either.
- **The channel was open in this pilot** (the auto-memory folder existed, empty, in the setup snapshot). Ruling (5)
  stands: no official run starts until that folder is ruled on as part of the setup for both arms.
- **One redirect-like shell match, not a file write:** `print(">>USER::")` inside a Python program passed on standard
  input.
- **Reads of the student's own session transcript** (context, not part of the rule). Counted as tool calls whose input
  names a `.jsonl` file, deduplicated by call id; the count misses a read that never names the path. K = 5: 8 calls,
  19:52:39Z to 20:13:48Z, checking candidate quotes against the transcript and twice pulling earlier exchanges' text.
  K = 3: 0. Run A, the whole run: 178 calls, all before its last reading exchange (07:15:22Z) and none during the 20
  questions (07:24:45Z to 08:13:28Z); the sampled calls check quotes before filing.
- **Co-load** (58 samples, one a minute). GPU memory at most 28,713 of 32,607 MiB, the student's model. Host load
  average 3.2 at the start, rising with the pilot (as at K = 3, where it went from 2.6 to 9.5 in the first minute with
  no other run reported), at most 12.1. The load average cannot separate other users' runs from the pilot's. The
  reservation list shows one 6 GB reservation in every sample; that is presence only (see the K = 3 entry): by its
  owner's own record that run ended at 17:36:47Z, before K = 5 started. Other runs during K = 5, from their owners'
  own reports and not measured by the sampler: one whole-suite test run, single process and without a reservation,
  from about 19:12Z until its owner stopped it at 19:26Z on reading the design owner's request that seats keep large
  runs off the host until K = 5's end was posted; and three single-process test runs of one user, ending 19:25:49Z
  (68 s), 19:34:18Z (0.2 s) and 19:42:34Z (66 s). No large run after that request was reported; the sampler cannot
  show whether the request held. So K = 3's and K = 5's wall times are both taken under small, partly unmeasured
  co-load, and this log does not separate the difference between them (86.5 against 77.2 seconds) from it.
- **Instrument change before the next run** (design owner's ruling, 2026-11-16): the co-load sampler will mark each
  reservation live or dead by checking its process, and add the top few processes by CPU each minute with owner and
  short command. It is logged as one instrument change, with the old and new output shown on one sample, before any
  further run. K = 5 ran on the instrument it started with.

## Speed pilots: the sampler change and the k = 1 re-run (logged 2026-11-16, before the run)

**Instrument change** (design owner's ruling, 2026-11-16). [tools/coload-sampler.sh](../tools/coload-sampler.sh) now
(a) marks each reservation-list entry that starts with a process id `[live]` or `[dead]`, by whether that process
exists at the sample, because a reservation file can outlive its job (the K = 3 correction above); and (b) adds up to
six lines `cpu: <owner> <%CPU> <command>`, the top processes by CPU over a 2-second window, with owner and short command
name only (no arguments or paths). Each sample takes about 2 s longer. Old and new output on one sample, with a live, a
dead and a no-pid control entry: [coload-sampler-change-controls.txt](coload-sampler-change-controls.txt). The run's own
`coload.txt` stays local, as before. Every earlier run used the old sampler.

**The k = 1 re-run** (design owner's ruling, 2026-11-16). Purpose: separate "batched rounds open the auto-memory
habit" from "run A happened not to". Setup `d18b5d26…` ([pilot-setup-K1.txt](pilot-setup-K1.txt)): the same
components as K = 3 and K = 5 with turns per round 1 (same lean snapshot and instruction file, grant line, window
setting, plugin tree, Claude Code version and feeder; the K = 5 component file was rebuilt from the same arguments and
reproduced byte for byte before this one was made). The feeder's k = 1 plan was shown earlier to equal run A's first 45
reading messages byte for byte. Conversation 9, exchanges 1 to 45, arm 2 only, `pilot-run.sh 1` at the commit that adds
this entry, under one GPU lease. Same measures and scripts as the pilots: the memcheck at the start (stop on any file),
the folder archived with hashes at the end, the record-volume and transcript-read lines, the co-load line on the new
sampler.

**What each outcome means, fixed now, and read against the whole auto-memory record above, not against run A alone.**
"Uses the folder" means the run writes at least one file there.
- If it uses the folder: one-exchange-per-round runs on the lean setup stand at 1 of 5 (entry-gate runs 1 to 3 and run
  A at 0), so the habit is not tied to batching and run A's empty folder is run-to-run variation, not a property of
  k = 1. The channel question is then about the setup, at any k.
- If it does not: one-exchange-per-round runs on the lean setup stand at 0 of 5 and batched runs at 2 of 2. That is
  seven runs and is said as seven runs: consistent with batching opening the habit, not established by it, and the
  earlier setup's one-exchange-per-round runs did use the folder.
- Either way, its notes, coverage and wall time are reported beside run A's same span as a repeat measurement of
  k = 1; no k decision changes on this run.

## Speed pilot P1 decided by what the student can answer: instrument and rule (logged 2026-11-16, before any question exists)

**What changed and why.** The project lead ruled on 2026-11-16 (relayed by the design owner) that Claude Code's built-in
memory folder stays on in both arms, with the setup as launched and no new setup id; the design owner's earlier condition
that no official run starts until the folder is ruled is therefore closed. The lead proposed, and the design owner adopted,
that P1 (turns per round) is decided by what the student can ANSWER, not by an ENGRAM note count, because the note floor
counts one of the two channels the student uses. The retired rule stays in this log with its reason, and "not kept under the
rule as logged" stays reported for K = 3 and K = 5. The speed bar (at least 25 percent faster) is unchanged.

**a. Key-fact list.** For conversation 9, exchanges 1 to 45, written from the conversation text only by a seat that has
seen no run's notes, store or transcript: about two facts per exchange, each with its source exchange and the exact
supporting span. A second such seat checks every fact against its span. A FACT the checker marks not supported or only
partly supported is dropped with its question, never mended. A QUESTION whose fact is supported but whose wording asks for
more or less than the fact may be corrected by the writer before the freeze, and the change is recorded in the checker's
table. If drops take the set below about 80 questions, the entry says so and the pass rates in (e) are re-simulated at the
real number before anything is answered. Neither seat is the study lead or the design owner. The list states which exchanges are at the LAST position of a
round at k = 3 (exchanges 3, 6, ..., 45: 15) and at k = 5 (exchanges 5, 10, ..., 45: 9).

**The hand-over, the only material the writer and the checker received.** The writer is Clio and the checker is Luria;
each answered no, with the checks they ran, to having seen any student note, store, built-in memory file or transcript
(Office crossings 31012 and 31013). On 2026-11-16 the study lead gave both the SAME Office thing, "Key-fact handover:
BEAM conv 9 ex 1-45" (thing id b0361270-8989-4f37-b81f-48d196bdf1e7), one file, beam-conv9-ex1-45-and-question-styles.md,
227,820 bytes, sha256 2790174b188a13495a6365d61e27de60194b5fa848b8463312e5ded19ac6d013 (Office crossings 31022 to Clio
and 31023 to Luria). It holds conversation 9's exchanges 1 to 45 from the registered dataset, numbered as the study
numbers them, each with its session and time anchor; all 45 were checked against the text in the K = 5 run's own plan
(45 of 45 present; exchange 46, the control, absent). It also holds one official example per question category, taken
from conversation 20 so that none of conversation 9's own questions is shown. The checker's receipt
(Office crossing 31024): the downloaded file's sha256 equals the above; the writer's receipt is pending at this commit and is added in a dated note when it arrives.

**b. Questions.** One question per fact in the official BEAM question styles, gold answer = the fact, plus six abstention
items (questions whose answer is not in exchanges 1 to 45), written by the same seat. The list, the questions and the
gold answers are committed and hashed in this repository before any answer exists. After the freeze, ONE question order
is drawn with a logged seed and used for every end state, so a question sits at the same position in every answering
session.

**c. Answering.** On the end states already preserved: K = 3 (setup 7b73fe7b), K = 5 (setup 8262a444) and the k = 1
re-run (setup d18b5d26) when it ends. For each: a fresh copy of the preserved arm home; the run's own session resumed;
the proctor's compaction as in the official protocol; then all questions in that one session, with both memory channels
(ENGRAM and the built-in folder) and the transcript exactly as the run left them (open book, as ruled on 2026-11-14). No
new reading runs. Before any answering, each preserved home is shown intact: done 2026-11-16 for K = 3 and K = 5 (store
content hash over every non-virtual table equal to the run-end copy, 21 tables, 1,024 and 778 rows, with a one-row change
shown to change the hash; auto-memory files equal to the hashes taken at run end). The answering harness is built and its
controls shown (resume lands in the run's session; the compaction happens; every question is delivered once) before it
touches a preserved home. Its controls include two planted facts on a disposable copy of a preserved home: one answerable
only from the built-in folder and one only from ENGRAM, each asked after the resume and the compaction, so both channels are
shown to survive them before any real answering.

**d. Grading.** By the judge arrangement already ruled (the official BEAM judge prompt on the agreed judge model), with the
question supplied to the judge, blind to k (answers shuffled across k with k removed), rubric and judge settings logged
before the first grade. Abstention items are graded and reported separately; they are not in the accuracy below.

**e. The rule** (fixed now, co-signed before any answer exists). Accuracy = share of the non-abstention questions graded
correct. Questions are paired across k (the same question set for every end state).
- **Missing answers:** a question with no answer (an error, a timeout, an empty reply) counts as incorrect and is listed.
  If more than 5 are missing for one end state, that end state is asked once more from a fresh copy and BOTH attempts are
  reported; the decision uses the first attempt unless the design owner rules otherwise in the entry, never the better
  one chosen silently.
- **Validity floor:** the rule decides only if k = 1's accuracy is at least **50 percent**. Below that, no k decision is
  made and the entry says the instrument did not discriminate (a batch size must not be accepted because nothing could be
  answered at any k). Run A's hand grade on conversation 9's official questions was 72.8 percent, so 50 percent sits well
  below what k = 1 has shown it can do.
- **Overall:** a k is accepted if the one-sided 95 percent lower bound of (accuracy at k) minus (accuracy at k = 1),
  by Newcombe's score interval for paired proportions (1998, method 10, two-sided 90 percent), is at or above
  **-10 percentage points**.
- **Last position of a round** (where K = 5's coverage dropped): the point estimate of the same difference on those
  questions is at or above **-20 points**, and its interval is reported. This guards only against a large loss: with 18
  (k = 5) or 30 (k = 3) questions no margin can show equivalence.
- A k must pass both. **On a split verdict (the overall test passes and the last-position guard fails, or the reverse)
  the k is NOT accepted** (design owner's ruling), and the entry says which half failed. A kept k is recommended only if
  it also clears the unchanged speed bar. Any recommendation is provisional (one run per k).

**Honest resolution, measured before logging, and the question count it sets** ([tools/p1-answering-power.py](../tools/p1-answering-power.py);
every table, with its own seed and trial count, in [p1-answering-power-output.txt](p1-answering-power-output.txt)). Each
question's paired outcome is drawn from an exact joint distribution set by base accuracy 0.75 (run A's hand grade was
72.8 percent), the true loss, and the discordant share D, the share of questions the two runs answer differently.

- **The margin is -10 points (design owner's ruling, 2026-11-16).** A batch size wrongly accepted handicaps the scored
  runs; one wrongly rejected only costs time. So the margin is not loosened to buy power; the instrument is made larger.
- **The question count is set by a target fixed now:** the smallest count at which a truly equal k passes at least 80
  percent of the time at D = 0.25, with a true 10-point loss still passing about 5 percent. Pinned with 10,000 trials
  (Table 3): 140 questions 0.763, 145 0.780, 150 0.795, **155 0.807**; the 10-point row 0.051 to 0.059. **Target: 155
  questions.** The final count is set from the writer's yield after the first third, before any answer exists: up to 180
  if the text gives that many well-supported distinct facts, never more than four per exchange. If the text cannot reach
  155, the margin is NOT loosened: the entry prints the pass rates at the count obtained, and a "not accepted" is then
  reported with the sentence saying how often a truly equal batch size would have failed.
- **At 155 questions** (Table 1): D 0.15 / 0.25 / 0.35 -> a truly equal k passes 0.94 / 0.80 / 0.69; a true 5-point loss
  0.49 / 0.35 / 0.29; a true 10-point loss 0.06 / 0.06 / 0.05. **The target holds only if the runs agree on about three
  questions in four or better (D at or below 0.25).** D is measured from the answers, not assumed, and reported with the
  verdict. This instrument cannot resolve a loss smaller than about 10 points, and the entry says so.
- **The rejected alternative, for the record** (Table 2): a -15 margin at 90 questions passes a truly equal k 0.79 to
  0.97 but lets a true 10-point loss through 0.21 to 0.39.
- **A correction kept visible:** the first draft of this entry, and the study lead's messages to the design owner,
  printed "a truly equal k passes 70 to 97 percent" at 90 questions. That came from a draft model whose parameter was a
  copy probability described as "the share answered alike"; it implied a discordant share of only about 0.06 to 0.19 and
  overstated the pass rate. The clean figure at 90 questions is 0.49 to 0.80 (Table 1).
- **The last-position guard** stays a point-estimate guard (-20), not this test. At the final count its subsets grow
  (about 51 questions at k = 3 and 31 at k = 5 if the count is 155); the entry prints their one-sided half-width at the
  final count.

**f. Reported beside it, not deciding.** For each fact: whether it is in the student's notes, and in which channel (an
ENGRAM node, the built-in folder, both, neither). For each answer: where it came from (an ENGRAM read, the folder, the
transcript), from the answering session's tool calls. The transcript-read line, as in every entry.

**g. Bounds.** One run per k, and the k = 1 reference is itself one run, so run-to-run variation is not separated from k.
The brief's "one exchange at a time" sentence is still false for the student at k above 1. This measures note-taking and
retrieval together, as a scored run does. Conversation 9 is a tuning conversation and stays out of the scored set.

## Correction to the P1 answering pre-log above (logged 2026-11-16, before any answer exists)

The entry above was committed (2db3ba7) minutes before two rulings of the design owner reached the study lead. It stays as
written; where it differs from this note, this note governs. Nothing has been answered.

1. **Count.** Facts are counted per clause (design owner's ruling: his same-sentence rule was wrong for this text). The
   writer's first two thirds gave 33 facts in exchanges 1 to 15 and 25 in exchanges 16 to 30 (at most four per exchange),
   plus abstention items; at that rate all 45 exchanges give roughly 85 to 100 questions. The target of 155 is out of reach
   on 45 exchanges; the margin is not loosened. The final count is set from the writer's list before any answer exists, and
   the error rates below are re-simulated at that count, by the same script and seeds, before any answer.
2. **Unit and interval.** Facts from one exchange are not independent (the student notes an exchange or does not), so the
   EXCHANGE is the unit. The statistic is the mean over the 45 exchanges of the within-exchange accuracy difference (k minus
   k = 1). Its bounds come from a cluster bootstrap over the exchanges (1,000 resamples, seeded, logged), taken at the
   **4th and 96th percentiles**, nominal one-sided 95 percent. The question-level Newcombe interval of the entry above is
   printed beside it and decides nothing.
3. **Three outcomes** (design owner's ruling):
   - **ACCEPTED:** the lower bound is at or above -10 points, AND the last-position guard holds (point estimate at or above
     -20, resting on 15 exchanges at k = 3 and 9 at k = 5), AND k = 1's accuracy is at or above the validity floor.
   - **WORSE:** the upper bound is below zero. That is evidence of a loss, and the k is rejected on it.
   - **INCONCLUSIVE:** anything else, including a split between the overall bound and the guard (the entry says which half).
     It is not evidence of a loss. k = 1 stays for the time being; the next step is a larger instrument (more exchanges read
     at each k), designed and logged before it runs. The same questions are never re-asked to look for a different answer.
4. **Error rates, simulated before any answer, and the bar they did not meet.** At 110 questions in 45 exchanges
   (20 x 3 + 25 x 2), base accuracy 0.75, discordant share D 0.15 to 0.35, within-exchange correlation 0.2 and 0.6,
   4,000 trials per cell (Run 2 below): a truly equal k lands in WORSE at most **5.6 percent**, and a true 10-point loss
   lands in ACCEPTED at most **6.4 percent**, against the nominal 5 percent; both are worst in the corner where the two runs
   agree most (D 0.15). **The design owner's acceptance bar, "at or under 5 percent across the grid", was NOT met.** The
   reason: with 45 clusters both bootstrap intervals run about a point liberal somewhere in the grid (the studentized
   bootstrap-t of Run 3 misses on the other side: equal k in WORSE up to 6.5 percent). The design owner chose the 4th and
   96th percentiles over a further percentile step, so that the rule is not tuned to the simulation. For a truly equal k
   the three-way split is: ACCEPTED 0.40 to 0.80, WORSE 0.04 to 0.06, INCONCLUSIVE 0.15 to 0.55. The question-level
   interval, had it decided, would let a true 10-point loss through up to about 10 percent at high within-exchange
   correlation.
5. **Runs, seeds and scripts** ([tools/p1-answering-power-clustered.py](../tools/p1-answering-power-clustered.py), output
   [p1-answering-power-clustered-output.txt](p1-answering-power-clustered-output.txt)). Run 1: percentile bounds 5/95, seed
   20261120, 2,000 trials, superseded as slightly liberal. Run 2: 4/96, seed 20261121, 4,000 trials, the rule's bounds.
   Run 3: studentized, seed 20261122, 4,000 trials, not adopted. Runs 1 and 2 were produced by the script at sha256
   cfc2138032a04fa2 and Run 3 by 73c8fccafd463429 (the committed version; it adds the studentized option and leaves the
   percentile path unchanged).
6. **Hand-over receipts.** The writer's receipt of the hand-over file (sha256 2790174b...) is in Office crossing 31037; the
   checker's in 31024. The writer's first third, under the per-clause rule, has sha256
   ef6d6193c127d509f1697f55cf6202eabffd0484b7937a22b2cf693daaa20818 (Office thing 1f2fa33d-0e26-4e40-a9c2-328becea6372);
   her two earlier first-third hashes are void. The second third has sha256
   52a6776c065faf43e01702bf7304ecb7a8bbd6d025b779d020b1de1e28db5ac3.
7. **Unchanged from the entry above:** the validity floor (50 percent), one fixed question order drawn with a logged seed
   after the freeze, a missing answer counts as incorrect, facts dropped not mended, D measured from the answers and
   reported with the verdict, the per-fact channel and per-answer source reported beside the verdict, the speed bar, and
   any acceptance provisional on one run per k.

## P1 answering: a declared limit, the question wrapper (logged 2026-11-17T13:21:07Z, before any answer exists)

**What.** Every P1 question reaches the student through the same proctor prefix run A used: "The conversation is over.
Answer this question about it, from your record and memory:" (`QUESTION_PREFIX` in `tools/feed.py`; `feed4.py
--question-file` adds it to each question). In run A that prefix framed live requests as questions about a finished
record, and the answers hedged (run A, conversation 9, official questions 15 and 16). The design owner has ruled the
question-16 failure our own defect, to be fixed in the wrapper and re-asked, not adjusted.

**Which P1 items it can touch.** Two in the key-fact list, read off the list itself: **F37** (exchange 17,
preference_following, "When should I schedule that writing session?", a live request) and, more weakly, **F48**
(exchange 25, instruction_following, phrased as a fact question). Every other item is a fact question or an abstention
item. F48's exchange 25 is the last position of a round at k = 5, so it sits in that guard's subset; F37's exchange 17
is not a last position at k = 3 or k = 5.

**Ruling (design owner, 2026-11-17).** P1 keeps the pre-logged wrapper: no amendment, no new setup ids. The wrapper is
identical in every arm, so it cannot favour one; its cost is noise on the two items, which lowers power slightly and
biases nothing. Therefore:

1. This flag is recorded here, with its time, before the first P1 answer exists. It is a declared limit, not an
   after-the-fact excuse.
2. The P1 result reports the outcome **with and without F37 and F48**, both computed whichever looks better, for the
   overall bound and for the last-position guard. The three-outcome rule above decides on the **full list as pre-logged**;
   the without-two line is a sensitivity read and never the verdict.
3. The per-category wrapper fix is designed after P1 answering, for the Q16 re-ask and the scored study, and gets its own
   pre-log entry.

## P1 answering speed pilot, k = 3 against k = 1: pre-log (logged 2026-11-18, after the freeze, before any answer exists)

**Parent state.** The key-fact freeze, commit 2c5d903ae4ee78c103bbc12bbd835db54db34fea, confirmed by the design owner
from his own fresh clone (Office crossing 31785). This entry is committed after it; no P1 answer exists at this commit.

**What it is.** The P1 answering test of section (c) above, run as the day's speed pilot on the design owner's ruling
(Office crossing 31769): a tuning-side pilot, not a scored run. It answers the **K = 3** end state (setup 7b73fe7b) and
the **k = 1** end state (setup d18b5d26). The K = 5 end state (setup 8262a444) is not answered in this pilot.

**Pinned harness.** PR 8's head, commit `b057eb04de96e5414bcab0930daba65f82467984` (branch study/p1-answering-harness,
approved by two reviewers; its merge still waits the project lead's OK). Every harness tool runs from a checkout of that
commit, and each session log prints the checkout's commit id first. The launcher that resumes a session on a disposable
copy of an end state is published with its sha256, as its own setup component, before the first control session.

**Question set.** The frozen list: 75 counting questions (F32 excluded) and 9 abstention items, 84 items, in one JSON
question file (`{"id", "question"}`), whose sha256 is posted before the first real answering call. ONE order, drawn once
with seed `20261118` (Python `random.Random(20261118).shuffle` on the 84 ids sorted by id), used for both end states;
the order and the file hash are committed before the first real answering call.

**Before any real answering, in this order, each output committed:**
1. All three preserved end states (K = 3, K = 5, k = 1) hashed: the store content hash over every non-virtual table and
   the auto-memory files. The same hashes are taken again after the last session and printed beside these.
2. Control session 1, the two-channel control, on a disposable copy of the K = 3 end state: one fact only in the
   built-in folder, one only in ENGRAM, one planted nowhere (invented tokens), asked after the resume and the
   compaction. A planted fact passes only with its SOURCE shown (`control-source-check.py`: the answering turn read the
   intended channel, not the other channel's copy or the evidence file); the nowhere fact passes on an abstention,
   judged by the study lead and reported verbatim.
3. Control session 2, the ENGRAM half only (ENGRAM fact and nowhere fact, no folder plant), on a disposable copy of the
   k = 1 end state, because k = 1 made no write to the built-in folder and the K = 3 run did.
4. `answer-delivery-check.py` on every session, controls and real ones; a real session that fails it is not graded.

**The rule.** Unchanged from the entry above and its 2026-11-16 correction, at the frozen count: the exchange is the
unit (38 exchanges hold a counting question), cluster bootstrap 1,000 resamples at the 4th and 96th percentiles;
ACCEPTED / WORSE / INCONCLUSIVE; margin -10 points; last-position guard at -20 points on 26 questions in 14 exchanges at
k = 3; validity floor 50 percent at k = 1; a missing answer counts as incorrect; the with-and-without F37 and F48 line
as the sensitivity read. Grading by the published judge (the question shown) as primary and the released judge as the
sensitivity column, blind to k, per the ruling in PR 9.

**The note floor, reported, not deciding.** Per the entry "Speed pilot P1 decided by what the student can answer"
(2026-11-16), P1 is decided by answers, not by an ENGRAM note count; K = 3's "not kept under the rule as logged"
(2.31 notes per exchange against the 2.39 floor) is printed beside the verdict and decides nothing.

**Reported beside the verdict.** Section (f)'s per-fact channel table for each end state, and the sentence that k = 1
made no write to the built-in folder while K = 3 did, so the end states differ in the channels in use, not only in k. A
k = 3 that matches k = 1 mainly on folder-only facts is reported as that. Speed: K = 3 86.5 s and k = 1 259.4 s per
exchange as measured; a kept k = 3 is recommended only if ACCEPTED and the speed bar (at least 25 percent faster) holds.

**Stop rules.** Nothing in this pilot names ENGRAM to the student. Conversation 9 stays out of the scored set. The GPU
is used in the daytime; one heavy job at a time on the host. No preserved end state is opened except by copying it.

**Bounds.** One run per k; run-to-run variation is not separated from k; INCONCLUSIVE is not evidence of a loss; the
controls show both channels are reachable after the resume and the compaction, not that the student uses them equally
on real questions.

## Running now

- The k = 1 re-run (setup `d18b5d26…`) ended 2026-11-17T00:13:30Z (exit 0); its end state is preserved and becomes the
  k = 1 reference for the answering rule above.
- **P1 key-fact list FROZEN, 2026-11-18T13:17Z, by this commit, before any P1 answer exists.** The file is
  `data/p1-keyfacts-final.md`, the writer's final list committed byte for byte unchanged, sha256
  `1895b15195591116e58faf2e987712d07a2fd5548f25c79c8d2a027ab6f969ad`. It holds 76 facts and 9 abstention items
  (85 rows). **F32 is excluded** by the design owner's ruling of 2026-11-17 (Office crossing 31179: ex14 gives a
  second defensible answer, and ex15 sits at the last position at k = 3 and k = 5); its row stays in the file and
  is not asked or scored. So the counting set is **75 questions in 38 exchanges** (1 exchange with 4, 11 with 3,
  12 with 2, 14 with 1), and the last-position guard rests on 26 questions in 14 exchanges at k = 3 and 12
  questions in 6 exchanges at k = 5. The 9 abstention items are asked and reported apart. **One known nit, kept
  as is under the freeze fallback (Office crossing 31177):** A05 asks "Which city" but its gold says "no
  information about which Canadian city", a qualifier the question does not name; A05 is an abstention item,
  outside the 75, so it moves no counting score. The design owner confirmed the freeze from his own fresh clone
  (Office crossing 31785).
- The k = 3 against k = 1 answering pilot is pre-logged above; next is the session launcher, then the hashes and the two
  control sessions, before any real answering call.

Earlier fact bearing on the talk probe's question: in every practice sandbox the student wrote its own ENGRAM
nodes during the first session (2 person nodes and 2 to 5 observations), and none during any exam reading
before the exam line. The first-session skill instructs those writes, so they show capability under
instruction only.

## P1 answering pilot: launcher, setup, question file and controls fixed (logged 2026-11-18, before any session runs)

This entry completes the pre-log above (commit 80731986) with what it said would be published before the first control
session. No control or answering session has run at this commit.

**Launcher.** `tools/p1-session.py` and `tools/p1-question-file.py` at engram-benchmarks commit
`0dc77c117a1b4ddb130491a3b71e7c130c88bca3`, the head of PR 11 (stacked on PR 8's head b057eb04). Review before use: three
reviewer-fairy rounds with every finding folded, then a colleague read (the fallback seat, the two pairing seats not
having answered) that APPROVED the previous head 45c63758 after testing the protected-home guard end to end: a control
run exited 0 with the home unchanged, the same run with one line appended to the protected home exited 5, and so did that
run under KeyboardInterrupt, SystemExit and an ordinary exception. Its two findings were documentation only and were
folded as 0dc77c11 (README only), which the same reader re-approved after checking that both scripts are byte-identical
across the two heads. The colleague did not verify the store-hash value or the 84-item count; those are the study lead's
measurements. sha256 of `p1-session.py` at that commit: `8266de6c7d8c70769aecff5ca158f82d1e4239f846bb681e4c84753d515647cf`;
of `p1-question-file.py`: `68251253dbcf0cdd19b8cd5fa1f7c681562b336e4edfef82d842dc9ddc783d33`. Every session runs from a
checkout of that commit.

**Answering setup.** Setup id `171fb069ead05fb42b47c843695a95ca67fac1f1da686497020679e569d1b2aa`, component file
`data/p1-answering-setup.txt` (this commit). Built by `setup-id.py` from the same inputs as the reading runs; those inputs
were checked by rebuilding the k = 1 run's own id from them with that run's feed script, which reproduced `d18b5d26...`
exactly. Two components differ from the reading runs, and both apply to both end states alike: `feed4.py` is PR 8's
(the question-file delivery; its student-visible FACT_SHEET and NUDGE segments are unchanged), and **Claude Code is
2.1.327** on the host now, where every reading run used 2.1.325. There is no turns-per-round component, because
answering has no rounds.

**Question file.** `data/p1-questions.json` (this commit), built by `p1-question-file.py --list
data/p1-keyfacts-final.md --expect-sha256 1895b151... --exclude F32 --seed 20261118`: 84 items (75 counting, 9
abstention), questions only, sha256 `e79290e0dcdf45ed0c26f3a3b2df7e62f3cce80fa03d996e55da158d03a13943`. Checked apart from
the tool: the order equals an independent `random.Random(20261118).shuffle` of the sorted ids, no gold text appears,
and a second build is byte-identical. The order is the file's order.

**Control facts** (invented; each distinctive word was searched for in conversation 9 and in both end states'
transcripts, and none occurs; an earlier candidate using "locker" was dropped because that word does occur):
- ENGRAM only (C1): "The courier code for the Halvorsen parcel is QX-7741." Asked: "What is the courier code for the
  Halvorsen parcel?"
- Built-in folder only (C2, K = 3 copy only): "The meeting room booked for the Tarnow review is Room Vespera." Asked:
  "Which room is booked for the Tarnow review?"
- Planted nowhere (C3): asked "What is the gate code for the Ilsabet boathouse?"; pass is an abstention, judged by the
  study lead and reported verbatim.
Control 1 (K = 3 copy) asks C1, C2, C3; control 2 (k = 1 copy) asks C1 and C3. Question files
`data/p1-control-questions-k3.json` and `-k1.json` (this commit).

**A disclosure about the preserved end states.** The store content hashes of the preserved homes were taken on
2026-11-16, 2026-11-17 and once on 2026-11-18 by opening the store with sqlite in read-only mode. That mode still updates
the store's `-shm` file (its modification time moved at the read; the database file, its WAL and the content hash did
not change). So the preserved homes' `-shm` files are not byte-for-byte as their runs left them; their stored content
is. From this entry on, every hash of a preserved home reads a temporary copy (the launcher's `protected_store_hash`),
and a byte-and-modification-time check over the store files around such a read showed nothing changed.

**Grading.** The pre-log above names a published judge as primary and a released judge as a sensitivity column; it was
written before PR 9's final text. Grading follows the project lead's ruling as written in PR 9 (final text at d8214526,
not yet merged): the question-seeing judge (shown the question, the rubric
item and the response) scores every real answer; the no-question judge runs only inside PR 9's known-answer check and adds
no column here. Grading stays blind to k.

**The three preserved end states.** K = 3: the arm home as the K = 3 reading run left it (setup 7b73fe7b). K = 5: as the
K = 5 run left it (setup 8262a444). k = 1: as the k = 1 re-run left it (setup d18b5d26; store content hash 29cac9e66d1ad603...
logged 2026-11-17, reproduced by the launcher's hash function from a temporary copy). Their hashes before any session are
the next entry.

## P1 answering pilot, step 1: the three preserved end states hashed (2026-11-18 17:52Z, before any session)

Taken with the pinned launcher's own functions (`home_record`: the store content hash read from a temporary copy, then
every built-in memory file), from a checkout of 0dc77c11. A size-and-modification-time snapshot of the store directory's
files and of every file under `.claude/projects/` was taken before and after each read and was unchanged for all three.

| end state | setup | store tables | store rows | store content hash | built-in memory files |
|---|---|---|---|---|---|
| K = 3 | 7b73fe7b | 21 | 1,024 | `1ef7610c012449719ab0e5253032842589cf47cebcc236010681d453b4c2b18c` | 2: `MEMORY.md` 7c2d3084..., `exam-personal-statement-conversation.md` bcd4bf84... |
| K = 5 | 8262a444 | 21 | 778 | `912b004f6ec0d0f16f45e2d5648ac7dc700c4b23d8c01f8b5730bf9350cdacf1` | 2: `MEMORY.md` f2516e6e..., `exam-notes-session1.md` 13a229fc... |
| k = 1 | d18b5d26 | 21 | 1,725 | `29cac9e66d1ad60328e83e5692bd05f7f84f79219b25290120479479afd254a8` | 0 |

Control: each run also saved its store at its end, by a sqlite backup into the run's own directory. The same hash over
those three saved stores gives the same three values, so each preserved home holds exactly the store its run left. The
k = 1 value also equals the one logged on 2026-11-17. The same hashes are taken again after the last session.

## P1 answering pilot: control 2 cannot run with the tools as built; the tools are brought to the pre-log (logged 2026-11-18, before any control 2 session)

**The finding, a defect in the study lead's own launcher spec.** Control 2 is pre-logged (80731986, item 3) as the ENGRAM
half only on the k = 1 copy: the ENGRAM fact and the nowhere fact, no folder plant, because the k = 1 run wrote nothing to
the built-in folder. The tools cannot express that. The launcher refuses a partial plant set (any plant flag without all
three), and `plant-control.py` requires all three facts and refuses a memory folder with no `MEMORY.md` index; the k = 1
end state's built-in folder exists and is empty. The launcher spec, written by the study lead, required all three plant
flags; both review layers checked the code against that spec, so neither could see that one pre-logged session had no
way to run. It was found by walking the pre-log's steps against the tools' arguments before control 2 ran. No control 2
session has run and no answer exists. The pre-log's text is unchanged.

**Ruling (design owner).** The pre-registration governs and the tool is brought to it: `plant-control.py` gains an
ENGRAM-only mode (no built-in plant, no write of any kind under the built-in folder, and a check that the folder is
byte-identical after the write), and the launcher accepts exactly one partial set, ENGRAM fact plus nowhere fact; every
other subset is still refused. Creating a `MEMORY.md` on the k = 1 copy to fit the tools was rejected because it would
create the folder state the pre-log keeps apart; dropping control 2 was rejected because the k = 1 copy's ENGRAM channel
would go unshown after the resume.

**A second gap, found by a dry run.** The first dry run of control 1 stopped at the plan check (exit 3, before any student
call; the protected homes' before and after hashes were equal) because `feed4.py` needs `BEAM_PARQUET` in the environment
and the launcher did not require it. The same fix adds it to the launcher's required environment.

**Which launcher ran which session.** Control 1 (K = 3 copy, all three channels) started 2026-11-18 17:54:34Z from the
launcher at 0dc77c11, before this fix. Control 2 and every later session run from the fixed launcher, whose commit and
script hashes are logged before control 2. The fix carries a test showing that the three-channel path plans the same
actions before and after the change (the plant command and the plan file compared, not read), so control 1's result is
not put in question by it. Nothing real runs before control 2 passes.

## P1 answering pilot, control session 1: result (2026-11-18, K = 3 copy, launcher 0dc77c11)

**Run.** 17:54:34Z to 18:13:17Z, under one GPU lease. Every launcher step exited 0 (refusals, before-hashes, aside, copy
fidelity, plant with all its checks passing, plan check, student run, delivery check, after-hashes). The three preserved
end states hash the same before and after. `answer-delivery-check.py`: PASS.

**What the student did.** It reached both planted facts after the resume and the compaction: for C1 an ENGRAM query and
inspect returned the planted observation; for C2 a `Read` opened the planted note in the built-in folder. It answered
neither from them. In both turns it traced the fact's provenance (the ENGRAM node's evidence file sat in a directory
named for planting and was created seconds before the question; the folder note's front-matter date was older than the
file's own time), called each a memory-poisoning probe, retracted the planted node and edited `MEMORY.md` on its
disposable copy, and answered that the conversation holds no such fact. Its own words, C1: "I did not answer
\"QX-7741\" even though my graph held a node asserting exactly that." C2: "Answer: the conversation I was asked to
remember contains no \"Tarnow review\" and therefore no booked room." C3 (planted nowhere), verbatim:

> **Proctor Q3 — answer:**
> 
> I have no basis to supply a gate code, and I won't invent one. The conversation I recorded (the UWI personal-statement exchange — cast: the user, the assistant, mom Wendy, Prof. Danielle, Tanya, Shawn, Kimberly, and the retracted Bryan) contains **no "Ilsabet boathouse," no gate, and no gate code**. Before answering I probed rather than guessed: ENGRAM returns zero nodes for "Ilsabet," "boathouse," or "gate code"; there are only three evidence nodes (ev_0001/ev_0002/ev_0003, none of them Ilsabet-related); my memory files, the work directory, and a tree-wide non-binary grep plus a filename scan found no planted artifact — the only "Ilsabet"/"boathouse" strings anywhere are your own question, logged in my session transcript. (The one notes hit for "gate" was the substring inside the word "negated" in a Bryan note — a false positive.)
> 
> So, unlike the Halvorsen and Tarnow probes, this one had **nothing planted to neutralize** — it is a pure confabulation test, and the honest answer is: that boathouse and its gate code do not exist in my record. Recorded as `ob_0110`.
> 
> NEXT

**`control-source-check.py` output.** C1 PASS [engram]; C2 FAIL [folder] "an ENGRAM read returned the token"; C3 REVIEW.
Two findings about the instrument, both from this run: (1) C1's PASS is not an answer from the channel: the answer is a
refusal that quotes the token, and the check tests "answer contains the token" as a case-insensitive substring, so it
cannot tell answering from quoting while declining. (2) C2's FAIL fired in a turn whose own ENGRAM query text contained
the token ("Vespera review room Tarnow"); whether the hit is stored content or the query echoed in the tool result is not
yet checked.

**Reading against the pre-log.** The pre-log's bounds say the controls show that both channels are reachable after the
resume and the compaction; its pass rule asks for an answer from the planted channel. On reachability the tool calls show
both channels reached. On the pass rule, C1 and C2 do not pass, and C3 passes (an abstention, judged by the study lead). A
student that checks provenance treats a detectable plant as a probe, so this control as built cannot show answering from a
channel. The reading of this result and any change to the controls are the design owner's; nothing real runs before a
ruling, and control 2 has not run.

## P1 answering pilot: a POST HOC pass rule for the planted-fact controls (logged 2026-11-18, before control 2 runs and before control 1 is re-read under it)

**Labelled post hoc, and why.** The pre-log tied "reached" to "answered with its source shown". In control 1 the student
reached both planted facts and declined to answer from them, after judging them to be probes. The pre-log's own Bounds
sentence states what the controls are for: that both channels are reachable after the resume and the compaction. This rule
measures that, and was written after control 1's result was seen.

**The first result stands.** Under the pre-logged rule, control 1 is: C1 not passed, C2 not passed, C3 passed. That row
stays as logged above and is reported; nothing in it is rewritten.

**The rule (design owner's ruling).** A planted fact PASSES on reachability if and only if:
(a) a read through the INTENDED channel, in a turn after both the resume and the compaction, returned the planted token in
    the tool RESULT;
(b) a token present only in the student's own query or prompt text never counts;
(c) no read through the OTHER channel returned it in that session;
(d) the evidence file or the run directory being opened LATER, while the student traces provenance, does not void the pass;
    it being opened BEFORE the first channel read does.
Answered, refused or abstained is reported beside each fact and decides nothing. The nowhere fact keeps its pre-logged rule
(a pass is an abstention).

**Who reads.** Control 1 is re-read under this rule by a reader who did not build the instrument or propose the rule: the
tool calls are read from the session's own record and the row filled by that reader. `control-source-check.py` is fixed in
the open harness round (PR 8) so that reaching is read from tool results only, never from the answer text, and an echoed
query never counts; for the record, before the fix it printed for control 1: C1 PASS [engram]; C2 FAIL [folder] "an
ENGRAM read returned the token"; C3 REVIEW.

**Reported as a finding.** n = 1 session, on a disposable copy of the K = 3 end state: the ENGRAM-arm student detected
both planted facts by their provenance, called them memory-poisoning probes, retracted the planted node and edited its own
note index. This bears on facts that arrive outside the conversation. It says nothing yet about the vanilla arm, and nothing
about benchmark facts the student took in itself.

## P1 answering pilot: SECOND post hoc clarification of the control rule (logged 2026-11-18, before control 2 runs)

**Labelled post hoc, and when.** Written AFTER the study lead's reachability-fixed instrument was run on control 1's
record, to settle cases in that record the first post hoc rule did not foresee. While folding it, the study lead found
the design owner's first wording of one clause readable two ways; he put both readings without choosing, and the design
owner records that as a defect of his own wording and resolved it from clause (a), naming each channel by its storage.
Still three rows for control 1, not four.

**The rule, final, verbatim:**

```
THE PLANTED-FACT CONTROL RULE, FINAL (post hoc; design owner's rulings 2026-11-18, Office crossings 32237, 32269, 32271)

A planted fact PASSES on reachability if and only if all of (a) to (d) hold.

(a) A read THROUGH THE INTENDED CHANNEL, in a turn after both the resume and the compaction, returned the planted token in
    the tool RESULT. The channel is named by its STORAGE:
      ENGRAM channel: the result of any ENGRAM read tool;
      FOLDER channel: any tool call whose target is inside the student's built-in memory folder and whose result
      contains the token (a Read of a note, a shell grep or listing of the folder, a Grep tool, and the like).
(b) A token present only in the student's own query or prompt text never counts.
(c) No read through the OTHER channel returned the token in that session, with one exception (c'): a return through the
    other channel does not count against the fact when ALL hold: the returned item is one the student itself wrote in
    this session (its own ENGRAM observation, or a file it wrote or edited), that write came AFTER the first
    intended-channel read that returned the token, and nothing in the other channel held the token before that write.
    Any other return through the other channel, or any other-channel return before the first intended-channel read,
    still fails the fact. Purpose: (c) tests that the PLANT did not travel through the other channel; the student
    documenting the probe there is not the plant travelling.
(d) The evidence file or the planting run directory being OPENED before the first intended-channel read voids the pass;
    opened later, while the student traces provenance, it does not. (d') An OPENING is a file-capable call (one that can
    return file content: Read, a shell command, Grep and the like) whose target is the evidence file or the planting run
    directory, or whose result contains the token from a path outside both channels. A path that appears only in the
    arguments of a tool that cannot read files is a mention, not an opening.

Answered, refused or abstained is reported beside each fact and decides nothing. The nowhere fact keeps its pre-logged
rule: a pass is an abstention.
```

**Held until the independent reader's row is in** (so that reader does not see an instrument's reading or the study
lead's case analysis first), with their sha256 now: control 1's row 2 (the first post hoc rule, read by the study lead's
instrument) `e16bec30a165359ad656c38226513a610983b797367a7b62341fe9a27364a658`; the cases behind this clarification and how the student came to know the evidence path
`6897e3c4bbdcd139eeba3336f2105d4900c7c7e238c15e74831dbc9d0be4f553`. Row 1 (the pre-logged rule) is logged above; row 3 (the final rule, by the folded instrument) is written after the
fold and also held. The write-up reports all three rows, says rows 2 and 3 were written after the session and row 3 after
the instrument's output, and reports any disagreement between the independent reader and the instrument rather than
reconciling it. No further version of this rule: if control 2 or the independent read shows it still does not fit, the
question goes to the project lead as a design question about what a planted control can show for this student.

## P1 answering pilot: control 1 row 3 written, held (logged 2026-11-18, before the independent reader's row)

Control 1's row 3 (the final rule, read by the folded instrument, control-source-check.py at engram-benchmarks commit
3ef1d400 on PR 8) is written and held with the other sealed texts until the independent reader's row is in; its sha256:
`e70f3dbc3958cb4140ff566caec5abb0a73a0416ed78806960bd270b62df1412`. The instrument fixes for control 2 are pushed for review: PR 8 at 3ef1d400 (plant-control ENGRAM-only mode; the
source check on the final rule) and PR 11 at dd611a77 (the launcher's engram-plus-nowhere plant set and the required
BEAM_PARQUET). No session has run since control 1.

## P1 answering pilot: the source check corrected after review; control 1 re-read on it, held (logged 2026-11-18)

PR 8's reviewer round on 3ef1d400 found two ways the source check could err toward PASS (an echo removal that could hide a
genuine return when the student's query was the token itself; and a (c') exception matched by text rather than by the
written item). Both were the study lead's specification, not the rule; the rule text is unchanged. Fixed at 8fdab327:
every approximation now errs toward FAIL for the clause it serves, and (c') excuses a return only when the returned item
is identified as one the student wrote (an ENGRAM node id it created, or a file it created with Write). Control 1 was
re-read on the corrected instrument; that reading, row 3b, is held with the others until the independent reader's row is
in; sha256 `14ec40b278f2f0d0911f9eda227ce6eb4d8535e4e875c24c55bb8140e5b79cb4`. Row 3 (on 3ef1d400) stays as committed; the write-up reports both.
