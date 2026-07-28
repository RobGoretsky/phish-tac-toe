# phish-tac-toe

A setlist bingo board for **Phish at Madison Square Garden, Wednesday 2026-07-29 — 1996 Night**,
the final night of a 5-night run where each show recreates a year (1992, 1993, 1994, 1995, **1996**).

Three boards (Rob, Dylan, Justin), nine songs each. A square lights up when Phish plays it.
First to three in a row wins; if two boards complete a line, the one that completed **earlier in
the show** takes it. Tapping a square opens the song's story, a famous line, and why it might drop
tonight.

**Live at:** https://robgoretsky.github.io/phish-tac-toe/

---

## How the squares were chosen

Not vibes — setlist data. Every Phish setlist from 1996 (71 shows) and from 2023 onward
(165 shows) was pulled from the [Phantasy Tour API](https://www.phantasytour.com) and scored on
two axes:

| axis | what it measures |
|------|------------------|
| `r96` | share of 1996 shows containing the song — how *1996* it is |
| `rMod` | share of shows since Jan 2023 containing it — whether they still play it |

```
score = (r96 + 0.004) ** 0.4  ×  (rMod + 0.012) ** 0.8
```

`scripts/analyze96.py` (run with `uv run --with numpy scripts/analyze96.py`) regenerates the whole
analysis — rates, scores, board annealing — from `analysis/setlists_raw.json`.

Scores are turned into probabilities with a Poisson transform, `p = 1 − exp(−λ·score)`, where λ is
solved so the probabilities sum to 21 — a typical Phish show length.

**Everything already played this run is excluded.** Phish doesn't repeat inside a run, and the
first four nights burned 86 songs — almost the whole 1996 core (Divided Sky, Runaway Jim, Split
Open and Melt, Stash, Simple, Down with Disease, Taste, Theme, Free, Sample in a Jar are all
gone). Night five is played from the leftovers, which makes it the most predictable night of the
run: only 90 songs Phish played in 1996 are even still legal.

### Backtest

The exponents come from a backtest against this run's own first three nights — each night scored
with **that year's** play rates and with the earlier nights' songs excluded, exactly as Wednesday
is scored. The model put ~50% of each night's real setlist in its top picks; random guessing over
the same candidate pool would land around 17%. Calibration held up too: squares marked 30% hit
about 30% of the time in that test.

It is still one model's opinion. Phish will do whatever Phish wants.

### Fairness

The centre square is **Character Zero** on all three boards — at 94% it's the single likeliest
song left, the *Billy Breathes* set-closer that 1996 minted. (You Enjoy Myself, at 92%, is the
model's white whale: flagged as a top pick on all four previous nights and wrong all four times.
It sits on one board at its honest number — if they're ever playing it this run, it's tonight.)

The other 24 were placed by simulated annealing over 8,000 simulated versions of tonight,
balancing three things at once: **who wins the game**, who gets a line at all, and expected score.
Win-rate is the hard one: with a 94% shared centre, two boards often complete lines on the *same
song*, and the app's tiebreak hands those ties to the earlier board in the list — a structural
edge to Rob that the layout has to actively counterbalance. The anneal also can't just trust its
own 8,000 sims (the differences being optimised are close to sampling noise), so it shortlists
its best layouts and re-scores them on an independent 80,000-show batch before the final pick.

Validated on 60,000 further shows with a different RNG algorithm:

| board | wins the game | gets a line | avg score |
|-------|--------------|-------------|-----------|
| Rob | 31.4% | 57.8% | 4.51 / 9 |
| Dylan | 31.2% | 61.5% | 4.47 / 9 |
| Justin | 30.3% | 62.1% | 4.50 / 9 |
| nobody | 7.1% | | |

A 1.2-point spread on winning, and near-identical average scores. Somebody wins ~93% of the
time — the leftovers of a burned-out run are a target-rich environment.

### One deliberate override

**Hello My Baby** is on a board by choice rather than by score — the 1899 barbershop number was
1996's running a cappella gag, sung at 17 of the year's 71 shows including the Clifford Ball, but
it hasn't been in rotation for years, so it carries its honest 24% and is labelled a story square.
It displaced the #25 song by score, Fast Enough For You (29%). The year's *other* landmark song
needed no charity: **Crosseyed and Painless**, from the *Remain in Light* Halloween costume, is
back in heavy modern rotation and makes the boards at an earned 50%.

The 1995 build tested whether landmark-event songs deserve a systematic score bonus and the
backtest said no — sweeping a landmark multiplier across nights 1–3 left precision flat at
51–52%. Theme nights lean on that year's workhorses, not its deep cuts. Story squares therefore keep
their honest numbers.

---

## How it stays live

The browser can't call either setlist source directly — neither sends CORS headers, and no free
CORS proxy reaches them. So a GitHub Action does the fetching:

```
Phantasy Tour API  ─┐
phish.net API v5   ─┼─▶ scripts/refresh_setlist.py ─▶ commit data/setlist.json ─▶ Pages
phish.net web page ─┘        (longest wins)                                        │
                                              page re-fetches every 45s  ◀─────────┘
```

### Two live feeds, one parked backup

| source | key needed | status |
|--------|-----------|--------|
| `phish.net-api` | `PHISHNET_API_KEY` | **active — leads** |
| `phish.net-web` | no | **active — live fallback** |
| `phantasy-tour` | no | parked |

`phish.net-api` leads: canonical, structured, and measured ~2× faster (112–270ms vs 217–551ms).
`phish.net-web` rides along because phish.net's docs warn API responses are cached and not intended
for in-progress shows — since ties go to the API, the scrape only takes over if the API genuinely
falls behind.

Bring a backup online without touching code — set the workflow's `sources` input (or
`SETLIST_SOURCES`) to e.g. `phish.net-api,phish.net-web`. With several active, the one furthest
ahead wins and ties go to the API; the winner is shown in the setlist header.

⚠️ **Known risk.** phish.net's docs say API responses are *"cached for a short period"* and that
embedding data from an *in-progress show* requires a special method that is *"forthcoming"*. That's
exactly this use case. If the boards lag during the show, add `phish.net-web` to `sources` — it
scrapes the live page and will overtake the API automatically.

Validate the key without waiting for a show: run the workflow with **`probe: true`**. It prints the
response shape, the distinct `set` values and the parsed result, then exits without committing.
Probe a *past* `show_date` to see real rows — a future date returns zero, which proves auth works
but tells you nothing about the schema.

### Provenance logging

Every poll logs which feed supplied the data and how far behind the others were:

```
sources: phish.net-api=12 (410ms), phish.net-web=21 (281ms) -> WINNER phish.net-web with 21 | BEHIND: phish.net-api by 9
```

Actions logs expire, so the same information is appended to **`data/feed-log.jsonl`** and committed
(one line per change, not per poll) and echoed to the job summary. After a show that file answers
the question that decides the next show's config: *was the API keeping up?*

```json
{"t":"2026-07-27T23:41:02+00:00","showDate":"2026-07-27","winner":"phish.net-web",
 "count":21,"counts":{"phish.net-api":12,"phish.net-web":21},"behind":{"phish.net-api":9}}
```

### The scraper is date-driven

`phish.net/setlists/?d=YYYY-MM-DD` 302s to the canonical slug, so `phish.net-web` needs only
`SHOW_DATE` — no hand-built URL. That makes it reusable for any future show (1996 night, next tour)
by changing one input.

Multi-source is safe because the feeds agree. Checked against nights 1–4 of this run, Phantasy Tour and
phish.net reported **identical setlist lengths**, differing only in cosmetic naming — `Divided Sky`
vs `The Divided Sky`, `My Friend, My Friend` vs `My Friend My Friend`, `Run Like an Antelope` vs
`Run Like An Antelope` — all of which the app's title normaliser already collapses. So "longest
wins" tracks whichever source is furthest ahead rather than oscillating between them.

`PHISHNET_API_KEY` is a repo secret (phish.net's **private** key — never the public one, since this
repo is world-readable). Without it the API source reports `skipped` and, with the backups parked,
nothing updates — so the secret is required for the default configuration.

Two failure modes are guarded explicitly, both found by testing rather than by reasoning:

- **A skipped source must not win.** The phish.net API returns `None` when unconfigured, not `[]`.
  Returning an empty list made it look like a successful fetch of an empty setlist, so with the
  two real feeds down it "won" with zero songs and overwrote a full setlist — blanking every board.
- **Setlists don't shrink.** If a poll returns fewer songs than the file already has *and* any
  source errored, the write is refused. With every source healthy a shrink is a real moderator
  correction and is allowed through.
- **Song names come from the anchor text, not the `title` attribute.** Songs listed in phish.net's
  jam charts render with `data-toggle="tooltip"` and a `title` holding *annotation prose* instead of
  the song name. Reading the title silently dropped exactly those songs — on 10/31/95 it lost
  Drowned and You Enjoy Myself, which would have cost someone a win. `scripts/test_parsers.py`
  pins this with saved fixtures.

Cross-checked during the 1995-night build: parsing 10/31/95 from phish.net and from Phantasy Tour
independently produced the identical board outcome on that night's boards.

### Scheduling

GitHub's cron is best-effort and can fire late, so **each run polls in an 8-minute internal loop**
at 30-second intervals rather than once; with a `*/10` schedule that leaves no gap, and a
`concurrency` group stops two runs pushing over each other. `data/setlist.json` is only rewritten
when the setlist actually changes, plus a heartbeat every 8 minutes so the page's "live · Nm ago"
badge proves the pipeline is alive rather than merely quiet.

If the feed lags anyway — it's fan-updated during the show — **Manual entry** lets you mark squares
by hand. Those marks live in `localStorage` on that one device and can only *add* hits, never
remove one the feed found.

### Song matching

Phantasy Tour carries duplicate rows for the same tune and renames songs between eras, so a square
matches on its PT song id *and* on a normalised title, plus explicit aliases. The 1996 board is
tamer than 1995's (no Fog That Surrounds / Keyboard Army renames survive the burn), but
**McGrupp and the Watchful Hosemasters** still answers to *McGrupp* and the singular *…Hosemaster*,
and **Old Home Place** to *The Old Home Place*.

---

## Layout

```
index.html          the page
app.js              rendering, polling, sheets
logic.js            pure scoring — matching, win detection, tiebreak (no DOM)
styles.css
data/boards.json    the three boards            } generated by
data/songs.json     per-song copy + stats       } scripts/build_data.py
data/setlist.json   written by the refresh job
analysis/           ranked96.json, blurbs.json, layout.json, raw setlists
                    (ranked95.json is the 1995-night build, kept for reference)
scripts/
  refresh_setlist.py   poll the feeds, write data/setlist.json
  analyze96.py         setlists_raw.json ──▶ ranked96.json + layout.json (uv run --with numpy)
  build_data.py        analysis/ ──▶ data/
  test_logic.js        node scripts/test_logic.js
```

```bash
node scripts/test_logic.js       # 21 assertions: scoring engine, data integrity, markup/CSS
npm i && node scripts/test_dom.js     # 30 assertions: drives the real UI in jsdom
python3 scripts/test_parsers.py  # 19 assertions: both setlist parsers + source selection
python3 scripts/refresh_setlist.py --probe   # validate the phish.net API (needs the key)
python3 scripts/build_data.py  # regenerate data/ from analysis/
python3 -m http.server 8000    # then open http://localhost:8000
```

`test_dom.js` loads the actual `index.html`, `logic.js` and `app.js` into jsdom with `fetch`
stubbed against the local data files, then clicks through squares, sheets and board navigation.
It exists because both bugs that reached production were presentation bugs the pure-logic tests
couldn't see: overlay sheets pinned open by a `display` rule beating `[hidden]`, and a close
button that scrolled out of reach inside its own scroll container.

Song bios, lyrics and 1996 facts were researched against [phish.net](https://phish.net) and
cross-checked against the independently computed Phantasy Tour play counts.
