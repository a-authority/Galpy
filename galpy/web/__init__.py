"""GalPy Web 应用: 基于 Flask 的游戏服务器 + 浏览器客户端。

通过浏览器访问同一份 project.json, 实现跨平台 / 多人在线游玩。

用法:
  from galpy.web import run_server
  run_server("path/to/project.json", host="0.0.0.0", port=5000)

命令行:
  python main.py serve <project.json> [--host 0.0.0.0] [--port 5000] [--no-browser]
"""
from .server import create_app, run_server

__all__ = ["create_app", "run_server"]
