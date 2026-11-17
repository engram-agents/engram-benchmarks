#!/usr/bin/env python3
"""score-review: the engine behind the three-phase review in SCORE-REVIEW-PRINCIPLES.md.

Everything is files (JSON Lines, append-only for verdicts). The record formats are in schema.md.
Standard library only; pyarrow is imported lazily by the BEAM importer.
"""
import argparse
import datetime
import hashlib
import json
import math
import os
import random
import re
import sys

import blind_packet
from ids import valid_answer_id, valid_item_id
from chatfile import load_chat

SCHEMA = 1
JUDGEMENT_LEVEL = {"correct": "full", "partly": "partial", "wrong": "zero"}
INDEPENDENCE = ("all reviewers belong to the team that builds the agent under test. These principles reduce our bias; "
                "they do not make the adjusted score independent.")
LETTERS = blind_packet.LETTERS


class UserError(Exception):
    """A refusal: reported on stderr as `refused: ...`, exit code 1, nothing written."""


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def canonical_sha(rec):
    body = {k: v for k, v in rec.items() if k != "record_sha256"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                          .encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ file loading

def read_jsonl(path, required=True):
    if not os.path.exists(path):
        if required:
            raise UserError("file not found: %s" % path)
        return []
    rows = []
    with open(path, "r", encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except ValueError as exc:
                raise UserError("%s line %d is not JSON: %s" % (path, n, exc))
    return rows


def write_jsonl_atomic(path, rows):
    tmp = "%s.tmp" % path
    with open(tmp, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def load_items(path):
    items = {}
    for r in read_jsonl(path):
        iid = r.get("item_id")
        if not valid_item_id(iid):
            raise UserError("items file: bad item_id %r" % (iid,))
        if iid in items:
            raise UserError("items file: duplicate item %s" % iid)
        ans = r.get("answers")
        if not isinstance(r.get("question"), str) or not isinstance(ans, list) or len(ans) < 1:
            raise UserError("items file: item %s needs a question and at least one answer" % iid)
        ids = []
        for a in ans:
            aid = a.get("answer_id")
            if not valid_answer_id(aid):
                raise UserError("items file: item %s has a bad answer id %r (lowercase letters and digits only)" % (iid, aid))
            if not isinstance(a.get("text"), str) or not all(isinstance(c, int) and not isinstance(c, bool)
                                                             for c in a.get("cited_ids", [])):
                raise UserError("items file: item %s answer %s is malformed" % (iid, aid))
            ids.append(aid)
        if len(set(ids)) != len(ids) or len(ids) > len(LETTERS):
            raise UserError("items file: item %s has duplicate answer ids or too many answers" % iid)
        items[iid] = r
    return dict(sorted(items.items()))  # item-id order, whatever the file's row order: nothing pairs by position


def load_grades(path, items):
    grades = {}
    for r in read_jsonl(path):
        iid = r.get("item_id")
        if iid not in items:
            raise UserError("grades file names an item that is not in the items file: %r" % (iid,))
        ids = [a["answer_id"] for a in items[iid]["answers"]]
        kind = r.get("reference_kind", "answer")
        off = r.get("official_id")
        if kind == "criterion":
            if off is not None:
                raise UserError("grades: item %s is criterion-type, so official_id must be null" % iid)
            if not isinstance(r.get("criterion_text"), str) or not r["criterion_text"].strip():
                raise UserError("grades: item %s is criterion-type and needs a non-empty criterion_text" % iid)
            agents = sorted(ids)
        elif kind == "answer":
            if "criterion_text" in r:
                raise UserError("grades: item %s is answer-type and must not carry a criterion_text" % iid)
            if off not in ids:
                raise UserError("grades: item %s official_id is not one of its answers" % iid)
            if len(ids) < 2:
                raise UserError("grades: item %s is answer-type and needs the official answer and at least one agent answer"
                                % iid)
            agents = sorted(i for i in ids if i != off)
        else:
            raise UserError("grades: item %s has an unknown reference_kind %r" % (iid, kind))
        if sorted(r.get("scores", {})) != agents:
            raise UserError("grades: item %s needs rubric scores for exactly the agent answers" % iid)
        n = len(r.get("rubric_lines", []))
        for aid, sc in r["scores"].items():
            if len(sc) != n:
                raise UserError("grades: item %s answer %s has %d scores for %d rubric lines" % (iid, aid, len(sc), n))
        if not {"max", "min"} <= set(r.get("scale", {})):
            raise UserError("grades: item %s has no scale" % iid)
        grades[iid] = r
    missing = [i for i in items if i not in grades]
    if missing:
        raise UserError("grades file lacks items: %s" % ", ".join(missing))
    return grades


def load_verdicts(path, required=False):
    rows = read_jsonl(path, required=required)
    for r in rows:
        if r.get("record_sha256") != canonical_sha(r):
            raise UserError("verdict record %s does not recompute its record_sha256 (file altered?)"
                            % str(r.get("record_sha256"))[:12])
        if r.get("kind") == EXPORT_KIND:
            missing = [k for k in EXPORT_FIELDS if not isinstance(r.get(k), str) or not r.get(k)]
            if missing:
                raise UserError("an export record (%s) is malformed: missing %s"
                                % (str(r.get("record_sha256"))[:12], ", ".join(missing)))
    return rows


EXPORT_KIND = "export_2b"
EXPORT_FIELDS = ("item_id", "reviewer", "exported_at", "after_2a_record_sha256")


def is_verdict(rec):
    """THE predicate for 'this store record is a reviewer's verdict'. The store also holds export records (the
    moment a criterion was handed to a reviewer); they carry a `kind`, and are never a phase record anywhere."""
    return rec.get("kind") is None


def effective(rows):
    """Verdicts not superseded by a later record (export records are not verdicts and are never returned)."""
    dead = {r["supersedes"] for r in rows if r.get("supersedes")}
    return [r for r in rows if is_verdict(r) and r["record_sha256"] not in dead]


def append_record(path, rec):
    """Append one record to the verdict store in a single O_APPEND write (the only way anything enters it)."""
    line = (json.dumps(rec, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, line)
    finally:
        os.close(fd)


# ------------------------------------------------------------------ the rules (principles section 6, section 2)

def _close(a, b):
    return math.isclose(a, b, rel_tol=0.0, abs_tol=1e-9)


def level_of_scores(scores, scale):
    """A line is met when its score equals scale.max. full: all met; zero: all at scale.min; else partial."""
    if not scores:
        raise ValueError("no rubric scores")
    if all(_close(s, scale["max"]) for s in scores):
        return "full"
    if all(_close(s, scale["min"]) for s in scores):
        return "zero"
    return "partial"


def official_levels(grade):
    return {aid: level_of_scores(sc, grade["scale"]) for aid, sc in sorted(grade["scores"].items())}


def outcome_for(judgement, official_id, levels):
    """First matching row of the outcome table. judgement is keyed by answer ids (or {"ambiguous": v})."""
    if "ambiguous" in judgement:
        return ("ambiguous_split" if judgement["ambiguous"] == "reviewers split" else "ambiguous_source"), []
    reference = official_id if official_id is not None else "criterion"  # a criterion item's reference is its criterion
    if judgement.get(reference) != "correct":
        return "key_wrong", []
    flagged = sorted(aid for aid, lv in levels.items() if JUDGEMENT_LEVEL.get(judgement.get(aid)) != lv)
    if flagged:
        return "grading_error", flagged
    return "key_stands", []


def agree(j1, j2):
    a1, a2 = "ambiguous" in j1, "ambiguous" in j2
    if a1 or a2:
        return a1 and a2
    return j1 == j2


def route(levels, p1, p2, drawn, forced=()):
    """levels {item: {answer_id: level}}, p1/p2 {item: outcome}, drawn: set of item ids.

    forced: items whose 2a was changed after the criterion export (amendments 4 and 7). Whatever the outcomes, such an item is
    never an unquestioned control and is always in phase 3.
    """
    out = {}
    for item, lv in levels.items():
        a = any(v != "full" for v in lv.values())
        b = item in p1 and p1[item] != "key_stands"
        c = item in drawn
        f = item in forced
        in2 = a or b or c or f
        control = (not a) and (not f) and p1.get(item) == "key_stands" and p2.get(item) == "key_stands"
        in3 = in2 and not control
        out[item] = {"set_a": a, "set_b": b, "set_c": c, "forced_phase3": f, "in_phase2": in2, "in_phase3": in3,
                     "unquestioned_control": control, "phase3_required": in3}
    return out


def merge_facts(records):
    """Concatenate every phase's facts, marking the contributor. Nothing is dropped or deduplicated."""
    merged = []
    for rec in records:
        for f in rec.get("facts", []):
            m = dict(f)
            m["phase"] = rec["phase"]
            m["reviewer"] = rec["reviewer"]
            if rec.get("step"):
                m["step"] = rec["step"]
            merged.append(m)
    return merged


# ------------------------------------------------------------------ record

FACT_KEYS = {"msg_id", "quote", "bears_on", "direction", "against_own"}
FILE_KEYS = {"item_id", "step", "keyed_by", "judgement", "fuller_answer", "facts", "guesses", "minutes_spent", "notes"}
REVIEWER_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def validate_verdict(vd, item, phase, chat, grade):
    if not isinstance(vd, dict):
        raise UserError("the verdict file must hold one JSON object")
    extra = set(vd) - FILE_KEYS
    if extra:
        raise UserError("unknown field(s) in the verdict file: %s" % ", ".join(sorted(extra)))
    if vd.get("item_id") != item["item_id"]:
        raise UserError("the verdict file's item_id does not match the item")
    criterion = grade.get("reference_kind", "answer") == "criterion"
    step = vd.get("step")
    if criterion and phase == 2:
        if step not in ("2a", "2b"):
            raise UserError("a phase-2 record for a criterion-type item must carry step 2a or 2b")
    elif step is not None:
        raise UserError("step belongs to phase 2 of a criterion-type item only")
    keyed = "label" if (phase != 2 or step == "2b") else "letter"
    if vd.get("keyed_by", keyed) != keyed:
        raise UserError("phase %d%s must be keyed by %s" % (phase, " step 2b" if step == "2b" else "",
                                                           "letter" if keyed == "letter" else "label (answer id)"))
    j = vd.get("judgement")
    if not isinstance(j, dict) or not j:
        raise UserError("judgement must be a non-empty object")
    ids = [a["answer_id"] for a in item["answers"]]
    if step == "2b":
        if set(j) != {"criterion"} or j["criterion"] not in JUDGEMENT_LEVEL:
            raise UserError("a 2b record's judgement has exactly one key, criterion, with the value correct, partly or wrong")
    elif "ambiguous" in j:
        allowed = {"source"} if phase in (1, 2) else {"source", "reviewers split"}
        if len(j) != 1 or j["ambiguous"] not in allowed:
            raise UserError("ambiguous must stand alone with the value %s in phase %d"
                            % (" or ".join(sorted(allowed)), phase))
    else:
        if phase == 2:
            expected = set(LETTERS[:len(ids)])
        else:
            expected = set(ids) | ({"criterion"} if criterion else set())
        if set(j) != expected:
            raise UserError("phase %d judgement must be keyed by %s, exactly one entry for each of %d answers%s"
                            % (phase, "letters" if phase == 2 else "answer ids", len(ids),
                               " plus criterion" if (criterion and phase != 2) else ""))
        for k, v in j.items():
            if v not in JUDGEMENT_LEVEL:
                raise UserError("judgement for %s must be correct, partly or wrong, not %r" % (k, v))
    fa = vd.get("fuller_answer")
    if fa is not None and not isinstance(fa, str):
        raise UserError("fuller_answer must be text or null")
    notes = vd.get("notes", "")
    if not isinstance(notes, str):
        raise UserError("notes must be text")
    mins = vd.get("minutes_spent")
    if mins is not None and (isinstance(mins, bool) or not isinstance(mins, (int, float)) or mins < 0):
        raise UserError("minutes_spent must be a non-negative number or null")
    facts = vd.get("facts", [])
    if not isinstance(facts, list):
        raise UserError("facts must be a list")
    for f in facts:
        if not isinstance(f, dict) or set(f) != FACT_KEYS:
            raise UserError("every fact needs exactly: %s" % ", ".join(sorted(FACT_KEYS)))
        if isinstance(f["msg_id"], bool) or not isinstance(f["msg_id"], int):
            raise UserError("fact msg_id must be an integer")
        if not isinstance(f["quote"], str) or not f["quote"].strip():
            raise UserError("fact quote must be non-empty text")
        if f["bears_on"] not in j:
            raise UserError("fact bears_on %r is not a key of the judgement" % (f["bears_on"],))
        if f["direction"] not in ("supports", "against") or not isinstance(f["against_own"], bool):
            raise UserError("fact direction must be supports or against, and against_own true or false")
    if chat is not None:
        check_quotes(facts, chat)
    g = vd.get("guesses")
    if g is not None:
        if phase != 2 or step == "2b":
            raise UserError("guesses belong to phase 2 (a 2a record, for a criterion-type item) only")
        valid = set(LETTERS[:len(ids)])
        shape = {"arms"} if criterion else {"official", "arms"}
        if (not isinstance(g, dict) or set(g) != shape or ("official" in g and g["official"] not in valid)
                or not isinstance(g["arms"], dict) or not set(g["arms"]) <= valid
                or not all(isinstance(v, str) for v in g["arms"].values())):
            raise UserError("guesses must be %s" % ("{arms: {<letter>: <arm>}} (a criterion has no official-answer guess)"
                                                    if criterion else "{official: <letter>, arms: {<letter>: <arm>}}"))
    return {"step": step, "keyed_by": keyed, "judgement": j, "fuller_answer": fa, "facts": facts, "guesses": g,
            "minutes_spent": mins, "notes": notes}


def check_quotes(facts, chat):
    for f in facts:
        m = chat.get(f["msg_id"])
        if m is None:
            raise UserError("fact cites message %d, which is not in the chat file" % f["msg_id"])
        if f["quote"] not in m["body"]:
            raise UserError("quote is not verbatim in message %d: %r" % (f["msg_id"], f["quote"]))


def check_order(live, iid, phase, step, reviewer, criterion, rows):
    """Phases are recorded in order (S2): 2 after 1, 3 after both (a criterion item: after 1, 2a and 2b).
    `rows` is the whole store, export records included: a 2b needs its export (A8-1)."""
    def has(ph, st=None):
        return any((r["item_id"], r["phase"], r.get("step")) == (iid, ph, st) for r in live)
    if phase >= 2 and not has(1):
        raise UserError("phase %d needs a recorded phase-1 verdict for this item; the phases are recorded in order" % phase)
    if phase == 3 and not (has(2, "2a") and has(2, "2b") if criterion else has(2)):
        raise UserError("phase 3 needs a recorded phase-2 verdict for this item%s; the phases are recorded in order"
                        % (" (both its 2a and its 2b)" if criterion else ""))
    if step == "2b" and not any((r["item_id"], r["phase"], r.get("step"), r["reviewer"]) == (iid, 2, "2a", reviewer)
                                for r in live):
        raise UserError("a 2b record needs a recorded 2a record for this item by the same reviewer")
    if step == "2b" and not any(r.get("kind") == EXPORT_KIND and (r["item_id"], r["reviewer"]) == (iid, reviewer)
                                for r in rows):
        raise UserError("a 2b record needs an export-criterion record for this item and this reviewer (%s) earlier in "
                        "the verdicts file: run export-criterion first; the criterion is not judged before it is shown"
                        % reviewer)


def cmd_record(a):
    try:
        phase = int(a.phase)
    except ValueError:
        raise UserError("phase must be 1, 2 or 3")
    if phase not in (1, 2, 3):
        raise UserError("unknown phase %s: phases are 1, 2 and 3" % a.phase)
    if not a.reviewer or not REVIEWER_RE.fullmatch(a.reviewer):
        raise UserError("reviewer must be a plain token")
    items = load_items(a.items)
    try:
        with open(a.file, "r", encoding="utf-8") as fh:
            vd = json.load(fh)
    except (OSError, ValueError) as exc:
        raise UserError("cannot read the verdict file: %s" % exc)
    item = items.get(vd.get("item_id") if isinstance(vd, dict) else None)
    if item is None:
        raise UserError("the verdict file names an item that is not in the items file")
    chat = load_chat(a.chat) if a.chat else None
    grade = load_grades(a.grades, items)[item["item_id"]]
    body = validate_verdict(vd, item, phase, chat, grade)
    rows = load_verdicts(a.verdicts)
    iid = item["item_id"]
    live = effective(rows)
    check_order(live, iid, phase, body["step"], a.reviewer, grade.get("reference_kind", "answer") == "criterion", rows)
    # one EFFECTIVE record per (item, phase, step), whoever the reviewer: a second reviewer would make `map` refuse
    # the whole study, so it is refused here unless it supersedes the current record, with a reason
    prior = [r for r in live if (r["item_id"], r["phase"], r.get("step")) == (iid, phase, body["step"])]
    if prior:
        if not a.supersedes or not (a.reason or "").strip():
            raise UserError("a record for this item, phase and step already exists (reviewer %s): record again only "
                            "with --supersedes <its record_sha256> and a --reason" % prior[0]["reviewer"])
        if a.supersedes != prior[0]["record_sha256"]:
            raise UserError("--supersedes must name the current record's record_sha256")
    elif a.supersedes:
        raise UserError("--supersedes names a record, but there is none to supersede")
    rec = {"schema_version": SCHEMA, "item_id": iid, "phase": phase, "reviewer": a.reviewer,
           "recorded_at": now(), "supersedes": a.supersedes if prior else None,
           "reason": a.reason.strip() if prior else None}
    rec.update(body)
    rec["record_sha256"] = canonical_sha(rec)
    if phase == 2 and body["step"]:
        who = {r["step"]: r["reviewer"] for r in effective(rows + [rec]) if r["item_id"] == iid and r["phase"] == 2}
        if len(set(who.values())) > 1:
            raise UserError("this record would leave the 2a and the 2b of item %s with different reviewers (%s); "
                            "both steps are by one reviewer" % (iid, ", ".join("%s: %s" % kv for kv in sorted(who.items()))))
    append_record(a.verdicts, rec)
    print(rec["record_sha256"])


def cmd_quote_check(a):
    chat = load_chat(a.chat)
    bad = []
    for r in effective(load_verdicts(a.verdicts, required=True)):
        try:
            check_quotes(r.get("facts", []), chat)
        except UserError as exc:
            bad.append("%s phase %s %s: %s" % (r["item_id"], r["phase"], r["reviewer"], exc))
    if bad:
        print("\n".join(bad))
        raise UserError("%d verdict(s) carry a quote that is not verbatim" % len(bad))
    print("quote-check: every quote is verbatim")


# ------------------------------------------------------------------ draw

def cmd_draw(a):
    items = load_items(a.items)
    grades = load_grades(a.grades, items)
    try:
        n = int(a.n)
    except ValueError:
        raise UserError("--n must be an integer")
    if n < 0:
        raise UserError("--n must not be negative")
    seen = [r for r in load_verdicts(a.verdicts) if is_verdict(r) and r["phase"] == 1 and r["item_id"] in items]
    if seen:
        raise UserError("a phase-1 verdict already exists for this run (%d record(s)); the draw is fixed before any "
                        "phase-1 outcome exists" % len(seen))
    prior = read_jsonl(a.draws, required=False)
    if any(r.get("run") == a.run for r in prior):
        raise UserError("run %s has already been drawn; the draw is never redone" % a.run)
    eligible = sorted(i for i in items if all(v == "full" for v in official_levels(grades[i]).values()))
    if n > len(eligible):
        raise UserError("--n %d is larger than the %d eligible items" % (n, len(eligible)))
    drawn = sorted(random.Random(str(a.seed)).sample(eligible, n))
    rec = {"schema_version": SCHEMA, "run": a.run, "n": n, "seed": a.seed, "drawn_item_ids": drawn,
           "eligible_item_ids": eligible, "drawn_at": now()}
    with open(a.draws, "ab") as fh:
        fh.write((json.dumps(rec, sort_keys=True) + "\n").encode("utf-8"))
    print("drew %d of %d eligible items for run %s: %s" % (n, len(eligible), a.run, ", ".join(drawn)))


# ------------------------------------------------------------------ packets

def _cited_block(ans, chat, lines):
    cited = ans.get("cited_ids") or []
    lines.append("   cited messages: %s" % (", ".join(map(str, cited)) if cited else "(no messages cited)"))
    if chat is not None:
        for c in cited:
            m = chat.get(c)
            lines.append("   --- msg %d | %s | %s" % (c, m["role"], m["date"]) if m else "   --- msg %d (not in chat file)" % c)
            if m:
                lines.append("   " + m["body"].replace("\n", "\n   "))


def cmd_packet1(a):
    items = load_items(a.items)
    grades = load_grades(a.grades, items)
    if a.item not in items:
        raise UserError("unknown item %s" % a.item)
    it, g = items[a.item], grades[a.item]
    chat = load_chat(a.chat) if a.chat else None
    L = ["Item %s" % a.item, "", "Question: %s" % it["question"], ""]
    if g.get("reference_kind") == "criterion":
        L += ["Criterion (the reference for this item; it is not an answer): %s" % g["criterion_text"], ""]
    L += ["Answers:"]
    for ans in it["answers"]:
        mark = " (official)" if ans["answer_id"] == g["official_id"] else ""
        L.append("- [%s]%s %s" % (ans["answer_id"], mark, ans["text"]))
        _cited_block(ans, chat, L)
    L += ["", "Rubric lines:"] + ["%d. %s" % (i, t) for i, t in enumerate(g["rubric_lines"], 1)]
    L += ["", "Official scores (one per rubric line; scale max %s, min %s):" % (g["scale"]["max"], g["scale"]["min"])]
    for aid, sc in sorted(g["scores"].items()):
        L.append("- [%s] %s" % (aid, sc))
    print("\n".join(L))


def cmd_packet2(a):
    try:
        packet, key, sha = blind_packet.write_packet(a.items, a.item, a.seed, a.keys_dir, a.out_dir, a.chat)
    except (ValueError, FileExistsError, OSError) as exc:
        raise UserError(str(exc))
    print("packet: %s" % packet)
    print("key: %s" % key)
    print("key_sha256: %s" % sha)


# ------------------------------------------------------------------ re-keying, outcomes (map, export, report)

class Ctx:
    def __init__(self, items_path, grades_path, verdicts_path, keys_dir):
        self.items = load_items(items_path)
        self.grades = load_grades(grades_path, self.items)
        self.rows = load_verdicts(verdicts_path, required=True)
        self.keys_dir = keys_dir
        self.levels = {i: official_levels(self.grades[i]) for i in self.items}

    def phase_record(self, item, phase, step=None):
        recs = [r for r in effective(self.rows)
                if r["item_id"] == item and r["phase"] == phase and r.get("step") == step]
        if len(recs) > 1:
            raise UserError("item %s has %d reviewers recorded for phase %d%s; this version supports one"
                            % (item, len(recs), phase, (" step " + step) if step else ""))
        return recs[0] if recs else None

    def is_criterion(self, item):
        return self.grades[item].get("reference_kind", "answer") == "criterion"

    def _opening_step(self, item):
        """The step that opens an item's phase 2: none for an answer-type item, the 2a for a criterion-type one."""
        return "2a" if self.is_criterion(item) else None

    def has_phase2_record(self, item):
        """THE is-it-recorded predicate for phase 2 (one definition: `phase2` asks it too)."""
        return self.phase_record(item, 2, self._opening_step(item)) is not None

    def phase2(self, item):
        """The label-keyed phase-2 record, or None while it is incomplete.

        An answer-type item has one phase-2 record. A criterion-type item has a 2a (agent answers) and a 2b
        (the criterion); both must be recorded, by one reviewer, and the judgement is the two merged: the 2b
        `criterion` judgement stands where an official answer's would, beside the re-keyed 2a judgements.
        When the 2a was superseded AFTER the criterion was exported (see `criterion_change`), the ORIGINAL 2a, the
        one the reviewer gave before seeing the criterion, is the one merged; the later 2a is carried beside it
        as `post_reveal_revision`. A 2a superseded before the export is an ordinary correction: the latest is merged.
        """
        if not self.has_phase2_record(item):
            return None
        head = self.phase_record(item, 2, self._opening_step(item))
        if not self.is_criterion(item):
            return self.rekey(item, head)
        r2b = self.phase_record(item, 2, "2b")
        if r2b is None:
            return None
        if head["reviewer"] != r2b["reviewer"]:
            raise UserError("item %s: the 2a and 2b records are by different reviewers" % item)
        change = self.criterion_change(item)
        out = self.rekey(item, self.mapped_head(item))
        if "ambiguous" not in out["judgement"]:
            out["judgement"] = dict(out["judgement"], criterion=r2b["judgement"]["criterion"])
        out["facts"] = list(out["facts"]) + [dict(f) for f in r2b["facts"]]
        out["record_sha256_2b"] = r2b["record_sha256"]
        out["fuller_answer_2b"] = r2b.get("fuller_answer")
        if change:
            late = self.rekey(item, change[1])
            out["post_reveal_revision"] = {"reviewer": late["reviewer"], "record_sha256": late["record_sha256"],
                                           "judgement": late["judgement"], "fuller_answer": late.get("fuller_answer"),
                                           "facts": late["facts"], "reason": late.get("reason")}
            out["facts"] += [dict(f, post_reveal=True) for f in late["facts"]]
        return out

    def criterion_change(self, item):
        """(original 2a, latest 2a) when the item's 2a was superseded AFTER the criterion was exported, else None.

        The boundary is the reviewer's FIRST export record in the verdict store (`export-criterion` writes it before
        it releases the criterion); order is the file's, which the append-only store witnesses (a timestamp has a
        one-second grain). The original is the 2a that export names (`after_2a_record_sha256`): the 2a as it
        stood when the criterion was shown. A 2a superseded before the export is an ordinary correction.
        The named record must be a verdict of this item, phase 2, step 2a, by the same reviewer, else refused.
        """
        r2a, r2b = self.phase_record(item, 2, "2a"), self.phase_record(item, 2, "2b")
        if r2a is None or r2b is None:
            return None
        who = r2b["reviewer"]
        first = next((n for n, r in enumerate(self.rows)
                      if r.get("kind") == EXPORT_KIND and (r["item_id"], r["reviewer"]) == (item, who)), None)
        if first is None:
            return None
        revised = any(n > first and is_verdict(r) and r.get("supersedes")
                      and (r["item_id"], r["phase"], r.get("step"), r["reviewer"]) == (item, 2, "2a", who)
                      for n, r in enumerate(self.rows))
        if not revised:
            return None
        named = self.rows[first]["after_2a_record_sha256"]
        original = next((r for r in self.rows if is_verdict(r) and r["record_sha256"] == named), None)
        if original is None:
            raise UserError("item %s: the criterion export names a 2a record (%s) that is not in the verdicts file"
                            % (item, str(named)[:12]))
        if (original["item_id"], original["phase"], original.get("step"), original["reviewer"]) != (item, 2, "2a", who):
            raise UserError("item %s: the criterion export names a record (%s) that is not this reviewer's 2a for this "
                            "item" % (item, str(named)[:12]))
        return (original, r2a)

    def mapped_head(self, item):
        """The one phase-2 record whose judgement `map` takes for an item's phase 2 (its 2a for a criterion item,
        the ORIGINAL when the 2a changed after the export): the single definition `phase2` and the arm-guess
        statistic both read. None when the item has no such record."""
        head = self.phase_record(item, 2, self._opening_step(item))
        if head is None or not self.is_criterion(item):
            return head
        change = self.criterion_change(item)
        return change[0] if change else head

    def key_path(self, item):
        return os.path.join(self.keys_dir, "%s.json" % item)

    def letters(self, item):
        """Read an item's key file. Callers reach this only for an item whose phase-2 verdict is recorded."""
        try:
            with open(self.key_path(item), "r", encoding="utf-8") as fh:
                key = json.load(fh)
        except (OSError, ValueError) as exc:
            raise UserError("item %s has a recorded phase-2 verdict but its key file cannot be read: %s" % (item, exc))
        ids = {a["answer_id"] for a in self.items[item]["answers"]}
        if key.get("item_id") != item or set(key.get("letters", {}).values()) != ids:
            raise UserError("the key file for %s does not match the item" % item)
        return key["letters"]

    def rekey(self, item, rec):
        """Re-key a phase-2 record from letters to answer ids. Refuses without a recorded verdict."""
        if rec is None or not rec.get("record_sha256"):
            raise UserError("item %s has no recorded phase-2 verdict; its key is not read" % item)
        letters = self.letters(item)
        j = rec["judgement"]
        jj = dict(j) if "ambiguous" in j else {letters[k]: v for k, v in j.items()}
        facts = []
        for f in rec["facts"]:
            f = dict(f)
            f["bears_on"] = f["bears_on"] if f["bears_on"] == "ambiguous" else letters[f["bears_on"]]
            facts.append(f)
        out = dict(rec)
        out["judgement"], out["facts"] = jj, facts
        g = rec.get("guesses")
        out["official_guess"] = None
        if g and "official" in g:
            gid = letters[g["official"]]
            out["official_guess"] = {"guessed_id": gid, "correct": gid == self.grades[item]["official_id"]}
        out.pop("guesses", None)
        return out

    def phase_view(self, item, phase, rec):
        """The label-keyed view of one recorded phase: judgement, outcome, flagged answers."""
        g = self.grades[item]
        out, flagged = outcome_for(rec["judgement"], g["official_id"], self.levels[item])
        v = {"reviewer": rec["reviewer"], "record_sha256": rec["record_sha256"], "judgement": rec["judgement"],
             "outcome": out, "flagged": flagged, "fuller_answer": rec.get("fuller_answer")}
        if phase == 2:
            v["official_guess"] = rec.get("official_guess")
            if rec.get("record_sha256_2b"):
                v["record_sha256_2b"] = rec["record_sha256_2b"]
                v["fuller_answer_2b"] = rec.get("fuller_answer_2b")
            if rec.get("post_reveal_revision"):
                v["post_reveal_revision"] = rec["post_reveal_revision"]
        return v


def compute_outcomes(ctx, draws, note):
    p1o, p2o, recs, views = {}, {}, {}, {}
    for item in ctx.items:
        r1, r3 = ctx.phase_record(item, 1), ctx.phase_record(item, 3)
        r2 = ctx.phase2(item)
        if r2 is None and not ctx.has_phase2_record(item) and os.path.exists(ctx.key_path(item)):
            note("refused: %s has a key file but no recorded phase-2 verdict; the key is not read, nothing is re-keyed"
                 % item)
        recs[item] = (r1, r2, r3)
        views[item] = {str(p): ctx.phase_view(item, p, r) for p, r in zip((1, 2, 3), (r1, r2, r3)) if r is not None}
        if r1:
            p1o[item] = views[item]["1"]["outcome"]
        if r2:
            p2o[item] = views[item]["2"]["outcome"]
    drawn = set()
    for d in draws:
        drawn |= set(d.get("drawn_item_ids", []))
    forced = {item for item in ctx.items if ctx.criterion_change(item)}
    routing = route(ctx.levels, p1o, p2o, drawn, forced)
    out = []
    for item in ctx.items:
        r1, r2, r3 = recs[item]
        v, rt = views[item], routing[item]
        agr = {"p1_p2": agree(r1["judgement"], r2["judgement"]) if r1 and r2 else None,
               "all": (agree(r1["judgement"], r2["judgement"]) and agree(r2["judgement"], r3["judgement"]))
               if r1 and r2 and r3 else None}
        if not r1:
            status = "phase1_pending"
        elif not rt["in_phase2"]:
            status = "not_reviewed"
        elif not r2:
            status = "phase2_pending"
        elif rt["unquestioned_control"]:
            status = "control_settled"
        elif not r3:
            status = "pending"
        elif v["3"]["outcome"] == "ambiguous_split":
            status = "ambiguous_split"
        elif agr["all"]:
            status = "settled"
        else:
            status = "disagreement"
        out.append({
            "schema_version": SCHEMA, "item_id": item, "generated_at": now(),
            "official_id": ctx.grades[item]["official_id"],
            "reference_kind": ctx.grades[item].get("reference_kind", "answer"), "official_levels": ctx.levels[item],
            "routing": rt, "phases": v, "agreement": agr, "status": status,
            "adjusted": adjusted_entry(status, v, ctx.levels[item]),
            "facts": merge_facts([r for r in (r1, r2, r3) if r]),
        })
    return out


def adjusted_entry(status, views, levels):
    ids = sorted(levels)
    unchanged = {i: "unchanged" for i in ids}
    if status in ("not_reviewed", "control_settled", "ambiguous_split"):
        return {"method": None, "per_answer": unchanged}
    if status == "settled":
        oc = views["3"]["outcome"]
        if oc == "key_wrong":
            return {"method": "judge-rerun", "per_answer": {i: "pending judge-rerun" for i in ids}}
        if oc == "grading_error":
            fl = set(views["3"]["flagged"])
            return {"method": "hand-regrade", "per_answer": {i: ("pending hand-regrade" if i in fl else "unchanged") for i in ids}}
        return {"method": None, "per_answer": unchanged}
    return {"method": None, "per_answer": {i: "pending" for i in ids}}


def cmd_map(a):
    ctx = Ctx(a.items, a.grades, a.verdicts, a.keys_dir)
    draws = read_jsonl(a.draws, required=False)
    if not os.path.exists(a.draws):
        print("map: no draws file; set (c) is empty", file=sys.stderr)
    notes = []
    rows = compute_outcomes(ctx, draws, lambda m: (notes.append(m), print("score-review: " + m, file=sys.stderr)))
    write_jsonl_atomic(a.out, rows)
    print("map: wrote %d item(s) to %s" % (len(rows), a.out))


def cmd_export_phase3(a):
    ctx = Ctx(a.items, a.grades, a.verdicts, a.keys_dir)
    if a.item not in ctx.items:
        raise UserError("unknown item %s" % a.item)
    r1, r2 = ctx.phase_record(a.item, 1), ctx.phase2(a.item)
    if r1 is None or r2 is None:
        raise UserError("item %s needs both a phase-1 and a complete phase-2 verdict (a criterion-type item needs its "
                        "2a and its 2b) before phase 3" % a.item)
    it, g = ctx.items[a.item], ctx.grades[a.item]
    v1, v2 = ctx.phase_view(a.item, 1, r1), ctx.phase_view(a.item, 2, r2)
    v1["notes"] = r1.get("notes", "")
    v2.pop("official_guess", None)  # the guesses name letters and arms; phase 3 does not receive them
    revision = v2.pop("post_reveal_revision", None)  # present when the 2a was revised after the reveal: phase 3 sees both
    export = {
        "schema_version": SCHEMA, "item_id": a.item, "exported_at": now(), "question": it["question"],
        "answers": it["answers"], "official_id": g["official_id"],
        "reference_kind": g.get("reference_kind", "answer"), "official_levels": ctx.levels[a.item],
        "phase1": v1, "phase2": v2, "agreement": {"p1_p2": agree(r1["judgement"], r2["judgement"])},
        "facts": merge_facts([r1, r2]),
    }
    if g.get("reference_kind") == "criterion":
        export["criterion_text"] = g["criterion_text"]
    if revision:
        export["phase2_post_reveal_revision"] = revision
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(export, fh, sort_keys=True, indent=2)
        fh.write("\n")
    print("export-phase3: wrote %s" % a.out)


def cmd_export_criterion(a):
    """Step 2b: hand the criterion to a phase-2 reviewer, only after that reviewer's 2a record is in the file."""
    items = load_items(a.items)
    grades = load_grades(a.grades, items)
    if a.item not in items:
        raise UserError("unknown item %s" % a.item)
    g = grades[a.item]
    if g.get("reference_kind") != "criterion":
        raise UserError("item %s is not criterion-type; there is no criterion to export" % a.item)
    rows = load_verdicts(a.verdicts, required=False)  # every record's record_sha256 must recompute
    r2a = [r for r in effective(rows) if (r["item_id"], r["phase"], r.get("step"), r["reviewer"])
           == (a.item, 2, "2a", a.reviewer)]
    if not r2a:
        raise UserError("no recorded 2a record for item %s by reviewer %s; the criterion is not released before it"
                        % (a.item, a.reviewer))
    meta = g.get("metadata") or {}
    # The reveal is an event in the store: record it BEFORE the criterion is released, so a criterion that was
    # handed out always has its record (a record without a file is the safe direction).
    event = {"schema_version": SCHEMA, "kind": EXPORT_KIND, "item_id": a.item, "reviewer": a.reviewer,
             "exported_at": now(), "after_2a_record_sha256": r2a[0]["record_sha256"]}
    event["record_sha256"] = canonical_sha(event)
    append_record(a.verdicts, event)
    export = {"schema_version": SCHEMA, "item_id": a.item, "reviewer": a.reviewer, "exported_at": event["exported_at"],
              "after_2a_record_sha256": r2a[0]["record_sha256"], "criterion_text": g["criterion_text"],
              "criterion_lists": {k: meta[k] for k in ("compliance_indicators", "non_compliance_signs") if k in meta}}
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(export, fh, sort_keys=True, indent=2)
        fh.write("\n")
    print("export-criterion: wrote %s" % a.out)


# ------------------------------------------------------------------ report

def cmd_report(a):
    items = load_items(a.items)
    grades = load_grades(a.grades, items)
    shas = {r["record_sha256"] for r in load_verdicts(a.verdicts, required=True)}
    outcomes = read_jsonl(a.outcomes)
    for o in outcomes:
        if o["item_id"] not in items:
            raise UserError("outcomes name an item that is not in the items file: %s" % o["item_id"])
        for p, v in o["phases"].items():
            cited = [v["record_sha256"], v.get("record_sha256_2b", v["record_sha256"]),
                     (v.get("post_reveal_revision") or v)["record_sha256"]]
            if any(c not in shas for c in cited):
                raise UserError("outcomes are stale: %s phase %s cites a record that is not in the verdicts file; "
                                "run map again" % (o["item_id"], p))
    arm_stats = None
    if a.unblind and a.keys_dir:
        arm_stats = _arm_guess_stats(a, items, grades)
    L = ["# Score review log", "",
         "> Independence: %s" % INDEPENDENCE, "",
         "Official column: graded by the benchmark's own method against its own key, unchanged. "
         "Adjusted column: our corrected reading, by the reviewers named under each item. "
         "Anyone may dispute any item in this log.", "",
         "Arm labels: %s." % ("shown (unblinded)" if a.unblind else "hidden; answers are named by their opaque ids"), ""]
    counts = {}
    for o in outcomes:
        counts[o["status"]] = counts.get(o["status"], 0) + 1
    L += ["## Summary", ""] + ["- %s: %d" % (k, counts[k]) for k in sorted(counts)] + [""]
    L += _guess_section(outcomes, items, arm_stats, a.unblind)
    for o in outcomes:
        it, g = items[o["item_id"]], grades[o["item_id"]]
        L += ["## Item %s" % o["item_id"], "", "Question: %s" % it["question"], "", "Status: **%s**" % o["status"], ""]
        if g.get("reference_kind") == "criterion":
            L += ["Criterion (the reference; not an answer): %s" % g["criterion_text"], ""]
        L += ["| answer | official level | adjusted | text |", "|---|---|---|---|"]
        for ans in it["answers"]:
            aid = ans["answer_id"]
            name = "`%s`" % aid
            if aid == g["official_id"]:
                name += " (official answer)"
                lv, adj = "n/a", "n/a"
            else:
                if a.unblind:
                    name += " (arm %s)" % g["arms"][aid]
                lv, adj = o["official_levels"][aid], o["adjusted"]["per_answer"][aid]
            L.append("| %s | %s | %s | %s |" % (name, lv, adj, ans["text"].replace("|", "\\|").replace("\n", " ")))
        if o["adjusted"]["method"]:
            L += ["", "Adjusted entries by: %s." % o["adjusted"]["method"]]
        L.append("")
        for p in ("1", "2", "3"):
            if p in o["phases"]:
                v = o["phases"][p]
                L.append("- Phase %s, reviewer %s (record %s): outcome **%s**%s; judgement %s" % (
                    p, v["reviewer"], v["record_sha256"][:12], v["outcome"],
                    ", flagged " + ", ".join("`%s`" % f for f in v["flagged"]) if v["flagged"] else "",
                    json.dumps(v["judgement"], sort_keys=True)))
                if v.get("fuller_answer"):
                    L.append("  - fuller answer: %s" % v["fuller_answer"])
                if v.get("fuller_answer_2b"):
                    L.append("  - fuller answer (2b): %s" % v["fuller_answer_2b"])
                if v.get("post_reveal_revision"):
                    o2 = v["post_reveal_revision"]
                    L.append("  - the 2a above is the original (given before the criterion was shown); post-reveal revision "
                             "(record %s, reviewer %s, reason: %s): %s"
                             % (o2["record_sha256"][:12], o2["reviewer"], o2.get("reason") or "none given",
                                json.dumps(o2["judgement"], sort_keys=True)))
            elif o["routing"]["in_phase3"] and p == "3" and o["status"] in ("pending", "disagreement"):
                L.append("- Phase 3: **pending**")
        L += ["", "Merged fact list (%d fact(s); none dropped):" % len(o["facts"])]
        L += ["- [phase %s, %s] msg %s: \"%s\" bears on `%s`, %s%s" % (
            f["phase"], f["reviewer"], f["msg_id"], f["quote"], f["bears_on"], f["direction"],
            ", against own judgement" if f["against_own"] else "") for f in o["facts"]] or ["- (none)"]
        L.append("")
    with open(a.out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print("report: wrote %s" % a.out)


def _guess_section(outcomes, items, arm_stats, unblind):
    tot = hit = 0
    chance = 0.0
    for o in outcomes:
        g = o["phases"].get("2", {}).get("official_guess")
        if g:
            tot += 1
            hit += 1 if g["correct"] else 0
            chance += 1.0 / len(items[o["item_id"]]["answers"])
    L = ["## Phase-2 guess rates", ""]
    if tot:
        L.append("- Official answer guessed correctly: %d of %d (a blind guess reaches %.2f of %d on average)."
                 % (hit, tot, chance, tot))
    else:
        L.append("- Official answer guess: no guesses recorded.")
    if arm_stats:
        L.append("- Arm guessed correctly: %d of %d (a blind guess reaches %.2f of %d on average)." % arm_stats)
    elif unblind:
        L.append("- Arm guesses: not computed (pass --keys-dir with --unblind).")
    else:
        L.append("- Arm guesses: shown only with --unblind.")
    return L + [""]


def _arm_guess_stats(a, items, grades):
    ctx = Ctx(a.items, a.grades, a.verdicts, a.keys_dir)
    tot = hit = 0
    chance = 0.0
    for item in sorted(ctx.items):
        r = ctx.mapped_head(item)  # the mapped 2a (the original when it changed after the export), as the official guess
        g = r.get("guesses") if r else None
        if not g or not g.get("arms"):
            continue
        with open(os.path.join(a.keys_dir, "%s.json" % item), "r", encoding="utf-8") as fh:
            letters = json.load(fh)["letters"]
        arms = grades[item]["arms"]
        for letter, guess in g["arms"].items():
            aid = letters[letter]
            if aid in arms:
                tot += 1
                hit += 1 if arms[aid] == guess else 0
                chance += 1.0 / len(arms)
    return (hit, tot, chance, tot) if tot else None


# ------------------------------------------------------------------ importers

def cmd_import_beam(a):
    from importers import beam
    try:
        questions, sha = beam.load_questions(a.parquet, a.conv)
        agent_rows = read_jsonl(a.answers)
        items, grades, skipped = beam.build_records(a.conv, questions, agent_rows, a.seed, a.dataset, sha)
    except beam.ImportError_ as exc:
        raise UserError(str(exc))
    except ImportError as exc:
        raise UserError("pyarrow is needed to read a parquet file: %s" % exc)
    if not items:
        raise UserError("no question has an agent answer; nothing to write")
    write_jsonl_atomic(a.items_out, items)
    write_jsonl_atomic(a.grades_out, grades)
    print("import-beam: %d question(s) in the conversation, %d item(s) written, %d without an agent answer%s"
          % (len(questions), len(items), len(skipped), (" (question_no %s)" % ", ".join(map(str, skipped))) if skipped else ""))


def cmd_import_turns(a):
    scores = {}
    if a.grades:
        for r in read_jsonl(a.grades):
            scores[r["question_no"]] = r["rubric_scores"]
    out = []
    seen = set()
    for r in read_jsonl(a.turns):
        if r.get("kind") != "question":
            continue
        turn = r.get("turn", r.get("i"))
        if not isinstance(turn, int):
            raise UserError("a question row has no integer `turn` (or `i`) field")
        qn = turn - int(a.first_question_turn) + 1
        if qn < 1 or qn in seen:
            raise UserError("question turn %d gives question_no %d, which is out of range or repeated" % (turn, qn))
        seen.add(qn)
        out.append({"question_no": qn, "text": r.get("result"), "cited_ids": [], "rubric_scores": scores.get(qn),
                    "arm": a.arm_label})
    out.sort(key=lambda r: r["question_no"])
    write_jsonl_atomic(a.out, out)
    print("import-turns: wrote %d answer(s)" % len(out))


# ------------------------------------------------------------------ CLI

def build_parser():
    p = argparse.ArgumentParser(prog="score_review", description=__doc__.strip().splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, *opts):
        sp = sub.add_parser(name)
        for o in opts:
            flag, kw = (o if isinstance(o, tuple) else (o, {}))
            kw = dict(kw)
            if "action" not in kw and "default" not in kw and not kw.pop("optional", False):
                kw["required"] = True
            kw.pop("optional", None)
            sp.add_argument(flag, **kw)
        sp.set_defaults(fn=fn)

    opt = {"optional": True}
    add("import-beam", cmd_import_beam, "--parquet", "--conv", "--answers", "--items-out", "--grades-out", "--seed",
        ("--dataset", {"default": "BEAM"}))
    add("import-turns", cmd_import_turns, "--turns", "--first-question-turn", "--arm-label", "--out",
        ("--grades", opt))
    add("draw", cmd_draw, "--items", "--grades", "--run", "--n", "--seed", "--draws", "--verdicts")
    add("packet1", cmd_packet1, "--items", "--grades", "--item", ("--chat", opt))
    add("packet2", cmd_packet2, "--items", "--item", "--seed", "--keys-dir", "--out-dir", ("--chat", opt))
    add("record", cmd_record, "--verdicts", "--items", "--grades", "--phase", "--reviewer", "--file", ("--chat", opt),
        ("--supersedes", opt), ("--reason", opt))
    add("map", cmd_map, "--items", "--grades", "--verdicts", "--keys-dir", "--draws", "--out")
    add("export-criterion", cmd_export_criterion, "--items", "--grades", "--verdicts", "--item", "--reviewer", "--out")
    add("export-phase3", cmd_export_phase3, "--items", "--grades", "--verdicts", "--keys-dir", "--item", "--out")
    add("quote-check", cmd_quote_check, "--verdicts", "--chat")
    add("report", cmd_report, "--items", "--grades", "--verdicts", "--outcomes",
        ("--unblind", {"action": "store_true"}), ("--keys-dir", opt), "--out")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        args.fn(args)
    except (UserError, ValueError) as exc:
        print("score-review: refused: %s" % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
