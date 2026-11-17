"""The phase-2 packet builder.

Blind by construction: this module takes the items file and a seed, and nothing else. It has no
parameter, import or code path that could reach any other study file, so what it writes cannot
carry anything that file does not hold. It writes the standalone packet and the letter key.
"""
import glob
import hashlib
import json
import os
import random

from chatfile import load_chat
from ids import valid_answer_id, valid_item_id

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
CITED_NOT_SHOWN = "Cited messages: not shown for this item"


def load_item(items_path, item_id):
    """Return the one row for item_id. The whole file is read: a duplicate row, or any row that is not a JSON
    object with an item_id, is refused before anything is written, never resolved by taking the first match."""
    if not valid_item_id(item_id):
        raise ValueError("item id %r is not a plain token" % (item_id,))
    found = []
    with open(items_path, "r", encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError as exc:
                raise ValueError("items file row %d is not JSON: %s" % (n, exc))
            if not isinstance(row, dict) or not isinstance(row.get("item_id"), str):
                raise ValueError("items file row %d is not a JSON object with an item_id" % n)
            if row["item_id"] == item_id:
                found.append(row)
    if not found:
        raise ValueError("item %s not found in the items file" % item_id)
    if len(found) > 1:
        raise ValueError("item %s occurs on more than one row of the items file; the key could not be trusted" % item_id)
    return found[0]


def check_answers(item):
    """Refuse an item the key could not describe: the key maps letters to answer ids, so the ids must be distinct."""
    answers = item.get("answers")
    if not isinstance(answers, list) or not answers:
        raise ValueError("item %s has no answers" % item.get("item_id"))
    ids = []
    for ans in answers:
        aid = ans.get("answer_id") if isinstance(ans, dict) else None
        if not isinstance(aid, str) or not aid:
            raise ValueError("item %s has an answer with no answer_id" % item.get("item_id"))
        if not valid_answer_id(aid):
            raise ValueError("item %s has an answer id %r the scorer would refuse (lowercase letters and digits, "
                             "not a reserved id)" % (item.get("item_id"), aid))
        ids.append(aid)
    if len(set(ids)) != len(ids):
        raise ValueError("item %s has answers whose answer ids are not distinct" % item.get("item_id"))
    if len(ids) > len(LETTERS):
        raise ValueError("too many answers for letter labels")


def letter_order(item, seed):
    """The permutation is derived from (seed, item_id): one seed, a different order for each item."""
    answers = sorted(item["answers"], key=lambda a: a["answer_id"])
    rng = random.Random("%s\x1f%s" % (seed, item["item_id"]))
    rng.shuffle(answers)
    return answers


def build_packet(item, seed, chat=None):
    """Return (packet_text, letters) where letters maps "A".. to the answer id shown under it.

    The cited-messages line can tell answers apart (the benchmark's reference cites messages, an agent's
    answer often cannot), so cited ids are listed only when EVERY answer of the item has a non-empty list;
    otherwise no answer gets one and a single neutral line says so.
    """
    check_answers(item)
    answers = letter_order(item, seed)
    show_cited = all(ans.get("cited_ids") for ans in answers)
    out = ["# Review packet: %s" % item["item_id"], "", "## Question", "", item["question"], "", "## Answers", "",
           "The answers below are in an arbitrary order and carry letters only.", ""]
    if not show_cited:
        out += [CITED_NOT_SHOWN, ""]
    letters = {}
    for letter, ans in zip(LETTERS, answers):
        letters[letter] = ans["answer_id"]
        out += ["### Answer %s" % letter, "", ans["text"], ""]
        if show_cited:
            cited = ans["cited_ids"]
            out.append("Cited messages: %s" % ", ".join(str(c) for c in cited))
            if chat is not None:
                for c in cited:
                    m = chat.get(c)
                    out += ["", "#### msg %d | %s | %s" % (c, m["role"], m["date"]) if m else "#### msg %d (not in the chat file)" % c]
                    if m:
                        out += ["", m["body"]]
            out.append("")
    return "\n".join(out), letters


def _stage(path, data):
    """Write data to a fresh temporary file beside path and return its name (the caller renames or removes it)."""
    tmp = "%s.tmp-%d" % (path, os.getpid())
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
    except BaseException:
        _drop(tmp)
        raise
    return tmp


def _drop(path):
    try:
        os.unlink(path)
    except OSError:
        pass


def _stale_temps(path):
    """Temporary files an earlier, killed run left beside `path` (named <path>.tmp-<pid>)."""
    return sorted(glob.glob(glob.escape(path) + ".tmp-*"))


def _place(tmp, path):
    """Hard-link the staged file to path: atomic, and it fails if path exists, so it is never an overwrite."""
    try:
        os.link(tmp, path)
    finally:
        _drop(tmp)


def write_packet(items_path, item_id, seed, keys_dir, out_dir, chat_path=None):
    """Write packets/phase2/<item>.md and keys/<item>.json. Returns (packet_path, key_path, key_sha256).

    The packet is written first and the key last, each through a temporary file and a hard link, so a failure
    leaves no key without its packet and no half-written file. An existing packet or key is never read and never
    overwritten: the builder refuses instead. Because the packet is placed the same way, a packet that exists when
    the key stage fails is always this run's own, and it is then removed. A stale temporary file beside either
    output (a killed run's residue) is refused by name, never ignored.
    """
    item = load_item(items_path, item_id)
    key_path = os.path.join(keys_dir, "%s.json" % item_id)
    packet_path = os.path.join(out_dir, "%s.md" % item_id)
    stale = _stale_temps(packet_path) + _stale_temps(key_path)
    if stale:
        raise ValueError("a stale temporary file from an interrupted run sits beside the outputs: %s; "
                         "check it and remove it, then run again" % ", ".join(stale))
    if os.path.lexists(key_path):
        raise ValueError("a key file already exists for %s; it is never overwritten" % item_id)
    if os.path.lexists(packet_path):
        raise ValueError("a packet already exists for %s; it is never overwritten" % item_id)
    chat = load_chat(chat_path) if chat_path else None
    text, letters = build_packet(item, seed, chat)
    key = {"schema_version": 1, "item_id": item_id, "seed": seed, "letters": letters}
    key_bytes = (json.dumps(key, sort_keys=True) + "\n").encode("utf-8")
    os.makedirs(keys_dir, exist_ok=True)
    os.makedirs(out_dir, exist_ok=True)
    tmp_packet = _stage(packet_path, text.encode("utf-8"))
    try:
        _place(tmp_packet, packet_path)
    except FileExistsError:
        raise ValueError("a packet already exists for %s; it is never overwritten" % item_id)
    # From here the packet is this run's own: the link above would have failed on any other file.
    try:
        tmp_key = _stage(key_path, key_bytes)
        _place(tmp_key, key_path)
    except FileExistsError:
        _drop(packet_path)
        raise ValueError("a key file already exists for %s; it is never overwritten" % item_id)
    except BaseException:
        _drop(packet_path)
        raise
    return packet_path, key_path, hashlib.sha256(key_bytes).hexdigest()
