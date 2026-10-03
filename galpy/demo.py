"""示例工程生成器。

create_demo_project(dir) 会在指定目录下生成:
  - project.json          (含多个场景, 演示 对白/旁白/选项/换背景/换BGM/音效/跳转/结束)
  - assets/backgrounds/   (占位背景 PNG, 用 QPainter 绘制)
  - assets/characters/    (占位立绘 PNG, 透明背景)
  - assets/bgm/           (短旋律 WAV, 可循环)
  - assets/sfx/           (提示音 WAV)

视频演示需用户自行放入 mp4 (引擎已支持, 见 README)。
所有素材均为代码生成, 无需外部文件, 开箱即用。
"""
from __future__ import annotations

import math
import os
import struct
import wave
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen, QPixmap

from .config import ASSETS_DIR_NAME
from .i18n import get_effective_language
from .model import ChoiceOption, Project, Scene, Step


# ============================================================
# 资源生成
# ============================================================
def _make_background(path: str, top: str, bottom: str, label: str) -> None:
    pix = QPixmap(1280, 720)
    grad = QLinearGradient(0, 0, 0, 720)
    grad.setColorAt(0.0, QColor(top))
    grad.setColorAt(1.0, QColor(bottom))
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.fillRect(pix.rect(), grad)
    # 装饰圆点
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(255, 255, 255, 30))
    painter.drawEllipse(900, 120, 220, 220)
    painter.setBrush(QColor(255, 255, 255, 20))
    painter.drawEllipse(120, 480, 320, 320)
    # 标签
    painter.setPen(QColor(255, 255, 255, 220))
    f = QFont(); f.setPointSize(30); f.setBold(True); painter.setFont(f)
    painter.drawText(pix.rect(), Qt.AlignCenter, label)
    painter.end()
    pix.save(path, "PNG")


def _make_character(path: str, body: str, label: str) -> None:
    pix = QPixmap(480, 720)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(QColor(255, 255, 255, 220), 3)
    painter.setPen(pen)
    # 头部
    painter.setBrush(QColor(body).lighter(130))
    painter.drawEllipse(160, 70, 160, 160)
    # 眼睛
    painter.setBrush(QColor(40, 40, 60))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(195, 140, 16, 22)
    painter.drawEllipse(269, 140, 16, 22)
    # 身体
    painter.setPen(pen)
    painter.setBrush(QColor(body))
    painter.drawRoundedRect(130, 240, 220, 410, 50, 50)
    # 名字
    painter.setPen(QColor(255, 255, 255))
    f = QFont(); f.setPointSize(24); f.setBold(True); painter.setFont(f)
    painter.drawText(pix.rect(), Qt.AlignBottom | Qt.AlignHCenter, label)
    painter.end()
    pix.save(path, "PNG")


def _make_wav(path: str, notes: List[float], note_dur: float = 0.32,
              sr: int = 22050, volume: float = 0.4) -> None:
    """生成一段简单旋律 WAV (正弦波叠加泛音, 带淡入淡出)。"""
    n_samples = int(sr * note_dur * len(notes))
    with wave.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        for i, freq in enumerate(_expand_notes(notes)):
            start = int(i * sr * note_dur)
            end = int((i + 1) * sr * note_dur)
            seg = end - start
            for k in range(seg):
                t = k / sr
                # 基波 + 二次泛音
                s = (math.sin(2 * math.pi * freq * t)
                     + 0.3 * math.sin(2 * math.pi * 2 * freq * t)) / 1.3
                # 淡入淡出
                env = 1.0
                if k < 500:
                    env = k / 500
                if k > seg - 1500:
                    env = max(0.0, (seg - k) / 1500)
                s *= env * volume
                s = max(-1.0, min(1.0, s))
                w.writeframes(struct.pack("<h", int(s * 32767)))


def _expand_notes(notes: List[float]) -> List[float]:
    return notes


# ============================================================
# 工程构建
# ============================================================
def create_demo_project(directory: str, title: Optional[str] = None) -> Project:
    """在 directory 下生成完整示例工程, 返回 Project 对象。"""
    is_en = (get_effective_language() == "en_US")
    demo_title = title or ("Demo: Morning Sun" if is_en else "示例: 晨光")

    assets_dir = os.path.join(directory, ASSETS_DIR_NAME)
    for sub in ("backgrounds", "characters", "bgm", "sfx", "voice", "videos"):
        os.makedirs(os.path.join(assets_dir, sub), exist_ok=True)

    rel = lambda *p: os.path.relpath(os.path.join(assets_dir, *p), directory).replace("\\", "/")

    # ---- 背景图 ----
    bg_room = rel("backgrounds", "bg_room.png")
    bg_school = rel("backgrounds", "bg_school.png")
    bg_night = rel("backgrounds", "bg_night.png")
    _make_background(os.path.join(assets_dir, "backgrounds", "bg_room.png"),
                     "#f6d365", "#fda085", "My Room" if is_en else "我的房间")
    _make_background(os.path.join(assets_dir, "backgrounds", "bg_school.png"),
                     "#a1c4fd", "#c2e9fb", "School" if is_en else "学校")
    _make_background(os.path.join(assets_dir, "backgrounds", "bg_night.png"),
                     "#2c3e50", "#4ca1af", "Night" if is_en else "夜晚")

    # ---- 角色立绘 ----
    char_a = rel("characters", "char_a.png")
    char_b = rel("characters", "char_b.png")
    name_a = "Ming" if is_en else "小明"
    name_b = "Hong" if is_en else "小红"
    _make_character(os.path.join(assets_dir, "characters", "char_a.png"),
                     "#5b8def", name_a)
    _make_character(os.path.join(assets_dir, "characters", "char_b.png"),
                     "#ef5b9c", name_b)

    # ---- 音频 ----
    bgm_path = rel("bgm", "theme.wav")
    _make_wav(os.path.join(assets_dir, "bgm", "theme.wav"),
              [523.25, 659.25, 783.99, 659.25, 523.25, 392.0, 523.25, 659.25],
              note_dur=0.4, volume=0.35)
    sfx_path = rel("sfx", "beep.wav")
    _make_wav(os.path.join(assets_dir, "sfx", "beep.wav"),
              [880.0, 1174.66], note_dur=0.15, volume=0.5)

    # ---- 工程 ----
    project = Project(
        title=demo_title,
        author="GalPy Demo",
        width=1280,
        height=720,
    )
    project.assets = {
        "backgrounds": [bg_room, bg_school, bg_night],
        "characters": [char_a, char_b],
        "bgm": [bgm_path],
        "voice": [],
        "sfx": [sfx_path],
        "videos": [],
    }

    if is_en:
        s1 = Scene(name="Opening", background=bg_room, bgm=bgm_path)
        s1.steps = [
            Step(type="narration", text="Morning sunlight pours into the bedroom. A brand new day begins."),
            Step(type="bg_change", background=bg_school),
            Step(type="dialogue", speaker=name_a, text="What beautiful weather today!",
                 character=char_a, position="left"),
            Step(type="dialogue", speaker=name_b, text="Yeah! Shall we walk to school together?",
                 character=char_b, position="right"),
            Step(type="choice", prompt="What is your choice?", options=[
                ChoiceOption(text="Sure, let's go!", next=""),
                ChoiceOption(text="I want to sleep a bit more…", next="scene_late"),
            ]),
        ]

        s2 = Scene(name="Walk to School", background=bg_school)
        s2.steps = [
            Step(type="dialogue", speaker=name_a, text="Here we are at school!",
                 character=char_a, position="left"),
            Step(type="audio_change", audio_category="sfx", audio_action="play",
                 audio_file=sfx_path),
            Step(type="dialogue", speaker=name_b, text="Let's head inside together!",
                 character=char_b, position="right"),
            Step(type="narration", text="The two walked into the campus side by side……"),
            Step(type="character_exit", exit_position="all"),
            Step(type="goto", next="scene_end"),
        ]

        s3 = Scene(id="scene_late", name="Sleep In", background=bg_room)
        s3.steps = [
            Step(type="narration", text="You fell back asleep for a little while……"),
            Step(type="dialogue", speaker=name_b, text="You really can't help it, can you?",
                 character=char_b, position="right"),
            Step(type="character_exit", exit_position="right"),
            Step(type="goto", next="scene_end"),
        ]

        s4 = Scene(id="scene_end", name="Ending", background=bg_night)
        s4.steps = [
            Step(type="audio_change", audio_category="bgm", audio_action="stop"),
            Step(type="narration", text="And so, another pleasant day quietly came to a close."),
            Step(type="narration", text="(This is a sample project generated by GalPy)"),
            Step(type="end"),
        ]
    else:
        s1 = Scene(name="开场", background=bg_room, bgm=bgm_path)
        s1.steps = [
            Step(type="narration", text="清晨的阳光洒进房间, 新的一天开始了。"),
            Step(type="bg_change", background=bg_school),
            Step(type="dialogue", speaker="小明", text="今天天气真不错呀!",
                 character=char_a, position="left"),
            Step(type="dialogue", speaker="小红", text="是呀, 一起去学校吧?",
                 character=char_b, position="right"),
            Step(type="choice", prompt="你的选择是?", options=[
                ChoiceOption(text="好的, 走吧!", next=""),
                ChoiceOption(text="我想再睡一会儿…", next="scene_late"),
            ]),
        ]

        s2 = Scene(name="上学路", background=bg_school)
        s2.steps = [
            Step(type="dialogue", speaker="小明", text="学校到了!",
                 character=char_a, position="left"),
            Step(type="audio_change", audio_category="sfx", audio_action="play",
                 audio_file=sfx_path),
            Step(type="dialogue", speaker="小红", text="走, 一起进去!",
                 character=char_b, position="right"),
            Step(type="narration", text="两人并肩走进了校园……"),
            Step(type="character_exit", exit_position="all"),
            Step(type="goto", next="scene_end"),
        ]

        s3 = Scene(id="scene_late", name="赖床", background=bg_room)
        s3.steps = [
            Step(type="narration", text="你又睡了个回笼觉……"),
            Step(type="dialogue", speaker="小红", text="真拿你没办法。",
                 character=char_b, position="right"),
            Step(type="character_exit", exit_position="right"),
            Step(type="goto", next="scene_end"),
        ]

        s4 = Scene(id="scene_end", name="结尾", background=bg_night)
        s4.steps = [
            Step(type="audio_change", audio_category="bgm", audio_action="stop"),
            Step(type="narration", text="一天就这样悄然过去了。"),
            Step(type="narration", text="(这是一个由 GalPy 生成的示例工程)"),
            Step(type="end"),
        ]

    # 封面场景 (标题画面): 用房间背景 + 主题音乐, 标题即工程标题
    cover = Scene(name=demo_title, background=bg_room, bgm=bgm_path, is_cover=True)
    project.scenes = [cover, s1, s2, s3, s4]
    project.start_scene = s1.id

    # 保存
    project.save(os.path.join(directory, "project.json"))
    return project
