from __future__ import annotations

from dataclasses import dataclass

import requests

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) ccet-crawler/0.0.1"
REQUEST_TIMEOUT_SECONDS = 30


@dataclass
class FetchedPage:
    url: str
    status_code: int
    text: str
# end class


def fetch_guide_page(url: str) -> FetchedPage:
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return FetchedPage(url=url, status_code=response.status_code, text=response.text)
# end def
