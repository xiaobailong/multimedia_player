# -*- coding: utf-8 -*-
"""归集（批量拷贝）相关的纯逻辑：文件类型判定、目录递归扫描、目标重名处理。

UI 在 `src/layout/collect_dialog.py`，后台执行在 `src/collect/collect_thread.py`。
"""
import os

# 扩展名清单与播放器 / 列表扫描共用一份（`src/utils/media_types.py`），避免口径分裂
from src.utils.media_types import IMAGE_SUFFIXES, VIDEO_SUFFIXES
from src.utils.media_scan import collect_media_files

ALL_SUFFIXES = IMAGE_SUFFIXES + VIDEO_SUFFIXES

# 归集弹框里「文件类型」的取值
KIND_ALL = 'all'
KIND_IMAGE = 'image'
KIND_VIDEO = 'video'


def suffixes_for_kind(kind=KIND_ALL):
    """把归集的「文件类型」映射成扫描用的扩展名元组。"""
    if kind == KIND_IMAGE:
        return IMAGE_SUFFIXES
    if kind == KIND_VIDEO:
        return VIDEO_SUFFIXES
    return ALL_SUFFIXES


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
    """遍历 `root`（递归、多线程扫描）并产出匹配的媒体文件绝对路径。

    - 扫描交给 `utils.media_scan.collect_media_files`（按目录层级并发的 `scandir`）；
    - 结果按路径升序产出，保证「顺序归集」稳定；
    - `is_cancelled()` 返回 True 时立即结束（扫描中途取消则一个都不产出）；
    - `keyword` 只匹配**文件名**（不区分大小写），空串表示不过滤；
    - `on_dir(root)` 仅用于兼容旧调用（多线程扫描没有"当前目录"的概念）。

    注意：必须在后台线程里调用（`ISSUE-007`：GUI 线程同步遍历大目录会假死）。
    """
    if not root or not os.path.isdir(root):
        return
    if on_dir is not None:
        on_dir(root)
    files = collect_media_files(root, suffixes_for_kind(kind), is_cancelled=is_cancelled)
    if files is None:
        return
    keyword = (keyword or '').strip().lower()
    for path in sorted(files):
        if keyword and keyword not in os.path.basename(path).lower():
            continue
        yield path


def unique_destination(dest_dir, filename, reserved=None):
    """目标目录里已有同名文件时追加 " (n)"，返回不会覆盖任何文件的完整路径。

    `reserved` 是并行拷贝时共享的「已预约目标路径」集合（大小写不敏感比较）：
    多个线程同时往同一目录拷同名文件时，只靠 `os.path.exists` 会选中同一个名字，
    后写的那份会把前一份覆盖掉。调用方需要在锁内调用本函数并把返回值加入 `reserved`。
    """
    base, ext = os.path.splitext(filename)
    candidate = os.path.join(dest_dir, filename)
    index = 1
    while True:
        if reserved is not None and os.path.normcase(candidate) in reserved:
            taken = True
        else:
            taken = os.path.exists(candidate)
        if not taken:
            return candidate
        candidate = os.path.join(dest_dir, '%s (%d)%s' % (base, index, ext))
        index += 1
