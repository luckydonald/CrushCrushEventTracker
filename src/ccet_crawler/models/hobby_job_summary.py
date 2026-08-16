from __future__ import annotations

from pydantic import BaseModel


class HobbySummary(BaseModel):
    max_level: int
    hobby_name: str
    unlock_character: str | None
    gild_required_count: int | None = None
# end class


class JobLevelGroup(BaseModel):
    level: int
    job_track: str
    job_names: list[str]
    highlighted_job_name: str | None
# end class


class JobSummary(BaseModel):
    groups: list[JobLevelGroup]
    gild_required_count: int | None = None
# end class


class PayDetail(BaseModel):
    job_track: str
    money_per_second: int
    money_per_time_block_per_second: int

    def time_blocks_needed(self, target_money_per_second: int) -> int:
        if self.money_per_time_block_per_second <= 0:
            return 0
        # end if
        full_blocks, remainder = divmod(target_money_per_second, self.money_per_time_block_per_second)
        return full_blocks + (1 if remainder else 0)
    # end def
# end class


class HobbyJobInfo(BaseModel):
    hobbies_description: str | None
    hobbies: list[HobbySummary]
    jobs_description: str | None
    jobs: JobSummary
    pay_details: list[PayDetail]
# end class
