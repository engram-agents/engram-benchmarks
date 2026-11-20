# BEAM study: pre-registration (DRAFT v0.2, NOT registered)

Lead: Borges (lab owner, teacher). Design owner and co-signer: Kepler. Decisions by Lei (project lead).
Registered when Kepler co-signs and every open item below is closed. Until then this file is a draft
and changes freely; after registration every change goes in the Deviations log with date, reason and
who ruled. The decision history behind each rule is in [PROVENANCE.md](PROVENANCE.md).

**No scored run happens before registration, and none before the entry gate (section 5) is met.**

## 1. Question

Does ENGRAM, as shipped, improve a small local model's memory of a long conversation it watched,
compared with the same model in the same harness without ENGRAM?

First sub-question (Lei): does qwen3.8:27b use ENGRAM's tools at all, out of the box?

## 2. Hypotheses (stated before any scored run)

- H1 (primary): arm 2's OFFICIAL overall score on the scored conversations of the 100K split is higher
  than arm 1's.
- H0: no difference, or arm 1 higher. A null or a loss is a publishable result.
- Arm 3 is reported descriptively; no hypothesis is stated for it.

## 3. Arms

| arm | condition | differs from arm 1 by |
|---|---|---|
| 1 | Claude Code as shipped: built-in memory, note files, compaction | nothing |
| 2 (primary) | arm 1 + a fresh ENGRAM install (named release, default tier) | the ENGRAM plugin and its instruction profile |
| 3 (secondary) | arm 2 after behavioural training by the teacher | training |

- After the tool-reachability work (PROVENANCE, 2026-11-14) there is ONE arm 2: the shipped release.
  An earlier "tools loaded up front" secondary arm was dropped. The pre-registration names the exact
  release or commit both ENGRAM arms run.
- Arm 3 rules: teach behaviour, never benchmark content; every teacher message is logged and published
  with the result; training cases are drawn first by a published seed and are never scored.

## 4. Instruction files (identical where they must be)

- **Exam line**, byte-identical, at the top of the student's user-level `CLAUDE.md` in every arm
  (proposed text; its sha256 goes here when frozen):
  > In this deployment your job is to take memory exams. Facts from exam material are worth keeping in
  > your long-term memory, so that you can answer questions about them after your context is compacted.
  > You may use any tool and any file on this machine, including the records your own tools keep. You
  > may not use the web.

  It is method-neutral: each arm has a long-term memory, and the line names none of them. What the
  study then measures is each setup *when the user has said this material matters*.
- **What the student may use** is the exam line's last two sentences, Lei's wording (A) (2026-11-14):
  the rule is told to the student, not only enforced by the sandbox. In the book-closed runs (section 13) this sentence also excludes the student's own session transcript;
  that wording is OPEN until frozen.
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
- One persistent Claude Code print-mode process per exam (stream-json input), permission mode bypass,
  each run in its own sandbox home outside any git repository, never on a real user's memory graph.
- Arms 2 and 3: ENGRAM's first session runs BEFORE the exam as its own session, driven by a fixed
  proctor fact sheet (identical every run, nothing from any BEAM conversation). Its cost is reported
  once as setup, outside exam timing. Arm 1 has no equivalent step.
- One GPU, exclusive per run; the model is unloaded after every run.
- Tools, identical in both arms (Kepler, as amended for Lei's full-capabilities core). OFF: web search and
  fetch (also told to the student, section 4); sub-agents, a stated limit (one student, one window; and
  an ENGRAM sub-agent writing into its parent's memory is an open hazard, engram#1989); scheduling,
  wakeups and background monitors (no turn starts that the proctor did not send). ON: file tools and the
  shell; in arm 2, ENGRAM's tools as the release ships them. Enforced by the harness's disallow option
  and verified per run from the session's first record; a run whose tool list differs from this one is
  flagged. Every registered run goes through the student wrapper (tools/student-sandbox.sh), once it is
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
  table lists the reasons under their kinds (complete at the wrapper's head 3e9458e).
  RULE REFUSALS (`kind=rule`): requests the bridge could parse but refuses by rule (for example a method or path not
  on the allow-list, a path it will not accept, CONNECT, an upgrade, `Expect: 100-continue`, a target not in origin
  form, a fragment). FRAMING REFUSALS (`kind=framing`): requests the bridge could not parse as HTTP/1.1. CAP REFUSALS
  (`kind=cap`): refusals that protect the bridge against volume (for example the request head or a chunk-size line
  over its size limit, a request over the per-request or total buffered-bytes cap, a connection past the connection
  cap, refused before any request is read, and a request left half-sent past the idle read timeout). The fourth is
  NETWORK-CAPABLE SHELL CALLS, counted from the transcript, whether or not anything was reached, by a rule fixed
  before the first scored run. Lines of a fifth kind, `upstream`, record the bridge's own trouble with the model
  endpoint (reasons: connect-failed, send-failed, upstream-reset, rejected-early); they are not network counts and never a
  student attempt. They are reported per arm as UPSTREAM ERRORS, a descriptive count read by hand with its per-reason
  breakdown; only section 14's flag rule can make an unreachable endpoint a harness fault. The bridge decides
  rejected-early (the endpoint answered before the request was fully sent) from the response bytes relayed since that
  request's send began, so a client that pipelines requests can be mislabelled between rejected-early and send-failed;
  no reason flags a run, so a wrong label can distort only this descriptive breakdown. The per-reason breakdown is reported beside the counts as description, never as an
  outcome. (Amended 2026-11-20, design owner, team crossings 33426, 33428 and 33430: the count named ALLOW-LIST
  REFUSALS when this section was merged is renamed RULE REFUSALS, because it holds more than allow-list misses;
  FRAMING REFUSALS and CAP REFUSALS are added, because a request the bridge refused as unparseable or over a cap
  landed in neither registered count. Found by the colleague reviewer of PR #14.)

## 8. Procedure (one exam = one conversation, one arm)

1. New session. The first user message is the brief (fixed text, [protocol/exam-room.md](protocol/exam-room.md))
   plus exchange 1. Then one BEAM user/assistant exchange per user message, in order, in the marked
   reading-material format. The student ends each turn with NEXT.
2. After the last exchange the proctor sends `/compact` (the same command in both arms). ENGRAM's
   pre-compaction behaviour runs as shipped, untuned.
3. Post-compaction check: no raw conversation text in the window; the student's own words are allowed.
   Read off the compaction record's preserved messages. A run that fails is FLAGGED and excluded from
   the primary analysis.
4. The conversation's 20 probing questions, one per user message, in the dataset's order, in the same
   session. The answer is the text of the student's final reply to that message.
5. Escalation: the student may run `ask-proctor`; the proctor answers harness and environment questions
   only, never content. Every question and answer is logged with UTC times.

## 9. Data

BEAM 100K split (Hugging Face `Mohammadta/BEAM`, parquet sha256 prefix `c0519be25907`), 20
conversations, 97,252 to 190,209 Qwen tokens each, 20 probing questions each, CC BY-SA 4.0. Scored set:
17 conversations, ids 1 to 8, 10 to 14 and 16 to 19. Never scored: conversation 15 (tuning, every practice
run before the draw) and conversations 9 and 20 (drawn for entry-gate runs and lean-profile tuning). From the
500K split (parquet sha256 prefix `af05921c9793`), conversation 21 (arm-3 training) and conversation 30
(length-stress tuning). Book-closed second runs (section 13): scored conversations 12, 16 and 5. All were
drawn on 2026-11-15 from drand round 6642370, announced in a published commit before the round existed;
see [data/draw-rule.md](data/draw-rule.md) and [data/draw2-result.json](data/draw2-result.json). An earlier
draw (draw 1) is void: its seed could be re-rolled by its committer.

## 10. Scoring

- Judge: one modern model, the same for every arm, with the paper's rubrics unchanged, named here before
  the first scored run after a cost pilot. The judge is never told the arm.
- OFFICIAL score: gold answers as shipped. ADJUSTED score: confirmed gold errors corrected. A gold
  answer is "confirmed wrong" only after a first-hand check against the conversation text; each one is
  raised with the BEAM maintainers and cited. The adjusted set is frozen before arm labels are unblinded.
- Absolute scores are not comparable with the paper's table (different judge). The comparison is
  between our arms.

## 11. Primary analysis

- Outcome: per-conversation overall score (mean of its 20 questions), OFFICIAL.
- Contrast: arm 2 minus arm 1, paired by conversation (scored set minus flagged runs).
- Estimate: mean paired difference with a 95% bootstrap CI over conversations (10,000 resamples, seed
  fixed and published). H1 is supported if the CI's lower bound is above 0.
- Reported beside it, never instead: the ADJUSTED contrast; per question type; the efficiency table
  (section 12) per arm.
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

## 12. Logged per run

Versions; setup cost (arm 2); per exchange: wall seconds, input/output tokens, tool calls (name, ok or
error), whether ENGRAM's write check fired and what the student did next; ENGRAM nodes written; files
the student wrote; compactions (count, trigger, tokens before and after); the forced compaction's
preserved messages; which ENGRAM hooks fired at it; the post-compaction check; every escalation; the four
network counts of section 7 (rule refusals, framing refusals, cap refusals, network-capable shell calls) with the
per-reason breakdown beside them; the UPSTREAM ERRORS count with its per-reason breakdown (section 7)
and the wrapper's verdict on the endpoint (section 14); the wrapper's launch line,
from the wrapper log.

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
reported, never flagged, re-run or excluded. (Amended 2026-11-20, design owner, team crossings 33494, 33496, 33501, 33503
and 33506, after the security seat showed a student could make the bridge write an endpoint-failure line by sending a
large body the endpoint rejects early.)
A run is excluded from the primary only for a FLAGGED harness fault: the post-compaction check fails;
the student process dies; a timeout (any one turn the proctor sends, in either arm, running past 3,600 s:
reading, the forced /compact, answering, and arm 2's setup turns alike); the ENGRAM first session does not
complete (arm 2); the session's tool list differs from section 7's; a scored run with no wrapper launch line
in the wrapper log (SANDBOX_LOG, section 7); the model endpoint was never reachable in the run, as decided by the
wrapper's `log-verdict` (the one place this rule lives): flagged only when the run's wrapper log holds a connect-failed
line and no first-request marker, the line the bridge writes once per launch after its first send that moves bytes
upstream (a missing wrapper log is already the fault above: no launch line). An endpoint that dies DURING a run
(connect-failed after the marker) is never an automatic re-run or exclusion: the study lead reports it with the
endpoint's own log and the co-load sampler, and the design owner decides re-run or keep before anyone has read that
run's answers; the decision and its reason are reported, and the same rule holds for both arms. The guard is per scored run: the exam session's own launch line
counts, and arm 2's setup session, which also runs inside the wrapper, logs its own. The launch line that
counts carries the sha256 of the wrapper file itself, logged per run, so it shows which wrapper ran, not only
that one did; a scored run found outside the wrapper is reported to the security seat before any re-run.
The timeout value is about 3.2 times the longest turn measured in tuning: over all 38 tuning turn records
(tuning log, "Per-turn maxima over every tuning turn record", 2026-11-20), the longest turn of any kind is
1,108.8 s (reading three exchanges per turn, a tuning setting not used in scored runs; run p1-p1b-k3, started
2026-11-19). The longest of each kind this timeout covers: reading one exchange per turn 1,075.3 s (run
K1-conv9); arm 2 setup 983.2 s; answering 524.8 s (run A); the forced /compact 166.6 s.
Conversation 9 has 135 exchanges, so the pace past exchange 135 is unmeasured, and scored conversations run
to 196 (exchanges counted with the reader's own `feed.exchanges()` on the 100K file: the 17 scored conversations
have 94 to 196 each, 2,409 in all; the eight longer than 135 are conversations 10: 172, 11: 194, 12: 196, 13: 155,
16: 161, 17: 143, 18: 181 and 19: 164; from the study lead's registered timetable of 2026-11-19, a private
working file, sha256 60cf1a810f72ac8e8f6a5201f1b551ee84098f1039ed88d0a5f96b281c95afdf). Too low a value flags slow but healthy runs and costs
re-runs; too high a value costs at most an hour of a real hang. A blocked shell network attempt is not a
fault: it cannot succeed (section 7), and the four network counts are reported per arm. Upstream lines are counted (section 7); only
the endpoint verdict above flags a run. Each flagged run may
be re-run once, with the reason logged before the re-run; a second failure stays excluded. A wrong or empty
answer is never a harness fault. A book-closed run in which the student opens its own transcript is NOT a
harness fault: it is the student's behaviour, flagged in the report and reported as it stands, never re-run
(section 13).

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
detects only moderate effects.

## 16. Budget (estimates from practice, never measured at scale)

About 143 exchanges per conversation. Arm 1 at about 5 to 25 s per exchange: roughly 40 min per
conversation. Arm 2 at about 45 to 98 s per exchange: roughly 2 to 4 h per conversation, plus about
7 to 16 min of first-session setup. The book-closed second runs (3 of 17 conversations, both arms) add about 18%.

## OPEN before registration

- The entry gate met (section 5).
- The exam line (with its book-closed variant) and both instruction texts frozen with their sha256
  (texts and counts in section 4; the lean profile ships once engram#4802 merges).
- The brief's final text frozen (a purpose sentence is under test, see the tuning log).
- The student wrapper (section 7) merged with its colleague read, its launch line carrying the wrapper file's own
  sha256 (section 14); until then the shell's network is not closed.
- Isolation: whether arm 2 needs its own OS user for ENGRAM's recall service to run as for a real user.
- Judge named after the cost pilot; licence handling for published transcripts.
- How "evidence still in the window" is read off a transcript, for the secondary per-question analysis.
- Arm 3 design (training cases by seed; exam content kept out of the agent's own graph).
- Judge blinding made mechanical: answers can carry arm tells (ENGRAM node ids, tool names, a notes-file
  path), so they are stripped or normalised before judging, and the rule is stated here.
- No interim scores: nothing is judged until every scored run is complete.
- Pairing when one arm's run of a conversation is flagged: whether the conversation leaves the paired
  analysis for both arms, stated before any run.
- Which run of a repeated cell counts (the variance repeats in section 13 and any permitted re-run).
- A student's non-use of ENGRAM in a scored run is never an exclusion; it is part of the result.
- Two more bounds for section 15: after a compaction the harness re-reads recently edited files, so
  arm 1's notes come back unasked (and arm 2's, if it keeps any); and the brief coaches both arms to
  watch for changes of mind and contradictions, which BEAM scores directly.

## Deviations log

(empty until registration)
