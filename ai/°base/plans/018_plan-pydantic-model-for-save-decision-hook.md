# Plan: Pydantic model for save-decision hook

## Context

`save-decision/hook.py` currently parses two structurally different wire formats
(Claude Code `AskUserQuestion` and Codex `request_user_input`) through raw dict
lookups and a normalization function that re-serialises back to dicts.
`_render_block` then guesses keys again when rendering.

Goal: two flat Pydantic models that both parsers fill and `_render_block` reads
via attributes.

---

## Model design  (top of `save-decision/hook.py`)

```python
from pydantic import BaseModel, Field

class Choice(BaseModel):
    label: str
    description: str = ""
    preview: str = ""
    rank: int | None = None   # None = not selected; 1-based click order for multi-select

class Question(BaseModel):
    question: str
    header: str = ""
    multi_select: bool = False
    choices: list[Choice]           # predefined options with selection state embedded
    custom_text: str = ""           # free text in the auto-added Other box (multi-select)
    notes: str = ""                 # annotation note (notes-only single, or Codex user_note)
    selected_preview: str = ""      # annotation.preview when a preview-option was selected

    @property
    def timed_out(self) -> bool:
        return (
            not any(c.rank is not None for c in self.choices)
            and not self.custom_text
            and not self.notes
        )
```

`choices` holds only the **predefined** options (not the implicit "Other" row).
The renderer reconstructs the Other row from `custom_text` / `notes` / `selected_preview`.

---

## Two parsers → one `parse_payload(payload: dict) -> list[Question]`

Dispatch on `payload.get("tool_name")`:
- `"request_user_input"` → `_parse_codex(payload)`
- anything else (`"AskUserQuestion"`, missing) → `_parse_claude(payload)`

### `_parse_claude(payload) -> list[Question]`

Sources:
- questions list: `payload["tool_input"]["questions"]`
- answers dict (keyed by question text): `payload["tool_response"]["answers"]`
- annotations dict (keyed by question text): `payload["tool_response"].get("annotations", {})`

Existing fallback for bare `payload.get("questions")` list is kept.

Per question:
1. Parse `_parse_multi_answer(answer_str, labels)` → `(click_order, custom_text)`
2. Build `choices` from option list, setting `rank` for each matched label
3. Set `custom_text`, `notes` (from `annotation.notes`), `selected_preview` (from `annotation.preview`)

For single-select `answer == "(notes only)"`: no choices get `rank`, `notes` comes from annotation.

### `_parse_codex(payload) -> list[Question]`

Sources:
- questions list: `payload["tool_input"]["questions"]` — each has an `"id"` field
- answers: JSON-parse `payload["tool_response"]` string →
  `{qid: {"answers": ["Label", "user_note: text", "None of the above"]}}`

Per question id:
- `"user_note: ..."` items → strip prefix → `notes` (joined by `"; "`)
- `"None of the above"` → discard (UI-injected sentinel)
- remaining strings → selected labels → match against option list → set `rank` in click order
- no matched labels + notes → `notes` only (equivalent to notes-only)
- nothing at all → `timed_out` is True (computed from empty state)

---

## Updated `_render_block(questions: list[Question]) -> str`

Replaces `_render_block(tool_input: dict, tool_response: dict)`.

All dict accesses become attribute reads:
- `q.question`, `q.header`, `q.multi_select`, `q.choices`, `q.custom_text`, `q.notes`, `q.selected_preview`, `q.timed_out`
- `choice.label`, `choice.description`, `choice.preview`, `choice.rank`

`_parse_multi_answer` is removed — its job now happens at parse time (choices carry `rank`).

The "Other" row at the bottom of each question is rendered from:
- multi-select: `custom_text` → checked/unchecked + text if non-empty
- single-select with preview options: `selected_preview` → `"_Notes: Add notes on this design._"`
- single-select notes-only: `notes` → `[x] _Notes:_ \n > {notes}`
- single-select plain: `custom_text` → `"_Type something[.:]_"` (unchanged logic, just via attribute)

Summary section: `q.selected_preview` replaces `ann.get("preview")` lookup.

---

## `main()` simplification

```python
payload = read_payload()
dump_debug_payload(payload, "save-decision")
questions = parse_payload(payload)
if not questions:
    return 0
block = _render_block(questions)
slug = slugify(questions[0].question, fallback="decision")
...
```

`_normalize_codex_answers` is deleted — its logic moves into `_parse_codex`.

---

## Test update  (`scripts/°base/tests/test_save_decision.py`)

Update call site from `_render_block(tool_input, tool_response)` to:

```python
questions = _hook.parse_payload({
    "tool_name": "AskUserQuestion",
    "tool_input": {"questions": _data["questions"]},
    "tool_response": {
        "answers": _data["answers"],
        "annotations": _data.get("annotations", {}),
    },
})
actual = _hook._render_block(questions)
```

---

## Files changed

| File | Change |
|---|---|
| `scripts/°base/ai/hooks/save-decision/hook.py` | Add `Choice`/`Question` models + `parse_payload` + two parsers; rewrite `_render_block`; simplify `main`; delete `_normalize_codex_answers` + `_parse_multi_answer` |
| `scripts/°base/tests/test_save_decision.py` | Update call site to use `parse_payload` |

---

## Verification

```bash
cd /Users/user/Documents/programming/Python/base
python -m unittest scripts/°base/tests/test_save_decision.py -v
```

Then spot-check Codex parsing by feeding a debug payload through `parse_payload` and
inspecting `question.choices[*].rank`, `question.notes`, `question.timed_out` against
the debug files in `ai/°base/output/debug/`.
