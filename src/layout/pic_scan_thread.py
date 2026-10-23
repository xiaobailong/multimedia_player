"""图片目录后台扫描（递归）。

实际实现见 `media_scan_thread.MediaScanThread`；这里保留 `PicScanThread` 这个名字
与 `IMAGE_SUFFIXES` 导出，`PicInputLayout` 的既有调用不用改。
"""
from src.layout.media_scan_thread import IMAGE_SUFFIXES, MediaScanThread


class PicScanThread(MediaScanThread):
    """后台递归扫描图片目录（按修改时间升序返回）。

    为什么必须放后台：`os.scandir` + 逐文件 `stat` 是同步阻塞调用，
    在 GUI 线程里跑大目录（或网络盘/被安全软件挂钩的目录）会直接把事件循环卡住，
    Windows 判定「Python 未响应」（AppHang）后强制关闭，用户看到的就是"崩溃"
    （见 `ISSUE-007`）。
    """

    def __init__(self, token, path):
        super(PicScanThread, self).__init__(token, path, IMAGE_SUFFIXES)
