#!/usr/bin/env python3
"""Claude Workspace Launcher — LAN-accessible PWA to start claude sessions by directory."""

import http.server
from http.server import ThreadingHTTPServer

from api import Handler
from config import load_config
from network import get_local_ip
from workspace import start_tmux_monitor


if __name__ == "__main__":
    cfg = load_config()
    port = cfg.get("port", 8765)
    ip = get_local_ip()
    start_tmux_monitor()
    print(f"Claude Launcher  http://{ip}:{port}")
    print(f"Local            http://localhost:{port}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
