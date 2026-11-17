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
  these values plus drawn_at). Disclosure: a first attempt at 22:50:2xZ stopped before drawing, because drand's API
  answered HTTP 500 ('Failed to get beacon') a few seconds before the round's time; nothing was written, the script
  was changed only to treat 500 like 425 (not yet) and re-run; the round and seed are the announced ones.

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
- 2026-11-17T23:0xZ. Phase-1 transfer key checked (key holder): the study lead's .asc in commit 31d78815 gives
  primary 1336B2D7F547A11A943C35AC2EE2C21BE8617E43 (ed25519), encryption subkey
  9D6064C14E08345CCC5B2E7D711D6E77CEC5D314 (cv25519), equal to his channel-1 strings; repeated back to him.
- 2026-11-17T23:0xZ. Chat file for packets (two-seat check). Source: the study lead's conv9-full.md (the
  dataset's public text of conversation 9; no answers, grades or notes), file sha256
  110b77e1ee3f9cd9dbbe95bc83c293044c71a52435a2c46171318d766bd3f18b. One disclosed transformation: the parquet
  sets time_anchor only on each session's first message (5 of 270), and the file carries each session's anchor
  forward to every message of that session. The key holder's independent conversion from the parquet (sessions
  52/52/56/58/52, 270 messages, ids 0..269), with the same carry-forward rule, parsed by parse_chat at e5f0f26e:
  canonical hash (sha256 of json.dumps({str(id): parsed[id] for id in sorted}, sort_keys=True,
  ensure_ascii=False)) = 7805c3fe6926d60ffb4f76531da961f06bd9a0c9bcf645f5bb2b333fdf7313b8, equal to the study
  lead's; 0 message ids differ. Packets are built with --chat conv9-full.md. (The tool at e5f0f26e has no
  command that writes a chat file.)
