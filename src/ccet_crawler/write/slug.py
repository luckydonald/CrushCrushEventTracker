from __future__ import annotations

import re

_SLUG_INVALID_CHARS_PATTERN = re.compile(r"[^A-Za-z0-9]+")


def slugify(text: str) -> str:
    return _SLUG_INVALID_CHARS_PATTERN.sub("_", text).strip("_")
# end def
