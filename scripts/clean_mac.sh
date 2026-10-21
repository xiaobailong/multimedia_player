#!/bin/bash

# ============================================
#  MultimediaPlayer macOS Clean Script
#  清理 macOS 构建产物
# ============================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_DIR"

echo "========================================="
echo " 清理 macOS 构建产物"
echo "========================================="

# 清理 dist 目录
if [ -d "dist" ]; then
    rm -rf dist
    echo "已删除 dist/"
fi

# 清理 build 目录
if [ -d "build" ]; then
    rm -rf build
    echo "已删除 build/"
fi

# 清理根目录散落的 .spec 文件
for f in *.spec; do
    [ -e "$f" ] && rm -f "$f" && echo "已删除 $f"
done

# 清理 .sha256 校验文件
find . -name "*.sha256" -not -path "./.git/*" -delete 2>/dev/null || true

# 清理 macOS 系统文件
find . -name ".DS_Store" -not -path "./.git/*" -delete 2>/dev/null || true

echo ""
echo "清理完成！"