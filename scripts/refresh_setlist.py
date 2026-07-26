#!/usr/bin/env python3
"""Poll the Phantasy Tour API for tonight's setlist and write data/setlist.json.

Runs from a GitHub Action every few minutes during the show. The browser can't
call Phantasy Tour directly (the API sends no CORS headers), so this is the
bridge: fetch server-side, commit the JSON, let GitHub Pages serve it.

Idempotent by design — the file is rewritten from scratch each run, so a re-run
converges on the same content and the commit step is a no-op when nothing moved.
"""

import json
import os
import pathlib
import sys
import urllib.request
from datetime import datetime, timezone

SHOW_ID = int(os.environ.get("SHOW_ID", "62005"))  # 2026-07-27 MSG, 1995 night
# Rewrite (and therefore commit) at least this often even when nothing changed,
# so the page's "live · Nm ago" badge proves the pipeline is actually running.
HEARTBEAT_SEC = int(os.environ.get("HEARTBEAT_SEC", "480"))
OUT = pathlib.Path(__file__).resolve().parent.parent / "data" / "setlist.json"
API = "https://www.phantasytour.com/api/shows"
UA = {
    # Phantasy Tour is behind Cloudflare and 403s a bare urllib User-Agent.
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "application/json",
}


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main():
    try:
        raw = get(f"{API}/{SHOW_ID}/setlist")
    except Exception as e:
        print(f"fetch failed: {e}", file=sys.stderr)
        # Leave the last good file in place rather than blanking the boards.
        return 1

    songs = []
    for s in sorted(raw.get("ShowSongs", []), key=lambda x: (x["SetNumber"], x["Position"])):
        songs.append({
            "id": s["SongId"],
            "name": s["Song"]["Name"],
            "set": s["SetNumber"],          # 9 == encore
            "pos": s["Position"],
            "segue": bool(s.get("Segue")),
        })

    payload = {
        "showId": SHOW_ID,
        "fetchedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "showNotes": raw.get("ShowNotes"),
        "count": len(songs),
        "songs": songs,
    }

    prev = None
    if OUT.exists():
        try:
            prev = json.loads(OUT.read_text())
        except json.JSONDecodeError:
            pass

    # Leave the file byte-identical when nothing changed, so the workflow's
    # commit step short-circuits — but force a heartbeat rewrite periodically so
    # the page can tell "no songs yet" apart from "the poller is dead".
    if prev and prev.get("songs") == songs:
        age = None
        try:
            age = (datetime.now(timezone.utc)
                   - datetime.fromisoformat(prev["fetchedAt"])).total_seconds()
        except (KeyError, TypeError, ValueError):
            pass
        if age is not None and age < HEARTBEAT_SEC:
            print(f"no change ({len(songs)} songs, {age:.0f}s since last write)")
            return 0

    OUT.write_text(json.dumps(payload, indent=1) + "\n")
    print(f"wrote {len(songs)} songs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
