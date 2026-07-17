# Yarn 4 Guidance and Commit Guard

## Summary

- Add `ai/skills/code-style/references/yarn.md` as a detailed Yarn 4/Berry setup guide and link it from `ts.md`.
- Add an enabled-by-default pre-commit policy that stays completely silent in repositories without Node/package-manager artifacts.
- Base the guidance on Pipbuck’s real setup/history, while using deterministic Corepack commands and current official recommendations. Corepack is preferred over global Yarn; Node 25 no longer bundles Corepack, so setup examples will install it explicitly when necessary. [Yarn installation](https://yarnpkg.com/getting-started/install), [Node Corepack notice](https://nodejs.org/download/release/v25.8.0/docs/api/corepack.html)

## Configuration and Hook Contract

- Add this tracked setting to `ai/tool-settings/settings.json` and document it in the settings README:
  ```json
  "pre_commit": {
    "yarn_4": {
      "enabled": true
    }
  }
  ```
- Treat the check as enabled when the key is absent, allowing legacy repositories to opt out only with `"enabled": false`. Machine-local settings will not override shared commit policy.
- Register a new `require-yarn-4` pre-commit hook in both `.pre-commit-config.yaml` and `.pre-commit-hooks.yaml`; it reads the complete staged index itself and receives no filenames.
- The hook exits silently when the staged tree contains no Node/Yarn signals. Otherwise it:
  - Requires every independent Node project to be covered by a project root containing `package.json`, `yarn.lock`, and an exact `packageManager: "yarn@4.x.y"` pin.
  - Accepts workspace manifests beneath a validated Yarn root without requiring each workspace to own a lockfile.
  - Requires the Yarn 4 lock signature (`__metadata.version: 8`) and rejects Yarn Classic, Yarn 2, Yarn 3, malformed, or missing lockfiles.
  - Rejects legacy `.yarnrc`, non-v4 `yarnPath`/`.yarn/releases` binaries, competing npm/pnpm lockfiles, and any tracked or staged `node_modules/**`.
  - Allows valid Yarn 4 `.pnp.*`, `.yarnrc.yml`, patches, plugins, releases, SDKs, versions, and optional Zero-Install cache artifacts.
  - Emits an actionable, non-blocking warning on every commit when ignored local `node_modules/` directories exist.
- Blocking checks use index contents so unstaged working-tree changes cannot alter what is validated; malformed settings produce an explicit configuration error.

## Yarn Guide

- Explain Yarn naming, Yarn 4’s Node requirement, exact package-manager pinning, why `npm install -g yarn` installs Classic, and deterministic initialization with Corepack plus `yarn set version 4.x`. Prefer `packageManager` over `yarnPath`, while documenting checked-in releases as an offline/exception path. [Yarn version pinning](https://yarnpkg.com/cli/set/version), [packageManager field](https://yarnpkg.com/configuration/manifest)
- Cover `package.json`, `yarn.lock`, `.yarnrc.yml`, PnP versus `nodeLinker: node-modules`, workspaces, dependency/script commands, immutable installs, editor SDKs, upgrades, and migration cleanup.
- Provide tracked/ignored file matrices for normal PnP and Zero-Install projects, including `.yarn/cache`, patches, plugins, releases, SDKs, versions, `.pnp.*`, install state, unplugged artifacts, and `node_modules`. [Official Yarn ignore guidance](https://yarnpkg.com/getting-started/qa), [cache and Zero-Installs](https://yarnpkg.com/features/caching)
- Add Docker and Compose examples using manifest-first layers, Corepack, `yarn install --immutable`, BuildKit cache mounts, required Yarn/PnP files, and separate guidance for static builds versus Node runtimes.
- Add a GitHub Actions example using current `actions/checkout@v6`, `actions/setup-node@v6`, explicit Corepack setup, and `yarn install --immutable`; avoid claiming Pipbuck has CI history, because it does not. [setup-node guidance](https://github.com/actions/setup-node), [immutable installs](https://yarnpkg.com/cli/install)
- Document the new pre-commit opt-out and recovery commands for accidental old-Yarn lockfile rewrites.

## Test Plan

- Add isolated temporary-repository tests covering enabled, disabled, missing-key default, malformed settings, and no-Node silent behavior.
- Verify valid Yarn 4 single-project, workspace, nested-project, local-release, PnP, and Zero-Install layouts.
- Verify failures for Yarn v1/v2/v3 lockfiles, missing or non-v4 `packageManager`, legacy rc/release files, competing lockfiles, uncovered manifests, and tracked/staged `node_modules`.
- Verify ignored `node_modules` warns but returns success on unrelated commits.
- Run the focused hook tests, the full `scripts/°base` unittest suite, settings-sync check, and both pre-commit hook definitions against the base repository.
