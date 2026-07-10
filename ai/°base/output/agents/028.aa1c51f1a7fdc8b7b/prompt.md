I need to understand testing conventions in the repo at /Users/user/Documents/programming/Python/base, specifically under /Users/user/Documents/programming/Python/base/scripts/°base/tests/.

Please explore (read-only, no edits):

1. List every file under scripts/°base/tests/ (recursively) and give a one-line summary of what each tests.
2. Are there any existing tests that build temporary git repositories (using tempfile, subprocess git init, etc.)? If so, read them in full and report: what helper functions/classes exist for creating a temp git repo, making commits, creating branches, running merges, and asserting on git log/state. Include exact file:line references and function signatures so they can be reused.
3. Is there a shared/base test-case class (e.g. a `GitTestCase` or similar) used across multiple test files? If yes, show its full implementation.
4. What testing framework conventions are used — plain `unittest`, `unittest.mock`, any use of `subprocess.run` wrappers for git commands? Are commits made with fixed dates/authors for determinism (e.g. GIT_AUTHOR_DATE, faked committer identity)?
5. How do other tests in this repo handle temp directories — `tempfile.TemporaryDirectory`, fixture teardown, `setUp`/`tearDown` patterns?
6. Check pyproject.toml / project config under scripts/°base/ for test dependencies (pytest vs unittest, any git-related test libs like `gitpython`).
7. Look for any existing test file related to "split", "history_master", "rebase_to_master", "sync_unclean", "sync_splits", "trailers", "classify", "branches", "bootstrap" under scripts/°base/git/ or scripts/°base/tests/ — even partial/WIP ones — and report their current state in full.

Report comprehensively with file:line references so a plan can be written that reuses existing helpers rather than reinventing them.
