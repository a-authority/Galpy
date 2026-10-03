"""游戏运行时播放器: 加载 Project 并渲染运行。

渲染层级 (由下到上):
  1. 背景图 (铺满, 保持比例)
  2. 角色立绘 (按 position 定位, 底部对齐)
  3. 对白框 / 名牌 / 文字 (带打字机效果)
  4. 选项按钮 (分支)
  5. 视频层 (整屏覆盖)

交互: 鼠标左键 / 空格 / 回车 推进; ESC 退出; 视频播放中点击可跳过。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QTimer, Signal, QUrl
from PySide6.QtGui import QColor, QFont, QPainter, QPalette, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QVBoxLayout, QWidget,
)

from ..config import CHARACTER_POSITIONS, POSITION_LABELS
from ..model import INTERACTIVE_TYPES, Project, Scene, Step
from .media import AudioManager
from .save_manager import SaveManager, SaveSlot, resolve_saves_dir


# 立绘横向锚点比例
_POSITION_X_RATIO = {
    "left": 0.20,
    "center_left": 0.36,
    "center": 0.50,
    "center_right": 0.64,
    "right": 0.80,
}


@dataclass
class CharacterSprite:
    """一个屏幕上的立绘实例, 带 alpha 用于淡入/淡出动画。

    state 取值:
      - "in":   正在淡入 (alpha 0 -> 1)
      - "idle": 完全显示 (alpha = 1)
      - "out":  正在淡出 (alpha -> 0), 完成后从屏幕移除
    """
    character: str            # 立绘资源相对路径 (作为身份标识)
    position: str             # 所在预设位置
    pixmap: QPixmap           # 原始立绘图
    alpha: float = 0.0
    state: str = "in"


class GamePlayer(QWidget):
    """游戏播放窗口。"""

    finished = Signal()  # 游戏正常结束或被关闭

    def __init__(self, project: Project, base_dir: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.project = project
        self.base_dir = base_dir  # project.json 所在目录 (用于解析相对资源路径)

        self.setWindowTitle(project.title or "GalPy Player")
        self.resize(max(project.width, 640), max(project.height, 360))
        self.setMinimumSize(640, 360)
        self.setStyleSheet("background: #0a0a14;")

        # ---- 运行状态 ----
        self._scene: Optional[Scene] = None
        self._step_index: int = -1
        # 立绘: 按 position 存放可见/淡入中的 sprite; _exiting 存放淡出中的 sprite
        self._characters: Dict[str, CharacterSprite] = {}
        self._exiting: List[CharacterSprite] = []
        self._bg_pixmap: Optional[QPixmap] = None
        self._waiting: bool = False                  # 等待用户点击推进
        self._video_playing: bool = False
        self._ended: bool = False

        # ---- 存档用: 跟踪当前画面/音频的"相对路径", 以便存档/恢复 ----
        self._cur_bg: str = ""
        self._cur_bgm: str = ""
        self._cur_characters: Dict[str, str] = {}    # position -> 立绘相对路径

        # ---- 界面模式: title(标题菜单) / playing(游玩) / menu(系统菜单) / slots(存档槽) ----
        self._mode: str = "title"

        # ---- 媒体 ----
        self.audio = AudioManager(self)

        # ---- 打字机 ----
        self._full_text: str = ""
        self._shown_text: str = ""
        self._text_index: int = 0
        self._typewriter = QTimer(self)
        self._typewriter.setInterval(28)
        self._typewriter.timeout.connect(self._tick_typewriter)

        # ---- 立绘淡入/淡出动画 ----
        self._fade_in_ms: int = 300
        self._fade_out_ms: int = 300
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)   # ~60fps
        self._anim_timer.timeout.connect(self._tick_animation)

        # ---- UI: 对白框 (QFrame 比 QWidget 更可靠地渲染半透明背景与子控件文字) ----
        self._dialogue_box = QFrame(self)
        self._dialogue_box.setObjectName("DialogueBox")
        self._dialogue_box.setFrameShape(QFrame.StyledPanel)
        self._dialogue_box.setStyleSheet(
            "QFrame#DialogueBox { background-color: rgba(0, 0, 0, 185); "
            "border: 1px solid rgba(100, 120, 180, 80); border-radius: 14px; }"
        )

        self._name_label = QLabel(self._dialogue_box)
        self._name_label.setObjectName("NamePlate")
        self._name_label.setStyleSheet(
            "background-color: rgba(80, 120, 200, 230); color: white; "
            "padding: 4px 16px; border-radius: 8px; font-size: 17px; font-weight: bold;"
        )
        self._name_label.hide()

        self._text_label = QLabel(self._dialogue_box)
        self._text_label.setObjectName("BodyText")
        self._text_label.setWordWrap(True)
        self._text_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self._text_label.setTextInteractionFlags(Qt.NoTextInteraction)
        # 关键: 用调色板强制设置文字颜色, 绕开 QSS 在半透明父控件下的渲染问题
        self._text_palette = self._text_label.palette()
        self._text_palette.setColor(QPalette.WindowText, QColor("#ffffff"))
        self._text_label.setPalette(self._text_palette)
        self._text_label.setStyleSheet(
            "QLabel { color: #ffffff; font-size: 20px; }"
        )

        self._hint_label = QLabel("点击 / 空格 继续", self._dialogue_box)
        self._hint_label.setObjectName("HintText")
        self._hint_label.setAlignment(Qt.AlignRight)
        self._hint_palette = self._hint_label.palette()
        self._hint_palette.setColor(QPalette.WindowText, QColor("#a0b4d8"))
        self._hint_label.setPalette(self._hint_palette)
        self._hint_label.setStyleSheet("QLabel { color: #a0b4d8; font-size: 12px; }")

        dl = QVBoxLayout(self._dialogue_box)
        dl.setContentsMargins(24, 16, 24, 14)
        dl.setSpacing(8)
        dl.addWidget(self._name_label)
        dl.addWidget(self._text_label, 1)
        dl.addWidget(self._hint_label, 0, Qt.AlignRight)

        # ---- UI: 选项 ----
        self._prompt_label = QLabel(self)
        self._prompt_palette = self._prompt_label.palette()
        self._prompt_palette.setColor(QPalette.WindowText, QColor("#ffffff"))
        self._prompt_label.setPalette(self._prompt_palette)
        self._prompt_label.setStyleSheet(
            "color: #ffffff; font-size: 22px; font-weight: bold; "
            "background-color: rgba(0,0,0,180); padding: 10px 18px; border-radius: 8px;"
        )
        self._prompt_label.setAlignment(Qt.AlignCenter)
        self._prompt_label.hide()

        self._choices_widget = QFrame(self)
        self._choices_widget.setFrameShape(QFrame.StyledPanel)
        self._choices_widget.setStyleSheet(
            "QFrame { background-color: rgba(0, 0, 0, 150); border-radius: 12px; }"
        )
        self._choices_layout = QVBoxLayout(self._choices_widget)
        self._choices_layout.setContentsMargins(10, 10, 10, 10)
        self._choices_layout.setSpacing(12)
        self._choices_widget.hide()

        # ---- UI: 视频 ----
        self._video_widget = QVideoWidget(self)
        self._video_widget.hide()
        self._video_player = QMediaPlayer(self)
        self._video_audio = QAudioOutput(self)
        self._video_player.setAudioOutput(self._video_audio)
        self._video_player.setVideoOutput(self._video_widget)
        self._video_player.mediaStatusChanged.connect(self._on_video_status)

        # ---- UI: 结束 ----
        self._end_widget: Optional[QWidget] = None

        # 注: 文字颜色全部通过 setPalette + setStyleSheet 编程式设置,
        # 不再依赖顶层 QSS, 避免半透明父控件下 QSS 不生效的问题.

        # ---- 存档管理 ----
        saves_dir = resolve_saves_dir(self.base_dir, project.title)
        self.saves = SaveManager(saves_dir)

        # ---- UI: 标题菜单 / 系统菜单 / 存档槽 (覆盖层) ----
        self._slot_mode: str = "save"            # "save" / "load"
        self._slot_buttons: List[QPushButton] = []
        self._build_title_widget()
        self._build_system_menu_widget()
        self._build_slot_widget()
        self._build_quick_save_btn()

        # ---- 启动: 显示标题菜单 (开始/继续/加载/退出) ----
        QTimer.singleShot(0, self._show_title_menu)

    # ============================================================
    # 覆盖层 UI 构建 (标题菜单 / 系统菜单 / 存档槽)
    # ============================================================
    def _menu_btn(self, text: str, parent: QWidget) -> QPushButton:
        btn = QPushButton(text, parent)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(
            "QPushButton { background-color: rgba(30, 40, 70, 220); color: #ffffff; "
            "border: 1px solid #5577bb; border-radius: 8px; "
            "padding: 10px 22px; font-size: 17px; min-width: 220px; }"
            "QPushButton:hover { background-color: rgba(70, 100, 170, 240); "
            "border: 1px solid #aac4ff; }"
            "QPushButton:disabled { background-color: rgba(40, 42, 54, 180); "
            "color: #6a6f85; border: 1px solid #3a3f5c; }"
        )
        # 调色板双保险: 强制按钮文字为亮色
        pl = btn.palette()
        pl.setColor(QPalette.ButtonText, QColor("#ffffff"))
        btn.setPalette(pl)
        return btn

    def _overlay_title_label(self, text: str, parent: QWidget, size: int = 40) -> QLabel:
        lbl = QLabel(text, parent)
        lbl.setAlignment(Qt.AlignCenter)
        pl = lbl.palette()
        pl.setColor(QPalette.WindowText, QColor("#eef2ff"))
        lbl.setPalette(pl)
        lbl.setStyleSheet(f"color: #eef2ff; font-size: {size}px; font-weight: bold;")
        return lbl

    def _build_title_widget(self) -> None:
        self._title_widget = QFrame(self)
        self._title_widget.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(self._title_widget)
        lay.setAlignment(Qt.AlignCenter)
        self._title_label = self._overlay_title_label(self.project.title or "GalPy",
                                                      self._title_widget, size=44)
        sub_lbl = QLabel("— GalPy —", self._title_widget)
        sub_lbl.setAlignment(Qt.AlignCenter)
        sp = sub_lbl.palette()
        sp.setColor(QPalette.WindowText, QColor("#9aa3bd"))
        sub_lbl.setPalette(sp)
        sub_lbl.setStyleSheet("color: #9aa3bd; font-size: 14px;")
        self._btn_new_game = self._menu_btn("▶  开始游戏", self._title_widget)
        self._btn_continue = self._menu_btn("↻  继续游戏", self._title_widget)
        self._btn_load = self._menu_btn("📂  加载存档", self._title_widget)
        self._btn_quit_title = self._menu_btn("✕  退出", self._title_widget)
        self._btn_new_game.clicked.connect(self._start_new_game)
        self._btn_continue.clicked.connect(self._continue_game)
        self._btn_load.clicked.connect(lambda: self._show_slots("load", "title"))
        self._btn_quit_title.clicked.connect(self.close)
        lay.addStretch(1)
        lay.addWidget(self._title_label, 0, Qt.AlignCenter)
        lay.addWidget(sub_lbl, 0, Qt.AlignCenter)
        lay.addSpacing(28)
        for b in (self._btn_new_game, self._btn_continue, self._btn_load, self._btn_quit_title):
            lay.addWidget(b, 0, Qt.AlignCenter)
        lay.addStretch(1)
        self._title_widget.hide()

    def _build_system_menu_widget(self) -> None:
        self._menu_widget = QFrame(self)
        self._menu_widget.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(self._menu_widget)
        lay.setAlignment(Qt.AlignCenter)
        hdr = self._overlay_title_label("系统菜单", self._menu_widget, size=28)
        b_save = self._menu_btn("💾  保存进度", self._menu_widget)
        b_load = self._menu_btn("📂  读取进度", self._menu_widget)
        b_title = self._menu_btn("🏠  返回标题", self._menu_widget)
        b_quit = self._menu_btn("✕  退出游戏", self._menu_widget)
        b_resume = self._menu_btn("▶  返回游戏", self._menu_widget)
        b_save.clicked.connect(lambda: self._show_slots("save", "menu"))
        b_load.clicked.connect(lambda: self._show_slots("load", "menu"))
        b_title.clicked.connect(self._back_to_title)
        b_quit.clicked.connect(self.close)
        b_resume.clicked.connect(self._resume_game)
        lay.addStretch(1)
        lay.addWidget(hdr, 0, Qt.AlignCenter)
        lay.addSpacing(20)
        for b in (b_save, b_load, b_title, b_quit, b_resume):
            lay.addWidget(b, 0, Qt.AlignCenter)
        lay.addStretch(1)
        self._menu_widget.hide()

    def _build_slot_widget(self) -> None:
        self._slot_widget = QFrame(self)
        self._slot_widget.setStyleSheet("background: transparent;")
        outer = QVBoxLayout(self._slot_widget)
        outer.setAlignment(Qt.AlignCenter)
        self._slot_header = self._overlay_title_label("存档", self._slot_widget, size=26)
        grid = QGridLayout()
        grid.setSpacing(10)
        for i in range(9):
            btn = QPushButton(self._slot_widget)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setMinimumSize(230, 96)
            # 不透明背景 + 高对比文字, 避免在半透明覆盖层上文字看不清
            btn.setStyleSheet(
                "QPushButton { background-color: #2a3458; color: #f4f7ff; "
                "border: 1px solid #5577bb; border-radius: 8px; "
                "padding: 8px 12px; font-size: 15px; text-align: left; }"
                "QPushButton:hover { background-color: #3d5a99; "
                "border: 1px solid #aac4ff; color: #ffffff; }"
            )
            # 调色板双保险: 强制按钮文字为亮色 (绕开全局 QSS 对 QPushButton 颜色的覆盖)
            pl = btn.palette()
            pl.setColor(QPalette.ButtonText, QColor("#f4f7ff"))
            btn.setPalette(pl)
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            idx = i + 1
            btn.clicked.connect(lambda _checked=False, n=idx: self._on_slot_clicked(n))
            btn.customContextMenuRequested.connect(
                lambda _pos=None, n=idx: self._delete_slot(n)
            )
            grid.addWidget(btn, i // 3, i % 3)
            self._slot_buttons.append(btn)
        b_back = self._menu_btn("←  返回", self._slot_widget)
        b_back.clicked.connect(self._close_slots)
        outer.addStretch(1)
        outer.addWidget(self._slot_header, 0, Qt.AlignCenter)
        outer.addSpacing(16)
        outer.addLayout(grid, 1)
        outer.addSpacing(16)
        outer.addWidget(b_back, 0, Qt.AlignCenter)
        outer.addStretch(1)
        self._slot_widget.hide()

    def _build_quick_save_btn(self) -> None:
        """游玩中右上角的浮动"存档"按钮 — 提供显式的保存入口 (无需按 Esc 进菜单)。
        点击后打开存档槽界面 (mode=save, 返回到 playing)。"""
        self._quick_save_btn = QPushButton("💾 存档", self)
        self._quick_save_btn.setCursor(Qt.PointingHandCursor)
        self._quick_save_btn.setStyleSheet(
            "QPushButton { background-color: rgba(30, 40, 70, 200); color: #f4f7ff; "
            "border: 1px solid #5577bb; border-radius: 8px; "
            "padding: 6px 14px; font-size: 14px; }"
            "QPushButton:hover { background-color: rgba(70, 100, 170, 240); "
            "border: 1px solid #aac4ff; color: #ffffff; }"
        )
        pl = self._quick_save_btn.palette()
        pl.setColor(QPalette.ButtonText, QColor("#f4f7ff"))
        self._quick_save_btn.setPalette(pl)
        self._quick_save_btn.clicked.connect(
            lambda: self._show_slots("save", "playing")
        )
        self._quick_save_btn.hide()

    # ============================================================
    # 资源解析
    # ============================================================
    def _resolve(self, rel_path: str) -> str:
        """把工程内相对路径解析为绝对路径; 不存在则返回空串。"""
        if not rel_path:
            return ""
        if os.path.isabs(rel_path):
            return rel_path if os.path.exists(rel_path) else ""
        full = os.path.join(self.base_dir, rel_path)
        return full if os.path.exists(full) else ""

    def _load_pixmap(self, rel_path: str) -> Optional[QPixmap]:
        full = self._resolve(rel_path)
        if not full:
            return None
        pix = QPixmap(full)
        return pix if not pix.isNull() else None

    # ============================================================
    # 标题菜单 / 系统菜单 / 存档槽 (模式切换)
    # ============================================================
    def _hide_all_overlays(self) -> None:
        for w in (self._title_widget, self._menu_widget, self._slot_widget):
            w.hide()
        self._quick_save_btn.hide()
        if self._end_widget is not None:
            self._end_widget.hide()

    def _show_title_menu(self) -> None:
        """显示标题菜单 (开始/继续/加载/退出)。
        使用封面场景的背景 / BGM / 标题文字。"""
        self._mode = "title"
        self._ended = False
        self._waiting = False
        self._video_playing = False
        self._typewriter.stop()
        self._anim_timer.stop()
        self.audio.stop_all()
        self._dialogue_box.hide()
        self._choices_widget.hide()
        self._prompt_label.hide()
        self._video_widget.hide()
        # 封面场景: 背景图 / BGM / 标题文字
        cover = self.project.cover_scene()
        if cover is not None:
            self._cur_bg = cover.background
            self._bg_pixmap = self._load_pixmap(cover.background) if cover.background else None
            self._cur_bgm = cover.bgm
            if cover.bgm:
                self.audio.play_bgm(self._resolve(cover.bgm))
            self._title_label.setText(cover.name or self.project.title or "GalPy")
        else:
            self._cur_bg = ""
            self._bg_pixmap = None
            self._cur_bgm = ""
            self._title_label.setText(self.project.title or "GalPy")
        # 继续游戏按钮: 仅当存在自动存档时可用
        self._btn_continue.setEnabled(self.saves.has_auto())
        self._quick_save_btn.hide()
        self._title_widget.setGeometry(self.rect())
        self._title_widget.show()
        self._title_widget.raise_()
        self.update()

    def _start_new_game(self) -> None:
        """从头开始: 清空运行状态, 进入起始场景 (跳过封面场景)。"""
        self._hide_all_overlays()
        self._mode = "playing"
        self._ended = False
        self._waiting = False
        self._cur_bg = ""
        self._cur_bgm = ""
        self._cur_characters.clear()
        self._characters.clear()
        self._exiting.clear()
        self._bg_pixmap = None
        self.audio.stop_all()
        # 起始场景: 若指向封面 (或为空), 改用第一个非封面场景
        cover = self.project.cover_scene()
        start_id = self.project.start_scene
        if not start_id or (cover is not None and start_id == cover.id):
            first_game = next((s.id for s in self.project.scenes if not s.is_cover), "")
            start_id = first_game
        if start_id and self.project.get_scene(start_id):
            self._goto_scene(start_id)
            self._quick_save_btn.show()
            self._quick_save_btn.raise_()
        else:
            self._show_end()

    def _continue_game(self) -> None:
        """从上次离开的位置继续 (自动存档)。"""
        slot = self.saves.load_auto()
        if slot is None:
            QMessageBox.information(self, "无续玩记录", "没有找到上次的自动存档。")
            return
        self._hide_all_overlays()
        self._restore_state(slot)

    def _show_system_menu(self) -> None:
        """游玩中按 Esc: 暂停并显示系统菜单。"""
        if self._ended:
            return
        self._mode = "menu"
        self._typewriter.stop()
        self.audio.stop_voice()
        self._quick_save_btn.hide()
        self._menu_widget.setGeometry(self.rect())
        self._menu_widget.show()
        self._menu_widget.raise_()
        self.update()

    def _resume_game(self) -> None:
        """从系统菜单返回游戏。"""
        self._menu_widget.hide()
        self._mode = "playing"
        self._quick_save_btn.show()
        self._quick_save_btn.raise_()
        # 若对白文字未打完, 继续打字
        if self._waiting and self._text_index < len(self._full_text):
            self._typewriter.start()
        self.update()

    def _back_to_title(self) -> None:
        """从系统菜单返回标题菜单 (会丢失当前未保存进度, 但自动存档已保留)。"""
        self._auto_save()
        self._menu_widget.hide()
        self._show_title_menu()
        self.update()

    def _show_slots(self, mode: str, return_to: str) -> None:
        """显示存档槽网格。mode='save' 写入 / 'load' 读取。
        return_to: 'title' / 'menu' / 'playing' — 关闭存档槽后回到哪里。"""
        self._slot_mode = mode
        self._slot_return = return_to
        self._slot_header.setText("保存进度" if mode == "save" else "读取进度")
        self._refresh_slot_buttons()
        # 隐藏来源覆盖层
        if return_to == "title":
            self._title_widget.hide()
        elif return_to == "menu":
            self._menu_widget.hide()
        self._quick_save_btn.hide()
        self._mode = "slots"
        self._slot_widget.setGeometry(self.rect())
        self._slot_widget.show()
        self._slot_widget.raise_()
        self.update()

    def _refresh_slot_buttons(self) -> None:
        slots = self.saves.list_slots()
        for i, btn in enumerate(self._slot_buttons):
            sl = slots[i] if i < len(slots) else None
            if sl is None:
                btn.setText(f"槽位 {i + 1}\n— 空 —")
            else:
                btn.setText(f"槽位 {i + 1}\n{sl.label or '(无描述)'}\n{sl.timestamp}")

    def _on_slot_clicked(self, index: int) -> None:
        if self._slot_mode == "save":
            slot = self._capture_state()
            try:
                self.saves.save_slot(index, slot)
            except Exception as e:
                QMessageBox.warning(self, "保存失败", str(e))
                return
            self._refresh_slot_buttons()
            QMessageBox.information(self, "已保存", f"已保存到槽位 {index}。")
            self._close_slots()
        else:  # load
            slot = self.saves.load_slot(index)
            if slot is None:
                QMessageBox.information(self, "空槽位", f"槽位 {index} 没有存档。")
                return
            self._slot_widget.hide()
            self._restore_state(slot)

    def _delete_slot(self, index: int) -> None:
        slot = self.saves.load_slot(index)
        if slot is None:
            return
        if QMessageBox.question(
            self, "删除存档", f"确定删除槽位 {index} 的存档吗?",
            QMessageBox.Yes | QMessageBox.No,
        ) == QMessageBox.Yes:
            self.saves.delete_slot(index)
            self._refresh_slot_buttons()

    def _close_slots(self) -> None:
        """从存档槽界面返回 (到标题 / 系统菜单 / 游戏)。"""
        self._slot_widget.hide()
        ret = getattr(self, "_slot_return", "menu")
        if ret == "title" or self._scene is None:
            self._show_title_menu()
        elif ret == "playing":
            self._mode = "playing"
            self._quick_save_btn.show()
            self._quick_save_btn.raise_()
            if self._waiting and self._text_index < len(self._full_text):
                self._typewriter.start()
            self.update()
        else:  # menu
            self._mode = "menu"
            self._menu_widget.show()
            self._menu_widget.raise_()
            self.update()

    # ============================================================
    # 存档: 捕获 / 恢复
    # ============================================================
    def _save_label(self) -> str:
        if not self._scene:
            return ""
        if 0 <= self._step_index < len(self._scene.steps):
            return f"{self._scene.name}  #{self._step_index + 1}"
        return self._scene.name

    def _capture_state(self) -> SaveSlot:
        """把当前运行状态打包为一份存档。"""
        return SaveSlot(
            scene_id=self._scene.id if self._scene else "",
            step_index=max(0, self._step_index),
            background=self._cur_bg,
            bgm=self._cur_bgm,
            characters={pos: rel for pos, rel in self._cur_characters.items() if rel},
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            label=self._save_label(),
            title=self.project.title,
        )

    def _auto_save(self) -> None:
        """把当前位置写入自动存档 (续玩用)。仅在游玩中且有有效场景时保存。"""
        if self._mode != "playing" or self._scene is None:
            return
        if self._step_index < 0:
            return
        try:
            self.saves.save_auto(self._capture_state())
        except Exception:
            pass  # 存档失败不应中断游戏

    def _restore_state(self, slot: SaveSlot) -> None:
        """从存档恢复: 重建画面/音频/BGM, 从存档步骤重新展示。"""
        scene = self.project.get_scene(slot.scene_id)
        if scene is None:
            QMessageBox.warning(self, "无法读取存档",
                                "存档指向的场景已不存在 (可能已被删除)。")
            self._show_title_menu()
            return
        self._scene = scene
        self._step_index = max(0, slot.step_index)
        self._ended = False
        self._video_playing = False

        # 恢复背景
        self._cur_bg = slot.background
        self._bg_pixmap = self._load_pixmap(slot.background) if slot.background else None

        # 恢复立绘 (直接显示, 不带淡入)
        self._characters.clear()
        self._exiting.clear()
        self._cur_characters = {pos: rel for pos, rel in slot.characters.items() if rel}
        for pos, rel in self._cur_characters.items():
            pix = self._load_pixmap(rel)
            if pix:
                self._characters[pos] = CharacterSprite(
                    character=rel, position=pos, pixmap=pix,
                    alpha=1.0, state="idle",
                )

        # 恢复 BGM
        self._cur_bgm = slot.bgm
        self.audio.stop_all()
        if slot.bgm:
            self.audio.play_bgm(self._resolve(slot.bgm))

        # 隐藏所有覆盖层, 进入播放
        self._hide_all_overlays()
        self._mode = "playing"
        self._dialogue_box.hide()
        self._choices_widget.hide()
        self._prompt_label.hide()
        self._video_widget.hide()
        self._quick_save_btn.show()
        self._quick_save_btn.raise_()
        self.update()

        # 重新执行当前步骤 (重显对白 / 选项)
        if 0 <= self._step_index < len(scene.steps):
            self._execute_step(scene.steps[self._step_index])
        else:
            self._next_step()

    # ============================================================
    # 流程推进
    # ============================================================
    def _goto_scene(self, scene_id: str) -> None:
        scene = self.project.get_scene(scene_id)
        if scene is None:
            self._show_end()
            return
        self._scene = scene
        self._step_index = -1
        # 场景级背景 / BGM
        if scene.background:
            self._apply_bg(scene.background)
        if scene.bgm:
            self._apply_bgm(scene.bgm)
        self._next_step()

    def _next_step(self) -> None:
        if self._ended or self._scene is None:
            return
        self._step_index += 1
        steps = self._scene.steps
        if self._step_index >= len(steps):
            # 场景走完且无显式跳转: 自动进入下一个"顶级场景"。
            # 分支场景 (有 parent_scene) 只能由选项 next / goto 显式进入,
            # 自动推进时一律跳过 —— 否则会出现"选了分支A, 演完后却自动
            # 进入未选的分支B"的问题。若后续没有顶级场景则结束游戏。
            idx = self.project.scene_index(self._scene.id)
            nxt = None
            for i in range(idx + 1, len(self.project.scenes)):
                if not self.project.scenes[i].parent_scene:
                    nxt = self.project.scenes[i]
                    break
            if nxt is not None:
                self._goto_scene(nxt.id)
            else:
                self._show_end()
            return
        self._execute_step(steps[self._step_index])

    def _execute_step(self, step: Step) -> None:
        t = step.type
        if t == "dialogue":
            self._show_dialogue(step, narration=False)
        elif t == "narration":
            self._show_dialogue(step, narration=True)
        elif t == "choice":
            self._show_choice(step)
        elif t == "video":
            self._play_video(step)
        elif t == "bg_change":
            self._apply_bg(step.background)
            self._auto_advance()
        elif t == "audio_change":
            self._apply_audio_change(step)
            self._auto_advance()
        elif t == "character_exit":
            self._apply_character_exit(step)
            self._auto_advance()
        elif t == "goto":
            self._goto_scene(step.next)
        elif t == "end":
            self._show_end()

    def _auto_advance(self) -> None:
        """非交互步骤立即推进 (用 queued 调用避免深递归)。"""
        QTimer.singleShot(0, self._next_step)

    # ============================================================
    # 媒体应用
    # ============================================================
    def _apply_bg(self, rel_path: str) -> None:
        self._cur_bg = rel_path or ""
        if rel_path:
            self._bg_pixmap = self._load_pixmap(rel_path)
        else:
            self._bg_pixmap = None
        self.update()

    def _apply_bgm(self, rel_path: str) -> None:
        self._cur_bgm = rel_path or ""
        self.audio.play_bgm(self._resolve(rel_path))

    def _play_sfx(self, rel_path: str) -> None:
        self.audio.play_sfx(self._resolve(rel_path))

    def _apply_audio_change(self, step: Step) -> None:
        """切换音频: 按 audio_category (bgm/sfx/voice) + audio_action (play/stop) 执行。"""
        cat = step.audio_category or "bgm"
        act = step.audio_action or "play"
        if cat == "bgm":
            if act == "stop":
                self.audio.stop_bgm()
                self._cur_bgm = ""
            else:
                self._cur_bgm = step.audio_file or ""
                self.audio.play_bgm(self._resolve(step.audio_file))
        elif cat == "sfx":
            if act == "stop":
                self.audio.stop_sfx()
            else:
                self.audio.play_sfx(self._resolve(step.audio_file))
        elif cat == "voice":
            if act == "stop":
                self.audio.stop_voice()
            else:
                self.audio.play_voice(self._resolve(step.audio_file))

    def _apply_character_exit(self, step: Step) -> None:
        """立绘离场: 优先按 exit_character 清除指定立绘 (无论它在哪个位置),
        否则按 exit_position 清除 (兼容旧工程)。被清除的立绘会淡出后再消失。"""
        if step.exit_character:
            # 清除指定角色: 扫描所有位置, 命中即淡出
            target = step.exit_character
            for pos, sp in list(self._characters.items()):
                if sp.character == target:
                    sp.state = "out"
                    self._exiting.append(sp)
                    del self._characters[pos]
                    self._cur_characters.pop(pos, None)
        else:
            pos = step.exit_position or "all"
            if pos == "all":
                for sp in self._characters.values():
                    sp.state = "out"
                    self._exiting.append(sp)
                self._characters.clear()
                self._cur_characters.clear()
            else:
                sp = self._characters.pop(pos, None)
                if sp is not None:
                    sp.state = "out"
                    self._exiting.append(sp)
                    self._cur_characters.pop(pos, None)
        if self._exiting:
            self._start_anim()
        self.update()

    # ============================================================
    # 立绘放置 / 动画
    # ============================================================
    def _place_character(self, rel_path: str, position: str, pixmap: QPixmap) -> None:
        """在指定位置放置立绘, 带淡入动画。

        - 同一角色已在同位置: 仅刷新立绘 (表情切换), 不重新淡入;
        - 同一角色在其他位置: 旧位置淡出 (表现为角色"移动");
        - 该位置被其他角色占用: 旧角色淡出, 新角色淡入 (交叉淡入淡出)。
        """
        existing = self._characters.get(position)
        if existing is not None and existing.character == rel_path:
            # 同角色同位置: 只更新图, 保持当前显示状态
            existing.pixmap = pixmap
            return

        # 同角色在其他位置: 移到淡出队列 (让旧位置淡出)
        for pos, sp in list(self._characters.items()):
            if pos != position and sp.character == rel_path:
                sp.state = "out"
                self._exiting.append(sp)
                del self._characters[pos]
                self._cur_characters.pop(pos, None)

        # 该位置上的旧不同角色: 淡出
        if existing is not None:
            existing.state = "out"
            self._exiting.append(existing)
            self._characters.pop(position, None)
            self._cur_characters.pop(position, None)

        # 新立绘淡入
        self._characters[position] = CharacterSprite(
            character=rel_path, position=position, pixmap=pixmap,
            alpha=0.0, state="in",
        )
        self._cur_characters[position] = rel_path
        self._start_anim()

    def _start_anim(self) -> None:
        if not self._anim_timer.isActive():
            self._anim_timer.start()

    def _tick_animation(self) -> None:
        """驱动所有立绘的淡入/淡出; 无活动动画时自动停止定时器。"""
        interval = self._anim_timer.interval()
        delta_in = interval / self._fade_in_ms
        delta_out = interval / self._fade_out_ms
        active = False

        # 淡入中
        for sp in self._characters.values():
            if sp.state == "in":
                sp.alpha = min(1.0, sp.alpha + delta_in)
                if sp.alpha >= 1.0:
                    sp.alpha = 1.0
                    sp.state = "idle"
                else:
                    active = True

        # 淡出中: alpha 归零后剔除
        still: List[CharacterSprite] = []
        for sp in self._exiting:
            sp.alpha -= delta_out
            if sp.alpha > 0:
                active = True
                still.append(sp)
        self._exiting = still

        self.update()
        if not active:
            self._anim_timer.stop()

    # ============================================================
    # 对白 / 旁白
    # ============================================================
    def _show_dialogue(self, step: Step, narration: bool) -> None:
        # 立绘 (带淡入)
        if step.character:
            pos = step.position if step.position in _POSITION_X_RATIO else "left"
            pix = self._load_pixmap(step.character)
            if pix:
                self._place_character(step.character, pos, pix)
        self.update()

        # 语音
        self.audio.play_voice(self._resolve(step.voice))

        # 名牌
        if narration or not step.speaker:
            self._name_label.hide()
        else:
            self._name_label.setText(step.speaker)
            self._name_label.show()

        # 文字 + 打字机
        self._full_text = step.text or ""
        self._shown_text = ""
        self._text_index = 0
        self._text_label.setText("")
        self._dialogue_box.show()
        self._dialogue_box.raise_()
        self._waiting = True
        if self._full_text:
            self._typewriter.start()
        else:
            self._hint_label.show()
        # 到达可停留的交互步骤: 自动存档 (续玩用)
        self._auto_save()

    def _tick_typewriter(self) -> None:
        if self._text_index < len(self._full_text):
            self._shown_text += self._full_text[self._text_index]
            self._text_index += 1
            self._text_label.setText(self._shown_text)
        else:
            self._typewriter.stop()

    # ============================================================
    # 选项分支
    # ============================================================
    def _show_choice(self, step: Step) -> None:
        self._dialogue_box.hide()
        # 清空旧按钮
        while self._choices_layout.count():
            item = self._choices_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if step.prompt:
            self._prompt_label.setText(step.prompt)
            self._prompt_label.show()
        else:
            self._prompt_label.hide()

        for opt in step.options:
            btn = QPushButton(opt.text or "(空选项)", self._choices_widget)
            btn.setObjectName("ChoiceButton")
            btn.setCursor(Qt.PointingHandCursor)
            btn_pl = btn.palette()
            btn_pl.setColor(QPalette.ButtonText, QColor("#ffffff"))
            btn.setPalette(btn_pl)
            btn.setStyleSheet(
                "QPushButton { background-color: rgba(30, 40, 70, 220); color: #ffffff; "
                "border: 1px solid #5577bb; border-radius: 8px; padding: 12px 20px; font-size: 18px; }"
                "QPushButton:hover { background-color: rgba(70, 100, 170, 240); "
                "border: 1px solid #aac4ff; }"
            )
            next_id = opt.next
            btn.clicked.connect(lambda _checked=False, n=next_id: self._on_choice(n))
            self._choices_layout.addWidget(btn)

        self._choices_widget.show()
        self._choices_widget.raise_()
        self._prompt_label.raise_()
        self._reposition()
        # 到达选项 (可停留): 自动存档
        self._auto_save()

    def _on_choice(self, next_id: str) -> None:
        self._choices_widget.hide()
        self._prompt_label.hide()
        if next_id:
            self._goto_scene(next_id)
        else:
            self._next_step()

    # ============================================================
    # 视频
    # ============================================================
    def _play_video(self, step: Step) -> None:
        path = self._resolve(step.source)
        if not path:
            # 无视频源, 直接跳过
            self._auto_advance()
            return
        self._video_playing = True
        self._video_widget.show()
        self._video_widget.raise_()
        self._video_widget.setFullScreen(False)
        self._reposition()
        self._video_player.setSource(QUrl.fromLocalFile(path))
        self._video_player.play()

    def _on_video_status(self, status: QMediaPlayer.MediaStatus) -> None:
        if status == QMediaPlayer.EndOfMedia and self._video_playing:
            self._stop_video()
            self._next_step()

    def _stop_video(self) -> None:
        self._video_player.stop()
        self._video_player.setSource(QUrl())
        self._video_widget.hide()
        self._video_playing = False

    # ============================================================
    # 结束
    # ============================================================
    def _show_end(self) -> None:
        self._ended = True
        self._waiting = False
        self._video_playing = False
        self._mode = "title"
        self._anim_timer.stop()
        self._exiting.clear()
        self._characters.clear()
        self._cur_bg = ""
        self._cur_bgm = ""
        self._cur_characters.clear()
        self._dialogue_box.hide()
        self._choices_widget.hide()
        self._prompt_label.hide()
        self._video_widget.hide()
        self._quick_save_btn.hide()
        self.audio.stop_all()
        self.update()

        # 销毁旧的结束页 (若有) 再重建
        if self._end_widget is not None:
            self._end_widget.hide()
            self._end_widget.deleteLater()
        self._end_widget = QWidget(self)
        self._end_widget.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(self._end_widget)
        lay.setAlignment(Qt.AlignCenter)
        end_label = QLabel("— 终 —", self._end_widget)
        end_label.setObjectName("EndText")
        end_label.setAlignment(Qt.AlignCenter)
        end_pl = end_label.palette()
        end_pl.setColor(QPalette.WindowText, QColor("#ffffff"))
        end_label.setPalette(end_pl)
        end_label.setStyleSheet("color: #ffffff; font-size: 44px; font-weight: bold;")
        sub = QLabel(f"《{self.project.title}》", self._end_widget)
        sub_pl = sub.palette()
        sub_pl.setColor(QPalette.WindowText, QColor("#cfd8e8"))
        sub.setPalette(sub_pl)
        sub.setStyleSheet("color: #cfd8e8; font-size: 18px;")
        sub.setAlignment(Qt.AlignCenter)
        btn = QPushButton("返回标题", self._end_widget)
        btn.setObjectName("EndButton")
        btn.setCursor(Qt.PointingHandCursor)
        btn_pl = btn.palette()
        btn_pl.setColor(QPalette.ButtonText, QColor("#ffffff"))
        btn.setPalette(btn_pl)
        btn.setStyleSheet(
            "QPushButton { background-color: rgba(80, 120, 200, 230); color: #ffffff; "
            "border-radius: 8px; padding: 8px 24px; font-size: 16px; }"
        )
        btn.clicked.connect(self._on_end_close)
        lay.addStretch(1)
        lay.addWidget(end_label, 0, Qt.AlignCenter)
        lay.addWidget(sub, 0, Qt.AlignCenter)
        lay.addSpacing(20)
        lay.addWidget(btn, 0, Qt.AlignCenter)
        lay.addStretch(1)
        self._end_widget.setGeometry(self.rect())
        self._end_widget.show()
        self._end_widget.raise_()
        self.finished.emit()

    def _on_end_close(self) -> None:
        # 通关后返回标题菜单 (而非直接退出), 便于重玩 / 读档
        if self._end_widget is not None:
            self._end_widget.hide()
            self._end_widget.deleteLater()
            self._end_widget = None
        self._show_title_menu()

    # ============================================================
    # 用户输入
    # ============================================================
    def _advance(self) -> None:
        # 仅在游玩中响应推进; 标题/系统菜单/存档界面下忽略
        if self._mode != "playing":
            return
        if self._ended:
            return
        if self._video_playing:
            self._stop_video()
            self._next_step()
            return
        if not self._waiting:
            return  # 正在显示选项, 必须点击具体选项
        if self._typewriter.isActive():
            # 立即显示完整文字
            self._typewriter.stop()
            self._shown_text = self._full_text
            self._text_index = len(self._full_text)
            self._text_label.setText(self._shown_text)
            return
        # 推进到下一步
        self._waiting = False
        self.audio.stop_voice()
        self._next_step()

    def mousePressEvent(self, event) -> None:
        if self._mode != "playing":
            return
        if event.button() == Qt.LeftButton:
            self._advance()

    def keyPressEvent(self, event) -> None:
        k = event.key()
        if k == Qt.Key_Escape:
            # Esc: 游玩中打开系统菜单; 在菜单中再按 Esc 则返回游戏/标题
            if self._mode == "playing":
                self._show_system_menu()
            elif self._mode == "menu":
                self._resume_game()
            elif self._mode == "slots":
                self._close_slots()
            return
        if self._mode != "playing":
            return
        if k in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self._advance()
        elif k == Qt.Key_F11:
            # 切换全屏
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()

    # ============================================================
    # 绘制 / 布局
    # ============================================================
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect()

        # 背景
        if self._bg_pixmap and not self._bg_pixmap.isNull():
            scaled = self._bg_pixmap.scaled(
                rect.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )
            x = (rect.width() - scaled.width()) // 2
            y = (rect.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        else:
            painter.fillRect(rect, QColor(12, 14, 26))

        # 标题/系统菜单/存档槽 模式: 绘制半透明深色覆盖层 (替代子控件 stylesheet 背景)
        if self._mode in ("title", "menu", "slots") and not self._ended:
            painter.fillRect(rect, QColor(6, 8, 18, 200))

        # 结束页覆盖
        if self._ended and self._end_widget is not None:
            painter.fillRect(rect, QColor(0, 0, 0, 210))

        # 角色立绘 (含淡入/淡出: _characters 可见/淡入, _exiting 淡出)
        for sp in list(self._characters.values()) + list(self._exiting):
            if sp.pixmap is None or sp.pixmap.isNull():
                continue
            painter.setOpacity(max(0.0, min(1.0, sp.alpha)))
            self._draw_character(painter, sp.position, sp.pixmap, rect)
        painter.setOpacity(1.0)

        painter.end()

    def _draw_character(self, painter: QPainter, pos: str, pix: QPixmap, rect) -> None:
        target_h = int(rect.height() * 0.88)
        scaled = pix.scaledToHeight(target_h, Qt.SmoothTransformation)
        if scaled.isNull():
            return
        ratio = _POSITION_X_RATIO.get(pos, 0.5)
        cx = int(rect.width() * ratio)
        x = cx - scaled.width() // 2
        y = rect.height() - scaled.height()
        # 略微限制不超出左右
        x = max(0, min(x, rect.width() - scaled.width()))
        painter.drawPixmap(x, y, scaled)

    def resizeEvent(self, event) -> None:
        self._reposition()
        super().resizeEvent(event)

    def _reposition(self) -> None:
        w, h = self.width(), self.height()
        margin = int(w * 0.04)
        box_h = int(h * 0.30)
        self._dialogue_box.setGeometry(
            margin, h - box_h - margin, w - 2 * margin, box_h
        )

        # 选项居中
        cw = min(int(w * 0.55), 520)
        ch = int(h * 0.55)
        self._choices_widget.setGeometry((w - cw) // 2, int(h * 0.22), cw, ch)

        # 提示语在选项上方
        if self._prompt_label.isVisible():
            pw = min(int(w * 0.7), 700)
            ph = 60
            self._prompt_label.setGeometry((w - pw) // 2, int(h * 0.14), pw, ph)

        # 视频整屏
        self._video_widget.setGeometry(0, 0, w, h)

        if self._end_widget is not None:
            self._end_widget.setGeometry(self.rect())

        # 覆盖层 (标题/系统菜单/存档槽) 整屏铺满
        for wgt in (self._title_widget, self._menu_widget, self._slot_widget):
            if wgt.isVisible():
                wgt.setGeometry(self.rect())

        # 浮动存档按钮: 右上角 (游玩中可见)
        if self._quick_save_btn.isVisible():
            self._quick_save_btn.adjustSize()
            qsw = self._quick_save_btn.width()
            qsh = self._quick_save_btn.height()
            self._quick_save_btn.move(w - qsw - margin // 2, margin // 2)
            self._quick_save_btn.raise_()

    def closeEvent(self, event) -> None:
        # 关闭前把当前位置写入自动存档 (续玩用)
        self._auto_save()
        self.audio.stop_all()
        self._typewriter.stop()
        self._anim_timer.stop()
        self._stop_video()
        self.finished.emit()
        super().closeEvent(event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.update()  # 确保首次显示时立即绘制背景与覆盖层
