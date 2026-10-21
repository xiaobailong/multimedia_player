@echo off
chcp 65001 >nul 2>nul
setlocal enabledelayedexpansion

REM ============================================
REM  MultimediaPlayer One-Click Build Script
REM  Usage: build [clean|onedir|onefile|zip|norelease|nobump]
REM ============================================

REM ---- SCRIPT_DIR / PROJECT_ROOT ----
for %%i in ("%~dp0.") do set "SCRIPT_DIR=%%~fi\"
for %%i in ("%~dp0..") do set "PROJECT_ROOT=%%~fi\"

REM ============================================
REM  PASS 1: Tee stdout to console + build\build_full.log
REM  When no --log arg, re-invoke self via PowerShell pipe
REM ============================================
if "%~1" NEQ "--log" (
    if not exist "%PROJECT_ROOT%build" mkdir "%PROJECT_ROOT%build" 2>nul
    powershell -NoProfile -Command ^
        "$OutputEncoding = [Console]::OutputEncoding = [Console]::InputEncoding = [Text.Encoding]::UTF8; " ^
        "$utf8NoBom = [Text.UTF8Encoding]::new($false); " ^
        "$sw = [System.IO.StreamWriter]::new('%PROJECT_ROOT%build\build_full.log', $false, $utf8NoBom); $sw.AutoFlush = $true; " ^
        "try { cmd /c '%~f0 --log %*' 2>&1 | ForEach-Object { Write-Host $_; $sw.WriteLine($_) } } finally { $sw.Close(); exit $LASTEXITCODE }"
    exit /b
) else (
    shift
)

REM ============================================
REM  PASS 2: Build logic (only in --log mode)
REM ============================================

title 多媒体播放器 Build

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

REM ---- Release 推送开关 ----
if not defined SKIP_RELEASE set "SKIP_RELEASE=0"
if not "%~1"=="" for %%a in (%*) do if /i "%%a"=="norelease" set "SKIP_RELEASE=1"

REM ---- 版本号递增开关 ----
if not defined SKIP_BUMP set "SKIP_BUMP=0"
if not "%~1"=="" for %%a in (%*) do if /i "%%a"=="nobump" set "SKIP_BUMP=1"

REM ---- 路由到具体任务（clean 不需要 bump，先路由）----
if /i "%~1"=="clean"   goto :clean

REM ---- 统一版本号递增（所有构建目标共享，仅此一次）----
if "!SKIP_BUMP!"=="0" (
    call :bump_version
)

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
    REM where 可能因 pyinstaller 装在用户目录而找不到，用 pip 兜底
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

REM ---- 辅助脚本自检 ----
if not exist "%SCRIPT_DIR%tools\bump_version.ps1" (
    echo [错误] 缺少版本号更新脚本: %SCRIPT_DIR%tools\bump_version.ps1
    echo        可从 git 恢复: git checkout scripts\tools\bump_version.ps1
    goto :eof
)

REM ---- 更新 VERSION：最后一段 +1 ----
REM  必须用 -File 调脚本，不能用 powershell -Command 一行式！
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%tools\bump_version.ps1" -Path "%PROJECT_ROOT%VERSION"

REM ---- 回读校验：版本号必须真的变了 ----
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

REM 更新当前会话中的 VERSION 变量
set "VERSION=!NEW_VER!"
echo        版本号已更新: %VERSION%

REM 重新读取 VERSION 到当前会话（供后续构建使用）
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
REM  构建 onedir（目录版，用于 zip 分发）
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
REM  构建 onefile（单文件独立运行版）
REM ============================================
:build_onefile
echo.
echo ============================================
echo  构建单文件版 (onefile)
echo ============================================

call :ensure_ffmpeg

if not exist "build\dist\onefile" mkdir "build\dist\onefile" 2>nul

echo 清理旧的 onefile 构建产物...
if exist "build\dist\onefile\%APP_NAME%.exe" del "build\dist\onefile\%APP_NAME%.exe" 2>nul
if exist "build\dist\onefile\%APP_NAME%_v%VERSION%.exe" del "build\dist\onefile\%APP_NAME%_v%VERSION%.exe" 2>nul
if exist "build\dist\onefile\%APP_NAME_EN%_v%VERSION%.exe" del "build\dist\onefile\%APP_NAME_EN%_v%VERSION%.exe" 2>nul

echo 开始打包 onefile...
python -m PyInstaller -F -w --clean --distpath "build\dist\onefile" --workpath "build\pyi-work" --specpath "build" --hidden-import=loguru --add-data="%PROJECT_ROOT%%FFMPEG_TARGET%;ffmpeg" --name "%APP_NAME%" "%MAIN_SCRIPT%"
if !ERRORLEVEL! neq 0 (
    echo [错误] onefile 构建失败！
    exit /b 1
)

REM 重命名输出文件，加上版本号（使用英文前缀，避免 GitHub Release 中文名丢失）
set "ONEFILE_DEST=build\dist\onefile\%APP_NAME_EN%_v%VERSION%.exe"
if exist "build\dist\onefile\%APP_NAME%.exe" (
    move /y "build\dist\onefile\%APP_NAME%.exe" "%ONEFILE_DEST%" >nul 2>&1
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

REM 打包 zip（使用英文前缀，避免 GitHub Release 中文名丢失）
set "ZIP_DEST=build\dist\%APP_NAME_EN%_v%VERSION%.zip"

if not exist "build\dist\%APP_NAME%" (
    echo [错误] 未找到 build\dist\%APP_NAME%\，请先执行 onedir 构建
    exit /b 1
)

REM 删除旧 zip（兼容中英文前缀）
if exist "%ZIP_DEST%" del "%ZIP_DEST%" 2>nul
if exist "build\dist\%APP_NAME%_v%VERSION%.zip" del "build\dist\%APP_NAME%_v%VERSION%.zip" 2>nul

echo 正在打包 %ZIP_DEST%...
powershell -NoProfile -Command "Compress-Archive -Path 'build\dist\%APP_NAME%' -DestinationPath '%ZIP_DEST%' -Force"
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
REM 清理根目录散落的 .spec 文件
for %%f in ("*.spec") do del "%%f" 2>nul
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
if exist "build\dist\%APP_NAME_EN%_v%VERSION%.zip" (
    for %%f in ("build\dist\%APP_NAME_EN%_v%VERSION%.zip") do echo    [ZIP]  %%~nxf  (%%~zf bytes)
)
if exist "build\dist\onefile\%APP_NAME_EN%_v%VERSION%.exe" (
    for %%f in ("build\dist\onefile\%APP_NAME_EN%_v%VERSION%.exe") do echo    [EXE]  %%~nxf  (%%~zf bytes)
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