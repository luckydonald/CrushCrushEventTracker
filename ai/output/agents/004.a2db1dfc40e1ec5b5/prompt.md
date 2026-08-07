In repo at /home/user/git/luckydonald/base/.claude/worktrees/splitter, investigate a failing test.

Test: scripts/°base/tests/test_git_split_recovery.py::ResolveWatchedRefsTests.test_single_branch_includes_all_derived_refs (around line 43)

Failure: the test expects the resolved refs list to include, among others:
'refs/base-split/forward-cursor/clean/feature' and 'refs/base-split/forward-cursor/history/feature'
but the actual function output only includes up through 'refs/base-split/unclean-cursor/history/feature' — it's missing the two 'forward-cursor' entries entirely.

I need you to:
1. Read `scripts/°base/tests/test_git_split_recovery.py` fully, focusing on `ResolveWatchedRefsTests` class and `test_single_branch_includes_all_derived_refs` — what function is under test (likely something like `resolve_watched_refs`), what inputs it's given, and the full expected list.
2. Find the implementation of that function (search git_split module(s) under scripts/°base for "resolve_watched_refs" or similar, and search for "forward-cursor", "unclean-cursor", "history-master-fork-point" ref name patterns) to see how the derived-refs list is built for a branch.
3. Determine whether 'forward-cursor' refs are a currently-implemented concept in the codebase (grep for "forward-cursor" and "forward_cursor" across scripts/°base) — is this a recently-added or planned feature that the implementation doesn't fully build yet, or is it an old/removed concept that the test wasn't updated to drop?
4. Check git log / blame for the test file and the implementation file around these lines to see which one was most recently changed and whether there's a matching implementation change that didn't land, suggesting one side is stale.

Report back with: exact test expectation code, exact implementation code for building the refs list (with file:line), full list of 'forward-cursor' vs 'unclean-cursor' references you find in the codebase (files and counts), and your conclusion — is the implementation missing a feature (should add forward-cursor refs) or is the test asserting an outdated/wrong expectation (forward-cursor refs shouldn't exist for this scenario)? Cite specific evidence (comments, related classify/history-master code, other passing tests referencing forward-cursor) for your conclusion.