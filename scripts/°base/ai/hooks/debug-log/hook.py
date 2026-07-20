#!/usr/bin/env python3
"""Reusable raw-payload debug logger, wireable to any hook event.

Unlike the other hooks under `ai/hooks/`, this one does nothing but the
`dump_debug_payload` step every other hook already does internally: read the
JSON payload from stdin and, if the `.debug` marker file exists
(`ai[/°base]/.debug`), write it verbatim to `ai[/°base]/output/debug/`.

Purpose: probe undocumented/unclear hook payload shapes (e.g. `SubagentStop`,
`TaskCreated`, `TaskCompleted`, `Notification`) before writing real parsing
logic against them, by wiring this single script to several events at once —
the dumped filename is labeled from the payload's own `hook_event_name` field
(falling back to an explicit CLI arg, then to "debug"), so one script covers
every event without per-event copies.

Not meant to stay wired long-term for events that already have a real
handler (e.g. `UserPromptSubmit` -> `save-prompt/hook.py`) — this is a
throwaway probe, remove the wiring once the target event's payload shape is
understood and a real hook has been written for it.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _lib import dump_debug_payload, read_payload  # noqa: E402


def main() -> int:
    payload = read_payload()
    label = payload.get("hook_event_name") or (sys.argv[1] if len(sys.argv) > 1 else "debug")
    dump_debug_payload(payload, str(label))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())