"""Flask 服务器: 提供 Web 版 Galgame 播放器。

职责:
  - GET /              : 播放器页面 (player.html)
  - GET /api/project   : 返回 project.json 工程数据 (客户端据此渲染)
  - GET /api/health    : 健康检查
  - GET /assets/<path> : 提供图片 / 音频 / 视频等静态资源 (支持 Range 拖动)

设计要点:
  - 无服务端状态: 存档由客户端 localStorage 管理, 服务器可水平扩展
  - 资源服务做路径越界防护 (限制在工程目录内)
  - send_file(..., conditional=True) 自动处理 HTTP Range 请求,
    使 <audio>/<video> 可拖动进度
"""
from __future__ import annotations

import json
import os
import threading
import webbrowser
from typing import Optional

from flask import (
    Flask,
    abort,
    jsonify,
    render_template,
    send_file,
)

from ..config import ASSETS_DIR_NAME


# 本文件: galpy/web/server.py
_HERE = os.path.dirname(os.path.abspath(__file__))
_TEMPLATE_DIR = os.path.join(_HERE, "templates")
_STATIC_DIR = os.path.join(_HERE, "static")


def _safe_join(base: str, *parts: str) -> Optional[str]:
    """把 parts 拼接到 base 下, 返回规范化的绝对路径; 越界 (逃逸 base) 返回 None。"""
    try:
        # 规范化最终路径
        full = os.path.normpath(os.path.join(base, *parts))
    except (ValueError, TypeError):
        return None
    base_norm = os.path.normpath(base)
    # 必须仍在 base 之下 (或等于 base)
    if full != base_norm and not full.startswith(base_norm + os.sep):
        return None
    return full


def create_app(project_path: str, base_dir: str, title: Optional[str] = None) -> Flask:
    """构造 Flask 应用。

    Args:
        project_path: project.json 的绝对路径
        base_dir:     工程所在目录 (用于解析相对资源路径)
        title:        游戏标题 (页面标题; 为空则从工程读取)
    """
    project_path = os.path.abspath(project_path)
    base_dir = os.path.abspath(base_dir)

    app = Flask(
        __name__,
        template_folder=_TEMPLATE_DIR,
        static_folder=_STATIC_DIR,
    )
    # 允许 jsonify 输出中文原样 (而非 \uXXXX), 跨 Flask 版本兼容
    try:
        app.json.ensure_ascii = False
    except Exception:
        app.config["JSON_AS_ASCII"] = False

    # ---- 预读工程数据 (启动时一次性载入, 避免每次请求读盘) ----
    with open(project_path, "r", encoding="utf-8") as f:
        project_data = json.load(f)
    game_title = title or project_data.get("title") or "GalPy"

    # ==================================================================
    # 路由
    # ==================================================================
    @app.route("/")
    def index():
        """播放器页面。"""
        return render_template(
            "player.html",
            title=game_title,
            width=project_data.get("width", 1280),
            height=project_data.get("height", 720),
        )

    @app.route("/api/project")
    def api_project():
        """返回完整工程数据 (即 project.json 内容)。

        客户端据此驱动场景 / 步骤状态机。
        """
        return jsonify(project_data)

    @app.route("/api/health")
    def api_health():
        return jsonify({"ok": True, "title": game_title})

    @app.route("/assets/<path:rel_path>")
    def assets(rel_path: str):
        """提供工程资源文件 (图片 / 音频 / 视频)。

        工程内资源路径是相对 base_dir 的 (如 "assets/backgrounds/bg.png"),
        故在此拼接到 base_dir 下, 并做越界防护。
        conditional=True 使 send_file 自动处理 Range 请求 (音视频拖动)。
        """
        full = _safe_join(base_dir, rel_path)
        if full is None or not os.path.isfile(full):
            abort(404)
        return send_file(full, conditional=True)

    # 静态资源 (player.css / galpy_player.js) 由 Flask 默认 static 路由提供:
    #   /static/css/player.css
    #   /static/js/galpy_player.js

    return app


def run_server(
    project_path: str,
    host: str = "127.0.0.1",
    port: int = 5000,
    open_browser: bool = True,
    base_dir: Optional[str] = None,
) -> int:
    """启动 Flask 服务器。

    Args:
        project_path: project.json 路径
        host:         监听地址 ("0.0.0.0" 允许局域网访问)
        port:         监听端口
        open_browser: 是否自动打开默认浏览器
        base_dir:     工程目录; 为空则取 project_path 所在目录
    """
    project_path = os.path.abspath(project_path)
    if base_dir is None:
        base_dir = os.path.dirname(project_path)

    app = create_app(project_path, base_dir)

    url = f"http://127.0.0.1:{port}/" if host in ("127.0.0.1", "localhost") else f"http://{host}:{port}/"

    if open_browser:
        # 延迟打开浏览器, 等服务器就绪
        def _open():
            import time
            time.sleep(0.8)
            webbrowser.open(url)

        threading.Thread(target=_open, daemon=True).start()

    print(f"[GalPy Web] 游戏标题已加载, 服务启动中...")
    print(f"[GalPy Web] 本地访问:   http://127.0.0.1:{port}/")
    if host in ("0.0.0.0", "::"):
        print(f"[GalPy Web] 局域网访问: http://<本机IP>:{port}/")
    print(f"[GalPy Web] 工程目录: {base_dir}")
    print(f"[GalPy Web] 按 Ctrl+C 退出。")

    # debug=False 关闭重载器 (重载器会与自动开浏览器冲突); 关闭多线程无意义
    app.run(host=host, port=port, debug=False, threaded=True)
    return 0
