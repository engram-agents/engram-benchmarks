"""Round 7 contract tests (PR 7 colleague read): amendment 10, one definition of item and answer ids.

A10-1 the packet builder refuses an answer id the scorer would refuse later (' ', 'A', 'a\\n', a reserved id) before
anything is written; both modules take the patterns and predicates from ids.py and keep none of their own.
Written before the implementation. Synthetic data only.
"""
import ast
import pathlib

import pytest

import blind_packet
import score_review as sr
from test_round6 import _answers, _item, _packet2, _refused_with_nothing_written, _write_items

TOOL = pathlib.Path(sr.__file__).resolve().parent
BAD_ANSWER_IDS = [" ", "A", "a\n", "ambiguous", "official"]


@pytest.mark.parametrize("bad", BAD_ANSWER_IDS)
def test_a10_2_packet2_refuses_an_answer_id_the_scorer_would_refuse_and_writes_nothing(tmp_path, bad):
    items = _write_items(tmp_path, [_item("d1", answers=_answers("good", bad))])
    _refused_with_nothing_written(tmp_path, items, "d1")
    ok = _write_items(tmp_path / "ok", [_item("d1", answers=_answers("good", "fine"))])
    assert _packet2(tmp_path / "ok", ok).returncode == 0  # positive control


@pytest.mark.parametrize("bad", BAD_ANSWER_IDS)
def test_a10_2_check_answers_itself_refuses_so_no_caller_can_skip_it(bad):
    with pytest.raises(ValueError):
        blind_packet.check_answers(_item("d1", answers=_answers("good", bad)))


@pytest.mark.parametrize("bad", BAD_ANSWER_IDS)
def test_a10_2_the_items_loader_refuses_the_same_ids(tmp_path, bad):
    items = _write_items(tmp_path, [_item("d1", answers=_answers("good", bad))])
    with pytest.raises(sr.UserError):
        sr.load_items(str(items))


def test_a10_2_importer_style_ids_stay_valid():
    import ids
    assert ids.valid_item_id("0123456789") and ids.valid_answer_id("01234567") and ids.valid_answer_id("a1")
    assert not ids.valid_item_id("x\n") and not ids.valid_item_id("") and not ids.valid_item_id(None)
    assert not ids.valid_answer_id("official") and not ids.valid_answer_id(5)


def _tool_sources():
    return [p for p in sorted(TOOL.glob("*.py")) + sorted((TOOL / "importers").glob("*.py")) if p.name != "ids.py"]


def test_a10_2_the_patterns_are_defined_only_in_ids_py():
    names = {"ITEM_RE", "_ITEM_RE", "ANSWER_RE", "_ANSWER_RE", "RESERVED_IDS", "_RESERVED_IDS"}
    offenders = []
    for path in _tool_sources():
        text = path.read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
            else:
                targets = []
            for t in targets:
                if isinstance(t, ast.Name) and t.id in names:
                    offenders.append("%s:%d assigns %s" % (path.name, node.lineno, t.id))
            # the answer pattern and any literal set of the reserved ids (REVIEWER_RE, a different concept, may
            # share the item pattern's text, so only the answer pattern is matched by text)
            if isinstance(node, ast.Constant) and node.value == "^[0-9a-z]+$":
                offenders.append("%s:%d holds the answer pattern" % (path.name, node.lineno))
            if isinstance(node, ast.Set) and {"ambiguous", "official"} <= {
                    e.value for e in node.elts if isinstance(e, ast.Constant)}:
                offenders.append("%s:%d holds a reserved-id set" % (path.name, node.lineno))
    assert offenders == [], offenders
    ids_text = (TOOL / "ids.py").read_text(encoding="utf-8")
    assert "A-Za-z0-9._-" in ids_text and "[0-9a-z]" in ids_text


def test_a10_2_ids_py_imports_only_re():
    tree = ast.parse((TOOL / "ids.py").read_text(encoding="utf-8"))
    mods = [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    mods += [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert mods == ["re"], mods
