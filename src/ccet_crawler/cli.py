from __future__ import annotations

import argparse

from bs4 import BeautifulSoup
from markdownify import markdownify

from ccet_crawler import config
from ccet_crawler.fetch.client import fetch_guide_page
from ccet_crawler.git_add import git_add


def cmd_fetch(add_to_git: bool) -> None:
    page = fetch_guide_page(config.GUIDE_URL)

    config.CRAWL_GUIDE_DIR.mkdir(parents=True, exist_ok=True)
    config.RAW_HTML_PATH.write_text(page.text, encoding="utf-8")

    soup = BeautifulSoup(page.text, "html.parser")
    guide = soup.select_one("#profileBlock > .guide")
    rawish = markdownify(str(guide), heading_style="ATX") if guide is not None else ""
    config.RAWISH_MARKDOWN_PATH.write_text(rawish, encoding="utf-8")

    if add_to_git:
        git_add(config.RAW_HTML_PATH)
        git_add(config.RAWISH_MARKDOWN_PATH)
    # end if
# end def


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ccet-crawler")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser("fetch", help="Fetch the raw guide page and save it locally.")
    fetch_parser.add_argument("--add-to-git", action="store_true")

    return parser
# end def


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "fetch":
        cmd_fetch(add_to_git=args.add_to_git)
    # end if
# end def


if __name__ == "__main__":
    main()
# end if
