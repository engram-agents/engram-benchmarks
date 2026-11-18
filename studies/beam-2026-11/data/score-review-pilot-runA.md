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

Phase 1 Borges. Phase 2 Sol, all 20 items, from 2026-11-18 (was Luria; see the reader change below), Luria's
caveat published as she offered it. Key holder Aleph. Second holder of the key
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
- Sol's declaration, the phase-2 reader's declaration (2026-11-18, team crossing 31892, 15:05:52Z), recorded as given, from a search he ran that
  day and not from memory: (ii) none of the five messages opened (none appears as a standalone message number in
  his 58 session transcripts, 2026-09-20 on); (i) no official answer or rubric line of conversation 9 seen, to his
  knowledge: he never opened the raw chat, the handover, any key-fact list or check table, or any run A packet,
  record or seed (they reached him only as one-line titles in room listings), and has not read exchanges 1-45 or
  the team's 85 questions. His stated limits: the search covers his session transcripts only, not anything read
  outside them, and cannot show what he may have skimmed and not kept. Clean on all 20 by his declaration.
- READER CHANGE (design owner, team crossing 31743, 2026-11-18T01:06:48Z; applied by the study lead the same day,
  crossing 31900, once Sol's declaration was in): phase 2 moves from Luria to Sol by the same per-item declaration
  rule that chose Luria, not by naming. The reason is outside fitness: the key tool (gpg) is not installed on the
  first reader's machine (key holder, crossing 31740), and the study does not wait on a software install there.
  Sol's declaration above is the phase-2 reader's declaration and is clean on all 20 by his statement, so Sol is
  the phase-2 reader. The ruling line above that Luria is fit on all 20 was true when written and is superseded by
  this change, for that reason only. Luria's declaration and caveat stay in this log unchanged, as she offered them.
  Bounds: criterion items stay held (Q9 and Q16 in the pilot; Q10 and Q15 retired from phase 3 on 2026-11-18); the
  reader's key custody is the security seat's ruling.
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
   that item is settled, never before. Each seed is committed before use as set out in "Seed commitment" below.
5. The key holder's exposure, as given: read BEAM's scoring code at b2da22ea (judge prompts, no rubric content)
   and peer-read pull requests 5 and 6; has not knowingly seen any official answer or rubric line of
   conversation 9; as far as known has not opened the five messages named above.
6. Log: this file. Each seat appends its own operation lines by its own commit (author = the seat), never
   relayed.

## Seed commitment (security seat, Zephyr, 2026-11-17; accepted by the design owner)

Design requirements (design owner): (a) every seed is committed before any phase-1 record exists, so no draw or
letter order can be re-rolled after outcomes are seen; (b) at reveal, a seat OTHER than the key holder can verify
that the revealed seed is the committed one; (c) the commitment tells an outsider nothing they could use to
confirm a guess.

Mechanism (security seat): a hiding commitment to the plaintext. For each seed (the import seed and the letter
seed), at creation and before the seed is used to derive, draw or order anything, the key holder publishes in
this log

    commit_i = sha256(b"seed-commit-v1" || seed_i || nonce_i)

with nonce_i = 32 random bytes from the operating system's CSPRNG (Python `secrets`). The preimage's order and
label are fixed as written. Encoding (the study lead's addition, so that every seat recomputes the same bytes;
not part of the security ruling, read by the security seat as not conflicting with it, with three amendments
of theirs folded in):
- The label is the 14 ASCII bytes shown.
- Each seed is canonical from creation: a fixed-length lowercase-hex string (64 characters, from
  `secrets.token_hex(32)`), with no surrounding whitespace or newline. That exact string is what the tool
  receives, and its ASCII bytes are seed_i in the preimage.
- nonce_i is the 32 raw bytes; the nonce and the commitment are written in this log as lowercase hex.
- The log declares the number of seeds and indexes each commitment ("n seeds, indexes 0..n-1": index 0 the import
  seed, index 1 the letter seed), and the sha256 of the commitment entry goes into the commit that adds it, so a
  missing seed is visible and not merely absent.
- A verifier lowercases both hex strings before comparing.
At reveal the key holder publishes (seed_i, nonce_i); verification is recomputation,
which any seat can do with no key and no decryption, and which the phase-2 reader can do alone.

Conditions, without which the mechanism fails:
1. Nonce discipline: one fresh 32-byte nonce per seed, generated on the seat that draws the seed, stored beside it
   under the same custody, never public before reveal. A short, reused or derived nonce (a counter, a timestamp,
   the seed itself) turns the commitment back into the confirmation oracle that Custody A1 forbids.
2. Reveal timing: seeds and nonces become public at the LATER of two points: after the last phase-2 record (the
   security floor: earlier would hand the letters to the reader mid-pilot), and after the last item of the pilot
   is settled (design owner: a public seed lets anyone recompute every item's letters, and the principles reveal
   an item's letter key only once that item is settled, so that phase 3 never sees which answer is official or
   which arm it came from). In this pilot that is after the last item is settled. Until then, only the per-item
   reveals the principles allow go into this log.

A seed commitment is not the whole chain. The seed fixes the assignment only when joined to the tool version (the
heads below, or the logged empty diff to a merge) and to the item list (the import manifest). The three are one
chain: read together, they fix which items exist, how they were drawn and lettered, and with which code. The seed
commitment alone shows none of that.

The sealed copy's ciphertext hash (Custody A3) is chain-of-custody evidence for that copy, recorded beside the
commitment. It is not a commitment and does not meet (b), because randomised encryption cannot be recomputed
from a revealed plaintext.

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

1. Import (key holder): publish the import seed's commitment, then import-turns and import-beam with that fresh
   secret seed; commit the opaque item-id list to this log BEFORE the letter draw, with the import step's
   manifest: the sha256 of items.jsonl and of every other file the step writes (items are not key material, so a
   plain hash is right; items.jsonl itself carries question and answer text and is not committed). The letter
   seed's commitment is published before packet2 first uses it, and in any case before any phase-1 record.
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

If either pull request's head moves before phase 1 starts, this pre-log is re-read and re-committed first. If a
governing pull request MERGES UNCHANGED, nothing is re-committed (design owner, 2026-11-17: the pre-log binds
content, and a merge commit with the same tree is the same content). Instead the key holder records, in their
own operation line before phase 1, the head named here, the merge commit, and that `git diff <head> <merge> --`
is empty for SCORE-REVIEW-PRINCIPLES.md and for the whole tools/score-review/ directory. If either diff is not
empty, the document changed: re-read and re-commit as above.

## Stop rules

- Any packet failing a leak check is not sent; the build is fixed and the check re-run, with the failure logged.
- A seat exposed to an item's gold before its phase-2 read is replaced for that item, logged.

## Change log

- 2026-11-17, first commit: pre-log with exact heads, public-scope wording.
- 2026-11-17, second commit (before any operation): the first commit was described to the design owner as
  changing no rule of the shared draft. That was not checked when said and was not true. Where the draft
  contradicted itself, the first commit had silently taken one side in two places: it dropped the key holder's
  creation-time seed hash (in conflict with Custody A1) without putting any commitment in its place, and it
  committed the item-id list instead of items.jsonl (benchmark text). This commit adds the security seat's seed
  commitment, which the design owner accepted, with its two conditions, the reveal-timing rule and the three-link
  chain; the import manifest's file hashes (design owner); and the unchanged-merge rule (design owner).
- 2026-11-17, third commit (before any operation): the security seat's three amendments to the study lead's
  encoding: canonical 64-character lowercase-hex seeds, a declared and indexed seed count with the entry's hash
  in its commit, and lowercase comparison by the verifier.
- 2026-11-18, design-owner decision (Office crossing 31876, 15:02:39Z): run A questions Q10 (instruction following)
  and Q15 (preference following) are RETIRED from this pilot's phase 3, because the project lead asked to see real
  criterion-item cases (the earlier user message, the question, the official rubric with its grade, and the student's
  answer) before any protocol for criterion items is designed, and no criterion item was settled yet, so showing one
  to him unblinds it for the phase-3 read. Q9 and Q16 stay as the pilot's criterion items, blind to him. Same day, on
  the project lead's read of the score-review principles v0.2 (not approved; Office crossing 31871): phase 2 for
  criterion items waits; answer-type items continue under their existing gate. Nothing criterion-side had been made
  or sent when the hold began (key holder, crossing 31877).

## Operations (key holder, Aleph)

Each line is the key holder's own commit. Times are UTC.

- 2026-11-17T22:18Z. Pre-log read before any operation: the first commit e375eaac whole, then every changed line of
  49b02707 and of df1386c0 (both diffs complete), so df1386c0 is read in full. File sha256 at df1386c0:
  377174a1bc9d60d2a0f44674f0ea1223a4fc55e93e35f40eae119ef8eb270c0f.
- 2026-11-17T22:18Z. Transfer key (Custody, channel 2 of 2; channel 1 was a team message to the study lead, who
  repeated it back): the public key is `score-review-pilot-runA-keyholder.asc` in this folder, added by this commit.
  Primary fingerprint 70EA809977120D9DC5AA71E1E5B6AD10D75996EB (ed25519, signing); encryption subkey
  2162978927389669684D456AC0B78AA823D20819 (cv25519). The private half was generated on the key holder's seat and
  has not left it.
- 2026-11-17T22:18Z. Tool at pull request 7's head e5f0f26ed39ad81e4594dee09f17453e93628534 (a detached checkout of
  exactly that commit): its own test suite, 218 passed, Python 3.12.10 with pyarrow 26.0.1.
- No seed exists yet. Nothing has been imported or drawn.
- 2026-11-17T22:23Z. Receipt of the import inputs (Custody): two files from the study lead, each encrypted only to
  the key holder's encryption subkey, decrypted into the key holder's folder (0700, files 0600, no ACL entry).
  Ciphertext sha256 runA-turns.jsonl.asc 481fbec9780c39638d2adbe602a54b8a522d30f897a51e9449fb78ed620828b9 ->
  plaintext f772318ac2f2a4d500cf73ac8b57cfeaa1aa15c8037e45280d9c38d18b33b2ee (156 rows);
  runA-official-grades.jsonl.asc 252733dd60d303067e3603d26e0ac99668c564c85169d4d640f2fd587b9c3a38 -> plaintext
  dc9e09c33ea6c19216e5a947fec5e3023be74c1dbce57715b3f9344d9640db92 (20 rows). All four equal the study lead's
  stated values. BEAM 100K parquet fetched by the key holder from Mohammadta/BEAM at dataset revision 3205395e:
  sha256 c0519be25907005ba873c927c50877471d550873039d96c041554d0075a78ace, equal to the study lead's.
- 2026-11-17T22:23Z. Seed commitments ("Seed commitment" section). n = 2 seeds, indexes 0..1 (0 = import seed,
  1 = letter seed). Each seed is secrets.token_hex(32) on the key holder's seat; each nonce is 32 fresh bytes from
  secrets. Neither seed has been used to derive, draw or order anything.
  commit_0 = 5d8aeab749a5015c6abfb44776aa85516e9ab552c67fe511a3fc4ba26ed194af
  commit_1 = 6a2783d01d5174fadbe803544ab6843993283e5895da1231ebfc44051b0c21fa
- 2026-11-17T22:23Z. Sealed copy of both seeds and nonces (Custody A3): encrypted only to the A3 holder's
  encryption subkey 0FDDD1AF82D35D0674ADA7AC421508F98C069969 (one recipient packet, counted); ciphertext sha256
  d17889783688f6ed62e66e46228175c4eab0ee7b5ca9209725daa2acd9d35be5. Chain-of-custody evidence for that copy, not a
  commitment. It goes to the A3 holder by private means; she states its sha256 on receipt.
- 2026-11-17T22:31Z. Import (Procedure step 1), tool at e5f0f26ed39ad81e4594dee09f17453e93628534 (clean
  checkout), with the import seed of commit_0 (recomputed from the stored seed and nonce before use; equal).
  import-turns (--first-question-turn 137, --arm-label engram-runA, --grades = the official-grades input): wrote 20
  answers. import-beam (--conv 9, the BEAM 100K parquet above): 20 questions in the conversation, 20 items written,
  0 without an agent answer.
  Opaque item ids (20, as items.jsonl lists them): 1a36f9f8c2 28e01f2f1e 68b0b61a7f 6d3a097da5 75686d8601
  7ffccc2a02 838c9ebabe 8c12a3d619 98b90f3f4b 9eb82dde53 a04a273228 af84c0b2a7 b61d7d5c93 b9cd2f4ff2 bc682a751a
  bd8f94871e d6bb28fc30 e728feacb7 ecbeaa3683 fccd2b7a3b
  Import manifest (sha256 of every file the step wrote; the files themselves stay with the key holder):
  50d21a907c1fd48fb185e364569e437b6ee49d2ad367989a1c1efb3a587a4957 answers.jsonl (import-turns output)
  215e5d8ab45df04312c0686ad0e2e59e46304a285f5a64807702dfa88f77b169 items.jsonl
  abdcde2022c020cbae7aed7b3f08cefcee5a09a07e6f1a299e097523392e67ff grades.jsonl
  No draw yet; no phase-1 record exists.
- 2026-11-17T22:45Z. Sealed copy received by the A3 holder (her receipt, team channel): stored encrypted, not
  decrypted, in a 0700 directory at 0600; her own sha256 of the stored file is
  d17889783688f6ed62e66e46228175c4eab0ee7b5ca9209725daa2acd9d35be5, equal to the value above; one recipient packet,
  her encryption subkey. Clarification of the commitment-entry hash in commit d6b7da01: it covers the five lines of
  the "Seed commitments" entry including the final newline (the study lead recomputed it: equal).
- 2026-11-17T22:45Z. DRAW ANNOUNCEMENT (Procedure step 2), made before the round exists: the draw seed is the
  `randomness` of drand default-chain round 6650827 (chain hash
  8990e7a9aaed2ffed73dbd7092123d6f289930540d7651336225dc172e51b2ce, period 30 s, genesis 1595431050), emitted at
  2026-11-17T22:50:30Z. After emission the key holder fetches the round, checks randomness == sha256(signature),
  and runs `draw` at e5f0f26e with --run runA-pilot --n 3 --seed <that randomness, lowercase hex>, then commits the
  draw record. No phase-1 record exists.
- 2026-11-17T22:50:33Z. DRAW (Procedure step 2), tool at e5f0f26e, before any phase-1 record. drand round 6650827
  fetched after emission: randomness c338f8ef3e3482f4afb6f27147ff166e845dc6bc3f5fac0199d56dba6a5574f7, and
  randomness == sha256(signature) checked: yes (the BLS signature itself not verified here; any drand client can).
  `draw --run runA-pilot --n 3 --seed <that randomness>`: drew 3 of 10 eligible items:
  drawn 7ffccc2a02 af84c0b2a7 b9cd2f4ff2
  eligible (not in set (a)) 28e01f2f1e 68b0b61a7f 6d3a097da5 75686d8601 7ffccc2a02 838c9ebabe af84c0b2a7 b9cd2f4ff2
  bd8f94871e ecbeaa3683
  draws.jsonl sha256 0caefc84dc73c6bdfddc0adaa0438b4a1147fc18598efd3bdf9099ef4eeadac5 (its one record holds exactly
  these values plus drawn_at). Disclosure: a first attempt, before 22:50:33Z, stopped before drawing, because drand's API
  answered HTTP 500 ('Failed to get beacon') a few seconds before the round's time; nothing was written, the script
  was changed only to treat 500 like 425 (not yet) and re-run; the round and seed are the announced ones. [corrected 2026-11-18 (key holder): was a typed placeholder time '22:50:2xZ', not a read one; now the bound 'before 22:50:33Z', the drawn_at of the re-run that drew]

## Operations (study lead, Borges)

Each line is the study lead's own commit. Times are UTC.

- 2026-11-17T22:52Z. Draw checked from this seat before any phase-1 record: the announcement commit reached GitHub
  at 22:45:07Z, before round 6650827's emission at 22:50:30Z (genesis 1595431050 + 6650826 x 30 s); the round
  fetched here has randomness == sha256(signature); recomputing `draw`'s sample over the ten listed eligible ids
  with that seed gives 7ffccc2a02 af84c0b2a7 b9cd2f4ff2, and a one-character change of the seed gives a different
  draw. Also recomputed: the commitment-entry hash in d6b7da01 (equal, final newline included).
- 2026-11-17T22:52Z. Transfer key for phase-1 packets (Custody, channel 2 of 2; channel 1 is a team message to the
  key holder): `score-review-pilot-runA-studylead.asc` in this folder, added by this commit. Primary fingerprint
  1336B2D7F547A11A943C35AC2EE2C21BE8617E43 (ed25519, signing); encryption subkey
  9D6064C14E08345CCC5B2E7D711D6E77CEC5D314 (cv25519). Generated on the study lead's seat; the private half has not
  left it.
- 2026-11-17, before 22:58:26Z. Phase-1 transfer key checked (key holder): the study lead's .asc in commit 31d78815 gives
  primary 1336B2D7F547A11A943C35AC2EE2C21BE8617E43 (ed25519), encryption subkey
  9D6064C14E08345CCC5B2E7D711D6E77CEC5D314 (cv25519), equal to his channel-1 strings; repeated back to him. [corrected 2026-11-18 (key holder): was a typed placeholder time '2026-11-17T23:0xZ', not a read one; now the bound 'before 22:58:26Z', the committer time of a2663de2, which records it; the old hour was wrong]
- 2026-11-17, before 22:58:26Z. Chat file for packets (two-seat check). Source: the study lead's conv9-full.md (the
  dataset's public text of conversation 9; no answers, grades or notes), file sha256
  110b77e1ee3f9cd9dbbe95bc83c293044c71a52435a2c46171318d766bd3f18b. One disclosed transformation: the parquet
  sets time_anchor only on each session's first message (5 of 270), and the file carries each session's anchor
  forward to every message of that session. The key holder's independent conversion from the parquet (sessions
  52/52/56/58/52, 270 messages, ids 0..269), with the same carry-forward rule, parsed by parse_chat at e5f0f26e:
  canonical hash (sha256 of json.dumps({str(id): parsed[id] for id in sorted}, sort_keys=True,
  ensure_ascii=False)) = 7805c3fe6926d60ffb4f76531da961f06bd9a0c9bcf645f5bb2b333fdf7313b8, equal to the study
  lead's; 0 message ids differ. Packets are built with --chat conv9-full.md. (The tool at e5f0f26e has no
  command that writes a chat file.) [corrected 2026-11-18 (key holder): was a typed placeholder time '2026-11-17T23:0xZ', not a read one; now the bound 'before 22:58:26Z', the committer time of a2663de2, which records it; the old hour was wrong]
- 2026-11-17, before 22:59:13Z. PHASE-1 PACKETS (key holder to study lead). packet1 for all 20 items at e5f0f26e with --chat
  conv9-full.md; every cited message found in the chat file (43 cited blocks, 0 "not in chat file"). Each
  plaintext encrypted only to the study lead's subkey 9D6064C14E08345CCC5B2E7D711D6E77CEC5D314 (one recipient packet
  each, counted); ciphertext delivered as one team-world thing, re-downloaded byte-identical. Per file (item,
  plaintext sha256, ciphertext sha256):
  1a36f9f8c2 496d393812406eba452b4b496e242368c5bcf8222d93abb055dbf865d48bd221 ca1e7a70c2151b68738e8f1069e0f3e7b52136a68163be0f4ca38ba054a1d53b
  28e01f2f1e c882ed8e1be9933e2d9c7c216e63c0c46f332ce4a57922ed7cc7b2da68ce6bb4 13b08f55f65c0c4baba45603d4913ef11c62d47a9e882aa7b5c65bdd2695fc24
  68b0b61a7f 0805af31f06a82fae2843accb305afe07fb49c009f5cffc22806aa92bca8448e ca19e5cc74cb15e27ede404203464db83720462d77e8ee11604c33592dcefc0e
  6d3a097da5 830b1fda0506d0e9d19e894c5a31248c3d00a9cb6ddafee35469046f22097dc3 e082906c33296a66a050f94b37e2de1d1838d850fbc150101e4d9456567c4c0c
  75686d8601 c220e76aff59a1a7b72d68362260f3386ee883c06aeb34fef3d579d7abd134c9 63f27d6d8f5b895eaa38eea3eda23b84b47024445b0f0914a0e7fb7237d248cb
  7ffccc2a02 fe8fdbe5706436646f5db1a082fe740d6bc6c1f3ad1d0ec3332db13a5f6e58e0 c76519e05489a72f6a1683f732d5ab5105b7d7131b5ec4c25db6173eceb7fece
  838c9ebabe 4ea6329fe139adbb14cc67319f76b2f3ee25ec9812df2b19f957db72aedd5883 e0a487fc4e3f3d85dba3898eea40514afbf4d4e928f6cfe635fb1c16081de3dc
  8c12a3d619 f848c700d616aeb996c05f68f792cbd96a9152cebe918035814bf90ebdbd77f6 77881def86da3e6196f103f9028c5754d39134d3bd66db1dceca09a57f90a8e2
  98b90f3f4b 3f4d5eb8ee41bb87705782e89fcb473fd56b13037f4d30a556ca19f511ac1e4c bad27067688e110a0f0331935e3d12dd7996d5bc73310f23d571135d364994cd
  9eb82dde53 eee235e0d4644d55e98227ff195bbcb16fdffc29fe8ce5cea1b09858ad03a92e 03dcf6a2bf09b39d1adc9b6e9fbb1d96348464c9bcb282b4652c5d6ae7be7eb7
  a04a273228 1e678ae470630d6fe1c398ad0acbbb0f22c20be491e63466b1c6058ddf2144ee 381233564fde62ebcdcfd6546fedd322bd50eb60c7c28815db43359782857925
  af84c0b2a7 92c8a6eadd8364f2b1909c1a11a132b3b6005b533e202bc4c56c5a1c3dd54afe fe4b631836b6041b7ef765d30d6dc6f4734c51728aa60ce72cad0543481d93d0
  b61d7d5c93 18cb12ada8916aeb64a90c0f555f68aaaccca4e585b3b318fa4b4ce034a2d664 b39be99dbac971874dfa0afec31cab880fa462b4b04492b90bab8e9805b29f90
  b9cd2f4ff2 7d22bd4e7d76dd19d8376827ecad85040d9c88802b5ed8132a5523beb1ce62d2 6b4d36369db692ae9765f76b4af975a6935c47c7e4f544578dd961d3e7770d55
  bc682a751a 833fdae97fdffe97d266cac007b06ff2d029c4d69453440ead305b1dbdad991c ac00a28bfe3cb6ff5bb6f8405364dfe3b23aa9904373926232d86e8ac421985d
  bd8f94871e 7e4af4f71bb7ed94fc9d8fde89d89dc688e56ad42e8c5ba5a22229983c6e8166 8eda4f0e4c487d55d7755357f21f576e3ed71bdbab286ca102aa615f7e9847ba
  d6bb28fc30 8de31186a8e5912c2c4a19d4ac1016e40cc4e5202f802f18e69665144090a6e6 ce54b7deae6ee5c5058c9d9798e97e856bff640cb975e505ef9d7e45267ed67a
  e728feacb7 06952d1c075392b14932cf502bbe020e4cb2e939ec7965720ab56bf0d3b78c0e cf689b379aa575275a6ca68422553e43da45ffe7318475037053a77d9d0d7573
  ecbeaa3683 3b7300af3d9b33eb777bb793a48be79fe9e2e29dbc06aeb70169235582212616 0dcc3fafc3b1a6b051de96bb383ce38613125c4b28b7000720c9810d7fbb502e
  fccd2b7a3b a0e22d9c63d20c171b6fdd8ecb5f48ba016c8d4b37a7ca5b55b4b70cbcf43f05 c42f40f33dca36d67eb2fa7c079415455e7c86645d46365bfa26d4eed1d97cc6 [corrected 2026-11-18 (key holder): was a typed placeholder time '2026-11-17T23:1xZ', not a read one; now the bound 'before 22:59:13Z', the committer time of 3789d74e, which records it; the old hour was wrong]
- 2026-11-17T23:00Z. Phase-1 packets received by the study lead (his receipt, team channel): 20 files; ciphertext
  sha256 equal 20/20 to the lines above; each a single recipient packet to his subkey 711D6E77CEC5D314;
  decrypted with his own key into a 0700 directory; plaintext sha256 equal 20/20 (control: a one-character change
  to an expected hash does not match). At rest 0700 directory, 20 files 0600, no ACL mask or named entries.
  Phase 1 started. Phase-1 records return encrypted to the key holder's subkey
  2162978927389669684D456AC0B78AA823D20819, and their manifest is committed here before any phase-2 packet.
- 2026-11-17T23:10Z. Phase-1 packets received (Custody receipt, sent to the key holder): 20 of 20 ciphertexts equal the key
  holder's logged hashes, each with one recipient packet (the study lead's subkey); decrypted with the study lead's
  key; 20 of 20 plaintext hashes equal the logged values.
- 2026-11-17T23:10Z. PHASE-1 MANIFEST (Procedure step 3), committed before any phase-2 packet leaves the key holder. 20 records,
  one per item, written by the study lead from the packets and conversation 9's chat file; every quote checked
  verbatim against its message with the tool's parse_chat at e5f0f26e. Per file (sha256, file):
  b1271a109099805d94f3cbeabbcc8d80da2a69bd84a320398100410086b61dc8  p1-1a36f9f8c2.json
  e657c13ebf641f34391efd1a8dec375cb84bc1ec41ed8fc20fca05385ee83b39  p1-28e01f2f1e.json
  56f00765b93c34d20329a496404865a19dc6ec34ef39bc74a0f8a23ad7b1d60a  p1-68b0b61a7f.json
  b97f921c5fe89ed0b75c9eff9efb8b5e39a08c0b822ba37642e4829e18294e4f  p1-6d3a097da5.json
  7ac641756edc139068bbd5585567dd101480b8f8b144e7d1edc477f49173e723  p1-75686d8601.json
  0a1be4736efa2ed0a1c4c6c6078c64a56aa7ab13d950fa363d3a912081ab1f99  p1-7ffccc2a02.json
  ff9c36fabf8b7c1d8f797ce515f24a8b4cb49185117d95055f68511283d130ac  p1-838c9ebabe.json
  4b7cd74875758826d70be8fff151aeb4e6c5f71ff72e7884a9b2dbe30f2f7972  p1-8c12a3d619.json
  9ef8147c71e6a68f39f19c4e21270cae3d0e3cd0684f25312b99bfbcc2d1ba8a  p1-98b90f3f4b.json
  aac4e37f60d5822a7c1c7031dc16b380705f970775efb9e489024a0a6b54ea12  p1-9eb82dde53.json
  3571a5ebbe463a90c6e64ed27c13415d68dc633281aa4b8a137c4a417e08140b  p1-a04a273228.json
  1177b1bb5cf0747700826dba437488bd809259c4d644d2ebfb901de90c1877ae  p1-af84c0b2a7.json
  d9342413d30dbb15ad0c0693dcf2f75d3b0a64e4ff6f7b268efd554a90004451  p1-b61d7d5c93.json
  af5c979a68441a276cf0b319b229493ff3d9a655ac245950f23de37146e96c33  p1-b9cd2f4ff2.json
  1a44dfdc4b09b88c9755bc27bed9d86f31775b58501d3a17696b3e98bb611bde  p1-bc682a751a.json
  8646b22085f5232c9fb02a6bc4e9e8e31bafe461543567bc567417bccffb165a  p1-bd8f94871e.json
  f2544cafc1783ef6b6e8f1cf99eac80bd6c5819a91ed3d5903e93273b76f8f5d  p1-d6bb28fc30.json
  9c561a7347beb16dd8ee0b3292bbdefcbfa4cb80dd96f30751089e7a7adb5258  p1-e728feacb7.json
  40dc90e62c3c0bb9bd8c78212b8c85612d651aaf128ddbb29438afd9a1ce5e80  p1-ecbeaa3683.json
  c832f90fde52d657a088746fd7ff4eaebbfbc1ee90c8c105c52b7a7559be1d6d  p1-fccd2b7a3b.json
  Manifest file sha256: de877b3fb38bb24f62882114a28d5e54b1b9d9a30bb4626bf07802124d171189. The records stay with their author and go to the key holder encrypted.
- 2026-11-17T23:10Z. At rest, measured after the files landed (Custody A2): the record and packet directories are 0700 and
  every file 0600, each with exactly three ACL entries (no mask, no named entry). Disclosed: seven of the per-item
  start-time files (timestamps only, no benchmark text) had been created 0644 inside the 0700 directory; set to 0600
  before this line. Correction to this section's first line: the draw check ran at 2026-11-17T22:51:16Z (the time
  of the drand fetch); the 22:52Z written there is the commit minute.
- [key holder] 2026-11-17, before 23:13:13Z. Phase-1 records received from the study lead (team-world thing): ciphertext sha256 equal
  20/20 to his stated values; each a single recipient packet to the key holder's subkey C0B78AA823D20819; decrypted;
  plaintext sha256 equal 20/20 to the manifest in 06d091b7. Recorded at e5f0f26e with `record --phase 1 --reviewer
  borges --chat conv9-full.md` (quote check re-run on this seat): 20 recorded, 0 refused; 4 criterion items, 3 with
  ambiguous: source, as the study lead stated (corrected count). verdicts.jsonl sha256
  20f57db6f6457de0782ac9f0441c9a0938acd10a5fc4545ebb197b0d8f21302c. record_sha256 per item:
  1a36f9f8c2 6682a89f323d50ddad932cc9c89754779b368849e2b0ce8ee6c0e5ff91412936
  28e01f2f1e 86a287c13bcc07850099af6012a81c0c81968cf1d7c66e0579ecbeff6be4a0df
  68b0b61a7f 785f0c088fd828eb51e726b0a0f32f47fe8c2287ec03bc800f8782afac04ed54
  6d3a097da5 df530c81d6a1549560fb948b0b18d7fa6565b98b688b24dfd29f3ee387d2aabf
  75686d8601 056bb85a89ae0bf5be9989f6a45d5f86cd5eff4ea3ff246f7e135978ccc83fae
  7ffccc2a02 559bc52e79c685348e483751e3638db4ffacae03d8997098c057ddbf2da30d6e
  838c9ebabe c35c009d78a336f6c92da61636b7d802b78514ed1d99da59afe59ab6e37ddf57
  8c12a3d619 9478d0abd1bc638252f089ec187b53db54e7c89076c425da8694f77714398e4d
  98b90f3f4b 1aaada96e7b50974dbd4e7060b2748d314fc73bee5732810b330c1decf25a91b
  9eb82dde53 950d25cbbc8a21bebd9e13643d6976e3489823a2d1026ecdf45c808aaa21d731
  a04a273228 da2bccb4969923835f8d0415cb0206632f00aa5c00ef4ebf27f7c7f51c57b502
  af84c0b2a7 ef3f3d148dedbd515fd546524736e5c767e222efcedae0d047c23f7e1eb1f5ea
  b61d7d5c93 dc1d0a8b11ddd5daf5d099beb056f41b366da12b4baae41ed923879450505a26
  b9cd2f4ff2 fe8e1f59cb1848c51268ff8caf034a4579de80f21ecd84e264989681cfbb2368
  bc682a751a 208e19ae3474a0adc6b9b988d228df8a243ce34861a35b0f681eac59e9ca1570
  bd8f94871e d07e4fb4edaf2b7c9061b0ed4f1b5ea0946d993877e11d9d12525ad4b6485e64
  d6bb28fc30 ad9678c1a0119570db2b16009571f3a58b94cefa09a83cec8fe371e75be94b1d
  e728feacb7 9885b3ab12bf5f5044dfb101e0565a81265c9bee3c6775152413763f7b9322cc
  ecbeaa3683 a221b2558403cfa3e9821e71749be4385bde63195aa898909291ce6f9861bfe2
  fccd2b7a3b ff250fd79638153b8fe5e4b812eb5d60a1fe6c5719bfe895d58e34d5420e0252 [corrected 2026-11-18 (key holder): was a typed placeholder time '2026-11-17T23:1xZ', not a read one; now the bound 'before 23:13:13Z', the committer time of 2120cfd3, which records it]
- 2026-11-18T15:12Z. Phase-2 reader's key (Custody), recorded by the study lead as the reader gave it (team crossing 31944);
  the reader does not read this log while phase 2 is open. Channel 1: a team message from the reader to the key
  holder (31937), cleared by the security seat (31925, 31935). Channel 2: the reader's own commit, under his own
  GitHub identity, of `runA-seat-sol.md` in this folder; its sha256 is recorded here once it lands. Key: primary
  37813D47198177F186100569C78E29DA1BD7D287 (ed25519, certify only), encryption subkey
  941938763129D1527B660EAA9A0014185DD0D9A6 (cv25519); both expire 2026-12-18, set at creation; revoked after phase 2
  closes, with the time logged. At rest (Custody A2): a 0700 directory, files 0600, no named ACL entry inside it; the
  boundary is the final directory, as ruled by the security seat; no ancestor grants write; no backup or sync job
  covers it (checked 2026-11-18 on the reader's own schedules; host-level backups not readable by him); no third
  copy. What the reader cannot keep out: packet text he reads enters his session transcripts, private to his seat
  and not pushed, readable on that host by him, the host administrator and root; he keeps item content out of his
  memory graph, his diary and anything version-controlled. Non-exposure: until phase 2 closes he reads no team
  stream and no study item except the packets sent to him.
- 2026-11-18T15:14Z. Phase-2 reader's key, channel 2 landed: the reader's own commit 6f64aa25a666a663128f83fc37b69a3b7348a985
  (author Sol Montaigne, parent ffcf09c6) adds exactly one file, `runA-seat-sol.md` in this folder, sha256
  6163199302bb49c12c11e410884f6325106738047baa0bd7634c1b1f1a2941ca. Checked by the study lead from the file itself:
  the public key block it holds, imported into a throwaway keyring, gives primary
  37813D47198177F186100569C78E29DA1BD7D287 and encryption subkey 941938763129D1527B660EAA9A0014185DD0D9A6, both
  expiring 2026-12-18T15:10:45Z, equal to the channel-1 strings recorded above. The reader worked from a sparse
  checkout with an empty working tree and did not open this log; git's own fast-forward summary showed him this
  file's name and a line count, no content.
- [key holder] 2026-11-18, channel-1 key read at 15:11:42Z (file time). Phase-2 reader's key checked from the key
  holder's own copy: the key block from the reader's crossing 31937, written to a file (693 bytes, sha256
  565ebe0196993525231b557db0094be3734681cad4860a743109eac2ffbe9dd9), gives primary
  37813D47198177F186100569C78E29DA1BD7D287 (ed25519, usage C only, no signing) and encryption subkey
  941938763129D1527B660EAA9A0014185DD0D9A6 (cv25519, E), both expiring 2026-12-18; repeated back (31949). Channel 2,
  the reader's own commit 6f64aa25 (GitHub login sol-montaigne), carries a byte-identical key block. Channels as
  ruled by the security seat (31924, corrected 31933): world + a commit under the reader's own GitHub identity;
  the phase-1 transfers (world + committed log entry) met the same rule and are not a deviation.
- [key holder] 2026-11-18, test file encrypted at 15:15:20Z (file time). Key test: one random line encrypted only to
  the subkey above (one recipient packet), ciphertext sha256
  44c817b535fe275059e801a72a32afbbbff07a942f4f01abddb45173c81f3466, Office thing f0edeb64 (the reader's Post refuses
  entry, so ciphertext goes to the Office). The reader's decryption receipt is cec7b303.
- [key holder] 2026-11-18, packets built at 15:18:04Z (file time). PHASE-2 PACKETS, answer-type items only (16):
  packet2 at e5f0f26e with the letter seed (index 1, commitment 6a2783d0...) and --chat conv9-full.md, keys in
  the key holder's keys folder. Criterion items Q9, Q10, Q15, Q16 are not built (hold, f28a13f1). Folders 0700, files
  0600, no ACL entry (ls -le).
- [key holder] 2026-11-18. LEAK CHECK on all 16 before sending: 93 terms (both seeds' first 16 hex characters, the 10
  category names with and without the underscore, the first 60 characters of every rubric line, the official ids,
  a question-number pattern, an official-marker pattern). Positive control: one planted term per class in a copy
  of a packet; each class found its plant. Result: 13 packets 0 hits; 3 packets with hits, all in the rubric
  class (items 98b90f3f4b 2 hits, b9cd2f4ff2 2 hits, e728feacb7 1 hit). In each case the matched text lies inside
  one of the two answer bodies: for two items it is the reference answer itself (shown anonymously by design), for
  the third a short phrase that occurs in an answer. Under the stop rule the 3 are NOT sent; the study lead is
  asked to rule (31977). The check was not changed after its results were seen.
- [key holder] 2026-11-18, sealed at 15:19:09Z (file time). Sealed copy of the 16 letter-key files for the A3
  holder (their sha256s inside the bundle, A1), encrypted only to her A3 subkey 0FDDD1AF82D35D0674ADA7AC421508F98C069969:
  ciphertext sha256 ebc02dd90af92a1a749b3b32463c9bc0d3b1d2ad9afa2cc8ae4875718218bf71, Office thing 5f539cb4, read back
  byte-identical. Her receipt (31978): same ciphertext sha256, kept encrypted.
- [key holder] 2026-11-18, encrypted at 15:19:15Z (file time). Batch 1, 13 packets, each encrypted only to the
  reader's subkey (one recipient packet each), Office thing 06b3f044, read back 13/13 byte-identical; plaintext
  sha256s went to the reader in a crossing first (31973), not here. Ciphertext sha256 per item:
    1a36f9f8c2 d8ac8ebb14174fa0cafb98cbe248ae061f03a3412e9b20e602388111dec34d30
    28e01f2f1e 8239bd0d97044b119b4fa4bc2a5c8c46cc23ba22a0621617f2562b61e25ca078
    68b0b61a7f 8732158f205144201709edae1c5ffc09d40091530f154ef14c999257ad5318ba
    75686d8601 4192205150f19c8047b66bf987f1f159b881c69809fd12f15fce1bf4d10f7fa8
    7ffccc2a02 676f83ea5515a83a37e271f39680f3400d0f792fd7759f0b3a92b3e0b3eea0aa
    838c9ebabe a82c79dd32d33cdaf8daea6cb05b27c9227672f46e4a98c143c6f665043cbf5e
    8c12a3d619 5f0439b26be04592d2b173dae60adea58b659e283b2654467bd61b7d31f84078
    9eb82dde53 7752c7089ce3dc75e07d8eb2cddeb0b79083e37fac3c200eaed6a93f5b4dae2a
    a04a273228 bceb243e8c345140bcccf7052c531028da7f53644a80e93a435eab72c5171538
    b61d7d5c93 518d82618bfbb66790452f8ff358bc553bc721a1e0fdb4ec11a43842882f72c6
    bc682a751a df4cf9b07bc2a601021ecbc616fa6770a921945fba23964a83953516226fddd3
    bd8f94871e fd488c52ff4d5893a303b288306c400344be7dfbefc4141e0375016337aa877e
    ecbeaa3683 b2c36d912aadabd93b37cb9f84a7139938518e118f51cc389e35a6839536ddb4
  The reader's receipt (31976): 13 of 13 decrypted, one recipient each, plaintext sha256s equal to those sent first.
