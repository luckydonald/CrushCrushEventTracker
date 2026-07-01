from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from .commands import _parse_claude_permission_entry, _render_claude_permission_entry
from .json_io import _unique

_CORE_SHARED_KEYS = {"version", "hooks", "permissions", "enabledPlugins"}


def _hook_id(event: str, entry: dict[str, Any]) -> str:
    matcher = entry.get("matcher") or ""
    commands = []
    for hook in entry.get("hooks") or []:
        if isinstance(hook, dict):
            commands.append(_neutralize_command(hook.get("command") or ""))
    return "\0".join([event, matcher, "\0".join(commands)])


def _matcher_tokens(entry: dict[str, Any]) -> set[str]:
    matcher = str(entry.get("matcher") or "")
    return {part for part in matcher.split("|") if part} or {""}


def _entry_commands(entry: dict[str, Any]) -> set[str]:
    commands: set[str] = set()
    for hook in entry.get("hooks") or []:
        if isinstance(hook, dict):
            commands.add(_neutralize_command(str(hook.get("command") or "")))
    return commands


def _subsumes(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """True when entry ``a`` covers everything entry ``b`` covers."""
    return _matcher_tokens(a).issuperset(_matcher_tokens(b)) and _entry_commands(a).issuperset(_entry_commands(b))


def _overlay_entry(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(existing)
    for key, value in incoming.items():
        if key != "hooks":
            merged[key] = deepcopy(value)

    existing_hooks = merged.get("hooks") if isinstance(merged.get("hooks"), list) else []
    incoming_hooks = incoming.get("hooks") if isinstance(incoming.get("hooks"), list) else []
    hooks = []
    for index, hook in enumerate(incoming_hooks):
        if not isinstance(hook, dict):
            continue
        if index < len(existing_hooks) and isinstance(existing_hooks[index], dict):
            merged_hook = deepcopy(existing_hooks[index])
            merged_hook.update(deepcopy(hook))
            hooks.append(merged_hook)
        else:
            hooks.append(deepcopy(hook))
    if hooks:
        merged["hooks"] = hooks
    return merged


def _normalize_permissions(permissions: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(permissions)
    for key in ("allow", "deny"):
        values = permissions.get(key)
        if values is not None:
            normalized[key] = [_parse_claude_permission_entry(v) for v in values]
    return normalized


def _normalize_native(data: dict[str, Any]) -> dict[str, Any]:
    hooks = deepcopy(data.get("hooks") or {})
    for entries in hooks.values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            for hook in entry.get("hooks") or []:
                if isinstance(hook, dict):
                    hook["command"] = _neutralize_command(str(hook.get("command") or ""))
    return {
        "version": 1,
        "hooks": hooks,
        "permissions": _normalize_permissions(data.get("permissions") or {}),
        "enabledPlugins": deepcopy(data.get("enabledPlugins") or {}),
    }


def _shared_extras(data: dict[str, Any]) -> dict[str, Any]:
    return {key: deepcopy(value) for key, value in data.items() if key not in _CORE_SHARED_KEYS}


def _merge(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = _normalize_native(base)
    incoming = _normalize_native(incoming)

    hooks = deepcopy(merged.get("hooks") or {})
    for event, entries in (incoming.get("hooks") or {}).items():
        if not isinstance(entries, list):
            continue
        current = [deepcopy(entry) for entry in hooks.get(event, []) if isinstance(entry, dict)]
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            entry_id = _hook_id(event, entry)
            replaced = False
            for index, existing in enumerate(current):
                if _hook_id(event, existing) == entry_id:
                    current[index] = _overlay_entry(existing, entry)
                    replaced = True
                    break
            if replaced:
                continue
            if any(_subsumes(existing, entry) for existing in current):
                continue
            current = [existing for existing in current if not _subsumes(entry, existing)]
            by_id = {_hook_id(event, existing): existing for existing in current}
            by_id[entry_id] = deepcopy(entry)
            current = list(by_id.values())
        hooks[event] = current
    merged["hooks"] = hooks

    permissions = deepcopy(merged.get("permissions") or {})
    incoming_permissions = incoming.get("permissions") or {}
    for key in ("allow", "deny"):
        values = list(permissions.get(key) or [])
        values.extend(incoming_permissions.get(key) or [])
        permissions[key] = _unique(values)
    merged["permissions"] = permissions

    enabled_plugins = deepcopy(merged.get("enabledPlugins") or {})
    enabled_plugins.update(incoming.get("enabledPlugins") or {})
    merged["enabledPlugins"] = enabled_plugins
    return merged


def _replace_tool_arg(command: str, tool: str) -> str:
    if (
        "save-prompt/hook.py" in command
        or "save-decision/hook.py" in command
        or "save-plan/hook.py" in command
    ):
        command = command.replace("'claude'", f"'{tool}'")
        command = command.replace('"claude"', f'"{tool}"')
        if "save-plan/hook.py" in command and not re.search(r"['\"](?:claude|codex)['\"]", command):
            command = f"{command} '{tool}'"
    return command


def _normalize_command_path(command: str) -> str:
    command = command.replace("python3 .claude/hooks/permission-check.py", 'python3 "$(git rev-parse --show-toplevel)/.claude/hooks/permission-check.py"')
    return command


def _uv_project_hook_command(command: str) -> str:
    if "save-decision/hook.py" not in command:
        return command
    match = re.search(r"(?:python3|python)\s+\"?([^\"']*save-decision/hook\.py)\"?\s*(.*)\Z", command)
    if not match:
        return command
    script, args = match.groups()
    if "uv run --project" in command:
        return command
    script = script.strip()
    args = args.strip()
    if "$(git rev-parse --show-toplevel)" not in script:
        script = f"$(git rev-parse --show-toplevel)/{script.lstrip('./')}"
    return (
        f'"$(git rev-parse --show-toplevel)/scripts/°base/git/hooks/tool_path.sh" '
        f'uv run --project "$(git rev-parse --show-toplevel)/scripts/°base" '
        f'python "{script}"'
        + (f" {args}" if args else "")
    )


def _neutralize_uv_project_hook_command(command: str) -> str:
    match = re.search(
        r'\A(?:"?\$\(git rev-parse --show-toplevel\)/scripts/°base/git/hooks/tool_path\.sh"? )?'
        r"uv run --project \"?\$\(git rev-parse --show-toplevel\)/scripts/°base\"? "
        r"python \"?([^\"']*save-decision/hook\.py)\"?\s*(.*)\Z",
        command,
    )
    if not match:
        return command
    script, args = match.groups()
    script = script.strip()
    args = args.strip()
    return f'python3 "{script}"' + (f" {args}" if args else "")


def _neutralize_command(command: str) -> str:
    command = _normalize_command_path(command)
    command = _neutralize_uv_project_hook_command(command)
    if (
        "save-prompt/hook.py" in command
        or "save-decision/hook.py" in command
        or "save-plan/hook.py" in command
    ):
        command = command.replace("'codex'", "'claude'")
        command = command.replace('"codex"', '"claude"')
        if "save-plan/hook.py" in command and not re.search(r"['\"](?:claude|codex)['\"]", command):
            command = f"{command} 'claude'"
    return command


def _render_hooks(shared: dict[str, Any], tool: str) -> dict[str, Any]:
    rendered: dict[str, Any] = {"hooks": {}}
    for event, entries in (shared.get("hooks") or {}).items():
        if not isinstance(entries, list):
            continue
        rendered_entries = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            new_entry = deepcopy(entry)
            hooks = []
            for hook in new_entry.get("hooks") or []:
                if not isinstance(hook, dict):
                    continue
                new_hook = deepcopy(hook)
                command = str(new_hook.get("command") or "")
                command = _normalize_command_path(_replace_tool_arg(command, tool))
                command = _uv_project_hook_command(command)
                new_hook["command"] = command
                if tool == "codex":
                    new_hook.pop("async", None)
                hooks.append(new_hook)
            new_entry["hooks"] = hooks
            rendered_entries.append(new_entry)
        if rendered_entries:
            rendered["hooks"][event] = rendered_entries
    return rendered


def render_claude(shared: dict[str, Any]) -> dict[str, Any]:
    data = _render_hooks(shared, "claude")
    permissions = shared.get("permissions")
    if permissions:
        rendered_permissions: dict[str, Any] = {}
        for key in ("allow", "deny"):
            values = permissions.get(key)
            if values is not None:
                rendered_permissions[key] = [_render_claude_permission_entry(v) for v in values]
        for key, value in permissions.items():
            if key not in ("allow", "deny"):
                rendered_permissions[key] = deepcopy(value)
        data["permissions"] = rendered_permissions
    enabled_plugins = shared.get("enabledPlugins")
    if enabled_plugins:
        data["enabledPlugins"] = deepcopy(enabled_plugins)
    return data


def render_codex_hooks(shared: dict[str, Any]) -> dict[str, Any]:
    return _render_hooks(shared, "codex")
