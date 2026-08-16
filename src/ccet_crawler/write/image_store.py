from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable

Downloader = Callable[[str], bytes]


def store_images(images: list[tuple[str, str]], output_dir: Path, downloader: Downloader) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)

    mapping: dict[str, str] = {}
    filename_by_hash: dict[str, str] = {}

    for source_url, _alt in images:
        content = downloader(source_url)
        digest = hashlib.sha256(content).hexdigest()[:16]

        if digest not in filename_by_hash:
            filename = f"{digest}{_guess_extension(source_url, content)}"
            path = output_dir / filename
            if not path.exists():
                path.write_bytes(content)
            # end if
            filename_by_hash[digest] = filename
        # end if

        mapping[source_url] = f"img/{filename_by_hash[digest]}"
    # end for

    return mapping
# end def


_MAGIC_BYTE_EXTENSIONS: list[tuple[bytes, str]] = [
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"\xff\xd8\xff", ".jpg"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
]


def _guess_extension(url: str, content: bytes) -> str:
    path = url.split("?", 1)[0].split("#", 1)[0]
    basename = path.rsplit("/", 1)[-1]
    if "." in basename:
        return "." + basename.rsplit(".", 1)[-1]
    # end if

    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return ".webp"
    # end if
    for magic, extension in _MAGIC_BYTE_EXTENSIONS:
        if content.startswith(magic):
            return extension
        # end if
    # end for

    return ".bin"
# end def
