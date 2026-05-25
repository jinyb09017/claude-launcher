# Claude Workspace Launcher

局域网 PWA，从手机启动、管理和直接对话 Claude Code 工作空间。

---

## 项目简介

[Claude Code](https://docs.anthropic.com/en/docs/claude-code) 是 Anthropic 推出的 AI 编程助手，以 CLI 形式运行在本地。它支持 **Remote Control** 功能——在桌面端启动会话后，可以通过 Claude iOS/Android App 继续对话。

但存在一个缺口：**必须先在桌面端发起会话**，手机上无法主动选择项目目录、启动新会话，也无法直接查看和继续历史对话。

**Claude Launcher** 填补这个缺口：在 Mac 上常驻一个轻量 HTTP 服务，手机用 Safari 打开即可：

- 浏览本地所有项目目录，一键启动 tmux + claude 会话
- 查看所有历史 Claude 对话（项目 → 会话 → 消息，三级浏览）
- **在历史会话中直接输入消息，通过 tmux send-keys 与运行中的 Claude 交互**
- 支持收藏 / 隐藏项目、关键词搜索、中英文切换、明暗主题
- 注册为 macOS launchd 服务，开机自启，崩溃自动重启

---

## 核心架构

```
┌──────────────────────────────────┐
│   手机 / 平板  Safari (PWA)       │
└─────────────────┬────────────────┘
                  │  HTTP（局域网，同一 WiFi）
                  ▼
┌──────────────────────────────────┐
│   Python HTTP 服务（server.py）  │
│   ThreadingHTTPServer            │
│   端口 8765，监听 0.0.0.0        │
├──────────────────────────────────┤
│   API 路由层（api.py）           │
│   ┌─────────────────────────┐   │
│   │  workspace.py           │   │
│   │  · 扫描工作空间目录      │   │
│   │  · 读取 Claude 历史项目  │   │
│   │  · tmux 会话管理         │   │
│   │  · JSONL 消息解析        │   │
│   │  · tmux send-keys 聊天  │   │
│   └─────────────────────────┘   │
│   ┌─────────────────────────┐   │
│   │  config.py              │   │
│   │  · config.json 读写     │   │
│   └─────────────────────────┘   │
│   ┌─────────────────────────┐   │
│   │  network.py             │   │
│   │  · 本地 IP 探测          │   │
│   │  · 网络连通性检测        │   │
│   └─────────────────────────┘   │
├──────────────────────────────────┤
│   后台监控线程（_monitor_loop）  │
│   · 每 2s 轮询 tmux 会话变化    │
│   · 检测新 JSONL 建立 ID 映射   │
│   · 维护 launcher_sessions.json │
└──────────────┬───────────────────┘
               │  spawn
               ▼
┌──────────────────────────────────┐
│   tmux 会话（每个工作空间一个）   │
│   命名：<last2_path>_<HHMM>     │
└──────────────┬───────────────────┘
               │  exec
               ▼
┌──────────────────────────────────┐
│   claude CLI                     │
│   · -n <name> --remote-control  │
│   · --resume <session_id>        │
└──────────────────────────────────┘

持久化文件：
  ~/.claude/projects/<encoded>/<session_id>.jsonl  — claude 自动写入
  ~/.claude/launcher_sessions.json                  — session_id → tmux 名映射
```

---

## 目录结构

```
claude-launcher/
├── server.py                       # 入口：启动 HTTP 服务、后台监控线程
├── api.py                          # HTTP 请求路由，REST API 实现
├── workspace.py                    # 核心逻辑：工作空间扫描、tmux 管理、消息解析、会话映射
├── config.py                       # config.json 读写工具
├── network.py                      # 本地 IP 探测 / 网络连通性检测
├── config.example.json             # 配置模板（复制为 config.json 后编辑）
├── install.sh                      # 一键注册 launchd 服务
├── com.user.claude-launcher.plist  # macOS 服务配置
├── static/
│   ├── index.html     # PWA 页面骨架
│   ├── app.js         # 主应用逻辑（状态、渲染、交互、实时聊天）
│   ├── settings.js    # 设置面板（主题、语言切换）
│   ├── app.css        # 样式（CSS 变量主题、响应式布局）
│   └── i18n.js        # 国际化（中文 / 英文）
├── tests/
│   ├── test_sessions.py        # 会话新建 / 恢复 / 状态 API 测试
│   ├── test_chat.py            # 双向聊天功能验收测试
│   ├── test_resume.py          # 历史会话恢复测试
│   ├── test_project_delete.py  # 项目日志删除逻辑测试
│   ├── test_baseline.py        # 代理环境 / API 连通性基准测试
│   └── test_recon.py           # UI 侦察（Playwright 截图）
└── docs/
    └── screenshots/   # 设计稿与截图
```

---

## 实现原理

### 1. 服务启动（server.py）

使用 Python 内置 `ThreadingHTTPServer`，**零第三方依赖**，每个请求独立线程处理：

```python
start_tmux_monitor()  # 启动后台监控线程
ThreadingHTTPServer(('0.0.0.0', port), Handler).serve_forever()
```

启动时通过 `network.get_local_ip()` 探测本机局域网 IP——向 `8.8.8.8:80` 发送不实际传输数据的 UDP 探测包，读取 socket 本端地址，无需解析网络接口列表。

---

### 2. API 路由层（api.py）

`Handler` 继承自 `BaseHTTPRequestHandler`，在 `do_GET` / `do_POST` 中按路径手动分发：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 服务健康检查，附带网络连通性状态 |
| GET | `/api/workspaces` | 扫描工作空间目录，附带 tmux 运行状态 |
| GET | `/api/projects` | 读取 `~/.claude/projects/` 项目列表 |
| GET | `/api/projects/sessions` | 列出某项目的历史会话及运行状态 |
| GET | `/api/sessions/messages` | 解析某会话的消息内容 |
| GET | `/api/sessions/live` | 拉取 JSONL 新增行（实时聊天轮询） |
| POST | `/api/start` | 在 tmux 中启动 claude 会话（可恢复历史） |
| POST | `/api/stop` | 杀掉指定工作空间的全部 tmux 会话 |
| POST | `/api/chat` | 向运行中的 tmux 会话发送消息 |
| POST | `/api/sessions/delete` | 删除指定会话的 JSONL 记录 |
| POST | `/api/projects/delete` | 删除项目全部历史日志（运行中拒绝） |
| POST | `/api/config/toggle` | 切换收藏 / 隐藏状态 |
| POST | `/api/config` | 更新扫描目录、过滤规则等 |
| GET | `/static/*` | 返回前端静态资源 |

配置读写使用 `threading.Lock` 保证多请求并发安全。

---

### 3. 工作空间发现（workspace.py · scan_workspaces）

1. 读取 `config.json` 中的 `scan_dir`（默认 `~/Documents/ai-claude`）
2. 列出所有一级子目录，排除 `.` 开头的隐藏目录
3. 若 `require_claude_md: true`，跳过不含 `CLAUDE.md` 的目录
4. **排序规则**：收藏项目（`pinned`）按列表顺序优先，其余按目录修改时间倒序

**运行状态检测**：通过 `tmux ls` 列出所有活跃 session，与 `_path_base(path)` 前缀比对：

```python
def _path_base(path: str) -> str:
    # 取路径最后两级，用 _ 拼接，过滤非字母数字字符
    # /Users/foo/ai-claude/my-project → ai-claude_my-project
```

检测条件：session 名等于 `base`，或以 `base + '_'` 为前缀（覆盖所有 HHMM 后缀变体）。

---

### 4. tmux 会话管理

#### 命名规则

所有新建会话统一使用 **`<last2_path>_<HHMM>`** 格式：

```
/Users/foo/ai-claude/my-project → ai-claude_my-project_1041
```

- `_path_base()` 取路径最后两级，非字母数字字符替换为 `_`
- HHMM 为创建时刻的小时分钟（`%H%M`）
- 同一分钟内重复创建：追加计数后缀 `_2`、`_3`…

tmux session 名与 claude CLI 的 `-n <name>` 参数保持一致，两者共享同一名称，方便 Remote Control 对接。

#### 新建会话

```bash
# 全新会话
tmux new-session -d -s ai-claude_my-project_1041 -c <path> \
    claude -n ai-claude_my-project_1041 --remote-control

# 恢复历史会话
tmux new-session -d -s ai-claude_my-project_1041 -c <path> \
    claude -n ai-claude_my-project_1041 --remote-control --resume <session_id>
```

恢复时同时写入会话映射（`_register_session`），无需等待监控线程。

#### 同一项目多会话

不 kill 旧 session，直接开新 session，两者并存。同一项目最终可能有多个活跃 session（`_1041`、`_1305`…），互不干扰。

#### 停止会话

停止时 kill 路径对应的**所有** session（前缀匹配）：

```python
def kill_session(path):
    base = _path_base(path)
    for s in list_tmux_sessions():
        if s == base or s.startswith(base + '_'):
            subprocess.run(["tmux", "kill-session", "-t", s], ...)
```

#### 为什么用 tmux？

Claude Code 会话需要持久终端进程。tmux 将进程与 HTTP 服务器生命周期解耦，服务重启后 Claude 会话仍然存在。

---

### 5. 会话映射与后台监控

#### 问题：两个 ID，无法直接对应

Launcher 同时面对两套标识：

- **tmux session 名**（`ai-claude_my-project_1041`）：启动时由 Launcher 生成，Launcher 知道
- **Claude session_id**（UUID，如 `d512e889-...`）：由 claude CLI 内部分配，只有在 claude 把**第一条消息写入 JSONL 文件**后，才能从文件名推断出来

这个"先有 tmux、后才知道 session_id"的时间差，导致两个核心操作无法直接完成：

1. **会话列表显示运行状态**：`/api/projects/sessions` 拿到的是 session_id 列表，但 tmux 只认 session 名——不知道映射就无法判断哪条历史会话正在跑
2. **发消息给指定会话**：`/api/chat` 收到的是 session_id，最终要调用 `tmux send-keys -t <name>`——不知道名字就无法投递

#### 解法：map 是唯一事实来源

Launcher 维护 `~/.claude/launcher_sessions.json`，作为所有运行状态判断的**唯一来源**。所有 API（`/api/workspaces`、`/api/projects`、`/api/projects/sessions`、`/api/start`）都只读这个文件，不再直接查询 tmux。

Map 的结构有两种条目：

```json
{
  "d512e889-ab58-499d-85a2-d8195cd2fafd": "ai-claude_my-project_1041",
  "ai-claude_my-project_1305": "ai-claude_my-project_1305"
}
```

| 条目类型 | key | value | 说明 |
|---------|-----|-------|------|
| 已解析 | session_id（UUID） | tmux_name | JSONL 已出现，session_id 已知 |
| 占位符 | tmux_name | tmux_name（同上） | session 已启动，JSONL 还没写 |

占位符的存在让工作空间 running 检测能立即生效——会话刚启动就有占位符，无需等到用户发第一条消息。

有两条路径写入 map：

- **恢复历史会话（立即写入）**：session_id 已知，`start_session_by_path` 在启动 tmux 后立刻注册，无需等待
- **新建会话（监控线程写入）**：session_id 未知，监控线程先写占位符，JSONL 出现后替换为真实 session_id

#### 后台监控线程：全量对账

监控线程每 2 秒做一次完整对账，不再维护"watching 队列"：

```
每个周期：

① 读取当前 tmux 所有 session（含创建时间戳）
② 读取现有 map

③ 清理：map 中 value 不在 tmux 的条目 → 删除（session 已停止）

④ 补全：每个 tmux session（launcher 相关）若不在 map 的 values 中：
   - 有 JSONL（mtime >= session 创建时间）→ 写入 {session_id: tmux_name}
   - 无 JSONL → 写入占位符 {tmux_name: tmux_name}

⑤ 解析占位符：key==value 的条目若 JSONL 已出现 → 替换为 {session_id: tmux_name}

⑥ map 有变化 → 写入文件
```

**关键细节**：使用 `tmux ls -F "#{session_name} #{session_created}"` 获取 tmux 自身记录的创建时间戳（而非 `time.time()`），避免监控线程 2s 延迟导致漏检在此期间写入的 JSONL。

完整的状态流转：

```
新建会话
  │
  ├─ tmux session 启动（tmux_name 已知，session_id 未知）
  │     └─ 监控线程（≤2s）→ 写入占位符 {tmux_name: tmux_name}
  │         → 此后 /api/workspaces 可立即显示"运行中"
  │
  ├─ 用户发第一条消息
  │     → claude 写入 ~/.claude/projects/<encoded>/<session_id>.jsonl
  │
  └─ 监控线程（≤2s）→ 占位符替换为 {session_id: tmux_name}
        → 此后 /api/projects/sessions 可精确显示该会话"运行中"
           /api/chat 可路由到正确 session

恢复历史会话
  │
  └─ start_session_by_path 立即写入 {session_id: tmux_name}
        → 所有状态立即正确，无需等待监控线程
```

---

### 6. 会话消息数据来源——JSONL 文件

Claude CLI 将**所有会话内容自动持久化**到本地文件：

```
~/.claude/projects/<encoded_path>/<session_id>.jsonl
```

每行是一条 JSON，记录一轮对话：

```jsonl
{"message":{"role":"user","content":"帮我写个测试"},"promptId":"..."}
{"message":{"role":"assistant","content":[{"type":"text","text":"好的..."}]},"promptId":"..."}
```

**查看历史消息**：Launcher 直接读取对应 JSONL 文件，逐行解析，过滤系统注入消息。

**实时聊天时**：发送消息后前端轮询 `/api/sessions/live?from=<line>`，每次返回 JSONL 中新增的行，直到出现新的 assistant 消息为止。

---

### 7. Claude 历史项目读取

Claude CLI 对路径编码时将分隔符和特殊字符替换为 `-`：

```
/Users/foo/Documents/ai-claude/my-project
→ -Users-foo-Documents-ai-claude-my-project
```

`_decode_project_path()` 使用**贪心文件系统匹配**反向还原路径：逐段从文件系统中尝试最长路径组件，处理路径本身含 `-` 的歧义情况。

反向编码 `_encode_path()` 用于从实际路径生成 claude 的项目目录名，供查找 JSONL 文件时使用。

**会话过滤**：过滤一次性工具会话（如 `git diff` 分析、commit 消息生成），判断条件为：首条用户消息包含 git 操作指令或 diff 输出。

---

### 8. JSONL 消息解析（workspace.py · get_session_messages）

每行 JSONL 是 Claude API 消息格式的 JSON 对象，解析流程：

1. 按行读取，解析 `role`（user / assistant）
2. 跳过系统注入消息（sidechains、纯工具结果、XML 标签内容）
3. 按 `message.id` 或 `promptId` **去重**（多轮对话 JSONL 中存在重复记录）
4. 提取 content blocks：

| 块类型 | 处理方式 |
|--------|---------|
| `text` | 截取前 600 字符 |
| `tool_use` | 格式化为可读摘要（见下表） |
| `tool_result` | 跳过，不展示给用户 |

**工具摘要格式化**（`_tool_desc`）：

| 工具 | 展示内容 |
|------|---------|
| Read / Write / Edit | 文件路径 |
| Bash | 命令前 80 字符 |
| Agent | description 前 60 字符 |
| 其他 | 工具名称 |

---

### 9. 实时聊天（tmux send-keys + JSONL 轮询）

用户在手机上向运行中的 Claude 发送消息的完整链路：

```
用户输入消息 → POST /api/chat
  │
  ▼
find_tmux_session_for_project(encoded, session_id)
  │  先查 launcher_sessions.json（精确匹配）
  │  再按 _path_base 前缀扫描活跃 session（兜底）
  │
  ├─ 找到 → send_to_tmux_session(tmux_name, message)
  │         tmux send-keys -t <name> "<message>" Enter
  │
  └─ 未找到 → start_session_by_path(path, session_id) 启动新 session
              wait_for_claude_ready() 等待 JSONL 出现（最多 15s）
              → 再执行 send_to_tmux_session

前端收到 200 OK 后开始轮询：
  GET /api/sessions/live?encoded=...&id=...&from=<line>
  → 返回 JSONL 新增行中的 assistant 消息
  → 追加到聊天气泡，直到出现完整 assistant 回复
```

**为什么用 tmux send-keys 而非 `claude -p`？**

`--remote-control` 模式下，claude 会话持续运行、保有完整上下文，send-keys 直接将消息注入终端输入，与手动在桌面端打字效果一致。响应自动追加到 JSONL，前端轮询读取即可，无需维护流式连接。

---

### 10. 前端 PWA（static/app.js）

纯原生 JavaScript，无框架，无构建工具，单文件。

**两 Tab 架构**：

```
⭐ 收藏 Tab                    🌐 全部 Tab
──────────────────────         ──────────────────────
只显示已收藏的项目               全部 Claude 历史项目
左滑 → 取消收藏                 按时间分组（7天内/更早）
点击 → 会话列表面板             支持路径关键词搜索
                                左滑 → 收藏 / 删除日志
                                点击 → 会话列表面板
```

启动时默认加载收藏 Tab，切换到「全部」时才请求 `/api/projects`；回到「收藏」后数据已缓存，直接本地渲染，无需重新请求。

**左滑操作（direction-lock 方案）**：

收藏 Tab 和全部 Tab 的每张卡片均支持左滑手势：

```
收藏 Tab 卡片左滑：显示「取消收藏」按钮
全部 Tab 卡片左滑：显示「收藏」+「删除日志」按钮
会话列表左滑：显示「删除」按钮
```

方向锁定逻辑（移动 5px 后判断主方向）：
- 水平为主 → 锁定水平，`e.preventDefault()` 阻止页面滚动，追踪 dx 露出按钮
- 垂直为主 → 锁定垂直，关闭所有已展开的滑动行，允许页面正常滚动

`touchmove` 注册时使用 `{ passive: false }` 以支持 `preventDefault`。

**收藏机制**：

收藏状态存储在 `config.json` 的 `pinned` 数组中，以 `display_name`（`parent/child` 格式，如 `"ai-claude/my-project"`）作为标识键。前端通过 `POST /api/config/toggle` 切换收藏状态，操作后立即本地更新 `_projects` 缓存并重新渲染，无需重新请求后端。

**工作空间管理面板**（`openWsPanel`）：通过顶部齿轮图标右侧的管理按钮打开，列出所有工作空间（含隐藏项），可逐项切换收藏状态。

**状态管理**：所有 UI 状态存储在模块级变量：

```javascript
let _currentTab = 'favorites';  // 当前 Tab（favorites / all）
let _projects = [];             // 项目列表缓存（含收藏状态）
let _searchQuery = '';          // 搜索关键词
let _chatLoading = false;       // 是否正在等待 AI 响应
```

**网络轮询**：项目状态（running / 收藏）每 15 秒轮询一次；网络状态每 20 秒检测一次，同时监听 `online` / `offline` 事件即时响应。

**三级滑动面板**：

```
主界面（收藏 / 全部列表）
  └─ 会话列表面板（.slide-panel，从右滑入）
       └─ 消息查看 + 聊天面板（.slide-panel.on-top，再次从右叠加）
```

使用 CSS `transform: translateX(100%)` + `transition` 实现动画，无 JavaScript 动画循环。

**内置 Markdown 渲染器**（`renderMd`）：不引入任何库，按序处理：代码块保护 → 行内代码 → 标题 → 粗体/斜体 → 表格 → 列表 → 段落换行。

---

### 11. 国际化与主题

**国际化（i18n.js）**：

所有 UI 字符串集中在 `TRANSLATIONS` 对象（`zh` / `en` 两套），DOM 元素用 `data-i18n` 属性标记，切换语言时统一刷新：

```javascript
document.querySelectorAll('[data-i18n]').forEach(el => {
    el.textContent = t(el.dataset.i18n);
});
```

语言选择持久化到 `localStorage`；切换后同时触发 `render()`（刷新卡片列表）和 `renderSheet()`（刷新设置面板）。

**主题（app.css + settings.js）**：

CSS 自定义属性定义完整调色板，切换主题只需切换 `data-theme` 属性：

```css
:root               { --bg: #0a0a0a; --card: #1a1a1a; --text: #e8e8e8; }
[data-theme="light"]{ --bg: #f5f5f5; --card: #ffffff; --text: #1a1a1a; }
```

支持「跟随系统」模式（监听 `prefers-color-scheme` 媒体查询），选择持久化到 `localStorage`。`settings.js` 在页面首次渲染前即调用 `_applyThemeToDOM()` 应用主题，避免白屏闪烁。

**设置面板（settings.js）**：底部上拉 Sheet，仅包含外观设置（语言切换、主题切换）。工作空间管理（收藏/隐藏）独立为「管理工作空间」面板（`openWsPanel`），通过顶部按钮访问。

---

## 安装与使用

### 环境要求

- macOS + tmux（`brew install tmux`）
- Python 3.x（macOS 预装）
- 已安装并认证的 [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code)

### 一键安装

```bash
# 1. 复制配置模板
cp config.example.json config.json
# 编辑 config.json，填写 scan_dir（工作空间根目录）及代理等参数

# 2. 注册 launchd 服务
./install.sh
```

注册为 macOS launchd 服务（`~/Library/LaunchAgents/com.user.claude-launcher.plist`），开机自启，崩溃自动重启，日志写入 `launcher.log`。

### 手动启动（调试）

```bash
python3 server.py
```

### 访问

启动后终端打印：

```
Claude Launcher  http://192.168.x.x:8765
Local            http://localhost:8765
```

手机与 Mac 连接同一 WiFi，Safari 打开局域网地址即可。点击「分享 → 添加到主屏幕」获得全屏 PWA 体验。

### 服务管理

```bash
# 停止（必须用 launchctl，直接 kill 会被立即重启）
launchctl unload ~/Library/LaunchAgents/com.user.claude-launcher.plist

# 重启
launchctl unload ~/Library/LaunchAgents/com.user.claude-launcher.plist
launchctl load ~/Library/LaunchAgents/com.user.claude-launcher.plist

# 查看日志
tail -f launcher.log
```

---

## 配置说明（config.json）

首次使用请复制模板：

```bash
cp config.example.json config.json
```

```json
{
  "scan_dir": "~/Documents/ai-claude",
  "require_claude_md": false,
  "port": 8765,
  "pinned": ["ai-claude/my-project"],
  "hidden": ["ai-claude/temp-project"],
  "claude_env": {
    "HTTPS_PROXY": "",
    "HTTP_PROXY": "",
    "ALL_PROXY": "",
    "NO_PROXY": "localhost,127.0.0.1,::1"
  }
}
```

| 字段 | 说明 |
|------|------|
| `scan_dir` | 扫描工作空间的根目录，支持 `~` |
| `require_claude_md` | `true` 时只显示含 `CLAUDE.md` 的目录 |
| `port` | 监听端口，默认 8765 |
| `pinned` | 收藏的项目列表，格式为 `parent/child`（扫描目录末段 + 项目名），按列表顺序显示在收藏 Tab |
| `hidden` | 隐藏的项目列表，同 `pinned` 格式，不在「全部」Tab 中显示 |
| `claude_env` | 启动 claude 进程时注入的环境变量（如代理设置），留空则不注入 |

收藏状态可通过在「全部」Tab 左滑项目直接操作，无需手动编辑 `config.json`。

---

## 设计原则

| 原则 | 体现 |
|------|------|
| **零依赖** | 只用 Python 标准库，无需 `pip install` |
| **离线优先** | 核心功能不依赖公网，网络异常时展示提示而非崩溃 |
| **移动优先** | 触摸交互、安全区域（notch/home indicator）适配、大点击目标 |
| **简单可靠** | 无数据库、无复杂状态机，轮询代替 WebSocket |
| **安全** | 配置读写加并发锁、路径字符净化、HTML 转义防 XSS |

---

## License

MIT
