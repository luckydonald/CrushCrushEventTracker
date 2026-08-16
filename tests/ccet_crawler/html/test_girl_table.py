from __future__ import annotations

import unittest
from pathlib import Path

from ccet_crawler.html.girl_table import parse_girl_tables
from ccet_crawler.html.guide_page import group_by_event, split_guide_sections
from ccet_crawler.models.levels import GirlLevel
from ccet_crawler.models.requirements import JobLevelRequirement

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


class ParseGirlTablesTest(unittest.TestCase):
    def setUp(self) -> None:
        html = (FIXTURES_DIR / "guide_page_sample.html").read_text(encoding="utf-8")
        events = group_by_event(split_guide_sections(html))
        self.tables = parse_girl_tables(events[0].girl_reqs)
    # end def

    def test_finds_all_six_girls_in_order(self) -> None:
        self.assertEqual(
            [table.girl_name for table in self.tables],
            ["Charlotte", "Jelle", "Bonchovy", "Spectrum", "Quillzone", "Cassia"],
        )
    # end def

    def test_each_table_defaults_to_main_variant(self) -> None:
        self.assertTrue(all(table.variant == "main" for table in self.tables))
    # end def

    def test_charlotte_has_nine_rows_matching_the_level_ladder(self) -> None:
        charlotte = self.tables[0]
        self.assertEqual(len(charlotte.rows), 9)
        self.assertEqual(charlotte.rows[0].raw_level_label, "Adversary")
        self.assertEqual(charlotte.rows[0].resolved_level, GirlLevel.ADVERSARY)
        self.assertEqual(charlotte.rows[-1].raw_level_label, "Girlfriend")
        self.assertEqual(charlotte.rows[-1].resolved_level, GirlLevel.GIRLFRIEND)
    # end def

    def test_every_row_has_three_requirements(self) -> None:
        for table in self.tables:
            for row in table.rows:
                self.assertEqual(len(row.requirements), 3)
            # end for
        # end for
    # end def

    def test_first_requirement_of_first_row_is_job_level(self) -> None:
        first_requirement = self.tables[0].rows[0].requirements[0]
        self.assertIsInstance(first_requirement, JobLevelRequirement)
        self.assertEqual(first_requirement.job_name, "Cemetary Dredger")
        self.assertEqual(first_requirement.job_track, "Grave Digger")
    # end def
# end class


if __name__ == "__main__":
    unittest.main()
# end if
