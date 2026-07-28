/* Headless DOM test: loads the real index.html + logic.js + app.js in jsdom,
 * stubs fetch against the real data files, and drives the actual UI. */
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = path.join(__dirname, "..");
const read = (p) => fs.readFileSync(path.join(ROOT, p), "utf8");

let pass = 0;
const ok = (name, fn) => {
  try { fn(); console.log(`  ok   ${name}`); pass++; }
  catch (e) { console.error(`  FAIL ${name}\n       ${e.message}`); process.exitCode = 1; }
};

(async () => {
  const dom = new JSDOM(read("index.html"), {
    runScripts: "outside-only",
    pretendToBeVisual: true,
    url: "https://robgoretsky.github.io/phish-tac-toe/",
  });
  const { window } = dom;

  // stub fetch -> local files
  window.fetch = async (u) => {
    const clean = String(u).split("?")[0];
    const body = read(clean);
    return { ok: true, status: 200, json: async () => JSON.parse(body) };
  };
  window.localStorage.clear();

  window.eval(read("logic.js"));
  window.eval(read("app.js"));
  await new Promise((r) => setTimeout(r, 300)); // let main() resolve

  const $ = (id) => window.document.getElementById(id);
  const cells = () => [...window.document.querySelectorAll(".cell")];
  const click = (el) => el.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));

  console.log("boot");
  ok("board renders 9 cells", () => { if (cells().length !== 9) throw new Error(`got ${cells().length}`); });
  ok("scoreboard renders 3 players", () => {
    const n = window.document.querySelectorAll(".score").length;
    if (n !== 3) throw new Error(`got ${n}`);
  });
  ok("all three sheets start hidden", () => {
    for (const id of ["sheetWrap", "manualWrap", "aboutWrap"])
      if (!$(id).hidden) throw new Error(`${id} not hidden at boot`);
  });

  console.log("song sheet");
  ok("clicking a square opens the song sheet", () => {
    click(cells()[0]);
    if ($("sheetWrap").hidden) throw new Error("sheetWrap still hidden");
    if (!$("sheetBody").textContent.trim()) throw new Error("sheet body empty");
  });
  ok("the close button dismisses it", () => {
    click($("sheetClose"));
    if (!$("sheetWrap").hidden) throw new Error("sheetWrap still visible after clicking X");
  });
  ok("tapping the backdrop dismisses it", () => {
    click(cells()[0]);
    click($("sheetWrap"));
    if (!$("sheetWrap").hidden) throw new Error("backdrop tap did not close");
  });
  ok("Escape dismisses it", () => {
    click(cells()[0]);
    window.document.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    if (!$("sheetWrap").hidden) throw new Error("Escape did not close");
  });
  ok("opening a second song replaces the content", () => {
    click(cells()[0]);
    const a = $("sheetBody").textContent;
    click($("sheetClose"));
    click(cells()[8]);
    if ($("sheetBody").textContent === a) throw new Error("content did not change");
    click($("sheetClose"));
  });
  ok("every square opens and closes cleanly", () => {
    for (let i = 0; i < 9; i++) {
      click(cells()[i]);
      if ($("sheetWrap").hidden) throw new Error(`square ${i} did not open`);
      click($("sheetClose"));
      if (!$("sheetWrap").hidden) throw new Error(`square ${i} did not close`);
    }
  });

  console.log("other sheets");
  ok("manual entry opens and closes", () => {
    click($("manualBtn"));
    if ($("manualWrap").hidden) throw new Error("did not open");
    if (!window.document.querySelectorAll(".manual-row").length) throw new Error("no rows");
    click($("manualClose"));
    if (!$("manualWrap").hidden) throw new Error("did not close");
  });
  ok("about opens and closes", () => {
    click($("aboutBtn"));
    if ($("aboutWrap").hidden) throw new Error("did not open");
    if (!$("aboutBody").textContent.trim()) throw new Error("about body empty");
    click($("aboutClose"));
    if (!$("aboutWrap").hidden) throw new Error("did not close");
  });

  console.log("navigation");
  ok("arrows switch boards", () => {
    const before = $("boardName").textContent;
    click($("nextBtn"));
    if ($("boardName").textContent === before) throw new Error("board did not change");
  });
  ok("scoreboard tiles switch boards", () => {
    click(window.document.querySelectorAll(".score")[2]);
    if (!$("boardName").textContent.includes("Justin")) throw new Error($("boardName").textContent);
  });
  ok("a manual mark increments the score and persists", () => {
    click($("manualBtn"));
    const row = window.document.querySelector(".manual-row:not(.feed)");
    click(row);
    const stored = JSON.parse(window.localStorage.getItem("ptt.manual.v1") || "[]");
    if (!stored.length) throw new Error("not persisted");
    click($("manualClose"));
  });

  console.log("reachable exits (the scroll trap)");
  ok("every sheet has a bottom Close button that works", () => {
    const cases = [["sheetWrap", () => click(cells()[0])],
                   ["manualWrap", () => click($("manualBtn"))],
                   ["aboutWrap", () => click($("aboutBtn"))]];
    for (const [id, open] of cases) {
      open();
      if ($(id).hidden) throw new Error(`${id} did not open`);
      const done = $(id).querySelector(".sheet-done");
      if (!done) throw new Error(`${id} has no .sheet-done button`);
      click(done);
      if (!$(id).hidden) throw new Error(`${id} bottom Close did not dismiss`);
    }
  });
  ok("the bottom Close is the LAST thing you scroll to", () => {
    for (const id of ["sheetWrap", "manualWrap", "aboutWrap"]) {
      const scroll = $(id).querySelector(".sheet-scroll");
      const last = [...scroll.children].filter((n) => n.nodeType === 1).pop();
      if (!last.classList.contains("sheet-done"))
        throw new Error(`${id} scroll area ends with .${last.className}, not the Close button`);
    }
  });
  ok("the X sits outside the scrolling area", () => {
    // It used to live inside .sheet while .sheet was the scroll container, so it
    // scrolled away — and once pinned with sticky, the 20px border-radius clipped it.
    for (const id of ["sheetWrap", "manualWrap", "aboutWrap"]) {
      const x = $(id).querySelector(".close");
      if (!x) throw new Error(`${id} has no close button`);
      if (x.closest(".sheet-scroll"))
        throw new Error(`${id}: .close is inside .sheet-scroll and will scroll away`);
      if (x.parentElement !== $(id).querySelector(".sheet"))
        throw new Error(`${id}: .close should be a direct child of .sheet`);
    }
  });
  ok("all sheet content lives inside .sheet-scroll", () => {
    for (const id of ["sheetWrap", "manualWrap", "aboutWrap"]) {
      const scroll = $(id).querySelector(".sheet-scroll");
      if (!scroll) throw new Error(`${id} has no .sheet-scroll`);
      if (!scroll.querySelector(".sheet-done"))
        throw new Error(`${id}: bottom Close should be inside the scroll area`);
    }
  });
  ok("sheet heights use dvh, not bare vh", () => {
    // On iOS `vh` is the LARGEST viewport, so a bottom-anchored 88vh sheet hangs
    // above the visible area and clips its own title behind the URL bar.
    const css = fs.readFileSync(path.join(ROOT, "styles.css"), "utf8");
    for (const sel of ["sheet-wrap", "sheet"]) {
      const rule = new RegExp(`\\.${sel}\\s*\\{([^}]*)\\}`).exec(css);
      if (!rule) throw new Error(`.${sel} rule missing`);
      const heights = rule[1].match(/(?:max-)?height\s*:\s*[^;]+/g) || [];
      if (!heights.length) throw new Error(`.${sel} sets no height`);
      if (!heights.some((h) => /dvh/.test(h)))
        throw new Error(`.${sel} sizes with ${heights.join(", ")} — needs a dvh value`);
    }
  });

  ok("the song sheet scroll position resets between songs", () => {
    const scroll = $("sheetScroll");
    if (!scroll) throw new Error("no #sheetScroll");
    scroll.scrollTop = 120;
    click(cells()[0]);
    if (scroll.scrollTop !== 0) throw new Error(`opened at scrollTop ${scroll.scrollTop}`);
    click($("sheetClose"));
  });

  ok(".sheet-scroll can actually shrink and scroll", () => {
    // Without min-height:0 a flex item won't shrink below its content size, so
    // the sheet's overflow:hidden clips the top of long songs instead of scrolling.
    const css = fs.readFileSync(path.join(ROOT, "styles.css"), "utf8");
    const rule = /\.sheet-scroll\s*\{([^}]*)\}/.exec(css);
    if (!rule) throw new Error(".sheet-scroll rule missing");
    if (!/min-height\s*:\s*0/.test(rule[1]))
      throw new Error(".sheet-scroll needs min-height:0 or long sheets clip at the top");
    if (!/flex\s*:/.test(rule[1]))
      throw new Error(".sheet-scroll needs an explicit flex so it fills the sheet");
  });

  ok("only .sheet-scroll scrolls, never .sheet", () => {
    const css = fs.readFileSync(path.join(ROOT, "styles.css"), "utf8");
    const sheet = /\.sheet\s*\{[^}]*\}/.exec(css)[0];
    if (/overflow-y\s*:\s*auto/.test(sheet))
      throw new Error(".sheet scrolls again — the close button will scroll out of reach");
    if (!/\.sheet-scroll\s*\{[^}]*overflow-y\s*:\s*auto/.test(css))
      throw new Error(".sheet-scroll must be the scroll container");
  });

  console.log("setlist rendering");
  // Load a real 20-song 1996 setlist (the 6/6/96 Joyous Lake warm-up) into the page.
  const real = JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures/setlist-1996-06-06.json")));
  window.fetch = async (u) => {
    const clean = String(u).split("?")[0];
    const body = clean.endsWith("setlist.json") ? JSON.stringify(real) : read(clean);
    return { ok: true, status: 200, json: async () => JSON.parse(body) };
  };
  window.eval("loadSetlist()");
  await new Promise((r) => setTimeout(r, 200));

  const slSongs = () => [...window.document.querySelectorAll("#setlistBody .sl-song")];
  ok("the whole setlist renders", () => {
    if (slSongs().length !== real.songs.length)
      throw new Error(`rendered ${slSongs().length} of ${real.songs.length}`);
  });
  ok("no setlist element reuses a class that sets `display`", () => {
    // "board" used to be reused here and collided with .board { display: grid },
    // turning every matched song into a block and breaking the line flow.
    const css = fs.readFileSync(path.join(ROOT, "styles.css"), "utf8");
    const displayClasses = new Set(
      [...css.matchAll(/\.([a-zA-Z][\w-]*)[^{}]*\{[^}]*display\s*:/g)].map((m) => m[1]));
    for (const el of window.document.querySelectorAll("#setlistBody *"))
      for (const c of el.classList)
        if (displayClasses.has(c) && c !== "setrow")
          throw new Error(`<${el.tagName.toLowerCase()} class="${el.className}"> reuses .${c}, which sets display`);
  });
  ok("matched songs are inline, not block", () => {
    const css = fs.readFileSync(path.join(ROOT, "styles.css"), "utf8");
    for (const cls of ["sl-song", "sl-hit", "sl-sep"]) {
      const m = new RegExp(`\\.${cls}\\s*\\{([^}]*)\\}`).exec(css);
      if (m && /display\s*:\s*(block|grid|flex)/.test(m[1]))
        throw new Error(`.${cls} is display:${/display\s*:\s*(\w+)/.exec(m[1])[1]}`);
    }
  });
  ok("hits are colour-coded to their board owner", () => {
    const boards = JSON.parse(read("data/boards.json"));
    const accents = new Set(boards.players.map((p) => p.accent.toLowerCase()));
    const hits = slSongs().filter((e) => e.classList.contains("sl-hit"));
    if (hits.length < 5) throw new Error(`only ${hits.length} hits coloured`);
    for (const h of hits) {
      if (h.classList.contains("sl-multi")) {
        if (!/linear-gradient/.test(h.getAttribute("style") || ""))
          throw new Error(`shared song ${h.textContent} has no gradient`);
        continue;
      }
      const col = (h.style.color || "").toLowerCase();
      const hex = /^#/.test(col) ? col : rgbToHex(col);
      if (!accents.has(hex)) throw new Error(`${h.textContent} coloured ${col}, not a player accent`);
    }
  });
  ok("Character Zero is marked as shared by all three", () => {
    const cz = slSongs().find((e) => e.textContent === "Character Zero");
    if (!cz) throw new Error("Character Zero not in this setlist");
    if (!cz.classList.contains("sl-multi")) throw new Error("Character Zero should be .sl-multi");
  });
  ok("non-hits stay dim and unstyled", () => {
    const miss = slSongs().filter((e) => !e.classList.contains("sl-hit"));
    for (const m of miss)
      if (m.getAttribute("style")) throw new Error(`${m.textContent} should have no inline colour`);
  });
  ok("separators sit between songs, never trailing a set", () => {
    for (const row of window.document.querySelectorAll(".setrow")) {
      const kids = [...row.children];
      const last = kids[kids.length - 1];
      if (last.classList.contains("sl-sep"))
        throw new Error("a set ends with a dangling separator");
    }
  });
  ok("the legend lists all three players with their colours", () => {
    const keys = window.document.querySelectorAll("#legend .k");
    if (keys.length !== 3) throw new Error(`got ${keys.length} legend entries`);
  });

  console.log(`\n${pass} passed`);

  function rgbToHex(c) {
    const m = /rgb\((\d+),\s*(\d+),\s*(\d+)\)/.exec(c);
    if (!m) return c;
    return "#" + [1, 2, 3].map((i) => (+m[i]).toString(16).padStart(2, "0")).join("");
  }
})();
