# phish-tac-toe

A setlist bingo board for **Phish at Madison Square Garden, Monday 2026-07-27 — 1995 Night**,
night 4 of a 5-night run where each show recreates a year (1992, 1993, 1994, **1995**, 1996).

Three boards (Rob, Dylan, Justin), nine songs each. A square lights up when Phish plays it.
First to three in a row wins; if two boards complete a line, the one that completed **earlier in
the show** takes it. Tapping a square opens the song's story, a famous line, and why it might drop
tonight.

**Live at:** https://robgoretsky.github.io/phish-tac-toe/

---

## How the squares were chosen

Not vibes — setlist data. Every Phish setlist from 1995 (83 shows) and from 2023 onward
(164 shows) was pulled from the [Phantasy Tour API](https://www.phantasytour.com) and scored on
two axes:

| axis | what it measures |
|------|------------------|
| `r95` | share of 1995 shows containing the song — how *1995* it is |
| `rMod` | share of shows since Jan 2023 containing it — whether they still play it |

```
score = (r95 + 0.004) ** 0.4  ×  (rMod + 0.012) ** 0.8
```

Scores are turned into probabilities with a Poisson transform, `p = 1 − exp(−λ·score)`, where λ is
solved so the probabilities sum to 21 — a typical Phish show length.

**Everything already played this run is excluded.** Phish doesn't repeat inside a run, and nights
1–3 burned 66 songs including 20 of the 30 most-played songs of 1995. That's 62% of the
probability weight gone, which is why night 4 is far more predictable than night 1 was. (Tweezer
would have ranked #3 tonight had they not burned it on Saturday.)

### Backtest

The exponents come from a backtest against this run's own first three nights — each night scored
with **that year's** play rates and with the earlier nights' songs excluded, exactly as Monday is
scored. The model put ~50% of each night's real setlist in its top picks; random guessing over the
same candidate pool would land around 17%. Calibration held up too: squares marked 30% hit about
30% of the time in that test.

It is still one model's opinion. Phish will do whatever Phish wants.

### Fairness

The centre square is **You Enjoy Myself** on all three boards. It's the biggest song left
unburned, and the model flagged it as a top pick on all three previous nights and was wrong every
time — they're saving it. Sharing it means nobody gets an edge from the single likeliest song.

The other 24 were placed by simulated annealing over 8,000 simulated versions of tonight,
balancing three things at once: **who wins the game**, who gets a line at all, and expected score.
Optimising win-rate alone isn't enough — two boards can be equally likely to complete a line while
one completes it *earlier* and takes the tiebreak every time, which is exactly what the first
attempt did (a 3-point edge to Rob that only showed up in simulation).

Validated on 60,000 further shows with a different RNG:

| board | wins the game | gets a line | avg score |
|-------|--------------|-------------|-----------|
| Rob | 28.0% | 47.8% | 4.03 / 9 |
| Dylan | 28.2% | 48.7% | 4.04 / 9 |
| Justin | 28.3% | 51.2% | 4.04 / 9 |
| nobody | 15.5% | | |

A 0.3-point spread on winning, and effectively identical average scores.

### One deliberate override

**Drowned** is on a board by choice rather than by score. Phish played The Who's entire
*Quadrophenia* for Halloween 1995, and per phish.net it's the only song from that night they ever
played more than three times — it anchored 12/31/95 at this same building.

The obvious question is whether songs carrying a year's landmark-event meaning deserve a
systematic bonus. The 1994 night is suggestive: it *opened* with Back in the USSR, from that
year's White Album Halloween costume, and the model had it at 3% — rank #117 of 146.

But the hypothesis doesn't survive testing. Sweeping a landmark multiplier (and a discount for
one-off costume-set tracks) across nights 1–3 left precision flat at 51–52%, and Back in the USSR
never moved from #117 — a uniform bonus lifts every song from that show equally, so it can't
single one out. Aggregate behaviour points the same way: songs played 1–2 times in a given year
made up 4% / 12% / 12% of each theme night while being 31% / 27% / 39% of the available
repertoire. **Theme nights lean on that year's workhorses, not its deep cuts.**

So Drowned carries its honest 9%, displayed on the square. It's a story square, and it's labelled
as one.

Related correction: the 1994 night did **not** recreate the 6/18/94 "Tweezerfest" — overlap was
38%, against a 23% baseline for a random 1994 show. They played a lot of Tweezer; they didn't
reproduce that setlist.

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

Multi-source is safe because the feeds agree. Checked against nights 1–3 of this run, Phantasy Tour and
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

Cross-checked: parsing 10/31/95 from phish.net and from Phantasy Tour independently produces the
identical board outcome (Rob 3/9 and Dylan 4/9 both complete a line, Rob takes the tiebreak).

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
matches on any of several PT song ids *and* on a normalised title. Two cases that matter tonight:

- **Taste** also hits on *The Fog That Surrounds* — what the song was called in 1995.
- **Acoustic Army** also hits on *Keyboard Army*, the fall-'95 variant. Its odds include both.

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
analysis/           ranked95.json, blurbs.json, layout.json, raw setlists
scripts/
  refresh_setlist.py   poll Phantasy Tour, write data/setlist.json
  build_data.py        analysis/ ──▶ data/
  test_logic.js        node scripts/test_logic.js
```

```bash
node scripts/test_logic.js       # 22 assertions: scoring engine, data integrity, markup/CSS
npm i && node scripts/test_dom.js     # 27 assertions: drives the real UI in jsdom
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

Song bios, lyrics and 1995 facts were researched against [phish.net](https://phish.net) and
cross-checked against the independently computed Phantasy Tour play counts.
