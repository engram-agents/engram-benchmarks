# Score review principles

*Version 0.1, 2026-11-17. **Two parameters are still open** (see "Open questions"; each names who closes it).
Version-controlled like `METHODOLOGY.md`: amend by PR, give the reasoning in the PR body AND in the change log
at the end of this file, never edit history. These principles govern how we review an agent's answers against
a benchmark's official answer key, and how a corrected score is reported beside the official one.*

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
- **The external exam expert** checks the quality of the exam itself, using the information in the answers
  rather than sitting the exam from scratch.
- **The district official** does the final check on every item the expert reviewed, so that the recommended
  correction to the scoring standard is as right as it can be made.

## 1. Two columns, always side by side

Every result reports the **official** score (the benchmark's number: graded by the benchmark's method against
its own key, unchanged) and the **adjusted** score (our corrected reading) for every arm. The adjusted score is
never shown alone. The text says who graded each column.

## 2. What is reviewed

- Every answer below full score on the official key.
- **Plus a random sample of full-score answers**, so corrections can go in both directions, not only in the
  agent's favour. The seed and sample size are fixed in the study's pre-registration (or, for a pilot, in the
  study's log) before anyone looks.
- **Once an item's key is corrected (section 6), every arm's answer to that item is re-scored** against the
  rewritten rubric, whatever its official grade. A correction to the key applies to everyone who answered it.

## 3. Phase 1: the teacher

The study lead reviews each item in section 2, presuming neither the official answer nor the agent's answer
correct. Both answers, and the messages each cites, are used as pointers into the source material; the
reviewer answers the question from the source and judges which answer is more correct. If both are incomplete,
the reviewer writes the fuller correct answer. The ruling is one of the outcomes in section 6, written down and
sealed (section 5a) before phase 2 starts on that item.

*Known limit:* the teacher has seen the rubric, the question's category and which answer is the agent's.
Phase 1 is the least blind phase. Phases 2 and 3 exist to check it.

## 4. Phase 2: the external exam expert

**Coverage (open, see Open questions):** every item where the phase-1 ruling changes the official grade, plus a
random sample of the other reviewed items, seed and size fixed as in section 2. An item phase 2 does not review
keeps its official grade in both columns, and is listed as "phase 1 only, unchanged".

**Who:** a second reviewer from the team who, for that item, has not seen the official grade, the agent's grade,
the phase-1 ruling, or a framing of the item by the official key (for example an earlier read that showed them
the key first). Each reviewer's exposure is kept in a per-reviewer item log in the study's `data/` directory.

**The packet** contains exactly what the agent was given, plus the two answers:

- **Given:** the question text; the full source material; the two answers, labelled A and B in a random order,
  each with the messages it cites, listed in the same form. An answer that cites no messages is listed with
  "(no messages cited)".
- **Not given:** the rubric or key-point list; the question's category; any metadata field that frames the item
  (for example "tests for", "why unanswerable", contradiction type, difficulty); which answer is the agent's;
  the teacher's ruling.

The answers keep their own wording. Rewriting them into a neutral form would carry the rewriter's reading
into the text.

The reviewer writes the fuller correct answer if both are incomplete, and rules with one of the outcomes in
section 6. After ruling, the reviewer records which answer they believe is the agent's.

*Known limit, measured rather than assumed:* the reviewer may still guess which answer is the agent's from
style or citation habits. The guess rate is reported beside the results. In v0.1 it has no automatic
consequence; a high rate is stated as a limit of the phase-2 check.

## 5. Phase 3: the district official

The project lead rules on every item phase 2 reviewed. The project lead does not re-read the source material;
the reviewers bring the facts:

- **One fact list per item**, built by both reviewers: each load-bearing fact with a verbatim quote and the
  message it comes from. Each reviewer also lists the facts that cut **against** their own ruling. The two
  lists are merged mechanically: no fact is dropped by either reviewer.

If the three rulings agree, the item's outcome is settled. If they disagree, the three discuss it once, with
the fact list in front of them. If they still disagree after that, the outcome is **Ambiguous** (section 6) and
every ruling is published.

If the project lead is unavailable, the item **waits**: its adjusted entry reads "pending". A two-reviewer
verdict is never promoted to settled.

*Known limit:* phase 3 is decisive and is not blind. The project lead knows which answer is the agent's and
belongs to the team under test. Phases 1 and 2 are on the record before phase 3 rules, so a phase-3 ruling
against both of them is visible in the log.

### 5a. Mechanics (blinding by construction, METHODOLOGY section 5)

- The study lead builds the phase-2 packets with a script. The script draws the A/B order from a logged seed
  and writes the A/B key to a separate file whose hash is published before the phase-2 read. The key is opened
  only after phase 3 rules on that item.
- Each phase's ruling is committed with a hash before the next phase sees anything of it. Phase 2 never sees
  the phase-1 ruling. Phase 3 sees both, with the merged fact list.
- The fact lists are merged by script (concatenate, keep every fact, mark which reviewer contributed it), never
  by hand.

## 6. Outcomes and how each one scores

Each reviewed item ends in one of:

- **Key stands:** the official answer is right and the agent's answer was graded right against it. The grade
  is unchanged in both columns.
- **Key wrong or incomplete:** the settled answer differs from the key. The rubric is rewritten (below) and the
  answers are scored against it for the adjusted column only.
- **Grading error:** the key is right but the agent's answer was graded wrongly against it. The official column
  keeps the benchmark's own grade; the adjusted column takes the corrected grade. Logged under its own heading.
- **Ambiguous:** the source supports more than one reading, or the reviewers still disagree after the phase-3
  discussion. The item keeps its official grade in both columns, and all readings are published. Ambiguous is a
  legitimate outcome, not a failure to decide.

**Rewriting a rubric** (for "key wrong or incomplete"): the study lead writes the new rubric lines from the
settled answer, in the benchmark's own rubric form, one line per load-bearing point of the settled answer.
The second reviewer checks that the lines say what the settled answer says and nothing more, without the
agent's answers in front of them. The rewritten rubric is committed before any answer is re-scored. Re-scoring
uses the same grading method that produced the official column (the same judge model and judge prompt; for
hand-graded columns, the same grader), applied to every arm's answer to that item.

Two classes never move any single item's grade:

- **Our own harness defect** (for example, how we worded the prompt around a question): fix the harness,
  re-ask, and report the result as a rerun, whichever way it moves the score.
- **Official evaluator defect** (a flaw in the benchmark's scoring code, whatever its reach): its effect may be
  measured only by a separate re-scoring of every item it can affect, in every arm, declared in advance,
  reported as its own column, and reported whichever arm it favours.

## 7. What is published

- A per-item change log: item, official answer, our finding, the messages that prove it, each phase's ruling,
  each phase-2 reviewer's guess about which answer was the agent's, and the outcome.
- An open invitation to dispute any item, at the head of the log. A dispute that succeeds after publication is
  handled as a correction under METHODOLOGY section 7: a dated correction block on the artifact.
- Every correction applied to all arms identically (section 2). In a scored study the reviewers see answers
  without arm labels, and the adjusted set is frozen before arm labels are unblinded. On tuning data with a
  single arm, every reviewed item is flagged as reviewed with the agent's answer in view.
- This sentence, or its equivalent, wherever an adjusted score appears: **all reviewers belong to the team
  that builds the agent under test. These principles reduce our bias; they do not make the adjusted score
  independent.** That is why the per-item log and the dispute invitation matter most.

## 8. Upstream

A finding about the benchmark's key or its evaluator is reported to the benchmark's maintainers only after it
is settled under these principles, stating what was and was not checked, written as users who want the
benchmark to be right, with no claim about anyone's results.

## 9. Adoption by a study

A study adopts a version of these principles by a dated amendment to its pre-registration (METHODOLOGY
section 1), made before any scored answer exists. The amendment states the version adopted, the full-score
sample's seed and size, and the phase-2 sample's seed and size. Where the study's pre-registration already
defines official and adjusted scores, the amendment says how these principles refine that definition. A first
use of a version on unscored tuning data is logged as a pilot of the procedure.

## Open questions

Each stays open in this version until the named party closes it; closing one is a new version.

- **Phase-2 coverage. Closes it: the project lead.** Section 4 states the v0.1 rule. The project lead framed
  phase 2 as "the most disputed questions and some random questions"; whether that is the same rule is for the
  project lead to confirm.
- **The project lead's load in phase 3. Closes it: the first pilot.** Phase 3 puts every phase-2 item in front
  of one person. The first pilot measures the item count and the minutes per item; a scored study does not
  adopt these principles until that figure is in the change log.

## Change log

- **v0.1, 2026-11-17.** First version. *Why:* during the BEAM study's tuning, our corrections to the official
  key were first checked by a second read that was blind to our verdict and to the agent's answer, but showed
  the reviewer the official answer first, framed the way the key frames it. The project lead judged that this
  anchored the read on the key, and that one item it confirmed as a contradiction admits a reading in which
  the two statements describe different times. The project lead proposed the three phases and their roles. The
  study lead added: the full-score sample, the unlabelled answers, the shared fact list with verbatim quotes,
  and keeping the change log and dispute invitation. The project lead added: no rubric or category in the
  phase-2 packet. The BEAM study's design owner added: adoption through the pre-registration, the "pending"
  rule, measuring the phase-2 guess, facts against one's own ruling, the published independence sentence,
  "ambiguous" as an outcome, and naming who closes each open question. A first review of this file supplied:
  one stated coverage rule, the rubric-rewrite rule, re-scoring every arm's answer to a corrected item, the
  mechanics of section 5a, and the fit with a pre-registration that already defines both scores. Decided by
  the project lead.
