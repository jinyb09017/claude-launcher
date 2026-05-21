# Settings Panel + Architecture Refactor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 拆分 server.py 为独立模块 + 静态文件目录，然后新增 Bottom Sheet 设置面板（语言/主题切换、工作空间配置）。

**Architecture:** Python 后端拆为 config / network / workspace / api / server 五个模块；前端 HTML/CSS/JS 提取到 static/ 目录由 Python HTTP server 直接 serve；设置面板为 Bottom Sheet，语言/主题存 localStorage，工作空间配置走现有 API。

**Tech Stack:** Python 3 stdlib (http.server), vanilla JS, CSS custom properties, localStorage

---

## File Map

| 操作 | 文件 |
|------|------|
| 新建 | `config.py` |
| 新建 | `network.py` |
| 新建 | `workspace.py` |
| 新建 | `api.py` |
| 修改 | `server.py` (瘦身到 ~25 行) |
| 新建 | `static/index.html` |
| 新建 | `static/app.css` |
| 新建 | `static/app.js` |
| 新建 | `static/i18n.js` |
| 新建 | `static/settings.js` |

---

### Task 1: 创建 config.py 和 network.py

**Files:**
- Create: `config.py`
- Create: `network.py`

- [ ] **Step 1: 创建 config.py**

```python
import json
import pathlib

CONFIG_PATH = pathlib.Path(__file__).parent / "config.json"


def load_config():
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    cfg["scan_dir"] = str(pathlib.Path(cfg["scan_dir"]).expanduser())
    return cfg


def save_config(cfg):
    save = dict(cfg)
    save["scan_dir"] = cfg["scan_dir"].replace(str(pathlib.Path.home()), "~")
    with open(CONFIG_PATH, "w") as f:
        json.dump(save, f, indent=2, ensure_ascii=False)
```

- [ ] **Step 2: 创建 network.py**

```python
import socket


def check_internet():
    try:
        socket.setdefaulttimeout(2)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
        return True
    except Exception:
        return False


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"
```

- [ ] **Step 3: 验证模块可导入**

```bash
cd /Users/jinyabo/Documents/ai-claude/claude-launcher
python3 -c "from config import load_config; print(load_config()['scan_dir'])"
python3 -c "from network import get_local_ip; print(get_local_ip())"
```

Expected: 打印出 scan_dir 路径和本机 IP，无报错。

- [ ] **Step 4: Commit**

```bash
git add config.py network.py
git commit -m "refactor: extract config and network modules"
```

---

### Task 2: 创建 workspace.py

**Files:**
- Create: `workspace.py`

- [ ] **Step 1: 创建 workspace.py**

```python
import pathlib
import subprocess


def scan_workspaces(cfg, include_hidden=False):
    scan_dir = pathlib.Path(cfg["scan_dir"])
    require_md = cfg.get("require_claude_md", True)
    hidden = set(cfg.get("hidden", []))
    pinned = cfg.get("pinned", [])

    entries = []
    if scan_dir.exists():
        for d in sorted(scan_dir.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            if not include_hidden and d.name in hidden:
                continue
            if require_md and not (d / "CLAUDE.md").exists():
                continue
            mtime = d.stat().st_mtime
            entries.append({
                "name": d.name,
                "path": str(d),
                "mtime": mtime,
                "is_hidden": d.name in hidden,
            })

    entries.sort(key=lambda e: (
        0 if e["name"] in pinned else 1,
        pinned.index(e["name"]) if e["name"] in pinned else -e["mtime"]
    ))
    return entries


def list_tmux_sessions():
    try:
        out = subprocess.check_output(
            ["tmux", "ls", "-F", "#{session_name}"], stderr=subprocess.DEVNULL, text=True
        )
        return set(out.strip().splitlines())
    except subprocess.CalledProcessError:
        return set()


def session_name(dirname):
    return f"claude_{dirname}"


def start_session(dirname, path):
    name = session_name(dirname)
    subprocess.Popen(
        ["tmux", "new-session", "-d", "-s", name, "-c", path, "claude"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )


def kill_session(dirname):
    name = session_name(dirname)
    subprocess.run(["tmux", "kill-session", "-t", name], stderr=subprocess.DEVNULL)


def short_path(full_path):
    p = pathlib.Path(full_path)
    home = pathlib.Path.home()
    try:
        rel = p.relative_to(home)
        parts = rel.parts
        return "~/" + "/".join(parts[-2:]) if len(parts) >= 2 else "~/" + str(rel)
    except ValueError:
        parts = p.parts
        return "/".join(parts[-2:]) if len(parts) >= 2 else full_path
```

- [ ] **Step 2: 验证**

```bash
python3 -c "
from config import load_config
from workspace import scan_workspaces
cfg = load_config()
ws = scan_workspaces(cfg)
print(f'Found {len(ws)} workspaces')
for w in ws[:3]: print(' ', w['name'])
"
```

Expected: 打印工作空间数量和名称，无报错。

- [ ] **Step 3: Commit**

```bash
git add workspace.py
git commit -m "refactor: extract workspace module"
```

---

### Task 3: 创建 api.py

**Files:**
- Create: `api.py`

- [ ] **Step 1: 创建 api.py（第一段：imports + 常量 + 静态服务）**

```python
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
```

- [ ] **Step 2: 追加 Handler 类到 api.py**

```python

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
```

- [ ] **Step 3: 验证 api.py 可导入**

```bash
python3 -c "from api import Handler; print('api.py ok')"
```

Expected: 打印 `api.py ok`，无报错。

- [ ] **Step 4: Commit**

```bash
git add api.py
git commit -m "refactor: extract api handler module"
```

---

### Task 4: 瘦身 server.py

**Files:**
- Modify: `server.py`

- [ ] **Step 1: 用新内容完整替换 server.py**

```python
#!/usr/bin/env python3
"""Claude Workspace Launcher — LAN-accessible PWA to start claude sessions by directory."""

import http.server

from api import Handler
from config import load_config
from network import get_local_ip


if __name__ == "__main__":
    cfg = load_config()
    port = cfg.get("port", 8765)
    ip = get_local_ip()
    print(f"Claude Launcher  http://{ip}:{port}")
    print(f"Local            http://localhost:{port}")
    http.server.HTTPServer(("0.0.0.0", port), Handler).serve_forever()
```

- [ ] **Step 2: 创建 static/ 目录（仅创建占位文件，供后续任务填充）**

```bash
mkdir -p /Users/jinyabo/Documents/ai-claude/claude-launcher/static
touch /Users/jinyabo/Documents/ai-claude/claude-launcher/static/index.html
```

- [ ] **Step 3: 用旧 PWA_HTML 内容填充 static/index.html（临时，后续 Task 6 替换）**

暂时将旧 server.py 中的 HTML 保存到 static/index.html，保持服务可用。内容见 Task 6 Step 1（此处先用旧内容占位，Task 6 会替换）：

```bash
python3 -c "
import sys
sys.path.insert(0, '.')
# 从旧 git 版本提取 HTML 内容写入 static/index.html
"
```

实际操作：直接跳到 Task 6 完成 static/index.html，然后回来验证。

- [ ] **Step 4: 启动服务验证**

```bash
cd /Users/jinyabo/Documents/ai-claude/claude-launcher
python3 server.py &
sleep 1
curl -s http://localhost:8765/api/health | python3 -m json.tool
curl -s http://localhost:8765/api/workspaces | python3 -m json.tool | head -20
kill %1
```

Expected: `/api/health` 返回 `{"ok": true, "internet": ...}`，`/api/workspaces` 返回工作空间列表。

- [ ] **Step 5: Commit**

```bash
git add server.py static/
git commit -m "refactor: slim server.py to entry point, add static/ dir"
```

---

### Task 5: 创建 static/app.css

**Files:**
- Create: `static/app.css`

- [ ] **Step 1: 写入 app.css（主题变量 + 全部样式）**

```css
/* ── Theme variables ──────────────────────────────────────────── */
:root {
  --bg: #0d1117; --card: #161b22; --border: #30363d;
  --text: #e6edf3; --sub: #8b949e; --accent: #58a6ff;
  --green: #3fb950; --orange: #d29922; --red: #da3633;
  --radius: 12px;
}
[data-theme="light"] {
  --bg: #f6f8fa; --card: #ffffff; --border: #d0d7de;
  --text: #1f2328; --sub: #656d76; --accent: #0969da;
  --green: #1a7f37; --orange: #9a6700; --red: #cf222e;
}

/* ── Reset ───────────────────────────────────────────────────── */
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif;
  background: var(--bg); color: var(--text);
  min-height: 100dvh; padding-bottom: env(safe-area-inset-bottom);
  transition: background .2s, color .2s;
}

/* ── Network banner ──────────────────────────────────────────── */
.net-banner {
  display: none; position: sticky; top: 0; z-index: 20;
  padding: 9px 16px; font-size: 13px; font-weight: 500;
  text-align: center; gap: 6px; align-items: center; justify-content: center;
}
.net-banner.show { display: flex; }
.net-banner.lan-down  { background: #3d1a1a; color: #f85149; border-bottom: 1px solid rgba(248,81,73,.3); }
.net-banner.inet-warn { background: #2d2200; color: var(--orange); border-bottom: 1px solid rgba(210,153,34,.3); }
.net-dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; flex-shrink: 0; }

/* ── Header ──────────────────────────────────────────────────── */
header {
  position: sticky; top: 0; z-index: 10;
  background: rgba(13,17,23,0.88); backdrop-filter: blur(14px);
  padding: 14px 18px 11px; border-bottom: 1px solid var(--border);
  display: flex; justify-content: space-between; align-items: center;
}
[data-theme="light"] header { background: rgba(246,248,250,0.92); }
header h1 { font-size: 19px; font-weight: 600; }
.header-meta { display: flex; align-items: center; gap: 8px; margin-top: 3px; }
.header-sub { font-size: 12px; color: var(--sub); }

.net-pill {
  font-size: 11px; padding: 2px 7px; border-radius: 20px;
  border: 1px solid var(--border); display: inline-flex;
  align-items: center; gap: 4px; line-height: 1;
}
.net-pill .dot { width: 6px; height: 6px; border-radius: 50%; }
.net-pill.ok  { border-color: rgba(63,185,80,.3); color: var(--green); }
.net-pill.ok .dot  { background: var(--green); }
.net-pill.warn { border-color: rgba(210,153,34,.3); color: var(--orange); }
.net-pill.warn .dot { background: var(--orange); }
.net-pill.bad  { border-color: rgba(248,81,73,.3); color: var(--red); }
.net-pill.bad .dot  { background: var(--red); }

.gear-btn {
  background: none; border: 1px solid var(--border); border-radius: 8px;
  color: var(--sub); width: 36px; height: 36px; font-size: 17px;
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; transition: border-color .15s, color .15s;
}
.gear-btn:active, .gear-btn.active {
  border-color: var(--accent); color: var(--accent);
  background: rgba(88,166,255,.08);
}

/* ── Main content ────────────────────────────────────────────── */
main { padding: 14px 16px 32px; max-width: 520px; margin: 0 auto; }
.section-label {
  font-size: 11px; font-weight: 600; color: var(--sub);
  text-transform: uppercase; letter-spacing: .06em;
  margin: 18px 0 9px;
}

.card {
  background: var(--card); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 13px 14px;
  margin-bottom: 9px; display: flex;
  justify-content: space-between; align-items: center;
  cursor: pointer; transition: border-color .15s, opacity .15s;
  -webkit-tap-highlight-color: transparent; user-select: none;
}
.card:active:not(.loading) { border-color: var(--accent); }
.card.running { border-color: rgba(63,185,80,.35); }
.card.loading { opacity: .6; cursor: wait; }
.card-left { flex: 1; min-width: 0; margin-right: 10px; }
.card-name { font-size: 15px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.card-path { font-size: 12px; color: var(--sub); margin-top: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.card-right { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }

.status-dot { width: 8px; height: 8px; border-radius: 50%; }
.status-dot.on  { background: var(--green); box-shadow: 0 0 6px var(--green); }
.status-dot.off { background: var(--border); }
.status-dot.spinning {
  border: 2px solid var(--border); border-top-color: var(--accent);
  animation: spin .8s linear infinite; background: none; box-shadow: none;
}
@keyframes spin { to { transform: rotate(360deg); } }

.stop-btn {
  background: none; border: 1px solid var(--border); border-radius: 6px;
  color: var(--sub); font-size: 11px; padding: 3px 7px; cursor: pointer;
  line-height: 1.4; display: none;
}
.card.running .stop-btn { display: block; }
.stop-btn:active { background: rgba(218,54,51,.15); border-color: var(--red); color: var(--red); }

.guide {
  background: rgba(88,166,255,.07); border: 1px solid rgba(88,166,255,.2);
  border-radius: var(--radius); padding: 13px 15px; margin-bottom: 12px;
  font-size: 13px; line-height: 1.7; color: var(--sub);
}
.guide strong { color: var(--text); }
.guide ol { padding-left: 18px; margin-top: 5px; }
.empty { color: var(--sub); text-align: center; padding: 48px 20px; line-height: 1.8; }

/* ── Modal (session conflict) ───────────────────────────────── */
.overlay {
  display: none; position: fixed; inset: 0;
  background: rgba(0,0,0,.55); backdrop-filter: blur(4px);
  z-index: 100; align-items: flex-end; justify-content: center;
}
.overlay.show { display: flex; }
.modal {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 20px 20px 0 0; width: 100%; max-width: 520px;
  padding: 24px 20px calc(24px + env(safe-area-inset-bottom));
}
.modal h2 { font-size: 17px; font-weight: 600; margin-bottom: 6px; }
.modal p  { font-size: 14px; color: var(--sub); margin-bottom: 20px; }

.btn {
  display: block; width: 100%; padding: 14px; border: none;
  border-radius: var(--radius); font-size: 16px; font-weight: 500;
  cursor: pointer; margin-bottom: 10px; transition: opacity .1s;
}
.btn:active { opacity: .8; }
.btn:last-child { margin-bottom: 0; }
.btn-primary { background: var(--accent); color: #000; }
.btn-danger  { background: var(--red); color: #fff; }
.btn-cancel  { background: var(--border); color: var(--text); }

/* ── Toast ───────────────────────────────────────────────────── */
.toast {
  position: fixed; bottom: calc(24px + env(safe-area-inset-bottom));
  left: 50%; transform: translateX(-50%);
  background: #1f2937; border: 1px solid #374151;
  color: var(--text); border-radius: 10px;
  padding: 10px 18px; font-size: 14px; z-index: 200;
  opacity: 0; transition: opacity .25s; pointer-events: none;
  white-space: nowrap; max-width: calc(100vw - 40px); text-align: center;
}
.toast.show { opacity: 1; }
.toast.success { background: #0d3321; border-color: rgba(63,185,80,.4); }
.toast.info    { background: #0c1e3a; border-color: rgba(88,166,255,.4); }
.toast.warn    { background: #2d2200; border-color: rgba(210,153,34,.4); }

/* ── Settings Bottom Sheet ───────────────────────────────────── */
.sheet-overlay {
  display: none; position: fixed; inset: 0;
  background: rgba(0,0,0,.55); backdrop-filter: blur(4px);
  z-index: 100; align-items: flex-end; justify-content: center;
}
.sheet-overlay.show { display: flex; }
.sheet {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 20px 20px 0 0; width: 100%; max-width: 520px;
  max-height: 80dvh; overflow-y: auto;
  padding-bottom: calc(16px + env(safe-area-inset-bottom));
  transform: translateY(100%);
  transition: transform .28s cubic-bezier(0.32, 0.72, 0, 1);
}
.sheet-overlay.show .sheet { transform: translateY(0); }
.sheet-handle {
  width: 36px; height: 4px; background: var(--border);
  border-radius: 2px; margin: 10px auto 14px;
}
.sheet-section-label {
  font-size: 10px; font-weight: 600; color: var(--sub);
  text-transform: uppercase; letter-spacing: .06em;
  padding: 8px 16px 4px;
}
.sheet-group {
  background: var(--bg); border-radius: 12px;
  margin: 0 12px 8px; overflow: hidden;
}
.sheet-row {
  display: flex; align-items: center; padding: 11px 14px; gap: 10px;
  cursor: pointer; -webkit-tap-highlight-color: transparent;
}
.sheet-row + .sheet-row { border-top: 1px solid rgba(48,54,61,.5); }
.sheet-row:active { background: rgba(255,255,255,.04); }
.sheet-icon { font-size: 16px; width: 22px; text-align: center; flex-shrink: 0; }
.sheet-label { font-size: 14px; color: var(--text); flex: 1; }
.sheet-value { font-size: 12px; color: var(--sub); max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sheet-chevron { color: var(--sub); font-size: 12px; margin-left: 4px; }

/* Segmented control */
.seg-ctrl {
  display: flex; background: var(--card); border: 1px solid var(--border);
  border-radius: 8px; overflow: hidden; flex-shrink: 0;
}
.seg-item {
  flex: 1; padding: 5px 10px; text-align: center;
  font-size: 12px; color: var(--sub); cursor: pointer;
  border: none; background: none; white-space: nowrap;
  transition: background .15s, color .15s;
}
.seg-item.active { background: var(--accent); color: #000; font-weight: 500; }

/* Toggle */
.toggle-wrap { position: relative; width: 44px; height: 26px; flex-shrink: 0; }
.toggle-wrap input { opacity: 0; width: 0; height: 0; position: absolute; }
.toggle-track {
  position: absolute; inset: 0; background: var(--border);
  border-radius: 13px; cursor: pointer; transition: background .2s;
}
.toggle-wrap input:checked + .toggle-track { background: var(--green); }
.toggle-track::after {
  content: ''; position: absolute;
  width: 20px; height: 20px; background: #fff; border-radius: 10px;
  top: 3px; left: 3px; transition: transform .2s;
}
.toggle-wrap input:checked + .toggle-track::after { transform: translateX(18px); }

/* ── Workspace manage overlay (second level) ─────────────────── */
.settings-overlay {
  display: none; position: fixed; inset: 0;
  background: rgba(0,0,0,.55); backdrop-filter: blur(4px);
  z-index: 110; align-items: flex-end; justify-content: center;
}
.settings-overlay.show { display: flex; }
.settings-panel {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 20px 20px 0 0; width: 100%; max-width: 520px;
  padding: 24px 20px calc(24px + env(safe-area-inset-bottom));
  max-height: 75dvh; overflow-y: auto;
}
.settings-panel h2 { font-size: 17px; font-weight: 600; margin-bottom: 6px; }
.ws-item {
  display: flex; justify-content: space-between; align-items: center;
  padding: 11px 0; border-bottom: 1px solid var(--border); font-size: 14px;
}
.ws-item:last-child { border-bottom: none; }
.ws-item-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-right: 8px; }
.ws-item.hidden-item .ws-item-name { color: var(--sub); text-decoration: line-through; }
.tag-btn {
  font-size: 12px; padding: 4px 10px; border-radius: 6px;
  border: 1px solid var(--border); background: none; color: var(--text);
  cursor: pointer; margin-left: 6px; white-space: nowrap;
}
.tag-btn.active-pin  { border-color: var(--accent); color: var(--accent); }
.tag-btn.active-hide { border-color: var(--red); color: var(--red); }
```

- [ ] **Step 2: Commit**

```bash
git add static/app.css
git commit -m "refactor: extract app.css with theme variables and settings sheet styles"
```

---

### Task 6: 创建 static/index.html

**Files:**
- Create: `static/index.html`

- [ ] **Step 1: 写入 static/index.html**

```html
<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Claude">
<title>Claude Launcher</title>
<link rel="manifest" href="/manifest.json">
<link rel="stylesheet" href="/app.css">
</head>
<body>

<div class="net-banner" id="net-banner">
  <div class="net-dot"></div>
  <span id="net-banner-msg"></span>
</div>

<header>
  <div>
    <h1>⚡ Claude Launcher</h1>
    <div class="header-meta">
      <span class="header-sub" id="ip-hint">局域网 · 加载中...</span>
      <span class="net-pill" id="net-pill">
        <span class="dot"></span>
        <span id="net-pill-text" data-i18n="net_checking">检测中</span>
      </span>
    </div>
  </div>
  <button class="gear-btn" id="gear-btn" aria-label="Settings">⚙</button>
</header>

<main id="main">
  <div class="empty" data-i18n="empty_loading">加载中...</div>
</main>

<!-- Session conflict modal -->
<div class="overlay" id="modal">
  <div class="modal">
    <h2 id="modal-title"></h2>
    <p id="modal-desc" data-i18n="modal_running_desc"></p>
    <button class="btn btn-primary" id="btn-reuse" data-i18n="btn_reuse">继续使用现有会话</button>
    <button class="btn btn-danger"  id="btn-new"   data-i18n="btn_new_session">终止并新建会话</button>
    <button class="btn btn-cancel"  id="btn-cancel-modal" data-i18n="btn_cancel">取消</button>
  </div>
</div>

<!-- Settings bottom sheet (rendered by settings.js) -->
<div class="sheet-overlay" id="sheet-overlay">
  <div class="sheet" id="settings-sheet"></div>
</div>

<!-- Workspace manage panel (second level, z-index 110) -->
<div class="settings-overlay" id="settings-overlay">
  <div class="settings-panel">
    <h2 data-i18n="ws_panel_title">工作空间管理</h2>
    <p style="font-size:13px;color:var(--sub);margin-bottom:16px"
       data-i18n="ws_panel_hint">置顶常用项目，隐藏不需要显示的目录</p>
    <div id="settings-list"></div>
    <br>
    <button class="btn btn-cancel" id="btn-close-settings" data-i18n="btn_close">关闭</button>
  </div>
</div>

<div class="toast" id="toast"></div>

<script src="/i18n.js"></script>
<script src="/settings.js"></script>
<script src="/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: 启动服务验证 HTML 可访问**

```bash
python3 server.py &
sleep 1
curl -s http://localhost:8765/ | head -5
kill %1
```

Expected: 输出 `<!DOCTYPE html>` 开头的 HTML。

- [ ] **Step 3: Commit**

```bash
git add static/index.html
git commit -m "refactor: extract index.html to static/"
```

---

### Task 7: 创建 static/app.js

**Files:**
- Create: `static/app.js`

- [ ] **Step 1: 写入 static/app.js**

```javascript
/* global t, openSettings */
let workspaces = [];
let activeName = null;
let loadingCards = new Set();

// ── Network detection ──────────────────────────────────────────
const netState = { lan: true, inet: true };

async function checkNetwork() {
  let lanOk = false;
  try {
    const r = await fetch('/api/health', { signal: AbortSignal.timeout(3000) });
    const d = await r.json();
    lanOk = true;
    netState.inet = d.internet;
  } catch {
    lanOk = false;
  }
  netState.lan = lanOk;
  updateNetUI();
}

function updateNetUI() {
  const pill     = document.getElementById('net-pill');
  const pillText = document.getElementById('net-pill-text');
  const banner   = document.getElementById('net-banner');
  const bannerMsg = document.getElementById('net-banner-msg');

  if (!netState.lan) {
    pill.className = 'net-pill bad';
    pillText.textContent = t('net_bad');
    banner.className = 'net-banner show lan-down';
    bannerMsg.textContent = t('net_banner_lan_down');
    return;
  }
  if (!netState.inet) {
    pill.className = 'net-pill warn';
    pillText.textContent = t('net_warn');
    banner.className = 'net-banner show inet-warn';
    bannerMsg.textContent = t('net_banner_inet_warn');
    return;
  }
  pill.className = 'net-pill ok';
  pillText.textContent = t('net_ok');
  banner.className = 'net-banner';
}

window.addEventListener('offline', () => {
  netState.lan = false; updateNetUI();
  showToast(t('toast_net_offline'), 'warn');
});
window.addEventListener('online', () => {
  checkNetwork();
  showToast(t('toast_net_restored'), 'info');
});

// ── Data ───────────────────────────────────────────────────────
async function load() {
  try {
    const res = await fetch('/api/workspaces');
    const data = await res.json();
    workspaces = data.workspaces;
    document.getElementById('ip-hint').textContent =
      `${t('header_subtitle')} · ${data.ip}:${data.port}`;
    render();
  } catch {
    netState.lan = false; updateNetUI();
  }
}

// ── Render ─────────────────────────────────────────────────────
function render() {
  const pinned = workspaces.filter(w => w.pinned);
  const rest   = workspaces.filter(w => !w.pinned);
  let html = '';

  if (!workspaces.length) {
    document.getElementById('main').innerHTML =
      `<div class="empty">${t('empty_no_ws')}<br><small>${t('empty_no_ws_hint')}</small></div>`;
    return;
  }

  const anyRunning = workspaces.some(w => w.running);
  if (!anyRunning) {
    html += `<div class="guide">
      <strong>${t('guide_title')}</strong>
      <ol>
        <li>${t('guide_step1')}</li>
        <li>${t('guide_step2')}</li>
        <li>${t('guide_step3')}</li>
      </ol>
    </div>`;
  }

  if (pinned.length) {
    html += `<div class="section-label">${t('section_pinned')}</div>`;
    html += pinned.map(cardHTML).join('');
  }
  if (rest.length) {
    html += `<div class="section-label">${pinned.length ? t('section_other') : t('section_all')}</div>`;
    html += rest.map(cardHTML).join('');
  }

  document.getElementById('main').innerHTML = html;
  document.querySelectorAll('.stop-btn').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      doStop(btn.dataset.name);
    });
  });
}

function cardHTML(w) {
  const loading = loadingCards.has(w.name);
  const dotClass  = loading ? 'spinning' : (w.running ? 'on' : 'off');
  const cardClass = loading ? 'loading'  : (w.running ? 'running' : '');
  const ne = escAttr(w.name), nh = escHTML(w.name);
  return `<div class="card ${cardClass}" data-name="${ne}">
    <div class="card-left">
      <div class="card-name">${nh}</div>
      <div class="card-path">${escHTML(w.short_path)}</div>
    </div>
    <div class="card-right">
      <button class="stop-btn" data-name="${ne}">${t('btn_stop')}</button>
      <div class="status-dot ${dotClass}"></div>
    </div>
  </div>`;
}

document.getElementById('main').addEventListener('click', e => {
  const card = e.target.closest('.card');
  if (!card || card.classList.contains('loading')) return;
  const name = card.dataset.name;
  if (name) tap(name);
});

// ── Actions ────────────────────────────────────────────────────
function tap(name) {
  activeName = name;
  const ws = workspaces.find(w => w.name === name);
  if (!ws) return;
  if (ws.running) {
    document.getElementById('modal-title').textContent = ws.name;
    document.getElementById('modal-desc').textContent = t('modal_running_desc');
    document.getElementById('modal').classList.add('show');
  } else {
    doStart(name, false);
  }
}

function closeModal() {
  document.getElementById('modal').classList.remove('show');
  activeName = null;
}

async function doReuse() {
  closeModal();
  showToast(t('toast_reuse'), 'info');
}

async function doNew() {
  const name = activeName;
  closeModal();
  setLoading(name, true);
  await post('/api/start', { name, force_new: true });
  waitForSession(name);
}

async function doStart(name, force_new) {
  setLoading(name, true);
  await post('/api/start', { name, force_new });
  waitForSession(name);
}

async function doStop(name) {
  setLoading(name, true);
  await post('/api/stop', { name });
  setTimeout(() => { setLoading(name, false); load(); }, 700);
  showToast(`${t('toast_stopped')} ${name}`, 'info');
}

function waitForSession(name) {
  let attempts = 0;
  const poll = setInterval(async () => {
    attempts++;
    try {
      const res = await fetch('/api/workspaces');
      const data = await res.json();
      const ws = data.workspaces.find(w => w.name === name);
      if ((ws && ws.running) || attempts >= 10) {
        clearInterval(poll);
        setLoading(name, false);
        workspaces = data.workspaces;
        render();
        if (ws && ws.running)
          showToast(`✓ ${name} ${t('toast_started')}`, 'success');
      }
    } catch { clearInterval(poll); setLoading(name, false); }
  }, 1000);
}

function setLoading(name, val) {
  if (val) loadingCards.add(name); else loadingCards.delete(name);
  render();
}

// ── Workspace settings panel ───────────────────────────────────
async function openWsPanel() {
  const res = await fetch('/api/workspaces?all=1');
  const data = await res.json();
  const cfg = data.config;
  let html = data.workspaces.map(w => {
    const isHidden = w.is_hidden;
    const isPinned = cfg.pinned.includes(w.name);
    return `<div class="ws-item ${isHidden ? 'hidden-item' : ''}">
      <span class="ws-item-name">${escHTML(w.name)}</span>
      <div>
        <button class="tag-btn ${isPinned ? 'active-pin' : ''}"
          data-action="pin" data-name="${escAttr(w.name)}">${t('btn_pin')}</button>
        <button class="tag-btn ${isHidden ? 'active-hide' : ''}"
          data-action="hide" data-name="${escAttr(w.name)}">${t('btn_hide')}</button>
      </div>
    </div>`;
  }).join('');
  document.getElementById('settings-list').innerHTML =
    html || `<div style="color:var(--sub)">${t('empty_no_ws')}</div>`;
  document.getElementById('settings-overlay').classList.add('show');
}

document.getElementById('settings-list').addEventListener('click', async e => {
  const btn = e.target.closest('[data-action]');
  if (!btn) return;
  await post('/api/config/toggle', {
    key: btn.dataset.action === 'pin' ? 'pinned' : 'hidden',
    name: btn.dataset.name,
  });
  openWsPanel();
});

function closeWsPanel() {
  document.getElementById('settings-overlay').classList.remove('show');
  load();
}

// ── Modal wiring ───────────────────────────────────────────────
document.getElementById('btn-reuse').addEventListener('click', doReuse);
document.getElementById('btn-new').addEventListener('click', doNew);
document.getElementById('btn-cancel-modal').addEventListener('click', closeModal);
document.getElementById('modal').addEventListener('click',
  e => { if (e.target.id === 'modal') closeModal(); });
document.getElementById('btn-close-settings').addEventListener('click', closeWsPanel);
document.getElementById('settings-overlay').addEventListener('click',
  e => { if (e.target.id === 'settings-overlay') closeWsPanel(); });

// ── Utils ──────────────────────────────────────────────────────
async function post(url, body) {
  return fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

function showToast(msg, type = '') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = 'toast show' + (type ? ' ' + type : '');
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.classList.remove('show'), 3200);
}

function escHTML(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function escAttr(s) {
  return String(s).replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

// ── Boot ───────────────────────────────────────────────────────
checkNetwork();
load();
setInterval(load, 15000);
setInterval(checkNetwork, 20000);
```

- [ ] **Step 2: Commit**

```bash
git add static/app.js
git commit -m "refactor: extract app.js to static/"
```

---

### Task 8: 创建 static/i18n.js

**Files:**
- Create: `static/i18n.js`

- [ ] **Step 1: 写入 static/i18n.js**

```javascript
const TRANSLATIONS = {
  zh: {
    header_subtitle: '局域网',
    net_checking: '检测中', net_ok: '正常', net_warn: '无外网', net_bad: '断连',
    net_banner_lan_down: '无法连接到 Mac，请检查局域网连接',
    net_banner_inet_warn: 'Mac 当前无互联网连接，Claude 可能无法运行',
    section_pinned: '📌 置顶',
    section_other: '其他 工作空间',
    section_all: '全部 工作空间',
    guide_title: '使用方式',
    guide_step1: '点击项目启动 Claude 会话',
    guide_step2: '打开 Claude App → 底部 Code 标签',
    guide_step3: '找到同名会话（绿点）点击连接',
    btn_stop: '停止',
    empty_loading: '加载中...',
    empty_no_ws: '未找到工作空间',
    empty_no_ws_hint: '目录需包含 CLAUDE.md 文件',
    modal_running_desc: '该工作空间已有运行中的 Claude 会话，你想怎么处理？',
    btn_reuse: '继续使用现有会话',
    btn_new_session: '终止并新建会话',
    btn_cancel: '取消',
    toast_reuse: '前往 Claude App → Code 标签连接',
    toast_stopped: '已停止',
    toast_started: '已启动 → Claude App → Code 标签',
    toast_net_offline: '网络已断开',
    toast_net_restored: '网络已恢复',
    settings_title: '设置',
    settings_appearance: '外观',
    settings_language: '语言',
    settings_theme: '主题',
    theme_light: '浅色', theme_dark: '深色', theme_auto: '跟随系统',
    settings_workspace_section: '工作空间',
    settings_scan_dir: '扫描目录',
    settings_manage_ws: '管理工作空间',
    settings_require_md: '仅显示 CLAUDE.md',
    ws_panel_title: '工作空间管理',
    ws_panel_hint: '置顶常用项目，隐藏不需要显示的目录',
    btn_close: '关闭',
    btn_pin: '置顶',
    btn_hide: '隐藏',
  },
  en: {
    header_subtitle: 'LAN',
    net_checking: 'Checking', net_ok: 'OK', net_warn: 'No WAN', net_bad: 'Offline',
    net_banner_lan_down: 'Cannot reach Mac — check LAN connection',
    net_banner_inet_warn: 'Mac has no internet — Claude may not work',
    section_pinned: '📌 Pinned',
    section_other: 'Other Workspaces',
    section_all: 'All Workspaces',
    guide_title: 'How to use',
    guide_step1: 'Tap a project to start a Claude session',
    guide_step2: 'Open Claude App → Code tab at the bottom',
    guide_step3: 'Find the session (green dot) and connect',
    btn_stop: 'Stop',
    empty_loading: 'Loading...',
    empty_no_ws: 'No workspaces found',
    empty_no_ws_hint: 'Directories must contain CLAUDE.md',
    modal_running_desc: 'This workspace has a running Claude session.',
    btn_reuse: 'Use existing session',
    btn_new_session: 'Kill and restart',
    btn_cancel: 'Cancel',
    toast_reuse: 'Go to Claude App → Code tab',
    toast_stopped: 'Stopped',
    toast_started: 'Started → Claude App → Code tab',
    toast_net_offline: 'Network offline',
    toast_net_restored: 'Network restored',
    settings_title: 'Settings',
    settings_appearance: 'Appearance',
    settings_language: 'Language',
    settings_theme: 'Theme',
    theme_light: 'Light', theme_dark: 'Dark', theme_auto: 'Auto',
    settings_workspace_section: 'Workspace',
    settings_scan_dir: 'Scan Directory',
    settings_manage_ws: 'Manage Workspaces',
    settings_require_md: 'Require CLAUDE.md',
    ws_panel_title: 'Manage Workspaces',
    ws_panel_hint: 'Pin frequent projects, hide others',
    btn_close: 'Close',
    btn_pin: 'Pin',
    btn_hide: 'Hide',
  },
};

let _lang = localStorage.getItem('launcher_lang') || 'zh';

function t(key) {
  return (TRANSLATIONS[_lang] || TRANSLATIONS.zh)[key] || key;
}

function setLang(lang) {
  _lang = lang;
  localStorage.setItem('launcher_lang', lang);
  applyLang();
}

function applyLang() {
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    el.textContent = t(key);
  });
  if (typeof render === 'function') render();
  if (typeof renderSheet === 'function') renderSheet();
}

// Apply on load
document.addEventListener('DOMContentLoaded', applyLang);
```

- [ ] **Step 2: Commit**

```bash
git add static/i18n.js
git commit -m "feat: add i18n module with zh/en translations"
```

---

### Task 9: 创建 static/settings.js

**Files:**
- Create: `static/settings.js`

- [ ] **Step 1: 写入 static/settings.js**

```javascript
/* global t, setLang, load, openWsPanel */

let _requireMd = true;
let _scanDir = '';

function renderSheet() {
  const sheet = document.getElementById('settings-sheet');
  if (!sheet) return;

  sheet.innerHTML = `
    <div class="sheet-handle"></div>

    <div class="sheet-section-label">${t('settings_appearance')}</div>
    <div class="sheet-group">
      <div class="sheet-row" style="cursor:default">
        <span class="sheet-icon">🌐</span>
        <span class="sheet-label">${t('settings_language')}</span>
        <div class="seg-ctrl" id="lang-seg">
          <button class="seg-item ${_lang === 'zh' ? 'active' : ''}" data-lang="zh">中文</button>
          <button class="seg-item ${_lang === 'en' ? 'active' : ''}" data-lang="en">EN</button>
        </div>
      </div>
      <div class="sheet-row" style="cursor:default">
        <span class="sheet-icon">🎨</span>
        <span class="sheet-label">${t('settings_theme')}</span>
        <div class="seg-ctrl" id="theme-seg">
          <button class="seg-item ${_theme === 'light' ? 'active' : ''}" data-theme-val="light">${t('theme_light')}</button>
          <button class="seg-item ${_theme === 'dark'  ? 'active' : ''}" data-theme-val="dark">${t('theme_dark')}</button>
          <button class="seg-item ${_theme === 'auto'  ? 'active' : ''}" data-theme-val="auto">${t('theme_auto')}</button>
        </div>
      </div>
    </div>

    <div class="sheet-section-label">${t('settings_workspace_section')}</div>
    <div class="sheet-group">
      <div class="sheet-row" id="row-scan-dir">
        <span class="sheet-icon">📁</span>
        <span class="sheet-label">${t('settings_scan_dir')}</span>
        <span class="sheet-value" id="scan-dir-val">${escSheetHTML(_scanDir)}</span>
        <span class="sheet-chevron">›</span>
      </div>
      <div class="sheet-row" id="row-manage-ws">
        <span class="sheet-icon">📋</span>
        <span class="sheet-label">${t('settings_manage_ws')}</span>
        <span class="sheet-chevron">›</span>
      </div>
      <div class="sheet-row" style="cursor:default">
        <span class="sheet-icon">📄</span>
        <span class="sheet-label">${t('settings_require_md')}</span>
        <label class="toggle-wrap">
          <input type="checkbox" id="toggle-require-md" ${_requireMd ? 'checked' : ''}>
          <div class="toggle-track"></div>
        </label>
      </div>
    </div>
  `;

  // Language segment
  sheet.querySelector('#lang-seg').addEventListener('click', e => {
    const btn = e.target.closest('[data-lang]');
    if (!btn) return;
    setLang(btn.dataset.lang);
    renderSheet();
  });

  // Theme segment
  sheet.querySelector('#theme-seg').addEventListener('click', e => {
    const btn = e.target.closest('[data-theme-val]');
    if (!btn) return;
    applyTheme(btn.dataset.themeVal);
    renderSheet();
  });

  // Scan dir
  sheet.querySelector('#row-scan-dir').addEventListener('click', () => {
    const val = prompt(t('settings_scan_dir'), _scanDir);
    if (val === null) return;
    saveScanDir(val.trim());
  });

  // Manage workspaces
  sheet.querySelector('#row-manage-ws').addEventListener('click', () => {
    openWsPanel();
  });

  // require_claude_md toggle
  sheet.querySelector('#toggle-require-md').addEventListener('change', e => {
    saveRequireMd(e.target.checked);
  });
}

async function loadSheetData() {
  try {
    const res = await fetch('/api/workspaces');
    const data = await res.json();
    _requireMd = data.config.require_claude_md !== false;
    _scanDir = data.config.scan_dir || '';
  } catch { /* ignore */ }
}

async function saveScanDir(val) {
  if (!val) return;
  await fetch('/api/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scan_dir: val }),
  });
  _scanDir = val;
  renderSheet();
  if (typeof load === 'function') load();
}

async function saveRequireMd(val) {
  _requireMd = val;
  await fetch('/api/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ require_claude_md: val }),
  });
  if (typeof load === 'function') load();
}

// ── Theme ──────────────────────────────────────────────────────
let _theme = localStorage.getItem('launcher_theme') || 'dark';
let _mq = window.matchMedia('(prefers-color-scheme: dark)');

function applyTheme(mode) {
  _theme = mode;
  localStorage.setItem('launcher_theme', mode);
  _applyThemeToDOM();
}

function _applyThemeToDOM() {
  if (_theme === 'light') {
    document.documentElement.setAttribute('data-theme', 'light');
  } else if (_theme === 'dark') {
    document.documentElement.removeAttribute('data-theme');
  } else {
    // auto
    if (_mq.matches) {
      document.documentElement.removeAttribute('data-theme');
    } else {
      document.documentElement.setAttribute('data-theme', 'light');
    }
  }
}

_mq.addEventListener('change', () => {
  if (_theme === 'auto') _applyThemeToDOM();
});

// Apply theme immediately (before DOMContentLoaded)
_applyThemeToDOM();

// ── Sheet open / close ─────────────────────────────────────────
async function openSettings() {
  await loadSheetData();
  renderSheet();
  document.getElementById('gear-btn').classList.add('active');
  document.getElementById('sheet-overlay').classList.add('show');
}

function closeSettings() {
  document.getElementById('sheet-overlay').classList.remove('show');
  document.getElementById('gear-btn').classList.remove('active');
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('gear-btn').addEventListener('click', openSettings);
  document.getElementById('sheet-overlay').addEventListener('click', e => {
    if (e.target.id === 'sheet-overlay') closeSettings();
  });
});

// ── Helper ─────────────────────────────────────────────────────
function escSheetHTML(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
```

- [ ] **Step 2: Commit**

```bash
git add static/settings.js
git commit -m "feat: add settings.js — bottom sheet, theme switching, language switching"
```

---

### Task 10: 全链路验证 + .gitignore

**Files:**
- Modify: `.gitignore` (如存在)

- [ ] **Step 1: 检查 .gitignore，补充 .superpowers/**

```bash
grep -q ".superpowers" .gitignore 2>/dev/null || echo ".superpowers/" >> .gitignore
```

- [ ] **Step 2: 启动服务，全链路验证**

```bash
python3 server.py &
SERVER_PID=$!
sleep 1

# 1. 静态文件
curl -s -o /dev/null -w "%{http_code}" http://localhost:8765/        # 200
curl -s -o /dev/null -w "%{http_code}" http://localhost:8765/app.css  # 200
curl -s -o /dev/null -w "%{http_code}" http://localhost:8765/app.js   # 200
curl -s -o /dev/null -w "%{http_code}" http://localhost:8765/i18n.js  # 200
curl -s -o /dev/null -w "%{http_code}" http://localhost:8765/settings.js  # 200

# 2. API
curl -s http://localhost:8765/api/health | python3 -m json.tool
curl -s http://localhost:8765/api/workspaces | python3 -m json.tool | head -10

# 3. 新接口
curl -s -X POST http://localhost:8765/api/config \
  -H "Content-Type: application/json" \
  -d '{"require_claude_md": true}' | python3 -m json.tool

kill $SERVER_PID
```

Expected: 所有静态文件返回 200，API 返回正确 JSON。

- [ ] **Step 3: 清理旧代码 — 删除 server.py 中的 PWA_HTML 残留**

确认 server.py 只有 `main()` 逻辑（约 13 行），无任何 HTML 字符串。

- [ ] **Step 4: 最终 commit**

```bash
git add .gitignore server.py
git commit -m "feat: settings panel complete — lang/theme/workspace config, architecture refactored"
```

---

## 验收标准

1. `python3 server.py` 启动后，浏览器访问可看到工作空间列表（功能不回退）
2. 点击 ⚙ 按钮弹出 Bottom Sheet，有外观 / 工作空间两组设置
3. 语言切换：点击 EN 后所有 UI 文案变为英文，刷新后保持
4. 主题切换：浅色/深色/跟随系统三档，切换即时生效，刷新后保持
5. 扫描目录修改：输入新路径保存后，工作空间列表自动刷新
6. CLAUDE.md 开关：切换后工作空间列表即时刷新
7. 管理工作空间（pin/hide）功能正常
8. `install.sh` 和 `.plist` 无需修改，启动方式不变
