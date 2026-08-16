from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FetchedImage:
    source_url: str
    content: bytes
    content_type: str | None
# end class
