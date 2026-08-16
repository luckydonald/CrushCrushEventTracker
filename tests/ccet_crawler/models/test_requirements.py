from __future__ import annotations

import unittest

from pydantic import TypeAdapter

from ccet_crawler.models.requirements import (
    DateActivityRequirement,
    GildHobbiesRequirement,
    GildJobsRequirement,
    GirlsAtLevelRequirement,
    HobbyLevelRequirement,
    JobLevelRequirement,
    MoneyRequirement,
    PurchaseRequirement,
    Requirement,
    RequirementKind,
    WorkAtJobRequirement,
)

REQUIREMENT_ADAPTER: TypeAdapter[Requirement] = TypeAdapter(Requirement)


class RequirementDiscriminationTest(unittest.TestCase):
    def test_job_level_discriminates(self) -> None:
        parsed = REQUIREMENT_ADAPTER.validate_python(
            {"kind": "job_level", "level": 2, "job_name": "IT Monkey", "job_track": "Computers"}
        )
        self.assertIsInstance(parsed, JobLevelRequirement)
        self.assertEqual(parsed.kind, RequirementKind.JOB_LEVEL)
    # end def

    def test_work_at_job_discriminates(self) -> None:
        parsed = REQUIREMENT_ADAPTER.validate_python({"kind": "work_at_job", "job_track": "Tour Guide"})
        self.assertIsInstance(parsed, WorkAtJobRequirement)
    # end def

    def test_hobby_level_discriminates(self) -> None:
        parsed = REQUIREMENT_ADAPTER.validate_python({"kind": "hobby_level", "level": 1, "hobby_name": "Analytical"})
        self.assertIsInstance(parsed, HobbyLevelRequirement)
    # end def

    def test_purchase_discriminates(self) -> None:
        parsed = REQUIREMENT_ADAPTER.validate_python(
            {"kind": "purchase", "amount": 242_424, "item_name": "Greatsword", "total_price": 12_121_200}
        )
        self.assertIsInstance(parsed, PurchaseRequirement)
    # end def

    def test_money_discriminates(self) -> None:
        parsed = REQUIREMENT_ADAPTER.validate_python({"kind": "money", "amount": 15})
        self.assertIsInstance(parsed, MoneyRequirement)
        self.assertEqual(parsed.amount, 15)
    # end def

    def test_date_activity_discriminates(self) -> None:
        parsed = REQUIREMENT_ADAPTER.validate_python(
            {"kind": "date_activity", "count": 12, "activity_name": "Moonlight Stroll", "price_per_date": 500}
        )
        self.assertIsInstance(parsed, DateActivityRequirement)
    # end def

    def test_girls_at_level_discriminates(self) -> None:
        parsed = REQUIREMENT_ADAPTER.validate_python({"kind": "girls_at_level", "count": 2, "level_label": "Lover"})
        self.assertIsInstance(parsed, GirlsAtLevelRequirement)
    # end def

    def test_gild_jobs_discriminates(self) -> None:
        parsed = REQUIREMENT_ADAPTER.validate_python({"kind": "gild_jobs", "count": 1})
        self.assertIsInstance(parsed, GildJobsRequirement)
    # end def

    def test_gild_hobbies_discriminates(self) -> None:
        parsed = REQUIREMENT_ADAPTER.validate_python({"kind": "gild_hobbies", "count": 3})
        self.assertIsInstance(parsed, GildHobbiesRequirement)
    # end def
# end class


if __name__ == "__main__":
    unittest.main()
# end if
