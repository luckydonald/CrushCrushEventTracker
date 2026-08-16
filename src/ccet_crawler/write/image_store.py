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
            filename = f"{digest}{_guess_extension(source_url)}"
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


def _guess_extension(url: str) -> str:
    path = url.split("?", 1)[0].split("#", 1)[0]
    basename = path.rsplit("/", 1)[-1]
    if "." in basename:
        return "." + basename.rsplit(".", 1)[-1]
    # end if
    return ".bin"
# end def
