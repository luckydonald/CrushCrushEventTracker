from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class RequirementKind(StrEnum):
    JOB_LEVEL = "job_level"
    WORK_AT_JOB = "work_at_job"
    HOBBY_LEVEL = "hobby_level"
    PURCHASE = "purchase"
    MONEY = "money"
    DATE_ACTIVITY = "date_activity"
    GIRLS_AT_LEVEL = "girls_at_level"
    GILD_JOBS = "gild_jobs"
    GILD_HOBBIES = "gild_hobbies"
    ALL_HOBBIES_LEVEL = "all_hobbies_level"
# end class


class JobLevelRequirement(BaseModel):
    kind: Literal[RequirementKind.JOB_LEVEL] = RequirementKind.JOB_LEVEL
    level: int
    job_name: str
    job_track: str
# end class


class WorkAtJobRequirement(BaseModel):
    kind: Literal[RequirementKind.WORK_AT_JOB] = RequirementKind.WORK_AT_JOB
    job_track: str
# end class


class HobbyLevelRequirement(BaseModel):
    kind: Literal[RequirementKind.HOBBY_LEVEL] = RequirementKind.HOBBY_LEVEL
    level: int
    hobby_name: str
# end class


class PurchaseRequirement(BaseModel):
    kind: Literal[RequirementKind.PURCHASE] = RequirementKind.PURCHASE
    amount: int
    item_name: str
    total_price: int
# end class


class MoneyRequirement(BaseModel):
    kind: Literal[RequirementKind.MONEY] = RequirementKind.MONEY
    amount: int
# end class


class DateActivityRequirement(BaseModel):
    kind: Literal[RequirementKind.DATE_ACTIVITY] = RequirementKind.DATE_ACTIVITY
    count: int
    activity_name: str
    price_per_date: int
# end class


class GirlsAtLevelRequirement(BaseModel):
    kind: Literal[RequirementKind.GIRLS_AT_LEVEL] = RequirementKind.GIRLS_AT_LEVEL
    count: int
    level_label: str
# end class


class GildJobsRequirement(BaseModel):
    kind: Literal[RequirementKind.GILD_JOBS] = RequirementKind.GILD_JOBS
    count: int
# end class


class GildHobbiesRequirement(BaseModel):
    kind: Literal[RequirementKind.GILD_HOBBIES] = RequirementKind.GILD_HOBBIES
    count: int
# end class


class AllHobbiesLevelRequirement(BaseModel):
    kind: Literal[RequirementKind.ALL_HOBBIES_LEVEL] = RequirementKind.ALL_HOBBIES_LEVEL
    level: int
# end class


Requirement = Annotated[
    Union[
        JobLevelRequirement,
        WorkAtJobRequirement,
        HobbyLevelRequirement,
        PurchaseRequirement,
        MoneyRequirement,
        DateActivityRequirement,
        GirlsAtLevelRequirement,
        GildJobsRequirement,
        GildHobbiesRequirement,
        AllHobbiesLevelRequirement,
    ],
    Field(discriminator="kind"),
]
