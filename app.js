// Infill front end. Reads window.SITES (a GeoJSON FeatureCollection) from data/sites.js.
// Each feature's properties follow the schema in README.md ("Data schema").
const FLAGS = {
  underused:     "Vacant or underused",
  size_ok:       "Big enough to build on",
  zoning_allows: "Zoning likely allows housing",
  near_transit:  "Near frequent transit",
};
const COLORS = { high: "#1f7a4d", medium: "#c98a14", low: "#9a9a9a" };

const data = window.SITES || { type: "FeatureCollection", features: [] };
const meta = window.SITES_META || {};
const map = L.map("map").setView(meta.center || [33.70, -117.83], meta.zoom || 11);
L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
  attribution: '&copy; OpenStreetMap contributors &copy; CARTO', maxZoom: 20,
}).addTo(map);

const active = new Set(Object.keys(FLAGS));
const filtersEl = document.getElementById("filters");
for (const [k, label] of Object.entries(FLAGS)) {
  const l = document.createElement("label");
  l.innerHTML = `<input type="checkbox" checked data-k="${k}"> Must be: ${label}`;
  l.querySelector("input").onchange = (e) => { e.target.checked ? active.add(k) : active.delete(k); render(); };
  filtersEl.appendChild(l);
}

let layer = L.geoJSON(null).addTo(map);
let selectedId = null;

function passes(f) {
  const fl = f.properties.flags || {};
  return [...active].every((k) => fl[k]);
}

function render() {
  const shown = data.features.filter(passes).sort((a, b) => (b.properties.score || 0) - (a.properties.score || 0));
  layer.clearLayers();
  layer = L.geoJSON({ type: "FeatureCollection", features: shown }, {
    style: (f) => ({ color: COLORS[f.properties.confidence] || "#555", weight: 2, fillOpacity: 0.35 }),
    pointToLayer: (f, ll) => L.circleMarker(ll, { radius: 7, color: COLORS[f.properties.confidence] || "#555", fillOpacity: 0.7 }),
    onEachFeature: (f, l) => l.on("click", () => select(f)),
  }).addTo(map);

  document.getElementById("count").textContent =
    data.features.length ? `${shown.length} of ${data.features.length} parcels match` : "";
  const list = document.getElementById("list");
  list.innerHTML = "";
  if (!data.features.length) {
    list.innerHTML = '<div class="empty">No data loaded yet. Run <code>scripts/build_sites.py</code> to generate <code>data/sites.js</code> from the lane starter data.</div>';
    return;
  }
  for (const f of shown.slice(0, 200)) {
    const p = f.properties;
    const d = document.createElement("div");
    d.className = "item" + (p.id === selectedId ? " on" : "");
    d.innerHTML = `<b>${p.label || p.id}</b>
      <span class="pill ${p.confidence}">${p.confidence || "?"}</span>
      <span class="meta">${[p.city, p.acres ? p.acres.toFixed(2) + " ac" : null, p.zoning].filter(Boolean).join(" · ")}</span>`;
    d.onclick = () => select(f, true);
    list.appendChild(d);
  }
}

function select(f, fly) {
  const p = f.properties;
  selectedId = p.id;
  if (fly) {
    const b = L.geoJSON(f).getBounds();
    map.flyToBounds(b, { maxZoom: 18, duration: 0.6 });
  }
  const reasons = (p.reasons || []).map((r) =>
    `<li>${r.text}${r.source ? ` <span class="meta">— ${r.url ? `<a href="${r.url}" target="_blank" rel="noopener">${r.source}</a>` : r.source}</span>` : ""}</li>`).join("");
  const assumptions = (p.assumptions || []).map((a) => `<li>${a}</li>`).join("");
  const card = document.getElementById("card");
  card.innerHTML = `
    <button class="close" onclick="this.parentElement.style.display='none'">×</button>
    <h2>${p.label || p.id}</h2>
    <div class="meta"><span class="pill ${p.confidence}">${p.confidence} confidence</span>${p.apn ? "APN " + p.apn : ""}</div>
    ${p.summary ? `<p>${p.summary}</p>` : ""}
    <h3>Why this site</h3><ul>${reasons || "<li>No reasons recorded</li>"}</ul>
    ${assumptions ? `<h3>Assumed (not verified)</h3><ul>${assumptions}</ul>` : ""}
    <div class="verify"><b>Next step: verify on the ground.</b> Public records can be out of date. Confirm what is actually on the lot (site visit or existing-conditions survey) and check eligibility with the city before acting. This is a screening tool, not a zoning determination.</div>`;
  card.style.display = "block";
  render();
}

render();
