…
e2e_deep_flow.py", line 108, in _assert_clean_branch
    self.assertFalse(
    ~~~~~~~~~~~~~~~~^
        any(classify.is_ai_base_path(p) for p in paths),
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        f"commit {sha} on feature/test-eins touches an ai/base path: {paths}",
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    )
    ^
AssertionError: True is not false : commit 084f7b0e78f26a8b5411c7495e4c9ca8eb7f9ec2 on feature/test-eins touches an ai/base path: ['ai/ckpt8_ai_0.md']

======================================================================
FAIL: test_single_branch_includes_all_derived_refs (test_git_split_recovery.ResolveWatchedRefsTests.test_single_branch_includes_all_derived_refs)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/home/user/git/luckydonald/base/.claude/worktrees/splitter/scripts/°base/tests/test_git_split_recovery.py", line 43, in test_single_branch_includes_all_derived_refs
    self.assertEqual(
    ~~~~~~~~~~~~~~~~^
        refs,
        ^^^^^
    ...<9 lines>...
        ],
        ^^
    )
    ^
AssertionError: Lists differ: ['mas[226 chars]ture', 'refs/base-split/forward-cursor/clean/f[53 chars]ure'] != ['mas[226 chars]ture']

First list contains 2 additional elements.
First extra element 8:
'refs/base-split/forward-cursor/clean/feature'

  ['master',
   'ai/history/master',
   'feature',
   'ai/UNCLEAN/feature',
   'ai/history/feature',
   'refs/base-split/history-master-fork-point/feature',
   'refs/base-split/unclean-cursor/clean/feature',
-  'refs/base-split/unclean-cursor/history/feature',
?                                                  ^

+  'refs/base-split/unclean-cursor/history/feature']
?                                                  ^

-  'refs/base-split/forward-cursor/clean/feature',
-  'refs/base-split/forward-cursor/history/feature']

======================================================================
FAIL: test_no_node_files_is_silent (test_yarn_4_hook.Yarn4HookTests.test_no_node_files_is_silent)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/home/user/git/luckydonald/base/.claude/worktrees/splitter/scripts/°base/tests/test_yarn_4_hook.py", line 84, in test_no_node_files_is_silent
    self.assertEqual(result.stderr, "")
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^
AssertionError: "debug: last commited ai/tool-settings/settings.json has 'yarn@4': True\n" != ''
- debug: last commited ai/tool-settings/settings.json has 'yarn@4': True


----------------------------------------------------------------------
Ran 626 tests in 546.641s

FAILED (failures=5, skipped=2)
Rebasing onto merge-base abc123 with origin/mane, stripping AI attribution...
Rebasing onto merge-base abc123 with origin/mane, stripping AI attribution...
Checking for parent commits having older backup tags…
Found old backup tag: 'old-backup'
Tag cleanup done.
