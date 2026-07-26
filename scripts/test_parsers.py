#!/usr/bin/env python3
"""python3 scripts/test_parsers.py — tests the setlist parsers against saved HTML.

The phish.net scraper is regex-based, so it gets fixtures. The case that matters:
songs listed in phish.net's jam charts render with data-toggle="tooltip" and a
title attribute holding annotation prose rather than the song name. Reading the
title dropped exactly those songs -- including Drowned and You Enjoy Myself on
10/31/95 -- which would have silently cost someone a win.
"""
import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("refresh", ROOT / "scripts" / "refresh_setlist.py")
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)

FIX = ROOT / "scripts" / "fixtures"
passed = 0


def ok(name, fn):
    global passed
    try:
        fn()
        print(f"  ok   {name}")
        passed += 1
    except AssertionError as e:
        print(f"  FAIL {name}\n       {e}")
        sys.exit(1)


def parse(fixture):
    page = (FIX / fixture).read_text()
    R._get = lambda *a, **k: page          # noqa: E731  (stub the fetch)
    return R.from_phishnet_html()


CASES = [("phishnet-1995-10-31.html", 31), ("phishnet-2026-07-25.html", 22),
         ("phishnet-2026-07-22.html", 27)]

def _count(f, e):
    got = parse(f)
    assert len(got) == e, f"got {len(got)}, expected {e}"


for fixture, expected in CASES:
    ok(f"{fixture} parses {expected} songs",
       lambda f=fixture, e=expected: _count(f, e))


def no_prose():
    """Annotation text is long prose; song titles are not."""
    for fixture, _ in CASES:
        for s in parse(fixture):
            # Real titles are short; annotations are sentences. "Back in the
            # U.S.S.R." shows why this can't just forbid periods.
            assert len(s["name"]) <= 45 and len(s["name"].split()) <= 9, \
                f"{fixture}: prose leaked as a song name: {s['name']!r}"


ok("annotation prose never leaks into song names", no_prose)


def jam_chart_songs():
    """The regression: these two carry jam-chart tooltips on 10/31/95."""
    names = [s["name"] for s in parse("phishnet-1995-10-31.html")]
    for want in ("Drowned", "You Enjoy Myself", "Icculus"):
        assert want in names, f"{want} missing — the title-attribute bug is back"


ok("jam-chart annotated songs are still captured", jam_chart_songs)


def sets_and_encore():
    got = parse("phishnet-1995-10-31.html")
    assert sorted({s["set"] for s in got}) == [1, 2, 3, 9], \
        f"sets were {sorted({s['set'] for s in got})}"
    assert got[-1]["name"] == "My Generation", "encore not last"


ok("sets and encore map correctly", sets_and_encore)


def positions_contiguous():
    for fixture, _ in CASES:
        per = {}
        for s in parse(fixture):
            per.setdefault(s["set"], []).append(s["pos"])
        for setno, positions in per.items():
            assert positions == list(range(1, len(positions) + 1)), \
                f"{fixture} set {setno} positions not contiguous: {positions}"


ok("positions are contiguous within each set", positions_contiguous)


def skipped_not_empty():
    """An unconfigured phish.net API must report skipped, never an empty success."""
    import os
    old = os.environ.pop("PHISHNET_API_KEY", None)
    try:
        assert R.from_phishnet_api() is None, "unconfigured API returned [] not None"
    finally:
        if old is not None:
            os.environ["PHISHNET_API_KEY"] = old


ok("unconfigured phish.net API returns None, not []", skipped_not_empty)


def prefers_api_on_tie():
    """Equal-length results must resolve to the more trustworthy source."""
    same = [{"name": "Free", "set": 1, "pos": 1, "segue": False}]
    R.SOURCES = [("phish.net-api", lambda: list(same), 0),
                 ("phantasy-tour", lambda: list(same), 1),
                 ("phish.net-web", lambda: list(same), 2)]
    _, source, _, _ = R.collect()
    assert source == "phish.net-api", f"tie went to {source}"


ok("a tie prefers the phish.net API over the scrape", prefers_api_on_tie)


def longest_still_wins():
    """But being further ahead beats being preferred."""
    one = [{"name": "Free", "set": 1, "pos": 1, "segue": False}]
    two = one + [{"name": "Wilson", "set": 1, "pos": 2, "segue": False}]
    R.SOURCES = [("phish.net-api", lambda: list(one), 0),
                 ("phantasy-tour", lambda: list(two), 1)]
    songs, source, _, _ = R.collect()
    assert source == "phantasy-tour" and len(songs) == 2, f"got {source}/{len(songs)}"


ok("the source furthest ahead still wins", longest_still_wins)

API_ROWS = [
    # Shape per phishnet/api-v5 scripts/setlist.js
    {"artist_name": "Phish", "set": "1", "song": "Free", "trans_mark": " > ",
     "isjamchart": 1, "jamchart_description": "Big version with a long jam.", "slug": "free"},
    {"artist_name": "Phish", "set": "1", "song": "Wilson", "trans_mark": ", ", "isjamchart": 0},
    {"artist_name": "Phish", "set": "2", "song": "You Enjoy Myself", "trans_mark": " -> "},
    {"artist_name": "Phish", "set": "e", "song": "A Day in the Life", "trans_mark": ""},
    {"artist_name": "Phish", "set": "e2", "song": "Tweezer Reprise", "trans_mark": ""},
    {"artist_name": "Trey Anastasio Band", "set": "1", "song": "Push On Til the Day"},
    {"artist_name": "Phish", "set": "1", "song": "", "trans_mark": ", "},
]


def api_names():
    got = R.parse_phishnet_rows(API_ROWS)
    assert [s["name"] for s in got] == [
        "Free", "Wilson", "You Enjoy Myself", "A Day in the Life", "Tweezer Reprise"], got


ok("API rows parse to the right songs", api_names)


def api_jamchart_uses_song_field():
    """The API exposes annotations separately, so `song` must be used."""
    got = R.parse_phishnet_rows(API_ROWS)
    assert got[0]["name"] == "Free", f"jam-charted row became {got[0]['name']!r}"


ok("API jam-chart rows use `song`, not the description", api_jamchart_uses_song_field)


def api_sets_and_encores():
    got = R.parse_phishnet_rows(API_ROWS)
    assert [s["set"] for s in got] == [1, 1, 2, 9, 9], [s["set"] for s in got]
    assert [s["pos"] for s in got] == [1, 2, 1, 1, 2], [s["pos"] for s in got]


ok("API 'e'/'e2' map to the encore and positions reset per set", api_sets_and_encores)


def api_segues():
    got = R.parse_phishnet_rows(API_ROWS)
    assert [s["segue"] for s in got] == [True, False, True, False, False], got


ok("API trans_mark drives the segue flag", api_segues)


def api_filters_side_projects():
    names = [s["name"] for s in R.parse_phishnet_rows(API_ROWS)]
    assert "Push On Til the Day" not in names, "side project leaked in"


ok("API filters non-Phish artists", api_filters_side_projects)


def api_emits_no_ids():
    """phish.net song ids share no namespace with Phantasy Tour's, so emitting
    them as `id` could false-match a board square."""
    for s in R.parse_phishnet_rows(API_ROWS):
        assert "id" not in s, f"phish.net row emitted an id: {s}"


ok("API rows carry no id (avoids cross-source id collision)", api_emits_no_ids)


def api_rows_match_the_boards():
    """End-to-end: API-shaped names must hit the real board squares."""
    import json
    songs = json.loads((ROOT / "data" / "songs.json").read_text())
    parsed = R.parse_phishnet_rows(API_ROWS)
    norm = lambda t: (t.lower().replace("'", "").replace(".", "")
                      .replace("  ", " ").removeprefix("the ").strip())
    titles = {norm(v["title"]) for v in songs.values()}
    for want in ("Free", "Wilson", "You Enjoy Myself", "A Day in the Life"):
        assert norm(want) in titles, f"{want} is not a board song?"
    hit = [s["name"] for s in parsed if norm(s["name"]) in titles]
    assert len(hit) == 4, f"only matched {hit}"


ok("API song names match board squares", api_rows_match_the_boards)


def default_is_api_only():
    import os
    old = os.environ.pop("SETLIST_SOURCES", None)
    try:
        R.SOURCES = None
        assert [n for n, _, _ in R.active_sources()] == ["phish.net-api"], \
            "default should be phish.net-api only"
    finally:
        if old is not None:
            os.environ["SETLIST_SOURCES"] = old


ok("only phish.net-api runs by default", default_is_api_only)


def backups_still_available():
    import os
    os.environ["SETLIST_SOURCES"] = "phish.net-api,phantasy-tour,phish.net-web"
    try:
        got = [n for n, _, _ in R.active_sources()]
        assert got == ["phish.net-api", "phantasy-tour", "phish.net-web"], got
    finally:
        os.environ.pop("SETLIST_SOURCES", None)


ok("parked backups can be re-enabled without a code change", backups_still_available)

print(f"\n{passed} passed")
