#!/bin/bash

# ============================================
#  MultimediaPlayer macOS OneFile Build Script
#  仅构建 macOS 单文件独立可执行版
#  Usage: build_mac_onefile.sh [nobump] [norelease]
#  兼容 macOS 10.13+（2013 年后机型）
# ============================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_DIR"

# 透传参数到主脚本，固定使用 onefile 目标
EXTRA_ARGS=()
for arg in "$@"; do
    case "$arg" in
        nobump|norelease) EXTRA_ARGS+=("$arg") ;;
    esac
done

echo "========================================="
echo " 多媒体播放器 macOS OneFile 构建"
echo " 目标: onefile（单文件可执行）"
echo "========================================="

bash "$SCRIPT_DIR/build_mac.sh" onefile "${EXTRA_ARGS[@]}"

exit $?