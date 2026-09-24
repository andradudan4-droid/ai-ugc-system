#!/usr/bin/env python3
"""CRM control room. Zero dependencies — python3 crm/serve.py, then open the URL.

Reads  shared/data/dashboard.json  (regenerate: python3 tools/build_dashboard.py)
Writes shared/data/crm.json        (this file's own state — stages, contacts, events)

Never sends email. Never spends money. It records that a human did.
"""

import json, pathlib, http.server, socketserver, datetime as dt, urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "shared" / "data"
DASH = DATA / "dashboard.json"
CRM = DATA / "crm.json"
PORT = 4173

EMPTY = {"stages": {}, "contacts": {}, "events": [], "notes": {}}


def load_crm() -> dict:
    if not CRM.exists():
        return dict(EMPTY)
    try:
        d = json.loads(CRM.read_text())
    except Exception:
        # fail closed and loudly rather than silently resetting the operator's data
        raise SystemExit(f"ERROR: {CRM} is unreadable. Fix or move it; refusing to overwrite.")
    for k, v in EMPTY.items():
        d.setdefault(k, v if not isinstance(v, (dict, list)) else type(v)())
    return d


def save_crm(d: dict) -> None:
    CRM.write_text(json.dumps(d, indent=2))


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


class H(http.server.SimpleHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass  # quiet

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/index.html"):
            p = ROOT / "crm" / "index.html"
            return self._send(200, p.read_bytes(), "text/html; charset=utf-8")
        if path == "/api/data":
            if not DASH.exists():
                return self._send(503, json.dumps({
                    "error": "dashboard.json missing",
                    "fix": "python3 tools/build_dashboard.py"}))
            dash = json.loads(DASH.read_text())
            crm = load_crm()
            # operator stage overrides win over the derived stage
            for b in dash.get("brands", []):
                if b["slug"] in crm["stages"]:
                    b["stage"] = crm["stages"][b["slug"]]
                    b["stage_manual"] = True
            dash["crm"] = crm
            return self._send(200, json.dumps(dash))
        return self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._send(400, json.dumps({"error": "bad json"}))
        crm = load_crm()

        if path == "/api/stage":
            slug, stage = body.get("slug"), body.get("stage")
            if not slug or not stage:
                return self._send(400, json.dumps({"error": "slug and stage required"}))
            crm["stages"][slug] = stage
            crm["events"].append({"ts": now(), "slug": slug, "type": "stage", "detail": stage})

        elif path == "/api/contact":
            slug = body.get("slug")
            email = (body.get("email") or "").strip()
            if not slug or not email:
                return self._send(400, json.dumps({"error": "slug and email required"}))
            crm["contacts"][slug] = {
                "email": email, "role": body.get("role", ""),
                "source": body.get("source", ""), "added": now(),
            }
            crm["events"].append({"ts": now(), "slug": slug, "type": "contact",
                                  "detail": f"{email} — source: {body.get('source','unrecorded')}"})

        elif path == "/api/event":
            slug, kind = body.get("slug"), body.get("kind")
            if kind not in ("sent", "replied", "note"):
                return self._send(400, json.dumps({"error": "kind must be sent|replied|note"}))
            crm["events"].append({"ts": now(), "slug": slug, "type": kind,
                                  "detail": body.get("detail", "")})
            if kind == "sent":
                crm["stages"][slug] = "contacted"
            if kind == "replied":
                crm["stages"][slug] = "replied"
        else:
            return self._send(404, json.dumps({"error": "not found"}))

        save_crm(crm)
        return self._send(200, json.dumps({"ok": True}))


if __name__ == "__main__":
    if not DASH.exists():
        print("dashboard.json missing — run: python3 tools/build_dashboard.py")
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", PORT), H) as httpd:
        print(f"\n  CRM running →  http://127.0.0.1:{PORT}\n  ctrl-c to stop\n")
        httpd.serve_forever()
