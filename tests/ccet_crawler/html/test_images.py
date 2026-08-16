from __future__ import annotations

import unittest

from bs4 import BeautifulSoup

from ccet_crawler.html.images import collect_images


class CollectImagesTest(unittest.TestCase):
    def test_collects_src_and_alt_pairs(self) -> None:
        soup = BeautifulSoup(
            '<div><img src="https://example.com/a.png" alt="A"><p><img src="https://example.com/b.png"></p></div>',
            "html.parser",
        )
        images = collect_images(soup.div)
        self.assertEqual(
            images,
            [("https://example.com/a.png", "A"), ("https://example.com/b.png", "")],
        )
    # end def

    def test_skips_images_without_src(self) -> None:
        soup = BeautifulSoup('<div><img alt="no src"></div>', "html.parser")
        self.assertEqual(collect_images(soup.div), [])
    # end def
# end class


if __name__ == "__main__":
    unittest.main()
# end if
