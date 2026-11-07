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

const CAPTIONS = [
  "Nonprofits find land for affordable homes by luck. Anaheim lists 124 sites. Which ones are still real?",
  "Infill checks every site against public data: still open, flood, fire, transit, and the lower-income homes the city listed. Every check shows its source.",
  "Claude turns those facts into a call sheet and a draft email to the city, using only what the data shows.",
  "After a site visit or a 3D scan, the team logs what's really there (demo entry shown). Every miss goes into the error log, so the screen gets better.",
  "Same pipeline, any city: 1,117 sites across four Orange County cities so far.",
];

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
      #demo-cursor.down { transform:scale(.7); }`;
    document.head.appendChild(css);
    const t = document.createElement("div"); t.id = "demo-title";
    t.innerHTML = `<h1>Infill</h1><p>Nonprofits find land by luck. Infill finds it on purpose.</p><small>Claude Impact Lab · UCI × SoCal Affordable Housing · Lane 1: Find it</small>`;
    document.body.appendChild(t);
    const c = document.createElement("div"); c.id = "demo-cap"; c.style.opacity = "0"; document.body.appendChild(c);
    const k = document.createElement("div"); k.id = "demo-cursor"; document.body.appendChild(k);
  });
  const caption = (txt) => page.evaluate((t) => { const c = document.getElementById("demo-cap"); c.textContent = t; c.style.opacity = t ? "1" : "0"; }, txt);
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
  await wait(400); await caption(CAPTIONS[0]); await wait(4200);
  // 2. Site card with checks and sources
  await caption(CAPTIONS[1]);
  await point(".list-row", { nth: 0 }); await wait(2600);
  await page.evaluate(() => document.getElementById("card").scrollTo({ top: 360, behavior: "smooth" })); await wait(2200);
  // 3. Call sheet window + Mark as called
  await caption(CAPTIONS[2]);
  await page.evaluate(() => document.getElementById("card").scrollTo({ top: 0 })); await wait(200);
  await point("#callBtn"); await wait(2700);
  await page.evaluate(() => document.getElementById("modal").scrollTo({ top: 9999, behavior: "smooth" })); await wait(1600);
  await point("#m-called"); await wait(1300);
  await page.keyboard.press("Escape"); await wait(500);
  // 4. Log a 3D-scan visit on site 03, then Ground truth
  await caption(CAPTIONS[3]);
  await point(".list-row", { nth: 2 }); await wait(1000);
  await point("#visitBtn"); await wait(400);
  await page.selectOption("#v-found", "parking");
  await point('input[name="surveyed"]'); await wait(300);
  // Honest demo data: this visit did not happen, so the note says so on screen.
  await page.fill('#v-n', "Demo entry for this video, not a real site visit.");
  await point('#visitForm button[type="submit"]'); await wait(900);
  await point('.tabs button[data-view="truth"]'); await wait(2600);
  // 5. Scale: Garden Grove, all 946 sites
  await caption(CAPTIONS[4]);
  await point('.tabs button[data-view="map"]'); await wait(300);
  await page.evaluate(() => { document.getElementById("card").style.display = "none"; });
  await point("#city", { click: false });
  await page.selectOption("#city", "garden-grove"); await wait(900);
  await point('.segmented button[data-top="0"]'); await wait(3400);
  // End card
  await caption("");
  await page.evaluate(() => {
    const t = document.createElement("div"); t.id = "demo-title"; t.style.opacity = "0";
    t.innerHTML = `<h1>Infill</h1><p>Screen. Draft with Claude. Verify on the ground. Learn.</p><small>github.com/FB845/infill · public data only · prototype, not a zoning determination</small>`;
    document.body.appendChild(t); requestAnimationFrame(() => (t.style.opacity = "1"));
  });
  await wait(3000);
  fs.writeFileSync(path.join(OUT, "timing.json"), JSON.stringify({ keepFrom, total: (Date.now() - t0) / 1000 }, null, 1));
} finally {
  const v = page.video();
  await ctx.close();
  await browser.close();
  await fetch(URL + "api/pipeline", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(backup) });
  if (v) { const p = await v.path(); fs.renameSync(p, path.join(OUT, "infill-demo.webm")); console.log("saved", path.join(OUT, "infill-demo.webm")); }
}
