from __future__ import annotations

from ccet_crawler.models.event import CharacterRequirementTable
from ccet_crawler.models.hobby_job_summary import HobbyJobInfo
from ccet_crawler.models.requirements import HobbyLevelRequirement, JobLevelRequirement


def check_requirement_levels_against_summary(
    character_tables: list[CharacterRequirementTable],
    hobby_job_info: HobbyJobInfo,
) -> list[str]:
    warnings: list[str] = []

    max_hobby_levels = {hobby.hobby_name: hobby.max_level for hobby in hobby_job_info.hobbies}
    max_job_levels: dict[str, int] = {}
    for group in hobby_job_info.jobs.groups:
        max_job_levels[group.job_track] = max(max_job_levels.get(group.job_track, 0), group.level)
    # end for

    for table in character_tables:
        for row in table.rows:
            for requirement in row.requirements:
                if isinstance(requirement, HobbyLevelRequirement):
                    warnings.extend(_check_hobby_level(table, requirement, max_hobby_levels))
                elif isinstance(requirement, JobLevelRequirement):
                    warnings.extend(_check_job_level(table, requirement, max_job_levels))
                # end if
            # end for
        # end for
    # end for

    return warnings
# end def


def _check_hobby_level(
    table: CharacterRequirementTable, requirement: HobbyLevelRequirement, max_hobby_levels: dict[str, int]
) -> list[str]:
    max_level = max_hobby_levels.get(requirement.hobby_name)
    if max_level is None:
        return [
            f"{table.girl_name} ({table.variant}) requires hobby '{requirement.hobby_name}' "
            f"which is not in the Hobby & Job Info summary."
        ]
    # end if
    if requirement.level > max_level:
        return [
            f"{table.girl_name} ({table.variant}) requires hobby '{requirement.hobby_name}' "
            f"at level {requirement.level}, exceeding the summary max of {max_level}."
        ]
    # end if
    return []
# end def


def _check_job_level(
    table: CharacterRequirementTable, requirement: JobLevelRequirement, max_job_levels: dict[str, int]
) -> list[str]:
    max_level = max_job_levels.get(requirement.job_track)
    if max_level is None:
        return [
            f"{table.girl_name} ({table.variant}) requires job track '{requirement.job_track}' "
            f"which is not in the Hobby & Job Info summary."
        ]
    # end if
    if requirement.level > max_level:
        return [
            f"{table.girl_name} ({table.variant}) requires job '{requirement.job_name}' "
            f"(Lv {requirement.level}) in '{requirement.job_track}', exceeding the summary max of {max_level}."
        ]
    # end if
    return []
# end def
