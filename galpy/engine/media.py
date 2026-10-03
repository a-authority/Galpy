"""音频播放管理: BGM (循环) / 语音 / 音效 三个独立通道。

基于 PySide6.QtMultimedia (QMediaPlayer + QAudioOutput)。
三个通道相互独立, 可同时播放 (例如 BGM 持续 + 触发音效 + 角色语音)。
"""
from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer


class AudioChannel:
    """单个音频通道, 封装一个 QMediaPlayer + QAudioOutput。"""

    def __init__(self, volume: float = 0.8, loops: int = 1, parent: Optional[QObject] = None):
        self.player = QMediaPlayer(parent)
        self.output = QAudioOutput(parent)
        self.player.setAudioOutput(self.output)
        self.output.setVolume(volume)
        self.player.setLoops(loops)

    def play_file(self, path: str) -> None:
        """播放本地文件; 路径为空或不存在则停止。"""
        if not path:
            self.stop()
            return
        if not os.path.isabs(path):
            path = os.path.abspath(path)
        if not os.path.exists(path):
            self.stop()
            return
        self.player.setSource(QUrl.fromLocalFile(path))
        self.player.play()

    def stop(self) -> None:
        self.player.stop()
        self.player.setSource(QUrl())

    def set_volume(self, volume: float) -> None:
        self.output.setVolume(max(0.0, min(1.0, volume)))

    def set_loops(self, loops: int) -> None:
        self.player.setLoops(loops)

    def is_playing(self) -> bool:
        return self.player.playbackState() == QMediaPlayer.PlayingState


class AudioManager(QObject):
    """协调 BGM / 语音 / 音效 三个通道。"""

    # 语音播放结束信号 (用于可选的自动推进)
    voice_finished = Signal()

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        # BGM 无限循环
        self.bgm = AudioChannel(volume=0.6, loops=QMediaPlayer.Infinite, parent=self)
        self.voice = AudioChannel(volume=1.0, loops=1, parent=self)
        self.sfx = AudioChannel(volume=0.9, loops=1, parent=self)

        # 语音结束 -> 发信号
        self.voice.player.mediaStatusChanged.connect(self._on_voice_status)

    def _on_voice_status(self, status: QMediaPlayer.MediaStatus) -> None:
        if status == QMediaPlayer.EndOfMedia:
            self.voice_finished.emit()

    # ---- BGM ----
    def play_bgm(self, path: str) -> None:
        if path:
            self.bgm.play_file(path)
        else:
            self.bgm.stop()

    def stop_bgm(self) -> None:
        self.bgm.stop()

    # ---- 语音 ----
    def play_voice(self, path: str) -> None:
        if path:
            self.voice.play_file(path)
        else:
            self.voice.stop()

    def stop_voice(self) -> None:
        self.voice.stop()

    # ---- 音效 ----
    def play_sfx(self, path: str) -> None:
        if path:
            self.sfx.play_file(path)

    def stop_sfx(self) -> None:
        self.sfx.stop()

    # ---- 全局 ----
    def stop_all(self) -> None:
        for ch in (self.bgm, self.voice, self.sfx):
            ch.stop()

    def set_master_volume(self, volume: float) -> None:
        for ch in (self.bgm, self.voice, self.sfx):
            ch.set_volume(volume)
