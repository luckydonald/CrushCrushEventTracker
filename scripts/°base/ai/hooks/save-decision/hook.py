#!/usr/bin/env python3
"""PostToolUse hook for AskUserQuestion / request_user_input: append the asked
question(s) and the picked answer to ai/query.md as a markdown blockquote, then commit.

Usage: hook.py [ai_tool_name]   (accepted for parity with save-prompt; unused here)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic import BaseModel, StrictBool, StrictInt, computed_field

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _lib import append_and_commit, dump_debug_payload, read_payload, resolve_log_path, slugify  # noqa: E402


class Choice(BaseModel):
    label: str = ""
    description: str = ""
    preview: str = ""
    selection: StrictBool | StrictInt = False
    # False       → not selected
    # True        → selected, order unknown (single-select)
    # 1, 2, 3 …  → selected, 1-based click order (multi-select)
    # bool(selection) is always the correct "is selected" check
    note: str = ""          # free text / annotation note — Other entry only
    is_other: bool = False  # True for the parser-injected Other/Notes row

    @computed_field
    @property
    def selected(self) -> bool:
        return bool(self.selection)


class Question(BaseModel):
    question: str
    header: str = ""
    multi_select: bool = False
    choices: list[Choice]  # predefined options + one parser-injected Other at end

    @computed_field
    @property
    def selected(self) -> list[Choice]:
        return sorted(
            (c for c in self.choices if c.selected),
            key=lambda c: c.selection,
        )

    @computed_field
    @property
    def timed_out(self) -> bool:
        return not self.selected


Choice.model_rebuild()
Question.model_rebuild()


def _greedy_match(answer: str, labels: list[str]) -> tuple[list[str], str]:
    """Greedy left-to-right match of labels against the answer string.

    Returns (click_order, custom_text) where custom_text is the leftover after
    all matched labels are consumed.
    """
    available = list(labels)
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


def _parse_claude(payload: dict) -> list[Question]:
    """Parse a Claude Code AskUserQuestion payload into a list of Questions."""
    tool_input = payload.get("tool_input") or {}
    if not tool_input and isinstance(payload.get("questions"), list):
        tool_input = {"questions": payload["questions"]}
    raw_questions = tool_input.get("questions") or []

    raw_response = payload.get("tool_response") or {}
    if isinstance(raw_response, str):
        try:
            raw_response = json.loads(raw_response)
        except (json.JSONDecodeError, ValueError):
            raw_response = {}
    if not isinstance(raw_response, dict):
        raw_response = {}

    raw_answers: dict = raw_response.get("answers") or {}
    raw_annotations: dict = raw_response.get("annotations") or {}

    questions: list[Question] = []
    for q in raw_questions:
        if not isinstance(q, dict):
            continue
        qtext = q.get("question", "")
        raw_opts = [o for o in (q.get("options") or []) if isinstance(o, dict)]
        multi = bool(q.get("multiSelect", False))
        answer_str = raw_answers.get(qtext, "")
        raw_ann = raw_annotations.get(qtext) or {}
        ann_notes = raw_ann.get("notes", "")
        notes_only = answer_str == "(notes only)"

        if multi:
            labels = [o.get("label", "") for o in raw_opts]
            click_order, custom_text = _greedy_match(answer_str, labels)
            rank_map = {label: rank for rank, label in enumerate(click_order, 1)}
            choices: list[Choice] = [
                Choice(
                    label=o.get("label", ""),
                    description=o.get("description", ""),
                    preview=o.get("preview", ""),
                    selection=rank_map.get(o.get("label", ""), False),
                )
                for o in raw_opts
            ]
            other_sel: StrictBool | StrictInt = True if custom_text else False
            choices.append(Choice(is_other=True, selection=other_sel, note=custom_text))
        else:
            choices = [
                Choice(
                    label=o.get("label", ""),
                    description=o.get("description", ""),
                    preview=o.get("preview", ""),
                    selection=not notes_only and o.get("label", "") == answer_str,
                )
                for o in raw_opts
            ]
            choices.append(Choice(
                is_other=True,
                selection=notes_only,
                note=ann_notes if notes_only else "",
            ))

        questions.append(Question(
            question=qtext,
            header=q.get("header", ""),
            multi_select=multi,
            choices=choices,
        ))
    return questions


def _parse_codex(payload: dict) -> list[Question]:
    """Parse a Codex request_user_input payload into a list of Questions."""
    tool_input = payload.get("tool_input") or {}
    raw_questions = tool_input.get("questions") or []

    raw_response = payload.get("tool_response") or "{}"
    if isinstance(raw_response, str):
        try:
            codex_answers: dict = json.loads(raw_response).get("answers") or {}
        except (json.JSONDecodeError, ValueError):
            codex_answers = {}
    elif isinstance(raw_response, dict):
        codex_answers = raw_response.get("answers") or {}
    else:
        codex_answers = {}

    questions: list[Question] = []
    for q in raw_questions:
        if not isinstance(q, dict):
            continue
        qid = q.get("id", "")
        qtext = q.get("question", "")
        raw_opts = [o for o in (q.get("options") or []) if isinstance(o, dict)]
        multi = bool(q.get("multiSelect", False))

        raw_ans = codex_answers.get(qid)  # None when key absent (timeout)
        if raw_ans is None:
            items: list[str] | None = None
        else:
            items = raw_ans.get("answers") or [] if isinstance(raw_ans, dict) else []

        if items is None:
            notes = ""
            selected_labels: list[str] = []
            none_of_above = False
        else:
            notes = "; ".join(
                i[len("user_note: "):]
                for i in items
                if isinstance(i, str) and i.startswith("user_note: ")
            )
            none_of_above = "None of the above" in items
            selected_labels = [
                i for i in items
                if isinstance(i, str)
                and not i.startswith("user_note: ")
                and i != "None of the above"
            ]

        if multi:
            rank_map = {label: rank for rank, label in enumerate(selected_labels, 1)}
            choices: list[Choice] = [
                Choice(
                    label=o.get("label", ""),
                    description=o.get("description", ""),
                    selection=rank_map.get(o.get("label", ""), False),
                )
                for o in raw_opts
            ]
            if items is not None and (notes or none_of_above):
                other_sel: StrictBool | StrictInt = True
                other_note = notes
            else:
                other_sel = False
                other_note = ""
            choices.append(Choice(is_other=True, selection=other_sel, note=other_note))
        else:
            # For Codex single-select: when a predefined label is selected and a note
            # is present, the note belongs on that choice (not on Other). Other is only
            # selected for "None of the above" or when no predefined choice was picked.
            has_predefined_selection = bool(selected_labels)
            choices = [
                Choice(
                    label=o.get("label", ""),
                    description=o.get("description", ""),
                    selection=o.get("label", "") in selected_labels,
                    note=(
                        notes
                        if (o.get("label", "") in selected_labels and not none_of_above)
                        else ""
                    ),
                )
                for o in raw_opts
            ]
            other_selected = items is not None and (
                none_of_above or (not has_predefined_selection and bool(notes))
            )
            other_note = notes if (none_of_above or not has_predefined_selection) else ""
            choices.append(Choice(
                is_other=True,
                selection=other_selected,
                note=other_note,
            ))

        questions.append(Question(
            question=qtext,
            header=q.get("header", ""),
            multi_select=multi,
            choices=choices,
        ))
    return questions


def parse_payload(payload: dict) -> list[Question]:
    """Dispatch to the correct parser based on tool_name in the hook payload."""
    if payload.get("tool_name") == "request_user_input":
        return _parse_codex(payload)
    return _parse_claude(payload)


def _render_preview_block(preview: str, lang: str, out: list[str]) -> None:
    """Append a fenced code block for a preview field inside a blockquote list."""
    out.append(f">   - ```{lang}\n")
    for line in preview.splitlines():
        if line:
            out.append(f">     {line}\n")
        else:
            out.append(">\n")
    out.append(">     ```\n")


def _render_block(questions: list[Question], *, is_codex: bool = False) -> str:
    total = len(questions)
    out: list[str] = []
    glyph = "›" if is_codex else "❯"
    out.append(f"{glyph} Question answered.\n")
    out.append("> <details><summary>\n")
    out.append(">\n")

    # --- Summary ---
    for i, q in enumerate(questions, 1):
        indent = len(str(i)) + 3
        other = next((c for c in q.choices if c.is_other), None)

        out.append(f">> {i}. {q.question}\n")

        if q.multi_select:
            pred_selected = [c for c in q.selected if not c.is_other]
            items_to_show = [c.label for c in pred_selected]
            if other and other.selected:
                items_to_show.append(
                    f"_Other_: {other.note}" if other.note else "_Other_"
                )
            if items_to_show:
                for item in items_to_show:
                    out.append(f">>{'':>{indent}}- {item}\n")
            else:
                out.append(f">>{'':>{indent}}-\n")
        else:
            if other and other.selected:
                display = f"_Other_: {other.note}" if other.note else "_Other_"
            elif q.selected and not q.selected[0].is_other:
                display = q.selected[0].label
            else:
                display = ""
            out.append(f">>{'':>{indent}}- {display}\n")

            # Preview block (single-select only, when selected choice has a preview)
            if q.selected and not q.selected[0].is_other and q.selected[0].preview:
                pi = indent + 2
                out.append(f">>{'':>{pi}}```text\n")
                for pline in q.selected[0].preview.splitlines():
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

        pred_choices = [c for c in q.choices if not c.is_other]
        other = next((c for c in q.choices if c.is_other), None)
        has_any_preview = any(c.preview for c in pred_choices)
        last_pred_idx = len(pred_choices) - 1

        select_type = "Multi Select" if q.multi_select else "Single Select"
        out.append(f">> **{q.header}** ({i}/{total}) <kbd>{select_type}</kbd><br>\n")
        out.append(f">> {q.question}\n")

        if q.multi_select:
            for n, choice in enumerate(pred_choices, 1):
                check = "[x]" if choice.selected else "[ ]"
                rank_badge = (
                    f" <sup><sub><kbd>#{choice.selection}</kbd></sub></sup>"
                    if isinstance(choice.selection, int) and not isinstance(choice.selection, bool)
                    else ""
                )
                out.append(f"> - {check} {n}\\. {choice.label}{rank_badge}\n")
                if choice.description:
                    out.append(f">   - _{choice.description}_\n")
                if choice.preview:
                    lang = "text" if (n - 1) == last_pred_idx else ""
                    _render_preview_block(choice.preview, lang, out)

            other_n = len(pred_choices) + 1
            if other and other.note:
                other_check = "[ ]" if other.note.endswith("?") else "[x]"
                other_label = "_Type something:_"
            else:
                other_check = "[ ]"
                other_label = "_Type something._"
            out.append(f"> - {other_check} {other_n}\\. {other_label}\n")
            if other and other.note:
                out.append(f">   - > {other.note}\n")

        else:
            # Suppress [x] when the selected choice has a preview —
            # the preview display serves as the visual selection indicator.
            selected_has_preview = bool(
                q.selected and not q.selected[0].is_other and q.selected[0].preview
            )

            for n, choice in enumerate(pred_choices, 1):
                check = "[x]" if choice.selected and not selected_has_preview else "[ ]"
                out.append(f"> - {check} {n}\\. {choice.label}\n")
                if choice.description:
                    out.append(f">   - _{choice.description}_\n")
                if choice.note:
                    out.append(f">   - > {choice.note}\n")
                if choice.preview:
                    lang = "text" if (n - 1) == last_pred_idx else ""
                    _render_preview_block(choice.preview, lang, out)

            other_n = len(pred_choices) + 1
            if other and other.selected and other.note:
                other_check = "[x]"
                other_label = "_Notes:_" if has_any_preview else "_Type something:_"
                other_text = other.note
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


def main() -> int:
    _ = sys.argv[1] if len(sys.argv) > 1 else "unknown"  # accepted for parity, unused

    payload = read_payload()
    dump_debug_payload(payload, "save-decision")

    questions = parse_payload(payload)
    if not questions:
        return 0

    is_codex = payload.get("tool_name") == "request_user_input"
    block = _render_block(questions, is_codex=is_codex)
    slug = slugify(questions[0].question, fallback="decision")

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
