# Sync command permissions to Codex via `.rules` files

## Context

`scripts/°base/ai/settings/sync.py` currently syncs `hooks` and `enabledPlugins` between
Claude and Codex, but the `permissions.allow`/`permissions.deny` lists in
`ai/tool-settings/settings.json` are only ever rendered into `.claude/settings.json`
(`render_claude`, sync.py:405-413). `render_codex_hooks` (sync.py:416-417) never touches
permissions, so Codex gets none of the ~90 command allowlist rules Claude has.

The blocker was format, not intent: entries are opaque strings like `"Bash(git status:*)"`,
which is Claude's native glob syntax and doesn't correspond to anything Codex understands.
Research into `ai/references/https/developers.openai.com/codex/rules.md` (fetched during
planning, not yet saved to the repo) shows Codex's real equivalent: project-local
`.codex/rules/*.rules` files containing Starlark `prefix_rule(pattern=[...], decision=...)`
calls, scanned automatically for any trusted `.codex/` config layer — exactly parallel to how
`.codex/hooks.json` already works in this repo.

To drive both, the neutral store needs a structured format instead of opaque strings — matching
the user's suggested shape `{ "type": "bash", "command": "…" }`. This plan migrates
`ai/tool-settings/settings.json` to that shape and teaches `sync.py` to render it into both
Claude's string syntax and a generated Codex `.rules` file.

## Neutral permission entry schema

Each entry in `permissions.allow[]` / `permissions.deny[]` becomes an object:

```json
{ "type": "bash", "command": "git status:*" }
{ "type": "read", "path": "ai/skills/commit-with-lplp-style/SKILL.md" }
{ "type": "skill", "name": "commit-with-lplp-style" }
```

- `type` is the lowercased Claude tool name (`bash`, `read`, `write`, `edit`, `skill`, `glob`, `grep`, `webfetch`, ...).
- The value field is type-specific for readability: `command` for `bash`, `path` for
  `read`/`write`/`edit`/`glob`, `name` for `skill`, falling back to a generic `pattern` field
  for any other/unknown tool type.
- Legacy strings that don't match `Tool(content)` at all are preserved losslessly as
  `{ "type": "raw", "value": "<original string>" }`.
- Which array (`allow` vs `deny`) an entry lives in still carries the decision, same as today —
  no new per-entry decision field.

## Claude-side conversion (round-trippable)

Add to `sync.py`:
- `_parse_claude_permission_entry(s: str) -> dict` — regex `^([A-Za-z_]\w*)\((.*)\)$`, maps the
  captured tool name to a lowercase `type` and fills the type-specific field (fallback `pattern`
  for unknown tools; `raw` wrapper if the string doesn't match the pattern at all).
- `_render_claude_permission_entry(entry: dict) -> str` — the inverse, using a
  `TYPE_TO_CLAUDE_TOOL` map (`bash→Bash`, `read→Read`, `write→Write`, `edit→Edit`, `skill→Skill`,
  `glob→Glob`, `grep→Grep`, `webfetch→WebFetch`, `websearch→WebSearch`, else `str.capitalize()`)
  and the matching field name.
- Wire these into `_normalize_native` (sync.py:240-256) so any string entries found in
  `permissions.allow`/`deny` — whether from `.claude/settings.json` or an old-format
  `ai/tool-settings/settings.json` — are upgraded to objects before merging/deduping (`_unique`
  already dedups via `json.dumps(sort_keys=True)`, which works fine on dicts).
- Update `render_claude` (sync.py:405-413) to map `shared["permissions"]` entries through
  `_render_claude_permission_entry` before writing, so `.claude/settings.json` keeps its current
  string format unchanged from Claude's point of view.

This makes the migration self-executing: the next `sync.py` run rewrites the tracked
`ai/tool-settings/settings.json` permissions block from strings to objects automatically (large
one-time diff, ~90 entries — expected and desired).

## Codex-side: generate `.codex/rules/*.rules`

New in `sync.py`:
- `_bash_pattern_to_prefix(command: str) -> list[str] | None` — converts a Claude bash pattern
  into a Codex prefix-rule token list, or `None` if it can't be safely reduced:
  - Strip a trailing wildcard marker (`:*` or a bare trailing `*` token) before tokenizing —
    Codex `prefix_rule` patterns are inherently prefix matches, so `"git status:*"` becomes
    `["git", "status"]`.
  - No trailing wildcard → tokenize the whole string as the literal prefix (slightly more
    permissive than Claude's exact-match semantics, since Codex prefix rules always allow
    trailing args; acceptable, document as a known asymmetry).
  - Tokenize with `shlex.split`.
  - Return `None` (untranslatable) when the command contains shell metacharacters Codex won't
    safely split per its docs — `$`, `` ` ``, `&&`, `||`, `;`, `|`, `<`, `>` — or looks like an
    env-var assignment prefix (`^[A-Za-z_]\w*=`). These stay Claude-only.
- `render_codex_rules(shared: dict) -> str` — iterates `permissions.allow` (decision `"allow"`)
  and `permissions.deny` (decision `"forbidden"`), keeps only `type == "bash"` entries, calls
  `_bash_pattern_to_prefix`, skips `None` results, and emits one `prefix_rule(pattern=[...],
  decision="...")` Starlark call per entry (string literals via `json.dumps` — valid Starlark
  string syntax). Add a leading comment noting the file is generated (same
  `GENERATED_MARKER` convention already used for skills) and a summary comment of how many
  entries were skipped as untranslatable, so nothing silently vanishes.
- `read`/`skill`/`write`/`edit`/other non-`bash` types are intentionally not rendered for Codex —
  Codex rules only govern command execution, not per-path file permissions or skill invocation,
  so there's no equivalent to translate to.

## Wiring into the file-write flow

- New path constants: `CODEX_RULES = Path(".codex/rules/generated.rules")` (tracked) and
  `CODEX_RULES_LOCAL = Path(".codex/rules/generated.local.rules")` (local-only — the
  `*.local.*` name matches the existing `**/*.local.*` gitignore rule, confirmed already present).
- Extend `_apply_or_check` (sync.py:629-646) to take an optional `rules_path` and, alongside the
  three existing JSON writes, also compute `render_codex_rules(shared)` and write it via the
  existing `_write_text_if_changed` helper (already used for skills, sync.py:568-574).
- Update the two call sites in `main()` (sync.py:664-666) to pass `CODEX_RULES` /
  `CODEX_RULES_LOCAL` for the tracked and local groups respectively.
- This is one-directional generation only (shared → `.rules`), mirroring how `.codex/config.toml`
  is only lightly migrated today, not fully round-tripped — no Starlark parser is written to read
  `.codex/rules/*.rules` back into the shared model. Hand edits to that generated file would be
  overwritten on next sync, same as the other generated files.

## Docs

Update `ai/°base/AGENTS.md`'s settings table (around line 40-47) to add
`.codex/rules/generated.rules` (generated, do-not-edit) and mention the new structured
permission-entry schema.

## Tests (`scripts/°base/tests/test_ai_settings_sync.py`)

- `_parse_claude_permission_entry` / `_render_claude_permission_entry` round-trip for `bash`,
  `read`, `skill`, an unrecognized-tool fallback (`pattern` field), and a malformed string
  (`raw` wrapper).
- `_bash_pattern_to_prefix`: trailing `:*` and trailing `* ` stripping, plain literal command,
  and the untranslatable cases (`$(...)`, `&&`, env-assignment prefix) returning `None`.
- `render_codex_rules`: allow entries → `decision="allow"`, deny entries → `decision="forbidden"`,
  non-bash types skipped, untranslatable bash entries skipped (and counted in the summary
  comment).
- `render_claude` still emits legacy-style strings when fed object-form shared permissions
  (extends the existing `test_render_claude_keeps_permissions`).
- A migration test: loading a shared file with old plain-string permission entries produces
  object-form entries after `_load_layer`/`_merge`.
- `_apply_or_check`/`main`-level test that the new rules file is written and reported in
  `changed`, using the existing tmp-dir test harness pattern already in the file.

## Verification

1. `uv run --project scripts/°base python -m unittest scripts/°base/tests/test_ai_settings_sync.py -v` (new + existing tests pass).
2. Run `./scripts/°base/ai/settings/sync.py` for real in the repo:
   - Confirm `ai/tool-settings/settings.json` permissions are now objects and still contain all
     current allow/deny entries (spot check a few against the pre-change file).
   - Confirm `.codex/rules/generated.rules` is created with `prefix_rule(...)` entries for the
     translatable bash commands (e.g. `git status`, `tree`, `uv sync`), and that entries like the
     `GIT_SEQUENCE_EDITOR=...` and `echo "exit: $?"` ones are absent/reported as skipped.
   - Confirm `.claude/settings.json` permissions are byte-identical in meaning to before (same
     `Bash(...)`/`Read(...)`/`Skill(...)` strings).
3. Run `./scripts/°base/ai/settings/sync.py --check` again — should report already in sync
   (idempotency).
