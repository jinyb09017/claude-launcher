#!/bin/bash
# 安装 Claude Launcher 为 launchd 服务

set -e

PLIST_SRC="$(dirname "$0")/com.user.claude-launcher.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/com.user.claude-launcher.plist"

echo "安装 Claude Launcher..."

# 停止旧服务（如有）
launchctl unload "$PLIST_DEST" 2>/dev/null || true

# 复制 plist
cp "$PLIST_SRC" "$PLIST_DEST"

# 加载服务
launchctl load "$PLIST_DEST"

echo "✓ 服务已启动"
echo ""
echo "访问地址:"
python3 -c "import socket; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.connect(('8.8.8.8',80)); print(f'  http://{s.getsockname()[0]}:8765'); s.close()"
echo ""
echo "查看日志: tail -f $(dirname "$0")/launcher.log"
