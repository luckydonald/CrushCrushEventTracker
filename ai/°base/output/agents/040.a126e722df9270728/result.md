## Summary of investigation

### 1. `update-history-master` implementation

File: `/home/user/git/luckydonald/base/scripts/°base/git/°split_lib/history_master.py`

- Entry point: `update_history_master()` at **line 832**.
- The dirty-check / error message that appears in the transcript is built by `_checkout_scratch()` at **lines 136–165**:

```python
def _checkout_scratch(onto: str, cwd: Path) -> None:
    """(Re)create the scratch branch at `onto` and check it out. ..."""
    status = _git(["status", "--porcelain"], cwd, check=True).stdout
    dirty_paths = [
        line[3:]
        for line in status.splitlines()
        if len(line) > 3 and line[3:] != recovery.RECOVERY_FILENAME
    ]
    if dirty_paths:
        paths = ", ".join(dirty_paths)
        raise HistoryMasterError(
            "cannot check out the history-master scratch branch while the working "
            f"tree is dirty ({paths}); commit or stash these changes first."
        )
    # end if
    _git(["checkout", "--detach", "HEAD"], cwd)
    _delete_ref(SCRATCH_REF, cwd)
    git_ops.create_branch(SCRATCH_REF, onto, cwd)
    ...
```

`git status --porcelain` (v1 format) is used, and every line it produces (ordinary `XY path`, untracked `?? path`, rename `R  from -> to`) is uniformly `<2-char status><space><rest>`, so `line[3:]` is the standard/correct way to strip the status prefix and get the path — there is **no off-by-one or field-slicing bug** here that I could find. I checked this by re-deriving the expected sort order: `git status --porcelain` output paths are byte/ASCII sorted, and the reported list `1, README/, ai/, all:5.moz_log, assets/foo.html, assets/query.md, docker/, start.log, yeet_db.py, yeet_db.yml` is exactly in ASCII order (`'1'(49) < 'R'(82) < 'a'…'ai/' < 'all:...' < 'assets…' < 'docker/' < 'start.log' < 'yeet_db…'`). That consistency is strong evidence the two odd-looking tokens (`1,` and `all:5.moz_log`) are **not parser garbage** but real (if unusual) paths in the reporter's tree — `1` as a literal untracked filename, and `all:5.moz_log` as an actual filename (colon-containing Mozilla debug log style name) that happened to survive the manual/company-name redaction of the transcript relatively intact. I did not find any code path that would truncate or mis-join a status-code with a filename to produce `1,` — no count/length variable is interpolated into `paths` anywhere near this code. So: **finding 1 (the "garbled output/off-by-one parsing bug") does not appear to be a real bug in `_checkout_scratch`** based on static analysis; it looks like an artifact of the redaction applied when the user saved the transcript, not of the code. (If you want, this could still be double-checked empirically by reproducing with matching filenames in a scratch git repo — I did not do that since it would require creating files, which is outside this read-only task.)

Other related dirty-checks in the same file, for contrast:
- `_refuse_if_checked_out_dirty()` (line 194) — only refuses when the ref in question is the branch actually checked out, and only cares about `status.strip()` truthiness (doesn't parse per-file), used at lines 270, 823, 944.

### 2. Is the strictness appropriate for auto-mode bootstrap?

Call chain for the exact failure in the transcript:
- `update_history_master()` (line 832) → `_build_plan()` produces 0 steps ("first run", `ai/history/{main}` doesn't exist yet) → `_run_steps` (line 597) returns immediately with 0 steps executed (doesn't touch the worktree) → then at **lines 920–939**, since `base/base` was just fetched and isn't an ancestor of `master_tip`, `_fold_base(base_sha, tip, cwd)` (line 456) is called → `_fold_base` immediately calls `_checkout_scratch(onto, cwd)` (line 470), which does the dirty check and raises.

So yes — this fires specifically in the "very first run, folding `base/base` in" scenario, exactly the auto-mode bootstrap case the user describes. The dirty check itself (refusing to `checkout --detach HEAD` while there are uncommitted/untracked changes) is legitimate in general — a real `git checkout` would carry over local modifications, and `git status --porcelain` also reports **untracked files/dirs** as dirty even though a plain `checkout --detach HEAD` wouldn't actually touch or lose them (untracked files are never touched by checkout unless they'd collide with something coming into existence). That's the concrete overstrictness: the check treats "any status line at all" as blocking, including untracked files (`??`) that a mere `checkout --detach` to the *same* commit can't destroy. A tighter check would be to only worry about locally modified/staged tracked files (`git status --porcelain` codes other than `??`, or restricted to files that would actually be touched by the incoming scratch-branch content), not all untracked cruft in the tree (README/, ai/, assets/*, *.log, etc., in the transcript are plausible untracked build/log artifacts, not obstacles to a same-commit detach). There's no stash/restore logic anywhere in this path (no `git stash` call in `history_master.py`), so as it stands the function has one binary behavior: refuse entirely.

### 3. `get-base.py` auto-mode caller

File: `/home/user/git/luckydonald/base/scripts/°base/git/get-base.py`

- `auto_argv()` (line 165) is where the transcript's flow lives: when `ai/history/{main}` is missing, it calls `run_split(...)` with `["update-history-master", "--yes"]` (lines 200–204, 217–222) and simply aborts (`return None`) if the subprocess's return code is non-zero — no stash/retry/graceful handling implemented:

```python
if git_ops.rev_parse(history_main_ref, repo_root) is None:
    status(f"auto mode: {history_main_ref!r} missing -- running update-history-master first")
    rc = run_split(repo_root, worktree, ["update-history-master", "--yes"])
    if rc != 0:
        status("auto mode: update-history-master failed; aborting")
        return None
```

- `main()` (line 239) then reports `"auto mode could not complete; see the delegated command error above"` (line 253) and returns exit code 1 — matching the transcript exactly.

There is no partial stash/restore scaffolding here or in `history_master.py`; the abort is a clean dead-end, so any "stash untracked changes and restore them after" fix would need to be newly added (most naturally inside `_checkout_scratch`/`_fold_base`, or by loosening the porcelain-status filter to ignore `??` entries).

### 4. Existing tests covering this path

- `/home/user/git/luckydonald/base/scripts/°base/tests/test_git_split_history_master.py`, `test_scratch_checkout_refuses_dirty_worktree_without_detaching` (line 52) — only exercises a single modified tracked file (`root.txt`) via `_checkout_scratch` directly; it does not exercise untracked files, untracked directories, renames, or the multi-file message-formatting shown in the transcript.
- `/home/user/git/luckydonald/base/scripts/°base/tests/test_get_base.py`: `test_on_clean_feature_branch_aborts_if_update_history_master_fails` (line 270) and `test_on_unclean_branch_aborts_if_update_history_master_fails` (line 304) both mock `run_split` to just `return_value=1` — they verify `auto_argv` aborts on any failure but do not simulate an actual dirty-worktree failure or its message content.
- No test exercises `_fold_base` + `_checkout_scratch` together with untracked files present (the exact combination that produced the transcript), and no test asserts anything about the exact dirty-path list formatting/content — so the two suspicious tokens in finding 1 are currently untested territory either way.