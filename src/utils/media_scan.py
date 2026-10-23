# -*- coding: utf-8 -*-
"""媒体目录扫描（纯逻辑，不依赖 Qt）：递归 + 多线程。

为什么单独放这里：图片 / 视频列表（`src/layout/media_scan_thread.py`）和
归集（`src/collect/collect_service.py`）都要扫目录，
扫描函数必须两边共用一份，而且不能在纯逻辑模块里拖进 PyQt。

并发模型：按「目录层级」BFS —— 每一层的目录并行扫（`ThreadPoolExecutor`），
扫完一层再下发下一层。好处是天然无死锁、同一层目录越多并行度越高；
结果顺序与并发度无关（最后统一按 `st_mtime` 升序）。
"""
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from loguru import logger

# 递归扫描的默认并发目录数：scandir + stat 是 IO 密集，多线程能明显加快；
# 8 是折中值 —— 太小在大目录上收益有限，太大在机械盘 / 网络盘上会互相抢 IO。
DEFAULT_SCAN_WORKERS = 8
MAX_SCAN_WORKERS = 64


def _scan_one_dir(directory, suffixes):
    """扫描单个目录，返回 ([(file_path, mtime), ...], [subdir, ...])。"""
    files = []
    subdirs = []
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        subdirs.append(entry.path)
                        continue
                    if not entry.name.lower().endswith(suffixes):
                        continue
                    # scandir 的 stat 结果在 Windows 上会被缓存
                    files.append((entry.path, entry.stat(follow_symlinks=False).st_mtime))
                except OSError:
                    continue
    except OSError as e:
        logger.warning(f'跳过无法读取的目录 {directory}: {e}')
    return files, subdirs


def collect_media_files(root, suffixes, is_cancelled=None, recursive=True,
                        max_workers=None, on_progress=None):
    """递归收集 `root` 及其子目录下的媒体文件，返回按修改时间升序的绝对路径列表。

    - 多线程：每层目录并行 `scandir`，`max_workers` 默认 `DEFAULT_SCAN_WORKERS`；
    - 逐层检查 `is_cancelled()`，大目录也能较快响应取消；
    - 被删除 / 无权限的条目直接跳过，不让整个扫描失败；
    - `recursive=False` 时只看 `root` 这一层（删除后"找下一个视频"这类同步小扫描用），
      此时不开线程池（单目录没必要）；
    - `on_progress(found_count)` 每扫完一层回调一次（调用方自行限频）；
    - 取消时返回 `None`（与"真的一个都没扫到"区分开）。

    注意：同步 IO，必须在后台线程里调用（否则会卡住 GUI，见 `ISSUE-007`）。
    """
    if not root or not os.path.isdir(root):
        return []
    suffixes = tuple(suffixes)

    if not recursive:
        files, _subdirs = _scan_one_dir(root, suffixes)
        if is_cancelled is not None and is_cancelled():
            return None
        files.sort(key=lambda item: item[1])
        return [path for path, _ in files]

    try:
        workers = int(max_workers or DEFAULT_SCAN_WORKERS)
    except (TypeError, ValueError):
        workers = DEFAULT_SCAN_WORKERS
    workers = max(1, min(workers, MAX_SCAN_WORKERS))

    found = []
    level = [root]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        while level:
            if is_cancelled is not None and is_cancelled():
                return None
            futures = [pool.submit(_scan_one_dir, directory, suffixes) for directory in level]
            next_level = []
            for future in as_completed(futures):
                if is_cancelled is not None and is_cancelled():
                    for pending in futures:
                        pending.cancel()
                    return None
                files, subdirs = future.result()
                found.extend(files)
                next_level.extend(subdirs)
            level = next_level
            if on_progress is not None:
                on_progress(len(found))

    if is_cancelled is not None and is_cancelled():
        return None
    found.sort(key=lambda item: item[1])
    return [path for path, _ in found]
