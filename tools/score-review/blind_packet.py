"""The phase-2 packet builder.

Blind by construction: this module takes the items file and a seed, and nothing else. It has no
parameter, import or code path that could reach any other study file, so what it writes cannot
carry anything that file does not hold. It writes the standalone packet and the letter key.
"""
import hashlib
import json
import os
import random
import re

from chatfile import load_chat

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_ITEM_RE = re.compile(r"^[A-Za-z0-9._-]+$")
CITED_NOT_SHOWN = "Cited messages: not shown for this item"


def load_item(items_path, item_id):
    if not _ITEM_RE.match(item_id or ""):
        raise ValueError("item id %r is not a plain token" % (item_id,))
    with open(items_path, "r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("item_id") == item_id:
                return row
    raise ValueError("item %s not found in the items file" % item_id)


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
    answers = letter_order(item, seed)
    if len(answers) > len(LETTERS):
        raise ValueError("too many answers for letter labels")
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


def write_packet(items_path, item_id, seed, keys_dir, out_dir, chat_path=None):
    """Write packets/phase2/<item>.md and keys/<item>.json. Returns (packet_path, key_path, key_sha256).

    The packet is written first and the key last, each through a temporary file and an atomic rename, so a
    failure leaves no key without its packet and no half-written file. An existing key file is never read
    and never overwritten: the builder refuses instead.
    """
    item = load_item(items_path, item_id)
    key_path = os.path.join(keys_dir, "%s.json" % item_id)
    if os.path.exists(key_path):
        raise ValueError("a key file already exists for %s; it is never overwritten" % item_id)
    chat = load_chat(chat_path) if chat_path else None
    text, letters = build_packet(item, seed, chat)
    key = {"schema_version": 1, "item_id": item_id, "seed": seed, "letters": letters}
    key_bytes = (json.dumps(key, sort_keys=True) + "\n").encode("utf-8")
    os.makedirs(keys_dir, exist_ok=True)
    os.makedirs(out_dir, exist_ok=True)
    packet_path = os.path.join(out_dir, "%s.md" % item_id)
    had_packet = os.path.lexists(packet_path)
    tmp_packet = _stage(packet_path, text.encode("utf-8"))
    try:
        os.replace(tmp_packet, packet_path)
    except BaseException:
        _drop(tmp_packet)
        raise
    tmp_key = None
    try:
        tmp_key = _stage(key_path, key_bytes)
        os.link(tmp_key, key_path)  # atomic, and it fails if a key appeared meanwhile: never an overwrite
    except FileExistsError:
        if not had_packet:
            _drop(packet_path)
        raise ValueError("a key file already exists for %s; it is never overwritten" % item_id)
    except BaseException:
        if not had_packet:
            _drop(packet_path)
        raise
    finally:
        if tmp_key is not None:
            _drop(tmp_key)
    return packet_path, key_path, hashlib.sha256(key_bytes).hexdigest()
