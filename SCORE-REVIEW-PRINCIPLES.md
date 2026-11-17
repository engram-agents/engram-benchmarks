# Score review principles

*Version 0.1, 2026-11-17. Version-controlled like `METHODOLOGY.md`: amend by PR, give the reasoning in the
PR body AND in the change log at the end of this file, never edit history. These principles govern how we
review an agent's answers against a benchmark's official answer key, and how a corrected score is
reported beside the official one.*

## Why this exists

A benchmark's answer key can be wrong, ambiguous, or incomplete. Its grader can be wrong too. Reporting only
the official score then blames the agent for the key's errors, and tuning the agent toward that score teaches
it to bend correct behaviour to fit a flawed rubric. But the team that builds the agent has a stake in the
agent looking good, so a score the team corrects by itself is not credible on its own. These principles are
how we correct scores without trusting ourselves more than we should.

The roles, as the project lead framed them:

- **The teacher** reviews their own student's exam against the official guide. The teacher knows
  everything about the student and the guide, and stays impartial because the purpose is not this one score:
  it is to find exactly where each problem lies, so the student does better next time. If the guide is wrong,
  the student is not blamed. If the student is wrong, the student is not excused.
- **The external exam expert** checks the quality of the exam itself on the disputed items and a random
  sample, using the information in the answers rather than sitting the exam from scratch.
- **The district official** does the final check on every reviewed item, so that the recommended correction
  to the scoring standard is as right as it can be made.

## 1. Two columns, always side by side

Every result reports the **official** score (the benchmark's number, graded against its own key, unchanged)
and the **adjusted** score (our corrected reading) for every arm. The adjusted score is never shown alone.
The text says who graded each column.

## 2. What is reviewed

- Every answer below full score on the official key.
- **Plus a random sample of full-score answers**, with the seed and sample size logged before anyone looks.
  Reviewing only the agent's losses lets corrections go in one direction only; the sample lets them go both
  ways.

## 3. Phase 1: the teacher

The study lead rescores each item as objectively as possible, presuming neither the official answer nor the
agent's answer correct. Both answers, and the messages each cites, are used as pointers into the source
material; the reviewer answers the question from the source and judges which answer is more correct. If both
are incomplete, the reviewer writes the fuller correct answer.

*Known limit:* the teacher has seen the rubric, the question's category and which answer is the agent's.
Phase 1 is the least blind phase. Phases 2 and 3 exist to check it.

## 4. Phase 2: the external exam expert

A second reviewer from the team, with no stake in the agent being right on the item, does the same task in
the same way. The packet contains exactly what the agent was given, plus the two answers:

- **Given:** the question text; the full source material; the two answers, labelled A and B in a random order
  logged before the read, each with the messages it cites, listed in the same form.
- **Not given:** the rubric or key-point list; the question's category; any metadata field that frames the
  item (for example "tests for", "why unanswerable", contradiction type, difficulty); which answer is the
  agent's; the teacher's ruling.

The answers keep their own wording. Rewriting them into a neutral form would carry the rewriter's reading
into the text.

*Known limit, measured rather than assumed:* the reviewer may still guess which answer is the agent's from
style or citation habits. After ruling, the reviewer records which answer they believe is the agent's, so the
leak is measured.

*Who:* a reviewer who has already seen an item framed by the official key (for example through an earlier
read of it) does not take phase 2 for that item.

## 5. Phase 3: the district official

The project lead rules. Both earlier rulings are sealed until then. The project lead does not re-read the
source material; the reviewers bring the facts:

- **One fact list per item**, built by both reviewers: each load-bearing fact with a verbatim quote and the
  message it comes from. Each reviewer also lists the facts that cut **against** their own ruling. The two
  lists are merged mechanically: no fact is dropped by either reviewer.

If the three rulings agree, the item's outcome is settled. If they disagree, the reviewers and the project
lead discuss it and resolve it, or the dispute is published as data.

If the project lead is unavailable, the item **waits**: its adjusted entry reads "pending". A two-reviewer
verdict is never promoted to settled.

## 6. Outcomes

Each reviewed item ends in one of:

- **Key stands:** the official answer is right; the agent's grade is unchanged in both columns.
- **Key wrong or incomplete:** the settled answer differs from the key. The agent's answer is scored again
  against a rubric rewritten to the settled answer, for the adjusted column only. The rewritten rubric goes
  in the per-item log.
- **Grading error:** the key is right but the agent's answer was graded wrongly against it. Logged under its
  own heading.
- **Ambiguous:** careful reviewers disagree, or the source supports more than one reading. The item stays at
  its official grade in both columns, and both readings are published. Ambiguous is a legitimate outcome,
  not a failure to decide.

Two classes stay out of the adjusted column altogether:

- **Our own harness defect** (for example, how we worded the prompt around a question): fix the harness,
  re-ask, and report the result as a rerun, never as an adjustment.
- **Official evaluator defect** (a flaw in the benchmark's scoring code that affects every item in every
  arm): it does not move any single item's grade. Its effect may be measured only by a separate re-scoring
  of all items in all arms, declared in advance, reported as its own column, and reported whichever arm it
  favours.

## 7. What is published

- A per-item change log: item, official answer, our finding, the messages that prove it, each phase's ruling,
  each phase-2 reviewer's guess about which answer was the agent's, and the outcome.
- An open invitation to dispute any item, at the head of the log.
- Every correction applied to all arms identically. Where possible, the correction is decided before the
  answers of the arm under test are looked at for that item; items where that was not possible are flagged.
- This sentence, or its equivalent, wherever an adjusted score appears: **all reviewers belong to the team
  that builds the agent under test. These principles reduce our bias; they do not make the adjusted score
  independent.** That is why the per-item log and the dispute invitation matter most.

## 8. Upstream

A finding about the benchmark's key or its evaluator is reported to the benchmark's maintainers only after it
is settled under these principles, stating what was and was not checked, written as users who want the
benchmark to be right, with no claim about anyone's results.

## 9. Before a scored study

These principles, the full-score sample's seed and size, and the rule for rewriting a rubric go into the
study's pre-registration before any scored answer exists. A first use of a new version on unscored tuning data
is logged as a pilot of the procedure.

## Open questions

- **Phase-2 coverage** (v0.1 states it as: every item where phase 1 changes the official grade, plus a seeded
  random sample of the rest). The project lead framed phase 2 as "the most disputed questions and some random
  questions"; whether that is the same rule awaits the project lead's confirmation.
- **The project lead's load.** Phase 3 puts every reviewed item in front of one person. The first pilot
  measures the item count and minutes per item before a scored study commits to the rule.

## Change log

- **v0.1, 2026-11-17.** First version. *Why:* during the BEAM study's tuning, our corrections to the official
  key were first checked by a "blind" second read, blind to our verdict and to the agent's answer. But the
  read showed the reviewer the official answer first, framed the way the key frames it, before the reviewer
  read the source. The project lead found that this anchored the read on the key: one item the second reader
  confirmed as a contradiction admits a plain reading in which the two statements describe different times.
  The project lead proposed the three phases and their roles. The study lead added: the full-score sample, the
  unlabelled answers, the shared fact list with verbatim quotes, and keeping the change log and dispute
  invitation. The project lead added: no rubric or category in the phase-2 packet. The BEAM study's design owner
  added: the pre-registration rule, the "pending" rule, measuring the phase-2 guess, facts against one's own
  ruling, the published independence sentence, and "ambiguous" as an outcome. Decided by the project lead.
