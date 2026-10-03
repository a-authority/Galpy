<div align="center">

# 🎮 GalPy

### A Modern, Pure-Python Visual Novel Engine & Multi-Platform Publisher
**纯 Python 可视化 Galgame (视觉小说) 制作引擎与多端发布器**

[![Python Version](https://img.shields.io/badge/Python-3.9+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![GUI Framework](https://img.shields.io/badge/GUI-PySide6%20%28Qt6%29-41CD52?logo=qt&logoColor=white)](https://pypi.org/project/PySide6/)
[![Web Deployment](https://img.shields.io/badge/Deploy-Cloudflare%20%7C%20Vercel%20%7C%20Docker-F38020?logo=cloudflare&logoColor=white)](https://pages.cloudflare.com/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Language](https://img.shields.io/badge/Language-English%20%7C%20中文-lightgrey)](#-languages)

[**English**](README_EN.md) • [**简体中文**](README.md)

</div>

---

## 📖 Overview

**GalPy** is an all-in-one, ready-to-use modern Visual Novel (Galgame) creation engine and distribution toolkit written in Python.

Whether you are a creator, indie developer, or storytelling enthusiast, you can effortlessly script narratives, attach rich multimedia (dialogue, character portraits, dynamic backgrounds, BGM, SFX, voice acting, and full-screen video), and construct branching decisions—**all through an intuitive Graphical User Interface (GUI) without writing a single line of code**.

With a single click, package your game into a **standalone Windows executable (.exe)** or deploy it directly to global cloud edge networks (**Cloudflare Pages / Vercel / Docker**) for instant browser play anywhere in the world!

---

## ✨ Key Features

- 🖱️ **Pure Visual GUI Creation** — Build, preview, debug, and package games entirely within a polished visual editor. No programming knowledge required.
- 🌐 **Native Bilingual Support & Live Switch** — Native **English** and **Simplified Chinese** translations. Automatically detects your system locale, with an instant one-click toggle button (`🌐`) in the UI.
- 🎨 **Modern Dark Slate UI** — Sleek dark-mode aesthetic with an intuitive visual button hierarchy (Primary / Success / Danger) and high-DPI vector icons.
- 📝 **Rich Dialogue & Text Engine** — Speaker badges, character voice synchronization, narration mode, and customizable typewriter effects.
- 🖼️ **Multi-Layer Visuals** — Smart aspect-ratio background scaling with 5 character positioning slots and smooth cross-fading transitions.
- 🎵 **Triple-Track Audio Architecture** — Dedicated independent channels for **BGM** (seamless looping), **Character Voices**, and **Sound Effects (SFX)**.
- 🎬 **Full-Screen Cinematic Video** — High-definition video cutscenes (mp4, webm, mkv) with interactive click-to-skip support.
- 🔀 **Interactive Branching Trees** — Option decision branches, multi-scene navigation, and linear storyline continuity.
- 📦 **One-Click Desktop Packaging** — Bundled PyInstaller integration packages your project into a standalone `.exe`. Players can double-click and play immediately with zero setup.
- ☁️ **Web Sandbox & Direct Cloud Deployment**:
  - **Cloudflare Pages / Workers**: Instant edge CDN acceleration, 100% free with unlimited traffic, and custom domain binding.
  - **Vercel**: Automated continuous deployment with global edge distribution and zero-config SSL.
  - **Docker Containerization**: Lightweight Alpine Nginx micro-container (~15MB RAM usage) with full HTTP 206 byte-range audio/video streaming support.
  - **Client-Side Safe Saves**: Browser `localStorage` handles auto-saving and 9 manual save slots. Zero database required, 100% player privacy.
- 🧩 **Built-In Bilingual Demo** — One-click demo generation featuring full script dialogues, portraits, background music, and choice branches to jumpstart your creativity.

---

## 📦 Requirements & Installation

The engine only requires **2 core dependencies** (end-users do not need to install anything after packaging):

| Library | Purpose | Installation |
| :--- | :--- | :--- |
| **`PySide6`** | Qt for Python official suite; powers the modern GUI, audio/video multimedia pipeline | `pip install PySide6` |
| **`pyinstaller`** | Compiles Python source code and game assets into a standalone `.exe` | `pip install pyinstaller` |

> 📌 **Python Version Requirement**: **3.9+** (Python 3.10 or 3.11 recommended).

```bash
# Clone or download this repository, then install dependencies in your virtual environment:
pip install -r requirements.txt
```

---

## 🚀 Quick Start

### 1. Launch the Engine

Run via command line or double-click `run.bat` (Windows):

```bash
python main.py
```

### 2. Launcher Menu Options

The launcher dashboard offers quick access to all essential workflows:

- 📝 **New Project**: Create a new blank visual novel project and enter the visual editor.
- 📂 **Open Project**: Load an existing `project.json` or `.galpy` project file.
- ▶ **Direct Play**: Skip the editor and run the game directly in standalone player mode.
- ✨ **Create Demo Project**: Instantly generate a rich sample game with placeholder assets and branching choices to explore all features.
- 🌐 **Language Selector**: Click the globe icon in the top-right corner to switch between **English** and **简体中文**.

---

## 🎮 Player Controls & Shortcuts

| Key / Action | Function |
| :--- | :--- |
| **Left Click / Space / Enter** | Advance dialogue / Complete typewriter animation instantly / Skip video |
| **`F5`** | (In Editor) Play game from the very beginning |
| **`F6`** | (In Editor) Play game starting directly from the current scene |
| **`F11`** | Toggle Fullscreen / Windowed mode |
| **`ESC`** | Exit fullscreen or quit game player |

---

## 🛠️ Visual Editor Workflow

1. **Left Panel — Scene List**: A game consists of scenes. Easily create, rename, delete, or designate starting scenes.
2. **Center Panel — Scene Canvas & Steps**:
   - Set scene title, default background image, and scene-level ambient BGM.
   - Manage the step execution queue (add, modify, duplicate, reorder, or delete).
3. **Right Panel — Asset Browser**:
   - Categorized asset views (Backgrounds, Characters, BGM, Voices, SFX, Videos).
   - Click "Import Assets" to automatically copy and index files into the project's `assets/` directory with live audio/visual preview.
4. **Top Toolbar**: Quick access to Save, Test Play, Desktop Packaging, and Cloud Deployment.

---

## ☁️ Online Publishing & Cloud Deployment

GalPy natively converts your game into a **pure client-side HTML5 Web application** with streamlined deployment integrations:

### Platform Comparison

| Platform | Best For | Highlights | Setup Complexity |
| :--- | :--- | :--- | :---: |
| **Cloudflare Pages** | **Public Player Sharing (Recommended)** | Global Anycast Edge CDN, 100% free with unlimited bandwidth, custom domain support | ⭐⭐⭐⭐⭐ |
| **Vercel** | **GitHub CI/CD Integration** | Automated deployments on push, instant HTTPS, production edge performance | ⭐⭐⭐⭐ |
| **Docker** | **Private VPS / LAN Sharing** | Tiny memory footprint (~15MB), full HTTP 206 byte-range media seeking support | ⭐⭐⭐⭐ |

### Direct Online Deployment Steps

1. In the editor menu, select **"Publish & Deploy" ➔ "☁️ Online Cloud Deployment (Cloudflare / Vercel / Docker)"**.
2. Select your target platform (**Cloudflare Pages**, **Vercel**, or **Docker**).
3. Click **"🚀 Start Online Direct Deployment"**:
   - Compiles game assets and the Web player core.
   - Auto-generates deployment configuration files (`wrangler.toml`, `vercel.json`, `Dockerfile.nginx`, etc.).
   - Launches automated deployment with live streaming console logs.
4. Upon completion, an online URL (e.g. `https://your-game.pages.dev`) is generated. Click to play in your browser immediately!

> 💡 **Custom Domain Recommendation**:
> - You can attach a **Custom Domain** anytime in your Cloudflare Pages or Vercel dashboard for branded, high-speed access worldwide.

---

## 📐 Project Data Format (project.json)

```jsonc
{
  "version": "1.0",
  "title": "My Visual Novel",
  "author": "Developer",
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
      "name": "A New Beginning",
      "background": "assets/backgrounds/bg_room.png",
      "bgm": "assets/bgm/theme.mp3",
      "steps": [
        {
          "type": "dialogue",
          "speaker": "Ming",
          "text": "Good morning! Ready for a wonderful new day?",
          "character": "assets/characters/ming_smile.png",
          "position": "center"
        }
      ]
    }
  ]
}
```

### Step Types Reference

| Step Type | Description | Key Attributes | Execution Type |
| :--- | :--- | :--- | :---: |
| `dialogue` | Character dialogue line | `speaker`, `text`, `character`, `position`, `voice` | Interactive (waits for click) |
| `narration` | Third-person narrative text | `text` | Interactive (waits for click) |
| `choice` | Branching decision prompt | `prompt`, `options` (text + target scene_id) | Interactive (waits for selection) |
| `video` | Play full-screen video | `source` (video file path) | Interactive (plays until end or click) |
| `bg_change` | Switch background image | `background` | Instant (proceeds to next step) |
| `bgm_change` | Change or stop BGM | `bgm` (empty string stops playback) | Instant (proceeds to next step) |
| `sfx` | Play sound effect | `sfx` | Instant (proceeds to next step) |
| `goto` | Jump immediately to scene | `next` (target scene ID) | Instant (transitions scene) |
| `end` | End game credits screen | — | Interactive (shows completion UI) |

---

## 📁 Directory Structure

```
GalPy/
├── main.py                     # Unified CLI and GUI launcher entry
├── run.bat                     # Windows launch script
├── requirements.txt            # Python dependencies
├── LICENSE                     # MIT Open Source License
├── README.md                   # Chinese Documentation
├── README_EN.md                # English Documentation
├── web/                        # Web player runtime assets (HTML / CSS / JS)
└── galpy/
    ├── app.py                  # Launcher dashboard dialog
    ├── runtime.py              # Application lifecycle & modern QSS styles
    ├── i18n.py                 # Internationalization engine (zh_CN / en_US)
    ├── model.py                # Project, Scene, and Step data models
    ├── demo.py                 # Bilingual demo project generator
    ├── engine/
    │   ├── media.py            # Audio and multimedia playback controller
    │   └── player.py           # Desktop player window & canvas
    ├── editor/
    │   ├── main_window.py      # Main visual editor window
    │   ├── step_dialog.py      # Step editing card dialog
    │   └── asset_browser.py    # Asset management and preview panel
    └── packaging/
        ├── packager.py         # PyInstaller desktop packager
        └── web_packager.py     # Web exporter & Cloudflare/Vercel/Docker pipelines
```

---

## 📜 License

This project is licensed under the **[MIT License](LICENSE)**. You are free to use it for personal learning, fan creations, and commercial visual novel production.

> ⚠️ **Third-Party Dependency Notice**:
> - `PySide6` is licensed under **LGPLv3**;
> - `PyInstaller` is licensed under **GPLv2** with runtime exceptions.
> - When distributing your compiled standalone executables, please ensure compliance with upstream license terms.
