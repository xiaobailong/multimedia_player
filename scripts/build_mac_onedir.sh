#!/bin/bash

# ============================================
#  MultimediaPlayer macOS OneDir Build Script
#  构建 macOS 目录版 (.app) + ZIP 压缩包
#  Usage: build_mac_onedir.sh [nobump]
#    构建完成后需手动执行 push_release_mac.sh 推送 Release
#  兼容 macOS 10.13+（2013 年后机型）
# ============================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_DIR"

# 透传 nobump 参数到主脚本，固定使用 onedir 目标，不自动推送 Release
EXTRA_ARGS=()
for arg in "$@"; do
    case "$arg" in
        nobump) EXTRA_ARGS+=("$arg") ;;
    esac
done

echo "========================================="
echo " 多媒体播放器 macOS OneDir 构建"
echo " 目标: onedir + zip"
echo "========================================="

bash "$SCRIPT_DIR/build_mac.sh" onedir norelease "${EXTRA_ARGS[@]}"

exit $?