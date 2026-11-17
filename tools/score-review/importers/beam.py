"""Build review items for a BEAM conversation. pyarrow is imported lazily, only when a parquet is read."""
import ast
import hashlib
import json


class ImportError_(ValueError):
    pass


def _flatten_ids(v):
    if v is None:
        return []
    if isinstance(v, dict):
        out = []
        for x in v.values():
            out += _flatten_ids(x)
        return out
    if isinstance(v, (list, tuple)):
        out = []
        for x in v:
            out += _flatten_ids(x)
        return out
    return [int(v)]


def _parse_probing(raw):
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        try:
            return ast.literal_eval(raw)
        except (ValueError, SyntaxError) as exc:
            raise ImportError_("probing_questions is neither JSON nor a Python literal: %s" % exc)


_KNOWN = {"question", "ideal_answer", "answer", "rubric", "source_chat_ids"}
_CONV_COLUMNS = ("conversation_id", "conv_id", "id")


def load_questions(parquet_path, conv):
    """Return (questions, data_sha256_prefix). Order: BEAM's flattened probing_questions (dict order, then list order)."""
    import pyarrow.parquet as pq  # lazy: only the BEAM importer needs it

    with open(parquet_path, "rb") as fh:
        sha = hashlib.sha256(fh.read()).hexdigest()[:12]
    table = pq.read_table(parquet_path)
    col = next((c for c in _CONV_COLUMNS if c in table.column_names), None)
    if col is None:
        raise ImportError_("no conversation id column (looked for %s)" % ", ".join(_CONV_COLUMNS))
    if "probing_questions" not in table.column_names:
        raise ImportError_("no probing_questions column")
    hit = [i for i, v in enumerate(table.column(col).to_pylist()) if str(v) == str(conv)]
    if len(hit) != 1:
        raise ImportError_("conversation %r matched %d rows (expected exactly 1)" % (conv, len(hit)))
    probing = _parse_probing(table.column("probing_questions").to_pylist()[hit[0]])
    questions = []
    n = 0
    for category, lst in probing.items():
        for q in lst:
            n += 1
            answer = q.get("ideal_answer", q.get("answer"))
            if "question" not in q or answer is None or "rubric" not in q:
                raise ImportError_("question %d lacks question, ideal_answer/answer or rubric" % n)
            rubric = q["rubric"]
            rubric = [rubric] if isinstance(rubric, str) else list(rubric)
            meta = {k: v for k, v in q.items() if k not in _KNOWN}
            json.dumps(meta)  # must be plain JSON
            questions.append({"question_no": n, "question": q["question"], "answer": str(answer), "rubric": rubric,
                              "cited_ids": _flatten_ids(q.get("source_chat_ids")), "category": category,
                              "metadata": meta})
    return questions, sha


def opaque_id(seed, item_id, original_index):
    """First 8 hex of sha256 over seed, item id and the answer's original index (0 = official)."""
    return hashlib.sha256(("%s|%s|%d" % (seed, item_id, original_index)).encode("utf-8")).hexdigest()[:8]


def build_records(conv, questions, agent_rows, seed, dataset, data_sha256_prefix):
    """Return (items, grades) as lists of dicts, split by audience.

    Answer ids are opaque and per item; the list is sorted by id, so neither the id nor the position
    says which answer is official or which arm produced an answer. That fact lives in grades only.
    """
    items, grades, skipped = [], [], []
    for q in questions:
        rows = [r for r in agent_rows if r["question_no"] == q["question_no"]]
        if not rows:
            skipped.append(q["question_no"])
            continue
        arms_seen = [r["arm"] for r in rows]
        if len(set(arms_seen)) != len(arms_seen):
            raise ImportError_("question %d has two answers from one arm" % q["question_no"])
        item_id = "%s-q%02d" % (conv, q["question_no"])
        originals = [{"text": q["answer"], "cited_ids": list(q["cited_ids"]), "arm": None, "scores": None}]
        for r in rows:
            sc = r.get("rubric_scores")
            if sc is None or len(sc) != len(q["rubric"]):
                raise ImportError_("question %d, arm %s: rubric_scores must have %d entries"
                                   % (q["question_no"], r["arm"], len(q["rubric"])))
            originals.append({"text": r["text"], "cited_ids": list(r.get("cited_ids") or []), "arm": r["arm"],
                              "scores": [float(x) for x in sc]})
        ids = [opaque_id(seed, item_id, i) for i in range(len(originals))]
        if len(set(ids)) != len(ids):
            raise ImportError_("answer id collision in %s; change the seed" % item_id)
        answers = [{"answer_id": ids[i], "text": o["text"], "cited_ids": o["cited_ids"]} for i, o in enumerate(originals)]
        answers.sort(key=lambda a: a["answer_id"])
        items.append({"schema_version": 1, "item_id": item_id, "question": q["question"], "answers": answers})
        grades.append({
            "schema_version": 1, "item_id": item_id, "study": dataset, "conv": conv, "question_no": q["question_no"],
            "official_id": ids[0], "rubric_lines": list(q["rubric"]),
            "scores": {ids[i]: originals[i]["scores"] for i in range(1, len(originals))},
            "scale": {"max": 1.0, "min": 0.0}, "category": q.get("category"), "metadata": q.get("metadata") or {},
            "arms": {ids[i]: originals[i]["arm"] for i in range(1, len(originals))},
            "source_ref": {"dataset": dataset, "data_sha256_prefix": data_sha256_prefix, "conv": conv},
        })
    return items, grades, skipped
