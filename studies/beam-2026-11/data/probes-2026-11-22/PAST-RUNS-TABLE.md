# Past (affected) runs: did either route to an unsent turn occur? One table, populations named (Kepler 2026-11-22T20:19Z, 2026-11-22T20:21Z)

Computed by script on 2026-11-22 over the run directories in artefact-check-2026-11-22/windows.tsv (its run column; a
".../run" leaf counts as its parent): 41 directories. Patterns: "did not complete within its", "moved to the
background", "Command timed out after" (the three shell timeout messages of 2.1.328), and is_backgrounded true.
Positive controls: event format, cell U's own events (evidence-20261122T201436Z/events-U.jsonl): the move message found
in its Bash result, 2 backgrounded task events; transcript format, my own interactive 2.1.328 session transcript
(the study lead's interactive session): the move message found (incl. the real 19:59:26Z result recorded in INTERACTIVE-MOVE-RECORD.md).

| population | count | read by | what was searched | result |
|---|---|---|---|---|
| run directories | 41 | Borges (all files, as owner); Zephyr 127 of 135 candidate files (8 denied: readable by the study lead only) | everything below | see rows |
| event logs (events.jsonl, harness stream-json) | 39 files in 39 dirs | Borges; Zephyr (2026-11-22T19:44Z, independently) | every Bash tool_result for the 3 messages; every system event for is_backgrounded true | 860 Bash results; 0 hits on each pattern; 0 backgrounded events |
| student transcripts, 11-14 beam-p2 (student-transcript.jsonl) | 4 files | Borges ALONE (readable by the study lead only) | the 3 messages + is_backgrounded true, per file | 0 on every pattern in every file (Bash results 23, 1, 3, 0) |
| transcripts, 11-15 beam-speed (transcripts/ and first-session-transcripts/ under the runs) | 15 files | Borges ALONE (readable by the study lead only) | same, per file | 0 on every pattern in every file (Bash results per file 0 to 375; one session, 621d57cd, the lean-setup first session, appears as a copy in 7 of these files) |
| turn files (turns.jsonl) | 41 files, 739 rows | Borges | wall time per proctor turn (used only for the one dir below) | see the hole |
| directories with NO event log | 2 | Borges | | one has a student transcript (in the rows above); one has turn records only |

The 8 files Zephyr could not read (four beam-p2 student transcripts; four beam-speed transcripts under probe-copy-r1 and
probe-below-r1) are all inside the two transcript rows: for those eight THE ZERO IS MINE ALONE. Their modes were not
changed. The two transcript rows hold 19 files in all (a superset of Zephyr's eight; the other eleven are copies or
sessions under beam-speed run directories, also readable by the study lead only; I did not establish whether Zephyr's 135-file population included
them).

## The hole: one session

beam/incident-2026-11-21-unwrapped-probe has turn records only (6 turns, wall_s 28.49, 13.87, 18.55, 84.97, 16.09,
20.5). What a turn record CAN show: a command moved at the 120 s default makes its turn last at least about 120 s, so no
turn there contained a command that reached the timeout. What it CANNOT show: an unsent turn itself (rows are
proctor-driven), a background call the model requested itself (it can end fast), anything inside a turn.

SECOND INSTRUMENT on that session (Kepler 2026-11-22T20:22Z), on exactly what the turn records cannot show: its relay accounting,
calls.jsonl in the same folder (read by Borges and, independently, by Zephyr on 11-22 (2026-11-22T20:23:57Z/2026-11-22T20:23:59Z); by Kepler on 11-21). 7 relay calls, all status 200; the request
message counts run 2, 4, 6, 8, then (after the system fingerprint changes, i.e. after the compaction) 5, 7, 9; call 4 is
the compaction (6,359 output tokens, 64.06 s). So 7 calls = 6 answers + 1 compaction for 6 proctor turns: no extra
request exists for a tool round trip (a tool call would need a further request inside a turn, carrying the tool
result), so no tool call was made in the session at all, background or foreground. Bound: a count of relay calls and
their message counts; the file holds fingerprints, not bodies (a text search of it for tool_use proves nothing), and
the reading assumes call 4 is the compaction, which its size and the fingerprint change support.

## Two different "eights", named apart (correction of mine)

1. In my message to Zephyr and Kepler I wrote "eight 11-14 sessions have turn records but no transcripts" as the hole.
   WRONG for this question. Those eight are the windows.tsv sessions whose Claude Code SESSION transcripts were gone
   when I computed time windows (marked APPROXIMATE there); they HAVE event logs, which is what this search reads.
2. Zephyr's eight are the transcript files above readable by the study lead only, which I read. Not the same eight.

## Earlier figures, placed

- "40 logs" (audit F, 2026-11-22T19:44Z): consistent with the 39 event logs + the one directory with a student transcript and no
  event log; that is MY READING of the earlier count (the arithmetic fits), not re-derived from audit F's own selection.
- "860 Bash results": the Bash tool_results in the 39 event logs.
- "805 turn rows in 43 files" (earlier today): a different population (included turn files outside these 41 run
  directories); this table counts 739 rows in 41 files.
- "217 files" (my message 2026-11-22T20:19Z): every .jsonl/.json/.log file under the 41 directories, the scope of a recursive grep
  that read all files as owner; superseded here by the per-population rows.

## Reading

In the affected configuration both routes to an unsent turn were open (cell U, 2.1.328 print mode). In these records
neither occurred: no backgrounded task and no moved or timed-out shell command in 39 event logs (read by two seats) and
19 transcript files (read by one seat, me); the one turn-records-only session has no turn long enough to contain a
moved command. Bounds: 2.1.328, the files that exist now, a scan for the harness's own messages.

## Sentence for the public correction (Zephyr's, adopted by Kepler 2026-11-22T20:24Z; keep at exactly this strength)

Quoted exactly from 2026-11-22T20:24Z: "on 2.1.328 in print mode the 120 s move to the background is the default; it was open in
the affected configuration; across every population named in the table there is no occurrence of the move or of a
backgrounded task; the single session that records turns only is covered by relay accounting, to that bound."
