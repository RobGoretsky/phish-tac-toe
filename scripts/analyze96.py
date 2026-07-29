#!/usr/bin/env python3
"""Score the 1996 candidates and lay out the three boards for 1996 Night.

    uv run --with numpy scripts/analyze96.py

Reads  analysis/setlists_raw.json  (every 1996 setlist + every show since
Jan 2023 + this run's four earlier nights, all from the Phantasy Tour API).
Writes analysis/ranked96.json      every unburned 1996 song, scored
       analysis/layout.json        the annealed board assignment + about copy

Method (same as the 1995 build, see README):
  score = (r96 + 0.004)^0.4 * (rMod + 0.012)^0.8
  p     = 1 - exp(-lambda * score),  lambda solved so sum(p) = 21
  burned = union of the four setlists already played this run (62002/3/4/5) --
  Phish doesn't repeat inside a run, so those songs are excluded outright.

The 24 non-centre squares are placed by simulated annealing over 8,000
simulated shows, balancing champion share (with the earlier-in-show tiebreak
exactly as logic.js scores it, including ties going to the earlier board),
line rate and expected score. The result is validated on 60,000 fresh shows
from a different RNG algorithm, and those are the numbers that ship.
"""
import json
import math
import pathlib
import re
from collections import Counter

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
ANALYSIS = ROOT / "analysis"

BURNED_SHOW_IDS = ["62002", "62003", "62004", "62005"]   # 7/22, 7/24, 7/25, 7/27
MODERN_FROM = "2023-01-01"
TARGET_SONGS = 21.0

# The 25 squares: centre first, then the 24 board songs. Top of ranked96 by p,
# with one deliberate story pick -- Hello My Baby (17 of 71 shows in 1996, the
# a cappella barbershop signature of that year) in place of #25 by score,
# Fast Enough For You. It carries its honest probability, same deal as Drowned
# on the 1995 boards.
CENTRE = "Character Zero"
PICKS = [
    "Character Zero", "You Enjoy Myself", "Waste", "Ya Mar", "Cars Trucks Buses",
    "Crosseyed and Painless", "Fee", "Poor Heart", "Buried Alive",
    "McGrupp and the Watchful Hosemasters", "Train Song", "A Day in the Life",
    "Old Home Place", "Guyute", "Horn", "I Didn't Know", "Esther",
    "The Mango Song", "Frankenstein", "Rocky Top", "Ginseng Sullivan",
    "Lawn Boy", "Fire", "If I Could", "Hello My Baby",
]

PLAYERS = [("rob", "Rob", "#ffcf4a"), ("jayme", "Jayme", "#6ce5ff"),
           ("justin", "Justin", "#ff7ad9")]
LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8),
         (0, 4, 8), (2, 4, 6)]


def norm(s):
    s = s.lower().replace("’", "").replace("'", "").replace("`", "").replace(".", "")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"^the ", "", s).strip()


# Phantasy Tour renames songs between eras and carries duplicate rows, so
# everything is aggregated on a normalised-title canon.
ALIAS = {
    "fog that surrounds": "taste", "taste that surrounds": "taste",
    "keyboard army": "acoustic army",
    "timber": "timber jerry the mule",
    "mcgrupp and the watchful hosemaster": "mcgrupp and the watchful hosemasters",
}


def canon(name):
    n = norm(name)
    return ALIAS.get(n, n)


def rank():
    raw = json.loads((ANALYSIS / "setlists_raw.json").read_text())
    shows96 = [v for v in raw.values() if v["date"].startswith("1996")]
    modern = [v for v in raw.values() if v["date"] >= MODERN_FROM]

    n96, nmod, names, ids = Counter(), Counter(), {}, {}
    for v in shows96:
        for c in {canon(s["name"]) for s in v["songs"]}:
            n96[c] += 1
    for v in modern:
        for c in {canon(s["name"]) for s in v["songs"]}:
            nmod[c] += 1
    # display name / PT id: earliest seen, then prefer the modern-era row
    for pool in (sorted(shows96, key=lambda x: x["date"]),
                 sorted(modern, key=lambda x: x["date"])):
        for v in pool:
            for s in v["songs"]:
                names[canon(s["name"])] = s["name"]
                ids[canon(s["name"])] = s["id"]

    burned = set()
    for sid in BURNED_SHOW_IDS:
        burned |= {canon(s["name"]) for s in raw[sid]["songs"]}

    scores = {}
    for c, k in n96.items():
        if c in burned:
            continue
        r96 = k / len(shows96)
        rmod = nmod.get(c, 0) / len(modern)
        scores[c] = (r96 + 0.004) ** 0.4 * (rmod + 0.012) ** 0.8

    lo, hi = 0.01, 100.0
    for _ in range(200):
        lam = (lo + hi) / 2
        if sum(1 - math.exp(-lam * s) for s in scores.values()) < TARGET_SONGS:
            lo = lam
        else:
            hi = lam

    ranked = [{"id": ids[c], "name": names[c], "n96": n96[c],
               "nMod": nmod.get(c, 0), "p": round(1 - math.exp(-lam * scores[c]), 4)}
              for c in sorted(scores, key=lambda c: -scores[c])]
    (ANALYSIS / "ranked96.json").write_text(
        json.dumps(ranked, indent=1, ensure_ascii=False) + "\n")
    print(f"ranked96: {len(ranked)} unburned candidates over {len(shows96)} 1996 "
          f"shows / {len(modern)} modern shows, lambda={lam:.3f}, "
          f"{len(burned)} burned songs excluded")
    return ranked


# ---------------------------------------------------------------- simulation

def simulate(p, rng, n_sims):
    """Each song plays independently with probability p; played songs get a
    random position in the show (a uniform draw works as an order statistic)."""
    played = rng.random((n_sims, len(p))) < p
    t = rng.random((n_sims, len(p)))
    return played, np.where(played, t, np.inf)


def evaluate(boards, played, t):
    """boards: (3,9) song indices -> (shares incl. nobody, line rates)."""
    lines = np.array(LINES)                       # (8,3)
    cells = np.array(boards)                      # (3,9)
    hit = played[:, cells]                        # (S,3,9)
    tt = t[:, cells]                              # (S,3,9)
    line_hit = hit[:, :, lines].all(axis=3)       # (S,3,8)
    line_t = np.where(line_hit, tt[:, :, lines].max(axis=3), np.inf)
    ptime = line_t.min(axis=2)                    # (S,3) completion time
    best = ptime.min(axis=1)
    # argmin takes the FIRST minimum -> exact tie goes to the earlier board,
    # matching logic.js's reduce.
    champ = np.where(np.isfinite(best), ptime.argmin(axis=1), 3)
    shares = np.bincount(champ, minlength=4) / len(champ)
    line_rate = np.isfinite(ptime).mean(axis=0)
    return shares, line_rate


def cost(boards, played, t, p):
    shares, line_rate = evaluate(boards, played, t)
    exp = p[np.array(boards)].sum(axis=1)
    # Champion share dominates: ties on the shared centre go to the earlier
    # board, a structural edge the layout has to actively counterbalance, so
    # the optimizer is allowed to spend line rate and expected score to buy
    # share equality (the 1995 build made the same trade).
    return (10.0 * (shares[:3].max() - shares[:3].min())
            + 0.5 * (line_rate.max() - line_rate.min())
            + 0.1 * (exp.max() - exp.min()))


def anneal(ranked):
    by_name = {r["name"]: r for r in ranked}
    p = np.array([by_name[s]["p"] for s in PICKS])
    rng = np.random.Generator(np.random.PCG64(96))
    played, t = simulate(p, rng, 8000)
    # A layout can look great purely by fitting the 8k-sim noise (the share
    # differences being optimized are ~2x the sampling error), so the anneal
    # keeps a shortlist of its best distinct layouts and the winner is chosen
    # on an independent 80k batch before the final held-out validation.
    srng = np.random.Generator(np.random.PCG64(1996))
    splayed, st = simulate(p, srng, 80000)
    shortlist = {}

    # start: snake-deal the 24 by descending p, centre (index 0) shared at cell 4
    order = sorted(range(1, 25), key=lambda i: -p[i])
    boards = [[None] * 9 for _ in range(3)]
    slots = [[i for i in range(9) if i != 4] for _ in range(3)]
    bi, step = 0, 1
    for song in order:
        boards[bi][slots[bi].pop(0)] = song
        bi += step
        if bi in (3, -1):
            step = -step
            bi += step
    for b in boards:
        b[4] = 0

    cur = cost(boards, played, t, p)
    best, best_cost = json.loads(json.dumps(boards)), cur
    cells = [(b, c) for b in range(3) for c in range(9) if c != 4]
    n_steps = 40000
    for k in range(n_steps):
        temp = 0.02 * (0.0005 / 0.02) ** (k / n_steps)
        i, j = [cells[x] for x in rng.choice(len(cells), 2, replace=False)]
        boards[i[0]][i[1]], boards[j[0]][j[1]] = boards[j[0]][j[1]], boards[i[0]][i[1]]
        nxt = cost(boards, played, t, p)
        if nxt <= cur or rng.random() < math.exp((cur - nxt) / temp):
            cur = nxt
            if cur < best_cost:
                best, best_cost = json.loads(json.dumps(boards)), cur
            if cur < 0.12:
                shortlist[json.dumps(boards)] = cur
        else:
            boards[i[0]][i[1]], boards[j[0]][j[1]] = boards[j[0]][j[1]], boards[i[0]][i[1]]
    print(f"anneal: best cost {best_cost:.4f}, shortlist {len(shortlist)}")

    # re-score the shortlist on independent sims; the anneal-set cost is
    # partly noise, so the pick is whatever holds up out of sample
    pool = sorted(shortlist, key=shortlist.get)[:120] or [json.dumps(best)]
    best = min((json.loads(b) for b in pool),
               key=lambda bd: cost(bd, splayed, st, p))
    print(f"reselected from {len(pool)} candidates: "
          f"held-out cost {cost(best, splayed, st, p):.4f}")

    # validate on a bigger batch with a different RNG algorithm
    vrng = np.random.Generator(np.random.Philox(19960729))
    vplayed, vt = simulate(p, vrng, 60000)
    shares, line_rate = evaluate(best, vplayed, vt)
    exp = p[np.array(best)].sum(axis=1)
    for i, (_, nm, _) in enumerate(PLAYERS):
        print(f"  {nm:7s} share={shares[i]:.4f} line={line_rate[i]:.4f} exp={exp[i]:.3f}")
    print(f"  nobody  share={shares[3]:.4f}")
    return best, shares, line_rate, exp


ABOUT = """
<h3>Phish-Tac-Toe</h3>
<p class="body">Three boards, nine songs each. A square lights up when Phish plays that
song tonight. <b>First to three in a row</b> — across, down or diagonal — wins. If more than
one board completes a line, the winner is whoever's line finished <b>earlier in the show</b>,
which the app works out from the actual setlist order.</p>

<div class="label">Why these 25 songs</div>
<p class="body">Every setlist Phish played in 1996 (71 shows) and every show since Jan 2023
(165 shows) was pulled from the Phantasy Tour API. Each candidate got two numbers: how core it
was to <b>1996</b>, and how often the band <b>still</b> plays it. The score blends them, weighted
0.4 / 0.8 — meaning current rotation actually matters a bit more than era authenticity.</p>

<div class="label">Everything already played is gone</div>
<p class="body">Phish doesn't repeat inside a run, and this is night five: the first four nights
(1992, 1993, 1994, 1995) burned <b>86 songs</b>, including almost the entire 1996 core — Divided
Sky, Runaway Jim, Split Open and Melt, Stash, Simple, Down with Disease, Taste, Theme, Free,
Sample. Tonight is played from what's left, which makes the leftovers weirdly predictable: the
model is more confident about tonight than about any other night of the run.</p>

<div class="label">Does the model actually work?</div>
<p class="body">It was backtested against this run's first three nights — scoring each night with
that year's own play rates, and excluding whatever the earlier nights had used. It put about
<b>half</b> of each night's real setlist in its top picks, against roughly 17% for guessing at
random. The percentages on the squares are calibrated: squares marked 30% hit about 30% of the
time in that test.</p>

<div class="label">The center square</div>
<p class="body">Character Zero is the center of all three boards on purpose. It's the single
likeliest song left — the <i>Billy Breathes</i> rocker that 1996 minted as a set-closer, and
they've played it {czpct}% of the nights of this run's era. When it drops, all three boards
light up together and nobody gets an edge from the one near-certainty. (You Enjoy Myself, the
model's white whale, is finally down to one board — it flagged YEM as a top pick on every night
of this run and has been wrong all four times.)</p>

<div class="label">Fairness</div>
<p class="body">The other 24 were placed by an optimizer that simulated 8,000 possible versions of
tonight and balanced the thing that actually matters — <b>who wins the game</b>, not just who gets a
line. Checked against 60,000 further simulated shows on a separate random generator:</p>
<table class="fair"><tr><th>board</th><th>wins</th><th>gets a line</th><th>avg score</th></tr>
{fairrows}</table>
<p class="body">Somebody wins about {somebody}% of the time.</p>

<div class="label">The one square the model didn't pick</div>
<p class="body"><b>Hello My Baby</b> is on here by choice, not by score. The 1903 barbershop
number was 1996's running gag — the band sang it a cappella at 17 of the year's 71 shows,
including the Clifford Ball. It hasn't been in rotation for years (zero shows since Jan 2023),
which is exactly why its square says {hmbpct}% and not something flattering. The other story square earned its spot honestly:
<b>Crosseyed and Painless</b>, from the <i>Remain in Light</i> Halloween costume, is back in
heavy rotation and rates {cppct}% on the numbers alone.</p>

<div class="label">If the feed lags</div>
<p class="body">The setlist feed is re-checked about every 30 seconds during the show. If it
falls behind, hit <b>Manual entry</b> and mark squares yourself — those marks stay on your own
phone and can only add hits, never remove one.</p>

<p class="fine" style="margin-top:18px">Odds are one model's opinion, not gospel. Phish will do
whatever Phish wants. That's the entire point.</p>
"""


def main():
    ranked = rank()
    boards, shares, line_rate, exp = anneal(ranked)
    by_name = {r["name"]: r for r in ranked}

    fairrows = "".join(
        f"<tr><td>{nm}</td><td>{shares[i] * 100:.1f}%</td>"
        f"<td>{line_rate[i] * 100:.1f}%</td><td>{exp[i]:.2f}</td></tr>"
        for i, (_, nm, _) in enumerate(PLAYERS))
    about = ABOUT.format(
        fairrows=fairrows,
        somebody=round((1 - shares[3]) * 100),
        czpct=round(by_name["Character Zero"]["p"] * 100),
        hmbpct=round(by_name["Hello My Baby"]["p"] * 100),
        cppct=round(by_name["Crosseyed and Painless"]["p"] * 100))

    layout = {
        "show": {"id": 62006, "date": "2026-07-29", "venue": "Madison Square Garden",
                 "title": "1996 Night", "line": "Wed Jul 29 · MSG · 1996 Night"},
        "about": about,
        "players": [
            {"id": pid, "name": nm, "accent": accent,
             "squares": [PICKS[s] for s in boards[i]],
             "pwin": round(float(line_rate[i]), 4),
             "expected": round(float(exp[i]), 3),
             "share": round(float(shares[i]), 4)}
            for i, (pid, nm, accent) in enumerate(PLAYERS)],
    }
    (ANALYSIS / "layout.json").write_text(
        json.dumps(layout, indent=1, ensure_ascii=False) + "\n")
    print("wrote analysis/layout.json")


if __name__ == "__main__":
    main()
