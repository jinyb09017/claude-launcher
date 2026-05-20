#!/usr/bin/env python3
"""Claude Workspace Launcher — LAN-accessible PWA to start claude sessions by directory."""

import http.server
import json
import os
import pathlib
import subprocess
import threading
import urllib.parse
from datetime import datetime

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


def scan_workspaces(cfg):
    scan_dir = pathlib.Path(cfg["scan_dir"])
    require_md = cfg.get("require_claude_md", True)
    hidden = set(cfg.get("hidden", []))
    pinned = cfg.get("pinned", [])

    entries = []
    if scan_dir.exists():
        for d in sorted(scan_dir.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            if d.name in hidden:
                continue
            if require_md and not (d / "CLAUDE.md").exists():
                continue
            mtime = d.stat().st_mtime
            entries.append({"name": d.name, "path": str(d), "mtime": mtime})

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
    subprocess.Popen([
        "tmux", "new-session", "-d", "-s", name, "-c", path, "claude"
    ])


def kill_session(dirname):
    name = session_name(dirname)
    subprocess.run(["tmux", "kill-session", "-t", name],
                   stderr=subprocess.DEVNULL)


PWA_HTML = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Claude">
<title>Claude Launcher</title>
<link rel="manifest" href="/manifest.json">
<style>
  :root {
    --bg: #0d1117; --card: #161b22; --border: #30363d;
    --text: #e6edf3; --sub: #8b949e; --accent: #58a6ff;
    --green: #3fb950; --radius: 12px;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif;
    background: var(--bg); color: var(--text);
    min-height: 100dvh; padding-bottom: env(safe-area-inset-bottom);
  }
  header {
    position: sticky; top: 0; z-index: 10;
    background: rgba(13,17,23,0.85); backdrop-filter: blur(12px);
    padding: 16px 20px 12px; border-bottom: 1px solid var(--border);
    display: flex; justify-content: space-between; align-items: center;
  }
  header h1 { font-size: 20px; font-weight: 600; }
  header .sub { font-size: 12px; color: var(--sub); margin-top: 2px; }
  .settings-btn {
    background: none; border: 1px solid var(--border); border-radius: 8px;
    color: var(--sub); padding: 6px 10px; font-size: 13px; cursor: pointer;
  }
  .settings-btn:active { background: var(--card); }
  main { padding: 16px 16px 24px; max-width: 520px; margin: 0 auto; }
  .section-label {
    font-size: 11px; font-weight: 600; color: var(--sub);
    text-transform: uppercase; letter-spacing: .06em;
    margin: 20px 0 10px;
  }
  .card {
    background: var(--card); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 14px 16px;
    margin-bottom: 10px; display: flex;
    justify-content: space-between; align-items: center;
    cursor: pointer; transition: border-color .15s;
    -webkit-tap-highlight-color: transparent;
  }
  .card:active { border-color: var(--accent); }
  .card.running { border-color: rgba(63,185,80,.4); }
  .card-left { flex: 1; min-width: 0; }
  .card-name { font-size: 15px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .card-path { font-size: 12px; color: var(--sub); margin-top: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .status-dot {
    width: 8px; height: 8px; border-radius: 50%;
    flex-shrink: 0; margin-left: 12px;
  }
  .status-dot.on { background: var(--green); box-shadow: 0 0 6px var(--green); }
  .status-dot.off { background: var(--border); }

  /* Modal */
  .overlay {
    display: none; position: fixed; inset: 0;
    background: rgba(0,0,0,.6); backdrop-filter: blur(4px);
    z-index: 100; align-items: flex-end; justify-content: center;
  }
  .overlay.show { display: flex; }
  .modal {
    background: var(--card); border: 1px solid var(--border);
    border-radius: 20px 20px 0 0; width: 100%; max-width: 520px;
    padding: 24px 20px calc(24px + env(safe-area-inset-bottom));
  }
  .modal h2 { font-size: 17px; font-weight: 600; margin-bottom: 6px; }
  .modal p { font-size: 14px; color: var(--sub); margin-bottom: 20px; }
  .btn {
    display: block; width: 100%; padding: 14px;
    border: none; border-radius: var(--radius);
    font-size: 16px; font-weight: 500; cursor: pointer;
    margin-bottom: 10px; transition: opacity .1s;
  }
  .btn:active { opacity: .8; }
  .btn-primary { background: var(--accent); color: #000; }
  .btn-danger { background: #da3633; color: #fff; }
  .btn-cancel { background: var(--border); color: var(--text); margin-bottom: 0; }

  /* Settings panel */
  .settings-overlay {
    display: none; position: fixed; inset: 0;
    background: rgba(0,0,0,.6); backdrop-filter: blur(4px);
    z-index: 100; align-items: flex-end; justify-content: center;
  }
  .settings-overlay.show { display: flex; }
  .settings-panel {
    background: var(--card); border: 1px solid var(--border);
    border-radius: 20px 20px 0 0; width: 100%; max-width: 520px;
    padding: 24px 20px calc(24px + env(safe-area-inset-bottom));
    max-height: 70dvh; overflow-y: auto;
  }
  .settings-panel h2 { font-size: 17px; font-weight: 600; margin-bottom: 16px; }
  .setting-row {
    display: flex; justify-content: space-between; align-items: center;
    padding: 12px 0; border-bottom: 1px solid var(--border);
    font-size: 14px;
  }
  .setting-row:last-child { border-bottom: none; }
  .ws-item {
    display: flex; justify-content: space-between; align-items: center;
    padding: 10px 0; border-bottom: 1px solid var(--border); font-size: 14px;
  }
  .ws-item:last-child { border-bottom: none; }
  .tag-btn {
    font-size: 12px; padding: 4px 10px; border-radius: 6px;
    border: 1px solid var(--border); background: none; color: var(--text);
    cursor: pointer; margin-left: 6px;
  }
  .tag-btn.active-pin { border-color: var(--accent); color: var(--accent); }
  .tag-btn.active-hide { border-color: #da3633; color: #da3633; }

  .toast {
    position: fixed; bottom: calc(20px + env(safe-area-inset-bottom));
    left: 50%; transform: translateX(-50%);
    background: #238636; color: #fff; border-radius: 10px;
    padding: 10px 18px; font-size: 14px; z-index: 200;
    opacity: 0; transition: opacity .3s; pointer-events: none;
  }
  .toast.show { opacity: 1; }
</style>
</head>
<body>
<header>
  <div>
    <h1>⚡ Claude Launcher</h1>
    <div class="sub" id="ip-hint">局域网 · 加载中...</div>
  </div>
  <button class="settings-btn" onclick="openSettings()">设置</button>
</header>
<main id="main">加载中...</main>

<div class="overlay" id="modal" onclick="if(event.target===this)closeModal()">
  <div class="modal">
    <h2 id="modal-title"></h2>
    <p id="modal-desc"></p>
    <button class="btn btn-primary" id="btn-reuse" onclick="doReuse()">继续使用现有会话</button>
    <button class="btn btn-danger" id="btn-new" onclick="doNew()">终止并新建</button>
    <button class="btn btn-cancel" onclick="closeModal()">取消</button>
  </div>
</div>

<div class="settings-overlay" id="settings-overlay" onclick="if(event.target===this)closeSettings()">
  <div class="settings-panel">
    <h2>工作空间管理</h2>
    <div id="settings-list">加载中...</div>
    <br>
    <button class="btn btn-cancel" onclick="closeSettings()">关闭</button>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
let workspaces = [];
let activeName = null;

async function load() {
  const res = await fetch('/api/workspaces');
  const data = await res.json();
  workspaces = data.workspaces;
  document.getElementById('ip-hint').textContent = `局域网 · ${data.ip}:${data.port}`;
  render();
}

function render() {
  const pinned = workspaces.filter(w => w.pinned);
  const rest = workspaces.filter(w => !w.pinned);
  let html = '';
  if (pinned.length) {
    html += '<div class="section-label">📌 置顶</div>';
    html += pinned.map(cardHTML).join('');
  }
  if (rest.length) {
    html += '<div class="section-label">全部工作空间</div>';
    html += rest.map(cardHTML).join('');
  }
  if (!workspaces.length) html = '<div style="color:var(--sub);text-align:center;padding:40px 0">未找到工作空间<br><small>需含 CLAUDE.md</small></div>';
  document.getElementById('main').innerHTML = html;
}

function cardHTML(w) {
  const on = w.running;
  return `<div class="card ${on ? 'running' : ''}" onclick="tap('${w.name}','${on}')">
    <div class="card-left">
      <div class="card-name">${w.name}</div>
      <div class="card-path">${w.path}</div>
    </div>
    <div class="status-dot ${on ? 'on' : 'off'}"></div>
  </div>`;
}

function tap(name, running) {
  activeName = name;
  if (running === 'true') {
    document.getElementById('modal-title').textContent = name;
    document.getElementById('modal-desc').textContent = '该工作空间已有运行中的 Claude 会话，你想怎么处理？';
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
  showToast('✓ 打开 Claude iOS app → Code tab 连接');
}

async function doNew() {
  closeModal();
  await post('/api/start', { name: activeName, force_new: true });
  showToast('✓ 已新建会话，前往 Claude iOS app → Code');
  setTimeout(load, 1200);
}

async function doStart(name, force_new) {
  await post('/api/start', { name, force_new });
  showToast('✓ 已启动，前往 Claude iOS app → Code');
  setTimeout(load, 1200);
}

async function post(url, body) {
  return fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
}

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 3000);
}

async function openSettings() {
  const res = await fetch('/api/workspaces');
  const data = await res.json();
  const cfg = data.config;
  let html = data.workspaces.map(w => `
    <div class="ws-item">
      <span>${w.name}</span>
      <div>
        <button class="tag-btn ${cfg.pinned.includes(w.name) ? 'active-pin' : ''}"
          onclick="togglePin('${w.name}')">置顶</button>
        <button class="tag-btn ${cfg.hidden.includes(w.name) ? 'active-hide' : ''}"
          onclick="toggleHide('${w.name}')">隐藏</button>
      </div>
    </div>`).join('');
  document.getElementById('settings-list').innerHTML = html || '暂无工作空间';
  document.getElementById('settings-overlay').classList.add('show');
}

function closeSettings() {
  document.getElementById('settings-overlay').classList.remove('show');
  load();
}

async function togglePin(name) {
  await post('/api/config/toggle', { key: 'pinned', name });
  openSettings();
}

async function toggleHide(name) {
  await post('/api/config/toggle', { key: 'hidden', name });
  openSettings();
}

load();
setInterval(load, 10000);
</script>
</body>
</html>"""

MANIFEST = json.dumps({
    "name": "Claude Launcher",
    "short_name": "Claude",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#0d1117",
    "theme_color": "#0d1117",
    "icons": [{"src": "/icon.png", "sizes": "192x192", "type": "image/png"}]
})


def get_local_ip():
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


_lock = threading.Lock()


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/":
            self._send(200, "text/html; charset=utf-8", PWA_HTML.encode())
        elif path == "/manifest.json":
            self._send(200, "application/json", MANIFEST.encode())
        elif path == "/api/workspaces":
            self._api_workspaces()
        else:
            self._send(404, "text/plain", b"Not found")

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        if path == "/api/start":
            self._api_start(body)
        elif path == "/api/config/toggle":
            self._api_config_toggle(body)
        else:
            self._send(404, "text/plain", b"Not found")

    def _api_workspaces(self):
        with _lock:
            cfg = load_config()
        workspaces = scan_workspaces(cfg)
        sessions = list_tmux_sessions()
        ip = get_local_ip()
        result = []
        for w in workspaces:
            result.append({
                "name": w["name"],
                "path": w["path"],
                "pinned": w["name"] in cfg.get("pinned", []),
                "running": session_name(w["name"]) in sessions,
            })
        data = json.dumps({
            "workspaces": result,
            "ip": ip,
            "port": cfg.get("port", 8765),
            "config": cfg
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
                # 互斥：加入 hidden 时从 pinned 移除，反之亦然
                other = "pinned" if key == "hidden" else "hidden"
                if name in cfg.get(other, []):
                    cfg[other].remove(name)
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


if __name__ == "__main__":
    cfg = load_config()
    port = cfg.get("port", 8765)
    ip = get_local_ip()
    print(f"Claude Launcher running on http://{ip}:{port}")
    print(f"Local:   http://localhost:{port}")
    http.server.HTTPServer(("0.0.0.0", port), Handler).serve_forever()
