#!/usr/bin/env python3
"""Live check of any Orange County parcel at a point (used by serve.py: /api/check, /api/geocode).

Runs the same checks as build_sites.py on one parcel, straight from the public services:
SCAG zoning (parcel outline, APN, zoning), SCAG existing land use, SCAG housing-element sites,
OC building footprints, OC floodplains, OC fire zones (LRA) and Caltrans HQTA.
Never requests owner names or mailing addresses."""
import glob, json, math, os, sys, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_data import LAYERS, rings_of  # noqa: E402
import build_sites as B  # noqa: E402


TIMEOUT = 20  # seconds per request for live checks

def call(url, params, tries=2):
    """POST an ArcGIS query with a short timeout; logs how long each service took."""
    body = urllib.parse.urlencode(params).encode()
    name = url.split("/rest/services/")[-1][:60]
    last = None
    for i in range(tries):
        t = time.time()
        try:
            req = urllib.request.Request(url, data=body, headers={"User-Agent": "infill-hackathon-prototype/0.2",
                                                                  "Content-Type": "application/x-www-form-urlencoded"})
            # The county's ocgis.com server can be slow: give it longer than the others.
            with urllib.request.urlopen(req, timeout=TIMEOUT * (2.5 if "ocgis.com" in url else 1)) as r:
                d = json.loads(r.read().decode("utf-8"))
            sys.stderr.write(f"  [check] {name}: {time.time() - t:.1f}s\n")
            if isinstance(d, dict) and "error" in d:
                raise RuntimeError(json.dumps(d["error"])[:200])
            return d
        except Exception as e:
            last = e
            sys.stderr.write(f"  [check] {name}: failed after {time.time() - t:.1f}s ({e})\n")
    raise RuntimeError(f"{name}: {last}")

def safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default

def _point_query(url, lng, lat, out_fields, geometry=False):
    return call(url + "/query", {
        "geometry": json.dumps({"x": lng, "y": lat, "spatialReference": {"wkid": 4326}}),
        "geometryType": "esriGeometryPoint", "inSR": 4326, "spatialRel": "esriSpatialRelIntersects",
        "outFields": out_fields, "returnGeometry": str(geometry).lower(), "outSR": 4326,
        "f": "geojson", "geometryPrecision": 6}).get("features", [])

def geocode(q):
    url = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress?" + urllib.parse.urlencode(
        {"address": q, "benchmark": "Public_AR_Current", "format": "json"})
    req = urllib.request.Request(url, headers={"User-Agent": "infill-hackathon-prototype/0.2"})
    with urllib.request.urlopen(req, timeout=30) as r:
        m = json.loads(r.read().decode()).get("result", {}).get("addressMatches", [])
    if not m:
        return None
    c = m[0]["coordinates"]
    return {"lat": c["y"], "lng": c["x"], "matched": m[0].get("matchedAddress"), "source": "US Census Geocoder"}

def check(lat, lng):
    t_start = time.time()
    sys.stderr.write(f"[check] lot at {lat:.6f},{lng:.6f}\n")
    day = time.strftime("%Y-%m-%d")
    S = B.SRC
    fields = "PID24,APN24,CITY,ACRES,SLOPE,ZN24_CITY,ZN24_SCAG,YEAR_ZN"
    z = _point_query(LAYERS["zoning"], lng, lat, fields, geometry=True)
    snapped_m = None
    if not z:
        # Geocoded addresses often land in the street. Look for the nearest parcel within ~50 m.
        for d in (0.00025, 0.0005):
            cand = call(LAYERS["zoning"] + "/query", {
                "geometry": f"{lng - d},{lat - d},{lng + d},{lat + d}", "geometryType": "esriGeometryEnvelope", "inSR": 4326,
                "spatialRel": "esriSpatialRelIntersects", "outFields": fields, "returnGeometry": "true", "outSR": 4326,
                "f": "geojson", "geometryPrecision": 6}).get("features", [])
            cand = [f for f in cand if f.get("geometry") and B.centroid(f["geometry"])]
            if cand:
                kx, ky = 111320 * math.cos(math.radians(lat)), 110540
                dist = lambda f: math.hypot((B.centroid(f["geometry"])[0] - lng) * kx, (B.centroid(f["geometry"])[1] - lat) * ky)
                best = min(cand, key=dist); z = [best]; snapped_m = round(dist(best)); break
    if not z:
        return {"error": "No parcel found at or near that point in SCAG's Orange County zoning layer. Zoom in and click inside the lot."}
    parcel = z[0]; g = parcel["geometry"]; zp = parcel["properties"]
    pid = zp.get("PID24")
    c = B.centroid(g); lng0, lat0 = c
    esri = {"rings": rings_of(g), "spatialReference": {"wkid": 4326}}
    jobs = {
        "lu": lambda: call(LAYERS["landuse"] + "/query", {"where": f"PID24='{pid}'", "outFields": "LU24,YEAR", "returnGeometry": "false", "f": "json"}).get("features", []),
        "he": lambda: call(LAYERS["he_sites"] + "/query", {"where": f"PID24='{pid}'", "outFields": "Low_Income_HE_Capacity,Total_HE_Capacity,YEAR,Jurisdiction", "returnGeometry": "false", "f": "json"}).get("features", []),
        "fps": lambda: call(LAYERS["footprints"] + "/query", {"geometry": json.dumps(esri), "geometryType": "esriGeometryPolygon", "inSR": 4326,
                    "spatialRel": "esriSpatialRelIntersects", "outFields": "Height", "returnGeometry": "true", "outSR": 4326, "f": "geojson", "geometryPrecision": 6}).get("features", []),
        "flood": lambda: _point_query(LAYERS["flood"], lng0, lat0, "FLD_ZONE,SFHA_TF"),
        "fire": lambda: _point_query(LAYERS["fire_lra"], lng0, lat0, "HAZ_CLASS"),
        "hqta": lambda: _point_query(LAYERS["hqta"], lng0, lat0, "hqta_type"),
    }
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {k: ex.submit(safe, fn) for k, fn in jobs.items()}
        R = {k: f.result() for k, f in futs.items()}
    lu = R["lu"][0]["attributes"] if R["lu"] else {}
    he = R["he"][0]["attributes"] if R["he"] else None
    site_m2 = B.area_m2(g)
    checks, assumptions = [], []
    # Still available? building coverage
    fps, fp_note = R["fps"], ""
    if fps is None:
        # Fallback: if this lot is a housing-element site we already downloaded, use its cached footprints.
        for d in sorted(glob.glob(os.path.join(B.RAW, "*"))):
            sites = B.load(os.path.relpath(os.path.join(d, "he_sites.geojson"), B.RAW)) or {}
            hit = next((f for f in sites.get("features", []) if f["properties"].get("PID24") == pid), None)
            fp_file = hit and os.path.join(d, "footprints", f"{hit['properties'].get('OBJECTID')}.json")
            if fp_file and os.path.exists(fp_file):
                fps = json.load(open(fp_file))
                day = (open(os.path.join(d, "FETCHED_AT.txt")).read().strip()[:10] if os.path.exists(os.path.join(d, "FETCHED_AT.txt")) else "date unknown")
                fp_note = f" (live service didn't answer; checked against the copy downloaded {day})"
                break
    b_m2 = sum(B.area_m2(x.get("geometry")) for x in (fps or []) if (cc := B.centroid(x.get("geometry"))) and B.in_geom(cc, g))
    cov = min(b_m2 / site_m2, 1.0) if (site_m2 and fps is not None) else None
    if cov is None:
        checks.append({"group": "Still available?", "test": "Building coverage", "status": "unknown", "detail": "Footprint service didn't answer or lot area unknown", "source": S["footprints"][0], "url": S["footprints"][1]})
    else:
        st = "pass" if cov < B.COVER_OPEN else ("fail" if cov > B.COVER_BUILT else "unknown")
        checks.append({"group": "Still available?", "test": "Building coverage", "status": st, "detail": f"Buildings cover about {cov*100:.0f}% of the lot (estimate)" + fp_note, "source": S["footprints"][0], "url": S["footprints"][1]})
        assumptions.append(f"ASSUMPTION: under {int(B.COVER_OPEN*100)}% coverage = mostly open; over {int(B.COVER_BUILT*100)}% = may be built out")
    # Usable? flood, fire, transit (center of the lot)
    def cached_hits(key, pt):
        """Fallback: the city-wide copy fetch_data.py already downloaded (raw/<city>/<layer>.geojson)."""
        layer = {"flood": "flood", "fire": "fire_lra", "hqta": "hqta"}[key]
        for path in sorted(glob.glob(os.path.join(B.RAW, "*", f"{layer}.geojson"))):
            d = os.path.dirname(path)
            sites = B.load(os.path.relpath(os.path.join(d, "he_sites.geojson"), B.RAW))
            if not sites or not sites.get("features"):
                continue
            # the area fetch_data.py downloaded this layer for: the city's sites plus the same padding
            from fetch_data import bbox as _bbox
            x0, y0, x1, y1 = _bbox(sites["features"])
            if not (x0 <= pt[0] <= x1 and y0 <= pt[1] <= y1):
                continue
            fc = B.load(os.path.relpath(path, B.RAW)) or {"features": []}
            day = (open(os.path.join(d, "FETCHED_AT.txt")).read().strip()[:10] if os.path.exists(os.path.join(d, "FETCHED_AT.txt")) else "date unknown")
            return B.hits(pt, B.index(fc)), day
        return None, None
    def hz(key, test, src, fail_if_hit, hit_detail, miss_detail):
        feats, note = R[key], ""
        if feats is None:
            feats, day = cached_hits(key, (lng0, lat0))
            if feats is None:
                checks.append({"group": "Usable?", "test": test, "status": "unknown", "detail": "Service didn't answer in time and no cached copy covers this lot: try again", "source": S[src][0], "url": S[src][1]}); return
            note = f" (live service didn't answer; checked against the copy downloaded {day})"
        hit = feats if key != "flood" else [x for x in feats if str(x["properties"].get("SFHA_TF")).upper() == "T"]
        st = ("fail" if hit else "pass") if fail_if_hit else ("pass" if hit else "fail")
        checks.append({"group": "Usable?", "test": test, "status": st, "detail": (hit_detail(hit) if hit else miss_detail) + note, "source": S[src][0], "url": S[src][1]})
    zones = lambda hit, f: ", ".join(sorted({str(x["properties"].get(f)) for x in hit}))
    hz("flood", "Flood zone", "flood", True, lambda h: f"Lot center is in a special flood hazard area (zone {zones(h, 'FLD_ZONE')})", "Lot center is not in a mapped special flood hazard area")
    hz("fire", "Fire hazard zone", "fire", True, lambda h: f"Lot center is in a fire hazard severity zone: {zones(h, 'HAZ_CLASS')}", "Not in a mapped local-responsibility fire zone (state-responsibility zones not checked)")
    hz("hqta", "High-quality transit", "hqta", False, lambda h: f"Inside a Caltrans High Quality Transit Area ({zones(h, 'hqta_type')}). Parking minimums may not apply under AB 2097: confirm the site is within 1/2 mile of a major transit stop", "Not inside a Caltrans High Quality Transit Area")
    # Room for lower-income homes? only if the city listed it
    low = int(B.num(he.get("Low_Income_HE_Capacity")) or 0) if he else None
    tot = int(B.num(he.get("Total_HE_Capacity")) or 0) if he else None
    if he:
        checks.append({"group": "Room for lower-income homes?", "test": "City-listed capacity", "status": "pass" if low > 0 else "fail",
                       "detail": f"On the adopted housing-element site list: {low} lower-income homes of {tot} total", "source": S["he"][0], "url": S["he"][1]})
    else:
        checks.append({"group": "Room for lower-income homes?", "test": "City-listed capacity", "status": "unknown",
                       "detail": ("Housing-element service didn't answer: try again" if R["he"] is None else "Not on the city's housing-element site list. Capacity depends on zoning and which law applies"), "source": S["he"][0], "url": S["he"][1]})
    avail = [x["status"] for x in checks if x["group"] == "Still available?"]
    unknowns = sum(1 for x in checks if x["status"] == "unknown")
    apn = B.apn_fmt(zp.get("APN24"))
    acres = round(site_m2 / 4046.86, 2) if site_m2 else B.num(zp.get("ACRES"))
    open_flag = "pass" in avail and "fail" not in avail
    summary = ("Mostly open" if open_flag else ("May already be built out" if "fail" in avail else "Availability unclear")) + \
              (f" · {low} lower-income homes listed" if he else (" · housing-element list not checked" if R["he"] is None else " · not on the housing-element list")) + (f" · zoned {zp.get('ZN24_CITY')}" if zp.get("ZN24_CITY") else "")
    sys.stderr.write(f"[check] done in {time.time() - t_start:.1f}s\n")
    return {"type": "Feature", "geometry": g, "properties": {
        "id": f"CK-{pid}", "kind": "checked", "label": f"APN {apn}" if apn else f"Parcel {pid}", "apn": apn,
        "city": str(zp.get("CITY") or "").title() or None, "acres": acres, "zoning": zp.get("ZN24_CITY"), "zoning_scag": zp.get("ZN24_SCAG"),
        "landuse_code": lu.get("LU24"), "slope": zp.get("SLOPE"), "low_income_capacity": low, "total_capacity": tot,
        "coverage": None if cov is None else round(cov, 3), "checks": checks, "assumptions": assumptions,
        "confidence": "high" if unknowns == 0 else ("medium" if unknowns == 1 else "low"), "summary": summary,
        "flags": {"open": open_flag}, "checked_at": day, "rank": None, "top": False,
        "snapped_m": snapped_m,
        "snap_note": (f"The point fell outside any parcel; this is the nearest parcel (its center is about {snapped_m} m away). Check it's the right lot." if snapped_m is not None else None)}}

if __name__ == "__main__":
    print(json.dumps(check(float(sys.argv[1]), float(sys.argv[2])), indent=1)[:3000])
