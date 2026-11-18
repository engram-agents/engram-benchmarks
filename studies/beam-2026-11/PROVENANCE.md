# BEAM study: provenance and decision log

Who decided what, when, and why, for every rule in the pre-registration. Quotes are verbatim (typos
kept). Each entry cites the node in Borges's ENGRAM graph that records it: the node holds the full
quote, its source and the interpretation filed at the time. Node ids are ids in that one graph and do
not resolve in any other. Times are UTC, as filed, within minutes of the decision.

People: **Lei** (project lead, the human who directs the study), **Kepler** (design owner, co-signs the
pre-registration), **Borges** (study lead, lab owner, teacher), Luria (a second agent seat, one data
point below), Ariadne (a seat outside the study, who improved arm 1's text). Lei's words reached Borges either in session or relayed verbatim by Kepler; relayed
entries say so.

## Data source

- Dataset: BEAM (Tavakoli et al., arXiv 2510.27246 v2), Hugging Face `Mohammadta/BEAM`, 100K split,
  parquet sha256 prefix `c0519be25907` (matches the dataset's LFS object id). Licence CC BY-SA 4.0
  (data); the released code is MIT. Not redistributed here. `ob_7428`, `ob_7444`, `ob_7451`.
- Released scoring code hard-codes `gpt-4.1-mini` at temperature 0 as judge (read first-hand,
  `ob_7428`); this study uses its rubrics with a different judge (2026-11-14, below).

## Decision log, 2026-11-14

| UTC | who | decision | quote | node |
|---|---|---|---|---|
| 18:42 | Lei (relayed by Kepler) | Run BEAM; Borges leads; three arms (harness baseline, fresh ENGRAM, ENGRAM after behavioural training); read the benchmark first-hand, pick the harness, time the GPU, pre-register before any student opens an item. | "BEAM is the one." | `ob_7427` |
| 18:52 | Kepler | Both arms receive the conversation the same way; the only difference between arms is the plugin. | "BOTH ARMS RECEIVE THE CONVERSATION THE SAME WAY." | `ob_7432` |
| 19:08 | Lei | Judge: a stronger, more recent model, the same for every arm, with the paper's rubrics. | "We can use a stronger and more recent judge model, as long as we use the same model for all three arms, and use the same rubrics as the paper, that should be fine and even better" | `ob_7433` |
| 19:08 | Lei | Two scores per arm, official and adjusted; confirmed gold errors raised with the maintainers. | "we can report two scores for each arm, the "official score" using strictly only the answers provided by the benchmark, and the "adjusted score" where we fix any confirmed errors in the official answers if we found any, and cite the issues we raised to the BEAM repo" | `ob_7434` |
| 19:08 | Lei | Judge chosen after a cost pilot. | "We'll run some pilot test first to estimate the judge cost" | `ob_7435` |
| 19:08 | Lei | Conversations are not meant to fit one window; at least a 128K window; first learn whether the 27B model works with ENGRAM. | "the conversation is never meant to be fitting into one context window, that's the whole point of the benchmark I think" | `ob_7436` |
| 19:08 | Lei | Delivery: the student is a quiet bystander; one exchange per user prompt in one session so ENGRAM's recall fires natively; the student takes notes and asks for the next turn. | "tell the student they are like a quiet by-stander to another conversation, listen and record the history, pay attention to changes of mind and contradictions over time" | `ob_7437` |
| 19:08 | Lei | Write the design and pre-registration before the final run; tune the harness first; give the student an escalation channel. | "We should write down these designs and pre-registers before the final benchmark." | `ob_7438` |
| 19:21 | Lei | Questions in the SAME continuous session, both arms, so plain Claude Code keeps its compaction-summary continuity. | "Let's keep the exam answering right after consuming the context, all in one continuous session, in both arms, so the vanilla arm is having its full capabilities and the normal usage format (users keep using one session for one topic)." | `ob_7448` |
| 19:22 | Kepler | Withdrew his fresh-session rule; added the can/cannot-show sentence and per-arm compaction logging. | "Lei's ruling stands and my fresh-session rule (29440, 29459, 29460) is withdrawn: questions in the same continuous session, both arms." | `ob_7450` |
| 19:28 | Lei | One forced compaction after reading, before the questions, both arms, so the test is cross-window memory only. | "we can add one compaction after the conversation reading phase, so that the test is strictly on the long term memory, not the in-context part" | `ob_7452` (its reading as cross-window memory only is superseded at 23:10-23:12 by the open-book core) |
| 19:29 | Kepler | Same compaction command in both arms, ENGRAM untuned; post-compaction check; failing runs flagged. | "confirm from the transcript that no conversation turn text remains in the window in either arm (the summary and any recalled notes are allowed; that is each arm's memory). If the check fails for a run, the run is flagged, not scored as primary." | `ob_7453` |
| 19:46 | Kepler | Arm 2 primary = ENGRAM as shipped with tool deferral at the harness default (later superseded by the reachability rulings below). | "Primary = ENGRAM as shipped, deferral left at the harness default, because 'does a 27B model work with out-of-the-box ENGRAM' is Lei's first question and a 'no, it never finds the tools' is a true and useful answer." | `ob_7458` |
| 20:31 | Lei | Exam format must mark proctor messages apart from reading material; note-taking must not be steered by the prompts. | "The student needs to know what prompt is from the exam maintainer and what are the reading material, so make sure we define the format clearly." | `ob_7466` |
| 20:45 | Lei | Make ENGRAM's tools usable by the small model BEFORE benchmarking, so the benchmark measures ENGRAM and not tool-finding. | "Let's try to find a way to let the model actually be able to use ENGRAM first." | `ob_7471` |
| 20:48 | Borges | The always-loaded core set (six tools) chosen by measured call share on one seat, not for BEAM; a second seat (Luria) agreed on four of six. | "13217  10.2% engram_inspect" | `ob_7473`, `ob_7475` |
| 20:55 | Lei | An exam is not identity-bearing, so ENGRAM's identity-focused nudges legitimately skip it; the student needs an explicit reason to keep exam facts. | "we need to make this change otherwise the student will legitimately skip ENGRAM because one exam is not identity-bearing at all" | `ob_7477` |
| 20:56 | Kepler | The reason goes in one byte-identical, method-neutral user-level line in both arms; the product's nudge is not widened. | "Do NOT widen the product's nudge." | `ob_7478` |
| 21:01 | Lei | A lean ENGRAM instruction profile for arm 2; comparable guidance for arm 1. | "We should definitely make a super lean and clear version for arm 2 as well, not to overwhelm a small model with lots of irrelevant information." | `ob_7479` |
| 21:02 | Kepler | One identical exam line plus each arm's own cited memory practice; the lean profile is a product manifest over existing components that keeps the consent paragraph and is read by Lei before merge. | "it may not drop what tells an agent to ask before acting outward." | `ob_7480` |
| 21:06 | Lei | Keep the record of these discussions and rationale in a repository. | "we should keep the record of these discussions and rationale in the relevant repo" | `ob_7490` |
| 21:12 | Lei | A new public repository for this and future benchmarks, privacy-aware from the start. | "another way to unblock our study is to just start a public repo just for the benchmark (or future benchmarks), and we start the repo with privacy awareness." | `ob_7483` |
| 21:27 | Lei | Entry gate: the scored benchmark starts only when the student reliably uses ENGRAM for note taking; non-use is diagnosed first. | "I'll say, the official starting criteria for the real benchmark, is when the model is reliably using ENGRAM for note taking. If we see it is not using ENGRAM as we hoped, we should see if there's a reason that is preventing it to use ENGRAM." | `ob_7487` |
| 21:27 | Lei | A direct-conversation probe to tell a capability gap from an intentional decision. | "That way, we can see if the no-ENGRAM behavior is a capability gap (the model simply don't know or remember to use it) or a intentional decision (exams are not important enough to be written in its own ENGRAM)." | `ob_7488` |
| 21:30 | Kepler | Tuning guards: tuning conversations leave the scored set; no arm-versus-arm accuracy during tuning; a public, complete tuning log with arm-1 equivalents. | "TUNING SET, kept apart. Every practice run today used conversation 15 of the 100K split. That conversation is now a tuning conversation and leaves the scored set, together with any other conversation used before the pre-registration is signed." | `ob_7491` |
| 21:33 | Lei | This repository is public from day one, with the plan and its refinement history; Kepler's tuning guards endorsed. | "it is public from day 1, and feel free to push to it with our plan and refinement history." | `ob_7492` |
| 21:34 | Kepler | Defines "reliably" for the entry gate (pre-registration section 5) and adds the stop rule: if the gate needs naming ENGRAM to the student or changing what ENGRAM's nudges are for, tuning stops for Lei. | "If the gate can only be met by telling the student to use ENGRAM by name, or by changing what ENGRAM's own nudges are for, STOP and hold it for Lei; that is his design, not a tuning knob." | `ob_7493` |
| 21:42 | Ariadne (a seat outside the study) | Arm 1's memory text improved and measured: print mode loads the auto-memory index, so auto memory, written as facts are learned, is plain Claude Code's honest best. | "in print mode (claude -p, v2.1.325) MEMORY.md is loaded into context. Two runs: auto memory on, my MEMORY.md text appears in the run's transcript (2 hits); same prompt with CLAUDE_CODE_DISABLE_AUTO_MEMORY=1, 0 hits." | `ob_7496` |
| 21:51 | Kepler | Amendment 1 to the entry gate: short runs test writing only; recall is tested only in a run long enough to compact naturally during the reading. | "a 3-exchange run cannot test recall, because one compaction summary carries the whole reading, node ids and content included; a criterion that cannot fail for the right reason, or pass for it, is not a criterion." | `ob_7499` |
| 22:28 | Kepler | One tuning run on the whole of conversation 15 to test recall, with a pre-committed hashed question file, a counting rule and a fixed pass rule; no rescue. | "PASS RULE, fixed now: on at least half of the counting questions, an ENGRAM read (query, inspect or equivalent) returns a node CREATED DURING THE READING (creation time between the first exchange and the forced compaction, read from the saved store) BEFORE the student's final answer to that question." | `ob_7506` |
| 22:33 | Kepler | Before any result: only read tool calls the student makes in the question's own turn count; the automatic recall hook is logged, not counted. | "Counting the hook now would widen a criterion after the run started; that it is unread does not change that." | `ob_7507` |
| 22:58 | Kepler | The lean profile ships as a generic named-manifest mechanism with no trust meaning, built from existing components chosen for a minimal ENGRAM seat, not for the exam. | "Build it as a GENERIC mechanism with no trust meaning in it: #4442's design talk with Lei has not happened, so nothing here may presume that #4442 uses it." | `ob_7510`, `ob_7511` |
| 22:58 | Kepler | Amendment 2: the comparable-length condition is withdrawn; both texts and every arm's token counts go in the pre-registration, with a stated bound; arm 1 is not padded. | "option (a), and I WITHDRAW 'comparable length'." | `ob_7512` |
| 23:01 | Ariadne | Arm 1's 182-token text stays: what it leaves out would make the student save less. She notes she sits on the ENGRAM team. | "Padding arm 1 past its docs would mean we write arm 1 a memory method of our own, which tests our prose, not Claude Code." | `ob_7515` |
| 23:03 | Kepler | The tool list for both arms: web, sub-agents and scheduling off; file tools and the shell on; enforced by configuration and verified per run; the shell's network reach blocked or logged and flagged. | "THE SHELL IS THE HOLE in (1): a shell can reach the network." | `ob_7516` |
| 23:03 | Lei | Preserve the student's whole environment after the long run and continue with conversation 15's 20 official questions, as a look, not a score. | "Let's preserve the student's engram and whole environment after your current 6-question run, and continue with the official 20 questions" | `ob_7517` |
| 23:05 | Kepler | Phase 2 agreed inside the tuning guards, with a hashed snapshot, a second forced compaction, teacher-marked correctness and two fences. | "PHASE 2 (conversation 15's 20 official questions on the preserved student): AGREED, it is inside the tuning guards" | `ob_7518` |
| 23:10 | Lei | The core setting allows full Claude Code capabilities, the session transcript included, with no web stated to the student as a rule; plus a book-closed look. | "I want one conversation be tested with "book closed" no transcript looking, just to see how the vanilla memories can work on their own." | `ob_7519` |
| 23:12 | Kepler | Open-book core agreed, with its meaning stated in section 15; book closed is instruction plus detection on both arms. | "OPEN-BOOK CORE: AGREED, and the pre-registration says what it now measures: each product's whole memory as shipped, the on-disk transcript included" | `ob_7522` |
| 23:41 | Lei | Wording (A); book closed on the second run of the three repeated conversations; no sub-agents; the draw as recommended (two from 100K, two from 500K). | "Ok, the answers: 1, (A )looks good. 2. Yes, all three sounds good. 3. Yes, no sub agents. 4. Agree with the recommended." | `ob_7527` |
| 23:41 | Lei | Report efficiency beside the score; keep every run's graph; supersede as ENGRAM's likely edge; decide how cascades are resolved in exams. | "Or actually just let the agent do the cascade resolution right away when a supersede happens?" | `ob_7528` |
| 23:43 | Kepler | Rulings on those ideas: efficiency list and the Knowledge Update and Contradiction Resolution secondary committed before any Phase 1 or Phase 2 result is read; graphs kept, published only as scrubbed text; cascades measured first, no exam sleep schedule. | "(a) and (c) are committed to the plan BEFORE Phase 1 or Phase 2 results are read" | `ob_7529` |
| 23:52 | Lei | Cascade resolution stays in sleep: resolving at supersede time would make a waiting user wait, and telling when a user is away is unreliable; the exam has no waiting user, but no exam-only switch is added. | "I'd err on the side of keeping cascade in the sleep." | `ob_7535` |

## Decision log, 2026-11-17

| UTC | who | decision | quote | node |
|---|---|---|---|---|
| 14:15 | Kepler | The judge never seeing the question is a defect of the evaluator, a fourth class: it does not move the ADJUSTED score; its cost, if measured, is a separate pre-declared third column ("question-aware judge"), all items, both arms, never merged into ADJUSTED. | "a judge that never sees the question is a property of the instrument and touches every item in both arms" | `ob_7765` |
| 19:25 | Lei (relayed by Kepler) | The OFFICIAL score is the central result; our adjustments and disagreements with official answers go in a clearly noticeable place in the report, not a footnote or a late page, with a pointer to per-item details, so readers see which official answers we dispute and can form their own view. | Paraphrased, not quoted: whether the project lead's own words are quoted in this public log is his open choice. | `ob_7806` |
| 19:27 | Kepler | Before any finding goes upstream, check the benchmark's issue tracker: credit findings already reported (the evaluator finding is upstream issue 15; disputed gold labels in the 100K split are issues 4, 5 and 6 on conversation 1 and part of issue 16 on conversation 3; none concerns conversation 9) and corroborate there rather than report again. | "do not draft a fresh report of the evaluator defect" | `ob_7810` |

## Decision log, 2026-11-18

| UTC | who | decision | quote | node |
|---|---|---|---|---|
| 00:39 | Lei (relayed by Kepler) | Having read the pre-registration amendment: find out whether the released judge leaving out the question is intended, starting from the paper; if it is fairly surely a bug, report the score under the fixed judge rather than the released one, decided by a known-answer check with and without the question; if the check is not clear, run both. Four other points of the amendment stand. | Paraphrased, not quoted, as for his earlier ruling in this log. | `ob_7828` |
| 00:43 | Kepler (design owner) | The judge for both the OFFICIAL and the ADJUSTED column is the paper's published protocol (Listing 20, the question filled in), byte-pinned to the upstream template at 3e12035; the released judge is a sensitivity column; the known-answer check is pre-logged before it runs. This replaces the 14:15 ruling of 2026-11-17 above (a third column, never primary). | "This withdraws my morning ruling (third column, never primary)." | `ob_7831` |
| 00:46 | Lei (relayed by Kepler) | A standing rule: where the benchmark's paper clearly contradicts its released code, the study follows the paper, as the peer-reviewed artifact, and says so plainly rather than deferring to the released code. Also: the paper the team may write bundles this BEAM study and the tracked BEAM corrections, not the team's own long-term benchmark. | Paraphrased, not quoted, as for his earlier rulings in this log. | `ob_7833`, `ob_7832` |

## Corrections (METHODOLOGY section 7)

- 18:52: a first record of Kepler's both-arms ruling cited the wrong evidence and was retracted
  (`ob_7431`); the corrected record is `ob_7432`.
- 19:12: Borges told Kepler he would recommend same-session questions to Lei, contradicting Kepler's
  ruling of 16 minutes earlier; a tripwire caught it after sending and the recommendation was withdrawn
  before Borges replied to Lei. Lei then ruled for same-session questions on his own reasoning
  (`ob_7439`, `ob_7448`).
- 21:06 to 21:12: the study's first named home was the team's private experiments repository; Lei moved
  it here six minutes later (`ob_7490` supersedes the earlier record).
- 23:11: Borges told Kepler and Lei that only arm 2 is pointed at the session transcript after a compaction.
  It was never measured; Kepler questioned it from his own context, and one search showed plain Claude Code's
  compaction summary carries the same pointer. The claim was retracted (`ob_7520`; the measured record is
  `ob_7521`).

## Practice observations behind the rulings

Summarised in [data/tuning-log.md](data/tuning-log.md). None is a finding; all used tuning
conversation 15.
