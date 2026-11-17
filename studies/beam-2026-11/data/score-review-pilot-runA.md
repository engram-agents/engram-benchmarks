# Pre-log: run A three-phase score review pilot (BEAM 100K, conversation 9)

Status: pre-log, committed before any pilot operation. Nothing below has run. Written 2026-11-17 by Borges (study
lead), after the design owner's reads (Kepler) and the answers of the key holder (Aleph) and the phase-2 reader
(Luria). Seat names are agent seats of the team under test.

Governs: `SCORE-REVIEW-PRINCIPLES.md` v0.1 (on main) as amended by the v0.2 draft (pull request 6, not yet merged,
waiting for the project lead's read). Tool: `tools/score-review` (pull request 7, not yet merged). Exact heads are
in the Heads section. If v0.2 or the tool changes before phase 1 starts, this pre-log is re-read and re-committed
first.

## What this pilot is for

Run A (whole conversation 9, setup 8762312e) is gate evidence, not a scored run. Its items were already read
under the old blind-second-read rule. The review convention says they are redone under the three-phase review,
all of them, including those that went our way, with the plan logged first. The pilot measures the PROCEDURE:
load per phase, whether the phase-2 blind holds (guess rates), and agreement between phases. It does not produce
a headline score.

## Scope (the project lead's coverage ruling, 2026-11-17)

- Phase 1: every item of run A conversation 9 (20 items: 16 answer-type, 4 criterion-type: Q9, Q10, Q15, Q16).
- Phase 2: the union of (a) every item where run A's answer is below full official score; (b) every item whose
  phase-1 outcome is anything other than "Key stands"; (c) a seeded draw of the remaining items, size N_DRAW.
- Phase 3: every phase-2 item except unquestioned full-score controls.
- N_DRAW = 3 (design owner, 2026-11-17: a pilot parameter; if fewer than 3 items are eligible, all of them).
  Eligible = items NOT in set (a). Seed: a drand round announced in a commit before the round exists, as for
  draw 2. THE DRAW PRECEDES PHASE 1. The tool's `draw` refuses once any phase-1 verdict exists, and that refusal
  is the rule. Set (b) is added after phase 1; a drawn item that phase 1 later questions sits in both sets.
  The draw size for the scored study is a separate decision for the pre-registration.

## Seats (final, design owner, 2026-11-17)

Phase 1 Borges. Phase 2 Luria, all 20 items, her caveat published. Key holder Aleph. Second holder of the key
files Ariadne (a non-participant; a sealed copy). Phase 3 the project lead. Disputes Kepler.

- Phase 1, the teacher: Borges.
- Phase 2, the external exam expert: chosen per item BY DECLARATION (design owner), never by assumption. The
  candidate declares per item: (i) whether any earlier check showed them an official answer or rubric line of
  conversation 9; (ii) whether they have opened any of the five team-channel messages in which the study lead
  listed per-question verdicts for run A. A seat clean on an item reads it. For any item the first candidate is
  not clean on, the next candidate makes the same declaration (order: Luria, Sol, Halley; Clio is out for
  run A, having done blind reads on these items). Declarations are recorded as given, never reconstructed.
- Luria's declaration (2026-11-17), recorded as given and with her caveat: (ii) none of the five messages
  opened; (i) no official answer or rubric line of any of Q1-Q20 seen, to her knowledge. CAVEAT: on 2026-11-16
  she read conversation 9's exchanges 1-45 and a set of 85 team-written questions with key facts (written by the
  team, not BEAM's items), so she knows that content for every item whose answer lies there; she cannot say
  which items those are without seeing the official ones. She asked to be over-routed rather than assumed fit.
- RULED (design owner, 2026-11-17): Luria is fit on all 20 and nothing routes to the next candidate. Her caveat
  is knowledge of the source, which every reader's packet carries anyway, not of the key's framing or of earlier
  judgements. It is published with the result. Logged beside it, per item: whether the item's evidence lies
  inside exchanges 1-45 (her prior familiarity) or outside, so agreement and minutes can be compared between the
  two afterwards.
- Key holder (runs import, draw, packet2 and map; holds both seeds; reviews no item): Aleph, on the conditions in
  the next section. The design owner rules on disputes and talks to every seat, so he does not hold the letters.
- Phase 3, the district official: the project lead.

## The key holder's conditions (Aleph, 2026-11-17; part of this pre-log)

1. Order: import with a fresh secret import seed, commit the opaque item-id list, then the seeded draw (N_DRAW =
   3, or all if fewer are eligible) from a drand round the key holder announces in this log before it exists,
   all BEFORE any phase-1 record. Then packet2, then map after each phase-2 record. The key holder refuses to
   run the draw if any phase-1 record exists.
2. Heads: nothing runs until pull request 7 has had its peer read and this pre-log is committed with exact heads;
   operations run only from those heads, and each operation's output line carries the head it ran on.
3. The committed pre-log is the one the key holder reads whole before step 1 (by repository commit).
4. Secrets: both seeds come from Python's `secrets` module on the key holder's seat and never appear in a
   message, the repository or a shared file until reveal. Letter keys are revealed per item, with the time, once
   that item is settled, never before. (For the hash rule on seeds and keys, see Custody, A1.)
5. The key holder's exposure, as given: read BEAM's scoring code at b2da22ea (judge prompts, no rubric content)
   and peer-read pull requests 5 and 6; has not knowingly seen any official answer or rubric line of
   conversation 9; as far as known has not opened the five messages named above.
6. Log: this file. Each seat appends its own operation lines by its own commit (author = the seat), never
   relayed.

## Public repository and benchmark text (design owner, 2026-11-17)

Phase records quote conversation 9 verbatim (facts with message ids), and packets contain the whole chat. This
repository is public; benchmark text is published only after a scrub and under the dataset's licence
(PROVENANCE.md). So the per-phase commit, which is the order witness, commits a hash MANIFEST, not the files:

1. One manifest per phase, listing every file of that phase with its sha256, plus the manifest's own sha256 in
   the commit, so a missing or added file is visible later, not only a changed one.
2. Two holders for every file, byte-exact, transferred by private means only, never through a shared path.
3. No phase-1 file and no key file anywhere the phase-2 reader can read.

## Custody (security seat, Zephyr, 2026-11-17)

Transfer: the sender states the plaintext sha256 first (see A1 for the exception); the recipient generates a
keypair locally (the private half never leaves that seat) and publishes the public key and its full fingerprint
on two channels; the file is encrypted to that one key and the ciphertext sha256 stated; only ciphertext may sit
in any shared place; verification is by the decryption receipt, never by a fingerprint comparison; both
fingerprints, the ciphertext hashes and each receipt are recorded in this log.

Three amendments, none optional:
- A1. Documents may have a public plaintext sha256 in a manifest. SEEDS AND LETTER KEYS NEVER (a small candidate
  space makes the hash a confirmation oracle): for those only the ciphertext hash is public, and the plaintext
  hash is stated inside the encrypted bundle or after the secret is retired.
- A2. At rest: decrypt into a directory of mode 0700 with files of mode 0600, and verify with the platform's ACL
  reader that no entry names another principal (chmod does not remove an ACL). Denial at the final directory is
  the boundary. It is measured again after the files land; ancestors are checked for any ACL entry that grants
  more than the mode; no copy sits on a readable path, in a synced or backed-up location, or under a temporary
  path (an earlier transfer on this team lost files and a key to a temporary-folder sweep). Accepted and named:
  other seats on the same host can see the directory's name and modification time, a timing signal, not content.
- A3. Phase-1 records are held by their author and the key holder. KEY FILES (seeds, letter keys) are held by the
  key holder plus a NON-PARTICIPANT, never the phase-2 reader and never the phase-1 author (either could
  unblind); a sealed copy, kept encrypted to the non-participant's own key and not decrypted, is acceptable.

Residual risk, stated: keys without a passphrase protect nothing against a process running as the same account;
the isolation between seats is the account boundary, not the encryption. Host administrators can read files on
their host; none of them is a phase-2 reader.

Where files live: phase-1 records with the phase-1 author under A2; items, grades, seeds, keys and packets with
the key holder; phase-2 records with the reader, copied to the key holder; the sealed key copy with the
non-participant. All are published at the end only under PROVENANCE.md's terms. Every outcome, judgement label,
minute count and guess goes into this log as plain lines without quotes.

## Procedure (the draw precedes phase 1)

1. Import (key holder): import-turns and import-beam with a fresh secret import seed; commit the opaque item-id
   list to this log BEFORE the letter draw.
2. Draw (key holder), before any phase-1 record exists: `draw` from the items not in set (a), with the logged
   N_DRAW and the pre-announced drand round; commit the draw record.
3. Phase 1 (Borges): one record per item with judgement, fuller answer where needed, and facts with verbatim
   quotes and message ids, including facts against my own ruling. Commit the phase-1 manifest before any
   phase-2 packet leaves the key holder. Set (b) is formed from these records.
4. Phase 2 (reader): packets from packet2 (letters seeded per item). Criterion items run 2a, then the export
   record, then 2b. The reader records the arm guess at the end of 2a, before the reveal. Commit the phase-2
   manifest after phase 2.
5. Map (key holder): re-key only items whose phase-2 record is in; reveal key files only into this log, with
   times, and only for settled items.
6. Phase 3 (the project lead): export-phase3 packets; he rules on the quoted fact list. Each packet asks him, in
   one line, for the minutes he spent. When phases 1 and 2 are committed, the study lead gives the design owner
   the count of phase-3 items, and the design owner puts one request to the project lead with that number.
   Items wait as "pending" if he is unavailable.

## Measures, logged per item and per phase

- Minutes spent (each record's minutes_spent), for the project lead's load estimate.
- Phase-2 guess rates: which answer is official (answer-type items only) and which arm. Both reported beside
  chance.
- Agreement phase 1 vs phase 2, answer by answer, per the principles' definition.
- Count of 2a records superseded after the export (forced to phase 3), with reasons.
- How well the "Cited messages: not shown for this item" line predicts the item kind (design owner's note on
  pull request 6).
- The project lead's minutes per phase-3 item, as he reports them.
- Leak checks run on every packet before it is sent: no criterion text, category, rubric line, either seed,
  question number, or official marker. The result is logged.

## Disclosures (published with the result)

- Phase 1 is not fresh: I have read run A's items, the official answers, the rubric and the categories, and
  argued several (Q1, Q3, Q4, Q5, Q12) with teammates. Phases 2 and 3 exist to check me.
- All reviewers belong to the team under test. The procedure reduces our bias; it does not make the adjusted
  column independent. The dispute invitation stands.
- Evaluator defects (the official judge never sees the question; the Q3 finding) never enter the adjusted
  column.
- The four criterion items carry only the agent's answer (single-arm), so phase 2 sees no A/B comparison for
  them, and the log says so per item.

## Heads (read from GitHub on 2026-11-17, immediately before this commit)

- Principles v0.1: main at e4867ed996ebccf4ced74d52e293f765e1f39b40 (pull request 5's merge).
- Principles v0.2 draft: pull request 6 head 5d1341460cc641c28f576649c7a95668f3e3fa2c (carries the hash-manifest
  sentence the design owner asked for).
- Tool: pull request 7 head e5f0f26ed39ad81e4594dee09f17453e93628534 (peer-approved at this head).
- This log's base: study branch at e35467f2b041faccc3ca1a53184365b284bfa102.

If either pull request's head moves before phase 1 starts, this pre-log is re-read and re-committed first.

## Stop rules

- Any packet failing a leak check is not sent; the build is fixed and the check re-run, with the failure logged.
- A seat exposed to an item's gold before its phase-2 read is replaced for that item, logged.
