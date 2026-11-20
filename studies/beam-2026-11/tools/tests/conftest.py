"""Shared helpers for the P1 harness cells. Synthetic fixtures only: no real data, no student model, no Ollama."""
import hashlib, json, os, shutil, stat, subprocess, sys
import pytest

TOOLS = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _has_pyarrow(py):
    try:
        return subprocess.run([py, "-c", "import pyarrow"], capture_output=True).returncode == 0
    except OSError:
        return False


@pytest.fixture(scope="session")
def arrow_python():
    """A python that has pyarrow: $BEAM_PY, else this interpreter. Cells needing the parquet skip without one."""
    for py in (os.environ.get("BEAM_PY"), sys.executable):
        if py and _has_pyarrow(py):
            return py
    pytest.skip("no python with pyarrow (set BEAM_PY)")


@pytest.fixture(scope="session")
def synthetic_parquet(arrow_python, tmp_path_factory):
    p = tmp_path_factory.mktemp("pq") / "syn.parquet"
    code = (
        "import pyarrow as pa, pyarrow.parquet as pq, sys\n"
        "sess=[]\n"
        "for s in range(2):\n"
        "    m=[]\n"
        "    for i in range(4):\n"
        "        m.append({'role':'user','content':f'user {s}.{i}','time_anchor':'May-01-2024' if i==0 else None})\n"
        "        m.append({'role':'assistant','content':f'asst {s}.{i}','time_anchor':None})\n"
        "    sess.append(m)\n"
        "t=pa.table({'conversation_id':[9],'chat':[sess],'probing_questions':[str({'a':[{'question':'Q one?'},{'question':'Q two?'}]})]})\n"
        "pq.write_table(t, sys.argv[1])\n")
    subprocess.run([arrow_python, "-c", code, str(p)], check=True)
    return str(p)


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f)
    return str(path)


MEMORY_INDEX = ("- [Old pointer](feedback_old.md) \u2014 a pointer kept from before\n"
                "- [Other pointer](feedback_other.md) \u2014 another pointer kept from before\n")

# ---- a synthetic arm home for plant-control.py (no real model, no real preserved home) ----
SEED = (
    "import os, sys\n"
    "home = sys.argv[1]\n"
    "os.environ['ENGRAM_HOME'] = home + '/.engram'; os.environ['HOME'] = home\n"
    "os.environ['ENGRAM_NO_DB_GUARDS'] = '1'; os.environ['ENGRAM_NO_EMBEDDINGS'] = '1'\n"
    "sys.path.insert(0, home + '/.engram/marketplace/plugins/engram')\n"
    "import engram_core; c = engram_core._get_db(); c.close()\n"
    "import engram_epistemic\n"
    "print(engram_epistemic._add_axiom_impl(claim='seed axiom for the synthetic fixture', basis='fixture'))\n")


def engram_plugin_src():
    p = os.environ.get("P1_ENGRAM_PLUGIN")
    if not p or not os.path.isfile(os.path.join(p, "engram_observation.py")):
        pytest.skip("set P1_ENGRAM_PLUGIN to a plugin tree that holds engram_observation.py (an ENGRAM src/engram)")
    return p


@pytest.fixture(scope="session")
def arm_home_template(tmp_path_factory):
    """One synthetic arm home, built once: .claude with a memory folder under a project folder, a work folder, a
    transcript, and .engram with the plugin tree and a seeded knowledge.db. Copied per test."""
    src = engram_plugin_src()
    h = tmp_path_factory.mktemp("armtpl") / "home"
    plug = h / ".engram" / "marketplace" / "plugins" / "engram"
    shutil.copytree(src, plug, ignore=shutil.ignore_patterns("__pycache__", "tests"))
    (h / "work").mkdir()
    proj = h / ".claude" / "projects" / "-synthetic-work"
    (proj / "memory").mkdir(parents=True)
    (proj / "memory" / "MEMORY.md").write_text(MEMORY_INDEX)  # the index the student reads the folder through
    (proj / "session-0001.jsonl").write_text(json.dumps({"type": "user", "message": "an ordinary turn"}) + "\n")
    (h / ".claude" / "plugins" / "memory").mkdir(parents=True)  # a 'memory' dir under plugins/: memcheck excludes it
    r = subprocess.run([sys.executable, "-c", SEED, str(h)], capture_output=True, text=True,
                       env={"PATH": os.environ["PATH"]})
    assert r.returncode == 0 and "ax_0001" in r.stdout, r.stdout + r.stderr
    shutil.rmtree(h / ".engram" / "knowledge.db.setup.lockdir", ignore_errors=True)
    return str(h)


@pytest.fixture
def arm_home(arm_home_template, tmp_path):
    """A disposable copy of the synthetic arm home, marked, with an evidence dir beside it (outside the home)."""
    h = tmp_path / "home"
    shutil.copytree(arm_home_template, h, symlinks=True)
    (h / ".disposable-copy").write_text("")
    (tmp_path / "evidence").mkdir()
    return h


def memory_dir(h):
    return h / ".claude" / "projects" / "-synthetic-work" / "memory"


# A stand-in `systemctl` for hosts that have no systemd (a Mac): the launch module asks `systemctl --user` to stop a scope, to
# show its cgroup and to list units, and this answers as an EMPTY user manager (no units, nothing to stop). The cells that
# need a real user manager (real scopes, real boxes) are marked needs_box and skip there; the others run against this.
STUB_SYSTEMCTL = """#!/bin/sh
case "$*" in
  *is-active*) echo inactive; exit 3 ;;
esac
exit 0
"""


def install_stub_systemctl(dirpath):
    os.makedirs(dirpath, exist_ok=True)
    path = os.path.join(str(dirpath), "systemctl")
    with open(path, "w") as f:
        f.write(STUB_SYSTEMCTL)
    os.chmod(path, 0o755)
    return str(dirpath)
