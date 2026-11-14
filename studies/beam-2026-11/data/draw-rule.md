# Draw rule: tuning and training conversations

## Purpose

Tuning and training conversations are drawn by a seed nobody can choose,
before any result is read. Drawn conversations are never scored.

## Procedure

1. This rule and the script
   (`studies/beam-2026-11/tools/draw-tuning-conversations.py`) are committed
   first, in one commit, and published.
2. The seed is the first 8 hex digits of the SHA of the commit that adds the
   script. That SHA does not exist until the commit is made, so nobody could
   pick it in advance.
3. The draw is then run, and its output is committed in a second commit.
4. Anyone can re-run it:
   `python3 studies/beam-2026-11/tools/draw-tuning-conversations.py`
   (reads the seed from git), or with `--seed-hex <8 hex digits>` to check a
   draw by hand. The script refuses to run on an uncommitted or edited copy.
   That includes a later committed edit: the script must be identical to the
   version in the commit that added it.

## Strata (100K split)

The 19 eligible 100K conversations, by content tokens (Qwen3.8-27B
tokenizer). Conversation 15 is the existing tuning conversation and is
excluded. The median conversation (7) belongs to neither stratum and stays
scored.

| conversation_id | tokens | group |
|---|---|---|
| 4 | 106,945 | lower |
| 8 | 110,625 | lower |
| 14 | 112,110 | lower |
| 13 | 117,170 | lower |
| 9 | 121,456 | lower |
| 6 | 122,690 | lower |
| 2 | 123,805 | lower |
| 1 | 124,215 | lower |
| 3 | 126,491 | lower |
| 7 | 129,081 | MEDIAN (excluded from draw, stays scored) |
| 17 | 129,846 | upper |
| 16 | 143,591 | upper |
| 10 | 149,955 | upper |
| 5 | 154,773 | upper |
| 19 | 163,498 | upper |
| 18 | 173,432 | upper |
| 20 | 181,440 | upper |
| 12 | 186,294 | upper |
| 11 | 190,209 | upper |

## What is drawn

One conversation from each 100K stratum, and two from the 500K split's 35
conversations (ids 1 to 35). The draw order is fixed:

1. Seed a Python `random.Random` with the seed as an integer.
2. One sample from the lower stratum (ids sorted numerically).
3. One sample from the upper stratum (ids sorted numerically).
4. Two samples, without replacement, from the 500K ids sorted numerically;
   the order returned is kept.

Purposes, by position:

- 100K lower pick and 100K upper pick: entry-gate runs and lean-profile tuning.
- First 500K pick: arm-3 training.
- Second 500K pick: length-stress tuning.

## Consequence

The scored 100K set becomes 17 conversations (20, minus conversation 15,
minus the two 100K picks). The drawn conversations are named in the
pre-registration and are never scored. The study lead and the design owner
do not choose or change any pick.

## Data provenance

BEAM dataset on Hugging Face (Mohammadta/BEAM), licence CC BY-SA 4.0.
The script does not read these files; their hashes are recorded in its
output.

- `data/100K-00000-of-00001.parquet`: sha256
  `c0519be25907005ba873c927c50877471d550873039d96c041554d0075a78ace`
- `data/500K-00000-of-00001.parquet`: sha256
  `af05921c979355038e1761b7cde3d2dd713200dd3071b278de0200f6c7f30122`

## Record

- The rule and script were published in commit `75f72db7` before the draw ran; the draw ran from that
  commit and its output is [draw-result.json](draw-result.json).
- Before publication, one earlier local commit (`5d22250e`) was amended, before any draw had been run
  with it, to add the check that a later committed edit of the script cannot reuse the seed and to fix a
  path bug that made the git mode refuse a committed script. Anyone can run `--seed-hex 5d22250e` to see
  what that commit would have drawn.
- The git mode's success path was first exercised in a separate throwaway repository with a different
  commit, so no draw for seed `75f72db7` was computed before publication.
