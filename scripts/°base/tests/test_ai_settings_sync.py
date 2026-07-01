from __future__ import annotations

import contextlib
import io
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "ai" / "settings" / "sync.py"
SPEC = importlib.util.spec_from_file_location("ai_settings_sync", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class AiSettingsSyncTests(unittest.TestCase):
    @contextlib.contextmanager
    def patched_skill_paths(self, root: Path):
        names = [
            "SHARED_SKILLS",
            "AGENTS_SKILLS",
            "CLAUDE_SKILLS",
            "CLAUDE_COMMANDS",
            "CODEX_COMMANDS",
        ]
        previous = {name: getattr(MODULE, name) for name in names}
        MODULE.SHARED_SKILLS = root / "ai" / "skills"
        MODULE.AGENTS_SKILLS = root / ".agents" / "skills"
        MODULE.CLAUDE_SKILLS = root / ".claude" / "skills"
        MODULE.CLAUDE_COMMANDS = root / ".claude" / "commands"
        MODULE.CODEX_COMMANDS = root / ".codex" / "commands"
        try:
            yield
        finally:
            for name, value in previous.items():
                setattr(MODULE, name, value)

    def test_render_codex_rewrites_prompt_tool_arg(self):
        shared = {
            "hooks": {
                "UserPromptSubmit": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": "python3 scripts/°base/ai/hooks/save-prompt/hook.py 'claude'",
                            }
                        ]
                    }
                ]
            }
        }

        rendered = MODULE.render_codex_hooks(shared)
        command = rendered["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]

        self.assertIn("'codex'", command)
        self.assertNotIn("'claude'", command)

    def test_render_codex_rewrites_plan_tool_arg(self):
        shared = {
            "hooks": {
                "Stop": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": "python3 scripts/°base/ai/hooks/save-plan/hook.py 'claude'",
                            }
                        ]
                    }
                ]
            }
        }

        codex = MODULE.render_codex_hooks(shared)
        claude = MODULE.render_claude(shared)
        codex_command = codex["hooks"]["Stop"][0]["hooks"][0]["command"]
        claude_command = claude["hooks"]["Stop"][0]["hooks"][0]["command"]

        self.assertIn("'codex'", codex_command)
        self.assertNotIn("'claude'", codex_command)
        self.assertIn("'claude'", claude_command)
        self.assertNotIn("'codex'", claude_command)

    def test_render_save_decision_uses_uv_project_environment(self):
        shared = {
            "hooks": {
                "PostToolUse": [
                    {
                        "matcher": "AskUserQuestion|request_user_input",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "python3 \"$(git rev-parse --show-toplevel)/scripts/°base/ai/hooks/save-decision/hook.py\" 'claude'",
                            }
                        ],
                    }
                ]
            }
        }

        rendered = MODULE.render_codex_hooks(shared)
        command = rendered["hooks"]["PostToolUse"][0]["hooks"][0]["command"]

        self.assertIn('"$(git rev-parse --show-toplevel)/scripts/°base/git/hooks/tool_path.sh"', command)
        self.assertIn('uv run --project "$(git rev-parse --show-toplevel)/scripts/°base"', command)
        self.assertIn('python "$(git rev-parse --show-toplevel)/scripts/°base/ai/hooks/save-decision/hook.py"', command)
        self.assertIn("'codex'", command)

    def test_uv_wrapped_save_decision_neutralizes_to_same_identity(self):
        plain = {
            "hooks": {
                "PostToolUse": [
                    {
                        "matcher": "AskUserQuestion|request_user_input",
                        "hooks": [
                            {
                                "command": "python3 \"$(git rev-parse --show-toplevel)/scripts/°base/ai/hooks/save-decision/hook.py\" 'claude'",
                            }
                        ],
                    }
                ]
            }
        }
        wrapped = {
            "hooks": {
                "PostToolUse": [
                    {
                        "matcher": "AskUserQuestion|request_user_input",
                        "hooks": [
                            {
                                "command": "\"$(git rev-parse --show-toplevel)/scripts/°base/git/hooks/tool_path.sh\" uv run --project \"$(git rev-parse --show-toplevel)/scripts/°base\" python \"$(git rev-parse --show-toplevel)/scripts/°base/ai/hooks/save-decision/hook.py\" 'codex'",
                                "async": True,
                            }
                        ],
                    }
                ]
            }
        }

        merged = MODULE._merge(plain, wrapped)
        entries = merged["hooks"]["PostToolUse"]

        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0]["hooks"][0]["async"])

    def test_normalize_native_adds_default_plan_tool_arg(self):
        native = {
            "hooks": {
                "Stop": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": "python3 scripts/°base/ai/hooks/save-plan/hook.py",
                            }
                        ]
                    }
                ]
            }
        }

        normalized = MODULE._normalize_native(native)
        command = normalized["hooks"]["Stop"][0]["hooks"][0]["command"]

        self.assertTrue(command.endswith("'claude'"))

    def test_render_codex_strips_async(self):
        shared = {
            "hooks": {
                "SessionStart": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": "python3 hook.py",
                                "async": True,
                            }
                        ]
                    }
                ]
            }
        }

        rendered = MODULE.render_codex_hooks(shared)
        hook = rendered["hooks"]["SessionStart"][0]["hooks"][0]

        self.assertNotIn("async", hook)

    def test_render_claude_keeps_permissions(self):
        shared = {
            "hooks": {},
            "permissions": {"allow": ["Bash(git status:*)"], "deny": ["Read(**/.env*)"]},
        }

        rendered = MODULE.render_claude(shared)

        self.assertEqual(rendered["permissions"]["allow"], ["Bash(git status:*)"])
        self.assertEqual(rendered["permissions"]["deny"], ["Read(**/.env*)"])

    def test_load_layer_preserves_shared_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shared_path = root / "ai" / "tool-settings" / "settings.json"
            claude_path = root / ".claude" / "settings.json"
            codex_path = root / ".codex" / "hooks.json"
            shared_path.parent.mkdir(parents=True)
            shared_path.write_text(
                '{"version": 1, "hooks": {}, "permissions": {"allow": [], "deny": []}, "download_link": {"ide": "pycharm"}}',
                encoding="utf-8",
            )

            shared = MODULE._load_layer(shared_path, claude_path, codex_path)

            self.assertEqual(shared["download_link"], {"ide": "pycharm"})
            self.assertNotIn("download_link", MODULE.render_claude(shared))
            self.assertNotIn("download_link", MODULE.render_codex_hooks(shared))

    def test_merge_unions_permissions_without_duplicates(self):
        base = {"permissions": {"allow": ["A", "B"], "deny": ["X"]}}
        incoming = {"permissions": {"allow": ["B", "C"], "deny": ["X", "Y"]}}

        merged = MODULE._merge(base, incoming)

        self.assertEqual(merged["permissions"]["allow"], ["A", "B", "C"])
        self.assertEqual(merged["permissions"]["deny"], ["X", "Y"])

    def test_merge_replaces_same_hook_identity(self):
        base = {
            "hooks": {
                "SessionStart": [
                    {"hooks": [{"command": "cmd"}], "matcher": "old", "extra": "old"}
                ]
            }
        }
        incoming = {
            "hooks": {
                "SessionStart": [
                    {"hooks": [{"command": "cmd"}], "matcher": "old", "extra": "new"}
                ]
            }
        }

        merged = MODULE._merge(base, incoming)

        self.assertEqual(merged["hooks"]["SessionStart"][0]["extra"], "new")

    def test_merge_preserves_missing_hook_fields_for_same_identity(self):
        base = {
            "hooks": {
                "SessionStart": [
                    {"hooks": [{"command": "cmd", "async": True}], "matcher": ""}
                ]
            }
        }
        incoming = {
            "hooks": {
                "SessionStart": [
                    {"hooks": [{"command": "cmd"}], "matcher": ""}
                ]
            }
        }

        merged = MODULE._merge(base, incoming)

        self.assertTrue(merged["hooks"]["SessionStart"][0]["hooks"][0]["async"])

    def test_rewrite_codex_feature_flag(self):
        text = "model = \"gpt-5\"\n[features]\ncodex_hooks = true\n\n[projects]\n"

        rewritten, changed = MODULE._rewrite_codex_feature_flag(text)

        self.assertTrue(changed)
        self.assertEqual(
            rewritten,
            "model = \"gpt-5\"\n[features]\nhooks = true\n\n[projects]\n",
        )

    def test_rewrite_codex_feature_flag_removes_deprecated_when_hooks_exists(self):
        text = "[features]\nhooks = true\ncodex_hooks = true\n"

        rewritten, changed = MODULE._rewrite_codex_feature_flag(text)

        self.assertTrue(changed)
        self.assertEqual(rewritten, "[features]\nhooks = true\n")

    def test_migrate_codex_feature_flag_yes_writes_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text("[features]\ncodex_hooks = true\n", encoding="utf-8")
            previous_input = getattr(MODULE, "input", None)
            MODULE.input = lambda _prompt: "y"
            out = io.StringIO()
            try:
                with contextlib.redirect_stdout(out):
                    status = MODULE._migrate_codex_feature_flag(path, True, True)
            finally:
                if previous_input is None:
                    delattr(MODULE, "input")
                else:
                    MODULE.input = previous_input

            self.assertEqual(status, 0)
            self.assertEqual(path.read_text(encoding="utf-8"), "[features]\nhooks = true\n")

    def test_migrate_codex_feature_flag_exit_prints_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            original = "[features]\ncodex_hooks = true\n"
            path.write_text(original, encoding="utf-8")
            previous_input = getattr(MODULE, "input", None)
            MODULE.input = lambda _prompt: "exit"
            out = io.StringIO()
            try:
                with contextlib.redirect_stdout(out):
                    status = MODULE._migrate_codex_feature_flag(path, True, True)
            finally:
                if previous_input is None:
                    delattr(MODULE, "input")
                else:
                    MODULE.input = previous_input

            self.assertEqual(status, 1)
            self.assertIn(str(path), out.getvalue())
            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_sync_skills_imports_claude_command_and_renders_wrappers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            command = root / ".claude" / "commands" / "demo.md"
            command.parent.mkdir(parents=True)
            command.write_text(
                "---\n"
                "name: demo\n"
                "description: Use demo: carefully.\n"
                "---\n\n"
                "# Demo\n\n"
                "Full command body.\n",
                encoding="utf-8",
            )

            with self.patched_skill_paths(root):
                changed = MODULE._sync_skills(True)

            shared = root / "ai" / "skills" / "demo" / "SKILL.md"
            codex_skill = root / ".agents" / "skills" / "demo" / "SKILL.md"
            wrapper = root / ".claude" / "skills" / "demo" / "SKILL.md"
            self.assertIn(str(shared), changed)
            self.assertTrue(shared.is_file())
            self.assertIn('description: "Use demo: carefully."', shared.read_text(encoding="utf-8"))
            self.assertIn("Full command body.", shared.read_text(encoding="utf-8"))
            self.assertIn(MODULE.GENERATED_MARKER, codex_skill.read_text(encoding="utf-8"))
            self.assertIn(MODULE.GENERATED_MARKER, wrapper.read_text(encoding="utf-8"))
            self.assertIn(MODULE.GENERATED_MARKER, command.read_text(encoding="utf-8"))
            self.assertNotIn("Full command body.", codex_skill.read_text(encoding="utf-8"))
            self.assertNotIn("Full command body.", wrapper.read_text(encoding="utf-8"))
            self.assertNotIn("Full command body.", command.read_text(encoding="utf-8"))

    def test_sync_skills_imports_new_claude_skill_over_generated_wrapper(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shared = root / "ai" / "skills" / "demo" / "SKILL.md"
            shared.parent.mkdir(parents=True)
            shared.write_text(
                "---\n"
                "name: demo\n"
                "description: Old shared source.\n"
                "---\n\n"
                "Old body.\n",
                encoding="utf-8",
            )

            generated = root / ".claude" / "commands" / "demo.md"
            generated.parent.mkdir(parents=True)
            generated.write_text(
                MODULE._render_claude_command_shim("demo", "Old shared source.", shared),
                encoding="utf-8",
            )

            claude_skill = root / ".claude" / "skills" / "demo" / "SKILL.md"
            claude_skill.parent.mkdir(parents=True)
            claude_skill.write_text(
                "---\n"
                "name: demo\n"
                "description: New Claude skill.\n"
                "---\n\n"
                "New body.\n",
                encoding="utf-8",
            )
            os.utime(claude_skill, (shared.stat().st_mtime + 10, shared.stat().st_mtime + 10))

            with self.patched_skill_paths(root):
                MODULE._sync_skills(True)

            shared_text = shared.read_text(encoding="utf-8")
            self.assertIn("New Claude skill.", shared_text)
            self.assertIn("New body.", shared_text)
            self.assertIn(MODULE.GENERATED_MARKER, claude_skill.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
