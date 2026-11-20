"""Round 4 contract tests (PR 7 review round 2 and the design owner's mapping ruling): amendments 6 and 7.

A6-2 packet placement refuses an existing file, A6-3 items.jsonl in item-id order and nothing paired by position,
A6-4 the import seed never reaches a packet, A6-5 a stale temp file is refused, not silent.
A7 the reveal is an event in the verdict store (an export record), and the ORIGINAL 2a is the one mapped when a 2a
is superseded after it. Written before the implementation. All text is synthetic.
"""
import json
import re

import pytest

from helpers import SEED, Store, assert_refused, read_jsonl, run, write_json
from test_round2 import CStore
from test_round3 import _planted, _tree, QBASE


def _packet_args(s, item="i02", seed=SEED, out=None):
    return ["packet2", "--items", s.items, "--item", item, "--seed", seed, "--keys-dir", s.keys,
            "--out-dir", out or (s.root / "packets" / "phase2")]


# ---------------------------------------------------------------- A6-2: the packet is placed like the key, never over a file

def test_a62_a_pre_existing_packet_is_refused_before_anything_is_written(tmp_path):
    s = Store(tmp_path)
    out = s.root / "packets" / "phase2"
    out.mkdir(parents=True)
    (out / "i02.md").write_bytes(b"someone else's packet\n")
    cp = run(*_packet_args(s))
    assert_refused(cp)
    assert (out / "i02.md").read_bytes() == b"someone else's packet\n"  # not replaced, not removed
    assert _tree(out) == ["i02.md"]  # no temp file left
    assert not s.keys.exists() or _tree(s.keys) == []  # no key, no key dir content


def test_a62_a_pre_existing_packet_is_refused_through_the_api_too(tmp_path):
    import blind_packet
    s = Store(tmp_path)
    out = s.root / "packets" / "phase2"
    out.mkdir(parents=True)
    (out / "i02.md").write_bytes(b"old")
    with pytest.raises((ValueError, OSError)):
        blind_packet.write_packet(str(s.items), "i02", SEED, str(s.keys), str(out))
    assert (out / "i02.md").read_bytes() == b"old"
    assert not (s.keys / "i02.json").exists()


def test_a62_a_key_failure_removes_the_packet_this_run_wrote(tmp_path, monkeypatch):
    import blind_packet
    s = Store(tmp_path)
    out = s.root / "packets" / "phase2"
    real = blind_packet.os.link

    def failing(src, dst, *a, **k):
        if str(dst).endswith(".json"):
            raise OSError("simulated key write failure")
        return real(src, dst, *a, **k)
    monkeypatch.setattr(blind_packet.os, "link", failing)
    with pytest.raises(OSError):
        blind_packet.write_packet(str(s.items), "i02", SEED, str(s.keys), str(out))
    assert _tree(out) == [] and _tree(s.keys) == []


def test_a62_a_packet_placed_by_this_run_is_never_an_overwrite(tmp_path, monkeypatch):
    """The packet must be placed by a link (which fails on an existing file), never by a rename that replaces."""
    import blind_packet
    s = Store(tmp_path)
    out = s.root / "packets" / "phase2"
    out.mkdir(parents=True)
    calls = []
    real_replace = blind_packet.os.replace

    def spy(src, dst, *a, **k):
        calls.append(str(dst))
        return real_replace(src, dst, *a, **k)
    monkeypatch.setattr(blind_packet.os, "replace", spy)
    blind_packet.write_packet(str(s.items), "i02", SEED, str(s.keys), str(out))
    assert not [c for c in calls if c.endswith("i02.md")], calls


def test_a62_a_packet_that_appears_while_the_run_is_staging_is_refused_and_left_alone(tmp_path, monkeypatch):
    """A packet created by someone else between the early check and the placement survives their file and ours is dropped."""
    import blind_packet
    s = Store(tmp_path)
    out = s.root / "packets" / "phase2"
    out.mkdir(parents=True)
    real = blind_packet.os.link

    def racing(src, dst, *a, **k):
        if str(dst).endswith(".md"):
            with open(dst, "wb") as fh:
                fh.write(b"the other run's packet")
        return real(src, dst, *a, **k)
    monkeypatch.setattr(blind_packet.os, "link", racing)
    with pytest.raises((ValueError, OSError)):
        blind_packet.write_packet(str(s.items), "i02", SEED, str(s.keys), str(out))
    assert (out / "i02.md").read_bytes() == b"the other run's packet"  # never removed: it is not this run's
    assert _tree(out) == ["i02.md"] and not (s.keys / "i02.json").exists()


# ---------------------------------------------------------------- A6-3: item-id order, nothing paired by position

def test_a63_the_importer_writes_items_sorted_by_item_id_not_question_order():
    items, grades, _ = _planted()
    ids = [it["item_id"] for it in items]
    assert ids == sorted(ids)
    assert sorted(g["item_id"] for g in grades) == ids  # same set; pairing is by item_id


def _shuffle_file(path, order):
    rows = path.read_text().splitlines()
    path.write_text("\n".join(rows[i] for i in order) + "\n")


# Fields that are a wall-clock reading by design, or a digest over a record that carries one. Two stores built a second
# apart differ in exactly these and nothing else (measured: with a 1.1 s sleep between the stores, the only differing
# output field was phases/2/record_sha256, the sha256 of the phase-2 record, which includes its `recorded_at`).
#   generated_at, exported_at, recorded_at : second-grain UTC stamps written by now()
#   record_sha256, after_2a_record_sha256  : canonical_sha over a record that includes recorded_at (or the 2a's hash)
_CLOCK_DERIVED = ("generated_at", "exported_at", "recorded_at", "record_sha256", "after_2a_record_sha256")


def _stable(x):
    """The value with the clock-derived fields removed at every depth; row order and everything else is kept."""
    if isinstance(x, dict):
        return {k: _stable(v) for k, v in x.items() if k not in _CLOCK_DERIVED}
    if isinstance(x, list):
        return [_stable(v) for v in x]
    return x


def _report_stable(text):
    """The report prints a 12-hex prefix of the phase-2 record's sha256 (`record cbb32fe3c5b0`), a digest over a record
    that carries `recorded_at`: the same clock-derived value as record_sha256 above, in text form."""
    return re.sub(r"\brecord [0-9a-f]{12}\b", "record <sha12>", text)


def test_a63_shuffling_the_row_order_of_items_and_grades_changes_no_output(tmp_path):
    a, b = Store(tmp_path / "a"), Store(tmp_path / "b")
    n = len(a.item_ids)
    order = list(reversed(range(n)))
    order = order[1:] + order[:1]
    for st in (a, b):
        st.p1("i02")
    _shuffle_file(b.items, order)
    _shuffle_file(b.grades, order[::-1])
    for st in (a, b):
        st.packet2("i02")
        st.p2("i02", st.honest("i02"))
    ca, oa = a.map()
    cb, ob = b.map()
    assert ca.returncode == 0 and cb.returncode == 0, (ca.stderr, cb.stderr)
    assert _stable(read_jsonl(oa)) == _stable(read_jsonl(ob))  # same rows, same order
    pa = (a.root / "packets" / "phase2" / "i02.md").read_bytes()
    pb = (b.root / "packets" / "phase2" / "i02.md").read_bytes()
    assert pa == pb
    assert a.key("i02") == b.key("i02")
    for st, o in ((a, oa), (b, ob)):
        run("report", "--items", st.items, "--grades", st.grades, "--verdicts", st.verdicts, "--outcomes", o,
            "--out", st.root / "report.md")
    assert _report_stable((a.root / "report.md").read_text()) == _report_stable((b.root / "report.md").read_text())
    # draw samples from the same eligible set whatever the file order
    da = run("draw", "--items", Store(tmp_path / "c").items, "--grades", tmp_path / "c" / "grades.jsonl",
             "--verdicts", tmp_path / "c" / "v.jsonl", "--draws", tmp_path / "c" / "d.jsonl", "--run", "r", "--n", "2", "--seed", "s")
    c2 = Store(tmp_path / "d")
    _shuffle_file(c2.items, order)
    _shuffle_file(c2.grades, order[::-1])
    db = run("draw", "--items", c2.items, "--grades", c2.grades, "--verdicts", tmp_path / "d" / "v.jsonl",
             "--draws", tmp_path / "d" / "d.jsonl", "--run", "r", "--n", "2", "--seed", "s")
    assert da.returncode == 0 and db.returncode == 0, (da.stderr, db.stderr)
    assert da.stdout == db.stdout


# ---------------------------------------------------------------- A6-4: the import seed never reaches a packet

def test_a64_the_import_seed_and_the_packet_seed_appear_in_no_packet_text(tmp_path):
    import_seed, packet_seed = "1a2b3c4d" * 8, "9e8d7c6b" * 8
    items, grades, _ = _planted(n=6, seed=import_seed)
    ip = tmp_path / "items.jsonl"
    ip.write_text("".join(json.dumps(i) + "\n" for i in items))
    seen = [ip.read_text()]
    for it in items:
        cp = run("packet2", "--items", ip, "--item", it["item_id"], "--seed", packet_seed, "--keys-dir",
                 tmp_path / "keys", "--out-dir", tmp_path / "packets")
        assert cp.returncode == 0, cp.stderr
        seen.append(cp.stdout)
    for f in (tmp_path / "packets").iterdir():
        seen += [f.name, f.read_text()]
    blob = "\n".join(seen)
    assert import_seed not in blob and import_seed[:16] not in blob
    assert packet_seed not in blob.replace(str(tmp_path / "keys"), "") and packet_seed[:16] not in blob


# ---------------------------------------------------------------- A6-5: a stale temp file is seen, not silent

@pytest.mark.parametrize("where, name", [("packets", "i02.md.tmp-4242"), ("keys", "i02.json.tmp-4242")])
def test_a65_a_stale_temp_file_beside_the_outputs_is_refused_and_named(tmp_path, where, name):
    s = Store(tmp_path)
    d = (s.root / "packets" / "phase2") if where == "packets" else s.keys
    d.mkdir(parents=True)
    (d / name).write_bytes(b"crash residue")
    cp = run(*_packet_args(s))
    assert_refused(cp)
    assert name in cp.stderr  # named
    assert (d / name).read_bytes() == b"crash residue"  # left for the operator, not deleted
    other = s.keys if where == "packets" else (s.root / "packets" / "phase2")
    assert not other.exists() or _tree(other) == []
    assert not (s.keys / "i02.json").exists() and not (s.root / "packets" / "phase2" / "i02.md").exists()


def test_a65_a_stale_temp_file_of_another_item_does_not_block_this_one(tmp_path):
    s = Store(tmp_path)
    out = s.root / "packets" / "phase2"
    out.mkdir(parents=True)
    (out / "i03.md.tmp-1").write_bytes(b"residue of another item")
    s.packet2("i02")
    assert (out / "i02.md").exists()


# ---------------------------------------------------------------- A7: the reveal is an event in the store

def _criterion_flow(s, *, supersede, new_y="partly", item="k1"):
    """supersede: where the 2a is superseded: 'before_export', 'after_export' (before the 2b), 'after_2b'."""
    s.p1(item)
    orig = s.p2a(item, {"x": "correct", "y": "correct"})
    new = None

    def change():
        return s.ok(item, 2, "expert", s.vd(item, _lj(s, item, "correct", new_y), step="2a", fuller="Revised reading."),
                    extra=("--supersedes", orig, "--reason", "reread the instruction"))
    if supersede == "before_export":
        new = change()
    cp, _ = s.export_criterion(item)
    assert cp.returncode == 0, cp.stderr
    if supersede == "after_export":
        new = change()
    s.ok(item, 2, "expert", s.vd(item, {"criterion": "correct"}, step="2b"))
    if supersede == "after_2b":
        new = change()
    return orig, new


def _lj(s, item, x, y):
    return {s.letter(item, s.ids[item]["x"]): x, s.letter(item, s.ids[item]["y"]): y}


def test_a7_a_supersede_before_the_export_is_an_ordinary_correction(tmp_path):
    s = CStore(tmp_path)
    orig, new = _criterion_flow(s, supersede="before_export")
    k1 = s.outcomes()["k1"]
    y = s.ids["k1"]["y"]
    assert k1["phases"]["2"]["record_sha256"] == new and k1["phases"]["2"]["judgement"][y] == "partly"  # latest mapped
    assert "post_reveal_revision" not in k1["phases"]["2"]
    assert k1["routing"]["forced_phase3"] is False
    x = tmp_path / "x.json"
    assert run("export-phase3", "--items", s.items, "--grades", s.grades, "--verdicts", s.verdicts, "--keys-dir", s.keys,
               "--item", "k1", "--out", x).returncode == 0
    assert "phase2_post_reveal_revision" not in json.loads(x.read_text())


@pytest.mark.parametrize("when", ["after_export", "after_2b"])
def test_a7_a_supersede_after_the_export_maps_the_original_forces_phase3_and_shows_both(tmp_path, when):
    s = CStore(tmp_path)
    orig, new = _criterion_flow(s, supersede=when)
    k1 = s.outcomes()["k1"]
    y = s.ids["k1"]["y"]
    p2 = k1["phases"]["2"]
    assert p2["record_sha256"] == orig and p2["judgement"][y] == "correct" and p2["outcome"] == "key_stands"
    rev = p2["post_reveal_revision"]
    assert rev["record_sha256"] == new and rev["judgement"][y] == "partly" and rev["reviewer"] == "expert"
    assert rev["reason"] == "reread the instruction" and rev["fuller_answer"] == "Revised reading."
    assert set(rev) >= {"reviewer", "record_sha256", "judgement", "fuller_answer", "facts", "reason"}
    assert k1["routing"]["forced_phase3"] is True and k1["routing"]["unquestioned_control"] is False
    assert k1["routing"]["in_phase3"] is True and k1["status"] == "pending"
    x = tmp_path / "x.json"
    assert run("export-phase3", "--items", s.items, "--grades", s.grades, "--verdicts", s.verdicts, "--keys-dir", s.keys,
               "--item", "k1", "--out", x).returncode == 0
    ex = json.loads(x.read_text())
    assert ex["phase2"]["record_sha256"] == orig and ex["phase2_post_reveal_revision"]["record_sha256"] == new
    cp, out = s.map()
    rep = tmp_path / "r.md"
    assert run("report", "--items", s.items, "--grades", s.grades, "--verdicts", s.verdicts, "--outcomes", out,
               "--out", rep).returncode == 0
    text = rep.read_text()
    assert orig[:12] in text and new[:12] in text and "post-reveal revision" in text and "reread the instruction" in text


def test_a7_the_export_record_is_in_the_store_and_is_not_a_phase_record(tmp_path):
    s = CStore(tmp_path)
    sha = s.p2a("k2", {"x": "correct", "y": "partly"})
    before = s.verdicts.read_bytes()
    cp, out = s.export_criterion("k2")
    assert cp.returncode == 0, cp.stderr
    rows = read_jsonl(s.verdicts)
    ex = [r for r in rows if r.get("kind") == "export_2b"]
    assert len(ex) == 1 and rows[-1].get("kind") == "export_2b"
    e = ex[0]
    assert e["item_id"] == "k2" and e["reviewer"] == "expert" and e["after_2a_record_sha256"] == sha
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", e["exported_at"]) and "phase" not in e
    assert s.verdicts.read_bytes().startswith(before) and s.verdicts.read_bytes() != before
    json.loads(out.read_text())  # the export file is written too
    # not a 2a: the map still reads one effective 2a and says the 2b is pending; nothing counts a second reviewer
    k2 = s.outcomes()["k2"]
    assert "2" not in k2["phases"] and k2["status"] == "phase2_pending"
    # S1: the same reviewer records the 2b after it; a second 2a without a supersede is still refused
    assert_refused(s.record("k2", 2, "expert", s.vd("k2", _lj(s, "k2", "correct", "partly"), step="2a")))
    s.ok("k2", 2, "expert", s.vd("k2", {"criterion": "partly"}, step="2b"))
    assert s.outcomes()["k2"]["phases"]["2"]["record_sha256"] == sha
    # a second export is allowed and recorded; the first stays the boundary
    cp, _ = s.export_criterion("k2")
    assert cp.returncode == 0
    assert len([r for r in read_jsonl(s.verdicts) if r.get("kind") == "export_2b"]) == 2


def test_a7_a_refused_export_appends_nothing(tmp_path):
    s = CStore(tmp_path)
    s.p1("k2", s.level_j("k2"))
    before = s.verdicts.read_bytes()
    cp, out = s.export_criterion("k2")  # no 2a
    assert_refused(cp)
    assert s.verdicts.read_bytes() == before and not out.exists()


def test_a7_the_export_record_hash_verifies_like_the_others_and_tampering_is_refused(tmp_path):
    from score_review import canonical_sha
    s = CStore(tmp_path)
    s.p2a("k2", {"x": "correct", "y": "partly"})
    cp, _ = s.export_criterion("k2")
    assert cp.returncode == 0
    rows = read_jsonl(s.verdicts)
    e = [r for r in rows if r.get("kind") == "export_2b"][0]
    assert e["record_sha256"] == canonical_sha(e)
    e["after_2a_record_sha256"] = "0" * 64  # moving the boundary after the fact
    s.verdicts.write_text("".join(json.dumps(r) + "\n" for r in rows))
    cp, _ = s.map()
    assert_refused(cp)
    cp, _ = s.export_criterion("k2", out=tmp_path / "again.json")
    assert_refused(cp)


def test_a7_an_export_record_does_not_disturb_draw_quote_check_or_the_arm_stats(tmp_path):
    s = CStore(tmp_path)
    s.p2a("k2", {"x": "correct", "y": "partly"}, guesses_arms={"x": "CRIT-ARM-TOKEN-x"})
    cp, _ = s.export_criterion("k2")
    assert cp.returncode == 0
    cp, out = s.map()
    assert cp.returncode == 0, cp.stderr
    assert run("quote-check", "--verdicts", s.verdicts, "--chat", s.chat).returncode == 0
    rep = tmp_path / "r.md"
    cp = run("report", "--items", s.items, "--grades", s.grades, "--verdicts", s.verdicts, "--outcomes", out,
             "--out", rep, "--unblind", "--keys-dir", s.keys)
    assert cp.returncode == 0, cp.stderr


def test_a7_the_first_export_is_the_boundary_even_when_a_second_export_follows_the_supersede(tmp_path):
    s = CStore(tmp_path)
    s.p1("k1")
    orig = s.p2a("k1", {"x": "correct", "y": "correct"})
    cp, _ = s.export_criterion("k1")  # the criterion is shown here
    assert cp.returncode == 0
    new = s.ok("k1", 2, "expert", s.vd("k1", _lj(s, "k1", "correct", "partly"), step="2a"),
               extra=("--supersedes", orig, "--reason", "reread the instruction"))
    cp, _ = s.export_criterion("k1", out=tmp_path / "again.json")  # a second export, AFTER the change
    assert cp.returncode == 0
    s.ok("k1", 2, "expert", s.vd("k1", {"criterion": "correct"}, step="2b"))
    k1 = s.outcomes()["k1"]
    assert k1["phases"]["2"]["record_sha256"] == orig and k1["phases"]["2"]["post_reveal_revision"]["record_sha256"] == new
    assert k1["routing"]["forced_phase3"] is True


def test_a7_draw_reads_past_an_export_record_and_still_refuses_on_a_phase1_verdict(tmp_path):
    s = CStore(tmp_path)
    s.p2a("k2", {"x": "correct", "y": "partly"})
    cp, _ = s.export_criterion("k2")
    assert cp.returncode == 0
    cp = run("draw", "--items", s.items, "--grades", s.grades, "--verdicts", s.verdicts, "--draws", tmp_path / "d2.jsonl",
             "--run", "r2", "--n", "1", "--seed", "s")
    assert_refused(cp)
    assert "phase-1" in cp.stderr and "Traceback" not in cp.stderr
