# Claude Workspace Launcher

局域网 PWA，从手机启动/管理 Claude Code 工作空间。

## 快速启动

```bash
# 首次安装（注册 launchd 服务）
./install.sh

# 手动启动（调试用）
python3 server.py

# 查看日志
tail -f launcher.log
```

## 访问

手机 Safari 打开：`http://<Mac-IP>:8765`（本机 IP 启动时打印在终端）

## 配置（config.json）

- `pinned`: 置顶的项目名称列表
- `hidden`: 隐藏的项目名称列表
- `require_claude_md`: true = 只显示含 CLAUDE.md 的目录
- `port`: 监听端口，默认 8765

## 服务管理

```bash
# 停止
launchctl unload ~/Library/LaunchAgents/com.user.claude-launcher.plist

# 重启
launchctl unload ~/Library/LaunchAgents/com.user.claude-launcher.plist
launchctl load ~/Library/LaunchAgents/com.user.claude-launcher.plist
```
