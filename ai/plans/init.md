# CrushCrush Event (Progress) Tracker — CCET

This is building a static website for GitHub pages.
It is a self-service progress tracker for CrushCrush Parallel events.
The idea is that you can check off done stuff easily and hence see your next requirements clearer.


## Part 1: Data Collection
But we'll first build the data collection for it now, which will happen in python,
see @ai/skills/code-style/references/py.md.

It is a self-service progress tracker for CrushCrush Parallel events.
It is an idle game consisting of the following metrics:
- job progress
- hobby progress
- money earned
- relationship progress
- gilding jobs and hobbies

For that it will parse the guide page at `https://steamcommunity.com/sharedfiles/filedetails/?id=2911827400`.
- You need to patch ssl to connect through the akami cdn.
- Parse `#profileBlock > .guide`.
- It will firstly generate a Markdown representation and write that to disk (the tables etc.).
  - Download the images, too, link them relatively, hash them for duplicate removal.
  - Location: `/data/guide/README.md` and `/data/guide/img/<file>`


The page contains multiple seasonal events.
Generally it's structured like that, with 2 subsections per event:

1. **… Girl Reqs.**
   - Contents:
     1. Event name in first part of headline
        - Event, Year, Main Girl: e.g. `Spring Fling 2024 (Abby)`
     2. Description of the event
        - Can contain notes for reruns and such
     3. Tables per girl
        1. Headline (`.bb_h2`)
           - The name of the Girl
        2. Table itself (`bb_table`)
           - The first column is the Level of the Girl
           - Those levels are usually:
             1. Adversary
             2. Nuisance
             3. Frenemy
             4. Acquaintance
             5. Friendzoned
             6. Awkward Besties
             7. Crush
             8. Sweetheart
             9. Girlfriend
           - However, if uncommon, they _can_ be renamed for the event with a different name(s)
           - The columns after that denote the requirements:
             - Job levels (level, name of level, job): e.g. `Lv 2 IT Monkey (Computers)`, `Lv 2 Creepy Doll Disposer (Exorcist)`
               - Special case: Work at job: e.g. `Work at Tour Guide`
                 - This means you have to at least once be payd by it (basically a level 1 check)
             - Hobby levels: e.g. `1 Analytical`
             - Purchase to be made, (amount, item, price): `242,424 Greatsword ($12,121,200)`
             - Dates to do: e.g. `12 Moonlight Stroll`
               - Those _should_ be fixed:
                 1. Moonlight Stroll (`$500`)
                 2. Movie Theater (`$25,000`)
                 3. Sightseeing (`$5,000`)
                 4. Beach (`$2,500`)
             - X Girls at Level: e.g. `2 Girls at Lover`
             - Gild X Jobs: e.g. `Gild any 1 Jobs`
             - Gild X Hobbies: e.g. `Gild any 3 Hobbies`
           - Usually it's exactly 3 columns, but it may be flexable in the future.
   - Possibly is duplicated with **… Alt. Reqs.**, for slightly different tables.
     - In that case you must be able to choose which, the description and girl names should be enough to describe.
2. **… Hobby & Job Info**
   - Those are mostly summary tables to show you what the max level per hobby/job you'll ever need to finish successfully.
     - Hence, a sanity check would be to make sure that no character table is bigger than that; and one or more should match it exactly.
   - Contents:
     1. Event name in first part of headline
        - Event, Year, Main Girl: e.g. `Spring Fling 2024 (Abby)`, like with the tables above.
     2. Description of the event
        - Can contain notes for reruns and such; then usually repeats (parts) of the first description
        - Can be missing
     3. **Hobbies**
        - `.bb_h2` headline
        - description (body text under headline before list)
        - `ul` with the max level of hobbies to be archived to be able to finish
          - Format: level, hobby, expected unlock character: e.g. `69 Responsible - expected unlock Mallory Adversary`
          - Special guild requirements: e.g. `1 hobby must be gilded.`
     4. **Jobs**
        - `.bb_h2` headline
        - description
          - Usually: `Bold text indicates highest rank required. 3 jobs must be gilded.`
        - `ul` with the jobs listed:
          - e.g.: `Lv 5 Spring Mascot: Rabbit’s Foot Holder, Faux-Fur Wearer, Cottontail Copycat, Jelly Bean Distributor, **Bunny Kigu Model**, Silly Rabbit, Hare Apparent, Painted Egg Provider, Spring Festival Mascot, Mechanical Rabbit Suit Operator`
          - so Level, Job name, List of jobs level names with the same Level as the number in bold.
     5. **Pay details (at max level and boost)**
        - `<br>` separated "list".
        - Format: Job, Money per second, Money per time block per second
          - e.g.: `Florist: $4,688,964/s ($520,996/time block/s)`
          - should allow to calculate the timeblocks per job needed, too.

Those should be parsed into well-formatted `pydantic` models, with the checks as mentioned before run on them too.
Then they'll be written to disk as well, with 2 spaces indent.
Those write to `/data/events/2025/Event_Name__Character.json`.


-----

## Part 2: Frontend
It shall use vue 3, see @ai/skills/code-style/references/vue.md
It will use the provided data statically, utilizing fully typescripted stuff.
<!-- TODO: later -->
