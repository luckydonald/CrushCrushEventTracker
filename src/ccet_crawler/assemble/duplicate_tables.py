from __future__ import annotations

from ccet_crawler.models.event import CharacterRequirementTable


def merge_main_and_alt_tables(
    main_tables: list[CharacterRequirementTable],
    alt_tables: list[CharacterRequirementTable],
) -> list[CharacterRequirementTable]:
    tagged_alt_tables = [table.model_copy(update={"variant": "alt"}) for table in alt_tables]
    return [*main_tables, *tagged_alt_tables]
# end def
