# Infill

**Nonprofits find land by luck. Infill finds it on purpose.**

Built at the Claude Impact Lab: UCI x SoCal Affordable Housing (Nov 7, 2026). Lane: **Find it**.

## One-line summary
A map that screens public parcel and zoning data for <CITY> and shows which lots a nonprofit builder could pursue for affordable homes, with the reasons and sources for every flag.

## Real user
**Who:** <e.g. a site-acquisition lead at a Habitat-style nonprofit builder in Orange County>
**Before:** <how they find sites today: broker tips, word of mouth, driving around, luck>
**After:** <they open Infill, filter to lots that pass every check, and get a shortlist with reasons and sources in minutes>

## What it does
1. Loads public parcel, zoning and transit data for <CITY>.
2. Flags each parcel against simple screening checks:
   - Vacant or underused
   - Big enough to build on
   - Zoning likely allows housing
   - Near frequent transit
3. Ranks the matches and gives each one a confidence label (high / medium / low).
4. Explains *why* each site was flagged, with a source for every reason.
5. Ends every site card with a "verify on the ground" step: public records can be out of date, so the next step is a site visit or existing-conditions survey (e.g. 3D scan) and a check with the city.

Infill is a screening tool. It does not make zoning or eligibility determinations.

## Run it
Open `index.html` in a browser. No server or API key needed.
To rebuild the data: `python3 scripts/build_sites.py` (writes `data/sites.js`).

## Sources
| Data | Source | Link | Date pulled |
|---|---|---|---|
| Parcels | <lane starter data / county> | <link> | 2026-11-07 |
| Zoning | <city GIS> | <link> | 2026-11-07 |
| Transit stops | <OCTA GTFS> | <link> | 2026-11-07 |
| Laws referenced | <e.g. AB 2011, SB 4, Housing Element site inventory> | <link> | |

## Assumptions (every assumed number is labeled)
- <e.g. "Underused" = improvement value under X% of land value — ASSUMED threshold>
- <e.g. "Big enough" = at least X acres — ASSUMED>
- <e.g. "Near transit" = within 0.5 mi of a frequent stop — ASSUMED>

## Data schema (`data/sites.js`)
`window.SITES` is a GeoJSON FeatureCollection. Each feature's `properties`:
- `id`, `label`, `apn`, `city`, `acres`, `zoning`
- `flags`: `{ underused, size_ok, zoning_allows, near_transit }` (booleans)
- `score` (number, for ranking), `confidence` (`high` | `medium` | `low`)
- `summary` (one plain-English line)
- `reasons`: `[{ text, source, url }]`
- `assumptions`: `[string]`

No owner names or other personal information are stored or shown.

## Scale
The pipeline only needs parcel, zoning and transit layers, which every county and most cities publish. Pointing it at a new city means swapping the input files, so the next 100 projects come from running the same screen across OC cities, not from new code.

## License
MIT
