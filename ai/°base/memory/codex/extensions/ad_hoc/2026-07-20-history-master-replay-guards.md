# History-master replay guards

- `recreate_base_merge()` can encounter Git-generated conflict paths of the form `path~<40-hex-oid>` that are absent from the original merge tree. Never blindly run `git rm` on any missing historical path; require the synthetic suffix and evidence that the normal counterpart exists on the target side. Raise `HistoryMasterError` for unrelated missing paths.
- When a cherry-pick becomes empty after conflict resolution, use `git commit --allow-empty --no-edit`, not `git cherry-pick --skip`, so the replay keeps the original commit message and `X-*` history trailers.
- Internal replay commits and cherry-pick continuation may need `core.hooksPath=/dev/null` because target repositories can have hooks that assume project-specific configuration; otherwise hook failures obscure the actual Git operation.
- After scratch-branch conflict resolution, reset the scratch checkout hard to its committed tip before restoring the caller's branch. Otherwise an unstaged conflict artifact can make a successful replay appear to fail on dirty-worktree restoration.
- Parse `git diff --name-only --diff-filter=U -z` as NUL-delimited output; quoted line-oriented parsing breaks on paths containing spaces or special characters.
