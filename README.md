<div align="center">

# 🎮 GalPy

### 纯 Python 可视化 Galgame (视觉小说) 制作引擎与多端发布器
**A Modern, Pure-Python Visual Novel Engine & Multi-Platform Publisher**

[![Python Version](https://img.shields.io/badge/Python-3.9+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![GUI Framework](https://img.shields.io/badge/GUI-PySide6%20%28Qt6%29-41CD52?logo=qt&logoColor=white)](https://pypi.org/project/PySide6/)
[![Web Deployment](https://img.shields.io/badge/Deploy-Cloudflare%20%7C%20Vercel%20%7C%20Docker-F38020?logo=cloudflare&logoColor=white)](https://pages.cloudflare.com/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Language](https://img.shields.io/badge/Language-中文%20%7C%20English-lightgrey)](#-语言--languages)

[**简体中文**](README.md) • [**English**](README_EN.md)

</div>

---

## 📖 简介

**GalPy** 是一款开箱即用的现代化 Galgame（视觉小说）制作引擎与一体化发布套件。

无论你是创作者、独立开发者还是游戏爱好者，你都可以通过**纯图形界面 (GUI) 操作**轻松完成剧本编排、多媒体素材挂载（文本、立绘、背景、BGM、音效、全屏视频）与分支选项设定，并且支持**一键打包为独立 Windows 桌面程序 (.exe)** 或**直接发布至全球云平台（Cloudflare Pages / Vercel / Docker）**，实现跨平台网页秒开畅玩！

---

## ✨ 核心特性

- 🖱️ **纯可视化无代码创作** — 制作、排版、预览调试、打包发布全程图形界面，零编程基础也能快速上手。
- 🌐 **双语支持与即时切换** — 原生支持 **简体中文** 与 **English**，默认跟随操作系统语言，并可在界面右上角 `🌐` 按钮一键无缝热切换。
- 🎨 **现代化精致 UI** — 采用暗黑现代科技风设计，层级分明的按钮规范（Primary / Success / Danger）与流畅的高清矢量图标交互。
- 📝 **全功能文本表现** — 对白系统（支持说话者名牌、专属角色语音）、旁白模式与打字机打字渐变动效。
- 🖼️ **丰富图像层级** — 背景图智能自适应铺满显示 + 角色立绘 5 档预设站位，支持平滑淡入淡出。
- 🎵 **专业级独立音频** — 独立管理 **BGM**（自动无缝循环）、**角色语音** 与 **场景音效** 三路通道，音量独立控制。
- 🎬 **全屏剧场视频** — 完美支持 mp4 / webm / mkv 等高清视频全屏播映，支持按键跳过。
- 🔀 **交互式分支走向** — 选项决策树、跨场景跳转逻辑与顺序推进。
- 📦 **桌面端一键打包** — 集成 PyInstaller，一键将工程与素材封装为单个独立 `.exe`，玩家双击即玩，免装 Python 环境。
- ☁️ **Web 纯前端与云端直连部署**：
  - **Cloudflare Pages / Workers**：自动化边缘节点加速，全球无限流量，免代理极速畅玩。
  - **Vercel**：全球自动化持续部署与 HTTPS 域名分配。
  - **Docker 容器化**：预置超轻量 Alpine Nginx 镜像（内存占用仅约 15MB），完美支持 HTTP 206 流式音视频拖动播放。
  - **本地安全存档**：浏览器端 `localStorage` 实现自动存档与 9 档手动存档，无需后端数据库。
- 🧩 **内置开箱即用示例** — 内置一键生成全套演示项目（含对白、立绘、BGM、分支），助你 10 秒了解全部工作流。

---

## 📦 环境要求与依赖安装

整个引擎仅依赖 **2 个核心第三方库**（桌面打包或云端导出后，终端玩家无需安装任何依赖）：

| 依赖库 | 核心用途 | 安装命令 |
| :--- | :--- | :--- |
| **`PySide6`** | Qt for Python 官方套件，负责现代化 GUI 渲染、音频多媒体引擎与视频播放管线 | `pip install PySide6` |
| **`pyinstaller`** | 将 Python 源码及游戏资源一键打包为独立 `.exe` 可执行程序 | `pip install pyinstaller` |

> 📌 **Python 版本要求**：**3.9+**（强烈推荐 Python 3.10 或 3.11）。

```bash
# 克隆或下载本项目后，在你的虚拟环境中一键安装依赖
pip install -r requirements.txt
```

---

## 🚀 快速上手

### 1. 启动引擎

在命令行或直接双击运行 `run.bat`（Windows）：

```bash
python main.py
```

### 2. 启动菜单选项

启动后将呈现现代启动面板，支持以下操作：

- 📝 **新建工程**：创建空白工程并进入主编辑器。
- 📂 **打开工程**：加载已有 `project.json` 或 `.galpy` 工程文件。
- ▶ **直接播放**：跳过编辑器，以独立全屏播放器模式直接运行已有游戏工程。
- ✨ **新建示例工程**：自动生成完整的多场景、多分支示范工程（含自适应中文/英文角色与素材），立即体验全部特性！
- 🌐 **语言切换**：点击右上方地球图标，可在 **简体中文 / English** 之间实时切换。

---

## 🎮 播放器操作快捷键

| 按键 / 操作 | 响应功能 |
| :--- | :--- |
| **鼠标左键 / 空格 / 回车** | 推进对白 / 瞬间完成打字机输出 / 跳过视频 |
| **`F5`** | （编辑器内）从头完整运行游戏 |
| **`F6`** | （编辑器内）从当前选中的场景快速开始调试运行 |
| **`F11`** | 切换全屏 / 窗口化模式 |
| **`ESC`** | 退出全屏或退出播放器 |

---

## 🛠️ 可视化编辑器工作流

1. **左侧「场景列表」**：游戏由若干 Scene 构成。可自由新增、重命名、删除场景，或右键设置起始场景。
2. **中间「场景画布与步骤」**：
   - 设置当前场景的名称、默认背景图与氛围 BGM。
   - 管理步骤序列（添加、编辑、复制、拖动排序或删除）。
3. **右侧「资源管理器」**：
   - 分类查看（背景 / 立绘 / BGM / 语音 / 音效 / 视频）。
   - 点击「导入素材」，文件将被安全复制至项目 `assets/` 目录并自动纳管，支持一键实时预览与试听。
4. **顶部工具栏**：提供保存、测试播放、桌面打包与云端部署入口。

---

## ☁️ 在线发布与云端部署 (Cloudflare / Vercel / Docker)

GalPy 原生具备将视觉小说转化为**纯前端 Web 应用**的能力，并集成自动化发布流程：

### 部署方式对比

| 部署目标 | 适合场景 | 优势特点 | 零配置门槛 |
| :--- | :--- | :--- | :---: |
| **Cloudflare Pages** | **全球公网玩家分享（首选）** | 遍布全球的 Anycast 边缘 CDN，永久免费、无限流量，国内可绑自定义域名免翻畅玩 | ⭐⭐⭐⭐⭐ |
| **Vercel** | **与 GitHub 联动持续集成** | 自动化 HTTPS 与 CI/CD，支持自定义二级域名 | ⭐⭐⭐⭐ |
| **Docker** | **私有服务器 / 局域网分享** | 极速秒启，内存占用极小 (~15MB)，支持 HTTP 206 流式视频 Range 请求 | ⭐⭐⭐⭐ |

### 一键部署步骤

1. 在编辑器顶部菜单选择 **「发布与部署」➔「☁️ 云端在线部署 (Cloudflare / Vercel / 容器)」**。
2. 选择你要发布的目标平台（Cloudflare / Vercel / Docker）。
3. 点击 **「🚀 开始在线对接部署」**：
   - 软件将全自动编译游戏资源与前端播放器。
   - 自动生成对应平台的配置文件（`wrangler.toml`、`vercel.json`、`Dockerfile.nginx` 等）。
   - 自动调用后台进程完成发布，并实时回传控制台流式日志。
4. 部署完成后直接生成全球在线访问链接（如 `https://your-game.pages.dev`），点击即可直接在浏览器畅玩！

> 💡 **中国大陆网络访问优化提示**：
> - Cloudflare 与 Vercel 的默认二级域名（`*.pages.dev` / `*.vercel.app`）在大陆部分网络下可能存在 DNS 污染。
> - **免翻畅玩方案**：在 Cloudflare 或 Vercel 控制台中为该项目绑定**自定义域名 (Custom Domain)**，即可在国内实现极速秒开！

---

## 📐 工程数据规范 (project.json)

```jsonc
{
  "version": "1.0",
  "title": "游戏名称",
  "author": "制作人",
  "width": 1280,
  "height": 720,
  "start_scene": "scene_001",
  "assets": {
    "backgrounds": ["assets/backgrounds/bg_room.png"],
    "characters": ["assets/characters/ming_smile.png"],
    "bgm": ["assets/bgm/theme.mp3"],
    "voices": [],
    "sfx": [],
    "videos": []
  },
  "scenes": [
    {
      "id": "scene_001",
      "name": "晨光熹微",
      "background": "assets/backgrounds/bg_room.png",
      "bgm": "assets/bgm/theme.mp3",
      "steps": [
        {
          "type": "dialogue",
          "speaker": "小明",
          "text": "早安！又是充满希望的一天！",
          "character": "assets/characters/ming_smile.png",
          "position": "center"
        }
      ]
    }
  ]
}
```

### 步骤（Step）类型一览

| 步骤类型 | 说明 | 核心字段 | 执行机制 |
| :--- | :--- | :--- | :---: |
| `dialogue` | 角色对白 | `speaker`、`text`、`character`、`position`、`voice` | 交互式（等待用户点击） |
| `narration` | 旁白解说 | `text` | 交互式（等待用户点击） |
| `choice` | 互动选项分支 | `prompt`、`options`（包含选项文本与跳转 scene_id） | 交互式（等待玩家做出抉择） |
| `video` | 播放全屏视频 | `source`（视频文件路径） | 交互式（播放完毕或点击跳过） |
| `bg_change` | 切换背景图像 | `background` | 即时执行（自动进入下一步） |
| `bgm_change` | 切换或停止背景音乐 | `bgm`（留空则为停止播放） | 即时执行（自动进入下一步） |
| `sfx` | 播放单次音效 | `sfx` | 即时执行（自动进入下一步） |
| `goto` | 立即跳转至目标场景 | `next`（目标场景 ID） | 即时执行（切换场景） |
| `end` | 宣告本篇完结 | — | 交互式（显示完结界面） |

---

## 📁 目录架构说明

```
GalPy/
├── main.py                     # 统一命令行与图形入口脚本
├── run.bat                     # Windows 一键自适应启动脚本
├── requirements.txt            # Python 依赖清单
├── LICENSE                     # MIT 开源许可证
├── README.md                   # 中文文档
├── README_EN.md                # 英文文档
├── web/                        # Web 播放器核心运行时资产 (HTML / CSS / JS)
└── galpy/
    ├── app.py                  # 启动引导菜单窗口
    ├── runtime.py              # QApplication 样式主题与现代 QSS
    ├── i18n.py                 # 双语国际化引擎 (zh_CN / en_US)
    ├── model.py                # 工程、场景、步骤数据模型
    ├── demo.py                 # 双语演示项目生成器
    ├── engine/
    │   ├── media.py            # 音频与多媒体流播放调度
    │   └── player.py           # 桌面端游戏播放器视窗
    ├── editor/
    │   ├── main_window.py      # 主编辑器视窗 (含动态国际化与工具栏)
    │   ├── step_dialog.py      # 步骤编辑卡片对话框
    │   └── asset_browser.py    # 素材管理器与音频图片试听面板
    └── packaging/
        ├── packager.py         # PyInstaller 桌面端单文件打包器
        └── web_packager.py     # Web 打包器与 Cloudflare/Vercel/Docker 自动化发布流水线
```

---

## 📜 开源许可证

本项目基于 **[MIT License](LICENSE)** 开源。您可以自由用于私人学习、二创修改以及商业化游戏发布。

> ⚠️ **关于依赖许可声明**：
> - 本项目使用的图形界面依赖库 `PySide6` 遵循 **LGPLv3** 开源协议；
> - 桌面端打包组件 `PyInstaller` 遵循 **GPLv2** 开源协议（带特许例外的运行时支持）。
> - 当您打包并分发独立可执行程序时，请知悉并遵守相关上游开源协议约定。
