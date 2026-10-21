@echo off
REM ============================================
REM  smartops-agent 调试入口（Windows 专用）
REM  用法:  run.bat <python参数>
REM  示例:  run.bat main.py
REM          run.bat -m src.evaluation.evaluate
REM ============================================
cd /d "%~dp0"

set "HF_HUB_OFFLINE=1"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

.venv\Scripts\python.exe %*
