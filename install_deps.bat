@echo off
chcp 65001 >nul
echo 正在安装 DeepSeek Web Search Skill 依赖...
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 install_dependencies.py
) else (
    python install_dependencies.py
)

echo.
pause
