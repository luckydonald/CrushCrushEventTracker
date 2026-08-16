from __future__ import annotations

import argparse
import json

from bs4 import BeautifulSoup
from markdownify import markdownify

from ccet_crawler import config
from ccet_crawler.assemble.build_event import build_events_from_html
from ccet_crawler.fetch.client import fetch_bytes, fetch_guide_page
from ccet_crawler.git_add import git_add
from ccet_crawler.write.event_json import write_event_json
from ccet_crawler.write.markdown_guide import render_guide_markdown, write_guide_markdown


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


def cmd_parse(input_path: str) -> None:
    html = config.RAW_HTML_PATH.read_text(encoding="utf-8") if input_path is None else open(input_path, encoding="utf-8").read()
    events = build_events_from_html(html)
    summary = [
        {
            "name": event.name,
            "year": event.year,
            "main_girl": event.main_girl,
            "girls": [table.girl_name for table in event.character_tables],
            "warnings": event.warnings,
        }
        for event in events
    ]
    print(json.dumps(summary, indent=2))
# end def


def cmd_write(input_path: str, add_to_git: bool) -> None:
    html = config.RAW_HTML_PATH.read_text(encoding="utf-8") if input_path is None else open(input_path, encoding="utf-8").read()

    soup = BeautifulSoup(html, "html.parser")
    guide = soup.select_one("#profileBlock > .guide")
    if guide is None:
        raise ValueError("Could not find '#profileBlock > .guide' in the given HTML.")
    # end if

    markdown_text = render_guide_markdown(guide, config.GUIDE_IMG_DIR, downloader=fetch_bytes)
    write_guide_markdown(markdown_text, config.GUIDE_README_PATH)

    events = build_events_from_html(html)
    written_paths = [path for event in events for path in write_event_json(event, config.EVENTS_DIR)]

    if add_to_git:
        git_add(config.GUIDE_README_PATH)
        git_add(config.GUIDE_IMG_DIR)
        for path in written_paths:
            git_add(path)
        # end for
    # end if
# end def


def cmd_crawl(add_to_git: bool) -> None:
    cmd_fetch(add_to_git=add_to_git)
    cmd_write(input_path=None, add_to_git=add_to_git)
# end def


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ccet-crawler")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser("fetch", help="Fetch the raw guide page and save it locally.")
    fetch_parser.add_argument("--add-to-git", action="store_true")

    parse_parser = subparsers.add_parser("parse", help="Parse the saved guide page and print a debug summary.")
    parse_parser.add_argument("--input", default=None, help="Path to a saved guide HTML file (defaults to the last fetch).")

    write_parser = subparsers.add_parser("write", help="Parse the saved guide page and write the Markdown guide + JSON events.")
    write_parser.add_argument("--input", default=None, help="Path to a saved guide HTML file (defaults to the last fetch).")
    write_parser.add_argument("--add-to-git", action="store_true")

    crawl_parser = subparsers.add_parser("crawl", help="Fetch, parse, and write in one step.")
    crawl_parser.add_argument("--add-to-git", action="store_true")

    return parser
# end def


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "fetch":
        cmd_fetch(add_to_git=args.add_to_git)
    elif args.command == "parse":
        cmd_parse(input_path=args.input)
    elif args.command == "write":
        cmd_write(input_path=args.input, add_to_git=args.add_to_git)
    elif args.command == "crawl":
        cmd_crawl(add_to_git=args.add_to_git)
    # end if
# end def


if __name__ == "__main__":
    main()
# end if
