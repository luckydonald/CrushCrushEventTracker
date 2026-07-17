In the repo /home/user/git/luckydonald/base, I need to understand the existing hook infrastructure so I can design a new hook that captures `/compact` command invocations (specifically ones with a custom prompt argument) and saves them to files.

Please investigate and report back:

1. Where are Claude Code hooks defined in this repo? Look for `ai/hooks/` or similar directories, and any `settings.json`/`settings.local.json` hook wiring (search for "PreCompact", "UserPromptSubmit", "hooks" in settings files).
2. Find the existing hook(s) that handle saving prompts (`ai: updated prompt` auto-commits) and saving plans (`ai: save plan NNN_slug` auto-commits) and memory records (`ai: record memory <slug>`) — likely under `ai/hooks/` or `scripts/°base/...`. Show me their file paths and roughly how they work: what event triggers them, how they pick the file name, how NNN numbering is computed (e.g. for plans — is it a simple increment based on existing files in a directory?), and how they auto-commit (git add + commit, message format, whitelisted commands).
3. Find where "ai/°base/plans/" and "ai/°base/decisions/" and "ai/°base/memory/" directories are referenced/created, to understand the existing `ai/°base/<category>/` file-per-item convention.
4. Check if there's already any handling of `/compact` or `PreCompact` hook event anywhere (grep for "compact" case-insensitively across ai/hooks, scripts, settings).
5. Check AGENTS.md or ai/°base/AGENTS.md for documented conventions about the ai/°base/ directory structure and numbering scheme (NNN_slug naming, index files, etc.).

Report file paths with line numbers for the key logic (event matching, filename/NNN generation, commit message construction, git add/commit invocation). Keep the report factual and complete — I'll use it to design the new hook myself, so include enough detail (e.g. actual code snippets for the numbering logic and commit command construction) that I don't need to re-open every file.