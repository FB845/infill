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
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")

SYSTEM = """You prepare call sheets for a one-person acquisitions lead at a small affordable-housing nonprofit in Orange County, California.
You get ONE candidate site as JSON. Every fact you may use is in that JSON.
Rules:
- Use only facts in the JSON. Never invent an address, owner, price, statute section, fee, deadline, phone number, person or zoning meaning.
- If a check is "unknown", say it is unknown and what would settle it.
- Zoning codes and land-use codes: repeat them as given; do not interpret them unless the JSON explains them.
- No personal information. Do not name or guess an owner.
- This is screening, not a zoning, legal or financial determination. Say "confirm with the city" where it matters.
- The email is a DRAFT for a human to edit and send. Address it to "City of {city} housing / planning staff". Use [brackets] for anything the user must fill in.
Always return the call sheet by calling the call_sheet tool exactly once. Do not answer in plain text."""

CALL_SHEET_TOOL = {
    "name": "call_sheet",
    "description": "Return the call sheet for this site.",
    "input_schema": {
        "type": "object",
        "properties": {
            "headline": {"type": "string", "description": "One sentence."},
            "known": {"type": "array", "items": {"type": "string"}, "description": "Up to 5 bullets of what the data shows, each ending with its source name in parentheses."},
            "unknown": {"type": "array", "items": {"type": "string"}, "description": "Up to 5 bullets of what is still unknown and what would settle it."},
            "ask_city": {"type": "array", "items": {"type": "string"}, "description": "3-5 questions for city housing or planning staff."},
            "ask_on_site": {"type": "array", "items": {"type": "string"}, "description": "3-5 things to look for or measure on a site visit or existing-conditions survey."},
            "email_subject": {"type": "string"},
            "email_body": {"type": "string", "description": "Under 150 words. A draft for a human to edit and send."},
        },
        "required": ["headline", "known", "unknown", "ask_city", "ask_on_site", "email_subject", "email_body"],
    },
}

def claude(site):
    body = {"model": MODEL, "max_tokens": 2000, "system": SYSTEM,
            "tools": [CALL_SHEET_TOOL], "tool_choice": {"type": "auto"},
            "messages": [{"role": "user", "content": "Site JSON:\n" + json.dumps(site, indent=1)}]}
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(),
                                 headers={"x-api-key": KEY, "anthropic-version": "2023-06-01",
                                          "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read().decode()
    try:
        d = json.loads(raw)
    except ValueError:
        sys.stderr.write(f"[callsheet] non-JSON response: {raw[:500]}\n")
        raise RuntimeError("Claude API returned a non-JSON response (see server log)")
    blocks = d.get("content", [])
    tool = next((b for b in blocks if b.get("type") == "tool_use" and b.get("name") == "call_sheet"), None)
    if tool and isinstance(tool.get("input"), dict):
        out = tool["input"]
    else:
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
        i, j = text.find("{"), text.rfind("}")
        if i < 0 or j < i:
            sys.stderr.write(f"[callsheet] no tool call or JSON. stop_reason={d.get('stop_reason')} blocks={[b.get('type') for b in blocks]} text={text[:400]!r}\n")
            raise RuntimeError(f"Claude replied without a call sheet (stop_reason {d.get('stop_reason')}; see server log)")
        out = json.loads(text[i:j + 1])
    for k in ("known", "unknown", "ask_city", "ask_on_site"):
        if isinstance(out.get(k), str):
            out[k] = [out[k]]
    out["model"] = d.get("model", MODEL)
    return out

def pick_model():
    global MODEL
    req = urllib.request.Request("https://api.anthropic.com/v1/models?limit=50",
                                 headers={"x-api-key": KEY, "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=30) as r:
        ids = [m["id"] for m in json.loads(r.read().decode()).get("data", [])]
    MODEL = next((i for i in ids if "sonnet" in i), ids[0] if ids else MODEL)
    sys.stderr.write(f"switched to model {MODEL}\n")

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
        site = self.body().get("site", {})
        try:
            try:
                return self.send_json(200, claude(site))
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    raise
                pick_model()  # model name not available on this key: choose one that is, retry once
                return self.send_json(200, claude(site))
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
