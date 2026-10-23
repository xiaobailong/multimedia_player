#!/bin/bash

# ============================================
#  MultimediaPlayer macOS OneFile Build Script
#  构建 macOS 单文件独立可执行版
#  Usage: build_mac_onefile.sh [nobump]
#    构建完成后需手动执行 push_release_mac.sh 推送 Release
#  兼容 macOS 10.13+（2013 年后机型）
# ============================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_DIR"

# 透传 nobump 参数到主脚本，固定使用 onefile 目标，不自动推送 Release
EXTRA_ARGS=()
for arg in "$@"; do
    case "$arg" in
        nobump) EXTRA_ARGS+=("$arg") ;;
    esac
done

echo "========================================="
echo " 多媒体播放器 macOS OneFile 构建"
echo " 目标: onefile（单文件可执行）"
echo "========================================="

bash "$SCRIPT_DIR/build_mac.sh" onefile norelease "${EXTRA_ARGS[@]}"

exit $?