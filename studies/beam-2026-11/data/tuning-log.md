# Tuning log (practice runs; never scored)

Every practice run, and every change made to get the student to use ENGRAM, with its reason and arm 1's
equivalent (Kepler's tuning guard). All runs used tuning conversation 15 of the 100K split, which is
therefore not in the scored set. No arm-versus-arm accuracy is computed on any of them; the practice
questions only show that the pipeline runs. Raw transcripts are not published yet (they contain BEAM
text; licence handling is an open item).

Format v1 = bare `USER:`/`ASSISTANT:` turns, brief only in the first message. Format v2 = marked proctor
messages and reading material (see [../protocol/exam-room.md](../protocol/exam-room.md)).

## Runs, 2026-11-14

| run | format | arm | setup | what happened |
|---|---|---|---|---|
| hello | n/a | 1 | one print-mode turn | Works. Base prompt 24,206 input tokens. The server gave Claude Code requests a 32,768-token context, so a 131,072-token model variant was made. |
| P1 | v1 | 2 | one `claude -p --resume` process per turn; first session not run | FAULT: ENGRAM's SessionStart hook re-fired every turn. 3 exchanges, 45 to 73 s each; ENGRAM's tools were deferred behind tool search, which the student never used; notes in a markdown file; 0 ENGRAM writes. |
| P2 | v1 | 2 | one persistent process; first session run inside the exam session; sandbox inside a git repository | FAULTS: the first session cost 983 s and much of the window; the git repository made ENGRAM refuse transcript citations. The student completed the first session itself (found the deferred tools, wrote nodes, napped unprompted), then read 3 exchanges with markdown notes only, 0 ENGRAM writes. |
| P3 | v1 | 1 | one persistent process, sandbox outside git | 3 exchanges, 5 to 25 s each, accurate markdown notes. |
| P4 | v1 | 1 | P3 + forced `/compact` + 2 practice questions | `/compact` works as a stream-json user message: 14,181 to 5,410 tokens in 33.7 s; the preserved messages are the student's own last reply only. Both practice questions answered from the summary. |
| P5 | v1 | 2 | first session as its own session (393 s), then a fresh exam session; 3 exchanges + `/compact` + 2 practice questions | The student tried to reach ENGRAM's write tools, misread tool search's successful keyword results as failure, guessed wrong exact names, concluded the tools were unreachable, and kept notes in a file. After compaction it answered from its summary, no tools. Of ENGRAM's hooks only the SessionStart (compact) hook left a visible trace at the compaction. |
| v2 | v2 | 1 and 2 | same as P5 per arm | Arm 2, tools still deferred: the student did not look for ENGRAM while reading. When ENGRAM's write check fired it answered "Nothing to record to ENGRAM", treating a bystander exam as outside ENGRAM's scope. |
| E2 | v2 | 2 | six core ENGRAM tools always loaded (sandbox patch), the rest deferred; first session once, then 3 exams from fresh copies | 0 of 3 runs wrote ENGRAM while reading or read it after compaction. Fails the criterion below. |

## Changes made to get ENGRAM used

| # | change | kind | why | arm 1 equivalent |
|---|---|---|---|---|
| 1 | Harness: one persistent student process; first session as its own session; sandboxes outside git | harness fault fix | P1, P2 | same harness for arm 1 |
| 2 | Format v2 (marked proctor and reading material) | exam format | Lei: the student must know what is instruction and what is material | identical for arm 1 |
| 3 | Six core tools always loaded (E2, sandbox only) | product candidate | Lei: make the tools usable before benchmarking; chosen by measured call share on one seat; a second seat agreed on four of the six | none needed (arm 1's memory tools are built in) |
| 4 | Exam line in the user-level `CLAUDE.md` (E3) | instruction | Lei: an exam is not identity-bearing, so the student needs a reason to keep exam facts | identical line in arm 1 |
| 5 | Purpose sentence in the brief (E3) | exam format | the brief said questions come later, not that they come after compaction | identical for arm 1 |

## Pre-written criterion for the reachability experiments (written before E1/E2 ran)

On format v2, with the brief unchanged, "the model can use ENGRAM" means: in at least 2 of 3 short runs
(3 exchanges, forced compaction, 2 practice questions), (a) at least one successful ENGRAM write during
reading and (b) at least one successful ENGRAM read after the compaction. Also measured: prompt tokens
added per session and the first turn's wall time.

## Running now

- **E3**: E2's setup + change 4 + change 5, on the full ENGRAM instruction template. Read against the
  criterion above; a step result, not the entry gate.
- **Talk probe** (Lei's design): E2's setup without the exam line; a normal three-turn conversation with
  the student's own user about its own situation, never naming ENGRAM or note-taking; then `/compact`
  and one recall question. ENGRAM writes here but not in the exam point to an intentional decision;
  writes in neither point to a capability gap.
- Measured so far for that question: in every practice sandbox the student wrote its own ENGRAM nodes
  during the first session (2 person nodes and 2 to 5 observations), and none during any exam reading.
  The first-session skill instructs those writes, so they show capability under instruction only.
