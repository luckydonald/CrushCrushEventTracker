/plan I want to have "explore" commands written to the prompt log, similar to `Task Notification:`.
Claude CLI writes:
```log
Explore(Explore record-memory hook and commit logic)
```
I think we could write it like this:

@ai/°base/errors/9.expected.md

- [x] Done

---

If `ai/.debug` file exists, all hooks shall write their payload to `ai/output/debug/`. Adapt paths for `°base` as usual.

- [x] Done

---

Record `/compact` results, too.
For `/compact`, see @ai/°base/errors/10.md and @ai/°base/errors/10.expected.md

- [x] Done

---

For the `Task Notification:` prompt update, from [5.expected.md](./errors/5.expected.md), the last line (tools, tokens, time) is missing. Implement it.

- [x] Done

---

Fix prompts-while-running for claude being lost.
E.g. in this repo/prompt (blockquote me):
> Change the output dir for agent stuff to `ai/output/agents/NNN.task-id/` (+`output`)

- [x] Done

---
