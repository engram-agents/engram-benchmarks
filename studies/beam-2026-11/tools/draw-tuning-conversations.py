#!/usr/bin/env python3
"""Draw which BEAM conversations leave the scored set (tuning / training).

The seed is the first 8 hex digits of the SHA of the git commit that ADDED
this script, so nobody can choose it before the script is published.
Python 3 standard library only.  See studies/beam-2026-11/data/draw-rule.md.

Usage:
    python3 draw-tuning-conversations.py [--out PATH]
    python3 draw-tuning-conversations.py --seed-hex 0123abcd   # hand re-check
"""
import argparse
import json
import os
import platform
import random
import re
import subprocess
import sys

# Conversation ids of the 100K split below / above the median token length of
# the 19 eligible conversations (data/draw-rule.md has the token table).
# Conversation "15" (existing tuning conversation) is excluded; the median
# conversation "7" belongs to neither stratum and stays scored.
STRATUM_100K_LOWER = ["1", "2", "3", "4", "6", "8", "9", "13", "14"]
STRATUM_100K_UPPER = ["5", "10", "11", "12", "16", "17", "18", "19", "20"]
# The 500K split's 35 conversation_ids (BEAM dataset, 500K parquet).
IDS_500K = [str(i) for i in range(1, 36)]
# "15": the existing tuning conversation; "7": the median, stays scored.
TUNING_EXISTING = ["15"]
MEDIAN_EXCLUDED = "7"

# Provenance of the parquet files (Hugging Face dataset Mohammadta/BEAM,
# files data/100K-00000-of-00001.parquet and data/500K-00000-of-00001.parquet).
# This script does not read them; the hashes are recorded in its output.
PARQUET_SHA256 = {
    "100K": "c0519be25907005ba873c927c50877471d550873039d96c041554d0075a78ace",
    "500K": "af05921c979355038e1761b7cde3d2dd713200dd3071b278de0200f6c7f30122",
}

PURPOSE_100K = "entry-gate runs and lean-profile tuning"
PURPOSE_500K_FIRST = "arm-3 training"
PURPOSE_500K_SECOND = "length-stress tuning"


def refuse(msg):
    sys.stderr.write("refused: %s\n" % msg)
    sys.exit(1)


def git(args, cwd):
    return subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)


def seed_from_git():
    """Return (full_sha, seed_hex) of the single commit that added this file."""
    script = os.path.realpath(__file__)
    here = os.path.dirname(script)
    top = git(["rev-parse", "--show-toplevel"], here)
    if top.returncode != 0:
        refuse("script is not inside a git repository")
    top_dir = os.path.realpath(top.stdout.strip())
    rel = os.path.relpath(script, top_dir)
    here = top_dir  # git pathspecs are cwd-relative; rel is repo-root-relative
    tracked = git(["ls-files", "--error-unmatch", "--", rel], here)
    if tracked.returncode != 0:
        refuse("script is untracked (not committed); the draw must come from the committed script")
    log = git(["log", "--diff-filter=A", "--format=%H", "--", rel], here)
    if log.returncode != 0:
        refuse("git log failed: %s" % log.stderr.strip())
    shas = [s for s in log.stdout.split() if s]
    if len(shas) == 0:
        refuse("no commit adds this script (never committed)")
    if len(shas) > 1:
        refuse("%d commits add this script; expected exactly one" % len(shas))
    if git(["diff", "--quiet", "HEAD", "--", rel], here).returncode != 0:
        refuse("script has uncommitted changes relative to HEAD")
    if git(["diff", "--quiet", shas[0], "HEAD", "--", rel], here).returncode != 0:
        refuse("script differs from the version in the commit that added it; "
               "the draw must use the rules as first published")
    return shas[0], shas[0][:8]


def self_checks(lower, upper, ids_100k):
    if set(lower) & set(upper):
        refuse("self-check: strata are not disjoint")
    for bad in TUNING_EXISTING + [MEDIAN_EXCLUDED]:
        if bad in lower or bad in upper:
            refuse("self-check: stratum contains excluded conversation %s" % bad)
    covered = set(lower) | set(upper) | set(TUNING_EXISTING) | {MEDIAN_EXCLUDED}
    if len(lower) + len(upper) + 2 != 20 or covered != set(ids_100k):
        refuse("self-check: strata with 7 and 15 do not cover exactly 1..20")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seed-hex", help="8 lowercase hex chars; replaces the git-derived seed")
    ap.add_argument("--out", help="also write the JSON to this path")
    args = ap.parse_args()

    ids_100k = [str(i) for i in range(1, 21)]
    lower = sorted(STRATUM_100K_LOWER, key=int)
    upper = sorted(STRATUM_100K_UPPER, key=int)
    self_checks(lower, upper, ids_100k)

    if args.seed_hex is not None:
        if not re.fullmatch(r"[0-9a-f]{8}", args.seed_hex):
            refuse("--seed-hex must be exactly 8 lowercase hex characters")
        source, commit, seed_hex = "argument", None, args.seed_hex
    else:
        commit, seed_hex = seed_from_git()
        source = "git-add-commit"
    seed_int = int(seed_hex, 16)

    # Draw order is part of the contract.
    rng = random.Random(seed_int)
    pick_lower = rng.sample(lower, 1)[0]
    pick_upper = rng.sample(upper, 1)[0]
    k500 = rng.sample(sorted(IDS_500K, key=int), 2)

    if k500[0] == k500[1]:
        refuse("self-check: the two 500K picks are identical")
    draws = [
        {"split": "100K", "conversation_id": pick_lower, "stratum": "lower", "purpose": PURPOSE_100K},
        {"split": "100K", "conversation_id": pick_upper, "stratum": "upper", "purpose": PURPOSE_100K},
        {"split": "500K", "conversation_id": k500[0], "stratum": None, "purpose": PURPOSE_500K_FIRST},
        {"split": "500K", "conversation_id": k500[1], "stratum": None, "purpose": PURPOSE_500K_SECOND},
    ]
    out_ids = set(TUNING_EXISTING) | {pick_lower, pick_upper}
    scored = sorted((i for i in ids_100k if i not in out_ids), key=int)
    if len(scored) != 17:
        refuse("self-check: scored_set_count is %d, expected 17" % len(scored))

    result = {
        "seed_source": source,
        "seed_commit": commit,
        "seed_hex": seed_hex,
        "seed_int": seed_int,
        "python_version": platform.python_version(),
        "parquet_sha256": PARQUET_SHA256,
        "draws": draws,
        "scored_set_100K": scored,
        "scored_set_count": len(scored),
    }
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.out:
        with open(args.out, "w") as f:
            f.write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
