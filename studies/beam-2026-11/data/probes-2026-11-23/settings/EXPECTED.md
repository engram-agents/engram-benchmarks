# Settings-file probe: written expectations (before any run)

Written 2026-11-23 by Borges, before the probe has run. Script: probe.py in this directory, a copy of
probes/capability-2026-11-22/probe.py with the changes in probe.diff (sha256 of both in the covering message).
Order: the plan's OPEN item (preregistration.md, group 'Before the freeze'): "whether a file in the student's
home (a settings file's environment block, user or project level) can change the three switches of section 7
or bring the shell's background option back against the environment the harness sets. One dry-box cell
answers it, its expectations and command read by the security seat first." Queue: Kepler 2026-11-23T14:07Z / 2026-11-23T14:19Z.
NOT run before the security seat has read this file and probe.diff.

This is NOT section 7's whole-configuration dry-box cell (OFF set + switches + variables unset, in the scored
launcher's real argv). That one waits on the scored launcher and is not touched here.

## Command

    python3 probe.py --claude <pinned claude-2.1.328 binary> \
        --evidence <study lead's private probe folder>/evidence-<stamp> --cells UE,SEU,SEP,SEL

Same containment as 2026-11-22: the whole probe runs in `bwrap --unshare-net` (loopback only), the gate refuses
to start if 1.1.1.1:443 connects or api.anthropic.com resolves, throwaway HOME per cell under
<probe base>-<stamp>/ (removed and verified at the end), no plugins, no exam material, no model
(scripted stub on loopback). Claude Code 2.1.328, print mode, one run per cell. Wall time about 20 minutes
(four cells, each with turn 4's 150 s command and its 60 s silence). CPU: negligible (sleeps), so it does not
compete with the host's other work.

## What is new against cell S (everything else is cell S unchanged)

- Turn 5, sent FIRST in every new cell: one Bash call,
  `echo SW=[$CLAUDE_CODE_DISABLE_BACKGROUND_TASKS][$CLAUDE_CODE_DISABLE_CRON][$CLAUDE_CODE_DISABLE_WORKFLOWS]
  MARK=[$PROBE_SETTINGS_ENV]` (each printed as `unset` when absent). It shows what a child of the harness sees:
  whether the settings env block reached the process environment, and which value won.
  Then turns 1, 2, 3, 4 as in S (turn 4 stays last so its 60 s silence window is unchanged).
- A settings file written before launch:
  - SEU: `$HOME/.claude/settings.json` = `{"env": {the three switches: "0", "PROBE_SETTINGS_ENV": "user"}}`,
    harness environment = cell S (three switches "1", enabling variable unset).
  - SEP: the same block in the project file `$HOME/work/.claude/settings.json` (the student's cwd is
    `$HOME/work`), user file `{}`; marker "project".
  - SEL: the same block in `$HOME/work/.claude/settings.local.json`; marker "local".
  - UE (mechanism control): cell U's environment (NO switch in the environment) with the user file
    `{"env": {the three switches: "1", "PROBE_SETTINGS_ENV": "user-on"}}`.
- Every request the stub receives is logged whole, as before, so Bash's input schema is read per request.

## Expectations (confidence stated; I have not read how 2.1.328 applies a settings env block)

- UE (the mechanism): I expect the settings file to be READ and applied: MARK=[user-on], SW=[1][1][1], and then
  cell S's behaviour: run_in_background absent from Bash's schema, turn 3 refused at input validation, turn 4
  killed at 120 s, no unsent turn. Confidence moderate. If UE behaves like U instead (schema keeps the option,
  turn 4 moved), the settings file cannot drive the switches at all in this configuration, and SEU/SEP/SEL
  are read only for the MARK and SW lines.
- SEU / SEP / SEL (the question): no confident expectation. Two outcomes are live:
  (a) the harness environment wins: SW=[1][1][1] (or MARK present with SW unchanged), S's behaviour on both legs;
  (b) the settings file wins: SW=[0][0][0], run_in_background back in Bash's schema, turn 3's background call
      accepted, turn 4 moved at about 120 s with an unsent turn after it.
  I lean (b) for the user file, weakly. Settings env blocks are documented as applied to every session, and
  nothing I know of protects variables that were already set. For SEP and SEL I lean the same, more weakly: a
  project file may also need the folder to be trusted, and print mode may or may not count it as trusted. The
  MARK line separates "file not read" from "file read, environment kept".
- Mixed outcomes are possible and are reported as measured, per leg, never rounded to (a) or (b). For example:
  SW=[0] but the schema still lacks the option because the tool definition was built earlier.

## Reading matrix (written before the run)

| UE | SEx | reads as |
|---|---|---|
| S-like | S-like, MARK set | the file is read and can set the switches; the harness environment wins over it |
| S-like | U-like (moved) | a file in the student's home CAN turn the switches off: the OPEN item's 'if it can' branch |
| U-like | S-like | the file does not drive the switches in this configuration; a quiet SEx says nothing about precedence beyond that |
| anything | MARK=[unset] | that file level was not read in this configuration (state which level) |

If any SEx cell is U-like on either leg, the forwarder's per-request refusal is still the barrier (section 7). What
changes is the class of that refusal: it becomes the arm's behaviour, not a harness fault. The plan's words "a
harness fault counted against the arm" then need the design owner's ruling with the security seat. I report and
change nothing in the plan.

## Bounds, stated in advance

Claude Code 2.1.328 only, print mode, one host, one run per cell, scripted model. The value tried is "0" only. A
different falsy spelling ("false", empty) is not tried; if UE shows the file is read and SEx stays S-like with
SW=[1], the value spelling is irrelevant to that outcome. Managed (system) settings and command-line --settings are
not tried: the student cannot write either. The cell says what this version does, not what the student did. No arm's
past run had a settings env block (every arm home's user file was `{}`, 2026-11-22 setup notes). That is a claim
about the homes as built, not re-read here.

## Cleanup, verified and reported

As 2026-11-22: processes matching the base before and after removal, and whether the base still exists.

---

# Amendment after the security read (Zephyr 2026-11-23T20:15Z), before any run

The value "0" could not answer this file's own question. In 2.1.328 the switch is consumed by truthiness, not by value.
Read by me in the binary after Zephyr: `function Uve(){return s.CLAUDE_CODE_DISABLE_BACKGROUND_TASKS||lr()}`, and the
other call sites have the same shape (`...||s.CLAUDE_CODE_DISABLE_BACKGROUND_TASKS||lr()`). In JavaScript "0" and
"false" are truthy, so the only spelling that can turn the switch off is the empty string. What `lr()` returns in print
mode is NOT read (strings are context, not control flow).

## Cells now (command: `--cells UE,SEU,SEU0,SEP,SEL`, about 25 minutes)

- SEU, SEP, SEL: the env block sets the three switches to "" (empty), at user, project and project-local level.
  This tests the switch.
- SEU0 (new): the user file sets them to "0", marker "user-zero". This tests whether the block's value reaches the
  process at all, against the harness environment's "1".
- UE: unchanged, the mechanism control.
- Turn 5's echo tells empty from absent: `[]` means set to empty, `[unset]` means absent.
- probe.py sha256 27be950f; diff against v1 in probe-v2.delta (f5b55204); full diff against 11-22 in probe.diff
  (affe463c).

## Expectations, revised

- UE: unchanged (moderate). The file is read: MARK=[user-on], SW=[1][1][1], S-like on both legs.
- SEU0: if the block is applied over the harness environment, SW=[0][0][0] with S-like behaviour (the value won, and
  the consumer reads truthiness). If the harness environment wins, SW=[1][1][1]. No confident lean between these.
- SEU, SEP, SEL: the same two live outcomes as before, (a) harness environment wins and (b) file wins, now with a
  value that can actually turn the switch off. Under (b) the expected signature is SW=[][][] and the option back in
  Bash's schema (U-like), unless `lr()` holds it on in print mode. Lean (b) for the user file, weakly, as before.

## Reading matrix, rows added (written before the run)

| cell | MARK | SW | behaviour | reads as |
|---|---|---|---|---|
| SEU0 | set | [0][0][0] | S-like | the file's value reached the process and overwrote the harness's "1"; the switch stayed on only because "0" is truthy. NOT 'the harness environment wins' |
| SEU0 | set | [1][1][1] | S-like | the harness environment wins over the user file's value |
| SEx | set | [][][] | U-like | a file in the student's home CAN turn the switches off (the OPEN item's 'if it can' branch) |
| SEx | set | [][][] | S-like | the value reached the process but the option stayed closed by another path (`lr()`, or a settings key); reported as measured, cause not claimed |
| SEx | set | [1][1][1] | S-like | the harness environment wins at that level |

The first row of the original matrix ('the file is read ... the harness environment wins') applies only when SW shows
the harness's own value. It is never applied from behaviour alone.

## Wording rule for RESULT

The `settings_files` log line records what the script WROTE (intent), not what the harness read. Only the MARK line is
evidence that the harness read the file. The two are never quoted interchangeably.

## Bounds added (Zephyr 2026-11-23T20:15Z (Q1), not covered by these cells)

- `~/.claude.json`, which 2.1.328 reads: whether it can carry an env block is unmeasured.
- Settings keys that are not environment. The binary reads `backgroundTasksDisabled` (and
  `backgroundAgentLaunchDisabled`) from settings. In every call site I read they are ORed WITH the environment
  variable, so they can add a disable and none is seen removing one. That is a reading of three call sites as strings,
  not a measurement.
- The harness's process environment is unreachable through shell dotfiles: the launcher spawns claude from a built
  dict with no shell (Zephyr, feed4.py:53).

## Two reading rules added after the security seat's delta read (Zephyr 2026-11-23T20:18Z, NO HOLD), before any run

(a) SEU0 and SEU are read as a PAIR. If SEU0 shows the value landing (SW=[0][0][0]), the user file's block does
overwrite values the harness set, so a SEx cell at SW=[1][1][1] reads as "empty values are not applied" (dropped by
the loader, or treated as unset), NOT as "the harness environment wins". The precedence reading of SW=[1][1][1] stands
only when SEU0 also shows [1][1][1].
(b) MARK=[unset] in a SEx cell has two causes: the file level was not read, or the file was read and rejected at parse
(a validator refusing an empty-string env value would lose the whole block, MARK included). Before any cell is called
"not read", that cell's stderr-<cell>.log and its events are searched for a settings-validation message, and what the
search returned is quoted in RESULT.
