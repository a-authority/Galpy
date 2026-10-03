"""GalPy 国际化 (i18n) 模块: 支持中英文语言切换与系统语言自动检测。

支持语言:
  - "auto"  : 跟随操作系统 (默认; 中文系统用 zh_CN, 其它用 en_US)
  - "zh_CN" : 简体中文 (Simplified Chinese)
  - "en_US" : English (英文)

通过 QSettings("GalPy", "GalPy") 持久化用户选择。
"""
from __future__ import annotations

import os
import sys
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import QLocale, QObject, QSettings, Signal


class _LanguageManager(QObject):
    """全局语言管理单例, 发射 language_changed 信号。"""
    language_changed = Signal(str)


_manager = _LanguageManager()

# 当前选定的语言配置 ("auto", "zh_CN", "en_US")
_current_pref: Optional[str] = None
# 实际生效的语言 ("zh_CN" 或 "en_US")
_effective_lang: Optional[str] = None


# ==============================================================================
# 语言探测与偏好读写
# ==============================================================================

def get_system_language() -> str:
    """探测系统默认语言, 返回 'zh_CN' 或 'en_US'。"""
    try:
        loc = QLocale.system()
        name = loc.name().lower()
        if name.startswith("zh") or "chinese" in loc.nativeLanguageName().lower():
            return "zh_CN"
    except Exception:
        pass
    # 备选环境变量
    for env_var in ("LANG", "LANGUAGE", "LC_ALL"):
        val = os.environ.get(env_var, "").lower()
        if val.startswith("zh"):
            return "zh_CN"
    return "en_US"


def load_language_pref() -> str:
    """从 QSettings 读取用户语言设置; 默认 'auto'。"""
    try:
        s = QSettings("GalPy", "GalPy")
        val = str(s.value("ui/language", "auto")).strip()
        if val in ("auto", "zh_CN", "en_US"):
            return val
    except Exception:
        pass
    return "auto"


def save_language_pref(lang: str) -> None:
    """持久化用户语言偏好。"""
    try:
        s = QSettings("GalPy", "GalPy")
        s.setValue("ui/language", lang)
    except Exception:
        pass


def get_language() -> str:
    """返回当前配置的语言标识 ('auto' / 'zh_CN' / 'en_US')。"""
    global _current_pref
    if _current_pref is None:
        _current_pref = load_language_pref()
    return _current_pref


def get_effective_language() -> str:
    """返回当前实际生效的语言 ('zh_CN' 或 'en_US')。"""
    global _effective_lang
    if _effective_lang is None:
        pref = get_language()
        if pref == "auto":
            _effective_lang = get_system_language()
        else:
            _effective_lang = pref
    return _effective_lang


def set_language(lang: str, persist: bool = True) -> None:
    """设置语言偏好 ('auto', 'zh_CN', 'en_US'), 并通知所有监听者。"""
    global _current_pref, _effective_lang
    if lang not in ("auto", "zh_CN", "en_US"):
        lang = "auto"
    _current_pref = lang
    if lang == "auto":
        _effective_lang = get_system_language()
    else:
        _effective_lang = lang

    if persist:
        save_language_pref(lang)

    _manager.language_changed.emit(_effective_lang)


def on_language_changed(slot: Callable[[str], None]) -> None:
    """连接语言切换信号。"""
    _manager.language_changed.connect(slot)


# ==============================================================================
# 词典定义 (简体中文 / English)
# ==============================================================================

_TRANSLATIONS: Dict[str, Dict[str, str]] = {
    # ---- 基础与通用 ----
    "app_title": {
        "zh_CN": "GalPy 视觉小说引擎",
        "en_US": "GalPy Visual Novel Engine",
    },
    "app_subtitle": {
        "zh_CN": "纯 Python 实现的 Galgame 引擎\n文字 · 音频 · 视频 · 图片 · 可视化编辑 · 一键在线发布",
        "en_US": "Python-Powered Visual Novel Engine\nStory · Audio · Video · Sprites · Visual Editor · 1-Click Online Deploy",
    },
    "ok": {
        "zh_CN": "确定",
        "en_US": "OK",
    },
    "cancel": {
        "zh_CN": "取消",
        "en_US": "Cancel",
    },
    "close": {
        "zh_CN": "关闭",
        "en_US": "Close",
    },
    "apply": {
        "zh_CN": "应用",
        "en_US": "Apply",
    },
    "save": {
        "zh_CN": "保存",
        "en_US": "Save",
    },
    "delete": {
        "zh_CN": "删除",
        "en_US": "Delete",
    },
    "edit": {
        "zh_CN": "编辑",
        "en_US": "Edit",
    },
    "add": {
        "zh_CN": "添加",
        "en_US": "Add",
    },
    "refresh": {
        "zh_CN": "刷新",
        "en_US": "Refresh",
    },
    "browse": {
        "zh_CN": "浏览…",
        "en_US": "Browse…",
    },
    "select": {
        "zh_CN": "选择…",
        "en_US": "Select…",
    },
    "clear": {
        "zh_CN": "清空",
        "en_US": "Clear",
    },
    "preview": {
        "zh_CN": "试听/预览",
        "en_US": "Preview",
    },
    "stop": {
        "zh_CN": "停止",
        "en_US": "Stop",
    },
    "none": {
        "zh_CN": "(无)",
        "en_US": "(None)",
    },
    "ready": {
        "zh_CN": "就绪",
        "en_US": "Ready",
    },
    "success": {
        "zh_CN": "成功",
        "en_US": "Success",
    },
    "error": {
        "zh_CN": "错误",
        "en_US": "Error",
    },
    "warning": {
        "zh_CN": "提示",
        "en_US": "Notice",
    },

    # ---- 启动器 Launcher ----
    "launcher_new": {
        "zh_CN": "📝  新建工程",
        "en_US": "📝  New Project",
    },
    "launcher_new_tip": {
        "zh_CN": "创建空白工程并进入可视化编辑器",
        "en_US": "Create a new project and open the visual editor",
    },
    "launcher_open": {
        "zh_CN": "📂  打开工程",
        "en_US": "📂  Open Project",
    },
    "launcher_open_tip": {
        "zh_CN": "打开已有的 .galpy / project.json 工程进行编辑",
        "en_US": "Open an existing .galpy or project.json file to edit",
    },
    "launcher_play": {
        "zh_CN": "▶  直接播放",
        "en_US": "▶  Play Game",
    },
    "launcher_play_tip": {
        "zh_CN": "选择工程直接以全屏或窗口模式运行游玩",
        "en_US": "Select a project to run and play immediately",
    },
    "launcher_demo": {
        "zh_CN": "✨  新建示例工程",
        "en_US": "✨  Create Demo Project",
    },
    "launcher_demo_tip": {
        "zh_CN": "自动生成带示例素材与多分支选项的演示工程",
        "en_US": "Generate an interactive demo project with sample assets and branches",
    },
    "launcher_quit": {
        "zh_CN": "退出",
        "en_US": "Exit",
    },
    "launcher_new_title_prompt": {
        "zh_CN": "请输入工程名称 (英文或中文):",
        "en_US": "Enter project title (name):",
    },
    "launcher_new_dir_prompt": {
        "zh_CN": "选择工程保存文件夹",
        "en_US": "Select Folder to Save Project",
    },

    # ---- 语言切换 ----
    "lang_menu": {
        "zh_CN": "语言 (&L)",
        "en_US": "Language (&L)",
    },
    "lang_auto": {
        "zh_CN": "🌐 跟随系统 (System Default)",
        "en_US": "🌐 System Default (跟随系统)",
    },
    "lang_zh": {
        "zh_CN": "🇨🇳 简体中文 (Simplified Chinese)",
        "en_US": "🇨🇳 Simplified Chinese (简体中文)",
    },
    "lang_en": {
        "zh_CN": "🇺🇸 English (英文)",
        "en_US": "🇺🇸 English",
    },

    # ---- 编辑器菜单 ----
    "menu_file": {
        "zh_CN": "文件 (&F)",
        "en_US": "File (&F)",
    },
    "action_new": {
        "zh_CN": "新建工程",
        "en_US": "New Project",
    },
    "action_open": {
        "zh_CN": "打开工程…",
        "en_US": "Open Project…",
    },
    "action_save": {
        "zh_CN": "保存工程",
        "en_US": "Save Project",
    },
    "action_save_as": {
        "zh_CN": "另存为…",
        "en_US": "Save As…",
    },
    "action_demo": {
        "zh_CN": "新建示例工程…",
        "en_US": "New Demo Project…",
    },
    "action_exit": {
        "zh_CN": "退出",
        "en_US": "Exit",
    },

    "menu_run": {
        "zh_CN": "运行 (&R)",
        "en_US": "Run (&R)",
    },
    "action_play_all": {
        "zh_CN": "从头开始运行",
        "en_US": "Play from Start",
    },
    "action_play_here": {
        "zh_CN": "从当前场景运行",
        "en_US": "Play Current Scene",
    },

    "menu_publish": {
        "zh_CN": "发布与部署 (&P)",
        "en_US": "Publish & Deploy (&P)",
    },
    "action_cloud_deploy": {
        "zh_CN": "☁️ 云端在线直连部署 (Cloudflare / Vercel / 容器)…",
        "en_US": "☁️ Online Direct Deploy (Cloudflare / Vercel / Docker)…",
    },
    "action_web_package": {
        "zh_CN": "🌐 导出 Web 纯静态应用…",
        "en_US": "🌐 Export Static Web Game…",
    },
    "action_desktop_package": {
        "zh_CN": "📦 打包为桌面可执行程序 (.exe)…",
        "en_US": "📦 Pack Desktop App (.exe)…",
    },
    "action_web_preview": {
        "zh_CN": "▶ 在浏览器中预览…",
        "en_US": "▶ Preview in Browser…",
    },

    "menu_help": {
        "zh_CN": "帮助 (&H)",
        "en_US": "Help (&H)",
    },
    "action_about": {
        "zh_CN": "关于 GalPy",
        "en_US": "About GalPy",
    },

    # ---- 工具栏 ----
    "tb_play": {
        "zh_CN": "▶ 运行游戏",
        "en_US": "▶ Play",
    },
    "tb_save": {
        "zh_CN": "💾 保存",
        "en_US": "💾 Save",
    },
    "tb_package": {
        "zh_CN": "📦 打包与发布",
        "en_US": "📦 Package",
    },
    "tb_stop_audio": {
        "zh_CN": "⏹ 停止音频",
        "en_US": "⏹ Stop Audio",
    },
    "tb_auto_save": {
        "zh_CN": "💨 自动保存",
        "en_US": "💨 Auto-Save",
    },
    "tb_recover_auto": {
        "zh_CN": "↩ 从自动保存恢复",
        "en_US": "↩ Restore Backup",
    },
    "tb_theme_tip": {
        "zh_CN": "切换浅色 / 深色主题",
        "en_US": "Toggle Light / Dark Theme",
    },
    "tb_lang_tip": {
        "zh_CN": "切换显示语言 (中文 / English)",
        "en_US": "Switch Language (Chinese / English)",
    },

    # ---- 场景面板 ----
    "dock_scenes": {
        "zh_CN": "场景列表",
        "en_US": "Scenes",
    },
    "btn_add_scene": {
        "zh_CN": "+ 新建场景",
        "en_US": "+ Add Scene",
    },
    "btn_del_scene": {
        "zh_CN": "删除场景",
        "en_US": "Delete Scene",
    },
    "btn_rename_scene": {
        "zh_CN": "重命名",
        "en_US": "Rename",
    },
    "scene_cover_tag": {
        "zh_CN": "[封面]",
        "en_US": "[Cover]",
    },
    "scene_name_label": {
        "zh_CN": "场景名称:",
        "en_US": "Scene Title:",
    },
    "scene_bg_label": {
        "zh_CN": "背景图:",
        "en_US": "Background:",
    },
    "scene_bgm_label": {
        "zh_CN": "背景音乐:",
        "en_US": "BGM Music:",
    },
    "cover_hint": {
        "zh_CN": "🎬 封面场景 (Title Screen)\n\n封面是游戏的标题画面，游戏启动时优先展示。\n包含: 标题画面、背景音乐与开始/继续菜单。\n如需编写剧本步骤，请切换到下方各主线场景。",
        "en_US": "🎬 Cover Scene (Title Screen)\n\nThe cover is your game's opening title screen.\nConfigures: Title art, theme music, and main menu.\nTo edit dialogue & gameplay steps, select any scene below.",
    },

    # ---- 步骤面板 ----
    "steps_title": {
        "zh_CN": "剧情步骤列表 (按顺序执行):",
        "en_US": "Story Steps (Executed in sequence):",
    },
    "btn_add_step": {
        "zh_CN": "+ 添加步骤",
        "en_US": "+ Add Step",
    },
    "btn_edit_step": {
        "zh_CN": "编辑",
        "en_US": "Edit",
    },
    "btn_del_step": {
        "zh_CN": "删除",
        "en_US": "Delete",
    },
    "btn_up_step": {
        "zh_CN": "上移",
        "en_US": "Move Up",
    },
    "btn_down_step": {
        "zh_CN": "下移",
        "en_US": "Move Down",
    },

    # ---- 资源管理器 ----
    "dock_assets": {
        "zh_CN": "工程素材库",
        "en_US": "Asset Library",
    },
    "btn_import_asset": {
        "zh_CN": "导入文件…",
        "en_US": "Import Files…",
    },
    "btn_delete_asset": {
        "zh_CN": "从工程删除",
        "en_US": "Delete Asset",
    },
    "asset_filter_all": {
        "zh_CN": "全部素材",
        "en_US": "All Assets",
    },

    # ---- 步骤类型名称 ----
    "step_dialogue": {
        "zh_CN": "角色对白",
        "en_US": "Dialogue",
    },
    "step_narration": {
        "zh_CN": "旁白 / 叙述",
        "en_US": "Narration",
    },
    "step_choice": {
        "zh_CN": "分支选项",
        "en_US": "Choice Branch",
    },
    "step_video": {
        "zh_CN": "全屏视频",
        "en_US": "Play Video",
    },
    "step_bg_change": {
        "zh_CN": "更换背景",
        "en_US": "Change Background",
    },
    "step_audio_change": {
        "zh_CN": "切换音频 (BGM/音效)",
        "en_US": "Audio Control",
    },
    "step_character_exit": {
        "zh_CN": "立绘离场",
        "en_US": "Character Exit",
    },
    "step_goto": {
        "zh_CN": "跳转场景",
        "en_US": "Jump to Scene",
    },
    "step_end": {
        "zh_CN": "结束剧情",
        "en_US": "End Story",
    },

    # ---- 资源类别名称 ----
    "cat_backgrounds": {
        "zh_CN": "背景图片",
        "en_US": "Backgrounds",
    },
    "cat_characters": {
        "zh_CN": "角色立绘",
        "en_US": "Character Sprites",
    },
    "cat_bgm": {
        "zh_CN": "背景音乐 (BGM)",
        "en_US": "BGM Music",
    },
    "cat_voice": {
        "zh_CN": "角色语音",
        "en_US": "Voice Acting",
    },
    "cat_sfx": {
        "zh_CN": "环境音效 (SFX)",
        "en_US": "Sound Effects (SFX)",
    },
    "cat_videos": {
        "zh_CN": "过场视频",
        "en_US": "Cutscene Videos",
    },

    # ---- 角色位置 ----
    "pos_left": {
        "zh_CN": "左侧",
        "en_US": "Left",
    },
    "pos_center_left": {
        "zh_CN": "偏左",
        "en_US": "Center Left",
    },
    "pos_center": {
        "zh_CN": "居中",
        "en_US": "Center",
    },
    "pos_center_right": {
        "zh_CN": "偏右",
        "en_US": "Center Right",
    },
    "pos_right": {
        "zh_CN": "右侧",
        "en_US": "Right",
    },

    # ---- 音频操作 ----
    "audio_play": {
        "zh_CN": "播放",
        "en_US": "Play",
    },
    "audio_stop": {
        "zh_CN": "停止",
        "en_US": "Stop",
    },

    # ---- 步骤对话框表单字段 ----
    "step_dlg_title": {
        "zh_CN": "编辑剧情步骤",
        "en_US": "Edit Story Step",
    },
    "step_type_label": {
        "zh_CN": "步骤类型:",
        "en_US": "Step Type:",
    },
    "speaker_label": {
        "zh_CN": "说话角色:",
        "en_US": "Speaker Name:",
    },
    "dialogue_text_label": {
        "zh_CN": "台词内容:",
        "en_US": "Dialogue Text:",
    },
    "voice_label": {
        "zh_CN": "配音音频:",
        "en_US": "Voice Audio:",
    },
    "character_label": {
        "zh_CN": "登场立绘:",
        "en_US": "Character Sprite:",
    },
    "position_label": {
        "zh_CN": "显示位置:",
        "en_US": "Position:",
    },
    "bg_label": {
        "zh_CN": "背景图像:",
        "en_US": "Background:",
    },
    "video_label": {
        "zh_CN": "视频文件:",
        "en_US": "Video File:",
    },
    "prompt_label": {
        "zh_CN": "分支提示语:",
        "en_US": "Choice Prompt:",
    },
    "options_label": {
        "zh_CN": "选项分支列表:",
        "en_US": "Branch Options:",
    },
    "target_scene_label": {
        "zh_CN": "目标场景:",
        "en_US": "Target Scene:",
    },
    "audio_cat_label": {
        "zh_CN": "音频分类:",
        "en_US": "Audio Type:",
    },
    "audio_action_label": {
        "zh_CN": "执行动作:",
        "en_US": "Action:",
    },

    # ---- 选项编辑 ----
    "btn_add_option": {
        "zh_CN": "+ 新增选项",
        "en_US": "+ Add Option",
    },
    "btn_del_option": {
        "zh_CN": "删除选项",
        "en_US": "Delete Option",
    },
    "opt_text_header": {
        "zh_CN": "选项文字",
        "en_US": "Option Text",
    },
    "opt_next_header": {
        "zh_CN": "跳转场景",
        "en_US": "Destination Scene",
    },

    # ---- 对话框与提示 ----
    "dirty_save_prompt": {
        "zh_CN": "当前工程有未保存的修改，是否立即保存？",
        "en_US": "The project has unsaved changes. Would you like to save now?",
    },
    "project_saved": {
        "zh_CN": "工程已成功保存！",
        "en_US": "Project saved successfully!",
    },
    "confirm_delete_scene": {
        "zh_CN": "确定要删除场景「{name}」及其包含的所有步骤吗？此操作无法撤销。",
        "en_US": "Are you sure you want to delete scene '{name}' and all its steps? This cannot be undone.",
    },
    "confirm_delete_step": {
        "zh_CN": "确定要删除选中的步骤吗？",
        "en_US": "Are you sure you want to delete the selected step?",
    },

    # ---- 云部署与 Web 打包对话框 ----
    "web_dlg_title": {
        "zh_CN": "☁️ 云端在线部署与 Web 游戏发布",
        "en_US": "☁️ Cloud Online Deployment & Web Game Export",
    },
    "tab_cloud_deploy": {
        "zh_CN": "☁️ 云端在线直连部署",
        "en_US": "☁️ Direct Online Deploy",
    },
    "tab_export_pkg": {
        "zh_CN": "📦 导出 Web 部署包",
        "en_US": "📦 Export Web Package",
    },
    "tab_deploy_guide": {
        "zh_CN": "📖 部署教程与指引",
        "en_US": "📖 Deployment Guide",
    },
    "lbl_select_platform": {
        "zh_CN": "选择对接平台:",
        "en_US": "Select Platform:",
    },
    "lbl_project_slug": {
        "zh_CN": "项目英文标识:",
        "en_US": "Project Slug (ID):",
    },
    "btn_start_deploy": {
        "zh_CN": "🚀 开始在线对接部署",
        "en_US": "🚀 Start Online Deploy",
    },
    "btn_stop_deploy": {
        "zh_CN": "🛑 停止",
        "en_US": "🛑 Stop",
    },
    "btn_open_browser": {
        "zh_CN": "🌐 在浏览器中打开",
        "en_US": "🌐 Open in Browser",
    },
    "btn_copy_url": {
        "zh_CN": "📋 复制链接",
        "en_US": "📋 Copy URL",
    },
    "btn_open_folder": {
        "zh_CN": "📂 浏览生成的文件",
        "en_US": "📂 Browse Output Folder",
    },
    "btn_start_pkg": {
        "zh_CN": "📦 开始构建 Web 部署包",
        "en_US": "📦 Build Web Deployment Package",
    },
    "deploy_success_banner": {
        "zh_CN": "🎉 恭喜！游戏已成功部署上线！",
        "en_US": "🎉 Congratulations! Your game is deployed online!",
    },
    # ---- 场景与编辑器界面扩充 ----
    "editor_title": {
        "zh_CN": "{app_name} 编辑器",
        "en_US": "{app_name} Editor",
    },
    "editor_title_project": {
        "zh_CN": "{app_name} 编辑器 - {title}{path}{dirty}",
        "en_US": "{app_name} Editor - {title}{path}{dirty}",
    },
    "unsaved": {
        "zh_CN": "未保存",
        "en_US": "Unsaved",
    },
    "scene_list_title": {
        "zh_CN": "场景列表 (可拖拽排序)",
        "en_US": "Scenes (Drag to Reorder)",
    },
    "btn_new_scene": {
        "zh_CN": "新建场景",
        "en_US": "New Scene",
    },
    "btn_del_scene": {
        "zh_CN": "删除场景",
        "en_US": "Delete Scene",
    },
    "btn_move_up": {
        "zh_CN": "上移",
        "en_US": "Move Up",
    },
    "btn_move_down": {
        "zh_CN": "下移",
        "en_US": "Move Down",
    },
    "btn_set_start": {
        "zh_CN": "设为起始场景",
        "en_US": "Set as Start Scene",
    },
    "scene_title_text": {
        "zh_CN": "标题文字:",
        "en_US": "Title Text:",
    },
    "scene_name": {
        "zh_CN": "场景名称:",
        "en_US": "Scene Name:",
    },
    "scene_background": {
        "zh_CN": "背景图:",
        "en_US": "Background:",
    },
    "scene_bgm": {
        "zh_CN": "背景音乐:",
        "en_US": "BGM Music:",
    },
    "btn_choose": {
        "zh_CN": "选择…",
        "en_US": "Select…",
    },
    "step_list_title": {
        "zh_CN": "步骤列表 (按顺序执行):",
        "en_US": "Steps (Executed sequentially):",
    },
    "cover_scene_hint": {
        "zh_CN": "🎬 封面场景\n\n封面是游戏的标题画面, 不含步骤。\n可设置: 标题文字、背景图、背景音乐。\n游戏启动时显示此画面与主菜单 (开始/继续/加载/退出)。",
        "en_US": "🎬 Cover Scene\n\nThe cover is your game's opening title screen and contains no steps.\nConfigures: Title text, background image, and BGM.\nDisplayed at game startup with the main menu (Start/Continue/Load/Exit).",
    },
    "menu_run_title": {
        "zh_CN": "运行(&R)",
        "en_US": "Run(&R)",
    },
    "menu_file_title": {
        "zh_CN": "文件(&F)",
        "en_US": "File(&F)",
    },
    "menu_deploy_title": {
        "zh_CN": "发布与部署(&P)",
        "en_US": "Publish & Deploy(&P)",
    },
    "menu_help_title": {
        "zh_CN": "帮助(&H)",
        "en_US": "Help(&H)",
    },
    "menu_lang_title": {
        "zh_CN": "语言(&L)",
        "en_US": "Language(&L)",
    },
    "action_play": {
        "zh_CN": "从头播放",
        "en_US": "Play from Start",
    },
    "action_play_here": {
        "zh_CN": "从当前场景播放",
        "en_US": "Play Current Scene",
    },
    "action_cloud_deploy_full": {
        "zh_CN": "☁️ 云端在线部署 (Cloudflare / Vercel / 容器)…",
        "en_US": "☁️ Cloud Online Deploy (Cloudflare / Vercel / Docker)…",
    },
    "action_web_pkg_full": {
        "zh_CN": "🌐 打包为 Web 静态应用…",
        "en_US": "🌐 Export Static Web App…",
    },
    "action_pkg_full": {
        "zh_CN": "📦 打包为桌面可执行程序 (.exe)…",
        "en_US": "📦 Package Desktop Executable (.exe)…",
    },
    "action_web_preview_full": {
        "zh_CN": "▶ 在浏览器中预览…",
        "en_US": "▶ Preview in Browser…",
    },
    "tb_play_btn": {
        "zh_CN": "▶ 播放",
        "en_US": "▶ Play",
    },
    "tb_save_btn": {
        "zh_CN": "💾 保存",
        "en_US": "💾 Save",
    },
    "tb_pkg_btn": {
        "zh_CN": "📦 打包",
        "en_US": "📦 Package",
    },
    "tb_pkg_tip": {
        "zh_CN": "打包为可执行程序 / Web 应用",
        "en_US": "Package as Desktop Exe / Web App",
    },
    "action_pkg_win": {
        "zh_CN": "打包为 Windows 可执行程序…",
        "en_US": "Package for Windows (.exe)…",
    },
    "action_pkg_web": {
        "zh_CN": "打包为 Web 应用…",
        "en_US": "Package for Web…",
    },
    "action_web_preview_tb": {
        "zh_CN": "🌐 浏览器中预览…",
        "en_US": "🌐 Preview in Browser…",
    },
    "tb_stop_audio_btn": {
        "zh_CN": "⏹ 停止音频",
        "en_US": "⏹ Stop Audio",
    },
    "tb_auto_save_btn": {
        "zh_CN": "💨 自动保存",
        "en_US": "💨 Auto-Save",
    },
    "tb_auto_save_tip": {
        "zh_CN": "开启: 每 3 分钟写一份 .auto.galpy 副本 (不覆盖主文件)\n关闭: 仅手动保存时才写主文件",
        "en_US": "On: Writes a .auto.galpy backup every 3 min (does not overwrite main file)\nOff: Writes to main file only upon manual save",
    },
    "tb_recover_auto_btn": {
        "zh_CN": "↩ 恢复自动保存",
        "en_US": "↩ Restore Backup",
    },
    "status_ready": {
        "zh_CN": "就绪",
        "en_US": "Ready",
    },
    "about_title": {
        "zh_CN": "关于 GalPy",
        "en_US": "About GalPy",
    },
    "about_content": {
        "zh_CN": "<h3>{app_name}</h3><p>纯 Python 实现的 Galgame 引擎</p><p>支持 文字 / 音频 / 视频 / 图片 渲染</p><p>可视化编辑 + PyInstaller 一键打包 (Windows 脱机)</p><p>Flask Web 服务器 + 浏览器游玩 + 云端在线部署</p>",
        "en_US": "<h3>{app_name}</h3><p>Python-Powered Visual Novel Engine</p><p>Supports Dialogue, Audio, Cutscene Video & Character Sprites</p><p>Visual Editor + PyInstaller 1-Click Offline Packaging</p><p>Flask Web Server + Browser Play + Cloud Deployment</p>",
    },
}

LANGUAGES = [
    ("auto", "lang_auto"),
    ("zh_CN", "lang_zh"),
    ("en_US", "lang_en"),
]


# ==============================================================================
# 翻译与取值函数
# ==============================================================================

def tr(key: str, default: Optional[str] = None, **kwargs: Any) -> str:
    """翻译给定的文本键 (key)。

    Args:
        key:     翻译词条标识 (如 "app_title", "save")
        default: 若找不到对应的翻译时回退的文本 (默认使用 key 本身)
        kwargs:  字符串格式化参数 (如 count=3, name="晨光")
    """
    lang = get_effective_language()
    entry = _TRANSLATIONS.get(key)
    if entry:
        res = entry.get(lang) or entry.get("zh_CN") or entry.get("en_US")
        if res:
            if kwargs:
                try:
                    return res.format(**kwargs)
                except Exception:
                    return res
            return res

    fallback = default if default is not None else key
    if kwargs:
        try:
            return fallback.format(**kwargs)
        except Exception:
            return fallback
    return fallback


def get_step_type_label(step_type: str) -> str:
    """获取步骤类型的本地化名称。"""
    key = f"step_{step_type}"
    return tr(key, default=step_type)


def get_asset_category_label(category: str) -> str:
    """获取资源类别的本地化名称。"""
    key = f"cat_{category}"
    return tr(key, default=category)


def get_position_label(position: str) -> str:
    """获取角色站位预设的本地化名称。"""
    key = f"pos_{position}"
    return tr(key, default=position)


def get_audio_category_label(category: str) -> str:
    """获取音频分类的本地化名称。"""
    key = f"cat_{category}"
    return tr(key, default=category)


def get_audio_action_label(action: str) -> str:
    """获取音频操作的本地化名称。"""
    key = f"audio_{action}"
    return tr(key, default=action)
