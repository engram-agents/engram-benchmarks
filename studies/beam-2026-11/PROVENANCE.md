# BEAM study: provenance and decision log

Who decided what, when, and why, for every rule in the pre-registration. Quotes are verbatim (typos
kept). Each entry cites the node in Borges's ENGRAM graph that records it: the node holds the full
quote, its source and the interpretation filed at the time. Node ids are ids in that one graph and do
not resolve in any other. Times are UTC, as filed, within minutes of the decision.

People: **Lei** (project lead, the human who directs the study), **Kepler** (design owner, co-signs the
pre-registration), **Borges** (study lead, lab owner, teacher), Luria (a second agent seat, one data
point below). Lei's words reached Borges either in session or relayed verbatim by Kepler; relayed
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
| 19:28 | Lei | One forced compaction after reading, before the questions, both arms, so the test is cross-window memory only. | "we can add one compaction after the conversation reading phase, so that the test is strictly on the long term memory, not the in-context part" | `ob_7452` |
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

## Corrections (METHODOLOGY section 7)

- 18:52: a first record of Kepler's both-arms ruling cited the wrong evidence and was retracted
  (`ob_7431`); the corrected record is `ob_7432`.
- 19:12: Borges told Kepler he would recommend same-session questions to Lei, contradicting Kepler's
  ruling of 16 minutes earlier; a tripwire caught it after sending and the recommendation was withdrawn
  before Borges replied to Lei. Lei then ruled for same-session questions on his own reasoning
  (`ob_7439`, `ob_7448`).
- 21:06 to 21:12: the study's first named home was the private engram-experiments repository; Lei moved
  it here six minutes later (`ob_7490` supersedes the earlier record).

## Practice observations behind the rulings

Summarised in [data/tuning-log.md](data/tuning-log.md). None is a finding; all used tuning
conversation 15.
