"""Render tests driven by real debug payloads recorded during hook testing.

Input:  ai/°base/output/debug/20260624-152802_886401-save-decision.json  (Claude)
        ai/°base/output/debug/20260624-153111_724937-save-decision.json  (Codex)
Spec:   ai/°base/errors/15.expected.md
"""
from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
_HOOK_PATH = ROOT / "scripts" / "°base" / "ai" / "hooks" / "save-decision" / "hook.py"
_SPEC_PATH = ROOT / "ai" / "°base" / "errors" / "15.expected.md"

_CLAUDE_DEBUG = ROOT / "ai" / "°base" / "output" / "debug" / "20260624-152802_886401-save-decision.json"
_CODEX_DEBUG  = ROOT / "ai" / "°base" / "output" / "debug" / "20260624-153111_724937-save-decision.json"


def _load_hook():
    spec = importlib.util.spec_from_file_location("_save_decision_hook_15_test", _HOOK_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _parse_spec() -> tuple[str, str]:
    """Extract (claude_expected, codex_expected) from 15.expected.md.

    Uses the same ce+1 trick as test_save_decision.py to include the trailing
    blank line that _render_block emits.
    """
    text = _SPEC_PATH.read_text(encoding="utf-8")

    marker_claude = "# `query.md` addition (Claude)\n\n"
    marker_codex_header = "\n# Input (Codex)"
    marker_codex = "# `query.md` addition (Codex)\n\n"

    cs = text.index(marker_claude) + len(marker_claude)
    ce = text.index(marker_codex_header, cs)
    claude_expected = text[cs : ce + 1]  # +1 to include the trailing blank line

    ks = text.index(marker_codex) + len(marker_codex)
    codex_expected = text[ks:]

    return claude_expected, codex_expected


_hook = _load_hook()
_claude_expected, _codex_expected = _parse_spec()


class RenderFromDebugTests(unittest.TestCase):

    def test_claude_debug_payload(self):
        """Claude payload from debug file renders to the spec in 15.expected.md."""
        payload = json.loads(_CLAUDE_DEBUG.read_text(encoding="utf-8"))
        questions = _hook.parse_payload(payload)
        actual = _hook._render_block(questions, is_codex=False)
        self.assertEqual(actual, _claude_expected)

    def test_codex_debug_payload(self):
        """Codex payload from debug file renders to the spec in 15.expected.md."""
        payload = json.loads(_CODEX_DEBUG.read_text(encoding="utf-8"))
        questions = _hook.parse_payload(payload)
        actual = _hook._render_block(questions, is_codex=True)
        self.assertEqual(actual, _codex_expected)


if __name__ == "__main__":
    unittest.main()
