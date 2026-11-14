<!-- Carried from engram-experiments (private) on 2026-11-14 at its v1 text, unchanged, so both repos run on one set of conventions. Author of v1: Kepler. Amend by PR with the reasoning in the PR body. -->

# Research Methodology — experiment-design conventions

*Version-controlled on purpose: these meta-principles are themselves research
output. Amend by PR with the reasoning in the PR body; never edit history.
(v1, 2026-08-25, drafted by Kepler from the conventions practiced in the
July calibration studies and the August benchmark/identity work; approved
shape per Lei's 2026-08-25 direction.)*

## 1. Pre-register before you run

Every study writes its design BEFORE collecting the data it will be judged on:
hypotheses, protocol, sample size (with the extension rule pre-declared if any),
scoring rubric, and the decision rule for each outcome. The pre-registration is
frozen once signed — later changes are amendments with their own timestamps,
never silent edits. A result only licenses claims the pre-registration scoped
(the claim-license fence: you may claim over exactly the bias layers you
exogenized, no further).

## 2. Instruments are validated against known positives

An instrument (scorer, classifier, grep, diff, comparator) may not assert an
absence or a clean result until it has found a planted known-positive through
the same path. Controls must be able to FAIL: a control that cannot come back
different from the treatment certifies nothing (measured live: the vacuous
dev-vs-dev~1 comparison, 2026-08-25). Where possible, verify by mutation —
flip the thing the instrument claims to detect and watch it fire.

## 3. Measured numbers only, with their instrument named

A number in a durable artifact comes from a measurement run for that sentence,
with the instrument cited — not from memory, not relayed from someone else's
sentence (whose scope was theirs, not yours), not from mental arithmetic over
correct parts. Bounded reads state their bound and assert collected == total.
When two measurements disagree, neither is repeated onward: someone counts.

## 4. Standard study layout

```
studies/<slug>/                  slug: <topic>-<YYYY-MM>
  preregistration.md             frozen once signed; amendments appended, dated
  protocol/                      runnable procedure, prompts, rubrics, taxonomies
  data/                          frozen run artifacts (raw before derived)
  tools/                         UI + analysis code used on this study
  report/                        results, analysis, conclusions
  PROVENANCE.md                  who/when/where-from; ENGRAM node ids for the
                                 decision history behind the design
```

## 5. Blinding is mechanical, not honor-system

Where a study is blind, the blind is enforced by construction: sealed keys held
by a named non-participant, published only after ratings lock; condition labels
randomized per unit; anything that could carry a side-channel tell (e.g. a
model's thinking blocks, timing artifacts) identified in the pre-registration
and stripped or measured. "The rater promises not to look" is not a design.

## 6. Outcome taxonomies are pre-declared

If a positive result needs decomposing (which failure class, which tell layer,
which question category), the taxonomy and the per-layer decision rule are in
the pre-registration — classifying after seeing the data is exploration, and
gets reported as exploration.

## 7. Corrections are first-class results

Errors found after publication are corrected ON the artifact (dated correction
blocks, supersede-not-overwrite), and the correction states what was wrong, how
it was caught, and what survives. A finding's history of corrections is part of
the finding. Negative results and dead ends are recorded where the next person
will look — an hour spent ruling something out is only spent once if written.

## 8. Provenance reaches back to the graphs

Study decisions trace to ENGRAM nodes (the thinking of record) and forward to
the artifacts here. PROVENANCE.md carries the node ids. The paper repo cites
frozen artifacts in this repo; this repo does not hold paper prose.

## 9. Scale claims honestly across seats and lineages

Per-seat measurements are labeled per-seat; pooling requires one shared
instrument run by each seat on its own data (method variation and seat
variation must not be entangled). Same-lineage agreement between agents is
discounted as correlated judgment; cross-lineage or reality-anchored
corroboration is what upgrades it.
