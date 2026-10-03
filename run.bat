@echo off
REM ============================================================
REM  GalPy 启动脚本 (Windows)
REM  双击即可运行; 也可命令行: run.bat [launcher|edit|play ...]
REM
REM  解释器选择优先级:
REM    1) 工程内虚拟环境  (.venv / venv)
REM    2) py 启动器        (py -3)  <- 规避 "Python 未找到 / 应用商店别名"
REM    3) 系统 python
REM ============================================================
setlocal
cd /d "%~dp0"

REM 0) 显式覆盖: set GALPY_PY=你的虚拟环境\Scripts\python.exe
if defined GALPY_PY (
    "%GALPY_PY%" main.py %*
    goto :done
)

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" main.py %*
    goto :done
)
if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" main.py %*
    goto :done
)

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 main.py %*
    goto :done
)

python main.py %*

:done
if %errorlevel%==9009 (
    echo.
    echo [错误] 未找到 Python 解释器。
    echo 请安装 Python 3.9+ (勾选 Add to PATH) 或创建虚拟环境:
    echo     py -m venv .venv
    echo     .venv\Scripts\activate
    echo     pip install -r requirements.txt
    echo 然后再次运行 run.bat
    pause
)
endlocal
