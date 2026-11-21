"""Synthetic fixtures for the review-page tests. Every string here is invented; none is benchmark text.

The precomputed numbers are produced by a small independent routine (`_score`) written for the tests, not by
the tool, so a test that compares the tool with these rows compares two implementations.
"""
import collections
import json
import os

MARK = {"yes": 1.0, "partial": 0.5, "no": 0.0}
LABEL = {"not_stored": "Never stored", "over_caution": "Over-cautious", "recall_miss": "Stored but not recalled"}

# One entry per question: n, category, marks, adjusted marks (or None), grade, causes (keys), asked (bool),
# justified, finding ids linked. A tag built from the run and the question number makes every text field unique.
RUN_SPECS = {
    "RA": dict(conv=1, setup="aaaa1111", grader="hand-A", questions=[
        dict(n=1, cat="alpha_topic", marks=["yes", "yes"], adj=None, grade="pass", causes=[], asked=False,
             just="", findings=["F4"]),
        dict(n=2, cat="beta_topic", marks=["yes", "no"], adj=["yes", "yes"], grade="partial", causes=["not_stored"],
             asked=True, just="yes", findings=["F1"]),
        dict(n=3, cat="alpha_topic", marks=["no", "no", "partial"], adj=None, grade="fail",
             causes=["not_stored", "over_caution"], asked=False, just="", findings=["F2", "F4"]),
        dict(n=4, cat="beta_topic", marks=["partial", "partial"], adj=None, grade="partial",
             causes=["over_caution"], asked=True, just="no", findings=[]),
    ]),
    "RB": dict(conv=2, setup="bbbb2222", grader="hand-B", questions=[
        dict(n=1, cat="alpha_topic", marks=["yes", "partial"], adj=None, grade="partial", causes=["recall_miss"],
             asked=False, just="", findings=[]),
        dict(n=2, cat="beta_topic", marks=["yes", "yes"], adj=None, grade="pass", causes=[], asked=False,
             just="", findings=[]),
        dict(n=3, cat="alpha_topic", marks=["no", "partial"], adj=None, grade="fail", causes=["over_caution"],
             asked=True, just="partly", findings=["F5"]),
        dict(n=4, cat="beta_topic", marks=["yes", "no"], adj=None, grade="partial", causes=["not_stored"],
             asked=False, just="", findings=[]),
    ]),
}

# (finding_id, question_no, area, conv). F5 carries a conv of its own; F6 does not, so it is matched on its
# question_no in every conv.
FINDING_SPECS = [("F1", 2, "Official dataset", None), ("F2", 3, "Our student", None),
                 ("F3", None, "Our harness", None), ("F4", 1, "Our student", None),
                 ("F5", 3, "Our student", 2), ("F6", 3, "Our harness", None)]


def tag(run, n):
    return f"{run}{n}"


def _score(marks):
    return sum(MARK[m] for m in marks) / len(marks)


def answer_text(run, n):
    return f"ANSWERTEXT-{tag(run, n)}-zq \"quoted\" line1\nline2 </b> café"


def answers_file_texts():
    """The --answers-file content: 'conv:question_no' -> text."""
    return {f"{spec['conv']}:{q['n']}": answer_text(run, q["n"])
            for run, spec in RUN_SPECS.items() for q in spec["questions"]}


def build_data(omit=(), drop_findings=(), with_answer=True, poison_runs=False, poison_answers=False):
    """The five datasets {name: {"rows": [...], "meta": [...]}}. `omit` is a set of (conv, n) pairs left out
    entirely and `drop_findings` a set of finding ids left out (both used to build the kept-only baseline).
    `poison_runs` / `poison_answers` write a wrong shipped run score / question score (a build refuses these)."""
    runs, cats, causes, answers = [], [], [], []
    for run, spec in RUN_SPECS.items():
        qs = [q for q in spec["questions"] if (spec["conv"], q["n"]) not in omit]
        off, adj = [], []
        bycat = collections.defaultdict(list)
        cause_n = collections.Counter()
        grades = collections.Counter()
        asked_n = asked_j = 0
        for q in qs:
            o = _score(q["marks"])
            d = _score(q["adj"]) if q["adj"] else o
            off.append(o)
            adj.append(d)
            bycat[q["cat"]].append((o, d))
            grades[q["grade"]] += 1
            for c in q["causes"]:
                cause_n[LABEL[c]] += 1
            if q["asked"]:
                asked_n += 1
                asked_j += q["just"] == "yes"
            t = tag(run, q["n"])
            rubric = [dict(line=f"RUBRICLINE-{t}-{i}-zq \"r\" </i> ün", mark=m,
                           adjusted=(q["adj"][i] if q["adj"] else None)) for i, m in enumerate(q["marks"])]
            links = [f for f in q["findings"] if f not in drop_findings]
            row = dict(run_id=run, key=f"{run}:{q['n']}", question_no=q["n"], category=q["cat"],
                       question=f"QUESTIONTEXT-{t}-zq?", reference=f"REFERENCE-{t}-zq",
                       official_score=99.9 if (poison_answers and not answers) else round(100 * o, 1), adjusted_score=round(100 * d, 1), grade=q["grade"],
                       grader=spec["grader"], causes="; ".join(LABEL[c] for c in q["causes"]),
                       asked_back="yes" if q["asked"] else "no", ask_justified=q["just"], gate_cell=f"gate-{t}",
                       findings=", ".join(links), notes=f"NOTES-{t}-zq \"n\"",
                       rubric=json.dumps(rubric, ensure_ascii=False))
            if with_answer:
                row["answer"] = answer_text(run, q["n"])
            answers.append(row)
        if not qs:
            continue
        o_pct = round(100 * sum(off) / len(off), 1)
        a_pct = round(100 * sum(adj) / len(adj), 1)
        runs.append(dict(run_id=run, conv=spec["conv"], setup_hash=spec["setup"], grader=spec["grader"],
                         questions=len(qs), official_pct=99.9 if poison_runs else o_pct,
                         adjusted_pct=11.1 if poison_runs else a_pct,
                         adjust_delta=round(a_pct - o_pct, 1), pass_n=grades["pass"], partial_n=grades["partial"],
                         fail_n=grades["fail"], asked_back_n=asked_n, asked_back_justified_n=asked_j))
        for cat in sorted(bycat):
            v = bycat[cat]
            cats.append(dict(run_id=run, category=cat, label=cat.replace("_", " "), n=len(v),
                             official_pct=round(100 * sum(x for x, _ in v) / len(v), 1),
                             adjusted_pct=round(100 * sum(y for _, y in v) / len(v), 1)))
        key_of = {v: k for k, v in LABEL.items()}
        for lab, n in sorted(cause_n.items(), key=lambda kv: -kv[1]):
            causes.append(dict(run_id=run, cause=key_of[lab], label=lab, count=n))
    findings = [_finding(*s) for s in FINDING_SPECS if s[0] not in drop_findings]
    meta = [{"label": "note", "value": "fixture", "type": "text"}]
    return {n: {"rows": r, "meta": meta} for n, r in
            (("runs", runs), ("categories", cats), ("causes", causes), ("answers", answers),
             ("findings", findings))}


def _finding(fid, qno, area, conv):
    t = f"FIND{fid}"
    ver = [dict(at="2026-01-02T03:04:05Z", reader="reader-x", method="full_read", result="supports",
                exchanges_read=[1, 2], speakers_read=["user", "assistant"],
                evidence=[dict(exchange=1, speaker="user", quote=f"EVQUOTE-{t}-zq \"e\" </p>")],
                notes=f"VERNOTE-{t}-zq")]
    row = dict(finding_id=fid, question_no=qno, kind="student_behaviour", area=area, claim_type="behaviour",
               claim=f"CLAIM-{t}-zq", status="candidate", status_label="Suspected", severity="",
               opened_at="2026-01-02T03:04:05Z", checks=1, methods="full read",
               verifications=json.dumps(ver, ensure_ascii=False), report_line=f"REPORTLINE-{t}-zq",
               notes=f"FNOTES-{t}-zq")
    if conv is not None:
        row["conv"] = conv
    return row


def write_data(dirpath, data):
    os.makedirs(dirpath, exist_ok=True)
    for name, d in data.items():
        with open(os.path.join(dirpath, name + ".json"), "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False)
