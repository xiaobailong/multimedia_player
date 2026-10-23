# -*- coding: utf-8 -*-
"""归集（批量拷贝）相关的纯逻辑：文件类型判定、目录递归扫描、目标重名处理。

UI 在 `src/layout/collect_dialog.py`，后台执行在 `src/collect/collect_thread.py`。
"""
import os

# 扩展名清单与播放器 / 列表扫描共用一份（`src/utils/media_types.py`），避免口径分裂
from src.utils.media_types import IMAGE_SUFFIXES, VIDEO_SUFFIXES

ALL_SUFFIXES = IMAGE_SUFFIXES + VIDEO_SUFFIXES

# 归集弹框里「文件类型」的取值
KIND_ALL = 'all'
KIND_IMAGE = 'image'
KIND_VIDEO = 'video'


def media_kind(path):
    """返回 'image' / 'video' / ''（不认识的扩展名返回空串）。"""
    lower = (path or '').lower()
    if lower.endswith(IMAGE_SUFFIXES):
        return KIND_IMAGE
    if lower.endswith(VIDEO_SUFFIXES):
        return KIND_VIDEO
    return ''


def matches_kind(path, kind=KIND_ALL):
    """判断是否属于要归集的媒体文件。

    - 任何情况下都只认「图片 / 视频」（`.txt` 等非媒体文件不会被归集）；
    - `kind` 为 'all' 时表示「图片 + 视频」，否则只匹配指定类型。
    """
    actual = media_kind(path)
    if not actual:
        return False
    if not kind or kind == KIND_ALL:
        return True
    return actual == kind


def iter_media_files(root, kind=KIND_ALL, keyword='', is_cancelled=None, on_dir=None):
    """递归遍历 `root`，按「目录名 → 文件名」排序产出匹配的文件绝对路径。

    - 用 `os.scandir` 迭代（Windows 下 stat 结果有缓存，比 os.walk + getmtime 快）；
    - `is_cancelled()` 返回 True 时尽快退出（大目录 / 网络盘也能及时响应取消）；
    - `on_dir(dir_path)` 用于回报当前正在扫描的目录（调用方自行限频）；
    - `keyword` 只匹配**文件名**（不区分大小写），空串表示不过滤。

    注意：必须在后台线程里调用（`ISSUE-007`：GUI 线程同步遍历大目录会假死）。
    """
    if not root or not os.path.isdir(root):
        return
    keyword = (keyword or '').strip().lower()
    pending = [root]
    while pending:
        if is_cancelled and is_cancelled():
            return
        current = pending.pop()
        if on_dir is not None:
            on_dir(current)
        try:
            with os.scandir(current) as entries:
                sub_dirs = []
                for entry in entries:
                    if is_cancelled and is_cancelled():
                        return
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            sub_dirs.append(entry.path)
                            continue
                        name = entry.name
                        if not matches_kind(name, kind):
                            continue
                        if keyword and keyword not in name.lower():
                            continue
                        yield entry.path
                    except OSError:
                        # 扫描期间被删除 / 无权限的条目直接跳过
                        continue
                # 排序后再入栈，保证「顺序」模式下每次扫描结果稳定
                sub_dirs.sort()
                pending.extend(reversed(sub_dirs))
        except OSError:
            continue


def unique_destination(dest_dir, filename):
    """目标目录里已有同名文件时追加 " (n)"，返回不会覆盖任何文件的完整路径。"""
    base, ext = os.path.splitext(filename)
    candidate = os.path.join(dest_dir, filename)
    index = 1
    while os.path.exists(candidate):
        candidate = os.path.join(dest_dir, '%s (%d)%s' % (base, index, ext))
        index += 1
    return candidate
