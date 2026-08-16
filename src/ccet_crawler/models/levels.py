from __future__ import annotations

from enum import StrEnum


class GirlLevel(StrEnum):
    ADVERSARY = "Adversary"
    NUISANCE = "Nuisance"
    FRENEMY = "Frenemy"
    ACQUAINTANCE = "Acquaintance"
    FRIENDZONED = "Friendzoned"
    AWKWARD_BESTIES = "Awkward Besties"
    CRUSH = "Crush"
    SWEETHEART = "Sweetheart"
    GIRLFRIEND = "Girlfriend"
# end class


GIRL_LEVEL_ORDER: list[GirlLevel] = list(GirlLevel)


def resolve_girl_level(raw_label: str, row_index: int) -> GirlLevel | None:
    for level in GirlLevel:
        if level.value == raw_label:
            return level
        # end if
    # end for
    if 0 <= row_index < len(GIRL_LEVEL_ORDER):
        return GIRL_LEVEL_ORDER[row_index]
    # end if
    return None
# end def
