"""The one definition of the canonical SECRET seed: 64 lowercase hex characters.

Imports only `re`, so the blind packet builder and the importer can both use it without a cycle and without the packet
builder gaining a path to any study file. `reveal` publishes an item id, its letters and the sha256 of its key file, and
the answer ids are public sha256 values of the import seed, so only the seed stays unknown to a reader: a short or
guessable one could be brute-forced. Every writer of a secret-derived artifact (`blind_packet.write_packet`,
`importers.beam.build_records`) calls `require_canonical_seed` itself, so no caller can skip it.
"""
import re

SECRET_SEED_RE = re.compile(r"^[0-9a-f]{64}$")


def is_canonical_seed(value):
    return isinstance(value, str) and SECRET_SEED_RE.fullmatch(value) is not None


def require_canonical_seed(value, name):
    """Raise ValueError unless value is canonical. The message names the seed, never its value."""
    if not is_canonical_seed(value):
        raise ValueError("%s must be 64 lowercase hex characters (the canonical secret seed); the value is not echoed" % name)
