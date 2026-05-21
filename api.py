import base64
import http.server
import json
import mimetypes
import pathlib
import threading
import urllib.parse
from datetime import datetime

from config import load_config, save_config
from network import check_internet, get_local_ip
from workspace import (
    scan_workspaces, list_tmux_sessions,
    session_name, start_session, kill_session, short_path,
)

STATIC_DIR = pathlib.Path(__file__).parent / "static"

_ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="192" height="192" viewBox="0 0 192 192">
  <rect width="192" height="192" rx="42" fill="#1a1a2e"/>
  <text x="96" y="130" font-size="110" text-anchor="middle" font-family="system-ui">⚡</text>
</svg>"""
_ICON_B64 = base64.b64encode(_ICON_SVG.encode()).decode()
_ICON_DATA = f"data:image/svg+xml;base64,{_ICON_B64}"

_lock = threading.Lock()


def _manifest(icon_url):
    return json.dumps({
        "name": "Claude Launcher",
        "short_name": "Claude",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0d1117",
        "theme_color": "#0d1117",
        "icons": [{"src": icon_url, "sizes": "192x192", "type": "image/svg+xml"}]
    })


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            self._serve_static("index.html")
        elif path == "/manifest.json":
            self._send(200, "application/json", _manifest(_ICON_DATA).encode())
        elif path == "/icon.png":
            self._send(200, "image/svg+xml", _ICON_SVG.encode())
        elif path == "/api/workspaces":
            include_all = query.get("all", ["0"])[0] == "1"
            self._api_workspaces(include_all)
        elif path == "/api/health":
            self._api_health()
        else:
            fname = path.lstrip("/")
            static_file = STATIC_DIR / fname
            if static_file.exists() and static_file.is_file():
                self._serve_static(fname)
            else:
                self._send(404, "text/plain", b"Not found")

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        if path == "/api/start":
            self._api_start(body)
        elif path == "/api/stop":
            self._api_stop(body)
        elif path == "/api/config/toggle":
            self._api_config_toggle(body)
        elif path == "/api/config":
            self._api_config_update(body)
        else:
            self._send(404, "text/plain", b"Not found")

    def _serve_static(self, filename):
        filepath = STATIC_DIR / filename
        try:
            content = filepath.read_bytes()
            mime, _ = mimetypes.guess_type(filename)
            if filename.endswith(".js"):
                mime = "application/javascript; charset=utf-8"
            elif filename.endswith(".css"):
                mime = "text/css; charset=utf-8"
            elif filename.endswith(".html"):
                mime = "text/html; charset=utf-8"
            self._send(200, mime or "application/octet-stream", content)
        except FileNotFoundError:
            self._send(404, "text/plain", b"Not found")

    def _api_health(self):
        data = json.dumps({"ok": True, "internet": check_internet()}).encode()
        self._send(200, "application/json", data)

    def _api_workspaces(self, include_all=False):
        with _lock:
            cfg = load_config()
        workspaces = scan_workspaces(cfg, include_hidden=include_all)
        sessions = list_tmux_sessions()
        ip = get_local_ip()
        result = []
        for w in workspaces:
            result.append({
                "name": w["name"],
                "path": w["path"],
                "short_path": short_path(w["path"]),
                "pinned": w["name"] in cfg.get("pinned", []),
                "running": session_name(w["name"]) in sessions,
                "is_hidden": w.get("is_hidden", False),
            })
        data = json.dumps({
            "workspaces": result,
            "ip": ip,
            "port": cfg.get("port", 8765),
            "config": cfg,
        }).encode()
        self._send(200, "application/json", data)

    def _api_start(self, body):
        name = body.get("name")
        force_new = body.get("force_new", False)
        with _lock:
            cfg = load_config()
        workspaces = scan_workspaces(cfg)
        ws = next((w for w in workspaces if w["name"] == name), None)
        if not ws:
            self._send(404, "text/plain", b"workspace not found")
            return
        sessions = list_tmux_sessions()
        sname = session_name(name)
        if sname in sessions and force_new:
            kill_session(name)
        if sname not in sessions or force_new:
            start_session(name, ws["path"])
        self._send(200, "application/json", b'{"ok":true}')

    def _api_stop(self, body):
        name = body.get("name")
        if not name:
            self._send(400, "text/plain", b"missing name")
            return
        kill_session(name)
        self._send(200, "application/json", b'{"ok":true}')

    def _api_config_toggle(self, body):
        key = body.get("key")
        name = body.get("name")
        if key not in ("pinned", "hidden"):
            self._send(400, "text/plain", b"invalid key")
            return
        with _lock:
            cfg = load_config()
            lst = cfg.setdefault(key, [])
            if name in lst:
                lst.remove(name)
            else:
                lst.append(name)
                other = "pinned" if key == "hidden" else "hidden"
                if name in cfg.get(other, []):
                    cfg[other].remove(name)
            save_config(cfg)
        self._send(200, "application/json", b'{"ok":true}')

    def _api_config_update(self, body):
        allowed = {"scan_dir", "require_claude_md"}
        updates = {k: v for k, v in body.items() if k in allowed}
        if not updates:
            self._send(400, "text/plain", b"no valid fields")
            return
        with _lock:
            cfg = load_config()
            cfg.update(updates)
            save_config(cfg)
        self._send(200, "application/json", b'{"ok":true}')

    def _send(self, code, content_type, body):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] {fmt % args}")
