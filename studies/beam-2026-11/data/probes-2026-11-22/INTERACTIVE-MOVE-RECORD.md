# Record: a foreground Bash call moved to the background at 120 s in an interactive Claude Code 2.1.328 session

Written 2026-11-22 for Kepler 2026-11-22T20:02Z (c), so the plan cites a file, not a recollection. The study lead's interactive session.

## What ran

From the session's own transcript, extracted by script into interactive-move-record.raw.json (3 records):
- tool_use at 2026-11-22T19:57:26.532Z, Bash, no timeout parameter, no run_in_background: a readlink/file/grep
  over the 2.1.328 binary (grep -c and grep -ao over about 200 MB), description "Locate the sleep-guard code in the
  pinned binary".
- tool_result at 2026-11-22T19:59:26.778Z (120.2 s later), text, verbatim:
  "Command did not complete within its 120s timeout and was moved to the background (ID: bms17hu1y). Output is being
  written to: <session tasks dir>/bms17hu1y.output. You will be notified when it completes. It is running now: do not
  start a second copy while it runs. If it is no longer needed, stop it with TaskStop. To check interim output, use
  Read on that file path."
- The task was later stopped with TaskStop (no longer needed).

## Version and mode

- Transcript records carry "version": "2.1.328" (the tool_use and the tool_result).
- The harness process (pid in CLAUDE_PID) runs /home/<user>/.local/share/claude/versions/2.1.328 (readlink of its
  exe); CLAUDE_CODE_EXECPATH in the shell child names the same.
- Mode: interactive, not -p (argv has --remote-control and no -p; CLAUDE_CODE_ENTRYPOINT=cli and
  CLAUDE_CODE_SESSION_ATTENDED=1 in the shell child).
- CORRECTION, mine: I first reported this as 2.1.329, from `claude --version`, which prints the newest INSTALLED
  binary, not the running session. The running session is 2.1.328, the same version as the affected runs.

## Environment, as far as I can show it

- Harness process environ (/proc/<pid>/environ, readable, 22 variables): 0 of CLAUDE_AUTO_BACKGROUND*,
  CLAUDE_CODE_AUTO_BACKGROUND*, CLAUDE_CODE_DISABLE_BACKGROUND*, BASH_DEFAULT_TIMEOUT*, BASH_MAX_TIMEOUT* present.
  Positive control on the same read: HOME= matched 1 time(s).
- Shell child environment: interactive-move-env.txt (CLAUDE_* variables, the messaging token redacted; the five
  variables above all <unset>).
- Bound: the environ file shows the environment at exec time; a value the harness set internally after start, or read
  from a settings file, would not appear in it. Settings files were not read for this record.

## What it shows, and what it does not

- Shows: on 2.1.328, in an interactive session, the timeout-move route operated with no enabling variable in the
  process environment. So the route is not gated by that variable alone.
- Does not show: what happens under -p (the affected runs' mode). That is cell U.
