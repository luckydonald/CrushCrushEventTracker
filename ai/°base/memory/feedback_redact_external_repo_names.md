---
name: feedback-redact-external-repo-names
description: "In the base repo, commits (including ai/query.md, plans, test fixtures, and ai/°base/errors/*) must not contain repo/client/project names outside the luckydonald/ namespace — redact them."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 0dcdee12-bcc8-4ffa-8679-7f88974e2f82
---

Repo, client, and project names outside the `luckydonald/` namespace must never land in `base` repo commits — including `ai/query.md`, plan files, test fixtures, and `ai/°base/errors/*.*`. `[bracket]` scope tags naming a `luckydonald/`-owned repo (e.g. `[hoass_plugin-template]`) are fine and match the existing commit-prefix convention; the rule targets external/client identifiers only.

**Why:** During a commit-history cleanup (folding stray `ai:` auto-commits, see [[feedback_lplp_never_drop_ai_autocommits]] — since removed as an overreaction), a real client name and its branch/ticket reference had leaked from a redacted bug report into AI-authored plan files and a test fixture (`src/<client>.py`). The original `ai/query.md` prompt had already redacted the path as `/path/to/<redacted>`, but the plan/test content I generated afterward re-introduced the real name as a "concrete example."

**How to apply:** Before committing or amending history in `base`, grep new/changed `ai/query.md`, plan, test, and `ai/°base/errors/*.*` content for real external repo/client/project names. When redacting, use a generic placeholder (e.g. `widget`, `XXXXXX-manual-widget-refresh`) consistently across every file/commit that mentions it, not just the original source.
