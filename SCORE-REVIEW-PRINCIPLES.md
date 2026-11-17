# Score review principles

*Version 0.2, 2026-11-17. **One parameter is still open** (see "Open questions"; it names who closes it).
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
- **The external exam expert** checks the quality of the exam itself on the items that are in question and on
  a random set of controls, using the information in the answers rather than sitting the exam from scratch.
- **The district official** does the final check on every item that anyone questioned, so that the
  recommended correction to the scoring standard is as right as it can be made.

## 1. Two columns, always side by side

Every result reports the **official** score (the benchmark's number: graded by the benchmark's method against
its own key, unchanged) and the **adjusted** score (our corrected reading) for every arm. The adjusted score is
never shown alone. The text says who graded each column.

## 2. Who reviews what

An **item** is one question. In a study with several arms, an item carries one answer per arm.

| phase | reviews |
|---|---|
| 1, the teacher | **every item**, and every arm's answer to it |
| 2, the external exam expert | the union of: (a) every item where any arm's answer is below full official score; (b) every item where the phase-1 outcome is anything other than "Key stands"; (c) a fixed number of the remaining items, drawn with a seed |
| 3, the district official | every phase-2 item **except** the unquestioned controls: items where every arm's answer has full official score and both phase 1 and phase 2 map to "Key stands", and no step-2a record was superseded after the criterion was shown (section 4) |

The number drawn in (c) and its seed are fixed and logged **before any phase-1 outcome exists for that run**, so
the sample cannot follow the results: in the study's pre-registration for a scored study, in the study's log for
a pilot. A pilot on items phase 1 has already seen says so in its log. An item that phase 2 does not review keeps
its official grade in both columns.

Phase 2 receives the items in a random order, without being told which set each came from. Otherwise the
selection itself tells the reviewer which items someone doubted.

## 3. Phase 1: the teacher

The study lead reviews every item, presuming neither the official answer nor any agent's answer correct. The
answers, and the messages each cites, are used as pointers into the source material; the reviewer answers the
question from the source and writes the answer-level judgement of section 6, including a fuller correct
answer when the official answer is not fully correct. Phase 1 is not lettered: its packet marks which answer is
the official one, so its outcome is mapped directly and can decide phase-2 selection (section 2, set b). In a
scored study the teacher sees the agents' answers without arm labels, each under an **arm-blind answer id**
(an id that carries no meaning, section 5a) that stays the same for that item through phase 3 (the study's pre-registration freezes
the adjusted set before arm labels are unblinded).

*Known limit:* the teacher has seen the rubric, the question's category, and, on single-arm data, which answer
is the agent's. Phase 1 is the least blind phase. Phases 2 and 3 exist to check it.

## 4. Phase 2: the external exam expert

**Who:** a second reviewer from the team who, for that item, has not seen the official grade, any agent's grade,
the phase-1 judgement, or a framing of the item by the official key (for example an earlier read that showed
them the key first). Each reviewer's exposure is kept in a per-reviewer item log in the study's `data/`
directory.

**The packet**, one per item, contains exactly what the agent was given, plus the answers:

- **Given:** the question text; the full source material; the official answer and every arm's answer, labelled
  with letters in a random order. Cited messages are listed only when every answer in the item comes with a
  citation list (possibly empty) from the same kind of source; then each answer's list is shown in the same form,
  and an empty one reads "(no messages cited)". Otherwise no answer's cited messages are listed, since a citation
  line under only one answer, or an empty line only under one, would mark it. This settles the case where an
  answer's citations are absent by construction, not merely unknown: an agent answer imported without its
  citations, or an official answer whose key records no reference (in BEAM's 100K tier, none of the 40
  abstention items has a reference field, while every item of the other nine categories has one). A study names,
  per benchmark, where the official answer's citations come from.
- **Not given:** the rubric or key-point list; the question's category; any metadata field that frames the item
  (for example "tests for", "why unanswerable", contradiction type, difficulty); which answer is the official
  one and which are the agents'; any grade; the teacher's judgement.

The answers keep their own wording. Rewriting them into a neutral form would carry the rewriter's reading
into the text.

The reviewer writes the answer-level judgement of section 6. After that, the reviewer records which answer
they believe is the official one and, in a study with several arms, which arm they believe each agent answer
came from.

*Known limit, measured rather than assumed:* the reviewer may still guess which answer is which from style or
citation habits; an agent answer can also reveal its arm by how it cites its memory. The guess rate is reported beside the results. It has no automatic consequence; a
high rate is stated as a limit of the phase-2 check.

**Items whose reference is a criterion, not an answer** (for example a benchmark's instruction-following and
preference-following questions, whose key says what a compliant response must do rather than giving one). Showing
the criterion first would anchor the reviewer on the key's framing, so phase 2 runs in two steps, enforced by the
tooling:

- **Step 2a.** The packet holds the question, the source material and the agent answers under letters, and no
  criterion. The reviewer judges each agent answer and writes what a complying answer must do, with the message
  that sets the instruction or preference. This judgement is committed with its hash.
- **Step 2b.** Only after the step-2a judgement is committed does a separate export, run by the study lead, show
  the reviewer the criterion (an exception to "Not given" above, for this step only, recorded in the reviewer's
  per-item exposure log). The export is itself a record with its time, written and hashed in the same record file
  as the judgements, before the criterion reaches the reviewer, so whether a step-2a record came before or after
  it is read off the file's own order, not judged. The reviewer judges the criterion
  itself (correct, partly correct or wrong: does the source support it, and does it ask for the right thing) and,
  when it is not correct, writes the fuller criterion. Whether the item as a whole is ambiguous is judged in step
  2a, before the criterion is seen. A step-2b judgement cannot change step 2a; a change of mind is a superseding
  step-2a record with its reason. A step-2a record superseded after the criterion was shown is exactly the
  anchored read this procedure exists to avoid, so such an item always goes to phase 3, which sees both records;
  the original step-2a record is the one mapped to an outcome, and the later one is published beside it as a
  post-reveal revision, with its reason, for phase 3 to weigh. The split is by time, read off the order of the
  records: a step-2a record superseded before the step-2b export exists for that item is an ordinary correction,
  the latest record is mapped, and the item is not sent to phase 3 for that reason. *Why the original:* the phase-2
  column means the unanchored second read; if a post-reveal revision took its place, the column would change what
  it measures on exactly the items where anchoring happened.

**Everywhere else in this document, for a criterion item:** "the official answer" means the criterion, "the settled
answer" means the settled criterion, and rewriting a rubric starts from the settled criterion. The phase-1 packet
shows the criterion where it would mark the official answer; phase 3 and the re-keyed output label it "criterion".

For these items there is no official-answer guess (they are left out of that guess rate); the arm guess is still
recorded, at the end of step 2a, before the criterion is shown. *Known limits:* a packet with
no official answer tells the reviewer what kind of item it is, so the category is not hidden for these items; and
with a single agent answer (single-arm data) there is nothing to compare it with, only an unanchored read. For
such an item phase 3 receives no A/B comparison at all: only the step-2a read of that one answer and the step-2b
judgement of the criterion, so its phase-2 evidence is weaker by design, and the log says so per item.

## 5. Phase 3: the district official

The project lead rules on every item section 2 sends to phase 3. The project lead does not re-read the source
material; the reviewers bring the facts:

- **One fact list per item**, built by both reviewers: each load-bearing fact with a verbatim quote and the
  message it comes from. Each reviewer also lists the facts that cut **against** their own judgement. The two
  lists are merged mechanically: no fact is dropped by either reviewer.

The project lead's ruling is written in the same answer-level form as phases 1 and 2 (section 6), with the
settled answer where the key is wrong, and is mapped by the same table. **The phases agree** on an item when
their judgements are identical answer by answer: the same judgement of the official answer, the same judgement
of every agent answer, and, where the key is wrong, settled answers that do not differ on a load-bearing point.
The answer-by-answer comparison is computed by script on the re-keyed judgements (section 5a). Whether two
settled answers differ on a load-bearing point is judged by the project lead in phase 3, which every item with a
wrong key reaches. If all three agree, the outcome is settled. If not, the three
discuss it once, with the fact list in front of them. If they still disagree after that, the outcome is
**Ambiguous (reviewers split)** and every ruling is published.

If the project lead is unavailable, the item **waits**: its adjusted entry reads "pending". Without the project
lead, only two kinds of item are settled, and neither changes a grade: an item phase 2 does not review (it keeps
its official grade, section 2) and an unquestioned control (section 2, which excludes any item whose step-2a record
was superseded after the criterion was shown).

*Known limit:* phase 3 is not blind. The project lead knows which answer is the official one and belongs to the
team under test. Phase 3 can block a correction but cannot impose one alone: a ruling against phases 1 and 2
ends as "reviewers split", and the item keeps its official grade. Phases 1 and 2 are on the record before phase 3
rules, so any such ruling is visible in the log.

### 5a. Mechanics (blinding by construction, METHODOLOGY section 5)

- The data the phase-2 packet tooling reads holds only what phase 2 may see (the one exception is the step-2b
  export of section 4, which reads a criterion only after the committed step-2a record exists). Item ids carry no
  meaning either (no question number or position, which can imply the category). Answer ids carry no meaning and differ from
  item to item, so neither an id nor a position says which answer is official or which arm an answer came from;
  which answer is official, the grades, the rubric, the category and the arms live in separate files the phase-2
  packet builder never opens.
- The item ids are fixed before any packet is built: derived by a script from a seed held by the key-holder (so a
  reviewer cannot invert an id into a question number), and the list of ids is committed to the study's log
  before the letter order is drawn; the seed is published when the round is settled, so anyone can then re-derive
  both.
- A script builds the phase-2 packets. It draws each item's letter order from a logged seed and the item's own id
  (so the same letter is not the same answer from item to item) and writes the letter key to a separate file
  whose hash is published before the phase-2 read. The key is held by a named seat that reviews no item in that
  round, recorded in the study's log.
- **The key-holder's duties, in one line:** the key-holder runs the mapping script, which reads the key and
  prints each item's phase-2 outcome and phase-2 judgement re-keyed from letters to "official" and the arm-blind
  answer ids (never the letters, never arm labels), into the phase-3 packet. It re-keys an item only after that
  item's phase-2 judgement is recorded with its hash (for a criterion item: the step-2a record that is mapped,
  together with the step-2b record; where a step-2a record was superseded after the criterion was shown, the
  original is the record re-keyed for mapping and the superseding record is re-keyed and carried beside it, for
  phase 3, as the post-reveal revision). The key file itself is revealed only into the study's log,
  only once the item is settled (after phase 3, or after phase 2 for an unquestioned control), and every reveal is
  logged with its time. An unlogged reveal is the one way this seat can break the design.
- *Known limit:* METHODOLOGY section 5 asks for a named non-participant. The key-holder reviews no item but
  belongs to the team under test.
- Each phase's judgement is committed with a hash before the next phase sees anything of it, and each phase's
  judgements are committed to the study's repository before the next phase's packets are handed out: the commit is
  the outside witness that the order held. Phase 2 never sees the phase-1 judgement. Phase 3 sees both, with the
  merged fact list.
- The fact lists are merged by script (concatenate, keep every fact, mark which reviewer contributed it), never
  by hand.

## 6. Outcomes, and how each one scores

**The answer-level judgement.** Phases 1 and 2 write the same form for each item: for the official answer and
for each agent answer, one of **correct**, **partly correct**, or **wrong**; or, for the item as a whole,
**ambiguous** (the source supports more than one reading). When the official answer is not judged correct, the
reviewer also writes the fuller correct answer.

**Grade levels.** A rubric line is **met** when its official score is the maximum of the benchmark's line scale
(for a 1.0 / 0.5 / 0.0 scale, 1.0). An official grade is **full** when every rubric line is met, **zero** when
every line scores the scale's minimum, and **partial** otherwise, whatever the benchmark's own scale. A judgement of correct, partly correct or wrong
corresponds to full, partial or zero.

**From judgement to outcome** (applied by script; the first matching row decides):

| judgement | outcome |
|---|---|
| the item is ambiguous | **Ambiguous (source)** |
| the official answer is partly correct or wrong | **Key wrong or incomplete** |
| the official answer is correct, and every agent answer's judgement corresponds to its official grade level | **Key stands** |
| the official answer is correct, and one or more agent answers' judgements do not correspond to their official grade levels | **Grading error**, for exactly those answers |

For an item whose reference is a criterion (section 4), the judgement of the criterion takes the place of the
judgement of the official answer in this table.

How each outcome scores:

- **Key stands:** grades unchanged in both columns.
- **Key wrong or incomplete:** the rubric is rewritten (below), and every arm's answer to the item is re-scored
  against it for the adjusted column, whatever its official grade. This is applied only once phase 3 settles
  the item.
- **Grading error:** the official column keeps the benchmark's own grade. For each flagged answer, the adjusted
  column takes a re-grade against the unchanged official rubric, applied line by line by the study lead, checked
  by the second reviewer, and settled in phase 3. Logged under its own heading.
- **Ambiguous**, logged as one of two values: **source** (the source material supports more than one reading)
  or **reviewers split** (section 5). Either way the item keeps its official grade in both columns, and all
  readings are published. Ambiguous is a legitimate outcome, not a failure to decide.

**Rewriting a rubric** (for "Key wrong or incomplete"): the study lead writes the new rubric lines from the
settled answer, in the benchmark's own rubric form, one line per load-bearing point of the settled answer. The
second reviewer checks that the lines say what the settled answer says and nothing more, without the answers in
front of them. The rewritten rubric is committed before any answer is re-scored. Re-scoring uses the same
grading method that produced the official column (the same judge model and judge prompt; for hand-graded
columns, the same grader). *Known limit:* the study lead who writes the lines has seen the answers; only the
check is blind to them.

**Two classes never move any single item's grade:**

- **Our own harness defect** (for example, how we worded the prompt around a question). On tuning data: fix the
  harness, re-ask, and report the result as a rerun, whichever way it moves the score. In a scored study the
  harness is fixed by the pre-registration: the defect is reported as a limit, and any rerun follows the
  pre-registration's own rerun rules, for every arm or for none.
- **Official evaluator defect** (a flaw in the benchmark's scoring code, whatever its reach): its effect may be
  measured only by a separate re-scoring of every item it can affect, in every arm, declared in advance,
  reported as its own column, and reported whichever arm it favours.

## 7. What is published

- A per-item change log: item, official answer, our finding, the messages that prove it, each phase's
  judgement, each phase-2 reviewer's guesses (which answer was the official one; which arm each agent answer
  came from), the outcome, and for each adjusted entry the grading method that produced it (the official judge
  re-run against a rewritten rubric, or a hand re-grade for a grading error).
- The phase-2 guess rates reported beside the rate a blind guess would reach (1 / the number of answers in the
  packet for the official answer, over items that have an official answer; 1 / the number of arms for the arm
  guess).
- An open invitation to dispute any item, at the head of the log. A dispute that succeeds after publication is
  handled as a correction under METHODOLOGY section 7: a dated correction block on the artifact.
- Every correction to the key applied to all arms identically (section 6); a grading error is corrected for the
  answer it names. In a scored study, the adjusted set is frozen
  before arm labels are unblinded; an item still "pending" at the freeze counts at its official grade, is
  listed as pending, and the adjusted column is labelled provisional until none is pending. On single-arm tuning
  data, every reviewed item is flagged as reviewed with the agent's answer in view.
- This sentence, or its equivalent, wherever an adjusted score appears: **all reviewers belong to the team
  that builds the agent under test. These principles reduce our bias; they do not make the adjusted score
  independent.** That is why the per-item log and the dispute invitation matter most.

## 8. Upstream

A finding about the benchmark's key or its evaluator is reported to the benchmark's maintainers only after it
is settled under these principles, stating what was and was not checked, written as users who want the
benchmark to be right, with no claim about anyone's results.

## 9. Adoption by a study

A study adopts a version of these principles by a dated amendment to its pre-registration (METHODOLOGY
section 1), made before any scored answer exists. The amendment states the version adopted, the number drawn
for phase-2 controls and its seed, and the seat that holds the letter key. Where the study's pre-registration
already defines official and adjusted scores, or limits reruns, the amendment says how these principles refine
those sections. A first use of a version on unscored tuning data is logged as a pilot of the procedure.

## Open questions

Each stays open until the named party closes it; closing one is a new version.

- **The load of each phase. Closes it: the first pilot.** Phase 1 reads every item against the full source;
  phase 3 puts every questioned item in front of one person. The first pilot measures, for each phase, the
  number of items and the minutes per item; a scored study does not adopt these principles until those figures
  are in the change log.

## Change log

- **v0.2, 2026-11-17.** *Why:* building the tooling for v0.1 and running it on the real data of the BEAM study
  showed four things v0.1 did not say. (1) A fifth of that benchmark's questions (instruction following and
  preference following) carry a criterion, not an answer, so the A/B blind between official and agent answers
  cannot hold for them; the study lead first proposed showing phase 2 the criterion openly, and the BEAM design
  owner ruled that this would repeat the anchoring v0.1 was written against, and set the two-step procedure in
  section 4 instead, including that a step-2a record changed after the criterion was shown is kept as a published
  revision while the original is the record mapped. (2) The design owner's read of the tooling's data found that an answer id that names the
  official answer, or a letter order fixed across items, would tell the reviewer which answer is which; section 5a
  now requires meaningless per-item ids and a per-item letter order. (3) Re-keying a phase-2 judgement before it is
  recorded would let anyone holding both forms read that item's key; section 5a now orders it. (4) The commit of
  each phase before the next phase's packets go out is stated as the outside witness of order. Also: the guess-rate
  sentence no longer names a version. Proposed by the study lead from the design owner's rulings; the project
  lead's decision is recorded on the pull request that merges this version.
- **v0.1, 2026-11-17.** First version. *Why:* during the BEAM study's tuning, our corrections to the official
  key were first checked by a second read that was blind to our verdict and to the agent's answer, but showed
  the reviewer the official answer first, framed the way the key frames it. The project lead judged that this
  anchored the read on the key, and that one item it confirmed as a contradiction admits a reading in which
  the two statements describe different times. The project lead proposed the three phases and their roles,
  and set who reviews what: phase 1 every item; phase 2 the questioned items plus seeded controls; phase 3
  everything except unquestioned controls. The study lead added: controls among full-score answers, unlabelled
  answers, the shared fact list with verbatim quotes, keeping the change log and dispute invitation, routing
  grading errors to phase 3, the definition of agreement, and hiding why an item was selected. The project lead
  added: no rubric or category in the phase-2 packet. The BEAM study's design owner added: adoption through the
  pre-registration, the "pending" rule, measuring the phase-2 guess, facts against one's own judgement, the
  published independence sentence, "ambiguous" as an outcome with two log values, naming who closes each open
  question, fixing the control draw before any phase-1 outcome exists, the key-holder's duties, recording the
  phase-2 arm guess, and measuring every phase's load in the pilot. Three review rounds on this file
  supplied: the rubric-rewrite rule, re-scoring every arm on a corrected item, the answer-level judgement and its
  outcome table, an unlettered phase 1 and a key read only by script, agreement answer by answer, the grade
  levels and the re-grade for a grading error, the mechanics of section 5a, and the fit with a pre-registration
  that already defines both scores and limits reruns. The peer review (the calibration seat) supplied: phase-2
  judgements re-keyed to arm-blind answer ids for phase 3, a definition of a met rubric line, phase 3 as able to
  block but not impose, the grading method marked per adjusted entry, who judges a load-bearing difference, and
  guess rates beside chance. Decided by the project lead.
