"""
Launcher 基准测试
=================
T1  proxy env 传递 — 启动 session 后 claude 进程是否带代理变量
T2  API 连通性     — curl 直接走代理能否访问 Anthropic API
T3  remote control — 启动后 RC 能否握手（看 JSONL 写入）
T4  新建会话完整流程
T5  恢复会话完整流程
T6  running 状态同步
"""

import json, os, pathlib, subprocess, sys, time, urllib.request, urllib.parse

BASE = "http://localhost:8765"
PROJ = "/Users/jinyabo/Documents/ai-claude/claude-launcher"
PROJ2 = "/Users/jinyabo/Documents/ai-claude"
CLAUDE_DIR = pathlib.Path.home() / ".claude"
CFG_FILE = pathlib.Path(__file__).parent / "config.json"

PASS, FAIL, WARN = "✓", "✗", "⚠"
results = []

def check(label, ok, detail=""):
    sym = PASS if ok else FAIL
    print(f"  {sym} {label}" + (f"  [{detail}]" % () if detail else ""))
    results.append((label, ok))
    return ok

def warn(label, detail=""):
    print(f"  {WARN} {label}" + (f"  [{detail}]" if detail else ""))

def section(title):
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")

def api(method, path, body=None):
    url = BASE + path
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read())

def tmux_sessions():
    r = subprocess.run(["tmux", "ls", "-F", "#{session_name}"],
                       capture_output=True, text=True)
    return r.stdout.strip().splitlines() if r.returncode == 0 else []

def kill_prefix(prefix):
    for s in tmux_sessions():
        if s.startswith(prefix):
            subprocess.run(["tmux", "kill-session", "-t", s], stderr=subprocess.DEVNULL)

def wait_monitor(timeout=6):
    smap = CLAUDE_DIR / "launcher_sessions.json"
    for _ in range(timeout * 5):
        try:
            if not json.loads(smap.read_text()):
                return
        except Exception:
            return
        time.sleep(0.2)

def get_pane_pid(sname):
    return subprocess.run(["tmux", "list-panes", "-t", sname, "-F", "#{pane_pid}"],
                          capture_output=True, text=True).stdout.strip()

def get_proc_env_proxy(pid):
    """macOS: ps eww to get environment"""
    r = subprocess.run(["ps", "eww", "-p", pid], capture_output=True, text=True)
    return [tok for tok in r.stdout.split() if "PROXY" in tok.upper()]

def get_cmdline(sname):
    pid = get_pane_pid(sname)
    if not pid:
        return ""
    return subprocess.run(["ps", "-p", pid, "-o", "args="],
                          capture_output=True, text=True).stdout.strip()

# ═══════════════════════════════════════════════════════════════
section("T1: proxy env 传递")
# ═══════════════════════════════════════════════════════════════

cfg = json.loads(CFG_FILE.read_text())
claude_env = cfg.get("claude_env", {})
print(f"  config.json claude_env: {list(claude_env.keys())}")
check("T1.1 config 包含 HTTPS_PROXY", "HTTPS_PROXY" in claude_env)

# 启动一个 shell session 验证 env 传递机制
MARKER = f"LAUNCHER_PROXY_TEST={claude_env.get('HTTPS_PROXY','')}"
subprocess.Popen(
    ["tmux", "new-session", "-d", "-s", "test_env_probe", "-c", "/tmp",
     "sh", "-c", f"env | grep PROXY > /tmp/launcher_env_probe.txt"],
    env={**os.environ, **claude_env},
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
time.sleep(0.8)
probe_output = pathlib.Path("/tmp/launcher_env_probe.txt").read_text() if pathlib.Path("/tmp/launcher_env_probe.txt").exists() else ""
subprocess.run(["tmux", "kill-session", "-t", "test_env_probe"], stderr=subprocess.DEVNULL)
print(f"  probe 输出: {probe_output.strip()!r}")
warn("T1.2 subprocess.Popen env= 传入 tmux session (已知无效，用 -e 替代)",
     "env= 只影响 tmux client，不传入 pane" if "PROXY" not in probe_output else "ok")

# 正确方式：通过 tmux -e 传递
subprocess.Popen(
    ["tmux", "new-session", "-d", "-s", "test_env_probe2", "-c", "/tmp"]
    + [arg for k, v in claude_env.items() for arg in ["-e", f"{k}={v}"]]
    + ["sh", "-c", "env | grep PROXY > /tmp/launcher_env_probe2.txt"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
time.sleep(0.8)
probe2 = pathlib.Path("/tmp/launcher_env_probe2.txt").read_text() if pathlib.Path("/tmp/launcher_env_probe2.txt").exists() else ""
subprocess.run(["tmux", "kill-session", "-t", "test_env_probe2"], stderr=subprocess.DEVNULL)
print(f"  tmux -e 方式输出: {probe2.strip()!r}")
check("T1.3 tmux -e 传递代理变量", "PROXY" in probe2)

# ═══════════════════════════════════════════════════════════════
section("T2: Anthropic API 直连测试（走代理）")
# ═══════════════════════════════════════════════════════════════

proxy = claude_env.get("HTTPS_PROXY", "")
print(f"  代理: {proxy}")

# curl 测试代理连通
r = subprocess.run(
    ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
     "--proxy", proxy, "--max-time", "8",
     "https://api.anthropic.com/"],
    capture_output=True, text=True
)
http_code = r.stdout.strip()
print(f"  curl → api.anthropic.com HTTP {http_code}")
check("T2.1 代理可达 Anthropic API", http_code not in ("000", ""),
      f"http {http_code} — 000 表示代理无响应")

# ═══════════════════════════════════════════════════════════════
section("T3: 新建会话 + env 传递实测")
# ═══════════════════════════════════════════════════════════════

kill_prefix("ai-claude_claude-launcher")
wait_monitor()

before = set(tmux_sessions())
api("POST", "/api/start", {"path": PROJ, "force_new": True})
time.sleep(2)
new = set(tmux_sessions()) - before
print(f"  新增 session: {new}")

if check("T3.1 tmux session 已创建", bool(new)):
    sname = list(new)[0]
    pid = get_pane_pid(sname)
    print(f"  pane pid: {pid}")
    cmdline = get_cmdline(sname)
    print(f"  cmdline: {cmdline}")
    check("T3.2 命令含 --remote-control", "--remote-control" in cmdline)

    proxy_in_env = get_proc_env_proxy(pid)
    print(f"  进程代理环境变量: {proxy_in_env}")
    check("T3.3 claude 进程继承代理变量",
          bool(proxy_in_env),
          "缺失 — subprocess.Popen env= 未传入 tmux pane" if not proxy_in_env else "ok")

# ═══════════════════════════════════════════════════════════════
section("T4: remote control 握手（pane 状态检查）")
# ═══════════════════════════════════════════════════════════════
# --remote-control 新 session 在收到第一条消息前不写 JSONL，
# 改为检查 pane 内容是否出现 "Remote Control active"。

if new:  # new is the set from T3
    sname_t4 = list(new)[0]
    rc_active = False
    t0 = time.time()
    while time.time() - t0 < 30:
        pane = subprocess.run(
            ["tmux", "capture-pane", "-t", sname_t4, "-p"],
            capture_output=True, text=True).stdout
        if "Remote Control active" in pane or "remote-control is active" in pane.lower():
            rc_active = True
            break
        time.sleep(1)

    print(f"  等待 {time.time()-t0:.0f}s 后检测")
    check("T4.1 pane 显示 Remote Control active", rc_active,
          "未检测到 RC 激活 — 可能认证或代理失败")

    # 检查状态栏有无 "no proxy" 警告
    pane_final = subprocess.run(
        ["tmux", "capture-pane", "-t", sname_t4, "-p"],
        capture_output=True, text=True).stdout
    no_proxy_warn = "no proxy" in pane_final.lower() or "🚫" in pane_final
    print(f"  状态栏代理警告: {'有 🚫 no proxy' if no_proxy_warn else '无（代理正常）'}")
    check("T4.2 状态栏无 no proxy 警告", not no_proxy_warn)
else:
    check("T4.1 pane 显示 Remote Control active", False, "T3 未创建 session，跳过")
    check("T4.2 状态栏无 no proxy 警告", False, "N/A")

# ═══════════════════════════════════════════════════════════════
section("T5: 恢复会话")
# ═══════════════════════════════════════════════════════════════

sid_dir = CLAUDE_DIR / "projects" / "-Users-jinyabo-Documents-ai-claude"
jsonl_files = sorted(sid_dir.glob("*.jsonl")) if sid_dir.exists() else []
SID = jsonl_files[-1].stem if jsonl_files else None

if SID:
    kill_prefix("Documents_ai-claude")
    wait_monitor()
    before = set(tmux_sessions())
    api("POST", "/api/start", {"path": PROJ2, "session_id": SID, "force_new": False})
    time.sleep(2)
    new = set(tmux_sessions()) - before
    print(f"  新增 session: {new}")

    if check("T5.1 恢复 session 已创建", bool(new)):
        sname2 = list(new)[0]
        cmd2 = get_cmdline(sname2)
        print(f"  cmdline: {cmd2}")
        check("T5.2 含 --resume", "--resume" in cmd2)
        check("T5.3 含 --remote-control", "--remote-control" in cmd2)
        pid2 = get_pane_pid(sname2)
        proxy2 = get_proc_env_proxy(pid2)
        print(f"  进程代理环境变量: {proxy2}")
        check("T5.4 恢复 session 继承代理变量", bool(proxy2),
              "缺失" if not proxy2 else "ok")
    kill_prefix("Documents_ai-claude")
    wait_monitor()
else:
    warn("T5 无历史 JSONL，跳过恢复场景")

# ═══════════════════════════════════════════════════════════════
section("T6: running 状态同步")
# ═══════════════════════════════════════════════════════════════

time.sleep(2)
ws_data = api("GET", "/api/workspaces")
ws = next((w for w in ws_data["workspaces"] if "claude-launcher" in w["name"]), None)
print(f"  claude-launcher: {ws}")
check("T6.1 workspace running=true（有 tmux session）",
      ws is not None and ws["running"])

kill_prefix("ai-claude_claude-launcher")
wait_monitor(8)
ws_data2 = api("GET", "/api/workspaces")
ws2 = next((w for w in ws_data2["workspaces"] if "claude-launcher" in w["name"]), None)
print(f"  kill 后 claude-launcher: {ws2}")
check("T6.2 kill 后 running=false", ws2 is not None and not ws2["running"])

# ═══════════════════════════════════════════════════════════════
section("汇总")
# ═══════════════════════════════════════════════════════════════
passed = sum(1 for _, ok in results if ok)
failed = [(l, ok) for l, ok in results if not ok]
print(f"\n  通过: {passed}/{len(results)}")
if failed:
    print(f"  失败项:")
    for l, _ in failed:
        print(f"    {FAIL} {l}")
else:
    print(f"  全部通过")

sys.exit(0 if not failed else 1)
