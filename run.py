#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""启动脚本 - 将项目根目录加入 sys.path 使 from src.* 导入生效"""
import sys
import os

if __name__ == '__main__':
    # 将项目根目录加入 Python 路径
    project_root = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, project_root)

    # 启动主程序
    from src.main.Player import MainWindow
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QLockFile
    import tempfile

    app = QApplication(sys.argv)

    # 单实例锁
    lock_file_path = os.path.join(tempfile.gettempdir(), "多媒体播放器.lock")
    lock_file = QLockFile(lock_file_path)
    if not lock_file.tryLock(100):
        print("已有实例在运行，退出当前进程")
        sys.exit(0)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())