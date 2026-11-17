"""The one definition of item and answer ids. Imports only `re`, so the blind packet builder can use it and still
open no study file. Every validator of these ids elsewhere in the tool calls these predicates."""
import re

ITEM_RE = re.compile(r"^[A-Za-z0-9._-]+$")
ANSWER_RE = re.compile(r"^[0-9a-z]+$")
RESERVED_IDS = frozenset({"ambiguous", "official"})


def valid_item_id(value):
    return isinstance(value, str) and ITEM_RE.fullmatch(value) is not None


def valid_answer_id(value):
    return isinstance(value, str) and ANSWER_RE.fullmatch(value) is not None and value not in RESERVED_IDS
