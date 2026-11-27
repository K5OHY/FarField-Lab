"""The example logs on the Log page: a card for each, with what the log is, the antenna and power, and a link to the video it came from. The text of the cards is
`examples/log/manifest.json`; the log and the saved RBN and WSPR data behind each (so it opens at once) are made by `build_log_examples.py`."""
import json
from functools import lru_cache

import frozen_data

DIR = frozen_data.DIR


@lru_cache(maxsize=1)
def manifest():
    """The examples that can be opened (their log and their saved data are both there), as a list of dicts, in the order of the manifest."""
    path = DIR / "manifest.json"
    if not path.exists():
        return []
    ready = set(frozen_data.available())
    return [e for e in json.loads(path.read_text(encoding="utf-8")) if e["key"] in ready and (DIR / f"{e['key']}.adi").exists()]


def get(key):
    """One example's card, or None."""
    return next((e for e in manifest() if e["key"] == key), None)


def log_bytes(key):
    """The text of an example's log, as an uploaded file's bytes."""
    return (DIR / f"{key}.adi").read_bytes()


def file_name(key):
    return f"{key}.adi"
