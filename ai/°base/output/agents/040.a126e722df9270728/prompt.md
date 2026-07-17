In the repo /home/user/git/luckydonald/base, there's a recorded error transcript at `ai/°base/errors/22.txt` (paths/company names redacted) showing this failure from `get-base.py` auto mode:

```
get-base.py: auto mode: 'ai/history/main' missing -- running update-history-master first
...
update-history-master: cannot check out the history-master scratch branch while the working tree is dirty (1, README/, ai/, all:5.moz_log, assets/foo.html, assets/query.md, docker/, start.log, yeet_db.py, yeet_db.yml); commit or stash these changes first.
get-base.py: auto mode: update-history-master failed; aborting
```

Two things look suspicious and worth investigating as a potential bug:
1. The dirty-file list looks garbled: `1, README/, ai/, all:5.moz_log, assets/foo.html, ...` — the leading `1,` and the token `all:5.moz_log` look like a formatting/parsing bug in how the dirty-check renders `git status` output (e.g. maybe it's mis-joining a status-code count with filenames, or mis-parsing a git status porcelain line with a `?? ` / rename `->` marker), rather than real file paths.
2. Even if the underlying dirty-check is accurate, look at whether `update-history-master`'s "cannot proceed while working tree is dirty" is overly strict for this scenario (auto mode bootstrapping `ai/history/main` when it's missing) — i.e. should it stash-and-restore, or ignore untracked files, or only care about files that would actually collide with the checkout?

Please find:
- The `update-history-master` command's implementation (likely under `scripts/°base/git/°split_lib/` or similar — search for "history-master", "update-history-master", "cannot check out the history-master scratch branch", "working tree is dirty").
- The exact code that builds that dirty-file list / error message — show me the function and how it gets `git status` output, and whether there's an obvious bug (e.g. off-by-one in parsing porcelain status lines, wrong field slicing, string formatting bug producing `1,` and `all:5.moz_log`).
- Whether there are existing tests covering this dirty-check path, and if so which file/test names.
- The `get-base.py` auto-mode caller that invokes `update-history-master` and aborts on failure, to see if there's a more graceful handling already partially implemented, or where it should stash/restore.

Report back file paths with line numbers and the relevant code snippets (the dirty-check function's full body is important — I need to see exactly how the message is constructed to diagnose the `all:5.moz_log`/`1,` garbling). Do not make any edits — this is read-only investigation to hand off for a fix.