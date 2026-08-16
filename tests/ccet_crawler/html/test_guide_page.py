from __future__ import annotations

import unittest
from pathlib import Path

from ccet_crawler.html.guide_page import group_by_event, split_guide_sections
from ccet_crawler.html.section_classify import SectionKind

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


class SplitGuideSectionsTest(unittest.TestCase):
    def test_cassia_fixture_has_two_sections(self) -> None:
        html = (FIXTURES_DIR / "guide_page_sample.html").read_text(encoding="utf-8")
        sections = split_guide_sections(html)
        kinds = [section.kind for section in sections]
        self.assertEqual(kinds, [SectionKind.GIRL_REQS, SectionKind.HOBBY_JOB_INFO])
        self.assertTrue(all(section.event_name == "Spooky Event" for section in sections))
        self.assertTrue(all(section.year == 2022 for section in sections))
        self.assertTrue(all(section.main_girl == "Cassia" for section in sections))
    # end def

    def test_missing_guide_root_raises(self) -> None:
        with self.assertRaises(ValueError):
            split_guide_sections("<div>no guide here</div>")
        # end with
    # end def
# end class


class GroupByEventTest(unittest.TestCase):
    def test_cassia_fixture_groups_into_one_event(self) -> None:
        html = (FIXTURES_DIR / "guide_page_sample.html").read_text(encoding="utf-8")
        events = group_by_event(split_guide_sections(html))
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual((event.event_name, event.year, event.main_girl), ("Spooky Event", 2022, "Cassia"))
        self.assertIsNotNone(event.girl_reqs)
        self.assertIsNotNone(event.hobby_job_info)
        self.assertIsNone(event.alt_reqs)
    # end def

    def test_loola_fixture_has_both_girl_reqs_and_alt_reqs(self) -> None:
        html = (FIXTURES_DIR / "guide_page_sample_alt_reqs.html").read_text(encoding="utf-8")
        events = group_by_event(split_guide_sections(html))
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertIsNotNone(event.girl_reqs)
        self.assertIsNotNone(event.alt_reqs)
        self.assertIsNotNone(event.hobby_job_info)
    # end def
# end class


if __name__ == "__main__":
    unittest.main()
# end if
