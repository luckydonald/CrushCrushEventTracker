from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from bs4.element import Tag


class SectionKind(StrEnum):
    GIRL_REQS = "girl_reqs"
    ALT_REQS = "alt_reqs"
    HOBBY_JOB_INFO = "hobby_job_info"
# end class


_SUFFIX_KINDS: dict[str, SectionKind] = {
    " Girl Reqs.": SectionKind.GIRL_REQS,
    " Alt. Reqs.": SectionKind.ALT_REQS,
    " Hobby & Job Info": SectionKind.HOBBY_JOB_INFO,
}

_EVENT_HEADER_PATTERN = re.compile(r"^(?P<name>.+) (?P<year>\d{4}) \((?P<main_girl>.+)\)$")


@dataclass
class ClassifiedSection:
    kind: SectionKind
    event_name: str
    year: int
    main_girl: str
    body: Tag
# end class


def classify_section(title_text: str, body: Tag) -> ClassifiedSection | None:
    for suffix, kind in _SUFFIX_KINDS.items():
        if not title_text.endswith(suffix):
            continue
        # end if
        header = title_text[: -len(suffix)]
        match = _EVENT_HEADER_PATTERN.match(header)
        if match is None:
            return None
        # end if
        return ClassifiedSection(
            kind=kind,
            event_name=match.group("name"),
            year=int(match.group("year")),
            main_girl=match.group("main_girl"),
            body=body,
        )
    # end for
    return None
# end def
