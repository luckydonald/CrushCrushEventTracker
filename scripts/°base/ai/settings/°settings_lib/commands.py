from __future__ import annotations

import re
import shlex
from typing import Any


_PERMISSION_ENTRY = re.compile(r"^([A-Za-z_]\w*)\((.*)\)$", re.DOTALL)

# Type-specific field name used for the entry's main value, keyed by the
# lowercased tool type. Anything not listed here falls back to `pattern`.
_TYPE_FIELD: dict[str, str] = {
    "bash": "command",
    "read": "path",
    "write": "path",
    "edit": "path",
    "glob": "path",
    "skill": "name",
}
_DEFAULT_FIELD = "pattern"

_TYPE_TO_CLAUDE_TOOL: dict[str, str] = {
    "bash": "Bash",
    "read": "Read",
    "write": "Write",
    "edit": "Edit",
    "skill": "Skill",
    "glob": "Glob",
    "grep": "Grep",
    "webfetch": "WebFetch",
    "websearch": "WebSearch",
}


def _parse_claude_permission_entry(entry: Any) -> dict[str, Any]:
    """Upgrade a legacy Claude permission string (or pass through an already
    structured object) into the neutral `{"type": ..., ...}` schema."""
    if isinstance(entry, dict):
        return entry
    if not isinstance(entry, str):
        return {"type": "raw", "value": entry}
    match = _PERMISSION_ENTRY.match(entry)
    if not match:
        return {"type": "raw", "value": entry}
    tool, content = match.groups()
    entry_type = tool.lower()
    field = _TYPE_FIELD.get(entry_type, _DEFAULT_FIELD)
    return {"type": entry_type, field: content}


def _render_claude_permission_entry(entry: Any) -> str:
    """Inverse of `_parse_claude_permission_entry`: render a neutral entry
    back into Claude's `Tool(content)` string syntax."""
    if isinstance(entry, str):
        return entry
    if not isinstance(entry, dict):
        return str(entry)
    entry_type = entry.get("type", "")
    if entry_type == "raw":
        return str(entry.get("value", ""))
    tool = _TYPE_TO_CLAUDE_TOOL.get(entry_type, entry_type.capitalize())
    field = _TYPE_FIELD.get(entry_type, _DEFAULT_FIELD)
    content = entry.get(field, entry.get(_DEFAULT_FIELD, ""))
    return f"{tool}({content})"


# Characters that mean a command string can't be safely reduced to a single
# static argv prefix the way Codex's `.rules` engine expects (see
# https://developers.openai.com/codex/rules — compound/redirected/substituted
# commands are evaluated as one opaque `bash -lc "<script>"` invocation).
_SHELL_METACHARACTERS = re.compile(r"[$`;|<>&]")
_ENV_ASSIGNMENT_PREFIX = re.compile(r"^[A-Za-z_]\w*=")


def _bash_pattern_to_prefix(command: str) -> list[str] | None:
    """Convert a Claude bash permission pattern into a Codex `prefix_rule`
    token list, or return None when it can't be safely translated."""
    command = command.strip()
    if not command:
        return None
    if _SHELL_METACHARACTERS.search(command) or _ENV_ASSIGNMENT_PREFIX.match(command):
        return None

    stripped = command
    if stripped.endswith(":*"):
        stripped = stripped[:-2]
    elif stripped.endswith("*"):
        stripped = stripped[:-1].rstrip()
    stripped = stripped.strip()
    if not stripped:
        return None

    try:
        tokens = shlex.split(stripped)
    except ValueError:
        return None
    return tokens or None
