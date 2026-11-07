# Infill

> For a one-person nonprofit acquisitions team: a ranked list of the sites in one Orange County city worth calling about this month, with every check shown as pass, fail or unknown, and its source.

**Team:** Infill
**Members:** Freddie Jiang
**Lane:** 1 Find it
**Built at:** Claude Impact Lab: UCI × SoCal Affordable Housing, November 7, 2026

## The real user

A one-person acquisitions lead at a small housing nonprofit in Orange County (the lane's scenario F02). They have no GIS team, and most of their sites still come from luck: a city calls about surplus land, or a congregation offers its parking lot. Cities already publish lists of sites they say can take new homes, but the lists are filed when the plan is adopted, so nobody knows which sites are still open, which are usable, and which one to call first.

**Before:** they open a city's housing-element PDF, look up parcels one at a time across several county and state map viewers, and still can't tell whether a site has been built on since the list was made.

**After:** they open Infill, see Anaheim's 124 listed sites ranked, and get a top 10 to call this month. Each site says what passed, what failed and what is still unknown, with a link to the source, and ends with the next step: verify on the ground.

## What we built

A map of every adopted housing-element site in a city, from SCAG's regional layer, plus public land that local agencies have listed as surplus. Four Orange County cities are built in and can be switched from the city picker: **Anaheim (124 sites), Garden Grove (946), Irvine (44) and Fullerton (3)**. Any of the 28 Orange County jurisdictions in the layer can be added with one command. Each site is checked against public data:

| Question | Check | Data |
|---|---|---|
| Still available? | How much of the lot is covered by buildings | OC Building Footprints |
| Usable? | In a special flood hazard area? | OC Floodplains (FEMA zones) |
| Usable? | In a fire hazard severity zone? | OC Fire Hazard Severity Zones (LRA) |
| Usable? | Inside a high-quality transit area? (parking minimums may not apply under AB 2097) | Caltrans HQTA |
| Room for lower-income homes? | Lower-income capacity the city itself listed | SCAG Housing Element Sites |

**Surplus public land** (the brief's idea #3): HCD's Surplus Land Act notices are joined to the same map as their own layer, with the agency, size, zoning text, existing use, notice date and the same flood, fire and transit checks. The data is messy, as the brief warned: of 3,112 notices statewide, only 30 are marked Active and 3,081 are "Archive". All 22 notices in the four built-in cities are archived, so they are shown as leads to re-check, never as available land. Contact names and emails in the notices are not copied into the tool.

Each check is **pass**, **fail** or **unknown**. Unknown means the data was missing or the result is in a gray zone, and the tool says so instead of guessing. Sites are ranked with simple weights shown on screen, and every site card ends with "verify on the ground": confirm what is actually on the lot, who owns it and whether they'd sell, and check eligibility with the city.

What it found on November 7, 2026:

Across the four cities: 1,117 housing-element sites and 22 surplus notices. In Anaheim:

- 124 adopted sites in Anaheim (housing element year 2025), with 8,887 homes of listed capacity, of which 576 are listed as lower-income.
- Only 18 of the 124 sites list any lower-income capacity. The top 10 covers 343 of the 576.
- 36 sites look mostly open (buildings cover under 15% of the lot), 36 look built out (over 40%), and 52 are in between and need a look.
- All 124 sites pass the flood and fire checks, and 103 are inside a high-quality transit area.

It has four views:

- **Map:** the ranked sites, filters for each check, and a card per site with every check and its source.
- **Rail:** a ticket board for the acquisitions lead: To call → Called → Site visit → Surveyed → Pursuing / Dropped. Every move is logged with a reason.
- **Ground truth:** what site visits and existing-conditions surveys (for example a 3D scan, with a link to the E57 or PDF files) actually found, compared with what the public data predicted. Misses go into an error log, and the screen's accuracy is shown as visits come in. A visit that finds the lot built out drops the site automatically.

- **Saved:** sites starred from any city, with their location, an "Open in Maps" link, CSV export and print.

Each site card opens a **call sheet** window that leads with what matters for the call (lower-income homes listed, lot size, check results, zoning), then what to ask the city, what's still unknown, what the data shows with sources, and a draft email. From there the user can mark the site as called, log a visit, save it, export it as CSV, or print it to PDF. The call sheet itself: Claude turns the site's checks into what's known, what's unknown, questions for the city, what to look for on site, and a draft email to city housing staff (never sent).

**Demo video:** uploaded on the hub
**Live demo:** run it locally (see Try it). It is a static page, so it also works from GitHub Pages.

## How Claude is used

- **Building it:** Claude (in Cowork) read the lane repo and its `DATA-SOURCES.md`, found which public layers could answer each question, wrote the fetch and scoring scripts, built the map, and checked it in a headless browser. It also caught that Santa Ana is missing from the SCAG housing-element layer, and switched the city to Anaheim.
- **At run time:** the checks are deterministic. Every pass, fail or unknown comes from a query against public data. Claude is used for one thing: the **call sheet**. `scripts/serve.py` sends Claude only the facts already on the site card, with instructions to never invent an address, owner, statute, number or zoning meaning, and to say "unknown" when the data doesn't say. Claude returns what's known, what's unknown, questions for the city, things to check on site and a draft email. A person reads and edits it, and nothing is sent. With no API key set, the same call sheet is built from a plain template, so the tool still works.
- **The loop:** the tool screens, Claude drafts, a person verifies on the ground, and the visit feeds back into the error log. The tool never decides on its own.

## Try it

You need Python 3.8 or newer (standard library only, nothing to install) and a web browser.

```bash
git clone https://github.com/FB845/infill.git
cd infill
open index.html            # macOS. On Windows or Linux, open index.html in a browser
```

That opens the map with no server, accounts or keys. Rail and visit notes are then saved in your browser only.

For the full version (call sheets with Claude, and a shared `pipeline.json` for the rail and visit log):

```bash
cp .env.example .env       # then paste your ANTHROPIC_API_KEY into .env (optional)
python3 scripts/serve.py   # open http://localhost:8000
```

Without a key, call sheets use the plain template. `pipeline.json` and `.env` are git-ignored.

The repo includes the processed data (`data/sites.js`). To re-pull the public data and rebuild it:

```bash
python3 scripts/fetch_data.py                   # downloads and caches into raw/ (about 3 minutes, gentle on public servers)
python3 scripts/build_sites.py                  # writes data/sites.js and prints the top 10
python3 scripts/fetch_data.py --list               # the 28 OC jurisdictions in the layer
python3 scripts/fetch_data.py --city "Buena Park"   # add any of them, then:
python3 scripts/build_sites.py --city "Buena Park"  # it appears in the city picker
```

The only key is the optional `ANTHROPIC_API_KEY`, read by the local server and never sent to the browser or committed. Leaflet 1.9.4 is vendored in `vendor/` so the demo runs on slow Wi-Fi. Only the street basemap tiles need internet.

## Sources and assumptions

| Item | Source or assumption | Date checked |
|---|---|---|
| Housing-element sites, capacity by income | [SCAG HousingElementSite_poly_scag](https://maps.scag.ca.gov/scaggis/rest/services/LDX/HousingElementSite_poly_scag/MapServer) | 2026-11-07 |
| Zoning per parcel | [SCAG Zoning_poly_OR](https://maps.scag.ca.gov/scaggis/rest/services/LDX/Zoning_poly_OR/MapServer) | 2026-11-07 |
| Existing land use code per parcel | [SCAG Existinglanduse_poly_OR](https://maps.scag.ca.gov/scaggis/rest/services/LDX/Existinglanduse_poly_OR/MapServer) | 2026-11-07 |
| Building footprints | [OC Building Footprints](https://www.ocgis.com/arcpub/rest/services/Map_Layers/Building_Footprints/MapServer/0) | 2026-11-07 |
| Flood zones | [OC Floodplains](https://www.ocgis.com/arcpub/rest/services/Map_Layers/Floodplains/MapServer/0) (FEMA zones, county copy; `SFHA_TF = T` counts as a fail) | 2026-11-07 |
| Fire zones | [OC Fire Hazard Severity Zones LRA](https://www.ocgis.com/arcpub/rest/services/Map_Layers/Fire_Hazard_Severity_Zones_LRA/MapServer/0) | 2026-11-07 |
| Transit | [Caltrans CA HQ Transit Areas](https://caltrans-gis.dot.ca.gov/arcgis/rest/services/CHrailroad/CA_HQ_Transit_Areas/FeatureServer/0) | 2026-11-07 |
| AB 2097 (no minimum parking near major transit) | [HCD Technical Advisory](https://www.hcd.ca.gov/sites/default/files/docs/policy-and-research/ab-2097-ta.pdf) | 2026-11-07 |
| Surplus public land notices | [HCD Surplus Land Act Notices of Availability](https://data.ca.gov/dataset/surplus-land-act-notices-of-availability-received) (data.ca.gov CSV) | 2026-11-07 |
| Starting list of sources | [Lane 1 DATA-SOURCES.md](https://github.com/travcjohnson/claude-impact-lab-uci/blob/main/lanes/1-find-it/data/DATA-SOURCES.md) | 2026-11-07 |
| Buildings cover under 15% of the lot = mostly open | ASSUMPTION (our threshold) | |
| Buildings cover over 40% of the lot = may be built out | ASSUMPTION (our threshold) | |
| Building value under 50% / over 150% of land value = underused / redeveloped (used only where assessor values are free, e.g. Santa Ana) | ASSUMPTION (our threshold) | |
| Ranking weights: +4 if any lower-income capacity, + lower-income capacity / 25 (max +4), +3 mostly open, −2 may be built out, +2 in a high-quality transit area, −5 per flood or fire fail | ASSUMPTION (our weights) | |
| Top 10 = "sites to call this month" | ASSUMPTION (matches scenario F02) | |

Every number we made up is labelled ASSUMPTION here and in the tool.

## What is real and what is mocked

| Part | Status |
|---|---|
| Housing-element sites, capacity, zoning, land use | Working: real public data, 4 cities built in |
| Surplus public land layer | Working: real HCD notices; all in the 4 cities are archived, shown as leads |
| Grid references on site cards | Infill's own 8×8 grid over each city's sites (Thomas Guide style, not Thomas Guide pages) |
| Building coverage check | Working: real data, our thresholds |
| Flood, fire and transit checks | Working: real data |
| Building vs. land value check | Partly working: code is in place, but only Santa Ana publishes values for free, and Santa Ana is missing from the site layer |
| Ranking and top 10 | Working: our weights, shown on screen |
| Call sheet | Working with an API key (Claude); template without one |
| Rail and site-visit / survey log | Working: saved to `pipeline.json` (with the server) or the browser. Single-user; no logins |
| Screen accuracy and error log | Working, but only as good as the visits logged. No real visits are in the repo |
| Ownership, willingness to sell, utilities, contamination | Not built: shown as next steps on every card |
| Mocked data | None |

## Where it gets things wrong

- **Santa Ana is missing.** SCAG's housing-element layer lists 28 Orange County jurisdictions and Santa Ana isn't one of them, so Infill can't screen it from this layer yet.
- **Hazard and transit checks use the center of the lot.** A lot that is partly in a flood or fire zone can pass if its center is outside.
- **Coverage is an estimate.** A building is counted if its center falls inside the lot, so buildings that straddle a lot line can be counted on the wrong side. Parking lots count as open, which is often right for this purpose but not always.
- **Fire check covers local-responsibility zones only.** State-responsibility zones are not checked yet.
- **A high-quality transit area is not the same as AB 2097's "major transit stop."** The card says "parking minimums may not apply" and asks the user to confirm.
- **The capacity numbers are the city's own claims** from the 2025 housing element, not a feasibility study.
- **Housing-element lists go stale.** That's why the "still available?" check exists, but only a site visit settles it.
- **No ownership data.** The free county parcel layer has no owner field, so the tool can't say who to call yet.

## Next steps

See [ROADMAP.md](ROADMAP.md) for the longer view: all of Orange County, then LA and the Inland Empire, a fire-rebuild mode, coastal checks, and ADU-ready lots.

**For a nonprofit to use it next month:**
- Build every city in the layer (one command each).
- Add SB 4 faith-land leads (worship sites + IRS exempt-org file, labelled as leads, not facts).
- Add a "who to call" field from public sources.

**With one more week:**
- Check the whole lot instead of its center.
- Add state fire zones, slope and contamination (CalEnviroScreen).
- Use the error log to re-tune the thresholds (labelled ASSUMPTION) automatically once enough visits are logged.
- Shared rail for a whole team, with logins.

## Data and privacy

This project uses only public data. It contains no personal information about real tenants, buyers or residents. It does not request owner names or mailing addresses from any source, and stores only parcel numbers, zoning, land use, building outlines and hazard zones. The visit-note box warns users not to type owner, tenant or other personal names. It does not file applications or contact any city or person. It is a prototype and a screening tool, not a zoning, legal or financial determination.

## License

MIT, see the [LICENSE](LICENSE) file.
