#!/usr/bin/env python3
"""Unit tests for the Copilot ask_user parser in save-decision/hook.py.

Tests parse_payload() with Copilot-format payloads (tool_name = "ask_user")
and asserts on the resulting list[Question] model attributes. Copilot's
ask_user schema is much simpler than Claude's AskUserQuestion: a single
question, a flat list of choice strings, and an allow_freeform flag
(instead of multiSelect / per-choice label+description+preview).
"""
from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
_HOOK_PATH = ROOT / "scripts" / "°base" / "ai" / "hooks" / "save-decision" / "hook.py"


def _load_hook():
    spec = importlib.util.spec_from_file_location("_save_decision_hook_copilot_test", _HOOK_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_hook = _load_hook()


def _make_payload(question, choices, allow_freeform, answer):
    return {
        "tool_name": "ask_user",
        "tool_input": {"question": question, "choices": choices, "allow_freeform": allow_freeform},
        "tool_response": answer,
    }


class ParseCopilotTests(unittest.TestCase):
    def test_dispatches_to_copilot_parser(self):
        payload = _make_payload("Pick one", ["A", "B"], True, "A")
        questions = _hook.parse_payload(payload)
        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0].question, "Pick one")

    def test_selects_matching_choice(self):
        payload = _make_payload("Pick one", ["A", "B", "C"], True, "B")
        [q] = _hook.parse_payload(payload)
        selected = [c.label for c in q.choices if c.selected and not c.is_other]
        self.assertEqual(selected, ["B"])
        self.assertFalse(q.multi_select)

    def test_freeform_answer_lands_in_other(self):
        payload = _make_payload("Pick one", ["A", "B"], True, "Something else entirely")
        [q] = _hook.parse_payload(payload)
        other = next(c for c in q.choices if c.is_other)
        self.assertTrue(other.selected)
        self.assertEqual(other.note, "Something else entirely")
        self.assertFalse(any(c.selected for c in q.choices if not c.is_other))

    def test_no_freeform_when_disallowed_and_no_match(self):
        payload = _make_payload("Pick one", ["A", "B"], False, "Not a listed choice")
        [q] = _hook.parse_payload(payload)
        other = next(c for c in q.choices if c.is_other)
        self.assertFalse(other.selected)

    def test_timed_out_when_no_answer(self):
        payload = _make_payload("Pick one", ["A", "B"], True, "")
        [q] = _hook.parse_payload(payload)
        self.assertTrue(q.timed_out)

    def test_json_object_tool_response(self):
        payload = _make_payload("Pick one", ["A", "B"], True, json.dumps({"answer": "A"}))
        [q] = _hook.parse_payload(payload)
        selected = [c.label for c in q.choices if c.selected and not c.is_other]
        self.assertEqual(selected, ["A"])


class RenderCopilotGlyphTests(unittest.TestCase):
    def test_copilot_glyph_used_for_ask_user(self):
        payload = _make_payload("Pick one", ["A", "B"], True, "A")
        questions = _hook.parse_payload(payload)
        block = _hook._render_block(questions, tool="copilot")
        self.assertTrue(block.startswith("◆ Question answered.\n"))


if __name__ == "__main__":
    unittest.main()
