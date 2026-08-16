from __future__ import annotations

from pathlib import Path

GUIDE_URL = "https://steamcommunity.com/sharedfiles/filedetails/?id=2911827400"

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"

CRAWL_GUIDE_DIR = DATA_DIR / "crawl" / "guide"
RAW_HTML_PATH = CRAWL_GUIDE_DIR / "raw.html"
RAWISH_MARKDOWN_PATH = CRAWL_GUIDE_DIR / "rawish.md"

GUIDE_DIR = DATA_DIR / "guide"
GUIDE_README_PATH = GUIDE_DIR / "README.md"
GUIDE_IMG_DIR = GUIDE_DIR / "img"

EVENTS_DIR = DATA_DIR / "events"

DATE_ACTIVITY_PRICES: dict[str, int] = {
    "Moonlight Stroll": 500,
    "Movie Theater": 25_000,
    "Sightseeing": 5_000,
    "Beach": 2_500,
}
