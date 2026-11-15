#!/usr/bin/env python3
"""Draw 2: which BEAM conversations leave the scored set, seeded by drand.

Draw 1 seeded from a commit SHA, which its committer could re-roll.  Draw 2
takes its seed from the randomness of one drand round that is fixed (in
data/draw2-round.json, committed) BEFORE the round exists.  Nobody can
choose the randomness; the only choice, the round number, is public and
committed first.  Python 3 standard library only.

Usage:
    python3 draw-from-beacon.py --plan-round MINUTES     # read-only; prints a round
    python3 draw-from-beacon.py [--out PATH]             # the draw
    python3 draw-from-beacon.py --beacon-json PATH       # hand re-check from a saved response

The BLS signature is NOT verified here (stdlib only).  Anyone can verify it
with a drand client against the chain's public key.  This script checks the
sha256(signature) == randomness link only.
"""
import argparse
import hashlib
import json
import math
import os
import platform
import random
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

# drand default chain (pedersen-bls-chained, 30 s period) and its public API.
CHAIN_HASH = "8990e7a9aaed2ffed73dbd7092123d6f289930540d7651336225dc172e51b2ce"
API = "https://api.drand.sh"

# Repo-relative path of the committed round announcement.
ROUND_FILE = "studies/beam-2026-11/data/draw2-round.json"

# Same values as draw 1 (copied, not imported).  Conversation ids of the 100K
# split below / above the median token length of the 19 eligible conversations.
# "15" (existing tuning conversation) is excluded; the median "7" is in
# neither stratum and stays scored.
STRATUM_100K_LOWER = ["1", "2", "3", "4", "6", "8", "9", "13", "14"]
STRATUM_100K_UPPER = ["5", "10", "11", "12", "16", "17", "18", "19", "20"]
IDS_500K = [str(i) for i in range(1, 36)]
TUNING_EXISTING = ["15"]
MEDIAN_EXCLUDED = "7"

PURPOSE_100K = "entry-gate runs and lean-profile tuning"
PURPOSE_500K_FIRST = "arm-3 training"
PURPOSE_500K_SECOND = "length-stress tuning"
PURPOSE_BOOK_CLOSED = "book-closed second runs (pre-registration section 13)"


def refuse(msg):
    sys.stderr.write("refused: %s\n" % msg)
    sys.exit(1)


def git(args, cwd):
    return subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)


def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "beam-draw/1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def fetch_info():
    try:
        info = http_json("%s/%s/info" % (API, CHAIN_HASH))
    except Exception as e:  # network, HTTP, JSON
        refuse("cannot fetch chain info: %s" % e)
    if info.get("hash") != CHAIN_HASH:
        refuse("chain info hash %r differs from CHAIN_HASH" % info.get("hash"))
    return info


def plan_round(minutes):
    info = fetch_info()
    period, genesis = int(info["period"]), int(info["genesis_time"])
    target = int(time.time()) + minutes * 60
    # drand defines time_of_round(r) = genesis + (r-1)*period and
    # round_at(t) = floor((t-genesis)/period) + 1 (the round CURRENT at t,
    # which was emitted at or up to one period BEFORE t).  To get a round
    # emitted at or after t we need the smallest r with time_of_round(r) >= t,
    # i.e. r = ceil((t-genesis)/period) + 1.
    rnd = math.ceil((target - genesis) / period) + 1
    when = genesis + (rnd - 1) * period
    assert when >= target and when - period < target
    print(json.dumps({
        "chain_hash": CHAIN_HASH,
        "round": rnd,
        "round_time_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(when)),
        "period": period,
        "genesis_time": genesis,
    }, indent=2, sort_keys=True))


def self_checks(lower, upper, ids_100k):
    if set(lower) & set(upper):
        refuse("self-check: strata are not disjoint")
    for bad in TUNING_EXISTING + [MEDIAN_EXCLUDED]:
        if bad in lower or bad in upper:
            refuse("self-check: stratum contains excluded conversation %s" % bad)
    covered = set(lower) | set(upper) | set(TUNING_EXISTING) | {MEDIAN_EXCLUDED}
    if len(lower) + len(upper) + 2 != 20 or covered != set(ids_100k):
        refuse("self-check: strata with 7 and 15 do not cover exactly 1..20")


def check_committed():
    """R1 + R2.  Return (toplevel, full SHA of the commit that added ROUND_FILE)."""
    script = os.path.realpath(__file__)
    top = git(["rev-parse", "--show-toplevel"], os.path.dirname(script))
    if top.returncode != 0:
        refuse("script is not inside a git repository")
    top_dir = os.path.realpath(top.stdout.strip())
    srel = os.path.relpath(script, top_dir)
    paths = [ROUND_FILE, srel]
    # git pathspecs are cwd-relative; run everything from the toplevel.
    for p in paths:
        if git(["ls-files", "--error-unmatch", "--", p], top_dir).returncode != 0:
            refuse("%s is untracked (not committed)" % p)
    if git(["diff", "--quiet", "HEAD", "--"] + paths, top_dir).returncode != 0:
        refuse("round file or script has uncommitted changes relative to HEAD")
    log = git(["log", "--diff-filter=A", "--format=%H", "--", ROUND_FILE], top_dir)
    shas = [s for s in log.stdout.split() if s]
    if len(shas) != 1:
        refuse("%d commits add the round file; expected exactly one" % len(shas))
    if git(["diff", "--quiet", shas[0], "HEAD", "--"] + paths, top_dir).returncode != 0:
        refuse("round file or script differs from the commit that added the round "
               "file; the draw must use the rules as first published")
    return top_dir, shas[0]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plan-round", type=int, metavar="MINUTES",
                    help="print a round emitted at least MINUTES from now (>= 10); writes nothing")
    ap.add_argument("--beacon-json", help="use a saved beacon response instead of the network")
    ap.add_argument("--out", help="also write the JSON to this path")
    args = ap.parse_args()

    if args.plan_round is not None:
        if args.plan_round < 10:
            refuse("--plan-round MINUTES must be an integer >= 10")
        plan_round(args.plan_round)
        return

    # R1, R2
    top_dir, round_commit = check_committed()
    # R3
    try:
        with open(os.path.join(top_dir, ROUND_FILE)) as f:
            rf = json.load(f)
        want_round = int(rf["round"])
    except Exception as e:
        refuse("cannot read round file: %s" % e)
    if rf.get("chain_hash") != CHAIN_HASH:
        refuse("round file chain_hash differs from CHAIN_HASH")

    # R4
    if args.beacon_json:
        source = "file"
        try:
            with open(args.beacon_json) as f:
                beacon = json.load(f)
        except Exception as e:
            refuse("cannot read --beacon-json: %s" % e)
    else:
        source = "api"
        info = fetch_info()
        emitted_at = int(info["genesis_time"]) + (want_round - 1) * int(info["period"])
        if emitted_at > time.time():
            refuse("round %d not yet available" % want_round)
        try:
            beacon = http_json("%s/%s/public/%d" % (API, CHAIN_HASH, want_round))
        except urllib.error.HTTPError as e:
            refuse("round %d not yet available (HTTP %d)" % (want_round, e.code))
        except Exception as e:
            refuse("cannot fetch round %d: %s" % (want_round, e))
    if beacon.get("round") != want_round:
        refuse("beacon round %r != requested round %d" % (beacon.get("round"), want_round))

    # R5.  drand (pedersen-bls-chained): randomness = sha256(signature).  The BLS
    # signature itself is NOT verified by this script; only this hash link is.
    sig, rnd_hex = beacon.get("signature", ""), beacon.get("randomness", "")
    try:
        ok = hashlib.sha256(bytes.fromhex(sig)).hexdigest() == rnd_hex
    except ValueError:
        ok = False
    if not ok or not re.fullmatch(r"[0-9a-f]{64}", rnd_hex):
        refuse("randomness is not sha256(signature)")

    # R6
    ids_100k = [str(i) for i in range(1, 21)]
    lower = sorted(STRATUM_100K_LOWER, key=int)
    upper = sorted(STRATUM_100K_UPPER, key=int)
    self_checks(lower, upper, ids_100k)

    # Draw order is part of the contract.
    seed_int = int(rnd_hex, 16)
    rng = random.Random(seed_int)
    pick_lower = rng.sample(lower, 1)[0]
    pick_upper = rng.sample(upper, 1)[0]
    k500 = rng.sample(sorted(IDS_500K, key=int), 2)
    out_ids = set(TUNING_EXISTING) | {pick_lower, pick_upper}
    scored = sorted((i for i in ids_100k if i not in out_ids), key=int)
    if len(scored) != 17:
        refuse("self-check: scored_set_count is %d, expected 17" % len(scored))
    book_closed = rng.sample(scored, 3)

    draws = [
        {"split": "100K", "conversation_id": pick_lower, "stratum": "lower", "purpose": PURPOSE_100K},
        {"split": "100K", "conversation_id": pick_upper, "stratum": "upper", "purpose": PURPOSE_100K},
        {"split": "500K", "conversation_id": k500[0], "stratum": None, "purpose": PURPOSE_500K_FIRST},
        {"split": "500K", "conversation_id": k500[1], "stratum": None, "purpose": PURPOSE_500K_SECOND},
    ] + [
        {"split": "100K", "conversation_id": c, "stratum": None, "purpose": PURPOSE_BOOK_CLOSED}
        for c in book_closed
    ]

    with open(os.path.realpath(__file__), "rb") as f:
        script_sha = hashlib.sha256(f.read()).hexdigest()
    b = {"chain_hash": CHAIN_HASH, "round": want_round, "randomness": rnd_hex,
         "signature": sig, "source": source}
    if "previous_signature" in beacon:
        b["previous_signature"] = beacon["previous_signature"]
    result = {
        "beacon": b,
        "beacon_source": source,
        "bls_signature_verified": False,
        "bls_note": "BLS signature not verified by this script; sha256(signature)==randomness was checked",
        "seed_int": str(seed_int),
        "python_version": platform.python_version(),
        "round_file_commit": round_commit,
        "script_sha256": script_sha,
        "draws": draws,
        "scored_set_100K": scored,
        "scored_set_count": len(scored),
        "book_closed": book_closed,
    }
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.out:
        with open(args.out, "w") as f:
            f.write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
