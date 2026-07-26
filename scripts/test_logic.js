/* node scripts/test_logic.js — exercises the scoring logic against real data. */

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const PTT = require("../logic.js");

const ROOT = path.join(__dirname, "..");
const songs = JSON.parse(fs.readFileSync(path.join(ROOT, "data/songs.json")));
const boards = JSON.parse(fs.readFileSync(path.join(ROOT, "data/boards.json")));

let pass = 0;
const ok = (name, fn) => {
  try { fn(); console.log(`  ok   ${name}`); pass++; }
  catch (e) { console.error(`  FAIL ${name}\n       ${e.message}`); process.exitCode = 1; }
};

/** Build a setlist payload the way refresh_setlist.py writes it. */
const setlist = (names) => ({
  songs: names.map((n, i) => ({
    id: typeof n === "number" ? n : -1 - i,
    name: typeof n === "number" ? "" : n,
    set: 1, pos: i + 1, order: i,
  })),
});
const players = () => JSON.parse(JSON.stringify(boards.players));

console.log("matching");
ok("exact title matches", () => {
  const r = PTT.evaluate(players(), songs, setlist(["You Enjoy Myself"]), null);
  assert.strictEqual(r.players[0].score, 1);
  assert.strictEqual(r.players[1].score, 1);
  assert.strictEqual(r.players[2].score, 1, "shared centre should hit every board");
});

ok("1995-era rename matches (The Fog That Surrounds -> Taste)", () => {
  const r = PTT.evaluate(players(), songs, setlist(["The Fog That Surrounds"]), null);
  const hit = r.players.flatMap((p) => p.cells).filter((c) => c.hit).map((c) => c.key);
  assert.deepStrictEqual(hit, ["Taste"]);
});

ok("Keyboard Army counts for the Acoustic Army square", () => {
  const r = PTT.evaluate(players(), songs, setlist(["Keyboard Army"]), null);
  const hit = r.players.flatMap((p) => p.cells).filter((c) => c.hit).map((c) => c.key);
  assert.deepStrictEqual(hit, ["Acoustic Army"]);
});

ok("punctuation and articles are ignored", () => {
  const r = PTT.evaluate(players(), songs, setlist(["Halleys Comet", "Its Ice"]), null);
  const hit = r.players.flatMap((p) => p.cells).filter((c) => c.hit).map((c) => c.key);
  assert.ok(hit.includes("Halley's Comet"), "Halley's Comet");
  assert.ok(hit.includes("It's Ice"), "It's Ice");
});

ok("a duplicate Phantasy Tour id still matches by name", () => {
  // Night 1 used id 14800 for Hold Your Head Up while the catalogue's main row
  // is 1098 — the name fallback is what saves us from that class of bug.
  const s = { songs: [{ id: 999999, name: "Free", set: 1, pos: 1, order: 0 }] };
  const r = PTT.evaluate(players(), songs, s, null);
  assert.ok(r.players.find((p) => p.name === "Rob").cells.some((c) => c.key === "Free" && c.hit));
});

ok("an unrelated song hits nothing", () => {
  const r = PTT.evaluate(players(), songs, setlist(["Tweezer", "Harry Hood", "Reba"]), null);
  assert.strictEqual(r.players.reduce((a, p) => a + p.score, 0), 0);
});

console.log("wins");
ok("three in a row is detected", () => {
  const p = players();
  const rob = p.find((x) => x.name === "Rob");
  const row = [rob.squares[0], rob.squares[1], rob.squares[2]];
  const r = PTT.evaluate(p, songs, setlist(row), null);
  assert.ok(r.players.find((x) => x.name === "Rob").won);
  assert.strictEqual(r.champion.name, "Rob");
});

ok("two in a row is not a win but counts as close", () => {
  const p = players();
  const rob = p.find((x) => x.name === "Rob");
  const r = PTT.evaluate(p, songs, setlist([rob.squares[0], rob.squares[1]]), null);
  const scored = r.players.find((x) => x.name === "Rob");
  assert.ok(!scored.won);
  assert.ok(scored.close >= 1);
});

ok("diagonals win too", () => {
  const p = players();
  const j = p.find((x) => x.name === "Justin");
  const r = PTT.evaluate(p, songs, setlist([j.squares[0], j.squares[4], j.squares[8]]), null);
  assert.ok(r.players.find((x) => x.name === "Justin").won);
});

ok("earlier line wins the tiebreak", () => {
  const p = players();
  const rob = p.find((x) => x.name === "Rob");
  const dyl = p.find((x) => x.name === "Dylan");
  // Dylan's row completes at position 3, Rob's only at position 6.
  const names = [dyl.squares[0], dyl.squares[1], dyl.squares[2],
                 rob.squares[0], rob.squares[1], rob.squares[2]]
    .filter((n) => n !== "You Enjoy Myself");
  const r = PTT.evaluate(p, songs, setlist(names), null);
  assert.ok(r.players.find((x) => x.name === "Rob").won && r.players.find((x) => x.name === "Dylan").won,
    "both should have a line");
  assert.strictEqual(r.champion.name, "Dylan");
});

console.log("manual marks");
ok("manual marks add hits", () => {
  const p = players();
  const rob = p.find((x) => x.name === "Rob");
  const r = PTT.evaluate(p, songs, setlist([]), new Set([rob.squares[0]]));
  assert.strictEqual(r.players.find((x) => x.name === "Rob").score, 1);
});

ok("manual marks never clear a feed hit", () => {
  const p = players();
  const r = PTT.evaluate(p, songs, setlist(["You Enjoy Myself"]), new Set());
  assert.ok(r.players.every((x) => x.cells[4].hit));
});

ok("a manual-only line never steals the tiebreak from a real one", () => {
  const p = players();
  const rob = p.find((x) => x.name === "Rob");
  const dyl = p.find((x) => x.name === "Dylan");
  const r = PTT.evaluate(p, songs,
    setlist([dyl.squares[6], dyl.squares[7], dyl.squares[8]].filter((n) => n !== "You Enjoy Myself")),
    new Set([rob.squares[0], rob.squares[1], rob.squares[2]]));
  assert.strictEqual(r.champion.name, "Dylan");
});

console.log("edge cases");
ok("empty setlist scores zero and crowns nobody", () => {
  const r = PTT.evaluate(players(), songs, { songs: [] }, null);
  assert.strictEqual(r.champion, null);
  assert.ok(r.players.every((p) => p.score === 0));
});

ok("a missing setlist object does not throw", () => {
  const r = PTT.evaluate(players(), songs, null, null);
  assert.ok(r.players.every((p) => p.score === 0));
});

ok("every board square has a song entry", () => {
  for (const p of boards.players)
    for (const key of p.squares)
      assert.ok(songs[key], `no song data for "${key}"`);
});

ok("boards are 9 squares with a shared centre and no internal repeats", () => {
  for (const p of boards.players) {
    assert.strictEqual(p.squares.length, 9);
    assert.strictEqual(new Set(p.squares).size, 9, `${p.name} repeats a song`);
    assert.strictEqual(p.squares[4], "You Enjoy Myself");
  }
});

ok("no song appears on two boards except the centre", () => {
  const seen = new Map();
  for (const p of boards.players)
    p.squares.forEach((s, i) => {
      if (i === 4) return;
      assert.ok(!seen.has(s), `"${s}" is on both ${seen.get(s)} and ${p.name}`);
      seen.set(s, p.name);
    });
});

console.log(`\n${pass} passed`);
