# Plan: Pydantic model for save-decision hook

## Context

`save-decision/hook.py` currently parses two structurally different wire formats
(Claude Code `AskUserQuestion` and Codex `request_user_input`) through a chain of raw
dict lookups and a normalization function that re-serialises back to dicts.
`_render_block` then guesses keys again when rendering.

The goal is one typed Pydantic model that both parsers fill and `_render_block` reads
via attributes — no more `.get("key", default)` scattered throughout.

---

## Model hierarchy  (`save-decision/hook.py`, top of file)

```python
from pydantic import BaseModel, Field

class Option(BaseModel):
    label: str
    description: str = ""
    preview: str = ""

class Annotation(BaseModel):
    notes: str = ""
    preview: str = ""

class QuestionAnswer(BaseModel):
    question: str
    header: str = ""
    options: list[Option] = Field(default_factory=list)
    multi_select: bool = False
    answer: str = ""          # selected labels joined by ", ", or "(notes only)", or ""
    annotation: Annotation = Field(default_factory=Annotation)

class DecisionPayload(BaseModel):
    questions: list[QuestionAnswer] = Field(default_factory=list)
```

`answer` semantics (same as current string conventions, now made explicit):
- `"Label A, Label B"` — one or more selected option labels (multi joins with `", "`)
- `"(notes only)"` — user added a note but did not pick a label
- `""` — no selection (e.g. Codex "None of the above" with no note)

---

## Two parsers → one `parse_payload(payload: dict) -> DecisionPayload`

Dispatch on `payload.get("tool_name")`:
- `"request_user_input"` → `_parse_codex(payload)`
- anything else (`"AskUserQuestion"`, missing) → `_parse_claude(payload)`

### `_parse_claude(payload)`

Sources:
- questions: `payload["tool_input"]["questions"]`  
- answers:   `payload["tool_response"]["answers"]`  (keyed by question text)
- annotations: `payload["tool_response"]["annotations"]`  (keyed by question text)

Note: Claude Code sends `tool_response` as a **dict**; the existing fallback for
`payload.get("questions")` at top level is kept.

```python
for q in raw_questions:
    qtext = q["question"]
    raw_ann = raw_annotations.get(qtext) or {}
    QuestionAnswer(
        question=qtext,
        header=q.get("header", ""),
        options=[Option(**{k: o[k] for k in ("label","description","preview") if k in o})
                 for o in q.get("options") or []],
        multi_select=q.get("multiSelect", False),
        answer=raw_answers.get(qtext, ""),
        annotation=Annotation(notes=raw_ann.get("notes",""), preview=raw_ann.get("preview","")),
    )
```

### `_parse_codex(payload)`

Sources:
- questions: `payload["tool_input"]["questions"]` — each has an `"id"` field
- answers:   JSON-parse `payload["tool_response"]` string →  
  `{qid: {"answers": ["Label", "user_note: text", "None of the above"]}}`

Per question id:
- items starting with `"user_note: "` → strip prefix → `Annotation.notes` (joined by `"; "`)
- `"None of the above"` → discard (UI-injected sentinel, no meaningful label)
- remaining strings → selected labels → join with `", "` → `answer`
- if no labels but notes exist → `answer = "(notes only)"`
- if nothing → `answer = ""`

Build `id → QuestionAnswer` map, then emit in question-list order.

---

## Updated `_render_block(payload: DecisionPayload) -> str`

Signature changes from `(tool_input: dict, tool_response: dict)` to
`(payload: DecisionPayload)`.

Replace all dict accesses with attribute reads:
- `q.question`, `q.header`, `q.options`, `q.multi_select`, `q.answer`, `q.annotation`
- `opt.label`, `opt.description`, `opt.preview`
- `q.annotation.notes`, `q.annotation.preview`

`_parse_multi_answer` signature: `(answer: str, options: list[Option]) -> tuple[list[str], str]`  
— replace `o.get("label", "")` with `o.label`.

`_render_preview_block` is unchanged (takes plain strings, no model knowledge).

`total = len(payload.questions)`, iteration over `payload.questions`.

---

## `main()` simplification

```python
payload = read_payload()
dump_debug_payload(payload, "save-decision")
decision = parse_payload(payload)
if not decision.questions:
    return 0
block = _render_block(decision)
slug = slugify(decision.questions[0].question, fallback="decision")
...
```

`_normalize_codex_answers` is deleted — its logic lives in `_parse_codex`.

---

## Test update  (`scripts/°base/tests/test_save_decision.py`)

The test calls `_hook._render_block(tool_input, tool_response)` — update to:

```python
decision = _hook.parse_payload({
    "tool_name": "AskUserQuestion",
    "tool_input": {"questions": _data["questions"]},
    "tool_response": {
        "answers": _data["answers"],
        "annotations": _data.get("annotations", {}),
    },
})
actual = _hook._render_block(decision)
```

---

## Files changed

| File | Change |
|---|---|
| `scripts/°base/ai/hooks/save-decision/hook.py` | Add models + two parsers + `parse_payload`; rewrite `_render_block` + `_parse_multi_answer`; simplify `main`; delete `_normalize_codex_answers` |
| `scripts/°base/tests/test_save_decision.py` | Update call site to use `parse_payload` |

---

## Verification

```bash
cd /Users/user/Documents/programming/Python/base
python -m unittest scripts/°base/tests/test_save_decision.py -v
```

Then manually feed a Codex debug payload through `parse_payload` and spot-check
`decision.questions[*].answer` matches expectations from the debug files in
`ai/°base/output/debug/`.
