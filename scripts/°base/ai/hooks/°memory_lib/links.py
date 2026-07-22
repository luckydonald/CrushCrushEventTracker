"""Safe per-file synchronization for durable memory mirrors."""
from __future__ import annotations

import os
from pathlib import Path


def same_inode(first: Path, second: Path) -> bool:
    """Whether two existing paths already share one filesystem object."""
    try:
        return (
            first.stat().st_ino == second.stat().st_ino
            and first.stat().st_dev == second.stat().st_dev
        )
    except OSError:
        return False
    # end try
# end def


def link_file(source: Path, destination: Path) -> bool:
    """Make ``destination`` a hardlink to ``source``, or a symlink fallback.

    Returns whether the destination changed. The caller chooses the direction,
    which keeps conflict policy outside this small filesystem primitive.
    """
    if not source.is_file():
        return False
    # end if
    if destination.is_symlink():
        try:
            if destination.resolve() == source.resolve():
                return False
            # end if
        except OSError:
            pass
        # end try
    elif destination.exists() and same_inode(destination, source):
        return False
    # end if

    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink() or destination.exists():
        destination.unlink()
    # end if
    try:
        os.link(source, destination)
    except OSError:
        destination.symlink_to(source)
    # end try
    return True
# end def
