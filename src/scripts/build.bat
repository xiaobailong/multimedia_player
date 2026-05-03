@echo off
chcp 65001 >nul

set "ROOT_DIR=%~dp0..\.."
set "MAIN_DIR=%ROOT_DIR%\src\main"
set "FFMPEG_DIR=%ROOT_DIR%\libs\ffmpeg"
set "VENV_PYTHON=%ROOT_DIR%\.venv\Scripts\python.exe"

echo ROOT_DIR=%ROOT_DIR%
echo MAIN_DIR=%MAIN_DIR%
echo FFMPEG_DIR=%FFMPEG_DIR%

:: 清理旧的构建产物
if exist "%ROOT_DIR%\dist" rd /s/q "%ROOT_DIR%\dist"
if exist "%ROOT_DIR%\build" rd /s/q "%ROOT_DIR%\build"

:: 在根目录执行 pyinstaller，确保 src.core / src.layout 等导入路径正确
cd /d "%ROOT_DIR%"

"%VENV_PYTHON%" -m PyInstaller -D -w --clean ^
  --hidden-import=loguru ^
  --contents-directory "libs" ^
  --add-data "%FFMPEG_DIR%\ffmpeg.exe;ffmpeg" ^
  "%MAIN_DIR%\Player.py"

:: 复制 ffmpeg 到打包目录
if exist "%ROOT_DIR%\dist\Player\libs\ffmpeg" (
  copy /y "%FFMPEG_DIR%\ffmpeg.exe" "%ROOT_DIR%\dist\Player\libs\ffmpeg\"
)

echo.
echo ====== 打包完成 ======
echo 输出目录: %ROOT_DIR%\dist\Player
pause
