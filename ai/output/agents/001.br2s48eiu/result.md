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
Ran 579 tests in 537.073s

FAILED (failures=11, errors=6, skipped=15)
Rebasing onto merge-base abc123 with origin/mane, stripping AI attribution...
Rebasing onto merge-base abc123 with origin/mane, stripping AI attribution...
Checking for parent commits having older backup tags…
Found old backup tag: 'old-backup'
Tag cleanup done.
