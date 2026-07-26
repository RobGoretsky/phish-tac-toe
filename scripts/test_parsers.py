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
    _, source, _ = R.collect()
    assert source == "phish.net-api", f"tie went to {source}"


ok("a tie prefers the phish.net API over the scrape", prefers_api_on_tie)


def longest_still_wins():
    """But being further ahead beats being preferred."""
    one = [{"name": "Free", "set": 1, "pos": 1, "segue": False}]
    two = one + [{"name": "Wilson", "set": 1, "pos": 2, "segue": False}]
    R.SOURCES = [("phish.net-api", lambda: list(one), 0),
                 ("phantasy-tour", lambda: list(two), 1)]
    songs, source, _ = R.collect()
    assert source == "phantasy-tour" and len(songs) == 2, f"got {source}/{len(songs)}"


ok("the source furthest ahead still wins", longest_still_wins)

print(f"\n{passed} passed")
