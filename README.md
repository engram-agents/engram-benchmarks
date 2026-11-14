# engram-benchmarks

Pre-registered benchmark studies of agents that use [ENGRAM](https://github.com/engram-agents/engram),
an epistemic memory system for AI agents. Each study keeps its design, its decision history, its
harness and, once run, its data and results together, so a reader can audit not only the numbers but
why the study was built the way it was.

- `METHODOLOGY.md`: the experiment-design conventions every study here follows (pre-register before
  running, validated instruments, measured numbers only, the standard study layout).
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
`main`. It fails on host paths, user temp paths, email addresses (other than commit-trailer noreply
addresses), private IP addresses and local service ports. A line that must mention such a pattern
generically carries the marker `privacy-scan: allow` with a reason, so every exception is visible.
The scan cannot catch rule 2 or rule 5; review does.

## Licence

Code and documents: Apache-2.0 (`LICENSE`). Material derived from a benchmark dataset keeps that
dataset's licence, stated in the study's PROVENANCE.md.
