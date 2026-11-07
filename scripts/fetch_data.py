#!/usr/bin/env python3
"""Download and cache the public data Infill needs for one OC city.

Python 3.8+ standard library only. Writes JSON into raw/ (git-ignored).
Gentle on public servers: one request at a time with a pause, and every
response is cached, so re-running only fetches what is missing.

Usage:  python3 scripts/fetch_data.py                 (defaults to Anaheim)
        python3 scripts/fetch_data.py --city "Fullerton"
        python3 scripts/fetch_data.py --refresh       (re-download everything)
"""
import argparse, json, os, re, sys, time, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "raw")
PAUSE = 0.2  # seconds between requests

LAYERS = {
    "he_sites":   "https://maps.scag.ca.gov/scaggis/rest/services/LDX/HousingElementSite_poly_scag/MapServer/0",
    "zoning":     "https://maps.scag.ca.gov/scaggis/rest/services/LDX/Zoning_poly_OR/MapServer/0",
    "landuse":    "https://maps.scag.ca.gov/scaggis/rest/services/LDX/Existinglanduse_poly_OR/MapServer/0",
    "footprints": "https://www.ocgis.com/arcpub/rest/services/Map_Layers/Building_Footprints/MapServer/0",
    "sa_parcels": "https://gis.santa-ana.org/server/rest/services/Public/GIS_AssessorParcels/MapServer/0",
    "flood":      "https://www.ocgis.com/arcpub/rest/services/Map_Layers/Floodplains/MapServer/0",
    "fire_lra":   "https://www.ocgis.com/arcpub/rest/services/Map_Layers/Fire_Hazard_Severity_Zones_LRA/MapServer/0",
    "hqta":       "https://caltrans-gis.dot.ca.gov/arcgis/rest/services/CHrailroad/CA_HQ_Transit_Areas/FeatureServer/0",
}

def log(*a):
    print(*a, file=sys.stderr, flush=True)

def call(url, params, tries=3):
    """POST a query (avoids URL-length limits). Retries slow servers."""
    body = urllib.parse.urlencode(params).encode()
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=body, headers={
                "User-Agent": "infill-hackathon-prototype/0.2",
                "Content-Type": "application/x-www-form-urlencoded"})
            with urllib.request.urlopen(req, timeout=90) as r:
                data = json.loads(r.read().decode("utf-8"))
            time.sleep(PAUSE)
            if isinstance(data, dict) and "error" in data:
                raise RuntimeError(json.dumps(data["error"])[:300])
            return data
        except Exception as e:
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"{url[:120]} :: {last}")

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

def query_pages(url, base_params, page=1000):
    feats, offset = [], 0
    while True:
        p = dict(base_params, resultOffset=offset, resultRecordCount=page)
        d = call(url + "/query", p)
        got = d.get("features", [])
        feats += got
        more = d.get("exceededTransferLimit") or (d.get("properties") or {}).get("exceededTransferLimit")
        log(f"    {len(feats)} features")
        if not got or (len(got) < page and not more):
            break
        offset += len(got)
    return feats

def geo(url, where="1=1", out_fields="*", envelope=None, page=1000):
    p = {"where": where, "outFields": out_fields, "returnGeometry": "true",
         "outSR": 4326, "f": "geojson", "geometryPrecision": 6}
    if envelope:
        p.update({"geometry": ",".join(map(str, envelope)), "geometryType": "esriGeometryEnvelope",
                  "inSR": 4326, "spatialRel": "esriSpatialRelIntersects"})
    return {"type": "FeatureCollection", "features": query_pages(url, p, page)}

def attrs_in(url, field, values, out_fields, batch=100, quote=True):
    out = []
    for i in range(0, len(values), batch):
        vals = values[i:i + batch]
        ins = ",".join((f"'{v}'" if quote else str(v)) for v in vals)
        d = call(url + "/query", {"where": f"{field} IN ({ins})", "outFields": out_fields,
                                  "returnGeometry": "false", "f": "json"})
        out += [f["attributes"] for f in d.get("features", [])]
    return out

def rings_of(g):
    if g["type"] == "Polygon":
        return g["coordinates"]
    if g["type"] == "MultiPolygon":
        return [r for p in g["coordinates"] for r in p]
    return []

def bbox(features, pad=0.002):
    xs, ys = [], []
    for f in features:
        for r in rings_of(f.get("geometry") or {"type": "x"}):
            for x, y in r:
                xs.append(x); ys.append(y)
    return [min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default="Anaheim")
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    slug = a.city.lower().replace(" ", "-")
    R = a.refresh
    os.makedirs(os.path.join(RAW, slug), exist_ok=True)

    # 1. Find the exact jurisdiction spelling SCAG uses for this city
    names = cached("meta/he_jurisdictions.json", lambda: sorted({
        x["attributes"]["Jurisdiction"] for x in call(LAYERS["he_sites"] + "/query", {
            "where": "COUNTY='Orange'", "outFields": "Jurisdiction", "returnDistinctValues": "true",
            "returnGeometry": "false", "f": "json"}).get("features", [])}), R)
    key = re.sub(r"[^a-z]", "", a.city.lower())
    match = [n for n in names if key in re.sub(r"[^a-z]", "", str(n).lower())]
    log(f"[he_sites] OC jurisdictions: {len(names)}; match for {a.city!r}: {match}")
    if not match:
        log("No match. Available names:", names); sys.exit(1)
    jur = match[0].replace("'", "''")

    # 2. Housing-element sites (polygons + capacity)
    sites = cached(f"{slug}/he_sites.geojson",
                   lambda: geo(LAYERS["he_sites"], f"COUNTY='Orange' AND Jurisdiction='{jur}'"), R)
    if not sites["features"]:
        os.remove(os.path.join(RAW, slug, "he_sites.geojson"))
        log("0 sites returned; cache removed so the next run retries."); sys.exit(1)
    log(f"[he_sites] {len(sites['features'])} sites")
    env = bbox(sites["features"])

    # 3. Zoning + existing land use joined by SCAG parcel id (attributes only)
    pids = sorted({f["properties"].get("PID24") for f in sites["features"]} - {None, ""})
    log(f"[zoning/landuse] {len(pids)} parcel ids")
    cached(f"{slug}/zoning.json", lambda: attrs_in(LAYERS["zoning"], "PID24", pids,
           "PID24,APN24,CITY,ACRES,SLOPE,ZN24_CITY,ZN24_SCAG,YEAR_ZN"), R)
    cached(f"{slug}/landuse.json", lambda: attrs_in(LAYERS["landuse"], "PID24", pids,
           "PID24,APN24,ACRES,SLOPE,LU24,LU24_2ND,YEAR"), R)

    # 4. Constraint layers clipped to the city's bounding box (polygons)
    for k, fields in [("flood", "FLD_ZONE,ZONE_SUBTY,SFHA_TF"), ("fire_lra", "HAZ_CLASS,HAZ_CODE,INCORP"),
                      ("hqta", "hqta_type,agency_primary,hqta_details")]:
        log(f"[{k}]")
        try:
            cached(f"{slug}/{k}.geojson", lambda k=k, fl=fields: geo(LAYERS[k], "1=1", fl, env, page=500), R)
        except Exception as e:
            log(f"  {k} FAILED: {e}")

    # 5. Building footprints per site (polygon intersect; POST so long polygons are fine)
    fp_dir = f"{slug}/footprints"
    for i, f in enumerate(sites["features"]):
        g = f.get("geometry")
        if not g or not rings_of(g):
            continue
        oid = f["properties"].get("OBJECTID", i)
        def q(g=g):
            esri = {"rings": rings_of(g), "spatialReference": {"wkid": 4326}}
            d = call(LAYERS["footprints"] + "/query", {
                "geometry": json.dumps(esri), "geometryType": "esriGeometryPolygon", "inSR": 4326,
                "spatialRel": "esriSpatialRelIntersects", "outFields": "Height", "returnGeometry": "true",
                "outSR": 4326, "f": "geojson", "geometryPrecision": 6})
            return d.get("features", [])
        try:
            cached(f"{fp_dir}/{oid}.json", q, R)
        except Exception as e:
            log(f"  footprints {oid}: {e}")
        if i % 25 == 0:
            log(f"[footprints] {i + 1}/{len(sites['features'])}")

    # 6. Santa Ana assessor land vs. building value (privacy: values only, no owner/mailing fields)
    if slug == "santa-ana":
        apns = sorted({re.sub(r"\D", "", str(f["properties"].get("Assessor_Parcel_Number") or f["properties"].get("APN24") or ""))
                       for f in sites["features"]} - {""})
        log(f"[sa_parcels] {len(apns)} APNs")
        def sa():
            out = []
            for i in range(0, len(apns), 100):
                batch = apns[i:i + 100]
                ins = ",".join(f"'{x}'" for x in batch)
                for where in (f"REPLACE(AssessmentNo,'-','') IN ({ins})", f"AssessmentNo IN ({ins})"):
                    try:
                        d = call(LAYERS["sa_parcels"] + "/query", {"where": where,
                                 "outFields": "AssessmentNo,LandVal,ImprovedVal,AssdAmt,LotType",
                                 "returnGeometry": "false", "f": "json"})
                        out += [x["attributes"] for x in d.get("features", [])]
                        break
                    except Exception as e:
                        log(f"  sa_parcels where failed, trying next form: {e}")
            return out
        rows = cached(f"{slug}/sa_parcels.json", sa, R)
        log(f"[sa_parcels] {len(rows)} matched")

    with open(os.path.join(RAW, slug, "FETCHED_AT.txt"), "w") as fh:
        fh.write(time.strftime("%Y-%m-%d %H:%M %Z") + "\n")
    log("done")

if __name__ == "__main__":
    main()
