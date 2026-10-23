# -*- coding: utf-8 -*-
"""媒体目录后台扫描（图片 / 视频共用）。

为什么必须放后台：`os.scandir` + 逐条 `stat` 是同步阻塞调用，
在 GUI 线程里跑大目录（或网络盘 / 被安全软件挂钩的目录）会直接把事件循环卡住，
Windows 判定「Python 未响应」（AppHang）后强制关闭，用户看到的就是"崩溃"
（见 `ISSUE-007` / `ADR-012`）。
"""
import os

from PyQt5.QtCore import QThread, pyqtSignal
from loguru import logger

# 扩展名清单统一放在 src/utils/media_types.py；这里再导出一次，
# 既有的 `from src.layout.media_scan_thread import IMAGE_SUFFIXES / VIDEO_SUFFIXES` 不用改。
from src.utils.media_types import IMAGE_SUFFIXES, VIDEO_SUFFIXES  # noqa: F401


def collect_media_files(root, suffixes, is_cancelled=None, recursive=True):
    """递归收集 `root` 及其子目录下的媒体文件，返回按修改时间升序的绝对路径列表。

    - 用 `os.scandir` 迭代（Windows 下 stat 结果有缓存，比 `os.walk` + `getmtime` 快）；
    - 逐条目检查 `is_cancelled()`，大目录里也能快速响应取消；
    - 扫描期间被删除 / 无权限的条目直接跳过，不让整个扫描失败；
    - `recursive=False` 时只看 `root` 这一层（删除后"找下一个视频"这类同步小扫描用）；
    - 取消时返回 `None`（与"真的一个都没扫到"区分开）。

    注意：同步 IO，必须在后台线程里调用（除非只扫单层、且目录很小）。
    """
    if not root or not os.path.isdir(root):
        return []
    suffixes = tuple(suffixes)
    found = []
    pending_dirs = [root]
    while pending_dirs:
        if is_cancelled is not None and is_cancelled():
            return None
        current_dir = pending_dirs.pop()
        try:
            with os.scandir(current_dir) as entries:
                for entry in entries:
                    if is_cancelled is not None and is_cancelled():
                        return None
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if recursive:
                                pending_dirs.append(entry.path)
                            continue
                        if not entry.name.lower().endswith(suffixes):
                            continue
                        # scandir 的 stat 结果在 Windows 上会被缓存
                        found.append((entry.path, entry.stat(follow_symlinks=False).st_mtime))
                    except OSError:
                        continue
        except OSError as e:
            logger.warning(f'跳过无法读取的目录 {current_dir}: {e}')
            continue

    found.sort(key=lambda item: item[1])
    return [item[0] for item in found]


class MediaScanThread(QThread):
    """后台递归扫描媒体目录（图片 / 视频共用一套实现）。

    信号：`scanned(token, path, files)`，`files` 为按修改时间升序的绝对路径列表。
    `token` 是调用方的请求序号，用来丢弃过期结果（连续切换目录时只认最新一次）。
    """

    scanned = pyqtSignal(int, str, list)

    def __init__(self, token, path, suffixes):
        super(MediaScanThread, self).__init__()
        self.token = token
        self.path = path
        self.suffixes = tuple(suffixes)

    def run(self):
        files = collect_media_files(self.path, self.suffixes, self.isInterruptionRequested)
        if files is None:
            logger.info(f'媒体扫描已取消: {self.path}')
            return
        if self.isInterruptionRequested():
            return
        self.scanned.emit(self.token, self.path, files)
