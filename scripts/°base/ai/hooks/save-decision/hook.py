#!/usr/bin/env python3
"""PostToolUse hook for AskUserQuestion: append the asked question(s) and the
picked answer to ai/query.md as a markdown blockquote, then commit.

Usage: hook.py [ai_tool_name]   (currently unused; accepted for parity with save-prompt)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _lib import append_and_commit, dump_debug_payload, read_payload, resolve_log_path, slugify  # noqa: E402


def _parse_multi_answer(answer: str, options: list[dict]) -> tuple[list[str], str]:
    """Greedy left-to-right match of option labels against the answer string.

    Returns (click_order, custom_text) where click_order lists matched labels
    in the order they appear in answer, and custom_text is the leftover.
    """
    available = [o.get("label", "") for o in options]
    remaining = answer
    click_order: list[str] = []
    while remaining:
        matched = False
        for label in available:
            if not label:
                continue
            if remaining == label or remaining.startswith(label + ", "):
                click_order.append(label)
                available.remove(label)
                remaining = remaining[len(label):]
                if remaining.startswith(", "):
                    remaining = remaining[2:]
                matched = True
                break
        if not matched:
            break
    return click_order, remaining


def _render_preview_block(preview: str, lang: str, out: list[str]) -> None:
    """Append a fenced code block for a preview field inside a blockquote list."""
    out.append(f">   - ```{lang}\n")
    for line in preview.splitlines():
        if line:
            out.append(f">     {line}\n")
        else:
            out.append(">\n")
    out.append(">     ```\n")


def _render_block(tool_input: dict, tool_response: dict) -> str:
    questions = tool_input.get("questions") or []
    answers = tool_response.get("answers") or {}
    annotations = tool_response.get("annotations") or {}
    total = len(questions)

    out: list[str] = []
    out.append("❯ Question answered.\n")
    out.append("> <details><summary>\n")
    out.append(">\n")

    # --- Summary ---
    for i, q in enumerate(questions, 1):
        qtext = q.get("question", "")
        ann = annotations.get(qtext, {})
        answer = answers.get(qtext, "")
        indent = len(str(i)) + 3

        out.append(f">> {i}. {qtext}\n")

        display = ann["notes"] if ann.get("notes") else answer
        out.append(f">>{'':>{indent}}- {display}\n")

        if ann.get("preview"):
            pi = indent + 2
            out.append(f">>{'':>{pi}}```text\n")
            for pline in ann["preview"].splitlines():
                out.append(f">>{'':>{pi}}{pline}\n")
            out.append(f">>{'':>{pi}}```\n")

    out.append(">\n")
    out.append("> (click to expand)\n")
    out.append(">\n")
    out.append("> </summary>\n")
    out.append(">\n")

    # --- Details ---
    for i, q in enumerate(questions, 1):
        if i > 1:
            out.append(">\n")

        qtext = q.get("question", "")
        header = q.get("header", "")
        opts = q.get("options") or []
        multi = q.get("multiSelect", False)
        answer = answers.get(qtext, "")
        ann = annotations.get(qtext, {})

        select_type = "Multi Select" if multi else "Single Select"
        out.append(f">> **{header}** ({i}/{total}) <kbd>{select_type}</kbd><br>\n")
        out.append(f">> {qtext}\n")

        has_any_preview = any(o.get("preview") for o in opts)
        last_idx = len(opts) - 1

        if multi:
            click_order, custom_text = _parse_multi_answer(answer, opts)
            rank_map = {label: rank for rank, label in enumerate(click_order, 1)}

            for n, opt in enumerate(opts, 1):
                label = opt.get("label", "")
                desc = opt.get("description", "")
                preview = opt.get("preview", "")
                rank = rank_map.get(label)
                check = "[x]" if rank else "[ ]"
                badge = f" <sup><sub><kbd>#{rank}</kbd></sub></sup>" if rank else ""
                out.append(f"> - {check} {n}\\. {label}{badge}\n")
                if desc:
                    out.append(f">   - _{desc}_\n")
                if preview:
                    lang = "text" if (n - 1) == last_idx else ""
                    _render_preview_block(preview, lang, out)

            other_n = len(opts) + 1
            if custom_text:
                other_check = "[ ]" if custom_text.endswith("?") else "[x]"
                other_label = "_Type something:_"
            else:
                other_check = "[ ]"
                other_label = "_Type something._"
            out.append(f"> - {other_check} {other_n}\\. {other_label}\n")
            if custom_text:
                out.append(f">   - > {custom_text}\n")

        else:
            notes_only = answer == "(notes only)"
            has_preview_ann = bool(ann.get("preview"))
            selected_label = None if (notes_only or has_preview_ann) else answer

            for n, opt in enumerate(opts, 1):
                label = opt.get("label", "")
                desc = opt.get("description", "")
                preview = opt.get("preview", "")
                check = "[x]" if label == selected_label else "[ ]"
                out.append(f"> - {check} {n}\\. {label}\n")
                if desc:
                    out.append(f">   - _{desc}_\n")
                if preview:
                    lang = "text" if (n - 1) == last_idx else ""
                    _render_preview_block(preview, lang, out)

            other_n = len(opts) + 1
            if notes_only:
                other_check = "[x]"
                other_label = "_Notes:_"
                other_text = ann.get("notes", "")
            elif has_any_preview:
                other_check = "[ ]"
                other_label = "_Notes: Add notes on this design._"
                other_text = ""
            else:
                other_check = "[ ]"
                other_label = "_Type something._"
                other_text = ""
            out.append(f"> - {other_check} {other_n}\\. {other_label}\n")
            if other_text:
                out.append(f">   - > {other_text}\n")

    out.append(">\n")
    out.append("> </details>\n")
    out.append(">\n")
    out.append("\n")
    return "".join(out)


def _normalize_codex_answers(questions: list[dict], tool_response: dict) -> dict:
    """Normalize Codex answer format to Claude Code format when needed.

    Codex:  tool_response["answers"][qid]   = {"answers": ["Label", "user_note: text"]}
    Claude: tool_response["answers"][qtext] = "Label"  (+ separate annotations dict)

    Returns tool_response unchanged if it is already in Claude Code format.
    """
    raw_answers = tool_response.get("answers") or {}
    if not raw_answers:
        return tool_response

    first_val = next(iter(raw_answers.values()))
    if not isinstance(first_val, dict) or "answers" not in first_val:
        return tool_response  # already Claude Code format

    id_to_q = {q.get("id", ""): q for q in questions if q.get("id")}

    norm_answers: dict[str, str] = {}
    norm_annotations: dict[str, dict] = {}

    for qid, raw in raw_answers.items():
        q = id_to_q.get(qid)
        qtext = q.get("question", qid) if q else qid
        items = raw.get("answers") or [] if isinstance(raw, dict) else []

        notes = [i[len("user_note: "):] for i in items if isinstance(i, str) and i.startswith("user_note: ")]
        labels = [i for i in items if isinstance(i, str) and not i.startswith("user_note: ") and i != "None of the above"]

        if labels:
            norm_answers[qtext] = ", ".join(labels)
        elif notes:
            norm_answers[qtext] = "(notes only)"
        # "None of the above" with no note → nothing selected, omit

        if notes:
            norm_annotations[qtext] = {"notes": "; ".join(notes)}

    result = dict(tool_response)
    result["answers"] = norm_answers
    if norm_annotations:
        result["annotations"] = norm_annotations
    return result


def main() -> int:
    payload = read_payload()
    dump_debug_payload(payload, "save-decision")
    tool_input = payload.get("tool_input") or {}
    if not tool_input and isinstance(payload.get("questions"), list):
        tool_input = {"questions": payload.get("questions") or []}
    questions = tool_input.get("questions") or []
    if not questions:
        return 0

    raw_response = payload.get("tool_response")
    # Codex sends tool_response as a JSON string; Claude Code sends a dict.
    if isinstance(raw_response, str):
        try:
            raw_response = json.loads(raw_response)
        except (json.JSONDecodeError, ValueError):
            raw_response = {}
    tool_response = raw_response if isinstance(raw_response, dict) else {}
    tool_response = _normalize_codex_answers(questions, tool_response)
    block = _render_block(tool_input, tool_response)

    first_question = questions[0].get("question", "") if isinstance(questions[0], dict) else ""
    slug = slugify(first_question, fallback="decision")

    log_path = resolve_log_path("ai/query.md", "ai/°base/query.md")
    append_and_commit(
        log_path,
        block,
        commit_template_relpath="ai/commit-templates/decision.md",
        default_commit_msg=f"ai: save decision {slug}",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
