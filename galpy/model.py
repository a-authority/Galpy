"""GalPy 数据模型: Project / Scene / Step / ChoiceOption。

模型采用 dataclass, 可与 JSON 双向转换。一个 Project 即一个完整游戏,
由若干 Scene 组成; 每个 Scene 由若干 Step (步骤) 顺序执行。
Step 的 type 决定其语义 (对白 / 旁白 / 选项 / 视频 / 换背景 / 切换音频 /
立绘离场 / 跳转 / 结束)。
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, ClassVar, Dict, List, Optional


# 所有合法的 Step 类型
STEP_TYPES: Dict[str, str] = {
    "dialogue": "对白",
    "narration": "旁白",
    "choice": "选项分支",
    "video": "播放视频",
    "bg_change": "切换背景",
    "audio_change": "切换音频",
    "character_exit": "立绘离场",
    "goto": "跳转场景",
    "end": "结束游戏",
}

# 音频切换步骤支持的子类别 (对应 assets 分类)
AUDIO_CATEGORIES: Dict[str, str] = {
    "bgm": "背景音乐",
    "sfx": "音效",
    "voice": "语音",
}

# 音频切换步骤支持的操作
AUDIO_ACTIONS: Dict[str, str] = {
    "play": "播放",
    "stop": "停止",
}

# 等待用户点击推进的步骤类型 (需要用户交互)
INTERACTIVE_TYPES = {"dialogue", "narration", "choice", "video"}

# 旧 step.type -> 新 step.type 的兼容映射 (加载旧工程时自动迁移)
_LEGACY_TYPE_MAP = {
    "bgm_change": "audio_change",
    "sfx": "audio_change",
}


def _filter_step_fields(d: Dict[str, Any]) -> Dict[str, Any]:
    """从 dict 加载 Step 时, 过滤掉未知字段 (如旧工程的 sfx 字段),
    并把旧字段值迁移到新字段, 避免 TypeError。"""
    # 取出 type 用于判断迁移
    raw_type = d.get("type", "dialogue")
    clean: Dict[str, Any] = {}
    # Step 的所有合法字段名
    valid_fields = {
        "type", "speaker", "text", "voice", "character", "position", "emotion",
        "background", "bgm", "audio_category", "audio_action", "audio_file",
        "exit_character", "exit_position", "source", "prompt", "options", "next",
    }
    for k, v in d.items():
        if k in valid_fields:
            clean[k] = v
    # 旧字段迁移: sfx -> audio_file (当 type 旧值为 sfx 时)
    if "sfx" in d and "audio_file" not in clean:
        if raw_type == "sfx" and d["sfx"]:
            clean["audio_file"] = d["sfx"]
    return clean


@dataclass
class ChoiceOption:
    """选项分支中的一个可选项。"""
    text: str = ""          # 选项显示文字
    next: str = ""          # 跳转目标 scene id; 为空则继续下一步


@dataclass
class Step:
    """场景中的一步。不同 type 使用不同字段, 未用到的字段忽略。"""
    type: str = "dialogue"

    # --- 对白 / 旁白 ---
    speaker: str = ""              # 说话者名字 (对白)
    text: str = ""                 # 显示文字
    voice: str = ""                # 语音文件 (相对 assets 路径)
    character: str = ""            # 角色立绘 (相对 assets 路径)
    position: str = "left"         # 立绘位置
    emotion: str = ""              # 表情备注 (可选)

    # --- 媒体切换 ---
    background: str = ""           # 背景图 (bg_change 或 scene 级)
    bgm: str = ""                  # BGM (scene 级 BGM 字段, 保留)

    # --- 音频切换 (audio_change) ---
    audio_category: str = "bgm"    # bgm / sfx / voice
    audio_action: str = "play"     # play / stop
    audio_file: str = ""           # 音频文件 (相对 assets 路径)

    # --- 立绘离场 (character_exit) ---
    # exit_character 优先: 指定要清除的立绘 (相对 assets 路径), 无论它在哪个位置
    exit_character: str = ""       # 指定清除的立绘路径; 为空时回退到 exit_position
    exit_position: str = "all"     # 兼容旧工程: all / left / center / right 等; all=清除全部立绘

    # --- 视频 ---
    source: str = ""               # 视频文件

    # --- 选项 ---
    prompt: str = ""               # 选项提示语
    options: List[ChoiceOption] = field(default_factory=list)

    # --- 流程 ---
    next: str = ""                 # goto 跳转目标 scene id

    VALID_TYPES: ClassVar[set] = set(STEP_TYPES.keys())

    def __post_init__(self) -> None:
        # 兼容旧工程: bgm_change / sfx 自动迁移为 audio_change
        if self.type in _LEGACY_TYPE_MAP:
            old = self.type
            self.type = _LEGACY_TYPE_MAP[old]
            if old == "bgm_change":
                # 旧 bgm 字段映射到 audio_file + audio_category=bgm
                if not self.audio_file and self.bgm:
                    self.audio_file = self.bgm
                self.audio_category = "bgm"
                self.audio_action = "play"
            elif old == "sfx":
                # 旧 sfx 字段映射到 audio_file + audio_category=sfx
                self.audio_category = "sfx"
                self.audio_action = "play"
        if self.type not in self.VALID_TYPES:
            raise ValueError(f"非法的 step 类型: {self.type!r}")
        # 兼容从 dict 反序列化时 options 为 dict 列表的情况
        normalized: List[ChoiceOption] = []
        for opt in self.options:
            if isinstance(opt, dict):
                normalized.append(ChoiceOption(**opt))
            else:
                normalized.append(opt)
        self.options = normalized

    def label(self) -> str:
        """在编辑器列表中显示的简短描述。"""
        try:
            from .i18n import get_step_type_label, get_audio_category_label, get_audio_action_label, tr
            t = get_step_type_label(self.type)
            if self.type == "dialogue":
                spk = self.speaker or tr("none", "(无)")
                return f"[{t}] {spk}: {self.text[:18]}"
            if self.type == "narration":
                return f"[{t}] {self.text[:24]}"
            if self.type == "choice":
                opts = "/".join(o.text for o in self.options[:3])
                return f"[{t}] {self.prompt[:12]} ({opts})"
            if self.type == "video":
                return f"[{t}] {os.path.basename(self.source)}"
            if self.type == "bg_change":
                return f"[{t}] {os.path.basename(self.background)}"
            if self.type == "audio_change":
                cat = get_audio_category_label(self.audio_category)
                act = get_audio_action_label(self.audio_action)
                fname = os.path.basename(self.audio_file) if self.audio_action == "play" else ""
                return f"[{t}] {act} {cat} {fname}".strip()
            if self.type == "character_exit":
                if self.exit_character:
                    return f"[{t}] {tr('character_label', '立绘')}: {os.path.basename(self.exit_character)}"
                return f"[{t}] {tr('exit_all', '全部立绘')}"
            if self.type == "goto":
                return f"[{t}] -> {self.next}"
            return f"[{t}]"
        except Exception:
            t = STEP_TYPES.get(self.type, self.type)
            return f"[{t}]"


@dataclass
class Scene:
    """一个场景: 自带背景/BGM, 内含一系列 Step。"""
    id: str = ""
    name: str = ""
    background: str = ""
    bgm: str = ""
    # 父场景 id (为空=顶级场景)。由"选项中新建场景"产生的分支场景会指向其父场景,
    # 仅用于编辑器场景列表的缩进分类展示; 播放器不使用此字段。
    parent_scene: str = ""
    steps: List[Step] = field(default_factory=list)
    is_cover: bool = False        # 封面场景 (标题画面, 不可删除, 固定置顶)

    def __post_init__(self) -> None:
        if not self.id:
            self.id = f"scene_{uuid.uuid4().hex[:8]}"
        normalized: List[Step] = []
        for s in self.steps:
            if isinstance(s, dict):
                normalized.append(Step(**_filter_step_fields(s)))
            else:
                normalized.append(s)
        self.steps = normalized


@dataclass
class Project:
    """一个完整的 Galgame 工程。"""
    version: str = "1.0"
    title: str = "未命名游戏"
    author: str = ""
    width: int = 1280
    height: int = 720
    start_scene: str = ""
    assets: Dict[str, List[str]] = field(default_factory=dict)
    scenes: List[Scene] = field(default_factory=list)

    def __post_init__(self) -> None:
        # 确保 assets 各分类存在
        from .config import ASSET_CATEGORIES
        for cat in ASSET_CATEGORIES:
            self.assets.setdefault(cat, [])
        # 兼容 dict 反序列化
        normalized: List[Scene] = []
        for s in self.scenes:
            if isinstance(s, dict):
                normalized.append(Scene(**s))
            else:
                normalized.append(s)
        self.scenes = normalized
        if self.scenes and not self.start_scene:
            self.start_scene = self.scenes[0].id
        # 确保存在且仅存在一个封面场景, 并固定在列表顶部
        self._ensure_cover()

    def _ensure_cover(self) -> None:
        """保证工程有一个封面场景 (标题画面), 固定置顶、不可删除。
        加载旧工程时若无封面, 自动补一个; start_scene 不指向封面。"""
        cover = None
        for s in self.scenes:
            if s.is_cover:
                if cover is None:
                    cover = s
                else:
                    s.is_cover = False  # 去重: 只保留第一个
        if cover is None:
            cover = Scene(name=self.title or "封面", is_cover=True)
            self.scenes.insert(0, cover)
        elif self.scenes[0] is not cover:
            self.scenes.remove(cover)
            self.scenes.insert(0, cover)
        # 起始场景不应是封面 (封面是标题画面, 非游戏内容)
        if not self.start_scene or self.start_scene == cover.id:
            first_game = next((s for s in self.scenes if not s.is_cover), None)
            self.start_scene = first_game.id if first_game else ""

    # ---------- 查询 ----------
    def get_scene(self, scene_id: str) -> Optional[Scene]:
        for s in self.scenes:
            if s.id == scene_id:
                return s
        return None

    def scene_index(self, scene_id: str) -> int:
        for i, s in enumerate(self.scenes):
            if s.id == scene_id:
                return i
        return -1

    def scene_ids(self) -> List[str]:
        return [s.id for s in self.scenes]

    def cover_scene(self) -> Optional[Scene]:
        """封面场景 (标题画面)。"""
        return next((s for s in self.scenes if s.is_cover), None)

    def gameplay_scenes(self) -> List[Scene]:
        """非封面的游戏场景 (用于跳转/选项目标下拉, 排除封面)。"""
        return [s for s in self.scenes if not s.is_cover]

    def scene_depth(self, scene_id: str) -> int:
        """场景在分支树中的深度: 顶级=0, 一级分支=1, 二级分支=2, … (带防环)。"""
        depth = 0
        seen = {scene_id}
        sid = scene_id
        while True:
            scene = self.get_scene(sid)
            if scene is None or not scene.parent_scene:
                break
            if scene.parent_scene in seen:  # 防止循环引用
                break
            depth += 1
            seen.add(scene.parent_scene)
            sid = scene.parent_scene
        return depth

    # ---------- 编辑 ----------
    def new_scene(self, name: str = "") -> Scene:
        scene = Scene(name=name or f"场景 {len(self.scenes) + 1}")
        self.scenes.append(scene)
        if not self.start_scene:
            self.start_scene = scene.id
        return scene

    def add_branch_scene(self, parent_id: str, scene: Scene) -> int:
        """把 scene 作为 parent_id 的分支场景插入到父场景子树之后。

        设置 scene.parent_scene = parent_id, 并把 scene 插入到父场景及其
        所有后代之后 (保持分支在场景列表中紧随父场景, 形成缩进分类)。
        返回插入后的索引; 找不到父场景时追加到末尾。
        """
        scene.parent_scene = parent_id
        parent_idx = self.scene_index(parent_id)
        if parent_idx < 0:
            self.scenes.append(scene)
            return len(self.scenes) - 1
        # 子树 = 父场景 + 所有后代 (parent_scene 指向子树内某场景)
        subtree_ids = {parent_id}
        end = parent_idx + 1
        while end < len(self.scenes) and self.scenes[end].parent_scene in subtree_ids:
            subtree_ids.add(self.scenes[end].id)
            end += 1
        self.scenes.insert(end, scene)
        return end

    def add_asset(self, category: str, rel_path: str) -> None:
        self.assets.setdefault(category, [])
        if rel_path not in self.assets[category]:
            self.assets[category].append(rel_path)

    # ---------- 序列化 ----------
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json())

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Project":
        # 过滤未知字段, 防御性解析
        known = {f for f in ("version", "title", "author", "width", "height",
                             "start_scene", "assets", "scenes")}
        clean = {k: v for k, v in d.items() if k in known}
        return cls(**clean)

    @classmethod
    def load(cls, path: str) -> "Project":
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        return cls.from_dict(d)

    @classmethod
    def empty(cls, title: str = "未命名游戏") -> "Project":
        """创建带封面 + 一个初始游戏场景的空工程。"""
        proj = cls(title=title)  # __post_init__ 已自动补一个封面场景
        # 确保至少有一个游戏场景 (非封面)
        if not any(not s.is_cover for s in proj.scenes):
            proj.new_scene("开场")
        # 起始场景指向第一个非封面场景
        first_game = next((s for s in proj.scenes if not s.is_cover), None)
        if first_game:
            proj.start_scene = first_game.id
        return proj
