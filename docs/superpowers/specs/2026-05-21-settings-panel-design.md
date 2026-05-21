# Settings Panel Design

**Date:** 2026-05-21  
**Scope:** claude-launcher — 新增设置面板（语言切换、主题切换、工作空间配置）

---

## 概述

在 header 右上角新增 ⚙ 设置按钮，点击后从屏幕底部滑出 Bottom Sheet 设置面板，包含外观（语言、主题）和工作空间两组设置项。现有「管理」按钮的功能合并进设置面板。

---

## 入口

- Header 右上角：现有「管理」文字按钮 → 替换为 ⚙ 图标按钮
- 激活状态：按钮高亮（`border-color: var(--accent)`，`color: var(--accent)`）
- 点击已打开的面板外区域或再次点击按钮：关闭面板

---

## 面板结构（Bottom Sheet）

从屏幕底部滑入，覆盖主内容区，背景加模糊遮罩。顶部有拖拽把手（drag handle）。

### 外观分组

| 设置项 | 控件 | 选项 | 默认 |
|--------|------|------|------|
| 语言 Language | 分段控件（2 段）| 中文 / EN | 中文 |
| 主题 | 分段控件（3 段）| ☀️ 浅色 / 🌙 深色 / 💻 跟随系统 | 深色 |

### 工作空间分组

| 设置项 | 控件 | 说明 |
|--------|------|------|
| 扫描目录 | 行 + › | 显示当前值（短路径），点击弹出文本输入框修改 |
| 管理工作空间 | 行 + › | 点击打开现有工作空间 pin/hide 面板 |
| 仅显示 CLAUDE.md | Toggle 开关 | 对应 `require_claude_md`，即时生效并刷新列表 |

---

## 语言切换

整个 app UI 所有可见文案随语言切换实时更新，无需刷新页面。

**中英文对照表（所有需要翻译的字符串）：**

| Key | 中文 | English |
|-----|------|---------|
| app_title | Claude Launcher | Claude Launcher |
| header_subnet | 局域网 | LAN |
| header_loading | 加载中... | Loading... |
| net_checking | 检测中 | Checking |
| net_ok | 已连接 | Connected |
| net_warn | 仅局域网 | LAN only |
| net_bad | 网络断开 | Offline |
| section_pinned | 📌 置顶 | 📌 Pinned |
| section_others | 其他 工作空间 | Other Workspaces |
| section_all | 全部 工作空间 | All Workspaces |
| btn_manage | 管理工作空间 | Manage Workspaces |
| btn_stop | 停止 | Stop |
| settings_title | 设置 | Settings |
| settings_appearance | 外观 | Appearance |
| settings_language | 语言 | Language |
| settings_theme | 主题 | Theme |
| settings_theme_light | 浅色 | Light |
| settings_theme_dark | 深色 | Dark |
| settings_theme_auto | 跟随系统 | Auto |
| settings_workspace | 工作空间 | Workspace |
| settings_scan_dir | 扫描目录 | Scan Directory |
| settings_claude_md | 仅显示 CLAUDE.md | Require CLAUDE.md |
| empty_loading | 加载中... | Loading... |
| empty_no_workspace | 未找到工作空间 | No workspaces found |
| toast_started | 已启动 | Started |
| toast_stopped | 已停止 | Stopped |
| modal_start_title | 启动工作空间 | Start Workspace |
| modal_stop_title | 停止工作空间 | Stop Workspace |

语言偏好存储在 `localStorage`（key: `launcher_lang`），默认 `zh`。

---

## 主题切换

三种模式：
- **浅色（light）**：强制浅色 CSS 变量
- **深色（dark）**：当前默认变量（不变）
- **跟随系统（auto）**：通过 `prefers-color-scheme` media query 自动切换

主题偏好存储在 `localStorage`（key: `launcher_theme`），默认 `dark`。

**浅色主题变量（新增）：**
```css
[data-theme="light"] {
  --bg: #f6f8fa; --card: #ffffff; --border: #d0d7de;
  --text: #1f2328; --sub: #656d76; --accent: #0969da;
  --green: #1a7f37; --orange: #9a6700; --red: #cf222e;
}
```
`auto` 模式：监听 `matchMedia('(prefers-color-scheme: dark)')` 变化，动态切换 `data-theme`。

---

## 数据持久化

| 设置项 | 存储位置 | 说明 |
|--------|----------|------|
| 语言 | localStorage | 纯前端，无需写服务器 |
| 主题 | localStorage | 纯前端 |
| 扫描目录 | config.json（via POST /api/config） | 已有接口 |
| 仅显示 CLAUDE.md | config.json（via POST /api/config） | 已有接口 |
| 管理工作空间（pin/hide）| config.json（via POST /api/config/toggle）| 已有接口 |

---

## 动画规范

- Bottom Sheet 入场：`transform: translateY(100%)` → `translateY(0)`，`transition: 0.28s cubic-bezier(0.32, 0.72, 0, 1)`（iOS spring 近似）
- Bottom Sheet 退场：反向，`0.22s ease-in`
- 遮罩：`opacity: 0` → `0.55`，`0.25s`
- 主题切换：`transition: background 0.2s, color 0.2s` on `:root`

---

## 实现边界

- 不新增 Python 后端接口，复用 `/api/config` 和 `/api/config/toggle`
- 语言 / 主题切换纯前端，不写入 config.json
- 所有改动在 `server.py` 的 `PWA_HTML` 字符串内完成（单文件架构）
- 「管理」按钮移除，其功能通过设置面板的「管理工作空间」行访问
