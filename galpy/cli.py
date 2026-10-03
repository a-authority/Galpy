"""GalPy 命令行入口逻辑, 供 main.py 与 python -m galpy 复用。

用法:
  python main.py                          -> 启动菜单 (GUI)
  python main.py launcher                 -> 启动菜单
  python main.py edit [proj]              -> 直接打开编辑器
  python main.py play <proj>              -> 直接播放某工程 (桌面)
  python main.py serve <proj> [选项]      -> 启动 Flask Web 服务器, 浏览器游玩
                                             选项: --host <addr>  默认 127.0.0.1
                                                   --port <n>     默认 5000
                                                   --no-browser   不自动打开浏览器
  python main.py pack-web <proj> [选项]   -> 构建 Web 部署包 (含 Cloudflare/Vercel/Docker)
                                             选项: --out <dir>    默认 dist_web
                                                   --slug <name>  项目英文标识
  python main.py deploy <proj> [选项]     -> 命令行对接云端一键部署
                                             选项: --platform <cloudflare|vercel|docker>
                                                   --slug <name>
                                                   --token <token>
                                                   --port <8080>
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys


def _parse_serve_args(args):
    """解析 serve 子命令参数: <project.json> [--host H] [--port P] [--no-browser]。"""
    host = "127.0.0.1"
    port = 5000
    open_browser = True
    project = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--host" and i + 1 < len(args):
            host = args[i + 1]; i += 2
        elif a == "--port" and i + 1 < len(args):
            port = int(args[i + 1]); i += 2
        elif a == "--no-browser":
            open_browser = False; i += 1
        elif a in ("-h", "--help"):
            print("用法: python main.py serve <project.json> [--host 0.0.0.0] [--port 5000] [--no-browser]")
            sys.exit(0)
        else:
            project = a; i += 1
    return project, host, port, open_browser


def _parse_pack_web_args(args):
    """解析 pack-web 参数: <project> [--out dir] [--slug name] [--port 8080]。"""
    project = None
    out_dir = "dist_web"
    slug = None
    port = 8080
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--out" and i + 1 < len(args):
            out_dir = args[i + 1]; i += 2
        elif a in ("--slug", "--name") and i + 1 < len(args):
            slug = args[i + 1]; i += 2
        elif a == "--port" and i + 1 < len(args):
            port = int(args[i + 1]); i += 2
        elif a in ("-h", "--help"):
            print("用法: python main.py pack-web <project> [--out dist_web] [--slug name] [--port 8080]")
            sys.exit(0)
        else:
            project = a; i += 1
    return project, out_dir, slug, port


def _parse_deploy_args(args):
    """解析 deploy 参数: <project> [--platform cf|vercel|docker] [--slug name] [--token T] [--port 8080]。"""
    project = None
    platform = "cloudflare"
    slug = None
    token = ""
    account_id = ""
    port = 8080
    is_prod = True
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--platform", "-p") and i + 1 < len(args):
            p = args[i + 1].lower()
            if p in ("cf", "cloudflare", "pages"):
                platform = "cloudflare"
            elif p in ("vercel", "vc"):
                platform = "vercel"
            elif p in ("docker", "container"):
                platform = "docker"
            else:
                platform = p
            i += 2
        elif a in ("--slug", "--name") and i + 1 < len(args):
            slug = args[i + 1]; i += 2
        elif a == "--token" and i + 1 < len(args):
            token = args[i + 1]; i += 2
        elif a == "--account-id" and i + 1 < len(args):
            account_id = args[i + 1]; i += 2
        elif a == "--port" and i + 1 < len(args):
            port = int(args[i + 1]); i += 2
        elif a == "--preview":
            is_prod = False; i += 1
        elif a in ("-h", "--help"):
            print("用法: python main.py deploy <project> [--platform cloudflare|vercel|docker] [--slug name] [--token T] [--port 8080]")
            sys.exit(0)
        else:
            project = a; i += 1
    return project, platform, slug, token, account_id, port, is_prod


def main() -> int:
    args = sys.argv[1:]

    # 打包态: 冻结的 exe 内含 project.json 时, 直接播放该游戏
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        bundled = os.path.join(base, "project.json")
        if os.path.exists(bundled):
            from .runtime import run_player
            return run_player(bundled)

    from .runtime import run_editor, run_launcher, run_player

    mode = args[0] if args else "launcher"

    if mode in ("launcher", "menu", ""):
        return run_launcher()
    if mode == "edit":
        return run_editor(args[1] if len(args) > 1 else None)
    if mode == "play":
        if len(args) < 2:
            print("用法: python main.py play <project.json>")
            return 1
        return run_player(args[1])
    if mode in ("serve", "web"):
        rest = args[1:]
        project, host, port, open_browser = _parse_serve_args(rest)
        if not project:
            print("用法: python main.py serve <project.json> [--host 0.0.0.0] [--port 5000] [--no-browser]")
            return 1
        try:
            from .web import run_server
        except ImportError as e:
            print(f"未安装 Flask。请先执行: pip install flask\n(详情: {e})")
            return 1
        return run_server(project, host=host, port=port, open_browser=open_browser)

    if mode in ("pack-web", "build-web"):
        project_path, out_dir, slug, port = _parse_pack_web_args(args[1:])
        if not project_path:
            print("用法: python main.py pack-web <project> [--out dist_web] [--slug name] [--port 8080]")
            return 1
        from .model import Project
        from .packaging.web_packager import build_web_package
        proj = Project.load(project_path)
        dest = build_web_package(proj, project_path, out_dir, slug=slug, port=port, log=print)
        print(f"\n[成功] Web 部署包已生成到:\n{os.path.abspath(dest)}")
        return 0

    if mode in ("deploy", "cloud"):
        project_path, platform, slug, token, account_id, port, is_prod = _parse_deploy_args(args[1:])
        if not project_path:
            print("用法: python main.py deploy <project> [--platform cloudflare|vercel|docker] [--slug name] [--token T] [--port 8080]")
            return 1
        from .model import Project
        from .packaging.web_packager import build_web_package, safe_slug

        proj = Project.load(project_path)
        actual_slug = slug or safe_slug(proj.title)
        out_dir = os.path.join(os.path.dirname(os.path.abspath(project_path)), "dist_web")

        print(f"[GalPy] 正在构建项目 '{proj.title}' 部署包...")
        dest = build_web_package(proj, project_path, out_dir, slug=actual_slug, port=port, log=print)

        print(f"\n[GalPy] 开始在线对接部署到 {platform.upper()}...")
        env = os.environ.copy()
        if platform in ("cloudflare", "cloudflare_workers", "cf"):
            if token:
                env["CLOUDFLARE_API_TOKEN"] = token
            if account_id:
                env["CLOUDFLARE_ACCOUNT_ID"] = account_id
            bin_name = "wrangler" if shutil.which("wrangler") else "npx --yes wrangler"
            cmd = f"{bin_name} deploy"
        elif platform in ("cloudflare_pages", "pages"):
            if token:
                env["CLOUDFLARE_API_TOKEN"] = token
            if account_id:
                env["CLOUDFLARE_ACCOUNT_ID"] = account_id
            bin_name = "wrangler" if shutil.which("wrangler") else "npx --yes wrangler"
            subprocess.run(f"{bin_name} pages project create {actual_slug} --production-branch=main", cwd=dest, shell=True, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            cmd = f"{bin_name} pages deploy . --project-name={actual_slug} --branch=main"
        elif platform == "vercel":
            bin_name = "vercel" if shutil.which("vercel") else "npx --yes vercel"
            prod_flag = "--prod" if is_prod else ""
            token_flag = f'--token="{token}"' if token else ""
            cmd = f"{bin_name} {prod_flag} --yes {token_flag}".strip()
        elif platform == "docker":
            cmd = "docker compose up -d --build"
        else:
            print(f"[错误] 不支持的部署目标: {platform}")
            return 1

        print(f"➜ 执行命令: {cmd}")
        print(f"➜ 目录: {dest}\n")

        p = subprocess.Popen(
            cmd, cwd=dest, shell=True, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace",
        )
        url_regex = re.compile(r"https?://[a-zA-Z0-9][-a-zA-Z0-9.]*(?:\.vercel\.app|\.pages\.dev|\.workers\.dev)[^\s]*")
        detected_url = ""
        assert p.stdout is not None
        for line in p.stdout:
            print(line, end="")
            m = url_regex.search(line)
            if m:
                detected_url = m.group(0).rstrip(".,;'\"")

        code = p.wait()
        if code == 0:
            final_url = detected_url or (f"http://localhost:{port}/" if platform == "docker" else "")
            print("\n==================================================")
            print("  🎉 部署成功!")
            if final_url:
                print(f"  在线访问地址: {final_url}")
                if any(k in final_url for k in ("pages.dev", "workers.dev")):
                    print("\n  ⚠️ [中国大陆网络访问特别指引]:")
                    print("  Cloudflare 默认域名 (*.pages.dev / *.workers.dev) 在国内部分运营商网络受阻。")
                    print("  💡 强烈建议在 Cloudflare 控制台该项目中绑定【自定义域名】(Custom Domain)，国内玩家即可免代理秒开畅玩！")
                elif "vercel.app" in final_url:
                    print("\n  ⚠️ [中国大陆网络访问特别指引]:")
                    print("  Vercel 默认域名 (*.vercel.app) 在中国大陆由于政策性 DNS 污染无法直接访问。")
                    print("  💡 强烈建议在 Vercel 控制台 (Settings -> Domains) 绑定【自定义域名】，并设置 CNAME 解析指向 cname.vercel-dns.com，国内即可流畅畅玩！")
            print("==================================================")
            return 0
        else:
            print(f"\n[错误] 部署失败，退出代码: {code}")
            return code

    print(f"未知命令: {mode}")
    print("用法: python main.py [launcher|edit|play|serve|pack-web|deploy] [project.json]")
    return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
