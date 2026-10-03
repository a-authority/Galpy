"""PyInstaller 打包模块: 把 GalPy 工程打包为独立可执行程序。

打包流程:
  1. 在临时构建目录中写入 game_main.py (运行时入口) 与 galpy 包副本
  2. 复制 project.json 与 assets/ 资源
  3. 调用 PyInstaller 生成 exe, 通过 --add-data 把工程资源打进 _MEIPASS
  4. 生成的 exe 双击即可直接运行游戏, 终端用户无需安装任何库
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from typing import Optional

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout,
    QWidget,
)

from ..config import ASSETS_DIR_NAME, PROJECT_FILE_NAME
from ..i18n import tr
from ..model import Project


# 运行时入口模板: 冻结后从 _MEIPASS 读取 project.json 并启动播放器
GAME_MAIN_TEMPLATE = '''"""自动生成的游戏入口 (由 GalPy 打包器生成)。"""
import os
import sys


def _base_dir():
    if hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def main():
    from PySide6.QtWidgets import QApplication
    from galpy.model import Project
    from galpy.engine.player import GamePlayer

    base = _base_dir()
    proj_path = os.path.join(base, "{proj}")
    app = QApplication(sys.argv)
    project = Project.load(proj_path)
    player = GamePlayer(project, base)
    player.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
'''


def _data_sep() -> str:
    """PyInstaller --add-data 的路径分隔符: Windows 用 ';', 其它用 ':'。"""
    return ";" if os.name == "nt" else ":"


def _safe_name(name: str) -> str:
    out = "".join(c for c in name if c.isalnum() or c in "_-")
    return out or "game"


class PackageWorker(QThread):
    """后台执行 PyInstaller, 实时回传日志。"""

    log = Signal(str)
    finished_ok = Signal(str)   # exe 路径
    finished_err = Signal(str)  # 错误信息

    def __init__(self, project: Project, project_path: str, output_dir: str,
                 onefile: bool, show_console: bool, parent=None):
        super().__init__(parent)
        self.project = project
        self.project_path = project_path
        self.output_dir = output_dir
        self.onefile = onefile
        self.show_console = show_console   # True=打包后的 exe 启动时显示控制台

    def run(self) -> None:
        try:
            self.log.emit("[1/5] 准备构建目录…")
            build_dir = tempfile.mkdtemp(prefix="galpy_build_")

            # ---- 复制 galpy 包 ----
            # 本文件位于 .../GalPy/galpy/packaging/packager.py
            galpy_pkg = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            dst_galpy = os.path.join(build_dir, "galpy")
            shutil.copytree(
                galpy_pkg, dst_galpy,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )

            # ---- 写 game_main.py ----
            self.log.emit("[2/5] 生成运行时入口…")
            gm_path = os.path.join(build_dir, "game_main.py")
            with open(gm_path, "w", encoding="utf-8") as f:
                f.write(GAME_MAIN_TEMPLATE.format(proj=PROJECT_FILE_NAME))

            # ---- 复制工程文件与资源 ----
            shutil.copy2(self.project_path, os.path.join(build_dir, PROJECT_FILE_NAME))
            proj_dir = os.path.dirname(self.project_path)
            assets_src = os.path.join(proj_dir, ASSETS_DIR_NAME)
            assets_dst = os.path.join(build_dir, ASSETS_DIR_NAME)
            if os.path.isdir(assets_src):
                shutil.copytree(assets_src, assets_dst, dirs_exist_ok=True)
            else:
                os.makedirs(assets_dst, exist_ok=True)

            # ---- 构造 PyInstaller 命令 ----
            self.log.emit("[3/5] 调用 PyInstaller…")
            sep = _data_sep()
            name = _safe_name(self.project.title)
            cmd = [sys.executable, "-m", "PyInstaller"]
            cmd.append("--onefile" if self.onefile else "--onedir")
            # 是否为最终 exe 保留控制台窗口 (调试时可勾选; 发布 GUI 游戏通常关闭)
            if self.show_console:
                cmd.append("--console")
            else:
                cmd.append("--windowed")
            cmd += ["--name", name]
            cmd += ["--distpath", self.output_dir]
            cmd += ["--workpath", os.path.join(build_dir, "build")]
            cmd += ["--specpath", build_dir]
            cmd += ["--add-data", f"{PROJECT_FILE_NAME}{sep}."]
            cmd += ["--add-data", f"{ASSETS_DIR_NAME}{sep}{ASSETS_DIR_NAME}"]
            cmd += ["--paths", build_dir]
            # 确保多媒体插件 (音视频编解码) 一并打包
            cmd += ["--collect-all", "PySide6"]
            cmd += ["--collect-submodules", "galpy"]
            cmd += ["--clean", "--noconfirm"]
            cmd.append("game_main.py")

            self.log.emit("命令: " + " ".join(cmd))
            self.log.emit("工作目录: " + build_dir)

            # ---- 执行并实时输出 ----
            self.log.emit("[4/5] 正在打包, 请耐心等待…")
            # 强制子进程以 UTF-8 输出日志, 否则中文工程名 (如"游戏1") 在
            # 系统区域代码页 (如 cp1252) 下会被替换成 "??" 再被我们读到。
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"
            proc = subprocess.Popen(
                cmd, cwd=build_dir, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                bufsize=1,
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                self.log.emit(line.rstrip())
            ret = proc.wait()

            if ret != 0:
                self.finished_err.emit(f"PyInstaller 返回非零状态码: {ret}")
                return

            # ---- 定位产物 ----
            ext = ".exe" if os.name == "nt" else ""
            if self.onefile:
                exe = os.path.join(self.output_dir, name + ext)
            else:
                exe = os.path.join(self.output_dir, name, name + ext)
            self.log.emit("[5/5] 打包完成!")
            self.finished_ok.emit(exe)
        except FileNotFoundError:
            self.finished_err.emit(
                "未找到 PyInstaller。请先安装: pip install pyinstaller"
            )
        except Exception as e:
            self.finished_err.emit(f"打包失败:\n{e}\n{traceback.format_exc()}")


class PackageDialog(QDialog):
    """打包对话框: 配置选项 + 实时日志。"""

    def __init__(self, project: Project, project_path: str, parent=None):
        super().__init__(parent)
        self.project = project
        self.project_path = project_path
        self._worker: Optional[PackageWorker] = None
        self._exe_path: Optional[str] = None

        self.setWindowTitle(tr("action_pkg_full", "打包为桌面可执行程序 (.exe)"))
        self.resize(720, 520)

        # 选项
        self._title_edit = QLineEdit(project.title)
        self._output_edit = QLineEdit(os.path.join(os.path.dirname(project_path), "dist"))
        self._btn_browse = QPushButton(tr("btn_choose", "浏览…"))
        self._btn_browse.clicked.connect(self._browse_output)
        self._chk_onefile = QCheckBox(tr("package_onefile", "单文件模式 (--onefile)"))
        self._chk_onefile.setChecked(True)
        # 控制台窗口: 勾选=打包后 exe 启动时弹出黑色控制台 (调试用);
        # 不勾选=纯 GUI 窗口 (发布游戏推荐, 用户体验更干净)
        self._chk_console = QCheckBox(tr("package_console", "显示控制台窗口（调试时勾选；发布游戏建议关闭）"))
        self._chk_console.setChecked(False)

        form = QFormLayout()
        form.addRow(tr("package_game_name", "游戏名称:"), self._title_edit)
        out_row = QHBoxLayout()
        out_row.addWidget(self._output_edit, 1)
        out_row.addWidget(self._btn_browse)
        form.addRow(tr("package_output_dir", "输出目录:"), out_row)
        form.addRow("", self._chk_onefile)
        form.addRow("", self._chk_console)

        # 日志
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setStyleSheet(
            "QPlainTextEdit{background:#1e1e1e; color:#d4d4d4; font-family: Consolas, monospace;}"
        )

        # 按钮
        self._btn_start = QPushButton(tr("btn_start_package", "开始打包"))
        self._btn_start.setObjectName("PrimaryBtn")
        self._btn_start.clicked.connect(self._start)
        self._btn_open = QPushButton(tr("btn_open_output", "打开输出目录"))
        self._btn_open.setObjectName("SuccessBtn")
        self._btn_open.setEnabled(False)
        self._btn_open.clicked.connect(self._open_output)
        self._btn_close = QPushButton(tr("close", "关闭"))
        self._btn_close.clicked.connect(self.accept)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(QLabel(tr("package_log", "打包日志:")))
        lay.addWidget(self._log, 1)
        brow = QHBoxLayout()
        brow.addWidget(self._btn_start)
        brow.addStretch(1)
        brow.addWidget(self._btn_open)
        brow.addWidget(self._btn_close)
        lay.addLayout(brow)

    # ------------------------------------------------------------
    def _browse_output(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if d:
            self._output_edit.setText(d)

    def _start(self) -> None:
        out_dir = self._output_edit.text().strip()
        if not out_dir:
            QMessageBox.warning(self, "提示", "请选择输出目录。")
            return
        os.makedirs(out_dir, exist_ok=True)
        # 用编辑框中的名称覆盖工程标题 (仅用于打包命名)
        self.project.title = self._title_edit.text().strip() or self.project.title
        self.project.save(self.project_path)

        self._log.clear()
        self._btn_start.setEnabled(False)
        self._btn_open.setEnabled(False)

        self._worker = PackageWorker(
            self.project, self.project_path, out_dir,
            self._chk_onefile.isChecked(), self._chk_console.isChecked(), self,
        )
        self._worker.log.connect(self._append_log)
        self._worker.finished_ok.connect(self._on_ok)
        self._worker.finished_err.connect(self._on_err)
        self._worker.start()

    def _append_log(self, text: str) -> None:
        self._log.appendPlainText(text)

    def _on_ok(self, exe_path: str) -> None:
        self._exe_path = exe_path
        self._btn_start.setEnabled(True)
        self._btn_open.setEnabled(True)
        self._append_log(f"\n✅ 打包成功!\n产物: {exe_path}")
        QMessageBox.information(
            self, "打包完成",
            f"打包成功!\n\n可执行程序:\n{exe_path}\n\n双击即可运行, 无需安装任何库。"
        )

    def _on_err(self, msg: str) -> None:
        self._btn_start.setEnabled(True)
        self._append_log(f"\n❌ {msg}")
        QMessageBox.critical(self, "打包失败", msg)

    def _open_output(self) -> None:
        path = self._exe_path or self._output_edit.text()
        target = os.path.dirname(path) if os.path.isfile(path) else path
        if os.path.isdir(target):
            if os.name == "nt":
                os.startfile(target)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", target])
            else:
                subprocess.Popen(["xdg-open", target])
