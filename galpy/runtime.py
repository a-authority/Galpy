"""应用启动辅助: 统一构造 QApplication、全局现代化样式与多语言及模式入口。

三种模式:
  - run_launcher : 启动菜单 (选择新建/打开/播放)
  - run_editor   : 可视化编辑器
  - run_player   : 游戏播放器
"""
from __future__ import annotations

import math
import os
import sys
from typing import Optional

from PySide6.QtCore import Qt, QPointF, QSize, QSettings
from PySide6.QtGui import QAction, QColor, QFont, QFontDatabase, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QPushButton

from .i18n import (
    get_language, set_language, get_effective_language, tr,
    on_language_changed,
)

_app: Optional[QApplication] = None

# 当前是否为浅色主题 (默认深色)。启动时由 _load_theme_pref 载入用户偏好。
_theme_light: bool = False


def _configure_highdpi() -> None:
    """在 QApplication 构造前打开 HiDPI 支持 (Qt6 部分已默认, 保险起见)。"""
    try:
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    except Exception:
        pass


def _resolve_chinese_font() -> str:
    """在系统中挑选一款可用的高质量字体。"""
    preferred = [
        "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI",
        "PingFang SC", "PingFang TC",
        "Noto Sans CJK SC", "Noto Sans SC",
        "Source Han Sans SC", "WenQuanYi Micro Hei",
        "Arial", "sans-serif",
    ]
    families = set(QFontDatabase.families())
    for name in preferred:
        if name in families:
            return name
    return ""


# ==============================================================================
# 主题 (浅色 / 深色) 管理
# ==============================================================================

def _load_theme_pref() -> bool:
    """从 QSettings 读取用户主题偏好; 默认深色 (False)。"""
    try:
        s = QSettings("GalPy", "GalPy")
        return bool(s.value("ui/light_theme", False, type=bool))
    except Exception:
        return False


def _save_theme_pref(light: bool) -> None:
    try:
        s = QSettings("GalPy", "GalPy")
        s.setValue("ui/light_theme", light)
    except Exception:
        pass


def is_light_theme() -> bool:
    """当前是否处于浅色主题。"""
    return _theme_light


def apply_theme(light: bool, persist: bool = True) -> None:
    """切换全局主题并即时刷新所有窗口样式。"""
    global _theme_light
    _theme_light = light
    app = _app or QApplication.instance()
    if app is not None:
        app.setStyleSheet(_LIGHT_QSS if light else _GLOBAL_QSS)
    if persist:
        _save_theme_pref(light)


def ensure_app() -> QApplication:
    """全局单例 QApplication, 附带高质量字体、现代统一风格与用户偏好。"""
    global _app, _theme_light
    _configure_highdpi()
    if _app is None:
        _app = QApplication.instance() or QApplication(sys.argv)
        _app.setApplicationName("GalPy")
        _app.setStyle("Fusion")

        main_font = _resolve_chinese_font()
        font = QFont()
        if main_font:
            font.setFamilies([main_font, "Segoe UI", "PingFang SC", "Microsoft YaHei", "sans-serif"])
        else:
            font.setFamilies(["Segoe UI", "Arial", "sans-serif"])
        font.setPointSize(10)
        _app.setFont(font)

        _theme_light = _load_theme_pref()
        _app.setStyleSheet(_LIGHT_QSS if _theme_light else _GLOBAL_QSS)
    return _app  # type: ignore[return-value]


# ==============================================================================
# 全局现代化 QSS 样式系统 (深色主题 / Dark Slate)
# ==============================================================================

_GLOBAL_QSS = """
/* ---- 全局基础配色 ---- */
QWidget {
    background: #171821;
    color: #e6edf3;
    font-size: 13px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
}

/* ---- 启动菜单窗口专用 ---- */
QLabel#AppTitle {
    font-size: 36px;
    font-weight: 800;
    color: #79a8ff;
    letter-spacing: 1px;
}
QLabel#AppSubtitle {
    font-size: 13px;
    color: #9aa3be;
    line-height: 1.5;
}

QPushButton#LauncherBtn {
    background: #202334;
    color: #e6edf3;
    border: 1px solid #333852;
    border-radius: 10px;
    font-size: 15px;
    font-weight: 500;
    text-align: left;
    padding: 0px 22px;
}
QPushButton#LauncherBtn:hover {
    background: #2b3047;
    border: 1px solid #4f78f6;
    color: #ffffff;
}
QPushButton#LauncherBtn:pressed {
    background: #1c1e2d;
}
QPushButton#QuitBtn {
    background: transparent;
    border: 1px solid transparent;
    text-align: center;
    color: #8c95a8;
    padding: 8px 16px;
}
QPushButton#QuitBtn:hover {
    background: rgba(255, 255, 255, 12);
    border: 1px solid #34384e;
    color: #f88e96;
}

/* ---- 统一 QPushButton 样式体系 ---- */
QPushButton {
    background: #25283a;
    color: #e6edf3;
    border: 1px solid #383d57;
    border-radius: 6px;
    padding: 6px 16px;
    min-height: 24px;
    font-weight: 500;
}
QPushButton:hover {
    background: #32374e;
    border: 1px solid #4f587d;
}
QPushButton:pressed {
    background: #1d1f2e;
}
QPushButton:disabled {
    background: #1a1c27;
    color: #555b72;
    border-color: #272a3a;
}

/* 主操作按钮 (Primary / Default) */
QPushButton#PrimaryBtn,
QPushButton[primary="true"],
QPushButton:default {
    background: #2954a3;
    border: 1px solid #3d6dd0;
    color: #ffffff;
    font-weight: 600;
}
QPushButton#PrimaryBtn:hover,
QPushButton[primary="true"]:hover,
QPushButton:default:hover {
    background: #3468c4;
    border: 1px solid #5684e6;
}
QPushButton#PrimaryBtn:pressed,
QPushButton[primary="true"]:pressed,
QPushButton:default:pressed {
    background: #1f4284;
}

/* 成功 / 运行按钮 (Success) */
QPushButton#SuccessBtn,
QPushButton[success="true"] {
    background: #238636;
    border: 1px solid #2ea043;
    color: #ffffff;
    font-weight: 600;
}
QPushButton#SuccessBtn:hover,
QPushButton[success="true"]:hover {
    background: #2ea043;
    border: 1px solid #3fb950;
}
QPushButton#SuccessBtn:pressed,
QPushButton[success="true"]:pressed {
    background: #196628;
}

/* 危险 / 终止按钮 (Danger) */
QPushButton#DangerBtn,
QPushButton[danger="true"] {
    background: #3e1f25;
    border: 1px solid #8b2830;
    color: #ff858d;
}
QPushButton#DangerBtn:hover,
QPushButton[danger="true"]:hover {
    background: #50232b;
    border: 1px solid #c93b48;
    color: #ffffff;
}
QPushButton#DangerBtn:pressed,
QPushButton[danger="true"]:pressed {
    background: #2d161a;
}

/* 顶部栏轻量功能按钮 (主题与语言切换) */
QPushButton#ThemeToggleBtn,
QPushButton#LangSelectBtn {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 3px 8px;
    color: #9aa3bd;
    font-size: 12px;
}
QPushButton#ThemeToggleBtn:hover,
QPushButton#LangSelectBtn:hover {
    background: rgba(255, 255, 255, 18);
    border: 1px solid #383d56;
    color: #ffffff;
}

/* ---- 输入与选择控件 (聚焦微发光) ---- */
QLineEdit {
    background: #181924;
    color: #e6edf3;
    border: 1px solid #32364c;
    border-radius: 6px;
    padding: 6px 10px;
    selection-background-color: #2954a3;
}
QLineEdit:hover {
    border: 1px solid #444b6a;
}
QLineEdit:focus {
    border: 1px solid #4f78f6;
    background: #1d1f2e;
}
QLineEdit:read-only {
    background: #14151e;
    color: #8c93a8;
}

QSpinBox {
    background: #181924;
    color: #e6edf3;
    border: 1px solid #32364c;
    border-radius: 6px;
    padding: 5px 10px;
}
QSpinBox:focus {
    border: 1px solid #4f78f6;
}

QTextEdit, QPlainTextEdit {
    background: #181924;
    color: #e6edf3;
    border: 1px solid #32364c;
    border-radius: 6px;
    padding: 6px;
    selection-background-color: #2954a3;
}
QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #4f78f6;
}

/* ---- 下拉框 QComboBox ---- */
QComboBox {
    background: #181924;
    color: #e6edf3;
    border: 1px solid #32364c;
    border-radius: 6px;
    padding: 6px 10px;
    min-height: 22px;
}
QComboBox:hover {
    border: 1px solid #444b6a;
}
QComboBox:focus {
    border: 1px solid #4f78f6;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #9aa3bd;
}
QComboBox QAbstractItemView {
    background: #1f212f;
    color: #e6edf3;
    selection-background-color: #2954a3;
    selection-color: #ffffff;
    border: 1px solid #373c56;
    border-radius: 6px;
    padding: 4px;
    outline: none;
}

/* ---- 列表与表格 ---- */
QListWidget, QListView, QTreeWidget, QTreeView {
    background: #1b1d28;
    color: #e6edf3;
    border: 1px solid #30344a;
    border-radius: 6px;
    selection-background-color: #273456;
    selection-color: #ffffff;
    outline: 0;
    padding: 2px;
}
QListWidget::item, QTreeWidget::item {
    border-radius: 4px;
    padding: 5px 8px;
    margin: 1px 0px;
}
QListWidget::item:hover, QTreeWidget::item:hover {
    background: #232738;
}
QListWidget::item:selected, QTreeWidget::item:selected {
    background: #2954a3;
    color: #ffffff;
}

QTableWidget, QTableView {
    background: #1b1d28;
    color: #e6edf3;
    gridline-color: #2e3247;
    border: 1px solid #30344a;
    border-radius: 6px;
    selection-background-color: #2954a3;
    selection-color: #ffffff;
}
QHeaderView::section {
    background: #202332;
    color: #cfd8e8;
    border: none;
    border-right: 1px solid #2e3247;
    border-bottom: 1px solid #2e3247;
    padding: 6px 8px;
    font-weight: 600;
}

/* ---- 分组框 QGroupBox ---- */
QGroupBox {
    color: #cfd8e8;
    font-weight: 600;
    border: 1px solid #30344a;
    border-radius: 6px;
    margin-top: 14px;
    padding-top: 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    background: #171821;
}

/* ---- 复选框与单选钮 ---- */
QCheckBox, QRadioButton {
    color: #e6edf3;
    spacing: 7px;
}
QCheckBox::indicator, QRadioButton::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #3a3f5c;
    border-radius: 4px;
    background: #1b1d28;
}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {
    border-color: #4f78f6;
}
QCheckBox::indicator:checked {
    background: #2954a3;
    border-color: #4f78f6;
}

/* ---- 选项卡 QTabWidget ---- */
QTabWidget::pane {
    border: 1px solid #30344a;
    border-radius: 6px;
    background: #1b1d28;
    top: -1px;
}
QTabBar::tab {
    background: #171821;
    color: #8c95a8;
    border: 1px solid #30344a;
    border-bottom: none;
    padding: 7px 18px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
    font-weight: 500;
}
QTabBar::tab:hover:!selected {
    background: #212433;
    color: #e6edf3;
}
QTabBar::tab:selected {
    background: #1b1d28;
    color: #79a8ff;
    border-bottom: 2px solid #4f78f6;
    font-weight: 600;
}

/* ---- 极简平滑滚动条 ---- */
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #34384e;
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover {
    background: #4f587d;
}
QScrollBar:horizontal {
    background: transparent;
    height: 8px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: #34384e;
    border-radius: 4px;
    min-width: 24px;
}
QScrollBar::handle:horizontal:hover {
    background: #4f587d;
}
QScrollBar::add-line, QScrollBar::sub-line {
    border: none;
    background: none;
    width: 0;
    height: 0;
}

/* ---- 菜单栏与弹出菜单 ---- */
QMenuBar {
    background: #14151d;
    color: #e6edf3;
    border-bottom: 1px solid #272a3a;
    padding: 2px 4px;
}
QMenuBar::item {
    background: transparent;
    padding: 5px 10px;
    border-radius: 4px;
}
QMenuBar::item:selected {
    background: #25283a;
    color: #ffffff;
}
QMenu {
    background: #1e202e;
    color: #e6edf3;
    border: 1px solid #353a54;
    border-radius: 8px;
    padding: 4px;
}
QMenu::item {
    padding: 6px 24px 6px 12px;
    border-radius: 4px;
}
QMenu::item:selected {
    background: #2954a3;
    color: #ffffff;
}
QMenu::separator {
    height: 1px;
    background: #2e3247;
    margin: 4px 6px;
}

/* ---- 工具栏与状态栏 ---- */
QToolBar {
    background: #171821;
    border-bottom: 1px solid #272a3a;
    spacing: 6px;
    padding: 4px 8px;
}
QToolBar QToolButton {
    background: transparent;
    color: #e6edf3;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 5px 10px;
    min-height: 22px;
    font-weight: 500;
}
QToolBar QToolButton:hover {
    background: #25283a;
    border: 1px solid #373c56;
}
QToolBar QToolButton:checked {
    background: #2954a3;
    border: 1px solid #4f78f6;
    color: #ffffff;
}
QStatusBar {
    background: #14151d;
    color: #8c95a8;
    border-top: 1px solid #272a3a;
}

/* ---- 停靠窗与分割条 ---- */
QDockWidget {
    color: #e6edf3;
    titlebar-close-icon: none;
}
QDockWidget::title {
    background: #1a1c27;
    color: #cfd8e8;
    font-weight: 600;
    padding: 6px 12px;
    border: 1px solid #2a2d3e;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}
QSplitter::handle {
    background: #232534;
}
QSplitter::handle:hover {
    background: #4f78f6;
}

/* ---- 对话框体系 ---- */
QDialog, QMessageBox, QInputDialog, QFileDialog {
    background: #171821;
    color: #e6edf3;
}
QMessageBox QLabel, QInputDialog QLabel, QFileDialog QLabel {
    color: #e6edf3;
}
"""


# ==============================================================================
# 全局现代化 QSS 样式系统 (浅色主题 / Light Modern)
# ==============================================================================

_LIGHT_QSS = """
/* ---- 全局基础配色 ---- */
QWidget {
    background: #f4f5f8;
    color: #1f232e;
    font-size: 13px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
}

/* ---- 启动菜单窗口专用 ---- */
QLabel#AppTitle {
    font-size: 36px;
    font-weight: 800;
    color: #2752b0;
    letter-spacing: 1px;
}
QLabel#AppSubtitle {
    font-size: 13px;
    color: #656d7f;
    line-height: 1.5;
}

QPushButton#LauncherBtn {
    background: #ffffff;
    color: #1f232e;
    border: 1px solid #d5dae5;
    border-radius: 10px;
    font-size: 15px;
    font-weight: 500;
    text-align: left;
    padding: 0px 22px;
}
QPushButton#LauncherBtn:hover {
    background: #f0f3fa;
    border: 1px solid #3b66d1;
    color: #2752b0;
}
QPushButton#LauncherBtn:pressed {
    background: #e4e8f2;
}
QPushButton#QuitBtn {
    background: transparent;
    border: 1px solid transparent;
    text-align: center;
    color: #656d7f;
    padding: 8px 16px;
}
QPushButton#QuitBtn:hover {
    background: rgba(0, 0, 0, 10);
    border: 1px solid #d5dae5;
    color: #c93b48;
}

/* ---- 统一 QPushButton 样式体系 ---- */
QPushButton {
    background: #ffffff;
    color: #1f232e;
    border: 1px solid #d5dae5;
    border-radius: 6px;
    padding: 6px 16px;
    min-height: 24px;
    font-weight: 500;
}
QPushButton:hover {
    background: #f4f6fa;
    border: 1px solid #b2bad0;
}
QPushButton:pressed {
    background: #e8ecf4;
}
QPushButton:disabled {
    background: #f0f2f6;
    color: #9aa1b2;
    border-color: #e0e3ea;
}

/* 主操作按钮 (Primary / Default) */
QPushButton#PrimaryBtn,
QPushButton[primary="true"],
QPushButton:default {
    background: #2d5ec9;
    border: 1px solid #234fae;
    color: #ffffff;
    font-weight: 600;
}
QPushButton#PrimaryBtn:hover,
QPushButton[primary="true"]:hover,
QPushButton:default:hover {
    background: #396de0;
    border: 1px solid #2c59c4;
}
QPushButton#PrimaryBtn:pressed,
QPushButton[primary="true"]:pressed,
QPushButton:default:pressed {
    background: #1e4599;
}

/* 成功 / 运行按钮 (Success) */
QPushButton#SuccessBtn,
QPushButton[success="true"] {
    background: #1f883d;
    border: 1px solid #1a7f37;
    color: #ffffff;
    font-weight: 600;
}
QPushButton#SuccessBtn:hover,
QPushButton[success="true"]:hover {
    background: #269a47;
}
QPushButton#SuccessBtn:pressed,
QPushButton[success="true"]:pressed {
    background: #17662c;
}

/* 危险 / 终止按钮 (Danger) */
QPushButton#DangerBtn,
QPushButton[danger="true"] {
    background: #ffebe9;
    border: 1px solid #ff8182;
    color: #cf222e;
}
QPushButton#DangerBtn:hover,
QPushButton[danger="true"]:hover {
    background: #ffdbdc;
    border: 1px solid #cf222e;
}
QPushButton#DangerBtn:pressed,
QPushButton[danger="true"]:pressed {
    background: #f8c9cb;
}

/* 顶部栏轻量功能按钮 (主题与语言切换) */
QPushButton#ThemeToggleBtn,
QPushButton#LangSelectBtn {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 3px 8px;
    color: #656d7f;
    font-size: 12px;
}
QPushButton#ThemeToggleBtn:hover,
QPushButton#LangSelectBtn:hover {
    background: rgba(0, 0, 0, 16);
    border: 1px solid #ccd2de;
    color: #1f232e;
}

/* ---- 输入与选择控件 ---- */
QLineEdit {
    background: #ffffff;
    color: #1f232e;
    border: 1px solid #d5dae5;
    border-radius: 6px;
    padding: 6px 10px;
    selection-background-color: #2d5ec9;
}
QLineEdit:hover {
    border: 1px solid #b2bad0;
}
QLineEdit:focus {
    border: 1px solid #2d5ec9;
    background: #ffffff;
}
QLineEdit:read-only {
    background: #f0f2f6;
    color: #656d7f;
}

QSpinBox {
    background: #ffffff;
    color: #1f232e;
    border: 1px solid #d5dae5;
    border-radius: 6px;
    padding: 5px 10px;
}
QSpinBox:focus {
    border: 1px solid #2d5ec9;
}

QTextEdit, QPlainTextEdit {
    background: #ffffff;
    color: #1f232e;
    border: 1px solid #d5dae5;
    border-radius: 6px;
    padding: 6px;
    selection-background-color: #2d5ec9;
}
QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #2d5ec9;
}

/* ---- 下拉框 QComboBox ---- */
QComboBox {
    background: #ffffff;
    color: #1f232e;
    border: 1px solid #d5dae5;
    border-radius: 6px;
    padding: 6px 10px;
    min-height: 22px;
}
QComboBox:hover {
    border: 1px solid #b2bad0;
}
QComboBox:focus {
    border: 1px solid #2d5ec9;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #656d7f;
}
QComboBox QAbstractItemView {
    background: #ffffff;
    color: #1f232e;
    selection-background-color: #2d5ec9;
    selection-color: #ffffff;
    border: 1px solid #d5dae5;
    border-radius: 6px;
    padding: 4px;
    outline: none;
}

/* ---- 列表与表格 ---- */
QListWidget, QListView, QTreeWidget, QTreeView {
    background: #ffffff;
    color: #1f232e;
    border: 1px solid #d5dae5;
    border-radius: 6px;
    selection-background-color: #e5edff;
    selection-color: #1f232e;
    outline: 0;
    padding: 2px;
}
QListWidget::item, QTreeWidget::item {
    border-radius: 4px;
    padding: 5px 8px;
    margin: 1px 0px;
}
QListWidget::item:hover, QTreeWidget::item:hover {
    background: #f0f3fa;
}
QListWidget::item:selected, QTreeWidget::item:selected {
    background: #2d5ec9;
    color: #ffffff;
}

QTableWidget, QTableView {
    background: #ffffff;
    color: #1f232e;
    gridline-color: #e4e7ef;
    border: 1px solid #d5dae5;
    border-radius: 6px;
    selection-background-color: #2d5ec9;
    selection-color: #ffffff;
}
QHeaderView::section {
    background: #edf1f7;
    color: #1f232e;
    border: none;
    border-right: 1px solid #d5dae5;
    border-bottom: 1px solid #d5dae5;
    padding: 6px 8px;
    font-weight: 600;
}

/* ---- 分组框 QGroupBox ---- */
QGroupBox {
    color: #1f232e;
    font-weight: 600;
    border: 1px solid #d5dae5;
    border-radius: 6px;
    margin-top: 14px;
    padding-top: 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    background: #f4f5f8;
}

/* ---- 复选框与单选钮 ---- */
QCheckBox, QRadioButton {
    color: #1f232e;
    spacing: 7px;
}
QCheckBox::indicator, QRadioButton::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #c0c6d6;
    border-radius: 4px;
    background: #ffffff;
}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {
    border-color: #2d5ec9;
}
QCheckBox::indicator:checked {
    background: #2d5ec9;
    border-color: #2d5ec9;
}

/* ---- 选项卡 QTabWidget ---- */
QTabWidget::pane {
    border: 1px solid #d5dae5;
    border-radius: 6px;
    background: #ffffff;
    top: -1px;
}
QTabBar::tab {
    background: #e8ecf4;
    color: #656d7f;
    border: 1px solid #d5dae5;
    border-bottom: none;
    padding: 7px 18px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
    font-weight: 500;
}
QTabBar::tab:hover:!selected {
    background: #f0f3fa;
    color: #1f232e;
}
QTabBar::tab:selected {
    background: #ffffff;
    color: #2752b0;
    border-bottom: 2px solid #2d5ec9;
    font-weight: 600;
}

/* ---- 极简平滑滚动条 ---- */
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #c8cedb;
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover {
    background: #9aa1b2;
}
QScrollBar:horizontal {
    background: transparent;
    height: 8px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: #c8cedb;
    border-radius: 4px;
    min-width: 24px;
}
QScrollBar::handle:horizontal:hover {
    background: #9aa1b2;
}
QScrollBar::add-line, QScrollBar::sub-line {
    border: none;
    background: none;
    width: 0;
    height: 0;
}

/* ---- 菜单栏与弹出菜单 ---- */
QMenuBar {
    background: #ffffff;
    color: #1f232e;
    border-bottom: 1px solid #d5dae5;
    padding: 2px 4px;
}
QMenuBar::item {
    background: transparent;
    padding: 5px 10px;
    border-radius: 4px;
}
QMenuBar::item:selected {
    background: #f0f3fa;
    color: #2752b0;
}
QMenu {
    background: #ffffff;
    color: #1f232e;
    border: 1px solid #d5dae5;
    border-radius: 8px;
    padding: 4px;
}
QMenu::item {
    padding: 6px 24px 6px 12px;
    border-radius: 4px;
}
QMenu::item:selected {
    background: #eef2fb;
    color: #2752b0;
}
QMenu::separator {
    height: 1px;
    background: #e4e7ef;
    margin: 4px 6px;
}

/* ---- 工具栏与状态栏 ---- */
QToolBar {
    background: #f9fafb;
    border-bottom: 1px solid #d5dae5;
    spacing: 6px;
    padding: 4px 8px;
}
QToolBar QToolButton {
    background: transparent;
    color: #1f232e;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 5px 10px;
    min-height: 22px;
    font-weight: 500;
}
QToolBar QToolButton:hover {
    background: #eef2fb;
    border: 1px solid #c8d3ee;
}
QToolBar QToolButton:checked {
    background: #2d5ec9;
    border: 1px solid #234fae;
    color: #ffffff;
}
QStatusBar {
    background: #edf1f7;
    color: #656d7f;
    border-top: 1px solid #d5dae5;
}

/* ---- 停靠窗与分割条 ---- */
QDockWidget {
    color: #1f232e;
    titlebar-close-icon: none;
}
QDockWidget::title {
    background: #ebf0f7;
    color: #1f232e;
    font-weight: 600;
    padding: 6px 12px;
    border: 1px solid #d5dae5;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}
QSplitter::handle {
    background: #d5dae5;
}
QSplitter::handle:hover {
    background: #2d5ec9;
}

/* ---- 对话框体系 ---- */
QDialog, QMessageBox, QInputDialog, QFileDialog {
    background: #f4f5f8;
    color: #1f232e;
}
QMessageBox QLabel, QInputDialog QLabel, QFileDialog QLabel {
    color: #1f232e;
}
"""


# ==============================================================================
# 图标绘制工具 (太阳 / 月亮 / 地球地球仪)
# ==============================================================================

def make_sun_pixmap(size: int = 18, color: str = "#e6edf3") -> QPixmap:
    """绘制太阳图标 (圆心 + 8 道光芒)。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    c = QColor(color)
    pen = QPen(c, max(1.0, size * 0.08))
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    cx = cy = size / 2.0
    inner = size * 0.30
    outer = size * 0.46
    for i in range(8):
        ang = i * math.pi / 4
        p.drawLine(
            QPointF(cx + math.cos(ang) * inner, cy + math.sin(ang) * inner),
            QPointF(cx + math.cos(ang) * outer, cy + math.sin(ang) * outer),
        )
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    p.drawEllipse(QPointF(cx, cy), size * 0.16, size * 0.16)
    p.end()
    return pm


def make_moon_pixmap(size: int = 18, color: str = "#e6edf3") -> QPixmap:
    """绘制月牙图标。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    c = QColor(color)
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    cx = cy = size / 2.0
    r = size * 0.34
    p.drawEllipse(QPointF(cx, cy), r, r)
    p.setCompositionMode(QPainter.CompositionMode_DestinationOut)
    p.drawEllipse(QPointF(cx + r * 0.55, cy - r * 0.30), r * 0.92, r * 0.92)
    p.end()
    return pm


def make_globe_pixmap(size: int = 18, color: str = "#e6edf3") -> QPixmap:
    """绘制现代极简地球仪/语言图标。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    c = QColor(color)
    pen = QPen(c, max(1.1, size * 0.08))
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)

    cx = cy = size / 2.0
    r = size * 0.40
    # 外圆
    p.drawEllipse(QPointF(cx, cy), r, r)
    # 赤道水平线
    p.drawLine(QPointF(cx - r, cy), QPointF(cx + r, cy))
    # 经线椭圆
    p.drawEllipse(QPointF(cx, cy), r * 0.48, r)
    p.end()
    return pm


# ==============================================================================
# UI 功能小部件: 主题切换按钮与语言选择按钮
# ==============================================================================

class ThemeToggleButton(QPushButton):
    """主题切换按钮: 太阳/月亮图标, 点击即时在浅色/深色模式间切换。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ThemeToggleBtn")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(36, 30)
        self.setFocusPolicy(Qt.NoFocus)
        self.clicked.connect(self._on_toggle)
        self.refresh_ui()
        on_language_changed(lambda _: self.refresh_ui())

    def _on_toggle(self) -> None:
        apply_theme(not is_light_theme())
        self.refresh_ui()

    def refresh_ui(self) -> None:
        light = is_light_theme()
        color = "#1f232e" if light else "#e6edf3"
        if light:
            self.setIcon(make_moon_pixmap(18, color))
        else:
            self.setIcon(make_sun_pixmap(18, color))
        self.setIconSize(QSize(18, 18))
        self.setToolTip(tr("tb_theme_tip", "切换浅色 / 深色主题"))


class LanguageSelectorButton(QPushButton):
    """多语言选择按钮: 携带地球仪图标, 点击弹出系统/中文/English选择菜单。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LangSelectBtn")
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFixedHeight(30)
        self.setMinimumWidth(80)

        # 构建下拉菜单
        self._menu = QMenu(self)
        self.setMenu(self._menu)
        self.clicked.connect(self.showMenu)

        self.refresh_ui()
        on_language_changed(lambda _: self.refresh_ui())

    def refresh_ui(self) -> None:
        light = is_light_theme()
        color = "#1f232e" if light else "#e6edf3"
        self.setIcon(make_globe_pixmap(18, color))
        self.setIconSize(QSize(18, 18))

        cur_pref = get_language()
        eff = get_effective_language()

        # 显示短标识
        badge = "中文" if eff == "zh_CN" else "EN"
        if cur_pref == "auto":
            badge += " (Auto)"
        self.setText(f" {badge}")
        self.setToolTip(tr("tb_lang_tip", "切换语言 (Chinese / English)"))

        # 重建菜单项
        self._menu.clear()
        a_auto = self._menu.addAction(tr("lang_auto", "🌐 跟随系统 (System Default)"))
        a_auto.setCheckable(True)
        a_auto.setChecked(cur_pref == "auto")
        a_auto.triggered.connect(lambda: set_language("auto"))

        self._menu.addSeparator()

        a_zh = self._menu.addAction(tr("lang_zh", "🇨🇳 简体中文 (Simplified Chinese)"))
        a_zh.setCheckable(True)
        a_zh.setChecked(cur_pref == "zh_CN")
        a_zh.triggered.connect(lambda: set_language("zh_CN"))

        a_en = self._menu.addAction(tr("lang_en", "🇺🇸 English (英文)"))
        a_en.setCheckable(True)
        a_en.setChecked(cur_pref == "en_US")
        a_en.triggered.connect(lambda: set_language("en_US"))


# ==============================================================================
# 各工作模式入口
# ==============================================================================

def run_player(project_path: str) -> int:
    app = ensure_app()
    from .model import Project
    from .engine.player import GamePlayer

    base = os.path.dirname(os.path.abspath(project_path))
    project = Project.load(project_path)
    player = GamePlayer(project, base)
    player.show()
    return app.exec()


def run_editor(project_path: Optional[str] = None) -> int:
    app = ensure_app()
    from .editor.main_window import EditorWindow

    win = EditorWindow(project_path)
    win.show()
    return app.exec()


def run_launcher() -> int:
    app = ensure_app()
    from .app import LauncherWindow

    win = LauncherWindow()
    win.show()
    return app.exec()
