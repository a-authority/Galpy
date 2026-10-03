"""步骤编辑对话框: 根据 step.type 显示对应字段的编辑表单，支持多语言与现代化按钮。"""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from ..config import CHARACTER_POSITIONS, POSITION_LABELS
from ..i18n import (
    get_audio_action_label, get_audio_category_label, get_position_label,
    get_step_type_label, tr,
)
from ..model import (
    AUDIO_ACTIONS, AUDIO_CATEGORIES, ChoiceOption, Project, STEP_TYPES, Scene,
    Step,
)


class AssetPicker(QWidget):
    """从工程某分类资源中下拉选择一个相对路径 (或留空)。"""

    def __init__(self, project: Project, category: str, parent=None):
        super().__init__(parent)
        self.project = project
        self.category = category
        self._combo = QComboBox()
        self._combo.setMinimumWidth(220)
        self._combo.addItem(tr("none", "(无)"), "")
        for rel in project.assets.get(category, []):
            self._combo.addItem(rel, rel)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._combo)

    def value(self) -> str:
        return self._combo.currentData() or ""

    def set_value(self, val: str) -> None:
        idx = self._combo.findData(val)
        self._combo.setCurrentIndex(idx if idx >= 0 else 0)

    def reload_category(self, category: str) -> None:
        """切换资源分类并重建下拉列表 (保留当前值若仍存在)。"""
        cur = self.value()
        self.category = category
        self._combo.blockSignals(True)
        self._combo.clear()
        self._combo.addItem(tr("none", "(无)"), "")
        for rel in self.project.assets.get(category, []):
            self._combo.addItem(rel, rel)
        idx = self._combo.findData(cur)
        self._combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._combo.blockSignals(False)


class StepEditDialog(QDialog):
    """编辑单个 Step。根据类型动态切换可见字段。"""

    def __init__(self, step: Step, project: Project, current_scene_id: str = "", parent=None):
        super().__init__(parent)
        self.step = step
        self.project = project
        self._current_scene_id = current_scene_id or ""
        self._created_scenes: List[Scene] = []
        self.setWindowTitle(f"{tr('step_dlg_title')} - {get_step_type_label(step.type)}")
        self.setMinimumWidth(560)
        self.setMinimumHeight(300)
        self._initing = True

        # ---- 类型选择 ----
        self._type_combo = QComboBox()
        for t in STEP_TYPES.keys():
            self._type_combo.addItem(f"{get_step_type_label(t)} ({t})", t)
        self._type_combo.currentIndexChanged.connect(self._rebuild_form)

        # ---- 字段控件 ----
        self._speaker = QLineEdit()
        self._text = QTextEdit()
        self._text.setMaximumHeight(100)
        self._voice = AssetPicker(project, "voice")
        self._character = AssetPicker(project, "characters")

        self._position = QComboBox()
        for p in CHARACTER_POSITIONS:
            self._position.addItem(get_position_label(p), p)

        self._background = AssetPicker(project, "backgrounds")
        self._bgm = AssetPicker(project, "bgm")
        self._source = AssetPicker(project, "videos")
        self._prompt = QLineEdit()
        self._options_widget = self._build_options_widget()
        self._next = QComboBox()

        # --- 音频切换 (audio_change) ---
        self._audio_category = QComboBox()
        for cat in AUDIO_CATEGORIES.keys():
            self._audio_category.addItem(get_audio_category_label(cat), cat)

        self._audio_action = QComboBox()
        for act in AUDIO_ACTIONS.keys():
            self._audio_action.addItem(get_audio_action_label(act), act)

        self._audio_file = AssetPicker(project, "bgm")
        self._audio_category.currentIndexChanged.connect(self._on_audio_category_changed)
        self._audio_action.currentIndexChanged.connect(self._rebuild_form)

        # --- 立绘离场 (character_exit) ---
        self._exit_mode = QComboBox()
        self._exit_mode.addItem(tr("exit_all", "全部立绘"), "all")
        self._exit_mode.addItem(tr("exit_specific", "指定立绘"), "character")
        self._exit_mode.currentIndexChanged.connect(self._rebuild_form)
        self._exit_character = AssetPicker(project, "characters")

        # ---- 根布局 ----
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(16, 16, 16, 14)
        self._root.setSpacing(12)

        type_row = QHBoxLayout()
        type_row.setSpacing(10)
        lbl_type = QLabel(tr("step_type_label", "步骤类型:"))
        lbl_type.setStyleSheet("font-weight: 600;")
        type_row.addWidget(lbl_type)
        type_row.addWidget(self._type_combo, 1)
        self._root.addLayout(type_row)

        self._form_host = QWidget(self)
        self._root.addWidget(self._form_host, 1)

        self._options_widget.hide()
        self._root.addWidget(self._options_widget)

        self._buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_ok = self._buttons.button(QDialogButtonBox.Ok)
        btn_cancel = self._buttons.button(QDialogButtonBox.Cancel)
        if btn_ok:
            btn_ok.setText(tr("ok", "确定"))
            btn_ok.setObjectName("PrimaryBtn")
        if btn_cancel:
            btn_cancel.setText(tr("cancel", "取消"))

        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        self._root.addWidget(self._buttons)

        self._load_from_step()
        self._populate_next_combo()
        self._initing = False
        self._rebuild_form()

    # ------------------------------------------------------------
    def _build_options_widget(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lbl = QLabel(tr("options_label", "选项分支列表:"))
        lbl.setStyleSheet("font-weight: 600;")
        lay.addWidget(lbl)

        self._opt_list = QListWidget()
        self._opt_list.setMaximumHeight(130)
        lay.addWidget(self._opt_list)

        row = QHBoxLayout()
        b_add = QPushButton(tr("btn_add_option", "+ 新增选项"))
        b_add.setObjectName("PrimaryBtn")
        b_edit = QPushButton(tr("edit", "编辑"))
        b_del = QPushButton(tr("delete", "删除"))
        b_del.setObjectName("DangerBtn")

        b_add.clicked.connect(self._add_option)
        b_edit.clicked.connect(self._edit_option)
        b_del.clicked.connect(self._del_option)

        row.addWidget(b_add)
        row.addWidget(b_edit)
        row.addWidget(b_del)
        row.addStretch(1)
        lay.addLayout(row)
        return w

    def _scene_combo_label(self, s: Scene) -> str:
        depth = self.project.scene_depth(s.id)
        prefix = ("    " * depth + "└ ") if depth > 0 else ""
        return f"{prefix}{s.name} ({s.id})"

    def _populate_next_combo(self) -> None:
        self._next.blockSignals(True)
        self._next.clear()
        self._next.addItem(f"({tr('continue_next', '继续下一步')})", "")
        for s in self.project.gameplay_scenes():
            self._next.addItem(self._scene_combo_label(s), s.id)
        self._next.blockSignals(False)

    def _load_from_step(self) -> None:
        self._type_combo.blockSignals(True)
        idx = self._type_combo.findData(self.step.type)
        self._type_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._type_combo.blockSignals(False)
        self._speaker.setText(self.step.speaker)
        self._text.setPlainText(self.step.text)
        self._voice.set_value(self.step.voice)
        self._character.set_value(self.step.character)
        pos_idx = self._position.findData(self.step.position or "left")
        self._position.setCurrentIndex(pos_idx if pos_idx >= 0 else 0)
        self._background.set_value(self.step.background)
        self._bgm.set_value(self.step.bgm)
        self._source.set_value(self.step.source)
        self._prompt.setText(self.step.prompt)

        cat_idx = self._audio_category.findData(self.step.audio_category or "bgm")
        self._audio_category.setCurrentIndex(cat_idx if cat_idx >= 0 else 0)
        act_idx = self._audio_action.findData(self.step.audio_action or "play")
        self._audio_action.setCurrentIndex(act_idx if act_idx >= 0 else 0)

        self._audio_file.reload_category(self.step.audio_category or "bgm")
        self._audio_file.set_value(self.step.audio_file)

        if self.step.exit_character:
            mode_idx = self._exit_mode.findData("character")
            self._exit_mode.setCurrentIndex(mode_idx if mode_idx >= 0 else 0)
        else:
            all_idx = self._exit_mode.findData("all")
            self._exit_mode.setCurrentIndex(all_idx if all_idx >= 0 else 0)
        self._exit_character.set_value(self.step.exit_character)

        self._opt_list.clear()
        for opt in self.step.options:
            QListWidgetItem(f"{opt.text}  ->  {opt.next or tr('continue_next', '下一步')}", self._opt_list)
        self._opt_items: List[ChoiceOption] = list(self.step.options)

    def _on_audio_category_changed(self) -> None:
        cat = self._audio_category.currentData()
        if cat:
            self._audio_file.reload_category(cat)

    # ------------------------------------------------------------
    def _rebuild_form(self) -> None:
        if self._initing:
            return

        t = self._type_combo.currentData()

        reclaim = [
            self._speaker, self._text, self._voice, self._character,
            self._position, self._background, self._bgm,
            self._audio_category, self._audio_action, self._audio_file,
            self._exit_mode, self._exit_character,
            self._source, self._prompt, self._next,
        ]
        for w in reclaim:
            w.setParent(self)
            w.hide()

        old = self._form_host.layout()
        if old is not None:
            QWidget().setLayout(old)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFormAlignment(Qt.AlignTop)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        def add(label: str, widget: QWidget) -> None:
            widget.setParent(self._form_host)
            widget.show()
            form.addRow(label, widget)

        if t == "dialogue":
            add(tr("speaker_label", "说话角色:"), self._speaker)
            add(tr("dialogue_text_label", "台词内容:"), self._text)
            add(tr("voice_label", "配音音频:"), self._voice)
            add(tr("character_label", "登场立绘:"), self._character)
            add(tr("position_label", "显示位置:"), self._position)
        elif t == "narration":
            add(tr("dialogue_text_label", "旁白文字:"), self._text)
        elif t == "choice":
            add(tr("prompt_label", "分支提示语:"), self._prompt)
        elif t == "video":
            add(tr("video_label", "视频文件:"), self._source)
        elif t == "bg_change":
            add(tr("bg_label", "背景图:"), self._background)
        elif t == "audio_change":
            add(tr("audio_cat_label", "音频类别:"), self._audio_category)
            add(tr("audio_action_label", "执行动作:"), self._audio_action)
            if self._audio_action.currentData() == "play":
                add(tr("cat_bgm", "音频文件:"), self._audio_file)
        elif t == "character_exit":
            add(tr("exit_mode_label", "清除方式:"), self._exit_mode)
            if self._exit_mode.currentData() == "character":
                add(tr("exit_character_label", "清除立绘:"), self._exit_character)
        elif t == "goto":
            add(tr("target_scene_label", "目标场景:"), self._next)

        self._form_host.setLayout(form)
        self._options_widget.setVisible(t == "choice")
        self.updateGeometry()
        self._root.activate()

    # ---- 选项编辑 ----
    def _add_option(self) -> None:
        opt = ChoiceOption(text=tr("new_option", "新选项"), next="")
        if self._edit_option_dialog(opt):
            self._opt_items.append(opt)
            self._refresh_opt_list()

    def _edit_option(self) -> None:
        row = self._opt_list.currentRow()
        if 0 <= row < len(self._opt_items):
            if self._edit_option_dialog(self._opt_items[row]):
                self._refresh_opt_list()

    def _del_option(self) -> None:
        row = self._opt_list.currentRow()
        if 0 <= row < len(self._opt_items):
            del self._opt_items[row]
            self._refresh_opt_list()

    def _edit_option_dialog(self, opt: ChoiceOption) -> bool:
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("edit_option_title", "编辑分支选项"))
        dlg.resize(460, 180)
        form = QFormLayout(dlg)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        text_edit = QLineEdit(opt.text)
        next_combo = QComboBox()
        next_combo.addItem(f"({tr('continue_next', '继续下一步')})", "")
        for s in self.project.gameplay_scenes():
            next_combo.addItem(self._scene_combo_label(s), s.id)
        idx = next_combo.findData(opt.next)
        next_combo.setCurrentIndex(idx if idx >= 0 else 0)

        b_new_scene = QPushButton(tr("btn_add_scene", "+ 新建场景"))
        b_new_scene.setObjectName("PrimaryBtn")
        b_new_scene.setToolTip(tr("btn_new_scene_tip", "创建新场景作为本选项的分支目标"))
        b_new_scene.clicked.connect(lambda: self._create_branch_scene(next_combo))

        next_row = QHBoxLayout()
        next_row.setContentsMargins(0, 0, 0, 0)
        next_row.addWidget(next_combo, 1)
        next_row.addWidget(b_new_scene)

        form.addRow(tr("opt_text_header", "选项文字:"), text_edit)
        form.addRow(tr("opt_next_header", "跳转场景:"), next_row)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_ok = bb.button(QDialogButtonBox.Ok)
        btn_cancel = bb.button(QDialogButtonBox.Cancel)
        if btn_ok:
            btn_ok.setText(tr("ok", "确定"))
            btn_ok.setObjectName("PrimaryBtn")
        if btn_cancel:
            btn_cancel.setText(tr("cancel", "取消"))

        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        form.addRow(bb)

        if dlg.exec() == QDialog.Accepted:
            opt.text = text_edit.text()
            opt.next = next_combo.currentData() or ""
            return True
        return False

    def _create_branch_scene(self, combo: QComboBox) -> None:
        if not self._current_scene_id:
            QMessageBox.information(
                self, tr("warning"),
                tr("no_current_scene", "未选定当前场景，无法创建关联分支。")
            )
            return
        default_name = f"{tr('branch_scene', '分支场景')} {len(self._created_scenes) + 1}"
        name, ok = QInputDialog.getText(
            self, tr("btn_add_scene"), tr("scene_name_label"), text=default_name
        )
        if not ok:
            return
        name = name.strip() or default_name
        scene = Scene(name=name)
        self.project.add_branch_scene(self._current_scene_id, scene)
        self._created_scenes.append(scene)

        combo.blockSignals(True)
        combo.clear()
        combo.addItem(f"({tr('continue_next', '继续下一步')})", "")
        for s in self.project.gameplay_scenes():
            combo.addItem(self._scene_combo_label(s), s.id)
        new_idx = combo.findData(scene.id)
        combo.setCurrentIndex(new_idx if new_idx >= 0 else 0)
        combo.blockSignals(False)

    def _refresh_opt_list(self) -> None:
        self._opt_list.clear()
        for opt in self._opt_items:
            QListWidgetItem(f"{opt.text}  ->  {opt.next or tr('continue_next', '下一步')}", self._opt_list)

    def accept(self) -> None:
        t = self._type_combo.currentData()
        self.step.type = t
        self.step.speaker = self._speaker.text()
        self.step.text = self._text.toPlainText()
        self.step.voice = self._voice.value()
        self.step.character = self._character.value()
        self.step.position = self._position.currentData() or "left"
        self.step.background = self._background.value()
        self.step.bgm = self._bgm.value()
        self.step.source = self._source.value()
        self.step.prompt = self._prompt.text()
        self.step.options = list(self._opt_items) if t == "choice" else []
        self.step.next = self._next.currentData() or ""

        self.step.audio_category = self._audio_category.currentData() or "bgm"
        self.step.audio_action = self._audio_action.currentData() or "play"
        self.step.audio_file = self._audio_file.value() if self.step.audio_action == "play" else ""

        if self._exit_mode.currentData() == "character":
            self.step.exit_character = self._exit_character.value()
            self.step.exit_position = "all"
        else:
            self.step.exit_character = ""
            self.step.exit_position = "all"

        if self._created_scenes:
            used = {o.next for o in self.step.options if o.next}
            for sc in self._created_scenes:
                if sc.id not in used and sc in self.project.scenes:
                    self.project.scenes.remove(sc)
            self._created_scenes.clear()
        super().accept()

    def reject(self) -> None:
        for sc in self._created_scenes:
            if sc in self.project.scenes:
                self.project.scenes.remove(sc)
        self._created_scenes.clear()
        super().reject()

    @staticmethod
    def edit(step: Step, project: Project, current_scene_id: str = "", parent=None) -> bool:
        dlg = StepEditDialog(step, project, current_scene_id, parent)
        return dlg.exec() == QDialog.Accepted
