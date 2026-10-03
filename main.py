"""GalPy 入口脚本。

运行方式:
  python main.py                 # 启动菜单 (GUI)
  python main.py edit [proj]     # 直接打开编辑器
  python main.py play <proj>     # 直接播放某工程 (桌面)
  python main.py serve <proj>    # 启动 Flask Web 服务器, 浏览器游玩
                                 #   选项: --host 0.0.0.0 --port 5000 --no-browser
  python main.py pack-web <proj> # 构建 Web 部署包 (含 Cloudflare/Vercel/Docker)
  python main.py deploy <proj>   # 命令行在线对接部署 (Cloudflare / Vercel / Docker)
"""
import os
import sys

# 确保工程根目录在搜索路径中, 以便 import galpy
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from galpy.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main() or 0)
