@echo off
chcp 65001 >nul

set "ROOT_DIR=%~dp0..\.."
set "MAIN_DIR=%ROOT_DIR%\src\main"
set "FFMPEG_DIR=%ROOT_DIR%\libs\ffmpeg"
set "VENV_PYTHON=%ROOT_DIR%\.venv\Scripts\python.exe"

echo ROOT_DIR=%ROOT_DIR%
echo MAIN_DIR=%MAIN_DIR%
echo FFMPEG_DIR=%FFMPEG_DIR%

:: 清理旧的构建产物（如果有文件被锁定则跳过）
if exist "%ROOT_DIR%\dist" (
  rd /s/q "%ROOT_DIR%\dist" 2>nul
  if exist "%ROOT_DIR%\dist" echo 警告: 无法完全清理 dist 目录（可能有文件被占用），将使用 --noconfirm 覆盖
)
if exist "%ROOT_DIR%\build" rd /s/q "%ROOT_DIR%\build"

:: 在根目录执行 pyinstaller，确保 src.core / src.layout 等导入路径正确
cd /d "%ROOT_DIR%"

"%VENV_PYTHON%" -m PyInstaller -D -w --clean --noconfirm ^
  --distpath "%ROOT_DIR%\dist_temp" ^
  --hidden-import=loguru ^
  --hidden-import=send2trash ^
  --hidden-import=apsw ^
  --hidden-import=vlc ^
  --contents-directory "libs" ^
  --add-data "%FFMPEG_DIR%\ffmpeg.exe;ffmpeg" ^
  "%MAIN_DIR%\Player.py"

:: PyInstaller 输出到 dist_temp\Player，将其移到最终目录
if exist "%ROOT_DIR%\dist_temp\Player" (
  :: 尝试清理旧 dist（如果被锁定可能失败）
  if exist "%ROOT_DIR%\dist\Player" (
    rd /s/q "%ROOT_DIR%\dist\Player" 2>nul
  )
  :: 重命名 temp 为最终目录
  move /y "%ROOT_DIR%\dist_temp\Player" "%ROOT_DIR%\dist\Player" >nul 2>&1
  if not exist "%ROOT_DIR%\dist\Player" (
    :: move 可能因权限失败，用 robocopy 回退
    if exist "%ROOT_DIR%\dist_temp\Player" (
      robocopy "%ROOT_DIR%\dist_temp\Player" "%ROOT_DIR%\dist\Player" /E /MOV /NP /NFL /NDL /NJH /NJS /R:2 /W:1 >nul 2>&1
    )
  )
)

:: 清理 dist_temp
if exist "%ROOT_DIR%\dist_temp" rd /s/q "%ROOT_DIR%\dist_temp" 2>nul

:: 复制 ffmpeg 到打包目录
if exist "%ROOT_DIR%\dist\Player\libs\ffmpeg" (
  copy /y "%FFMPEG_DIR%\ffmpeg.exe" "%ROOT_DIR%\dist\Player\libs\ffmpeg\"
)

:: 复制 VLC DLL 到打包目录（用于硬件加速）
set "VLC_INSTALL_DIR=C:\Program Files\VideoLAN\VLC"
if exist "%VLC_INSTALL_DIR%\libvlc.dll" (
  echo 检测到 VLC 已安装，正在复制 VLC DLL...
  if not exist "%ROOT_DIR%\dist\Player\vlc" mkdir "%ROOT_DIR%\dist\Player\vlc"
  copy /y "%VLC_INSTALL_DIR%\libvlc.dll" "%ROOT_DIR%\dist\Player\vlc\"
  copy /y "%VLC_INSTALL_DIR%\libvlccore.dll" "%ROOT_DIR%\dist\Player\vlc\"
  :: 用 robocopy 复制 plugins 目录（跳过权限问题）
  robocopy "%VLC_INSTALL_DIR%\plugins" "%ROOT_DIR%\dist\Player\vlc\plugins" /E /NP /NFL /NDL /NJH /NJS /R:2 /W:1 >nul 2>&1
  echo VLC DLL 复制完成
) else (
  echo 未检测到 VLC 安装，跳过 VLC DLL 复制
)

echo.
echo ====== 打包完成 ======
echo 输出目录: %ROOT_DIR%\dist\Player
pause
