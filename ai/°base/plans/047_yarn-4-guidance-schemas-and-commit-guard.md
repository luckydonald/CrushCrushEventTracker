# Yarn 4 Guidance, Schemas, and Commit Guard

## Summary

- Add `ai/skills/code-style/references/yarn.md` with detailed Yarn 4/Berry setup guidance and link it from `ts.md`.
- Add an enabled-by-default Yarn 4 pre-commit policy that remains silent when the repository contains no Node/package-manager artifacts.
- Add IDE-discoverable schemas for tracked and machine-local tool settings. Machine-local declaration of the Yarn policy is always an error.

## Settings and Schema Contract

- Add this shared configuration to `ai/tool-settings/settings.json`:
  ```json
  {
    "$schema": "./settings.schema.json",
    "pre_commit": {
      "yarn_4": {
        "enabled": true
      }
    }
  }
  ```
- Introduce `settings.schema.json` for the complete neutral settings shape, including hooks, permissions, plugins, MCP via a reference to `mcp.schema.json`, downloader metadata, and `pre_commit.yarn_4.enabled`.
- Introduce `settings-local.schema.json`, composing the shared definitions while explicitly prohibiting the entire `pre_commit` key.
- Have settings sync preserve/inject the appropriate `$schema`:
  - `settings.json` → `./settings.schema.json`
  - `settings.local.json` → `./settings-local.schema.json`
- Reject `pre_commit` in `ai/tool-settings/settings.local.json` during settings sync with an actionable message directing the user to the tracked file. The Yarn hook independently performs the same check so local configuration cannot bypass or shadow repository policy.
- Treat an absent shared `pre_commit.yarn_4.enabled` as `true`; only tracked `"enabled": false` disables enforcement for legacy projects.
- Document the shared-only rule and both schemas in the tool-settings README and repository guidance.

## Hook Behavior

- Add `require_yarn_4.py` and register `require-yarn-4` in both pre-commit manifests with `pass_filenames: false`.
- Read blocking inputs from the staged index. Exit silently when it contains no Node/Yarn signals.
- When Node/package-manager artifacts exist:
  - Require every independent project to have `package.json`, `yarn.lock`, and an exact Yarn 4 `packageManager` pin; workspace manifests may inherit their containing root.
  - Require Yarn 4 lock metadata and reject Yarn Classic, Yarn 2, Yarn 3, malformed, or missing lockfiles.
  - Reject legacy `.yarnrc`, non-v4 `yarnPath` or `.yarn/releases` binaries, competing npm/pnpm locks, and tracked or staged `node_modules/**`.
  - Allow valid Yarn 4 `.pnp.*`, `.yarnrc.yml`, patches, plugins, releases, SDKs, versions, and Zero-Install artifacts.
- Inspect the working tree only for ignored `node_modules/` directories and emit a non-blocking warning on every commit when any exist.
- Report exact offending paths and Yarn 4/Corepack recovery commands.

## Yarn Guide

- Cover Yarn Modern/Berry terminology, Node requirements, Corepack installation—including Node 25’s removal of bundled Corepack—and deterministic exact Yarn 4 pinning. [Yarn installation](https://yarnpkg.com/getting-started/install), [Node Corepack notice](https://nodejs.org/download/release/v25.8.0/docs/api/corepack.html)
- Explain `package.json`, `packageManager`, `yarn.lock`, `.yarnrc.yml`, PnP versus `nodeLinker: node-modules`, workspaces, editor SDKs, dependency commands, immutable installs, upgrades, and migration cleanup. [Yarn version pinning](https://yarnpkg.com/cli/set/version)
- Provide tracked/ignored file matrices for ordinary PnP and Zero-Install repositories. [Official ignore guidance](https://yarnpkg.com/getting-started/qa), [cache strategies](https://yarnpkg.com/features/caching)
- Add deterministic Docker and Compose examples using manifest-first layers, Corepack, BuildKit cache mounts, `yarn install --immutable`, and the required PnP/runtime artifacts.
- Add a GitHub Actions example using current `actions/checkout@v6`, `actions/setup-node@v6`, explicit Corepack setup, and an immutable install. [setup-node guidance](https://github.com/actions/setup-node)
- Document the enabled-by-default commit guard, tracked opt-out, forbidden local override, and recovery from accidental old-Yarn lockfile rewrites.

## Test Plan

- Test shared default/enabled/disabled settings, malformed values, and rejection of any local `pre_commit` declaration.
- Parse both schemas, verify their references resolve, verify the shared Yarn setting shape, and verify the local schema explicitly rejects it.
- Test schema injection/preservation through settings sync without leaking neutral policy metadata into generated Claude, Codex, or Copilot files.
- Test no-Node silent behavior and valid Yarn 4 single-project, workspace, nested-project, PnP, local-release, and Zero-Install layouts.
- Test failures for Yarn v1/v2/v3 locks, missing or invalid package-manager pins, legacy files, competing locks, uncovered manifests, and tracked/staged `node_modules`.
- Test that ignored `node_modules` warns but succeeds.
- Run focused hook/settings-sync tests, the full `scripts/°base` unittest suite, settings-sync check, and both pre-commit definitions.
