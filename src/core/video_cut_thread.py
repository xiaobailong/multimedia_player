import os
import subprocess
from loguru import logger

from PyQt6.QtCore import QThread, pyqtSignal
from src.utils import get_log_path

log_dir = get_log_path()


class VideoCutThread(QThread):
    finished = pyqtSignal(str, int)

    def __init__(self, command, file_name, parent=None):
        super(VideoCutThread, self).__init__(parent)
        self.command = command
        self.file_name = file_name

    def run(self) -> None:
        """
        执行 ffmpeg 剪切命令，等待完成后发射 finished 信号。
        使用 subprocess.Popen 替代 os.popen，确保：
        1. 子进程完成后才发射信号
        2. 正确关闭管道/句柄，避免资源泄漏导致 native 崩溃 (0xC0000409)
        """
        try:
            # 使用 subprocess.Popen + wait() 确保 ffmpeg 完成后才继续
            # 同时将 stdout/stderr 输出到空设备，避免管道缓冲区满阻塞
            with open(os.devnull, 'wb') as devnull:
                p = subprocess.Popen(
                    self.command,
                    stdout=devnull,
                    stderr=devnull,
                    shell=True  # 兼容原 os.popen 的 shell 语义
                )
                # 等待子进程结束，保证资源正确回收
                retcode = p.wait()
                p.stdout = None
                p.stderr = None

            logger.info(f"剪切完成: {self.file_name}, 返回码: {retcode}")
            self.finished.emit(self.file_name, retcode)
        except Exception as e:
            logger.error(f"视频剪切失败: {e}")
            self.finished.emit(self.file_name, -1)
