// Records a ~30-second Infill walkthrough with captions and a visible cursor.
// Needs the local server running:  python3 scripts/serve.py   (http://localhost:8000)
// Then:  cd video && npm install && npx playwright install chromium && npm run record
// Output: video/out/infill-demo.webm (+ out/timing.json with where the intro ends)
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const URL = process.env.INFILL_URL || "http://localhost:8000/";
const OUT = path.resolve("out");
const W = 1600, H = 900;
fs.mkdirSync(OUT, { recursive: true });
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

import { LINES } from "./script.mjs";
const CAPTIONS = LINES.slice(0, 5).map((t, i) => (i === 3 ? t.replace("there.", "there (demo entry shown).") : t));
// Scene lengths follow the voiceover if out/voice/manifest.json exists (npm run voice)
let VOICE = [];
try { VOICE = JSON.parse(fs.readFileSync(path.join(OUT, "voice", "manifest.json"), "utf8")).clips.map((c) => c.seconds || 0); console.log("pacing to voiceover:", VOICE.map((x) => x.toFixed(1)).join(", ")); } catch { console.log("no voiceover manifest: default pacing"); }
const marks = [];

// Back up the team's notes, record on a clean slate, then put them back.
const backup = await (await fetch(URL + "api/pipeline")).json();
const health = await (await fetch(URL + "api/health")).json();
console.log("server:", health);
await fetch(URL + "api/pipeline", { method: "PUT", headers: { "Content-Type": "application/json" }, body: "{}" });

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: W, height: H }, recordVideo: { dir: OUT, size: { width: W, height: H } } });
const page = await ctx.newPage();
const t0 = Date.now();
try {
  await page.addInitScript(() => { try { localStorage.setItem("infill-city", "anaheim"); } catch {} });
  await page.goto(URL);
  await page.waitForSelector(".list-row");

  // Overlay: title card, captions, cursor
  await page.evaluate(() => {
    const css = document.createElement("style");
    css.textContent = `
      #demo-title { position:fixed; inset:0; z-index:9999; background:#F4F1E8; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:14px;
        background-image:linear-gradient(#E3DECF 1px, transparent 1px), linear-gradient(90deg, #E3DECF 1px, transparent 1px); background-size:40px 40px; transition:opacity .5s; }
      #demo-title h1 { margin:0; font:800 88px/1 Overpass, system-ui, sans-serif; color:#1B1F1D; letter-spacing:-.02em; }
      #demo-title p { margin:0; font:500 26px/1.3 "Public Sans", system-ui, sans-serif; color:#575C55; }
      #demo-title small { font:500 16px/1 "IBM Plex Mono", monospace; color:#575C55; margin-top:18px; }
      #demo-cap { position:fixed; left:50%; bottom:28px; transform:translateX(-50%); z-index:9998; max-width:1100px; background:#1B1F1D; color:#fff;
        font:500 22px/1.4 "Public Sans", system-ui, sans-serif; padding:14px 22px; border-radius:8px; box-shadow:0 8px 24px rgba(0,0,0,.25); transition:opacity .3s; text-align:center; }
      #demo-cursor { position:fixed; z-index:10000; width:22px; height:22px; margin:-11px 0 0 -11px; border-radius:50%; background:rgba(184,81,13,.35); border:2px solid #B8510D;
        pointer-events:none; transition:left .6s cubic-bezier(.3,.7,.2,1), top .6s cubic-bezier(.3,.7,.2,1), transform .15s; left:800px; top:450px; }
      #demo-cursor.down { transform:scale(.7); }
      html, body { overflow:hidden !important; }
      .app, #modal { transform-origin:0 0; transition:transform .9s cubic-bezier(.45,.05,.25,1); will-change:transform; }`;
    document.head.appendChild(css);
    const t = document.createElement("div"); t.id = "demo-title";
    t.innerHTML = `<h1>Infill</h1><p>Nonprofits find land by luck. Infill finds it on purpose.</p><small>Claude Impact Lab · UCI × SoCal Affordable Housing · Lane 1: Find it</small>`;
    document.body.appendChild(t);
    const c = document.createElement("div"); c.id = "demo-cap"; c.style.opacity = "0"; document.body.appendChild(c);
    const k = document.createElement("div"); k.id = "demo-cursor"; document.body.appendChild(k);
  });
  const caption = (txt) => page.evaluate((t) => { const c = document.getElementById("demo-cap"); c.textContent = t; c.style.opacity = t ? "1" : "0"; }, txt);
  let sceneT = 0;
  async function scene(i) { marks[i] = (Date.now() - t0) / 1000; sceneT = Date.now(); if (i < 5) await caption(CAPTIONS[i]); }
  async function hold(i) { const need = (VOICE[i] || 0) + 0.4, spent = (Date.now() - sceneT) / 1000; if (need > spent) await wait((need - spent) * 1000); }
  async function point(selector, { click = true, nth = 0 } = {}) {
    const el = page.locator(selector).nth(nth);
    await el.scrollIntoViewIfNeeded();
    const b = await el.boundingBox();
    const x = b.x + b.width / 2, y = b.y + b.height / 2;
    await page.evaluate(([x, y]) => { const k = document.getElementById("demo-cursor"); k.style.left = x + "px"; k.style.top = y + "px"; }, [x, y]);
    await wait(700);
    if (click) {
      await page.evaluate(() => document.getElementById("demo-cursor").classList.add("down"));
      await el.click();
      await wait(120);
      await page.evaluate(() => document.getElementById("demo-cursor").classList.remove("down"));
    }
  }

  // Camera: scale .app and the call-sheet window around a target; captions and cursor stay unscaled.
  let cam = { s: 1, tx: 0, ty: 0 };
  async function zoom(selector, scale = 1.4, { nth = 0, dx = 0, dy = 0 } = {}) {
    if (!selector || scale === 1) cam = { s: 1, tx: 0, ty: 0 };
    else {
      const b = await page.locator(selector).nth(nth).boundingBox();
      // back out of the current camera to page coordinates
      const cx = (b.x + b.width / 2 - cam.tx) / cam.s + dx, cy = (b.y + b.height / 2 - cam.ty) / cam.s + dy;
      let tx = W / 2 - scale * cx, ty = H / 2 - scale * cy;
      tx = Math.min(0, Math.max(W - scale * W, tx)); ty = Math.min(0, Math.max(H - scale * H, ty));
      cam = { s: scale, tx, ty };
    }
    await page.evaluate((c) => {
      const t = `translate(${c.tx}px, ${c.ty}px) scale(${c.s})`;
      document.querySelector(".app").style.transform = t;
      document.getElementById("modal").style.transform = t;
    }, cam);
    await wait(1000);
  }

  // Warm up the call sheet for site 01 behind the title card (Claude can take a while)
  const firstId = await page.evaluate(() => sites.slice().sort((a, b) => a.properties.rank - b.properties.rank)[0].properties.id);
  await page.evaluate(async (id) => { await callSheet(id); }, firstId);
  // Zoom so the close-together top pins separate
  await page.evaluate(() => { const top = shownSites().slice(0, 3); const b = L.geoJSON({ type: "FeatureCollection", features: top }).getBounds(); map.fitBounds(b, { padding: [180, 180], maxZoom: 15 }); });
  await wait(1500);
  const introEnd = (Date.now() - t0) / 1000;
  await page.evaluate(() => { const t = document.getElementById("demo-title"); t.style.opacity = "0"; setTimeout(() => t.remove(), 600); });
  // Keep a 2.5 s title card at the start of the final cut
  const keepFrom = Math.max(0, introEnd - 2.5);

  // 1. The problem
  await wait(400); await scene(0); await wait(4200); await hold(0);
  // 2. Site card with checks and sources
  await scene(1);
  await point(".list-row", { nth: 0 }); await wait(1300);
  await zoom("#card .card-head", 1.5, { dy: 150 }); await wait(900);
  await page.evaluate(() => document.getElementById("card").scrollTo({ top: 360, behavior: "smooth" })); await wait(2000);
  await hold(1); await zoom(null);
  // 3. Call sheet window + Mark as called
  await scene(2);
  await page.evaluate(() => document.getElementById("card").scrollTo({ top: 0 })); await wait(200);
  await point("#callBtn"); await wait(700);
  await zoom(".m-stats", 1.45, { dy: -60 }); await wait(1600);
  await zoom(".m-body", 1.3, { dy: -40 }); await wait(1200);
  await zoom(null);
  await page.evaluate(() => document.getElementById("modal").scrollTo({ top: 9999, behavior: "smooth" })); await wait(1000);
  await zoom(".m-foot", 1.6, { dx: 140 });
  await point("#m-called"); await wait(1100);
  await zoom(null);
  await hold(2);
  await page.keyboard.press("Escape"); await wait(400);
  // 4. Log a 3D-scan visit on site 03, then Ground truth
  await scene(3);
  await point(".list-row", { nth: 2 }); await wait(1000);
  await point("#visitBtn"); await wait(300);
  await zoom("#visitForm", 1.45, { dy: -40 });
  await page.selectOption("#v-found", "parking");
  await point('input[name="surveyed"]'); await wait(300);
  // Honest demo data: this visit did not happen, so the note says so on screen.
  await page.fill('#v-n', "Demo entry for this video, not a real site visit.");
  await point('#visitForm button[type="submit"]'); await wait(700);
  await zoom(null);
  await page.evaluate(() => { document.getElementById("card").style.display = "none"; });
  await point('.tabs button[data-view="truth"]'); await wait(500);
  await zoom("#truth .stats", 1.35, { dy: 120 }); await wait(2000); await hold(3);
  await zoom(null);
  // 5. Scale: Garden Grove, all 946 sites
  await scene(4);
  await point('.tabs button[data-view="map"]'); await wait(300);
  await page.evaluate(() => { document.getElementById("card").style.display = "none"; });
  await point("#city", { click: false });
  await page.selectOption("#city", "garden-grove"); await wait(900);
  await point('.segmented button[data-top="0"]'); await wait(900);
  await page.evaluate(() => { document.querySelector(".app").style.transition = "transform 2.6s ease-in-out"; });
  await zoom("#map", 1.25, { dx: 200 }); await wait(1800);
  await page.evaluate(() => { document.querySelector(".app").style.transition = ""; });
  await hold(4);
  await zoom(null);
  // End card
  await caption("");
  marks[5] = (Date.now() - t0) / 1000; sceneT = Date.now();
  await page.evaluate(() => {
    document.getElementById("demo-cursor").style.display = "none";
    const t = document.createElement("div"); t.id = "demo-title"; t.style.opacity = "0";
    t.innerHTML = `<h1>Infill</h1><p>Screen. Draft with Claude. Verify on the ground. Learn.</p><small>github.com/FB845/infill · public data only · prototype, not a zoning determination</small>`;
    document.body.appendChild(t); requestAnimationFrame(() => (t.style.opacity = "1"));
  });
  await wait(1200); await hold(5); await wait(1200);
  fs.writeFileSync(path.join(OUT, "timing.json"), JSON.stringify({ keepFrom, marks, total: (Date.now() - t0) / 1000 }, null, 1));
} finally {
  const v = page.video();
  await ctx.close();
  await browser.close();
  await fetch(URL + "api/pipeline", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(backup) });
  if (v) { const p = await v.path(); fs.renameSync(p, path.join(OUT, "infill-demo.webm")); console.log("saved", path.join(OUT, "infill-demo.webm")); }
}
