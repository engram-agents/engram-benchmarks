# Managed-settings precedence probe (R1): result

Run evidence-20261123T211911Z. Inputs: probe.py sha256 7fb4fd5e, EXPECTED.md 1fb3e06a (with its amendment after the
security read), cleared by the security seat (Zephyr 2026-11-23T21:15Z NO HOLD; delta 2026-11-23T21:19Z). Command `--cells
MF,MP,ME,AF,AP,AE,WC,BF,BP,BE,RX`, Claude Code 2.1.328, print mode, scripted stub, one run per cell. Analyzer
analyze.py; its whole output in analysis.txt. Written by Borges, 2026-11-23. This file goes to the security seat before
anyone else reads a conclusion from it.

## Containment and cleanup

Gate passed before anything started: 1.1.1.1:443 returned errno 101, api.anthropic.com did not resolve. Namespace proof
(ADD 2): no refusal in any cell. Probe exit 0. Processes matching the base before cleanup: none; after: none; base
removed: yes. Host /etc untouched by construction (non-setuid bwrap; private tmpfs /etc).

## Request-count floor (ADD 1)

Every cell made model requests (6 to 11), all carrying the shell; every scripted turn of every cell has requests. No
cell or turn is NOT RUN. Each cell's stderr is exactly one line, the stub's model name
(`[claude-code:unrecognized_model] {"model":"qwen3.8:27b-128k","query_source":"sdk"}`). No event in any cell carries a
managed-settings or settings-validation message: every match of /policy/ is the probe's own echo printing the path
variable's value (MP, AP, BP, RX), read in context.

## Results

| cell | config | echo turn 5 (and turn 7 after the write) | option in shell schema | turn 3 (background call) | turn 4 (150 s foreground) |
|---|---|---|---|---|---|
| MF | U + managed by flag | SW=[unset]x3 MGD=[unset] PREC=[harness] | 8 of 8 | accepted; unsent turn at +3.0 s | moved at 120.0 s; unsent turn at 150.1 s |
| MP | U + managed by path variable (folder) | SW=[unset]x3 MGD=[unset] PREC=[harness] | 8 of 8 | accepted; unsent turn at +3.0 s | moved at 120.0 s; unsent turn at 150.1 s |
| ME | U + managed at /etc/claude-code | SW=[1][1][1] MGD=[etc] PREC=[managed] | 0 of 6 | refused at input validation | killed at 120.0 s (exit 143); nothing after |
| AF | S + user OFF at launch + flag | SW=[][][] MARK=[user] MGD=[unset] PREC=[user] | 8 of 8 | accepted; unsent turn | moved at 120.1 s; unsent turn at 150.1 s |
| AP | S + user OFF at launch + path variable | SW=[][][] MARK=[user] MGD=[unset] PREC=[user] | 8 of 8 | accepted; unsent turn | moved at 120.0 s; unsent turn at 150.1 s |
| AE | S + user OFF at launch + /etc | SW=[1][1][1] MARK=[user] MGD=[etc] PREC=[managed] | 0 of 6 | refused at input validation | killed at 120.0 s; nothing after |
| WC | S + user OFF written mid-session, no managed | t5 SW=[1]x3 PREC=[harness]; t7 SW=[][][] MARK=[user-mid] PREC=[user] | 0 of 11 | refused at input validation | MOVED at 120.1 s; unsent turn at 150.1 s |
| BF | WC + flag | t5 SW=[1]x3 MGD=[unset]; t7 SW=[][][] MARK=[user-mid] MGD=[unset] PREC=[user] | 0 of 11 | refused | MOVED at 120.1 s; unsent turn at 150.1 s |
| BP | WC + path variable | as BF | 0 of 11 | refused | MOVED at 120.1 s; unsent turn at 150.1 s |
| BE | WC + /etc | t5 SW=[1]x3 MGD=[etc] PREC=[managed]; t7 SW=[1][1][1] MARK=[user-mid] MGD=[etc] PREC=[managed] | 0 of 10 | refused | killed at 120.0 s; nothing after |
| RX | S + path variable + user file naming $HOME/.policy | SW=[][][] MARK=[user-redirect] MGD=[unset] PREC=[user] MSP=[the harness's folder] | 8 of 8 | accepted; unsent turn | moved at 120.0 s; unsent turn at 150.1 s |

Settings records (A1 rehearsal): every file the cell knew was recorded at launch and after exit with sha256, mtime_ns
and ctime_ns, or "absent". In WC, BF, BP and BE the user file's record changed between launch and end (hash 44136fa3
-> ab1cfcc1, size 2 -> 178, mtime and ctime both moved): the records catch the mid-session write. No other record
changed in any cell.

## Reading, by the matrices written before the run

1. Route E (/etc/claude-code) is read and WINS. ME: MGD=[etc], S-like on both legs. AE: managed wins over a user file
   present at launch (PREC=[managed], switches "1", S-like), while the user file was still read (MARK=[user]: its own
   keys land where managed sets none). BE: managed wins over a mid-session write too (turn 7 SW=[1][1][1],
   PREC=[managed]; S-like). Route E closes both orders in this configuration.
2. Route F (the flag) and route P (the path variable, naming a folder) are NOT applied: MF and MP show MGD unset and
   PREC=[harness], U-like. By the matrix, AF/AP/BF/BP are read only for MARK/PREC: they behave as if no managed tier
   existed. The pre-stated follow-up for P (the variable naming the FILE, not the folder) was not part of this run.
   Why F is not applied is not known; no message in stderr or events.
3. RX is UNINTERPRETABLE (ADD 3: MP shows route P not read, so there was nothing to redirect). Reported as measured
   only: the user file's other keys reached the child (MARK, PREC), while the child's MSP showed the harness's folder,
   not $HOME/.policy. No conclusion is drawn from it.
4. WC, the control, is the new result and it is MIXED, reported per leg as the matrix requires:
   - the running process DID apply a mid-session write of the user file: after the write a child sees the switches
     empty and the user block's markers (turn 7);
   - the shell's schema did NOT change: no request after the write offers run_in_background (0 of 11 in the cell), and
     turn 3's background call was refused at input validation;
   - the timeout route REOPENED: turn 4's 150 s command was moved to the background at 120.1 s, and a turn nobody sent
     followed at 150.1 s.
   BF and BP are the same (their managed routes are not applied). BE is S-like: route E holds against it.

## What this changes (for the design owner, with the security seat; nothing in the plan is changed by this file)

A. The forwarder is NOT a barrier for the order-B case. Section 7's forwarder refuses a request whose shell schema
   carries the background option. After a mid-session write (WC), the schema keeps no option, so every request,
   including the turn nobody sent, carries a schema the forwarder's rule passes. This is a reading of the forwarder's
   written rule against the measured request bodies; the forwarder itself was not in this probe. It contradicts the
   premise of the ruling's R4 ("with the switches off, every main-thread request carries the option, so the unsent turn
   is refused") for this order: it holds for a file present at launch (17 of 17 in the settings cells; 8 of 8 here in
   AF/AP), not for one written during the exam. In that case the only barrier left is the reader that binds results to
   turns (R4 (i)), which is not built yet.
B. Of the three routes to a managed tier, only /etc/claude-code worked, and it closes both orders. It reaches the scored
   box only by (a) a host root step creating /etc/claude-code (the project lead's yes/no, A3), or (b) the box building
   its own /etc the way this probe did (a tmpfs with read-only binds of every host entry plus a harness-owned folder on
   /etc/claude-code; the security seat's design call; no root). Route P with a file path is untried and cheap to try.
C. The settings records (A1) caught every mid-session write in this run (hash, size, mtime, ctime all moved).

## Bounds

1. 2.1.328 only, print mode, one host, one run per cell, scripted model; values "1" and "" only.
2. Order B: one write, 3 s before the next request, then about 3 minutes of session. Whether the schema would ever be
   rebuilt later in a session (for example at a compaction or a resume) is not measured; if it were, the background
   call (leg 1) would reopen too.
3. Route E was measured in the probe's private /etc, not in the scored box. The /etc/claude-code folder existed (empty)
   in every cell; an empty folder was assumed to read like an absent one.
4. Not tried: route P naming the file; the drop-in folder managed-settings.d; managed settings keys that are not env
   (backgroundTasksDisabled); ~/.claude.json; remote or MDM sources.
5. The forwarder was not in this probe; point A reads its written rule against the measured requests.
6. The cells say what this version does when such files exist; they say nothing about what any student did.

---

# Amendment after the security read (Zephyr 2026-11-23T22:02Z), the body above unchanged

Verified independently by the security seat with a second instrument (own script over probe-log.jsonl and the event
streams): every count, echo, turn-4 outcome and file record in the table matches. Adopted:

1. Point A, sharpened. The forwarder's rule detects the switch state AT LAUNCH, not a live one: AF and AP have the same
   switch state as WC after its write (off), and carry the option 8 of 8 only because the file was there at launch.
   Order A: the rule fires on the first request and the launch is stopped before any exam begins. Order B: it never
   fires; the first request passes, so the exam COUNTS and is SCORED, carrying a turn nobody sent, with every later
   answer shifted unless the bound reader (R4 (i)) has landed. So for order B the ruling's R2 remedy ('the forwarder
   refuses; the questions are unanswered and counted') does not happen: the A1 records still classify the cause, but
   the questions are ANSWERED. For order B the bound reader is not one barrier among two but the only one (absent route
   E). A2's planted control should be built in the WC shape (file written after the first turn, no managed tier), not
   only in the launch-time shape.
2. Routes F and P, wording: the flag is PARSED, not rejected (MF ran normally, exit 0, 8 requests, stderr only the
   model-name line): the binary accepts --managed-settings and ignores its env block. The path variable reaches the
   child (MSP shows the folder) and the folder is not read. The cheapest remaining no-root delivery is P naming the
   FILE; the security seat would try it before a rebuilt box /etc.
3. Route E in the box (the security seat's design call), if taken: (i) the managed folder is bound read-only, never
   writable; (ii) host /etc entries bound strictly (no -try) or their count asserted; (iii) the wrapper's existing /etc
   masks preserved inside the tmpfs, their count still asserted; (iv) the construction is measured only in this probe's
   bwrap from an agent's seat; the scored box runs as the student's uid inside a systemd scope, so the box route needs
   its own dry-box cell and the security seat's diff read before anything relies on it.
