I need a deep understanding of the git "split" tool at /Users/user/Documents/programming/Python/base/scripts/°base/git/°split_lib/ (files: cli.py, bootstrap.py, branches.py, classify.py, git_ops.py, history_master.py, identity.py, push_checks.py, rebase_to_master.py, recovery.py, sync_splits.py, sync_unclean.py, trailers.py, tree_ops.py).

Please read ALL of these files in full and report back, in detail:

1. What is the overall purpose of this tool? (It appears to split a consuming repo's "unclean" branches — which mix "code" changes and "ai" folder/file changes — into a clean `feature/*` branch containing only code, and an `ai/history/*` branch containing only ai-only history, while also handling a `base/base` upstream merge and a special `mane`/main branch and `ai/history/mane` branch.)

2. What CLI entry points / commands does cli.py expose? What arguments does each take? Is there a "fake curl" / bootstrap install mechanism (bootstrap.py) — how would one invoke the script as if downloaded via curl from a local repo checkout rather than GitHub?

3. What are the exact branch naming conventions recognized (e.g. `ai/UNCLEAN/feature/*`, `ai/history/*`, `mane`/main, `empty/init`, `base/base`)? Is `mane` hardcoded, configurable, or auto-detected from current branch/HEAD?

4. How does classify.py distinguish "ai" files/folders from "code" files? What paths/patterns count as "ai" (e.g. `ai/**`, `.claude/**`, etc.)? Read any config or constants defining this.

5. How does the tool detect and handle merge commits — specifically merges from `empty/init` and from `base/base` (a local directory clone)? How does it avoid re-merging `base/base` multiple times, and how does it identify "the most recent base/base merge" already present in history?

6. How does trailers.py work — what trailers does it add to commits (e.g. references to original commit hashes), and how would a test verify that trailers on `ai/history/*` commits point to the correct original commit hash on the `ai/UNCLEAN/*` branch?

7. How does rebase_to_master.py / sync_unclean.py handle rebasing `ai/UNCLEAN/feature/*` and `ai/history/feature/*` onto an updated `mane`, especially the special case for the `mane`-named branch itself (i.e., `ai/UNCLEAN/mane` history / `ai/history/mane`) versus feature branches based on it?

8. How does README.md / .gitignore conflict handling work when merging cleanly — is there special-case logic to auto-resolve conflicts in those two files?

9. What existing tests already exist for this tool? Look at /Users/user/Documents/programming/Python/base/scripts/°base/tests/ for any test files related to "split" or "git" and summarize their structure/helpers (e.g. do they build temp git repos, what helper functions exist for creating commits/branches, running the script, asserting on results).

10. Is there a README or docs file describing this workflow in prose (mentioned in the task as "README.md" — check scripts/°base/git/ or ai/°base/ or docs for one, e.g. describing `empty/init`, `base/base` remote, `mane` naming, `ai/UNCLEAN/*` etc.)?

Report comprehensively with file:line references. This is purely a research/read task — do not write or edit any files.