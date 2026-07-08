# Fix: memory-file deletions never propagate to the repo mirror

## Context

`scripts/°base/ai/hooks/record-memory/hook.py` mirrors Claude Code's per-project
memory files between an external directory
(`~/.claude/projects/<encoded-repo-path>/memory/<name>.md`) and a git-tracked
mirror inside the repo (`ai/°base/memory/<name>.md`, or `ai/memory/...` for
consuming repos), via hardlink (falling back to symlink cross-filesystem). It
only fires on `PostToolUse` matcher `"Write|Edit"` and on `SessionStart`
(`ai/tool-settings/settings.json`).

Earlier this session, a memory file was deleted from the external directory
via a plain `rm` (Bash tool) instead of the sanctioned deletion helper. Since
`record-memory` never listens for `Bash`, nothing observed the deletion — the
repo mirror was left stale, had to be cleaned up by hand (`git rm`), and that
deletion commit lacked the required `Deleted Memory: <name>.md` marker and
later got folded away during an unrelated history squash. This is exactly the
gap the user asked to fix: hook into the deletion itself and properly
propagate it to the repo mirror.

**Why this isn't just "make missing-source mean delete"**: the hook used to
work that way and it caused a real data-loss incident (commit `d1b384a`) — an
encoding bug in path resolution made the hook think the source dir was empty,
and it deleted real, wanted memory files from the repo. The fix (plan
`ai/°base/plans/007_prevent-accidental-memory-deletion.md`, commit `e12db5f`)
made the **repo copy authoritative**: `_sync_all()`'s `SessionStart` resync
never deletes the repo mirror from absence alone — a missing external file is
*recreated* from the repo copy instead. The only sanctioned way to originate a
deletion is `scripts/°base/ai/memory/delete.py`, which unlinks both copies and
commits the repo-side deletion with a `Deleted Memory: <name>.md` marker (a
pre-commit hook, `require_memory_delete_marker.py`, enforces this marker on
any commit that deletes a memory `.md` file). The bug is that `delete.py` is
never invoked automatically by anything — ordinary `rm` usage bypasses it
entirely, so deletions silently never propagate, and the *next* `SessionStart`
would even resurrect the external file from the (stale, should-be-deleted)
repo copy.

**The fix**: add a narrow, *reactive* detection — when the `Bash` tool runs a
command whose parsed argv includes an `rm` of an absolute `.md` path living
directly under the external memory source dir, and that file is confirmed
gone from disk right after, treat it as a deliberate deletion signal (this is
categorically different and much safer than the old "resync sees absence"
signal that caused the incident — it's triggered by an actually-observed `rm`
of a specific named file, not by inferring intent from ambient directory
state) and propagate it into the repo mirror using the exact same mechanism
`delete.py` already uses. `_sync_all()`/`SessionStart` behavior is untouched.

## Approach

### 1. Extract a shared deletion-commit helper

`scripts/°base/ai/hooks/_lib.py` currently has `base_ai_commit_subject()` and
other shared helpers already imported by both `delete.py` and
`record-memory/hook.py`. Add to it:

```python
def _tracked(path: str) -> bool: ...          # git ls-files --error-unmatch
def _unlink_path(path: Path) -> None: ...     # unlink if symlink or exists
def delete_memory_mirror(name: str, *, src_dir: Path, dst_dir: Path, dst_dir_rel: str) -> bool:
    """Unlink both copies of memory `name` and commit the repo-side deletion
    with the required `Deleted Memory: <name>` marker. Returns True if a
    commit was made (False if the repo copy wasn't tracked — nothing to do)."""
```

Body: port `delete.py`'s existing `_tracked`/`_unlink`/commit sequence
(`delete.py:36-46, 68-91`) verbatim — `git add -- <dst_rel>`, then
`git commit --only <dst_rel> -m <subject> -m "Deleted Memory: <name>"`, subject via
`base_ai_commit_subject(f"ai: delete memory {Path(name).stem}")`.

### 2. Refactor `delete.py` to call the shared helper

`main()` keeps its CLI arg validation, `_memory_dirs()`/`_subproject_root()`
resolution, the "not tracked" early-exit message, and the final
"Deleted memory X in <sha>" print — but delegates the actual unlink+commit to
`delete_memory_mirror()`. Behavior must be byte-identical (all of
`test_memory_delete.py` passes unchanged).

### 3. Detect Bash `rm` of a source memory file in `record-memory/hook.py`

Add a small parser (same technique as `.claude/hooks/permission-check.py`'s
`split_on_shell_operators` + `shlex.split` — don't reinvent differently, but
keep it local to this file since it's a different hook directory/sys.path
setup):

```python
def _rm_targets(command: str) -> list[str]:
    """Absolute-path .md arguments passed to a plain `rm` invocation anywhere
    in `command` (chained via &&/||/;). Relative paths are skipped -- the
    hook has no reliable view of the Bash tool's cwd."""
```

Logic: `shlex.split(command)`, split on `{"&&", "||", ";"}` into sub-argvs
(copy `split_on_shell_operators`'s ~10 lines), for each sub-argv whose
`argv[0] == "rm"`: walk the remaining tokens, skip ones starting with `-`
(flags) up to a bare `--`, keep the rest; for each kept token, resolve
`Path(token).expanduser()` — skip if not absolute, skip if suffix isn't
`.md`. Return the raw list of resolved `Path`s (name-filtering against
`src_dir` happens in the caller, which already has `src_dir` resolved).

In `main()`'s `PostToolUse` branch (`hook.py:323-335`), branch on payload
shape instead of assuming Write/Edit: check `tool_input.get("command")`
first (Bash-shaped) before falling back to today's `tool_input.get("file_path")`
(Write/Edit-shaped, unchanged). For the Bash case:

- For each path from `_rm_targets(command)` whose `.parent == src_dir.resolve()`
  and which is now confirmed absent (`not path.exists()`) — call
  `delete_memory_mirror(path.name, src_dir=src_dir, dst_dir=dst_dir, dst_dir_rel=dst_dir_rel)`.
- No matches → no-op, same as today.

This only ever *removes* — it never creates/recreates anything, and it never
touches `_sync_all()`/the `SessionStart` path at all.

### 4. Wire the new matcher

`ai/tool-settings/settings.json`: widen the existing `record-memory`
`PostToolUse` entry's matcher from `"Write|Edit"` to
`"Write|Edit|Bash|shell|unified_exec"` (same Bash-family pattern already used
by the `PermissionRequest` entry for `permission-check.py`) — one hooks array,
not a duplicate entry, since `hook.py` now branches on payload shape itself.

Run `python3 scripts/°base/ai/settings/sync.py` afterward and confirm
`.claude/settings.json`, `.codex/hooks.json`, and `.github/hooks/generated.json`
all pick up the widened matcher (`sync.py --check` must pass clean).

### 5. Doc touch-up

`ai/°base/AGENTS.md`'s hook table (~line 105): update the `record-memory`
row's trigger column from `` `Write`, `Edit`, `SessionStart` `` to
`` `Write`, `Edit`, `Bash`, `SessionStart` ``.

## Tests

`scripts/°base/tests/test_ai_hooks_base_routing.py` (reuse `run_hook()`,
`init_repo()`, `_encode_project_path()`, `last_subject()` already defined
there; follow the existing `test_memory_*` tests' setup style):

- **Bash `rm` of a tracked mirror file → mirror deleted with marker.** Seed a
  repo-tracked mirror file + matching external source file, fire
  `{"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": f'rm "{src_file}"'}}`,
  assert the mirror file no longer exists and
  `git log -1 --format=%B` contains a standalone `Deleted Memory: <name>.md` line.
- **`rm` of a `.md` file outside the source dir → no-op.** Unrelated absolute
  path; assert no commit, mirror untouched.
- **Non-`rm` command mentioning a `.md` filename (e.g. `cat`) → no-op.**
- **`rm` of a source file with no tracked repo mirror → no-op**, no crash.
- **Chained command (`rm "<path>" && echo done`) → still detected.**
- Existing `test_memory_session_start_restores_missing_claude_source_from_repo`
  and `test_memory_session_start_does_not_resurrect_marked_deleted_memory`
  must keep passing unchanged — confirms `SessionStart`/`_sync_all` behavior
  is untouched.

`scripts/°base/tests/test_memory_delete.py`: run as-is after the refactor —
all existing cases must still pass, confirming `delete.py`'s externally
observable behavior didn't change.

Run:
```bash
uv run --project scripts/°base python -m unittest discover -s scripts/°base/tests -v
python3 scripts/°base/ai/settings/sync.py --check
```

## Manual verification

In a scratch temp repo (or reuse the test helpers interactively): seed a
tracked `ai/°base/memory/<name>.md` plus a matching external source file,
pipe a synthetic `PostToolUse`/`Bash` `rm "<abs-path>"` payload into
`record-memory/hook.py` directly, and confirm the mirror file is gone and
`git log -1` shows the `Deleted Memory:` marker — reproducing the exact
scenario from this session, now handled automatically instead of requiring a
manual `git rm` + hand-written marker.
