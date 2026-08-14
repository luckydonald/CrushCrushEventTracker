In the repo `/home/user/git/luckydonald/CrushCrushEventTracker`, I'm planning a Python scraper (Part 1 of an "init" plan at ai/plans/init.md) that will:
- Fetch a Steam Community guide page (https://steamcommunity.com/sharedfiles/filedetails/?id=2911827400), patching SSL to get through Akamai's CDN.
- Parse `#profileBlock > .guide` HTML with BeautifulSoup.
- Generate Markdown + download images to `/data/guide/README.md` and `/data/guide/img/<file>`.
- Parse structured event/character requirement tables into pydantic models, writing JSON to `/data/events/2025/Event_Name__Character.json`.

Please research:

1. List everything currently under `/home/user/git/luckydonald/CrushCrushEventTracker/ai/references/` recursively (it's currently untracked in git per `git status` — dir `ai/references/https/steamcommunity.com/`). Read any files found there (HTML/markdown) — is this a raw downloaded copy of the target Steam guide page already? Report file sizes/names and a short snippet if it's HTML, enough to tell if `#profileBlock > .guide` selector is present and what structure the actual page has (event headlines, tables, etc.).
2. Look at `/home/user/git/luckydonald/CrushCrushEventTracker/.agents/skills/` and `/home/user/git/luckydonald/CrushCrushEventTracker/ai/skills/` — for each of bugsink-setup, code-style, commit-with-lplp-style, coolify-compose-deploy, sanitize-error-logs — just list the file structure (don't need full contents) so I know what's available. Read `ai/skills/code-style/SKILL.md` (or equivalent) fully and report a summary, plus list what reference files exist under `ai/skills/code-style/references/` (e.g. py.md, vue.md, others).
3. Check if there's a `ai/skills/code-style/references/vue.md` and summarize briefly (for Part 2 planning context, low priority).
4. Search the whole repo (excluding .git) for any existing Python source files (`*.py`) outside of `scripts/` and `.agents`/`ai` tooling directories — i.e., is there any existing app code already, like a `src/` or `ccet/` package? Report full paths found.
5. Check `/home/user/git/luckydonald/CrushCrushEventTracker/docs/README.md` contents briefly.

Report concisely, under 600 words, with file paths and short excerpts only (not full file dumps, except keep any HTML/CSS selector snippets you find useful for understanding the guide page's DOM structure).