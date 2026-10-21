@echo off
setlocal enabledelayedexpansion

REM ============================================
REM  多媒体播放器 一键构建脚本
REM  用法: build              (完整构建：onedir + onefile + zip)
REM        build clean        (清理构建产物)
REM        build onedir       (仅构建目录版)
REM        build onefile      (仅构建单文件版)
REM        build zip          (仅打包 zip)
REM        build norelease    (构建但不自动推送 Release)
REM ============================================

title 多媒体播放器 Build

REM 切换控制台编码为 UTF-8，使中文输出正常显示（必须在 title 之后，避免 cmd.exe /c 解析异常）
chcp 65001 >nul 2>nul

REM ---- SCRIPT_DIR / PROJECT_ROOT ----
for %%i in ("%~dp0.") do set "SCRIPT_DIR=%%~fi\"
for %%i in ("%~dp0..") do set "PROJECT_ROOT=%%~fi"

REM ---- pip 国内镜像源 ----
set "PIP_MIRROR=https://pypi.tuna.tsinghua.edu.cn/simple"

REM ---- 切换到项目根目录 ----
cd /d "%PROJECT_ROOT%"
if %ERRORLEVEL% neq 0 (
    echo [错误] 无法切换到项目目录: %PROJECT_ROOT%
    exit /b 1
)

REM ---- 读取版本号 ----
set "VERSION="
if exist "VERSION" (
    for /f "usebackq delims=" %%v in ("VERSION") do set "VERSION=%%v"
)
if not defined VERSION (
    echo [错误] 未找到 VERSION 文件
    exit /b 1
)
echo 当前版本: %VERSION%

REM ---- 构建配置 ----
set "APP_NAME=多媒体播放器"
set "APP_NAME_EN=MultimediaPlayer"
set "MAIN_SCRIPT=Player.py"

REM ---- Release 推送开关 ----
if not defined SKIP_RELEASE set "SKIP_RELEASE=0"
if not "%~1"=="" for %%a in (%*) do if /i "%%a"=="norelease" set "SKIP_RELEASE=1"

REM ---- 路由到具体任务 ----
if /i "%~1"=="clean"   goto :clean
if /i "%~1"=="onedir"  goto :build_onedir
if /i "%~1"=="onefile" goto :build_onefile
if /i "%~1"=="zip"     goto :build_zip
goto :build_all

REM ============================================
REM  完整构建
REM ============================================
:build_all
echo.
echo ============================================
echo  完整构建 - %date% %time%
echo ============================================

call :checkenv
if !ERRORLEVEL! neq 0 exit /b 1

call :build_onedir
if !ERRORLEVEL! neq 0 exit /b 1

call :build_onefile
if !ERRORLEVEL! neq 0 exit /b 1

call :build_zip
if !ERRORLEVEL! neq 0 exit /b 1

call :print_summary

if "!SKIP_RELEASE!"=="0" (
    echo.
    echo 正在推送 Release...
    call "%SCRIPT_DIR%push_release.bat"
)

goto :end

REM ============================================
REM  环境检查
REM ============================================
:checkenv
echo.
echo [检查环境]...

where python >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo [错误] 未找到 Python
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do echo        Python: %%v

where pyinstaller >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo [警告] 未找到 pyinstaller，尝试安装...
    pip install pyinstaller -i %PIP_MIRROR% --trusted-host pypi.tuna.tsinghua.edu.cn
    if !ERRORLEVEL! neq 0 (
        echo [错误] pyinstaller 安装失败
        exit /b 1
    )
)
echo        PyInstaller: OK

echo        [pip] 检查更新...
python -m pip install --upgrade pip -i %PIP_MIRROR% --trusted-host pypi.tuna.tsinghua.edu.cn
if !ERRORLEVEL! neq 0 (
    echo [警告] pip 更新失败，继续...
)

if exist "requirement.txt" (
    echo        [依赖] 安装 requirement.txt（PyQt5/OpenCV 较大，请耐心等待）...
    pip install -r requirement.txt -i %PIP_MIRROR% --trusted-host pypi.tuna.tsinghua.edu.cn
    if !ERRORLEVEL! neq 0 (
        echo [警告] 部分依赖安装失败，尝试继续...
    ) else (
        echo        [依赖] 安装完成
    )
)
exit /b 0

REM ============================================
REM  构建 onedir（目录版，用于 zip 分发）
REM ============================================
:build_onedir
echo.
echo ============================================
echo  构建目录版 (onedir)
echo ============================================

REM 检查 ffmpeg
set "FFMPEG_PATH=libs\ffmpeg\ffmpeg.exe"
if not exist "%FFMPEG_PATH%" (
    echo [警告] 未找到 %FFMPEG_PATH%，构建可能缺少 ffmpeg
)

echo 清理旧的 onedir 构建产物...
if exist "build" rd /s /q "build" 2>nul
if exist "dist\%APP_NAME%" rd /s /q "dist\%APP_NAME%" 2>nul
del "%APP_NAME%.spec" 2>nul

echo 开始打包 onedir...
pyinstaller -D -w --clean --hidden-import=loguru --contents-directory "libs" --add-data="%FFMPEG_PATH%;ffmpeg" --name "%APP_NAME%" "%MAIN_SCRIPT%"
if !ERRORLEVEL! neq 0 (
    echo [错误] onedir 构建失败！
    exit /b 1
)

echo onedir 构建完成: dist\%APP_NAME%\
exit /b 0

REM ============================================
REM  构建 onefile（单文件独立运行版）
REM ============================================
:build_onefile
echo.
echo ============================================
echo  构建单文件版 (onefile)
echo ============================================

REM 检查 ffmpeg
set "FFMPEG_PATH=libs\ffmpeg\ffmpeg.exe"
if not exist "%FFMPEG_PATH%" (
    echo [警告] 未找到 %FFMPEG_PATH%，构建可能缺少 ffmpeg
)

echo 清理旧的 onefile 构建产物...
if exist "build" rd /s /q "build" 2>nul
if exist "dist\%APP_NAME%.exe" del "dist\%APP_NAME%.exe" 2>nul
del "%APP_NAME%.spec" 2>nul

echo 开始打包 onefile...
pyinstaller -F -w --clean --hidden-import=loguru --add-data="%FFMPEG_PATH%;ffmpeg" --name "%APP_NAME%" "%MAIN_SCRIPT%"
if !ERRORLEVEL! neq 0 (
    echo [错误] onefile 构建失败！
    exit /b 1
)

REM 重命名输出文件，加上版本号
set "ONEFILE_DEST=dist\%APP_NAME%_v%VERSION%.exe"
if exist "dist\%APP_NAME%.exe" (
    move /y "dist\%APP_NAME%.exe" "%ONEFILE_DEST%" >nul 2>&1
    echo onefile 构建完成: %ONEFILE_DEST%
) else (
    echo [错误] onefile 输出文件未生成
    exit /b 1
)
exit /b 0

REM ============================================
REM  打包 zip（压缩目录版）
REM ============================================
:build_zip
echo.
echo ============================================
echo  打包 ZIP
echo ============================================

set "ZIP_DEST=dist\%APP_NAME%_v%VERSION%.zip"

if not exist "dist\%APP_NAME%" (
    echo [错误] 未找到 dist\%APP_NAME%\，请先执行 onedir 构建
    exit /b 1
)

REM 删除旧 zip
if exist "%ZIP_DEST%" del "%ZIP_DEST%" 2>nul

echo 正在打包 %ZIP_DEST%...
powershell -NoProfile -Command "Compress-Archive -Path 'dist\%APP_NAME%' -DestinationPath '%ZIP_DEST%' -Force"
if !ERRORLEVEL! neq 0 (
    echo [错误] ZIP 打包失败！
    exit /b 1
)

for %%f in ("%ZIP_DEST%") do set "ZIP_SIZE=%%~zf"
echo ZIP 打包完成: %ZIP_DEST% (!ZIP_SIZE! bytes)
exit /b 0

REM ============================================
REM  清理
REM ============================================
:clean
echo.
echo ============================================
echo  清理构建产物
echo ============================================
if exist "build" (
    rd /s /q "build" 2>nul
    echo 已删除 build\
)
if exist "dist" (
    rd /s /q "dist" 2>nul
    echo 已删除 dist\
)
del *.spec 2>nul
echo 清理完成
goto :end

REM ============================================
REM  打印构建摘要
REM ============================================
:print_summary
echo.
echo ============================================
echo  构建摘要
echo ============================================
echo  版本: %VERSION%
echo  产物:
if exist "dist\%APP_NAME%_v%VERSION%.zip" (
    for %%f in ("dist\%APP_NAME%_v%VERSION%.zip") do echo    [ZIP]  %%~nxf  (%%~zf bytes)
)
if exist "dist\%APP_NAME%_v%VERSION%.exe" (
    for %%f in ("dist\%APP_NAME%_v%VERSION%.exe") do echo    [EXE]  %%~nxf  (%%~zf bytes)
)
echo ============================================

exit /b 0

REM ============================================
REM  结束
REM ============================================
:end
echo.
echo 构建完成，窗口将在 30 秒后关闭，或按任意键...
timeout /t 30 > nul
exit /b 0