Good, environment has Python 3.14 and `uv` available — matches the target version.

# Implementation Plan — Part 1: Data Collection (`src/ccet_data/`)

## 0. Guiding constraints (from `ai/plans/init.md` + `ai/skills/code-style/references/py.md`)

- New root-level `uv`-managed package: `src/ccet_data/` (src-layout), own `pyproject.toml`, own `tests/`.
- Python 3.14+, full type annotations, native generics, `# end if/for/while/with/def/class` comments on every such block, no `_`-prefixed "private" module/identifier names — split into modules instead.
- Output: `data/guide/README.md` + `data/guide/img/<file>` (Markdown mirror of the guide, images downloaded/relative-linked/de-duped by hash) and `data/events/2025/Event_Name__Character.json` (pydantic-modeled, 2-space indent JSON).
- The live page's DOM is unknown — a failed generic fetch already exists at `ai/references/https/steamcommunity.com/sharedfiles/filedetails/_.md` (0 bytes), so step 1 of real implementation must be an empirical fetch, not parser-writing against assumed markup.
- Precedent worth reusing structurally (not code): `scripts/°base/ai/references/°dllink_lib/` splits `cli.py` / `config.py` / `http.py` / `html.py` / `models.py` / `paths.py` / `providers/` — a good model-split shape, minus its `urllib.request`-only HTTP layer (that's exactly what fails against Akamai) and minus its leading-underscore test filenames (`scripts/°base/tests/_git_test_helpers.py`) which violate the style rule we must follow for new code — those exist only in the old base tooling being copied from for structural precedent, not as a naming pattern to replicate. `download_ref.py`/`markdownify` is confirmed already used in this repo as the HTML→Markdown tool of choice, worth reusing for the guide-body conversion instead of hand-rolling one.

## 1. Package layout — `src/ccet_data/`

```
pyproject.toml                       # root-level, uv-managed, src-layout
src/
  ccet_data/
    __init__.py
    cli.py                # argparse subcommands: fetch / parse / write / all
    config.py              # URLs, paths (data/guide, data/events), constants (level names, date-activity costs)
    fetch/
      __init__.py
      client.py            # HttpClient protocol + fetch_page(url) -> FetchedPage
      akamai_ssl.py         # swappable TLS-adapter/context builder for requests
      httpx_client.py       # fallback implementation using httpx (only if requests/akamai_ssl fails)
    html/
      __init__.py
      guide_page.py         # top-level: split raw HTML into ordered "sections" (h1/h2 boundaries)
      section_classify.py   # classify each section: GirlReqsSection | AltReqsSection | HobbyJobInfoSection
      girl_table.py         # parse one girl's bb_table into rows of raw cell strings
      requirement_cell.py   # parse a single requirement-cell string into a Requirement variant
      hobby_job_info.py     # parse the "Hobby & Job Info" ul/br lists into summary structures
      images.py             # find <img> tags in a section body, return list of (src_url, alt)
    models/
      __init__.py
      levels.py              # GirlLevel enum (Adversary..Girlfriend) + custom-name support
      requirements.py        # Requirement discriminated union + concrete requirement models
      event.py                # Event, CharacterRequirementTable, EventDescription
      hobby_job_summary.py     # HobbySummary, JobSummary, PayDetail, HobbyJobInfo
      fetched.py               # FetchedPage, FetchedImage (transport-layer models, not domain models)
    assemble/
      __init__.py
      sanity_checks.py       # cross-check per-character tables vs Hobby&Job Info maxima
      duplicate_tables.py    # Girl Reqs vs Alt. Reqs disambiguation logic
    write/
      __init__.py
      markdown_guide.py       # writes data/guide/README.md
      image_store.py           # downloads + hashes + de-dups images into data/guide/img/
      event_json.py             # writes data/events/<year>/Event_Name__Character.json
tests/
  __init__.py
  fixtures/
    guide_page_sample.html    # saved real page (or a hand-built minimal excerpt) once fetched
  test_requirement_cell.py
  test_girl_table.py
  test_hobby_job_info.py
  test_models_requirements.py
  test_sanity_checks.py
  test_duplicate_tables.py
  test_markdown_guide.py
  test_image_store.py
  test_event_json.py
  test_fetch_client_contract.py   # tests the HttpClient protocol against a stub, not the network
```

Naming follows the "extract, don't hide" rule: instead of a private `_akamai.py` helper inside `client.py`, `akamai_ssl.py` is its own module that `client.py` imports and can be swapped for `httpx_client.py` without either module needing to know about the other's internals.

## 2. Fetch strategy — isolate the Akamai TLS workaround

Define a small `Protocol` in `fetch/client.py` so the parser layer never depends on requests vs httpx:

```python
from __future__ import annotations
from typing import Protocol

class FetchedPage:
    url: str
    status_code: int
    text: str
    # end class

class HttpClient(Protocol):
    def get(self, url: str) -> FetchedPage: ...
    # end def
# end class

def fetch_page(url: str, client: HttpClient) -> FetchedPage:
    return client.get(url)
# end def
```

`fetch/akamai_ssl.py` builds the `requests.Session` with a custom `HTTPAdapter`/`ssl.SSLContext` (e.g. `ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)` with `set_ciphers`, possibly `context.options |= ssl.OP_LEGACY_SERVER_CONNECT` or a lowered `SECLEVEL` via `context.set_ciphers("DEFAULT@SECLEVEL=1")`) and exposes a class implementing `HttpClient`. `fetch/httpx_client.py` is a drop-in alternative implementing the same `HttpClient` protocol using `httpx.Client(verify=...)`.

**First implementation task (before any parser code is written):** run a short exploratory script/REPL session against the live URL using `akamai_ssl.py`; if the TLS handshake still fails, swap to `httpx_client.py` and adjust its SSL context the same way, without touching anything under `html/` or `models/`. `cli.py`'s `fetch` subcommand picks whichever client is configured in `config.py` (a single `HTTP_CLIENT_BACKEND` constant / factory function), so switching backends is a one-line change.

This satisfies point 3's requirement that fetch strategy be swappable and explicitly empirical/exploratory rather than assumed correct up front.

## 3. Parsing strategy — discover DOM first, parse second

Step ordering, matching the "fetch / parse / write" CLI split in point 6:

1. **`ccet-data fetch`** — fetches the raw page HTML via the chosen `HttpClient` and saves it verbatim to `ai/references/https/steamcommunity.com/sharedfiles/filedetails/id_2911827400.html` (replacing/filling the previously-empty placeholder location so the existing base doc-cache convention is reused), plus a small companion `_.md` note if useful. This is the one command explicitly allowed to hit the network; everything downstream only reads that local file. This local capture also becomes the seed for `tests/fixtures/guide_page_sample.html` (trimmed to 1–2 representative events to keep the fixture small, once the real structure is known).
2. **`ccet-data parse`** — reads the saved HTML (BeautifulSoup4, `html.parser` or `lxml`), locates `#profileBlock > .guide`, and hands it to `html/guide_page.py`, which walks the guide body splitting on heading boundaries into ordered sections. `html/section_classify.py` decides, per section, whether it is a "… Girl Reqs." section, an "… Alt. Reqs." section, or a "… Hobby & Job Info" section, using the heading text pattern (`.bb_h2`/whatever the real tag turns out to be) rather than a hardcoded position.
3. **`ccet-data write`** (or `assemble` then `write`) — turns classified sections into the pydantic models (`assemble/`), runs sanity checks, then calls `write/markdown_guide.py` and `write/event_json.py`.

**Assumptions to encode as the starting hypothesis, with explicit fallback branches:**
- Expected selectors per spec: `#profileBlock > .guide` (guide root), `.bb_h2` (headline level for girl name / hobbies / jobs subheadings), `.bb_table` (the per-girl requirement tables). Code should look these up by class name via BeautifulSoup `select`, not hardcode tag names, so if the live page instead uses e.g. `.bb_h1`/`.bb_h3` for event names, only `html/guide_page.py`'s selector constants need updating, not the row/cell parsers.
- **Duplicate table disambiguation** (`assemble/duplicate_tables.py`): when both "… Girl Reqs." and "… Alt. Reqs." exist for the same event+girl, keep both `CharacterRequirementTable` variants tagged with a `variant: Literal["main", "alt"]` field rather than silently picking one; the description text (already captured per spec) is attached so a human/consumer can choose. Do not guess which is "correct" — surface both.
- **Sanity check** (`assemble/sanity_checks.py`): for each event, compare every per-character requirement's job/hobby *levels* against `HobbyJobInfo.hobbies`/`HobbyJobInfo.jobs` maxima for that event; raise (or collect into a warnings list attached to the `Event` model) if any character table requires a level higher than the summary states, and verify at least one girl matches the summary exactly. Implement this as pure functions over already-validated models, not embedded in the parser, so it's cleanly unit-testable without HTML.
- **Fallback plan if real markup doesn't match assumptions:** since step 1 saves the raw HTML before any parser code exists, the actual first coding action after fetching should be a throwaway `python -i` / notebook-style exploration (not committed) to confirm real selectors, table row shapes (are Job/Hobby/Purchase/Date/Girls-at-Level/Gild cells reliably plain text, or do they contain nested `<b>`/`<a>` markup that needs stripping?), and whether "3 columns" truly holds. Update the selector constants and `requirement_cell.py`'s regex/parsing rules accordingly; the discriminated-union model shape in section 4 below should absorb column-order/count variation without a redesign (each column is parsed independently into whichever `Requirement` variant matches its text pattern, not positionally bound to "column 2 = hobby").

## 4. Pydantic models (`src/ccet_data/models/`)

`models/levels.py`:
```python
from __future__ import annotations
from enum import StrEnum

class GirlLevel(StrEnum):
    ADVERSARY = "Adversary"
    NUISANCE = "Nuisance"
    FRENEMY = "Frenemy"
    ACQUAINTANCE = "Acquaintance"
    FRIENDZONED = "Friendzoned"
    AWKWARD_BESTIES = "Awkward Besties"
    CRUSH = "Crush"
    SWEETHEART = "Sweetheart"
    GIRLFRIEND = "Girlfriend"
# end class

GIRL_LEVEL_ORDER: list[GirlLevel] = list(GirlLevel)
```
Since levels "can be renamed for the event", the row model stores the *raw label text* plus an optional resolved `GirlLevel` (matched by position/index against `GIRL_LEVEL_ORDER` when the label doesn't match the enum verbatim), so unusual events don't crash parsing.

`models/requirements.py` — discriminated union via a `kind` literal field, one class per requirement type from the spec:

```python
from __future__ import annotations
from typing import Annotated, Literal, Union
from pydantic import BaseModel, Field

class JobLevelRequirement(BaseModel):
    kind: Literal["job_level"] = "job_level"
    level: int
    job_name: str
    job_track: str
# end class

class WorkAtJobRequirement(BaseModel):
    kind: Literal["work_at_job"] = "work_at_job"
    job_track: str
# end class

class HobbyLevelRequirement(BaseModel):
    kind: Literal["hobby_level"] = "hobby_level"
    level: int
    hobby_name: str
# end class

class PurchaseRequirement(BaseModel):
    kind: Literal["purchase"] = "purchase"
    amount: int
    item_name: str
    total_price: int
# end class

class DateActivityRequirement(BaseModel):
    kind: Literal["date_activity"] = "date_activity"
    count: int
    activity_name: str
    price_per_date: int
# end class

class GirlsAtLevelRequirement(BaseModel):
    kind: Literal["girls_at_level"] = "girls_at_level"
    count: int
    level_label: str
# end class

class GildJobsRequirement(BaseModel):
    kind: Literal["gild_jobs"] = "gild_jobs"
    count: int
# end class

class GildHobbiesRequirement(BaseModel):
    kind: Literal["gild_hobbies"] = "gild_hobbies"
    count: int
# end class

Requirement = Annotated[
    Union[
        JobLevelRequirement,
        WorkAtJobRequirement,
        HobbyLevelRequirement,
        PurchaseRequirement,
        DateActivityRequirement,
        GirlsAtLevelRequirement,
        GildJobsRequirement,
        GildHobbiesRequirement,
    ],
    Field(discriminator="kind"),
]
```

`config.py` holds the fixed date-activity price table from the spec:
```python
DATE_ACTIVITY_PRICES: dict[str, int] = {
    "Moonlight Stroll": 500,
    "Movie Theater": 25_000,
    "Sightseeing": 5_000,
    "Beach": 2_500,
}
```
`requirement_cell.py` uses this dict to fill `price_per_date` and validate parsed dates against it (mismatch = sanity-check warning, since the spec says these "should" be fixed, implying they might occasionally not be).

`models/event.py`:
```python
class GirlLevelRow(BaseModel):
    raw_level_label: str
    resolved_level: GirlLevel | None
    requirements: list[Requirement]
# end class

class CharacterRequirementTable(BaseModel):
    girl_name: str
    variant: Literal["main", "alt"] = "main"
    rows: list[GirlLevelRow]
# end class

class EventDescription(BaseModel):
    text: str
    notes: str | None = None
# end class

class Event(BaseModel):
    name: str
    year: int
    main_girl: str
    description: EventDescription
    character_tables: list[CharacterRequirementTable]
    hobby_job_info: HobbyJobInfo | None
    warnings: list[str] = []
# end class
```

`models/hobby_job_summary.py`:
```python
class HobbySummary(BaseModel):
    max_level: int
    hobby_name: str
    unlock_character: str | None
    gild_required_count: int | None = None
# end class

class JobLevelGroup(BaseModel):
    level: int
    job_track: str
    job_names: list[str]
    highlighted_job_name: str | None
# end class

class JobSummary(BaseModel):
    groups: list[JobLevelGroup]
    gild_required_count: int | None = None
# end class

class PayDetail(BaseModel):
    job_track: str
    money_per_second: int
    money_per_time_block_per_second: int

    def time_blocks_needed(self, target_money_per_second: int) -> int:
        ...
    # end def
# end class

class HobbyJobInfo(BaseModel):
    hobbies_description: str | None
    hobbies: list[HobbySummary]
    jobs_description: str | None
    jobs: JobSummary
    pay_details: list[PayDetail]
# end class
```

`models/fetched.py` keeps `FetchedPage`/`FetchedImage` (transport concerns) separate from the domain models above — these never get JSON-dumped to `data/events/`.

## 5. Output writing (`src/ccet_data/write/`)

- `write/image_store.py`: given a list of `(source_url, alt_text)` from `html/images.py`, downloads each (via the same `HttpClient`), computes `hashlib.sha256(content).hexdigest()[:16]` as the on-disk filename stem (keeping original extension), writes into `data/guide/img/<hash>.<ext>` only if not already present, and returns a `dict[str, str]` mapping original `src` → relative path `img/<hash>.<ext>` for the markdown writer to substitute.
- `write/markdown_guide.py`: converts the classified guide sections back to Markdown. Since `markdownify` is already a repo-wide dependency precedent (used by `°dllink_lib`), reuse it on each section's HTML with an `image_store`-aware pre-pass (rewrite `<img src>` to the relative path before conversion, or post-process the markdown output) rather than hand-rolling table/heading conversion — much less code and consistent with existing style. Writes the full concatenated result to `data/guide/README.md`.
- `write/event_json.py`: for each `Event`, writes `data/events/<year>/<Event_Name>__<Character>.json` per character table (spec's filename pattern is `Event_Name__Character.json`, one file per girl) using `model_dump_json(indent=2)` (native pydantic v2, no manual `json.dumps`), with `Event_Name` and `Character` slugified (spaces → underscores, strip parens/punctuation) via a small `slugify` helper — propose colocating that helper in `write/event_json.py` itself since it's tiny and single-purpose, or a shared `write/slug.py` if reused by the markdown writer too (likely yes, for `img/` filenames or anchor links) — prefer `write/slug.py` as its own module per the "extract instead of hide" rule.

## 6. CLI (`src/ccet_data/cli.py`)

`argparse` (stdlib, no extra dependency) with subcommands matching the fetch/parse/write staged pipeline from section 3, so each stage is independently runnable and testable during the DOM-discovery phase:

```
uv run --project . python -m ccet_data fetch                 # network I/O, saves raw HTML to ai/references/...
uv run --project . python -m ccet_data parse --input <path>   # HTML -> structured sections, dumps as debug JSON to stdout/scratch for inspection
uv run --project . python -m ccet_data write --input <path>   # sections -> models -> data/guide/ + data/events/
uv run --project . python -m ccet_data all                    # fetch + parse + write in sequence
```

`__main__.py` (or `if __name__ == "__main__"` block guard inside `cli.py`) wires this so it's runnable as `python -m ccet_data`. A `[project.scripts]` entry (`ccet-data = "ccet_data.cli:main"`) in `pyproject.toml` also gives a `uv run ccet-data ...` shortcut.

## 7. Testing plan

Realistically unit-testable now (no network, no real DOM needed):
- `models/*` — pydantic validation, discriminator resolution, `PayDetail.time_blocks_needed` math.
- `write/event_json.py` — given hand-built `Event` fixtures, assert exact JSON output (2-space indent, filename slugging).
- `write/image_store.py` — feed fake bytes through a stub `HttpClient`, assert hashing/de-dup logic (two identical byte blobs → one file).
- `assemble/sanity_checks.py` / `assemble/duplicate_tables.py` — pure functions over hand-built models, easy to exercise with edge cases (level exceeds summary max, missing summary, both main+alt present).
- `html/requirement_cell.py` — table-driven tests: string in → `Requirement` variant out, for every example literally given in the spec (`Lv 2 IT Monkey (Computers)`, `Work at Tour Guide`, `1 Analytical`, `242,424 Greatsword ($12,121,200)`, `12 Moonlight Stroll`, `2 Girls at Lover`, `Gild any 1 Jobs`, `Gild any 3 Hobbies`) — this can be written before the real page is even fetched, since the exact strings are given in the spec.

Inherently exploratory, deferred until after the `fetch` step produces real HTML:
- `html/guide_page.py` section-splitting and `html/section_classify.py` — needs the real fixture HTML; write these tests once `tests/fixtures/guide_page_sample.html` exists (trimmed from the real fetched page, containing at least one event with both Girl Reqs + Alt Reqs + Hobby & Job Info, to exercise the duplicate-table path too).
- `hobby_job_info.py` parsing of `ul`/`<br>`-separated pay-detail lists — same, needs a real fixture snippet since the exact separator/whitespace behavior in the live HTML is unverified.
- `fetch/akamai_ssl.py` — not unit-tested in the conventional sense (it's inherently an integration/live-network concern); at most a `test_fetch_client_contract.py` that checks the `HttpClient` Protocol contract using a stub, kept separate from any live-network smoke test which should NOT run in normal `unittest discover` (mirroring `scripts/°base/tests/test_download_link_live.py`'s naming convention of suffixing live/network tests with `_live` so they can be excluded/opted-into separately).

Run via: `uv run --project src/ccet_data python -m unittest discover -s src/ccet_data/tests` (or wherever `tests/` ends up relative to the new `pyproject.toml`'s root — likely `pyproject.toml` at repo root next to `src/`, so `uv run --project . python -m unittest discover -s tests`, matching the `scripts/°base` pattern of pyproject.toml colocated with `tests/`).

## 8. `pyproject.toml` (new, root-level, alongside `src/ccet_data/`)

```toml
[project]
name = "ccet-data"
version = "0.0.1"
description = "Data collection pipeline for the CrushCrush Event Tracker guide."
requires-python = ">=3.14"
dependencies = [
    "requests>=2.32,<3",
    "beautifulsoup4>=4.12,<5",
    "pydantic>=2.9,<3",
    "markdownify>=0.13,<2",
]

[project.optional-dependencies]
httpx-fallback = ["httpx>=0.27,<1"]

[project.scripts]
ccet-data = "ccet_data.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.uv]
package = true

[dependency-groups]
dev = []
```

Notes:
- `lxml` intentionally omitted initially — `beautifulsoup4`'s bundled `html.parser` is dependency-free and sufficient; add `lxml` only if the real page's malformed HTML needs it (common with Steam Community pages — worth flagging as a likely-needed follow-up dependency once the real fetch/parse step runs).
- `httpx` kept as an optional extra rather than a hard dependency, so `akamai_ssl.py`/`httpx_client.py` can be swapped in without bloating the base install if `requests` ends up working.
- No `pillow`/image library — `hashlib.sha256` on raw bytes is sufficient for de-dup; file extension can be derived from the URL path or `Content-Type` header without decoding the image.
- `unittest` (stdlib) as the test runner, no `pytest` dependency, matching the `scripts/°base` convention of `uv run --project <dir> python -m unittest discover -s <dir>/tests`.
- `[tool.uv] package = true` (unlike `scripts/°base`'s `package = false`) since this package defines a `src/` layout with an installable console script (`ccet-data`), not just loose helper scripts.

## Suggested implementation order

1. `fetch/client.py` (Protocol) + `fetch/akamai_ssl.py`, exploratory-test against the live URL → confirm requests-based TLS patch works, or fall back to `fetch/httpx_client.py`.
2. `cli.py fetch` subcommand, run it once to produce the real saved HTML at `ai/references/https/steamcommunity.com/sharedfiles/filedetails/id_2911827400.html`.
3. Manually inspect that HTML to confirm/adjust the assumed selectors (`#profileBlock > .guide`, `.bb_h2`, `.bb_table`) and requirement-cell string shapes; trim a representative slice into `tests/fixtures/guide_page_sample.html`.
4. `models/` (fully spec-driven, buildable in parallel with step 1–3 since it doesn't depend on real HTML).
5. `html/requirement_cell.py` + its tests (spec-example-driven, no fixture needed).
6. `html/guide_page.py`, `html/section_classify.py`, `html/girl_table.py`, `html/hobby_job_info.py`, `html/images.py` against the real fixture from step 3.
7. `assemble/duplicate_tables.py`, `assemble/sanity_checks.py`.
8. `write/slug.py`, `write/image_store.py`, `write/markdown_guide.py`, `write/event_json.py`.
9. Wire `cli.py parse`/`write`/`all`, run end-to-end against the real page, spot-check `data/guide/README.md` and a sample `data/events/2025/*.json`.

### Critical Files for Implementation
- /home/user/git/luckydonald/CrushCrushEventTracker/ai/plans/init.md
- /home/user/git/luckydonald/CrushCrushEventTracker/ai/skills/code-style/references/py.md
- /home/user/git/luckydonald/CrushCrushEventTracker/scripts/°base/ai/references/°dllink_lib/http.py (negative reference — shows the plain-urllib approach that will NOT work for Akamai)
- /home/user/git/luckydonald/CrushCrushEventTracker/scripts/°base/pyproject.toml (structural precedent for the new root `pyproject.toml`)
- /home/user/git/luckydonald/CrushCrushEventTracker/ai/references/https/steamcommunity.com/sharedfiles/filedetails/_.md (placeholder to be replaced by the real fetched HTML in step 2 of implementation)