# Infill roadmap

Infill screens public data for land where affordable homes could go, shows every check as pass, fail or unknown with its source, and closes the loop with ground truth: what a site visit or existing-conditions survey actually finds. This is where it goes after the hackathon.

## Phase 0: today (Nov 7, 2026)

- Anaheim: 124 adopted housing-element sites, ranked, with flood, fire, transit, building-coverage and lower-income-capacity checks.
- City picker for other Orange County cities in SCAG's housing-element layer.
- Surplus public land (HCD Surplus Land Act notices) on the same map.
- Rail (To call → Called → Site visit → Surveyed → Pursuing / Dropped), ground-truth visit and survey log, error log, Claude call sheets.

## Phase 1: next month, all of Orange County

- Every jurisdiction in the SCAG layer (28 in Orange County as of Nov 7, 2026). Fill the gaps the layer has (Santa Ana is not in it) from city portals.
- SB 4 faith and nonprofit-college land: worship sites (OpenStreetMap) plus the IRS exempt-organizations file, labelled as leads, not facts.
- ADU-ready lots: single-family lots screened by size, building coverage and garage presence, using the same footprint math. ADUs, garage conversions and SB 9 splits add homes on land people already own.
- Whole-lot hazard checks (today the tool checks the center of the lot).
- "Who to call" from public sources, never from personal data.

## Phase 2: next quarter, LA and the Inland Empire

- SCAG's housing-element layer already covers its six-county region (Imperial, Los Angeles, Orange, Riverside, San Bernardino, Ventura). The flood, fire and transit layers are statewide. Expanding is mostly configuration: county zoning and land-use layers, and each city's parcel source. To verify: SCAG's per-county zoning and land-use layers outside Orange County.
- Fire-rebuild mode, starting with Altadena and Pacific Palisades. Burned parcels from CAL FIRE damage inspection data, crossed with lot size and zoning, to find lots that could come back with more homes than before (ADU, SB 9). Rebuild rules changed through emergency orders after the January 2025 fires, so every rule shown must cite the current order.
- Ground truth matters most here: what survived (foundations, garages, walls) decides what can be rebuilt, and that is what an existing-conditions survey records.

## Phase 3: later

- Coastal checks: inside the Coastal Zone (usually a coastal development permit, which is time cost), and sea-level-rise and coastal-flood exposure.
- A shared rail for a whole team, with logins.
- Re-tune the screening thresholds (labelled ASSUMPTION today) from the error log once enough visits are logged, per city.

## The loop that makes it scale

1. **Screen** public data for every site in a city.
2. **Draft** with Claude: a call sheet from the facts on the card, never invented ones.
3. **Verify on the ground**: a site visit or an existing-conditions survey (for example a 3D scan). For small sites, ADUs and conversions, those measured drawings are also the first step of the permit set.
4. **Learn**: every visit is compared with what the data predicted, and misses go into the error log. The screen gets more accurate in each city it is used in.

The tool never decides on its own. People verify, and the data gets better because they did.
