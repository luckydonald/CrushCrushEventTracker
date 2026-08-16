from __future__ import annotations

from bs4.element import Tag


def collect_images(body: Tag) -> list[tuple[str, str]]:
    images: list[tuple[str, str]] = []
    for img in body.find_all("img"):
        src = img.get("src")
        if not src:
            continue
        # end if
        images.append((src, img.get("alt", "")))
    # end for
    return images
# end def
