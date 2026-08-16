from __future__ import annotations

import unittest

from ccet_crawler.html.requirement_cell import parse_requirement_cell
from ccet_crawler.models.requirements import (
    AllHobbiesLevelRequirement,
    DateActivityRequirement,
    GildHobbiesRequirement,
    GildJobsRequirement,
    GirlsAtLevelRequirement,
    HobbyLevelRequirement,
    JobLevelRequirement,
    MoneyRequirement,
    PurchaseRequirement,
    WorkAtJobRequirement,
)


class SpecExampleTest(unittest.TestCase):
    """Every literal example string given in ai/plans/init.md."""

    def test_job_level(self) -> None:
        result = parse_requirement_cell("Lv 2 IT Monkey (Computers)")
        self.assertEqual(
            result, JobLevelRequirement(level=2, job_name="IT Monkey", job_track="Computers")
        )
    # end def

    def test_work_at_job(self) -> None:
        result = parse_requirement_cell("Work at Tour Guide")
        self.assertEqual(result, WorkAtJobRequirement(job_track="Tour Guide"))
    # end def

    def test_hobby_level(self) -> None:
        result = parse_requirement_cell("1 Analytical")
        self.assertEqual(result, HobbyLevelRequirement(level=1, hobby_name="Analytical"))
    # end def

    def test_purchase(self) -> None:
        result = parse_requirement_cell("242,424 Greatsword ($12,121,200)")
        self.assertEqual(
            result, PurchaseRequirement(amount=242_424, item_name="Greatsword", total_price=12_121_200)
        )
    # end def

    def test_date_activity(self) -> None:
        result = parse_requirement_cell("12 Moonlight Stroll")
        self.assertEqual(
            result, DateActivityRequirement(count=12, activity_name="Moonlight Stroll", price_per_date=500)
        )
    # end def

    def test_girls_at_level(self) -> None:
        result = parse_requirement_cell("2 Girls at Lover")
        self.assertEqual(result, GirlsAtLevelRequirement(count=2, level_label="Lover"))
    # end def

    def test_gild_jobs(self) -> None:
        result = parse_requirement_cell("Gild any 1 Jobs")
        self.assertEqual(result, GildJobsRequirement(count=1))
    # end def

    def test_gild_hobbies(self) -> None:
        result = parse_requirement_cell("Gild any 3 Hobbies")
        self.assertEqual(result, GildHobbiesRequirement(count=3))
    # end def
# end class


class RealDataPatternTest(unittest.TestCase):
    """Patterns confirmed against the actual fetched guide page (data/crawl/guide/raw.html)."""

    def test_bare_money(self) -> None:
        result = parse_requirement_cell("$15")
        self.assertEqual(result, MoneyRequirement(amount=15))
    # end def

    def test_bare_money_with_billion_magnitude(self) -> None:
        result = parse_requirement_cell("$2 Billion")
        self.assertEqual(result, MoneyRequirement(amount=2_000_000_000))
    # end def

    def test_purchase_with_decimal_billion_price(self) -> None:
        result = parse_requirement_cell("70,000 Mummified Hand ($2.19 Billion)")
        self.assertEqual(
            result,
            PurchaseRequirement(amount=70_000, item_name="Mummified Hand", total_price=2_190_000_000),
        )
    # end def

    def test_purchase_with_trillion_price(self) -> None:
        result = parse_requirement_cell("2,867 Tulips ($1.08 Trillion)")
        self.assertEqual(
            result,
            PurchaseRequirement(amount=2_867, item_name="Tulips", total_price=1_080_000_000_000),
        )
    # end def

    def test_date_activity_with_comma_count(self) -> None:
        result = parse_requirement_cell("1,000 Movie Theater")
        self.assertEqual(
            result, DateActivityRequirement(count=1_000, activity_name="Movie Theater", price_per_date=25_000)
        )
    # end def

    def test_all_hobbies_level(self) -> None:
        result = parse_requirement_cell("All Hobbies level 47")
        self.assertEqual(result, AllHobbiesLevelRequirement(level=47))
    # end def

    def test_job_level_with_multiword_job_name(self) -> None:
        result = parse_requirement_cell("Lv 5 Ghost Tour Guide (Paranormal Investigator)")
        self.assertEqual(
            result,
            JobLevelRequirement(level=5, job_name="Ghost Tour Guide", job_track="Paranormal Investigator"),
        )
    # end def

    def test_unrecognized_text_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_requirement_cell("Something entirely unexpected")
        # end with
    # end def
# end class


if __name__ == "__main__":
    unittest.main()
# end if
