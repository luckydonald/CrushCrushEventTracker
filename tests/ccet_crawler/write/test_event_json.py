from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ccet_crawler.models.event import CharacterRequirementTable, Event, EventDescription, GirlLevelRow
from ccet_crawler.models.requirements import MoneyRequirement
from ccet_crawler.write.event_json import write_event_json


def _event() -> Event:
    return Event(
        name="Spooky Event",
        year=2022,
        main_girl="Cassia",
        description=EventDescription(text=""),
        character_tables=[
            CharacterRequirementTable(
                girl_name="Charlotte",
                rows=[GirlLevelRow(raw_level_label="Adversary", resolved_level=None, requirements=[MoneyRequirement(amount=15)])],
            ),
            CharacterRequirementTable(girl_name="Jelle", rows=[]),
        ],
        hobby_job_info=None,
    )
# end def


class WriteEventJsonTest(unittest.TestCase):
    def test_writes_one_file_per_character_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            events_dir = Path(tmp)
            paths = write_event_json(_event(), events_dir)

            self.assertEqual(len(paths), 2)
            self.assertEqual(
                {path.name for path in paths},
                {"Spooky_Event__Charlotte.json", "Spooky_Event__Jelle.json"},
            )
            for path in paths:
                self.assertEqual(path.parent, events_dir / "2022")
            # end for
        # end with
    # end def

    def test_each_file_scopes_character_tables_to_its_own_girl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = write_event_json(_event(), Path(tmp))
            charlotte_path = next(path for path in paths if "Charlotte" in path.name)
            content = json.loads(charlotte_path.read_text(encoding="utf-8"))

            self.assertEqual(len(content["character_tables"]), 1)
            self.assertEqual(content["character_tables"][0]["girl_name"], "Charlotte")
            self.assertEqual(content["name"], "Spooky Event")
        # end with
    # end def

    def test_json_is_indented_with_two_spaces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = write_event_json(_event(), Path(tmp))
            text = paths[0].read_text(encoding="utf-8")
            self.assertIn('\n  "name"', text)
        # end with
    # end def
# end class


if __name__ == "__main__":
    unittest.main()
# end if
