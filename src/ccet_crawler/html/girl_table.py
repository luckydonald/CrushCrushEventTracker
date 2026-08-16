from __future__ import annotations

from bs4.element import Tag

from ccet_crawler.html.requirement_cell import parse_requirement_cell
from ccet_crawler.models.event import CharacterRequirementTable, GirlLevelRow
from ccet_crawler.models.levels import resolve_girl_level


def parse_girl_tables(body: Tag) -> list[CharacterRequirementTable]:
    tables: list[CharacterRequirementTable] = []
    girl_name: str | None = None

    for child in body.children:
        if not isinstance(child, Tag):
            continue
        # end if
        classes = child.get("class") or []
        if "bb_h2" in classes:
            girl_name = child.get_text(strip=True)
        elif "bb_table" in classes and girl_name is not None:
            tables.append(CharacterRequirementTable(girl_name=girl_name, rows=_parse_table(child)))
            girl_name = None
        # end if
    # end for

    return tables
# end def


def _parse_table(table: Tag) -> list[GirlLevelRow]:
    rows: list[GirlLevelRow] = []
    for index, tr in enumerate(table.select(".bb_table_tr")):
        cells = tr.select(".bb_table_td")
        if not cells:
            continue
        # end if
        raw_label = cells[0].get_text(strip=True)
        requirements = [parse_requirement_cell(cell.get_text(strip=True)) for cell in cells[1:]]
        rows.append(
            GirlLevelRow(
                raw_level_label=raw_label,
                resolved_level=resolve_girl_level(raw_label, index),
                requirements=requirements,
            )
        )
    # end for
    return rows
# end def
