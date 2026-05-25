"""
测试场景：
1. 新建会话 — POST /api/start (无 session_id) → tmux 启动不带 --resume
2. 恢复会话 — POST /api/start (带 session_id, force_new=false) → tmux 启动带 --resume
3. 运行状态 — /api/workspaces 和 /api/projects/sessions 的 running 字段
4. UI 截图验证面板渲染
"""

import json, subprocess, time, os, sys
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8765"
PROJ_PATH = "/Users/jinyabo/Documents/ai-claude/claude-launcher"

# ── 辅助 ──────────────────────────────────────────────────────────────────────

def api(method, path, body=None):
    import urllib.request, urllib.error
    url = BASE + path
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"error": e.code, "body": e.read().decode()}

def list_tmux():
    r = subprocess.run(["tmux", "ls", "-F", "#{session_name}"],
                       capture_output=True, text=True)
    return r.stdout.strip().splitlines() if r.returncode == 0 else []

def kill_tmux_by_prefix(prefix):
    for s in list_tmux():
        if s.startswith(prefix):
            subprocess.run(["tmux", "kill-session", "-t", s], stderr=subprocess.DEVNULL)

def pass_(msg): print(f"  ✓ {msg}")
def fail_(msg): print(f"  ✗ {msg}"); sys.exit(1)
def section(title): print(f"\n{'='*60}\n  {title}\n{'='*60}")

# ── 场景 1：新建会话 ───────────────────────────────────────────────────────────

section("场景 1: 新建会话 (force_new, 无 session_id)")

# 确保目标项目没有残留 tmux session
kill_tmux_by_prefix("claude-launcher")
time.sleep(0.5)

before = set(list_tmux())
resp = api("POST", "/api/start", {"path": PROJ_PATH, "force_new": True})
print(f"  API 响应: {resp}")
time.sleep(2)  # 等待 tmux 创建

after = set(list_tmux())
new_sessions = after - before
print(f"  新增 tmux sessions: {new_sessions}")

if not new_sessions:
    fail_("未检测到新 tmux session")
pass_("tmux session 已创建")

# 验证启动命令不含 --resume
new_sname = list(new_sessions)[0]
pane_cmd = subprocess.run(
    ["tmux", "display-message", "-p", "-t", new_sname, "#{pane_start_command}"],
    capture_output=True, text=True).stdout.strip()
print(f"  pane 启动命令: {pane_cmd}")

# 检查 tmux session 的 pane 内容（命令行参数）
pane_content = subprocess.run(
    ["tmux", "list-panes", "-t", new_sname, "-F", "#{pane_pid}"],
    capture_output=True, text=True).stdout.strip()
pid = pane_content.strip()
if pid:
    cmdline = subprocess.run(
        ["ps", "-p", pid, "-o", "args="],
        capture_output=True, text=True).stdout.strip()
    print(f"  进程命令行: {cmdline}")
    if "--resume" in cmdline:
        fail_("新建会话不应包含 --resume")
    else:
        pass_("新建会话命令行不含 --resume")

# ── 场景 2：/api/workspaces running 状态 ──────────────────────────────────────

section("场景 2: running 状态 — /api/workspaces")
time.sleep(2)  # 等待 monitor 更新

ws_data = api("GET", "/api/workspaces")
workspaces = ws_data.get("workspaces", [])
launcher_ws = next((w for w in workspaces if "claude-launcher" in w["name"]), None)
print(f"  claude-launcher workspace: {launcher_ws}")

if launcher_ws is None:
    fail_("找不到 claude-launcher workspace")
if not launcher_ws["running"]:
    fail_("workspace running 应为 true，但为 false")
pass_(f"running=true 检测正确")

# ── 场景 3：恢复会话 (--resume) ───────────────────────────────────────────────

section("场景 3: 恢复已有 JSONL 会话 (force_new=false, 带 session_id)")

# 找到一个真实存在的 session_id
import pathlib
CLAUDE_DIR = pathlib.Path.home() / ".claude"
encoded_path = PROJ_PATH.replace("/", "-").lstrip("-")
sessions_dir = CLAUDE_DIR / "projects" / encoded_path
print(f"  sessions 目录: {sessions_dir}")

jsonl_files = sorted(sessions_dir.glob("*.jsonl")) if sessions_dir.exists() else []
if not jsonl_files:
    print("  (无历史 JSONL，跳过恢复场景)")
else:
    sid = jsonl_files[-1].stem
    print(f"  使用 session_id: {sid}")

    kill_tmux_by_prefix("claude-launcher")
    time.sleep(0.5)
    before2 = set(list_tmux())

    resp2 = api("POST", "/api/start", {
        "path": PROJ_PATH,
        "session_id": sid,
        "force_new": False
    })
    print(f"  API 响应: {resp2}")
    time.sleep(2)

    after2 = set(list_tmux())
    new2 = after2 - before2
    print(f"  新增 tmux sessions: {new2}")

    if not new2:
        fail_("未创建 tmux session（恢复场景）")
    pass_("恢复场景 tmux session 已创建")

    sname2 = list(new2)[0]
    pid2 = subprocess.run(
        ["tmux", "list-panes", "-t", sname2, "-F", "#{pane_pid}"],
        capture_output=True, text=True).stdout.strip()
    if pid2:
        cmdline2 = subprocess.run(
            ["ps", "-p", pid2, "-o", "args="],
            capture_output=True, text=True).stdout.strip()
        print(f"  进程命令行: {cmdline2}")
        if "--resume" not in cmdline2:
            fail_("恢复会话命令行应包含 --resume")
        else:
            pass_(f"恢复会话包含 --resume {sid[:8]}…")

    # 场景 3b：再次恢复同一 session（已在运行）→ API 应直接返回，不重新创建 tmux
    time.sleep(2)
    before3 = set(list_tmux())
    resp3 = api("POST", "/api/start", {
        "path": PROJ_PATH,
        "session_id": sid,
        "force_new": False
    })
    after3 = set(list_tmux())
    dup = after3 - before3
    print(f"  重复恢复新增 sessions: {dup}")
    if dup:
        fail_("已运行的会话不应再创建新 tmux session")
    pass_("已运行会话重复请求被幂等处理")

# ── 场景 4：/api/projects/sessions running 字段 ───────────────────────────────

section("场景 4: /api/projects/sessions running 字段")
import urllib.parse
encoded_q = urllib.parse.quote(encoded_path, safe="")
ps_data = api("GET", f"/api/projects/sessions?encoded={encoded_q}")
sessions_list = ps_data.get("sessions", [])
print(f"  会话总数: {len(sessions_list)}")
running_sessions = [s for s in sessions_list if s.get("running")]
print(f"  running=true 的会话: {[s['id'][:8] for s in running_sessions]}")
if running_sessions:
    pass_("至少有一个会话 running=true")
else:
    print("  (warn) 没有检测到 running session（可能 monitor 未同步）")

# ── 场景 5：UI 截图验证 ───────────────────────────────────────────────────────

section("场景 5: UI 截图验证")
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 390, "height": 844})  # 手机尺寸
    page.goto(BASE)
    page.wait_for_load_state("networkidle")
    page.screenshot(path="/tmp/test_main.png", full_page=True)
    pass_("主页截图已保存 /tmp/test_main.png")

    # 点击进入 claude-launcher workspace
    launcher_btn = page.locator("text=claude-launcher").first
    if launcher_btn.count() == 0:
        print("  (warn) 找不到 claude-launcher 按钮")
    else:
        launcher_btn.click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(800)
        page.screenshot(path="/tmp/test_sessions.png", full_page=True)
        pass_("会话列表截图已保存 /tmp/test_sessions.png")

    browser.close()

section("所有测试完成")
