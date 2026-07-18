# Yarn 4 Guidance, Schemas, and Commit Guard

## Summary

- Add `ai/skills/code-style/references/yarn.md` with detailed Yarn 4/Berry guidance and link it from `ts.md`.
- Add an enabled-by-default Yarn 4 pre-commit guard that remains silent in repositories without Node/package-manager artifacts.
- Add IDE-discoverable schemas for shared and local settings, with automated schema and hook tests.

## Settings and Schemas

- Add the shared configuration:
  ```json
  {
    "$schema": "./settings.schema.json",
    "pre_commit": {
      "yarn@4": {
        "enabled": true
      }
    }
  }
  ```
- Introduce `settings.schema.json` for the neutral settings format, composing the existing MCP schema and defining `pre_commit["yarn@4"].enabled` as a boolean.
- Introduce `settings-local.schema.json` for local overlays:
  - Allow `pre_commit` and any other valid pre-commit settings.
  - Explicitly prohibit only the nested `pre_commit["yarn@4"]` property.
- Have settings sync preserve or inject the appropriate `$schema` reference in tracked and local settings.
- Reject any local declaration of `pre_commit["yarn@4"]`, regardless of its value, during settings sync and in the Yarn hook. Direct users to configure it in tracked `settings.json`.
- Treat a missing shared `pre_commit["yarn@4"].enabled` as enabled; legacy projects must explicitly set tracked `"enabled": false`.
- Document this contract in the tool-settings README and repository guidance.

## Hook and Yarn Guide

- Add `require_yarn_4.py` and register `require-yarn-4` in both pre-commit manifests with `pass_filenames: false`.
- Read blocking state from Git’s index and:
  - Exit silently when no Node/package-manager artifacts exist.
  - Require each independent Node project to have a Yarn 4 project root with an exact `packageManager: "yarn@4.x.y"` pin and Yarn 4 lockfile.
  - Allow workspace manifests to inherit their containing Yarn root.
  - Reject Yarn v1/v2/v3 locks, legacy `.yarnrc`, non-v4 `yarnPath` or release binaries, competing npm/pnpm locks, and tracked or staged `node_modules/**`.
  - Allow valid Yarn 4 PnP, Zero-Install, patch, plugin, SDK, release, and version artifacts.
  - Warn without failing on every commit when ignored local `node_modules/` directories exist.
- Make failures list exact paths and Corepack/Yarn 4 recovery commands.
- Cover Corepack installation, exact version pinning, package and lock files, `.yarnrc.yml`, PnP versus node-modules, workspaces, tracked/ignored files, local commands, migrations, Docker/Compose, and GitHub Actions. [Yarn installation](https://yarnpkg.com/getting-started/install), [version pinning](https://yarnpkg.com/cli/set/version), [ignore guidance](https://yarnpkg.com/getting-started/qa), [setup-node](https://github.com/actions/setup-node)
- Prefer deterministic Corepack setup and immutable installs; explain that Node 25 no longer bundles Corepack. [Node Corepack notice](https://nodejs.org/download/release/v25.8.0/docs/api/corepack.html)

## Automated Test Plan

- Add `jsonschema` as a test dependency and update the scripts lockfile.
- Add Draft 2020-12 schema tests that automatically:
  - Resolve the shared, local, and MCP schema references.
  - Validate the repository’s real `settings.json`.
  - Accept shared `pre_commit["yarn@4"]` and unrelated local `pre_commit` keys.
  - Reject local `pre_commit["yarn@4"]`, invalid `enabled` values, and malformed policy objects.
- Add settings-sync tests for schema injection/preservation, local-policy rejection, and preventing neutral policy metadata from leaking into generated tool-native settings.
- Add temporary-repository hook tests covering:
  - No-Node silence and tracked enable/disable behavior.
  - Valid Yarn 4 single-project, workspace, nested, PnP, local-release, and Zero-Install layouts.
  - Yarn v1/v2/v3 locks, missing or invalid pins, legacy artifacts, competing locks, uncovered manifests, and tracked/staged `node_modules`.
  - Non-blocking warnings for ignored `node_modules`.
- Include all new tests in the existing unittest discovery suite and verify the pre-commit registrations through automated subprocess tests; no manual acceptance checks are required.
