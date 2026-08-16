from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from ccet_crawler.models.hobby_job_summary import HobbyJobInfo
from ccet_crawler.models.levels import GirlLevel
from ccet_crawler.models.requirements import Requirement


class GirlLevelRow(BaseModel):
    raw_level_label: str
    resolved_level: GirlLevel | None
    requirements: list[Requirement]
# end class


class CharacterRequirementTable(BaseModel):
    girl_name: str
    variant: Literal["main", "alt"] = "main"
    rows: list[GirlLevelRow]
# end class


class EventDescription(BaseModel):
    text: str
    notes: str | None = None
# end class


class Event(BaseModel):
    name: str
    year: int
    main_girl: str
    description: EventDescription
    character_tables: list[CharacterRequirementTable]
    hobby_job_info: HobbyJobInfo | None
    warnings: list[str] = []
# end class
