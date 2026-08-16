from __future__ import annotations

import subprocess
from pathlib import Path


def git_add(path: Path) -> None:
    subprocess.run(["git", "add", str(path)], check=True)
# end def
