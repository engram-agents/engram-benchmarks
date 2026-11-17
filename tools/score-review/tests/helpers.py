"""Shared helpers for the score-review contract tests. All fixtures are synthetic."""
import hashlib
import json
import pathlib
import subprocess
import sys

TOOL = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = TOOL / "score_review.py"
if str(TOOL) not in sys.path:
    sys.path.insert(0, str(TOOL))

CHAT = (
    "## msg 1 | user | 2026-01-01\n"
    "The synthetic plant sits on the north shelf.\n\n"
    "## msg 2 | assistant | 2026-01-02\n"
    "Watering happens every Tuesday.\n"
)
QUOTE_OK = "north shelf"

DEFAULT_CITED = {"official": [1], "a1": [1, 2], "a2": []}  # mixed on purpose: some answers cite, one does not
TEXT_TOKEN = {"official": "alpha", "a1": "beta", "a2": "gamma"}
ITEM_IDS = ["i01", "i02", "i03", "i04", "i05", "i06"]


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True)


def assert_refused(cp):
    assert cp.returncode == 1, (cp.returncode, cp.stdout, cp.stderr)
    assert "refused" in cp.stderr.lower(), cp.stderr


def read_jsonl(path):
    p = pathlib.Path(path)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path, obj):
    pathlib.Path(path).write_text(json.dumps(obj), encoding="utf-8")
    return str(path)


def forge_verdict(verdicts_path, **fields):
    """Append a hand-built, hash-valid verdict that `record` itself would refuse (for fixtures of states the
    order rules forbid, e.g. a phase-2 record with no phase-1 record)."""
    import score_review
    rec = {"schema_version": 1, "recorded_at": "2026-01-01T00:00:00Z", "step": None, "keyed_by": "label",
           "fuller_answer": None, "facts": [], "guesses": None, "minutes_spent": None, "notes": "",
           "supersedes": None, "reason": None}
    rec.update(fields)
    rec["record_sha256"] = score_review.canonical_sha(rec)
    with open(verdicts_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")
    return rec["record_sha256"]


def level(scores):
    if all(s == 1.0 for s in scores):
        return "full"
    if all(s == 0.0 for s in scores):
        return "zero"
    return "partial"


LEVEL_TO_JUDGEMENT = {"full": "correct", "partial": "partly", "zero": "wrong"}


def hid(*parts):
    return hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:8]


class Store:
    """A synthetic study store: items, grades, chat, with opaque per-item answer ids."""

    def __init__(self, root, item_ids=ITEM_IDS, plan=None, cited=None):
        self.root = pathlib.Path(root)
        self.item_ids = list(item_ids)
        self.plan = plan or {}
        self.cited = dict(DEFAULT_CITED, **(cited or {}))
        self.items = self.root / "items.jsonl"
        self.grades = self.root / "grades.jsonl"
        self.verdicts = self.root / "verdicts.jsonl"
        self.draws = self.root / "draws.jsonl"
        self.keys = self.root / "keys"
        self.chat = self.root / "chat.md"
        self.meta = {}
        self.write()

    def write(self):
        self.root.mkdir(parents=True, exist_ok=True)
        irows, grows = [], []
        for k, iid in enumerate(self.item_ids):
            roles = ["official", "a1", "a2"]
            ids = {r: hid("fx", iid, r) for r in roles}
            self.meta[iid] = ids
            cited = self.cited
            answers = [
                {"answer_id": ids[r], "text": "text-%s-%s zorp" % (iid, TEXT_TOKEN[r]), "cited_ids": cited[r]}
                for r in roles
            ]
            answers.sort(key=lambda a: a["answer_id"])
            irows.append({"schema_version": 1, "item_id": iid, "question": "Question text %s?" % iid, "answers": answers})
            plan = self.plan.get(iid, {})
            scores = {ids["a1"]: plan.get("a1", [1.0, 1.0]), ids["a2"]: plan.get("a2", [1.0, 1.0])}
            grows.append({
                "schema_version": 1, "item_id": iid, "study": "fx", "conv": "c1", "question_no": k + 1,
                "official_id": ids["official"],
                "rubric_lines": ["RUBRIC-TOKEN %s line one" % iid, "RUBRIC-TOKEN %s line two" % iid],
                "scores": scores, "scale": {"max": 1.0, "min": 0.0},
                "category": "CATEGORY-TOKEN", "metadata": {"tests_for": "META-TOKEN"},
                "arms": {ids["a1"]: "ARM-TOKEN-ONE", ids["a2"]: "ARM-TOKEN-TWO"},
                "source_ref": {"dataset": "synthetic", "data_sha256_prefix": "0" * 12, "conv": "c1"},
            })
        self.items.write_text("".join(json.dumps(r) + "\n" for r in irows), encoding="utf-8")
        self.grades.write_text("".join(json.dumps(r) + "\n" for r in grows), encoding="utf-8")
        self.chat.write_text(CHAT, encoding="utf-8")

    # --- ids and judgements
    def oid(self, item):
        return self.meta[item]["official"]

    def a1(self, item):
        return self.meta[item]["a1"]

    def a2(self, item):
        return self.meta[item]["a2"]

    def levels(self, item):
        p = self.plan.get(item, {})
        return {self.a1(item): level(p.get("a1", [1.0, 1.0])), self.a2(item): level(p.get("a2", [1.0, 1.0]))}

    def honest(self, item, **override):
        """Judgement keyed by answer id: official correct, agents matching their official level."""
        j = {self.oid(item): "correct"}
        for aid, lv in self.levels(item).items():
            j[aid] = LEVEL_TO_JUDGEMENT[lv]
        for role, val in override.items():
            j[self.meta[item][role]] = val
        return j

    def fact(self, bears_on, quote=QUOTE_OK, msg_id=1, direction="supports", against_own=False):
        return {"msg_id": msg_id, "quote": quote, "bears_on": bears_on, "direction": direction, "against_own": against_own}

    def vdict(self, item, judgement, facts=None, guesses=None, fuller=None, notes="", minutes=5):
        return {"item_id": item, "judgement": judgement, "fuller_answer": fuller,
                "facts": facts if facts is not None else [], "guesses": guesses,
                "minutes_spent": minutes, "notes": notes}

    def record(self, item, phase, reviewer, vd, chat=True, extra=()):
        f = write_json(self.root / ("vf-%s-%s-%s.json" % (item, phase, reviewer)), vd)
        args = ["record", "--verdicts", self.verdicts, "--items", self.items, "--grades", self.grades, "--phase", phase,
                "--reviewer", reviewer, "--file", f]
        if chat:
            args += ["--chat", self.chat]
        return run(*args, *extra)

    def must_record(self, item, phase, reviewer, vd, **kw):
        cp = self.record(item, phase, reviewer, vd, **kw)
        assert cp.returncode == 0, cp.stderr
        return cp.stdout.strip()

    def p1(self, item, judgement=None, reviewer="lead", **kw):
        return self.must_record(item, 1, reviewer, self.vdict(item, judgement or self.honest(item), **kw))

    def packet2(self, item, seed="seedx"):
        cp = run("packet2", "--items", self.items, "--item", item, "--seed", seed, "--keys-dir", self.keys,
                 "--out-dir", self.root / "packets" / "phase2")
        assert cp.returncode == 0, cp.stderr
        return cp

    def key(self, item):
        return json.loads((self.keys / ("%s.json" % item)).read_text())

    def letter_of(self, item, answer_id):
        for letter, aid in self.key(item)["letters"].items():
            if aid == answer_id:
                return letter
        raise KeyError(answer_id)

    def p2(self, item, judgement_by_id, reviewer="expert", facts_by_id=None, guesses=None, fuller=None):
        if not (self.keys / ("%s.json" % item)).exists():
            self.packet2(item)
        if "ambiguous" in judgement_by_id:
            jl = dict(judgement_by_id)
        else:
            jl = {self.letter_of(item, a): v for a, v in judgement_by_id.items()}
        facts = [self.fact(self.letter_of(item, a), **kw) for a, kw in (facts_by_id or [])]
        return self.must_record(item, 2, reviewer, self.vdict(item, jl, facts=facts, guesses=guesses, fuller=fuller))

    def p3(self, item, judgement, facts=None, reviewer="owner", fuller=None):
        return self.must_record(item, 3, reviewer, self.vdict(item, judgement, facts=facts or [], fuller=fuller))

    def write_draws(self, drawn):
        row = {"schema_version": 1, "run": "r1", "n": len(drawn), "seed": "s", "drawn_item_ids": drawn,
               "eligible_item_ids": drawn, "drawn_at": "2026-01-01T00:00:00Z"}
        self.draws.write_text(json.dumps(row) + "\n", encoding="utf-8")

    def map(self, out=None):
        out = out or (self.root / "outcomes.jsonl")
        cp = run("map", "--items", self.items, "--grades", self.grades, "--verdicts", self.verdicts,
                 "--keys-dir", self.keys, "--draws", self.draws, "--out", out)
        return cp, out

    def outcomes(self):
        cp, out = self.map()
        assert cp.returncode == 0, cp.stderr
        return {r["item_id"]: r for r in read_jsonl(out)}


def build_flow(root):
    """The standard scenario used by the map/report/export tests.

    i01 full, not selected; i02 partial a1; i03 zero a1; i04 full + drawn control; i05 key wrong;
    i06 phase 1 grading error on a2, phase 2 disagrees; i07 a1 has one line at exactly half the scale
    max (partial, so set a), the only thing that puts it in phase 2.
    """
    plan = {"i02": {"a1": [0.37, 0.37]}, "i03": {"a1": [0.0, 0.0]}, "i07": {"a1": [1.0, 0.5]}}
    s = Store(root, item_ids=ITEM_IDS + ["i07"], plan=plan)
    s.write_draws(["i04"])
    for item in s.item_ids:
        j = s.honest(item)
        if item == "i05":
            j[s.oid(item)] = "partly"
        if item == "i06":
            j[s.a2(item)] = "wrong"
        facts = None
        if item == "i02":
            facts = [s.fact(s.oid(item)), s.fact(s.a1(item), direction="against", against_own=True)]
        s.p1(item, j, facts=facts, fuller=("fuller text" if item == "i05" else None))
    for item in ["i02", "i03", "i04", "i05", "i06", "i07"]:
        j = s.honest(item)
        if item == "i05":
            j[s.oid(item)] = "partly"
        facts_by_id = None
        if item == "i02":
            facts_by_id = [(s.oid(item), {}), (s.a1(item), {"quote": "Tuesday", "msg_id": 2}),
                           (s.a2(item), {"direction": "against"})]
        s.p2(item, j, facts_by_id=facts_by_id, fuller=("fuller text" if item == "i05" else None))
    s.p3("i02", s.honest("i02"), facts=[s.fact(s.oid("i02"))])
    j5 = s.honest("i05")
    j5[s.oid("i05")] = "partly"
    s.p3("i05", j5, fuller="fuller text")
    return s
