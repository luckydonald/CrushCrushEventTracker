from __future__ import annotations

import unittest

from ccet_crawler.assemble.sanity_checks import check_requirement_levels_against_summary
from ccet_crawler.models.event import CharacterRequirementTable, GirlLevelRow
from ccet_crawler.models.hobby_job_summary import HobbyJobInfo, HobbySummary, JobLevelGroup, JobSummary
from ccet_crawler.models.requirements import HobbyLevelRequirement, JobLevelRequirement, MoneyRequirement


def _hobby_job_info() -> HobbyJobInfo:
    return HobbyJobInfo(
        hobbies_description=None,
        hobbies=[HobbySummary(max_level=60, hobby_name="Creepy", unlock_character=None)],
        jobs_description=None,
        jobs=JobSummary(groups=[JobLevelGroup(level=5, job_track="Grave Digger", job_names=["a"], highlighted_job_name=None)]),
        pay_details=[],
    )
# end def


class CheckRequirementLevelsAgainstSummaryTest(unittest.TestCase):
    def test_no_warnings_when_within_summary_maxima(self) -> None:
        tables = [
            CharacterRequirementTable(
                girl_name="Charlotte",
                rows=[
                    GirlLevelRow(
                        raw_level_label="Adversary",
                        resolved_level=None,
                        requirements=[
                            HobbyLevelRequirement(level=10, hobby_name="Creepy"),
                            JobLevelRequirement(level=2, job_name="X", job_track="Grave Digger"),
                        ],
                    )
                ],
            )
        ]
        self.assertEqual(check_requirement_levels_against_summary(tables, _hobby_job_info()), [])
    # end def

    def test_warns_when_hobby_level_exceeds_summary_maximum(self) -> None:
        tables = [
            CharacterRequirementTable(
                girl_name="Charlotte",
                rows=[GirlLevelRow(raw_level_label="Girlfriend", resolved_level=None, requirements=[HobbyLevelRequirement(level=99, hobby_name="Creepy")])],
            )
        ]
        warnings = check_requirement_levels_against_summary(tables, _hobby_job_info())
        self.assertEqual(len(warnings), 1)
        self.assertIn("Creepy", warnings[0])
        self.assertIn("99", warnings[0])
    # end def

    def test_warns_when_hobby_missing_from_summary(self) -> None:
        tables = [
            CharacterRequirementTable(
                girl_name="Charlotte",
                rows=[GirlLevelRow(raw_level_label="Adversary", resolved_level=None, requirements=[HobbyLevelRequirement(level=1, hobby_name="Sweet Tooth")])],
            )
        ]
        warnings = check_requirement_levels_against_summary(tables, _hobby_job_info())
        self.assertEqual(len(warnings), 1)
        self.assertIn("Sweet Tooth", warnings[0])
        self.assertIn("not in the Hobby & Job Info summary", warnings[0])
    # end def

    def test_warns_when_job_level_exceeds_summary_maximum(self) -> None:
        tables = [
            CharacterRequirementTable(
                girl_name="Jelle",
                rows=[GirlLevelRow(raw_level_label="Girlfriend", resolved_level=None, requirements=[JobLevelRequirement(level=10, job_name="X", job_track="Grave Digger")])],
            )
        ]
        warnings = check_requirement_levels_against_summary(tables, _hobby_job_info())
        self.assertEqual(len(warnings), 1)
        self.assertIn("Grave Digger", warnings[0])
    # end def

    def test_non_level_requirements_are_ignored(self) -> None:
        tables = [
            CharacterRequirementTable(
                girl_name="Charlotte",
                rows=[GirlLevelRow(raw_level_label="Adversary", resolved_level=None, requirements=[MoneyRequirement(amount=15)])],
            )
        ]
        self.assertEqual(check_requirement_levels_against_summary(tables, _hobby_job_info()), [])
    # end def
# end class


if __name__ == "__main__":
    unittest.main()
# end if
