# -*- coding: utf-8 -*-
"""ffmpeg 下载后台线程。

下载 ffmpeg 会持续较长时间（几十秒到几分钟），
放在 GUI 主线程会让窗口「未响应」。本线程把这部分逻辑挪到后台，
通过 pyqtSignal 把下载进度、状态文本、最终结果回报给主线程更新 UI。
"""
from PyQt5.QtCore import QThread, pyqtSignal
from loguru import logger

from src.utils.ffmpeg_manager import ensure_ffmpeg


class FfmpegDownloadThread(QThread):
    """后台下载 ffmpeg.exe 到本地 libs/ffmpeg/。

    信号：
        progress(downloaded, total, speed_bps, source_url)  下载进度
        status(text)                                         状态文本
        completed(success, message)                          下载完成
        failed(message)                                      线程异常
    """

    progress = pyqtSignal(int, int, float, str)
    status = pyqtSignal(str)
    completed = pyqtSignal(bool, str)
    failed = pyqtSignal(str)

    def run(self):
        try:
            self.status.emit('正在下载 ffmpeg.exe…')

            def on_progress(downloaded, total, speed_bps, source_url):
                self.progress.emit(downloaded, total or 0, speed_bps, source_url)

            ok, msg = ensure_ffmpeg(on_progress=on_progress)
            if ok:
                self.status.emit('ffmpeg.exe 下载完成')
            else:
                self.status.emit('ffmpeg.exe 下载失败：%s' % msg)
            self.completed.emit(ok, msg)
        except Exception as e:
            logger.exception(f'ffmpeg 下载线程异常: {e}')
            self.failed.emit(str(e))