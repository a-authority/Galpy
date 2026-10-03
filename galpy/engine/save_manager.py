"""游戏存档管理: 自动存档 (续玩) + 多个手动存档槽位。

存档内容: 场景 id + 步骤索引 + 当前背景/BGM/立绘状态 + 时间戳 + 标签,
足以在恢复时重建画面与音频, 并从该步骤重新展示。

存档位置:
  - 开发态 (非打包): <工程目录>/saves/  (与工程放一起, 便于调试)
  - 打包态: <AppData>/GalPy/saves/<安全标题>/  (exe 同级可能只读,
    _MEIPASS 是临时目录, 故用 AppData 持久化)
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


SLOT_COUNT = 9                       # 手动存档槽位数 (3x3 网格)
AUTO_SLOT_FILE = "auto.json"         # 自动存档 (续玩) 文件名
SLOT_FILE_PREFIX = "slot_"           # 手动槽位文件名前缀 slot_01.json ...


@dataclass
class SaveSlot:
    """一份存档: 足以恢复到存档时的步骤并重建画面。"""
    scene_id: str = ""                                  # 所在场景 id
    step_index: int = 0                                 # 场景内步骤索引 (从 0 起)
    background: str = ""                                # 当前背景图相对路径
    bgm: str = ""                                       # 当前 BGM 相对路径
    characters: Dict[str, str] = field(default_factory=dict)  # position -> 立绘相对路径
    timestamp: str = ""                                 # 存档时间 (显示用)
    label: str = ""                                     # 存档描述 (场景名 #步骤)
    title: str = ""                                     # 工程标题 (显示用)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SaveSlot":
        known = {
            "scene_id", "step_index", "background", "bgm",
            "characters", "timestamp", "label", "title",
        }
        clean = {k: v for k, v in d.items() if k in known}
        return cls(**clean)


def _safe_name(title: str) -> str:
    """把工程标题转换为文件系统安全的目录名。"""
    s = "".join(c for c in (title or "game") if c.isalnum() or c in "-_")
    return s or "game"


def resolve_saves_dir(base_dir: str, project_title: str) -> str:
    """决定存档目录并确保存在。

    - 打包态: %APPDATA%/GalPy/saves/<标题>/ (跨启动持久, 不受 exe 位置影响)
    - 开发态: <工程目录>/saves/
    """
    if getattr(sys, "frozen", False):
        root = os.environ.get("APPDATA") or os.path.expanduser("~")
        d = os.path.join(root, "GalPy", "saves", _safe_name(project_title))
    else:
        d = os.path.join(base_dir, "saves")
    os.makedirs(d, exist_ok=True)
    return d


class SaveManager:
    """管理自动存档与若干手动槽位的读写。"""

    def __init__(self, saves_dir: str):
        self.saves_dir = saves_dir

    # ---------- 路径 ----------
    def _slot_path(self, index: int) -> str:
        return os.path.join(self.saves_dir, f"{SLOT_FILE_PREFIX}{index:02d}.json")

    @property
    def auto_path(self) -> str:
        return os.path.join(self.saves_dir, AUTO_SLOT_FILE)

    # ---------- 自动存档 (续玩) ----------
    def has_auto(self) -> bool:
        return os.path.exists(self.auto_path)

    def save_auto(self, slot: SaveSlot) -> None:
        if not slot.timestamp:
            slot.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        slot.title = slot.title
        with open(self.auto_path, "w", encoding="utf-8") as f:
            json.dump(slot.to_dict(), f, ensure_ascii=False, indent=2)

    def load_auto(self) -> Optional[SaveSlot]:
        if not os.path.exists(self.auto_path):
            return None
        try:
            with open(self.auto_path, "r", encoding="utf-8") as f:
                return SaveSlot.from_dict(json.load(f))
        except Exception:
            return None

    # ---------- 手动槽位 ----------
    def list_slots(self) -> List[Optional[SaveSlot]]:
        """返回长度为 SLOT_COUNT 的列表; 空槽位为 None。"""
        slots: List[Optional[SaveSlot]] = []
        for i in range(1, SLOT_COUNT + 1):
            p = self._slot_path(i)
            if os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        slots.append(SaveSlot.from_dict(json.load(f)))
                except Exception:
                    slots.append(None)
            else:
                slots.append(None)
        return slots

    def load_slot(self, index: int) -> Optional[SaveSlot]:
        p = self._slot_path(index)
        if not os.path.exists(p):
            return None
        with open(p, "r", encoding="utf-8") as f:
            return SaveSlot.from_dict(json.load(f))

    def save_slot(self, index: int, slot: SaveSlot) -> None:
        if index < 1 or index > SLOT_COUNT:
            raise ValueError(f"存档槽位超出范围: {index}")
        if not slot.timestamp:
            slot.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self._slot_path(index), "w", encoding="utf-8") as f:
            json.dump(slot.to_dict(), f, ensure_ascii=False, indent=2)

    def delete_slot(self, index: int) -> None:
        p = self._slot_path(index)
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass
