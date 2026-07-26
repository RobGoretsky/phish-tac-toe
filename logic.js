/* Pure scoring logic for Phish-Tac-Toe — no DOM, so it can be unit-tested in
 * node (see scripts/test_logic.js) and reused by app.js in the browser. */

(function (root) {
  const LINES = [
    [0, 1, 2], [3, 4, 5], [6, 7, 8],
    [0, 3, 6], [1, 4, 7], [2, 5, 8],
    [0, 4, 8], [2, 4, 6],
  ];

  /* Phantasy Tour renames songs between eras ("The Fog That Surrounds" became
   * "Taste") and carries duplicate rows for the same tune, so titles are
   * compared loosely and ids are checked first. */
  const norm = (s) =>
    (s || "")
      .toLowerCase()
      .replace(/[’'`]/g, "")
      .replace(/[^a-z0-9]+/g, " ")
      .replace(/^the /, "")
      .trim();

  /** Index a setlist by song id and by normalised name. */
  function playedIndex(setlist) {
    const byId = new Map();
    const byName = new Map();
    for (const s of (setlist && setlist.songs) || []) {
      if (!byId.has(s.id)) byId.set(s.id, s);
      const n = norm(s.name);
      if (!byName.has(n)) byName.set(n, s);
    }
    return { byId, byName };
  }

  /** The setlist entry that satisfies this square, or null. */
  function findPlay(song, index) {
    for (const id of song.ptIds || []) if (index.byId.has(id)) return index.byId.get(id);
    for (const nm of [song.title].concat(song.aliases || [])) {
      const hit = index.byName.get(norm(nm));
      if (hit) return hit;
    }
    return null;
  }

  /**
   * Score every board against the setlist.
   * Returns { players, champion } where each player gains cells/score/won/etc.
   * `manual` is a Set of song keys marked by hand; it can only ADD hits.
   */
  function evaluate(players, songs, setlist, manual) {
    const index = playedIndex(setlist);
    const marks = manual || new Set();

    for (const p of players) {
      p.cells = p.squares.map((key) => {
        const song = songs[key];
        const play = findPlay(song, index);
        const isManual = marks.has(key);
        return { key, song, play, manual: isManual, hit: !!play || isManual };
      });
      p.score = p.cells.filter((c) => c.hit).length;

      p.winLines = [];
      p.close = 0;
      let best = null;
      for (const line of LINES) {
        const cells = line.map((i) => p.cells[i]);
        const hits = cells.filter((c) => c.hit).length;
        if (hits === 3) {
          p.winLines.push(line);
          // A line completes when its LAST song is played; manual marks have no
          // position, so they sort last and never win a tiebreak on their own.
          const order = Math.max.apply(null, cells.map((c) => (c.play ? c.play.order : Infinity)));
          if (best === null || order < best) best = order;
        } else if (hits === 2) {
          p.close++;
        }
      }
      p.won = p.winLines.length > 0;
      p.winOrder = best;
      p.winCells = new Set([].concat.apply([], p.winLines));
    }

    const winners = players.filter((x) => x.won);
    const champion = winners.length
      ? winners.reduce((a, b) =>
          ((a.winOrder === null ? Infinity : a.winOrder) <= (b.winOrder === null ? Infinity : b.winOrder) ? a : b))
      : null;

    return { players, champion };
  }

  const api = { LINES, norm, playedIndex, findPlay, evaluate };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.PTT = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
