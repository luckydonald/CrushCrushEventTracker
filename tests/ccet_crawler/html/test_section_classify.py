from __future__ import annotations

import unittest

from bs4 import BeautifulSoup

from ccet_crawler.html.section_classify import SectionKind, classify_section

_EMPTY_BODY = BeautifulSoup("<div></div>", "html.parser").div


class ClassifySectionTest(unittest.TestCase):
    def test_girl_reqs_suffix(self) -> None:
        result = classify_section("Spooky Event 2022 (Cassia) Girl Reqs.", _EMPTY_BODY)
        assert result is not None
        self.assertEqual(result.kind, SectionKind.GIRL_REQS)
        self.assertEqual(result.event_name, "Spooky Event")
        self.assertEqual(result.year, 2022)
        self.assertEqual(result.main_girl, "Cassia")
    # end def

    def test_alt_reqs_suffix(self) -> None:
        result = classify_section("Outer Space Event 2025 (Loola) Alt. Reqs.", _EMPTY_BODY)
        assert result is not None
        self.assertEqual(result.kind, SectionKind.ALT_REQS)
        self.assertEqual(result.event_name, "Outer Space Event")
        self.assertEqual(result.main_girl, "Loola")
    # end def

    def test_hobby_job_info_suffix(self) -> None:
        result = classify_section("Spooky Event 2022 (Cassia) Hobby & Job Info", _EMPTY_BODY)
        assert result is not None
        self.assertEqual(result.kind, SectionKind.HOBBY_JOB_INFO)
    # end def

    def test_main_girl_with_ampersand(self) -> None:
        result = classify_section("Fuzzy Festival 2025 (Ginger & Wasabi) Girl Reqs.", _EMPTY_BODY)
        assert result is not None
        self.assertEqual(result.event_name, "Fuzzy Festival")
        self.assertEqual(result.main_girl, "Ginger & Wasabi")
    # end def

    def test_main_girl_with_apostrophe_event_name(self) -> None:
        result = classify_section("Valentine's Event 2026 (Sugar) Girl Reqs.", _EMPTY_BODY)
        assert result is not None
        self.assertEqual(result.event_name, "Valentine's Event")
        self.assertEqual(result.main_girl, "Sugar")
    # end def

    def test_unrelated_faq_heading_returns_none(self) -> None:
        self.assertIsNone(classify_section("Basic information", _EMPTY_BODY))
        self.assertIsNone(classify_section("Summarized completion reqs. (2022-2023)", _EMPTY_BODY))
    # end def
# end class


if __name__ == "__main__":
    unittest.main()
# end if
