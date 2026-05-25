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
    scan_workspaces,
    start_session, kill_session, short_path,
    scan_claude_projects, get_project_sessions, get_session_messages,
    delete_session, delete_project_logs,
    start_session_by_path, _encode_path, _load_session_map,
    _path_base, _decode_project_path, find_session_cwd,
    count_jsonl_lines, read_new_jsonl_messages,
    find_tmux_session_for_project, send_to_tmux_session, wait_for_claude_ready,
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
        elif path == "/api/projects":
            self._api_projects()
        elif path == "/api/projects/sessions":
            self._api_project_sessions(query)
        elif path == "/api/sessions/messages":
            self._api_session_messages(query)
        elif path == "/api/sessions/live":
            self._api_sessions_live(query)
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
        elif path == "/api/sessions/delete":
            self._api_session_delete(body)
        elif path == "/api/projects/delete":
            self._api_project_delete(body)
        elif path == "/api/chat":
            self._api_chat(body)
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
        active_tmux = set(_load_session_map().values())
        ip = get_local_ip()
        result = []
        for w in workspaces:
            base = _path_base(w["path"]) if w.get("path") else None
            result.append({
                "name": w["name"],
                "path": w["path"],
                "short_path": short_path(w["path"]),
                "pinned": w["name"] in cfg.get("pinned", []),
                "running": bool(base and any(
                    s == base or s.startswith(base + '_')
                    for s in active_tmux
                )),
                "is_hidden": w.get("is_hidden", False),
            })
        data = json.dumps({
            "workspaces": result,
            "ip": ip,
            "port": cfg.get("port", 8765),
            "config": cfg,
        }).encode()
        self._send(200, "application/json", data)

    def _api_projects(self):
        with _lock:
            cfg = load_config()
        pinned_set = set(cfg.get('pinned', []))
        projects = scan_claude_projects()
        active_tmux = set(_load_session_map().values())
        now = datetime.now().timestamp()
        result = []
        for p in projects:
            path_base = _path_base(p['path']) if p['path'] else None
            running = bool(path_base and any(
                s == path_base or s.startswith(path_base + '_')
                for s in active_tmux
            ))
            age_days = (now - p['last_mtime']) / 86400
            result.append({
                'encoded': p['encoded'],
                'path': p['path'],
                'display_name': p['display_name'],
                'session_count': p['session_count'],
                'last_mtime': p['last_mtime'],
                'recent': age_days < 7,
                'running': running,
                'pinned': p['display_name'] in pinned_set,
            })
        self._send(200, "application/json", json.dumps({'projects': result}).encode())

    def _api_project_sessions(self, query):
        encoded = query.get('encoded', [''])[0]
        if not encoded:
            self._send(400, "text/plain", b"missing encoded")
            return
        sessions = get_project_sessions(encoded)
        sess_map = _load_session_map()
        active_tmux = set(sess_map.values())
        from datetime import datetime
        now = datetime.now().timestamp()
        for s in sessions:
            name = sess_map.get(s['id'])
            s['running'] = bool(name and name in active_tmux)
            s['age_days'] = (now - s['mtime']) / 86400
        self._send(200, "application/json", json.dumps({'sessions': sessions}).encode())

    def _api_session_messages(self, query):
        encoded = query.get('encoded', [''])[0]
        sid = query.get('id', [''])[0]
        if not encoded or not sid:
            self._send(400, "text/plain", b"missing encoded or id")
            return
        messages = get_session_messages(encoded, sid)
        line_count = count_jsonl_lines(encoded, sid)
        sess_map = _load_session_map()
        tmux_name = sess_map.get(sid)
        running = bool(tmux_name and tmux_name in set(sess_map.values()))
        self._send(200, "application/json", json.dumps({
            'messages': messages,
            'line_count': line_count,
            'running': running,
        }).encode())

    def _api_sessions_live(self, query):
        encoded = query.get('encoded', [''])[0]
        sid = query.get('id', [''])[0]
        from_line = int(query.get('from', ['0'])[0])
        if not encoded or not sid:
            self._send(400, "text/plain", b"missing encoded or id")
            return
        messages, line_count = read_new_jsonl_messages(encoded, sid, from_line)
        self._send(200, "application/json", json.dumps({'messages': messages, 'line_count': line_count}).encode())

    def _api_session_delete(self, body):
        encoded = body.get("encoded", "")
        session_id = body.get("session_id", "")
        if not encoded or not session_id:
            self._send(400, "text/plain", b"missing encoded or session_id")
            return
        ok = delete_session(encoded, session_id)
        self._send(200, "application/json", json.dumps({"ok": ok}).encode())

    def _api_project_delete(self, body):
        encoded = body.get("encoded", "")
        if not encoded:
            self._send(400, "text/plain", b"missing encoded")
            return
        sess_map = _load_session_map()
        active = set(sess_map.values())
        project_sessions = get_project_sessions(encoded)
        if any(sess_map.get(s["id"]) in active for s in project_sessions):
            self._send(409, "application/json", json.dumps({
                "ok": False,
                "error": "project_running",
            }).encode())
            return
        ok = delete_project_logs(encoded)
        self._send(200, "application/json", json.dumps({"ok": ok}).encode())

    def _api_start(self, body):
        # Path-based start (global tab)
        if 'path' in body:
            path = body['path']
            session_id = body.get('session_id')
            force_new = body.get('force_new', False)
            if not force_new:
                existing = find_tmux_session_for_project(_encode_path(path), session_id)
                if existing:
                    self._send(200, "application/json", b'{"ok":true}')
                    return
            else:
                kill_session(path)
            start_session_by_path(path, session_id)
            self._send(200, "application/json", b'{"ok":true}')
            return
        # Name-based start (favorites tab)
        name = body.get("name")
        force_new = body.get("force_new", False)
        with _lock:
            cfg = load_config()
        workspaces = scan_workspaces(cfg)
        ws = next((w for w in workspaces if w["name"] == name), None)
        if not ws:
            self._send(404, "text/plain", b"workspace not found")
            return
        sessions = set(_load_session_map().values())
        base = _path_base(ws["path"])
        ws_running = any(s == base or s.startswith(base + '_') for s in sessions)
        if not ws_running or force_new:
            if force_new and ws_running:
                kill_session(ws["path"])
            start_session(name, ws["path"])
        self._send(200, "application/json", b'{"ok":true}')

    def _api_stop(self, body):
        name = body.get("name")
        if not name:
            self._send(400, "text/plain", b"missing name")
            return
        with _lock:
            cfg = load_config()
        workspaces = scan_workspaces(cfg, include_hidden=True)
        ws = next((w for w in workspaces if w["name"] == name), None)
        if ws:
            kill_session(ws["path"])
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

    def _api_chat(self, body):
        encoded = body.get('encoded', '')
        session_id = body.get('session_id', '')
        message = body.get('message', '').strip()
        if not message:
            self._send(400, 'text/plain', b'missing message')
            return

        tmux_name = find_tmux_session_for_project(encoded, session_id)
        if not tmux_name:
            path = find_session_cwd(encoded, session_id)
            lines_before = count_jsonl_lines(encoded, session_id)
            tmux_name = start_session_by_path(path, session_id)
            if not wait_for_claude_ready(encoded, session_id, lines_before):
                self._send(500, 'application/json',
                           json.dumps({'error': 'session_start_timeout'}).encode())
                return

        ok = send_to_tmux_session(tmux_name, message)
        if ok:
            self._send(200, 'application/json',
                       json.dumps({'ok': True, 'session': tmux_name}).encode())
        else:
            self._send(500, 'application/json',
                       json.dumps({'error': 'send_failed'}).encode())

    def _send(self, code, content_type, body):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] {fmt % args}")
