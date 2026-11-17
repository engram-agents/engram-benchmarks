"""Build review items for a BEAM conversation. pyarrow is imported lazily, only when a parquet is read."""
import ast
import hashlib
import json


class ImportError_(ValueError):
    pass


def _as_list(v, field, kind):
    """A list, or a dict of lists flattened in key order, of strings (kind str) or integers (kind int).

    None, an empty list and an empty dict give []. Anything else is refused, naming the field.
    """
    if v is None:
        return []
    if isinstance(v, dict):
        parts = list(v.values())
        if not all(isinstance(x, (list, tuple)) for x in parts):
            raise ImportError_("%s: a dict must hold lists" % field)
        flat = [y for x in parts for y in x]
    elif isinstance(v, (list, tuple)):
        flat = list(v)
    else:
        raise ImportError_("%s must be a list or a dict of lists, not %s" % (field, type(v).__name__))
    for y in flat:
        ok = (isinstance(y, int) and not isinstance(y, bool)) if kind is int else isinstance(y, str)
        if not ok:
            raise ImportError_("%s must hold only %s values, found %r"
                               % (field, "integer" if kind is int else "text", y))
    return flat


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


_REFERENCE_KEYS = ("ideal_answer", "answer", "ideal_response", "ideal_summary")
_CRITERION_LISTS = ("compliance_indicators", "non_compliance_signs")
_CONV_COLUMNS = ("conversation_id", "conv_id", "id")


def questions_from_probing(probing):
    """Flatten a probing_questions mapping into question dicts (dict order, then list order).

    The reference text is the first present of ideal_answer, answer, ideal_response, ideal_summary
    (reference_kind "answer"); failing those, expected_compliance (reference_kind "criterion").
    """
    questions = []
    n = 0
    for category, lst in probing.items():
        for q in lst:
            n += 1
            if "question" not in q or "rubric" not in q:
                raise ImportError_("question %d lacks question or rubric" % n)
            used = next((k for k in _REFERENCE_KEYS if q.get(k) is not None), None)
            kind = "answer"
            if used is None and q.get("expected_compliance") is not None:
                used, kind = "expected_compliance", "criterion"
            if used is None:
                raise ImportError_("question %d has no reference (%s or expected_compliance)"
                                   % (n, ", ".join(_REFERENCE_KEYS)))
            rubric = _as_list(q["rubric"], "rubric", str)
            if not rubric:
                raise ImportError_("question %d has an empty rubric" % n)
            cited = _as_list(q.get("source_chat_ids"), "source_chat_ids", int)
            meta = {k: v for k, v in q.items() if k not in ("question", "rubric", "source_chat_ids", used)}
            for k in _CRITERION_LISTS:
                if k in meta:
                    meta[k] = _as_list(meta[k], k, str)
            json.dumps(meta)  # must be plain JSON
            questions.append({"question_no": n, "question": q["question"], "answer": str(q[used]), "rubric": rubric,
                              "cited_ids": cited, "category": category, "metadata": meta, "reference_kind": kind})
    return questions


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
    return questions_from_probing(probing), sha


def opaque_id(seed, item_id, original_index):
    """First 8 hex of sha256 over seed, item id and the answer's original index (0 = official)."""
    return hashlib.sha256(("%s|%s|%d" % (seed, item_id, original_index)).encode("utf-8")).hexdigest()[:8]


def opaque_item_id(seed, conv, question_no):
    """First 10 hex of sha256 over seed, conversation and question number: the item id carries neither."""
    return hashlib.sha256(("%s|%s|%d" % (seed, conv, question_no)).encode("utf-8")).hexdigest()[:10]


def build_records(conv, questions, agent_rows, seed, dataset, data_sha256_prefix):
    """Return (items, grades, skipped) as lists, split by audience.

    Item ids and answer ids are opaque; the answer list is sorted by id, so neither an id nor a position
    says which answer is official or which arm produced an answer, and no item id says which conversation or
    question it is (the question number maps to the category). Those facts live in grades only.
    """
    items, grades, skipped = [], [], []
    seen_items = set()
    for q in questions:
        rows = [r for r in agent_rows if r["question_no"] == q["question_no"]]
        if not rows:
            skipped.append(q["question_no"])
            continue
        arms_seen = [r["arm"] for r in rows]
        if len(set(arms_seen)) != len(arms_seen):
            raise ImportError_("question %d has two answers from one arm" % q["question_no"])
        item_id = opaque_item_id(seed, conv, q["question_no"])
        if item_id in seen_items:
            raise ImportError_("item id collision at question %d; change the seed" % q["question_no"])
        seen_items.add(item_id)
        criterion = q.get("reference_kind", "answer") == "criterion"
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
        # A criterion is not an answer: it never enters items.jsonl (the phase-2 builder renders what items holds).
        shown = range(1, len(originals)) if criterion else range(len(originals))
        answers = [{"answer_id": ids[i], "text": originals[i]["text"], "cited_ids": originals[i]["cited_ids"]} for i in shown]
        answers.sort(key=lambda a: a["answer_id"])
        items.append({"schema_version": 1, "item_id": item_id, "question": q["question"], "answers": answers})
        meta = dict(q.get("metadata") or {})
        if criterion and q["cited_ids"]:
            meta["source_chat_ids"] = list(q["cited_ids"])
        g = {
            "schema_version": 1, "item_id": item_id, "study": dataset, "conv": conv, "question_no": q["question_no"],
            "reference_kind": "criterion" if criterion else "answer",
            "official_id": None if criterion else ids[0], "rubric_lines": list(q["rubric"]),
            "scores": {ids[i]: originals[i]["scores"] for i in range(1, len(originals))},
            "scale": {"max": 1.0, "min": 0.0}, "category": q.get("category"), "metadata": meta,
            "arms": {ids[i]: originals[i]["arm"] for i in range(1, len(originals))},
            "source_ref": {"dataset": dataset, "data_sha256_prefix": data_sha256_prefix, "conv": conv},
        }
        if criterion:
            g["criterion_text"] = q["answer"]
        grades.append(g)
    return items, grades, skipped
