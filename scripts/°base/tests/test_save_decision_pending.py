"""Tests for the pending-decision marker mechanism added to save-decision/hook.py:
capturing an AskUserQuestion call at PreToolUse time so a canceled ("chat about
this") question is still recorded even though Claude Code fires no PostToolUse,
PostToolUseFailure, or PermissionDenied hook for a manual denial. See
scripts/°base/ai/hooks/_lib.py's write_pending_decision/sweep_pending_decisions.
"""
from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path

_routing = importlib.import_module("scripts.°base.tests.test_ai_hooks_base_routing")
DECISION_HOOK = _routing.DECISION_HOOK
init_repo = _routing.init_repo
last_subject = _routing.last_subject
run_hook = _routing.run_hook

QUESTIONS = [
    {
        "question": "Pick one?",
        "header": "Test",
        "multiSelect": False,
        "options": [
            {"label": "A", "description": "first"},
            {"label": "B", "description": "second"},
        ],
    }
]


def _pending_dir(repo: Path) -> Path:
    return repo / "ai" / "output" / ".pending-decisions"


def _query_md(repo: Path) -> Path:
    return repo / "ai" / "query.md"


class PendingDecisionTests(unittest.TestCase):
    def test_pre_tool_use_writes_marker_without_touching_query_md(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")

            run_hook(
                repo,
                DECISION_HOOK,
                {
                    "hook_event_name": "PreToolUse",
                    "tool_name": "AskUserQuestion",
                    "tool_use_id": "toolu_pending_1",
                    "tool_input": {"questions": QUESTIONS},
                },
                "claude",
            )

            markers = list(_pending_dir(repo).glob("*.md"))
            self.assertEqual(len(markers), 1)
            self.assertIn("Pick one?", markers[0].read_text(encoding="utf-8"))
            self.assertIn("canceled", markers[0].read_text(encoding="utf-8"))
            self.assertFalse(_query_md(repo).exists())

    def test_post_tool_use_deletes_marker_and_renders_answered(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")

            run_hook(
                repo,
                DECISION_HOOK,
                {
                    "hook_event_name": "PreToolUse",
                    "tool_name": "AskUserQuestion",
                    "tool_use_id": "toolu_pending_2",
                    "tool_input": {"questions": QUESTIONS},
                },
                "claude",
            )
            self.assertEqual(len(list(_pending_dir(repo).glob("*.md"))), 1)

            run_hook(
                repo,
                DECISION_HOOK,
                {
                    "hook_event_name": "PostToolUse",
                    "tool_name": "AskUserQuestion",
                    "tool_use_id": "toolu_pending_2",
                    "tool_input": {"questions": QUESTIONS},
                    "tool_response": {"answers": {"Pick one?": "A"}},
                },
                "claude",
            )

            self.assertEqual(list(_pending_dir(repo).glob("*.md")), [])
            content = _query_md(repo).read_text(encoding="utf-8")
            self.assertIn("Question answered", content)
            self.assertNotIn("canceled", content)

    def test_stop_sweeps_leftover_marker_as_canceled(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")

            run_hook(
                repo,
                DECISION_HOOK,
                {
                    "hook_event_name": "PreToolUse",
                    "tool_name": "AskUserQuestion",
                    "tool_use_id": "toolu_pending_3",
                    "tool_input": {"questions": QUESTIONS},
                },
                "claude",
            )

            # No matching PostToolUse ever fires (user picked "chat about this").
            run_hook(repo, DECISION_HOOK, {"hook_event_name": "Stop"}, "claude")

            self.assertEqual(list(_pending_dir(repo).glob("*.md")), [])
            content = _query_md(repo).read_text(encoding="utf-8")
            self.assertIn("Question canceled (chat about this)", content)
            self.assertIn("Pick one?", content)
            self.assertEqual(last_subject(repo), "ai: save canceled decision")

    def test_stop_is_a_noop_when_nothing_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")

            before = last_subject(repo)
            run_hook(repo, DECISION_HOOK, {"hook_event_name": "Stop"}, "claude")

            self.assertEqual(last_subject(repo), before)
            self.assertFalse(_query_md(repo).exists())


if __name__ == "__main__":
    unittest.main()
