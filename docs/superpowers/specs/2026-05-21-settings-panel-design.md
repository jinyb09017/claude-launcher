# Settings Panel + Architecture Refactor Design

**Date:** 2026-05-21  
**Scope:** claude-launcher — 架构拆分 + 新增设置面板（语言切换、主题切换、工作空间配置）

---

## 背景

当前 `server.py` 为 778 行单文件，内嵌 Python 后端 + HTML/CSS/JS。新增设置面板后预计超过 1200 行。需要先做架构拆分，再实现功能。

---

## 架构设计

### 目录结构（重构后）

```
claude-launcher/
├── server.py           # 入口（仅 main()，~25 行）
├── api.py              # HTTP Handler + 路由分发
├── workspace.py        # 工作空间扫描 + tmux 管理
├── config.py           # config.json 读写
├── network.py          # check_internet, get_local_ip
├── static/
│   ├── index.html      # HTML 骨架（引用 css/js）
│   ├── app.css         # 全部样式 + 主题变量
│   ├── app.js          # 主逻辑（工作空间列表、modal、轮询）
│   ├── i18n.js         # 翻译表 + 语言切换
│   └── settings.js     # 设置面板（Bottom Sheet、主题、语言控件）
├── config.json
├── install.sh
└── com.user.claude-launcher.plist
```

### 模块职责

| 文件 | 职责 | 预计行数 |
|------|------|----------|
| `server.py` | `main()` — 读 config、启动 HTTPServer | ~25 |
| `api.py` | `Handler` 类、路由、静态文件服务 | ~120 |
| `workspace.py` | `scan_workspaces`、tmux 操作、`short_path` | ~70 |
| `config.py` | `load_config`、`save_config` | ~25 |
| `network.py` | `check_internet`、`get_local_ip` | ~25 |
| `static/index.html` | HTML 骨架 | ~40 |
| `static/app.css` | 样式 + 主题变量 | ~200 |
| `static/app.js` | 主逻辑 | ~250 |
| `static/i18n.js` | 翻译表 + `t()` 函数 | ~80 |
| `static/settings.js` | 设置面板逻辑 | ~150 |

### 静态文件服务

`api.py` 的 Handler 对未匹配 API 路由的 GET 请求，从 `static/` 目录查找并返回文件，支持 `.html/.css/.js` MIME 类型。`/` 映射到 `static/index.html`。

### 新增后端 API

`POST /api/config` — 更新 `scan_dir` 或 `require_claude_md`：

```json
{ "scan_dir": "~/new/path" }
{ "require_claude_md": false }
```

返回 `{"ok": true}`。复用已有 `_lock` 和 `save_config`。

---

## 设置面板（前端）

### 入口

Header 右上角：现有「管理」文字按钮 → 替换为 ⚙ 图标按钮（`id="gear-btn"`）。激活状态高亮（`border-color: var(--accent)`）。

### Bottom Sheet 结构

```html
<div class="sheet-overlay" id="sheet-overlay">
  <div class="sheet" id="settings-sheet">
    <div class="sheet-handle"></div>
    <!-- 外观分组 -->
    <!-- 工作空间分组 -->
  </div>
</div>
```

动画：入场 `translateY(100%)→0`，`0.28s cubic-bezier(0.32,0.72,0,1)`；退场 `0.22s ease-in`。

### 外观分组

| 设置项 | 控件 | 选项 | 存储 |
|--------|------|------|------|
| 语言 | 分段控件（2 段）| 中文 / EN | `localStorage.launcher_lang`，默认 `zh` |
| 主题 | 分段控件（3 段）| ☀️ 浅色 / 🌙 深色 / 💻 跟随系统 | `localStorage.launcher_theme`，默认 `dark` |

### 工作空间分组

| 设置项 | 控件 | 行为 |
|--------|------|------|
| 扫描目录 | 行 + › + 当前值 | 点击弹出 `<input>` 输入框，保存时 `POST /api/config` |
| 管理工作空间 | 行 + › | 点击打开现有 pin/hide 面板（复用逻辑，迁移到 settings.js） |
| 仅显示 CLAUDE.md | Toggle | 点击即 `POST /api/config`，然后刷新列表 |

---

## 语言切换（i18n.js）

`t(key)` 函数，根据 `localStorage.launcher_lang` 返回对应语言字符串。切换时调用 `applyLang()` 遍历所有带 `data-i18n` 属性的 DOM 节点更新 `textContent`，动态内容在 `render()` 内直接调用 `t()`。

**完整翻译表：**

| Key | 中文 | English |
|-----|------|---------|
| `header_subtitle` | 局域网 | LAN |
| `net_checking` | 检测中 | Checking |
| `net_ok` | 正常 | OK |
| `net_warn` | 无外网 | No WAN |
| `net_bad` | 断连 | Offline |
| `net_banner_lan_down` | 无法连接到 Mac，请检查局域网连接 | Cannot reach Mac — check LAN |
| `net_banner_inet_warn` | Mac 当前无互联网连接，Claude 可能无法运行 | Mac has no internet — Claude may not work |
| `section_pinned` | 📌 置顶 | 📌 Pinned |
| `section_other` | 其他 工作空间 | Other Workspaces |
| `section_all` | 全部 工作空间 | All Workspaces |
| `guide_title` | 使用方式 | How to use |
| `guide_step1` | 点击项目启动 Claude 会话 | Tap a project to start a Claude session |
| `guide_step2` | 打开 Claude App → 底部 Code 标签 | Open Claude App → Code tab |
| `guide_step3` | 找到同名会话（绿点）点击连接 | Find the session (green dot) and connect |
| `btn_stop` | 停止 | Stop |
| `empty_no_ws` | 未找到工作空间 | No workspaces found |
| `empty_no_ws_hint` | 目录需包含 CLAUDE.md 文件 | Directories must contain CLAUDE.md |
| `modal_running_desc` | 该工作空间已有运行中的 Claude 会话，你想怎么处理？ | This workspace has a running Claude session. |
| `btn_reuse` | 继续使用现有会话 | Use existing session |
| `btn_new_session` | 终止并新建会话 | Kill and restart |
| `btn_cancel` | 取消 | Cancel |
| `toast_reuse` | 前往 Claude App → Code 标签连接 | Go to Claude App → Code tab |
| `toast_stopped` | 已停止 | Stopped |
| `toast_started` | 已启动 → Claude App → Code 标签 | Started → Claude App → Code tab |
| `toast_net_offline` | 网络已断开 | Network offline |
| `toast_net_restored` | 网络已恢复 | Network restored |
| `settings_title` | 设置 | Settings |
| `settings_appearance` | 外观 | Appearance |
| `settings_language` | 语言 | Language |
| `settings_theme` | 主题 | Theme |
| `theme_light` | 浅色 | Light |
| `theme_dark` | 深色 | Dark |
| `theme_auto` | 跟随系统 | Auto |
| `settings_workspace_section` | 工作空间 | Workspace |
| `settings_scan_dir` | 扫描目录 | Scan Directory |
| `settings_manage_ws` | 管理工作空间 | Manage Workspaces |
| `settings_require_md` | 仅显示 CLAUDE.md | Require CLAUDE.md |
| `ws_panel_title` | 工作空间管理 | Manage Workspaces |
| `ws_panel_hint` | 置顶常用项目，隐藏不需要显示的目录 | Pin frequent projects, hide others |
| `btn_close` | 关闭 | Close |
| `btn_pin` | 置顶 | Pin |
| `btn_hide` | 隐藏 | Hide |

---

## 主题切换（app.css + settings.js）

```css
/* 深色（默认） */
:root {
  --bg: #0d1117; --card: #161b22; --border: #30363d;
  --text: #e6edf3; --sub: #8b949e; --accent: #58a6ff;
  --green: #3fb950; --orange: #d29922; --red: #da3633;
  --radius: 12px;
}
/* 浅色 */
[data-theme="light"] {
  --bg: #f6f8fa; --card: #ffffff; --border: #d0d7de;
  --text: #1f2328; --sub: #656d76; --accent: #0969da;
  --green: #1a7f37; --orange: #9a6700; --red: #cf222e;
}
```

`settings.js` 的 `applyTheme(mode)`:
- `dark` → `document.documentElement.removeAttribute('data-theme')`
- `light` → `setAttribute('data-theme','light')`
- `auto` → 监听 `matchMedia('(prefers-color-scheme: dark)')` 动态切换

主题切换加 CSS transition：`body { transition: background .2s, color .2s; }`

---

## 实现边界

- `server.py` 保持为入口文件，`python3 server.py` 启动方式不变
- `install.sh` 和 `.plist` 无需修改
- 语言 / 主题纯前端，不写 config.json
- 现有 `/api/config/toggle` 接口不变，新增 `/api/config` 接口
- 静态文件由 Python 内置 HTTP server 直接 serve，无需 nginx
