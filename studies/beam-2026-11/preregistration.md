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

  It is method-neutral: each arm has a long-term memory, and the line names none of them. What the
  study then measures is each setup *when the user has said this material matters*.
- **What the student may use**, told to the student in the same line, identical in both arms (Lei,
  2026-11-14, wording (A)):
  > You may use any tool and any file on this machine, including the records your own tools keep. You
  > may not use the web.

  In the book-closed runs (section 13) this sentence also excludes the student's own session transcript;
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
  every practice run so far, is a tuning conversation and is not scored. More tuning material is
  drawn by a recorded seed, never chosen by how it looks.
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
  flagged. The shell can reach the network: either the sandbox allows no outbound traffic except the
  model endpoint, or every shell command is logged and any other network call flags the run (OPEN:
  which one is implemented).

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
17 conversations, ids 1 to 13 and 17 to 20. Never scored: conversation 15 (tuning, every practice run
before the draw) and conversations 14 and 16 (drawn for entry-gate runs and lean-profile tuning). From the
500K split (parquet sha256 prefix `af05921c9793`), conversation 8 (arm-3 training) and conversation 1
(length-stress tuning). All four were drawn on 2026-11-14 by seed `75f72db7`, the first 8 hex digits of
the commit that published the draw rule and script; see [data/draw-rule.md](data/draw-rule.md) and
[data/draw-result.json](data/draw-result.json).

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
preserved messages; which ENGRAM hooks fired at it; the post-compaction check; every escalation.

Efficiency, per question and per conversation, the same instruments in both arms, from the harness log
and the transcript: wall seconds; input and output tokens with the cache fields (on a local model most
input tokens are the window re-read); GPU seconds, only if their method of measurement is stated here
first (OPEN); tool calls by kind (ENGRAM read, ENGRAM write, file read, file write, transcript read,
shell); compactions. Claude Code's OpenTelemetry export is not used unless a tuning run first shows, by a
diff of both arms' first prompts, that switching it on changes nothing the student sees.

Per answer: whether the student opened its own session transcript (tool calls naming its path; this
detector misses a path-free search such as listing every transcript file).

Kept from every run, tuning and training included: the ENGRAM store, the transcript and the work files,
with a sha256 file list taken before anyone opens them. They are published only as a scripted, scrubbed
text export, after the repository's rule against publishing graphs is amended for a study subject's
sandbox graph and the licence item is closed; the originals stay private, with their hashes published.

## 13. Variance

Claude Code cannot pass a sampling seed to the server, so each (conversation, arm) cell is one sample.
Three scored conversations, drawn by a published seed before the first scored run, run a second time
per arm with the BOOK CLOSED (Lei, 2026-11-14): the student is told not to open its own session
transcript. Closed means the student's own tool calls (read, search, shell) do not open the transcript
file or a copy of it; what ENGRAM's server does inside its own tools is arm 2's memory and is allowed, and
arm 1's own notes are allowed. A run in which the student opens its transcript is flagged and reported
as it stands. These are three paired looks at each arm's memory without the transcript, never a result.
Consequence, a stated bound: run-to-run noise within a cell is not measured.

## 14. Exclusions and re-runs

A run is excluded from the primary only for a FLAGGED harness fault: the post-compaction check fails;
the student process dies; a timeout; the ENGRAM first session does not complete (arm 2). Each flagged
run may be re-run once, with the reason logged before the re-run; a second failure stays excluded. A
wrong or empty answer is never a harness fault.

## 15. What this design can and cannot show

It measures each product's whole memory as shipped, the on-disk session transcript included, in
one-topic, one-session use when the user has said the material matters (Lei's open-book core,
2026-11-14; this supersedes reading the forced compaction as "cross-window memory only"). After the
forced compaction neither arm holds the reading in its window, so answers come from what each product
keeps outside it: the compaction summary, note files and the transcript, or ENGRAM and the transcript.
The score therefore includes how diligently the student searches. The expected gap between arms is
smaller than with the record taken away, and a null means ENGRAM adds nothing over transcript search on
this task, which is a publishable answer. The book-closed looks (section 13) are the only view without
the transcript. It cannot
separate ENGRAM's storage from the model's choice or ability to reach it; it runs Claude Code in print
mode, where ENGRAM's PostCompact hook left no visible trace in practice, unlike interactive use; it does
not measure memory across days or sessions; and with one sample per cell and 17 scored conversations it
detects only moderate effects.

## 16. Budget (estimates from practice, never measured at scale)

About 143 exchanges per conversation. Arm 1 at about 5 to 25 s per exchange: roughly 40 min per
conversation. Arm 2 at about 45 to 98 s per exchange: roughly 2 to 4 h per conversation, plus about
7 to 16 min of first-session setup. The variance repeats add about 15%.

## OPEN before registration

- The entry gate met (section 5).
- The exam line (with its book-closed variant) and both instruction texts frozen with their sha256
  (texts and counts in section 4; the lean profile ships once engram#4802 merges).
- The brief's final text frozen (a purpose sentence is under test, see the tuning log).
- Network for the shell: blocked, or logged and flagged (section 7). GPU-seconds method (section 12).
- The three book-closed conversations drawn by a published seed (section 13).
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
- The per-turn timeout value, fixed before the first scored run.

## Deviations log

(empty until registration)
