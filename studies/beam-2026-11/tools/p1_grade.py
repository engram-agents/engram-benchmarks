#!/usr/bin/env python3
"""BEAM P1 grading, step 1 of 2: build a BLIND pool of answers from both sessions and judge it.

Rule part d (P1 rule entry) and the design owner's rulings 32566/32574/32673-4/32683: the question-seeing judge (the
official BEAM judge prompt at upstream 3e12035, sha256 pinned below, <question> filled), on claude-sonnet-5-5 at a fixed
effort, one call per item, answers pooled across both sessions under opaque ids so the judge never sees which k produced
an answer. This step records raw judge scores per opaque id only; it never unblinds and never scores. Step 2 (the
scoring, under ruling 32683) reads the sealed key after every call is done.

Pool: one PRIMARY item per (session, question) with an answer; one SENSITIVITY item per missing turn that has an
earlier text block. A missing primary is never pooled (it scores 0 under every reading, ruling 32683). An undecided near
variant REFUSES the build. Pool rows carry only opaque_id, question, gold, answer.

Usage:
  p1_grade.py build --k3 A.json --k1 B.json --questions q.json --gold final.md --gold-sha256 H --seed N --out DIR
  p1_grade.py judge --pool DIR/pool.json --pool-sha256 H --template T --effort low --key-file NAME [--workers 4]
The API key is read from $ENGRAM_HOME/secrets/NAME inside this process and never printed.
"""
import argparse, concurrent.futures as cf, hashlib, json, os, random, re, sys, time

TEMPLATE_SHA256 = "d349c9a8559bed9c14bfe2e624212225b09218ff864258a739229c15f4c8e869"
MODEL = "claude-sonnet-5-5"
ANSWERED = ("recorded", "last_text_block")
MISSING = ("missing", "placeholder_missing", "ruled_missing")


class GradeRefused(Exception):
    pass


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def load_gold(path, expect_sha):
    raw = open(path, "rb").read()
    if _sha(raw) != expect_sha:
        raise GradeRefused(f"gold file {path} sha256 {_sha(raw)} != expected {expect_sha}")
    gold = {}
    for line in raw.decode("utf-8").splitlines():
        m = re.match(r"^([AF]\d+) \| .* \|\| (.*)$", line)
        if m:
            gold[m.group(1)] = m.group(2).strip()
    return gold


def build_pool(answer_files, question_file, gold_file, gold_sha, seed):
    """answer_files: {"K3": path, "k1": path}. Returns (pool rows, key {opaque_id: {session, qid, kind}})."""
    gold = load_gold(gold_file, gold_sha)
    questions = {q["id"]: q["question"] for q in json.load(open(question_file))}
    items = []
    for session in sorted(answer_files):
        answers = json.load(open(answer_files[session]))["answers"]
        for qid in sorted(answers):
            a = answers[qid]
            route = a["route"]
            if route == "near_variant":
                raise GradeRefused(f"{session} {qid}: route near_variant is undecided; grading waits for a ruling")
            if route in ANSWERED:
                items.append((session, qid, "primary", a["answer"]))
            elif route in MISSING:
                if a.get("sensitivity_answer") is not None:
                    items.append((session, qid, "sensitivity", a["sensitivity_answer"]))
            else:
                raise GradeRefused(f"{session} {qid}: unknown route {route!r}")
    for _s, qid, _k, _a in items:
        if qid not in gold:
            raise GradeRefused(f"no gold line for {qid}")
        if qid not in questions:
            raise GradeRefused(f"no question text for {qid}")
    rng = random.Random(seed)
    rng.shuffle(items)
    pool, key = [], {}
    for n, (session, qid, kind, answer) in enumerate(items, 1):
        oid = f"P{n:03d}"
        pool.append({"opaque_id": oid, "question": questions[qid], "gold": gold[qid], "answer": answer})
        key[oid] = {"session": session, "qid": qid, "kind": kind}
    return pool, key


def write_sealed(pool, key, pool_path, key_path):
    pb = json.dumps(pool, indent=1, ensure_ascii=False).encode("utf-8")
    kb = json.dumps(key, indent=1, sort_keys=True).encode("utf-8")
    open(pool_path, "wb").write(pb)
    open(key_path, "wb").write(kb)
    return _sha(pb), _sha(kb)


def load_template(path):
    raw = open(path, "rb").read()
    if _sha(raw) != TEMPLATE_SHA256:
        raise GradeRefused(f"template {path} sha256 {_sha(raw)} != pinned {TEMPLATE_SHA256}")
    return raw.decode("utf-8")


def fill_prompt(template, question, rubric_item, answer):
    return template.replace("<question>", question).replace("<rubric_item>", rubric_item).replace("<llm_response>", answer)


def parse_json_response(response):
    """Upstream parse_json_response, ported (as in the run-A judge)."""
    response = response.strip()
    if response.startswith("```"):
        m = re.search(r"```(?:json)?\s*(\[.*\]|\{.*\})\s*```", response, re.DOTALL)
        if m:
            response = m.group(1).strip()
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass
    m = re.search(r'(\{.*?\}|\[.*?\])', response, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    raise ValueError("No valid JSON found in response.")


def judge_one(client, template, effort, row):
    prompt = fill_prompt(template, row["question"], row["gold"], row["answer"])
    t0 = time.time()
    resp = client.beta.messages.create(
        model=MODEL, max_tokens=4000, betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        output_config={"effort": effort}, messages=[{"role": "user", "content": prompt}])
    text = "".join(b.text for b in resp.content if b.type == "text")
    rec = dict(opaque_id=row["opaque_id"], served_by=resp.model, stop_reason=resp.stop_reason,
               seconds=round(time.time() - t0, 2), input_tokens=resp.usage.input_tokens,
               output_tokens=resp.usage.output_tokens, request_id=resp._request_id)
    if resp.stop_reason == "refusal":
        rec.update(score=None, reason="REFUSAL", raw=text)
        return rec
    try:
        parsed = parse_json_response(text)
        rec.update(score=float(parsed["score"]), reason=parsed.get("reason", ""))
    except Exception as e:
        rec.update(score=None, reason=f"PARSE_ERROR: {e}", raw=text)
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--k3", required=True); b.add_argument("--k1", required=True)
    b.add_argument("--questions", required=True); b.add_argument("--gold", required=True)
    b.add_argument("--gold-sha256", required=True); b.add_argument("--seed", type=int, required=True)
    b.add_argument("--out", required=True)
    j = sub.add_parser("judge")
    j.add_argument("--pool", required=True); j.add_argument("--pool-sha256", required=True)
    j.add_argument("--template", required=True); j.add_argument("--effort", default="low", choices=["low", "medium", "high"])
    j.add_argument("--key-file", required=True); j.add_argument("--workers", type=int, default=4)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "build":
            pool, key = build_pool({"K3": a.k3, "k1": a.k1}, a.questions, a.gold, a.gold_sha256, a.seed)
            os.makedirs(a.out, exist_ok=True)
            hp, hk = write_sealed(pool, key, os.path.join(a.out, "pool.json"), os.path.join(a.out, "key.json"))
            kinds = {}
            for v in key.values():
                kinds[(v["session"], v["kind"])] = kinds.get((v["session"], v["kind"]), 0) + 1
            print(f"pool items {len(pool)}; per (session, kind) {sorted(kinds.items())}")
            print(f"pool.json sha256 {hp}")
            print(f"key.json sha256 {hk}")
            return 0
        template = load_template(a.template)
        raw = open(a.pool, "rb").read()
        if _sha(raw) != a.pool_sha256:
            raise GradeRefused(f"pool {a.pool} sha256 {_sha(raw)} != expected {a.pool_sha256}")
        pool = json.loads(raw)
        out_path = os.path.join(os.path.dirname(a.pool), "judge-raw.jsonl")
        done = set()
        if os.path.exists(out_path):
            done = {json.loads(l)["opaque_id"] for l in open(out_path) if l.strip()}
        todo = [r for r in pool if r["opaque_id"] not in done]
        import anthropic
        secrets = os.path.join(os.environ.get("ENGRAM_HOME", os.path.expanduser("~/.engram")), "secrets")
        client = anthropic.Anthropic(api_key=open(os.path.join(secrets, a.key_file)).read().strip())
        print(f"judging {len(todo)} of {len(pool)} items (resume skips {len(done)}); model {MODEL}, effort {a.effort}")
        with open(out_path, "a") as out, cf.ThreadPoolExecutor(a.workers) as ex:
            for rec in ex.map(lambda r: judge_one(client, template, a.effort, r), todo):
                out.write(json.dumps(rec) + "\n"); out.flush()
        recs = [json.loads(l) for l in open(out_path) if l.strip()]
        bad = [r["opaque_id"] for r in recs if r.get("score") is None]
        off = [r["opaque_id"] for r in recs if not str(r.get("served_by", "")).startswith(MODEL)]
        print(f"records {len(recs)}; unscored {len(bad)} {bad}; served by another model {len(off)} {off}")
        print(f"judge-raw.jsonl sha256 {_sha(open(out_path, 'rb').read())}")
        return 0 if not bad and not off and len(recs) == len(pool) else 4
    except GradeRefused as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
