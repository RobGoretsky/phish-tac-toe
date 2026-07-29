#!/usr/bin/env python3
"""Freeze a finished show into data/archive/<date>.json for the lookback view.

A past night can't be rebuilt from the current data files: boards.json and
songs.json are overwritten for each new show, and the setlist feed is reset. The
only surviving copy of a played night is in git history, so this reads the blobs
straight out of the commits that held them and writes one self-contained file.

Self-contained matters -- the archive carries its own players, songs and setlist,
so the page can render an old night without the current show's data being
compatible with it. In particular the per-year song fields (`why96`, `n96`,
`fact96` in 1996; `why95`/`n95`/`fact95` in 1995) are normalised here to
year-agnostic keys (`why`, `nYear`, `fact`) so app.js has one shape to render.

Usage (args are git revisions):
    python3 scripts/build_archive.py --date 2026-07-27 \
        --boards ce240e1^ --songs ce240e1^ --setlist a81605c
"""

import argparse
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def blob(rev, path):
    """Read one file as it existed at `rev`."""
    out = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=ROOT,
                         capture_output=True, text=True)
    if out.returncode:
        sys.exit(f"cannot read {path} at {rev}: {out.stderr.strip()}")
    return json.loads(out.stdout)


def normalise_songs(songs):
    """Map the year-suffixed fields onto year-agnostic ones.

    Returns (songs, year) -- the year is recovered from the suffix rather than
    passed in, so a future archive can't silently disagree with its own data.
    """
    year = None
    for s in songs.values():
        for key in list(s):
            m = re.fullmatch(r"(why|n|fact)(\d{2})", key)
            if not m:
                continue
            stem, yy = m.groups()
            year = year or f"19{yy}"
            s["nYear" if stem == "n" else stem] = s.pop(key)
    return songs, year


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="show date, YYYY-MM-DD")
    ap.add_argument("--boards", required=True, help="rev holding that night's data/boards.json")
    ap.add_argument("--songs", required=True, help="rev holding that night's data/songs.json")
    ap.add_argument("--setlist", required=True, help="rev holding the FINAL data/setlist.json")
    # The song sheet's stat grid is labelled "n of N shows in <year>". N was a
    # literal in that build's app.js, so it has to be supplied -- guessing it
    # would silently mislabel the archive (1995 ran 83 shows, 1996 only 71).
    ap.add_argument("--year-shows", required=True, type=int,
                    help="how many shows the band played that theme year")
    ap.add_argument("--modern-shows", required=True, type=int,
                    help="how many shows since Jan 2023 the model scored against")
    a = ap.parse_args()

    boards = blob(a.boards, "data/boards.json")
    songs, year = normalise_songs(blob(a.songs, "data/songs.json"))
    setlist = blob(a.setlist, "data/setlist.json")

    if setlist.get("showDate") != a.date:
        sys.exit(f"setlist at {a.setlist} is for {setlist.get('showDate')}, not {a.date}")
    if not setlist.get("songs"):
        sys.exit(f"setlist at {a.setlist} is empty -- point --setlist at the final commit")

    out = {
        "show": boards["show"] | {"year": year, "final": True},
        "players": boards["players"],
        "about": boards["about"],
        "songs": songs,
        "setlist": setlist,
        # Counts for the song sheet's stat grid, which is labelled per-year.
        "counts": {"year": a.year_shows, "modern": a.modern_shows},
    }

    dest = ROOT / "data" / "archive" / f"{a.date}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {dest.relative_to(ROOT)} -- {year} night, "
          f"{len(setlist['songs'])} songs, {len(boards['players'])} boards "
          f"({', '.join(p['name'] for p in boards['players'])})")


if __name__ == "__main__":
    main()
