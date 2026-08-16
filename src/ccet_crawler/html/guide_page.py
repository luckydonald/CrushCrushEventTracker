from __future__ import annotations

from dataclasses import dataclass

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

from ccet_crawler.html.section_classify import ClassifiedSection, SectionKind, classify_section


@dataclass
class EventSections:
    event_name: str
    year: int
    main_girl: str
    girl_reqs: Tag | None = None
    alt_reqs: Tag | None = None
    hobby_job_info: Tag | None = None
# end class


def split_guide_sections(html: str) -> list[ClassifiedSection]:
    soup = BeautifulSoup(html, "html.parser")
    guide = soup.select_one("#profileBlock > .guide")
    if guide is None:
        raise ValueError("Could not find '#profileBlock > .guide' in the given HTML.")
    # end if

    classified: list[ClassifiedSection] = []
    for section in guide.select(".subSection.detailBox"):
        title_el = section.select_one(".subSectionTitle")
        body = section.select_one(".subSectionDesc")
        if title_el is None or body is None:
            continue
        # end if
        result = classify_section(title_el.get_text(strip=True), body)
        if result is not None:
            classified.append(result)
        # end if
    # end for
    return classified
# end def


def group_by_event(sections: list[ClassifiedSection]) -> list[EventSections]:
    grouped: dict[tuple[str, int], EventSections] = {}
    for section in sections:
        key = (section.event_name, section.year)
        if key not in grouped:
            grouped[key] = EventSections(
                event_name=section.event_name, year=section.year, main_girl=section.main_girl
            )
        # end if
        event = grouped[key]
        if section.kind == SectionKind.GIRL_REQS:
            event.girl_reqs = section.body
        elif section.kind == SectionKind.ALT_REQS:
            event.alt_reqs = section.body
        elif section.kind == SectionKind.HOBBY_JOB_INFO:
            event.hobby_job_info = section.body
        # end if
    # end for
    return list(grouped.values())
# end def


def extract_section_description(body: Tag) -> str:
    first_h2 = body.find("div", class_="bb_h2")
    parts: list[str] = []
    for node in body.children:
        if node is first_h2:
            break
        # end if
        if isinstance(node, NavigableString):
            parts.append(str(node))
        # end if
    # end for
    return "".join(parts).strip()
# end def
