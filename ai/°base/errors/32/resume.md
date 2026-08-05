# Structure only — content redacted/omitted, this is `008.…/result.md` shape

Plain markdown, no `<analysis>`/`<summary>` tags — just a leading disclaimer line, then the same 9 fixed numbered sections as `summary.md` (see [[summary]]), un-tagged:

```
This session is being continued from a previous conversation that ran out of context. The summary below covers the earlier portion of the conversation.

Summary:
1. Primary Request and Intent:
2. Key Technical Concepts:
3. Files and Code Sections:
4. Errors and fixes:
5. Problem Solving:
6. All user messages (verbatim, non-tool-result turns only):
7. Pending Tasks:
8. Current Work:
9. Optional Next Step:
```

Differences vs. the tagged `summary.md` variant:
- No `<analysis>` walkthrough section preceding it — starts straight at the numbered summary.
- Ends with two trailing instruction lines not present in the tagged variant:
  - a pointer to the full raw transcript path (`/home/user/.claude/projects/<slug>/<uuid>.jsonl`) for recovering exact snippets,
  - an explicit "continue directly, no recap, no acknowledgement" directive for the next turn.
