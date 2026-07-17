#!/usr/bin/env python3
"""PreCompact hook: save the user's manual `/compact <custom prompt>` argument.

Usage: hook.py [ai_tool_name]
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _lib import (  # noqa: E402
    append_and_commit,
    base_ai_commit_subject,
    dump_debug_payload,
    is_cross_tool_duplicate,
    read_payload,
    resolve_log_path,
)

# Field name unconfirmed against first-party docs; check all plausible spellings.
_INSTRUCTION_KEYS = ("custom_instructions", "custom_instruction", "customInstructions", "instructions")


def _custom_instructions(payload: dict) -> str:
    for key in _INSTRUCTION_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _next_compacted_number(compacted_dir: Path) -> int:
    if not compacted_dir.exists():
        return 1
    nums = [
        int(m.group(1))
        for f in compacted_dir.glob("*.md")
        if (m := re.fullmatch(r"(\d+)\.md", f.name))
    ]
    return max(nums, default=0) + 1


def main() -> int:
    ai_tool = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    payload = read_payload()
    if is_cross_tool_duplicate(ai_tool):
        return 0
    dump_debug_payload(payload, "save-compact-prompt")

    if payload.get("trigger") != "manual":
        return 0
    text = _custom_instructions(payload)
    if not text:
        return 0

    log_path = resolve_log_path("ai/query.md", "ai/°base/query.md")
    compacted_dir = log_path.parent / "output" / "compacted"
    num = _next_compacted_number(compacted_dir)
    dir_name = f"{num:03d}"
    compacted_dir.mkdir(parents=True, exist_ok=True)
    compacted_file = compacted_dir / f"{dir_name}.md"
    compacted_file.write_text(text, encoding="utf-8")

    cwd = Path.cwd()
    compacted_rel = str(compacted_file.relative_to(cwd))
    subprocess.run(["git", "add", "--", compacted_rel], capture_output=True)
    subprocess.run(
        ["git", "commit", "--no-verify", "--only", compacted_rel,
         "-m", base_ai_commit_subject(f"ai: compact {dir_name} prompt")],
        capture_output=True,
    )

    rel_compacted = f"output/compacted/{dir_name}.md"
    content = f"- [`/compact` possible prompt](./{rel_compacted})\n"
    append_and_commit(
        log_path,
        content,
        commit_template_relpath="ai/commit-templates/prompt",
        default_commit_msg=f"ai: link compact {dir_name} prompt",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
