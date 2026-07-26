/* Phish-Tac-Toe — 1995 Night at MSG
 *
 * Source of truth is data/setlist.json, refreshed by a GitHub Action that polls
 * the Phantasy Tour API. The page re-fetches it every POLL_MS. Manual marks are
 * layered on top and stored per-device in localStorage; they can only ADD hits,
 * never remove one the feed already found.
 */

const POLL_MS = 45_000;
const STALE_MS = 12 * 60_000; // feed considered stale if setlist.json is older than this
const LS_MANUAL = "ptt.manual.v1";
const LS_BOARD = "ptt.board.v1";

const { playedIndex, findPlay } = PTT; // from logic.js

const $ = (id) => document.getElementById(id);
const state = {
  boards: null,
  songs: null,
  setlist: { songs: [], fetchedAt: null },
  manual: new Set(JSON.parse(localStorage.getItem(LS_MANUAL) || "[]")),
  idx: 0,
  celebrated: new Set(),
};

/* ---------- render ------------------------------------------------------- */
function render() {
  state.champion = PTT.evaluate(
    state.boards.players, state.songs, state.setlist, state.manual,
  ).champion;
  renderScoreboard();
  renderBoard();
  renderSetlist();
}

function renderScoreboard() {
  const el = $("scoreboard");
  el.innerHTML = "";
  state.boards.players.forEach((p, i) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "score" + (i === state.idx ? " sel" : "") + (p.won ? " won" : "");
    b.style.color = p.accent;
    const sub = p.won
      ? (state.champion === p ? "🏆 WINNER" : "3 in a row")
      : p.close
        ? `${p.close} line${p.close > 1 ? "s" : ""} one away`
        : "";
    b.innerHTML = `<div class="nm">${p.name}</div>
      <div class="val" style="color:${p.won ? "var(--gold)" : "var(--ink)"}">${p.score}<span style="font-size:15px;color:var(--dim)">/9</span></div>
      <div class="sub">${sub}</div>`;
    b.onclick = () => { state.idx = i; localStorage.setItem(LS_BOARD, String(i)); render(); };
    el.appendChild(b);
  });
}

function renderBoard() {
  const p = state.boards.players[state.idx];
  document.documentElement.style.setProperty("--accent", p.accent);
  $("boardName").textContent = `${p.name}'s Board`;
  $("boardStatus").textContent = p.won
    ? (state.champion === p ? "🏆 Three in a row — winner!" : "🏆 Three in a row")
    : `${p.score} of 9 hit${p.close ? ` · ${p.close} line${p.close > 1 ? "s" : ""} one square away` : ""}`;

  const board = $("board");
  board.innerHTML = "";
  p.cells.forEach((c, i) => {
    const d = document.createElement("button");
    d.type = "button";
    d.className = "cell"
      + (c.hit ? " hit" : "")
      + (p.winCells.has(i) ? " winline" : "")
      + (c.manual && !c.play ? " manual" : "")
      + (i === 4 ? " free" : "");
    d.innerHTML = `<span class="odds">${Math.round(c.song.p * 100)}%</span><span class="t">${c.song.title}</span>`;
    d.onclick = () => openSong(c.key);
    board.appendChild(d);
  });

  if (state.champion && !state.celebrated.has(state.champion.id)) {
    state.celebrated.add(state.champion.id);
    confetti(state.champion.accent);
  }
}

function renderLegend() {
  $("legend").innerHTML =
    state.boards.players
      .map((p) => `<span class="k"><i style="background:${p.accent}"></i><b style="color:${p.accent}">${p.name}</b></span>`)
      .join("") + `<span class="note">bold = on a board</span>`;
}

function renderSetlist() {
  const songs = state.setlist.songs || [];
  const src = state.setlist.source;
  $("setlistCount").textContent =
    (songs.length ? `${songs.length} songs` : "") +
    (src && src !== "none" ? `${songs.length ? " · " : ""}via ${src}` : "");
  const body = $("setlistBody");
  if (!songs.length) {
    body.innerHTML = `<p class="empty">Nothing played yet. Lights are still on. 🍩</p>`;
    return;
  }
  // Map each played song to the players whose board it hit, so the setlist can
  // be colour-coded to match the scoreboard.
  const owners = new Map(); // show-order -> [player, ...]
  for (const p of state.boards.players)
    for (const c of p.cells)
      if (c.play) {
        if (!owners.has(c.play.order)) owners.set(c.play.order, []);
        owners.get(c.play.order).push(p);
      }

  const setName = (n) => (n >= 9 ? "Encore" : `Set ${n}`);
  const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
  const sorted = songs.slice().sort((a, b) => a.order - b.order);

  let html = "";
  let cur = null;
  sorted.forEach((s, i) => {
    if (s.set !== cur) {
      if (cur !== null) html += "</div>";
      cur = s.set;
      html += `<div class="setname">${setName(s.set)}</div><div class="setrow">`;
    }
    const who = owners.get(s.order) || [];
    let style = "";
    if (who.length === 1) {
      style = ` style="color:${who[0].accent}"`;
    } else if (who.length > 1) {
      // Shared square (the YEM centre): blend every owner's colour across the text.
      style = ` style="background-image:linear-gradient(96deg,${who.map((p) => p.accent).join(",")})"`;
    }
    const cls = "sl-song" + (who.length ? " sl-hit" : "") + (who.length > 1 ? " sl-multi" : "");
    const last = i === sorted.length - 1 || sorted[i + 1].set !== s.set;
    html += `<span class="${cls}"${style}>${esc(s.name)}</span>`;
    if (!last) html += `<span class="sl-sep">${s.segue ? " &gt; " : ", "}</span>`;
  });
  if (cur !== null) html += "</div>";
  body.innerHTML = html;
}

/* ---------- song detail sheet -------------------------------------------- */
function openSong(key) {
  const song = state.songs[key];
  const index = playedIndex(state.setlist);
  const play = findPlay(song, index);
  const manual = state.manual.has(key);
  const owners = state.boards.players.filter((p) => p.squares.includes(key));

  const badges = [
    play
      ? `<span class="badge on">✓ Played · ${play.set >= 9 ? "Encore" : "Set " + play.set}, #${play.pos}</span>`
      : manual
        ? `<span class="badge on">✓ Marked manually</span>`
        : `<span class="badge">Not yet played</span>`,
    `<span class="badge gold">${Math.round(song.p * 100)}% likely</span>`,
    song.debut ? `<span class="badge">Debut ${song.debut}</span>` : "",
    song.cover ? `<span class="badge">Cover</span>` : "",
  ].join("");

  $("sheetBody").innerHTML = `
    <h2 class="songtitle">${song.title}</h2>
    <div class="badges">${badges}</div>
    ${song.lyric ? `<div class="lyric">“${song.lyric}”</div>` : ""}
    <div class="label">What it is</div>
    <p class="body">${song.bio}</p>
    <div class="label">Why it could drop on 1995 night</div>
    <p class="body">${song.why95}</p>
    <div class="statgrid">
      <div class="stat"><b>${song.n95}</b><span>of 83 shows<br>in 1995</span></div>
      <div class="stat"><b>${song.nMod}</b><span>of 164 shows<br>since 2023</span></div>
      <div class="stat"><b>${Math.round(song.p * 100)}%</b><span>our odds<br>for tonight</span></div>
    </div>
    ${song.fact95 ? `<div class="label">1995 factoid</div><p class="body">${song.fact95}</p>` : ""}
    <p class="onboards">On ${owners.map((o) => `<b style="color:${o.accent}">${o.name}</b>`).join(" · ")}${owners.length > 1 ? "'s boards" : "'s board"}.</p>
  `;
  show("sheetWrap");
}

/* ---------- manual entry -------------------------------------------------- */
function openManual() {
  const index = playedIndex(state.setlist);
  const keys = [...new Set(state.boards.players.flatMap((p) => p.squares))]
    .sort((a, b) => state.songs[a].title.localeCompare(state.songs[b].title));
  const list = $("manualList");
  list.innerHTML = "";
  for (const key of keys) {
    const song = state.songs[key];
    const play = findPlay(song, index);
    const on = !!play || state.manual.has(key);
    const owners = state.boards.players.filter((p) => p.squares.includes(key)).map((p) => p.name[0]).join("");
    const row = document.createElement("button");
    row.type = "button";
    row.className = "manual-row" + (on ? " on" : "") + (play ? " feed" : "");
    row.innerHTML = `<span class="box">${on ? "✓" : ""}</span><span>${song.title}</span><span class="who">${play ? "FEED" : owners}</span>`;
    if (!play) {
      row.onclick = () => {
        state.manual.has(key) ? state.manual.delete(key) : state.manual.add(key);
        localStorage.setItem(LS_MANUAL, JSON.stringify([...state.manual]));
        openManual();
        render();
      };
    }
    list.appendChild(row);
  }
  show("manualWrap");
}

/* ---------- data loading -------------------------------------------------- */
async function loadSetlist() {
  try {
    const r = await fetch(`data/setlist.json?t=${Date.now()}`, { cache: "no-store" });
    if (!r.ok) throw new Error(r.status);
    const d = await r.json();
    d.songs = (d.songs || []).map((s, i) => ({ ...s, order: i }));
    state.setlist = d;
    setStatus(d);
  } catch (e) {
    $("statusPill").className = "status error";
    $("statusText").textContent = "feed offline";
  }
  render();
}

function setStatus(d) {
  const pill = $("statusPill");
  const age = d.fetchedAt ? Date.now() - Date.parse(d.fetchedAt) : Infinity;
  const mins = Math.round(age / 60000);
  if (age < STALE_MS) {
    pill.className = "status live";
    $("statusText").textContent = mins < 1 ? "live · just now" : `live · ${mins}m ago`;
  } else {
    pill.className = "status stale";
    $("statusText").textContent = Number.isFinite(mins) ? `updated ${mins}m ago` : "waiting for feed";
  }
}

/* ---------- chrome -------------------------------------------------------- */
function show(id) { $(id).hidden = false; }
function hide(id) { $(id).hidden = true; }

function confetti(color) {
  const box = $("confetti");
  const colors = [color, "#ffcf4a", "#6ce5ff", "#ff7ad9", "#21c07a"];
  for (let i = 0; i < 90; i++) {
    const p = document.createElement("i");
    p.style.left = Math.random() * 100 + "vw";
    p.style.background = colors[i % colors.length];
    p.style.animationDuration = 2.4 + Math.random() * 2.2 + "s";
    p.style.animationDelay = Math.random() * 0.7 + "s";
    box.appendChild(p);
    setTimeout(() => p.remove(), 6000);
  }
}

function move(delta) {
  const n = state.boards.players.length;
  state.idx = (state.idx + delta + n) % n;
  localStorage.setItem(LS_BOARD, String(state.idx));
  render();
}

function wireUp() {
  $("prevBtn").onclick = () => move(-1);
  $("nextBtn").onclick = () => move(1);
  $("statusPill").onclick = loadSetlist;
  $("manualBtn").onclick = openManual;
  $("aboutBtn").onclick = () => { $("aboutBody").innerHTML = state.boards.about; show("aboutWrap"); };
  $("sheetClose").onclick = () => hide("sheetWrap");
  $("manualClose").onclick = () => hide("manualWrap");
  $("aboutClose").onclick = () => hide("aboutWrap");
  $("manualReset").onclick = () => {
    state.manual.clear();
    localStorage.removeItem(LS_MANUAL);
    openManual();
    render();
  };
  for (const id of ["sheetWrap", "manualWrap", "aboutWrap"]) {
    $(id).addEventListener("click", (e) => { if (e.target.id === id) hide(id); });
  }
  for (const b of document.querySelectorAll(".sheet-done")) {
    b.onclick = (e) => hide(e.target.closest(".sheet-wrap").id);
  }
  document.addEventListener("keydown", (e) => {
    if (e.key === "ArrowLeft") move(-1);
    if (e.key === "ArrowRight") move(1);
    if (e.key === "Escape") ["sheetWrap", "manualWrap", "aboutWrap"].forEach(hide);
  });

  // swipe between boards
  let x0 = null, y0 = null;
  const b = $("board");
  b.addEventListener("touchstart", (e) => { x0 = e.touches[0].clientX; y0 = e.touches[0].clientY; }, { passive: true });
  b.addEventListener("touchend", (e) => {
    if (x0 === null) return;
    const dx = e.changedTouches[0].clientX - x0;
    const dy = e.changedTouches[0].clientY - y0;
    if (Math.abs(dx) > 55 && Math.abs(dx) > Math.abs(dy) * 1.6) move(dx < 0 ? 1 : -1);
    x0 = y0 = null;
  }, { passive: true });

  // refresh when the phone comes back from sleep / tab refocus
  document.addEventListener("visibilitychange", () => { if (!document.hidden) loadSetlist(); });
}

async function main() {
  const [boards, songs] = await Promise.all([
    fetch("data/boards.json").then((r) => r.json()),
    fetch("data/songs.json").then((r) => r.json()),
  ]);
  state.boards = boards;
  state.songs = songs;
  state.idx = Math.min(Number(localStorage.getItem(LS_BOARD) || 0), boards.players.length - 1);
  $("showLine").textContent = boards.show.line;
  document.title = `Phish-Tac-Toe · ${boards.show.title}`;
  wireUp();
  renderLegend();
  await loadSetlist();
  setInterval(loadSetlist, POLL_MS);
}

main();
