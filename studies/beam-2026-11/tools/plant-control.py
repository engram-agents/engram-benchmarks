#!/usr/bin/env python3
"""Two-channel planted-fact control, for a DISPOSABLE copy of an arm home only (BEAM P1 answering). This file is the
study's harness, not shipped product code.

Plants three invented facts:
  --builtin-fact   as ONE markdown file in the arm's own built-in auto-memory folder (the folder pilot-memcheck.sh
                   finds: a directory named 'memory' under HOME/.claude, not under plugins/), in the front-matter
                   format of a file already there if there is one;
  --engram-fact    as ONE observation written by ENGRAM's own write code (engram_observation._add_observation_impl,
                   the function the engram_add_observation MCP tool calls), imported IN-PROCESS from the arm home's
                   installed plugin, with ENGRAM_HOME at HOME/.engram. No SQL. Its evidence is a content-addressed
                   file in --evidence-dir (named by its sha256, so ENGRAM's archive guard accepts it without git);
  --absent-fact    planted NOWHERE (the control for answering from nothing).
Each fact must be an invented value of at least 6 characters, and no fact may contain another.

Refuses (exit 2, nothing written) unless HOME holds the marker file .disposable-copy, HOME is not under any path in
the colon-separated environment variable P1_PROTECTED (which must be set), the memory folder exists and is unique, the
evidence dir is outside HOME/work (and outside the memory folder), and the arm home's plugin imports.

After planting it prints and enforces (exit 0 only if every line passes, else 1):
  built-in file read back; ENGRAM observation read back through ENGRAM's own read code (_query_impl);
  transcript leak (no fact in any *.jsonl under HOME, nor any file under .claude/projects outside the memory folder);
  cross-absence (the ENGRAM fact in no file of the memory folder; the built-in fact not in the ENGRAM store);
  absent fact (in neither channel, no transcript); row counts per table before and after, failing if any table other
  than those ENGRAM's observation write touches changed.
Run it with the python of the arm home's own ENGRAM venv (the plugin's dependencies live there).

Round 2: the built-in note is also listed in the folder's MEMORY.md (the index the student finds the folder
through) by ONE appended line in the format of an existing line, with NEUTRAL text and a link naming the note
(`- [Reference note](reference_note_<hash8>.md) \u2014 a stored reference note`); the tool exits 2 if there is no
MEMORY.md, and with --question TEXT it exits 2 if the index line holds any content word of that question
(lowercase letters-only words, longer than 3 characters, not stopwords). No fact text may be in the index (checked). The
ENGRAM observation is written with embeddings ON by default, through the arm's own embedder (exit 2 if it cannot
load; an inherited ENGRAM_NO_EMBEDDINGS fails the same way, never silently); --no-embeddings opts out. The tool
prints which. The store reads of the checks never refresh recall (the recall counters are left as the write made them).

usage: plant-control.py --home DISPOSABLE_HOME --builtin-fact TEXT --engram-fact TEXT --absent-fact TEXT
                        --evidence-dir DIR [--allowed-tables CSV] [--question TEXT] [--no-embeddings]
"""
import argparse, hashlib, json, os, re, sqlite3, sys

MIN_FACT = 6
# Tables ENGRAM's own observation write touches (measured on a synthetic home: nodes, edges, edit_history, the
# id sequences, and the nodes_fts / vec_nodes index tables). --allowed-tables replaces this list.
ALLOWED_TABLES = frozenset({"nodes", "edges", "edit_history", "sequences", "sqlite_sequence"})
ALLOWED_PREFIXES = ("nodes_fts", "vec_nodes")


def refuse(msg):
    print(f"REFUSE: {msg}", file=sys.stderr)
    sys.exit(2)


def under(path, root):
    path, root = os.path.realpath(path), os.path.realpath(root)
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def find_memory_dirs(home):
    """The folders pilot-memcheck.sh finds: directories named 'memory' under HOME/.claude, not under plugins/."""
    out = []
    base = os.path.join(home, ".claude")
    for root, dirs, _ in os.walk(base):
        rel = os.path.relpath(root, home).split(os.sep)
        if "plugins" in rel:
            dirs[:] = []
            continue
        for d in dirs:
            if d == "memory":
                out.append(os.path.join(root, d))
    return sorted(out)


def files_under(root):
    for r, _, fs in os.walk(root):
        for f in fs:
            yield os.path.join(r, f)


def contains(path, text):
    """Case-insensitive byte search of one file (a leak that differs only in case is still a leak)."""
    try:
        return text.lower().encode() in open(path, "rb").read().lower()
    except OSError:
        return False


def leak_scan_files(home, memdir):
    """Every transcript-like file: any *.jsonl* under HOME, plus any file under .claude/projects outside memory."""
    seen = set()
    for p in files_under(home):
        if ".jsonl" in os.path.basename(p):
            seen.add(p)
    proj = os.path.join(home, ".claude", "projects")
    if os.path.isdir(proj):
        for p in files_under(proj):
            if not under(p, memdir):
                seen.add(p)
    return sorted(seen)


def leak_hits(home, memdir, text):
    return [p for p in leak_scan_files(home, memdir) if contains(p, text)]


def embedded_ids(db):
    """Ids of nodes that carry an embedding (read-only)."""
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return {r[0] for r in c.execute("select id from nodes where embedding is not null")}
    finally:
        c.close()


def table_counts(db):
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        out = {}
        for (n,) in c.execute("select name from sqlite_master where type='table' order by 1"):
            try:
                out[n] = c.execute(f'select count(*) from "{n}"').fetchone()[0]
            except sqlite3.Error as e:
                out[n] = f"unreadable: {e}"  # e.g. a virtual table whose module is not loaded; compared as text
        return out
    finally:
        c.close()


def changed_tables(before, after, allowed):
    """Names of tables NOT in `allowed` whose row count, or whose presence, differs between the two snapshots."""
    bad = []
    for t in sorted(set(before) | set(after)):
        if t in allowed:
            continue
        if before.get(t, "absent") != after.get(t, "absent"):
            bad.append(t)
    return bad


def default_allowed(*snapshots):
    names = set(ALLOWED_TABLES)
    for snap in snapshots:
        names |= {t for t in snap if t.startswith(ALLOWED_PREFIXES)}
    return names


def front_matter_of(memdir):
    """Front-matter lines of an existing .md file in the memory folder, or None."""
    for p in sorted(files_under(memdir)):
        if p.endswith(".md") and os.path.basename(p) != "MEMORY.md":
            text = open(p, encoding="utf-8", errors="replace").read()
            m = re.match(r"---\n(.*?)\n---\n", text, re.S)
            if m:
                return m.group(1).split("\n")
    return None


def build_memory_file(fact, template_lines, slug):
    desc = "A note recorded for later reference."
    if template_lines is None:
        fm = [f"name: {slug}", f'description: "{desc}"', "metadata: ", "  node_type: memory", "  type: reference"]
    else:
        fm = []
        for ln in template_lines:
            if ln.startswith("name:"):
                fm.append(f"name: {slug}")
            elif ln.startswith("description:"):
                fm.append(f'description: "{desc}"')
            elif re.match(r"\s+originSessionId:", ln):
                continue  # a session id of the run the template came from: never copied
            else:
                fm.append(ln)
    return "---\n" + "\n".join(fm) + "\n---\n" + fact + "\n"


STOPWORDS = frozenset("""about above after again against all also and any are because been before being below between both
but can could did does doing down during each few for from further had has have having her here hers him his how into its
itself just more most not now off once only other our ours out over own same she should some such than that the their
theirs them then there these they this those through too under until very was were what when where which while who whom
why will with would you your yours""".split())


def content_words(text):
    """Lowercase letters-only words of `text` that are longer than 3 characters and not stopwords."""
    return {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) > 3 and w not in STOPWORDS}


def index_line_for(existing_text, fname):
    """ONE neutral index line, in the bullet and separator style of the first parseable line of `existing_text`
    (default: `- [..](..) \u2014 ..`)."""
    bullet, sep = "- ", " \u2014 "
    for ln in existing_text.splitlines():
        m = re.match(r"(\s*[-*+]\s+)\[[^\]]*\]\([^)]*\)(\s*(?:\u2014|\u2013|-|:)\s*)", ln)
        if m:
            bullet, sep = m.group(1), m.group(2)
            break
    return f"{bullet}[Reference note]({fname}){sep}a stored reference note"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", required=True); ap.add_argument("--evidence-dir", required=True)
    ap.add_argument("--builtin-fact", required=True); ap.add_argument("--engram-fact", required=True)
    ap.add_argument("--absent-fact", required=True)
    ap.add_argument("--allowed-tables", help="comma-separated; replaces the default list of tables the observation "
                    "write may change")
    ap.add_argument("--question", help="the control question's text: the index line must hold none of its content words")
    ap.add_argument("--no-embeddings", action="store_true",
                    help="plant the ENGRAM observation without an embedding (default: embeddings ON, as for the student's own writes)")
    a = ap.parse_args()

    # ---- refusals: nothing is written before every one of these has passed
    facts = {"builtin": a.builtin_fact, "engram": a.engram_fact, "absent": a.absent_fact}
    for k, v in facts.items():
        if len(v.strip()) < MIN_FACT:
            refuse(f"the {k} fact is shorter than {MIN_FACT} characters (facts must be invented values)")
    for k1, v1 in facts.items():
        for k2, v2 in facts.items():
            if k1 != k2 and v1.lower() in v2.lower():
                refuse(f"the {k1} fact is contained in the {k2} fact; the cross checks would mean nothing")
    home = os.path.realpath(a.home)
    if not os.path.isdir(home):
        refuse(f"{a.home} is not a directory")
    if not os.path.isfile(os.path.join(home, ".disposable-copy")):
        refuse("the home has no .disposable-copy marker file (this tool plants only into a disposable copy)")
    protected = [p for p in os.environ.get("P1_PROTECTED", "").split(":") if p]
    if not protected:
        refuse("P1_PROTECTED is not set (colon-separated preserved homes); refusing to guess what is protected")
    for p in protected:
        if under(home, p) or under(p, home):
            refuse(f"the home is inside, or contains, a protected path from P1_PROTECTED ({p})")
    mems = find_memory_dirs(home)
    if not mems:
        refuse("no built-in memory folder (a directory named 'memory' under .claude, not under plugins/); not inventing one")
    if len(mems) > 1:
        refuse(f"{len(mems)} memory folders found; refusing to choose one")
    memdir = mems[0]
    index_path = os.path.join(memdir, "MEMORY.md")
    if not os.path.isfile(index_path):
        refuse("the memory folder has no MEMORY.md index (the student finds the folder through it); "
               "choose a home that has one")
    tag = hashlib.sha256(a.builtin_fact.encode()).hexdigest()[:8]
    note_name = f"reference_note_{tag}.md"
    index_line = index_line_for(open(index_path, encoding="utf-8", errors="replace").read(), note_name)
    if a.question:
        shared = sorted(content_words(a.question) & content_words(index_line))
        if shared:
            refuse(f"the index line would contain content word(s) of the control question: {', '.join(shared)}")
    ev = os.path.realpath(a.evidence_dir)
    if under(ev, os.path.join(home, "work")):
        refuse("the evidence dir is inside the arm home's work folder (the student's)")
    if under(ev, memdir):
        refuse("the evidence dir is inside the memory folder")
    plug = os.path.join(home, ".engram", "marketplace", "plugins", "engram")
    db = os.path.join(home, ".engram", "knowledge.db")
    for need in ("engram_core.py", "engram_observation.py", "engram_query.py"):
        if not os.path.isfile(os.path.join(plug, need)):
            refuse(f"the arm home's plugin lacks {need} at {os.path.relpath(plug, home)}")
    if not os.path.isfile(db):
        refuse("the arm home has no .engram/knowledge.db")
    # Import ENGRAM from THIS arm home's plugin, with its environment pointed at this home (set before the import:
    # engram_core reads ENGRAM_HOME at import time, and the evidence archive root is read at import time too).
    os.makedirs(ev, exist_ok=True)
    os.environ["ENGRAM_HOME"] = os.path.join(home, ".engram")
    os.environ["HOME"] = home
    os.environ["ENGRAM_EVIDENCE_ARCHIVE"] = ev
    if a.no_embeddings:
        os.environ["ENGRAM_NO_EMBEDDINGS"] = "1"
    sys.path.insert(0, plug)
    try:
        import engram_core, engram_observation, engram_query  # noqa: E401
    except Exception as e:  # noqa: BLE001
        refuse(f"the arm home's plugin cannot be imported: {type(e).__name__}: {e}")
    for m in (engram_core, engram_observation, engram_query):
        if not under(m.__file__, plug):
            refuse(f"{m.__name__} was imported from {m.__file__}, not from the arm home's plugin")

    # ---- embeddings: ON unless --no-embeddings. Proven on the arm's own embedder BEFORE anything is written.
    if a.no_embeddings:
        print("embeddings: OFF (--no-embeddings)")
    else:
        try:
            model = engram_core._get_embedding_config().get("model", engram_core.DEFAULT_EMBEDDING_MODEL)
            avail = engram_core._embedder.is_available()
            vec = engram_core._embedder.embed("embedding self-test", model) if avail else None
        except Exception as e:  # noqa: BLE001
            avail, vec, model = False, None, f"{type(e).__name__}: {e}"
        if not avail:
            refuse("embeddings are required (the student's own writes are embedded) but the embedder is not available "
                   "(ENGRAM_NO_EMBEDDINGS set, or sentence-transformers missing); pass --no-embeddings to plant without")
        if not vec:
            refuse(f"embeddings are required but the embedding model {model!r} could not load or returned no vector; "
                   "pass --no-embeddings to plant without")
        print(f"embeddings: ON (model {model}, {len(vec)} dimensions)")

    allowed_arg = {t for t in a.allowed_tables.split(",") if t} if a.allowed_tables else None
    before = table_counts(db)

    # ---- plant, built-in channel: one markdown file
    slug = f"note-{tag}"
    mpath = os.path.join(memdir, note_name)
    with open(mpath, "w", encoding="utf-8") as f:
        f.write(build_memory_file(a.builtin_fact, front_matter_of(memdir), slug))
    with open(index_path, "a+", encoding="utf-8") as f:  # the neutral index line, so the folder lists the note
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(max(size - 1, 0))
        if size and f.read(1) != "\n":
            f.write("\n")
        f.write(index_line + "\n")

    # ---- plant, ENGRAM channel: evidence file outside the work folder, then ONE observation via ENGRAM's own code
    body = (a.engram_fact + "\n").encode()
    epath = os.path.join(ev, hashlib.sha256(body).hexdigest() + ".txt")
    with open(epath, "wb") as f:
        f.write(body)
    res = engram_observation._add_observation_impl(
        quoted_text=a.engram_fact, interpretation="Recorded as stated in the source.", claim=a.engram_fact,
        quote_type="hard_data", source_class="external", url="file://" + epath, title="Source note")
    try:
        r = json.loads(res)
    except ValueError:
        r = {"error": res}
    ob_id = r.get("observation_id")
    print(f"ENGRAM write: {res if not ob_id else 'created ' + ob_id}")

    fails = []

    def line(name, ok, detail=""):
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f": {detail}" if detail else ""))
        if not ok:
            fails.append(name)

    def store_has(text):
        """(found, error, ids): the ENGRAM store read through ENGRAM's own query code (the echoed query is NOT
        counted: only the result rows), plus a raw byte check of the db files. An errored read is never 'absent'."""
        out = engram_query._query_impl(query=text, refresh_recall=False)
        err, results = None, []
        try:
            parsed = json.loads(out)
            results = parsed.get("results")
            if "error" in parsed or not isinstance(results, list):
                err, results = out[:200], []
        except ValueError:
            err = "query output is not JSON"
        found = text.lower() in json.dumps(results).lower()
        raw = any(contains(p, text) for p in (db, db + "-wal"))
        return found or raw, err, [x.get("id") for x in results if isinstance(x, dict)]

    # check 1: the built-in file, read back
    ok1 = os.path.isfile(mpath) and a.builtin_fact in open(mpath, encoding="utf-8").read()
    line("built-in file read back", ok1, os.path.relpath(mpath, home))
    # check 2: the observation, read back through ENGRAM's own read code
    found, err, ids = store_has(a.engram_fact)
    line("engram observation read back", bool(ob_id) and found and not err and ob_id in ids,
         ob_id or "no observation id")
    # the index: no fact text in MEMORY.md (the student reads the folder through it)
    idx_text = open(index_path, encoding="utf-8", errors="replace").read().lower()
    idx_hits = [k for k, v in facts.items() if v.lower() in idx_text]
    line("index: no fact text in MEMORY.md", not idx_hits, ", ".join(idx_hits) or "none")
    if not a.no_embeddings:
        line("engram observation embedded", bool(ob_id) and ob_id in embedded_ids(db), ob_id or "no observation id")
    # check 3: transcript leak, for all three facts
    for k, v in facts.items():
        hits = leak_hits(home, memdir, v)
        line(f"transcript leak ({k} fact)", not hits, "; ".join(os.path.relpath(h, home) for h in hits) or "found nowhere")
    # addendum: cross-absence before the session
    mem_hits = [p for p in files_under(memdir) if contains(p, a.engram_fact)]
    line("cross-absence: engram fact in the memory folder", not mem_hits, "; ".join(os.path.basename(h) for h in mem_hits) or "absent")
    found_b, err_b, _ = store_has(a.builtin_fact)
    line("cross-absence: built-in fact in the ENGRAM store", not found_b and not err_b, err_b or ("PRESENT" if found_b else "absent"))
    # addendum: the third fact is planted nowhere
    mem_a = [p for p in files_under(memdir) if contains(p, a.absent_fact)]
    found_a, err_a, _ = store_has(a.absent_fact)
    ev_a = [p for p in files_under(ev) if contains(p, a.absent_fact)]
    line("absent fact in neither channel", not mem_a and not found_a and not err_a and not ev_a,
         err_a or ("; ".join(os.path.basename(p) for p in mem_a + ev_a) + (" store" if found_a else "") if (mem_a or ev_a or found_a) else "absent"))
    # addendum: row counts, before and after (after is read last, so a write by any read above would show)
    after = table_counts(db)
    allowed = allowed_arg if allowed_arg is not None else default_allowed(before, after)
    print("row counts before:"); [print(f"  {t} {before[t]}") for t in sorted(before)]
    print("row counts after:"); [print(f"  {t} {after[t]}") for t in sorted(after)]
    bad = changed_tables(before, after, allowed)
    line("row counts: only the observation write's tables changed", not bad, ", ".join(bad) or "ok")

    print("ALL CHECKS PASS" if not fails else f"{len(fails)} CHECK(S) FAILED; discard this disposable copy")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
