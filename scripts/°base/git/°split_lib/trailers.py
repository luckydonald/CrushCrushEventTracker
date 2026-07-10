"""Shared git-trailer read/write helpers, built on `git interpret-trailers`."""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

_TRAILER_LINE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9-]*:\s")


def split_trailer_block(message: str) -> tuple[str, str]:
    """Split a full commit message into (body_without_trailers, trailer_block).

    The trailer block is the trailing run of "Key: value"-shaped lines after
    the last blank line -- the same heuristic sync_unclean.py's
    `_strip_trailers` already uses, exposed here as a shared helper so
    anything needing the trailer block's own text (not just stripping it)
    doesn't have to reimplement the line-walk. Returns ("", "") for an empty
    message, and (message, "") when there's no trailer-shaped trailing run.
    """
    lines = message.splitlines()
    trailer_lines: list[str] = []
    while lines and _TRAILER_LINE_RE.match(lines[-1]):
        trailer_lines.insert(0, lines.pop())
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines), "\n".join(trailer_lines)


def read_trailers(message: str, cwd: Path) -> dict[str, list[str]]:
    """Parse trailers out of a full commit message body.

    Returns a dict of trailer key -> list of values (a key may repeat).
    """
    result = subprocess.run(
        ["git", "interpret-trailers", "--parse"],
        cwd=cwd,
        input=message,
        capture_output=True,
        text=True,
        check=True,
    )
    trailers: dict[str, list[str]] = {}
    for line in result.stdout.splitlines():
        if not line.strip() or ":" not in line:
            continue
        key, _, value = line.partition(":")
        trailers.setdefault(key.strip(), []).append(value.strip())
    return trailers


def read_trailer_value(message: str, key: str, cwd: Path) -> str | None:
    """Convenience: return the first value for `key`, or None if absent."""
    values = read_trailers(message, cwd).get(key)
    return values[0] if values else None


def write_trailers(message: str, trailers: dict[str, str], cwd: Path) -> str:
    """Append the given trailers to a commit message, returning the new message text."""
    args = ["git", "interpret-trailers"]
    for key, value in trailers.items():
        args += ["--trailer", f"{key}: {value}"]

    with tempfile.NamedTemporaryFile("w", suffix=".msg", delete=False) as handle:
        handle.write(message)
        path = Path(handle.name)

    try:
        result = subprocess.run(
            [*args, str(path)],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    finally:
        path.unlink(missing_ok=True)
