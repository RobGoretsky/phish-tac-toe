#!/usr/bin/env python3
"""Poll for tonight's setlist and write data/setlist.json.

Runs from a GitHub Action during the show. The browser can't fetch either source
directly (no CORS headers), so this is the bridge: fetch server-side, commit the
JSON, let GitHub Pages serve it.

Three independent sources, because the one night this has to work is the one
night we can't debug it:

  1. Phantasy Tour API      — no key needed
  2. phish.net API v5       — needs PHISHNET_API_KEY; skipped silently if unset
  3. phish.net setlist page — no key needed, scraped from HTML

Whichever returns the most songs wins. The two feeds were verified to agree
exactly on nights 1-3 of this run (same lengths, only cosmetic name differences
that the app's matcher already normalises away), so "longest wins" tracks
whichever source is furthest ahead rather than flip-flopping between them.

Idempotent: the file is rebuilt from scratch each run, so a re-run converges.
"""

import html as html_mod
import json
import os
import pathlib
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

SHOW_ID = int(os.environ.get("SHOW_ID", "62005"))          # Phantasy Tour id
SHOW_DATE = os.environ.get("SHOW_DATE", "2026-07-27")      # phish.net key
PNET_SLUG = os.environ.get(
    "PNET_SLUG", "phish-july-27-2026-madison-square-garden-new-york-ny-usa")
HEARTBEAT_SEC = int(os.environ.get("HEARTBEAT_SEC", "480"))
OUT = pathlib.Path(__file__).resolve().parent.parent / "data" / "setlist.json"

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


def from_phishnet_api():
    """phish.net API v5. Returns None (= skipped) when no key is configured.

    It must NOT return [] here: an empty list looks like a successful fetch of an
    empty setlist, which would let this source "win" while the real feeds are
    down and blank the boards.
    """
    key = os.environ.get("PHISHNET_API_KEY", "").strip()
    if not key:
        return None
    url = ("https://api.phish.net/v5/setlists/showdate/"
           f"{urllib.parse.quote(SHOW_DATE)}.json?apikey={urllib.parse.quote(key)}")
    d = _get(url)
    if d.get("error"):
        raise RuntimeError(f"phish.net api error: {d.get('error_message')}")
    rows = d.get("data") or []
    out = []
    for r in rows:
        # The showdate endpoint can include side projects; keep Phish proper.
        artist = str(r.get("artist_name") or r.get("artistid") or "1")
        if artist not in ("Phish", "1"):
            continue
        name = (r.get("song") or "").strip()
        if not name:
            continue
        raw_set = str(r.get("set") or "1").strip().upper()
        setno = 9 if raw_set.startswith("E") else (int(raw_set) if raw_set.isdigit() else 1)
        trans = str(r.get("trans_mark") or r.get("transmark") or "")
        out.append({
            "id": int(r.get("songid") or 0) * -1 or None,   # negative: not a PT id
            "name": name,
            "set": setno,
            "pos": int(r.get("position") or len(out) + 1),
            "segue": ">" in trans,
        })
    out.sort(key=lambda s: (s["set"], s["pos"]))
    for s in out:
        if s["id"] is None:
            del s["id"]
    return out


def from_phishnet_html():
    """Scrape the public setlist page — no key required."""
    page = _get(f"https://phish.net/setlists/{PNET_SLUG}.html", as_json=False)
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
# canonical database, and a structured API beats scraping the same site's HTML,
# so the scrape is strictly a fallback for when the API is unavailable.
SOURCES = [
    ("phish.net-api", from_phishnet_api, 0),
    ("phantasy-tour", from_phantasy_tour, 1),
    ("phish.net-web", from_phishnet_html, 2),
]


def collect():
    """Try every source; return (songs, winning_source_name, per_source_counts).

    `best_name` is None only when every source raised. A source that answers with
    an empty setlist has still *worked* -- that's the normal state before the
    lights go down -- so it must count as a success, or the heartbeat never fires
    and the page reports a dead feed all evening.
    """
    best, best_name, best_pref, counts = [], None, None, {}
    for name, fn, pref in SOURCES:
        try:
            songs = fn()
        except Exception as e:                      # a dead source must not stop the others
            counts[name] = f"error: {type(e).__name__}"
            print(f"  {name}: {e}", file=sys.stderr)
            continue
        if songs is None:                           # deliberately skipped, not a success
            counts[name] = "skipped"
            continue
        counts[name] = len(songs)
        # Furthest ahead wins; on a tie the more trustworthy source wins.
        if best_name is None or (len(songs), -pref) > (len(best), -best_pref):
            best, best_name, best_pref = songs, name, pref
    return best, best_name, counts


def main():
    songs, source, counts = collect()
    print("sources: " + ", ".join(f"{k}={v}" for k, v in counts.items()))

    if source is None:
        # Every source raised — leave the last good file rather than blanking boards.
        print("all sources failed; leaving existing file untouched", file=sys.stderr)
        return 1

    payload = {
        "showId": SHOW_ID,
        "showDate": SHOW_DATE,
        "fetchedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": source,
        "sourceCounts": counts,
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


if __name__ == "__main__":
    sys.exit(main())
