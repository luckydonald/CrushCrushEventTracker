from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ccet_crawler.write.image_store import store_images


class StoreImagesTest(unittest.TestCase):
    def test_downloads_and_writes_each_unique_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "img"
            downloads = {"https://example.com/a.png": b"aaa", "https://example.com/b.png": b"bbb"}
            mapping = store_images(list(downloads.items()), output_dir, downloader=lambda url: downloads[url])

            self.assertEqual(len(mapping), 2)
            self.assertEqual(len(list(output_dir.iterdir())), 2)
            for source_url, relative_path in mapping.items():
                self.assertTrue((output_dir / Path(relative_path).name).exists())
            # end for
        # end with
    # end def

    def test_identical_content_is_deduplicated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "img"
            images = [("https://example.com/a.png", ""), ("https://example.com/a-mirror.png", "")]
            mapping = store_images(images, output_dir, downloader=lambda url: b"same-bytes")

            self.assertEqual(mapping["https://example.com/a.png"], mapping["https://example.com/a-mirror.png"])
            self.assertEqual(len(list(output_dir.iterdir())), 1)
        # end with
    # end def

    def test_extension_guessed_from_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "img"
            mapping = store_images(
                [("https://example.com/pic.jpg?v=2", "")], output_dir, downloader=lambda url: b"content"
            )
            self.assertTrue(mapping["https://example.com/pic.jpg?v=2"].endswith(".jpg"))
        # end with
    # end def

    def test_extension_sniffed_from_content_when_url_has_none(self) -> None:
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"rest-of-file"
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "img"
            mapping = store_images(
                [("https://images.steamusercontent.com/ugc/123/ABC/", "")],
                output_dir,
                downloader=lambda url: png_bytes,
            )
            self.assertTrue(mapping["https://images.steamusercontent.com/ugc/123/ABC/"].endswith(".png"))
        # end with
    # end def

    def test_unrecognized_content_without_url_extension_falls_back_to_bin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "img"
            mapping = store_images(
                [("https://example.com/opaque-id", "")], output_dir, downloader=lambda url: b"not-a-known-format"
            )
            self.assertTrue(mapping["https://example.com/opaque-id"].endswith(".bin"))
        # end with
    # end def
# end class


if __name__ == "__main__":
    unittest.main()
# end if
