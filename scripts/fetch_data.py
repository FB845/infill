#!/usr/bin/env python3
"""Download and cache the public data Infill needs for one city.

Python 3.8+ standard library only. Writes JSON into raw/ (git-ignored).
Gentle on public servers: one request at a time with a pause, and every
response is cached, so re-running only fetches what is missing.

Usage:  python3 scripts/fetch_data.py            (defaults to Santa Ana)
        python3 scripts/fetch_data.py --city "Santa Ana" --refresh
"""
import argparse, json, os, re, sys, time, urllib.parse, urllib.request

RAW = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "raw")
PAUSE = 0.25  # seconds between requests

SRC = {
    "he_sites":   "https://maps.scag.ca.gov/scaggis/rest/services/LDX/HousingElementSite_poly_scag/MapServer",
    "zoning":     "https://maps.scag.ca.gov/scaggis/rest/services/LDX/Zoning_poly_OR/MapServer",
    "landuse":    "https://maps.scag.ca.gov/scaggis/rest/services/LDX/Existinglanduse_poly_OR/MapServer",
    "footprints": "https://www.ocgis.com/arcpub/rest/services/Map_Layers/Building_Footprints/MapServer/0",
    "sa_parcels": "https://gis.santa-ana.org/server/rest/services/Public/GIS_AssessorParcels/MapServer/0",
    "flood":      "https://www.ocgis.com/arcpub/rest/services/Map_Layers/Floodplains/MapServer/0",
    "fire_lra":   "https://www.ocgis.com/arcpub/rest/services/Map_Layers/Fire_Hazard_Severity_Zones_LRA/MapServer/0",
    "hqta":       "https://caltrans-gis.dot.ca.gov/arcgis/rest/services/CHrailroad/CA_HQ_Transit_Areas/FeatureServer/0",
}

def get(url, params=None, tries=3):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "infill-hackathon-prototype/0.1"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read().decode("utf-8"))
            time.sleep(PAUSE)
            if isinstance(data, dict) and "error" in data:
                raise RuntimeError(json.dumps(data["error"])[:300])
            return data
        except Exception as e:  # retry slow servers (FEMA/SCAG can time out on first call)
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"GET failed: {url[:160]} :: {last}")

def cached(name, fn, refresh=False):
    path = os.path.join(RAW, name)
    if os.path.exists(path) and not refresh:
        with open(path) as f:
            return json.load(f)
    data = fn()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)
    return data

def layer_url(base):
    """MapServer root -> first feature layer URL; layer URL -> itself."""
    if re.search(r"/(MapServer|FeatureServer)/\d+$", base):
        return base
    info = get(base, {"f": "json"})
    layers = [l for l in info.get("layers", []) if not l.get("subLayerIds")]
    return f"{base}/{layers[0]['id']}"

def fields(meta):
    return [f["name"] for f in meta.get("fields", [])]

def pick(names, *patterns):
    for p in patterns:
        for n in names:
            if re.search(p, n, re.I):
                return n
    return None

def query_all(url, where, out_fields="*", geometry=True, page=None):
    feats, offset = [], 0
    meta = get(url, {"f": "json"})
    page = page or int(meta.get("maxRecordCount") or 1000)
    while True:
        d = get(url + "/query", {
            "where": where, "outFields": out_fields, "returnGeometry": str(geometry).lower(),
            "outSR": 4326, "f": "geojson", "resultOffset": offset, "resultRecordCount": page,
            "geometryPrecision": 6,
        })
        got = d.get("features", [])
        feats += got
        print(f"    {len(feats)} features", file=sys.stderr)
        if len(got) < page and not d.get("exceededTransferLimit") and not d.get("properties", {}).get("exceededTransferLimit"):
            break
        offset += len(got)
        if not got:
            break
    return {"type": "FeatureCollection", "features": feats}

def intersect(url, geom, out_fields="*", geometry=False):
    """Features of `url` intersecting one GeoJSON polygon (sent as Esri JSON, WGS84)."""
    rings = geom["coordinates"] if geom["type"] == "Polygon" else [r for p in geom["coordinates"] for r in p]
    esri = {"rings": rings, "spatialReference": {"wkid": 4326}}
    d = get(url + "/query", {
        "geometry": json.dumps(esri), "geometryType": "esriGeometryPolygon", "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects", "outFields": out_fields,
        "returnGeometry": str(geometry).lower(), "outSR": 4326, "f": "geojson", "geometryPrecision": 6,
    })
    return d.get("features", [])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default="Santa Ana")
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    slug = a.city.lower().replace(" ", "-")
    os.makedirs(RAW, exist_ok=True)

    # 1. Layer metadata (so field names are discovered, not guessed)
    urls, metas = {}, {}
    for k, base in SRC.items():
        try:
            urls[k] = cached(f"meta/{k}_url.json", lambda b=base: layer_url(b), a.refresh)
            metas[k] = cached(f"meta/{k}.json", lambda u=urls[k]: get(u, {"f": "json"}), a.refresh)
            print(f"[meta] {k}: {len(fields(metas[k]))} fields", file=sys.stderr)
        except Exception as e:
            print(f"[meta] {k}: FAILED {e}", file=sys.stderr)

    # 2. Housing-element sites for the city
    hf = fields(metas["he_sites"])
    jur = pick(hf, r"^Jurisdiction$", r"jurisdic", r"^CITY$")
    where = f"UPPER({jur}) LIKE '%{a.city.upper()}%'"
    print(f"[he_sites] where {where}", file=sys.stderr)
    sites = cached(f"{slug}/he_sites.geojson", lambda: query_all(urls["he_sites"], where), a.refresh)
    print(f"[he_sites] {len(sites['features'])} sites", file=sys.stderr)

    # 3. Per-site checks (cached one file per site so a crash can resume)
    checks = {
        "footprints": ("footprints", True),
        "flood": ("flood", False),
        "fire_lra": ("fire_lra", False),
        "hqta": ("hqta", False),
        "zoning": ("zoning", False),
        "landuse": ("landuse", False),
    }
    for i, f in enumerate(sites["features"]):
        g = f.get("geometry")
        if not g or g["type"] not in ("Polygon", "MultiPolygon"):
            continue
        sid = f"site{i:04d}"
        for name, (k, want_geom) in checks.items():
            if k not in urls:
                continue
            try:
                cached(f"{slug}/checks/{sid}_{name}.json",
                       lambda u=urls[k], g=g, w=want_geom: intersect(u, g, geometry=w), a.refresh)
            except Exception as e:
                print(f"  {sid} {name}: {e}", file=sys.stderr)
        if i % 10 == 0:
            print(f"[checks] {i+1}/{len(sites['features'])}", file=sys.stderr)

    # 4. Santa Ana assessor values by APN (only for Santa Ana)
    if a.city.lower() == "santa ana" and "sa_parcels" in metas:
        pf = fields(metas["sa_parcels"])
        apn_f = pick(pf, r"^APN$", r"APN", r"ASSESS")
        he_apn = pick(hf, r"Assessor_Parcel", r"APN")
        apns = sorted({re.sub(r"\D", "", str(s["properties"].get(he_apn) or "")) for s in sites["features"]} - {""})
        # Privacy: never download owner names or mailing addresses. Keep APN, values, use, size, year only.
        keep = [n for n in pf if re.search(r"APN|LAND|IMPR|VAL|YEAR|YR|USE|ACRE|SQ|AREA|ZON", n, re.I)
                and not re.search(r"MAIL|OWNER|NAME|ADDR|SITUS|PHONE|EMAIL", n, re.I)]
        sa_fields = ",".join(dict.fromkeys([apn_f] + keep))
        print(f"[sa_parcels] {len(apns)} APNs via field {apn_f}; fields {sa_fields}", file=sys.stderr)
        out = []
        for j in range(0, len(apns), 50):
            batch = apns[j:j + 50]
            def q(batch=batch):
                ins = ",".join(f"'{x}'" for x in batch)
                # match with or without dashes
                w = f"REPLACE({apn_f},'-','') IN ({ins})"
                try:
                    return get(urls["sa_parcels"] + "/query", {"where": w, "outFields": sa_fields, "returnGeometry": "false", "f": "json"}).get("features", [])
                except Exception:
                    return get(urls["sa_parcels"] + "/query", {"where": f"{apn_f} IN ({ins})", "outFields": sa_fields, "returnGeometry": "false", "f": "json"}).get("features", [])
            out += cached(f"{slug}/sa_parcels_{j:05d}.json", q, a.refresh)
        print(f"[sa_parcels] {len(out)} matched", file=sys.stderr)

    with open(os.path.join(RAW, slug, "FETCHED_AT.txt"), "w") as fh:
        fh.write(time.strftime("%Y-%m-%d %H:%M %Z") + "\n")
    print("done", file=sys.stderr)

if __name__ == "__main__":
    main()
