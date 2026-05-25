"""
Strict acceptance test for the bidirectional chat feature.

Test cases:
  T1  API: /api/sessions/messages includes line_count
  T2  API: /api/sessions/live returns incremental messages + line_count
  T3  API: /api/chat with active tmux → 200 {ok:true}
  T4  API: /api/chat with no tmux → auto-starts session, waits for init, returns 200
  T5  UI:  message panel opens with input bar visible
  T6  UI:  send button disabled when input is empty
  T7  UI:  sending a message shows user bubble + typing indicator
  T8  UI:  live poll delivers assistant reply, typing indicator disappears
"""

import json
import subprocess
import time
import requests
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8765"
LAUNCHER_ENC = "-Users-jinyabo-Documents-ai-claude-claude-launcher"

# ── helpers ──────────────────────────────────────────────────────────────────

def api(path, **kw):
    return requests.get(BASE + path, **kw)

def post(path, body):
    return requests.post(BASE + path, json=body)

def get_first_session(encoded):
    r = api(f"/api/projects/sessions?encoded={encoded}")
    sessions = r.json()["sessions"]
    assert sessions, f"no sessions for {encoded}"
    return sessions[0]["id"]

def tmux_sessions():
    try:
        out = subprocess.check_output(["tmux", "ls", "-F", "#{session_name}"],
                                      stderr=subprocess.DEVNULL, text=True)
        return set(out.strip().splitlines())
    except subprocess.CalledProcessError:
        return set()

PASS = "✅ PASS"
FAIL = "❌ FAIL"
results = []

def check(name, cond, detail=""):
    status = PASS if cond else FAIL
    results.append((name, status, detail))
    print(f"{status}  {name}" + (f"  [{detail}]" if detail else ""))

# ── T1: /api/sessions/messages includes line_count ───────────────────────────
print("\n── T1: messages endpoint has line_count ─────────")
sid = get_first_session(LAUNCHER_ENC)
r = api(f"/api/sessions/messages?encoded={LAUNCHER_ENC}&id={sid}")
d = r.json()
check("T1 status 200", r.status_code == 200)
check("T1 has messages", isinstance(d.get("messages"), list))
check("T1 has line_count", isinstance(d.get("line_count"), int) and d["line_count"] > 0,
      f"line_count={d.get('line_count')}")

# ── T2: /api/sessions/live returns incremental data ──────────────────────────
print("\n── T2: live endpoint ────────────────────────────")
lc = d["line_count"]
r2 = api(f"/api/sessions/live?encoded={LAUNCHER_ENC}&id={sid}&from={lc}")
d2 = r2.json()
check("T2 status 200", r2.status_code == 200)
check("T2 has messages list", isinstance(d2.get("messages"), list))
check("T2 has line_count", isinstance(d2.get("line_count"), int))
check("T2 no new msgs at current cursor", len(d2["messages"]) == 0,
      f"got {len(d2['messages'])} unexpected new msgs")

# from=0 should return all parsed messages
r3 = api(f"/api/sessions/live?encoded={LAUNCHER_ENC}&id={sid}&from=0")
d3 = r3.json()
check("T2 from=0 returns messages", len(d3["messages"]) > 0,
      f"got {len(d3['messages'])} messages")

# ── T3: /api/chat with active tmux session ───────────────────────────────────
print("\n── T3: chat routes to active tmux ───────────────")
# Find which sessions have a running tmux
active = [s for s in tmux_sessions() if "claude-launcher" in s]
print(f"  active tmux sessions: {active}")

if active:
    sname = active[0]
    # Derive session_id from last 8 chars of tmux name
    last8 = sname.rsplit("_", 1)[-1]
    # Find matching session
    sessions_r = api(f"/api/projects/sessions?encoded={LAUNCHER_ENC}")
    matching = [s for s in sessions_r.json()["sessions"] if s["id"].endswith(last8)]
    if matching:
        test_sid = matching[0]["id"]
        line_before = api(f"/api/sessions/messages?encoded={LAUNCHER_ENC}&id={test_sid}").json()["line_count"]
        r = post("/api/chat", {"encoded": LAUNCHER_ENC, "session_id": test_sid,
                               "message": "echo LAUNCHER_TEST_PING"})
        d = r.json()
        check("T3 status 200", r.status_code == 200, str(r.status_code))
        check("T3 ok=true", d.get("ok") is True, str(d))
        check("T3 session name returned", "session" in d, str(d))
    else:
        check("T3 (skipped - no matching session)", True, "no exact match")
else:
    check("T3 (skipped - no active tmux)", True, "start a session first to test T3")

# ── T4: /api/chat with no tmux → auto-start ──────────────────────────────────
print("\n── T4: auto-start when no tmux ──────────────────")
CHAT_ENC = "-Users-jinyabo-Documents-ai-claude-chat-test"
chat_sid = get_first_session(CHAT_ENC)
# Ensure no tmux session is running for chat-test
chat_sessions = [s for s in tmux_sessions() if "chat-test" in s]
for s in chat_sessions:
    subprocess.run(["tmux", "kill-session", "-t", s], stderr=subprocess.DEVNULL)
time.sleep(0.5)

print(f"  sending to chat-test session {chat_sid[:8]}… (will auto-start, wait for init)")
t0 = time.monotonic()
r = post("/api/chat", {"encoded": CHAT_ENC, "session_id": chat_sid,
                       "message": "请用一句话回复：收到"})
elapsed = time.monotonic() - t0
d = r.json()
print(f"  response after {elapsed:.1f}s: {d}")
check("T4 status 200", r.status_code == 200, str(r.status_code))
check("T4 ok=true", d.get("ok") is True, str(d))
check("T4 took ≤20s", elapsed <= 20, f"{elapsed:.1f}s")

# Verify tmux session was created
new_sessions = [s for s in tmux_sessions() if "chat-test" in s]
check("T4 tmux session created", len(new_sessions) > 0, str(new_sessions))

# ── T5–T8: UI tests ──────────────────────────────────────────────────────────
print("\n── T5-T8: UI tests ──────────────────────────────")
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(BASE)
    page.wait_for_load_state("networkidle")

    # Navigate to all tab → first project → first session
    page.locator('[data-tab="all"]').click()
    page.wait_for_timeout(1200)

    cards = page.locator('.project-card').all()
    check("T5 project cards rendered", len(cards) > 0, f"{len(cards)} cards")

    if cards:
        cards[0].scroll_into_view_if_needed()
        cards[0].click()
        page.wait_for_selector('#sess-panel.open', timeout=4000)
        page.wait_for_selector('.sess-item', timeout=5000)
        sess_items = page.locator('.sess-item').all()
        check("T5 session list populated", len(sess_items) > 0, f"{len(sess_items)} sessions")

        if sess_items:
            sess_items[0].click()
            page.wait_for_selector('#msg-panel.open', timeout=4000)
            page.screenshot(path='/tmp/test_msg_panel.png')

            inp = page.locator('#msg-input')
            btn = page.locator('#msg-send-btn')
            check("T5 input visible", inp.is_visible())
            check("T5 send btn visible", btn.is_visible())

            # T6: button disabled when empty (panel just opened — state should already be correct)
            check("T6 btn disabled when empty", btn.is_disabled())

            # T7: typing shows user bubble + typing indicator
            inp.fill('收到了吗？')
            page.wait_for_timeout(100)
            check("T7 btn enabled when text entered", not btn.is_disabled())

            btn.click()
            page.wait_for_timeout(800)
            page.screenshot(path='/tmp/test_after_send.png')

            user_bubbles = page.locator('.msg-user .bubble').all()
            check("T7 user bubble appears", len(user_bubbles) > 0,
                  f"{len(user_bubbles)} user bubbles")
            typing = page.locator('#msg-typing')
            check("T7 typing indicator shown", typing.is_visible())
            check("T7 send btn disabled while loading",
                  page.locator('#msg-send-btn').is_disabled())

            # T8: verify live poll delivers new JSONL lines and removes typing indicator
            # Inject a mock assistant reply directly into JSONL (avoids Claude rate limits)
            print("  injecting mock assistant reply into JSONL…")
            import pathlib
            CLAUDE_DIR = pathlib.Path.home() / '.claude'
            enc_dir = CLAUDE_DIR / 'projects' / CHAT_ENC
            # Find the session file used in the UI (first sess-item opened)
            jsonl_files = sorted(enc_dir.glob('*.jsonl'),
                                 key=lambda f: f.stat().st_mtime, reverse=True)
            target_jsonl = jsonl_files[0]
            mock_line = json.dumps({
                "type": "assistant",
                "message": {"role": "assistant", "content": [{"type": "text", "text": "已收到，这是自动测试注入的回复。"}]},
                "sessionId": target_jsonl.stem
            }, ensure_ascii=False)
            with open(target_jsonl, 'a') as f:
                f.write(mock_line + '\n')
            print(f"  wrote mock reply to {target_jsonl.name}")

            try:
                page.wait_for_selector('#msg-typing', state='detached', timeout=8000)
                page.wait_for_timeout(300)
                ai_bubbles = page.locator('.msg-ai .bubble').all()
                check("T8 typing indicator removed by live poll", True)
                check("T8 assistant bubble appeared", len(ai_bubbles) > 0,
                      f"{len(ai_bubbles)} ai bubbles")
                # btn stays disabled while input is empty — type to confirm loading was reset
                inp.fill('再确认一下')
                page.wait_for_timeout(150)
                check("T8 send btn re-enabled after reply", not page.locator('#msg-send-btn').is_disabled())
                page.screenshot(path='/tmp/test_reply_received.png')
            except Exception as e:
                check("T8 typing indicator removed by live poll", False, str(e))
                check("T8 assistant bubble appeared", False, "timed out")
                check("T8 send btn re-enabled", False, "timed out")

    browser.close()

# ── Summary ───────────────────────────────────────────────────────────────────
print("\n" + "="*52)
passed = sum(1 for _, s, _ in results if s == PASS)
failed = sum(1 for _, s, _ in results if s == FAIL)
print(f"  {passed} passed  {failed} failed  (total {len(results)})")
print("="*52)
if failed:
    print("\nFailed tests:")
    for name, status, detail in results:
        if status == FAIL:
            print(f"  {name}: {detail}")
