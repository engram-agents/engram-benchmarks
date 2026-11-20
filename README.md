# engram-benchmarks

Pre-registered benchmark studies of agents that use [ENGRAM](https://github.com/engram-agents/engram),
an epistemic memory system for AI agents. Each study keeps its design, its decision history, its
harness and, once run, its data and results together, so a reader can audit not only the numbers but
why the study was built the way it was.

- `METHODOLOGY.md`: the experiment-design conventions every study here follows (pre-register before
  running, validated instruments, measured numbers only, the standard study layout).
- `SCORE-REVIEW-PRINCIPLES.md`: how we review answers against a benchmark's official answer key and report
  a corrected score beside the official one (versioned, with a change log giving the reason for each change).
- `studies/<topic>-<YYYY-MM>/`: one directory per study, in the layout of METHODOLOGY section 4.
- `tools/`: repository tooling (the privacy scan below).

## Studies

| study | question | status |
|---|---|---|
| [`beam-2026-11`](studies/beam-2026-11/) | Does ENGRAM help a small local model remember a long conversation, compared with the same model and harness without it? | design and tuning; nothing scored |

## Privacy rules

This repository is public, and the agents and people who build these studies work on real machines
with real lives. Everything committed here follows these rules, and a reviewer blocks a PR that
breaks one.

1. **No host details.** No home directories, usernames, hostnames, uids, internal ports, IP
   addresses or machine names. Scripts take paths from arguments or environment variables. Say what a
   detail is for ("a sandbox home outside any git repository"), not where it lives.
2. **No personal details.** Nothing about any person's family, health, location, schedule or accounts.
   People appear only as the authors of design decisions, quoted for the decision itself.
3. **No credentials and no operational state.** No tokens, keys or receipts; nothing about which
   machine runs which service, rollout status, or the team's internal channels.
4. **Benchmark data is referenced, not copied.** Datasets are named by their public source and a
   content hash; their files are not redistributed here. Transcripts that contain benchmark text are
   published only after a scrub and under the dataset's licence (see each study's PROVENANCE.md).
5. **Graph content is quoted, not dumped.** A study may quote a node from an agent's memory graph
   when the node is the record of a design decision. It never publishes a graph or a graph export.

**The mechanical half:** `tools/privacy-scan.sh` runs on every pull request and on every push to
`main`. It reads every tracked file and file name at the head; with `--history <range>` it also reads
each commit's message, author and committer identity, and **every line the commit adds**, so a line that
was added and later deleted is still caught. It fails on host paths, user temp paths, email addresses
(other than noreply addresses and the identities listed in `tools/privacy-scan-allowed-identities.txt`),
private IP addresses, private DNS names and local service ports. A line that must mention such a
pattern generically carries the marker `privacy-scan: allow` with a reason, so every exception is
visible.

It runs after a push, so on this public repository it **detects** a leak and cannot prevent one:
whatever is pushed is public at once. Run it locally before every push, on the files and on the
commits you are about to push (`tools/privacy-scan.sh` and `tools/privacy-scan.sh --history <range>`).
A leak that reaches GitHub is an incident: it is removed from the history with the maintainers'
approval, not covered by a later commit, because a deleted line stays readable in the history.
The scan cannot catch rule 2 or rule 5; review does.

**Benchmark text.** No question-with-gold text and no verbatim conversation text from a benchmark dataset is committed
while a study using that conversation is open; commit the file's sha256 and hold the file privately.
`tools/public-text-check.py` enforces this on every pull request and push (CI) and is run locally before every push to
a public branch, in file mode and over the commits being pushed (`--history <range>`), with the pinned dataset.
Exception: none; the check never prints what it matched.
A run of 8 words shared with the dataset counts as a hit; the few windows listed by hash in
`tools/public-text-check-exempt-windows.txt` (each with a reason and an approver, added only after a second seat's read)
are the only windows it lets through.

## Licence

Code and documents: Apache-2.0 (`LICENSE`). Material derived from a benchmark dataset keeps that
dataset's licence, stated in the study's PROVENANCE.md.
