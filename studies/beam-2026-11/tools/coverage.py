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
  BEAM_PARQUET=<100K parquet> python3 coverage.py run --run-dir DIR --run-start ISO8601 [--conv 9] [--span 45]
      (runA is an alias)
      a k = 1 run's coverage under both rules at MIN = 20 / 40 / 80, plus a real-data shifted-attribution control.
      DIR holds the run's turns.jsonl (under run/) and the student's saved store (knowledge-after.db).
feed.py (the renderer the student read) is imported from --feed-dir, default this file's own directory.
"""
import argparse, json, os, re, sqlite3, sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))


def norm(s):
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


USER_LABEL, ASSISTANT_LABEL = "CONVERSATION USER:", "CONVERSATION ASSISTANT:"


def load_feed(feed_dir):
    """The renderer the student read (feed.py), whose own constants define the wrapper."""
    sys.path.insert(0, feed_dir)
    import feed
    return feed


def content_only(rendered, fd):
    """Return the user's and the assistant's text of ONE exchange rendered by fd.render, parsed against fd's own
    wrapper constants. Raises ValueError if the text is not exactly that shape: a render that changed by a line must
    fail loud, never silently drop content or keep wrapper (design owner, 2026-11-16). Matching against the wrapper
    credited a node that quoted only the rendered header in every exchange carrying it (found by the shift control)."""
    pat = (re.escape(fd.TURN_LINE) + r"\n" + re.escape(fd.BEGIN) + r" \(conversation session \d+, time anchor [^\n]*\) >>>\n"
           + re.escape(USER_LABEL) + r"\n(?P<user>.*?)\n\n" + re.escape(ASSISTANT_LABEL) + r"\n(?P<assistant>.*)\n"
           + re.escape(fd.END))
    m = re.fullmatch(pat, rendered, re.DOTALL)
    if not m:
        raise ValueError("not a single exchange in feed.render's shape: " + repr(rendered[:120]))
    return m.group("user") + "\n\n" + m.group("assistant")


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
def controls(fd):
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
    # Control 5 (content only), on feed.render's REAL output: a node quoting only the session line credits nothing;
    # mutant: matching the rendered text (wrapper kept) credits it.
    rend = {e: fd.render(e, 1, "March-15-2024", texts[e], "ok") for e in (1, 2, 3)}
    hdr = rend[2].split("\n")[1]
    q, _, _ = coverage([[1], [2], [3]], {e: content_only(r, fd) for e, r in rend.items()},
                       [dict(round=1, quote=hdr, claim="")], 40)
    show("control 5, wrapper-only quote", q[2], 0, "a quote of the rendered session line credits nothing")
    q, _, _ = coverage([[1], [2], [3]], rend, [dict(round=1, quote=hdr, claim="")], 40)
    show("mutant of control 5 (wrapper kept)", q[2] > 0, True, f"matching the rendered text credits it: {q[2]}")
    # Control 6, the parser itself: content_only refuses any render that is not exactly feed.render's shape.
    good = rend[1]
    try:
        content_only(good, fd); refused_good = False
    except ValueError:
        refused_good = True
    show("control 6, parser accepts a real render", refused_good, False, "feed.render's own output parses")
    bad = good.replace("\n", "\nAN EXTRA HEADER LINE\n", 1)
    try:
        content_only(bad, fd); refused = False
    except ValueError:
        refused = True
    show("mutant of control 6 (an extra header line)", refused, True, "a render changed by one line fails loud")
    print("\n".join(out))
    print("CONTROLS:", "ALL PASS" if ok else "FAILED")
    return 0 if ok else 1


# ---------------------------------------------------------------- a run (any k)
def run(a):
    """Coverage and speed measures for one run. Rounds come from each turn row's 'exchanges' list (written by the
    k-feeder); a row without it is a k = 1 round carrying exchange i."""
    span, run_dir = a.span, a.run_dir
    fd = load_feed(a.feed_dir)
    import pyarrow.parquet as pq
    from collections import Counter
    parquet = os.environ.get("BEAM_PARQUET") or sys.exit("set BEAM_PARQUET to the BEAM 100K parquet file")
    conv = next(c for c in pq.read_table(parquet).to_pylist() if str(c["conversation_id"]) == str(a.conv))
    rendered = {i + 1: t for i, t in enumerate(fd.exchanges(conv))}
    texts = {e: content_only(r, fd) for e, r in rendered.items()}
    turns = [json.loads(l) for l in open(os.path.join(run_dir, "run/turns.jsonl"))]
    rows = sorted((t for t in turns if t["kind"] == "exchange"), key=lambda t: t["i"])
    all_rounds = [r.get("exchanges") or [r["i"]] for r in rows]
    flat = [e for r in all_rounds for e in r]
    assert flat == list(range(1, len(flat) + 1)), "rounds do not carry exchanges 1..N in order"
    k = max(len(r) for r in all_rounds)
    keep = [i for i, r in enumerate(all_rounds) if max(r) <= span]   # rounds wholly inside the span
    assert sum(len(all_rounds[i]) for i in keep) == span, f"span {span} does not end on a round boundary (k = {k})"
    rounds = [all_rounds[i] for i in keep]
    ends = [datetime.fromisoformat(a.run_start.replace("Z", "+00:00"))] + [datetime.fromisoformat(r["utc_end"]) for r in rows]
    db = sqlite3.connect("file:" + os.path.join(run_dir, "knowledge-after.db") + "?mode=ro", uri=True)
    obs = db.execute("select id, created_at, quoted_text, claim, metadata from nodes where type like 'observation%'").fetchall()
    nodes, per_old = [], {e: 0 for e in range(1, span + 1)}
    before = after = unverified = 0
    for nid, created, quote, claim, meta in obs:
        t = datetime.fromisoformat(created)
        ri = next((x for x in range(1, len(ends)) if ends[x - 1] < t <= ends[x]), None)
        if ri is None:
            before += t <= ends[0]; after += t > ends[-1]
            continue
        ri -= 1
        if ri >= len(keep):
            continue
        verified = json.loads(meta or "{}").get("quote_verified") is True
        unverified += not verified
        for e in all_rounds[ri]:
            per_old[e] += 1   # OLD rule at k = 1; at k > 1 every exchange of the round gets the round's nodes
        nodes.append(dict(round=ri, quote=(quote or "") if verified else "", claim=claim or "", id=nid,
                          verified=verified))
    print(f"run in {os.path.basename(os.path.normpath(run_dir))}, conversation {a.conv}, exchanges 1..{span}: {len(nodes)} observation nodes created in span "
          f"(excluded: {before} before the run started, {after} after reading ended or outside every exchange window)")
    old = sum(1 for e in per_old if per_old[e] > 0)
    print(f"notes per source exchange (store-confirmed observations created in the span): "
          f"{len(nodes)}/{span} = {len(nodes) / span:.2f}")
    if k == 1:
        print(f"OLD rule (any node created during the exchange): {old}/{span} = {old / span:.3f}")
    else:
        print(f"OLD rule at the ROUND level (any node created during the exchange's round; with k = {k} every exchange "
              f"of a round gets the round's nodes, so this is trivially high and not comparable with k = 1): "
              f"{old}/{span} = {old / span:.3f}")
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
    print(f"rule 2: {unverified} node(s) not marked quote_verified, excluded from the quote column")
    if unverified == 0:
        print("note: every observation in this store has quote_verified = True, so rule 2 does not filter here")
    lens = sorted(len(n["quote"]) for n in nodes if n["verified"])
    pct = lambda p: lens[min(len(lens) - 1, int(p * len(lens)))]
    print(f"quote length (chars): min {lens[0]}, p25 {pct(.25)}, median {pct(.5)}, p75 {pct(.75)}, max {lens[-1]}; "
          f"under 40: {sum(1 for x in lens if x < 40)}")
    # Real-data negative control: attribute every node to the round `shift` rounds later (wrapping in the span).
    shift = 5
    nr = len(rounds)
    shifted = [dict(n, round=(n["round"] + shift) % nr) for n in nodes]
    q, _, _ = coverage(rounds, texts, shifted, 40)
    cov = sum(1 for e in q if q[e] > 0)
    why = {}
    for n in shifted:
        got, _ = credit(n["quote"], rounds[n["round"]], texts, 40)
        if got:
            own = rounds[(n["round"] - shift) % nr]
            m = [w for w in windows(n["quote"], 40) if any(w in norm(texts[e]) for e in got)]
            why[n["id"]] = "repeated in own exchange too" if any(w in norm(texts[e]) for w in m for e in own) \
                else "matches the shifted exchange only"
    print(f"REAL-DATA NEGATIVE CONTROL: every node attributed {shift} {'exchanges' if k == 1 else 'rounds'} late -> "
          f"quote-credited {cov}/{span} at 40 chars ({len(why)} nodes credited: {dict(Counter(why.values()))})")
    # --- added 2026-11-16 for the pilots (design owner's measures); none of the lines above changed meaning.
    q, _, _ = coverage(rounds, texts, nodes, 40)
    print(f"k (exchanges per round): {k}; rounds in span: {len(rounds)}")
    for pos in range(k):
        es = [r[pos] for r in rounds if len(r) > pos]
        print(f"  coverage at position {pos + 1} of the round: {sum(1 for e in es if q[e] > 0)}/{len(es)}")
    # covered ONLY by nodes whose matching text also occurs in an exchange before the node's round
    only_repeat = 0
    for r_i, r in enumerate(rounds):
        first = min(r)
        for e in r:
            if q[e] == 0:
                continue
            fresh = False
            for n in nodes:
                if n["round"] != r_i or e not in credit(n["quote"], r, texts, 40)[0]:
                    continue
                m = [w for w in windows(n["quote"], 40) if w in norm(texts[e])]
                if not all(any(w in norm(texts[x]) for x in range(1, first)) for w in m):
                    fresh = True
                    break
            only_repeat += not fresh
    print(f"covered exchanges credited ONLY by text the conversation already showed in an earlier exchange: {only_repeat}")
    kept_rows = [rows[i] for i in keep]
    wall = sum(r["wall_s"] or 0 for r in kept_rows)
    tok = sum(r["in_tok"] or 0 for r in kept_rows)
    print(f"wall seconds per source exchange: {wall / span:.1f}; input tokens per source exchange: {tok / span:.0f}")
    ev_path = os.path.join(run_dir, "run/events.jsonl")
    per_turn, turn = Counter(), 1
    for line in open(ev_path):
        e = json.loads(line)
        if e.get("type") == "system" and e.get("subtype") == "compact_boundary" and \
                e.get("compact_metadata", {}).get("trigger") == "auto":
            per_turn[turn] += 1
        if e.get("type") == "result":
            turn += 1
    in_span = [rows[i]["i"] for i in keep]
    comp = sum(per_turn[i] for i in in_span)
    print(f"automatic compactions during the span's rounds (each begins inside a round): {comp}; "
          f"per source exchange {comp / span:.2f}; rounds with at least one: {sum(1 for i in in_span if per_turn[i])}")


def render_check(a):
    """Control 7 (design owner, 2026-11-16): on feed.render's REAL output, for every exchange of every planned round of
    each k, the round message contains the exchange's render verbatim, and after stripping, the user's and the
    assistant's text are present whole and no wrapper line is. Raw texts are paired independently of feed.exchanges."""
    fd = load_feed(a.feed_dir)
    import pyarrow.parquet as pq
    parquet = os.environ.get("BEAM_PARQUET") or sys.exit("set BEAM_PARQUET to the BEAM 100K parquet file")
    conv = next(c for c in pq.read_table(parquet).to_pylist() if str(c["conversation_id"]) == str(a.conv))
    raw = []
    for sess in conv["chat"]:
        pend = None
        for msg in sess:
            if msg["role"] == "user":
                pend = msg
            elif msg["role"] == "assistant" and pend is not None:
                raw.append((pend["content"], msg["content"])); pend = None
    rendered = fd.exchanges(conv)
    assert len(raw) == len(rendered), "independent pairing disagrees with feed.exchanges on the count"
    wrapper = (fd.TURN_LINE, fd.END, USER_LABEL, ASSISTANT_LABEL)
    ok = True
    for path in a.plans:
        plan = [p for p in json.load(open(path)) if p["kind"] == "exchange"]
        bad = 0; n = 0
        for p in plan:
            for e in p["exchanges"]:
                n += 1
                r = rendered[e - 1]
                body = content_only(r, fd)
                u, s = raw[e - 1]
                lines = body.split("\n")
                good = (r in p["text"] and u in body and s in body
                        and not any(l in wrapper or l.startswith(fd.BEGIN) for l in lines))
                bad += not good
        k = max(len(p["exchanges"]) for p in plan)
        print(f"{'PASS' if bad == 0 else 'FAIL'}  control 7 on {os.path.basename(path)}: k = {k}, {len(plan)} rounds, "
              f"{n} exchanges, {bad} failing (render verbatim in round; user and assistant text whole; no wrapper line)")
        ok &= bad == 0
    try:
        content_only(rendered[0].replace("\n", "\nAN EXTRA HEADER LINE\n", 1), fd); flipped = False
    except ValueError:
        flipped = True
    print(f"{'PASS' if flipped else 'FAIL'}  mutant of control 7 (real render plus one header line): refused = {flipped}")
    ok &= flipped
    print("RENDER CHECK:", "ALL PASS" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["controls", "run", "runA", "render-check"])
    ap.add_argument("--span", type=int, default=45)
    ap.add_argument("--conv", type=int, default=9)
    ap.add_argument("--run-dir"); ap.add_argument("--run-start", help="the run's start, ISO 8601 UTC")
    ap.add_argument("--plans", nargs="*", default=[], help="render-check: feed4 --dump-plan outputs, one per k")
    ap.add_argument("--feed-dir", default=HERE)
    a = ap.parse_args()
    if a.what in ("run", "runA") and not (a.run_dir and a.run_start):
        ap.error("run needs --run-dir and --run-start")
    if a.what == "render-check" and not a.plans:
        ap.error("render-check needs --plans")
    sys.exit(controls(load_feed(a.feed_dir)) if a.what == "controls" else
             render_check(a) if a.what == "render-check" else (run(a) or 0))
