@echo off
chcp 65001 >nul 2>nul
setlocal enabledelayedexpansion

REM ============================================
REM  MultimediaPlayer OneDir Build Script
REM  Usage: build_onedir [nobump]
REM ============================================

REM ---- SCRIPT_DIR / PROJECT_ROOT ----
for %%i in ("%~dp0.") do set "SCRIPT_DIR=%%~fi\"
for %%i in ("%~dp0..") do set "PROJECT_ROOT=%%~fi\"

REM ============================================
REM  PASS 1: Tee stdout to console + build\build_onedir.log
REM  When no --log arg, re-invoke self via PowerShell pipe
REM ============================================
if "%~1" NEQ "--log" (
    if not exist "%PROJECT_ROOT%build" mkdir "%PROJECT_ROOT%build" 2>nul
    powershell -NoProfile -Command ^
        "$OutputEncoding = [Console]::OutputEncoding = [Console]::InputEncoding = [Text.Encoding]::UTF8; " ^
        "$utf8NoBom = [Text.UTF8Encoding]::new($false); " ^
        "$sw = [System.IO.StreamWriter]::new('%PROJECT_ROOT%build\build_onedir.log', $false, $utf8NoBom); $sw.AutoFlush = $true; " ^
        "try { cmd /c '%~f0 --log %*' 2>&1 | ForEach-Object { Write-Host $_; $sw.WriteLine($_) } } finally { $sw.Close(); exit $LASTEXITCODE }"
    exit /b
) else (
    shift
)

REM ============================================
REM  PASS 2: Build logic (only in --log mode)
REM ============================================

title 多媒体播放器 Build (OneDir)

REM ---- 切换到项目根目录 ----
cd /d "%PROJECT_ROOT%"
if !ERRORLEVEL! neq 0 (
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

REM ---- 参数解析 ----
if not defined SKIP_BUMP set "SKIP_BUMP=0"
if not "%~1"=="" for %%a in (%*) do if /i "%%a"=="nobump" set "SKIP_BUMP=1"

REM ---- 版本号递增 ----
if "!SKIP_BUMP!"=="0" (
    call :bump_version
)

REM ============================================
REM  构建 onedir
REM ============================================

call :checkenv
if !ERRORLEVEL! neq 0 exit /b 1

call :build_onedir
if !ERRORLEVEL! neq 0 exit /b 1

call :print_summary

echo.
echo 构建完成，窗口将在 30 秒后关闭，或按任意键...
timeout /t 30 > nul
exit /b 0

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
    python -m pip show pyinstaller >nul 2>&1
    if !ERRORLEVEL! neq 0 (
        echo [警告] 未找到 pyinstaller，尝试安装...
        pip install pyinstaller -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
        if !ERRORLEVEL! neq 0 (
            echo [错误] pyinstaller 安装失败
            exit /b 1
        )
    )
)
echo        PyInstaller: OK

echo        [pip] 检查更新...
python -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
if !ERRORLEVEL! neq 0 (
    echo [警告] pip 更新失败，继续...
)

if exist "requirement.txt" (
    echo        [依赖] 安装 requirement.txt（PyQt5/OpenCV 较大，请耐心等待）...
    pip install -r requirement.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
    if !ERRORLEVEL! neq 0 (
        echo [警告] 部分依赖安装失败，尝试继续...
    ) else (
        echo        [依赖] 安装完成
    )
)
exit /b 0

REM ============================================
REM  版本号递增（每次构建自动 +1 patch）
REM ============================================
:bump_version
if "!SKIP_BUMP!"=="1" (
    echo        [版本] 跳过版本号递增（nobump）
    goto :eof
)

echo        [版本] 递增版本号...

if not exist "%PROJECT_ROOT%VERSION" (
    echo [错误] 未找到 VERSION 文件
    goto :eof
)

if not exist "%SCRIPT_DIR%tools\bump_version.ps1" (
    echo [错误] 缺少版本号更新脚本: %SCRIPT_DIR%tools\bump_version.ps1
    echo        可从 git 恢复: git checkout scripts\tools\bump_version.ps1
    goto :eof
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%tools\bump_version.ps1" -Path "%PROJECT_ROOT%VERSION"

set "NEW_VER="
for /f "usebackq delims=" %%v in ("%PROJECT_ROOT%VERSION") do set "NEW_VER=%%v"
if not defined NEW_VER (
    echo [错误] VERSION 版本号未更新
    goto :eof
)
if "!NEW_VER!"=="%VERSION%" (
    echo [错误] VERSION 版本号未递增：仍是 %VERSION%
    echo        排查：手动修改 VERSION 文件
    goto :eof
)

set "VERSION=!NEW_VER!"
echo        版本号已更新: %VERSION%

for /f "usebackq delims=" %%v in ("%PROJECT_ROOT%VERSION") do set "VERSION=%%v"
goto :eof

REM ============================================
REM  确保 ffmpeg.exe 就位（构建必须依赖）
REM ============================================
:ensure_ffmpeg
set "FFMPEG_TARGET=libs\ffmpeg\ffmpeg.exe"
set "FFMPEG_SOURCE=D:\Tools\DevTools\base\ffmpeg-master-latest-win64-gpl\bin\ffmpeg.exe"

if exist "%FFMPEG_TARGET%" goto :eof

if not exist "%FFMPEG_SOURCE%" (
    echo [警告] 未找到 %FFMPEG_TARGET%，也未找到本机 ffmpeg
    echo        %FFMPEG_SOURCE%
    echo        构建可能缺少 ffmpeg 依赖
    goto :eof
)

echo [ffmpeg] 未找到 %FFMPEG_TARGET%，从本机拷贝...
if not exist "libs\ffmpeg" mkdir "libs\ffmpeg" 2>nul
copy /y "%FFMPEG_SOURCE%" "%FFMPEG_TARGET%" >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo [错误] ffmpeg 拷贝失败
    exit /b 1
)
echo [ffmpeg] 拷贝完成: %FFMPEG_TARGET%
goto :eof

REM ============================================
REM  构建 onedir（目录版）
REM ============================================
:build_onedir
echo.
echo ============================================
echo  构建目录版 (onedir)
echo ============================================

call :ensure_ffmpeg

echo 清理旧的 onedir 构建产物...
if exist "build\dist\%APP_NAME%" rd /s /q "build\dist\%APP_NAME%" 2>nul

echo 开始打包 onedir...
python -m PyInstaller -D -w --clean --distpath "build\dist" --workpath "build\pyi-work" --specpath "build" --hidden-import=loguru --contents-directory "libs" --add-data="%PROJECT_ROOT%%FFMPEG_TARGET%;ffmpeg" --name "%APP_NAME%" "%MAIN_SCRIPT%"
if !ERRORLEVEL! neq 0 (
    echo [错误] onedir 构建失败！
    exit /b 1
)

echo onedir 构建完成: build\dist\%APP_NAME%\
exit /b 0

REM ============================================
REM  打印构建摘要
REM ============================================
:print_summary
echo.
echo ============================================
echo  构建摘要
echo ============================================
echo  版本: %VERSION%
echo  模式: onedir（目录版）
echo  产物:
if exist "build\dist\%APP_NAME%" (
    echo    [DIR]  build\dist\%APP_NAME%\
)
echo ============================================

exit /b 0