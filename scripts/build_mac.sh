#!/bin/bash

# 多媒体播放器 macOS 构建脚本
# 使用 pyinstaller 打包成独立的 .app 应用程序
# 打包后无需任何依赖即可在 macOS 上直接运行

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
echo "项目目录: $PROJECT_DIR"
cd "$PROJECT_DIR"

# 读取版本号
VERSION=""
if [ -f "VERSION" ]; then
    VERSION=$(cat VERSION)
else
    echo "错误: 未找到 VERSION 文件"
    exit 1
fi
echo "版本: $VERSION"

# 自动检测 Python 解释器（优先使用 python3.9，然后 python3）
PYTHON=""
for candidate in "/usr/local/opt/python@3.9/bin/python3.9" "/usr/local/bin/python3.9" "/opt/homebrew/bin/python3.9" "python3.9" "python3"; do
    if command -v $candidate &>/dev/null; then
        PYTHON="$candidate"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "错误: 未找到 Python 解释器！请安装 Python 3.9+"
    exit 1
fi

echo "使用 Python: $PYTHON"
$PYTHON --version

PYINSTALLER="$PYTHON -m PyInstaller"
APP_NAME="多媒体播放器"
APP_NAME_EN="MultimediaPlayer"

# 清理旧的构建产物
echo "正在清理旧的构建产物..."
rm -rf build dist *.spec 2>/dev/null || true

# 检查图标文件是否存在
ICON_PATH=""
if [ -f "img/app_icon.icns" ]; then
    ICON_PATH="--icon=img/app_icon.icns"
    echo "使用图标: img/app_icon.icns"
else
    echo "未找到图标文件，跳过图标设置"
fi

# ============================================
# 构建 onedir（目录版，用于 ZIP 分发）
# ============================================
echo ""
echo "========================================="
echo " 构建目录版 (onedir)"
echo "========================================="

$PYINSTALLER \
    --name "$APP_NAME" \
    --windowed \
    --onedir \
    $ICON_PATH \
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
    --osx-bundle-identifier=com.xiaobailong.mediaplayer \
    --distpath="dist" \
    --workpath="build" \
    --specpath="." \
    Player.py

# 检查是否生成 .app
if [ ! -d "dist/$APP_NAME.app" ]; then
    echo "错误: onedir 构建失败，未生成 .app"
    exit 1
fi

# ============================================
# 修复 Info.plist 和可执行文件名
# ============================================
PLIST_FILE="dist/$APP_NAME.app/Contents/Info.plist"
MACOS_DIR="dist/$APP_NAME.app/Contents/MacOS"
EXEC_OLD="$MACOS_DIR/$APP_NAME"
EXEC_NEW="$MACOS_DIR/$APP_NAME_EN"

if [ -f "$PLIST_FILE" ]; then
    echo "修复 Info.plist：移除 LSBackgroundOnly..."
    /usr/libexec/PlistBuddy -c "Delete :LSBackgroundOnly" "$PLIST_FILE" 2>/dev/null || true
    /usr/libexec/PlistBuddy -c "Delete :CFBundleIconFile" "$PLIST_FILE" 2>/dev/null || true
    echo "修复 Info.plist：CFBundleExecutable 改为 $APP_NAME_EN..."
    /usr/libexec/PlistBuddy -c "Set :CFBundleExecutable $APP_NAME_EN" "$PLIST_FILE" 2>/dev/null || true
    echo "Info.plist 已修复"
fi

if [ -f "$EXEC_OLD" ]; then
    echo "重命名可执行文件: $APP_NAME -> $APP_NAME_EN"
    mv "$EXEC_OLD" "$EXEC_NEW"
fi

# 重新签名
echo "重新签名应用..."
codesign --deep --force --verbose --sign - "dist/$APP_NAME.app" 2>&1

# ============================================
# 打包 ZIP
# ============================================
echo ""
echo "========================================="
echo " 打包 ZIP"
echo "========================================="

ZIP_NAME="${APP_NAME_EN}_v${VERSION}.zip"
cd dist
zip -r "$ZIP_NAME" "$APP_NAME.app"
cd "$PROJECT_DIR"
ZIP_SIZE=$(ls -lh "dist/$ZIP_NAME" | awk '{print $5}')
echo "ZIP 打包完成: dist/$ZIP_NAME ($ZIP_SIZE)"

# ============================================
# 构建摘要
# ============================================
echo ""
echo "========================================="
echo " 构建完成!"
echo "========================================="
echo "  版本: $VERSION"
echo "  产物:"
if [ -f "dist/$ZIP_NAME" ]; then
    echo "    [ZIP] $ZIP_NAME ($ZIP_SIZE)"
fi
if [ -d "dist/$APP_NAME.app" ]; then
    APP_SIZE=$(du -sh "dist/$APP_NAME.app" | cut -f1)
    echo "    [APP] dist/$APP_NAME.app ($APP_SIZE)"
fi
echo ""
echo "你可以双击 dist/$APP_NAME.app 运行"
echo "或将应用拖入 Applications 文件夹安装"