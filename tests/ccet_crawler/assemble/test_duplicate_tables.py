from __future__ import annotations

import unittest

from ccet_crawler.assemble.duplicate_tables import merge_main_and_alt_tables
from ccet_crawler.models.event import CharacterRequirementTable


class MergeMainAndAltTablesTest(unittest.TestCase):
    def test_alt_tables_are_tagged_and_main_tables_are_untouched(self) -> None:
        main = [CharacterRequirementTable(girl_name="Loola", rows=[])]
        alt = [CharacterRequirementTable(girl_name="Loola", rows=[])]

        merged = merge_main_and_alt_tables(main, alt)

        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0].variant, "main")
        self.assertEqual(merged[1].variant, "alt")
        self.assertEqual(merged[0].girl_name, merged[1].girl_name)
    # end def

    def test_no_alt_tables_returns_only_main(self) -> None:
        main = [CharacterRequirementTable(girl_name="Cassia", rows=[])]
        self.assertEqual(merge_main_and_alt_tables(main, []), main)
    # end def

    def test_original_main_table_variant_untouched_when_reused(self) -> None:
        main = [CharacterRequirementTable(girl_name="Loola", rows=[])]
        alt = [CharacterRequirementTable(girl_name="Loola", rows=[])]
        merge_main_and_alt_tables(main, alt)
        self.assertEqual(main[0].variant, "main")
        self.assertEqual(alt[0].variant, "main")
    # end def
# end class


if __name__ == "__main__":
    unittest.main()
# end if
