// Infill front end. Reads window.SITES (GeoJSON) and window.SITES_META from data/sites.js,
// which scripts/build_sites.py generates from public data.
const FLAGS = {
  open:         "Mostly open (still available)",
  low_income:   "City listed lower-income capacity",
  no_flood:     "Not in a flood hazard area",
  no_fire:      "Not in a fire hazard zone",
  near_transit: "Inside a high-quality transit area",
};
const COLORS = { high: "#1f7a4d", medium: "#c98a14", low: "#9a9a9a" };
const ICON = { pass: "✓", fail: "✕", unknown: "?" };

const data = window.SITES || { type: "FeatureCollection", features: [] };
const meta = window.SITES_META || {};
const map = L.map("map").setView(meta.center || [33.835, -117.914], meta.zoom || 12);
L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
  attribution: '&copy; OpenStreetMap contributors &copy; CARTO', maxZoom: 20,
}).addTo(map);

let topOnly = true;
const active = new Set();
const filtersEl = document.getElementById("filters");
const topLabel = document.createElement("label");
topLabel.innerHTML = `<input type="checkbox" checked> <b>Top ${meta.top_n || 10} to call this month</b>`;
topLabel.querySelector("input").onchange = (e) => { topOnly = e.target.checked; render(); };
filtersEl.appendChild(topLabel);
for (const [k, label] of Object.entries(FLAGS)) {
  const l = document.createElement("label");
  l.innerHTML = `<input type="checkbox" data-k="${k}"> Must be: ${label}`;
  l.querySelector("input").onchange = (e) => { e.target.checked ? active.add(k) : active.delete(k); render(); };
  filtersEl.appendChild(l);
}

let layer = L.geoJSON(null).addTo(map);
let selectedId = null;
const passes = (f) => (!topOnly || f.properties.top) && [...active].every((k) => (f.properties.flags || {})[k]);

function render() {
  const shown = data.features.filter(passes).sort((a, b) => a.properties.rank - b.properties.rank);
  layer.clearLayers();
  layer = L.geoJSON({ type: "FeatureCollection", features: shown }, {
    style: (f) => ({ color: f.properties.id === selectedId ? "#1b1b1b" : (COLORS[f.properties.confidence] || "#555"),
                     weight: f.properties.id === selectedId ? 4 : 2, fillOpacity: 0.35 }),
    onEachFeature: (f, l) => { l.on("click", () => select(f)); l.bindTooltip(`#${f.properties.rank} ${f.properties.label}`); },
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
    const p = f.properties;
    const d = document.createElement("div");
    d.className = "item" + (p.id === selectedId ? " on" : "");
    d.innerHTML = `<b>#${p.rank} · ${p.label}</b>
      <span class="pill ${p.confidence}">${p.confidence}</span>
      <span class="meta">${p.summary || ""}</span>`;
    d.onclick = () => select(f, true);
    list.appendChild(d);
  }
  if (!shown.length) list.innerHTML = '<div class="empty">No sites pass every selected check. Untick a filter.</div>';
  const foot = document.createElement("div");
  foot.className = "empty";
  foot.innerHTML = `<b>Sources</b> (checked ${meta.sources?.[0]?.checked || "?"})<br>` +
    (meta.sources || []).map((s) => `<a href="${s.url}" target="_blank" rel="noopener">${s.name}</a>`).join("<br>") +
    `<br><br><b>How sites are ranked</b><br>${meta.ranking || ""}` +
    `<br><br>Prototype. Screening only, not a zoning or legal determination.`;
  list.appendChild(foot);
}

function select(f, fly) {
  const p = f.properties;
  selectedId = p.id;
  if (fly) map.flyToBounds(L.geoJSON(f).getBounds(), { maxZoom: 18, duration: 0.6 });
  const groups = {};
  for (const c of p.checks || []) (groups[c.group] ||= []).push(c);
  const checks = Object.entries(groups).map(([g, cs]) => `<h3>${g}</h3><ul class="checks">` + cs.map((c) =>
    `<li class="${c.status}"><span class="st">${ICON[c.status]}</span><div><b>${c.test}</b>: ${c.detail}
     <div class="meta"><a href="${c.url}" target="_blank" rel="noopener">${c.source}</a></div></div></li>`).join("") + "</ul>").join("");
  const assumptions = (p.assumptions || []).map((a) => `<li>${a}</li>`).join("");
  const facts = [p.acres ? `${p.acres} acres` : null, p.zoning ? `zoning ${p.zoning}` : null,
                 p.landuse_code ? `SCAG land use code ${p.landuse_code}` : null].filter(Boolean).join(" · ");
  const card = document.getElementById("card");
  card.innerHTML = `
    <button class="close" onclick="this.parentElement.style.display='none'">×</button>
    <h2>#${p.rank} · ${p.label}</h2>
    <div class="meta"><span class="pill ${p.confidence}">${p.confidence} confidence</span>${facts}</div>
    <p>${p.summary || ""}</p>
    ${checks}
    ${assumptions ? `<h3>Assumed (our thresholds, not law)</h3><ul>${assumptions}</ul>` : ""}
    <div class="verify"><b>Next step: verify on the ground.</b> Housing-element lists are filed when the plan is adopted, so a site may have sold or been built since. Confirm what is actually on the lot (site visit or existing-conditions survey), who owns it and whether they would sell, and check eligibility with the city. Screening tool, not a zoning determination.</div>`;
  card.style.display = "block";
  render();
}

render();
