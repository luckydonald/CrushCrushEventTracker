# History-master replay guards

- `recreate_base_merge()` hit Git conflict paths shape `path~<40-hex-oid>`, missing from original merge tree. Never blind `git rm` missing historical path; require synthetic suffix plus evidence normal counterpart exist on target side. Raise `HistoryMasterError` for unrelated missing paths.
- Cherry-pick empty after conflict resolution: use `git commit --allow-empty --no-edit`, not `git cherry-pick --skip`. Keeps original commit message and `X-*` history trailers.
- Internal replay commits and cherry-pick continuation may need `core.hooksPath=/dev/null` — target repos can have hooks assuming project-specific config; else hook failures hide real Git operation.
- After scratch-branch conflict resolution, reset scratch checkout hard to committed tip before restoring caller's branch. Else unstaged conflict artifact make successful replay look failed on dirty-worktree restoration.
- Parse `git diff --name-only --diff-filter=U -z` as NUL-delimited output; quoted line parsing break on paths with spaces or special chars.
