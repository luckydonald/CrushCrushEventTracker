## Findings

**1. Test setup (`scripts/°base/tests/test_yarn_4_hook.py:76-86`)**

```python
def test_no_node_files_is_silent(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        init_repo(repo)

        result = run_hook(repo)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
    # end with
# end def
```

`init_repo` (lines 26-34) creates a fresh git repo and stages `ai/tool-settings/settings.json` with `{"pre_commit": {"yarn@4": {"enabled": True}}}` — but it stages *no* `package.json`, `yarn.lock`, or any other Node/Yarn artifact. This is meant to exercise the hook's early-exit path: when there is no Node/JS signal in the index at all, the hook should have literally nothing to say and just exit 0 silently. That's the only test in the suite that asserts full stderr silence (`assertEqual(result.stderr, "")`); every other passing test uses `assertIn(..., result.stderr)` or checks only the exit code, deliberately tolerating/expecting specific messages. This test is unique in enforcing zero-output for the "nothing to check" scenario, which is a reasonable UX expectation (a hook shouldn't chatter when it's a no-op).

**2. The debug print (`scripts/°base/git/hooks/commit/require_yarn_4.py:88-105`, specifically line 93)**

```python
def policy_enabled(paths: list[PurePosixPath], repo: Path) -> bool:
    enabled = True
    if SHARED_SETTINGS in paths:
        shared = parse_json_object(index_text(SHARED_SETTINGS), SHARED_SETTINGS.as_posix())
        enabled = yarn_setting(shared, SHARED_SETTINGS.as_posix(), local=False)
        print(f"debug: last commited {SHARED_SETTINGS} has 'yarn@4': {enabled}", file=sys.stderr)   # line 93
    else:
        print(f"debug: {SHARED_SETTINGS} is not git tracked, ignoring value, not checking.", file=sys.stderr)  # line 95
    # end if
    ...
```

This function runs unconditionally at the very start of `main()` (line 269, `enabled = policy_enabled(paths, repo)`), *before* the node-signal short-circuit at lines 273-277 (`signals = any(node_signal(path) for path in paths); if not signals and not warnings: return 0`). Since `ai/tool-settings/settings.json` is always staged by `init_repo`, `policy_enabled` always hits the `SHARED_SETTINGS in paths` branch and always prints the `debug: last commited ...` line to stderr — regardless of whether any Node/JS files exist. There is no `--verbose`/`--debug` flag or logging-level guard anywhere in the file; `print(..., file=sys.stderr)` is called unconditionally.

**3. Guarded or unconditional?**

Unconditional — there is no verbose/debug flag in this script at all (`grep -n "verbose\|debug" ` only turns up these two literal `print("debug: ...")` calls). It's a plain leftover diagnostic print, not a feature gated behind a flag.

**4. History**

- `b7ae12f` (2026-07-18) — original hook + test added. At this point `policy_enabled` had no debug prints, and `test_no_node_files_is_silent` already existed and presumably passed.
- `4ca382e` (2026-07-28) — commit titled "Made the `yarn@4` check more verbose, especially that it uses the last commited `settings.json` file," added exactly these two `print(..., file=sys.stderr)` debug lines (lines 93 and 95), with no accompanying test changes and no flag/guard added.

This is a straightforward regression: the "make it more verbose" commit added an always-on debug trace intended for the author's own troubleshooting, but it runs on every invocation (even the silent no-op path) and was never gated or reconciled with the existing `test_no_node_files_is_silent` expectation.

## Conclusion

The fix belongs in the hook implementation, not the test. The debug `print` statements at `scripts/°base/git/hooks/commit/require_yarn_4.py:93` and `:95` should either be removed (they read like ad-hoc troubleshooting output left in by mistake) or, if genuinely useful, gated behind an explicit verbose/debug env var or CLI flag that defaults to off. Evidence supporting this:
- `test_no_node_files_is_silent` is the only test that asserts full-stderr silence, and it predates the debug-print commit — it was passing before `4ca382e` and broke only because of that later change, not because the original design ever intended chatter here.
- All other tests in the file intentionally use `assertIn` against specific, meaningful error/warning strings (e.g. `"warning: ignored local node_modules"`, `"node_modules must never be tracked"`), i.e., every message that's expected to survive to stderr is a deliberate, user-facing diagnostic tied to an actual policy violation or warning — never a raw "debug:" trace. The `debug: last commited ...` line is qualitatively different (a bare internal-state dump) and doesn't fit the pattern of any other stderr output the suite tolerates.
- The print fires unconditionally before the "no signals" short-circuit, so it violates the hook's own no-op/silent contract for repositories with zero Node/JS files — undermining the very scenario `test_no_node_files_is_silent` is designed to protect.