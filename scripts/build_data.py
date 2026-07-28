#!/usr/bin/env python3
"""Assemble data/songs.json + data/boards.json from the analysis + blurbs.

Inputs (all committed under analysis/):
  analysis/ranked96.json   per-song 1996 rate, current rate, calibrated odds
  analysis/blurbs.json     researched bio / lyric / why96 / debut / fact96
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
EXTRA_IDS = {}
ALIASES = {
    "McGrupp and the Watchful Hosemasters": ["McGrupp and the Watchful Hosemaster", "McGrupp"],
    "Old Home Place": ["The Old Home Place"],
}
COVERS = {
    "Ya Mar", "A Day in the Life", "Hello My Baby", "Crosseyed and Painless",
    "Old Home Place", "Frankenstein", "Rocky Top", "Ginseng Sullivan", "Fire",
}


def main():
    ranked = {r["name"]: r for r in json.loads((ANALYSIS / "ranked96.json").read_text())}
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
            "why96": b["why96"],
            "debut": b.get("debut"),
            "fact96": b.get("fact96"),
            "n96": r["n96"],
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
