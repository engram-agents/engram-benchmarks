#!/usr/bin/env python3
"""Build a human-review page for benchmark results: ONE html file from five row files.

    build_page.py --data DIR --out FILE.html [--answers-file PATH] [--withhold FILE --withhold-reason TEXT]
                  [--d3 PATH] [--title TEXT] [--official-note TEXT]

The tool holds no data. It reads the result files it is given, checks them, and writes the page. Exit 0 on
success; exit 2 on any bad input, with the reason on stderr and nothing written. The inputs, the withhold
contract and the offline mode are described in README.md next to this file.
"""
import argparse
import collections
import hashlib
import html
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EXIT_BAD_INPUT = 2

# d3 7.8.5, minified. How the hash was measured: see README.md, "Offline mode".
D3_URL = "https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"
D3_SHA256 = "d6b03aefc9f6c44c7bc78713679c78c295028fa914319119e5cc4b4954855b1c"

NAMES = ["runs", "categories", "causes", "answers", "findings"]
MARK = {"yes": 1.0, "partial": 0.5, "no": 0.0}
GRADES = ("pass", "partial", "fail")

# The fields the page code reads from each row, with the type it needs. 'any' = present, any value.
# 'str?' / 'int?' = a string / an integer or null. 'conv' = a conversation id: a non-negative integer or a
# string of ASCII digits (normalised to int on load). Read off page.html, not from memory: see README.md.
SCHEMA = {
    "runs": {"run_id": "str", "conv": "conv", "setup_hash": "str", "grader": "str", "questions": "num",
             "official_pct": "num",
             "adjusted_pct": "num", "adjust_delta": "num", "pass_n": "num", "partial_n": "num", "fail_n": "num",
             "asked_back_n": "num", "asked_back_justified_n": "num"},
    "categories": {"run_id": "str", "category": "str", "label": "str", "n": "num", "official_pct": "num",
                   "adjusted_pct": "num"},
    "causes": {"run_id": "str", "cause": "str", "label": "str", "count": "num"},
    "answers": {"run_id": "str", "key": "str", "question_no": "int", "category": "str", "question": "str",
                "reference": "str", "official_score": "num", "adjusted_score": "num", "grade": "str",
                "grader": "str", "causes": "str", "asked_back": "str", "ask_justified": "str",
                "gate_cell": "any", "findings": "str", "notes": "str", "rubric": "str"},
    "findings": {"finding_id": "str", "question_no": "int?", "area": "str", "claim_type": "str", "claim": "str",
                 "status": "str", "status_label": "str", "severity": "str", "opened_at": "str", "checks": "num",
                 "verifications": "str", "report_line": "str", "notes": "str"},
}
# `answer` (the student's full text) is read by the page too; it is checked separately because it may come
# from --answers-file instead of the row.


class InputError(Exception):
    """Bad input. main() prints it to stderr and exits 2 without writing anything."""


# ---------------------------------------------------------------------------------------------- loading
def _kind_ok(kind, v):
    if kind == "any":
        return True
    if kind == "str":
        return isinstance(v, str)
    if kind == "str?":
        return v is None or isinstance(v, str)
    if kind == "num":
        return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
    if kind == "int":
        return isinstance(v, int) and not isinstance(v, bool)
    if kind == "int?":
        return v is None or (isinstance(v, int) and not isinstance(v, bool))
    if kind == "conv":
        return _conv(v) is not None
    raise AssertionError(kind)


def _conv(v):
    """A conversation id as an int, or None when v is not one (bool, float, negative, non-digit text)."""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v if v >= 0 else None
    if isinstance(v, str) and re.fullmatch(r"[0-9]+", v):
        return int(v)
    return None


def _no_constant(token):
    raise ValueError(f"{token} is not a finite number")


def _finite_float(text):
    v = float(text)
    if not math.isfinite(v):
        raise ValueError(f"{text} is not a finite number")
    return v


def load_dataset(data_dir, name):
    path = os.path.join(data_dir, name + ".json")
    if not os.path.isfile(path):
        raise InputError(f"{name}.json: file not found in {data_dir}")
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh, parse_constant=_no_constant, parse_float=_finite_float)
    except (OSError, ValueError) as e:
        raise InputError(f"{name}.json: cannot be read as JSON ({e})")
    if not isinstance(d, dict) or not isinstance(d.get("rows"), list):
        raise InputError(f"{name}.json: must be an object with a 'rows' list")
    for i, row in enumerate(d["rows"]):
        if not isinstance(row, dict):
            raise InputError(f"{name}.json: row {i} is not an object")
        for field, kind in SCHEMA[name].items():
            if field not in row:
                raise InputError(f"{name}.json: row {i}: missing field {field!r}")
            if not _kind_ok(kind, row[field]):
                raise InputError(f"{name}.json: row {i}: field {field!r} must be {kind}, got {row[field]!r}")
        if row.get("conv") is not None:  # runs.conv (required) and findings.conv (optional), one rule
            c = _conv(row["conv"])
            if c is None:
                raise InputError(f"{name}.json: row {i}: field 'conv' must be an integer or a string of digits, got {row['conv']!r}")
            row["conv"] = c
    return d["rows"]


def parse_rubric(row, where):
    """The rubric of an answer row: a JSON string holding [{line, mark, adjusted}]. Returns the question's
    (official marks, adjusted marks); a line without an adjusted mark keeps its own mark in the adjusted list."""
    try:
        lines = json.loads(row["rubric"])
    except ValueError:
        raise InputError(f"{where}: field 'rubric' is not valid JSON")
    if not isinstance(lines, list) or not lines:
        raise InputError(f"{where}: field 'rubric' must be a non-empty list of rubric lines")
    off, adj = [], []
    for ln in lines:
        if not isinstance(ln, dict) or ln.get("mark") not in MARK:
            bad = ln.get("mark") if isinstance(ln, dict) else ln
            raise InputError(f"{where}: rubric mark {bad!r} is not one of yes / partial / no")
        a = ln.get("adjusted")
        if a is not None and a not in MARK:
            raise InputError(f"{where}: rubric adjusted mark {a!r} is not one of yes / partial / no")
        off.append(ln["mark"])
        adj.append(a if a is not None else ln["mark"])
    return off, adj


def parse_withhold(path):
    """A file of `conv:question_no` lines. Blank lines and lines starting with # are ignored."""
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError as e:
        raise InputError(f"--withhold {path}: cannot be read ({e})")
    pairs = set()
    for ln in lines:
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        m = re.fullmatch(r"([0-9]+):([0-9]+)", s)
        if not m or int(m.group(2)) < 1:
            raise InputError(f"--withhold {path}: line {ln!r} is not conv:question_no (question_no >= 1)")
        pairs.add((int(m.group(1)), int(m.group(2))))
    if not pairs:
        raise InputError(f"--withhold {path}: no pairs in the file")
    return pairs


def answer_texts(path):
    """Full answer texts keyed by (conv, question_no), from a JSON object {"conv:question_no": "text"}."""
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, ValueError) as e:
        raise InputError(f"--answers-file {path}: cannot be read as JSON ({e})")
    if not isinstance(d, dict):
        raise InputError(f"--answers-file {path}: must be a JSON object of 'conv:question_no' -> text")
    out = {}
    for k, v in d.items():
        m = re.fullmatch(r"([0-9]+):([0-9]+)", k)
        if not m:
            raise InputError(f"--answers-file {path}: key {k!r} is not conv:question_no")
        if not isinstance(v, str):
            raise InputError(f"--answers-file {path}: the text for {k!r} is not a string")
        out[(int(m.group(1)), int(m.group(2)))] = v
    return out


def load_d3(path):
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError as e:
        raise InputError(f"--d3 {path}: cannot be read ({e})")
    got = hashlib.sha256(raw).hexdigest()
    if got != D3_SHA256:
        raise InputError(f"--d3 {path}: sha256 {got} does not match the pinned d3 7.8.5 hash {D3_SHA256}")
    text = raw.decode("utf-8")
    if re.search(r"</script", text, re.I):
        raise InputError(f"--d3 {path}: contains a closing script tag and cannot be inlined")
    return text


# -------------------------------------------------------------------------------------------- recompute
def _pct(xs):
    return round(100 * sum(xs) / len(xs), 1) if xs else None


def _mean(marks):
    return sum(MARK[m] for m in marks) / len(marks)


def is_withheld(withheld, question_no, conv=None):
    """THE one place that decides whether a row is about a withheld (conv, question_no) pair. `conv` is the
    row's conversation, or None when the row does not carry one (a finding without `conv`): then the
    question number alone decides, in any conv. Fail-closed: it can over-match, never under-match."""
    return question_no is not None and any(q == question_no and (conv is None or c == conv) for c, q in withheld)


# A shipped percentage is rounded to one decimal, so it can sit up to 0.05 from the exact mean. Anything
# further apart than that (plus float noise) is a different number, not a rounding.
SHIPPED_TOLERANCE = 0.05 + 1e-9


def check_shipped(data):
    """Recompute every question and every run over ALL the input rows and compare with the scores the input
    shipped (`official_score` / `adjusted_score` on answer rows; `official_pct` / `adjusted_pct` on run rows).
    A difference beyond SHIPPED_TOLERANCE is InputError. This re-checks the formula against the input's own
    numbers on every build. It cannot catch an input whose shipped scores were computed the same wrong way.
    A run with no answer row in the input has nothing to recompute and is skipped."""
    by_run = collections.defaultdict(list)
    for a in data["answers"]:
        om, am = parse_rubric(a, f"answers.json {a['key']}")
        o, d = 100 * _mean(om), 100 * _mean(am)
        for field, exact in (("official_score", o), ("adjusted_score", d)):
            if not abs(exact - a[field]) <= SHIPPED_TOLERANCE:  # written so NaN / inf fail it
                raise InputError(f"answers.json {a['key']}: shipped {field} {a[field]} but its rubric recomputes "
                                 f"to {exact:.2f}")
        by_run[a["run_id"]].append((o, d))
    for r in data["runs"]:
        qs = by_run.get(r["run_id"])
        if not qs:
            continue
        for field, exact in (("official_pct", sum(x for x, _ in qs) / len(qs)),
                             ("adjusted_pct", sum(y for _, y in qs) / len(qs))):
            if not abs(exact - r[field]) <= SHIPPED_TOLERANCE:  # written so NaN / inf fail it
                raise InputError(f"runs.json run {r['run_id']}: shipped {field} {r[field]} but its {len(qs)} answer "
                                 f"rows recompute to {exact:.2f}")


def recompute(runs, cats, causes, answers, withheld):
    """Run rows, category rows and cause rows computed from the answer rows that are NOT withheld.

    Question score = mean of its rubric lines (yes 1, partial 0.5, no 0); the adjusted score uses a line's
    adjusted mark where it has one. Run score = mean over the kept questions. Nothing is read from the input's
    precomputed scores or counts; the input rows only supply the labels and the order. Each returned run row
    carries `questions` (N, kept) and `questions_total` (M, all of that run's answer rows in the input), and
    ONLY its SCHEMA fields plus the ones computed here: any other field of the input run row is dropped.

    Orders: runs keep the input's order; within a run the answers are taken in question_no order; categories are
    sorted by category name; causes are sorted by count, highest first, ties in first-seen order (question_no
    order, then the order of a question's own `causes` text)."""
    conv_of = {r["run_id"]: r["conv"] for r in runs}
    cat_label = {(c["run_id"], c["category"]): c["label"] for c in cats}
    cause_key = {c["label"]: c["cause"] for c in causes}
    total = collections.Counter(a["run_id"] for a in answers)
    kept = collections.defaultdict(list)
    for a in sorted(answers, key=lambda r: r["question_no"]):
        if not is_withheld(withheld, a["question_no"], conv_of[a["run_id"]]):
            kept[a["run_id"]].append(a)
    out_runs, out_cats, out_causes = [], [], []
    for r in runs:
        rows = kept.get(r["run_id"], [])
        off, adj = [], []
        bycat = collections.defaultdict(list)
        cause_n = collections.Counter()
        grades = collections.Counter()
        asked = justified = 0
        for a in rows:
            where = f"answers.json {a['key']}"
            om, am = parse_rubric(a, where)
            o, d = _mean(om), _mean(am)
            off.append(o)
            adj.append(d)
            bycat[a["category"]].append((o, d))
            if a["grade"] not in GRADES:
                raise InputError(f"{where}: grade {a['grade']!r} is not one of pass / partial / fail")
            grades[a["grade"]] += 1
            for lab in [x for x in a["causes"].split("; ") if x]:
                if lab not in cause_key:
                    raise InputError(f"{where}: cause label {lab!r} is not in causes.json")
                cause_n[lab] += 1
            if a["asked_back"] == "yes":
                asked += 1
                justified += a["ask_justified"] == "yes"
        o_pct, a_pct = _pct(off), _pct(adj)
        computed = dict(questions=len(rows), questions_total=total[r["run_id"]], official_pct=o_pct,
                        adjusted_pct=a_pct,
                        adjust_delta=None if o_pct is None else round(a_pct - o_pct, 1),
                        pass_n=grades["pass"], partial_n=grades["partial"], fail_n=grades["fail"],
                        asked_back_n=asked, asked_back_justified_n=justified)
        # Default-deny: the row is its SCHEMA fields from the input plus what is computed here; an unknown input
        # field is dropped. The allowed set is generated from those two, never listed a second time. The
        # categories and causes rows below are built from explicit keys, so they are already closed the same way.
        out_runs.append({**{k: r[k] for k in SCHEMA["runs"] if k in r}, **computed})
        for cat in sorted(bycat):
            v = bycat[cat]
            out_cats.append(dict(run_id=r["run_id"], category=cat,
                                 label=cat_label.get((r["run_id"], cat), cat.replace("_", " ")), n=len(v),
                                 official_pct=_pct([x for x, _ in v]), adjusted_pct=_pct([y for _, y in v])))
        for lab, n in sorted(cause_n.items(), key=lambda kv: -kv[1]):
            out_causes.append(dict(run_id=r["run_id"], cause=cause_key[lab], label=lab, count=n))
    return {"runs": out_runs, "categories": out_cats, "causes": out_causes}


def _split_ids(s):
    """The finding ids in an answer row's `findings` text, in order."""
    return [x.strip() for x in s.split(",") if x.strip()]


def apply_withhold(data, withheld):
    """Remove every row about a withheld question; recompute what was derived from them. Returns the new
    datasets (rows only). A finding is DROPPED, whole, when it touches a withheld question: its own
    question_no matches one (in the finding's `conv` when it has one, else in any conv) or a withheld answer
    row links to it. A finding cannot be partly redacted without a guess about which words carry content."""
    conv_of = {r["run_id"]: r["conv"] for r in data["runs"]}
    for a in data["answers"]:
        if a["run_id"] not in conv_of:
            raise InputError(f"answers.json {a['key']}: run_id {a['run_id']!r} is not in runs.json")
    for c, q in sorted(withheld):
        if not any(is_withheld({(c, q)}, a["question_no"], conv_of[a["run_id"]]) for a in data["answers"]):
            raise InputError(f"--withhold: {c}:{q} matches no answer row in the data (a typo?)")
    keep, gone = [], []
    for a in data["answers"]:
        (gone if is_withheld(withheld, a["question_no"], conv_of[a["run_id"]]) else keep).append(a)
    linked = set()
    for a in gone:
        linked |= set(_split_ids(a["findings"]))
    dropped = set()
    for f in data["findings"]:
        if is_withheld(withheld, f["question_no"], f.get("conv")) or f["finding_id"] in linked:
            dropped.add(f["finding_id"])
    derived = recompute(data["runs"], data["categories"], data["causes"], data["answers"], withheld)
    answers = []
    for a in keep:
        answers.append(dict(a, findings=", ".join(i for i in _split_ids(a["findings"]) if i not in dropped)))
    return {"runs": derived["runs"], "categories": derived["categories"], "causes": derived["causes"],
            "answers": answers, "findings": [f for f in data["findings"] if f["finding_id"] not in dropped]}


# ------------------------------------------------------------------------------------------------ render
SHIM = r"""
(function () {
  const RAW = window.__BS_DATA__;
  const draws = new Map(), listeners = [];
  const dash = {
    colors: ['var(--s0)', 'var(--s1)', 'var(--s2)', 'var(--s3)'],
    data(id) { const d = RAW[id]; if (!d) return {status: 'missing', data: [], meta: []};
      const rows = d.rows || []; const out = {status: 'ok', data: rows, meta: d.meta || [], truncated: false, refreshing: false};
      out.data.columns = rows.length ? Object.keys(rows[0]) : []; return out; },
    onData(fn) { listeners.push(fn); try { fn(); } catch (e) { console.error(e); } },
    draw(name, fn) {
      if (fn === undefined) { const f = draws.get(name); if (f) runDraw(name, f); return; }
      draws.set(name, fn);
    },
    calc() {}, loader() {}, refresh() {}, params() { return {}; }, setParams() {}, resetParams() {}, setLink() {},
  };
  function runDraw(name, fn) {
    document.querySelectorAll('[data-draw="' + name + '"]').forEach((el) => {
      try {
        if (typeof fn === 'function') fn(el);
        else { if (!el.__made) el.__made = fn.mount ? fn.mount(el) : undefined; if (fn.update) fn.update(el, el.__made); }
      } catch (e) { console.error('draw ' + name, e); }
    });
  }
  function all() { listeners.forEach((f) => { try { f(); } catch (e) { console.error(e); } }); draws.forEach((fn, n) => runDraw(n, fn)); }
  window.dash = dash;
  window.addEventListener('DOMContentLoaded', all);
  let t; window.addEventListener('resize', () => { clearTimeout(t); t = setTimeout(all, 150); });
})();
"""

TOKENS = """
:root { --color-fg:#1d2126; --color-fg-muted:#5d6670; --color-bg:#f6f7f8; --color-panel:#ffffff; --color-border-line:#dde1e5;
  --color-ok:#1f7a4d; --color-warn:#9a6400; --color-bad:#b3261e; --s0:#3b6fb6; --s1:#c9893a; --s2:#5b9a7d; --s3:#8a6bb8;
  --font-anthropic-sans: Inter, system-ui, -apple-system, "Segoe UI", sans-serif; --font-anthropic-serif: Georgia, "Times New Roman", serif;
  --cds-font-size-caption:12px; --cds-font-size-body:14px; --cds-font-size-heading:17px; --cds-font-size-title:30px; --cds-font-weight-medium:600;
  --cds-gap-xs:4px; --cds-gap-sm:8px; --cds-gap-md:14px; --cds-gap-lg:20px; --cds-gap-xl:28px;
  --cds-pad-xs:4px; --cds-pad-sm:8px; --cds-pad-md:12px; --cds-pad-lg:16px; --cds-radius:8px;
  --cds-chart-grid:#e3e6ea; --cds-text-secondary:#5d6670; --cds-surface-popover:#ffffff; --cds-border:#dde1e5; --cds-shadow-popover:0 4px 14px rgba(0,0,0,.12); }
@media (prefers-color-scheme: dark) { :root { --color-fg:#e7eaee; --color-fg-muted:#a3acb6; --color-bg:#15181c; --color-panel:#1d2126;
  --color-border-line:#2f353c; --color-ok:#5cc58f; --color-warn:#e2b04a; --color-bad:#f08a80; --s0:#78a6e6; --s1:#e3a85b;
  --cds-chart-grid:#2c3238; --cds-text-secondary:#a3acb6; --cds-surface-popover:#23282e; --cds-border:#353b42; color-scheme: dark; } }
body { margin:0; background:var(--color-bg); color:var(--color-fg); font-family:var(--font-anthropic-sans); font-size:14px; }
#dash-root { max-width: 1080px; margin: 0 auto; padding-block: 24px; padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); }
"""


FREE_TEXT_NOTICE = ("Free text on the questions that remain (notes, findings) is shown as written and is not "
                    "checked for mentions of the withheld questions.")


def banner_html(withheld, reason):
    by_conv = collections.defaultdict(list)
    for c, q in sorted(withheld):
        by_conv[c].append(q)
    listing = "; ".join(f"conv {c}: " + ", ".join(f"Q{q}" for q in qs) for c, qs in sorted(by_conv.items()))
    n = len(withheld)
    reason = reason.strip()
    if reason and reason[-1] not in ".!?":
        reason += "."
    return (f'<div class="bs-card" id="withheld-notice" role="note"><b>{n} question{"s" if n != 1 else ""} '
            f"withheld</b> ({html.escape(listing)}). Reason: {html.escape(reason)} Their text, grades, notes and "
            f"linked findings are not in this file; scores below are recomputed over the questions that "
            f"remain. {html.escape(FREE_TEXT_NOTICE)}</div>")


# SCORE-REVIEW-PRINCIPLES.md section 7: "This sentence, or its equivalent, wherever an adjusted score appears".
# Quoted exactly; only its first letter is capitalised for display. It is FIXED: no option and no input
# switches it off, and the tests read the principles file to check this text against it.
INDEPENDENCE_SENTENCE = ("All reviewers belong to the team that builds the agent under test. These principles "
                         "reduce our bias; they do not make the adjusted score independent.")


def independence_html():
    return f'<p class="bs-k bs-independence">{html.escape(INDEPENDENCE_SENTENCE)}</p>'


def official_note_html(note):
    """The note shown beside every place 'Official' labels a column or chart, or '' when no note was given.
    Escaped like the withhold reason; the markup is the same in every section that carries it."""
    if note is None:
        return ""
    return f'<p class="bs-k bs-official-note">{html.escape(note.strip())}</p>'


def blob_json(datasets):
    blob = json.dumps({n: {"rows": datasets[n]} for n in NAMES}, ensure_ascii=False)
    # keep the data from closing or re-opening the script block it sits in
    return blob.replace("</", "<\\/").replace("<!--", "<\\u0021--")


def render(datasets, title, banner, d3_text, official_note=None):
    with open(os.path.join(HERE, "page.html"), encoding="utf-8") as fh:
        page = fh.read()
    t = html.escape(title)
    # ONE pass over the template: a marker-shaped string inside a filled-in value (a title, the note) is text,
    # never substituted again.
    fill = {"TITLE": t, "BANNER": banner, "OFFICIAL_NOTE": official_note_html(official_note),
            "INDEPENDENCE": independence_html()}
    page = re.sub(r"__(" + "|".join(fill) + r")__", lambda m: fill[m.group(1)], page)
    d3_tag = f"<script>{d3_text}</script>" if d3_text is not None else f'<script src="{D3_URL}"></script>'
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{t}</title>
<style>{TOKENS}</style>
{d3_tag}
<script>window.__BS_DATA__ = {blob_json(datasets)};</script>
<script>{SHIM}</script>
</head><body><div id="dash-root">
{page}
</div></body></html>"""


# --------------------------------------------------------------------------------------------------- main
def build(args):
    if (args.withhold is None) != (args.withhold_reason is None):
        raise InputError("--withhold and --withhold-reason go together (the page must say why questions are withheld)")
    if not os.path.isdir(args.data):
        raise InputError(f"--data {args.data}: not a directory")
    data = {n: load_dataset(args.data, n) for n in NAMES}
    # `is not None`, never truthiness: an unset shell variable gives '' and must fail, not switch the option off
    if args.withhold_reason is not None and not args.withhold_reason.strip():
        raise InputError("--withhold-reason is empty: say why the questions are withheld")
    if args.official_note is not None and not args.official_note.strip():
        raise InputError("--official-note is empty: give the text to show beside the official columns and charts")
    d3_text = load_d3(args.d3) if args.d3 is not None else None
    withheld = parse_withhold(args.withhold) if args.withhold is not None else None
    texts = answer_texts(args.answers_file) if args.answers_file is not None else {}
    conv_of = {r["run_id"]: r["conv"] for r in data["runs"]}
    for a in data["answers"]:
        if a["run_id"] not in conv_of:
            raise InputError(f"answers.json {a['key']}: run_id {a['run_id']!r} is not in runs.json")
        t = texts.get((conv_of[a["run_id"]], a["question_no"]))
        if t is not None:
            a["answer"] = t
    check_shipped(data)  # over ALL input rows, before anything is withheld; also rejects a bad rubric
    banner = ""
    if withheld is not None:
        datasets = apply_withhold(data, withheld)
        banner = banner_html(withheld, args.withhold_reason)
    else:
        datasets = data
    for a in datasets["answers"]:
        if not isinstance(a.get("answer"), str):
            raise InputError(f"answers.json {a['key']}: no 'answer' text (not in the row, not in --answers-file)")
    return render(datasets, args.title, banner, d3_text, args.official_note), d3_text is not None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build a human-review page from five result row files.")
    ap.add_argument("--data", required=True, help="directory with runs/categories/causes/answers/findings .json")
    ap.add_argument("--out", required=True, help="html file to write")
    ap.add_argument("--answers-file", help="JSON {'conv:question_no': full answer text}")
    ap.add_argument("--withhold", help="file of conv:question_no pairs to leave out of the page")
    ap.add_argument("--withhold-reason", help="why those questions are withheld (shown on the page; required with --withhold)")
    ap.add_argument("--d3", help="local d3 7.8.5 min.js (checked against a pinned sha256); makes the page offline")
    ap.add_argument("--title", default="BEAM Scorecard", help="page title")
    ap.add_argument("--official-note", help="text shown beside every column and chart labelled Official (which grader "
                    "produced it, and any caveat for this page); one text carries all of it")
    args = ap.parse_args(argv)
    try:
        page, offline = build(args)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(page)
    except InputError as e:
        print(f"build_page: {e}", file=sys.stderr)
        return EXIT_BAD_INPUT
    except OSError as e:
        print(f"build_page: cannot write {args.out} ({e})", file=sys.stderr)
        return EXIT_BAD_INPUT
    print(f"wrote {args.out} ({len(page.encode('utf-8'))} bytes)")
    if not offline:
        print("note: no --d3 given, so the page loads d3 from a CDN and needs network access to draw its charts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
