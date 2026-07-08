#!/usr/bin/env python3
"""Unit tests for the todo-capture feature in save-plan/hook.py.

Covers: _normalize_todos, _render_todos_markdown, _apply_todos_section, and
the end-to-end _handle_todo_capture dispatch (TodoWrite/update_todo →
inject/update a "## Todos" section into the session's saved plan snapshot).
"""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
_HOOK_PATH = ROOT / "scripts" / "°base" / "ai" / "hooks" / "save-plan" / "hook.py"


def _load_hook():
    spec = importlib.util.spec_from_file_location("_save_plan_hook_todo_test", _HOOK_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_hook = _load_hook()


class NormalizeTodosTests(unittest.TestCase):
    def test_claude_todo_write_shape(self):
        tool_input = {
            "todos": [
                {"content": "Do A", "status": "done", "activeForm": "Doing A"},
                {"content": "Do B", "status": "in_progress", "activeForm": "Doing B"},
                {"content": "Do C", "status": "pending", "activeForm": "Doing C"},
            ]
        }
        todos = _hook._normalize_todos(tool_input)
        self.assertEqual(
            todos,
            [
                {"text": "Do A", "status": "done"},
                {"text": "Do B", "status": "in_progress"},
                {"text": "Do C", "status": "pending"},
            ],
        )

    def test_alternate_field_names_defensive(self):
        tool_input = {"items": [{"title": "Do X", "status": "blocked"}]}
        todos = _hook._normalize_todos(tool_input)
        self.assertEqual(todos, [{"text": "Do X", "status": "blocked"}])

    def test_missing_text_skipped(self):
        tool_input = {"todos": [{"status": "pending"}]}
        self.assertEqual(_hook._normalize_todos(tool_input), [])

    def test_no_todos_key_returns_empty(self):
        self.assertEqual(_hook._normalize_todos({}), [])

    def test_missing_status_defaults_pending(self):
        tool_input = {"todos": [{"content": "Do A"}]}
        self.assertEqual(_hook._normalize_todos(tool_input), [{"text": "Do A", "status": "pending"}])


class RenderTodosMarkdownTests(unittest.TestCase):
    def test_empty_returns_empty_string(self):
        self.assertEqual(_hook._render_todos_markdown([]), "")

    def test_renders_checkboxes_by_status(self):
        todos = [
            {"text": "Done thing", "status": "done"},
            {"text": "Active thing", "status": "in_progress"},
            {"text": "Waiting thing", "status": "pending"},
            {"text": "Stuck thing", "status": "blocked"},
        ]
        md = _hook._render_todos_markdown(todos)
        self.assertIn("## Todos", md)
        self.assertIn("- [x] Done thing", md)
        self.assertIn("- [ ] Active thing *(in progress)*", md)
        self.assertIn("- [ ] Waiting thing", md)
        self.assertNotIn("[ ] Waiting thing *(", md)
        self.assertIn("- [ ] Stuck thing *(blocked)*", md)


class ApplyTodosSectionTests(unittest.TestCase):
    def test_appends_when_no_existing_section(self):
        plan = "# Plan: Foo\n\nSome content.\n"
        todos_md = "## Todos\n\n- [ ] Do A"
        result = _hook._apply_todos_section(plan, todos_md)
        self.assertTrue(result.startswith("# Plan: Foo\n\nSome content.\n\n## Todos"))
        self.assertIn("- [ ] Do A", result)

    def test_replaces_existing_section_in_place(self):
        plan = (
            "# Plan: Foo\n\nSome content.\n\n"
            "## Todos\n\n- [ ] Old item\n\n"
            "## Notes\n\nMore stuff.\n"
        )
        todos_md = "## Todos\n\n- [x] New item"
        result = _hook._apply_todos_section(plan, todos_md)
        self.assertIn("- [x] New item", result)
        self.assertNotIn("Old item", result)
        self.assertIn("## Notes\n\nMore stuff.", result)

    def test_idempotent_on_repeated_apply(self):
        plan = "# Plan: Foo\n\nSome content.\n"
        todos_md = "## Todos\n\n- [ ] Do A"
        once = _hook._apply_todos_section(plan, todos_md)
        twice = _hook._apply_todos_section(once, todos_md)
        self.assertEqual(once, twice)


class HandleTodoCaptureTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.tmp_path = Path(self.tmpdir.name)

        state_patch = mock.patch.object(_hook, "_STATE_FILE", self.tmp_path / "state.json")
        state_patch.start()
        self.addCleanup(state_patch.stop)

        commit_patch = mock.patch.object(_hook, "_commit")
        self.mock_commit = commit_patch.start()
        self.addCleanup(commit_patch.stop)

    def _write_state(self, session_id: str, relpath: str, prefix: str = "042") -> None:
        _hook._save_state({session_id: {"prefix": prefix, "relpath": relpath, "source": "plan.md"}})

    def test_no_session_id_is_noop(self):
        self.assertEqual(_hook._handle_todo_capture("", {"todos": [{"content": "A", "status": "pending"}]}), 0)
        self.mock_commit.assert_not_called()

    def test_unknown_session_is_noop(self):
        self._write_state("other-session", "somewhere.md")
        result = _hook._handle_todo_capture("session-1", {"todos": [{"content": "A", "status": "pending"}]})
        self.assertEqual(result, 0)
        self.mock_commit.assert_not_called()

    def test_missing_plan_file_is_noop(self):
        self._write_state("session-1", str(self.tmp_path / "missing.md"))
        result = _hook._handle_todo_capture("session-1", {"todos": [{"content": "A", "status": "pending"}]})
        self.assertEqual(result, 0)
        self.mock_commit.assert_not_called()

    def test_no_todos_is_noop(self):
        plan_path = self.tmp_path / "042_test-plan.md"
        plan_path.write_text("# Plan: Test\n", encoding="utf-8")
        self._write_state("session-1", str(plan_path))
        result = _hook._handle_todo_capture("session-1", {"todos": []})
        self.assertEqual(result, 0)
        self.mock_commit.assert_not_called()

    def test_injects_todos_and_commits(self):
        plan_path = self.tmp_path / "042_test-plan.md"
        plan_path.write_text("# Plan: Test\n\nBody text.\n", encoding="utf-8")
        self._write_state("session-1", str(plan_path))
        tool_input = {"todos": [{"content": "Do A", "status": "in_progress"}]}
        result = _hook._handle_todo_capture("session-1", tool_input)
        self.assertEqual(result, 0)
        updated = plan_path.read_text(encoding="utf-8")
        self.assertIn("## Todos", updated)
        self.assertIn("- [ ] Do A *(in progress)*", updated)
        self.mock_commit.assert_called_once()
        args, _ = self.mock_commit.call_args
        self.assertEqual(args[0], [str(plan_path)])

    def test_unchanged_content_skips_commit(self):
        plan_path = self.tmp_path / "042_test-plan.md"
        plan_path.write_text("# Plan: Test\n\n## Todos\n\n- [ ] Do A\n", encoding="utf-8")
        self._write_state("session-1", str(plan_path))
        tool_input = {"todos": [{"content": "Do A", "status": "pending"}]}
        result = _hook._handle_todo_capture("session-1", tool_input)
        self.assertEqual(result, 0)
        self.mock_commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
