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
    """Return (packet_text, letters) where letters maps "A".. to the answer id shown under it."""
    answers = letter_order(item, seed)
    if len(answers) > len(LETTERS):
        raise ValueError("too many answers for letter labels")
    out = ["# Review packet: %s" % item["item_id"], "", "## Question", "", item["question"], "", "## Answers", "",
           "The answers below are in an arbitrary order and carry letters only.", ""]
    letters = {}
    for letter, ans in zip(LETTERS, answers):
        letters[letter] = ans["answer_id"]
        out += ["### Answer %s" % letter, "", ans["text"], ""]
        cited = ans.get("cited_ids") or []
        if cited:
            out.append("Cited messages: %s" % ", ".join(str(c) for c in cited))
            if chat is not None:
                for c in cited:
                    m = chat.get(c)
                    out += ["", "#### msg %d | %s | %s" % (c, m["role"], m["date"]) if m else "#### msg %d (not in the chat file)" % c]
                    if m:
                        out += ["", m["body"]]
        else:
            out.append("(no messages cited)")
        out.append("")
    return "\n".join(out), letters


def write_packet(items_path, item_id, seed, keys_dir, out_dir, chat_path=None):
    """Write packets/phase2/<item>.md and keys/<item>.json. Returns (packet_path, key_path, key_sha256).

    An existing key file is never read and never overwritten: the builder refuses instead.
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
    with open(key_path, "xb") as fh:
        fh.write(key_bytes)
    with open(packet_path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return packet_path, key_path, hashlib.sha256(key_bytes).hexdigest()
