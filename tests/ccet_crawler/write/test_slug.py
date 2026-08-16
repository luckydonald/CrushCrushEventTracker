from __future__ import annotations

import unittest

from ccet_crawler.write.slug import slugify


class SlugifyTest(unittest.TestCase):
    def test_spaces_become_underscores(self) -> None:
        self.assertEqual(slugify("Fuzzy Festival"), "Fuzzy_Festival")
    # end def

    def test_ampersand_and_apostrophe_are_stripped(self) -> None:
        self.assertEqual(slugify("Ginger & Wasabi"), "Ginger_Wasabi")
        self.assertEqual(slugify("Valentine's Event"), "Valentine_s_Event")
    # end def

    def test_no_leading_or_trailing_underscore(self) -> None:
        self.assertEqual(slugify("!Wow!"), "Wow")
    # end def
# end class


if __name__ == "__main__":
    unittest.main()
# end if
