// Infill front end.
// Data: window.SITES / window.SITES_META from data/sites.js (scripts/build_sites.py).
// Team state (rail stations + site visits) lives in pipeline.json via scripts/serve.py,
// or in this browser's localStorage when the page is opened as a plain file.

const FLAGS = {
  open:         "Mostly open (still available)",
  low_income:   "City listed lower-income capacity",
  no_flood:     "Not in a flood hazard area",
  no_fire:      "Not in a fire hazard zone",
  near_transit: "Inside a high-quality transit area",
};
const STATIONS = [
  ["screened", "Screened"], ["to_call", "To call"], ["called", "Called"],
  ["visit", "Site visit"], ["surveyed", "Surveyed"], ["pursuing", "Pursuing"], ["dropped", "Dropped"],
];
const FOUND = [
  ["vacant", "Vacant land", "open"], ["parking", "Surface parking", "open"],
  ["small_bldg", "Small building(s), most of lot open", "partly"], ["built", "Built out / occupied", "built"],
  ["construction", "Under construction", "built"], ["other", "Other (see note)", "unknown"],
];
const COLORS = { high: "#1f7a4d", medium: "#c98a14", low: "#9a9a9a" };
const ICON = { pass: "✓", fail: "✕", unknown: "?" };
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const data = window.SITES || { type: "FeatureCollection", features: [] };
const meta = window.SITES_META || {};
const byId = Object.fromEntries(data.features.map((f) => [f.properties.id, f]));

// ---------- team state ----------
let server = false, claudeOn = false, state = {};
const LS = "infill-pipeline-v1";
async function loadState() {
  try {
    const h = await (await fetch("/api/health")).json();
    server = !!h.ok; claudeOn = !!h.claude;
    state = await (await fetch("/api/pipeline")).json();
  } catch { try { state = JSON.parse(localStorage.getItem(LS) || "{}"); } catch { state = {}; } }
}
async function saveState() {
  if (server) { try { await fetch("/api/pipeline", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(state) }); return; } catch {} }
  try { localStorage.setItem(LS, JSON.stringify(state)); } catch {}
}
const siteState = (id) => (state[id] ||= { station: byId[id]?.properties.top ? "to_call" : "screened", visits: [], log: [] });
function setStation(id, st, why) {
  const s = siteState(id);
  if (s.station === st) return;
  s.log.push({ at: new Date().toISOString(), from: s.station, to: st, why: why || "" });
  s.station = st; saveState(); renderAll();
}

// What the desk screen predicted about availability
function predicted(p) {
  const av = (p.checks || []).filter((c) => c.group === "Still available?").map((c) => c.status);
  if (av.includes("pass") && !av.includes("fail")) return "open";
  if (av.includes("fail")) return "built";
  return "unknown";
}
function verdict(p, v) {
  const found = (FOUND.find((x) => x[0] === v.found) || [])[2] || "unknown";
  const pred = predicted(p);
  if (pred === "unknown" || found === "unknown") return { kind: "new", text: "The data couldn't tell. The visit settles it." };
  if (pred === found || (pred === "open" && found === "partly")) return { kind: "match", text: "The visit matches what the data predicted." };
  return { kind: "miss", text: `Data predicted "${pred === "open" ? "mostly open" : "built out"}", visit found "${(FOUND.find((x) => x[0] === v.found) || [])[1]}".` };
}

// ---------- map ----------
const map = L.map("map").setView(meta.center || [33.835, -117.914], meta.zoom || 12);
// Basemap: OpenStreetMap standard tiles, with Esri light gray as an automatic backup.
const BASEMAPS = [
  ["https://tile.openstreetmap.org/{z}/{x}/{y}.png", '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors', 19],
  ["https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}", "Tiles &copy; Esri", 16],
];
let baseIdx = 0, baseErrors = 0, base;
function setBase(i) {
  if (base) map.removeLayer(base);
  const [url, attribution, maxZoom] = BASEMAPS[i];
  base = L.tileLayer(url, { attribution, maxZoom: 19, maxNativeZoom: maxZoom }).addTo(map);
  base.bringToBack();
  base.on("tileerror", () => { if (++baseErrors > 4 && baseIdx < BASEMAPS.length - 1) { baseErrors = 0; setBase(++baseIdx); } });
}
setBase(0);

let topOnly = true, view = "map";
const active = new Set();
const filtersEl = document.getElementById("filters");
const topLabel = document.createElement("label");
topLabel.innerHTML = `<input type="checkbox" checked> <b>Top ${meta.top_n || 10} to call this month</b>`;
topLabel.querySelector("input").onchange = (e) => { topOnly = e.target.checked; renderAll(); };
filtersEl.appendChild(topLabel);
for (const [k, label] of Object.entries(FLAGS)) {
  const l = document.createElement("label");
  l.innerHTML = `<input type="checkbox" data-k="${k}"> Must be: ${label}`;
  l.querySelector("input").onchange = (e) => { e.target.checked ? active.add(k) : active.delete(k); renderAll(); };
  filtersEl.appendChild(l);
}

let layer = L.geoJSON(null).addTo(map);
let selectedId = null;
const passes = (f) => (!topOnly || f.properties.top) && [...active].every((k) => (f.properties.flags || {})[k]);
const stationName = (k) => (STATIONS.find((s) => s[0] === k) || [k, k])[1];

function renderList() {
  const shown = data.features.filter(passes).sort((a, b) => a.properties.rank - b.properties.rank);
  layer.clearLayers();
  layer = L.geoJSON({ type: "FeatureCollection", features: shown }, {
    style: (f) => ({ color: f.properties.id === selectedId ? "#1b1b1b" : (COLORS[f.properties.confidence] || "#555"),
                     weight: f.properties.id === selectedId ? 4 : 2, fillOpacity: 0.35,
                     dashArray: siteState(f.properties.id).station === "dropped" ? "4 4" : null }),
    onEachFeature: (f, l) => { l.on("click", () => select(f.properties.id)); l.bindTooltip(`#${f.properties.rank} ${f.properties.label}`); },
  }).addTo(map);
  document.getElementById("count").textContent = data.features.length
    ? `${shown.length} of ${data.features.length} housing-element sites in ${meta.city || "the city"} · data pulled ${meta.pulled || "?"}`
    : "";
  const list = document.getElementById("list");
  list.innerHTML = "";
  if (!data.features.length) {
    list.innerHTML = '<div class="empty">No data loaded yet. Run <code>python3 scripts/fetch_data.py</code> then <code>python3 scripts/build_sites.py</code>.</div>';
    return;
  }
  for (const f of shown.slice(0, 300)) {
    const p = f.properties, s = siteState(p.id);
    const d = document.createElement("div");
    d.className = "item" + (p.id === selectedId ? " on" : "");
    d.innerHTML = `<b>#${p.rank} · ${esc(p.label)}</b>
      <span class="pill ${p.confidence}">${p.confidence}</span><span class="station st-${s.station}">${stationName(s.station)}</span>
      <span class="meta">${esc(p.summary)}</span>`;
    d.onclick = () => select(p.id, true);
    list.appendChild(d);
  }
  if (!shown.length) list.innerHTML = '<div class="empty">No sites pass every selected check. Untick a filter.</div>';
  const foot = document.createElement("div");
  foot.className = "empty";
  foot.innerHTML = `<b>Sources</b> (checked ${esc(meta.sources?.[0]?.checked || "?")})<br>` +
    (meta.sources || []).map((s) => `<a href="${s.url}" target="_blank" rel="noopener">${esc(s.name)}</a>`).join("<br>") +
    `<br><br><b>How sites are ranked</b><br>${esc(meta.ranking || "")}` +
    `<br><br>Team notes are saved ${server ? "to pipeline.json on this computer" : "in this browser only (run scripts/serve.py to share)"}.` +
    `<br>Prototype. Screening only, not a zoning or legal determination.`;
  list.appendChild(foot);
}

// ---------- rail (Ticket Rail style) ----------
function renderRail() {
  const rail = document.getElementById("rail");
  const tracked = data.features.filter((f) => siteState(f.properties.id).station !== "screened" || f.properties.top);
  rail.innerHTML = `<div class="rail-head"><b>Rail</b> · ${tracked.length} sites in play. Move a ticket from its card. Every move is logged with a reason.</div>
    <div class="rail-cols">` + STATIONS.filter(([k]) => k !== "screened").map(([k, name]) => {
      const items = tracked.filter((f) => siteState(f.properties.id).station === k).sort((a, b) => a.properties.rank - b.properties.rank);
      return `<div class="col"><div class="col-h">${name} <span>${items.length}</span></div>` + items.map((f) => {
        const p = f.properties, s = siteState(p.id), last = s.visits[s.visits.length - 1];
        return `<div class="ticket ${p.id === selectedId ? "on" : ""}" data-id="${p.id}">
          <div class="t-top"><b>#${p.rank}</b><span class="pill ${p.confidence}">${p.confidence}</span></div>
          <div>${esc(p.label)}</div>
          <div class="meta">${p.low_income_capacity} lower-income · ${p.acres ?? "?"} ac</div>
          ${last ? `<div class="meta">Visited ${esc(last.date)}${last.survey ? " · surveyed" : ""}</div>` : ""}
        </div>`;
      }).join("") + `</div>`;
    }).join("") + `</div>`;
  rail.querySelectorAll(".ticket").forEach((t) => (t.onclick = () => select(t.dataset.id)));
}

// ---------- ground truth log ----------
function renderTruth() {
  const el = document.getElementById("truth");
  const rows = [];
  for (const [id, s] of Object.entries(state)) for (const v of s.visits || []) if (byId[id]) rows.push({ id, p: byId[id].properties, v, r: verdict(byId[id].properties, v) });
  rows.sort((a, b) => (b.v.date || "").localeCompare(a.v.date || ""));
  const judged = rows.filter((r) => r.r.kind !== "new"), hits = judged.filter((r) => r.r.kind === "match").length;
  const misses = rows.filter((r) => r.r.kind === "miss");
  el.innerHTML = `<div class="rail-head"><b>Ground truth</b> · what site visits and existing-conditions surveys found, compared with what the public data predicted.</div>
    <div class="truth-stats">
      <div><b>${rows.length}</b><span>visits logged</span></div>
      <div><b>${rows.filter((r) => r.v.survey).length}</b><span>surveys (e.g. 3D scan)</span></div>
      <div><b>${judged.length ? Math.round((100 * hits) / judged.length) + "%" : "–"}</b><span>screen accuracy (${hits} of ${judged.length} judged)</span></div>
      <div><b>${misses.length}</b><span>misses in the error log</span></div>
    </div>
    <h3 class="sec">Error log: where the data was wrong</h3>
    ${misses.length ? misses.map((r) => row(r)).join("") : '<div class="empty">No misses yet. Log a site visit from any site card.</div>'}
    <h3 class="sec">All visits</h3>
    ${rows.length ? rows.map((r) => row(r)).join("") : '<div class="empty">No visits yet.</div>'}
    <p class="meta" style="padding:0 20px 20px">Each miss is a correction to the public data and a test case for the screening thresholds (labelled ASSUMPTION). The more visits are logged, the better the next ranking gets.</p>`;
  el.querySelectorAll("[data-id]").forEach((t) => (t.onclick = () => select(t.dataset.id)));
  function row(r) {
    const f = FOUND.find((x) => x[0] === r.v.found);
    return `<div class="truth-row ${r.r.kind}" data-id="${r.id}"><b>#${r.p.rank} · ${esc(r.p.label)}</b> <span class="meta">${esc(r.v.date)}</span>
      <div>${esc(f ? f[1] : r.v.found)}${r.v.buildings ? ` · ${esc(r.v.buildings)} building(s)` : ""}${r.v.survey ? ` · ${esc(r.v.survey.method)} survey` : ""}</div>
      <div class="meta">${esc(r.r.text)}${r.v.note ? " · " + esc(r.v.note) : ""}</div></div>`;
  }
}

function renderAll() {
  renderList();
  document.getElementById("rail").style.display = view === "rail" ? "block" : "none";
  document.getElementById("truth").style.display = view === "truth" ? "block" : "none";
  if (view === "rail") renderRail();
  if (view === "truth") renderTruth();
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("on", b.dataset.view === view));
  if (selectedId && document.getElementById("card").style.display === "block") renderCard(selectedId);
}
document.querySelectorAll(".tabs button").forEach((b) => (b.onclick = () => { view = b.dataset.view; renderAll(); if (view === "map") setTimeout(() => map.invalidateSize(), 50); }));

// ---------- site card ----------
function select(id, fly) {
  selectedId = id;
  const f = byId[id];
  if (fly && view === "map") map.flyToBounds(L.geoJSON(f).getBounds(), { maxZoom: 18, duration: 0.6 });
  document.getElementById("card").style.display = "block";
  renderAll();
}

function renderCard(id) {
  const p = byId[id].properties, s = siteState(id);
  const groups = {};
  for (const c of p.checks || []) (groups[c.group] ||= []).push(c);
  const lastVisit = s.visits[s.visits.length - 1];
  if (lastVisit) {
    const fv = FOUND.find((x) => x[0] === lastVisit.found);
    const r = verdict(p, lastVisit);
    (groups["Still available?"] ||= []).unshift({ test: "Ground truth", status: fv && fv[2] === "built" ? "fail" : (fv && fv[2] !== "unknown" ? "pass" : "unknown"),
      detail: `${fv ? fv[1] : "Visited"} (${lastVisit.survey ? lastVisit.survey.method + " survey" : "site visit"}, ${lastVisit.date}). ${r.text}`, source: "Logged by the team", url: null });
  }
  const checks = Object.entries(groups).map(([g, cs]) => `<h3>${g}</h3><ul class="checks">` + cs.map((c) =>
    `<li class="${c.status}"><span class="st">${ICON[c.status]}</span><div><b>${esc(c.test)}</b>: ${esc(c.detail)}
     <div class="meta">${c.url ? `<a href="${c.url}" target="_blank" rel="noopener">${esc(c.source)}</a>` : esc(c.source)}</div></div></li>`).join("") + "</ul>").join("");
  const assumptions = (p.assumptions || []).map((a) => `<li>${esc(a)}</li>`).join("");
  const facts = [p.acres ? `${p.acres} acres` : null, p.zoning ? `zoning ${esc(p.zoning)}` : null,
                 p.landuse_code ? `SCAG land use code ${esc(p.landuse_code)}` : null].filter(Boolean).join(" · ");
  const visits = s.visits.slice().reverse().map((v) => {
    const fv = FOUND.find((x) => x[0] === v.found);
    return `<li><b>${esc(v.date)}</b> · ${esc(fv ? fv[1] : v.found)}${v.buildings ? ` · ${esc(v.buildings)} bldg` : ""}${v.survey ? ` · ${esc(v.survey.method)}${v.survey.sqft ? `, ${esc(v.survey.sqft)} sq ft` : ""}${v.survey.link ? ` · <a href="${esc(v.survey.link)}" target="_blank" rel="noopener">survey files</a>` : ""}` : ""}${v.note ? `<div class="meta">${esc(v.note)}</div>` : ""}</li>`;
  }).join("");
  const card = document.getElementById("card");
  card.innerHTML = `
    <button class="close" id="closeCard">×</button>
    <h2>#${p.rank} · ${esc(p.label)}</h2>
    <div class="meta"><span class="pill ${p.confidence}">${p.confidence} confidence</span>${facts}</div>
    <p>${esc(p.summary)}</p>
    <div class="row"><label class="meta">Station</label>
      <select id="station">${STATIONS.map(([k, n]) => `<option value="${k}" ${k === s.station ? "selected" : ""}>${n}</option>`).join("")}</select></div>
    <div class="row"><button id="callBtn" class="btn">Call sheet${claudeOn ? " (Claude)" : ""}</button>
      <button id="visitBtn" class="btn ghost">Log site visit / survey</button></div>
    <div id="callOut"></div>
    <form id="visitForm" style="display:none" class="visit">
      <label>Date <input type="date" name="date" required value="${new Date().toISOString().slice(0, 10)}"></label>
      <label>What is actually on the lot <select name="found">${FOUND.map(([k, n]) => `<option value="${k}">${n}</option>`).join("")}</select></label>
      <label>Buildings seen <input type="number" name="buildings" min="0" step="1" placeholder="optional"></label>
      <label class="chk"><input type="checkbox" name="surveyed"> Existing-conditions survey done</label>
      <div class="survey" style="display:none">
        <label>Method <select name="method"><option>3D scan</option><option>Tape / laser measure</option><option>Drone</option><option>Other</option></select></label>
        <label>Measured area (sq ft) <input type="number" name="sqft" min="0" placeholder="optional"></label>
        <label>Link to files (E57, PDF, DWG) <input type="url" name="link" placeholder="optional"></label>
      </div>
      <label>Note <textarea name="note" rows="2" placeholder="What the data got wrong. No owner, tenant or other personal names."></textarea></label>
      <button class="btn" type="submit">Save visit</button>
    </form>
    ${visits ? `<h3>Visits</h3><ul>${visits}</ul>` : ""}
    ${checks}
    ${assumptions ? `<h3>Assumed (our thresholds, not law)</h3><ul>${assumptions}</ul>` : ""}
    <div class="verify"><b>Next step: verify on the ground.</b> Housing-element lists are filed when the plan is adopted, so a site may have sold or been built since. Confirm what is actually on the lot (site visit or existing-conditions survey), who owns it and whether they would sell, and check eligibility with the city. Screening tool, not a zoning determination.</div>`;
  card.querySelector("#closeCard").onclick = () => { card.style.display = "none"; selectedId = null; renderAll(); };
  card.querySelector("#station").onchange = (e) => setStation(id, e.target.value, "set on site card");
  const form = card.querySelector("#visitForm");
  card.querySelector("#visitBtn").onclick = () => (form.style.display = form.style.display === "none" ? "grid" : "none");
  form.surveyed.onchange = (e) => (form.querySelector(".survey").style.display = e.target.checked ? "grid" : "none");
  form.onsubmit = (e) => {
    e.preventDefault();
    const v = { date: form.date.value, found: form.found.value, buildings: form.buildings.value || null, note: form.note.value.trim() || null,
                survey: form.surveyed.checked ? { method: form.method.value, sqft: form.sqft.value || null, link: form.link.value || null } : null };
    s.visits.push(v);
    const next = v.survey ? "surveyed" : (["to_call", "called", "screened"].includes(s.station) ? "visit" : s.station);
    if ((FOUND.find((x) => x[0] === v.found) || [])[2] === "built") setStation(id, "dropped", "visit found the lot built out");
    else setStation(id, next, v.survey ? "existing-conditions survey logged" : "site visit logged");
    saveState(); renderAll();
  };
  card.querySelector("#callBtn").onclick = () => callSheet(id);
  if (callCache[id]) showCall(id, callCache[id]);
}

// ---------- call sheet ----------
const callCache = {};
function siteForClaude(p) {
  const s = siteState(p.id);
  return { city: p.city, label: p.label, apn: p.apn, acres: p.acres, zoning_code: p.zoning, scag_zoning_category: p.zoning_scag,
           scag_land_use_code: p.landuse_code, lower_income_capacity_listed: p.low_income_capacity, total_capacity_listed: p.total_capacity,
           rank: p.rank, summary: p.summary,
           checks: p.checks.map((c) => ({ question: c.group, test: c.test, status: c.status, detail: c.detail, source: c.source })),
           assumptions: p.assumptions, site_visits: s.visits.map((v) => ({ date: v.date, found: (FOUND.find((x) => x[0] === v.found) || [])[1], survey: v.survey ? v.survey.method : null })),
           data_pulled: meta.pulled };
}
function templateSheet(p) {
  const by = (st) => p.checks.filter((c) => c.status === st);
  return { headline: `${p.label} in ${p.city}: ${p.summary}.`,
    known: by("pass").concat(by("fail")).map((c) => `${c.test}: ${c.detail} (${c.source})`).slice(0, 5),
    unknown: by("unknown").map((c) => `${c.test}: ${c.detail}`).concat(["Who owns the site and whether they would sell", "Water and sewer capacity", "Contamination history"]).slice(0, 5),
    ask_city: ["Is this site still available as listed in the housing element?", "Which objective standards apply (parking, setbacks, height)?", "Is the site eligible for any streamlined approval path?", "Who in housing or planning staff handles affordable projects on this site?"],
    ask_on_site: ["What is on the lot today (buildings, parking, vacant)?", "Access, curb cuts and street frontage", "Visible utilities (power poles, meters, manholes)", "Grade changes, trees or easements visible on site"],
    email_subject: `Question about housing element site ${p.apn ? "APN " + p.apn : p.label}`,
    email_body: `Hello,\n\nI work with [nonprofit name], an affordable housing nonprofit. Your adopted housing element lists ${p.apn ? "APN " + p.apn : p.label} with capacity for ${p.low_income_capacity} lower-income homes. Could you tell me whether the site is still available, and who we should talk to about it?\n\nThank you,\n[name]\n[phone]`,
    model: "template (no Claude key set)" };
}
async function callSheet(id) {
  const p = byId[id].properties, out = document.getElementById("callOut");
  out.innerHTML = `<div class="callsheet meta">${claudeOn ? "Claude is writing the call sheet from this site's checks…" : "Building the call sheet…"}</div>`;
  let sheet;
  if (claudeOn) {
    try {
      const r = await fetch("/api/callsheet", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ site: siteForClaude(p) }) });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || r.status);
      sheet = j;
    } catch (e) { sheet = templateSheet(p); sheet.model += ` · Claude call failed: ${e.message}`; }
  } else sheet = templateSheet(p);
  callCache[id] = sheet; showCall(id, sheet);
}
function showCall(id, c) {
  const li = (xs) => (xs || []).map((x) => `<li>${esc(x)}</li>`).join("");
  document.getElementById("callOut").innerHTML = `<div class="callsheet">
    <div class="meta">Call sheet · ${esc(c.model)} · uses only the facts on this card. Check before you rely on it.</div>
    <p><b>${esc(c.headline)}</b></p>
    <h4>Known</h4><ul>${li(c.known)}</ul><h4>Unknown</h4><ul>${li(c.unknown)}</ul>
    <h4>Ask the city</h4><ul>${li(c.ask_city)}</ul><h4>Look for on site</h4><ul>${li(c.ask_on_site)}</ul>
    <h4>Draft email (not sent)</h4><div class="email"><b>${esc(c.email_subject)}</b><pre>${esc(c.email_body)}</pre></div>
    <button class="btn ghost" id="copyEmail">Copy email</button></div>`;
  document.getElementById("copyEmail").onclick = () => navigator.clipboard?.writeText(`${c.email_subject}\n\n${c.email_body}`);
}

loadState().then(renderAll);
