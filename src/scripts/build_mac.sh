#!/bin/bash

# 多媒体播放器 macOS 构建脚本
# 使用 pyinstaller 打包成独立的 .app 应用程序
# 打包后无需任何依赖即可在 macOS 上直接运行

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "项目目录: $PROJECT_DIR"
cd "$PROJECT_DIR"

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

# 创建 spec 文件
echo "正在生成 spec 文件..."
# 先生成 spec 文件，然后修改关键配置
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

# 检查 spec 文件是否生成
SPEC_FILE="${APP_NAME}.spec"
if [ ! -f "$SPEC_FILE" ]; then
    echo "错误: spec 文件生成失败！"
    exit 1
fi
echo "spec 文件已生成: $SPEC_FILE"

# 修改 spec 文件：禁用 UPX（macOS Big Sur+ 上 UPX 会导致 Gatekeeper 拒绝）
echo "修改 spec 文件配置..."
sed -i '' 's/upx=True/upx=False/g' "$SPEC_FILE"

# 修改 spec 文件：启用控制台输出，方便调试
sed -i '' 's/console=False/console=True/g' "$SPEC_FILE"
sed -i '' 's/disable_windowed_traceback=False/disable_windowed_traceback=True/g' "$SPEC_FILE"

echo ""
echo "========================================="
echo "开始构建 $APP_NAME.app ..."
echo "========================================="
echo ""

# 使用修改后的 spec 文件重新构建
$PYINSTALLER \
    --clean \
    --noconfirm \
    --distpath="dist" \
    --workpath="build" \
    "$SPEC_FILE"

# ============================================================
# 修复 Info.plist 和可执行文件名
# macOS Launch Services 无法处理中文可执行文件名（kLSNoExecutableErr）
# ============================================================
PLIST_FILE="dist/$APP_NAME.app/Contents/Info.plist"
MACOS_DIR="dist/$APP_NAME.app/Contents/MacOS"
EXEC_OLD="$MACOS_DIR/$APP_NAME"
EXEC_NEW="$MACOS_DIR/MultimediaPlayer"

if [ -f "$PLIST_FILE" ]; then
    # 1. 移除 LSBackgroundOnly（PyInstaller 错误添加的）
    echo "修复 Info.plist：移除 LSBackgroundOnly..."
    /usr/libexec/PlistBuddy -c "Delete :LSBackgroundOnly" "$PLIST_FILE" 2>/dev/null || true

    # 2. 移除 CFBundleIconFile 引用（无图标时避免警告）
    /usr/libexec/PlistBuddy -c "Delete :CFBundleIconFile" "$PLIST_FILE" 2>/dev/null || true

    # 3. 将 CFBundleExecutable 从中文改为 ASCII（修复 Launch Services bug）
    echo "修复 Info.plist：CFBundleExecutable 改为 MultimediaPlayer..."
    /usr/libexec/PlistBuddy -c "Set :CFBundleExecutable MultimediaPlayer" "$PLIST_FILE" 2>/dev/null || true
    echo "Info.plist 已修复"
fi

# 4. 重命名可执行文件（匹配 CFBundleExecutable）
if [ -f "$EXEC_OLD" ]; then
    echo "重命名可执行文件: $APP_NAME -> MultimediaPlayer"
    mv "$EXEC_OLD" "$EXEC_NEW"
fi

# 5. 重新签名（修改文件后需要重新签名）
echo "重新签名应用..."
codesign --deep --force --verbose --sign - "dist/$APP_NAME.app" 2>&1

echo ""
echo "========================================="
echo "构建完成!"
echo ""
echo "应用程序位于: dist/$APP_NAME.app"
echo "========================================="

# 显示构建产物大小
if [ -d "dist/$APP_NAME.app" ]; then
    APP_SIZE=$(du -sh "dist/$APP_NAME.app" | cut -f1)
    echo "应用大小: $APP_SIZE"
    echo ""
    echo "你可以双击 dist/$APP_NAME.app 运行"
    echo "或将应用拖入 Applications 文件夹安装"
    
    # 检查应用内容结构
    echo ""
    echo "应用内容结构:"
    find "dist/$APP_NAME.app" -maxdepth 3 -not -path "*/Resources/*" -not -path "*/MacOS/*" | head -20
    echo ""
    echo "Resources 目录内容:"
    ls -la "dist/$APP_NAME.app/Contents/Resources/" 2>/dev/null | head -20
    echo ""
    echo "MacOS 目录内容:"
    ls -la "dist/$APP_NAME.app/Contents/MacOS/" 2>/dev/null | head -10
fi