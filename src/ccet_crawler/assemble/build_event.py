from __future__ import annotations

from ccet_crawler.assemble.duplicate_tables import merge_main_and_alt_tables
from ccet_crawler.assemble.sanity_checks import check_requirement_levels_against_summary
from ccet_crawler.html.girl_table import parse_girl_tables
from ccet_crawler.html.guide_page import EventSections, extract_section_description, group_by_event, split_guide_sections
from ccet_crawler.html.hobby_job_info import parse_hobby_job_info
from ccet_crawler.models.event import Event, EventDescription


def build_event(sections: EventSections) -> Event:
    main_tables = parse_girl_tables(sections.girl_reqs) if sections.girl_reqs is not None else []
    alt_tables = parse_girl_tables(sections.alt_reqs) if sections.alt_reqs is not None else []
    character_tables = merge_main_and_alt_tables(main_tables, alt_tables)

    description_text = extract_section_description(sections.girl_reqs) if sections.girl_reqs is not None else ""
    notes_text = extract_section_description(sections.alt_reqs) if sections.alt_reqs is not None else None

    hobby_job_info = parse_hobby_job_info(sections.hobby_job_info) if sections.hobby_job_info is not None else None
    warnings = (
        check_requirement_levels_against_summary(character_tables, hobby_job_info)
        if hobby_job_info is not None
        else []
    )

    return Event(
        name=sections.event_name,
        year=sections.year,
        main_girl=sections.main_girl,
        description=EventDescription(text=description_text, notes=notes_text or None),
        character_tables=character_tables,
        hobby_job_info=hobby_job_info,
        warnings=warnings,
    )
# end def


def build_events_from_html(html: str) -> list[Event]:
    sections = split_guide_sections(html)
    return [build_event(event_sections) for event_sections in group_by_event(sections)]
# end def
