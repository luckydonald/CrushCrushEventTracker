In repo at /home/user/git/luckydonald/base/.claude/worktrees/splitter, investigate a failing test.

Test: scripts/°base/tests/test_git_split_e2e_deep_flow.py::DeepFlowTests.test_deep_flow_repo_variant_1 (and variant_2, variant_3)

Failure: at line 108, `_assert_clean_branch` asserts `not any(classify.is_ai_base_path(p) for p in paths)` for commits on `feature/test-eins` branch, but it fails because a commit touches path `ai/ckpt8_ai_0.md`, and `classify.is_ai_base_path('ai/ckpt8_ai_0.md')` returns True.

I need you to:
1. Read `scripts/°base/tests/test_git_split_e2e_deep_flow.py` fully, especially `_run_deep_flow` and `_assert_clean_branch` (around lines 1-120), and understand what "unclean_manifest" and "known_base_merge_shas" are, and what the test is verifying (that feature branch commits don't touch base-owned ai/ paths).
2. Find where `ai/ckpt8_ai_0.md` file name comes from — likely in fixtures.py (search `scripts/°base/tests/` for a fixtures module used here, e.g. `fixtures.build_repo_variant_1_random_commits`). Understand what kind of file "ckpt8_ai_0.md" is meant to represent (a checkpoint / AI file, random commit content, etc.) and whether it's supposed to be a "base ai" file or a "generic ai" file that isn't base-owned.
3. Find `classify.is_ai_base_path` definition (search for `is_ai_base_path` in scripts/°base, likely in a git_split classify module). Read its full implementation and any docstring/comments explaining what qualifies as an "ai base path" (e.g. `ai/°base/...` vs any `ai/...` path).
4. Determine: is the test's fixture generating a file at a path that SHOULD be classified as ai-base (meaning the test's expectation is wrong / outdated), or is `is_ai_base_path` incorrectly matching a path that should NOT be classified as base-owned (meaning the classify implementation has a bug)? Look for git history/recent commits or comments suggesting intentional behavior for this classify function.
5. Also check whether other similar existing tests (e.g. test_git_split_classify.py) show what paths ARE and ARE NOT expected to classify as ai_base_path, to see whether 'ai/ckpt8_ai_0.md'-style path (a plain 'ai/<name>.md', not under 'ai/°base/') matches existing accepted false or true cases.

Report back: exact code of is_ai_base_path, exact fixture code generating the 'ckpt8_ai_0.md'-style filenames (with surrounding context to know what kind of file it is / what directory it's placed under), and your conclusion on which side (test expectation vs implementation) is wrong and why, citing file:line evidence.