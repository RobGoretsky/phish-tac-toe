#!/usr/bin/env python3
"""Assemble data/songs.json + data/boards.json from the analysis + blurbs.

Inputs (all committed under analysis/):
  analysis/ranked95.json   per-song 1995 rate, current rate, calibrated odds
  analysis/blurbs.json     researched bio / lyric / why95 / debut / fact95
  analysis/layout.json     which song sits in which square of whose board

Re-running this is a pure function of those three files, so the generated data
files can be regenerated at any time and will converge on the same bytes.
"""

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
ANALYSIS = ROOT / "analysis"
DATA = ROOT / "data"

# Phantasy Tour carries duplicate / renamed rows for the same tune. A square
# hits on ANY of these ids, and the app also falls back to normalised titles.
EXTRA_IDS = {
    "Taste": [1000, 1010, 1211],            # + "The Fog That Surrounds" (its 1995 name)
    "Acoustic Army": [558, 810],            # + the fall-'95 "Keyboard Army" variant
    "Timber (Jerry the Mule)": [1032, 6812],
}
ALIASES = {
    "Taste": ["The Fog That Surrounds", "Taste That Surrounds"],
    "Acoustic Army": ["Keyboard Army"],
    "Timber (Jerry the Mule)": ["Timber"],
    "McGrupp and the Watchful Hosemasters": ["McGrupp and the Watchful Hosemaster", "McGrupp"],
    "NICU": ["N.I.C.U."],
}
COVERS = {
    "Ya Mar", "Timber (Jerry the Mule)", "Funky Bitch", "Loving Cup",
    "A Day in the Life", "Hello My Baby",
}


def main():
    ranked = {r["name"]: r for r in json.loads((ANALYSIS / "ranked95.json").read_text())}
    blurbs = {b["song"]: b for b in json.loads((ANALYSIS / "blurbs.json").read_text())}
    layout = json.loads((ANALYSIS / "layout.json").read_text())

    used = sorted({s for p in layout["players"] for s in p["squares"]})
    missing = [s for s in used if s not in blurbs]
    if missing:
        raise SystemExit(f"missing blurbs for: {missing}")

    songs = {}
    for title in used:
        r = ranked[title]
        b = blurbs[title]
        songs[title] = {
            "title": title,
            "ptIds": EXTRA_IDS.get(title, [r["id"]]),
            "aliases": ALIASES.get(title, []),
            "bio": b["bio"],
            "lyric": b.get("lyric"),
            "why95": b["why95"],
            "debut": b.get("debut"),
            "fact95": b.get("fact95"),
            "n95": r["n95"],
            "nMod": r["nMod"],
            "p": r["p"],
            "cover": title in COVERS,
        }

    boards = {
        "show": layout["show"],
        "about": layout["about"],
        "players": layout["players"],
    }

    DATA.mkdir(exist_ok=True)
    (DATA / "songs.json").write_text(json.dumps(songs, indent=1, ensure_ascii=False) + "\n")
    (DATA / "boards.json").write_text(json.dumps(boards, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {len(songs)} songs across {len(boards['players'])} boards")


if __name__ == "__main__":
    main()
