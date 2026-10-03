"""启动菜单窗口: 图形化选择 新建 / 打开 / 播放 / 示例工程。

支持浅色/深色主题切换与中英文多语言切换 (默认跟随系统)。
"""
from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox,
    QPushButton, QVBoxLayout, QWidget,
)

from .config import APP_NAME, APP_VERSION, ASSETS_DIR_NAME, PROJECT_EXT, PROJECT_FILE_FILTER, PROJECT_FILE_NAME
from .i18n import get_effective_language, on_language_changed, tr
from .runtime import LanguageSelectorButton, ThemeToggleButton


class LauncherWindow(QWidget):
    """GalPy 启动菜单主窗口。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.resize(600, 480)

        # 标题与副标题
        self._title = QLabel(APP_NAME)
        self._title.setObjectName("AppTitle")
        self._title.setAlignment(Qt.AlignCenter)
        self._subtitle = QLabel()
        self._subtitle.setObjectName("AppSubtitle")
        self._subtitle.setAlignment(Qt.AlignCenter)

        # 菜单按钮
        self._btn_new = self._make_btn("", "")
        self._btn_new.clicked.connect(self._new_project)
        self._btn_open = self._make_btn("", "")
        self._btn_open.clicked.connect(self._open_project)
        self._btn_play = self._make_btn("", "")
        self._btn_play.clicked.connect(self._play_project)
        self._btn_demo = self._make_btn("", "")
        self._btn_demo.clicked.connect(self._new_demo)
        self._btn_quit = self._make_btn("", "")
        self._btn_quit.setObjectName("QuitBtn")
        self._btn_quit.clicked.connect(self.close)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(40, 24, 40, 28)
        lay.setSpacing(12)

        # 右上角: 多语言切换 + 浅色/深色主题切换
        top_row = QHBoxLayout()
        top_row.addStretch(1)
        self._lang_btn = LanguageSelectorButton(self)
        self._theme_btn = ThemeToggleButton(self)
        top_row.addWidget(self._lang_btn)
        top_row.addSpacing(6)
        top_row.addWidget(self._theme_btn)
        lay.addLayout(top_row)

        lay.addWidget(self._title)
        lay.addWidget(self._subtitle)
        lay.addSpacing(14)
        for b in (self._btn_new, self._btn_open, self._btn_play, self._btn_demo):
            lay.addWidget(b)
        lay.addStretch(1)
        lay.addWidget(self._btn_quit)

        self._refresh_texts()
        on_language_changed(lambda _: self._refresh_texts())

    def _refresh_texts(self) -> None:
        """刷新当前界面所有文本。"""
        self._subtitle.setText(tr("app_subtitle"))
        self._btn_new.setText(tr("launcher_new"))
        self._btn_new.setToolTip(tr("launcher_new_tip"))
        self._btn_open.setText(tr("launcher_open"))
        self._btn_open.setToolTip(tr("launcher_open_tip"))
        self._btn_play.setText(tr("launcher_play"))
        self._btn_play.setToolTip(tr("launcher_play_tip"))
        self._btn_demo.setText(tr("launcher_demo"))
        self._btn_demo.setToolTip(tr("launcher_demo_tip"))
        self._btn_quit.setText(tr("launcher_quit"))

    def _make_btn(self, text: str, tip: str) -> QPushButton:
        b = QPushButton(text)
        b.setObjectName("LauncherBtn")
        b.setMinimumHeight(52)
        b.setCursor(Qt.PointingHandCursor)
        if tip:
            b.setToolTip(tip)
        return b

    def _switch_to_editor(self, project_path: Optional[str]) -> None:
        from .editor.main_window import EditorWindow
        self._editor = EditorWindow(project_path)
        self._editor.show()
        self.close()

    def _switch_to_player(self, project_path: str) -> None:
        from .model import Project
        from .engine.player import GamePlayer
        base = os.path.dirname(os.path.abspath(project_path))
        try:
            project = Project.load(project_path)
        except Exception as e:
            QMessageBox.critical(self, tr("error"), f"{tr('error')}:\n{e}")
            return
        self._player = GamePlayer(project, base)
        self._player.show()
        self.close()

    def _new_project(self) -> None:
        # 1) 输入工程名称
        title, ok = QInputDialog.getText(
            self, tr("action_new"), tr("launcher_new_title_prompt"),
            text="MyGame" if tr("ok") == "OK" else "我的游戏"
        )
        if not ok:
            return
        title = title.strip() or ("MyGame" if tr("ok") == "OK" else "我的游戏")

        # 2) 选择上级目录
        parent_dir = QFileDialog.getExistingDirectory(self, tr("launcher_new_dir_prompt"))
        if not parent_dir:
            return

        project_dir = os.path.join(parent_dir, title + "Galpy")
        os.makedirs(project_dir, exist_ok=True)
        os.makedirs(os.path.join(project_dir, ASSETS_DIR_NAME), exist_ok=True)

        project_file = os.path.join(project_dir, title + PROJECT_EXT)

        from .model import Project
        proj = Project.empty(title)
        proj.save(project_file)
        self._switch_to_editor(project_file)

    def _open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("action_open"), "", PROJECT_FILE_FILTER
        )
        if path:
            self._switch_to_editor(path)

    def _play_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("launcher_play"), "", PROJECT_FILE_FILTER
        )
        if path:
            self._switch_to_player(path)

    def _new_demo(self) -> None:
        parent_dir = QFileDialog.getExistingDirectory(
            self, tr("launcher_demo")
        )
        if not parent_dir:
            return
        try:
            demo_title = "Demo_MorningSun" if get_effective_language() == "en_US" else "示例_晨光"
            project_dir = os.path.join(parent_dir, demo_title + "Galpy")
            os.makedirs(project_dir, exist_ok=True)
            from .demo import create_demo_project
            from .config import PROJECT_EXT
            project = create_demo_project(project_dir, demo_title)
            project_file = os.path.join(project_dir, demo_title + PROJECT_EXT)
            project.save(project_file)
            self._switch_to_editor(project_file)
        except Exception as e:
            QMessageBox.critical(self, tr("error"), f"{e}")
