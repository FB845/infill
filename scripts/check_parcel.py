#!/usr/bin/env python3
"""Live check of any Orange County parcel at a point (used by serve.py: /api/check, /api/geocode).

Runs the same checks as build_sites.py on one parcel, straight from the public services:
SCAG zoning (parcel outline, APN, zoning), SCAG existing land use, SCAG housing-element sites,
OC building footprints, OC floodplains, OC fire zones (LRA) and Caltrans HQTA.
Never requests owner names or mailing addresses."""
import json, os, sys, time, urllib.parse, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_data import LAYERS, call, rings_of  # noqa: E402
import build_sites as B  # noqa: E402

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
    day = time.strftime("%Y-%m-%d")
    S = B.SRC
    z = _point_query(LAYERS["zoning"], lng, lat, "PID24,APN24,CITY,ACRES,SLOPE,ZN24_CITY,ZN24_SCAG,YEAR_ZN", geometry=True)
    if not z:
        return {"error": "No parcel found at that point in SCAG's Orange County zoning layer."}
    parcel = z[0]; g = parcel["geometry"]; zp = parcel["properties"]
    pid = zp.get("PID24")
    lu = call(LAYERS["landuse"] + "/query", {"where": f"PID24='{pid}'", "outFields": "LU24,YEAR", "returnGeometry": "false", "f": "json"}).get("features", [])
    lu = lu[0]["attributes"] if lu else {}
    he = call(LAYERS["he_sites"] + "/query", {"where": f"PID24='{pid}'", "outFields": "Low_Income_HE_Capacity,Total_HE_Capacity,YEAR,Jurisdiction",
                                              "returnGeometry": "false", "f": "json"}).get("features", [])
    he = he[0]["attributes"] if he else None
    c = B.centroid(g); site_m2 = B.area_m2(g)
    checks, assumptions = [], []
    # Still available? building coverage
    esri = {"rings": rings_of(g), "spatialReference": {"wkid": 4326}}
    fps = call(LAYERS["footprints"] + "/query", {"geometry": json.dumps(esri), "geometryType": "esriGeometryPolygon", "inSR": 4326,
               "spatialRel": "esriSpatialRelIntersects", "outFields": "Height", "returnGeometry": "true", "outSR": 4326,
               "f": "geojson", "geometryPrecision": 6}).get("features", [])
    b_m2 = sum(B.area_m2(x.get("geometry")) for x in fps if (cc := B.centroid(x.get("geometry"))) and B.in_geom(cc, g))
    cov = min(b_m2 / site_m2, 1.0) if site_m2 else None
    if cov is None:
        checks.append({"group": "Still available?", "test": "Building coverage", "status": "unknown", "detail": "Lot area unknown", "source": S["footprints"][0], "url": S["footprints"][1]})
    else:
        st = "pass" if cov < B.COVER_OPEN else ("fail" if cov > B.COVER_BUILT else "unknown")
        checks.append({"group": "Still available?", "test": "Building coverage", "status": st, "detail": f"Buildings cover about {cov*100:.0f}% of the lot (estimate)", "source": S["footprints"][0], "url": S["footprints"][1]})
        assumptions.append(f"ASSUMPTION: under {int(B.COVER_OPEN*100)}% coverage = mostly open; over {int(B.COVER_BUILT*100)}% = may be built out")
    # Usable? flood, fire, transit (center of the lot)
    lng0, lat0 = c
    fl = _point_query(LAYERS["flood"], lng0, lat0, "FLD_ZONE,SFHA_TF")
    sfha = [x for x in fl if str(x["properties"].get("SFHA_TF")).upper() == "T"]
    checks.append({"group": "Usable?", "test": "Flood zone", "status": "fail" if sfha else "pass",
                   "detail": (f"Lot center is in a special flood hazard area (zone {', '.join(sorted({str(x['properties'].get('FLD_ZONE')) for x in sfha}))})" if sfha else "Lot center is not in a mapped special flood hazard area"),
                   "source": S["flood"][0], "url": S["flood"][1]})
    fz = _point_query(LAYERS["fire_lra"], lng0, lat0, "HAZ_CLASS")
    checks.append({"group": "Usable?", "test": "Fire hazard zone", "status": "fail" if fz else "pass",
                   "detail": (f"Lot center is in a fire hazard severity zone: {', '.join(sorted({str(x['properties'].get('HAZ_CLASS')) for x in fz}))}" if fz else "Not in a mapped local-responsibility fire zone (state-responsibility zones not checked)"),
                   "source": S["fire"][0], "url": S["fire"][1]})
    hq = _point_query(LAYERS["hqta"], lng0, lat0, "hqta_type")
    checks.append({"group": "Usable?", "test": "High-quality transit", "status": "pass" if hq else "fail",
                   "detail": (f"Inside a Caltrans High Quality Transit Area ({', '.join(sorted({str(x['properties'].get('hqta_type')) for x in hq}))}). Parking minimums may not apply under AB 2097: confirm the site is within 1/2 mile of a major transit stop" if hq else "Not inside a Caltrans High Quality Transit Area"),
                   "source": S["hqta"][0], "url": S["hqta"][1]})
    # Room for lower-income homes? only if the city listed it
    low = int(B.num(he.get("Low_Income_HE_Capacity")) or 0) if he else None
    tot = int(B.num(he.get("Total_HE_Capacity")) or 0) if he else None
    if he:
        checks.append({"group": "Room for lower-income homes?", "test": "City-listed capacity", "status": "pass" if low > 0 else "fail",
                       "detail": f"On the adopted housing-element site list: {low} lower-income homes of {tot} total", "source": S["he"][0], "url": S["he"][1]})
    else:
        checks.append({"group": "Room for lower-income homes?", "test": "City-listed capacity", "status": "unknown",
                       "detail": "Not on the city's housing-element site list. Capacity depends on zoning and which law applies", "source": S["he"][0], "url": S["he"][1]})
    avail = [x["status"] for x in checks if x["group"] == "Still available?"]
    unknowns = sum(1 for x in checks if x["status"] == "unknown")
    apn = B.apn_fmt(zp.get("APN24"))
    acres = round(site_m2 / 4046.86, 2) if site_m2 else B.num(zp.get("ACRES"))
    open_flag = "pass" in avail and "fail" not in avail
    summary = ("Mostly open" if open_flag else ("May already be built out" if "fail" in avail else "Availability unclear")) + \
              (f" · {low} lower-income homes listed" if he else " · not on the housing-element list") + (f" · zoned {zp.get('ZN24_CITY')}" if zp.get("ZN24_CITY") else "")
    return {"type": "Feature", "geometry": g, "properties": {
        "id": f"CK-{pid}", "kind": "checked", "label": f"APN {apn}" if apn else f"Parcel {pid}", "apn": apn,
        "city": str(zp.get("CITY") or "").title() or None, "acres": acres, "zoning": zp.get("ZN24_CITY"), "zoning_scag": zp.get("ZN24_SCAG"),
        "landuse_code": lu.get("LU24"), "slope": zp.get("SLOPE"), "low_income_capacity": low, "total_capacity": tot,
        "coverage": None if cov is None else round(cov, 3), "checks": checks, "assumptions": assumptions,
        "confidence": "high" if unknowns == 0 else ("medium" if unknowns == 1 else "low"), "summary": summary,
        "flags": {"open": open_flag}, "checked_at": day, "rank": None, "top": False}}

if __name__ == "__main__":
    print(json.dumps(check(float(sys.argv[1]), float(sys.argv[2])), indent=1)[:3000])
