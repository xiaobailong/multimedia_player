@echo off
chcp 65001 >nul 2>nul
setlocal enabledelayedexpansion

title 多媒体播放器 Release Push

set "GH_EXE="

REM ---- SCRIPT_DIR / PROJECT_ROOT ----
for %%i in ("%~dp0.") do set "SCRIPT_DIR=%%~fi\"
for %%i in ("%~dp0..") do set "PROJECT_ROOT=%%~fi"

cd /d "%PROJECT_ROOT%"
if %ERRORLEVEL% neq 0 (
    set "ERR_MSG=无法切换到项目目录: %PROJECT_ROOT%"
    goto :die
)

REM ---- 读取版本号 ----
set "VERSION="
if not exist "VERSION" (
    set "ERR_MSG=未找到 VERSION 文件"
    goto :die
)
for /f "usebackq delims=" %%v in ("VERSION") do set "VERSION=%%v"
if not defined VERSION (
    set "ERR_MSG=无法从 VERSION 文件读取版本号"
    goto :die
)
echo 当前版本: !VERSION!

REM ---- 检查构建产物 ----
set "APP_NAME=多媒体播放器"
set "APP_NAME_EN=MultimediaPlayer"
set "ZIP_FILE=build\dist\!APP_NAME_EN!_v!VERSION!.zip"
set "EXE_FILE=build\dist\onefile\!APP_NAME_EN!_v!VERSION!.exe"

set "HAS_ZIP=0"
set "HAS_EXE=0"
if exist "!ZIP_FILE!" set "HAS_ZIP=1"
if exist "!EXE_FILE!" set "HAS_EXE=1"

if "!HAS_ZIP!"=="0" if "!HAS_EXE!"=="0" (
    set "ERR_MSG=未找到构建产物。请先执行 scripts\build.bat 完成构建"
    goto :die
)

if "!HAS_ZIP!"=="1" (
    for %%f in ("!ZIP_FILE!") do set "ZIP_SIZE=%%~zf"
    echo ZIP: !ZIP_FILE! (!ZIP_SIZE! bytes)
)
if "!HAS_EXE!"=="1" (
    for %%f in ("!EXE_FILE!") do set "EXE_SIZE=%%~zf"
    echo EXE: !EXE_FILE! (!EXE_SIZE! bytes)
)

REM ---- 定位 gh CLI ----
:resolve_gh
if defined GH_EXE if exist "!GH_EXE!" goto :gh_found
set "GH_EXE="
for /f "delims=" %%g in ('where gh 2^>nul') do if not defined GH_EXE set "GH_EXE=%%g"
if not defined GH_EXE if exist "%ProgramFiles%\GitHub CLI\gh.exe" set "GH_EXE=%ProgramFiles%\GitHub CLI\gh.exe"
if not defined GH_EXE if exist "%ProgramFiles(x86)%\GitHub CLI\gh.exe" set "GH_EXE=%ProgramFiles(x86)%\GitHub CLI\gh.exe"
if not defined GH_EXE if exist "%LOCALAPPDATA%\Programs\GitHub CLI\gh.exe" set "GH_EXE=%LOCALAPPDATA%\Programs\GitHub CLI\gh.exe"
if not defined GH_EXE if exist "%USERPROFILE%\scoop\shims\gh.exe" set "GH_EXE=%USERPROFILE%\scoop\shims\gh.exe"
if defined GH_EXE goto :gh_found
set "ERR_MSG=未找到 gh CLI。安装: winget install --id GitHub.cli"
goto :die

:gh_found
echo gh: !GH_EXE!

REM ---- 检查 gh 登录状态（重试 3 次，应对 Windows 凭据管理器间歇性超时） ----
set "GH_AUTH_FILE=%TEMP%\mediaplayer_gh_auth.txt"
set "GH_LOGGED_IN=0"
set "GH_RETRY=0"

:auth_retry
set /a "GH_RETRY+=1"
"%GH_EXE%" auth status > "%GH_AUTH_FILE%" 2>&1
set "GH_AUTH_RC=!ERRORLEVEL!"

if !GH_AUTH_RC! equ 0 set "GH_LOGGED_IN=1"
for /f "tokens=*" %%l in ('findstr /i "Logged.in" "%GH_AUTH_FILE%" 2^>nul') do set "GH_LOGGED_IN=1"

if "!GH_LOGGED_IN!"=="1" goto :auth_ok
if !GH_RETRY! lss 3 (
    echo        gh auth keyring 超时，重试 !GH_RETRY!/3...
    timeout /t 2 >nul
    goto :auth_retry
)

del "%GH_AUTH_FILE%" 2>nul
set "ERR_MSG=gh 未登录。请执行: gh auth login"
goto :die

:auth_ok
set "GH_HAS_REPO_SCOPE=0"
echo        gh 已登录

REM ---- 检查 token scope ----
for /f "tokens=*" %%l in ('findstr /i "Token.scopes" "%GH_AUTH_FILE%" 2^>nul') do set "TOKEN_LINE=%%l"
if defined TOKEN_LINE (
    echo "!TOKEN_LINE!" | findstr /i "repo" >nul 2>&1
    if !ERRORLEVEL! equ 0 set "GH_HAS_REPO_SCOPE=1"
)
del "%GH_AUTH_FILE%" 2>nul
set "GH_AUTH_FILE="

if "!GH_HAS_REPO_SCOPE!"=="0" (
    set "ERR_MSG=gh token 缺少 repo scope。授权: gh auth refresh -h github.com -s repo"
    goto :die
)
echo        token 包含 repo scope

REM ---- 解析仓库 owner/repo ----
set "RELEASE_SLUG="
for /f "delims=" %%u in ('git config --get remote.origin.url 2^>nul') do set "REMOTE_URL=%%u"
if not defined REMOTE_URL (
    set "ERR_MSG=无 remote.origin，无法确定目标仓库"
    goto :die
)
set "REMOTE_TAIL=!REMOTE_URL:*github.com:=!"
if "!REMOTE_TAIL!"=="!REMOTE_URL!" set "REMOTE_TAIL=!REMOTE_URL:*github.com/=!"
set "REMOTE_TAIL=!REMOTE_TAIL:.git=!"
for /f "tokens=1,2 delims=/" %%a in ("!REMOTE_TAIL!") do if not "%%b"=="" set "RELEASE_SLUG=%%a/%%b"
if not defined RELEASE_SLUG (
    set "ERR_MSG=无法解析 remote.origin 为 GitHub owner/repo"
    goto :die
)
echo 仓库: !RELEASE_SLUG!
set "REL_REPO_ARG=--repo !RELEASE_SLUG!"

REM ---- 当前 HEAD 信息 ----
set "GIT_SHA="
set "GIT_SHA_SHORT="
set "GIT_DESC="
set "GIT_BRANCH="
for /f "delims=" %%c in ('git rev-parse HEAD 2^>nul') do set "GIT_SHA=%%c"
for /f "delims=" %%c in ('git rev-parse --short HEAD 2^>nul') do set "GIT_SHA_SHORT=%%c"
for /f "delims=" %%c in ('git log -1 --oneline 2^>nul') do set "GIT_DESC=%%c"
for /f "delims=" %%c in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set "GIT_BRANCH=%%c"
if not defined GIT_SHA (
    set "ERR_MSG=无 git 提交记录"
    goto :die
)
echo 分支: !GIT_BRANCH!
echo 提交: !GIT_DESC!

REM ---- 检查 Release 是否已存在且资产完整 ----
set "RELEASE_TAG=v!VERSION!"
set "ALREADY_PUBLISHED=0"
set "GH_REL_FILE=%TEMP%\mediaplayer_gh_rel.txt"
"%GH_EXE%" release view "!RELEASE_TAG!" --json assets,isDraft !REL_REPO_ARG! > "!GH_REL_FILE!" 2>nul
if !ERRORLEVEL! equ 0 (
    set "ZIP_ASSET_OK=0"
    set "EXE_ASSET_OK=0"
    set "IS_DRAFT=0"

    for /f "delims=" %%a in ('powershell -NoProfile -Command "$j=Get-Content '!GH_REL_FILE!' ^| ConvertFrom-Json; if ($j.assets.name -contains '!APP_NAME_EN!_v!VERSION!.zip') { '1' } else { '0' }"') do set "ZIP_ASSET_OK=%%a"
    for /f "delims=" %%a in ('powershell -NoProfile -Command "$j=Get-Content '!GH_REL_FILE!' ^| ConvertFrom-Json; if ($j.assets.name -contains '!APP_NAME_EN!_v!VERSION!.exe') { '1' } else { '0' }"') do set "EXE_ASSET_OK=%%a"
    for /f "delims=" %%a in ('powershell -NoProfile -Command "$j=Get-Content '!GH_REL_FILE!' ^| ConvertFrom-Json; if ($j.isDraft -eq $true) { '1' } else { '0' }"') do set "IS_DRAFT=%%a"

    set "ALL_OK=1"
    if "!HAS_ZIP!"=="1" if "!ZIP_ASSET_OK!"=="0" set "ALL_OK=0"
    if "!HAS_EXE!"=="1" if "!EXE_ASSET_OK!"=="0" set "ALL_OK=0"
    if "!IS_DRAFT!"=="1" set "ALL_OK=0"

    if "!ALL_OK!"=="1" set "ALREADY_PUBLISHED=1"
)
del "!GH_REL_FILE!" 2>nul
set "GH_REL_FILE="
if "!ALREADY_PUBLISHED!"=="1" (
    echo.
    echo ============================================
    echo  [跳过] Release !RELEASE_TAG! 已推送成功
    echo        页面: https://github.com/!RELEASE_SLUG!/releases/tag/!RELEASE_TAG!
    echo ============================================
    goto :end_ok
)

REM ---- 计算 SHA-256 ----
echo.
echo 计算 SHA-256...

set "ZIP_SHA="
if "!HAS_ZIP!"=="1" (
    for /f "usebackq delims=" %%h in (`powershell -NoProfile -Command "(Get-FileHash -Algorithm SHA256 '!ZIP_FILE!').Hash.ToLower()"`) do set "ZIP_SHA=%%h"
    if not defined ZIP_SHA (
        set "ERR_MSG=计算 ZIP SHA-256 失败"
        goto :die
    )
    > "!ZIP_FILE!.sha256" echo !ZIP_SHA!
    echo ZIP SHA-256: !ZIP_SHA!
)

set "EXE_SHA="
if "!HAS_EXE!"=="1" (
    for /f "usebackq delims=" %%h in (`powershell -NoProfile -Command "(Get-FileHash -Algorithm SHA256 '!EXE_FILE!').Hash.ToLower()"`) do set "EXE_SHA=%%h"
    if not defined EXE_SHA (
        set "ERR_MSG=计算 EXE SHA-256 失败"
        goto :die
    )
    > "!EXE_FILE!.sha256" echo !EXE_SHA!
    echo EXE SHA-256: !EXE_SHA!
)

REM ---- Release 说明文件 ----
set "RELEASE_TITLE=多媒体播放器 v!VERSION!"
set "NOTES_FILE=build\dist\release_notes_!VERSION!.md"

> "!NOTES_FILE!" echo # 多媒体播放器 v!VERSION!

set "GIT_DESC=!GIT_DESC:<=!"
set "GIT_DESC=!GIT_DESC:>=!"
set "GIT_DESC=!GIT_DESC:&=!"
set "GIT_DESC=!GIT_DESC:|=!"

echo.>> "!NOTES_FILE!"
echo --->> "!NOTES_FILE!"
echo.>> "!NOTES_FILE!"
echo - version: !VERSION!>> "!NOTES_FILE!"
echo - build time: %DATE% %TIME%>> "!NOTES_FILE!"
echo - commit: !GIT_DESC!>> "!NOTES_FILE!"
echo - branch: !GIT_BRANCH!>> "!NOTES_FILE!"
echo.>> "!NOTES_FILE!"
echo ## 下载>> "!NOTES_FILE!"
echo.>> "!NOTES_FILE!"

if "!HAS_ZIP!"=="1" (
    set "PRODUCT_LINE=!APP_NAME_EN!_v!VERSION!.zip (!ZIP_SIZE! bytes)"
    echo - [便携版 ZIP]: !APP_NAME_EN!_v!VERSION!.zip>> "!NOTES_FILE!"
    echo   - 大小: !ZIP_SIZE! bytes>> "!NOTES_FILE!"
    echo   - SHA-256: `!ZIP_SHA!`>> "!NOTES_FILE!"
    echo   - 解压后运行 `!APP_NAME!\!APP_NAME!.exe`>> "!NOTES_FILE!"
    echo.>> "!NOTES_FILE!"
)
if "!HAS_EXE!"=="1" (
    set "PRODUCT_LINE=!APP_NAME_EN!_v!VERSION!.exe (!EXE_SIZE! bytes)"
    echo - [单文件版 EXE]: !APP_NAME_EN!_v!VERSION!.exe>> "!NOTES_FILE!"
    echo   - 大小: !EXE_SIZE! bytes>> "!NOTES_FILE!"
    echo   - SHA-256: `!EXE_SHA!`>> "!NOTES_FILE!"
    echo   - 直接双击运行，无需安装>> "!NOTES_FILE!"
    echo.>> "!NOTES_FILE!"
)
echo ## 校验>> "!NOTES_FILE!"
echo ```powershell>> "!NOTES_FILE!"
if "!HAS_ZIP!"=="1" echo Get-FileHash -Algorithm SHA256 .\!APP_NAME_EN!_v!VERSION!.zip>> "!NOTES_FILE!"
if "!HAS_EXE!"=="1" echo Get-FileHash -Algorithm SHA256 .\!APP_NAME_EN!_v!VERSION!.exe>> "!NOTES_FILE!"
echo ```>> "!NOTES_FILE!"

REM ---- 构建待上传文件列表 ----
set "ASSET_FILES="
if "!HAS_ZIP!"=="1" set ASSET_FILES=!ASSET_FILES! "!ZIP_FILE!" "!ZIP_FILE!.sha256"
if "!HAS_EXE!"=="1" set ASSET_FILES=!ASSET_FILES! "!EXE_FILE!" "!EXE_FILE!.sha256"

REM ---- 推送 Release ----
echo.
echo ============================================
echo  推送 Release
echo ============================================

set "REL_EXISTS=0"
"%GH_EXE%" release view "!RELEASE_TAG!" !REL_REPO_ARG! >nul 2>&1
if !ERRORLEVEL! equ 0 set "REL_EXISTS=1"

if "!REL_EXISTS!"=="1" goto :update_release

REM ---- 新建 Release ----
echo 创建 Release !RELEASE_TAG! (tag: !GIT_SHA_SHORT!)...
echo 检查 commit !GIT_SHA_SHORT! 是否已推送到 origin...
set "COMMIT_ON_REMOTE=0"
git ls-remote origin "!GIT_SHA!" >nul 2>&1
if !ERRORLEVEL! equ 0 set "COMMIT_ON_REMOTE=1"
if "!COMMIT_ON_REMOTE!"=="0" (
    set "ERR_MSG=commit !GIT_SHA_SHORT! 未推送到 origin。请先执行: git push origin !GIT_BRANCH!"
    goto :die
)
echo 确认，正在创建 Release...

"%GH_EXE%" release create "!RELEASE_TAG!" !ASSET_FILES! --title "!RELEASE_TITLE!" --notes-file "!NOTES_FILE!" --latest --target !GIT_SHA! !REL_REPO_ARG!
set "REL_EXIT=!ERRORLEVEL!"
goto :check_rel_exit

:update_release
echo Release !RELEASE_TAG! 已存在，正在更新资产和说明...
"%GH_EXE%" release upload "!RELEASE_TAG!" !ASSET_FILES! --clobber !REL_REPO_ARG!
set "REL_EXIT=!ERRORLEVEL!"
if "!REL_EXIT!"=="0" (
    "%GH_EXE%" release edit "!RELEASE_TAG!" --title "!RELEASE_TITLE!" --notes-file "!NOTES_FILE!" --latest --draft=false !REL_REPO_ARG!
    set "REL_EXIT=!ERRORLEVEL!"
)
goto :check_rel_exit

:check_rel_exit
if "!REL_EXIT!"=="0" (
    echo.
    echo ============================================
    echo  Release 已发布: !RELEASE_TAG!
    echo       页面: https://github.com/!RELEASE_SLUG!/releases/tag/!RELEASE_TAG!
    echo       最新: https://github.com/!RELEASE_SLUG!/releases/latest
    echo ============================================
) else (
    echo.
    echo ============================================
    echo  [失败] Release 推送失败 (exit=!REL_EXIT!)
    echo ============================================
    exit /b !REL_EXIT!
)

:end_ok
echo.
echo 窗口将在 30 秒后关闭，或按任意键...
timeout /t 30 > nul
exit /b 0

:die
echo.
echo ============================================
echo  [错误] !ERR_MSG!
echo ============================================
echo.
echo 窗口将在 30 秒后关闭，或按任意键...
timeout /t 30 > nul
exit /b 1