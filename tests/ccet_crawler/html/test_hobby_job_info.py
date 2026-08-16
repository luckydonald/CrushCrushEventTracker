from __future__ import annotations

import unittest
from pathlib import Path

from ccet_crawler.html.guide_page import group_by_event, split_guide_sections
from ccet_crawler.html.hobby_job_info import parse_hobby_job_info

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


class ParseHobbyJobInfoTest(unittest.TestCase):
    def setUp(self) -> None:
        html = (FIXTURES_DIR / "guide_page_sample.html").read_text(encoding="utf-8")
        events = group_by_event(split_guide_sections(html))
        self.info = parse_hobby_job_info(events[0].hobby_job_info)
    # end def

    def test_hobbies_description_captured(self) -> None:
        self.assertEqual(
            self.info.hobbies_description,
            "Expected unlocks are estimates; you may unlock some hobbies from other girls.",
        )
    # end def

    def test_twelve_hobbies_parsed_with_unlock_character(self) -> None:
        self.assertEqual(len(self.info.hobbies), 12)
        first = self.info.hobbies[0]
        self.assertEqual((first.max_level, first.hobby_name, first.unlock_character), (61, "Creepy", "Charlotte Adversary"))
    # end def

    def test_jobs_description_captured(self) -> None:
        self.assertEqual(self.info.jobs_description, "Bold text indicates highest rank required.")
    # end def

    def test_ten_job_groups_parsed(self) -> None:
        self.assertEqual(len(self.info.jobs.groups), 10)
    # end def

    def test_job_group_captures_names_and_the_bolded_highlight_even_mid_list(self) -> None:
        exorcist = next(group for group in self.info.jobs.groups if group.job_track == "Exorcist")
        self.assertEqual(exorcist.level, 4)
        self.assertEqual(exorcist.highlighted_job_name, "Banshee Shusher")
        self.assertIn("Banshee Shusher", exorcist.job_names)
        self.assertIn("Who You Gonna Call", exorcist.job_names)
        self.assertEqual(len(exorcist.job_names), 10)
    # end def

    def test_ten_pay_details_parsed(self) -> None:
        self.assertEqual(len(self.info.pay_details), 10)
        wizard = next(pay for pay in self.info.pay_details if pay.job_track == "Wizard")
        self.assertEqual((wizard.money_per_second, wizard.money_per_time_block_per_second), (2_016_492, 201_649))
    # end def
# end class


if __name__ == "__main__":
    unittest.main()
# end if
