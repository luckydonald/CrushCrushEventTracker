from __future__ import annotations

import contextlib
import io
import importlib
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


LIB_ROOT = Path(__file__).resolve().parents[1] / "ai" / "settings"
sys.path.insert(0, str(LIB_ROOT))

paths = importlib.import_module("°settings_lib.paths")
commands = importlib.import_module("°settings_lib.commands")
hooks = importlib.import_module("°settings_lib.hooks")
codex_rules = importlib.import_module("°settings_lib.codex_rules")
codex_toml = importlib.import_module("°settings_lib.codex_toml")
skills = importlib.import_module("°settings_lib.skills")
cli = importlib.import_module("°settings_lib.cli")

ENTRYPOINT_PATH = LIB_ROOT / "sync.py"
SPEC = importlib.util.spec_from_file_location("ai_settings_sync_entrypoint", ENTRYPOINT_PATH)
ENTRYPOINT = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(ENTRYPOINT)


class EntrypointTests(unittest.TestCase):
    def test_shim_exposes_main(self):
        self.assertIs(ENTRYPOINT.main, cli.main)


class HooksTests(unittest.TestCase):
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

        rendered = hooks.render_codex_hooks(shared)
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

        codex = hooks.render_codex_hooks(shared)
        claude = hooks.render_claude(shared)
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

        rendered = hooks.render_codex_hooks(shared)
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

        merged = hooks._merge(plain, wrapped)
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

        normalized = hooks._normalize_native(native)
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

        rendered = hooks.render_codex_hooks(shared)
        hook = rendered["hooks"]["SessionStart"][0]["hooks"][0]

        self.assertNotIn("async", hook)

    def test_render_claude_keeps_permissions(self):
        shared = {
            "hooks": {},
            "permissions": {"allow": ["Bash(git status:*)"], "deny": ["Read(**/.env*)"]},
        }

        rendered = hooks.render_claude(shared)

        self.assertEqual(rendered["permissions"]["allow"], ["Bash(git status:*)"])
        self.assertEqual(rendered["permissions"]["deny"], ["Read(**/.env*)"])

    def test_render_claude_renders_structured_permission_entries(self):
        shared = {
            "hooks": {},
            "permissions": {
                "allow": [{"type": "bash", "command": "git status:*"}, {"type": "skill", "name": "demo"}],
                "deny": [{"type": "read", "path": "**/.env*"}],
            },
        }

        rendered = hooks.render_claude(shared)

        self.assertEqual(rendered["permissions"]["allow"], ["Bash(git status:*)", "Skill(demo)"])
        self.assertEqual(rendered["permissions"]["deny"], ["Read(**/.env*)"])

    def test_merge_unions_permissions_without_duplicates(self):
        base = {"permissions": {"allow": ["A", "B"], "deny": ["X"]}}
        incoming = {"permissions": {"allow": ["B", "C"], "deny": ["X", "Y"]}}

        merged = hooks._merge(base, incoming)

        self.assertEqual(
            merged["permissions"]["allow"],
            [{"type": "raw", "value": v} for v in ("A", "B", "C")],
        )
        self.assertEqual(
            merged["permissions"]["deny"],
            [{"type": "raw", "value": v} for v in ("X", "Y")],
        )

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

        merged = hooks._merge(base, incoming)

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

        merged = hooks._merge(base, incoming)

        self.assertTrue(merged["hooks"]["SessionStart"][0]["hooks"][0]["async"])


class CommandsTests(unittest.TestCase):
    def test_parse_render_round_trip_bash(self):
        entry = commands._parse_claude_permission_entry("Bash(git status:*)")
        self.assertEqual(entry, {"type": "bash", "command": "git status:*"})
        self.assertEqual(commands._render_claude_permission_entry(entry), "Bash(git status:*)")

    def test_parse_render_round_trip_read(self):
        entry = commands._parse_claude_permission_entry("Read(**/.env*)")
        self.assertEqual(entry, {"type": "read", "path": "**/.env*"})
        self.assertEqual(commands._render_claude_permission_entry(entry), "Read(**/.env*)")

    def test_parse_render_round_trip_skill(self):
        entry = commands._parse_claude_permission_entry("Skill(commit-with-lplp-style)")
        self.assertEqual(entry, {"type": "skill", "name": "commit-with-lplp-style"})
        self.assertEqual(commands._render_claude_permission_entry(entry), "Skill(commit-with-lplp-style)")

    def test_parse_render_round_trip_unknown_tool_uses_pattern_field(self):
        entry = commands._parse_claude_permission_entry("WebFetch(https://example.com)")
        self.assertEqual(entry, {"type": "webfetch", "pattern": "https://example.com"})
        self.assertEqual(commands._render_claude_permission_entry(entry), "WebFetch(https://example.com)")

    def test_parse_malformed_string_is_lossless_raw(self):
        entry = commands._parse_claude_permission_entry("not-a-tool-call")
        self.assertEqual(entry, {"type": "raw", "value": "not-a-tool-call"})
        self.assertEqual(commands._render_claude_permission_entry(entry), "not-a-tool-call")

    def test_parse_passes_through_existing_object(self):
        entry = {"type": "bash", "command": "tree:*"}
        self.assertIs(commands._parse_claude_permission_entry(entry), entry)

    def test_bash_pattern_to_prefix_strips_colon_wildcard(self):
        self.assertEqual(commands._bash_pattern_to_prefix("git status:*"), ["git", "status"])

    def test_bash_pattern_to_prefix_strips_bare_wildcard(self):
        self.assertEqual(commands._bash_pattern_to_prefix("uv lock *"), ["uv", "lock"])

    def test_bash_pattern_to_prefix_plain_literal(self):
        self.assertEqual(commands._bash_pattern_to_prefix("git branch --show-current"), ["git", "branch", "--show-current"])

    def test_bash_pattern_to_prefix_rejects_substitution(self):
        self.assertIsNone(commands._bash_pattern_to_prefix('echo "exit: $?"'))

    def test_bash_pattern_to_prefix_rejects_compound_commands(self):
        self.assertIsNone(commands._bash_pattern_to_prefix("git add . && rm -rf /"))

    def test_bash_pattern_to_prefix_rejects_env_assignment_prefix(self):
        self.assertIsNone(commands._bash_pattern_to_prefix("GIT_SEQUENCE_EDITOR=/tmp/x.sh git rebase --continue"))


class CodexRulesTests(unittest.TestCase):
    def test_render_codex_rules_allow_and_deny(self):
        shared = {
            "permissions": {
                "allow": [{"type": "bash", "command": "git status:*"}],
                "deny": [{"type": "bash", "command": "rm -rf /"}],
            }
        }

        text = codex_rules.render_codex_rules(shared)

        self.assertIn('prefix_rule(pattern = ["git", "status"], decision = "allow")', text)
        self.assertIn('prefix_rule(pattern = ["rm", "-rf", "/"], decision = "forbidden")', text)

    def test_render_codex_rules_skips_non_bash_and_untranslatable(self):
        shared = {
            "permissions": {
                "allow": [
                    {"type": "skill", "name": "demo"},
                    {"type": "bash", "command": 'echo "exit: $?"'},
                ],
                "deny": [],
            }
        }

        text = codex_rules.render_codex_rules(shared)

        self.assertNotIn("prefix_rule", text)
        self.assertIn("1 command permission(s) could not be translated", text)

    def test_parse_codex_rules_round_trips_generated_output(self):
        shared = {
            "permissions": {
                "allow": [{"type": "bash", "command": "git status:*"}],
                "deny": [{"type": "bash", "command": "rm -rf /"}],
            }
        }
        text = codex_rules.render_codex_rules(shared)

        parsed = codex_rules.parse_codex_rules(text)

        self.assertEqual(parsed["allow"], [{"type": "bash", "command": "git status:*"}])
        self.assertEqual(parsed["deny"], [{"type": "bash", "command": "rm -rf /:*"}])

    def test_parse_codex_rules_skips_prompt_decision_and_bad_input(self):
        text = 'prefix_rule(pattern = ["gh", "pr", "view"], decision = "prompt")\n'
        parsed = codex_rules.parse_codex_rules(text)
        self.assertEqual(parsed, {"allow": [], "deny": []})

        self.assertEqual(codex_rules.parse_codex_rules("not even python(("), {"allow": [], "deny": []})


class CodexTomlTests(unittest.TestCase):
    def test_rewrite_codex_feature_flag(self):
        text = "model = \"gpt-5\"\n[features]\ncodex_hooks = true\n\n[projects]\n"

        rewritten, changed = codex_toml._rewrite_codex_feature_flag(text)

        self.assertTrue(changed)
        self.assertEqual(
            rewritten,
            "model = \"gpt-5\"\n[features]\nhooks = true\n\n[projects]\n",
        )

    def test_rewrite_codex_feature_flag_removes_deprecated_when_hooks_exists(self):
        text = "[features]\nhooks = true\ncodex_hooks = true\n"

        rewritten, changed = codex_toml._rewrite_codex_feature_flag(text)

        self.assertTrue(changed)
        self.assertEqual(rewritten, "[features]\nhooks = true\n")

    def test_migrate_codex_feature_flag_yes_writes_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text("[features]\ncodex_hooks = true\n", encoding="utf-8")
            previous_input = getattr(codex_toml, "input", None)
            codex_toml.input = lambda _prompt: "y"
            out = io.StringIO()
            try:
                with contextlib.redirect_stdout(out):
                    status = codex_toml._migrate_codex_feature_flag(path, True, True)
            finally:
                if previous_input is None:
                    delattr(codex_toml, "input")
                else:
                    codex_toml.input = previous_input

            self.assertEqual(status, 0)
            self.assertEqual(path.read_text(encoding="utf-8"), "[features]\nhooks = true\n")

    def test_migrate_codex_feature_flag_exit_prints_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            original = "[features]\ncodex_hooks = true\n"
            path.write_text(original, encoding="utf-8")
            previous_input = getattr(codex_toml, "input", None)
            codex_toml.input = lambda _prompt: "exit"
            out = io.StringIO()
            try:
                with contextlib.redirect_stdout(out):
                    status = codex_toml._migrate_codex_feature_flag(path, True, True)
            finally:
                if previous_input is None:
                    delattr(codex_toml, "input")
                else:
                    codex_toml.input = previous_input

            self.assertEqual(status, 1)
            self.assertIn(str(path), out.getvalue())
            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_parse_render_plugins_round_trip(self):
        text = codex_toml.render_codex_plugins("", {"openai-developers@openai-developers": True})

        parsed = codex_toml.parse_codex_plugins(text)

        self.assertEqual(parsed, {"openai-developers@openai-developers": True})
        self.assertIn('[plugins."openai-developers@openai-developers"]', text)
        self.assertIn("enabled = true", text)

    def test_render_codex_plugins_preserves_unrelated_content(self):
        existing = (
            "model = \"gpt-5.5\"\n"
            "\n"
            "# a comment that must survive\n"
            "[projects.\"/home/user/repo\"]\n"
            "trust_level = \"trusted\"\n"
            "\n"
            "[plugins.\"gmail@openai-curated\"]\n"
            "enabled = false\n"
        )

        rendered = codex_toml.render_codex_plugins(existing, {"gmail@openai-curated": True, "new@marketplace": True})

        self.assertIn("model = \"gpt-5.5\"", rendered)
        self.assertIn("# a comment that must survive", rendered)
        self.assertIn("trust_level = \"trusted\"", rendered)
        self.assertIn('[plugins."new@marketplace"]', rendered)
        parsed = codex_toml.parse_codex_plugins(rendered)
        self.assertEqual(parsed["gmail@openai-curated"], True)
        self.assertEqual(parsed["new@marketplace"], True)

    def test_parse_codex_plugins_ignores_garbage(self):
        self.assertEqual(codex_toml.parse_codex_plugins("not { valid toml"), {})


class CliLoadLayerTests(unittest.TestCase):
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

            shared = cli._load_layer(shared_path, claude_path, codex_path)

            self.assertEqual(shared["download_link"], {"ide": "pycharm"})
            self.assertNotIn("download_link", hooks.render_claude(shared))
            self.assertNotIn("download_link", hooks.render_codex_hooks(shared))

    def test_load_layer_merges_hand_edited_codex_rules_and_plugins(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shared_path = root / "ai" / "tool-settings" / "settings.json"
            claude_path = root / ".claude" / "settings.json"
            codex_path = root / ".codex" / "hooks.json"
            rules_path = root / ".codex" / "rules" / "generated.rules"
            config_path = root / ".codex" / "config.toml"

            shared_path.parent.mkdir(parents=True)
            shared_path.write_text(
                '{"version": 1, "hooks": {}, "permissions": {"allow": [], "deny": []}, "enabledPlugins": {}}',
                encoding="utf-8",
            )
            rules_path.parent.mkdir(parents=True)
            rules_path.write_text(
                'prefix_rule(pattern = ["tree"], decision = "allow")\n',
                encoding="utf-8",
            )
            config_path.write_text(
                '[plugins."hand-added@marketplace"]\nenabled = true\n',
                encoding="utf-8",
            )

            shared = cli._load_layer(shared_path, claude_path, codex_path, rules_path, config_path)

            self.assertIn({"type": "bash", "command": "tree:*"}, shared["permissions"]["allow"])
            self.assertEqual(shared["enabledPlugins"], {"hand-added@marketplace": True})

            claude = hooks.render_claude(shared)
            self.assertIn("Bash(tree:*)", claude["permissions"]["allow"])


class CliApplyOrCheckTests(unittest.TestCase):
    def test_apply_or_check_writes_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shared_path = root / "ai" / "tool-settings" / "settings.json"
            claude_path = root / ".claude" / "settings.json"
            codex_path = root / ".codex" / "hooks.json"
            rules_path = root / ".codex" / "rules" / "generated.rules"
            config_path = root / ".codex" / "config.toml"

            shared_path.parent.mkdir(parents=True)
            shared_path.write_text(
                '{"version": 1, "hooks": {}, '
                '"permissions": {"allow": [{"type": "bash", "command": "tree:*"}], "deny": []}, '
                '"enabledPlugins": {"demo@marketplace": true}}',
                encoding="utf-8",
            )

            changed = cli._apply_or_check(shared_path, claude_path, codex_path, True, rules_path, config_path)

            self.assertIn(str(rules_path), changed)
            self.assertIn(str(config_path), changed)
            self.assertTrue(rules_path.is_file())
            self.assertTrue(config_path.is_file())
            self.assertIn('prefix_rule(pattern = ["tree"], decision = "allow")', rules_path.read_text(encoding="utf-8"))
            self.assertIn('[plugins."demo@marketplace"]', config_path.read_text(encoding="utf-8"))

            second_pass = cli._apply_or_check(shared_path, claude_path, codex_path, True, rules_path, config_path)
            self.assertEqual(second_pass, [])

    def test_exact_command_without_wildcard_does_not_duplicate_across_runs(self):
        # Regression test: `render_codex_rules` always emits a prefix rule (no
        # exact-match concept in Codex), so an exact Claude command like
        # "yarn" comes back out of `parse_codex_rules` as "yarn:*" — a
        # different-looking string. Reading that back naively as a "new"
        # permission would duplicate it, growing the list on every run.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shared_path = root / "ai" / "tool-settings" / "settings.json"
            claude_path = root / ".claude" / "settings.json"
            codex_path = root / ".codex" / "hooks.json"
            rules_path = root / ".codex" / "rules" / "generated.rules"
            config_path = root / ".codex" / "config.toml"

            shared_path.parent.mkdir(parents=True)
            shared_path.write_text(
                '{"version": 1, "hooks": {}, '
                '"permissions": {"allow": [{"type": "bash", "command": "yarn"}], "deny": []}, '
                '"enabledPlugins": {}}',
                encoding="utf-8",
            )

            for _ in range(3):
                cli._apply_or_check(shared_path, claude_path, codex_path, True, rules_path, config_path)

            shared = json.loads(shared_path.read_text(encoding="utf-8"))
            self.assertEqual(shared["permissions"]["allow"], [{"type": "bash", "command": "yarn"}])
            claude = json.loads(claude_path.read_text(encoding="utf-8"))
            self.assertEqual(claude["permissions"]["allow"], ["Bash(yarn)"])


class SkillsTests(unittest.TestCase):
    @contextlib.contextmanager
    def patched_skill_paths(self, root: Path):
        names = [
            "SHARED_SKILLS",
            "AGENTS_SKILLS",
            "CLAUDE_SKILLS",
            "CLAUDE_COMMANDS",
            "CODEX_COMMANDS",
        ]
        previous = {name: getattr(paths, name) for name in names}
        paths.SHARED_SKILLS = root / "ai" / "skills"
        paths.AGENTS_SKILLS = root / ".agents" / "skills"
        paths.CLAUDE_SKILLS = root / ".claude" / "skills"
        paths.CLAUDE_COMMANDS = root / ".claude" / "commands"
        paths.CODEX_COMMANDS = root / ".codex" / "commands"
        try:
            yield
        finally:
            for name, value in previous.items():
                setattr(paths, name, value)

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
                changed = skills._sync_skills(True)

            shared = root / "ai" / "skills" / "demo" / "SKILL.md"
            codex_skill = root / ".agents" / "skills" / "demo" / "SKILL.md"
            wrapper = root / ".claude" / "skills" / "demo" / "SKILL.md"
            self.assertIn(str(shared), changed)
            self.assertTrue(shared.is_file())
            self.assertIn('description: "Use demo: carefully."', shared.read_text(encoding="utf-8"))
            self.assertIn("Full command body.", shared.read_text(encoding="utf-8"))
            self.assertIn(paths.GENERATED_MARKER, codex_skill.read_text(encoding="utf-8"))
            self.assertIn(paths.GENERATED_MARKER, wrapper.read_text(encoding="utf-8"))
            self.assertIn(paths.GENERATED_MARKER, command.read_text(encoding="utf-8"))
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
                skills._render_claude_command_shim("demo", "Old shared source.", shared),
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
                skills._sync_skills(True)

            shared_text = shared.read_text(encoding="utf-8")
            self.assertIn("New Claude skill.", shared_text)
            self.assertIn("New body.", shared_text)
            self.assertIn(paths.GENERATED_MARKER, claude_skill.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
