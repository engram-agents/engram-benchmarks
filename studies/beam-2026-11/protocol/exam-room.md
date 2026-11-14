# The exam room

How one BEAM conversation is delivered to a student, compacted, and examined. The rules come from the
decision log in [../PROVENANCE.md](../PROVENANCE.md); the harness that implements them is in
[../tools/](../tools/).

**Single source for every text the student sees.** The brief, the proctor's turn line, the reading-
material wrapper, the question prompts, the first-session fact sheet and its nudge are constants in
`tools/feed.py` and `tools/feed2.py`, and nowhere else. This page describes them; it does not copy
them, so the two cannot drift. When the texts are frozen for registration, their sha256 values go in
the pre-registration.

## Roles

- **Student**: Claude Code driving `qwen3.8:27b` (see the pre-registration for versions). Arm 2 adds
  ENGRAM.
- **Proctor**: the study lead, through the harness. Every proctor message starts with `[EXAM PROCTOR]`,
  except `/compact`, which is a Claude Code command and must stand alone.
- **Reading material**: one BEAM exchange at a time. Never an instruction to the student.

## Message format (v2; Lei's ruling that proctor text and reading material be told apart)

1. The first user message is the brief followed by exchange 1. The brief tells the student it is a
   quiet bystander to a conversation between two other parties, that only `[EXAM PROCTOR]` messages are
   instructions, that the conversation will be followed by questions, that it may take whatever notes
   it chooses in whatever way it chooses, and that it ends each reply with `NEXT`. It names no files,
   no memory system and no note method.
2. Every later user message is the proctor's one fixed sentence followed by one exchange, wrapped as:
   `<<< READING MATERIAL (conversation session N, time anchor T) >>>`, then `CONVERSATION USER:` and
   `CONVERSATION ASSISTANT:` blocks, then `<<< END OF READING MATERIAL >>>`. The speakers are relabelled
   so they never collide with the student's own user and assistant roles. The time anchor is the last
   anchor BEAM set in that session (BEAM sets it on some messages only).
3. Under test (tuning log, E3): a purpose sentence added to the brief, telling the student that the
   questions come after its context has been compacted. Identical in both arms if adopted.

## Instruction files

- An identical exam line at the top of the student's user-level `CLAUDE.md` in every arm (text in the
  pre-registration, section 4).
- Each arm's own memory-practice text, at comparable length (pre-registration, section 4).

## Sequence

1. Arm 2 only, before the exam and as its own session: ENGRAM's first session, driven by the fixed
   fact sheet. Nothing in it comes from BEAM.
2. The exam session: brief + exchanges, one per user message, in dataset order.
3. `/compact`, sent by the proctor as a user message, in both arms.
4. The post-compaction check (no raw conversation text in the window). This is an analysis step on
   the logged events, not code in the harness. A notes file the student wrote may come back into the
   window by itself: after compaction Claude Code re-reads up to five recently edited files. That is
   the student's own record and is allowed.
5. The probing questions, one per user message, in the same session.

## Escalation

The student may run `ask-proctor "<question>"`. The question is written where the proctor watches; the
proctor answers questions about the exam procedure and environment only, never about the conversation.
Every question and answer is logged with UTC times and published with the results.

## Sandboxes

Each run gets its own home directory, Claude Code configuration and ENGRAM data directory, outside any
git repository (inside one, ENGRAM refused the student's transcript citations in practice). No run ever
touches a real user's memory graph. The model is unloaded after each run.
