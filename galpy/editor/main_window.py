"""编辑器主窗口: 场景管理 + 步骤列表 + 资源管理 + 运行/打包。"""
from __future__ import annotations

import os
import sys
import subprocess
import tempfile
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal, QDateTime
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QDockWidget, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QListView, QMainWindow,
    QMenu, QMessageBox, QPlainTextEdit, QPushButton, QSizePolicy, QSplitter,
    QToolBar, QToolButton, QVBoxLayout, QWidget,
)

from ..config import APP_NAME, AUTO_SAVE_SUFFIX, PROJECT_EXT, PROJECT_FILE_FILTER, PROJECT_FILE_NAME, ASSETS_DIR_NAME
from ..engine.media import AudioManager
from ..i18n import (
    tr, on_language_changed, get_language, set_language,
    get_effective_language, LANGUAGES,
)
from ..runtime import ThemeToggleButton, LanguageSelectorButton
from ..model import Project, Scene, Step, STEP_TYPES
from .asset_browser import AssetBrowser
from .step_dialog import StepEditDialog


class ReorderableSceneList(QListWidget):
    """支持拖拽重排序的场景列表; 拖放完成后发射 reordered 信号。"""

    reordered = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        # 仅允许内部移动 (本列表内重排), 杜绝跨控件拖放造成的"乱序"
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setMovement(QListView.Static)  # 不允许自由飘动, 保持列表对齐
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)

    def dropEvent(self, event) -> None:
        """拖放完成: 先在 UI 上移动项, 再通知父窗口同步数据模型。"""
        # 记录拖放前的选中场景 id — 拖放后按 id 精确恢复, 不依赖行号
        sel_id = None
        sel_row = -1
        cur = self.currentItem()
        if cur is not None:
            sel_id = cur.data(Qt.UserRole)
            sel_row = self.row(cur)

        # 先在 UI 上完成移动 (Qt 内部机制)
        super().dropEvent(event)

        # 在 UI 移动完成后, 基于当前视觉位置更新数据模型, 由父窗口负责
        self.reordered.emit()

        # 数据模型同步完成后, 恢复选中 —— 必须按 id 查找, 确保与实际场景对应
        # 注意: 不再 setCurrentRow (会触发 currentRowChanged 引发级联错误),
        # 仅通过 blockSignals 下的 setCurrentItem 改变视觉选中状态
        if sel_id is not None:
            for i in range(self.count()):
                if self.item(i).data(Qt.UserRole) == sel_id:
                    self.blockSignals(True)
                    self.setCurrentRow(i)
                    self.blockSignals(False)
                    break


class EditorWindow(QMainWindow):
    """GalPy 可视化编辑器主窗口。"""

    def __init__(self, project_path: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} 编辑器")
        self.resize(1200, 760)

        self.project: Project = Project.empty()
        self.project_path: Optional[str] = None
        self.project_dir: str = ""
        self._current_scene: Optional[Scene] = None
        self._suppress_scene_signal = False
        # 脏标记: 自上次保存后是否有未保存修改 (标题栏显示 * 并在关闭时提示)
        self._dirty: bool = False

        # 自动保存状态: True=开启 (写 .auto.galpy 副本), False=关闭 (仅手动保存)
        self._auto_save_enabled = True

        # 编辑器内音频预览管理器 (试听 BGM / 音效; 窗口关闭时统一停止)
        self._audio = AudioManager(self)

        # 自动保存定时器: 每 3 分钟写一次 .auto.galpy 副本 (永远不覆盖主文件)
        self._auto_save_timer = QTimer(self)
        self._auto_save_timer.setInterval(180 * 1000)  # 3 分钟
        self._auto_save_timer.timeout.connect(self._auto_save)
        self._auto_save_timer.start()

        self._build_ui()
        self._build_menus()
        self._build_toolbar()
        self.retranslate_ui()
        on_language_changed(lambda _lang: self.retranslate_ui())

        if project_path and os.path.exists(project_path):
            self._load_project(project_path)
        else:
            self._set_project(Project.empty(), None)

    # ============================================================
    # UI 构建
    # ============================================================
    def _build_ui(self) -> None:
        # 左: 场景列表 (支持拖拽重排)
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(6, 6, 6, 6)
        self._lbl_scenes = QLabel("场景列表 (可拖拽排序)")
        left_lay.addWidget(self._lbl_scenes)
        self._scene_list = ReorderableSceneList()
        self._scene_list.reordered.connect(self._sync_scene_order)
        self._scene_list.currentRowChanged.connect(self._on_scene_selected)
        left_lay.addWidget(self._scene_list, 1)

        srow = QHBoxLayout()
        self._b_add_s = QPushButton("新建场景")
        self._b_add_s.setObjectName("PrimaryBtn")
        self._b_del_s = QPushButton("删除场景")
        self._b_del_s.setObjectName("DangerBtn")
        self._b_add_s.clicked.connect(self._add_scene)
        self._b_del_s.clicked.connect(self._del_scene)
        srow.addWidget(self._b_add_s)
        srow.addWidget(self._b_del_s)
        left_lay.addLayout(srow)

        srow2 = QHBoxLayout()
        self._b_up_s = QPushButton("上移")
        self._b_down_s = QPushButton("下移")
        self._b_up_s.clicked.connect(lambda: self._move_scene(-1))
        self._b_down_s.clicked.connect(lambda: self._move_scene(1))
        srow2.addWidget(self._b_up_s)
        srow2.addWidget(self._b_down_s)
        left_lay.addLayout(srow2)

        self._b_start = QPushButton("设为起始场景")
        self._b_start.clicked.connect(self._set_start_scene)
        left_lay.addWidget(self._b_start)

        # 中: 场景编辑 (属性 + 步骤)
        center = QWidget()
        cl = QVBoxLayout(center)
        cl.setContentsMargins(6, 6, 6, 6)

        # 场景属性
        self._scene_name = QLineEdit()
        self._scene_name.textEdited.connect(lambda _t: self._mark_dirty())
        self._scene_bg = QLineEdit()
        self._scene_bg.setReadOnly(True)
        self._scene_bg_btn = QPushButton("选择…")
        self._scene_bg_btn.clicked.connect(self._pick_scene_bg)
        self._scene_bg_clr = QPushButton("清空")
        self._scene_bg_clr.clicked.connect(self._clear_scene_bg)
        self._scene_bgm = QLineEdit()
        self._scene_bgm.setReadOnly(True)
        self._scene_bgm_btn = QPushButton("选择…")
        self._scene_bgm_btn.clicked.connect(self._pick_scene_bgm)
        self._scene_bgm_play = QPushButton("试听")
        self._scene_bgm_play.clicked.connect(self._preview_bgm)
        self._scene_bgm_stop = QPushButton("停止")
        self._scene_bgm_stop.clicked.connect(self._stop_bgm)
        self._scene_bgm_clr = QPushButton("清空")
        self._scene_bgm_clr.clicked.connect(self._clear_scene_bgm)

        self._scene_name_label = QLabel("场景名称:")
        self._scene_bg_label = QLabel("背景图:")
        self._scene_bgm_label = QLabel("背景音乐:")

        form = QFormLayout()
        form.addRow(self._scene_name_label, self._scene_name)
        bg_row = QHBoxLayout()
        bg_row.addWidget(self._scene_bg, 1)
        bg_row.addWidget(self._scene_bg_btn)
        bg_row.addWidget(self._scene_bg_clr)
        form.addRow(self._scene_bg_label, bg_row)
        bgm_row = QHBoxLayout()
        bgm_row.addWidget(self._scene_bgm, 1)
        bgm_row.addWidget(self._scene_bgm_btn)
        bgm_row.addWidget(self._scene_bgm_play)
        bgm_row.addWidget(self._scene_bgm_stop)
        bgm_row.addWidget(self._scene_bgm_clr)
        form.addRow(self._scene_bgm_label, bgm_row)
        cl.addLayout(form)

        # 步骤区 (容器: 选中封面时整体隐藏)
        self._steps_section = QWidget()
        sl = QVBoxLayout(self._steps_section)
        sl.setContentsMargins(0, 0, 0, 0)
        self._lbl_steps = QLabel("步骤列表 (按顺序执行):")
        sl.addWidget(self._lbl_steps)
        self._step_list = QListWidget()
        self._step_list.currentRowChanged.connect(self._on_step_selected)
        sl.addWidget(self._step_list, 1)
        strow = QHBoxLayout()
        self._b_add_step = QPushButton("添加步骤")
        self._b_add_step.setObjectName("PrimaryBtn")
        self._b_edit_step = QPushButton("编辑")
        self._b_del_step = QPushButton("删除")
        self._b_del_step.setObjectName("DangerBtn")
        self._b_up_step = QPushButton("上移")
        self._b_down_step = QPushButton("下移")
        self._b_add_step.clicked.connect(self._add_step)
        self._b_edit_step.clicked.connect(self._edit_step)
        self._b_del_step.clicked.connect(self._del_step)
        self._b_up_step.clicked.connect(lambda: self._move_step(-1))
        self._b_down_step.clicked.connect(lambda: self._move_step(1))
        for b in (self._b_add_step, self._b_edit_step, self._b_del_step,
                  self._b_up_step, self._b_down_step):
            strow.addWidget(b)
        strow.addStretch(1)
        sl.addLayout(strow)
        cl.addWidget(self._steps_section, 1)

        # 封面场景提示 (选中封面时显示)
        self._cover_hint = QLabel(
            "🎬 封面场景\n\n封面是游戏的标题画面, 不含步骤。\n"
            "可设置: 标题文字、背景图、背景音乐。\n"
            "游戏启动时显示此画面与主菜单 (开始/继续/加载/退出)。"
        )
        self._cover_hint.setAlignment(Qt.AlignCenter)
        self._cover_hint.setWordWrap(True)
        self._cover_hint.setStyleSheet("color: #9aa3bd; font-size: 14px;")
        self._cover_hint.hide()
        cl.addWidget(self._cover_hint, 1)

        # 右: 资源浏览器 (作为 dock)
        self._asset_browser = AssetBrowser(self.project, self.project_dir)
        self._asset_browser.assets_changed.connect(self._mark_dirty)
        self._dock = QDockWidget("资源管理", self)
        self._dock.setWidget(self._asset_browser)
        self._dock.setFeatures(QDockWidget.DockWidgetMovable)
        self.addDockWidget(Qt.RightDockWidgetArea, self._dock)

        # 主分割
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(center)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        self.setCentralWidget(splitter)

        # 状态栏
        self.statusBar().showMessage(tr("status_ready", "就绪"))

    def _build_menus(self) -> None:
        mb = self.menuBar()

        self._m_file = mb.addMenu("文件(&F)")
        self._a_new = QAction("新建工程", self)
        self._a_new.setShortcut("Ctrl+N")
        self._a_new.triggered.connect(self._new_project)
        self._a_open = QAction("打开工程…", self)
        self._a_open.setShortcut("Ctrl+O")
        self._a_open.triggered.connect(self._open_project)
        self._a_save = QAction("保存工程", self)
        self._a_save.setShortcut("Ctrl+S")
        self._a_save.triggered.connect(self._save_project)
        self._a_saveas = QAction("另存为…", self)
        self._a_saveas.triggered.connect(self._save_project_as)
        self._m_file.addAction(self._a_new)
        self._m_file.addAction(self._a_open)
        self._m_file.addAction(self._a_save)
        self._m_file.addAction(self._a_saveas)
        self._m_file.addSeparator()
        self._a_new_demo = QAction("新建示例工程…", self)
        self._a_new_demo.triggered.connect(self._new_demo_project)
        self._m_file.addAction(self._a_new_demo)
        self._m_file.addSeparator()
        self._a_quit = QAction("退出", self)
        self._a_quit.setShortcut("Ctrl+Q")
        self._a_quit.triggered.connect(self.close)
        self._m_file.addAction(self._a_quit)

        self._m_run = mb.addMenu("运行(&R)")
        self._a_play = QAction("从头播放", self)
        self._a_play.setShortcut("F5")
        self._a_play.triggered.connect(self._play_game)
        self._a_play_here = QAction("从当前场景播放", self)
        self._a_play_here.setShortcut("F6")
        self._a_play_here.triggered.connect(self._play_from_current)
        self._m_run.addAction(self._a_play)
        self._m_run.addAction(self._a_play_here)

        self._m_pkg = mb.addMenu("发布与部署(&P)")
        self._a_cloud_deploy = QAction("☁️ 云端在线部署 (Cloudflare / Vercel / 容器)…", self)
        self._a_cloud_deploy.triggered.connect(self._deploy_cloud)
        self._m_pkg.addAction(self._a_cloud_deploy)
        self._a_web_pkg = QAction("🌐 打包为 Web 静态应用…", self)
        self._a_web_pkg.triggered.connect(self._package_web)
        self._m_pkg.addAction(self._a_web_pkg)
        self._a_pkg = QAction("📦 打包为桌面可执行程序 (.exe)…", self)
        self._a_pkg.triggered.connect(self._package_game)
        self._m_pkg.addAction(self._a_pkg)
        self._m_pkg.addSeparator()
        self._a_web_preview = QAction("▶ 在浏览器中预览…", self)
        self._a_web_preview.triggered.connect(self._preview_web)
        self._m_pkg.addAction(self._a_web_preview)

        # 语言菜单
        self._m_lang = mb.addMenu("语言(&L)")
        self._lang_actions: dict[str, QAction] = {}
        for code, label_key in [("auto", "lang_auto"), ("zh_CN", "lang_zh"), ("en_US", "lang_en")]:
            act = QAction(code, self)
            act.setCheckable(True)
            act.triggered.connect(lambda checked=False, c=code: set_language(c))
            self._m_lang.addAction(act)
            self._lang_actions[code] = act

        self._m_help = mb.addMenu("帮助(&H)")
        self._a_about = QAction("关于", self)
        self._a_about.triggered.connect(self._about)
        self._m_help.addAction(self._a_about)

    def _build_toolbar(self) -> None:
        self._tb = QToolBar("主工具栏")
        self._tb.setMovable(False)
        self._a_tb_play = self._tb.addAction("▶ 播放", self._play_game)
        self._a_tb_save = self._tb.addAction("💾 保存", self._save_project)

        # 打包按钮 (下拉菜单: Windows 打包 / Web 打包 / Web 预览)
        self._pkg_btn = QToolButton()
        self._pkg_btn.setText("📦 打包")
        self._pkg_btn.setPopupMode(QToolButton.InstantPopup)  # 点击即弹出菜单
        self._pkg_btn.setToolTip("打包为可执行程序 / Web 应用")
        self._pkg_menu = QMenu(self._pkg_btn)
        self._a_pkg_win = self._pkg_menu.addAction("打包为 Windows 可执行程序…")
        self._a_pkg_win.triggered.connect(self._package_game)
        self._a_pkg_web = self._pkg_menu.addAction("打包为 Web 应用…")
        self._a_pkg_web.triggered.connect(self._package_web)
        self._pkg_menu.addSeparator()
        self._a_web_preview_tb = self._pkg_menu.addAction("🌐 浏览器中预览…")
        self._a_web_preview_tb.triggered.connect(self._preview_web)
        self._pkg_btn.setMenu(self._pkg_menu)
        self._tb.addWidget(self._pkg_btn)

        self._tb.addSeparator()
        self._a_stop_audio = self._tb.addAction("⏹ 停止音频", self._stop_all_audio)
        self._tb.addSeparator()
        # 自动保存开关 (Checkable QAction)
        self._auto_save_action = self._tb.addAction("💨 自动保存")
        self._auto_save_action.setCheckable(True)
        self._auto_save_action.setChecked(True)
        self._auto_save_action.setToolTip(
            "开启: 每 3 分钟写一份 .auto.galpy 副本 (不覆盖主文件)\n"
            "关闭: 仅手动保存时才写主文件"
        )
        self._auto_save_action.triggered.connect(self._toggle_auto_save)
        # 从自动保存恢复
        self._a_recover_auto_save = self._tb.addAction("↩ 恢复自动保存", self._recover_from_auto_save)

        # 右侧: 语言选择与深浅色主题切换
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._tb.addWidget(spacer)
        self._lang_btn = LanguageSelectorButton(self)
        self._tb.addWidget(self._lang_btn)
        self._theme_btn = ThemeToggleButton(self)
        self._tb.addWidget(self._theme_btn)
        self.addToolBar(self._tb)

    def retranslate_ui(self, _lang: Optional[str] = None) -> None:
        """动态更新整个编辑器界面语言。"""
        self._update_title()

        # 菜单
        if hasattr(self, "_m_file"):
            self._m_file.setTitle(tr("menu_file_title", "文件(&F)"))
            self._a_new.setText(tr("action_new", "新建工程"))
            self._a_open.setText(tr("action_open", "打开工程…"))
            self._a_save.setText(tr("action_save", "保存工程"))
            self._a_saveas.setText(tr("action_save_as", "另存为…"))
            self._a_new_demo.setText(tr("action_demo", "新建示例工程…"))
            self._a_quit.setText(tr("action_exit", "退出"))

        if hasattr(self, "_m_run"):
            self._m_run.setTitle(tr("menu_run_title", "运行(&R)"))
            self._a_play.setText(tr("action_play", "从头播放"))
            self._a_play_here.setText(tr("action_play_here", "从当前场景播放"))

        if hasattr(self, "_m_pkg"):
            self._m_pkg.setTitle(tr("menu_deploy_title", "发布与部署(&P)"))
            self._a_cloud_deploy.setText(tr("action_cloud_deploy_full", "☁️ 云端在线部署 (Cloudflare / Vercel / 容器)…"))
            self._a_web_pkg.setText(tr("action_web_pkg_full", "🌐 打包为 Web 静态应用…"))
            self._a_pkg.setText(tr("action_pkg_full", "📦 打包为桌面可执行程序 (.exe)…"))
            self._a_web_preview.setText(tr("action_web_preview_full", "▶ 在浏览器中预览…"))

        if hasattr(self, "_m_lang"):
            self._m_lang.setTitle(tr("menu_lang_title", "语言(&L)"))
            cur = get_language()
            for code, act in self._lang_actions.items():
                label_key = "lang_zh" if code == "zh_CN" else ("lang_en" if code == "en_US" else "lang_auto")
                act.setText(tr(label_key, code))
                act.setChecked(cur == code)

        if hasattr(self, "_m_help"):
            self._m_help.setTitle(tr("menu_help_title", "帮助(&H)"))
            self._a_about.setText(tr("action_about", "关于"))

        # 工具栏
        if hasattr(self, "_tb"):
            self._tb.setWindowTitle(tr("toolbar_title", "主工具栏"))
            self._a_tb_play.setText(tr("tb_play_btn", "▶ 播放"))
            self._a_tb_save.setText(tr("tb_save_btn", "💾 保存"))
            self._pkg_btn.setText(tr("tb_pkg_btn", "📦 打包"))
            self._pkg_btn.setToolTip(tr("tb_pkg_tip", "打包为可执行程序 / Web 应用"))
            self._a_pkg_win.setText(tr("action_pkg_win", "打包为 Windows 可执行程序…"))
            self._a_pkg_web.setText(tr("action_pkg_web", "打包为 Web 应用…"))
            self._a_web_preview_tb.setText(tr("action_web_preview_tb", "🌐 浏览器中预览…"))
            self._a_stop_audio.setText(tr("tb_stop_audio_btn", "⏹ 停止音频"))
            self._auto_save_action.setText(tr("tb_auto_save_btn", "💨 自动保存"))
            self._auto_save_action.setToolTip(tr("tb_auto_save_tip", "开启: 每 3 分钟写一份 .auto.galpy 副本\n关闭: 仅手动保存时才写主文件"))
            self._a_recover_auto_save.setText(tr("tb_recover_auto_btn", "↩ 恢复自动保存"))

        # 左侧场景列表面板
        if hasattr(self, "_lbl_scenes"):
            self._lbl_scenes.setText(tr("scene_list_title", "场景列表 (可拖拽排序)"))
            self._b_add_s.setText(tr("btn_new_scene", "新建场景"))
            self._b_del_s.setText(tr("btn_del_scene", "删除场景"))
            self._b_up_s.setText(tr("btn_move_up", "上移"))
            self._b_down_s.setText(tr("btn_move_down", "下移"))
            self._b_start.setText(tr("btn_set_start", "设为起始场景"))

        # 中部属性面板
        if hasattr(self, "_scene_name_label"):
            is_cover = bool(self._current_scene and self._current_scene.is_cover)
            self._scene_name_label.setText(
                tr("scene_title_text", "标题文字:") if is_cover else tr("scene_name", "场景名称:")
            )
            self._scene_bg_label.setText(tr("scene_background", "背景图:"))
            self._scene_bg_btn.setText(tr("btn_choose", "选择…"))
            self._scene_bg_clr.setText(tr("clear", "清空"))
            self._scene_bgm_label.setText(tr("scene_bgm", "背景音乐:"))
            self._scene_bgm_btn.setText(tr("btn_choose", "选择…"))
            self._scene_bgm_play.setText(tr("btn_preview", "试听"))
            self._scene_bgm_stop.setText(tr("stop", "停止"))
            self._scene_bgm_clr.setText(tr("clear", "清空"))

        # 步骤区域
        if hasattr(self, "_lbl_steps"):
            self._lbl_steps.setText(tr("step_list_title", "步骤列表 (按顺序执行):"))
            self._b_add_step.setText(tr("btn_add_step", "+ 添加步骤"))
            self._b_edit_step.setText(tr("edit", "编辑"))
            self._b_del_step.setText(tr("delete", "删除"))
            self._b_up_step.setText(tr("btn_move_up", "上移"))
            self._b_down_step.setText(tr("btn_move_down", "下移"))

        # 封面提示
        if hasattr(self, "_cover_hint"):
            self._cover_hint.setText(tr("cover_scene_hint", "🎬 封面场景..."))

        # 资源管理器 Dock
        if hasattr(self, "_dock"):
            self._dock.setWindowTitle(tr("dock_assets", "资源管理"))

        # 刷新步骤列表以更新各步骤类型的中英文标签
        if hasattr(self, "_scene_list"):
            self._refresh_scenes()

    def _toggle_auto_save(self, checked: bool) -> None:
        """切换自动保存模式 (写独立副本 vs 仅手动保存)。"""
        self._auto_save_enabled = checked
        if checked:
            self._auto_save_timer.start()
            self.statusBar().showMessage(
                "自动保存: 已开启 (每 3 分钟写 .auto.galpy 副本)", 4000
            )
        else:
            self._auto_save_timer.stop()
            self.statusBar().showMessage(
                "自动保存: 已关闭 (仅手动保存时写主文件)", 4000
            )

    def _stop_all_audio(self) -> None:
        """停止编辑器内所有预览音频 (BGM / 音效)。"""
        self._audio.stop_all()
        self.statusBar().showMessage("已停止所有音频预览", 2000)

    # ============================================================
    # 工程管理
    # ============================================================
    def _update_title(self) -> None:
        """统一更新窗口标题: 工程名 + 路径 + 未保存标记 (*)。"""
        star = " *" if self._dirty else ""
        path_info = f"  [{self.project_path}]" if self.project_path else f"  [{tr('unsaved', '未保存')}]"
        self.setWindowTitle(
            tr(
                "editor_title_project",
                "{app_name} 编辑器 - {title}{path}{dirty}",
                app_name=APP_NAME,
                title=self.project.title,
                path=path_info,
                dirty=star,
            )
        )

    def _mark_dirty(self) -> None:
        if not self._dirty:
            self._dirty = True
            self._update_title()

    def _clear_dirty(self) -> None:
        if self._dirty:
            self._dirty = False
            self._update_title()

    def _set_project(self, project: Project, path: Optional[str]) -> None:
        self.project = project
        self.project_path = path
        self.project_dir = os.path.dirname(path) if path else ""
        self._asset_browser.set_project(project, self.project_dir)
        self._refresh_scenes()
        if project.scenes:
            self._scene_list.setCurrentRow(0)
        self._dirty = False
        self._update_title()
        self.statusBar().showMessage(
            f"已加载工程: {project.title}  场景 {len(project.scenes)} 个"
        )

    def _new_project(self) -> None:
        if not self._confirm_discard():
            return
        self._set_project(Project.empty("新游戏"), None)

    def _new_demo_project(self) -> None:
        if not self._confirm_discard():
            return
        parent_dir = QFileDialog.getExistingDirectory(self, "选择示例工程保存位置")
        if not parent_dir:
            return
        try:
            demo_title = "Demo_MorningSun" if get_effective_language() == "en_US" else "示例_晨光"
            project_dir = os.path.join(parent_dir, demo_title + "Galpy")
            os.makedirs(project_dir, exist_ok=True)
            os.makedirs(os.path.join(project_dir, ASSETS_DIR_NAME), exist_ok=True)
            from ..demo import create_demo_project
            project = create_demo_project(project_dir, demo_title)
            save_name = os.path.join(project_dir, demo_title + PROJECT_EXT)
            project.save(save_name)
            self._set_project(project, save_name)
        except Exception as e:
            QMessageBox.critical(self, tr("error", "示例工程生成失败"), str(e))

    def _open_project(self) -> None:
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "打开工程", "", PROJECT_FILE_FILTER
        )
        if path:
            self._load_project(path)

    def _load_project(self, path: str) -> None:
        # 检测: 如果用户打开的是 .auto.galpy 副本, 警告并建议切换到主文件
        base, ext = os.path.splitext(path)
        if base.endswith(AUTO_SAVE_SUFFIX):
            main_path = base[:-len(AUTO_SAVE_SUFFIX)] + ext
            hint = ""
            if os.path.exists(main_path):
                hint = f"\n\n主文件路径:\n  {main_path}"
            reply = QMessageBox.warning(
                self, "打开的是自动保存副本",
                f"你当前打开的是自动保存副本:\n  {path}\n\n"
                f"副本是 3 分钟自动生成的备份, 可能不是你想要的版本。\n"
                f"建议直接打开主文件 ({os.path.basename(main_path)})。{hint}\n\n"
                f"• 是: 加载此副本内容 (仅作查看)\n"
                f"• 否: 重新选择文件",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply == QMessageBox.No:
                self._open_project()  # 让用户重新选
                return
        try:
            project = Project.load(path)
        except Exception as e:
            QMessageBox.critical(self, "打开失败", f"无法读取工程文件:\n{e}")
            return
        self._set_project(project, path)
        # 检测是否存在比主文件更新的 .auto.galpy 副本, 提示恢复
        self._check_auto_save_recovery(path)

    def _save_project(self) -> None:
        if not self.project_path:
            return self._save_project_as()
        try:
            self._flush_scene_form()
            self.project.save(self.project_path)
            self._clear_dirty()
            self.statusBar().showMessage(f"已保存: {self.project_path}", 3000)
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))

    def _auto_save_path(self) -> Optional[str]:
        """返回自动保存副本的路径: 主文件 + .auto.galpy。"""
        if not self.project_path:
            return None
        # 如果当前工程本身就是 .auto.galpy 副本, 不做自动保存 (避免副本套副本)
        base, ext = os.path.splitext(self.project_path)
        if base.endswith(AUTO_SAVE_SUFFIX):
            return None
        if ext == PROJECT_EXT:
            return base + AUTO_SAVE_SUFFIX + PROJECT_EXT
        return base + AUTO_SAVE_SUFFIX + ext

    def _auto_save(self) -> None:
        """自动保存 (3 分钟一次): 写入独立的 .auto.galpy 副本, 永远不覆盖主文件。"""
        if not self._auto_save_enabled or not self.project_path:
            return
        auto_path = self._auto_save_path()
        if not auto_path:
            return
        try:
            self._flush_scene_form()
            self.project.save(auto_path)
            ts = QDateTime.currentDateTime().toString("HH:mm:ss")
            # 左下角状态栏提示, 附带主文件对比说明
            self.statusBar().showMessage(
                f"✓ 自动保存副本 ({ts}) → {os.path.basename(auto_path)}  [主文件未改动]",
                5000
            )
        except Exception as e:
            self.statusBar().showMessage(f"✗ 自动保存失败: {e}", 5000)

    def _recover_from_auto_save(self) -> None:
        """工具栏「恢复自动保存」按钮: 读取当前工程的 .auto.galpy 副本。"""
        auto_path = self._auto_save_path()
        if not auto_path or not os.path.exists(auto_path):
            QMessageBox.information(
                self, "无自动保存副本",
                f"当前工程没有找到自动保存副本:\n{auto_path or '(未保存)'}"
            )
            return
        if not self._confirm_discard():
            return
        self._recover_specific_auto_save(auto_path)

    def _check_auto_save_recovery(self, path: str) -> None:
        """打开工程时检测: 如果存在 .auto.galpy 副本且比主文件新, 提示用户是否恢复。"""
        base, ext = os.path.splitext(path)
        auto_path = base + AUTO_SAVE_SUFFIX + ext
        if not os.path.exists(auto_path):
            return
        try:
            main_mtime = os.path.getmtime(path)
            auto_mtime = os.path.getmtime(auto_path)
        except OSError:
            QMessageBox.warning(self, "检查自动保存副本失败", f"无法获取文件时间戳:\n{auto_path}")
            return
        if auto_mtime <= main_mtime:
            return  # 副本不比主文件新, 不需要提示
        # 格式化时间
        main_time = QDateTime.fromSecsSinceEpoch(int(main_mtime)).toString("yyyy-MM-dd HH:mm:ss")
        auto_time = QDateTime.fromSecsSinceEpoch(int(auto_mtime)).toString("yyyy-MM-dd HH:mm:ss")
        reply = QMessageBox.question(
            self, "发现自动保存副本",
            f"检测到更新的自动保存副本:\n\n"
            f"  主文件: {os.path.basename(path)}      (上次保存: {main_time})\n"
            f"  副本:   {os.path.basename(auto_path)}  (自动保存: {auto_time})\n\n"
            f"是否从自动保存副本恢复?\n\n"
            f"• 是: 加载副本内容到编辑器 (主文件不改动, 需手动保存确认)\n"
            f"• 否: 继续使用当前主文件",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply == QMessageBox.Yes:
            self._recover_specific_auto_save(auto_path)

    def _recover_specific_auto_save(self, auto_path: str) -> None:
        """从指定路径的自动保存副本恢复。"""
        try:
            backup = Project.load(auto_path)
        except Exception as e:
            QMessageBox.critical(self, "恢复失败", f"读取副本失败:\n{e}")
            return
        self.project = backup
        self._refresh_scenes()
        self._scene_list.setCurrentRow(0 if backup.scenes else -1)
        self.statusBar().showMessage(
            f"已从自动保存副本恢复: {backup.title}  ({len(backup.scenes)} 个场景)  — 请手动保存确认",
            6000
        )
        QMessageBox.information(
            self, "恢复成功",
            f"已从自动保存副本恢复:\n  {auto_path}\n\n"
            f"当前编辑器内容已替换为副本内容, 但主文件未改动。\n"
            f"如需永久生效, 请点击「💾 保存」手动保存。"
        )

    def _save_project_as(self) -> None:
        # 另存为: 选择父目录, 自动创建 "项目名Galpy/" 文件夹
        title = self.project.title or "我的游戏"
        parent_dir = QFileDialog.getExistingDirectory(
            self, "选择保存位置 (将自动创建项目文件夹)"
        )
        if not parent_dir:
            return
        project_dir = os.path.join(parent_dir, title + "Galpy")
        os.makedirs(project_dir, exist_ok=True)
        os.makedirs(os.path.join(project_dir, ASSETS_DIR_NAME), exist_ok=True)
        path = os.path.join(project_dir, title + PROJECT_EXT)
        self.project_path = path
        self.project_dir = project_dir
        self._asset_browser.set_project(self.project, self.project_dir)
        self._save_project()

    def _confirm_discard(self) -> bool:
        # 仅在有未保存修改时才提示放弃
        if not self._dirty:
            return True
        return QMessageBox.question(
            self, "确认", "放弃当前未保存的修改?",
            QMessageBox.Yes | QMessageBox.No,
        ) == QMessageBox.Yes

    # ============================================================
    # 场景管理
    # ============================================================
    def _scene_display_text(self, s: Scene) -> str:
        """场景在列表中显示的文字: 封面加 🎬, 按分支深度缩进, 起始场景加 ★。"""
        depth = self.project.scene_depth(s.id)
        mark = " ★" if s.id == self.project.start_scene else ""
        if s.is_cover:
            return f"🎬 {s.name}{mark}"
        if depth > 0:
            return f"{'    ' * depth}└ {s.name}{mark}"
        return f"{s.name}{mark}"

    def _refresh_scenes(self) -> None:
        """按 project.scenes 重建场景列表; 保留当前选中项 (按 sid 匹配)。"""
        # 记录当前选中的 sid
        cur_sid = None
        cur_item = self._scene_list.currentItem()
        if cur_item is not None:
            cur_sid = cur_item.data(Qt.UserRole)

        self._suppress_scene_signal = True
        self._scene_list.clear()
        sel_row = -1
        for i, s in enumerate(self.project.scenes):
            item = QListWidgetItem(self._scene_display_text(s))
            item.setData(Qt.UserRole, s.id)
            self._scene_list.addItem(item)
            if cur_sid is not None and s.id == cur_sid:
                sel_row = i

        # 恢复选中 (抑制信号)
        self._scene_list.blockSignals(True)
        if sel_row >= 0:
            self._scene_list.setCurrentRow(sel_row)
        self._scene_list.blockSignals(False)
        self._suppress_scene_signal = False
        self._refresh_steps()

    def _on_scene_selected(self, row: int) -> None:
        if self._suppress_scene_signal or row < 0:
            return
        self._flush_scene_form()  # 保存上一个场景编辑
        sid = self._scene_list.item(row).data(Qt.UserRole)
        self._current_scene = self.project.get_scene(sid)
        self._load_scene_form()

    def _load_scene_form(self) -> None:
        s = self._current_scene
        if s is None:
            self._scene_name.clear()
            self._scene_bg.clear()
            self._scene_bgm.clear()
            self._refresh_steps()
            return
        is_cover = s.is_cover
        # 封面场景: "场景名称" 改为 "标题文字"; 隐藏步骤区, 显示提示
        self._scene_name_label.setText(
            tr("scene_title_text", "标题文字:") if is_cover else tr("scene_name", "场景名称:")
        )
        self._steps_section.setVisible(not is_cover)
        self._cover_hint.setVisible(is_cover)
        self._scene_name.setText(s.name)
        self._scene_bg.setText(s.background)
        self._scene_bgm.setText(s.bgm)
        self._refresh_steps()

    def _flush_scene_form(self) -> None:
        """把表单中的编辑内容写回当前场景的数据模型, 并同步更新列表项文字。"""
        s = self._current_scene
        if s is None:
            return
        changed = False
        new_name = self._scene_name.text().strip()
        if new_name and new_name != s.name:
            s.name = new_name
            changed = True
        if self._scene_bg.text() != s.background:
            s.background = self._scene_bg.text()
            changed = True
        if self._scene_bgm.text() != s.bgm:
            s.bgm = self._scene_bgm.text()
            changed = True
        # 通过 sid 查找列表项并更新显示 —— 避免用 currentRow() 在排序后定位错误
        for i in range(self._scene_list.count()):
            item = self._scene_list.item(i)
            if item.data(Qt.UserRole) == s.id:
                item.setText(self._scene_display_text(s))
                break
        if changed:
            self._mark_dirty()

    def _add_scene(self) -> None:
        s = self.project.new_scene()
        self._refresh_scenes()
        # 选中新建的
        self._scene_list.setCurrentRow(len(self.project.scenes) - 1)
        self._mark_dirty()

    def _del_scene(self) -> None:
        s = self._current_scene
        if s is None:
            return
        if s.is_cover:
            QMessageBox.information(self, "无法删除", "封面场景不可删除。")
            return
        if QMessageBox.question(
            self, "删除场景", f"确定删除场景「{s.name}」吗?",
            QMessageBox.Yes | QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        # 子分支的 parent 指向被删场景时, 提升为顶级场景 (避免悬空 parent_scene)
        for sc in self.project.scenes:
            if sc.parent_scene == s.id:
                sc.parent_scene = ""
        self.project.scenes.remove(s)
        if self.project.start_scene == s.id:
            self.project.start_scene = self.project.scenes[0].id if self.project.scenes else ""
        self._current_scene = None
        self._refresh_scenes()
        if self.project.scenes:
            self._scene_list.setCurrentRow(0)
        self._mark_dirty()

    def _set_start_scene(self) -> None:
        s = self._current_scene
        if s is None:
            return
        if s.is_cover:
            QMessageBox.information(self, "无法设为起始", "封面场景不能作为游戏起始场景。")
            return
        self.project.start_scene = s.id
        self._refresh_scenes()
        self._mark_dirty()

    def _pick_scene_bg(self) -> None:
        rel = self._pick_asset("backgrounds", self._scene_bg.text())
        if rel is None or self._current_scene is None:
            return
        if rel != self._current_scene.background:
            self._scene_bg.setText(rel)
            self._current_scene.background = rel
            self._mark_dirty()

    def _pick_scene_bgm(self) -> None:
        rel = self._pick_asset("bgm", self._scene_bgm.text())
        if rel is None or self._current_scene is None:
            return
        if rel != self._current_scene.bgm:
            self._scene_bgm.setText(rel)
            self._current_scene.bgm = rel
            self._mark_dirty()

    def _clear_scene_bg(self) -> None:
        self._scene_bg.clear()
        if self._current_scene is not None and self._current_scene.background:
            self._current_scene.background = ""
            self._mark_dirty()

    def _clear_scene_bgm(self) -> None:
        self._scene_bgm.clear()
        if self._current_scene is not None and self._current_scene.bgm:
            self._current_scene.bgm = ""
            self._mark_dirty()
        self._audio.stop_bgm()

    def _preview_bgm(self) -> None:
        """试听当前选中的 BGM (循环播放, 直至点击停止)。"""
        rel = self._scene_bgm.text().strip()
        if not rel:
            QMessageBox.information(self, "试听", "请先选择背景音乐。")
            return
        full = rel if os.path.isabs(rel) else os.path.join(self.project_dir, rel)
        if not os.path.exists(full):
            QMessageBox.warning(self, "试听", f"文件不存在:\n{full}")
            return
        self._audio.play_bgm(full)
        self.statusBar().showMessage(f"试听 BGM: {os.path.basename(full)}", 3000)

    def _stop_bgm(self) -> None:
        """停止当前正在预览的 BGM。"""
        self._audio.stop_bgm()
        self.statusBar().showMessage("已停止 BGM 预览", 2000)

    # ---- 场景排序 ----
    def _sync_scene_order(self) -> None:
        """拖放重排后: 列表 UI 顺序已正确, 只需同步数据模型 + 重新加载表单。
        不再重建列表 (dropEvent 已完成 UI 移动), 避免二次清空造成的行号错乱。"""
        # 1) 保存当前场景表单到数据模型
        self._flush_scene_form()

        # 2) 按 UI 视觉顺序重建数据模型 (不重建 UI!)
        new_order: list = []
        for i in range(self._scene_list.count()):
            sid = self._scene_list.item(i).data(Qt.UserRole)
            scene = self.project.get_scene(sid)
            if scene is not None:
                new_order.append(scene)
        # 封面场景固定置顶: 若被拖到别处, 移回首位并刷新 UI
        cover = next((s for s in new_order if s.is_cover), None)
        displaced = cover is not None and new_order[0] is not cover
        if displaced:
            new_order.remove(cover)
            new_order.insert(0, cover)
        self.project.scenes = new_order

        # 3) 按当前选中项的 sid 重新加载表单 (确保场景名称 / BGM 等字段显示正确)
        sel_item = self._scene_list.currentItem()
        if sel_item is not None:
            sid = sel_item.data(Qt.UserRole)
            self._current_scene = self.project.get_scene(sid)
            self._load_scene_form()

        if displaced:
            self.statusBar().showMessage("封面场景固定在顶部, 已自动归位", 2500)
            self._refresh_scenes()
        else:
            self.statusBar().showMessage("场景顺序已更新", 2000)
        self._mark_dirty()

    def _move_scene(self, delta: int) -> None:
        """上移/下移当前场景 (按钮方式的排序)。"""
        row = self._scene_list.currentRow()
        total = len(self.project.scenes)
        new_row = row + delta
        if not (0 <= row < total) or not (0 <= new_row < total):
            return
        # 封面固定置顶: 不允许移动封面, 也不允许把别的场景移到封面之上 (row 0)
        if self.project.scenes[row].is_cover or self.project.scenes[new_row].is_cover:
            self.statusBar().showMessage("封面场景固定在顶部, 无法移动", 2500)
            return

        # 1) 先刷新当前场景表单到数据模型
        self._flush_scene_form()
        moved_scene = self._current_scene

        # 2) 交换数据模型
        scenes = self.project.scenes
        scenes[row], scenes[new_row] = scenes[new_row], scenes[row]

        # 3) 交换 UI 中的项 (抑制信号, 防止 currentRowChanged 干扰)
        self._suppress_scene_signal = True
        item = self._scene_list.takeItem(row)
        self._scene_list.insertItem(new_row, item)
        self._scene_list.blockSignals(True)
        self._scene_list.setCurrentRow(new_row)
        self._scene_list.blockSignals(False)
        self._suppress_scene_signal = False

        # 4) 手动刷新场景表单 (确保场景名称、BGM 等字段显示正确)
        self._current_scene = moved_scene
        self._load_scene_form()
        self._mark_dirty()

    def _pick_asset(self, category: str, current: str) -> Optional[str]:
        from PySide6.QtWidgets import QDialog, QListWidget, QDialogButtonBox, QVBoxLayout
        items = self.project.assets.get(category, [])
        if not items:
            QMessageBox.information(self, "无资源",
                                    f"请先在「资源管理」中导入 {category} 资源。")
            return None
        dlg = QDialog(self)
        dlg.setWindowTitle("选择资源")
        v = QVBoxLayout(dlg)
        lw = QListWidget()
        for rel in items:
            lw.addItem(rel)
        lw.setCurrentRow(0)
        v.addWidget(lw)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        if dlg.exec() == QDialog.Accepted and lw.currentItem():
            return lw.currentItem().text()
        return None

    # ============================================================
    # 步骤管理
    # ============================================================
    def _refresh_steps(self) -> None:
        self._step_list.clear()
        s = self._current_scene
        if s is None:
            return
        for i, st in enumerate(s.steps):
            self._step_list.addItem(f"{i + 1}. {st.label()}")

    def _on_step_selected(self, row: int) -> None:
        pass  # 仅用于高亮; 编辑通过按钮/双击触发

    def _add_step(self) -> None:
        if self._current_scene is None:
            QMessageBox.information(self, "提示", "请先选择一个场景。")
            return
        step = Step(type="dialogue", text="")
        sid = self._current_scene.id
        if StepEditDialog.edit(step, self.project, sid, self):
            self._current_scene.steps.append(step)
            # 可能新建了分支场景, 同步刷新场景列表 (内部会刷新步骤列表)
            self._refresh_scenes()
            self._step_list.setCurrentRow(len(self._current_scene.steps) - 1)
            self._mark_dirty()

    def _edit_step(self) -> None:
        s = self._current_scene
        if s is None:
            return
        row = self._step_list.currentRow()
        if row < 0 or row >= len(s.steps):
            return
        step = s.steps[row]
        if StepEditDialog.edit(step, self.project, s.id, self):
            # 可能新建了分支场景, 同步刷新场景列表 (内部会刷新步骤列表)
            self._refresh_scenes()
            self._step_list.setCurrentRow(row)
            self._mark_dirty()

    def _del_step(self) -> None:
        s = self._current_scene
        if s is None:
            return
        row = self._step_list.currentRow()
        if 0 <= row < len(s.steps):
            del s.steps[row]
            self._refresh_steps()
            self._mark_dirty()

    def _move_step(self, delta: int) -> None:
        s = self._current_scene
        if s is None:
            return
        row = self._step_list.currentRow()
        new = row + delta
        if 0 <= row < len(s.steps) and 0 <= new < len(s.steps):
            s.steps[row], s.steps[new] = s.steps[new], s.steps[row]
            self._refresh_steps()
            self._step_list.setCurrentRow(new)
            self._mark_dirty()

    # ============================================================
    # 运行 / 预览
    # ============================================================
    def _play_game(self) -> None:
        self._launch_player(start_scene_id=None)

    def _play_from_current(self) -> None:
        sid = self._current_scene.id if self._current_scene else None
        self._launch_player(start_scene_id=sid)

    def _launch_player(self, start_scene_id: Optional[str]) -> None:
        self._flush_scene_form()
        # 用临时文件播放 (避免修改原文件)
        tmp_dir = tempfile.mkdtemp(prefix="galpy_play_")
        # 把工程目录的资源软链/复制过去
        if self.project_dir and os.path.isdir(self.project_dir):
            import shutil
            for sub in os.listdir(self.project_dir):
                src = os.path.join(self.project_dir, sub)
                dst = os.path.join(tmp_dir, sub)
                if os.path.isdir(src):
                    try:
                        shutil.copytree(src, dst, dirs_exist_ok=True)
                    except Exception:
                        pass
                else:
                    try:
                        shutil.copy2(src, dst)
                    except Exception:
                        pass
        proj = self.project
        if start_scene_id:
            # 深拷贝一份并改起始场景, 避免影响原工程
            proj = Project.from_dict(self.project.to_dict())
            proj.start_scene = start_scene_id
        proj_path = os.path.join(tmp_dir, PROJECT_FILE_NAME)
        proj.save(proj_path)
        # 子进程运行, 释放编辑器
        try:
            subprocess.Popen(
                [sys.executable, "-m", "galpy", "play", proj_path],
                cwd=self._project_root(),
            )
        except Exception as e:
            QMessageBox.warning(self, "播放失败", str(e))

    def _project_root(self) -> str:
        """返回 galpy 包所在工程根 (用于子进程定位 main)。"""
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # ============================================================
    # 打包
    # ============================================================
    def _package_game(self) -> None:
        if not self.project_path:
            QMessageBox.information(self, "提示", "请先保存工程再打包。")
            return
        self._flush_scene_form()
        self.project.save(self.project_path)
        from ..packaging.packager import PackageDialog
        dlg = PackageDialog(self.project, self.project_path, self)
        dlg.exec()

    def _package_web(self) -> None:
        """打包为 Web 应用 (支持在线部署与容器化)。"""
        if not self.project_path:
            QMessageBox.information(self, "提示", "请先保存工程再打包。")
            return
        self._flush_scene_form()
        self.project.save(self.project_path)
        from ..packaging.web_packager import WebPackageDialog
        dlg = WebPackageDialog(self.project, self.project_path, self, initial_tab=1)
        dlg.exec()

    def _deploy_cloud(self) -> None:
        """云端在线直连部署 (Cloudflare / Vercel / Docker 容器)。"""
        if not self.project_path:
            QMessageBox.information(self, "提示", "请先保存工程再部署。")
            return
        self._flush_scene_form()
        self.project.save(self.project_path)
        from ..packaging.web_packager import WebPackageDialog
        dlg = WebPackageDialog(self.project, self.project_path, self, initial_tab=0)
        dlg.exec()

    def _preview_web(self) -> None:
        """在浏览器中即时预览: 后台启动 Flask 服务并打开浏览器。

        服务运行于守护线程, 编辑器关闭时自动结束。
        """
        if not self.project_path:
            QMessageBox.information(self, "提示", "请先保存工程再预览。")
            return
        # 防止重复启动多个服务
        if getattr(self, "_web_thread", None) is not None and self._web_thread.is_alive():
            QMessageBox.information(self, "已在运行",
                                    "Web 预览服务正在运行中。\n"
                                    "请勿重复启动。")
            return
        try:
            from ..web import run_server
        except ImportError:
            QMessageBox.critical(
                self, "缺少依赖",
                "Web 预览需要 Flask, 请先安装:\n\n    pip install flask"
            )
            return
        self._flush_scene_form()
        self.project.save(self.project_path)

        import threading
        try:
            self._web_thread = threading.Thread(
                target=run_server,
                args=(self.project_path,),
                kwargs={"host": "127.0.0.1", "port": 5000,
                        "open_browser": True},
                daemon=True,
            )
            self._web_thread.start()
            QMessageBox.information(
                self, "预览已启动",
                "Web 预览服务已启动, 浏览器即将打开:\n\n"
                "    http://127.0.0.1:5000/\n\n"
                "关闭编辑器时服务自动结束。"
            )
        except Exception as e:
            QMessageBox.critical(self, "预览失败", str(e))

    # ============================================================
    # 其它
    # ============================================================
    def _about(self) -> None:
        QMessageBox.about(
            self, tr("about_title", "关于 GalPy"),
            tr("about_content", "<h3>{app_name}</h3><p>纯 Python 实现的 Galgame 引擎</p><p>支持 文字 / 音频 / 视频 / 图片 渲染</p><p>可视化编辑 + PyInstaller 一键打包 (Windows 脱机)</p><p>Flask Web 服务器 + 浏览器游玩 + 云端在线部署</p>", app_name=APP_NAME)
        )

    def closeEvent(self, event) -> None:
        self._flush_scene_form()
        # 有未保存修改时: 提示保存 / 放弃 / 取消
        if self._dirty:
            ans = QMessageBox.question(
                self, "保存工程",
                f"工程「{self.project.title}」有未保存的修改, 是否保存?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            )
            if ans == QMessageBox.Cancel:
                event.ignore()
                return
            if ans == QMessageBox.Save:
                self._save_project()
                # 保存可能被取消 (如另存为对话框取消) 或失败: 仍脏则阻止关闭
                if self._dirty:
                    event.ignore()
                    return
        # 关闭编辑器时: 停止自动保存 + 停止所有预览音频
        try:
            self._auto_save_timer.stop()
        except Exception:
            pass
        try:
            self._audio.stop_all()
        except Exception:
            pass
        super().closeEvent(event)
