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
  than arm 1's (scored by the published judge of section 10).
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
- Paper over code (the project lead's rule): where the benchmark's peer-reviewed paper (published at ICLR 2026,
  per the paper's own header) and its released code
  clearly contradict each other (the paper states something at a location we can cite, and the code does
  otherwise), this study follows the paper. Where the paper is silent or ambiguous, or two places in the paper
  disagree, the released code stands, and a case of the last kind is listed as unresolved. Every application of
  this rule is listed here with its paper location and its code location, and is declared before the first
  scored run, never chosen after a result is seen. Applications so far: one, the judge prompt (next bullet).
  Partial credit is not one: the paper scores each rubric item 0, 0.5 or 1, and the current code parses the
  judge's score as a number (at b2da22e every score conversion of the earlier code, `int()`, upstream issue 8,
  became `float()`), so the paper and the current code agree.
- Judge prompt, used by both the OFFICIAL and the ADJUSTED column: the benchmark's PUBLISHED judge protocol, the
  paper's Listing 20 ("Rubric scoring for nugget satisfaction prompt", arXiv 2510.27246v2, Appendix H), whose
  inputs are the question, the rubric item and the response, with a responsiveness rule anchored to the question.
  The exact bytes are the upstream template `unified_llm_judge_base_prompt` at BEAM commit
  3e12035532eb85768f1a7cd779832b650c4b2ef9 (template sha256
  d349c9a8559bed9c14bfe2e624212225b09218ff864258a739229c15f4c8e869), with `<question>` filled by the item's
  question. Compared with Listing 20 word by word after normalising whitespace, every difference between the two
  is typographic (curly against straight quotes, line-wrap hyphens in the PDF) and none is in wording: they are
  one text. (How many differences one counts depends on the diff unit, so no count is given; the comparison is
  repeatable from the two sources.) "Official" in this study therefore means the benchmark's gold answers scored
  under the benchmark's published judge protocol.
- Why not the released code: no judge call in the released evaluation code (the ten of the eleven `evaluate_*`
  functions in `src/evaluation/compute_metrics.py` that format `unified_llm_judge_base_prompt` from
  `src/prompts.py`) fills
  the question in. At
  3e12035 the template asks for it, so the judge saw the literal string `<question>`; at
  b2da22eac88bb0874c64665f13457eb99835774a (the current main) the question line is removed, while the
  instruction to score 0.0 when the response does not address the question remains (reported upstream as
  issue 15). The paper gives no reason for a judge without the question. The one passage that could bear on it
  (nuggets are "atomic, self-contained") describes how rubric items are written, not what the judge is shown, so
  it is not a second place in the paper that disagrees with Listing 20, which shows the question to the judge.
- Not known: which code produced the paper's results table. "Official" here does not mean that our scores
  reproduce the paper's numbers.
- Known-answer check (the project lead's test), committed and run before any scored item is judged: a small
  set of responses whose verdicts are fixed in advance, judged with and without the question by the study's
  own judge (same model, settings and parsing). Part A: constructed responses that satisfy a rubric item's
  words without addressing the question, whose right verdict (0.0 under the responsiveness rule) is fixed by
  construction. Part B: run A items whose verdicts the three-reader score review has settled; these are the
  team's own verdicts, not independent ones, and are labelled so. Expected direction, written now: showing the
  question changes verdicts mainly on off-topic and abstention responses and little on on-topic ones; a large
  shift on on-topic responses would itself be a finding, and is reported. The check's own pre-log fixes the set
  sizes and the decision rule before the first call. The judge with the question counts as CLEARLY BETTER only
  if it matches the fixed verdicts on more Part A items and on no fewer Part B items. Every other outcome (a tie
  on Part A, fewer Part A matches, or fewer Part B matches) counts as NOT CLEARLY BETTER; a tie is a legitimate
  result of the check, not a failed check. A REVERSAL (the judge with the question matching fewer fixed
  verdicts than the judge without it, on Part A or on Part B) is stated in the report's summary, beside the
  primary result, not only in the check's own log. The outcome decides only how far the released judge runs: if clearly
  better, the released judge runs as a sensitivity column on a stated population; if not clearly better, it runs
  in full, on every item of both columns, so OFFICIAL and ADJUSTED are each reported under both judges (the
  project lead's four scores).
- In every outcome, H1 and the primary analysis (section 11) are tested on the scores of the published judge
  above; "the OFFICIAL score" in this plan means that judge's OFFICIAL score. The released judge (the b2da22e
  template, no question) is always the sensitivity column: its population is stated before it runs (the full
  set when the check is not clearly better), its scores are reported beside the primary ones, and they are
  never folded into OFFICIAL or ADJUSTED or used to test H1. Issue 15's own
  figures (on one run of one system, supplying the question changed the verdict on 160 of 1,051 rubric items)
  are that reporter's measurement, cited as theirs and not as ours.
- OFFICIAL score: gold answers as shipped. ADJUSTED score: confirmed gold errors corrected. A gold answer is
  "confirmed wrong" only after a first-hand check against the conversation text. Before any finding goes upstream
  it is checked against the benchmark's issue tracker, open and closed issues: a finding already reported there
  is credited to its reporter, with the issue number, in the study's per-item change log (the one
  SCORE-REVIEW-PRINCIPLES.md requires) and, where we agree, corroborated with a short comment on that issue
  rather than reported again; only a finding not already reported is raised as a new issue. Every finding,
  whether credited, corroborated or new, is cited. The adjusted set is frozen before arm labels are unblinded.
- Absolute scores are not comparable with the paper's table (a different judge model, and the code that
  produced that table is not known). The comparison is between our arms.

## 11. Primary analysis

- Outcome: per-conversation overall score (mean of its 20 questions), OFFICIAL, under the published judge of
  section 10. The OFFICIAL score is the central result (Lei, 2026-11-17).
- Report layout (Lei, 2026-11-17, binding): our adjustments and our disagreements with official answers appear
  in a clearly noticeable place in the report, not a footnote or a late page, with a pointer to the per-item
  details, so a reader sees which official answers we dispute and can judge for themselves. A floor that can be
  checked afterwards (the design owner's reading, open to the project lead's tightening): the ADJUSTED contrast
  appears in the same table and the same summary paragraph as the OFFICIAL one, and that summary states how many
  official answers we dispute and links to the per-item change log.
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
and the transcript: wall seconds; input tokens labelled "whole prompt per call" (Ollama's Anthropic-compatible endpoint
returns its cache fields as 0 or empty, so the transcript cannot tell reused prefix from newly
processed tokens) and output tokens; newly evaluated prompt tokens, from one source used identically in
both arms (the server's log or a logging proxy), OPEN until a tuning run shows a reliable source, since
a hook that injects changing text early in the prompt would break prefix reuse in one arm only; GPU seconds, only if their method of measurement is stated here
first (OPEN); tool calls by kind (ENGRAM read, ENGRAM write, file read, file write, transcript read,
shell); compactions. Claude Code's OpenTelemetry export is not used unless a tuning run first shows, by a
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

A run is excluded from the primary only for a FLAGGED harness fault: the post-compaction check fails;
the student process dies; a timeout; the ENGRAM first session does not complete (arm 2); the session's
tool list differs from section 7's; a shell network call to anything but the model endpoint (section
7). Each flagged run may be re-run once, with the reason logged before the re-run; a second failure
stays excluded. A wrong or empty answer is never a harness fault. A book-closed run in which the
student opens its own transcript is NOT a harness fault: it is the student's behaviour, flagged in the
report and reported as it stands, never re-run (section 13).

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
- Network for the shell: blocked, or logged and flagged (section 7). GPU-seconds method (section 12).
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
- How three upstream scoring reports bear on our judge, stated before the first scored run: issue 15 (the
  judge prompt never receives the question; the treatment is set in section 10), issue 8 (an int() conversion
  that drops 0.5 partial credit; our judge parses scores as floats) and issue 19 (a report of systematic
  judging bias on 100K conversation 1).

## Deviations log

(empty until registration)
