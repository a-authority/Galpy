"""资源浏览器: 导入 / 查看 / 删除工程资源 (图片 / 音频 / 视频)。"""
from __future__ import annotations

import os
import shutil
from typing import Optional

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from ..config import (
    ASSET_CATEGORIES, ASSETS_DIR_NAME, IMAGE_EXTS, AUDIO_EXTS, VIDEO_EXTS,
)
from ..i18n import get_asset_category_label, on_language_changed, tr
from ..model import Project

_EXT_TO_CATEGORY = {}
for _ext in IMAGE_EXTS:
    _EXT_TO_CATEGORY[_ext] = "backgrounds"
for _ext in AUDIO_EXTS:
    _EXT_TO_CATEGORY[_ext] = "sfx"  # 默认归类, 用户可改
for _ext in VIDEO_EXTS:
    _EXT_TO_CATEGORY[_ext] = "videos"


class AssetBrowser(QWidget):
    """工程素材资源管理器面板。"""

    assets_changed = Signal()

    def __init__(self, project: Project, project_dir: str, parent=None):
        super().__init__(parent)
        self.project = project
        self.project_dir = project_dir
        self._current_category = "backgrounds"

        self._title = QLabel()
        self._title.setStyleSheet("font-weight: bold; font-size: 14px; color: #cfd8e8;")

        # 分类切换下拉框
        self._category_combo = QComboBox()
        self._category_combo.currentIndexChanged.connect(self._on_category_changed)

        # 资源缩略图网格/列表
        self._list = QListWidget()
        self._list.setIconSize(QSize(72, 72))

        # 按钮 (采用现代层级样式)
        self._btn_import = QPushButton()
        self._btn_import.setObjectName("PrimaryBtn")
        self._btn_import.clicked.connect(self._import_files)

        self._btn_delete = QPushButton()
        self._btn_delete.setObjectName("DangerBtn")
        self._btn_delete.clicked.connect(self._delete_selected)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(8)
        lay.addWidget(self._title)
        lay.addWidget(self._category_combo)
        lay.addWidget(self._list, 1)

        row = QHBoxLayout()
        row.addWidget(self._btn_import, 1)
        row.addWidget(self._btn_delete)
        lay.addLayout(row)

        self.retranslate_ui()
        self._refresh()

        on_language_changed(lambda _: self.retranslate_ui())

    def retranslate_ui(self) -> None:
        """多语言文案即时刷新。"""
        self._title.setText(tr("dock_assets", "工程素材库"))
        self._btn_import.setText(tr("btn_import_asset", "导入文件…"))
        self._btn_delete.setText(tr("btn_delete_asset", "删除"))

        cur_cat = self._current_category
        self._category_combo.blockSignals(True)
        self._category_combo.clear()
        for cat in ASSET_CATEGORIES.keys():
            label = get_asset_category_label(cat)
            self._category_combo.addItem(f"{label} ({cat})", cat)
        idx = self._category_combo.findData(cur_cat)
        if idx >= 0:
            self._category_combo.setCurrentIndex(idx)
        self._category_combo.blockSignals(False)

    def set_project(self, project: Project, project_dir: str) -> None:
        self.project = project
        self.project_dir = project_dir
        self._refresh()

    def _on_category_changed(self) -> None:
        self._current_category = self._category_combo.currentData() or "backgrounds"
        self._refresh()

    def _refresh(self) -> None:
        self._list.clear()
        items = self.project.assets.get(self._current_category, [])
        for rel in items:
            display = os.path.basename(rel)
            item = QListWidgetItem(display)
            item.setToolTip(rel)
            item.setData(Qt.UserRole, rel)
            # 缩略图 (仅图片类)
            if self._current_category in ("backgrounds", "characters"):
                full = os.path.join(self.project_dir, rel) if not os.path.isabs(rel) else rel
                if os.path.exists(full):
                    pix = QPixmap(full)
                    if not pix.isNull():
                        item.setIcon(pix.scaled(72, 72, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self._list.addItem(item)

    def _import_files(self) -> None:
        cat = self._current_category
        if cat in ("backgrounds", "characters"):
            flt = f"{tr('cat_backgrounds', '图片')} (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;All Files (*.*)"
        elif cat in ("bgm", "voice", "sfx"):
            flt = f"{tr('cat_bgm', '音频')} (*.mp3 *.wav *.ogg *.flac *.m4a);;All Files (*.*)"
        else:
            flt = f"{tr('cat_videos', '视频')} (*.mp4 *.avi *.mkv *.mov *.webm);;All Files (*.*)"

        files, _ = QFileDialog.getOpenFileNames(self, tr("btn_import_asset", "导入文件"), "", flt)
        if not files:
            return
        dest_dir = os.path.join(self.project_dir, ASSETS_DIR_NAME, cat)
        os.makedirs(dest_dir, exist_ok=True)
        imported = 0
        for src in files:
            name = os.path.basename(src)
            dst = os.path.join(dest_dir, name)
            base, ext = os.path.splitext(name)
            i = 1
            while os.path.exists(dst):
                dst = os.path.join(dest_dir, f"{base}_{i}{ext}")
                i += 1
            try:
                shutil.copy2(src, dst)
            except Exception:
                continue
            rel = os.path.relpath(dst, self.project_dir).replace("\\", "/")
            self.project.add_asset(cat, rel)
            imported += 1
        self._refresh()
        if imported:
            self.assets_changed.emit()

    def _delete_selected(self) -> None:
        cat = self._current_category
        rows = self._list.selectedItems()
        if not rows:
            return
        names = "\n".join(it.text() for it in rows)
        title = tr("btn_delete_asset", "删除资源")
        prompt = f"{tr('confirm_delete_step', '确定删除选中的资源文件吗？')}\n\n{names}"
        if QMessageBox.question(self, title, prompt, QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        for item in rows:
            rel = item.data(Qt.UserRole)
            full = os.path.join(self.project_dir, rel) if not os.path.isabs(rel) else rel
            try:
                if os.path.exists(full):
                    os.remove(full)
            except OSError:
                pass
            if rel in self.project.assets.get(cat, []):
                self.project.assets[cat].remove(rel)
        self._refresh()
        self.assets_changed.emit()
