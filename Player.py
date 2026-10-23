# -*- coding: utf-8 -*-
"""多媒体播放器入口。

这里只保留启动必需的控制流，方便一眼看清程序是怎么起来的：

1. 抑制依赖库的 DeprecationWarning，初始化日志（``data/log/file_日期.log``）；
2. 单实例锁：``QLockFile`` 基于文件锁，进程退出时由系统自动释放，不会残留；
3. ``QApplication`` → ``MainWindow`` → 事件循环。

窗口与业务代码都在 ``src/`` 下，主窗口的组装见 ``src/window/main_window.py``。
"""
import os
import sys
import tempfile
import warnings

from PyQt5.QtCore import QLockFile
from PyQt5.QtWidgets import QApplication
from loguru import logger

from src.utils.utils import get_log_path
from src.window import MainWindow

warnings.filterwarnings("ignore", category=DeprecationWarning)


def init_logging():
    """日志按天切分，同时保留 loguru 默认的控制台输出。"""
    log_dir = get_log_path()
    logger.add(os.path.join(log_dir, "file_{time:YYYY-MM-DD}.log"), rotation="500 MB",
               format="{time} {level} {message}",
               filter="",
               level="INFO")
    logger.info(f"日志目录: {log_dir}")


def acquire_single_instance_lock():
    """尝试获取单实例锁；已有实例在运行时返回 None。"""
    lock_file_path = os.path.join(tempfile.gettempdir(), "多媒体播放器.lock")
    lock_file = QLockFile(lock_file_path)
    if not lock_file.tryLock(100):
        return None
    return lock_file


def main():
    init_logging()

    app = QApplication(sys.argv)

    lock_file = acquire_single_instance_lock()
    if lock_file is None:
        logger.warning("已有实例在运行，退出当前进程")
        sys.exit(0)

    window = MainWindow()
    window.show()

    # lock_file 必须存活到事件循环结束（被回收会提前解锁）
    exit_code = app.exec()
    del lock_file
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
