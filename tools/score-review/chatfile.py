"""Parser for the chat file format: `## msg <id> | <role> | <date>` headers, each followed by the body."""
import re

_HEADER = re.compile(r"^## msg (\d+) \| ([^|]*?) \| (.*)$")


def parse_chat(text):
    """Return {msg_id: {"role": str, "date": str, "body": str}}. Duplicate ids are an error."""
    msgs = {}
    cur = None
    buf = []

    def flush():
        if cur is not None:
            msgs[cur[0]] = {"role": cur[1], "date": cur[2], "body": "\n".join(buf).strip()}

    for line in text.splitlines():
        m = _HEADER.fullmatch(line)
        if m:
            flush()
            mid = int(m.group(1))
            if mid in msgs:
                raise ValueError("duplicate message id %d in chat file" % mid)
            cur = (mid, m.group(2), m.group(3))
            buf = []
        elif cur is not None:
            buf.append(line)
    flush()
    return msgs


def load_chat(path):
    with open(path, "r", encoding="utf-8") as fh:
        return parse_chat(fh.read())
