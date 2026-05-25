"""
恢复会话功能测试

测试场景:
1. 无其他会话运行时恢复指定会话 → tmux 带 --resume <id> 启动
2. 同项目另一会话正在运行时恢复指定会话 → 仍然启动新 tmux 带 --resume（BUG 修复验证）
3. 指定会话本身正在运行时再次点击恢复 → 不重复启动（幂等）
"""

import json, subprocess, time, os, sys, re

BASE = "http://localhost:8765"
PROJ_PATH = "/Users/jinyabo/Documents/ai-claude/claude-launcher"

# ── 辅助函数 ──────────────────────────────────────────────────────────────────

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

def kill_tmux(name):
    subprocess.run(["tmux", "kill-session", "-t", name],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def kill_tmux_by_prefix(prefix):
    for s in list_tmux():
        if s.startswith(prefix):
            kill_tmux(s)

def new_tmux_by_prefix(prefix, before_set):
    after = set(list_tmux())
    new = [s for s in after - before_set if s.startswith(prefix)]
    return new

def load_session_map():
    import pathlib
    p = pathlib.Path.home() / '.claude' / 'launcher_sessions.json'
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}

def get_sessions_for_project(encoded):
    r = api("GET", f"/api/projects/sessions?encoded={encoded}")
    return r.get("sessions", [])

def encode_path(path):
    """Mirror server-side _encode_path."""
    return '-' + re.sub(r'[^a-zA-Z0-9]', '-', path[1:])

def section(title):
    print(f"\n{'='*60}\n  {title}\n{'='*60}")

def pass_(msg): print(f"  ✓ {msg}")
def fail_(msg): print(f"  ✗ {msg}"); sys.exit(1)

ENCODED = encode_path(PROJ_PATH)
PREFIX = "ai-claude_claude-launcher"  # _path_base for this project

# ── 场景 1: 无运行会话时恢复 ───────────────────────────────────────────────────

section("场景 1: 无其他会话运行时恢复指定会话")

kill_tmux_by_prefix(PREFIX)
time.sleep(3)  # 等待 monitor 清理 session map

sessions = get_sessions_for_project(ENCODED)
if not sessions:
    print("  跳过（该项目无历史会话）")
else:
    target = sessions[0]
    sid = target["id"]
    print(f"  目标会话: {sid[:8]}... running={target['running']}")

    # 确认无运行会话
    running_before = [s for s in sessions if s["running"]]
    if running_before:
        fail_(f"前置条件失败: 仍有运行中的会话 {[s['id'][:8] for s in running_before]}")

    before = set(list_tmux())
    resp = api("POST", "/api/start", {"path": PROJ_PATH, "session_id": sid, "force_new": False})
    print(f"  API 响应: {resp}")
    time.sleep(2)

    new = new_tmux_by_prefix(PREFIX, before)
    if new:
        pass_(f"新 tmux session 已创建: {new}")
    else:
        fail_("未创建新 tmux session")

    # 验证 session map 中注册了该 session_id
    time.sleep(3)  # 等待 monitor 解析 JSONL
    m = load_session_map()
    if sid in m:
        pass_(f"session_id 已注册到 launcher_sessions.json: {m[sid]}")
    else:
        print(f"  ⚠ session_id 暂未注册（tmux 可能还没写 JSONL，非致命）")

    # 清理
    kill_tmux_by_prefix(PREFIX)
    time.sleep(3)

# ── 场景 2: 同项目另一会话正在运行时恢复（主要 BUG）─────────────────────────

section("场景 2: 同项目另一会话运行时恢复指定会话（BUG 修复验证）")

kill_tmux_by_prefix(PREFIX)
time.sleep(3)

sessions = get_sessions_for_project(ENCODED)
if len(sessions) < 2:
    print("  跳过（需要至少 2 个历史会话）")
else:
    s1 = sessions[0]
    s2 = sessions[1]
    print(f"  会话 A (先启动): {s1['id'][:8]}...")
    print(f"  会话 B (待恢复): {s2['id'][:8]}...")

    # 先启动会话 A（模拟另一会话正在运行）
    before1 = set(list_tmux())
    api("POST", "/api/start", {"path": PROJ_PATH, "session_id": s1["id"], "force_new": False})
    time.sleep(2)
    a_sessions = new_tmux_by_prefix(PREFIX, before1)
    if not a_sessions:
        fail_("前置: 会话 A 未启动")
    print(f"  会话 A tmux: {a_sessions[0]}")

    # 现在恢复会话 B（BUG: 之前这里会因 path-prefix fallback 而静默失败）
    before2 = set(list_tmux())
    resp = api("POST", "/api/start", {"path": PROJ_PATH, "session_id": s2["id"], "force_new": False})
    print(f"  恢复会话 B 的 API 响应: {resp}")
    time.sleep(2)

    b_sessions = new_tmux_by_prefix(PREFIX, before2)
    if b_sessions:
        pass_(f"会话 B 成功创建新 tmux session: {b_sessions[0]}（BUG 已修复）")
    else:
        fail_("会话 B 未创建新 tmux session（BUG 未修复: path-prefix fallback 阻止了 resume）")

    # 清理
    kill_tmux_by_prefix(PREFIX)
    time.sleep(3)

# ── 场景 3: 指定会话本身正在运行时幂等 ────────────────────────────────────────

section("场景 3: 指定会话正在运行时再次恢复（幂等）")

kill_tmux_by_prefix(PREFIX)
time.sleep(3)

sessions = get_sessions_for_project(ENCODED)
if not sessions:
    print("  跳过（无历史会话）")
else:
    sid = sessions[0]["id"]

    # 启动会话
    before = set(list_tmux())
    api("POST", "/api/start", {"path": PROJ_PATH, "session_id": sid, "force_new": False})
    time.sleep(3)
    m = load_session_map()

    if sid not in m:
        print("  ⚠ session_id 暂未注册，跳过幂等性测试")
    else:
        # 再次恢复同一会话
        before2 = set(list_tmux())
        api("POST", "/api/start", {"path": PROJ_PATH, "session_id": sid, "force_new": False})
        time.sleep(1)

        extra = new_tmux_by_prefix(PREFIX, before2)
        if not extra:
            pass_("幂等: 未重复创建 tmux session")
        else:
            fail_(f"非幂等: 创建了多余的 tmux session {extra}")

    kill_tmux_by_prefix(PREFIX)
    time.sleep(2)

print("\n✅ 所有测试完成\n")
