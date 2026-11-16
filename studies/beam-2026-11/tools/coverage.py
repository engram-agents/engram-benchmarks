#!/usr/bin/env python3
"""BEAM speed pilots: coverage attribution (tuning log, PR 3, entry accepted at 5e3970bd).

A source exchange is COVERED if at least one store node created during its ROUND carries text that occurs in that
exchange, under three rules:
  1. minimum match MIN characters (default 40) after normalising whitespace and case;
  2. quote first: credit on the node's verified quote; a claim-only match is a separate, weaker column;
  3. ambiguity: a matching window that occurs in more than one exchange of the same round credits none of them;
     a node whose matching windows are all shared is counted as ambiguous.
The OLD rule (criterion 1) for comparison: an exchange is covered if any node was created during it.
Matching is against the exchange's CONTENT only (the user's and assistant's text), never feed.render's wrapper.

  python3 coverage.py controls
      the controls, each with a mutant that must make it fail (one non-flipping variant kept as INFO)
  BEAM_PARQUET=<100K parquet> python3 coverage.py runA --run-dir DIR --run-start ISO8601 [--conv 9] [--span 45]
      a k = 1 run's coverage under both rules at MIN = 20 / 40 / 80, plus a real-data shifted-attribution control.
      DIR holds the run's turns.jsonl (under run/) and the student's saved store (knowledge-after.db).
feed.py (the renderer the student read) is imported from --feed-dir, default this file's own directory.
"""
import argparse, json, os, re, sqlite3, sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))


def norm(s):
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


WRAPPER_LABELS = ("CONVERSATION USER:", "CONVERSATION ASSISTANT:")


def content_only(rendered):
    """Strip feed.render's fixed wrapper (turn line, BEGIN line with session and time anchor, END line, and the two
    speaker labels), leaving the user's and the assistant's text. Matching against the wrapper credited a node that
    quoted only the rendered header in every exchange carrying it (found 2026-11-16 by the shift control)."""
    lines = rendered.split("\n")
    body = lines[2:-1]  # drop TURN_LINE, the BEGIN line, and END
    return "\n".join(l for l in body if l.strip() not in WRAPPER_LABELS)


def windows(text, n):
    """Every length-n window of normalised text (one window if the text is exactly n long)."""
    t = norm(text)
    return {t[i:i + n] for i in range(0, len(t) - n + 1)} if len(t) >= n else set()


def credit(node_text, round_exchanges, texts, min_len, ambiguity=True):
    """Return (credited exchange ids, ambiguous flag) for one node's text within one round."""
    hits = {}  # window -> exchanges of the round containing it
    nt = {e: norm(texts[e]) for e in round_exchanges}
    for w in windows(node_text, min_len):
        where = [e for e in round_exchanges if w in nt[e]]
        if where:
            hits[w] = where
    if not hits:
        return set(), False
    if not ambiguity:  # MUTANT used only by the controls: ignores rule 3
        return {e for v in hits.values() for e in v}, False
    unique = {v[0] for v in hits.values() if len(v) == 1}
    return unique, not unique


def coverage(rounds, texts, nodes, min_len, ambiguity=True):
    """rounds: list of lists of exchange ids. nodes: dicts with round index, quote, claim.
    Returns per-exchange quote credit, claim-only credit, and ambiguous-node count."""
    by_quote = {e: 0 for r in rounds for e in r}
    by_claim_only = {e: 0 for r in rounds for e in r}
    ambiguous = 0
    for n in nodes:
        r = rounds[n["round"]]
        got, amb = credit(n["quote"], r, texts, min_len, ambiguity)
        ambiguous += amb
        for e in got:
            by_quote[e] += 1
        if not got:
            got_c, _ = credit(n["claim"], r, texts, min_len, ambiguity)
            for e in got_c:
                by_claim_only[e] += 1
    return by_quote, by_claim_only, ambiguous


# ---------------------------------------------------------------- controls
def controls():
    u = lambda tag: f"unique passage {tag} " + " ".join(f"{tag}word{i}" for i in range(12))  # > 80 chars, unique
    shared = "this exact shared sentence appears verbatim in two neighbouring exchanges of one round."
    texts = {1: "alpha " + u("a"), 2: "beta " + u("b"), 3: "gamma " + u("c"),
             4: "delta " + u("d") + " " + shared, 5: "epsilon " + u("e") + " " + shared, 6: "zeta " + u("f")}
    rounds = [[1, 2, 3], [4, 5, 6]]
    out, ok = [], True

    def show(name, got, want, note):
        nonlocal ok
        passed = got == want
        ok &= passed
        out.append(f"{'PASS' if passed else 'FAIL'}  {name}: got {got}, want {want}  ({note})")

    # Control 1: a planted node per exchange is credited to exactly that exchange.
    nodes = [dict(round=0 if e <= 3 else 1, quote=u("abcdef"[e - 1])[:60], claim="") for e in range(1, 7)]
    q, _, amb = coverage(rounds, texts, nodes, 40)
    show("control 1, planted node per exchange", (q, amb), ({e: 1 for e in range(1, 7)}, 0),
         "each exchange credited once, nothing ambiguous")
    # Control 2: a node quoting only exchange j is not credited to j + 1 (same round).
    q, _, _ = coverage(rounds, texts, [dict(round=0, quote=u("a")[:60], claim="")], 40)
    show("control 2, quote of j only", (q[1], q[2]), (1, 0), "credited to exchange 1, not to exchange 2")
    # Control 3: a node quoting text shared by j and j + 1 is credited to neither and counted ambiguous.
    q, _, amb = coverage(rounds, texts, [dict(round=1, quote=shared, claim="")], 40)
    show("control 3, shared text", (q[4], q[5], amb), (0, 0, 1), "credited to neither, counted ambiguous")
    # Mutants: each must make its control fail.
    q, _, amb = coverage(rounds, texts, [dict(round=1, quote=shared, claim="")], 40, ambiguity=False)
    show("mutant of control 3 (rule 3 off)", (q[4], q[5], amb) != (0, 0, 1), True,
         f"without the ambiguity rule the shared quote credits 4 and 5: {(q[4], q[5])}")
    # Kept, and reported as NON-DISCRIMINATING (first attempt, 2026-11-16): lowering the minimum cannot make control 2
    # fail, because any window of a quote taken only from exchange j also occurs in j, so rule 3 already blocks credit
    # to j + 1. Control 2 therefore tests the round/ambiguity logic, not the minimum length; control 4 tests that.
    q, _, _ = coverage(rounds, texts, [dict(round=0, quote=u("a")[:60], claim="")], 1)
    out.append(f"INFO  min-1 variant of control 2 (expected NOT to flip, see comment): exchange 2 credit = {q[2]}")
    # Control 4 (the minimum-length rule): a node whose quote comes from OUTSIDE its round and shares only a
    # 14-character string with one exchange of the round is credited to nothing at 40 characters.
    texts4 = dict(texts); texts4[6] = texts[6] + " short marker!"
    outside = "text from an earlier round that ends with short marker! and nothing else from this round at all"
    q, _, _ = coverage(rounds, texts4, [dict(round=1, quote=outside, claim="")], 40)
    show("control 4, short coincidental match", q[6], 0, "a 14-character coincidence credits nothing at 40")
    q, _, _ = coverage(rounds, texts4, [dict(round=1, quote=outside, claim="")], 10)
    show("mutant of control 4 (min match 10)", q[6] > 0, True,
         f"at a 10-character minimum the same coincidence credits exchange 6: {q[6]}")
    q, _, _ = coverage(rounds, texts, [dict(round=0, quote="", claim=u("a")[:60])], 40)
    show("quote-first check (claim-only node)", q[1], 0, "a claim-only match never counts toward the quote column")
    # Control 5 (content only): a node quoting only the rendered wrapper credits nothing; mutant keeps the wrapper.
    hdr = "<<< BEGIN CONVERSATION MATERIAL (conversation session 1, time anchor March-15-2024) >>>"
    rend = {e: f"TURN\n{hdr}\nCONVERSATION USER:\n{texts[e]}\n\nCONVERSATION ASSISTANT:\nok\nEND" for e in (1, 2, 3)}
    node = [dict(round=0, quote=hdr, claim="")]
    q, _, _ = coverage([[1], [2], [3]], {e: content_only(r) for e, r in rend.items()},
                       [dict(node[0], round=1)], 40)
    show("control 5, wrapper-only quote", q[2], 0, "a quote of the rendered header credits nothing")
    q, _, _ = coverage([[1], [2], [3]], rend, [dict(node[0], round=1)], 40)
    show("mutant of control 5 (wrapper kept)", q[2] > 0, True, f"matching the rendered text credits it: {q[2]}")
    print("\n".join(out))
    print("CONTROLS:", "ALL PASS" if ok else "FAILED")
    return 0 if ok else 1


# ---------------------------------------------------------------- run A
def run_a(a):
    span, run_dir = a.span, a.run_dir
    sys.path.insert(0, a.feed_dir)
    import pyarrow.parquet as pq
    from feed import exchanges
    parquet = os.environ.get("BEAM_PARQUET") or sys.exit("set BEAM_PARQUET to the BEAM 100K parquet file")
    conv = next(c for c in pq.read_table(parquet).to_pylist() if str(c["conversation_id"]) == str(a.conv))
    rendered = {i + 1: t for i, t in enumerate(exchanges(conv))}
    texts = {e: content_only(r) for e, r in rendered.items()}
    turns = [json.loads(l) for l in open(os.path.join(run_dir, "run/turns.jsonl"))]
    ex = sorted((t for t in turns if t["kind"] == "exchange"), key=lambda t: t["i"])
    assert [t["i"] for t in ex] == list(range(1, len(ex) + 1)), "exchange turns are not 1..N"
    ends = [datetime.fromisoformat(a.run_start.replace("Z", "+00:00"))] + [datetime.fromisoformat(t["utc_end"]) for t in ex]
    db = sqlite3.connect("file:" + os.path.join(run_dir, "knowledge-after.db") + "?mode=ro", uri=True)
    obs = db.execute("select id, created_at, quoted_text, claim from nodes where type like 'observation%'").fetchall()
    nodes, per_old = [], {j: 0 for j in range(1, span + 1)}
    before = after = 0
    for nid, created, quote, claim in obs:
        t = datetime.fromisoformat(created)
        j = next((k for k in range(1, len(ends)) if ends[k - 1] < t <= ends[k]), None)
        if j is None:
            before += t <= ends[0]; after += t > ends[-1]
            continue
        if j <= span:
            per_old[j] += 1
            nodes.append(dict(round=j - 1, quote=quote or "", claim=claim or "", id=nid))
    rounds = [[j] for j in range(1, span + 1)]
    print(f"run in {os.path.basename(os.path.normpath(run_dir))}, conversation {a.conv}, exchanges 1..{span}: {len(nodes)} observation nodes created in span "
          f"(excluded: {before} before the run started, {after} after reading ended or outside every exchange window)")
    old = sum(1 for j in per_old if per_old[j] > 0)
    print(f"notes per source exchange (store-confirmed observations created in the span): "
          f"{len(nodes)}/{span} = {len(nodes) / span:.2f}")
    print(f"OLD rule (any node created during the exchange): {old}/{span} = {old / span:.3f}")
    for m in (20, 40, 80):
        q, c, amb = coverage(rounds, texts, nodes, m)
        cov = sum(1 for e in q if q[e] > 0)
        cov_c = sum(1 for e in q if q[e] == 0 and c[e] > 0)
        tag = "  <- decision setting" if m == 40 else ""
        print(f"NEW rule, min {m:>2} chars: quote-credited {cov}/{span} = {cov / span:.3f}; "
              f"claim-only (weaker column) adds {cov_c}; ambiguous nodes {amb}{tag}")
    unmatched = [n["id"] for n in nodes if not credit(n["quote"], rounds[n["round"]], texts, 40)[0]]
    print(f"nodes whose quote matches nothing in their own exchange at 40 chars: {len(unmatched)} "
          f"(first ids: {unmatched[:8]})")
    print("note: every observation in this store has quote_verified = True, so rule 2 does not filter here")
    lens = sorted(len(n["quote"]) for n in nodes)
    pct = lambda p: lens[min(len(lens) - 1, int(p * len(lens)))]
    print(f"quote length (chars): min {lens[0]}, p25 {pct(.25)}, median {pct(.5)}, p75 {pct(.75)}, max {lens[-1]}; "
          f"under 40: {sum(1 for x in lens if x < 40)}")
    # Real-data negative control: attribute every node to the exchange `shift` places later (wrapping in the span).
    shift = 5
    shifted = [dict(n, round=(n["round"] + shift) % span) for n in nodes]
    q, _, _ = coverage(rounds, texts, shifted, 40)
    cov = sum(1 for e in q if q[e] > 0)
    why = {}
    for n in shifted:
        s = rounds[n["round"]][0]
        if credit(n["quote"], [s], texts, 40)[0]:
            m = [w for w in windows(n["quote"], 40) if w in norm(texts[s])]
            own = n["round"] - shift
            why[n["id"]] = "repeated in own exchange too" if any(w in norm(texts[(own % span) + 1]) for w in m) \
                else "matches the shifted exchange only"
    from collections import Counter
    print(f"REAL-DATA NEGATIVE CONTROL: every node attributed {shift} exchanges late -> quote-credited {cov}/{span} "
          f"at 40 chars ({len(why)} nodes credited: {dict(Counter(why.values()))})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["controls", "runA"])
    ap.add_argument("--span", type=int, default=45)
    ap.add_argument("--conv", type=int, default=9)
    ap.add_argument("--run-dir"); ap.add_argument("--run-start", help="the run's start, ISO 8601 UTC")
    ap.add_argument("--feed-dir", default=HERE)
    a = ap.parse_args()
    if a.what == "runA" and not (a.run_dir and a.run_start):
        ap.error("runA needs --run-dir and --run-start")
    sys.exit(controls() if a.what == "controls" else (run_a(a) or 0))
