#!/bin/bash

# ============================================
#  MultimediaPlayer macOS Build Script
#  Usage: build_mac.sh [clean|onedir|onefile|zip|norelease|nobump]
#  兼容 macOS 10.13+（2013 年后机型）
# ============================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

# ---- 读取版本号 ----
VERSION=""
if [ -f "VERSION" ]; then
    VERSION=$(cat VERSION | tr -d '[:space:]')
else
    echo "[错误] 未找到 VERSION 文件"
    exit 1
fi
echo "当前版本: $VERSION"

# ---- 构建配置 ----
APP_NAME="多媒体播放器"
APP_NAME_EN="MultimediaPlayer"
MAIN_SCRIPT="Player.py"
MACOS_MIN_VERSION="10.13"

# ---- 参数解析 ----
SKIP_RELEASE=0
SKIP_BUMP=0
TARGET="all"

for arg in "$@"; do
    case "$arg" in
        norelease) SKIP_RELEASE=1 ;;
        nobump)    SKIP_BUMP=1 ;;
        onedir)    TARGET="onedir" ;;
        onefile)   TARGET="onefile" ;;
        zip)       TARGET="zip" ;;
        clean)     TARGET="clean" ;;
    esac
done

# ---- 自动检测 Python 解释器 ----
PYTHON=""
for candidate in \
    "/usr/local/opt/python@3.9/bin/python3.9" \
    "/usr/local/bin/python3.9" \
    "/opt/homebrew/bin/python3.9" \
    "/usr/local/opt/python@3.10/bin/python3.10" \
    "/usr/local/bin/python3.10" \
    "/opt/homebrew/bin/python3.10" \
    "/usr/local/opt/python@3.11/bin/python3.11" \
    "/usr/local/bin/python3.11" \
    "/opt/homebrew/bin/python3.11" \
    "/usr/local/opt/python@3.12/bin/python3.12" \
    "/usr/local/bin/python3.12" \
    "/opt/homebrew/bin/python3.12" \
    "python3"; do
    if command -v "$candidate" &>/dev/null; then
        PYTHON="$candidate"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "[错误] 未找到 Python 解释器！请安装 Python 3.9+"
    exit 1
fi
echo "使用 Python: $PYTHON"
$PYTHON --version

PYINSTALLER="$PYTHON -m PyInstaller"

# ============================================
#  路由
# ============================================
if [ "$TARGET" = "clean" ]; then
    ./scripts/clean_mac.sh
    exit $?
fi

# ---- 版本号递增 ----
if [ "$SKIP_BUMP" = "0" ]; then
    if [ -f "$SCRIPT_DIR/tools/bump_version.ps1" ]; then
        if command -v pwsh &>/dev/null || command -v powershell &>/dev/null; then
            PS="pwsh"
            command -v pwsh &>/dev/null || PS="powershell"
            echo "[版本] 递增版本号..."
            $PS -NoProfile -ExecutionPolicy Bypass -File "$SCRIPT_DIR/tools/bump_version.ps1" -Path "$PROJECT_DIR/VERSION"
            VERSION=$(cat VERSION | tr -d '[:space:]')
            echo "        版本号已更新: $VERSION"
        else
            echo "[警告] 未找到 PowerShell，跳过版本号递增"
        fi
    else
        echo "[警告] 缺少 bump_version.ps1，跳过版本号递增"
    fi
fi

# ---- 环境检查 ----
echo ""
echo "[检查环境]..."
$PYTHON -m pip show pyinstaller &>/dev/null || {
    echo "[警告] 未找到 pyinstaller，尝试安装..."
    $PYTHON -m pip install pyinstaller -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
}
echo "        PyInstaller: OK"

if [ -f "requirement_mac.txt" ]; then
    echo "        [依赖] 安装 requirement_mac.txt..."
    $PYTHON -m pip install -r requirement_mac.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn || echo "[警告] 部分依赖安装失败，继续..."
fi

# ---- 检查 ffmpeg（macOS 版） ----
ensure_ffmpeg() {
    FFMPEG_TARGET="libs/ffmpeg/ffmpeg"
    if [ -f "$FFMPEG_TARGET" ]; then
        echo "[ffmpeg] 已就位: $FFMPEG_TARGET"
        return 0
    fi
    echo "[ffmpeg] 未找到 $FFMPEG_TARGET，尝试下载..."
    mkdir -p libs/ffmpeg
    TMP_ZIP="/tmp/ffmpeg_mac_$$.zip"
    TMP_DIR="/tmp/ffmpeg_extract_$$"
    if curl -L -o "$TMP_ZIP" "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-macos64-gpl.zip" 2>/dev/null; then
        unzip -o "$TMP_ZIP" -d "$TMP_DIR" >/dev/null 2>&1
        FFMPEG_BIN=$(find "$TMP_DIR" -name ffmpeg -type f 2>/dev/null | head -1)
        if [ -n "$FFMPEG_BIN" ]; then
            cp "$FFMPEG_BIN" "$FFMPEG_TARGET"
            chmod +x "$FFMPEG_TARGET"
            echo "[ffmpeg] 下载完成: $FFMPEG_TARGET"
        else
            echo "[警告] ffmpeg 解压失败，构建可能缺少 ffmpeg 依赖"
        fi
        rm -rf "$TMP_ZIP" "$TMP_DIR"
    else
        echo "[警告] ffmpeg 下载失败，构建可能缺少 ffmpeg 依赖"
    fi
}

# ---- 图标 ----
ICON_PATH=""
if [ -f "img/app_icon.icns" ]; then
    ICON_PATH="--icon=img/app_icon.icns"
fi

# ============================================
#  构建 onedir
# ============================================
build_onedir() {
    echo ""
    echo "========================================="
    echo " 构建目录版 (onedir) — macOS"
    echo "========================================="

    ensure_ffmpeg

    echo "清理旧的 onedir 产物..."
    rm -rf "dist/$APP_NAME.app" 2>/dev/null || true
    rm -rf "build/pyi-mac" 2>/dev/null || true

    echo "开始打包 onedir..."
    $PYINSTALLER \
        --name "$APP_NAME" \
        --windowed \
        --onedir \
        $ICON_PATH \
        --osx-bundle-identifier=com.xiaobailong.mediaplayer \
        --osx-min-version="$MACOS_MIN_VERSION" \
        --hidden-import=loguru \
        --hidden-import=apsw \
        --hidden-import=send2trash \
        --hidden-import=cv2 \
        --hidden-import=PIL \
        --hidden-import=PIL.ImageGrab \
        --hidden-import=numpy \
        --hidden-import=PyQt5 \
        --hidden-import=PyQt5.QtMultimedia \
        --hidden-import=PyQt5.QtMultimediaWidgets \
        --hidden-import=PyQt5.QtSvg \
        --hidden-import=PyQt5.QtNetwork \
        --hidden-import=PyQt5.QtGui \
        --hidden-import=PyQt5.QtCore \
        --collect-submodules=src \
        --add-data="libs/ffmpeg/ffmpeg:ffmpeg" \
        --add-binary="libs/ffmpeg/ffmpeg:ffmpeg" \
        --distpath="dist" \
        --workpath="build/pyi-mac" \
        --specpath="build" \
        --noconfirm \
        "$MAIN_SCRIPT"

    if [ ! -d "dist/$APP_NAME.app" ]; then
        echo "[错误] onedir 构建失败，未生成 .app"
        exit 1
    fi

    # 修复 Info.plist 和可执行文件名
    PLIST_FILE="dist/$APP_NAME.app/Contents/Info.plist"
    MACOS_DIR="dist/$APP_NAME.app/Contents/MacOS"
    EXEC_OLD="$MACOS_DIR/$APP_NAME"
    EXEC_NEW="$MACOS_DIR/$APP_NAME_EN"

    if [ -f "$PLIST_FILE" ]; then
        echo "修复 Info.plist..."
        /usr/libexec/PlistBuddy -c "Delete :LSBackgroundOnly" "$PLIST_FILE" 2>/dev/null || true
        /usr/libexec/PlistBuddy -c "Delete :CFBundleIconFile" "$PLIST_FILE" 2>/dev/null || true
        /usr/libexec/PlistBuddy -c "Set :CFBundleExecutable $APP_NAME_EN" "$PLIST_FILE" 2>/dev/null || true
        /usr/libexec/PlistBuddy -c "Set :LSMinimumSystemVersion $MACOS_MIN_VERSION" "$PLIST_FILE" 2>/dev/null || true
    fi

    if [ -f "$EXEC_OLD" ]; then
        mv "$EXEC_OLD" "$EXEC_NEW"
    fi

    # 重新签名
    echo "重新签名应用..."
    codesign --deep --force --verbose --sign - "dist/$APP_NAME.app" 2>&1 || echo "[警告] 重新签名失败"

    echo "onedir 构建完成: dist/$APP_NAME.app"
}

# ============================================
#  打包 ZIP
# ============================================
build_zip() {
    echo ""
    echo "========================================="
    echo " 打包 ZIP — macOS"
    echo "========================================="

    if [ ! -d "dist/$APP_NAME.app" ]; then
        echo "[错误] 未找到 dist/$APP_NAME.app，请先执行 onedir 构建"
        exit 1
    fi

    ZIP_NAME="${APP_NAME_EN}_v${VERSION}_macOS.zip"
    ZIP_DEST="dist/$ZIP_NAME"

    rm -f "$ZIP_DEST" 2>/dev/null || true

    echo "正在打包 $ZIP_DEST..."
    cd dist
    zip -r "$ZIP_NAME" "$APP_NAME.app" -x "*.DS_Store"
    cd "$PROJECT_DIR"

    ZIP_SIZE=$(ls -lh "$ZIP_DEST" | awk '{print $5}')
    echo "ZIP 打包完成: $ZIP_DEST ($ZIP_SIZE)"
}

# ============================================
#  构建 onefile（macOS 单文件可执行）
# ============================================
build_onefile() {
    echo ""
    echo "========================================="
    echo " 构建单文件版 (onefile) — macOS"
    echo "========================================="

    ensure_ffmpeg

    mkdir -p dist/onefile

    echo "清理旧的 onefile 产物..."
    rm -f "dist/onefile/${APP_NAME_EN}_v${VERSION}_macOS" 2>/dev/null || true

    echo "开始打包 onefile..."
    $PYINSTALLER \
        --name "$APP_NAME_EN" \
        --windowed \
        --onefile \
        $ICON_PATH \
        --osx-bundle-identifier=com.xiaobailong.mediaplayer \
        --osx-min-version="$MACOS_MIN_VERSION" \
        --hidden-import=loguru \
        --hidden-import=apsw \
        --hidden-import=send2trash \
        --hidden-import=cv2 \
        --hidden-import=PIL \
        --hidden-import=PIL.ImageGrab \
        --hidden-import=numpy \
        --hidden-import=PyQt5 \
        --hidden-import=PyQt5.QtMultimedia \
        --hidden-import=PyQt5.QtMultimediaWidgets \
        --hidden-import=PyQt5.QtSvg \
        --hidden-import=PyQt5.QtNetwork \
        --hidden-import=PyQt5.QtGui \
        --hidden-import=PyQt5.QtCore \
        --collect-submodules=src \
        --add-data="libs/ffmpeg/ffmpeg:ffmpeg" \
        --add-binary="libs/ffmpeg/ffmpeg:ffmpeg" \
        --distpath="dist/onefile" \
        --workpath="build/pyi-mac-onefile" \
        --specpath="build" \
        --noconfirm \
        "$MAIN_SCRIPT"

    ONEFILE_SRC="dist/onefile/$APP_NAME_EN"
    ONEFILE_DEST="dist/onefile/${APP_NAME_EN}_v${VERSION}_macOS"

    if [ ! -f "$ONEFILE_SRC" ]; then
        echo "[错误] onefile 输出文件未生成"
        exit 1
    fi

    mv "$ONEFILE_SRC" "$ONEFILE_DEST"
    chmod +x "$ONEFILE_DEST"
    echo "onefile 构建完成: $ONEFILE_DEST"
}

# ============================================
#  执行目标
# ============================================
case "$TARGET" in
    onedir)
        build_onedir
        build_zip
        ;;
    onefile)
        build_onefile
        ;;
    zip)
        build_zip
        ;;
    all)
        build_onedir
        build_onefile
        build_zip
        ;;
esac

# ============================================
#  构建摘要
# ============================================
echo ""
echo "========================================="
echo " 构建摘要"
echo "========================================="
echo "  版本: $VERSION"
echo "  产物:"
if [ -f "dist/${APP_NAME_EN}_v${VERSION}_macOS.zip" ]; then
    ZIP_SIZE=$(ls -lh "dist/${APP_NAME_EN}_v${VERSION}_macOS.zip" | awk '{print $5}')
    echo "    [ZIP]  ${APP_NAME_EN}_v${VERSION}_macOS.zip ($ZIP_SIZE)"
fi
if [ -f "dist/onefile/${APP_NAME_EN}_v${VERSION}_macOS" ]; then
    ONEFILE_SIZE=$(ls -lh "dist/onefile/${APP_NAME_EN}_v${VERSION}_macOS" | awk '{print $5}')
    echo "    [BIN]  ${APP_NAME_EN}_v${VERSION}_macOS ($ONEFILE_SIZE)"
fi
if [ -d "dist/$APP_NAME.app" ]; then
    APP_SIZE=$(du -sh "dist/$APP_NAME.app" | cut -f1)
    echo "    [APP]  dist/$APP_NAME.app ($APP_SIZE)"
fi
echo "========================================="

# ---- 推送 Release ----
if [ "$SKIP_RELEASE" = "0" ]; then
    echo ""
    echo "正在推送 Release..."
    bash "$SCRIPT_DIR/push_release_mac.sh"
fi

echo ""
echo "构建完成！"