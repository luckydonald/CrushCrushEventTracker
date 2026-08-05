# Structure only — content redacted/omitted, this is `009.…/result.md` shape

Whole file wrapped in two top-level tags, no prose outside them:

```
<analysis>
...
</analysis>

<summary>
...
</summary>
```

## `<analysis>` block

Free-form prose, numbered list 1-8, chronological walkthrough of the session leading to this compact:

1. What session was resumed from (prior compact).
2. What got done since (commits, decisions), narrated step by step.
3. Enumerated sub-items (a-z / bullet) per work item, each naming files touched + commit hash.
4. Notable "gotcha" encountered mid-session (here: a background task's misleading "exit code 0" framing).
5. Detailed dump of the actual failing/erroring output (stack traces, panic messages, error codes) that triggered this compact.
6. Cross-reference to prior memory/session notes, noting whether they're stale.
7. Explicit "what I have NOT done yet" disclaimer — guardrail against hallucinating completed work.
8. "Key files I'll need to look at next" bullet list with file paths, justified from context, each flagged not-yet-read.

Closing line: explicit tool-call constraint for this turn + confirmation next turn starts the real work.

## `<summary>` block

Same 9 fixed section headers every time (numbered, bold-titled):

1. **Primary Request and Intent** — original ask + most current live instruction, verbatim-quoted.
2. **Key Technical Concepts** — bullet list of stack/framework/pattern names relevant to resuming.
3. **Files and Code Sections** — bullet list, one per file, each with a "not yet read/edited this segment" flag.
4. **Errors and fixes** — split into already-resolved (brief) vs. currently-unresolved (detailed, this is the pending task).
5. **Problem Solving** — ongoing hypotheses / open questions blocking the fix.
6. **All user messages** — verbatim list, non-tool-result turns only, this segment.
7. **Pending Tasks** — bullet list, explicit scope boundary quoted from user.
8. **Current Work** — narrative of the immediate last few actions before this compact fired.
9. **Optional Next Step** — one paragraph, ties directly back to section 1's live instruction.

Trailing pointer line to the full transcript path is NOT part of this tagged file (that line lives only in the plain/[[resume]]-style variant — see `resume.md`).
