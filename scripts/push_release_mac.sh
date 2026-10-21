#!/bin/bash

# ============================================
#  MultimediaPlayer macOS Release Push Script
#  将 macOS 构建产物（ZIP + 单文件可执行）上传到 GitHub Release
#  依赖: gh CLI（需已登录且具备 repo scope）
# ============================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_DIR"

# ---- 读取版本号 ----
if [ ! -f "VERSION" ]; then
    echo "[错误] 未找到 VERSION 文件"
    exit 1
fi
VERSION=$(cat VERSION | tr -d '[:space:]')
echo "当前版本: $VERSION"

# ---- 构建配置 ----
APP_NAME="多媒体播放器"
APP_NAME_EN="MultimediaPlayer"
MACOS_MIN_VERSION="10.13"

# macOS 产物路径
ZIP_FILE="dist/${APP_NAME_EN}_v${VERSION}_macOS.zip"
ONEFILE_FILE="dist/onefile/${APP_NAME_EN}_v${VERSION}_macOS"

HAS_ZIP=0
HAS_ONEFILE=0
[ -f "$ZIP_FILE" ] && HAS_ZIP=1
[ -f "$ONEFILE_FILE" ] && HAS_ONEFILE=1

if [ "$HAS_ZIP" -eq 0 ] && [ "$HAS_ONEFILE" -eq 0 ]; then
    echo "[错误] 未找到 macOS 构建产物。请先执行 scripts/build_mac.sh 完成构建"
    exit 1
fi

if [ "$HAS_ZIP" -eq 1 ]; then
    ZIP_SIZE=$(ls -lh "$ZIP_FILE" | awk '{print $5}')
    echo "ZIP: $ZIP_FILE ($ZIP_SIZE)"
fi
if [ "$HAS_ONEFILE" -eq 1 ]; then
    ONEFILE_SIZE=$(ls -lh "$ONEFILE_FILE" | awk '{print $5}')
    echo "BIN: $ONEFILE_FILE ($ONEFILE_SIZE)"
fi

# ---- 检查 gh CLI ----
if ! command -v gh &>/dev/null; then
    echo "[错误] 未找到 gh CLI。安装: brew install gh"
    exit 1
fi
GH_EXE="gh"

# ---- 检查 gh 登录状态 ----
GH_AUTH_OUTPUT=$($GH_EXE auth status 2>&1 || true)
if ! echo "$GH_AUTH_OUTPUT" | grep -qi "logged in"; then
    echo "[错误] gh 未登录。请执行: gh auth login"
    exit 1
fi
echo "gh 已登录"

if ! echo "$GH_AUTH_OUTPUT" | grep -qi "repo"; then
    echo "[错误] gh token 缺少 repo scope。授权: gh auth refresh -h github.com -s repo"
    exit 1
fi
echo "token 包含 repo scope"

# ---- 解析仓库 owner/repo ----
REMOTE_URL=$(git config --get remote.origin.url 2>/dev/null || true)
if [ -z "$REMOTE_URL" ]; then
    echo "[错误] 无 remote.origin，无法确定目标仓库"
    exit 1
fi

RELEASE_SLUG=$(echo "$REMOTE_URL" | sed -E 's#.*github.com[:/]##; s#\.git$##')
if [ -z "$RELEASE_SLUG" ] || [[ "$RELEASE_SLUG" != */* ]]; then
    echo "[错误] 无法解析 remote.origin 为 GitHub owner/repo"
    exit 1
fi
echo "仓库: $RELEASE_SLUG"

REL_REPO_ARG="--repo $RELEASE_SLUG"

# ---- 当前 HEAD 信息 ----
GIT_SHA=$(git rev-parse HEAD 2>/dev/null || true)
GIT_SHA_SHORT=$(git rev-parse --short HEAD 2>/dev/null || true)
GIT_DESC=$(git log -1 --oneline 2>/dev/null || true)
GIT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)

if [ -z "$GIT_SHA" ]; then
    echo "[错误] 无 git 提交记录"
    exit 1
fi
echo "分支: $GIT_BRANCH"
echo "提交: $GIT_DESC"

# ---- 检查 Release 是否已存在且资产完整 ----
RELEASE_TAG="v${VERSION}"
ALREADY_PUBLISHED=0

if $GH_EXE release view "$RELEASE_TAG" $REL_REPO_ARG >/dev/null 2>&1; then
    ASSETS_JSON=$($GH_EXE release view "$RELEASE_TAG" --json assets $REL_REPO_ARG 2>/dev/null || echo "{}")

    ZIP_ASSET_OK=0
    ONEFILE_ASSET_OK=0
    if echo "$ASSETS_JSON" | grep -q "\"name\":\"${APP_NAME_EN}_v${VERSION}_macOS.zip\""; then
        ZIP_ASSET_OK=1
    fi
    if echo "$ASSETS_JSON" | grep -q "\"name\":\"${APP_NAME_EN}_v${VERSION}_macOS\""; then
        ONEFILE_ASSET_OK=1
    fi

    ALL_OK=1
    [ "$HAS_ZIP" -eq 1 ] && [ "$ZIP_ASSET_OK" -eq 0 ] && ALL_OK=0
    [ "$HAS_ONEFILE" -eq 1 ] && [ "$ONEFILE_ASSET_OK" -eq 0 ] && ALL_OK=0

    [ "$ALL_OK" -eq 1 ] && ALREADY_PUBLISHED=1
fi

if [ "$ALREADY_PUBLISHED" -eq 1 ]; then
    echo ""
    echo "========================================="
    echo " [跳过] Release $RELEASE_TAG 已推送成功"
    echo "       页面: https://github.com/$RELEASE_SLUG/releases/tag/$RELEASE_TAG"
    echo "========================================="
    exit 0
fi

# ---- 计算 SHA-256 ----
echo ""
echo "计算 SHA-256..."

ZIP_SHA=""
if [ "$HAS_ZIP" -eq 1 ]; then
    ZIP_SHA=$(shasum -a 256 "$ZIP_FILE" | awk '{print $1}')
    echo "$ZIP_SHA" > "${ZIP_FILE}.sha256"
    echo "ZIP SHA-256: $ZIP_SHA"
fi

ONEFILE_SHA=""
if [ "$HAS_ONEFILE" -eq 1 ]; then
    ONEFILE_SHA=$(shasum -a 256 "$ONEFILE_FILE" | awk '{print $1}')
    echo "$ONEFILE_SHA" > "${ONEFILE_FILE}.sha256"
    echo "BIN SHA-256: $ONEFILE_SHA"
fi

# ---- Release 说明文件 ----
RELEASE_TITLE="多媒体播放器 v${VERSION}"
NOTES_FILE="dist/release_notes_mac_${VERSION}.md"

cat > "$NOTES_FILE" <<EOF
# 多媒体播放器 v${VERSION}

---

- version: ${VERSION}
- build time: $(date '+%Y-%m-%d %H:%M:%S')
- commit: ${GIT_DESC}
- branch: ${GIT_BRANCH}
- platform: macOS (兼容 macOS ${MACOS_MIN_VERSION:-10.13}+ / 2013 年后机型)

## 下载

EOF

if [ "$HAS_ZIP" -eq 1 ]; then
    cat >> "$NOTES_FILE" <<EOF
- [macOS 应用 ZIP]: ${APP_NAME_EN}_v${VERSION}_macOS.zip
  - 大小: ${ZIP_SIZE}
  - SHA-256: \`${ZIP_SHA}\`
  - 解压后将 \`${APP_NAME}.app\` 拖入 Applications 文件夹安装

EOF
fi

if [ "$HAS_ONEFILE" -eq 1 ]; then
    cat >> "$NOTES_FILE" <<EOF
- [macOS 单文件可执行]: ${APP_NAME_EN}_v${VERSION}_macOS
  - 大小: ${ONEFILE_SIZE}
  - SHA-256: \`${ONEFILE_SHA}\`
  - 双击直接运行，无需安装（首次运行可能需在「系统设置 → 隐私与安全性」中允许）

EOF
fi

cat >> "$NOTES_FILE" <<EOF
## 校验
\`\`\`bash
EOF
[ "$HAS_ZIP" -eq 1 ] && echo "shasum -a 256 ${APP_NAME_EN}_v${VERSION}_macOS.zip" >> "$NOTES_FILE"
[ "$HAS_ONEFILE" -eq 1 ] && echo "shasum -a 256 ${APP_NAME_EN}_v${VERSION}_macOS" >> "$NOTES_FILE"
cat >> "$NOTES_FILE" <<EOF
\`\`\`

## 注意事项
- macOS 首次运行未签名应用时，可能被 Gatekeeper 拦截。
  解决方式：右键点击应用 → 「打开」，或在「系统设置 → 隐私与安全性」中点击「仍要打开」。
- 视频播放依赖系统解码器（macOS 自带）。
EOF

# ---- 构建待上传文件列表 ----
ASSET_FILES=()
if [ "$HAS_ZIP" -eq 1 ]; then
    ASSET_FILES+=("$ZIP_FILE" "${ZIP_FILE}.sha256")
fi
if [ "$HAS_ONEFILE" -eq 1 ]; then
    ASSET_FILES+=("$ONEFILE_FILE" "${ONEFILE_FILE}.sha256")
fi

# ---- 推送 Release ----
echo ""
echo "========================================="
echo " 推送 Release"
echo "========================================="

REL_EXISTS=0
if $GH_EXE release view "$RELEASE_TAG" $REL_REPO_ARG >/dev/null 2>&1; then
    REL_EXISTS=1
fi

if [ "$REL_EXISTS" -eq 1 ]; then
    echo "Release $RELEASE_TAG 已存在，正在更新资产和说明..."
    if $GH_EXE release upload "$RELEASE_TAG" "${ASSET_FILES[@]}" --clobber $REL_REPO_ARG; then
        $GH_EXE release edit "$RELEASE_TAG" --title "$RELEASE_TITLE" --notes-file "$NOTES_FILE" --latest $REL_REPO_ARG
        REL_EXIT=$?
    else
        REL_EXIT=$?
    fi
else
    echo "创建 Release $RELEASE_TAG (tag: $GIT_SHA_SHORT)..."
    echo "检查 commit $GIT_SHA_SHORT 是否已推送到 origin..."
    if ! git ls-remote origin "$GIT_SHA" >/dev/null 2>&1; then
        echo "[错误] commit $GIT_SHA_SHORT 未推送到 origin。请先执行: git push origin $GIT_BRANCH"
        exit 1
    fi
    echo "确认，正在创建 Release..."
    $GH_EXE release create "$RELEASE_TAG" "${ASSET_FILES[@]}" \
        --title "$RELEASE_TITLE" \
        --notes-file "$NOTES_FILE" \
        --latest \
        --target "$GIT_SHA" \
        $REL_REPO_ARG
    REL_EXIT=$?
fi

if [ "$REL_EXIT" -eq 0 ]; then
    echo ""
    echo "========================================="
    echo " Release 已发布: $RELEASE_TAG"
    echo "      页面: https://github.com/$RELEASE_SLUG/releases/tag/$RELEASE_TAG"
    echo "      最新: https://github.com/$RELEASE_SLUG/releases/latest"
    echo "========================================="
    exit 0
else
    echo ""
    echo "========================================="
    echo " [失败] Release 推送失败 (exit=$REL_EXIT)"
    echo "========================================="
    exit $REL_EXIT
fi