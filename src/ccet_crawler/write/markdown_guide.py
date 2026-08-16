from __future__ import annotations

from pathlib import Path

from bs4.element import Tag
from markdownify import markdownify

from ccet_crawler.html.images import collect_images
from ccet_crawler.write.image_store import Downloader, store_images


def render_guide_markdown(guide: Tag, image_output_dir: Path, downloader: Downloader) -> str:
    images = collect_images(guide)
    image_mapping = store_images(images, image_output_dir, downloader)

    for img in guide.find_all("img"):
        src = img.get("src")
        if src in image_mapping:
            img["src"] = image_mapping[src]
        # end if
    # end for

    return markdownify(str(guide), heading_style="ATX")
# end def


def write_guide_markdown(markdown_text: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown_text, encoding="utf-8")
# end def
