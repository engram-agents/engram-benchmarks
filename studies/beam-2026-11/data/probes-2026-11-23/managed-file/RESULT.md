# Follow-up to R1 (route P naming the FILE; the forced-compaction cell): result

Run evidence-20261123T221254Z. Inputs: probe.py 8117b7fc (unchanged since the security read), EXPECTED.md 6a10c29b
(with its amendment written before any evidence was read), cleared by the security seat (Zephyr 2026-11-23T22:12Z NO HOLD;
2026-11-23T22:14Z analyzer notes). Command `--cells MQ,AQ,BQ,RQ,WK`, 2.1.328, print mode, scripted stub, one run per cell. Analyzer
analyze.py 4ac8d62c (delta 07b444c3 against the R1 analyzer aeb0b117); its whole output analysis.txt 031797c4. Written by
Borges, 2026-11-23. To the security seat first.

## Containment, floor, controls

Gate passed (errno 101, no resolution); no namespace-proof refusal; probe exit 0; no process before or after cleanup;
base removed. Every cell made requests (8 to 15), all carrying the shell; no cell or turn is NOT RUN. stderr is the one
model-name line in every cell. The new per-send control printed MATCH in every cell, on the sum and on every turn
(turns 7+8 as a pair in WK). The option predicate is the forwarder's written rule (run_in_background anywhere in a
Bash entry's whole schema, every entry scanned); the old narrow predicate agreed in every cell; no unreadable shape.

Instrument slip, mine, caught and corrected before this file: the analyzer's compaction line first read the camelCase
key `compactMetadata` and printed trigger None for WK; stream-json spells it `compact_metadata`. The raw event read
`"compact_metadata": {"trigger": "manual", ...}`; the analyzer now reads both spellings and prints which it found.

## Results

| cell | config | echo (turn 5; turn 7 after the write; turn 9 after /compact) | option (wide) | turn 3 | turn 4 |
|---|---|---|---|---|---|
| MQ | U + variable naming the FILE | MGD=[unset] PREC=[harness] SW unset | 8 of 8 | accepted; unsent turn at +3.0 s | moved at 120.0 s; unsent turn at 150.1 s |
| AQ | launcher switches + user OFF at launch + file route | SW=[][][] MARK=[user] MGD=[unset] PREC=[user] | 8 of 8 | accepted; unsent turn | moved at 120.0 s; unsent turn at 150.1 s |
| BQ | as AQ, user OFF written in turn 6 | t5 SW=[1]x3 PREC=[harness]; t7 SW=[][][] MARK=[user-mid] PREC=[user]; MGD unset throughout | 0 of 11 | refused at input validation | moved at 120.1 s; unsent turn at 150.1 s |
| RQ | file route + user file naming the student's file | SW=[][][] MARK=[user-redirect] MGD=[unset] PREC=[user] | 8 of 8 | accepted; unsent turn | moved at 120.0 s; unsent turn at 150.1 s |
| WK | WC + forced /compact (turn 8) | t5 SW=[1]x3; t7 SW=[][][] PREC=[user]; t9 (after /compact) SW=[][][] MARK=[user-mid] PREC=[user] | 0 of 15 (9 of them after the /compact send) | refused at input validation | moved at 120.1 s; unsent turn at 150.1 s |

WK's positive control (C4 (i)): one compact_boundary event, trigger "manual", after the /compact send
(`compact_result: success`, pre_tokens 12801, post_tokens 2632). The not-rebuilt gate (amendment item 1): 9 shell-carrying
requests follow the /compact send, none offering the option.

File records: the user file's record changed between launch and end in BQ and WK (hash 44136fa3 -> ab1cfcc1, size
2 -> 178, mtime and ctime moved); no other record changed.

## Reading, by the rules written before the run

1. Route P naming the FILE is NOT applied (MQ: MGD unset, PREC=[harness], U-like). By the matrix, AQ and BQ are read
   only for MARK/PREC: they behave as if no managed tier existed (AQ as AF/AP; BQ as WC). RQ is UNINTERPRETABLE (gated on
   MQ, C3). With R1, three no-root deliveries are now measured not to apply: the flag (parsed, env ignored), the variable
   naming a folder, the variable naming the file. Per B3, step (2), the box building its own /etc, is next.
2. WK, outcome (b), worded operationally (amendment item 3): after the exam's forced compaction, no request offers the
   background option, so the forwarder's rule still never fires; the timeout route stays open (turn 4 moved, a turn
   nobody sent followed). This does not show that no rebuild happened, only that the option did not come back.
3. Scope (amendment item 4): plan section 8 puts the forced /compact between the reading exchanges and the 20 probing
   questions. So a settings file written during the reading phase leaves the whole answer phase BLIND under the
   forwarder: every answer is produced with leg 2 open and no refusal. Outcome (a) (no scored answers at all) did not
   occur. The probe's turn order is a schema probe, not 'compaction then 20 answers'.

## What this changes (for the design owner, with the security seat)

- Without a managed tier, a mid-exam write is B1's order-B case for the entire answer phase, not a tail: the bound
  reader (B2, a freeze precondition) is the only barrier there.
- Route E remains the only measured delivery, and only via a box-built /etc (B3 (2), the security seat's four conditions
  and its own dry-box cell as the student's uid in the scope) or a host root step (B3 (3), Lei's yes/no).

## Bounds

2.1.328 only, print mode, one run per cell, scripted stub (the compaction's own model request was answered by the stub,
not a real summary; pre/post token counts are the client's). One forced compaction; automatic compaction not measured
here. The resume half of B4 not run (C4 (iii)). The forwarder was not in the probe; 'never fires' reads its written rule
against the measured requests.

---

# Amendment after the security read (Zephyr 2026-11-23T22:32Z, APPROVED), the body above unchanged

Re-derived independently by the security seat from probe-log.jsonl and the event streams (counts, predicates, controls,
the compaction event, turn-4 timings, file records); turn 3 checked structurally (MQ's window has a request at +3.0 s
and a 'Command running in background' result; WK's has none and an is_error InputValidationError): leg 1 closed after
the compaction, leg 2 open. Adopted:

1. MQ fails in the READING, not the delivery: the echo's MSP shows the file path in the child, so the variable reaches
   the process (as the folder variant did); what fails is the client reading that file as a managed source. A later
   fix should not be aimed at the delivery half, which works.
2. The settings SURVIVED the compaction: WK's echo takes exactly two forms across the cell (turn 5's, and the post-write
   form at turn 7, still present at turn 9 and after). So outcome (b) is not an artifact of the compaction resetting the
   settings; that closes the rival explanation the trigger and token counts do not exclude on their own.
3. Bound added: one forced compaction, two turns after the write. A second compaction, or one much later in a session,
   is not measured; the stated bound covers the compaction's form, not its position.
4. The instrument slip (the compaction key) was caught by C4 (i)'s positive control doing its job: without it, WK would
   have read as 'no manual trigger', i.e. uninterpretable.
