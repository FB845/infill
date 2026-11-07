#!/usr/bin/env python3
"""Local server for Infill: serves the map and two small APIs.

  GET  /api/health      -> {"ok": true, "claude": true|false}
  POST /api/callsheet   -> Claude turns one site's checks into a call sheet (JSON)
  GET  /api/pipeline    -> the team's rail + site-visit log (pipeline.json)
  PUT  /api/pipeline    -> save it

Python 3.8+ standard library only. The API key is read from the environment
or a local .env file (git-ignored). It is never sent to the browser.

Usage:  python3 scripts/serve.py        then open http://localhost:8000
"""
import http.server, json, os, sys, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPELINE = os.path.join(ROOT, "pipeline.json")
PORT = int(os.environ.get("PORT", "8000"))

def load_env():
    p = os.path.join(ROOT, ".env")
    if os.path.exists(p):
        for line in open(p):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
load_env()
KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")

SYSTEM = """You prepare call sheets for a one-person acquisitions lead at a small affordable-housing nonprofit in Orange County, California.
You get ONE candidate site as JSON. Every fact you may use is in that JSON.
Rules:
- Use only facts in the JSON. Never invent an address, owner, price, statute section, fee, deadline, phone number, person or zoning meaning.
- If a check is "unknown", say it is unknown and what would settle it.
- Zoning codes and land-use codes: repeat them as given; do not interpret them unless the JSON explains them.
- No personal information. Do not name or guess an owner.
- This is screening, not a zoning, legal or financial determination. Say "confirm with the city" where it matters.
- The email is a DRAFT for a human to edit and send. Address it to "City of {city} housing / planning staff". Use [brackets] for anything the user must fill in.
Return ONLY a JSON object with these keys:
{"headline": one sentence,
 "known": [up to 5 short bullets of what the data shows, each ending with its source name in parentheses],
 "unknown": [up to 5 short bullets of what is still unknown],
 "ask_city": [3-5 questions for city housing or planning staff],
 "ask_on_site": [3-5 things to look for or measure on a site visit or existing-conditions survey],
 "email_subject": string,
 "email_body": string (under 150 words)}"""

def claude(site):
    body = {"model": MODEL, "max_tokens": 1400, "system": SYSTEM,
            "messages": [{"role": "user", "content": "Site JSON:\n" + json.dumps(site, indent=1)}]}
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(),
                                 headers={"x-api-key": KEY, "anthropic-version": "2023-06-01",
                                          "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        d = json.loads(r.read().decode())
    text = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    out = json.loads(text[text.find("{"): text.rfind("}") + 1])
    out["model"] = d.get("model", MODEL)
    return out

class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=ROOT, **k)

    def send_json(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        if self.path == "/api/health":
            return self.send_json(200, {"ok": True, "claude": bool(KEY), "model": MODEL if KEY else None})
        if self.path == "/api/pipeline":
            data = json.load(open(PIPELINE)) if os.path.exists(PIPELINE) else {}
            return self.send_json(200, data)
        if self.path.startswith("/raw/") or self.path.startswith("/.env") or self.path.startswith("/.git"):
            return self.send_json(404, {"error": "not served"})
        return super().do_GET()

    def do_PUT(self):
        if self.path != "/api/pipeline":
            return self.send_json(404, {"error": "unknown"})
        data = self.body()
        tmp = PIPELINE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=1)
        os.replace(tmp, PIPELINE)
        return self.send_json(200, {"ok": True})

    def do_POST(self):
        if self.path != "/api/callsheet":
            return self.send_json(404, {"error": "unknown"})
        if not KEY:
            return self.send_json(503, {"error": "No ANTHROPIC_API_KEY set. Showing the plain template instead."})
        try:
            return self.send_json(200, claude(self.body().get("site", {})))
        except urllib.error.HTTPError as e:
            return self.send_json(502, {"error": f"Claude API {e.code}: {e.read().decode()[:300]}"})
        except Exception as e:
            return self.send_json(502, {"error": f"Call sheet failed: {e}"})

    def log_message(self, fmt, *a):
        if "/api/" in (a[0] if a else ""):
            sys.stderr.write("%s\n" % (fmt % a))

if __name__ == "__main__":
    print(f"Infill on http://localhost:{PORT}  (Claude call sheets: {'on, model ' + MODEL if KEY else 'off, no ANTHROPIC_API_KEY'})")
    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
