#!/usr/bin/env python3
"""Turn the cached raw/ data into data/sites.js for the map.

Every site gets the same checks, each marked pass / fail / unknown, with a
source and the date the data was pulled. Thresholds that are our own
judgment calls are labelled ASSUMPTION here, in the UI and in the README.

Usage: python3 scripts/build_sites.py [--city "Anaheim"]
"""
import argparse, json, math, os, re, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "raw")

# ---- ASSUMPTIONS (our judgment calls, not rules from any law) ----
COVER_OPEN = 0.15      # ASSUMPTION: buildings cover <15% of the site -> "mostly open"
COVER_BUILT = 0.40     # ASSUMPTION: buildings cover >40% of the site -> "may already be built out"
IMPR_UNDERUSED = 0.5   # ASSUMPTION: building value < 50% of land value -> "underused"
IMPR_BUILT = 1.5       # ASSUMPTION: building value > 150% of land value -> "may have been redeveloped"
TOP_N = 10

SRC = {
    "he": ("SCAG Housing Element Sites (HousingElementSite_poly_scag)",
           "https://maps.scag.ca.gov/scaggis/rest/services/LDX/HousingElementSite_poly_scag/MapServer"),
    "zoning": ("SCAG Zoning_poly_OR", "https://maps.scag.ca.gov/scaggis/rest/services/LDX/Zoning_poly_OR/MapServer"),
    "landuse": ("SCAG Existinglanduse_poly_OR", "https://maps.scag.ca.gov/scaggis/rest/services/LDX/Existinglanduse_poly_OR/MapServer"),
    "footprints": ("OC Building Footprints", "https://www.ocgis.com/arcpub/rest/services/Map_Layers/Building_Footprints/MapServer/0"),
    "sa": ("City of Santa Ana Assessor Parcels", "https://gis.santa-ana.org/server/rest/services/Public/GIS_AssessorParcels/MapServer/0"),
    "flood": ("OC Floodplains (FEMA zones, county copy)", "https://www.ocgis.com/arcpub/rest/services/Map_Layers/Floodplains/MapServer/0"),
    "fire": ("OC Fire Hazard Severity Zones (LRA)", "https://www.ocgis.com/arcpub/rest/services/Map_Layers/Fire_Hazard_Severity_Zones_LRA/MapServer/0"),
    "hqta": ("Caltrans High Quality Transit Areas", "https://caltrans-gis.dot.ca.gov/arcgis/rest/services/CHrailroad/CA_HQ_Transit_Areas/FeatureServer/0"),
    "ab2097": ("HCD Technical Advisory: AB 2097", "https://www.hcd.ca.gov/sites/default/files/docs/policy-and-research/ab-2097-ta.pdf"),
}

def load(path, default=None):
    p = os.path.join(RAW, path)
    if not os.path.exists(p):
        return default
    with open(p) as f:
        return json.load(f)

# ---------- geometry helpers (no dependencies) ----------
def polys(g):
    if not g: return []
    if g["type"] == "Polygon": return [g["coordinates"]]
    if g["type"] == "MultiPolygon": return g["coordinates"]
    return []

def ring_area_m2(r, lat0):
    kx, ky = 111320 * math.cos(math.radians(lat0)), 110540
    s = 0.0
    for (x1, y1), (x2, y2) in zip(r, r[1:]):
        s += (x1 * kx) * (y2 * ky) - (x2 * kx) * (y1 * ky)
    return abs(s) / 2

def area_m2(g):
    ps = polys(g)
    if not ps: return 0.0
    lat0 = ps[0][0][0][1]
    return sum(ring_area_m2(p[0], lat0) - sum(ring_area_m2(h, lat0) for h in p[1:]) for p in ps)

def centroid(g):
    pts = [pt for p in polys(g) for pt in p[0]]
    if not pts: return None
    return (sum(x for x, _ in pts) / len(pts), sum(y for _, y in pts) / len(pts))

def in_ring(x, y, r):
    inside = False
    for (x1, y1), (x2, y2) in zip(r, r[1:]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-15) + x1:
            inside = not inside
    return inside

def in_geom(pt, g):
    x, y = pt
    return any(in_ring(x, y, p[0]) and not any(in_ring(x, y, h) for h in p[1:]) for p in polys(g))

def index(fc):
    out = []
    for f in (fc or {}).get("features", []):
        ps = polys(f.get("geometry"))
        if not ps: continue
        xs = [x for p in ps for x, _ in p[0]]; ys = [y for p in ps for _, y in p[0]]
        out.append(((min(xs), min(ys), max(xs), max(ys)), f))
    return out

def hits(pt, idx):
    x, y = pt
    return [f for (b, f) in idx if b[0] <= x <= b[2] and b[1] <= y <= b[3] and in_geom(pt, f["geometry"])]

def apn_fmt(a):
    d = re.sub(r"\D", "", str(a or ""))
    return f"{d[:3]}-{d[3:6]}-{d[6:]}" if len(d) == 8 else (d or None)

def num(v):
    try: return float(v)
    except (TypeError, ValueError): return None

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--city", default="Anaheim"); a = ap.parse_args()
    slug = a.city.lower().replace(" ", "-")
    sites = load(f"{slug}/he_sites.geojson")
    if not sites or not sites.get("features"):
        sys.exit(f"No raw/{slug}/he_sites.geojson yet. Run scripts/fetch_data.py first.")
    pulled = (open(os.path.join(RAW, slug, "FETCHED_AT.txt")).read().strip()
              if os.path.exists(os.path.join(RAW, slug, "FETCHED_AT.txt")) else "date unknown")
    day = pulled[:10]

    zoning = {r["PID24"]: r for r in load(f"{slug}/zoning.json", [])}
    landuse = {r["PID24"]: r for r in load(f"{slug}/landuse.json", [])}
    flood_i, fire_i, hqta_i = (index(load(f"{slug}/{k}.geojson")) for k in ("flood", "fire_lra", "hqta"))
    have = {k: os.path.exists(os.path.join(RAW, slug, f"{k}.geojson")) for k in ("flood", "fire_lra", "hqta")}
    sa = {}
    for r in load(f"{slug}/sa_parcels.json", []) or []:
        k = re.sub(r"\D", "", str(r.get("AssessmentNo") or ""))
        if not k: continue
        cur = sa.setdefault(k, {"LandVal": 0.0, "ImprovedVal": 0.0, "n": 0})
        cur["LandVal"] += num(r.get("LandVal")) or 0; cur["ImprovedVal"] += num(r.get("ImprovedVal")) or 0; cur["n"] += 1

    out = []
    for i, f in enumerate(sites["features"]):
        p, g = f["properties"], f.get("geometry")
        c = centroid(g)
        if not c: continue
        oid = p.get("OBJECTID", i)
        apn = apn_fmt(p.get("Assessor_Parcel_Number") or p.get("APN24"))
        z, lu = zoning.get(p.get("PID24"), {}), landuse.get(p.get("PID24"), {})
        site_m2 = area_m2(g)
        acres = site_m2 / 4046.86 if site_m2 else num(z.get("ACRES"))
        low = int(num(p.get("Low_Income_HE_Capacity")) or 0)
        tot = int(num(p.get("Total_HE_Capacity")) or 0)
        checks, assumptions = [], []

        # A. Still available? building coverage
        fps = load(f"{slug}/footprints/{oid}.json")
        if fps is None or not site_m2:
            cov = None
            checks.append({"group": "Still available?", "test": "Building coverage", "status": "unknown",
                           "detail": "Footprints not fetched for this site", "source": SRC["footprints"][0], "url": SRC["footprints"][1]})
        else:
            b_m2 = sum(area_m2(x.get("geometry")) for x in fps if (cc := centroid(x.get("geometry"))) and in_geom(cc, g))
            cov = min(b_m2 / site_m2, 1.0)
            st = "pass" if cov < COVER_OPEN else ("fail" if cov > COVER_BUILT else "unknown")
            checks.append({"group": "Still available?", "test": "Building coverage",
                           "status": st, "detail": f"Buildings cover about {cov*100:.0f}% of the site (estimate)",
                           "source": SRC["footprints"][0], "url": SRC["footprints"][1]})
            assumptions.append(f"ASSUMPTION: under {int(COVER_OPEN*100)}% coverage = mostly open; over {int(COVER_BUILT*100)}% = may be built out")

        # B. Still available? building vs land value (Santa Ana only)
        ratio = None
        if slug == "santa-ana":
            v = sa.get(re.sub(r"\D", "", apn or ""))
            if v and v["LandVal"] > 0:
                ratio = v["ImprovedVal"] / v["LandVal"]
                st = "pass" if ratio < IMPR_UNDERUSED else ("fail" if ratio > IMPR_BUILT else "unknown")
                checks.append({"group": "Still available?", "test": "Building value vs. land value", "status": st,
                               "detail": f"Building value is {ratio*100:.0f}% of land value (assessor roll as published by the city)",
                               "source": SRC["sa"][0], "url": SRC["sa"][1]})
                assumptions.append(f"ASSUMPTION: building value under {int(IMPR_UNDERUSED*100)}% of land value = underused; over {int(IMPR_BUILT*100)}% = may have been redeveloped")
            else:
                checks.append({"group": "Still available?", "test": "Building value vs. land value", "status": "unknown",
                               "detail": "No matching assessor record found for this APN", "source": SRC["sa"][0], "url": SRC["sa"][1]})

        # C. Usable? flood
        if have["flood"]:
            fh = hits(c, flood_i)
            sfha = [x for x in fh if str(x["properties"].get("SFHA_TF")).upper() == "T"]
            if sfha:
                zn = sorted({str(x["properties"].get("FLD_ZONE")) for x in sfha})
                checks.append({"group": "Usable?", "test": "Flood zone", "status": "fail",
                               "detail": f"Site center is in a special flood hazard area (zone {', '.join(zn)})",
                               "source": SRC["flood"][0], "url": SRC["flood"][1]})
            else:
                checks.append({"group": "Usable?", "test": "Flood zone", "status": "pass",
                               "detail": "Site center is not in a mapped special flood hazard area",
                               "source": SRC["flood"][0], "url": SRC["flood"][1]})
        else:
            checks.append({"group": "Usable?", "test": "Flood zone", "status": "unknown", "detail": "Flood layer not fetched",
                           "source": SRC["flood"][0], "url": SRC["flood"][1]})

        # D. Usable? fire
        if have["fire_lra"]:
            fz = hits(c, fire_i)
            if fz:
                cl = sorted({str(x["properties"].get("HAZ_CLASS")) for x in fz})
                checks.append({"group": "Usable?", "test": "Fire hazard zone", "status": "fail",
                               "detail": f"Site center is in a fire hazard severity zone: {', '.join(cl)}",
                               "source": SRC["fire"][0], "url": SRC["fire"][1]})
            else:
                checks.append({"group": "Usable?", "test": "Fire hazard zone", "status": "pass",
                               "detail": "Not in a mapped local-responsibility fire zone (state-responsibility zones not checked)",
                               "source": SRC["fire"][0], "url": SRC["fire"][1]})
        else:
            checks.append({"group": "Usable?", "test": "Fire hazard zone", "status": "unknown", "detail": "Fire layer not fetched",
                           "source": SRC["fire"][0], "url": SRC["fire"][1]})

        # E. Transit
        if have["hqta"]:
            tz = hits(c, hqta_i)
            if tz:
                t = sorted({str(x["properties"].get("hqta_type")) for x in tz})
                checks.append({"group": "Usable?", "test": "High-quality transit", "status": "pass",
                               "detail": f"Inside a Caltrans High Quality Transit Area ({', '.join(t)}). Parking minimums may not apply under AB 2097: confirm the site is within 1/2 mile of a major transit stop",
                               "source": SRC["hqta"][0], "url": SRC["hqta"][1]})
            else:
                checks.append({"group": "Usable?", "test": "High-quality transit", "status": "fail",
                               "detail": "Not inside a Caltrans High Quality Transit Area",
                               "source": SRC["hqta"][0], "url": SRC["hqta"][1]})
        else:
            checks.append({"group": "Usable?", "test": "High-quality transit", "status": "unknown", "detail": "Transit layer not fetched",
                           "source": SRC["hqta"][0], "url": SRC["hqta"][1]})

        # F. Capacity the city itself listed
        checks.append({"group": "Room for lower-income homes?", "test": "City-listed capacity",
                       "status": "pass" if low > 0 else "fail",
                       "detail": f"{low} lower-income homes of {tot} total in the adopted housing element" + (f" ({p.get('YEAR')})" if p.get("YEAR") else ""),
                       "source": SRC["he"][0], "url": SRC["he"][1]})

        st = {x["test"]: x["status"] for x in checks}
        avail = [x["status"] for x in checks if x["group"] == "Still available?"]
        open_flag = "pass" in avail and "fail" not in avail
        unknowns = sum(1 for x in checks if x["status"] == "unknown")
        fails = sum(1 for x in checks if x["status"] == "fail" and x["group"] == "Usable?" and x["test"] != "High-quality transit")
        # ASSUMPTION: ranking weights below are ours, shown in the UI
        score = (4 if low > 0 else 0) + min(low, 100) / 25 \
                + (3 if open_flag else 0) - (2 if "fail" in avail else 0) \
                + (2 if st.get("High-quality transit") == "pass" else 0) - 5 * fails
        confidence = "high" if unknowns == 0 else ("medium" if unknowns == 1 else "low")
        zone = z.get("ZN24_CITY")
        summary = (f"{'Mostly open' if open_flag else ('May already be built out' if 'fail' in avail else 'Availability unclear')}"
                   f" · {low} lower-income homes listed" + (f" · zoned {zone}" if zone else ""))
        out.append({"type": "Feature", "geometry": g, "properties": {
            "id": f"HE-{oid}", "label": f"APN {apn}" if apn else f"Site {oid}", "apn": apn, "city": a.city,
            "acres": round(acres, 2) if acres else None, "zoning": zone, "zoning_scag": z.get("ZN24_SCAG"),
            "landuse_code": lu.get("LU24"), "slope": z.get("SLOPE"),
            "low_income_capacity": low, "total_capacity": tot, "coverage": None if cov is None else round(cov, 3),
            "value_ratio": None if ratio is None else round(ratio, 2),
            "flags": {"open": open_flag, "no_flood": st.get("Flood zone") == "pass",
                      "no_fire": st.get("Fire hazard zone") == "pass", "near_transit": st.get("High-quality transit") == "pass",
                      "low_income": low > 0},
            "checks": checks, "assumptions": sorted(set(assumptions)), "score": round(score, 2),
            "confidence": confidence, "summary": summary}})

    out.sort(key=lambda f: -f["properties"]["score"])
    for r, f in enumerate(out, 1):
        f["properties"]["rank"] = r
        f["properties"]["top"] = r <= TOP_N
    cx = sum(centroid(f["geometry"])[0] for f in out) / len(out); cy = sum(centroid(f["geometry"])[1] for f in out) / len(out)
    meta = {"city": a.city, "center": [cy, cx], "zoom": 13, "pulled": pulled, "built": time.strftime("%Y-%m-%d %H:%M"),
            "count": len(out), "top_n": TOP_N,
            "sources": [{"name": n, "url": u, "checked": day} for n, u in SRC.values()],
            "ranking": "ASSUMPTION (our weights): +4 if the city listed any lower-income capacity, + lower-income capacity / 25 (max +4), +3 mostly open, -2 may be built out, +2 inside a high-quality transit area, -5 per flood or fire fail"}
    js = ("// Generated by scripts/build_sites.py from public data. Do not edit by hand.\n"
          f"window.SITES_META = {json.dumps(meta)};\n"
          f"window.SITES = {json.dumps({'type': 'FeatureCollection', 'features': out}, separators=(',', ':'))};\n")
    with open(os.path.join(ROOT, "data", "sites.js"), "w") as fh:
        fh.write(js)
    print(f"wrote data/sites.js: {len(out)} sites, {len(js)//1024} KB. Top {TOP_N}:")
    for f in out[:TOP_N]:
        q = f["properties"]; print(f"  #{q['rank']:>2} {q['label']:<18} score {q['score']:>5}  {q['summary']}")

if __name__ == "__main__":
    main()
