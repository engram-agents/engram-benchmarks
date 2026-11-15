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
hash pins it, and that hash was published before the result existed, in the author's comment on this
pull request (2026-11-15T13:50:34Z, GitHub's stamp) and in a message to the design owner
(2026-11-15T13:50:36Z), who quoted it back at 13:51:02Z.
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

## Running now

- Probe 2 (from below), as logged above.

Earlier fact bearing on the talk probe's question: in every practice sandbox the student wrote its own ENGRAM
nodes during the first session (2 person nodes and 2 to 5 observations), and none during any exam reading
before the exam line. The first-session skill instructs those writes, so they show capability under
instruction only.
