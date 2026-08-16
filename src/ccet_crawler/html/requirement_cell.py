from __future__ import annotations

import re

from ccet_crawler.config import DATE_ACTIVITY_PRICES
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
    Requirement,
    WorkAtJobRequirement,
)

_MONEY_MAGNITUDES = {"Billion": 1_000_000_000, "Trillion": 1_000_000_000_000}
_MONEY_AMOUNT_PATTERN = r"[\d,]+(?:\.\d+)?(?: (?:Billion|Trillion))?"

_WORK_AT_JOB_PATTERN = re.compile(r"^Work at (?P<job_track>.+)$")
_JOB_LEVEL_PATTERN = re.compile(r"^Lv (?P<level>\d+) (?P<job_name>.+) \((?P<job_track>.+)\)$")
_GILD_JOBS_PATTERN = re.compile(r"^Gild any (?P<count>\d+) Jobs$")
_GILD_HOBBIES_PATTERN = re.compile(r"^Gild any (?P<count>\d+) Hobbies$")
_ALL_HOBBIES_LEVEL_PATTERN = re.compile(r"^All Hobbies level (?P<level>\d+)$")
_GIRLS_AT_LEVEL_PATTERN = re.compile(r"^(?P<count>[\d,]+) Girls at (?P<level_label>.+)$")
_DATE_ACTIVITY_PATTERN = re.compile(
    r"^(?P<count>[\d,]+) (?P<activity_name>" + "|".join(re.escape(name) for name in DATE_ACTIVITY_PRICES) + r")$"
)
_PURCHASE_PATTERN = re.compile(
    r"^(?P<amount>[\d,]+) (?P<item_name>.+) \(\$(?P<total_price>" + _MONEY_AMOUNT_PATTERN + r")\)$"
)
_MONEY_PATTERN = re.compile(r"^\$(?P<amount>" + _MONEY_AMOUNT_PATTERN + r")$")
_HOBBY_LEVEL_PATTERN = re.compile(r"^(?P<level>\d+) (?P<hobby_name>.+)$")


def _parse_int(text: str) -> int:
    return int(text.replace(",", ""))
# end def


def _parse_money(text: str) -> int:
    for magnitude_name, multiplier in _MONEY_MAGNITUDES.items():
        suffix = f" {magnitude_name}"
        if text.endswith(suffix):
            number = float(text[: -len(suffix)].replace(",", ""))
            return round(number * multiplier)
        # end if
    # end for
    return _parse_int(text)
# end def


def parse_requirement_cell(text: str) -> Requirement:
    text = text.strip()

    match = _WORK_AT_JOB_PATTERN.match(text)
    if match is not None:
        return WorkAtJobRequirement(job_track=match.group("job_track"))
    # end if

    match = _JOB_LEVEL_PATTERN.match(text)
    if match is not None:
        return JobLevelRequirement(
            level=_parse_int(match.group("level")),
            job_name=match.group("job_name"),
            job_track=match.group("job_track"),
        )
    # end if

    match = _GILD_JOBS_PATTERN.match(text)
    if match is not None:
        return GildJobsRequirement(count=_parse_int(match.group("count")))
    # end if

    match = _GILD_HOBBIES_PATTERN.match(text)
    if match is not None:
        return GildHobbiesRequirement(count=_parse_int(match.group("count")))
    # end if

    match = _ALL_HOBBIES_LEVEL_PATTERN.match(text)
    if match is not None:
        return AllHobbiesLevelRequirement(level=_parse_int(match.group("level")))
    # end if

    match = _GIRLS_AT_LEVEL_PATTERN.match(text)
    if match is not None:
        return GirlsAtLevelRequirement(
            count=_parse_int(match.group("count")),
            level_label=match.group("level_label"),
        )
    # end if

    match = _DATE_ACTIVITY_PATTERN.match(text)
    if match is not None:
        activity_name = match.group("activity_name")
        return DateActivityRequirement(
            count=_parse_int(match.group("count")),
            activity_name=activity_name,
            price_per_date=DATE_ACTIVITY_PRICES[activity_name],
        )
    # end if

    match = _PURCHASE_PATTERN.match(text)
    if match is not None:
        return PurchaseRequirement(
            amount=_parse_int(match.group("amount")),
            item_name=match.group("item_name"),
            total_price=_parse_money(match.group("total_price")),
        )
    # end if

    match = _MONEY_PATTERN.match(text)
    if match is not None:
        return MoneyRequirement(amount=_parse_money(match.group("amount")))
    # end if

    match = _HOBBY_LEVEL_PATTERN.match(text)
    if match is not None:
        return HobbyLevelRequirement(
            level=_parse_int(match.group("level")),
            hobby_name=match.group("hobby_name"),
        )
    # end if

    raise ValueError(f"Unrecognized requirement cell text: {text!r}")
# end def
