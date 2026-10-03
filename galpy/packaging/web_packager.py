"""Web 打包与云端部署模块: 把 GalPy 工程打包为在线 Web 应用并直接对接部署。

支持平台与形态:
  1. ⚡ Cloudflare Workers / Cloudflare Pages (全边缘 CDN 托管, 免费且性能优异)
  2. ▲ Vercel (极速自动化上线, 全自动 HTTPS 与全球 CDN)
  3. 🐳 Docker 容器 (基于高性能 Alpine Nginx, 支持 Range 请求拖动音视频, 附带 docker-compose)
  4. 🌐 纯静态 Web 应用 + 本地 Flask 启动器 (app.py)

产物目录 dist_web/<标题>/ 包含:
  - index.html               : 播放器页面 (纯前端状态机, 本地 LocalStorage 存档)
  - project.json             : 游戏工程数据
  - assets/                  : 图像、音频、视频资源
  - static/css|js/           : 样式与运行时引擎脚本
  - app.py                   : 内置 Flask 启动器
  - wrangler.toml, worker.js : Cloudflare Workers / Pages 配置
  - _headers                 : Cloudflare 资源缓存与 CORS 规则
  - vercel.json, .vercelignore: Vercel 部署配置
  - Dockerfile, nginx.conf   : Nginx 容器化配置 (优化音视频流传输)
  - Dockerfile.python        : Python 容器化备用配置
  - docker-compose.yml       : Docker 一键启动编排
  - package.json             : npm 常用部署脚本命令
  - deploy-cloudflare.bat/sh : Cloudflare 一键部署脚本
  - deploy-vercel.bat/sh     : Vercel 一键部署脚本
  - docker-run.bat/sh        : Docker 一键运行脚本
  - DEPLOY_GUIDE.md          : 详尽中文部署说明与各平台教程
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import traceback
import webbrowser
from datetime import datetime
from typing import Optional, Tuple

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
    QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPlainTextEdit, QPushButton, QSpinBox, QTabWidget, QTextBrowser,
    QVBoxLayout, QWidget,
)

from ..config import ASSETS_DIR_NAME, PROJECT_FILE_NAME
from ..i18n import get_effective_language, tr
from ..model import Project


_GALPY_PKG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_WEB_STATIC_DIR = os.path.join(_GALPY_PKG_DIR, "web", "static")


def safe_slug(name: str, default: str = "galpy-game") -> str:
    """把任意标题转换为合法的云平台与 Docker 项目标识 (只含小写字母、数字、短横线)。"""
    if not name:
        return default
    ascii_chars = []
    for ch in name.lower():
        if "a" <= ch <= "z" or "0" <= ch <= "9" or ch in ("-", "_"):
            ascii_chars.append(ch if ch != "_" else "-")
    slug = "".join(ascii_chars).strip("-")
    if not slug:
        h = hashlib.md5(name.encode("utf-8")).hexdigest()[:6]
        slug = f"galpy-game-{h}"
    slug = re.sub(r"-+", "-", slug).strip("-")
    if len(slug) < 3:
        slug = f"{slug}-game"
    return slug[:40] or default


def detect_deployment_env() -> dict[str, bool]:
    """检测当前机器上的部署工具可用性。"""
    return {
        "npx": shutil.which("npx") is not None or shutil.which("npx.cmd") is not None,
        "node": shutil.which("node") is not None or shutil.which("node.exe") is not None,
        "wrangler": shutil.which("wrangler") is not None or shutil.which("wrangler.cmd") is not None,
        "vercel": shutil.which("vercel") is not None or shutil.which("vercel.cmd") is not None,
        "docker": shutil.which("docker") is not None or shutil.which("docker.exe") is not None,
    }


# ==============================================================================
# 文件模板
# ==============================================================================

_INDEX_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>{title} - GalPy Web</title>
    <link rel="stylesheet" href="static/css/player.css">
</head>
<body>
    <div id="game-root" class="game-root">
        <div id="bg-layer" class="bg-layer"></div>
        <div id="char-layer" class="char-layer"></div>
        <video id="video-layer" class="video-layer" playsinline></video>
        <div id="dialogue-box" class="dialogue-box hidden">
            <div id="name-plate" class="name-plate hidden"></div>
            <div id="body-text" class="body-text"></div>
            <div id="hint-text" class="hint-text">点击 / 空格 继续</div>
        </div>
        <div id="prompt-label" class="prompt-label hidden"></div>
        <div id="choices-widget" class="choices-widget hidden"></div>
        <button id="quick-save-btn" class="quick-save-btn hidden">💾 存档</button>
        <div id="title-widget" class="overlay hidden">
            <div class="overlay-inner">
                <div id="title-label" class="overlay-title">{title}</div>
                <div class="overlay-sub">— GalPy Web —</div>
                <div class="overlay-spacer"></div>
                <button class="menu-btn" data-act="new-game">▶  开始游戏</button>
                <button class="menu-btn" data-act="continue">↻  继续游戏</button>
                <button class="menu-btn" data-act="load">📂  加载存档</button>
            </div>
        </div>
        <div id="menu-widget" class="overlay hidden">
            <div class="overlay-inner">
                <div class="overlay-title">系统菜单</div>
                <div class="overlay-spacer"></div>
                <button class="menu-btn" data-act="save">💾  保存进度</button>
                <button class="menu-btn" data-act="load-menu">📂  读取进度</button>
                <button class="menu-btn" data-act="title">🏠  返回标题</button>
                <button class="menu-btn" data-act="resume">▶  返回游戏</button>
            </div>
        </div>
        <div id="slot-widget" class="overlay hidden">
            <div class="overlay-inner">
                <div id="slot-header" class="overlay-title">存档</div>
                <div class="overlay-spacer"></div>
                <div id="slot-grid" class="slot-grid"></div>
                <div class="overlay-spacer"></div>
                <button class="menu-btn" data-act="slot-back">←  返回</button>
            </div>
        </div>
        <div id="end-widget" class="overlay hidden">
            <div class="overlay-inner">
                <div class="end-text">— 终 —</div>
                <div id="end-sub" class="end-sub"></div>
                <div class="overlay-spacer"></div>
                <button class="menu-btn" data-act="end-close">返回标题</button>
            </div>
        </div>
        <div id="loading" class="loading">
            <div class="loading-text">正在加载游戏…</div>
        </div>
    </div>
    <script>
        // 静态部署配置: 数据取同目录 project.json, 资源用相对路径 (无前缀)
        window.GALPY_PROJECT_URL = "project.json";
        window.GALPY_ASSET_PREFIX = "";
    </script>
    <script src="static/js/galpy_player.js"></script>
</body>
</html>
"""

_APP_PY_TEMPLATE = '''"""GalPy Web 应用启动器 (由打包器自动生成)。

运行:
  python app.py [port]

特性:
  - 以当前目录为静态根, 服务 index.html / project.json / assets/ / static/
  - 同一份产物既可 python app.py (Flask) 也可 python -m http.server (纯静态)
"""
import os
import sys

from flask import Flask, send_from_directory

HERE = os.path.dirname(os.path.abspath(__file__))


def create_app() -> Flask:
    app = Flask(__name__, static_folder=HERE, static_url_path="")

    @app.route("/")
    def index():
        return send_from_directory(HERE, "index.html")

    return app


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    app = create_app()
    print(f"[GalPy Web] 服务启动: http://127.0.0.1:{port}/  (Ctrl+C 退出)")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''

_WRANGLER_TOML_TEMPLATE = """# Cloudflare Workers 配置文件 (含静态资源绑定)
name = "{slug}"
main = "worker.js"
compatibility_date = "2024-04-01"

# 静态资源绑定目录 (Wrangler v3.78+)
assets = {{ directory = "." }}

[observability]
enabled = true
"""

_CF_ASSETS_IGNORE_TEMPLATE = """.git
.venv
venv
__pycache__
*.pyc
*.bat
*.sh
Dockerfile*
docker-compose.yml
nginx.conf
app.py
README.txt
DEPLOY_GUIDE.md
"""

_CF_WORKER_JS_TEMPLATE = """// Cloudflare Worker 静态资源分发入口
export default {
  async fetch(request, env) {
    return env.ASSETS.fetch(request);
  }
};
"""

_CF_HEADERS_TEMPLATE = """/*
  Access-Control-Allow-Origin: *
  X-Content-Type-Options: nosniff

/assets/*
  Cache-Control: public, max-age=31536000, immutable
  Access-Control-Allow-Origin: *

/static/*
  Cache-Control: public, max-age=86400
  Access-Control-Allow-Origin: *
"""

_VERCEL_JSON_TEMPLATE = """{{
  "version": 2,
  "framework": null,
  "cleanUrls": true,
  "headers": [
    {{
      "source": "/(.*)",
      "headers": [
        {{ "key": "Access-Control-Allow-Origin", "value": "*" }}
      ]
    }},
    {{
      "source": "/assets/(.*)",
      "headers": [
        {{ "key": "Cache-Control", "value": "public, max-age=31536000, immutable" }},
        {{ "key": "Access-Control-Allow-Origin", "value": "*" }}
      ]
    }},
    {{
      "source": "/static/(.*)",
      "headers": [
        {{ "key": "Cache-Control", "value": "public, max-age=86400" }},
        {{ "key": "Access-Control-Allow-Origin", "value": "*" }}
      ]
    }}
  ]
}}
"""

_VERCEL_IGNORE_TEMPLATE = """.git
.venv
venv
__pycache__
*.pyc
*.bat
*.sh
Dockerfile*
docker-compose.yml
nginx.conf
.dockerignore
"""

_NGINX_CONF_TEMPLATE = """server {
    listen 80;
    server_name localhost;

    root /usr/share/nginx/html;
    index index.html;

    # Gzip 压缩
    gzip on;
    gzip_min_length 1024;
    gzip_comp_level 5;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript image/svg+xml;

    # 媒体资源优化 (支持 HTTP 206 Partial Content / 拖动进度)
    location /assets/ {
        expires 30d;
        add_header Cache-Control "public, no-transform";
        add_header Access-Control-Allow-Origin *;
    }

    location /static/ {
        expires 7d;
        add_header Cache-Control "public, no-transform";
        add_header Access-Control-Allow-Origin *;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
"""

_DOCKERFILE_NGINX_TEMPLATE = """# 生产级高性能轻量容器 (Nginx Alpine, 仅 ~15MB)
FROM nginx:alpine
LABEL description="GalPy Visual Novel Web Game"

# 复制自定义 Nginx 配置 (支持媒体 Range 请求与 Gzip)
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 复制游戏网页及资源
COPY . /usr/share/nginx/html

# 清理构建相关文件
RUN rm -f /usr/share/nginx/html/Dockerfile* \\
          /usr/share/nginx/html/docker-compose.yml \\
          /usr/share/nginx/html/nginx.conf \\
          /usr/share/nginx/html/*.bat \\
          /usr/share/nginx/html/*.sh

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
"""

_DOCKERFILE_PYTHON_TEMPLATE = """# 备用: Python Flask 容器镜像
FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir flask
COPY . /app
EXPOSE 5000
CMD ["python", "app.py", "5000"]
"""

_DOCKER_COMPOSE_TEMPLATE = """version: '3.8'

services:
  {slug}:
    build:
      context: .
      dockerfile: Dockerfile.nginx
    image: {slug}:latest
    container_name: {slug}
    ports:
      - "{port}:80"
    restart: unless-stopped
"""

_DOCKER_IGNORE_TEMPLATE = """.git
.venv
venv
__pycache__
*.pyc
*.bat
*.sh
*.md
"""

_PACKAGE_JSON_TEMPLATE = """{{
  "name": "{slug}",
  "version": "1.0.0",
  "private": true,
  "description": "{title} - GalPy Web Game",
  "scripts": {{
    "start": "python app.py 5000",
    "deploy:cf": "npx wrangler pages deploy . --project-name={slug}",
    "deploy:cf:workers": "npx wrangler deploy",
    "deploy:vercel": "npx vercel --prod",
    "docker:build": "docker build -f Dockerfile.nginx -t {slug} .",
    "docker:run": "docker run -d -p {port}:80 --name {slug} {slug}",
    "docker:compose": "docker compose up -d --build"
  }}
}}
"""

_DEPLOY_CF_BAT = """@echo off
chcp 65001 >nul
echo ===================================================
echo  正在部署 {title} 到 Cloudflare Workers (边缘节点)
echo ===================================================
echo 提示: 若已在浏览器中完成授权登录，直接等待上传完成即可。
echo.
npx --yes wrangler deploy
if %errorlevel% neq 0 (
    echo.
    echo [提示] 尝试以 Pages 模式部署...
    npx --yes wrangler pages project create {slug} --production-branch=main >nul 2>nul
    npx --yes wrangler pages deploy . --project-name={slug}
)
echo.
pause
"""

_DEPLOY_CF_SH = """#!/bin/bash
echo "==================================================="
echo " 正在部署 {title} 到 Cloudflare Workers"
echo "==================================================="
npx --yes wrangler deploy
if [ $? -ne 0 ]; then
    npx --yes wrangler pages project create {slug} --production-branch=main 2>/dev/null
    npx --yes wrangler pages deploy . --project-name={slug}
fi
"""

_DEPLOY_VERCEL_BAT = """@echo off
chcp 65001 >nul
echo ===================================================
echo  正在部署 {title} 到 Vercel (生产环境)
echo ===================================================
echo 提示: 首次使用需按提示完成 Vercel 账号授权登录。
echo.
npx --yes vercel --prod
if %errorlevel% neq 0 (
    echo.
    echo [提示] 如果 npx 报错，请确保已安装 Node.js (https://nodejs.org)。
)
echo.
pause
"""

_DEPLOY_VERCEL_SH = """#!/bin/bash
echo "==================================================="
echo " 正在部署 {title} 到 Vercel (生产环境)"
echo "==================================================="
npx --yes vercel --prod
"""

_DOCKER_RUN_BAT = """@echo off
chcp 65001 >nul
echo ===================================================
echo  正在通过 Docker 构建并运行 {title}
echo ===================================================
docker compose up -d --build
if %errorlevel% neq 0 (
    echo [回退尝试] 直接构建并运行镜像...
    docker build -f Dockerfile.nginx -t {slug} .
    docker run -d -p {port}:80 --name {slug} {slug}
)
echo.
echo [成功] 容器已在后台运行!
echo 浏览器在线游玩地址: http://localhost:{port}/
echo.
pause
"""

_DOCKER_RUN_SH = """#!/bin/bash
echo "==================================================="
echo " 正在通过 Docker 构建并运行 {title}"
echo "==================================================="
docker compose up -d --build
if [ $? -ne 0 ]; then
    docker build -f Dockerfile.nginx -t {slug} .
    docker run -d -p {port}:80 --name {slug} {slug}
fi
echo "容器已启动! 浏览器在线游玩地址: http://localhost:{port}/"
"""

_README_TEMPLATE = """GalPy Web 应用 — 部署说明
========================================

游戏标题: {title}
项目标识: {slug}
生成时间: {timestamp}

本目录是一个完整的纯静态 Web 游戏，已内置对接 Cloudflare / Vercel / Docker 容器的所有配置！

【方式一】Cloudflare Pages / Workers (推荐·免费·全球CDN加速)
  - 软件内一键部署: 在 GalPy 编辑器中点击「云端在线部署」->「开始在线部署」。
  - 命令行部署: 双击运行 deploy-cloudflare.bat 或执行:
      npx wrangler pages deploy . --project-name={slug}
  - 网页拖拽部署 (无需安装 Node.js):
      登录 dash.cloudflare.com -> Workers 和 Pages -> 创建 -> Pages -> 上传资产
      将本文件夹直接拖入网页中，即可获得永久免费的 https://{slug}.pages.dev

【方式二】Vercel 部署 (一键上线·全自动HTTPS)
  - 软件内一键部署: 在 GalPy 编辑器中点击「云端在线部署」选择 Vercel。
  - 命令行部署: 双击运行 deploy-vercel.bat 或执行:
      npx vercel --prod
  - 网页部署: 访问 vercel.com 导入本文件夹或绑定 GitHub 仓库。

【方式三】Docker 容器化部署 (私有化与任何云服务器)
  - 本地一键启动: 双击运行 docker-run.bat 或执行:
      docker compose up -d --build
    启动后浏览器访问: http://localhost:{port}/
  - 云端部署: 支持直接部署到 Zeabur, Render, Railway, Fly.io 或各类 VPS 云主机。

【方式四】本地运行
  - Flask:  python app.py {port}
  - 纯静态: python -m http.server {port}

【⚠️ 🇨🇳 中国大陆网络访问特别指引 (自定义域名绑定)】
  Cloudflare 默认域名 (*.pages.dev / *.workers.dev) 与 Vercel 默认域名 (*.vercel.app)
  在中国大陆地区受 DNS 污染或运营商网络阻断，无法直接访问。
  💡 强烈建议在 Cloudflare 或 Vercel 控制台为该项目绑定你的【自定义域名】(如 game.yourdomain.com):
    - Cloudflare: 项目 -> Custom Domains (自定义域) -> 添加域名，享受免翻全球 Anycast CDN 极速加速！
    - Vercel: 项目 -> Settings -> Domains -> 添加域名，DNS 设置 CNAME 指向 cname.vercel-dns.com，
      国内亦可通过 Cloudflare 开启小黄云代理实现免翻稳定直连！

存档说明:
  所有游戏进度保存在玩家浏览器的 localStorage 中，换设备不丢失，无需服务端数据库！
"""

_DEPLOY_GUIDE_MD_ZH = """# 🚀 GalPy 视觉小说 — 云端在线部署与容器化完整指南

本工程已经自动构建为纯静态 Web 应用并生成了完整的云端配置文件。
你可以通过以下任意一种方式将你的 Galgame 发布到互联网，让所有人直接在浏览器中游玩！

---

## ⚡ 方案一：Cloudflare Pages / Workers 部署 (首选推荐)
> **优势**：永久免费、不限流量、全球 Anycast CDN 极速加速、支持绑定自定义域名、全自动 HTTPS。

### 方法 1. 在 GalPy 编辑器中直连部署（最简单）
1. 在 GalPy 菜单中选择 **打包与发布 -> ☁️ 云端在线部署**。
2. 平台选择 **Cloudflare Pages / Workers**。
3. 点击 **「🚀 开始在线部署」**，系统会自动调用 Wrangler 将游戏发布至边缘节点。
4. 部署成功后，界面将直接给出访问链接（如 `https://{slug}.pages.dev`）。

### 方法 2. 双击运行批处理脚本
- Windows 用户：直接双击本目录下的 `deploy-cloudflare.bat`。
- Linux / Mac 用户：执行 `bash deploy-cloudflare.sh`。

### 方法 3. 网页拖拽上传（无需本地安装 Node.js / CLI）
1. 打开 [Cloudflare 控制台](https://dash.cloudflare.com/) 并登录。
2. 在左侧菜单点击 **Workers 和 Pages** -> **创建应用程序** -> 选择 **Pages** 选项卡。
3. 选择 **上传资产 (Upload assets)**。
4. 创建项目名称（建议使用 `{slug}`）。
5. 将本文件夹直接拖入网页上传区域，点击 **部署站点**。
6. 约 20 秒后即可生成全球可访问的官方网址！

---

## ▲ 方案二：Vercel 部署
> **优势**：部署速度极快、开箱即用、支持自定义域名绑定与 GitHub 自动联动。

### 方法 1. 在 GalPy 编辑器中直连部署
1. 在 GalPy 菜单中选择 **打包与发布 -> ☁️ 云端在线部署**。
2. 平台选择 **Vercel**。
3. 点击 **「🚀 开始在线部署」**（首次使用会自动拉起浏览器授权登录或输入 Token）。
4. 部署完成后直接获取 `https://{slug}.vercel.app`。

### 方法 2. 双击批处理脚本
- 直接双击本目录下的 `deploy-vercel.bat` 即可一键完成生产发布。

### 方法 3. GitHub 联动部署
1. 将本文件夹内容推送（Push）到你的 GitHub 仓库。
2. 在 [Vercel 官网](https://vercel.com/) 点击 **Add New Project**，导入该仓库。
3. Framework Preset 选择 **Other**，直接点击 **Deploy** 即可。以后每次 git push 都会自动更新游戏！

---

## 🐳 方案三：Docker 容器化部署
> **优势**：标准化容器镜像、基于极轻量的 Nginx Alpine（约 15MB 内存占用）、完美支持 HTTP 206 媒体 Range 分段拖动、支持离线局域网与任何云容器平台。

### 方法 1. 本地一键启动容器
- Windows：直接双击 `docker-run.bat`。
- 命令行：执行 `docker compose up -d --build`。
- 运行后在浏览器打开：`http://localhost:{port}/` 即可开始游玩。

### 方法 2. 部署到云容器平台（Zeabur / Railway / Render / 宝塔面板）
- 本项目包含 `Dockerfile.nginx`、`Dockerfile.python` 和 `nginx.conf`。
- 在平台中导入仓库后，指定 Dockerfile 路径为 `Dockerfile.nginx`，即可秒级启动容器！

### 方法 3. 部署到个人 Linux 云主机 (VPS / 阿里云 / 腾讯云)
```bash
# 将本文件夹上传到服务器后执行:
docker compose up -d --build
```
即可在服务器的 80/8080 端口提供公网服务。

---

## 🌐 方案四：本地开发与局域网内测
- **使用内置 Flask 启动**：`python app.py 5000`
- **使用 Python 静态服务**：`python -m http.server 8000`

---

## ⚠️ 🇨🇳 中国大陆网络访问特别指引 (自定义域名绑定)

### 为什么默认域名国内无法访问？
- **Cloudflare** 分配的默认二级域名（`*.pages.dev` 与 `*.workers.dev`）在大陆部分网络环境下受运营商 SNI 阻断。
- **Vercel** 分配的默认二级域名（`*.vercel.app`）在大陆被政策性 DNS 污染，解析地址被重定向。

### 💡 最佳解决方案：免费绑定自定义域名 (免翻秒开)

#### 方案 A：Cloudflare Pages / Workers 绑定自定义域名 (极度推荐)
1. 登录 [Cloudflare 控制台](https://dash.cloudflare.com/)，在 **Workers 和 Pages** 中点击你刚刚创建的项目。
2. 点击 **「自定义域 (Custom Domains)」** 标签页。
3. 点击 **「设置自定义域」**，输入你拥有的二级域名（例如 `game.yourdomain.com`）。
4. Cloudflare 会自动配置全球 Anycast 节点解析并签发免费 SSL 证书，完成后国内网络即可极速直连畅玩！

#### 方案 B：Vercel 绑定自定义域名与 CDN 代理
1. 登录 [Vercel 控制台](https://vercel.com/dashboard)，进入该项目。
2. 点击 **Settings** -> **Domains**。
3. 输入你的自定义二级域名（如 `game.yourdomain.com`），点击 **Add**。
4. 在你的 DNS 服务商处（如阿里云/腾讯云 DNS，或 Cloudflare DNS）添加一条记录：
   - **记录类型**：`CNAME`
   - **主机记录**：`game`（对应二级域名前缀）
   - **记录值**：`cname.vercel-dns.com`
   - *(推荐)* 如果你的域名托管在 Cloudflare，把该 CNAME 记录开启**橙色小黄云代理 (Proxied)**，由 Cloudflare 负责海外到国内的高速路由，国内玩家即可免代理畅玩！

---

## 💾 存档机制说明
Web 版播放器采用 **纯前端沙盒状态机** 架构：
- 游戏存档保存在玩家本地浏览器的 `localStorage` 中。
- 支持自动存档与 9 个手动存档槽位。
- 存档数据独立保存在玩家端，无需服务端数据库，保护玩家隐私且完全零服务器运维成本！
"""

_DEPLOY_GUIDE_MD_EN = """# 🚀 GalPy Visual Novel — Cloud Deployment & Containerization Guide

This project has been built as a static Web application with pre-configured cloud deployment files.
You can publish your visual novel to the Internet using any of the following methods, allowing anyone to play instantly in a web browser!

---

## ⚡ Option 1: Cloudflare Pages / Workers (Recommended)
> **Key Benefits**: Free forever, unlimited bandwidth, global Anycast CDN acceleration, custom domains, and automated HTTPS.

### Method 1. Direct Deploy from GalPy Editor (Easiest)
1. Open the GalPy menu and choose **Publish & Deploy -> ☁️ Online Direct Deploy**.
2. Select **Cloudflare Workers** or **Cloudflare Pages**.
3. Click **"🚀 Start Online Deploy"**. The system invokes Wrangler to deploy your game directly to Cloudflare edge nodes.
4. Once completed, your live URL will be displayed (e.g. `https://{slug}.pages.dev`).

### Method 2. Double-Click Batch Script
- **Windows**: Run `deploy-cloudflare.bat` in this folder.
- **Linux / macOS**: Run `bash deploy-cloudflare.sh`.

### Method 3. Web Dashboard Drag & Drop (Zero CLI / Node.js Required)
1. Log into the [Cloudflare Dashboard](https://dash.cloudflare.com/).
2. In the sidebar, select **Workers & Pages** -> **Create application** -> **Pages** tab.
3. Click **Upload assets**.
4. Set a project name (suggested: `{slug}`).
5. Drag and drop this output directory into the upload box and click **Deploy site**.
6. In about 20 seconds, your game is live globally!

---

## ▲ Option 2: Vercel Deployment
> **Key Benefits**: Fast deployment, automated HTTPS, zero-config, and seamless GitHub Git-push CI/CD.

### Method 1. Direct Deploy from GalPy Editor
1. In the GalPy menu, choose **Publish & Deploy -> ☁️ Online Direct Deploy**.
2. Select **Vercel**.
3. Click **"🚀 Start Online Deploy"** (first-time use opens the browser for authorization or prompts for your personal token).
4. Receive your production URL: `https://{slug}.vercel.app`.

### Method 2. Double-Click Batch Script
- Double-click `deploy-vercel.bat` in this folder to deploy to production via command line.

### Method 3. GitHub Automated Git-Push Deploy
1. Push this folder to your GitHub repository.
2. In the [Vercel Dashboard](https://vercel.com/), click **Add New Project** and import the repository.
3. Keep Framework Preset as **Other** and click **Deploy**. Future git pushes will automatically update the online game!

---

## 🐳 Option 3: Docker Container Deployment
> **Key Benefits**: Standardized container image, ultra-lightweight Alpine Nginx (~15MB RAM footprint), native HTTP 206 Byte-Range streaming for audio/video scrub, works on LAN or any cloud host.

### Method 1. Local One-Click Container
- **Windows**: Double-click `docker-run.bat`.
- **Command Line**: Run `docker compose up -d --build`.
- Open in your browser: `http://localhost:{port}/` to start playing.

### Method 2. Cloud Container Platforms (Zeabur / Railway / Render / Fly.io)
- This package includes `Dockerfile.nginx`, `Dockerfile.python`, and `nginx.conf`.
- Import your repository into the container platform and set Dockerfile path to `Dockerfile.nginx`.

### Method 3. Linux Cloud Server (VPS / AWS / DigitalOcean)
```bash
# Upload this folder to your server and run:
docker compose up -d --build
```
Your game will be served publicly on port 80/8080!

---

## 🌐 Option 4: Local Testing & Development
- **Built-in Flask Server**: `python app.py 5000`
- **Standard Python HTTP**: `python -m http.server 8000`

---

## 💡 Custom Domains & Global Access Tips

### Why use a Custom Domain?
- Cloudflare subdomains (`*.pages.dev` / `*.workers.dev`) and Vercel subdomains (`*.vercel.app`) may face regional ISP restrictions or DNS filtering in certain territories (such as mainland China).
- Binding your own custom domain (e.g. `game.yourdomain.com`) ensures unblocked, high-speed access for players worldwide!

#### Cloudflare Pages / Workers Custom Domain:
1. In the Cloudflare Dashboard under **Workers & Pages**, select your project.
2. Go to the **Custom Domains** tab.
3. Click **Set up a custom domain** and enter your domain (e.g. `game.yourdomain.com`).
4. Cloudflare provisions automated SSL and routes global traffic seamlessly.

#### Vercel Custom Domain:
1. In the Vercel Dashboard, select your project -> **Settings** -> **Domains**.
2. Enter your domain (e.g. `game.yourdomain.com`) and click **Add**.
3. Add a `CNAME` record in your DNS provider pointing to `cname.vercel-dns.com`.

---

## 💾 Save & Data Storage Architecture
The Web player is powered by a **pure client-side state machine**:
- Game saves are stored in the player's local browser `localStorage`.
- Includes auto-save and 9 manual save slots.
- Completely client-side: 0 server database needed, 0 maintenance cost, and player privacy is fully protected!
"""

_DEPLOY_GUIDE_MD = _DEPLOY_GUIDE_MD_ZH


def get_deploy_guide_md(title: str, slug: str, port: int) -> str:
    """根据当前生效语言返回中文或英文版在线部署教程。"""
    tmpl = _DEPLOY_GUIDE_MD_EN if get_effective_language() == "en_US" else _DEPLOY_GUIDE_MD_ZH
    return tmpl.format(title=title, slug=slug, port=port)


# ==============================================================================
# 构建 Web 部署包函数
# ==============================================================================

def build_web_package(
    project: Project,
    project_path: str,
    output_dir: str,
    slug: Optional[str] = None,
    port: int = 8080,
    log=None,
) -> str:
    """构建包含所有云端配置与 Dockerfile 的纯静态 Web 部署包, 返回产物目录路径。

    Args:
        project:      Project 对象
        project_path: project.json / .galpy 路径
        output_dir:   输出父目录
        slug:         项目英文标识 (用于域名与容器名; 为空则自动推导)
        port:         Docker 容器暴露端口 (默认 8080)
        log:          日志回调 log(str)
    """
    def _log(msg: str) -> None:
        if log:
            log(msg)

    title = project.title or "GalPy"
    proj_slug = slug or safe_slug(title)
    dest = os.path.join(output_dir, proj_slug)
    is_en = get_effective_language() == "en_US"

    _log(f"[1/6] Preparing output directory: {dest}" if is_en else f"[1/6] 准备输出目录: {dest}")
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    os.makedirs(dest, exist_ok=True)

    # ---- 1. 复制工程数据与资源 ----
    _log("[2/6] Copying project data and game assets (images/audio/video)…" if is_en else "[2/6] 复制工程数据与游戏素材 (图片/音频/视频)…")
    shutil.copy2(project_path, os.path.join(dest, PROJECT_FILE_NAME))
    proj_dir = os.path.dirname(project_path)
    assets_src = os.path.join(proj_dir, ASSETS_DIR_NAME)
    assets_dst = os.path.join(dest, ASSETS_DIR_NAME)
    if os.path.isdir(assets_src):
        shutil.copytree(assets_src, assets_dst, dirs_exist_ok=True)
    else:
        os.makedirs(assets_dst, exist_ok=True)

    # ---- 2. 复制 Web 客户端 (static/) ----
    _log("[3/6] Copying Web player core runtime (css / js)…" if is_en else "[3/6] 复制 Web 播放器核心运行时 (css / js)…")
    if os.path.isdir(_WEB_STATIC_DIR):
        shutil.copytree(_WEB_STATIC_DIR, os.path.join(dest, "static"), dirs_exist_ok=True)
    else:
        _log(f"  [Warning] Web client directory not found: {_WEB_STATIC_DIR}" if is_en else f"  [警告] 未找到 Web 客户端目录: {_WEB_STATIC_DIR}")

    # ---- 3. 生成 index.html 与 Flask 启动器 ----
    _log("[4/6] Generating main index.html and local launcher app.py…" if is_en else "[4/6] 生成主页面 index.html 与本地启动器 app.py…")
    with open(os.path.join(dest, "index.html"), "w", encoding="utf-8") as f:
        f.write(_INDEX_HTML_TEMPLATE.format(title=title))

    with open(os.path.join(dest, "app.py"), "w", encoding="utf-8") as f:
        f.write(_APP_PY_TEMPLATE)

    # ---- 4. 生成云平台配置文件 (Cloudflare & Vercel) ----
    _log("[5/6] Generating Cloudflare Workers/Pages & Vercel deployment configs…" if is_en else "[5/6] 生成 Cloudflare Workers/Pages 与 Vercel 在线配置文件…")
    # Cloudflare
    with open(os.path.join(dest, "wrangler.toml"), "w", encoding="utf-8") as f:
        f.write(_WRANGLER_TOML_TEMPLATE.format(slug=proj_slug))
    with open(os.path.join(dest, "worker.js"), "w", encoding="utf-8") as f:
        f.write(_CF_WORKER_JS_TEMPLATE)
    with open(os.path.join(dest, "_headers"), "w", encoding="utf-8") as f:
        f.write(_CF_HEADERS_TEMPLATE)
    with open(os.path.join(dest, ".assetsignore"), "w", encoding="utf-8") as f:
        f.write(_CF_ASSETS_IGNORE_TEMPLATE)

    # Vercel
    with open(os.path.join(dest, "vercel.json"), "w", encoding="utf-8") as f:
        f.write(_VERCEL_JSON_TEMPLATE.format(slug=proj_slug))
    with open(os.path.join(dest, ".vercelignore"), "w", encoding="utf-8") as f:
        f.write(_VERCEL_IGNORE_TEMPLATE)

    # ---- 5. 生成容器文件与一键脚本 ----
    _log("[6/6] Generating Docker configuration, deployment scripts & documentation…" if is_en else "[6/6] 生成 Docker 容器化文件、一键部署脚本及部署指南…")
    # Docker
    with open(os.path.join(dest, "nginx.conf"), "w", encoding="utf-8") as f:
        f.write(_NGINX_CONF_TEMPLATE)
    with open(os.path.join(dest, "Dockerfile.nginx"), "w", encoding="utf-8") as f:
        f.write(_DOCKERFILE_NGINX_TEMPLATE)
    with open(os.path.join(dest, "Dockerfile.python"), "w", encoding="utf-8") as f:
        f.write(_DOCKERFILE_PYTHON_TEMPLATE)
    with open(os.path.join(dest, "docker-compose.yml"), "w", encoding="utf-8") as f:
        f.write(_DOCKER_COMPOSE_TEMPLATE.format(slug=proj_slug, port=port))
    with open(os.path.join(dest, ".dockerignore"), "w", encoding="utf-8") as f:
        f.write(_DOCKER_IGNORE_TEMPLATE)

    # package.json
    with open(os.path.join(dest, "package.json"), "w", encoding="utf-8") as f:
        f.write(_PACKAGE_JSON_TEMPLATE.format(title=title, slug=proj_slug, port=port))

    # 一键批处理脚本 (Windows & Linux/Mac)
    with open(os.path.join(dest, "deploy-cloudflare.bat"), "w", encoding="utf-8") as f:
        f.write(_DEPLOY_CF_BAT.format(title=title, slug=proj_slug))
    with open(os.path.join(dest, "deploy-cloudflare.sh"), "w", encoding="utf-8") as f:
        f.write(_DEPLOY_CF_SH.format(title=title, slug=proj_slug))
    with open(os.path.join(dest, "deploy-vercel.bat"), "w", encoding="utf-8") as f:
        f.write(_DEPLOY_VERCEL_BAT.format(title=title, slug=proj_slug))
    with open(os.path.join(dest, "deploy-vercel.sh"), "w", encoding="utf-8") as f:
        f.write(_DEPLOY_VERCEL_SH.format(title=title, slug=proj_slug))
    with open(os.path.join(dest, "docker-run.bat"), "w", encoding="utf-8") as f:
        f.write(_DOCKER_RUN_BAT.format(title=title, slug=proj_slug, port=port))
    with open(os.path.join(dest, "docker-run.sh"), "w", encoding="utf-8") as f:
        f.write(_DOCKER_RUN_SH.format(title=title, slug=proj_slug, port=port))

    # 说明文档
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(os.path.join(dest, "README.txt"), "w", encoding="utf-8") as f:
        f.write(_README_TEMPLATE.format(title=title, slug=proj_slug, port=port, timestamp=timestamp))
    with open(os.path.join(dest, "DEPLOY_GUIDE.md"), "w", encoding="utf-8") as f:
        f.write(get_deploy_guide_md(title=title, slug=proj_slug, port=port))
    with open(os.path.join(dest, "DEPLOY_GUIDE_ZH.md"), "w", encoding="utf-8") as f:
        f.write(_DEPLOY_GUIDE_MD_ZH.format(title=title, slug=proj_slug, port=port))
    with open(os.path.join(dest, "DEPLOY_GUIDE_EN.md"), "w", encoding="utf-8") as f:
        f.write(_DEPLOY_GUIDE_MD_EN.format(title=title, slug=proj_slug, port=port))

    _log(f"✅ Web deployment package built successfully! Output directory: {dest}" if is_en else f"✅ Web 部署包构建完成! 目录: {dest}")
    return dest


# ==============================================================================
# 后台打包 Worker
# ==============================================================================

class WebPackageWorker(QThread):
    """后台执行 Web 打包, 实时回传日志。"""

    log = Signal(str)
    finished_ok = Signal(str)   # 产物目录
    finished_err = Signal(str)  # 错误信息

    def __init__(
        self,
        project: Project,
        project_path: str,
        output_dir: str,
        slug: Optional[str] = None,
        port: int = 8080,
        parent=None,
    ):
        super().__init__(parent)
        self.project = project
        self.project_path = project_path
        self.output_dir = output_dir
        self.slug = slug
        self.port = port

    def run(self) -> None:
        try:
            dest = build_web_package(
                self.project,
                self.project_path,
                self.output_dir,
                slug=self.slug,
                port=self.port,
                log=lambda m: self.log.emit(m),
            )
            self.finished_ok.emit(dest)
        except Exception as e:
            is_en = get_effective_language() == "en_US"
            self.finished_err.emit(f"Web packaging failed:\n{e}\n{traceback.format_exc()}" if is_en else f"Web 打包失败:\n{e}\n{traceback.format_exc()}")


def normalize_deployed_url(url: str, slug: str) -> str:
    """清理并规范化部署 URL，去除产生 SSL 证书错误的预览 hash 前缀 (如 6d166a13.slug.pages.dev -> slug.pages.dev)。"""
    if not url:
        return url
    url = url.strip().rstrip(".,;'\"")
    if "pages.dev" in url:
        # 去掉类似 [hash]. 预览前缀，保留正式的 https://<slug>.pages.dev/
        m = re.search(r"https?://(?:[a-fA-F0-9_-]+\.)*(" + re.escape(slug) + r"\.pages\.dev)(?:/.*)?", url)
        if m:
            return f"https://{m.group(1)}/"
        return f"https://{slug}.pages.dev/"
    return url


# ==============================================================================
# 后台云端直连部署 Worker
# ==============================================================================

class CloudDeployWorker(QThread):
    """后台执行在线对接部署 (Cloudflare / Vercel / Docker), 实时流式回传控制台日志并捕获网址。"""

    log = Signal(str)
    url_detected = Signal(str)
    finished_ok = Signal(str)    # 成功部署并捕获到的在线网址
    finished_err = Signal(str)   # 失败信息

    def __init__(
        self,
        platform: str,           # "cloudflare" | "vercel" | "docker"
        dist_dir: str,
        slug: str,
        port: int = 8080,
        token: str = "",
        account_id: str = "",
        is_prod: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self.platform = platform
        self.dist_dir = dist_dir
        self.slug = slug
        self.port = port
        self.token = token.strip()
        self.account_id = account_id.strip()
        self.is_prod = is_prod
        self._proc: Optional[subprocess.Popen] = None
        self._canceled = False

    def cancel(self) -> None:
        """终止当前部署进程。"""
        self._canceled = True
        if self._proc is not None:
            try:
                self._proc.terminate()
            except Exception:
                pass
            try:
                self._proc.kill()
            except Exception:
                pass

    def run(self) -> None:
        try:
            self._do_deploy()
        except Exception as e:
            is_en = get_effective_language() == "en_US"
            prefix = "Deployment execution exception:\n" if is_en else "部署执行异常:\n"
            self.finished_err.emit(f"{prefix}{e}\n{traceback.format_exc()}")

    def _do_deploy(self) -> None:
        is_en = get_effective_language() == "en_US"
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        cmd_str = ""
        expected_url = ""

        if self.platform in ("cloudflare", "cloudflare_workers", "cf"):
            msg = f"[Cloudflare Workers] Deploying project '{self.slug}' to Cloudflare Workers (Edge)..." if is_en else f"[Cloudflare Workers] 正在部署项目 '{self.slug}' 到 Cloudflare Workers (边缘节点)..."
            self.log.emit(msg)
            if self.token:
                env["CLOUDFLARE_API_TOKEN"] = self.token
            if self.account_id:
                env["CLOUDFLARE_ACCOUNT_ID"] = self.account_id

            wrangler_bin = "wrangler" if shutil.which("wrangler") else "npx --yes wrangler"
            cmd_str = f"{wrangler_bin} deploy"
            expected_url = f"https://{self.slug}.workers.dev"

        elif self.platform in ("cloudflare_pages", "pages"):
            msg = f"[Cloudflare Pages] Deploying project '{self.slug}' to Cloudflare Pages..." if is_en else f"[Cloudflare Pages] 正在部署项目 '{self.slug}' 到 Cloudflare Pages..."
            self.log.emit(msg)
            if self.token:
                env["CLOUDFLARE_API_TOKEN"] = self.token
            if self.account_id:
                env["CLOUDFLARE_ACCOUNT_ID"] = self.account_id

            wrangler_bin = "wrangler" if shutil.which("wrangler") else "npx --yes wrangler"
            reg_msg = f"➜ Auto-registering Pages project: {self.slug} ..." if is_en else f"➜ 自动注册 Pages 项目: {self.slug} ..."
            self.log.emit(reg_msg)
            create_cmd = f"{wrangler_bin} pages project create {self.slug} --production-branch=main"
            subprocess.run(create_cmd, cwd=self.dist_dir, shell=True, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            cmd_str = f"{wrangler_bin} pages deploy . --project-name={self.slug} --branch=main"
            expected_url = f"https://{self.slug}.pages.dev"

        elif self.platform == "vercel":
            msg = f"[Vercel] Preparing to deploy project '{self.slug}' to Vercel platform..." if is_en else f"[Vercel] 准备对接部署项目 '{self.slug}' 到 Vercel 平台..."
            self.log.emit(msg)
            vercel_bin = "vercel" if shutil.which("vercel") else "npx --yes vercel"
            prod_flag = "--prod" if self.is_prod else ""
            token_flag = f'--token="{self.token}"' if self.token else ""
            cmd_str = f"{vercel_bin} {prod_flag} --yes {token_flag}".strip()
            expected_url = f"https://{self.slug}.vercel.app"

        elif self.platform == "docker":
            msg = f"[Docker] Preparing to build and run container service '{self.slug}', exposed port: {self.port}..." if is_en else f"[Docker] 准备构建并运行容器服务 '{self.slug}', 暴露端口: {self.port}..."
            self.log.emit(msg)
            cmd_str = "docker compose up -d --build"
            expected_url = f"http://localhost:{self.port}/"

        else:
            self.finished_err.emit(f"Unknown deployment target: {self.platform}" if is_en else f"未知部署目标: {self.platform}")
            return

        self.log.emit(f"➜ Executing command: {cmd_str}" if is_en else f"➜ 正在执行命令: {cmd_str}")
        self.log.emit(f"➜ Working directory: {self.dist_dir}\n" if is_en else f"➜ 工作目录: {self.dist_dir}\n")

        self._proc = subprocess.Popen(
            cmd_str,
            cwd=self.dist_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            shell=True,
            env=env,
        )

        detected_url = ""
        url_regex = re.compile(
            r"https?://[a-zA-Z0-9][-a-zA-Z0-9.]*(?:\.vercel\.app|\.pages\.dev|\.workers\.dev)[^\s]*"
        )

        assert self._proc.stdout is not None
        while True:
            line_bytes = self._proc.stdout.readline()
            if not line_bytes:
                break
            try:
                line = line_bytes.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    line = line_bytes.decode("gbk")
                except UnicodeDecodeError:
                    line = line_bytes.decode("utf-8", errors="replace")

            clean_line = line.rstrip("\r\n")
            self.log.emit(clean_line)

            m = url_regex.search(clean_line)
            if m:
                raw_url = m.group(0).rstrip(".,;'\"")
                norm_url = normalize_deployed_url(raw_url, self.slug)
                detected_url = norm_url
                self.url_detected.emit(norm_url)

        return_code = self._proc.wait()
        if self._canceled:
            self.finished_err.emit("Deployment cancelled by user." if is_en else "部署已被用户终止。")
            return

        if return_code == 0:
            final_url = detected_url or expected_url
            final_url = normalize_deployed_url(final_url, self.slug)
            if any(k in final_url for k in ("pages.dev", "workers.dev")):
                tip = "\n💡 [Network Tip] Cloudflare global CDN is active. Custom domains can be bound in the dashboard anytime!" if is_en else "\n💡 [网络提醒] Cloudflare 默认域名在国内受运营商阻断，建议在控制台绑定自定义域名即可免翻极速畅玩！"
                self.log.emit(tip)
            elif "vercel.app" in final_url:
                tip = "\n💡 [Network Tip] Vercel edge deployment is active. You can bind custom domains in Settings -> Domains." if is_en else "\n💡 [网络提醒] Vercel 默认域名 (*.vercel.app) 在国内受 DNS 污染，建议在 Settings->Domains 绑定自定义域名即可免翻秒开！"
                self.log.emit(tip)
            self.finished_ok.emit(final_url)
        else:
            # 针对 Docker Compose 失败的情况，尝试以标准 docker build & run 容错启动
            if self.platform == "docker":
                fb_msg = "\n[Fallback] docker compose failed, attempting direct docker build & docker run..." if is_en else "\n[自动容错] docker compose 命令未成功，尝试直接执行 docker build 与 docker run..."
                self.log.emit(fb_msg)
                fallback_cmd = (
                    f"docker build -f Dockerfile.nginx -t {self.slug} . && "
                    f"docker run -d -p {self.port}:80 --name {self.slug} {self.slug}"
                )
                self.log.emit(f"➜ Executing fallback command: {fallback_cmd}\n" if is_en else f"➜ 正在执行备用命令: {fallback_cmd}\n")
                self._proc = subprocess.Popen(
                    fallback_cmd,
                    cwd=self.dist_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    shell=True,
                    env=env,
                )
                while True:
                    line_bytes = self._proc.stdout.readline()
                    if not line_bytes:
                        break
                    try:
                        line = line_bytes.decode("utf-8")
                    except UnicodeDecodeError:
                        line = line_bytes.decode("gbk", errors="replace")
                    self.log.emit(line.rstrip("\r\n"))
                if self._proc.wait() == 0:
                    self.finished_ok.emit(expected_url)
                    return

            exit_msg = f"Deployment process exited with code: {return_code}" if is_en else f"部署进程退出，退出代码: {return_code}"
            self.finished_err.emit(exit_msg)


# ==============================================================================
# Web 打包与在线部署综合对话框
# ==============================================================================

class WebPackageDialog(QDialog):
    """Web 打包与在线对接部署对话框。

    包含三个选项卡:
      - Tab 0: 🚀 云端在线直连部署 (Cloudflare / Vercel / 容器)
      - Tab 1: 📦 本地 Web 部署包导出
      - Tab 2: 📖 详细部署指引与教程
    """

    def __init__(
        self,
        project: Project,
        project_path: str,
        parent=None,
        initial_tab: int = 0,
    ):
        super().__init__(parent)
        self.project = project
        self.project_path = project_path
        self._pkg_worker: Optional[WebPackageWorker] = None
        self._deploy_worker: Optional[CloudDeployWorker] = None
        self._last_dest: Optional[str] = None
        self._deployed_url: str = ""

        title = self.project.title or "游戏"
        self._default_slug = safe_slug(title)

        self.setWindowTitle(f"{tr('web_dlg_title', '☁️ 云端在线部署与 Web 游戏发布')} — {title}")
        self.resize(800, 600)

        # 主选项卡
        self._tabs = QTabWidget(self)

        # 构建三个子页面
        self._tab_deploy = self._create_deploy_tab()
        self._tab_export = self._create_export_tab()
        self._tab_guide = self._create_guide_tab()

        self._tabs.addTab(self._tab_deploy, tr("tab_cloud_deploy", "🚀 云端在线直连部署"))
        self._tabs.addTab(self._tab_export, tr("tab_export_pkg", "📦 本地 Web 部署包导出"))
        self._tabs.addTab(self._tab_guide, tr("tab_deploy_guide", "📖 详细部署教程与指引"))

        lay = QVBoxLayout(self)
        lay.addWidget(self._tabs, 1)

        bottom_bar = QHBoxLayout()
        bottom_bar.addStretch(1)
        btn_close = QPushButton(tr("close", "关闭"))
        btn_close.clicked.connect(self._on_close_clicked)
        bottom_bar.addWidget(btn_close)
        lay.addLayout(bottom_bar)

        self._tabs.setCurrentIndex(max(0, min(initial_tab, 2)))

    # --------------------------------------------------------------------------
    # Tab 0: 云端在线直连部署
    # --------------------------------------------------------------------------
    def _create_deploy_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        is_en = (get_effective_language() == "en_US")

        # 平台配置组
        gb_config = QGroupBox("Online Platform & Deployment Settings" if is_en else "在线对接平台与参数设置")
        form = QFormLayout(gb_config)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self._deploy_platform = QComboBox()
        if is_en:
            self._deploy_platform.addItem("⚡ Cloudflare Workers (Zero-Config Edge · Recommended)", "cloudflare")
            self._deploy_platform.addItem("📄 Cloudflare Pages (Static Pages Hosting)", "cloudflare_pages")
            self._deploy_platform.addItem("▲ Vercel (Fast Auto Deploy · Free HTTPS)", "vercel")
            self._deploy_platform.addItem("🐳 Docker Container (Local 1-Click / Image Export)", "docker")
        else:
            self._deploy_platform.addItem("⚡ Cloudflare Workers (全自动发布·免预建·推荐)", "cloudflare")
            self._deploy_platform.addItem("📄 Cloudflare Pages (静态页面托管)", "cloudflare_pages")
            self._deploy_platform.addItem("▲ Vercel (极速上线·全自动HTTPS·免费)", "vercel")
            self._deploy_platform.addItem("🐳 Docker 容器 (本地一键运行 / 容器镜像导出)", "docker")
        self._deploy_platform.currentIndexChanged.connect(self._on_platform_changed)

        self._deploy_slug = QLineEdit(self._default_slug)
        self._deploy_slug.setPlaceholderText("Subdomain & container ID, e.g. my-game" if is_en else "用于生成二级域名与容器标识，如 my-game")

        # 平台特定项
        self._cf_token_edit = QLineEdit()
        self._cf_token_edit.setPlaceholderText("API Token (or click Login on right)" if is_en else "API Token (或点击右侧一键登录)")
        self._cf_token_edit.setEchoMode(QLineEdit.Password)
        self._btn_cf_login = QPushButton("🔑 " + ("Login to Cloudflare" if is_en else "登录 Cloudflare"))
        self._btn_cf_login.setToolTip("Log in to Cloudflare via browser once for persistent access!" if is_en else "通过浏览器一键登录 Cloudflare，登录一次永久有效，免填 Token！")
        self._btn_cf_login.clicked.connect(self._login_cloudflare)
        self._cf_token_row_widget = QWidget()
        cf_token_row = QHBoxLayout(self._cf_token_row_widget)
        cf_token_row.setContentsMargins(0, 0, 0, 0)
        cf_token_row.addWidget(self._cf_token_edit, 1)
        cf_token_row.addWidget(self._btn_cf_login)

        self._cf_account_edit = QLineEdit()
        self._cf_account_edit.setPlaceholderText("Optional: Cloudflare Account ID" if is_en else "可选: Cloudflare Account ID")

        self._vercel_token_edit = QLineEdit()
        self._vercel_token_edit.setPlaceholderText("Vercel Token (or click Login on right)" if is_en else "Vercel Token (或点击右侧一键登录)")
        self._vercel_token_edit.setEchoMode(QLineEdit.Password)
        self._btn_vc_login = QPushButton("🔑 " + ("Login to Vercel" if is_en else "登录 Vercel"))
        self._btn_vc_login.setToolTip("Log in to Vercel via browser without manually typing Token!" if is_en else "通过浏览器一键登录 Vercel，免填 Token！")
        self._btn_vc_login.clicked.connect(self._login_vercel)
        self._vc_token_row_widget = QWidget()
        vc_token_row = QHBoxLayout(self._vc_token_row_widget)
        vc_token_row.setContentsMargins(0, 0, 0, 0)
        vc_token_row.addWidget(self._vercel_token_edit, 1)
        vc_token_row.addWidget(self._btn_vc_login)

        self._vercel_prod_chk = QCheckBox("Deploy to Production" if is_en else "部署到生产环境 (Production)")
        self._vercel_prod_chk.setChecked(True)

        self._docker_port_spin = QSpinBox()
        self._docker_port_spin.setRange(80, 65535)
        self._docker_port_spin.setValue(8080)

        form.addRow("Select Platform:" if is_en else "选择平台:", self._deploy_platform)
        form.addRow("Project Slug (ID):" if is_en else "项目英文标识:", self._deploy_slug)
        self._lbl_cf_token = QLabel("CF API Token:")
        form.addRow(self._lbl_cf_token, self._cf_token_row_widget)
        self._lbl_cf_acc = QLabel("CF Account ID:" if is_en else "CF 账户 ID:")
        form.addRow(self._lbl_cf_acc, self._cf_account_edit)
        self._lbl_vc_token = QLabel("Vercel Token:")
        form.addRow(self._lbl_vc_token, self._vc_token_row_widget)
        self._lbl_vc_env = QLabel("Vercel Environment:" if is_en else "Vercel 环境:")
        form.addRow(self._lbl_vc_env, self._vercel_prod_chk)
        self._lbl_docker_port = QLabel("Container Port:" if is_en else "容器映射端口:")
        form.addRow(self._lbl_docker_port, self._docker_port_spin)

        lay.addWidget(gb_config)

        # 平台网络访问指引横幅 (根据选择平台动态更新说明)
        self._cn_notice_card = QFrame()
        self._cn_notice_card.setStyleSheet(
            "QFrame { background: #1c2128; border: 1px solid #30363d; border-left: 4px solid #f0883e; border-radius: 6px; padding: 8px 12px; }"
            "QLabel { color: #e6edf3; font-size: 12px; line-height: 1.5; }"
        )
        notice_lay = QVBoxLayout(self._cn_notice_card)
        notice_lay.setContentsMargins(0, 0, 0, 0)
        self._cn_notice_label = QLabel()
        self._cn_notice_label.setWordWrap(True)
        self._cn_notice_label.setOpenExternalLinks(True)
        notice_lay.addWidget(self._cn_notice_label)
        lay.addWidget(self._cn_notice_card)

        # 环境检测信息栏
        self._env_label = QLabel()
        self._refresh_env_status()
        env_bar = QHBoxLayout()
        env_bar.addWidget(self._env_label, 1)
        btn_refresh_env = QPushButton("🔄 检测环境")
        btn_refresh_env.clicked.connect(self._refresh_env_status)
        env_bar.addWidget(btn_refresh_env)
        lay.addLayout(env_bar)

        # 部署成功结果卡片 (默认隐藏)
        self._result_card = QFrame()
        self._result_card.setFrameShape(QFrame.StyledPanel)
        self._result_card.setStyleSheet(
            "QFrame { background: #163828; border: 1px solid #2ea043; border-radius: 6px; padding: 10px; }"
            "QLabel { color: #e6edf3; font-size: 13px; }"
        )
        card_lay = QHBoxLayout(self._result_card)
        self._result_label = QLabel("🎉 游戏已成功部署上线！")
        self._result_label.setWordWrap(True)
        card_lay.addWidget(self._result_label, 1)

        self._btn_open_browser = QPushButton(tr("btn_open_browser", "🌐 在浏览器中打开"))
        self._btn_open_browser.setObjectName("SuccessBtn")
        self._btn_open_browser.clicked.connect(self._open_deployed_url)
        card_lay.addWidget(self._btn_open_browser)

        self._btn_copy_url = QPushButton(tr("btn_copy_url", "📋 复制链接"))
        self._btn_copy_url.clicked.connect(self._copy_deployed_url)
        card_lay.addWidget(self._btn_copy_url)

        self._result_card.setVisible(False)
        lay.addWidget(self._result_card)

        # 控制台实时输出
        lay.addWidget(QLabel("部署控制台日志:"))
        self._deploy_log = QPlainTextEdit()
        self._deploy_log.setReadOnly(True)
        self._deploy_log.setStyleSheet(
            "QPlainTextEdit { background: #181a20; color: #e0e0e0; font-family: Consolas, 'Courier New', monospace; font-size: 12px; }"
        )
        lay.addWidget(self._deploy_log, 1)

        # 操作按钮
        act_bar = QHBoxLayout()
        self._btn_start_deploy = QPushButton(tr("btn_start_deploy", "🚀 开始在线对接部署"))
        self._btn_start_deploy.setObjectName("PrimaryBtn")
        self._btn_start_deploy.setMinimumHeight(38)
        self._btn_start_deploy.clicked.connect(self._start_online_deploy)

        self._btn_stop_deploy = QPushButton(tr("btn_stop_deploy", "🛑 停止"))
        self._btn_stop_deploy.setObjectName("DangerBtn")
        self._btn_stop_deploy.setEnabled(False)
        self._btn_stop_deploy.clicked.connect(self._stop_online_deploy)

        self._btn_open_deploy_dir = QPushButton(tr("btn_open_folder", "📂 浏览生成的文件"))
        self._btn_open_deploy_dir.clicked.connect(self._open_output_dir)

        act_bar.addWidget(self._btn_start_deploy, 2)
        act_bar.addWidget(self._btn_stop_deploy)
        act_bar.addWidget(self._btn_open_deploy_dir)
        lay.addLayout(act_bar)

        self._on_platform_changed()
        return w

    def _on_platform_changed(self) -> None:
        """根据选择的平台动态显隐特定表单字段与网络访问指引。"""
        plat = self._deploy_platform.currentData()
        is_cf = plat in ("cloudflare", "cloudflare_pages")
        is_vercel = (plat == "vercel")
        is_docker = (plat == "docker")

        self._lbl_cf_token.setVisible(is_cf)
        self._cf_token_row_widget.setVisible(is_cf)
        self._lbl_cf_acc.setVisible(is_cf)
        self._cf_account_edit.setVisible(is_cf)

        self._lbl_vc_token.setVisible(is_vercel)
        self._vc_token_row_widget.setVisible(is_vercel)
        self._lbl_vc_env.setVisible(is_vercel)
        self._vercel_prod_chk.setVisible(is_vercel)

        self._lbl_docker_port.setVisible(is_docker)
        self._docker_port_spin.setVisible(is_docker)

        is_en = (get_effective_language() == "en_US")
        if is_cf:
            self._cn_notice_card.setVisible(True)
            if is_en:
                self._cn_notice_label.setText(
                    "💡 <b>Cloudflare Network & Custom Domain Guide</b>:<br>"
                    "Cloudflare official subdomains (<code>*.pages.dev</code> and <code>*.workers.dev</code>) might face ISP restrictions in some regions (such as mainland China).<br>"
                    "<b>【Recommended Solution】</b>: In your Cloudflare project dashboard, navigate to <b>Custom Domains</b> to bind your custom domain for free, enjoying global Anycast CDN acceleration and automated SSL!"
                )
            else:
                self._cn_notice_label.setText(
                    "💡 <b>🇨🇳 中国大陆网络访问指引 (Cloudflare)</b>：<br>"
                    "Cloudflare 官方分配的 <code>*.pages.dev</code> 与 <code>*.workers.dev</code> 默认域名在国内部分运营商网络受限无法直连。<br>"
                    "<b>【免翻畅玩方案】</b>：部署完成后在 Cloudflare 项目控制台点击「<b>自定义域 (Custom Domains)</b>」免费绑定你的独立域名，即可享受全球 Anycast CDN 极速加速！"
                )
        elif is_vercel:
            self._cn_notice_card.setVisible(True)
            if is_en:
                self._cn_notice_label.setText(
                    "💡 <b>Vercel Network & Custom Domain Guide</b>:<br>"
                    "Vercel official subdomains (<code>*.vercel.app</code>) are subject to regional DNS pollution in mainland China and cannot be reached directly.<br>"
                    "<b>【Recommended Solution】</b>: In your Vercel project dashboard, go to <b>Settings ➔ Domains</b> and bind your custom domain. Point a CNAME record to <code>cname.vercel-dns.com</code> (or proxy with Cloudflare Orange Cloud) for unblocked fast access!"
                )
            else:
                self._cn_notice_label.setText(
                    "💡 <b>🇨🇳 中国大陆网络访问指引 (Vercel)</b>：<br>"
                    "Vercel 官方分配的 <code>*.vercel.app</code> 默认域名在中国大陆由于政策性 DNS 污染无法直接访问。<br>"
                    "<b>【免翻畅玩方案】</b>：部署完成后在 Vercel 项目控制台进入 <b>Settings ➔ Domains</b> 绑定你的自定义域名，DNS 添加 CNAME 解析指向 <code>cname.vercel-dns.com</code>（推荐搭配 Cloudflare 代理开启小黄云），国内玩家即可秒开！"
                )
        elif is_docker:
            self._cn_notice_card.setVisible(True)
            if is_en:
                self._cn_notice_label.setText(
                    "💡 <b>🐳 Docker Container Runtime Notice</b>:<br>"
                    "The container runs locally at <code>http://localhost:" + str(self._docker_port_spin.value()) + "/</code> with high-performance HTTP media streaming and byte-range support. "
                    "It is completely independent of external domain blocks, ideal for LAN parties, intranet tunnels, or VPS servers."
                )
            else:
                self._cn_notice_label.setText(
                    "💡 <b>🐳 Docker 容器化运行提示</b>：<br>"
                    "容器将在本地（<code>http://localhost:" + str(self._docker_port_spin.value()) + "/</code>）直接提供高性能 HTTP 媒体流服务，"
                    "完全不受境外域名污染与网络限制，适合局域网联机、内网穿透（如 cpolar/frp）或上传至 VPS 云主机独立运营。"
                )
        else:
            self._cn_notice_card.setVisible(False)

    def _login_cloudflare(self) -> None:
        """弹出一个可见的交互终端窗口执行 npx wrangler login，由浏览器完成授权。"""
        is_en = (get_effective_language() == "en_US")
        try:
            if os.name == "nt":
                subprocess.Popen(
                    'start cmd /c "chcp 65001 >nul & title ' + ('Cloudflare Login' if is_en else 'Cloudflare 登录授权') + ' & '
                    'echo ======================================================== & '
                    'echo   ' + ('Launching Cloudflare authorization...' if is_en else '正在启动 Cloudflare 授权登录...') + ' & '
                    'echo   ' + ('Browser will open automatically, please click [Allow].' if is_en else '系统会自动在浏览器中打开授权页面，请点击【Allow】允许访问。') + ' & '
                    'echo ======================================================== & '
                    'npx --yes wrangler login & echo. & echo ' + ('Authorized! Press any key to exit...' if is_en else '授权完成! 按任意键退出本窗口...') + ' & pause"',
                    shell=True,
                )
            else:
                subprocess.Popen(["x-terminal-emulator", "-e", "npx --yes wrangler login"] if sys.platform != "darwin" else ["open", "-a", "Terminal", "npx", "--yes", "wrangler", "login"])
            QMessageBox.information(
                self,
                "Authorization" if is_en else "授权登录",
                ("A terminal window has opened for login!\n\n"
                 "Your default browser will open Cloudflare authorization page. Click 'Allow/Authorize' to complete.\n"
                 "Login is saved permanently on this machine.") if is_en else
                ("已弹出授权终端窗口！\n\n"
                 "系统会自动打开默认浏览器打开 Cloudflare 授权页，点击「允许/Authorize」即可完成登录。\n"
                 "登录一次永久有效，完成后便可直接在软件内一键免 Token 部署！")
            )
        except Exception as e:
            QMessageBox.warning(self, "Login Failed" if is_en else "登录失败", f"{e}")

    def _login_vercel(self) -> None:
        """提供一键获取 Token 与命令行登录两种方式。"""
        is_en = (get_effective_language() == "en_US")
        reply = QMessageBox.question(
            self,
            "Vercel Authorization" if is_en else "Vercel 授权认证",
            ("We recommend using a Personal Access Token (fastest and most reliable).\n\n"
             "• Click [Yes]: Open Vercel Token creation page in browser, create and paste your token into 'Vercel Token' above;\n"
             "• Click [No]: Try interactive 'vercel login' via command line terminal.") if is_en else
            ("Vercel 推荐使用【Personal Access Token】(最快最稳，不受命令行卡顿影响)。\n\n"
             "• 点击【是 (Yes)】：直接打开 Vercel 官网 Token 页面，创建后复制粘贴到上方「Vercel Token」输入框；\n"
             "• 点击【否 (No)】：在终端尝试运行 vercel login 命令行交互登录。"),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply == QMessageBox.Yes:
            webbrowser.open("https://vercel.com/account/tokens")
            return

        try:
            if os.name == "nt":
                subprocess.Popen(
                    'start cmd /c "chcp 65001 >nul & title ' + ('Vercel Login' if is_en else 'Vercel 登录授权') + ' & '
                    'echo ======================================================== & '
                    'echo   ' + ('Launching Vercel authorization...' if is_en else '正在启动 Vercel 授权登录...') + ' & '
                    'echo ======================================================== & '
                    'npx --yes --registry=https://registry.npmmirror.com vercel login & '
                    'echo. & echo ' + ('Authorized! Press any key to exit...' if is_en else '授权完成! 按任意键退出本窗口...') + ' & pause"',
                    shell=True,
                )
            else:
                subprocess.Popen(["x-terminal-emulator", "-e", "npx --yes --registry=https://registry.npmmirror.com vercel login"] if sys.platform != "darwin" else ["open", "-a", "Terminal", "npx", "--yes", "vercel", "login"])
        except Exception as e:
            QMessageBox.warning(self, "Login Failed" if is_en else "登录失败", f"{e}")

    def _refresh_env_status(self) -> None:
        """检测并更新 Node.js / Docker 等环境状态。"""
        env = detect_deployment_env()
        cf_ready = env["npx"] or env["wrangler"]
        vercel_ready = env["npx"] or env["vercel"]
        docker_ready = env["docker"]

        is_en = (get_effective_language() == "en_US")
        ready_text = "Ready" if is_en else "已就绪"
        missing_text = "Not found" if is_en else "未检测到"

        def _badge(ok: bool, name: str) -> str:
            return f"<b style='color:#3fb950;'>✔ {name}</b>" if ok else f"<span style='color:#8b949e;'>✖ {name} ({missing_text})</span>"

        prefix = "<b>Environment Check:</b>" if is_en else "<b>环境检测:</b>"
        text = (
            f"{prefix} Node.js/npx: {_badge(cf_ready, ready_text)} &nbsp;|&nbsp; "
            f"Docker: {_badge(docker_ready, ready_text)}"
        )
        self._env_label.setText(text)

    # --------------------------------------------------------------------------
    # Tab 1: 本地 Web 部署包导出
    # --------------------------------------------------------------------------
    def _create_export_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        form = QFormLayout()
        self._pkg_title_edit = QLineEdit(self.project.title)
        self._pkg_output_edit = QLineEdit(os.path.join(os.path.dirname(self.project_path), "dist_web"))
        btn_browse = QPushButton(tr("btn_choose", "浏览…"))
        btn_browse.clicked.connect(self._browse_output)

        out_row = QHBoxLayout()
        out_row.addWidget(self._pkg_output_edit, 1)
        out_row.addWidget(btn_browse)

        is_en = (get_effective_language() == "en_US")
        form.addRow("Game Title:" if is_en else "游戏名称:", self._pkg_title_edit)
        form.addRow("Output Directory:" if is_en else "输出目录:", out_row)

        gb_options = QGroupBox("Included Deployment Configurations & Scripts" if is_en else "包含的在线部署配置与脚本")
        opt_lay = QVBoxLayout(gb_options)
        self._chk_cf = QCheckBox("Cloudflare Workers / Pages config (wrangler.toml, _headers, worker.js)" if is_en else "Cloudflare Workers / Pages 静态分发配置 (wrangler.toml, _headers, worker.js)")
        self._chk_cf.setChecked(True)
        self._chk_vercel = QCheckBox("Vercel deployment config (vercel.json, .vercelignore)" if is_en else "Vercel 自动化部署配置 (vercel.json, .vercelignore)")
        self._chk_vercel.setChecked(True)
        self._chk_docker = QCheckBox("Docker container config (Dockerfile, docker-compose.yml, nginx.conf)" if is_en else "Docker 高性能容器配置 (Dockerfile, docker-compose.yml, nginx.conf)")
        self._chk_docker.setChecked(True)
        self._chk_scripts = QCheckBox("1-Click deployment scripts (.bat / .sh)" if is_en else "Windows / Linux 一键部署脚本 (.bat / .sh)")
        self._chk_scripts.setChecked(True)
        self._chk_flask = QCheckBox("Local Flask server launcher script (app.py)" if is_en else "本地 Flask 独立服务器启动脚本 (app.py)")
        self._chk_flask.setChecked(True)

        for c in (self._chk_cf, self._chk_vercel, self._chk_docker, self._chk_scripts, self._chk_flask):
            opt_lay.addWidget(c)

        lay.addLayout(form)
        lay.addWidget(gb_options)

        lay.addWidget(QLabel("Build Log:" if is_en else "打包日志:"))
        self._pkg_log = QPlainTextEdit()
        self._pkg_log.setReadOnly(True)
        self._pkg_log.setStyleSheet(
            "QPlainTextEdit { background: #181a20; color: #e0e0e0; font-family: Consolas, monospace; font-size: 12px; }"
        )
        lay.addWidget(self._pkg_log, 1)

        b_row = QHBoxLayout()
        self._btn_start_pkg = QPushButton(tr("btn_start_pkg", "📦 开始构建 Web 部署包"))
        self._btn_start_pkg.setObjectName("PrimaryBtn")
        self._btn_start_pkg.setMinimumHeight(36)
        self._btn_start_pkg.clicked.connect(self._start_packaging)

        self._btn_open_pkg_dir = QPushButton(tr("btn_open_output", "打开输出目录"))
        self._btn_open_pkg_dir.setObjectName("SuccessBtn")
        self._btn_open_pkg_dir.setEnabled(False)
        self._btn_open_pkg_dir.clicked.connect(self._open_output_dir)

        b_row.addWidget(self._btn_start_pkg)
        b_row.addStretch(1)
        b_row.addWidget(self._btn_open_pkg_dir)
        lay.addLayout(b_row)

        return w

    # --------------------------------------------------------------------------
    # Tab 2: 部署指引与教程
    # --------------------------------------------------------------------------
    def _create_guide_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setMarkdown(get_deploy_guide_md(
            title=self.project.title or "GalPy",
            slug=self._default_slug,
            port=8080,
        ))
        lay.addWidget(browser)
        return w

    # --------------------------------------------------------------------------
    # 动作响应
    # --------------------------------------------------------------------------
    def _browse_output(self) -> None:
        title = "Select Output Directory" if get_effective_language() == "en_US" else "选择输出目录"
        d = QFileDialog.getExistingDirectory(self, title)
        if d:
            self._pkg_output_edit.setText(d)

    def _open_output_dir(self) -> None:
        path = self._last_dest or self._pkg_output_edit.text()
        if os.path.isdir(path):
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        else:
            is_en = get_effective_language() == "en_US"
            QMessageBox.information(self, "Notice" if is_en else "提示", f"Directory does not exist yet:\n{path}" if is_en else f"目录尚不存在:\n{path}")

    def _start_packaging(self) -> None:
        is_en = get_effective_language() == "en_US"
        out_dir = self._pkg_output_edit.text().strip()
        if not out_dir:
            QMessageBox.warning(self, "Notice" if is_en else "提示", "Please select an output directory." if is_en else "请选择输出目录。")
            return
        os.makedirs(out_dir, exist_ok=True)
        self.project.title = self._pkg_title_edit.text().strip() or self.project.title
        self.project.save(self.project_path)

        self._pkg_log.clear()
        self._btn_start_pkg.setEnabled(False)
        self._btn_open_pkg_dir.setEnabled(False)

        slug = safe_slug(self.project.title)
        self._pkg_worker = WebPackageWorker(
            self.project, self.project_path, out_dir, slug=slug, port=8080, parent=self
        )
        self._pkg_worker.log.connect(self._pkg_log.appendPlainText)
        self._pkg_worker.finished_ok.connect(self._on_pkg_ok)
        self._pkg_worker.finished_err.connect(self._on_pkg_err)
        self._pkg_worker.start()

    def _on_pkg_ok(self, dest: str) -> None:
        is_en = get_effective_language() == "en_US"
        self._last_dest = dest
        self._btn_start_pkg.setEnabled(True)
        self._btn_open_pkg_dir.setEnabled(True)
        self._pkg_log.appendPlainText(f"\n🎉 Congratulations! Web package built successfully!\nPath: {dest}" if is_en else f"\n🎉 恭喜! Web 部署包已构建完毕!\n路径: {dest}")
        QMessageBox.information(
            self, "Packaging Complete" if is_en else "打包完成",
            (f"Web application package built successfully!\n\nOutput folder:\n{dest}\n\nCloudflare, Vercel, and Docker configuration files with one-click deployment scripts have been generated."
             if is_en else
             f"Web 应用打包成功!\n\n产物目录:\n{dest}\n\n已自动生成 Cloudflare、Vercel 与 Docker 配置文件及一键发布脚本。")
        )

    def _on_pkg_err(self, msg: str) -> None:
        is_en = get_effective_language() == "en_US"
        self._btn_start_pkg.setEnabled(True)
        self._pkg_log.appendPlainText(f"\n❌ {msg}")
        QMessageBox.critical(self, "Packaging Failed" if is_en else "打包失败", msg)

    # --------------------------------------------------------------------------
    # 在线部署逻辑
    # --------------------------------------------------------------------------
    def _start_online_deploy(self) -> None:
        """一键触发: 自动先构建最新的 Web 包，然后立即在后台执行直连部署。"""
        is_en = get_effective_language() == "en_US"
        slug = self._deploy_slug.text().strip()
        if not slug:
            QMessageBox.warning(self, "Notice" if is_en else "提示", "Please enter a project identifier (letters/numbers/hyphens)." if is_en else "请输入项目标识 (英文/数字/中划线)。")
            return
        slug = safe_slug(slug)
        self._deploy_slug.setText(slug)

        # 检查 Node / Docker 环境并给予友好提示
        env = detect_deployment_env()
        plat = self._deploy_platform.currentData()
        if plat in ("cloudflare", "vercel") and not env["npx"] and not env[plat]:
            reply = QMessageBox.question(
                self,
                "Node.js Not Detected" if is_en else "未检测到 Node.js",
                ("Node.js or npx was not found in your system PATH.\n\n"
                 "• If Node.js is installed, ensure it is added to your PATH environment variable.\n"
                 "• If not installed, you can install Node.js (https://nodejs.org);\n"
                 "  Or you can directly drag & drop the generated Web folder into Cloudflare Pages / Vercel web console!\n\n"
                 "Do you still want to attempt running the command?"
                 if is_en else
                 "未在系统 PATH 中找到 Node.js 或 npx。\n\n"
                 "• 如果已安装 Node.js，请确保其加入了 PATH 环境变量。\n"
                 "• 如果未安装，建议安装 Node.js (https://nodejs.org)；\n"
                 "  或者你也可以直接将生成的 Web 文件夹拖入 Cloudflare Pages / Vercel 网页控制台完成零环境部署！\n\n"
                 "是否仍要尝试继续执行命令？"),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                self._tabs.setCurrentIndex(1)  # 引导切换到本地导出页
                return

        if plat == "docker" and not env["docker"]:
            reply = QMessageBox.question(
                self,
                "Docker Not Detected" if is_en else "未检测到 Docker",
                ("Docker environment was not detected in system PATH.\n\n"
                 "Please check if Docker Desktop is running.\n\n"
                 "Do you still want to attempt running?"
                 if is_en else
                 "未在系统 PATH 中检测到 Docker 环境。\n\n"
                 "请确认 Docker Desktop 是否正在运行。\n\n"
                 "是否仍要尝试继续执行？"),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        # 准备输出目录并先同步构建最新的 Web 包
        out_dir = os.path.join(os.path.dirname(self.project_path), "dist_web")
        os.makedirs(out_dir, exist_ok=True)
        self.project.save(self.project_path)

        self._deploy_log.clear()
        self._result_card.setVisible(False)
        self._btn_start_deploy.setEnabled(False)
        self._btn_stop_deploy.setEnabled(True)

        self._deploy_log.appendPlainText("[System] Compiling game assets and building deployment package…" if is_en else "[系统] 正在编译游戏资源并生成部署包…")
        port = self._docker_port_spin.value()

        try:
            dest = build_web_package(
                self.project,
                self.project_path,
                out_dir,
                slug=slug,
                port=port,
                log=lambda m: self._deploy_log.appendPlainText(f"  {m}"),
            )
            self._last_dest = dest
        except Exception as e:
            self._btn_start_deploy.setEnabled(True)
            self._btn_stop_deploy.setEnabled(False)
            self._deploy_log.appendPlainText(f"\n[Error] Build package failed: {e}" if is_en else f"\n[错误] 构建部署包失败: {e}")
            QMessageBox.critical(self, "Build Error" if is_en else "构建错误", f"{e}")
            return

        self._deploy_log.appendPlainText(f"\n[System] Package ready, initiating {plat} deployment…\n" if is_en else f"\n[系统] 部署包就绪，开始执行 {plat} 对接部署…\n")

        token = self._cf_token_edit.text() if plat in ("cloudflare", "cloudflare_pages") else self._vercel_token_edit.text()
        account_id = self._cf_account_edit.text() if plat in ("cloudflare", "cloudflare_pages") else ""
        is_prod = self._vercel_prod_chk.isChecked() if plat == "vercel" else True

        self._deploy_worker = CloudDeployWorker(
            platform=plat,
            dist_dir=dest,
            slug=slug,
            port=port,
            token=token,
            account_id=account_id,
            is_prod=is_prod,
            parent=self,
        )
        self._deploy_worker.log.connect(self._deploy_log.appendPlainText)
        self._deploy_worker.url_detected.connect(self._on_url_detected)
        self._deploy_worker.finished_ok.connect(self._on_deploy_ok)
        self._deploy_worker.finished_err.connect(self._on_deploy_err)
        self._deploy_worker.start()

    def _stop_online_deploy(self) -> None:
        if self._deploy_worker and self._deploy_worker.isRunning():
            self._deploy_worker.cancel()
            is_en = get_effective_language() == "en_US"
            self._deploy_log.appendPlainText("\n[System] Sending termination signal…" if is_en else "\n[系统] 正在发送终止信号…")
            self._btn_stop_deploy.setEnabled(False)

    def _get_platform_access_tip(self, url: str) -> Tuple[str, str]:
        """根据部署后的 URL 生成国内网络访问提示 (HTML 卡片提示, 纯文本弹窗/日志提示)。"""
        is_en = get_effective_language() == "en_US"
        if any(k in url for k in ("pages.dev", "workers.dev")):
            if is_en:
                html = (
                    "<div style='margin-top:8px; padding:8px 12px; background:#1e293b; border:1px solid #388bfd; border-radius:5px; color:#93c5fd; font-size:12px; line-height:1.5;'>"
                    "🌐 <b>Cloudflare Global Edge Active</b>:<br>"
                    "Cloudflare's default domain (*.pages.dev) is accessible worldwide. "
                    "You can also attach custom branded domains anytime in the Cloudflare dashboard."
                    "</div>"
                )
                text = (
                    "\n\n🌐 Cloudflare Network Notice:\n"
                    "Cloudflare default domain (*.pages.dev / *.workers.dev) is active.\n"
                    "💡 You can attach a Custom Domain in Cloudflare dashboard for direct custom domain access."
                )
            else:
                html = (
                    "<div style='margin-top:8px; padding:8px 12px; background:#2d2812; border:1px solid #d29922; border-radius:5px; color:#ffdd88; font-size:12px; line-height:1.5;'>"
                    "⚠️ <b>🇨🇳 中国大陆网络访问提示</b>：<br>"
                    "Cloudflare 官方分配的默认二级域名在国内部分运营商网络受限无法直连。<br>"
                    "💡 <b>国内免翻畅玩方案</b>：登录 Cloudflare 控制台该项目，进入「<b>自定义域 (Custom Domains)</b>」绑定自己的域名，全球 Anycast CDN 极速加速！"
                    "</div>"
                )
                text = (
                    "\n\n⚠️ 中国大陆网络访问指引:\n"
                    "Cloudflare 默认域名 (*.pages.dev / *.workers.dev) 在国内部分网络环境下可能受阻。\n"
                    "💡 建议在 Cloudflare 控制台该项目中绑定【自定义域名】(Custom Domain)，国内玩家即可免代理秒开畅玩！"
                )
            return html, text
        elif "vercel.app" in url:
            if is_en:
                html = (
                    "<div style='margin-top:8px; padding:8px 12px; background:#1e293b; border:1px solid #388bfd; border-radius:5px; color:#93c5fd; font-size:12px; line-height:1.5;'>"
                    "🌐 <b>Vercel Edge Deployment Active</b>:<br>"
                    "Your game is published on Vercel's global CDN. You can bind custom domains in Vercel project ➔ <b>Settings ➔ Domains</b>."
                    "</div>"
                )
                text = (
                    "\n\n🌐 Vercel Edge Deployment:\n"
                    "Default domain (*.vercel.app) is active globally.\n"
                    "💡 You can configure custom domains under Settings -> Domains."
                )
            else:
                html = (
                    "<div style='margin-top:8px; padding:8px 12px; background:#2d2812; border:1px solid #d29922; border-radius:5px; color:#ffdd88; font-size:12px; line-height:1.5;'>"
                    "⚠️ <b>🇨🇳 中国大陆网络访问提示</b>：<br>"
                    "Vercel 官方分配的 <code>*.vercel.app</code> 默认域名在中国大陆由于政策性 DNS 污染无法直接访问。<br>"
                    "💡 <b>国内免翻畅玩方案</b>：登录 Vercel 控制台进入该项目 ➔ <b>Settings ➔ Domains</b> 绑定自定义域名，"
                    "DNS 添加 CNAME 指向 <code>cname.vercel-dns.com</code>（推荐搭配 Cloudflare 代理开启小黄云），国内玩家即可秒开！"
                    "</div>"
                )
                text = (
                    "\n\n⚠️ 中国大陆网络访问指引:\n"
                    "Vercel 默认域名 (*.vercel.app) 在中国大陆由于政策性 DNS 污染无法直接访问。\n"
                    "💡 建议在 Vercel 控制台该项目中 (Settings -> Domains) 绑定【自定义域名】，"
                    "并设置 CNAME 解析指向 cname.vercel-dns.com (推荐通过 Cloudflare 代理开启小黄云)，国内玩家即可免代理流畅游玩！"
                )
            return html, text
        elif any(k in url for k in ("localhost", "127.0.0.1")):
            if is_en:
                html = (
                    "<div style='margin-top:8px; padding:8px 12px; background:#1b2a3a; border:1px solid #388bfd; border-radius:5px; color:#a5d6ff; font-size:12px; line-height:1.5;'>"
                    "🐳 <b>Local Docker Container Active</b>:<br>"
                    "The game is running locally in Docker container. Access via localhost or share via LAN/tunneling tools."
                    "</div>"
                )
                text = (
                    "\n\n🐳 Local Container Notice:\n"
                    "Game is running in a local Docker container."
                )
            else:
                html = (
                    "<div style='margin-top:8px; padding:8px 12px; background:#1b2a3a; border:1px solid #388bfd; border-radius:5px; color:#a5d6ff; font-size:12px; line-height:1.5;'>"
                    "🐳 <b>本地 Docker 容器服务</b>：<br>"
                    "游戏已在本地容器内运行，完全不受公网域名污染或封锁影响。可通过局域网 IP 或内网穿透（如 cpolar / frp）分享给好友！"
                    "</div>"
                )
                text = (
                    "\n\n🐳 本地容器服务提示:\n"
                    "游戏正在本地 Docker 容器运行，局域网与单机可直接游玩，完全不受境外域名限制。"
                )
            return html, text
        return "", ""

    def _on_url_detected(self, url: str) -> None:
        is_en = get_effective_language() == "en_US"
        self._deployed_url = normalize_deployed_url(url, self._deploy_slug.text().strip())
        cn_tip, _ = self._get_platform_access_tip(self._deployed_url)
        header_text = "<b>🎉 Game successfully deployed online!</b><br>Online URL: " if is_en else "<b>🎉 游戏已成功部署上线！</b><br>在线访问地址: "
        self._result_label.setText(
            f"{header_text}<a href='{self._deployed_url}' style='color:#58a6ff; font-weight:bold;'>{self._deployed_url}</a>"
            f"{cn_tip}"
        )
        self._result_card.setVisible(True)

    def _on_deploy_ok(self, final_url: str) -> None:
        is_en = get_effective_language() == "en_US"
        self._btn_start_deploy.setEnabled(True)
        self._btn_stop_deploy.setEnabled(False)
        self._deployed_url = normalize_deployed_url(final_url or self._deployed_url, self._deploy_slug.text().strip())
        if not self._deployed_url:
            self._deployed_url = f"http://localhost:{self._docker_port_spin.value()}/"

        cn_tip, cn_msg_tip = self._get_platform_access_tip(self._deployed_url)

        title_str = "<b>🎉 Congratulations! Game successfully deployed online!</b><br>Online URL: " if is_en else "<b>🎉 恭喜！游戏已成功发布上线！</b><br>在线访问网址: "
        self._result_label.setText(
            f"{title_str}<a href='{self._deployed_url}' style='color:#58a6ff; font-weight:bold;'>{self._deployed_url}</a>"
            f"{cn_tip}"
        )
        self._result_card.setVisible(True)
        self._deploy_log.appendPlainText(f"\n==================================================")
        ok_msg = f"  ✅ Deployment complete! Online URL: {self._deployed_url}" if is_en else f"  ✅ 部署完成！在线网址: {self._deployed_url}"
        self._deploy_log.appendPlainText(ok_msg)
        if cn_msg_tip:
            self._deploy_log.appendPlainText(cn_msg_tip.strip())
        self._deploy_log.appendPlainText(f"==================================================\n")

        mb_title = "Deployment Succeeded" if is_en else "发布成功"
        mb_body = (
            f"The game has been successfully deployed online!\n\nAccess URL:\n{self._deployed_url}\n\nYou can click 'Open in Browser' to play immediately!"
            if is_en else
            f"游戏已成功发布上线！\n\n在线访问链接:\n{self._deployed_url}\n\n可以直接点击「在浏览器中打开」进行游玩！"
        )
        QMessageBox.information(
            self, mb_title,
            f"{mb_body}{cn_msg_tip}"
        )

    def _on_deploy_err(self, err_msg: str) -> None:
        is_en = get_effective_language() == "en_US"
        self._btn_start_deploy.setEnabled(True)
        self._btn_stop_deploy.setEnabled(False)
        err_header = "\n❌ Deployment incomplete:\n" if is_en else "\n❌ 部署未完成:\n"
        self._deploy_log.appendPlainText(f"{err_header}{err_msg}")

        full_log = self._deploy_log.toPlainText()
        if "CLOUDFLARE_API_TOKEN" in full_log or "non-interactive" in full_log:
            q_title = "Cloudflare Not Authenticated" if is_en else "Cloudflare 尚未授权登录"
            q_body = (
                "Cloudflare deployment failed: Not logged in or API Token not set.\n\n"
                "[Recommended] Click 'Yes' to launch a terminal window and log in via your browser (one-time setup);\n"
                "[Alternative] Click 'No' and provide your CF API Token above, or run deploy-cloudflare.bat directly."
                if is_en else
                "Cloudflare 部署失败: 尚未登录或未设置 API Token。\n\n"
                "【推荐】点击「是」立即弹出终端窗口通过浏览器一键登录 (只需登录一次即可永久使用)；\n"
                "【备选】点击「否」您可以手动在上方输入 CF API Token，或者使用生成的 deploy-cloudflare.bat 脚本部署。"
            )
            reply = QMessageBox.question(
                self, q_title, q_body,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if reply == QMessageBox.Yes:
                self._login_cloudflare()
            return

        if "login" in full_log.lower() and "vercel" in full_log.lower():
            q_title = "Vercel Not Logged In" if is_en else "Vercel 尚未登录"
            q_body = (
                "Vercel deployment failed: Authorization required.\n\n"
                "Would you like to open a terminal to log into Vercel now?"
                if is_en else
                "Vercel 部署失败: 尚未登录授权。\n\n"
                "是否立即打开终端进行 Vercel 一键登录？"
            )
            reply = QMessageBox.question(
                self, q_title, q_body,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if reply == QMessageBox.Yes:
                self._login_vercel()
            return

        w_title = "Deployment Notice" if is_en else "部署提示"
        w_body = (
            f"Deployment did not complete successfully:\n{err_msg}\n\n"
            f"Note: Check the log output for details, or export the package locally to upload manually via Web UI."
            if is_en else
            f"部署未完全成功:\n{err_msg}\n\n"
            f"提示: 您可以查看控制台日志了解详情，或者在「本地 Web 部署包导出」导出后，"
            f"使用网页端拖拽上传部署。"
        )
        QMessageBox.warning(self, w_title, w_body)

    def _open_deployed_url(self) -> None:
        if self._deployed_url:
            webbrowser.open(self._deployed_url)

    def _copy_deployed_url(self) -> None:
        if self._deployed_url:
            clipboard = QApplication.clipboard()
            if clipboard:
                clipboard.setText(self._deployed_url)
                is_en = get_effective_language() == "en_US"
                title = "Copied" if is_en else "复制成功"
                msg = f"Online URL copied to clipboard:\n{self._deployed_url}" if is_en else f"在线网址已复制到剪贴板:\n{self._deployed_url}"
                QMessageBox.information(self, title, msg)

    def _on_close_clicked(self) -> None:
        if self._deploy_worker and self._deploy_worker.isRunning():
            is_en = get_effective_language() == "en_US"
            title = "Deployment In Progress" if is_en else "正在部署中"
            msg = (
                "Deployment is still running in background. Cancel and exit?"
                if is_en else
                "后台部署进程仍在运行，确定要关闭窗口并终止部署吗？"
            )
            reply = QMessageBox.question(
                self, title, msg,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
            self._deploy_worker.cancel()
        self.accept()
