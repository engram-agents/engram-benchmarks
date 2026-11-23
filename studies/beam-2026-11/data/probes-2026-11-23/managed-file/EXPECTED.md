# Follow-up to R1: route P naming the FILE, and the forced-compaction cell (written expectations, before any run)

Written 2026-11-23 by Borges, before the probe has run against the real binary. Order: Kepler's settings ruling,
addenda 2 and 3 (file fa6a60f8): B3 (1) the path variable naming the FILE, expectations to the security seat first;
C3 the redirect cell gated on the plain file cell; B4/C4 one cell, WC followed by the exam's FORCED compaction, with a
positive control that the compaction fired. Script: probe.py here, a copy of the R1 probe (7fb4fd5e) with the changes
in probe.delta. NOT run before the security seat has read this file and probe.delta.

## Command

    python3 probe.py --claude <pinned claude-2.1.328 binary> \
        --evidence <study lead's private probe folder>/evidence-<stamp> --cells MQ,AQ,BQ,RQ,WK

Containment unchanged from R1 (private network namespace, the gate, private tmpfs /etc with the namespace proof before
any wipe, throwaway homes under <probe base>-<stamp>/, removed and verified). 2.1.328, print mode, one run
per cell, scripted stub. About 25 minutes.

## What is new against the R1 probe (probe.delta)

- Route `pathfile`: the harness sets CLAUDE_CODE_MANAGED_SETTINGS_PATH to the managed FILE
  (<base>/policy-<cell>/managed-settings.json), not its folder. Same managed block as R1 (switches "1",
  PROBE_MANAGED_ENV="pathfile", PROBE_PREC="managed").
- Cells MQ (mechanism: cell U's environment + pathfile), AQ (order A: launcher switches "1" + user file OFF at launch
  + pathfile), BQ (order B: as AQ but the user file is written in turn 6), RQ (as RX, but the user file's env block
  names the student's FILE, $HOME/.policy/managed-settings.json, matching the route).
- Cell WK (B4): WC's configuration (launcher switches "1", no managed tier, user file OFF written in turn 6), then turn 8
  = the proctor sends `/compact` as a user message (the form feed4 uses for the exam's forced compaction), then turn 9
  = the echo again, then turns 3 and 4. Turns (5, 6, 7, 8, 9, 3, 4).
- Every proctor send is logged with its time and content; the analyzer assigns each model request to the latest send
  before it (so requests made during the compaction are attributed to turn 8, whatever label the stub gave them), and
  reports every `compact_boundary` event with its trigger. The analyzer's cell list now comes from the log (it had been
  a hand list, which missed WK in a stand-in run).

## Expectations (confidence stated)

- MQ: weak lean NOT applied (MGD unset). A string in the binary reads "the host attests the 'system' space absent, so
  this machine's policy folder (or the one CLAUDE_CODE_MANAGED_SETTINGS_PATH names) is not read", which suggests the
  variable names a folder and that reading it may depend on something else; MP showed the folder form not read. No
  better basis than that string; it is context, not behaviour.
- AQ, BQ: read only through MQ (R1's matrix rows). If MQ shows MGD=[pathfile], my lean for AQ/BQ is the same as route E
  measured (managed wins in both orders), moderate, since E and P would then feed the same tier.
- RQ: gated on MQ (C3, ADD 3): if MQ is not read, RQ is uninterpretable. If MQ is read: weak lean no redirect.
- WK: no lean on the question. Two outcomes are live:
  (a) the schema is REBUILT at the forced compaction: requests after turn 8 offer run_in_background, turn 3's background
      call is accepted (the probe has no forwarder; in the scored box the forwarder would refuse from that index, the
      pervasive-lapse case), turn 4 is moved;
  (b) the schema is NOT rebuilt: no request after turn 8 offers the option, turn 3 refused at validation, turn 4 moved at
      about 120 s with a turn nobody sent (as WC): a blind order-B run stays blind after the exam's compaction.

## Reading rules (written before the run)

- Zero model requests in a cell, or none after a given send, is NOT RUN for that cell or turn (ADD 1).
- WK is read only if its events carry a `compact_boundary` with trigger "manual" after the `/compact` send (C4 (i)). If
  none: the compaction did not fire, and WK says nothing about rebuilding (never 'not rebuilt').
- If turn 8 produces no `result` event, the proctor waits its 240 s bound and logs a turn timeout; reported, and the
  rest of the cell is read from the send-window attribution.
- MSP in the echo is what a child sees, never evidence of which file claude read; MGD and PREC are.

| MQ | AQ / BQ | reads as |
|---|---|---|
| MGD=[pathfile] | PREC=[managed], switches "1", S-like | route P (file) delivers the tier and wins in that order |
| MGD=[pathfile] | PREC=[user] or U-like | the user file beats route P (file) in that order |
| MGD unset | anything | route P (file) not read either: B3 step (2), the box-built /etc, is next |

| WK compact_boundary (manual) | requests after /compact | reads as |
|---|---|---|
| present | option offered | (a) rebuilt at forced compaction |
| present | no option | (b) not rebuilt: blind order B persists past the compaction |
| absent | anything | compaction did not fire: WK uninterpretable |

## Bounds, stated in advance

2.1.328 only, print mode, one run per cell, scripted model. The stub answers the compaction's own model request like any
other (it is not a real summary). One forced compaction, not an automatic one (C4 (ii): the forced form is what the exam
uses). The resume half of B4 is not in this run (C4 (iii): settled in the launcher's text first).

## Checked before this file, with no model and no real claude

A stand-in `claude` (cells MQ, RQ): MQ's process saw the variable naming an existing file holding the managed block;
RQ's user file named the student's file, which existed. A stand-in run of WK: the proctor sent 5, 6, 7, `/compact`, 9,
3, 4 in that order and the stand-in received exactly that. Cleanup clean in both. The edited analyzer, run over R1's
evidence, reproduces analysis.txt byte-for-byte over its first 523 lines.

---

# Amendment after the security read (Zephyr 2026-11-23T22:12Z, NO HOLD), written while the run was in progress, before any result was read

The run was started on the NO HOLD with probe.py unchanged (8117b7fc). Everything below changes the analyzer and the
reading only; nothing of the evidence had been read when it was written.

1. WK's "not rebuilt" row is gated on at least one model request AFTER the /compact send carrying the shell. None is
   NOT RUN for that half of the cell (ADD 1), never "not rebuilt".
2. The option count now uses the forwarder's written rule, not a variant of it: run_in_background anywhere in a Bash
   entry's whole input schema, every tool entry scanned, and any shape the forwarder cannot read (more than one Bash
   entry, a $ref, allOf/anyOf/oneOf) reported separately. RESULT names this predicate beside every count. On R1's
   evidence the wide and the old narrow predicate agree in every cell (8/8 MF, MP, AF, AP, RX; 0/6 ME, AE; 0/11 WC, BF,
   BP; 0/10 BE), matching the security seat's own figures; on constructed requests the wide one catches an option
   nested deeper and one in a second Bash entry, which the narrow one misses, and flags both unreadable shapes.
3. "No option after the compaction" supports the OPERATIONAL claim (the forwarder still never fires), not the
   MECHANISM claim (no rebuild happened): a rebuild that took the switches from the process environment would also show
   no option. RESULT words it operationally.
4. Scope of WK: plan section 8 puts the forced /compact between the reading exchanges and the 20 probing questions, so it
   precedes the entire scored answer phase. If rebuilt: every answer request carries the option and the forwarder
   refuses all of them; the exam yields no scored answers. If not rebuilt: every answer is produced blind with leg 2 open.
   The probe's turn order (5, 6, 7, 8, 9, 3, 4) is a schema probe, not 'compaction then 20 answers'; RESULT says its
   conclusion is about the answer phase that follows the forced compaction.
5. Control for the new per-send block: R1's evidence carries no send log, so it cannot serve. The control runs in this
   run instead: for every cell, the per-send request counts sum to the cell's total, and for each turn without a
   compaction, the per-send count equals the stub-label per-turn count. A mismatch is reported, not reconciled.
