from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

_GIT_ROOT_TOKEN = "$(git rev-parse --show-toplevel)"

MCP_TOML_BEGIN_MARKER = "# --- BEGIN generated mcp_servers (scripts/°base/ai/settings/sync.py) ---"
MCP_TOML_END_MARKER = "# --- END generated mcp_servers ---"

_TABLE_HEADER = re.compile(r'^\[([^\[\]]+)\]\s*$')


def _substitute_git_root(value: str, git_root: Path) -> str:
    return value.replace(_GIT_ROOT_TOKEN, str(git_root))


def _resolve_tool_ref(tools: dict[str, Any], ref: str) -> list[str] | None:
    name, _, variant = ref.partition("@")
    variants = tools.get(name)
    if not isinstance(variants, dict):
        return None
    entry = variants.get(variant)
    if not isinstance(entry, dict) or entry.get("mode") != "prefix":
        return None
    cmd = entry.get("cmd")
    if not isinstance(cmd, list) or not all(isinstance(token, str) for token in cmd):
        return None
    return list(cmd)


def _resolve_server_argv(mcp: dict[str, Any], server: dict[str, Any], git_root: Path) -> list[str] | None:
    tools = mcp.get("tools") or {}
    argv: list[str] = []
    for ref in server.get("tools") or []:
        resolved = _resolve_tool_ref(tools, ref)
        if resolved is None:
            return None
        argv.extend(resolved)
    cmd = server.get("cmd")
    if not isinstance(cmd, list) or not cmd or not all(isinstance(token, str) for token in cmd):
        return None
    argv.extend(cmd)
    return [_substitute_git_root(token, git_root) for token in argv]


def render_claude_mcp(shared: dict[str, Any], git_root: Path) -> tuple[dict[str, Any], list[str]]:
    """Build `.mcp.json` content. Returns (data, skipped_server_names)."""
    mcp = shared.get("mcp") or {}
    servers = mcp.get("servers") or {}
    rendered: dict[str, Any] = {}
    skipped: list[str] = []
    for name, server in servers.items():
        if not isinstance(server, dict):
            continue
        if server.get("type") == "http":
            entry: dict[str, Any] = {"type": "http", "url": server.get("url", "")}
            if server.get("headers"):
                entry["headers"] = dict(server["headers"])
            rendered[name] = entry
            continue
        argv = _resolve_server_argv(mcp, server, git_root)
        if argv is None:
            skipped.append(name)
            continue
        rendered[name] = {"type": "stdio", "command": argv[0], "args": argv[1:]}
    return {"mcpServers": rendered}, skipped


def parse_claude_mcp(mcp_json_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for name, entry in (mcp_json_data.get("mcpServers") or {}).items():
        if not isinstance(entry, dict):
            continue
        if entry.get("type") == "http" or "url" in entry:
            neutral: dict[str, Any] = {"type": "http", "url": entry.get("url", ""), "enabled": True}
            if entry.get("headers"):
                neutral["headers"] = dict(entry["headers"])
            result[name] = neutral
            continue
        command = entry.get("command")
        if not isinstance(command, str):
            continue
        args = entry.get("args") or []
        result[name] = {
            "type": "stdio",
            "cmd": [command, *[str(arg) for arg in args]],
            "enabled": True,
        }
    return result


def _server_table_lines(name: str, server: dict[str, Any], mcp: dict[str, Any], git_root: Path) -> list[str] | None:
    table_name = f'mcp_servers.{json.dumps(name)}'
    lines = [f"[{table_name}]"]
    if server.get("type") == "http":
        lines.append(f'url = {json.dumps(server.get("url", ""))}')
        headers = server.get("headers")
        if headers:
            lines.append(f'http_headers = {json.dumps(headers)}')
    else:
        argv = _resolve_server_argv(mcp, server, git_root)
        if argv is None:
            return None
        lines.append(f'command = {json.dumps(argv[0])}')
        lines.append(f'args = {json.dumps(argv[1:])}')
    enabled = server.get("enabled", True)
    lines.append(f'enabled = {"true" if enabled else "false"}')
    return lines


def render_codex_mcp_block(shared: dict[str, Any], git_root: Path) -> tuple[str, list[str]]:
    """Render the `[mcp_servers.*]` marked block. Returns (block_text, skipped_server_names)."""
    mcp = shared.get("mcp") or {}
    servers = mcp.get("servers") or {}
    lines = [MCP_TOML_BEGIN_MARKER]
    skipped: list[str] = []
    for name, server in servers.items():
        if not isinstance(server, dict):
            continue
        table_lines = _server_table_lines(name, server, mcp, git_root)
        if table_lines is None:
            skipped.append(name)
            continue
        lines.append("")
        lines.extend(table_lines)
    lines.append("")
    lines.append(MCP_TOML_END_MARKER)
    return "\n".join(lines) + "\n", skipped


def insert_or_replace_block(text: str, begin_marker: str, end_marker: str, body: str) -> str:
    if not text.strip():
        text = ""

    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"

    start = end = None
    for index, line in enumerate(lines):
        if line.strip() == begin_marker:
            start = index
        elif line.strip() == end_marker and start is not None:
            end = index
            break

    body_lines = body.splitlines(keepends=True)
    if body_lines and not body_lines[-1].endswith("\n"):
        body_lines[-1] += "\n"

    if start is not None and end is not None:
        lines[start:end + 1] = body_lines
        return "".join(lines)

    if lines and lines[-1].strip() != "":
        lines.append("\n")
    lines.extend(body_lines)
    return "".join(lines)


def parse_codex_mcp_toml(text: str) -> dict[str, dict[str, Any]]:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return {}
    mcp_servers = data.get("mcp_servers")
    if not isinstance(mcp_servers, dict):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for name, entry in mcp_servers.items():
        if not isinstance(entry, dict):
            continue
        enabled = bool(entry.get("enabled", True))
        if "url" in entry:
            neutral: dict[str, Any] = {"type": "http", "url": entry.get("url", ""), "enabled": enabled}
            if entry.get("http_headers"):
                neutral["headers"] = dict(entry["http_headers"])
            result[name] = neutral
            continue
        command = entry.get("command")
        if not isinstance(command, str):
            continue
        args = entry.get("args") or []
        result[name] = {
            "type": "stdio",
            "cmd": [command, *[str(arg) for arg in args]],
            "enabled": enabled,
        }
    return result
