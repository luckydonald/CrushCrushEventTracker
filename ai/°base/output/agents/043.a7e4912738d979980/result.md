Now I have all findings. Here's the report.

## Findings: coding-style constraints in `ai/°base/query.md` NOT yet in `references/py.md`

`py.md` currently only captures: (1) no `_`-prefix "private" naming, no private classes/functions, prefer separating into modules, and (2) the `# end if` / `# end with` / etc. block-closing-comment convention. Everything below is new/uncaptured.

### Python

1. **No `_lib.py` module names; use the `°*_lib` naming pattern instead** — and don't use underscore-prefixed function names either.
   - Line 3055: *"do not cram more stuff into `scripts/°base/ai/hooks/_lib.py` - instead separate it in multiple files in `scripts/°base/ai/hooks/°*libs`, following the format of e.g. `°split_lib` or `°dllink_lib`."*
   - Line 3369: *"Do not add/use `_lib.py`, instead use the `°*_lib` format already used otherwhere, do not use underscore function names."*
   - This is a distinct, more specific naming-convention rule than the general "no `_` prefix for privacy" rule already in `py.md` — it's specifically about splitting helper/lib modules and naming them `°<name>_lib.py` rather than `_lib.py`, plus a reiteration that plain functions also shouldn't get underscore-prefixed names.

### JSON / TOML (settings/export files)

These appeared while discussing `scripts/°base/ai/settings/sync.py`'s JSON/TOML export of settings files — phrased as general "always" rules for that export format, so plausibly worth a shared JSON/TOML style note:

- Line 2275: *"`enabled` booleans shall always come as first in json or toml export."*
- Line 2276: *"`permissions`.`allow`/`deny`'s elements should be singleline each."*
- Line 2277: *"if there's `enabled…`/`disabled…` variants (MCP, Plugins, etc.), always populate both arrays, and make sure they have a linesplit for best possible diffs."*
- Line 2282: *"`mcp.tools.<tool>.<variant>.cmd` and `mcp.servers.<name>.cmd` shall be single line."*

Note: these are somewhat tied to this repo's specific settings-file schema (allow/deny lists, mcp.tools/servers, enabledPlugins) rather than being a fully generic JSON/TOML rule — worth judgment-call on whether to generalize or keep as a project-specific note.

### Other languages (JS/TS, Bash, Go, Rust, SQL, YAML, Docker, Vue, etc.)

I searched thoroughly (keywords for indentation, quoting, naming conventions, import ordering, error handling, f-strings/type-hints, docstrings, line length, linters like black/ruff/isort/shellcheck, shebang conventions, const/let/var, arrow functions, interfaces, etc., plus explicit language names) and found **no additional coding-style constraints** for any language other than Python. The only other-language mentions in the file (bash one-liners like `curl ... | python3 -`, Vue/Python mentioned as example languages for the bugsink skill, JSON fixtures, pydantic model migration requests) are all task-specific implementation requests, not general style rules — nothing meeting the "always/never/prefer X for language Y" pattern.

### Summary for reference-file updates

- **`py.md`**: add the `_lib.py` → `°*_lib` naming rule (lines 3055, 3369).
- **Possible new `json.md` / `toml.md`** (or a combined note): the 4 export-formatting rules from lines 2275-2282, if you want to generalize them beyond the specific settings-sync context.
- No other language reference files are currently warranted based on this transcript — no JS/TS/Bash/Go/Rust/SQL/YAML/Docker/Vue style constraints were stated.