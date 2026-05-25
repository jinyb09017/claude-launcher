# 收藏列表重构设计

**日期**: 2026-05-25

## 背景

当前"收藏"tab 使用 `workspaces` 数据源（运行中的工作区），"全部"tab 使用 `projects` 数据源（所有有 Claude session 历史的目录）。两套数据源独立，收藏的概念混乱。

## 目标

1. 收藏列表数据源统一为 projects（全部列表的数据源）
2. 收藏 tab 支持取消收藏（左滑操作）
3. 全部 tab 支持收藏操作（左滑暴露"收藏 + 删除"两个按钮）
4. 管理空间面板只保留置顶操作，移除隐藏操作
5. 卡片点击行为：收藏 tab 与全部 tab 一致，点击打开会话列表面板

## 架构

### 数据层（后端）

- `/api/projects` 返回的每个 project 对象新增 `pinned: bool` 字段
  - 通过对比 `config.pinned` 列表注入
- `/api/config/toggle` key=`pinned` 已有，无需改动
- `/api/workspaces` 保留（供其他可能用途），但前端收藏 tab 不再使用

### 前端状态

- 移除 `workspaces` 全局变量及 `render()`、`load()`、`cardHTML()` 等旧收藏 tab 函数
- `_projects` 成为唯一数据源
- 收藏 tab 渲染：`_projects.filter(p => p.pinned)`

### 收藏 tab

- 复用 `projectCardHTML` 渲染卡片
- 左滑暴露"取消收藏"按钮（替代原来的"删除"按钮）
- 取消收藏：调用 `/api/config/toggle`，本地更新 `_projects` 中该项 `pinned=false`，重渲染
- 空状态文案：提示去全部 tab 收藏项目

### 全部 tab

- 左滑暴露两个按钮：[收藏/已收藏] [删除]
- 收藏按钮文字根据当前 `pinned` 状态切换
- 操作：调用 `/api/config/toggle`，本地更新 `pinned` 字段，重渲染

### 管理空间面板

- 移除"隐藏"按钮，只保留"置顶"按钮
- `ws_panel_hint` i18n 文本更新（去掉隐藏相关描述）

## 变更文件

| 文件 | 变更内容 |
|------|---------|
| `api.py` | `/api/projects` 注入 `pinned` 字段 |
| `static/app.js` | 移除旧 workspaces 相关代码；收藏 tab 改用 projects；全部 tab swipe 加收藏按钮；管理面板移除隐藏按钮 |
| `static/i18n.js` | 新增"取消收藏"、"收藏"、"已收藏"、空收藏文案的 i18n key |
| `static/app.css` | 全部 tab swipe 区域新增收藏按钮样式 |
| `static/index.html` | 管理空间面板 hint 文案调整（可通过 i18n 处理） |
