import os

from PyQt5.QtCore import QThread, pyqtSignal

from loguru import logger

# 支持的图片扩展名（与 PicShowLayout.is_pic 保持一致）
IMAGE_SUFFIXES = (
    '.bmp', '.dib', '.png', '.jpg', '.jpeg', '.pbm', '.pgm',
    '.ppm', '.tif', '.tiff', '.webp', '.gif')


class PicScanThread(QThread):
    """后台递归扫描图片目录。

    为什么必须放后台：`os.walk` + 逐文件 `getmtime` 是同步阻塞调用，
    在 GUI 线程里跑大目录（或网络盘/被安全软件挂钩的目录）会直接把事件循环卡住，
    Windows 判定「Python 未响应」（AppHang）后强制关闭，用户看到的就是"崩溃"。
    实测 `C:\\Windows\\WinSxS` 在 GUI 线程里 20s 都扫不完。
    """

    # token: 请求序号（用于丢弃过期结果）; path: 目录; files: 按修改时间升序的图片绝对路径
    scanned = pyqtSignal(int, str, list)

    def __init__(self, token, path):
        super().__init__()
        self.token = token
        self.path = path

    def run(self):
        found = []
        pending_dirs = [self.path]
        while pending_dirs:
            if self.isInterruptionRequested():
                logger.info(f'图片扫描已取消: {self.path}')
                return
            current_dir = pending_dirs.pop()
            try:
                with os.scandir(current_dir) as entries:
                    for entry in entries:
                        # 逐条目检查中断：大目录里也能快速响应取消
                        if self.isInterruptionRequested():
                            logger.info(f'图片扫描已取消: {self.path}')
                            return
                        try:
                            if entry.is_dir(follow_symlinks=False):
                                pending_dirs.append(entry.path)
                                continue
                            if not entry.name.lower().endswith(IMAGE_SUFFIXES):
                                continue
                            # scandir 的 stat 结果在 Windows 上会被缓存，比再调 getmtime 快得多
                            found.append((entry.path, entry.stat(follow_symlinks=False).st_mtime))
                        except OSError:
                            # 扫描期间被删除 / 无权限的条目直接跳过，不能让整个扫描失败
                            continue
            except OSError as e:
                logger.warning(f'跳过无法读取的目录 {current_dir}: {e}')
                continue

        found.sort(key=lambda item: item[1])
        if self.isInterruptionRequested():
            return
        self.scanned.emit(self.token, self.path, [item[0] for item in found])
