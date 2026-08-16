from __future__ import annotations

from pathlib import Path

from ccet_crawler.models.event import Event
from ccet_crawler.write.slug import slugify


def write_event_json(event: Event, events_dir: Path) -> list[Path]:
    year_dir = events_dir / str(event.year)
    year_dir.mkdir(parents=True, exist_ok=True)

    written_paths: list[Path] = []
    for table in event.character_tables:
        per_character_event = event.model_copy(update={"character_tables": [table]})
        path = year_dir / f"{slugify(event.name)}__{slugify(table.girl_name)}.json"
        path.write_text(per_character_event.model_dump_json(indent=2), encoding="utf-8")
        written_paths.append(path)
    # end for

    return written_paths
# end def
