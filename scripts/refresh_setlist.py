#!/usr/bin/env python3
"""Poll for tonight's setlist and write data/setlist.json.

Runs from a GitHub Action during the show. The browser can't fetch either source
directly (no CORS headers), so this is the bridge: fetch server-side, commit the
JSON, let GitHub Pages serve it.

Only ONE feed runs by default -- the phish.net API v5 (needs PHISHNET_API_KEY).
Two more are implemented, tested and parked as backups:

  * phantasy-tour  — Phantasy Tour API, no key needed
  * phish.net-web  — scrapes the public phish.net setlist page, no key needed

Enable them by setting SETLIST_SOURCES (or the workflow's `sources` input), e.g.
SETLIST_SOURCES="phish.net-api,phish.net-web". No code change required.

When more than one is active, whichever returns the most songs wins; ties go to
the lower-preference source (API over scrape). The feeds were verified to agree
exactly on nights 1-3 of this run -- same lengths, and parsing 10/31/95 through
phish.net and Phantasy Tour independently produced the identical board outcome.

CAVEAT: phish.net's docs state API responses are "cached for a short period" and
that embedding data from an in-progress show needs a special method that is
"forthcoming". If the API proves laggy mid-show, add phish.net-web to
SETLIST_SOURCES -- it reads the live page and will overtake the API.

Idempotent: the file is rebuilt from scratch each run, so a re-run converges.
"""

import html as html_mod
import json
import os
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

SHOW_ID = int(os.environ.get("SHOW_ID", "62005"))          # Phantasy Tour id
SHOW_DATE = os.environ.get("SHOW_DATE", "2026-07-27")      # phish.net key
# Empty by default: the scraper resolves the URL from SHOW_DATE via a redirect.
PNET_SLUG = os.environ.get("PNET_SLUG", "").strip()
HEARTBEAT_SEC = int(os.environ.get("HEARTBEAT_SEC", "480"))
OUT = pathlib.Path(__file__).resolve().parent.parent / "data" / "setlist.json"
FEED_LOG = OUT.parent / "feed-log.jsonl"

# Both hosts sit behind bot protection and 403 a bare urllib User-Agent.
UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "application/json,text/html",
}
SET_LABELS = {"SET 1": 1, "SET 2": 2, "SET 3": 3, "SET 4": 4,
              "ENCORE": 9, "ENCORE 2": 9, "ENCORE 3": 9}


def _get(url, as_json=True, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    return json.loads(raw) if as_json else raw.decode("utf-8", "replace")


# ---------------------------------------------------------------- sources


def from_phantasy_tour():
    d = _get(f"https://www.phantasytour.com/api/shows/{SHOW_ID}/setlist")
    out = []
    for s in sorted(d.get("ShowSongs", []), key=lambda x: (x["SetNumber"], x["Position"])):
        out.append({
            "id": s["SongId"],
            "name": s["Song"]["Name"],
            "set": s["SetNumber"],          # 9 == encore
            "pos": s["Position"],
            "segue": bool(s.get("Segue")),
        })
    return out


def phishnet_api_raw():
    """Raw phish.net API v5 setlist rows, or None when no key is configured."""
    key = os.environ.get("PHISHNET_API_KEY", "").strip()
    if not key:
        return None
    url = ("https://api.phish.net/v5/setlists/showdate/"
           f"{urllib.parse.quote(SHOW_DATE)}.json?apikey={urllib.parse.quote(key)}")
    d = _get(url)
    # v5 sends error as false/0 when fine, or a numeric code plus a message.
    err = d.get("error")
    if err not in (None, False, 0, "0", "false"):
        raise RuntimeError(f"phish.net api error {err}: {d.get('error_message')}")
    return d.get("data") or []


def parse_phishnet_rows(rows):
    """Turn v5 setlist rows into our song list.

    Schema per phish.net's own sample app (github.com/phishnet/api-v5,
    scripts/setlist.js): each row carries `song`, `set`, `trans_mark`,
    `artist_name`, `isjamchart`, `jamchart_description`, `slug`.

      * `set` is 1..4 for sets and 'e' / 'e2' / 'e3' for encores.
      * `trans_mark` is the separator AFTER the song (", ", " > ", " -> ").
      * `song` is always the clean title -- unlike the website's HTML, where
        jam-charted songs put annotation prose in the title attribute.

    Row order is the setlist order (the sample app just iterates), so position is
    derived from order rather than trusting a `position` field.

    No `id` is emitted: phish.net song ids live in a different namespace from
    Phantasy Tour's and could collide, producing a false match on a board square.
    The app's title matching covers every board song (verified).
    """
    out = []
    per_set = {}
    for r in rows:
        artist = str(r.get("artist_name") or "").strip()
        artistid = str(r.get("artistid") or "")
        # The showdate endpoint can include side projects; keep Phish proper.
        if artist and artist.lower() != "phish":
            continue
        if not artist and artistid and artistid != "1":
            continue
        name = (r.get("song") or "").strip()
        if not name:
            continue
        raw_set = str(r.get("set") if r.get("set") is not None else "1").strip().lower()
        if raw_set.startswith("e"):
            setno = 9
        elif raw_set.isdigit():
            setno = int(raw_set)
        else:
            setno = 1
        per_set[setno] = per_set.get(setno, 0) + 1
        trans = str(r.get("trans_mark") or "")
        out.append({
            "name": name,
            "set": setno,
            "pos": per_set[setno],
            "segue": ">" in trans,
        })
    return out


def from_phishnet_api():
    """phish.net API v5. Returns None (= skipped) when no key is configured.

    It must NOT return [] when unconfigured: an empty list looks like a
    successful fetch of an empty setlist, which would let this source "win"
    while the real feeds are down and blank the boards.
    """
    rows = phishnet_api_raw()
    if rows is None:
        return None
    return parse_phishnet_rows(rows)


def from_phishnet_html():
    """Scrape the public setlist page — no key required.

    The URL is resolved from the date: phish.net/setlists/?d=YYYY-MM-DD 302s to
    the canonical slug, which urllib follows. That keeps this source reusable for
    any show without hand-building a slug. PNET_SLUG overrides if ever needed.
    """
    if PNET_SLUG:
        url = f"https://phish.net/setlists/{PNET_SLUG}.html"
    else:
        url = f"https://phish.net/setlists/?d={urllib.parse.quote(SHOW_DATE)}"
    page = _get(url, as_json=False)
    i = page.find("setlist-body")
    if i < 0:
        return []
    parts = re.split(r"<span class=['\"]set-label['\"]>(.*?)</span>", page[i:])
    out = []
    for k in range(1, len(parts), 2):
        label = re.sub(r"<[^>]+>", "", parts[k]).strip().upper()
        setno = SET_LABELS.get(label)
        if setno is None:
            continue
        # Take the name from the anchor's TEXT, never its title attribute: songs
        # that appear in phish.net's jam charts carry data-toggle="tooltip" and
        # their title holds annotation prose instead of the song name. Lookaheads
        # so attribute order doesn't matter.
        toks = re.findall(
            r"<a\b(?=[^>]*href=['\"]/song/)(?=[^>]*class=['\"]setlist-song['\"])[^>]*>"
            r"(.*?)</a>"
            r"([^<]*(?:<sup[^>]*>.*?</sup>)?[^<]*)",
            parts[k + 1], re.S)
        pos = 0
        for inner, tail in toks:
            name = html_mod.unescape(re.sub(r"<[^>]+>", "", inner)).strip()
            if not name:
                continue
            pos += 1
            tail_txt = re.sub(r"<[^>]+>", "", tail)
            out.append({
                "name": name,
                "set": setno,
                "pos": pos,
                "segue": bool(re.search(r"->|>|&gt;", tail_txt)),
            })
    return out


# (name, fetcher, preference) — lower preference wins a tie. phish.net is the
# canonical database, and a structured API beats scraping the same site's HTML.
ALL_SOURCES = [
    ("phish.net-api", from_phishnet_api, 0),
    ("phantasy-tour", from_phantasy_tour, 1),
    ("phish.net-web", from_phishnet_html, 2),
]

# Only these actually run. phantasy-tour and phish.net-web stay implemented and
# tested as parked backups: add them to SETLIST_SOURCES (or the workflow's
# `sources` input) to bring them back without a code change.
DEFAULT_SOURCES = "phish.net-api"


def active_sources():
    wanted = [w.strip() for w in
              os.environ.get("SETLIST_SOURCES", DEFAULT_SOURCES).split(",") if w.strip()]
    known = {name for name, _, _ in ALL_SOURCES}
    unknown = [w for w in wanted if w not in known]
    if unknown:
        raise SystemExit(f"unknown source(s) {unknown}; known: {sorted(known)}")
    return [s for s in ALL_SOURCES if s[0] in wanted]


SOURCES = None   # resolved at call time so tests can override


def collect():
    """Try every source; return (songs, winning_source_name, per_source_counts).

    `best_name` is None only when every source raised. A source that answers with
    an empty setlist has still *worked* -- that's the normal state before the
    lights go down -- so it must count as a success, or the heartbeat never fires
    and the page reports a dead feed all evening.
    """
    best, best_name, best_pref, counts, timings = [], None, None, {}, {}
    for name, fn, pref in (SOURCES if SOURCES is not None else active_sources()):
        t0 = time.monotonic()
        try:
            songs = fn()
        except Exception as e:                      # a dead source must not stop the others
            counts[name] = f"error: {type(e).__name__}"
            timings[name] = round((time.monotonic() - t0) * 1000)
            print(f"  {name}: {e}", file=sys.stderr)
            continue
        timings[name] = round((time.monotonic() - t0) * 1000)
        if songs is None:                           # deliberately skipped, not a success
            counts[name] = "skipped"
            continue
        counts[name] = len(songs)
        # Furthest ahead wins; on a tie the more trustworthy source wins.
        if best_name is None or (len(songs), -pref) > (len(best), -best_pref):
            best, best_name, best_pref = songs, name, pref
    return best, best_name, counts, timings


def log_provenance(source, counts, timings, n):
    """Record which feed supplied the data, and how far behind the others were.

    Actions logs expire, so this also appends to data/feed-log.jsonl, which gets
    committed. After the show that file answers "was the API keeping up?" —
    which is the question that decides the source config for the next show.
    """
    numeric = {k: v for k, v in counts.items() if isinstance(v, int)}
    leader = max(numeric.values()) if numeric else 0
    lag = {k: leader - v for k, v in numeric.items() if leader - v > 0}

    detail = ", ".join(
        f"{k}={v}" + (f" ({timings[k]}ms)" if k in timings else "")
        for k, v in counts.items())
    line = f"sources: {detail} -> WINNER {source} with {n}"
    if lag:
        line += " | BEHIND: " + ", ".join(f"{k} by {d}" for k, d in sorted(lag.items()))
    print(line)

    entry = {
        "t": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "showDate": SHOW_DATE, "winner": source, "count": n,
        "counts": counts, "ms": timings,
    }
    if lag:
        entry["behind"] = lag
    try:
        prev_line = None
        if FEED_LOG.exists():
            tail = FEED_LOG.read_text().strip().splitlines()
            prev_line = json.loads(tail[-1]) if tail else None
        # Only append when something meaningful moved, so the file stays readable.
        if not prev_line or (prev_line.get("winner"), prev_line.get("counts")) != (source, counts):
            with FEED_LOG.open("a") as fh:
                fh.write(json.dumps(entry) + "\n")
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"  (could not append feed log: {e})", file=sys.stderr)

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        try:
            with open(summary, "a") as fh:
                fh.write(f"- `{entry['t']}` **{source}** → {n} songs "
                         f"({detail})" + (f" — behind: {lag}" if lag else "") + "\n")
        except OSError:
            pass


def main():
    songs, source, counts, timings = collect()

    if source is None:
        # Every source raised — leave the last good file rather than blanking boards.
        print("all sources failed; leaving existing file untouched", file=sys.stderr)
        return 1

    log_provenance(source, counts, timings, len(songs))

    payload = {
        "showId": SHOW_ID,
        "showDate": SHOW_DATE,
        "fetchedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": source,
        "sourceCounts": counts,
        "sourceMs": timings,
        "count": len(songs),
        "songs": songs,
    }

    prev = None
    if OUT.exists():
        try:
            prev = json.loads(OUT.read_text())
        except json.JSONDecodeError:
            pass

    # A setlist only grows during a show. If we came back with fewer songs than we
    # already had AND some source errored, that's an outage, not Phish un-playing
    # something -- keep what we have. (With every source healthy a shrink is a
    # real moderator correction, so allow it.)
    errored = [k for k, v in counts.items() if isinstance(v, str) and v.startswith("error")]
    if (prev and prev.get("showId") == SHOW_ID
            and len(songs) < int(prev.get("count") or 0) and errored):
        print(f"refusing to shrink {prev['count']} -> {len(songs)} songs "
              f"while {', '.join(errored)} failing", file=sys.stderr)
        return 0

    # Leave the file byte-identical when nothing changed so the workflow's commit
    # step short-circuits, but force a periodic heartbeat so the page can tell
    # "no songs yet" apart from "the poller is dead".
    if prev and prev.get("songs") == songs and prev.get("source") == source:
        try:
            age = (datetime.now(timezone.utc)
                   - datetime.fromisoformat(prev["fetchedAt"])).total_seconds()
            if age < HEARTBEAT_SEC:
                print(f"no change ({len(songs)} songs, {age:.0f}s since last write)")
                return 0
        except (KeyError, TypeError, ValueError):
            pass

    OUT.write_text(json.dumps(payload, indent=1) + "\n")
    print(f"wrote {len(songs)} songs from {source}")
    return 0




def probe():
    """`python3 scripts/refresh_setlist.py --probe` — validate the phish.net API.

    Prints the response shape and the parsed result so the API contract can be
    verified from a CI log. Never prints the key or full response bodies.
    """
    print(f"probing phish.net API for showdate={SHOW_DATE}")
    try:
        rows = phishnet_api_raw()
    except Exception as e:
        print(f"  FAILED: {type(e).__name__}: {e}")
        return 1
    if rows is None:
        print("  SKIPPED: PHISHNET_API_KEY is not set in this environment")
        return 1
    print(f"  rows returned: {len(rows)}")
    if rows:
        print(f"  fields present: {sorted(rows[0].keys())}")
        for r in rows[:3]:
            print(f"    set={r.get('set')!r} song={r.get('song')!r} "
                  f"trans_mark={r.get('trans_mark')!r} artist={r.get('artist_name')!r} "
                  f"isjamchart={r.get('isjamchart')!r}")
        sets = sorted({str(r.get("set")) for r in rows})
        print(f"  distinct set values: {sets}")
    parsed = parse_phishnet_rows(rows)
    print(f"  parsed to {len(parsed)} songs; sets={sorted({s['set'] for s in parsed})}")
    print("  first 8: " + ", ".join(f"{s['name']}{'>' if s['segue'] else ''}" for s in parsed[:8]))
    if rows and not parsed:
        print("  WARNING: rows returned but none parsed — check artist filtering")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(probe() if "--probe" in sys.argv else main())
