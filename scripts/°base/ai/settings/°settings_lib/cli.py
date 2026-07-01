"""Synchronize Claude and Codex project settings through a neutral JSON file.

The neutral files under ``ai/tool-settings/`` are meant to be readable and
editable by humans. Native files remain editable too: this script imports
entries from both sides, unions them by stable identity, then renders the
native formats back out.
"""
from __future__ import annotations

import argparse
import os
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

from . import codex_rules, codex_toml, commands, paths
from .hooks import _shared_extras, _merge, _normalize_native, render_claude, render_codex_hooks
from .json_io import _read_json, _same_json, _write_json, _write_text_if_changed
from .skills import _sync_skills


def _bash_prefix_key(command: str) -> tuple[str, ...] | None:
    prefix = commands._bash_pattern_to_prefix(command)
    return tuple(prefix) if prefix is not None else None


def _merge_codex_rules_additions(shared: dict[str, Any], rules_text: str) -> dict[str, Any]:
    """Merge genuinely new bash entries found in a (possibly hand-edited)
    `.rules` file into `shared`. Entries are compared by their Codex prefix
    tuple rather than their raw command string, because `render_codex_rules`
    normalizes every command into a `prefix + wildcard` rule — reparsing that
    same generated file would otherwise reintroduce e.g. "yarn" as the
    distinct-looking "yarn:*" every run and duplicate it forever."""
    parsed = codex_rules.parse_codex_rules(rules_text)
    if not parsed.get("allow") and not parsed.get("deny"):
        return shared

    shared = deepcopy(shared)
    permissions = shared.setdefault("permissions", {"allow": [], "deny": []})
    for bucket in ("allow", "deny"):
        existing = list(permissions.get(bucket) or [])
        known_prefixes = {
            key
            for entry in existing
            if isinstance(entry, dict) and entry.get("type") == "bash"
            for key in [_bash_prefix_key(entry.get("command", ""))]
            if key is not None
        }
        additions = []
        for entry in parsed.get(bucket) or []:
            key = _bash_prefix_key(entry["command"])
            if key is not None and key in known_prefixes:
                continue
            additions.append(entry)
            if key is not None:
                known_prefixes.add(key)
        if additions:
            permissions[bucket] = existing + additions
    shared["permissions"] = permissions
    return shared


def _load_layer(
    shared_path: Path,
    claude_path: Path,
    codex_path: Path,
    codex_rules_path: Path | None = None,
    codex_config_path: Path | None = None,
) -> dict[str, Any]:
    shared_source = _read_json(shared_path)
    shared = deepcopy(shared_source)
    if shared:
        shared = _merge({}, shared)

    native_sources: list[tuple[float, dict[str, Any]]] = []
    for path in (claude_path, codex_path):
        if path.is_file():
            native_sources.append((path.stat().st_mtime, _read_json(path)))
    if codex_config_path is not None and codex_config_path.is_file():
        plugins = codex_toml.parse_codex_plugins(codex_config_path.read_text(encoding="utf-8"))
        if plugins:
            native_sources.append((codex_config_path.stat().st_mtime, {"enabledPlugins": plugins}))

    if not shared and native_sources:
        shared = _normalize_native(sorted(native_sources, key=lambda item: item[0])[-1][1])
    for _, data in sorted(native_sources, key=lambda item: item[0]):
        shared = _merge(shared, data)
    shared = shared or {"version": 1, "hooks": {}, "permissions": {"allow": [], "deny": []}}

    if codex_rules_path is not None and codex_rules_path.is_file():
        shared = _merge_codex_rules_additions(shared, codex_rules_path.read_text(encoding="utf-8"))

    shared.update(_shared_extras(shared_source))
    return shared


def _apply_or_check(
    shared_path: Path,
    claude_path: Path,
    codex_path: Path,
    apply: bool,
    codex_rules_path: Path | None = None,
    codex_config_path: Path | None = None,
) -> list[str]:
    changed: list[str] = []
    shared = _load_layer(shared_path, claude_path, codex_path, codex_rules_path, codex_config_path)
    claude = render_claude(shared)
    codex = render_codex_hooks(shared)

    for path, data in (
        (shared_path, shared),
        (claude_path, claude),
        (codex_path, codex),
    ):
        if _same_json(path, data):
            continue
        changed.append(str(path))
        if apply:
            _write_json(path, data)

    if codex_rules_path is not None:
        rules_text = codex_rules.render_codex_rules(shared)
        changed.extend(_write_text_if_changed(codex_rules_path, rules_text, apply))

    if codex_config_path is not None:
        current_text = codex_config_path.read_text(encoding="utf-8") if codex_config_path.is_file() else ""
        plugins_text = codex_toml.render_codex_plugins(current_text, shared.get("enabledPlugins") or {})
        changed.extend(_write_text_if_changed(codex_config_path, plugins_text, apply))

    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Synchronize Claude and Codex AI tool settings.")
    parser.add_argument("--dry-run", action="store_true", help="show what would change without writing files")
    parser.add_argument("--check", action="store_true", help="like --dry-run but exit 1 if files are out of sync (used by pre-commit)")
    args = parser.parse_args(argv)

    os.chdir(paths._git_root())
    dry = args.dry_run or args.check
    apply = not dry
    if args.dry_run:
        print("Dry run — no files will be written.")

    config_status = codex_toml._migrate_codex_feature_flag(paths.CODEX_CONFIG, apply, sys.stdin.isatty())

    changed: list[str] = []
    changed.extend(
        _apply_or_check(
            paths.TRACKED_SHARED,
            paths.CLAUDE_SETTINGS,
            paths.CODEX_HOOKS,
            apply,
            paths.CODEX_RULES,
            paths.CODEX_PROJECT_CONFIG,
        )
    )
    if paths.LOCAL_SHARED.is_file() or paths.CLAUDE_LOCAL.is_file() or paths.CODEX_LOCAL_HOOKS.is_file():
        changed.extend(
            _apply_or_check(
                paths.LOCAL_SHARED,
                paths.CLAUDE_LOCAL,
                paths.CODEX_LOCAL_HOOKS,
                apply,
                paths.CODEX_RULES_LOCAL,
                None,
            )
        )
    changed.extend(_sync_skills(apply))

    if changed:
        if args.check:
            print("AI tool settings are out of sync:")
            for path in changed:
                print(f"  {path}")
            print("Run `./scripts/°base/ai/settings/sync.py` to fix.")
            return 1
        verb = "Would write" if dry else "Wrote"
        for path in changed:
            print(f"{verb}: {path}")
    else:
        print("All files are already in sync.")

    return config_status


if __name__ == "__main__":
    raise SystemExit(main())
