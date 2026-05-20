#!/usr/bin/env python3
"""Claude Workspace Launcher — LAN-accessible PWA to start claude sessions by directory."""

import base64
import http.server
import json
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


def check_internet():
    """Check if Mac has internet access by attempting a TCP connection."""
    import socket
    try:
        socket.setdefaulttimeout(2)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
        return True
    except Exception:
        return False


ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="192" height="192" viewBox="0 0 192 192">
  <rect width="192" height="192" rx="42" fill="#1a1a2e"/>
  <text x="96" y="130" font-size="110" text-anchor="middle" font-family="system-ui">⚡</text>
</svg>"""
ICON_B64 = base64.b64encode(ICON_SVG.encode()).decode()
ICON_DATA = f"data:image/svg+xml;base64,{ICON_B64}"

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
    --green: #3fb950; --orange: #d29922; --red: #da3633;
    --radius: 12px;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif;
    background: var(--bg); color: var(--text);
    min-height: 100dvh; padding-bottom: env(safe-area-inset-bottom);
  }

  /* Network banner */
  .net-banner {
    display: none; position: sticky; top: 0; z-index: 20;
    padding: 9px 16px; font-size: 13px; font-weight: 500;
    text-align: center; gap: 6px; align-items: center; justify-content: center;
  }
  .net-banner.show { display: flex; }
  .net-banner.lan-down  { background: #3d1a1a; color: #f85149; border-bottom: 1px solid rgba(248,81,73,.3); }
  .net-banner.inet-warn { background: #2d2200; color: var(--orange); border-bottom: 1px solid rgba(210,153,34,.3); }
  .net-dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; flex-shrink: 0; }

  header {
    position: sticky; top: 0; z-index: 10;
    background: rgba(13,17,23,0.88); backdrop-filter: blur(14px);
    padding: 14px 18px 11px; border-bottom: 1px solid var(--border);
    display: flex; justify-content: space-between; align-items: center;
  }
  header h1 { font-size: 19px; font-weight: 600; }
  .header-meta {
    display: flex; align-items: center; gap: 8px; margin-top: 3px;
  }
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

  .settings-btn {
    background: none; border: 1px solid var(--border); border-radius: 8px;
    color: var(--sub); padding: 6px 12px; font-size: 13px; cursor: pointer;
    flex-shrink: 0;
  }
  .settings-btn:active { background: var(--card); }

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

  .overlay, .settings-overlay {
    display: none; position: fixed; inset: 0;
    background: rgba(0,0,0,.55); backdrop-filter: blur(4px);
    z-index: 100; align-items: flex-end; justify-content: center;
  }
  .overlay.show, .settings-overlay.show { display: flex; }
  .modal, .settings-panel {
    background: var(--card); border: 1px solid var(--border);
    border-radius: 20px 20px 0 0; width: 100%; max-width: 520px;
    padding: 24px 20px calc(24px + env(safe-area-inset-bottom));
  }
  .settings-panel { max-height: 75dvh; overflow-y: auto; }
  .modal h2, .settings-panel h2 { font-size: 17px; font-weight: 600; margin-bottom: 6px; }
  .modal p { font-size: 14px; color: var(--sub); margin-bottom: 20px; }

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

  .empty { color: var(--sub); text-align: center; padding: 48px 20px; line-height: 1.8; }
</style>
</head>
<body>

<!-- Network status banner (shown only on problems) -->
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
        <span id="net-pill-text">检测中</span>
      </span>
    </div>
  </div>
  <button class="settings-btn" id="settings-btn">管理</button>
</header>
<main id="main">
  <div class="empty">加载中...</div>
</main>

<div class="overlay" id="modal">
  <div class="modal">
    <h2 id="modal-title"></h2>
    <p id="modal-desc"></p>
    <button class="btn btn-primary" id="btn-reuse">继续使用现有会话</button>
    <button class="btn btn-danger"  id="btn-new">终止并新建会话</button>
    <button class="btn btn-cancel"  id="btn-cancel-modal">取消</button>
  </div>
</div>

<div class="settings-overlay" id="settings-overlay">
  <div class="settings-panel">
    <h2>工作空间管理</h2>
    <p style="font-size:13px;color:var(--sub);margin-bottom:16px">置顶常用项目，隐藏不需要显示的目录</p>
    <div id="settings-list"></div>
    <br>
    <button class="btn btn-cancel" id="btn-close-settings">关闭</button>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
let workspaces = [];
let activeName = null;
let loadingCards = new Set();

// ── Network detection ─────────────────────────────────────────────
const netState = { lan: true, inet: true };

async function checkNetwork() {
  // LAN: can we reach the server?
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
  const pill = document.getElementById('net-pill');
  const pillText = document.getElementById('net-pill-text');
  const banner = document.getElementById('net-banner');
  const bannerMsg = document.getElementById('net-banner-msg');

  if (!netState.lan) {
    pill.className = 'net-pill bad';
    pillText.textContent = '断连';
    banner.className = 'net-banner show lan-down';
    bannerMsg.textContent = '无法连接到 Mac，请检查局域网连接';
    return;
  }
  if (!netState.inet) {
    pill.className = 'net-pill warn';
    pillText.textContent = '无外网';
    banner.className = 'net-banner show inet-warn';
    bannerMsg.textContent = 'Mac 当前无互联网连接，Claude 可能无法运行';
    return;
  }
  pill.className = 'net-pill ok';
  pillText.textContent = '正常';
  banner.className = 'net-banner';
}

// Browser-level offline detection
window.addEventListener('offline', () => {
  netState.lan = false; updateNetUI();
  showToast('网络已断开', 'warn');
});
window.addEventListener('online', () => {
  checkNetwork();
  showToast('网络已恢复', 'info');
});

// ── Data ──────────────────────────────────────────────────────────
async function load() {
  try {
    const res = await fetch('/api/workspaces');
    const data = await res.json();
    workspaces = data.workspaces;
    document.getElementById('ip-hint').textContent =
      `局域网 · ${data.ip}:${data.port}`;
    render();
  } catch(e) {
    netState.lan = false; updateNetUI();
  }
}

// ── Render ────────────────────────────────────────────────────────
function render() {
  const pinned = workspaces.filter(w => w.pinned);
  const rest   = workspaces.filter(w => !w.pinned);
  let html = '';

  if (!workspaces.length) {
    document.getElementById('main').innerHTML =
      '<div class="empty">未找到工作空间<br><small>目录需包含 CLAUDE.md 文件</small></div>';
    return;
  }

  const anyRunning = workspaces.some(w => w.running);
  if (!anyRunning) {
    html += `<div class="guide">
      <strong>使用方式</strong>
      <ol>
        <li>点击项目启动 Claude 会话</li>
        <li>打开 <strong>Claude App</strong> → 底部 <strong>Code</strong> 标签</li>
        <li>找到同名会话（绿点）点击连接</li>
      </ol>
    </div>`;
  }

  if (pinned.length) {
    html += '<div class="section-label">📌 置顶</div>';
    html += pinned.map(cardHTML).join('');
  }
  if (rest.length) {
    html += `<div class="section-label">${pinned.length ? '其他' : '全部'} 工作空间</div>`;
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
  const dotClass = loading ? 'spinning' : (w.running ? 'on' : 'off');
  const cardClass = loading ? 'loading' : (w.running ? 'running' : '');
  const ne = escAttr(w.name), nh = escHTML(w.name);
  return `<div class="card ${cardClass}" data-name="${ne}">
    <div class="card-left">
      <div class="card-name">${nh}</div>
      <div class="card-path">${escHTML(w.short_path)}</div>
    </div>
    <div class="card-right">
      <button class="stop-btn" data-name="${ne}">停止</button>
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

// ── Actions ───────────────────────────────────────────────────────
function tap(name) {
  activeName = name;
  const ws = workspaces.find(w => w.name === name);
  if (!ws) return;
  if (ws.running) {
    document.getElementById('modal-title').textContent = ws.name;
    document.getElementById('modal-desc').textContent =
      '该工作空间已有运行中的 Claude 会话，你想怎么处理？';
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
  showToast('前往 Claude App → Code 标签连接', 'info');
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
  showToast(`已停止 ${name}`, 'info');
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
          showToast(`✓ ${name} 已启动 → Claude App → Code 标签`, 'success');
      }
    } catch { clearInterval(poll); setLoading(name, false); }
  }, 1000);
}

function setLoading(name, val) {
  if (val) loadingCards.add(name); else loadingCards.delete(name);
  render();
}

// ── Settings ──────────────────────────────────────────────────────
async function openSettings() {
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
          data-action="pin" data-name="${escAttr(w.name)}">置顶</button>
        <button class="tag-btn ${isHidden ? 'active-hide' : ''}"
          data-action="hide" data-name="${escAttr(w.name)}">隐藏</button>
      </div>
    </div>`;
  }).join('');
  document.getElementById('settings-list').innerHTML = html || '<div style="color:var(--sub)">暂无工作空间</div>';
  document.getElementById('settings-overlay').classList.add('show');
}

document.getElementById('settings-list').addEventListener('click', async e => {
  const btn = e.target.closest('[data-action]');
  if (!btn) return;
  await post('/api/config/toggle', {
    key: btn.dataset.action === 'pin' ? 'pinned' : 'hidden',
    name: btn.dataset.name
  });
  openSettings();
});

function closeSettings() {
  document.getElementById('settings-overlay').classList.remove('show');
  load();
}

// ── Wiring ────────────────────────────────────────────────────────
document.getElementById('settings-btn').addEventListener('click', openSettings);
document.getElementById('btn-reuse').addEventListener('click', doReuse);
document.getElementById('btn-new').addEventListener('click', doNew);
document.getElementById('btn-cancel-modal').addEventListener('click', closeModal);
document.getElementById('btn-close-settings').addEventListener('click', closeSettings);
document.getElementById('modal').addEventListener('click',
  e => { if (e.target.id === 'modal') closeModal(); });
document.getElementById('settings-overlay').addEventListener('click',
  e => { if (e.target.id === 'settings-overlay') closeSettings(); });

// ── Utils ─────────────────────────────────────────────────────────
async function post(url, body) {
  return fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
}

function showToast(msg, type = '') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast show' + (type ? ' ' + type : '');
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove('show'), 3200);
}

function escHTML(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function escAttr(s) {
  return String(s).replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

// ── Boot ──────────────────────────────────────────────────────────
checkNetwork();
load();
setInterval(load, 15000);
setInterval(checkNetwork, 20000);
</script>
</body>
</html>"""


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
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        if path == "/":
            self._send(200, "text/html; charset=utf-8", PWA_HTML.encode())
        elif path == "/manifest.json":
            self._send(200, "application/json", _manifest(ICON_DATA).encode())
        elif path == "/icon.png":
            self._send(200, "image/svg+xml", ICON_SVG.encode())
        elif path == "/api/workspaces":
            include_all = query.get("all", ["0"])[0] == "1"
            self._api_workspaces(include_all)
        elif path == "/api/health":
            self._api_health()
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
        else:
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
    print(f"Claude Launcher  http://{ip}:{port}")
    print(f"Local            http://localhost:{port}")
    http.server.HTTPServer(("0.0.0.0", port), Handler).serve_forever()
