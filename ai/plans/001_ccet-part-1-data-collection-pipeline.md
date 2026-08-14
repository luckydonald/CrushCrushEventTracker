# CCET Part 1 — Data Collection Pipeline

## Context

`ai/plans/init.md` specs a static GitHub Pages progress tracker for CrushCrush Parallel. Part 1 (this plan) is the Python data pipeline: scrape the Steam Community guide page (`https://steamcommunity.com/sharedfiles/filedetails/?id=2911827400`), mirror it as Markdown+images, and parse its per-event/per-character requirement tables into typed `pydantic` models written as JSON. Part 2 (Vue frontend) is out of scope here.

This repo is built on the `luckydonald/base` template — everything under `°base`-prefixed paths is generic reusable tooling, not app code. There is currently **no application code anywhere in the repo** (no `src/`, no root `pyproject.toml`, no `data/`). A prior attempt to fetch the guide page via the generic `scripts/download_ref.py` tool failed (it uses plain `urllib.request`, no SSL handling) and left only a 0-byte placeholder at `ai/references/https/steamcommunity.com/sharedfiles/filedetails/_.md`. **The real DOM structure of `#profileBlock > .guide` is unknown** — the spec's selectors (`.bb_h2`, `.bb_table`) and column assumptions are a starting hypothesis to verify against the live page, not a confirmed schema.

User decisions: new code lives in a standalone `src/ccet_crawler/` package with its own root `pyproject.toml` (`uv`-managed), separate from `scripts/°base/`. Tests mirror the package structure under `tests/ccet_crawler/**` (not a flat `tests/`). HTTP client: try `requests` with a custom SSL adapter first for the Akamai CDN TLS quirk; may fall back to `httpx` — this choice should stay swappable, not hardcoded into parsing logic. Requirement variants are discriminated by a lowercase-snake-case `StrEnum` (`kind: RequirementKind`), not a bare `Literal[...]` string.

## Learnings from the live fetch spike (already done)

The guide page was fetched for real and saved to `data/crawl/guide/raw.html` (636 KB) + `data/crawl/guide/rawish.md` (a rough `markdownify` pass, for human skimming only — not the curated `data/guide/README.md`). Concrete findings that change/confirm the design below:

- **No SSL/Akamai workaround was needed** in this environment — plain `urllib.request` and `requests` both got a 200 with just a normal browser `User-Agent` header. Build `fetch/client.py` with a plain `requests.Session` first (no custom `SSLContext`); keep `akamai_ssl.py` as an opt-in swap behind the same `HttpClient` Protocol, only implemented if a real deployment/CI environment actually fails the handshake. Don't build speculative TLS-patching code against a problem that isn't reproducing.
- **Requirement tables are div-based, not real `<table>` elements**: `.bb_table` → `.bb_table_tr` → `.bb_table_td` (all `<div>`s). Parser must `select('.bb_table_tr')` / `.bb_table_td`, not `tr`/`td`.
- **Every requirement row has exactly 4 `.bb_table_td` cells** (confirmed across 1,404 real rows, 100% consistent): column 0 is the level label, columns 1–3 are requirements classified by content pattern, not position — confirms the plan's "parse each cell independently" approach. All 9 level labels appear verbatim in every table seen (no renames in current data) — still keep the raw-label + optional-resolved-enum fallback for future events.
- **New requirement kind needed**: bare money cells like `$15`, `$1,000`, `$150,000,000` (73 occurrences) — these are not `amount item ($price)` purchases, just a flat cash amount. Add `MoneyRequirement` (`kind: RequirementKind.money`, `amount: int`) alongside the other variants in `models/requirements.py`.
- **Girls-at-level cells** only ever say `"N Girls at Lover"` in current data — keep the field generic (`level_label: str`) rather than hardcoding "Lover".
- **Hobby & Job Info section structure confirmed**, with one correction: `.bb_h2` for "Hobbies" and "Jobs", but the "Pay details (at max level and boost)" heading is `.bb_h3`, not `.bb_h2`. Section-splitting in `guide_page.py` must treat `.bb_h2, .bb_h3` as heading boundaries, not `.bb_h2` alone. Hobbies list items: `"{level} {hobby} - expected unlock {character} {level_label}"`. Jobs list items: `"Lv {level} {job_track}: {job1}, {job2}, ..., <b>{highlighted}</b>, ..."`. Pay details are plain `<br/>`-separated lines directly in the section body: `"{job_track}: ${x}/s (${y}/time block/s)"`.
- **Trailing clearfix**: every `.subSectionDesc` ends with a stray `<div style="clear: both"></div>` — parsers must ignore/skip it, not treat it as content.
- **Section/event structure confirmed exactly as spec'd**: headline suffixes `" Girl Reqs."`, `" Alt. Reqs."`, `" Hobby & Job Info"` are real and consistent (e.g. `"Spooky Event 2022 (Cassia) Girl Reqs."`, `"Outer Space Event 2025 (Loola) Alt. Reqs."`). Confirmed the Alt. Reqs duplicate case: `Outer Space Event 2025 (Loola)` has both a "Girl Reqs." and an "Alt. Reqs." section with the identical 7 girl names (Fumi, Eva, Sirina, Odango, Brie, Alpha, Loola) — validates keying `duplicate_tables.py`'s main/alt pairing by girl name within the same event. Many unrelated FAQ/summary sections precede the per-event data (e.g. "Basic information", "Summarized completion reqs. (2022-2023)") — these don't match the three heading suffixes above, so `section_classify.py`'s pattern-based classification naturally skips them without extra filtering logic.
- Main girl names can contain `&` (`"Fuzzy Festival 2025 (Ginger & Wasabi)"`) and apostrophes (`"Valentine's Event 2026 (Sugar)"`) — event-name/year/main-girl extraction regex must not assume simple word characters only.

Code style (`ai/skills/code-style/references/py.md`, must follow exactly):
- No leading-underscore "private" names — extract into a module instead.
- Python 3.14+, full type annotations, native generics (`dict[str, int]`).
- Every `if/elif/else`, `with`, `for`, `while`, `def`, `class` block ends with an aligned `# end if` / `# end with` / `# end for` / `# end while` / `# end def` / `# end class` comment.
- Write tests (stdlib `unittest`, matching `scripts/°base/tests` convention: `uv run --project . python -m unittest discover -s tests/ccet_crawler`).

## Package layout — `src/ccet_crawler/`

```
pyproject.toml                     # root-level, uv-managed, src-layout
src/ccet_crawler/
  cli.py                # argparse subcommands: fetch / parse / write / all
  config.py              # URLs, data/ paths, GIRL level order, fixed date-activity prices
  fetch/
    client.py            # HttpClient Protocol + FetchedPage — parsing layer depends only on this
    akamai_ssl.py         # requests.Session + custom HTTPAdapter/SSLContext for the Akamai TLS quirk
    httpx_client.py       # fallback HttpClient impl using httpx, swappable via config.py
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
  fetch/test_client_contract.py      # HttpClient Protocol vs stub, no live network
```

Requirement variants (`models/requirements.py`), discriminated by a `kind: RequirementKind` field where `RequirementKind` is a lowercase-snake-case `StrEnum` (`job_level`, `work_at_job`, `hobby_level`, `purchase`, `money`, `date_activity`, `girls_at_level`, `gild_jobs`, `gild_hobbies`): `JobLevelRequirement`, `WorkAtJobRequirement`, `HobbyLevelRequirement`, `PurchaseRequirement`, `MoneyRequirement` (bare cash amount, no item — real data has ~73 of these, e.g. `$15`, `$150,000,000`), `DateActivityRequirement`, `GirlsAtLevelRequirement`, `GildJobsRequirement`, `GildHobbiesRequirement`. `config.py` holds the fixed date-activity price table (Moonlight Stroll $500, Movie Theater $25,000, Sightseeing $5,000, Beach $2,500) used to fill/validate `DateActivityRequirement.price_per_date`.

`GirlLevelRow` stores both the raw level label text and an optional resolved `GirlLevel`, since levels can be renamed per event — never assume the label matches the enum verbatim.

## Fetch strategy

`fetch/client.py` defines a minimal `HttpClient` Protocol so `html/`/`models/`/`write/` never import `requests` or `httpx` directly. Since the live-fetch spike showed a plain `requests.Session` with a normal browser `User-Agent` already gets a 200 (no Akamai/TLS blocking observed), the default implementation is a plain `requests`-based client — no custom `SSLContext` needed for now. `akamai_ssl.py` stays as a documented, not-yet-needed extension point behind the same Protocol (custom `HTTPAdapter`/`SSLContext`, e.g. lowered cipher security level) in case a different network environment (CI, a different IP range) does hit the CDN block; `httpx_client.py` is the other swappable alternative. Either swap is a single constant change in `config.py` — no other module changes.

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

`argparse` subcommands in `cli.py`: `fetch`, `parse --input <path>` (dumps structured sections for inspection), `write --input <path>`, `all`. `[project.scripts] ccet-crawler = "ccet_crawler.cli:main"` for `uv run ccet-crawler ...`.

## pyproject.toml (new, root-level)

Dependencies: `requests`, `beautifulsoup4`, `pydantic>=2`, `markdownify`. Optional extra: `httpx` (fallback client only, not a hard dependency). No `pillow` (plain `hashlib` suffices), no `lxml` initially (add later only if the real page's HTML needs it — plausible for Steam Community pages, flag as likely follow-up). `[tool.uv] package = true`. Test runner: stdlib `unittest`, no `pytest`.

## Testing

Buildable now, no live HTML needed: `models/*` validation, `PayDetail.time_blocks_needed`, `event_json.py` output shape, `image_store.py` hash/de-dup via stub bytes, `sanity_checks.py`/`duplicate_tables.py` over hand-built models, and `requirement_cell.py` against every literal example string given in the spec (`Lv 2 IT Monkey (Computers)`, `Work at Tour Guide`, `1 Analytical`, `242,424 Greatsword ($12,121,200)`, `12 Moonlight Stroll`, `2 Girls at Lover`, `Gild any 1 Jobs`, `Gild any 3 Hobbies`).

`guide_page.py`/`section_classify.py`/`hobby_job_info.py` tests are built against `tests/ccet_crawler/fixtures/guide_page_sample.html` (trimmed from the already-fetched `data/crawl/guide/raw.html`, see implementation order step 4).

`fetch/client.py`'s plain-`requests` default is not conventionally unit-tested beyond its `HttpClient` Protocol contract against a stub, in `tests/ccet_crawler/fetch/test_client_contract.py`; `akamai_ssl.py`/`httpx_client.py` stay unimplemented until actually needed (see Learnings).

## Implementation order

0. ~~Fetch spike~~ — done. `data/crawl/guide/raw.html` + `rawish.md` are saved; real selectors/structure confirmed (see Learnings above).
1. `fetch/client.py` (plain `requests`-based `HttpClient`) + `cli.py fetch` subcommand, wired to (re)produce `data/crawl/guide/raw.html`/`rawish.md` the same way the spike did.
2. `models/` (spec- and learnings-driven, including `MoneyRequirement` and the confirmed 9-level enum — no dependency on further HTML work).
3. `html/requirement_cell.py` + tests, against both the spec's literal examples and real patterns confirmed above (`Lv N Job (Track)`, `Work at Track`, `N Hobby`, `N Item ($Price)`, `$Amount`, `N (Moonlight Stroll|Movie Theater|Sightseeing|Beach)`, `N Girls at Level`, `Gild any N (Jobs|Hobbies)`).
4. Build `tests/ccet_crawler/fixtures/guide_page_sample.html` by trimming `data/crawl/guide/raw.html` down to one full event (recommend the small `Spooky Event 2022 (Cassia)` pair — 2 girls — for Girl Reqs + Hobby & Job Info; a second trimmed fixture from `Outer Space Event 2025 (Loola)` to cover the Alt. Reqs duplicate-table case).
5. `html/guide_page.py`, `section_classify.py`, `girl_table.py`, `hobby_job_info.py`, `images.py` against those fixtures.
6. `assemble/` (`duplicate_tables.py`, `sanity_checks.py`).
7. `write/` (`slug.py`, `image_store.py`, `markdown_guide.py`, `event_json.py`).
8. Wire `cli.py parse`/`write`/`all`, run end-to-end against the real saved `raw.html`, spot-check `data/guide/README.md` and sample `data/events/2025/*.json` files.

## Verification

- `uv run --project . python -m unittest discover -s tests/ccet_crawler` — all non-live tests pass.
- `uv run ccet-crawler fetch` succeeds against the live Steam URL, reproducing `data/crawl/guide/raw.html` and `data/crawl/guide/rawish.md` (already confirmed working during the spike).
- `uv run ccet-crawler all` produces `data/guide/README.md` with working relative image links, and at least one plausible `data/events/2025/*.json` file that round-trips through the `Event`/`CharacterRequirementTable` models.
- Spot-check that `Event.warnings` is empty (or explicable) for at least one fully-parsed event, confirming the sanity check logic is sound.

### Key reference files
- `ai/plans/init.md` — authoritative spec
- `ai/skills/code-style/references/py.md` — style rules
- `scripts/°base/pyproject.toml` — structural precedent for the new root `pyproject.toml`
- `data/crawl/guide/raw.html` / `data/crawl/guide/rawish.md` — the real fetched guide page, already saved; use directly to build `tests/ccet_crawler/fixtures/guide_page_sample.html` and to verify selectors while implementing `html/`
