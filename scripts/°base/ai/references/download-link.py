#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "markdownify>=0.13,<2",
# ]
# ///
from __future__ import annotations

import argparse
import dataclasses
import html.parser
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable


USER_AGENT = "base-download-link/1.0"


class DownloadError(RuntimeError):
    pass


@dataclasses.dataclass(frozen=True)
class Response:
    url: str
    status: int
    content: bytes
    content_type: str = ""

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")


@dataclasses.dataclass(frozen=True)
class DownloadPlan:
    source_url: str
    download_url: str
    output_path: Path
    convert_html: bool


Fetch = Callable[[str, str], Response]


def strip_fragment(url: str) -> str:
    parts = urllib.parse.urlsplit(url.strip())
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


def url_path_segments(url: str) -> list[str]:
    parts = urllib.parse.urlsplit(strip_fragment(url))
    segments = [parts.scheme.rstrip(":") or "unknown", parts.netloc]
    path = parts.path.lstrip("/")
    if path:
        segments.extend(part for part in path.split("/") if part)
    return [sanitize_path_segment(part) for part in segments if part]


def sanitize_path_segment(value: str) -> str:
    value = urllib.parse.unquote(value)
    value = value.replace("\x00", "")
    value = value.replace(os.sep, "_")
    if os.altsep:
        value = value.replace(os.altsep, "_")
    if value in {"", ".", ".."}:
        return "_"
    return value


def output_path_for_url(output_root: Path, url: str) -> Path:
    return output_root.joinpath(*url_path_segments(url))


def markdown_candidate_urls(url: str) -> list[str]:
    base = strip_fragment(url)
    parts = urllib.parse.urlsplit(base)
    if parts.path.endswith(".md"):
        return [base]

    candidates: list[str] = []
    path = parts.path or "/"
    stem, ext = os.path.splitext(path)
    if ext:
        candidates.append(urllib.parse.urlunsplit(parts._replace(path=f"{stem}.md")))
        candidates.append(urllib.parse.urlunsplit(parts._replace(path=f"{path}.md")))
    else:
        candidates.append(urllib.parse.urlunsplit(parts._replace(path=f"{path.rstrip('/')}.md")))
    return unique(candidates)


def unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def fetch_url(url: str, method: str = "GET") -> Response:
    request = urllib.request.Request(
        url,
        method=method,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/markdown,text/html,application/json,text/plain,*/*",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            content = b"" if method == "HEAD" else response.read()
            return Response(
                url=response.geturl(),
                status=int(response.status),
                content=content,
                content_type=response.headers.get("Content-Type", ""),
            )
    except urllib.error.HTTPError as exc:
        content = exc.read() if method != "HEAD" else b""
        exc.close()
        return Response(
            url=url,
            status=int(exc.code),
            content=content,
            content_type=exc.headers.get("Content-Type", ""),
        )
    except urllib.error.URLError as exc:
        raise DownloadError(f"fetch failed for {url}: {exc}") from exc


def github_api_json(url: str, fetch: Fetch) -> dict:
    response = fetch(url, "GET")
    if response.status != 200:
        raise DownloadError(f"GitHub API returned HTTP {response.status}: {url}")
    try:
        data = json.loads(response.text)
    except json.JSONDecodeError as exc:
        raise DownloadError(f"GitHub API did not return JSON: {url}") from exc
    if not isinstance(data, dict):
        raise DownloadError(f"GitHub API returned unexpected JSON: {url}")
    return data


def github_ref_sha(owner: str, repo: str, ref: str, fetch: Fetch) -> str:
    api_ref = urllib.parse.quote(f"heads/{ref}", safe="/")
    data = github_api_json(f"https://api.github.com/repos/{owner}/{repo}/git/ref/{api_ref}", fetch)
    obj = data.get("object") if isinstance(data, dict) else None
    sha = obj.get("sha") if isinstance(obj, dict) else None
    if isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha):
        return sha

    api_ref = urllib.parse.quote(f"tags/{ref}", safe="/")
    data = github_api_json(f"https://api.github.com/repos/{owner}/{repo}/git/ref/{api_ref}", fetch)
    obj = data.get("object") if isinstance(data, dict) else None
    sha = obj.get("sha") if isinstance(obj, dict) else None
    if isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha):
        return sha
    raise DownloadError(f"could not resolve GitHub ref {owner}/{repo}@{ref}")


def parse_github_blob(url: str) -> tuple[str, str, list[str]] | None:
    parts = urllib.parse.urlsplit(strip_fragment(url))
    if parts.netloc.lower() != "github.com":
        return None
    items = [part for part in parts.path.split("/") if part]
    if len(items) < 5 or items[2] != "blob":
        return None
    owner, repo = items[0], items[1]
    rest = items[3:]
    return owner, repo, rest


def github_plan(url: str, output_root: Path, fetch: Fetch) -> DownloadPlan | None:
    parsed = parse_github_blob(url)
    if parsed is None:
        return None
    owner, repo, rest = parsed
    if re.fullmatch(r"[0-9a-f]{40}", rest[0]):
        commit = rest[0]
        path = "/".join(rest[1:])
    else:
        commit = ""
        path = ""
        for index in range(1, len(rest)):
            ref = "/".join(rest[:index])
            candidate_path = "/".join(rest[index:])
            try:
                commit = github_ref_sha(owner, repo, ref, fetch)
            except DownloadError:
                continue
            path = candidate_path
            break
        if not commit or not path:
            raise DownloadError(f"could not resolve GitHub blob URL: {url}")
    permalink = f"https://github.com/{owner}/{repo}/blob/{commit}/{path}"
    raw = f"https://raw.githubusercontent.com/{owner}/{repo}/{commit}/{path}"
    return DownloadPlan(
        source_url=permalink,
        download_url=raw,
        output_path=output_path_for_url(output_root, permalink),
        convert_html=not path.endswith(".md"),
    )


@dataclasses.dataclass(frozen=True)
class GenericForgePattern:
    host_regex: str
    marker: str
    raw_template: str
    commit_template: str
    repo_parts: int = 2


GENERIC_FORGES = [
    GenericForgePattern(
        host_regex=r".*",
        marker="-/blob",
        raw_template="{scheme}://{host}/{repo}/-/raw/{ref}/{path}",
        commit_template="{scheme}://{host}/{repo}/-/blob/{commit}/{path}",
    ),
    GenericForgePattern(
        host_regex=r".*",
        marker="src/branch",
        raw_template="{scheme}://{host}/{repo}/raw/branch/{ref}/{path}",
        commit_template="{scheme}://{host}/{repo}/src/commit/{commit}/{path}",
    ),
    GenericForgePattern(
        host_regex=r".*",
        marker="src/tag",
        raw_template="{scheme}://{host}/{repo}/raw/tag/{ref}/{path}",
        commit_template="{scheme}://{host}/{repo}/src/commit/{commit}/{path}",
    ),
    GenericForgePattern(
        host_regex=r".*",
        marker="src/commit",
        raw_template="{scheme}://{host}/{repo}/raw/commit/{ref}/{path}",
        commit_template="{scheme}://{host}/{repo}/src/commit/{commit}/{path}",
    ),
    GenericForgePattern(
        host_regex=r"(^bitbucket\.org$)",
        marker="src",
        raw_template="{scheme}://{host}/{repo}/raw/{ref}/{path}",
        commit_template="{scheme}://{host}/{repo}/src/{commit}/{path}",
    ),
]


def git_ls_remote_sha(repo_url: str, ref: str) -> str | None:
    candidates = [f"refs/heads/{ref}", f"refs/tags/{ref}", ref]
    for candidate in candidates:
        result = subprocess.run(
            ["git", "ls-remote", repo_url, candidate],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            continue
        first = (result.stdout or "").splitlines()
        if not first:
            continue
        sha = first[0].split()[0]
        if re.fullmatch(r"[0-9a-f]{40}", sha):
            return sha
    return None


def generic_forge_plan(url: str, output_root: Path) -> DownloadPlan | None:
    parts = urllib.parse.urlsplit(strip_fragment(url))
    host = parts.netloc.lower()
    items = [part for part in parts.path.split("/") if part]
    for pattern in GENERIC_FORGES:
        if not re.search(pattern.host_regex, host):
            continue
        try:
            marker_parts = pattern.marker.split("/")
            marker_index = next(
                i for i in range(len(items))
                if items[i:i + len(marker_parts)] == marker_parts
            )
        except StopIteration:
            continue
        if marker_index < pattern.repo_parts:
            continue
        repo = "/".join(items[:marker_index])
        rest = items[marker_index + len(marker_parts):]
        if len(rest) < 2:
            continue
        ref = rest[0]
        path = "/".join(rest[1:])
        commit = ref if re.fullmatch(r"[0-9a-f]{40}", ref) else None
        if commit is None:
            repo_url = f"{parts.scheme}://{parts.netloc}/{repo}.git"
            commit = git_ls_remote_sha(repo_url, ref) or ref
        raw = pattern.raw_template.format(
            scheme=parts.scheme,
            host=parts.netloc,
            repo=repo,
            ref=ref,
            commit=commit,
            path=path,
        )
        permalink = pattern.commit_template.format(
            scheme=parts.scheme,
            host=parts.netloc,
            repo=repo,
            ref=ref,
            commit=commit,
            path=path,
        )
        return DownloadPlan(
            source_url=permalink,
            download_url=raw,
            output_path=output_path_for_url(output_root, permalink),
            convert_html=not path.endswith(".md"),
        )
    return None


def unsupported_forge_reason(url: str) -> str | None:
    host = urllib.parse.urlsplit(strip_fragment(url)).netloc.lower()
    names = {
        "sourceforge.net": "SourceForge",
        "git.sr.ht": "SourceHut",
        "launchpad.net": "Launchpad",
        "console.aws.amazon.com": "AWS CodeCommit",
    }
    if "radicle" in host:
        return "Radicle URLs are not standardized enough to map to raw files safely."
    for suffix, name in names.items():
        if host == suffix or host.endswith("." + suffix):
            return f"{name} URL shape is not supported yet for safe raw-file downloads."
    return None


def resolve_plan(url: str, output_root: Path, fetch: Fetch = fetch_url) -> DownloadPlan:
    cleaned = strip_fragment(url)
    for resolver in (github_plan,):
        plan = resolver(cleaned, output_root, fetch)
        if plan is not None:
            return plan

    generic = generic_forge_plan(cleaned, output_root)
    if generic is not None:
        return generic

    unsupported = unsupported_forge_reason(cleaned)
    if unsupported:
        raise DownloadError(unsupported)

    parts = urllib.parse.urlsplit(cleaned)
    if not parts.scheme or not parts.netloc:
        raise DownloadError(f"expected absolute URL, got: {url!r}")
    if parts.path.endswith(".md"):
        return DownloadPlan(
            source_url=cleaned,
            download_url=cleaned,
            output_path=output_path_for_url(output_root, cleaned),
            convert_html=False,
        )

    return DownloadPlan(
        source_url=cleaned,
        download_url=cleaned,
        output_path=output_path_for_url(output_root, cleaned) / "_.md",
        convert_html=True,
    )


def markdown_plan_if_available(plan: DownloadPlan, output_root: Path, fetch: Fetch) -> DownloadPlan:
    if not plan.convert_html:
        return plan
    for candidate in markdown_candidate_urls(plan.download_url):
        response = fetch(candidate, "GET")
        if response.status == 200 and looks_markdown(response):
            source_candidate = candidate
            if candidate == plan.download_url:
                source_candidate = plan.source_url
            return DownloadPlan(
                source_url=source_candidate,
                download_url=candidate,
                output_path=output_path_for_url(output_root, source_candidate),
                convert_html=False,
            )
    return plan


def looks_markdown(response: Response) -> bool:
    content_type = response.content_type.lower()
    if "markdown" in content_type or "text/plain" in content_type:
        return True
    if "html" in content_type:
        return False
    text = response.text.lstrip()
    return not text.startswith("<!doctype") and not text.startswith("<html")


class RevisionParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_code = False
        self.revision: str | None = None
        self._recent_text = ""

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() == "code" and "Revision" in self._recent_text[-80:]:
            self.in_code = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "code":
            self.in_code = False

    def handle_data(self, data: str) -> None:
        if self.in_code and self.revision is None:
            value = data.strip()
            if re.fullmatch(r"[0-9A-Za-z._-]+", value):
                self.revision = value
        self._recent_text = (self._recent_text + data)[-200:]


def readthedocs_revision(html: str) -> str | None:
    parser = RevisionParser()
    parser.feed(html)
    return parser.revision


class TextHTMLParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in {"p", "br", "div", "section", "article", "h1", "h2", "h3", "li"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.parts.append(text + " ")

    def markdown(self) -> str:
        text = "".join(self.parts)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip() + "\n"


def html_to_markdown(html: str) -> str:
    try:
        from markdownify import markdownify as md  # type: ignore
    except ImportError:
        parser = TextHTMLParser()
        parser.feed(html)
        return parser.markdown()
    return md(html, heading_style="ATX").strip() + "\n"


def final_output_path(plan: DownloadPlan, html_text: str) -> Path:
    host = urllib.parse.urlsplit(plan.source_url).netloc.lower()
    if host.endswith("readthedocs.io"):
        revision = readthedocs_revision(html_text)
        if revision:
            return (
                plan.output_path.parent / f"{revision}.md"
                if plan.output_path.name == "_.md"
                else plan.output_path / f"{revision}.md"
            )
    return plan.output_path


def download(plan: DownloadPlan, fetch: Fetch = fetch_url) -> tuple[Path, bytes]:
    response = fetch(plan.download_url, "GET")
    if response.status != 200:
        raise DownloadError(f"HTTP {response.status}: {plan.download_url}")
    if plan.convert_html:
        path = final_output_path(plan, response.text)
        return path, html_to_markdown(response.text).encode("utf-8")
    return plan.output_path, response.content


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


if __name__ == "__main__":
    raise SystemExit(main())
