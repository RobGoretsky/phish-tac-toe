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
  ok("only .sheet-scroll scrolls, never .sheet", () => {
    const css = fs.readFileSync(path.join(ROOT, "styles.css"), "utf8");
    const sheet = /\.sheet\s*\{[^}]*\}/.exec(css)[0];
    if (/overflow-y\s*:\s*auto/.test(sheet))
      throw new Error(".sheet scrolls again — the close button will scroll out of reach");
    if (!/\.sheet-scroll\s*\{[^}]*overflow-y\s*:\s*auto/.test(css))
      throw new Error(".sheet-scroll must be the scroll container");
  });

  console.log(`\n${pass} passed`);
})();
