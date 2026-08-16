from __future__ import annotations

import unittest

from ccet_crawler.models.levels import GIRL_LEVEL_ORDER, GirlLevel, resolve_girl_level


class ResolveGirlLevelTest(unittest.TestCase):
    def test_standard_label_resolves_by_value(self) -> None:
        self.assertEqual(resolve_girl_level("Adversary", row_index=0), GirlLevel.ADVERSARY)
        self.assertEqual(resolve_girl_level("Girlfriend", row_index=8), GirlLevel.GIRLFRIEND)
    # end def

    def test_renamed_label_falls_back_to_row_index(self) -> None:
        self.assertEqual(resolve_girl_level("Total Stranger", row_index=0), GirlLevel.ADVERSARY)
    # end def

    def test_out_of_range_index_resolves_to_none(self) -> None:
        self.assertIsNone(resolve_girl_level("Unknown", row_index=99))
    # end def

    def test_order_has_all_nine_levels(self) -> None:
        self.assertEqual(len(GIRL_LEVEL_ORDER), 9)
    # end def
# end class


if __name__ == "__main__":
    unittest.main()
# end if
