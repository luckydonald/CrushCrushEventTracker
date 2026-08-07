…
^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/user/git/luckydonald/base/.claude/worktrees/splitter/scripts/°base/tests/test_git_split_e2e_deep_flow.py", line 65, in _run_deep_flow
    self._assert_clean_branch(unclean_manifest, known_base_merge_shas, mane_merge_count_at_fork)
    ~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/user/git/luckydonald/base/.claude/worktrees/splitter/scripts/°base/tests/test_git_split_e2e_deep_flow.py", line 108, in _assert_clean_branch
    self.assertFalse(
    ~~~~~~~~~~~~~~~~^
        any(classify.is_ai_base_path(p) for p in paths),
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        f"commit {sha} on feature/test-eins touches an ai/base path: {paths}",
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    )
    ^
AssertionError: True is not false : commit c88d49c856defe8700113b8aefdd6419f541ec0e on feature/test-eins touches an ai/base path: ['ai/ckpt8_ai_0.md']

======================================================================
FAIL: test_deep_flow_repo_variant_3 (test_git_split_e2e_deep_flow.DeepFlowTests.test_deep_flow_repo_variant_3)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/home/user/git/luckydonald/base/.claude/worktrees/splitter/scripts/°base/tests/test_git_split_e2e_deep_flow.py", line 182, in test_deep_flow_repo_variant_3
    self._run_deep_flow(fixtures.build_repo_variant_3_readme_gitignore_conflict_setup)
    ~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/user/git/luckydonald/base/.claude/worktrees/splitter/scripts/°base/tests/test_git_split_e2e_deep_flow.py", line 65, in _run_deep_flow
    self._assert_clean_branch(unclean_manifest, known_base_merge_shas, mane_merge_count_at_fork)
    ~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/user/git/luckydonald/base/.claude/worktrees/splitter/scripts/°base/tests/test_git_split_e2e_deep_flow.py", line 108, in _assert_clean_branch
    self.assertFalse(
    ~~~~~~~~~~~~~~~~^
        any(classify.is_ai_base_path(p) for p in paths),
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        f"commit {sha} on feature/test-eins touches an ai/base path: {paths}",
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    )
    ^
AssertionError: True is not false : commit cf04de08b991ce80edaa782872310f307dc6405c on feature/test-eins touches an ai/base path: ['ai/ckpt8_ai_0.md']

----------------------------------------------------------------------
Ran 626 tests in 540.842s

FAILED (failures=3, skipped=2)
Rebasing onto merge-base abc123 with origin/mane, stripping AI attribution...
Rebasing onto merge-base abc123 with origin/mane, stripping AI attribution...
Checking for parent commits having older backup tags…
Found old backup tag: 'old-backup'
Tag cleanup done.
