from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .http import fetch_url
from .models import DownloadError
from .planner import download, markdown_plan_if_available, resolve_plan


def read_url_from_input(argv_url: str | None) -> str:
    if argv_url:
        return argv_url.strip()
    if not sys.stdin.isatty():
        data = sys.stdin.read().strip()
        if data:
            return data.splitlines()[0].strip()
        raise DownloadError(
            "No URL provided. Use `download-link.py URL` or pipe one with `echo URL | download-link.py`."
        )
    return input("URL: ").strip()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download documentation into ai/references.")
    parser.add_argument("url", nargs="?")
    parser.add_argument("--output-root", default="ai/references")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        url = read_url_from_input(args.url)
        if not url:
            raise DownloadError("No URL provided.")
        output_root = Path(args.output_root)
        plan = resolve_plan(url, output_root, fetch_url)
        plan = markdown_plan_if_available(plan, output_root, fetch_url)
        path, content = download(plan, fetch_url)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    except DownloadError as exc:
        print(f"download-link: {exc}", file=sys.stderr)
        return 1

    print(f"download: {plan.download_url}")
    print(f"wrote: {path}")
    return 0
