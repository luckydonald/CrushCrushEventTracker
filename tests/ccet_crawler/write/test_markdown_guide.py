from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bs4 import BeautifulSoup

from ccet_crawler.write.markdown_guide import render_guide_markdown, write_guide_markdown


class RenderGuideMarkdownTest(unittest.TestCase):
    def test_downloads_images_and_rewrites_to_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            image_output_dir = Path(tmp) / "img"
            soup = BeautifulSoup(
                '<div class="guide"><h2>Charlotte</h2><img src="https://example.com/a.png" alt="pic"></div>',
                "html.parser",
            )
            guide = soup.div

            markdown_text = render_guide_markdown(guide, image_output_dir, downloader=lambda url: b"image-bytes")

            self.assertIn("Charlotte", markdown_text)
            self.assertNotIn("https://example.com/a.png", markdown_text)
            self.assertIn("img/", markdown_text)
            self.assertEqual(len(list(image_output_dir.iterdir())), 1)
        # end with
    # end def
# end class


class WriteGuideMarkdownTest(unittest.TestCase):
    def test_writes_file_creating_parent_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "guide" / "README.md"
            write_guide_markdown("# Hello", output_path)
            self.assertEqual(output_path.read_text(encoding="utf-8"), "# Hello")
        # end with
    # end def
# end class


if __name__ == "__main__":
    unittest.main()
# end if
