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

Alright, let's modernize the question prompt log.
Currently, we have question output to `query.md` like @ai/°base/errors/12.md
Instead I want it changed to @ai/°base/errors/12.expected.md

Construct a unittest using `12.expected.md`'s `json` under **Input JSON (Claude)** as input and asserting the markdown under **`query.md` addition** as output.
For implementing, the sections **Summary of format options** and **Notes** may be helpful.

- [x] Done

---

Additionally, using @ai/references/https/developers.openai.com/codex/mcp.md and @ai/references/https/github.com/7c/bugsink-mcp/blob/87ce8bba8d65b15004f80314fce5845543ae193b/README.md support MCP sync.
While at it configure it directly with `envmcp` to use `ai/.env` of a repo, see @ai/references/https/github.com/griffithsbs/envmcp/blob/9dc9d6510aa07f999095b7bb5eed636428eebec5/README.md for that tool.

- [x] Done
