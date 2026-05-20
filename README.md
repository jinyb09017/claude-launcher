# Claude Launcher

**[English](#english) | [中文](#中文)**

---

## English

### Background

[Claude Code](https://docs.anthropic.com/en/docs/claude-code) is Anthropic's AI coding assistant that runs as a CLI on your local machine. It supports **Remote Control** — once a session is started on your desktop, you can connect to it from the Claude iOS/Android app and continue the conversation from your phone.

However, there's a gap: **you must initiate the session from the desktop first**. There's no native way to start a new local Claude Code session from your phone and pick a specific project directory.

For developers who maintain multiple project workspaces (each with its own `CLAUDE.md`, MCP servers, and Harness configuration), switching between projects from mobile is impractical.

**Claude Launcher** fills this gap: a lightweight LAN-accessible PWA that lets you browse your project directories and launch a Claude Code session in any of them directly from your phone.

### How It Works

```
Phone (Safari PWA)
  │  tap a project
  ▼
Mac HTTP Server (port 8765, managed by launchd)
  │  tmux new-session -c <project-dir> claude
  ▼
Claude Code session starts locally
  │  remoteControlAtStartup: true (auto-registers)
  ▼
Claude iOS app → Code tab → session appears with green dot
  │  tap to connect
  ▼
Full conversation interface on mobile
```

**Key components:**

| Component | Role |
|-----------|------|
| `server.py` | Python HTTP server — serves the PWA and manages session lifecycle via tmux |
| `config.json` | Workspace preferences — pinned projects, hidden projects, scan directory |
| `launchd plist` | macOS service manager — starts the server at login, auto-restarts on crash |
| PWA frontend | Single-page app embedded in `server.py` — mobile-optimized dark UI, no install required |

**Session management:**
- Workspace discovery: scans a configured directory for subdirectories containing `CLAUDE.md`
- Session tracking: queries `tmux ls` to determine which workspaces have active sessions
- Conflict handling: if a session already exists, prompts the user to reuse or recreate it
- Naming convention: sessions are named `claude_<dirname>` for easy identification

**Why tmux?**  
Claude Code sessions need a persistent terminal process. tmux detaches the process from the HTTP server's lifecycle, so sessions survive server restarts and remain stable even if the launcher itself is reloaded.

**Why PWA?**  
No App Store, no installation. Open the URL in Safari, tap "Add to Home Screen", and it behaves like a native app — full screen, offline-capable icon, system font rendering.

### Requirements

- macOS with tmux (`brew install tmux`)
- Python 3.x (pre-installed on macOS)
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated
- `remoteControlAtStartup: true` set in Claude Code config (run `/config` inside Claude)
- Claude iOS or Android app with a Pro/Max/Team subscription

### Installation

```bash
git clone https://github.com/jinyb09017/claude-launcher.git
cd claude-launcher
./install.sh
```

The installer registers a launchd agent that starts the server automatically at login.

### Usage

1. Find your Mac's local IP: `ipconfig getifaddr en0`
2. Open `http://<IP>:8765` in Safari on your phone
3. Tap "Add to Home Screen" for a native-app experience
4. Tap a project to launch Claude in that directory
5. Open the Claude app → **Code** tab → connect to the session

### Configuration (`config.json`)

```json
{
  "scan_dir": "~/your-projects-folder",
  "require_claude_md": true,
  "port": 8765,
  "pinned": ["project-a", "project-b"],
  "hidden": ["archive-project"]
}
```

| Field | Description |
|-------|-------------|
| `scan_dir` | Root directory to scan for workspaces |
| `require_claude_md` | Only show directories containing `CLAUDE.md` |
| `port` | HTTP server port |
| `pinned` | Projects that appear at the top of the list |
| `hidden` | Projects excluded from the list |

---

## 中文

### 背景

[Claude Code](https://docs.anthropic.com/en/docs/claude-code) 是 Anthropic 推出的 AI 编程助手，以 CLI 形式运行在本地机器上。它支持 **Remote Control** 功能——在桌面端启动会话后，可以通过 Claude iOS/Android App 连接并继续对话。

然而存在一个缺口：**必须先在桌面端发起会话**，手机上无法主动在指定项目目录启动一个新的本地 Claude Code 会话。

对于维护多个项目工作空间的开发者（每个项目有独立的 `CLAUDE.md`、MCP 服务和 Harness 配置），在移动端切换工作空间非常不便。

**Claude Launcher** 填补了这个缺口：一个轻量级的局域网 PWA，让你直接在手机上浏览项目目录并启动对应的 Claude Code 会话。

### 技术原理

```
手机 Safari (PWA)
  │  点击项目
  ▼
Mac HTTP 服务器（端口 8765，由 launchd 管理）
  │  tmux new-session -c <项目目录> claude
  ▼
Claude Code 会话在本地启动
  │  remoteControlAtStartup: true（自动注册 Remote Control）
  ▼
Claude iOS App → Code 标签页 → 出现绿点会话
  │  点击连接
  ▼
手机上完整的对话界面
```

**核心组件：**

| 组件 | 作用 |
|------|------|
| `server.py` | Python HTTP 服务器，提供 PWA 页面并通过 tmux 管理会话生命周期 |
| `config.json` | 工作空间偏好配置，包括置顶项目、隐藏项目、扫描目录 |
| `launchd plist` | macOS 服务管理，登录时自动启动服务，崩溃时自动重启 |
| PWA 前端 | 内嵌于 `server.py` 的单页应用，移动端优化深色 UI，无需安装 |

**会话管理逻辑：**
- 工作空间发现：扫描配置目录下包含 `CLAUDE.md` 的子目录
- 状态检测：通过 `tmux ls` 判断哪些工作空间有活跃会话
- 冲突处理：若会话已存在，提示用户选择复用还是新建
- 命名规范：会话统一命名为 `claude_<目录名>` 便于识别

**为什么用 tmux？**  
Claude Code 会话需要一个持久的终端进程。tmux 将进程与 HTTP 服务器的生命周期解耦，即使 Launcher 本身重启，Claude 会话依然保持稳定运行。

**为什么用 PWA？**  
无需 App Store，无需安装。Safari 打开链接，"添加到主屏幕"后即可像原生 App 一样全屏运行，使用系统字体，体验自然。

### 环境要求

- macOS + tmux（`brew install tmux`）
- Python 3.x（macOS 预装）
- 已安装并完成认证的 [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code)
- Claude Code 中已设置 `remoteControlAtStartup: true`（在 Claude 内执行 `/config`）
- Claude iOS 或 Android App，需 Pro/Max/Team 订阅

### 安装

```bash
git clone https://github.com/jinyb09017/claude-launcher.git
cd claude-launcher
./install.sh
```

安装脚本会注册 launchd 服务，登录后自动启动。

### 使用方式

1. 查看 Mac 本机 IP：`ipconfig getifaddr en0`
2. 手机 Safari 打开 `http://<IP>:8765`
3. 点击"分享" → "添加到主屏幕"，获得原生 App 体验
4. 点击项目卡片，在该目录启动 Claude
5. 打开 Claude App → **Code 标签页** → 连接会话

### 配置说明（`config.json`）

```json
{
  "scan_dir": "~/你的项目根目录",
  "require_claude_md": true,
  "port": 8765,
  "pinned": ["常用项目A", "常用项目B"],
  "hidden": ["归档项目"]
}
```

| 字段 | 说明 |
|------|------|
| `scan_dir` | 扫描工作空间的根目录 |
| `require_claude_md` | 仅显示包含 `CLAUDE.md` 的目录 |
| `port` | HTTP 服务端口 |
| `pinned` | 置顶显示的项目列表 |
| `hidden` | 从列表中隐藏的项目列表 |

---

## License

MIT
