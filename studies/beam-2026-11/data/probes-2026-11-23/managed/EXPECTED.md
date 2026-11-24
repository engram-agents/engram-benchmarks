# Managed-settings precedence probe (R1): written expectations (before any run)

Written 2026-11-23 by Borges, before the probe has run against the real binary. Order: Kepler's settings ruling R1 with
the addendum (A3), file <the host's shared agent directory>/kepler/beam-rulings/2026-11-23-settings-file-ruling.md (sha256 dc47bf5d).
Script: probe.py in this directory, a copy of probes/settings-2026-11-23/probe.py (27be950f) with the changes in
probe.diff (hashes in the covering message). NOT run before the security seat has read this file and probe.diff.

The question (R1): is there a place the student cannot write whose settings env block WINS over a user settings file
that turns the three switches off, with the user file present at launch (order A: written during setup, read when the
exam launches) and written during the session (order B: written by the student mid-exam)? I do not assert the
precedence; the cells measure it.

## Command

    python3 probe.py --claude <pinned claude-2.1.328 binary> \
        --evidence <study lead's private probe folder>/evidence-<stamp> \
        --cells MF,MP,ME,AF,AP,AE,WC,BF,BP,BE,RX

Containment as on 11-22 and this afternoon: the whole probe runs in `bwrap --unshare-net` (loopback only), the gate
refuses to start if 1.1.1.1:443 connects or api.anthropic.com resolves, a throwaway HOME per cell under
<probe base>-<stamp>/ (removed and verified at the end), no plugins, no exam material, no model (a scripted
stub on loopback). Claude Code 2.1.328, print mode, one run per cell. About 45 minutes (11 cells, each with turn 4's
150 s command and its 60 s silence). CPU negligible.

## No root step on the host (A3)

Three routes to the managed tier, all read from the 2.1.328 binary as strings (context, not behaviour: the SEU0 lesson),
none measured yet:

- F, the flag: `--managed-settings <json>`. Hidden help text: "Policy-tier settings JSON from a spawning parent process
  (SDK use only)". The code calls it "parent managed settings" and has a list of keys that are "only honored from the
  organization's managed settings sources (server-managed, MDM, managed-settings.json), not from settings a host
  passes in". I could not see whether `env` is on that list.
- P, the path variable: `CLAUDE_CODE_MANAGED_SETTINGS_PATH`, which a log string describes as naming the policy folder in
  place of the machine's ("this machine's policy folder (or the one CLAUDE_CODE_MANAGED_SETTINGS_PATH names)"). The
  probe sets it to a probe-owned FOLDER holding managed-settings.json. Folder vs file is my reading of that string.
- E, /etc/claude-code: the host has no /etc/claude-code. The outer bwrap mounts a tmpfs on /etc INSIDE THE PROBE'S
  MOUNT NAMESPACE, binds every host /etc entry back read-only (symlinks recreated), remounts /etc read-only, and binds a
  probe-owned folder on /etc/claude-code. The host /etc is never written: bwrap here is not setuid (-rwxr-xr-x root),
  so a write to the host /etc from inside can only fail. Checked before writing this file, with no claude involved:
  inside, /etc holds the host's 192 entries plus claude-code; /etc is read-only; the host /etc still has 192 entries
  and no claude-code.

For the scored launcher (not this probe): the box binds the host /etc read-only, and its own comment says bwrap cannot
create files there (student-sandbox.sh, the /etc overlay block). So route E would need either the box's /etc rebuilt the
way this probe does it (a box design change, the security seat's) or a host root step (the project lead's yes/no).
Routes P and F need neither: P is one variable plus a read-only bind of a harness-owned folder; F is argv only.

## What is new against the settings probe

- Turns 1 and 2 are left out of every R1 cell. In the SE cells turn 1's Task ran async and shifted the proctor's reading
  by one (settings RESULT, bound 1). R1 cells send 5, 3, 4 (order A and mechanism) or 5, 6, 7, 3, 4 (order B). Leg 1
  (turn 3's background call) is therefore exercised directly, not read from the schema alone.
- Turn 5's echo adds `MGD=[$PROBE_MANAGED_ENV]`, `PREC=[$PROBE_PREC]` and `MSP=[$CLAUDE_CODE_MANAGED_SETTINGS_PATH]`.
- ONE KEY, THREE WRITERS: `PROBE_PREC` is set to "harness" in the process environment, "managed" in the managed block
  and "user" in the user block. Whose value a child sees says which writer won for a key all three set, independently
  of how the switches are parsed.
- Turn 6 (order B): the scripted student writes the user file with one shell command
  (`printf '%s' '<block>' > "$HOME/.claude/settings.json" && sleep 3 && echo WROTE`). Turn 7 repeats turn 5's echo.
- A1 rehearsed: every settings file the cell knows (user, project, project-local, the /etc managed file, the P folder's
  file, RX's student folder) is recorded at launch and after exit with sha256, mtime_ns and ctime_ns (or "absent").
- /etc/claude-code is emptied before every cell; only an E cell has a file there (listing logged per cell).

## Cells

Managed block everywhere: `{"env": {three switches "1", PROBE_MANAGED_ENV: <route>, PROBE_PREC: "managed"}}`.
User block that turns them off: `{"env": {three switches "", PROBE_SETTINGS_ENV: <level>, PROBE_PREC: "user"}}`.
Every cell's process environment has PROBE_PREC=harness.

| cell | harness env | managed (route) | user file | turns | asks |
|---|---|---|---|---|---|
| MF / MP / ME | no switches (cell U) | F / P / E | `{}` | 5,3,4 | mechanism: is that route's managed env block applied at all? |
| AF / AP / AE | switches "1" (launcher) | F / P / E | OFF at launch ("user") | 5,3,4 | order A: managed vs user file present at launch |
| WC | switches "1" | none | `{}`, OFF written in turn 6 ("user-mid") | 5,6,7,3,4 | control: does a RUNNING process pick up a mid-session write at all? |
| BF / BP / BE | switches "1" | F / P / E | `{}`, OFF written in turn 6 | 5,6,7,3,4 | order B: managed vs a mid-session write |
| RX | switches "1" | P | OFF at launch, AND its env block sets CLAUDE_CODE_MANAGED_SETTINGS_PATH to `$HOME/.policy`, where a student-written managed file turns the switches off (MGD "student", PREC "student-policy") | 5,3,4 | can the user file redirect route P to a folder the student wrote? |

## Expectations (confidence stated)

Basis: the Claude Code documentation (https://code.claude.com/docs/en/settings, read 2026-11-23 through a search
summary) says managed settings take the highest precedence and that user, project and --settings values cannot
override a managed key, except a short list of security keys where the stricter value wins. It does not say how `env`
entries merge. That is the vendor's statement about the current product, not about 2.1.328, and I have not read how
2.1.328 merges env blocks across tiers.
The binary also carries strings about managed settings "not yet approved in the managed-settings dialog" not being
applied, so a print-mode session holding an env block back is a live possibility.

- ME: MGD=[etc], PREC=[managed], SW=[1][1][1]; S-like on both legs. Moderate.
- MP: the same, weaker (folder vs file is my reading). If MGD is unset, a file-path variant is the pre-stated follow-up
  (a second command, expectations amended first), not part of this run.
- MF: no lean. "SDK use only" plus the honoured-only-from-org list could drop `env` from the flag.
- AE / AP (if the route's M cell shows MGD set): lean managed wins: SW=[1][1][1], PREC=[managed], MARK=[user] (the user
  block still lands for keys managed does not set), S-like. Moderate. AF: no lean.
- WC: no confident lean. The strings suggest a settings watcher ("...changed after this generation's policy walk; it
  applies from the next reset"), which may mean a change is NOT applied to the running session.
- BE / BP / BF: read only through WC (matrix below).
- RX: weak lean that the redirect fails: the variable is read from the process environment at launch, before a user
  env block is applied, so MGD=[path] and PREC=[managed]. MSP in the echo is what a CHILD sees and can show the
  student's folder even when claude read the harness's. MSP is never evidence of which folder claude read; MGD and
  PREC are.

"S-like" per leg: no run_in_background in any Bash-carrying request; turn 3's background call refused at input
validation; turn 4 killed at 120 s, no request in the 60 s silence. "U-like": the option in the schema; turn 3
accepted; turn 4 moved at about 120 s with an unsent turn about 30 s later.

## Reading matrix (written before the run)

| M cell (route) | A cell | reads as |
|---|---|---|
| MGD set | SW=[1][1][1], PREC=[managed], S-like | that route's managed tier WINS over a user file present at launch |
| MGD set | SW=[][][], PREC=[user], U-like | the user file wins over that route's managed env block: the route does not close the hazard; R2 is the rule |
| MGD set | mixed (e.g. PREC=[managed] with SW=[][][], or SW=[1] with the option in the schema) | reported per key and per leg as measured, never rounded |
| MGD unset | anything | that route's env block is not applied in this configuration; the A cell is read only for MARK/PREC; stderr and events searched for a managed-settings message and quoted (rule b of the settings probe) |

| WC | B cell | reads as |
|---|---|---|
| U-like after turn 6 (turn 7 SW=[][][], option in requests after the write) | S-like, PREC=[managed] | the managed tier also wins against a mid-session write |
| U-like after turn 6 | U-like after turn 6 | a mid-session write beats the managed tier on that route |
| S-like after turn 6 (no pickup) | anything S-like | a running 2.1.328 process does not apply a mid-session user write within this cell's span (about 3 minutes); order B says nothing about precedence. The order-B hazard is then the NEXT launch, which order A covers |

| RX | reads as |
|---|---|
| MGD=[path], PREC=[managed], S-like | the user file did not redirect route P at launch |
| MGD=[student] or PREC=[student-policy] | the user file CAN redirect route P to a folder the student writes: route P is not safe for the launcher as is |
| MGD unset | as the M rows: report, quote stderr |

If a route wins in both orders (or in A, with WC showing no mid-session pickup) and RX does not redirect it, then per R1
the scored launcher can set the switches there and the route is closed by construction; R2 stays the residual rule.

## Bounds, stated in advance

- Claude Code 2.1.328 only, print mode, one host, one run per cell, scripted model, values "1" and "" only.
- Order B's write is a single file write with 3 s before the next request; a longer delay is not tried.
- Not tried here: the drop-in folder managed-settings.d (a follow-up cell if E and P disagree or E is not read);
  managed settings KEYS that are not env (backgroundTasksDisabled and its siblings, which the binary ORs with the
  variable: a follow-up if no managed env route wins); ~/.claude.json; remote or MDM managed sources.
- /etc/claude-code exists (empty) in every cell, because it is one bind for the whole probe. An empty folder is assumed
  to read the same as an absent one; not measured.
- An unsent turn after turn 3 (U-like cells) is consumed by the 20 s window before turn 4, as in cell U on 11-22.
- The cells say what this version does when such files exist. They say nothing about what any student did.

## Checked before this file, with no model and no real claude

- The private /etc construction above (bwrap only).
- The probe's plumbing, with a stand-in `claude` script that answered each turn with a result line and wrote down its
  argv, environment and /etc/claude-code (cells ME, RX, MF). The gate passed (errno 101, no resolution). ME's process
  saw the managed file at /etc/claude-code; the next cell saw the folder empty. MF's argv carried `--managed-settings`
  with the block. RX's user file named `$HOME/.policy`. Two file records per cell. Exit 0; no process left; base
  removed.
- Turn 6's command, run by itself under a throwaway HOME, wrote exactly the intended block (byte-equal, 178 bytes).

## Cleanup, verified and reported

As before: processes matching the base before and after removal, and whether the base still exists.

---

# Amendment after the security read (Zephyr 2026-11-23T21:15Z, NO HOLD), before any run

All three additions adopted.

ADD 1, a request-count floor. RESULT prints, per cell, the number of model requests the stub received (and how many
carry the shell). A cell with ZERO requests is NOT RUN: never S-like, never U-like, whatever its four absences say.
MF is the live case: if 2.1.328 rejects --managed-settings, the process can exit before the stub sees anything. A cell
with requests but none after a given turn is reported per turn the same way (that turn NOT RUN).

ADD 2, a namespace proof before the /etc/claude-code wipe. Before listing or removing anything there, run_cell compares
(st_dev, st_ino) of /etc/claude-code with the probe's own folder under base (a bind mount keeps both) and refuses with
nothing removed if they differ. Shown both ways before the run, no model: inside a box whose /etc/claude-code was a
different folder holding a sentinel file, `--inner` refused (exit 1, refusal logged) and the sentinel survived; inside
the real probe box (stand-in claude, cells ME and MF) the check passed, ME saw its managed file, MF saw the folder
empty and the flag in its argv, cleanup clean.

ADD 3, RX made explicit and gated. RX is read only after MP: if MP shows route P not read (MGD unset), RX has nothing to
redirect and is reported as uninterpretable. Rows:

| MP | RX | reads as |
|---|---|---|
| MGD=[path] | MGD=[path], PREC=[managed], S-like | the user file did not redirect route P at launch |
| MGD=[path] | MGD=[student] or PREC=[student-policy] | the user file CAN redirect route P to a folder the student writes |
| MGD=[path] | MGD unset and PREC not [managed] | the redirect's outcome is UNRESOLVED; stderr and events quoted; never 'no redirect' |
| MGD unset | anything | RX uninterpretable (route P not read) |

Launcher design rules from the same read, carried to the amendment and the launcher PR, not tested here: the
--managed-settings value is never computed from a path under the arm home; PATH never gains a student-writable
directory. The security seat prefers route P over F for the launcher (argv is readable through /proc); not a finding.
