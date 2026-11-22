# P1b: the larger K = 3 against k = 1 instrument, on the later exchanges (DESIGN, for the design owner's read)

Status: **ACCEPTED as the design** by the design owner (2026-11-19, read in full at 46cfb362), with six
additions, written in below as marked (A1 to A6); amendment diff read and GO TO BUILD given (2026-11-19), plus A7. The
registered
study stays at k = 1 meanwhile. Study lead: Borges. Key holder for P1b: Kepler.

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
- **A1. The continue-reading launcher's contract, stated before any code** (reviewer: Luria, else Zephyr; not the
  design owner):
  - (a) **What a run carries from round to round, and whether the preserved end state holds it:** the ENGRAM store
    (`knowledge.db` with its side files): held, hashed. The built-in auto-memory folder: held, hashed (K = 3 has two
    files; k = 1 has none). The Claude Code session transcript (the resumed session's JSONL, which carries the context and
    every compaction): held in the home. NOT held, and named as limits: the model server's in-memory state (the prefix
    cache; a resume starts cold, which can only slow the first rounds), and the continuity of the process itself: a resume
    fires the session-start hooks once at exchange 46, which an unbroken run would not do there. The resume's first-turn
    injection is recorded and reported.
  - (b) **Equivalence cell:** for the same state, the input the continue mode feeds for exchange 46 is byte-equal to what
    the full-run feeder would feed there (the plan dump of a full run, cut at exchange 46).
  - (c) It refuses a start that is not on a K boundary (46 for K = 3 and for k = 1, given rounds end at 45), and a state
    whose content hash differs from the preserved one.
  - (d) It works on a disposable copy only; the preserved original's hash is re-checked after each run (the P1 launcher's
    protected-home guard).
- **A7. Serving setup pinned (design owner, 2026-11-19):** both P1b readings and both answering sessions run on
  exactly the serving setup that produced P1's end states: the same model server build, model file and settings, recorded at
  each run's start. The queued serving-stack pilot changes nothing in that setup while P1b is open. If the study later
  adopts a different serving stack, R is not carried over: it is measured again there before K = 3 is used.
- **Order of the card (design owner, 2026-11-19):** the serving-stack pilot may use the card while the list and the launcher
  are
  in work; once the list is checked and the launcher reviewed, P1b goes ahead of everything else named in section 7. No
  P1b run until the list is checked, the count re-simulated at 4,000 trials, and the launcher reviewed; the final count and
  its two rates go to the design owner before the first reading round.
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
- **A2. R is computed by a script with a written contract:** from each run's `turns.jsonl`, reading rows only; R = (sum of
  the K = 3 run's reading wall seconds / 90) / (sum of the k = 1 run's reading wall seconds / 90), so a K = 3 round's wall
  time is divided evenly over its 3 exchanges by construction; compaction time counts wherever it falls (inside a round's
  wall, or as its own row). Both readings run on the same card under an exclusive GPU lease with no other GPU job, the broker
  status read at each run's start and end, the co-load sampler line printed per run. **No discretion near the line:** R
  decides as registered, with its bound stated.
- **Stop line, fixed now: if R > 0.75** (K = 3 less than 25% faster on the later stretch, the study's existing speed bar),
  the question is closed: the study runs at k = 1 **whatever the answer test says**.
- **R <= 0.75 and ACCEPTED:** K = 3 is recommended for the study, provisional on one run per k.
- **A3. What ACCEPTED means, written into the result text:** "not worse by 10 points or more", never "equal". At layout A a
  true 5-point loss is ACCEPTED 0.22 to 0.36 of the time at D 0.15 to 0.25 (0.17 to 0.36 over all six cells of
  `data/p1b-power-curve.txt`).
- **R <= 0.75 and INCONCLUSIVE or WORSE:** k = 1 stays; nothing further is asked of conversation 9.
- Bound, stated in the result: one run per k; co-load not separated (the sampler line is printed).

## 5. Writer and second reader (requirement 4)

Chosen by DECLARATION, never by assumption. Each candidate declares, before seeing any material, whether they have seen:
(a) any student record of conversation 9: run A's or the P1 runs' transcripts, notes, stores, answers or judge reasons;
(b) BEAM's official probing questions or rubrics for conversation 9, including run A's phase-2 packets;
(c) P1's key-fact list or its answer files. A candidate clean on all three may write. The second reader must be clean on the
same three. **A4, what is blind and what is on the list:** BLIND, the second reader receives the writer's QUESTIONS
without their gold lines and spans, and answers each from exchanges 46 to 135 alone, writing the answer and the exchange it
rests on. ON THE LIST, afterwards: they machine-check that every item's span occurs exactly once in the stated speaker's
text, compare their blind answer with the writer's gold, and flag any item whose answer depends on exchanges 1 to 45. An
item where the blind answer and the gold disagree, or that is flagged, is dropped, not mended (as in P1). **Not eligible:** Clio's seat
is down; the study lead and the design owner; Sol (run A's phase-2 reader) and Aleph (run A's key holder). **A5, order to ask
(design owner's change):** Mira, Halley, Zephyr, Ariadne last (Lei's 11-17 direction that Ariadne's ENGRAM Manager work
moves smoothly). The first two clean declarations are writer and second reader; if only Ariadne is clean, she writes.
Declarations are recorded as given.

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

- **A8. Timetable and cut-off rule (design owner, 2026-11-19, fixed before any reading round).** The card is
  used in daylight only. Lei's recorded words, as read by the design owner: 2026-10-27, "The machine has to go off around
  9 pm latest because it is bright and loud in the night and Leona is sleeping in the room"; 2026-11-16, "plan for the EOD
  around 8:30". The design owner's own bound, stricter and labelled as his: no GPU work of this study runs past 8:00 PM
  New York; a different hour from Lei replaces it. **Option A, each reading unbroken** (a split would add a second cold
  start and a second session-start injection to both arms). (1) The K = 3 reading starts on 2026-11-19 as soon as the
  card rule holds. (2) The k = 1 reading runs on its own day and starts only if it can start at or before 9:00 AM New
  York (its 10.6-hour upper bound must end by 8:00 PM); a later start moves it to the next day. (3) The two answering
  sessions run on the day after the k = 1 reading, both the same day, in the order the P1 rule sets. **Cut-off rule, by
  the clock only:** a reading that has not completed exchange 135 by 7:45 PM New York is stopped; that run is NOT used
  for R or for answering; its per-exchange wall times up to the stop are reported beside the result; the reading is
  done again unbroken on a later day, and the redo counts whatever its speed. The rule never depends on anything about
  answers. At each start: the A7 serving lines (C5) and the GPU broker status are recorded; at each end the broker status
  again. Limits line, in the design owner's words: P1 itself recorded no serving lines, so A7 rests on 'no record match
  for P1, file dates unchanged' (model file last modified 2026-11-14, server binary 2026-08-28, both before P1's reading
  runs began on 2026-11-16).
  - **A8 amendment, 2026-11-19 (K = 3 reading only), relayed by the design owner (2026-11-19).** *Who:* Lei,
    the owner of the household bound the cut-off was derived from. *When:* 4:48 PM New York, before the 7:45 PM cut-off,
    with 19 of the 30 K = 3 rounds done. *What he had seen:* round counts and the projected end only; nothing about
    answers (the study lead's progress reports carry counts, error counts and a projected end, never answer text). *His
    words:* "About today's 3-turn-per-read test, don't waste it if it's close to finish at 7:45pm, keep running until I
    check in and call eod tonight, and I'll make the decision whether it's still too far from finish and whether we
    forfeit the results and try another day." *Change:* the 7:45 PM clock stop is removed for this one reading; it runs
    until Lei calls end of day. *Forfeit:* Lei's decision, made then; his named criterion is distance from finishing. A
    reading that completes exchange 135 is used as designed; a forfeited one is treated as the cut-off rule above treats a
    stopped run. The design owner's 8:00 PM bound is lifted for this one run by the same word; nothing else starts on the
    card tonight. The k = 1 rule (start at or before 9:00 AM New York) is unchanged unless Lei changes it. *How the stop
    was lifted, without touching the session:* the cut-off was a `timeout` wrapper around the session process. The
    wrapper alone was suspended (SIGSTOP) at 21:50:52Z, before its timer fired; the session and its children kept
    running. A watcher resumes the wrapper after the session process has ended, so the run script's end steps still run.
    *Consequence for the record:* if the session ends after 00:45Z, the wrapper's timer has fired while suspended and the
    run script will print exit 124 with its "CUT-OFF ... NOT used" line although nothing was stopped. For this run, that
    exit code and that line do not decide anything. Completion is read from the session's own record (every step of its
    `setup.txt`, all 30 reading rounds in `turns.jsonl`, the saved end state and its hashes). If Lei forfeits while the
    reading is running, the session is stopped by sending the wrapper's stop signal (TERM) to its process group. The time
    of the stop and the rounds done are then reported as the cut-off rule requires.
- **A9. The student's Claude Code is pinned for the k = 1 reading (design owner, 2026-11-19;
  written before the first k = 1 round).** *What the setup file said:* the components file of setup `171fb069`, which
  both P1b readings run under, records Claude Code 2.1.327. *What actually ran,* read from each session's own
  transcript records (tuning log, entry "DEVIATION found", commit `89267b5f`): P1's readings 2.1.325; P1's controls
  2.1.327; P1's two answering sessions 2.1.328; P1b's K = 3 reading 2.1.328. The student's `claude` resolved through
  the study lead's own seat, which updated itself; the feeder's run-time check covers only its own files. *The pin and
  why:* the k = 1 reading runs on an exact copy of the 2.1.328 binary kept outside the seat's update path (sha256
  `a982d38030b97e750848add2cbb2df6d9a70d5544a22ca9b216a349ba25865e8`), so R compares the K = 3 and k = 1 readings on
  one harness version. *Refuse on mismatch:* a launcher change could not be built and read by a colleague before
  9:00 AM New York, so the design owner's alternative applies: the hash is verified at launch by the run script, which
  puts the pinned copy first on the search path, records the command and its output, and refuses to start if the
  `claude` it will run hashes differently. The record is written to its own file at launch and appended to the run's
  `setup.txt` after the run, because the launcher creates and writes `setup.txt` while it runs. *Limit carried to
  P1's report:* P1's version spread (readings 2.1.325, controls 2.1.327, answering 2.1.328) is stated there as a
  limit, not smoothed.
- **A10. Student custody: both P1b readings run exposed; nothing after them does (design owner, 2026-11-19;
  security judgments by Zephyr, 2026-11-19).** *The exposure:* the student of either
  arm runs as the study lead's OS user, with a shell and bypassed permissions, so it can read anything that user can,
  including the study lead's private files, the private key lists and the dataset with every gold answer, and it can
  reach services on the host's loopback. *What the records show:* over all 65 student transcripts on the host, no tool
  call named a path outside the student's own home except the evidence files the planted-fact controls handed it, and
  no search was rooted at or above the student's home; a value-blind scan for secret formats found nothing (its
  positive control fired). Outside the K = 3 reading's lineage, two other runs crossed a boundary with no data of
  consequence: one wrote its own scratch files under the shared temporary directory, and three calls (one practice
  run, one entry-gate run) fetched the title of another host service's dashboard on loopback. *Bound, carried with every number from
  either reading:* the student ran as the owner's user with a shell and bypassed permissions; its tool inputs were
  scanned with no path outside its home except by-design controls; a path-free discovery would not have appeared in
  that scan. *Rules:* (1) the k = 1 reading runs in the same setup as the K = 3 reading (no wrapper, on
  the pinned binary of A9), because R is a speed measurement only if the two readings differ in K alone; it is the
  last run under this allowance. (2) Nothing after the k = 1 reading runs without the student wrapper (a process,
  filesystem and network boundary around the student only, never around the feeder), pilots included, and only after
  the security seat has read the wrapper. (3) The value-blind secret scan, with its positive control, runs over the
  k = 1 reading's transcripts the moment the reading ends, before any number from it is used; any path outside the
  student's home that is not a planted control, any search rooted at or above it, or any secret-format hit means the
  run is discarded, not bounded. (4) The wrapper's own cost (added latency on the model path per exchange, any tool the
  student loses) is measured on a pilot before the registered setup is frozen. (5) A sealed key or answer list sits
  behind a user or host boundary, never behind a file mode on a user the student shares: a mode bit is not a seal when
  the owner's processes run the exam. *Our-side control from 2026-11-20:* each morning, the value-blind scan over every
  student transcript written since the last scan, one line to the design owner.
- **A11. The k = 1 reading starts tonight, overnight (design owner, 2026-11-20; written before
  the first k = 1 round).** *Lei's words,* 8:04 PM New York on 2026-11-19, relayed verbatim by the design owner: "How
  about we run another away night practice tonight? I'll leave the machine on, and Borges can run through the night?
  ... Tonight we rehearse the whole routine and make sure everything will work smoothly in the week I'm away." *The
  changed start rule:* A8's "starts only if it can start at or before 9:00 AM New York" existed because the night was
  closed to the card. Lei opens tonight, so the k = 1 reading runs as one unbroken overnight reading starting tonight
  instead, and the design owner's 8:00 PM bound is lifted for tonight by the same word. There is no daylight cut-off
  tonight. A hang guard of 20 hours (about twice the projected 9.5 to 10.6 hours) stops a stuck run, and a run stopped
  by it is reported, not used. *Unchanged:* the A9 pin, verified by hand at launch and recorded; the A10 custody
  terms. It is unwrapped, as the K = 3 reading was. It is still the LAST run under the security seat's allowance (no
  objection from Zephyr, 2026-11-20, conditions restated there). The falsifier and the value-blind scan
  with its control run the moment it ends, before any number is used. Any out-of-home path that is not a planted
  control means the run is discarded. Nothing about the run's content, K, exchanges, end state or analysis changes.

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

**What the card does otherwise (the design owner's question, answered before the first run).** No scored work is displaced:
the registered study cannot start any scored run while its pre-registration's "OPEN before registration" list stands (the
entry gate, the frozen texts, the judge-blinding rule, pairing, and the rest, read on main and on the study branch). And P1b
itself needs the GPU only after the second key-fact list is written and checked and the continue-reading launcher is built
and reviewed, so the card is free until then. What P1b's 17 to 24 GPU-hours would sit beside: the next speed pilot already
queued (the llama.cpp serving stack, the third step of the plan for the speed pilots), any entry-gate run, the Local Model Lab's parked rung work, and
other seats' GPU jobs through the broker. **The order among those is the design owner's to set.**

## 8. Limits stated now

One run per k; conversation 9 only; continuation from P1's states means P1b's arms differ in whatever P1's arms differed in
at exchange 45 (the k = 1 end state has no built-in-folder writes, the K = 3 end state does), reported as it was for P1.
INCONCLUSIVE is not evidence of a loss.
**A6.** The bootstrap is over exchanges within ONE run per k, so it does not carry run-to-run variation; any recommendation
for K = 3 is provisional on that, and the result says so.
