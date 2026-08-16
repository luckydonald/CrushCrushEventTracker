# CCET Part 1 — Data Collection Pipeline

## Context

`ai/plans/init.md` specs a static GitHub Pages progress tracker for CrushCrush Parallel. Part 1 (this plan) is the Python data pipeline: scrape the Steam Community guide page (`https://steamcommunity.com/sharedfiles/filedetails/?id=2911827400`), mirror it as Markdown+images, and parse its per-event/per-character requirement tables into typed `pydantic` models written as JSON. Part 2 (Vue frontend) is out of scope here.

This repo is built on the `luckydonald/base` template — everything under `°base`-prefixed paths is generic reusable tooling, not app code. There is currently **no application code anywhere in the repo** (no `src/`, no root `pyproject.toml`, no `data/`). A prior attempt to fetch the guide page via the generic `scripts/download_ref.py` tool failed (it uses plain `urllib.request`, no SSL handling) and left only a 0-byte placeholder at `ai/references/https/steamcommunity.com/sharedfiles/filedetails/_.md`. **The real DOM structure of `#profileBlock > .guide` is unknown** — the spec's selectors (`.bb_h2`, `.bb_table`) and column assumptions are a starting hypothesis to verify against the live page, not a confirmed schema.

User decisions: new code lives in a standalone `src/ccet_crawler/` package with its own root `pyproject.toml` (`uv`-managed), separate from `scripts/°base/`. Tests mirror the package structure under `tests/ccet_crawler/**` (not a flat `tests/`). Requirement variants are discriminated by a lowercase-snake-case `StrEnum` (`kind: RequirementKind`), not a bare `Literal[...]` string. Fetching is kept simple — plain `requests`, no client abstraction (see Learnings: no Akamai/SSL workaround is actually needed). A `crawl` subcommand combines fetch+parse+write for normal use. Every subcommand accepts `--add-to-git` to `git add` the files it wrote. The crawl is also run by a scheduled GitHub Actions workflow that commits results and opens/updates a PR.

## Learnings from the live fetch spike (already done)

The guide page was fetched for real and saved to `data/crawl/guide/raw.html` (636 KB) + `data/crawl/guide/rawish.md` (a rough `markdownify` pass, for human skimming only — not the curated `data/guide/README.md`). Concrete findings that change/confirm the design below:

- **No SSL/Akamai workaround was needed** — plain `urllib.request` and `requests` both got a 200 with just a normal browser `User-Agent` header. The spec's "patch SSL to connect through the Akamai CDN" concern doesn't reproduce; dropped the `HttpClient` Protocol/adapter abstraction entirely in favor of a single plain `requests.get(...)` call in `fetch/client.py`. If a real deployment (e.g. the GitHub Actions runner IP range) ever does get blocked, add the workaround then, against the actual failure — not speculatively.
- **Requirement tables are div-based, not real `<table>` elements**: `.bb_table` → `.bb_table_tr` → `.bb_table_td` (all `<div>`s). Parser must `select('.bb_table_tr')` / `.bb_table_td`, not `tr`/`td`.
- **Every requirement row has exactly 4 `.bb_table_td` cells** (confirmed across 1,404 real rows, 100% consistent): column 0 is the level label, columns 1–3 are requirements classified by content pattern, not position — confirms the plan's "parse each cell independently" approach. All 9 level labels appear verbatim in every table seen (no renames in current data) — still keep the raw-label + optional-resolved-enum fallback for future events.
- **New requirement kind needed**: bare money cells like `$15`, `$1,000`, `$150,000,000` (73 occurrences) — these are not `amount item ($price)` purchases, just a flat cash amount. Add `MoneyRequirement` (`kind: RequirementKind.money`, `amount: int`) alongside the other variants in `models/requirements.py`.
- **Girls-at-level cells** only ever say `"N Girls at Lover"` in current data — keep the field generic (`level_label: str`) rather than hardcoding "Lover".
- **Hobby & Job Info section structure confirmed**, with one correction: `.bb_h2` for "Hobbies" and "Jobs", but the "Pay details (at max level and boost)" heading is `.bb_h3`, not `.bb_h2`. Section-splitting in `guide_page.py` must treat `.bb_h2, .bb_h3` as heading boundaries, not `.bb_h2` alone. Hobbies list items: `"{level} {hobby} - expected unlock {character} {level_label}"`. Jobs list items: `"Lv {level} {job_track}: {job1}, {job2}, ..., <b>{highlighted}</b>, ..."`. Pay details are plain `<br/>`-separated lines directly in the section body: `"{job_track}: ${x}/s (${y}/time block/s)"`.
- **Trailing clearfix**: every `.subSectionDesc` ends with a stray `<div style="clear: both"></div>` — parsers must ignore/skip it, not treat it as content.
- **Section/event structure confirmed exactly as spec'd**: headline suffixes `" Girl Reqs."`, `" Alt. Reqs."`, `" Hobby & Job Info"` are real and consistent (e.g. `"Spooky Event 2022 (Cassia) Girl Reqs."`, `"Outer Space Event 2025 (Loola) Alt. Reqs."`). Confirmed the Alt. Reqs duplicate case: `Outer Space Event 2025 (Loola)` has both a "Girl Reqs." and an "Alt. Reqs." section with the identical 7 girl names (Fumi, Eva, Sirina, Odango, Brie, Alpha, Loola) — validates keying `duplicate_tables.py`'s main/alt pairing by girl name within the same event. Many unrelated FAQ/summary sections precede the per-event data (e.g. "Basic information", "Summarized completion reqs. (2022-2023)") — these don't match the three heading suffixes above, so `section_classify.py`'s pattern-based classification naturally skips them without extra filtering logic.
- Main girl names can contain `&` (`"Fuzzy Festival 2025 (Ginger & Wasabi)"`) and apostrophes (`"Valentine's Event 2026 (Sugar)"`) — event-name/year/main-girl extraction regex must not assume simple word characters only.
- **Building `requirement_cell.py` against all 4,212 real requirement cells (excluding the level column) surfaced 3 more patterns beyond the spec and the earlier bare-`$N` finding**: (1) money amounts over ~$1B are written as decimals with a magnitude word — `$2.19 Billion`, `$1.08 Trillion` — both as bare `MoneyRequirement`s and inside `PurchaseRequirement`'s `($...)` price; (2) date-activity counts can have thousands separators (`"1,000 Movie Theater"`), so `DateActivityRequirement`'s count regex needs `[\d,]+`, not `\d+`; (3) a new requirement kind exists, `"All Hobbies level 47"` — added `AllHobbiesLevelRequirement` (`kind: RequirementKind.all_hobbies_level`, `level: int`) to `models/requirements.py`. With all of these, `requirement_cell.py` parses 100% of real cells (verified by a one-off script iterating every `.bb_table_td` in `data/crawl/guide/raw.html`).
- **`html/guide_page.py`/`section_classify.py`/`girl_table.py`/`hobby_job_info.py` validated against the full real page**: iterating all 23 real events (47 classified sections) with zero parse errors — every girl-reqs row has exactly 3 requirements, every hobby/job/pay-detail list is non-empty. The "Pay details" body is plain text broken by literal `<br/>` sibling tags (not wrapped in its own container), so it's parsed by walking `.next_siblings` and splitting on `<br/>`/stopping at the trailing clearfix `<div>` — same technique used for the Hobbies/Jobs description text sitting between the `.bb_h2` heading and its `<ul class="bb_ul">`. Job list items can have their `<b>` (highest-rank) tag anywhere in the comma list, not just last (e.g. `Lv 4 Exorcist: ..., <b>Banshee Shusher</b>, Cursed Object Advisor, ...`) — parsed by walking the `<li>`'s child nodes in order rather than using `.get_text()`, which would lose the bold marker.
- **Guide images have no file extension in their URL** (`https://images.steamusercontent.com/ugc/<id>/<hash>/`, no trailing filename) — `image_store.py`'s extension guesser falls back to sniffing magic bytes from the downloaded content (PNG/JPEG/GIF/WEBP signatures) before giving up to `.bin`; all 3 real guide images turned out to be PNGs. End-to-end `ccet-crawler write` run against the real `data/crawl/guide/raw.html` produced 149 correct per-character JSON files and a working `data/guide/README.md` with relative `img/<hash>.png` links, confirming the whole pipeline.
- **`unittest discover -s tests/ccet_crawler` alone is broken**: since `tests/ccet_crawler/html/` mirrors `src/ccet_crawler/html/`, discovery from that start dir imports it as a top-level module literally named `html`, shadowing Python's stdlib `html` package and breaking any test that imports `beautifulsoup4` (which needs `html.entities`). Fixed by adding `tests/__init__.py` and always running discovery with `-t .` (repo root as the top-level dir) alongside `-s tests/ccet_crawler`, so modules resolve as `tests.ccet_crawler.html....` instead of bare `html....`. All verification/testing commands in this plan already reflect the `-t .` form.

Code style (`ai/skills/code-style/references/py.md`, must follow exactly):
- No leading-underscore "private" names — extract into a module instead.
- Python 3.14+, full type annotations, native generics (`dict[str, int]`).
- Every `if/elif/else`, `with`, `for`, `while`, `def`, `class` block ends with an aligned `# end if` / `# end with` / `# end for` / `# end while` / `# end def` / `# end class` comment.
- Write tests (stdlib `unittest`, matching `scripts/°base/tests` convention: `uv run --project . python -m unittest discover -t . -s tests/ccet_crawler`).

## Package layout — `src/ccet_crawler/`

```
pyproject.toml                     # root-level, uv-managed, src-layout
src/ccet_crawler/
  cli.py                # argparse subcommands: fetch / parse / write / crawl (= fetch+parse+write), each with --add-to-git
  git_add.py              # thin `git add <path>` helper shared by every subcommand's --add-to-git
  config.py              # URLs, data/ paths, GIRL level order, fixed date-activity prices
  fetch/
    client.py            # fetch_guide_page(url) -> FetchedPage, plain requests.get, no abstraction layer
  html/
    guide_page.py         # split raw HTML into ordered sections on heading boundaries
    section_classify.py   # classify each section: Girl Reqs / Alt. Reqs / Hobby & Job Info
    girl_table.py         # parse one girl's bb_table into rows
    requirement_cell.py   # parse one requirement-cell string into a Requirement variant
    hobby_job_info.py     # parse the Hobby & Job Info ul/br lists
    images.py             # collect (src_url, alt) pairs from a section
  models/
    levels.py             # GirlLevel StrEnum (Adversary..Girlfriend) + raw-label fallback
    requirements.py        # RequirementKind StrEnum (lowercase snake_case values) + Requirement discriminated union (kind: RequirementKind)
    event.py                 # Event, CharacterRequirementTable, GirlLevelRow, EventDescription
    hobby_job_summary.py      # HobbySummary, JobSummary, PayDetail, HobbyJobInfo
    fetched.py                 # FetchedPage/FetchedImage (transport-only, not domain models)
  assemble/
    duplicate_tables.py    # Girl Reqs vs Alt. Reqs — keep both, tag variant, never silently pick
    sanity_checks.py        # per-character levels vs Hobby&Job Info maxima; collect warnings
  write/
    slug.py                 # shared filename slugging (event/character names, image links)
    image_store.py            # download, sha256-hash, de-dup into data/guide/img/
    markdown_guide.py           # sections -> data/guide/README.md (via markdownify)
    event_json.py                 # Event -> data/events/2025/Event_Name__Character.json (indent=2)
tests/ccet_crawler/                 # mirrors src/ccet_crawler/ 1:1
  fixtures/guide_page_sample.html   # trimmed real page, added after step 3 below
  html/test_requirement_cell.py      # spec-example-driven, no fixture needed
  models/test_*.py
  assemble/test_sanity_checks.py, assemble/test_duplicate_tables.py
  write/test_markdown_guide.py, write/test_image_store.py, write/test_event_json.py
```

Requirement variants (`models/requirements.py`), discriminated by a `kind: RequirementKind` field where `RequirementKind` is a lowercase-snake-case `StrEnum` (`job_level`, `work_at_job`, `hobby_level`, `purchase`, `money`, `date_activity`, `girls_at_level`, `gild_jobs`, `gild_hobbies`, `all_hobbies_level`): `JobLevelRequirement`, `WorkAtJobRequirement`, `HobbyLevelRequirement`, `PurchaseRequirement`, `MoneyRequirement` (bare cash amount, no item — real data has ~73 of these, e.g. `$15`, `$150,000,000`, plus decimal-with-magnitude forms like `$2.19 Billion`), `DateActivityRequirement`, `GirlsAtLevelRequirement`, `GildJobsRequirement`, `GildHobbiesRequirement`, `AllHobbiesLevelRequirement` (`"All Hobbies level 47"`). `config.py` holds the fixed date-activity price table (Moonlight Stroll $500, Movie Theater $25,000, Sightseeing $5,000, Beach $2,500) used to fill/validate `DateActivityRequirement.price_per_date`.

`GirlLevelRow` stores both the raw level label text and an optional resolved `GirlLevel`, since levels can be renamed per event — never assume the label matches the enum verbatim.

## Fetch strategy

Kept deliberately simple per the live-fetch spike: `fetch/client.py` is one function, `fetch_guide_page(url: str) -> FetchedPage`, using `requests.get(url, headers={"User-Agent": ...}, timeout=...)`. No client abstraction, no Protocol, no pluggable backends — there's nothing to swap since the plain request already works. If a future environment (e.g. the GitHub Actions runner) turns out to be blocked, handle it then by editing this one function.

## Parsing strategy — discover DOM first

1. **`fetch` subcommand**: hits the network once, saves raw HTML to `data/crawl/guide/raw.html` and a `markdownify`-converted copy to `data/crawl/guide/rawish.md` (both are the raw crawl artifact, distinct from the final curated `data/guide/README.md`). All other stages read `raw.html` only. Already done manually for the spike (see Learnings) — the CLI subcommand should reproduce the same result.
2. The saved HTML has already been inspected; real selectors/cell shapes are captured in Learnings above. Still need to trim a representative slice into `tests/ccet_crawler/fixtures/guide_page_sample.html` (implementation order step 4).
3. **`parse` subcommand**: `guide_page.py` splits `#profileBlock > .guide`'s `.subSection.detailBox` children into sections keyed by `.subSectionTitle` text; `section_classify.py` classifies by heading-suffix pattern (`" Girl Reqs."` / `" Alt. Reqs."` / `" Hobby & Job Info"`), which also naturally filters out the guide's unrelated FAQ/summary sections. Within a section body, `.bb_h2`/`.bb_h3` are both heading boundaries (Pay details uses `bb_h3`). Table rows are `.bb_table_tr`/`.bb_table_td` divs, not real `<table>` markup. Selectors are looked up by class name (`select(...)`) so a mismatch only requires updating constants in `guide_page.py`, not the row/cell parsers.
4. **`write` subcommand**: sections → models (`assemble/`) → sanity checks → markdown + JSON writers.
5. **Duplicate tables**: when both Girl Reqs and Alt. Reqs exist, keep both as separate `CharacterRequirementTable` entries tagged `variant: "main"|"alt"` — never silently discard one.
6. **Sanity check**: compare each character-table requirement's level against `HobbyJobInfo` maxima for that event; collect mismatches into `Event.warnings` rather than hard-failing, since spec calls this "a sanity check."

## Output writing

- `image_store.py`: `hashlib.sha256(content).hexdigest()[:16]` + original extension as filename, skip if already present, return `src_url -> relative img/ path` mapping.
- `markdown_guide.py`: reuse `markdownify` (already a repo precedent via `°dllink_lib`) per section, with images rewritten to relative paths first. Writes concatenated `data/guide/README.md`.
- `event_json.py`: one JSON file per character table, `data/events/2025/<Event_Name>__<Character>.json`, via `model_dump_json(indent=2)`, filenames slugged via `write/slug.py`.

## CLI

`argparse` subcommands in `cli.py`: `fetch`, `parse --input <path>` (dumps structured sections for inspection), `write --input <path>`, and `crawl` (fetch + parse + write in sequence — the normal entry point for both local use and the GitHub workflow). Every subcommand accepts `--add-to-git`: after writing its file(s), it calls a shared `git_add.py` helper (`subprocess.run(["git", "add", str(path)])`) for each path it wrote, so the workflow doesn't need its own `git add -A` and can't accidentally stage unrelated files. `[project.scripts] ccet-crawler = "ccet_crawler.cli:main"` for `uv run ccet-crawler ...`.

## pyproject.toml (new, root-level)

Dependencies: `requests`, `beautifulsoup4`, `pydantic>=2`, `markdownify`. No `httpx` (not needed — see Fetch strategy), no `pillow` (plain `hashlib` suffices), no `lxml` initially (add later only if the real page's HTML needs it — plausible for Steam Community pages, flag as likely follow-up). `[tool.uv] package = true`. Test runner: stdlib `unittest`, no `pytest`.

## Testing

Buildable now, no live HTML needed: `models/*` validation, `PayDetail.time_blocks_needed`, `event_json.py` output shape, `image_store.py` hash/de-dup via stub bytes, `sanity_checks.py`/`duplicate_tables.py` over hand-built models, and `requirement_cell.py` against every literal example string given in the spec (`Lv 2 IT Monkey (Computers)`, `Work at Tour Guide`, `1 Analytical`, `242,424 Greatsword ($12,121,200)`, `12 Moonlight Stroll`, `2 Girls at Lover`, `Gild any 1 Jobs`, `Gild any 3 Hobbies`).

`guide_page.py`/`section_classify.py`/`hobby_job_info.py` tests are built against `tests/ccet_crawler/fixtures/guide_page_sample.html` (trimmed from the already-fetched `data/crawl/guide/raw.html`, see implementation order step 4).

`fetch/client.py` (a single `requests.get` call) is inherently a live-network concern and isn't unit-tested; it's exercised directly by the `fetch`/`crawl` subcommands against the real URL (see Verification). `git_add.py`'s helper is trivially tested by mocking `subprocess.run`.

## Implementation order

0. ~~Fetch spike~~ — done. `data/crawl/guide/raw.html` + `rawish.md` are saved; real selectors/structure confirmed (see Learnings above).
1. `fetch/client.py` (single `fetch_guide_page` function) + `git_add.py` helper + `cli.py fetch --add-to-git` subcommand, wired to (re)produce `data/crawl/guide/raw.html`/`rawish.md` the same way the spike did.
2. `models/` (spec- and learnings-driven, including `MoneyRequirement` and the confirmed 9-level enum — no dependency on further HTML work).
3. `html/requirement_cell.py` + tests, against both the spec's literal examples and real patterns confirmed above (`Lv N Job (Track)`, `Work at Track`, `N Hobby`, `N Item ($Price)`, `$Amount`, `N (Moonlight Stroll|Movie Theater|Sightseeing|Beach)`, `N Girls at Level`, `Gild any N (Jobs|Hobbies)`).
4. Build `tests/ccet_crawler/fixtures/guide_page_sample.html` by trimming `data/crawl/guide/raw.html` down to one full event (recommend the small `Spooky Event 2022 (Cassia)` pair — 2 girls — for Girl Reqs + Hobby & Job Info; a second trimmed fixture from `Outer Space Event 2025 (Loola)` to cover the Alt. Reqs duplicate-table case).
5. `html/guide_page.py`, `section_classify.py`, `girl_table.py`, `hobby_job_info.py`, `images.py` against those fixtures.
6. `assemble/` (`duplicate_tables.py`, `sanity_checks.py`).
7. `write/` (`slug.py`, `image_store.py`, `markdown_guide.py`, `event_json.py`).
8. Wire `cli.py parse`/`write`/`crawl`, each with `--add-to-git`; run end-to-end against the real saved `raw.html`, spot-check `data/guide/README.md` and sample `data/events/2025/*.json` files.
9. `.github/workflows/crawl.yml` — scheduled workflow (see below).

## GitHub Actions automation

`.github/workflows/crawl.yml`, styled after the existing `codex-issue-agent.yml` (bot git identity, `gh` CLI via `GH_TOKEN: ${{ github.token }}`, `permissions: contents: write, pull-requests: write`):

- Trigger: `schedule` (e.g. weekly cron) + `workflow_dispatch` for manual runs.
- Fixed branch name `data-crawl/guide-update` (not per-run unique) so repeated runs land on the same PR instead of opening a new one each time.
- Steps:
  1. Checkout the default branch.
  2. Check whether `data-crawl/guide-update` already exists on `origin` (`git ls-remote --exit-code --heads origin data-crawl/guide-update`). If it exists, `git switch` to it (tracking `origin/data-crawl/guide-update`) so the new commit lands on top of prior crawl commits; otherwise create it fresh off the default branch.
  3. `uv run --project . ccet-crawler crawl --add-to-git`.
  4. If `git diff --cached --quiet` reports staged changes, commit (bot identity, message like `"Update guide crawl data"`) and push the branch. If nothing is staged, stop — no PR/commit needed for an unchanged crawl.
  5. Check for an existing open PR from that branch (`gh pr list --head data-crawl/guide-update --state open`). If none exists, `gh pr create` (mirroring the codex workflow's pattern); if one exists, the push in step 4 already updated it — nothing more to do.

## Implementation workflow (for building this)

- Enable the `commit-with-lplp-style` skill for the implementation work itself.
- Commit after each completed step from Implementation order above, **before** running its tests — so if a first-pass mistake only surfaces once tests run, the fix lands as its own follow-up commit rather than being folded silently into the first one.
- Fold any unpushed `ai:` prompt/decision auto-commits into the matching implementation commit (per the skill's normal behavior), rather than leaving them as separate noise commits.

## Verification

- `uv run --project . python -m unittest discover -t . -s tests/ccet_crawler` — all tests pass.
- `uv run ccet-crawler fetch --add-to-git` succeeds against the live Steam URL, reproducing `data/crawl/guide/raw.html` and `data/crawl/guide/rawish.md` (already confirmed working during the spike), and stages them (`git status` shows them staged).
- `uv run ccet-crawler crawl` produces `data/guide/README.md` with working relative image links, and at least one plausible `data/events/2025/*.json` file that round-trips through the `Event`/`CharacterRequirementTable` models.
- Spot-check that `Event.warnings` is empty (or explicable) for at least one fully-parsed event, confirming the sanity check logic is sound.
- Dry-run the branch-reuse logic in `crawl.yml` locally (or via `act`/manual `workflow_dispatch`) at least once to confirm it correctly finds/reuses an existing `data-crawl/guide-update` branch instead of duplicating PRs.

### Key reference files
- `ai/plans/init.md` — authoritative spec
- `ai/skills/code-style/references/py.md` — style rules
- `scripts/°base/pyproject.toml` — structural precedent for the new root `pyproject.toml`
- `data/crawl/guide/raw.html` / `data/crawl/guide/rawish.md` — the real fetched guide page, already saved; use directly to build `tests/ccet_crawler/fixtures/guide_page_sample.html` and to verify selectors while implementing `html/`
- `.github/workflows/codex-issue-agent.yml` — style precedent for the new `crawl.yml` (bot git identity, `gh pr create`/`gh pr list` usage, `GH_TOKEN` wiring)
