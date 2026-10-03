"""全局配置与常量。"""
import os
import sys

APP_NAME = "GalPy"
APP_VERSION = "1.0.0"

# 默认窗口分辨率
DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 720

# 支持的文件后缀
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}
AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".flac", ".m4a"}
VIDEO_EXTS = {".mp4", ".avi", ".mkv", ".mov", ".webm"}

# 资源分类 (目录名 -> 中文名)
ASSET_CATEGORIES = {
    "backgrounds": "背景图片",
    "characters": "角色立绘",
    "bgm": "背景音乐",
    "voice": "语音",
    "sfx": "音效",
    "videos": "视频",
}

# 角色立绘在屏幕上的预设位置
CHARACTER_POSITIONS = ["left", "center_left", "center", "center_right", "right"]
POSITION_LABELS = {
    "left": "左侧",
    "center_left": "偏左",
    "center": "居中",
    "center_right": "偏右",
    "right": "右侧",
}

# 项目文件 / 资源目录命名
PROJECT_EXT = ".galpy"          # GalPy 工程后缀 (新格式)
PROJECT_FILE_NAME = "project.json"  # 旧格式兼容 (仍可打开, 保存默认用 .galpy)
AUTO_SAVE_SUFFIX = ".auto"      # 自动保存副本后缀: 项目名.auto.galpy
PROJECT_FILE_FILTER = (
    f"GalPy 工程 (*{PROJECT_EXT} *{AUTO_SAVE_SUFFIX}{PROJECT_EXT} {PROJECT_FILE_NAME})"
)
ASSETS_DIR_NAME = "assets"


def resource_path(relative_path: str) -> str:
    """获取资源绝对路径, 兼容开发态与 PyInstaller 打包态。

    打包后, 被 --add-data 收录的文件会解压到 sys._MEIPASS 临时目录;
    开发态则相对于当前工作目录或本文件所在目录解析。
    """
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    # 开发态: 优先相对工程根, 其次相对本文件
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, relative_path)


def app_base_dir() -> str:
    """返回程序"数据基目录":
      - 打包态: exe 所在目录 (用于读取与 exe 同级的外部资源)
      - 开发态: 工程根目录
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
