# P1b: the larger K = 3 against k = 1 instrument, on the later exchanges (DESIGN, for the design owner's read)

Status: **draft for reading** (design owner's GO to design, Office crossing 32699). Nothing in it is built or run until
it has been read. The registered study stays at k = 1 meanwhile. Study lead: Borges.

## 0. Why, in one paragraph

P1 came out INCONCLUSIVE (accuracy 80.0% at K = 3 against 82.7% at k = 1; exchange-mean difference -3.5 points, bounds
[-15.4, +8.3]). The decision it feeds is large: on the first 45 exchanges K = 3 read about 3.4 times faster (86.5 s
against 290.7 s per exchange), which, if it held over whole conversations, would cut the study's arm 2 from about 315 to 353
GPU-hours to about 94 to 118. That projection rests on a ratio measured only on run A's mildest stretch. P1b answers both
open questions with one pair of runs: **is K = 3 as good** on new questions, and **is the saving real** where k = 1 is slowest.

## 1. Material and runs

- **Material:** conversation 9 (a tuning conversation, never scored), exchanges **46 to 135**, the 90 exchanges P1 did not
  read. These are run A's slow stretch (its thirds ran 307 and 452 s per exchange).
- **Runs: continue from P1's preserved end states**, not from exchange 1. The K = 3 and k = 1 end states after exchange 45
  are preserved and hash-checked (unchanged through every P1 session, before and after). Each run resumes a disposable copy
  of its end state and reads exchanges 46 to 135 under the same setup: K = 3 in 30 rounds (46-48 ... 133-135), k = 1 in 90.
  Then one answering session per end state, as in P1. This saves re-reading 1 to 45 and keeps each run continuous with its
  P1 state. **Build needed:** the launcher has no "continue reading" mode; it is specified contract-first and reviewed before
  use, like the P1 launcher.
- **Measures per run,** as in the reading pilots: wall seconds and input tokens per exchange (from `turns.jsonl`, reading
  rounds only), compactions, notes, the co-load sampler line.

## 2. Size (requirement 1)

From `tools/p1-answering-power-clustered.py`, the script that set P1's rule, at the rule's settings (margin -0.10, bounds
at the 4th and 96th percentiles), base accuracy 0.80 (P1 measured 80 to 83%), 2,000 trials per cell, seed 20261124
(`data/p1b-power-curve.txt`). Share of runs in which a TRULY EQUAL K = 3 is ACCEPTED / a TRUE 10-POINT LOSS is ACCEPTED:

| layout | questions / exchanges | equal K = 3 accepted (D 0.15 / 0.25 / 0.35) | 10-point loss accepted |
|---|---|---|---|
| P1 as run | 75 / 38 | 0.59-0.61 / 0.40-0.45 / 0.31-0.34 | 0.04-0.07 |
| **A: 46-135 at P1's density** | **150 / 76** | **0.81-0.85 / 0.60-0.68 / 0.48-0.53** | **0.04-0.05** |
| C: 46-135 at a richer yield | 216 / 90 | 0.93-0.97 / 0.74-0.83 / 0.61-0.72 | 0.04-0.06 |

(Ranges span within-exchange correlation 0.2 and 0.6.) P1 measured D = 0.187, between the first two columns. **A fair chance
exists at a feasible size,** so the statistic and the question stand; no different statistic is needed. P1's writer found
1.7 facts per exchange (cap 4), which on 90 exchanges points to about 150 questions, layout A.

**Rule for the count, fixed now:** the writer takes as many well-supported distinct facts as exchanges 46 to 135 give
(cap 4 per exchange; each fact stated within 46 to 135, none depending on exchanges 1 to 45), plus abstention items as in
P1. Before any answer exists the same script is re-run at the final count and layout, 4,000 trials. **If a truly equal K =
3 would be accepted less than half the time at D = 0.25, the study lead stops and reports to the design owner before any
run** (the honest options then are a different statistic or a different question). The margin is never loosened.

## 3. Pooling with P1 (requirement 2): NO

Simulated conditional on P1 having come out INCONCLUSIVE, which it did (`tools/p1b/pooling_sim.py`, seed 20261125, 3,000
trials per cell, `data/p1b-pooling-sim.txt`; decision on the overall bound only, a stated simplification): a true 10-point
loss is accepted 4.6 to 5.0% of the time by P1b alone and **4.7 to 6.9% pooled** (worst where the arms agree most); an
equal K = 3 is accepted 0.61 to 0.86 alone and 0.71 to 0.91 pooled. Pooling buys some power and pays for it in error
rate, and it also mixes two estimands: P1's questions were answered at the after-exchange-45 state, P1b's will be answered
at the after-exchange-135 state. **P1b decides on its own questions only.** The pooled bound is printed beside the verdict
and decides nothing.

## 4. Speed as a registered quantity (requirement 3)

- **R** = (K = 3 wall seconds per exchange) / (k = 1 wall seconds per exchange) over exchanges 46 to 135, reading rounds
  only, each from its own run's `turns.jsonl`. Input tokens per exchange reported beside it.
- **Stop line, fixed now: if R > 0.75** (K = 3 less than 25% faster on the later stretch, the study's existing speed bar),
  the question is closed: the study runs at k = 1 **whatever the answer test says**.
- **R <= 0.75 and ACCEPTED:** K = 3 is recommended for the study, provisional on one run per k.
- **R <= 0.75 and INCONCLUSIVE or WORSE:** k = 1 stays; nothing further is asked of conversation 9.
- Bound, stated in the result: one run per k; co-load not separated (the sampler line is printed).

## 5. Writer and second reader (requirement 4)

Chosen by DECLARATION, never by assumption. Each candidate declares, before seeing any material, whether they have seen:
(a) any student record of conversation 9: run A's or the P1 runs' transcripts, notes, stores, answers or judge reasons;
(b) BEAM's official probing questions or rubrics for conversation 9, including run A's phase-2 packets;
(c) P1's key-fact list or its answer files. A candidate clean on all three may write. The second reader must be clean on the
same three, and also must not see the writer's list before doing their own check. They machine-check that every item's span
occurs exactly once in the stated speaker's text, and read each gold line against its span. **Not eligible:** Clio's seat
is down; the study lead and the design owner; Sol (run A's phase-2 reader) and Aleph (run A's key holder). **Proposed order
to ask:** Ariadne, Zephyr, Halley, Mira; the first two clean declarations are writer and second reader. Declarations are
recorded as given.

## 6. Answer rules, written in up front (requirement 5)

1. The answer is the turn's final text block. A turn whose final assistant message ends on a tool call is answered by its
   last text block; a turn with no text block is a missing answer.
2. A final text whose whole stripped content is the placeholder `[no output]`, or "no output" in any letter case with
   optional surrounding brackets or punctuation, is a missing answer: incorrect, no judge call. Other near-variant classes
   (none, null, empty, n/a, no content, no response, no answer, no letters or digits) are listed by the script and go to the
   design owner per class, with id, class, length and item type only, before grading.
3. The sensitivity score substitutes, for each missing answer, the judge's grade of the last text block before it.
4. Correct iff the question-seeing judge (claude-sonnet-5-5, effort low, the BEAM template pinned at 3e12035, the question
   filled) gives the gold line a 1. The raw score is secondary and never decides; 0/0.5/1 counts are reported.
5. The deciding statistic, the bootstrap (B = 1,000, 4th/96th percentiles, seed fixed before the key is opened), the three
   outcomes, the validity floor (50% at k = 1), and the last-position guard (the same statistic over exchanges whose number is
   a multiple of 3, against -0.20) are P1's, unchanged. The more-than-5-missing re-ask rule is P1's.
6. Answers are pooled across k under opaque ids, the key sealed by hash and held by a second seat before the first judge
   call. Progress during sessions is read as counts only.

The tools exist: `tools/p1_answers.py`, `tools/p1_grade.py`, `tools/p1_score.py` (contract-tested, mutation-checked),
plus the new reading-continuation mode in section 1.

## 7. Cost (requirement 6)

Each figure from a named measurement; GPU-hours, single card, one job at a time.

| step | GPU-hours | from |
|---|---|---|
| k = 1 reads 46-135 | 9.5-10.6 | run A's measured thirds (307, 452 s/exchange); upper end scaled to the k = 1 re-run's pace on 1-45 |
| K = 3 reads 46-135 | 2.8-3.5 if P1's ratio holds; 7.1-8.0 at the stop line | the same base times 0.30-0.33 (P1) or 0.75 |
| two answering sessions, about 168 questions each | 4.6-5.2 | P1's measured 49.2 and 55.3 s per question |
| judge | minutes, API cost a few dollars | P1: 168 calls in 59 s |
| **total** | **about 17 to 24** | |

Not measured, so not costed: the writer's time for the list, and the second reader's.

## 8. Limits stated now

One run per k; conversation 9 only; continuation from P1's states means P1b's arms differ in whatever P1's arms differed in
at exchange 45 (the k = 1 end state has no built-in-folder writes, the K = 3 end state does), reported as it was for P1.
INCONCLUSIVE is not evidence of a loss.
