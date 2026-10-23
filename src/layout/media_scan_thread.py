# -*- coding: utf-8 -*-
"""媒体目录后台扫描（图片 / 视频共用）—— Qt 包装层。

真正的扫描逻辑（递归 + 多线程）在 `src/utils/media_scan.py`（不依赖 Qt，
归集那边也用同一份）；这里只负责把扫描结果通过信号送回 GUI 线程。

为什么必须放后台：`os.scandir` + 逐条 `stat` 是同步阻塞调用，
在 GUI 线程里跑大目录（或网络盘 / 被安全软件挂钩的目录）会直接把事件循环卡住，
Windows 判定「Python 未响应」（AppHang）后强制关闭，用户看到的就是"崩溃"
（见 `ISSUE-007` / `ADR-012`）。
"""
from PyQt5.QtCore import QThread, pyqtSignal
from loguru import logger

# 扩展名清单统一放在 src/utils/media_types.py；这里再导出一次，
# 既有的 `from src.layout.media_scan_thread import IMAGE_SUFFIXES / VIDEO_SUFFIXES` 不用改。
from src.utils.media_types import IMAGE_SUFFIXES, VIDEO_SUFFIXES  # noqa: F401
# 扫描实现（含多线程）在纯逻辑模块里，这里转出供既有调用方继续 import。
from src.utils.media_scan import DEFAULT_SCAN_WORKERS, collect_media_files  # noqa: F401


class MediaScanThread(QThread):
    """后台递归扫描媒体目录（图片 / 视频共用一套实现）。

    信号：`scanned(token, path, files)`，`files` 为按修改时间升序的绝对路径列表。
    `token` 是调用方的请求序号，用来丢弃过期结果（连续切换目录时只认最新一次）。
    `max_workers` 控制并发扫描的目录数（默认 `DEFAULT_SCAN_WORKERS`）。
    """

    scanned = pyqtSignal(int, str, list)

    def __init__(self, token, path, suffixes, max_workers=None):
        super(MediaScanThread, self).__init__()
        self.token = token
        self.path = path
        self.suffixes = tuple(suffixes)
        self.max_workers = max_workers

    def run(self):
        files = collect_media_files(self.path, self.suffixes,
                                    is_cancelled=self.isInterruptionRequested,
                                    max_workers=self.max_workers)
        if files is None:
            logger.info(f'媒体扫描已取消: {self.path}')
            return
        if self.isInterruptionRequested():
            return
        self.scanned.emit(self.token, self.path, files)
