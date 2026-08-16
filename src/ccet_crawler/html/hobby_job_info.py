from __future__ import annotations

import re

from bs4.element import NavigableString, Tag

from ccet_crawler.models.hobby_job_summary import HobbyJobInfo, HobbySummary, JobLevelGroup, JobSummary, PayDetail

_HOBBY_LI_PATTERN = re.compile(r"^(?P<level>\d+) (?P<hobby_name>.+?)(?: - expected unlock (?P<unlock_character>.+))?$")
_JOB_LI_HEADER_PATTERN = re.compile(r"^Lv (?P<level>\d+) (?P<job_track>.+?):\s*(?P<rest>.*)$", re.DOTALL)
_PAY_LINE_PATTERN = re.compile(r"^(?P<job_track>.+): \$(?P<per_second>[\d,]+)/s \(\$(?P<per_block>[\d,]+)/time block/s\)$")


def _parse_int(text: str) -> int:
    return int(text.replace(",", ""))
# end def


def _find_heading(body: Tag, class_name: str, text: str) -> Tag | None:
    for candidate in body.find_all("div", class_=class_name):
        if candidate.get_text(strip=True) == text:
            return candidate
        # end if
    # end for
    return None
# end def


def _find_pay_heading(body: Tag) -> Tag | None:
    for candidate in body.find_all("div", class_="bb_h3"):
        if candidate.get_text(strip=True).startswith("Pay details"):
            return candidate
        # end if
    # end for
    return None
# end def


def _text_between(start: Tag, end: Tag | None) -> str | None:
    parts: list[str] = []
    for sibling in start.next_siblings:
        if sibling is end:
            break
        # end if
        if isinstance(sibling, NavigableString):
            parts.append(str(sibling))
        # end if
    # end for
    text = "".join(parts).strip()
    return text or None
# end def


def _parse_hobbies_list(ul: Tag) -> list[HobbySummary]:
    hobbies: list[HobbySummary] = []
    for li in ul.find_all("li", recursive=False):
        match = _HOBBY_LI_PATTERN.match(li.get_text(strip=True))
        if match is None:
            continue
        # end if
        hobbies.append(
            HobbySummary(
                max_level=_parse_int(match.group("level")),
                hobby_name=match.group("hobby_name"),
                unlock_character=match.group("unlock_character"),
            )
        )
    # end for
    return hobbies
# end def


def _parse_job_li(li: Tag) -> JobLevelGroup | None:
    highlighted_job_name: str | None = None
    pieces: list[str] = []
    for node in li.children:
        if isinstance(node, Tag) and node.name == "b":
            name = node.get_text(strip=True)
            highlighted_job_name = name
            pieces.append(name)
        elif isinstance(node, NavigableString):
            pieces.append(str(node))
        # end if
    # end for

    header_match = _JOB_LI_HEADER_PATTERN.match("".join(pieces))
    if header_match is None:
        return None
    # end if

    job_names = [name.strip() for name in header_match.group("rest").split(",")]
    job_names = [name for name in job_names if name]

    return JobLevelGroup(
        level=_parse_int(header_match.group("level")),
        job_track=header_match.group("job_track"),
        job_names=job_names,
        highlighted_job_name=highlighted_job_name,
    )
# end def


def _parse_jobs_list(ul: Tag) -> JobSummary:
    groups = [group for li in ul.find_all("li", recursive=False) if (group := _parse_job_li(li)) is not None]
    return JobSummary(groups=groups)
# end def


def _parse_pay_details(pay_h3: Tag) -> list[PayDetail]:
    lines: list[str] = []
    current: list[str] = []
    for sibling in pay_h3.next_siblings:
        if isinstance(sibling, Tag) and sibling.name == "br":
            lines.append("".join(current).strip())
            current = []
            continue
        # end if
        if isinstance(sibling, Tag) and sibling.get("style") == "clear: both":
            break
        # end if
        if isinstance(sibling, NavigableString):
            current.append(str(sibling))
        # end if
    # end for
    if current:
        lines.append("".join(current).strip())
    # end if

    pay_details: list[PayDetail] = []
    for line in lines:
        match = _PAY_LINE_PATTERN.match(line)
        if match is None:
            continue
        # end if
        pay_details.append(
            PayDetail(
                job_track=match.group("job_track"),
                money_per_second=_parse_int(match.group("per_second")),
                money_per_time_block_per_second=_parse_int(match.group("per_block")),
            )
        )
    # end for
    return pay_details
# end def


def parse_hobby_job_info(body: Tag) -> HobbyJobInfo:
    hobbies_h2 = _find_heading(body, "bb_h2", "Hobbies")
    jobs_h2 = _find_heading(body, "bb_h2", "Jobs")
    pay_h3 = _find_pay_heading(body)

    hobbies_ul = hobbies_h2.find_next_sibling("ul", class_="bb_ul") if hobbies_h2 is not None else None
    jobs_ul = jobs_h2.find_next_sibling("ul", class_="bb_ul") if jobs_h2 is not None else None

    return HobbyJobInfo(
        hobbies_description=_text_between(hobbies_h2, hobbies_ul) if hobbies_h2 is not None else None,
        hobbies=_parse_hobbies_list(hobbies_ul) if hobbies_ul is not None else [],
        jobs_description=_text_between(jobs_h2, jobs_ul) if jobs_h2 is not None else None,
        jobs=_parse_jobs_list(jobs_ul) if jobs_ul is not None else JobSummary(groups=[]),
        pay_details=_parse_pay_details(pay_h3) if pay_h3 is not None else [],
    )
# end def
