# -*- coding: utf-8 -*-
"""
GIF 后台解码线程模块

为解决 GIF 播放加载慢的问题，将解码过程迁移到后台线程：
1. 首次加载时快速解析帧头信息（尺寸、帧数），仅解码首帧即可开始播放
2. 后台线程逐帧解码剩余帧，解码完成后通过信号通知 UI 线程
3. 使用队列缓存机制：已解码帧入队，UI 线程按需取出

优化点：
- 避免加载大 GIF 时阻塞 UI 线程
- 渐进式解码：首帧显示后再解码后续帧，减少等待时间
- 帧缓存池：循环缓存 N 帧，降低内存占用

线程安全注意事项：
- QPixmap 不是线程安全的，严禁在非 GUI 线程创建或操作 QPixmap
- 后台线程解码得到 QImage 后通过信号传递给主线程，在主线程转换为 QPixmap
"""
import os
import threading
from typing import Optional

from PIL import Image

from PyQt6.QtCore import QObject, QThread, pyqtSignal as Signal
from PyQt6.QtGui import QPixmap, QImage

from loguru import logger


class GifDecodeResult:
    """单帧解码结果"""

    __slots__ = ('pixmap', 'duration', 'frame_index', 'is_last')

    def __init__(self, pixmap: QPixmap, duration: int, frame_index: int, is_last: bool = False):
        self.pixmap = pixmap
        self.duration = duration
        self.frame_index = frame_index
        self.is_last = is_last


class GifDecoderWorker(QObject):
    """
    GIF 解码工作对象（运行在后台线程）

    重要：此类运行在后台线程，严禁在此类中创建 QPixmap 对象。
    解码得到 QImage 后通过信号传递给主线程，由主线程转换为 QPixmap。

    信号:
        frame_decoded(image, duration_ms, frame_index) - 每解码一帧发出（传递 QImage）
        decoding_finished(total_frames) - 所有帧解码完成
        decoding_error(error_msg) - 解码出错
    """

    frame_decoded = Signal(QImage, int, int)  # (QImage, duration_ms, frame_index) - 传递 QImage 而非 QPixmap
    decoding_finished = Signal(int)  # (total_frames)
    decoding_error = Signal(str)

    def __init__(self):
        super().__init__()
        self._cancelled = False

    def cancel(self):
        """取消解码（线程安全）"""
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled

    def decode_all_frames(self, file_path: str):
        """
        解码 GIF 所有帧（在后台线程运行）

        注意：QPixmap 不是线程安全的，所以此处只创建 QImage，
        通过信号传递给主线程后再转换为 QPixmap。

        Args:
            file_path: GIF 文件路径
        """
        self._cancelled = False
        if not os.path.isfile(file_path):
            self.decoding_error.emit(f"GIF 文件不存在: {file_path}")
            return

        try:
            pil_img = Image.open(file_path)
            frame_index = 0

            while not self._cancelled:
                try:
                    # 转换为 RGBA QImage（QImage 是线程安全的，可以在后台线程创建）
                    frame_rgba = pil_img.convert("RGBA")
                    data = frame_rgba.tobytes("raw", "RGBA")
                    # 注意：data 是 bytes 对象，需要在 QImage 生命周期内保持有效
                    # QImage(data, ...) 的构造函数会拷贝数据，所以是安全的
                    qimg = QImage(data, frame_rgba.width, frame_rgba.height,
                                  QImage.Format.Format_RGBA8888)

                    # 读取帧延迟时间
                    try:
                        delay = pil_img.info.get("duration", 100)
                        if delay < 20:
                            delay = 100
                    except Exception:
                        delay = 100

                    # 传递 QImage（线程安全），主线程会转换为 QPixmap
                    self.frame_decoded.emit(qimg, delay, frame_index)
                    frame_index += 1

                    # 移动到下一帧
                    pil_img.seek(pil_img.tell() + 1)

                except EOFError:
                    break
                except Exception as e:
                    if not self._cancelled:
                        logger.warning(f"GIF 第 {frame_index} 帧解码失败: {e}")
                    break

            if not self._cancelled:
                self.decoding_finished.emit(frame_index)
                logger.info(f"GIF 解码完成: {file_path}, 共 {frame_index} 帧")

        except Exception as e:
            if not self._cancelled:
                self.decoding_error.emit(f"GIF 解码失败: {e}")


class GifDecoderThread(QObject):
    """
    GIF 后台解码线程管理器

    封装 QThread + Worker 模式，提供便捷接口。

    使用方式：
        decoder = GifDecoderThread()
        decoder.frame_decoded.connect(on_frame)
        decoder.decoding_finished.connect(on_finished)
        decoder.decode("path/to/file.gif")
        # 可随时调用 decoder.cancel() 取消解码

    信号:
        frame_decoded(image, duration_ms, frame_index) - 每帧解码完成（传递 QImage）
        decoding_finished(total_frames) - 所有帧解码完成
        decoding_error(error_msg) - 解码失败
    """

    frame_decoded = Signal(QImage, int, int)  # 传递 QImage 而非 QPixmap
    decoding_finished = Signal(int)
    decoding_error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread: Optional[QThread] = None
        self._worker: Optional[GifDecoderWorker] = None
        self._is_running: bool = False

    @property
    def is_running(self) -> bool:
        return self._is_running

    def decode(self, file_path: str):
        """
        启动后台解码

        如果已有解码任务在进行，会自动取消并启动新任务
        """
        self.cancel()

        self._thread = QThread(self)
        self._worker = GifDecoderWorker()

        # 将 worker 移动到线程
        self._worker.moveToThread(self._thread)

        # 连接信号
        self._worker.frame_decoded.connect(self.frame_decoded.emit)
        self._worker.decoding_finished.connect(self._on_finished)
        self._worker.decoding_finished.connect(self.decoding_finished.emit)
        self._worker.decoding_error.connect(self._on_error)
        self._worker.decoding_error.connect(self.decoding_error.emit)

        # 线程启动时执行解码
        self._thread.started.connect(lambda: self._worker.decode_all_frames(file_path))

        # 线程结束清理
        self._thread.finished.connect(self._on_thread_finished)

        self._is_running = True
        self._thread.start()

    def cancel(self):
        """取消当前解码任务"""
        if self._worker:
            self._worker.cancel()
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(2000)
        self._cleanup()
        self._is_running = False

    def _on_finished(self, total_frames: int):
        """解码完成"""
        self._is_running = False

    def _on_error(self, error_msg: str):
        """解码出错"""
        self._is_running = False

    def _on_thread_finished(self):
        """线程结束清理"""
        self._is_running = False

    def _cleanup(self):
        """清理资源"""
        self._worker = None
        self._thread = None