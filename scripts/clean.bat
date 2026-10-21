@echo off
setlocal enabledelayedexpansion

REM ============================================
REM  多媒体播放器 构建产物清理脚本
REM  用法: clean
REM ============================================

REM ---- SCRIPT_DIR / PROJECT_ROOT ----
for %%i in ("%~dp0.") do set "SCRIPT_DIR=%%~fi\"
for %%i in ("%~dp0..") do set "PROJECT_ROOT=%%~fi\"

REM ---- 切换到项目根目录 ----
cd /d "%PROJECT_ROOT%"
if !ERRORLEVEL! neq 0 (
    echo [错误] 无法切换到项目目录: %PROJECT_ROOT%
    exit /b 1
)

title 多媒体播放器 Clean

echo.
echo ============================================
echo  清理构建产物
echo ============================================

REM ---- 清理 build 目录 ----
if exist "build" (
    rd /s /q "build" 2>nul
    if !ERRORLEVEL! equ 0 (
        echo [OK] 已删除 build\
    ) else (
        echo [信息] build\ 部分文件被占用，已跳过
    )
) else (
    echo [跳过] build\ 不存在
)

REM ---- 清理根目录散落的 spec 文件 ----
set "HAS_SPEC=0"
for %%f in ("*.spec") do (
    set "HAS_SPEC=1"
    echo [OK] 已删除 %%~nxf
    del "%%f" 2>nul
)
if "!HAS_SPEC!"=="0" echo [跳过] 无 .spec 文件

echo.
echo ============================================
echo  清理完成
echo ============================================

goto :end

:end
exit /b 0