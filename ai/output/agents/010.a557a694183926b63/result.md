## Research Report

**1. `ai/references/` — Steam guide page**

`.agents/skills` are symlinks into `ai/skills/`; `.agents/skills` is not tracked separately.

The relevant file is `/home/user/git/luckydonald/CrushCrushEventTracker/ai/references/https/steamcommunity.com/sharedfiles/filedetails/_.md` — **0 bytes**. There is no HTML file, no other content under `steamcommunity.com/`. So: **no raw copy of the target guide page exists** anywhere in the repo yet. The `#profileBlock > .guide` selector, event headlines, and table structure cannot be inspected from local files — you'll need to fetch the live page (with the SSL/Akamai workaround) to learn the actual DOM. Everything else under `ai/references/https/` is unrelated cached doc pages (OpenAI Codex config docs, pyte docs, Bugsink/Sentry docs, GitHub Copilot docs, Coolify docs) — not useful for this task.

**2. Skills structure**

`.agents/skills/*` are symlinks to `ai/skills/*` (bugsink-setup, bugsink-triage, code-style, commit-with-lplp-style, coolify-compose-deploy, sanitize-error-logs).

```
ai/skills/bugsink-setup/SKILL.md
ai/skills/bugsink-setup/references/{monorepo-deploys.md, python.md, rust.md, vue.md}
ai/skills/bugsink-triage/{SKILL.md, enable.md}
ai/skills/code-style/SKILL.md
ai/skills/code-style/agents/openai.yaml
ai/skills/code-style/references/{py.md, ts.md, vue.md, yarn.md}
ai/skills/commit-with-lplp-style/SKILL.md
ai/skills/coolify-compose-deploy/SKILL.md
ai/skills/coolify-compose-deploy/evals/evals.json
ai/skills/coolify-compose-deploy/references/{magic-and-predefined-vars.md, service-template-contribution.md}
ai/skills/sanitize-error-logs/SKILL.md
```

`code-style/SKILL.md` (full content, 19 lines): identify languages/frameworks in scope → read only matching `references/*.md` files (py, ts, vue) → apply every matching guide while writing/modifying/reviewing → prefer more-local repo instructions when they conflict → don't read references for out-of-scope languages. For a Python scraper task, only `references/py.md` is in scope.

**3. `vue.md` (low priority, for Part 2)**

Very short (7 lines): frontend stack is Vue + TypeScript + SCSS; prefer `<script setup lang="ts">` SFCs; apply the TypeScript guide inside `<script>` blocks; write tests for frontend code.

**4. Existing Python app code**

No `src/` or `ccet/` package exists. Searching outside `scripts/`, `.agents/`, and `ai/` for `*.py` found only `/home/user/git/luckydonald/CrushCrushEventTracker/.claude/hooks/permission-check.py` (a Claude Code hook, not app code). `scripts/` itself is full of generic git-base tooling (`scripts/°base/git/...`, tests, etc.) unrelated to the scraper — this confirms the repo currently has **no application code**; a scraper package would be starting fresh.

**5. `docs/README.md`**

This is not project-specific documentation for CrushCrushEventTracker — it's the README for the generic **"base"** git-tooling repo (`luckydonald/base`), describing how to adopt/merge/rebase this shared base into other repos, git LFS, Claude/Codex GitHub issue agents, and branch-splitting tooling (`scripts/°base/...`). It contains no information about the actual event-tracker app, guide scraping, or data model — irrelevant to Part 1/2 planning content-wise, but confirms this repo is built on the `luckydonald/base` template.