# Make clean branches trailer-free while preserving split metadata in history

## Summary

Newly generated or rebuilt clean commits—including merge-resolution commits and `master` integration commits—will contain no `X-Base-*` trailers. All provenance, cursors, and merge-registration metadata moves to history-side structures; existing published clean/master history is not rewritten.

## Clean/history split changes

- Strip every trailing `X-Base-*` entry from clean commit messages, including inherited source-message trailers; do not add split trailers during clean projection.
- Skip clean projections whose filtered tree is unchanged, count them separately from AI-only skips, and retain their history-side empty commits.
- Replace clean-message cursoring with durable forward cursor refs under `refs/base-split/forward-cursor/{clean,history}/<branch>`. Update each cursor after its target is safely advanced, including all-skipped runs and partial merge handling; retain legacy trailer reads only as a one-time migration fallback.
- Keep source, kind, counterpart, merge, and clean-projection patch identity in `ai/history/<branch>`. Pair trailer-free clean commits with history commits by stable clean patch ID, in chronological one-to-one order; report an unresolved/ambiguous prior pair as divergence rather than silently reconstructing the wrong unclean commit.
- Add an internal, empty JSON manifest commit on `ai/history/<branch>` whenever its clean tip changes or is rebased. The manifest records the branch and clean-tip SHA; reverse sync ignores it as workflow metadata.

## History-master integration

- Stop scanning `master` commit messages for `X-Base-Split-Clean-Branch`.
- Discover merge/fast-forward integrations by scanning the newest history manifests and finding a manifest clean tip newly reachable from `master`; replay that branch’s non-metadata history and write the existing history-master marker.
- Add `update-history-master --register-clean-merge BRANCH=MASTER_SHA` for squash merges. Validate that `MASTER_SHA` is reachable from `master`, replay the named branch’s history once, and record the history-side marker so later runs are idempotent.
- Preserve legacy master-trailer detection only for pre-existing history during the migration period; never emit those trailers again.

## Test plan

- Update split tests to assert clean projections have no `X-Base-*` trailers while their history counterparts retain the required source/provenance metadata.
- Add the reported two-empty-commit regression: clean creates only the widget-style code projection; history preserves the two empty provenance commits; a rerun creates nothing.
- Cover reverse reconstruction from trailer-free clean plus history patch metadata, cursor migration/idempotency, clean merge-resolution output, and unresolved-pair diagnostics.
- Cover manifest-based merge/fast-forward detection and explicit squash registration; ensure internal manifest commits are never replayed into unclean.
- Reproduce the original target in a fresh `/tmp` clone at `ai/UNCLEAN/XXXXXX-manual-widget-refresh` / `cc6a7ba…`, deleting only its local clean/history refs and retaining `ai/history/master`; verify auto-mode produces one trailer-free clean code commit from `336441f…`.

## Assumptions

- “Clean” includes `master`; no newly created clean/master commit may carry an `X-Base-*` trailer.
- Existing published clean/master commits remain unchanged.
- Squash merges require the explicit registration flag; merge and fast-forward integrations remain automatic.
