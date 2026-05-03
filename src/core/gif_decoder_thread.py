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
- QImage 即使被 Qt 标记为 "线程安全"，PyQt6 的 Python 包装器在不同线程间传递时
  仍可能出现 C++ 对象生命周期管理问题，导致 0xC000041D 崩溃
- 绝对安全的做法：后台线程只发原始字节数据（bytes + width + height），
  主线程收到后再创建 QImage -> QPixmap
"""
import os
from typing import Optional

from PIL import Image

from PyQt6.QtCore import QObject, QThread, pyqtSignal as Signal
from loguru import logger


class GifDecoderWorker(QObject):
    """
    GIF 解码工作对象（运行在后台线程）

    重要：此类运行在后台线程。
    - 严禁在此类中创建 QPixmap 对象
    - 严禁在此类中创建 QImage 对象（PyQt6 跨线程传递 QImage 仍有崩溃风险）
    - 只发送原始字节数据，主线程负责创建 Qt 图形对象

    信号:
        frame_decoded(data, width, height, duration_ms, frame_index)
            - data: bytes, RGBA 格式原始像素数据
            - width: int, 帧宽度
            - height: int, 帧高度
            - duration_ms: int, 帧延迟
            - frame_index: int, 帧索引
        decoding_finished(total_frames)
        decoding_error(error_msg)
    """

    # 只传递 Python 原生类型（bytes, int），绝对不传递任何 Qt 对象
    frame_decoded = Signal(bytes, int, int, int, int)  # (data, width, height, duration_ms, frame_index)
    decoding_finished = Signal(int)
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

        安全策略：
        - 不创建任何 Qt GUI 对象（QPixmap / QImage）
        - 只发送 Python 原生类型：bytes 像素数据 + int 维度信息
        - 主线程收到 signal 后创建 QImage + QPixmap

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
                    # 转换为 RGBA 原始字节
                    frame_rgba = pil_img.convert("RGBA")
                    data = frame_rgba.tobytes("raw", "RGBA")  # 纯 Python bytes
                    w, h = frame_rgba.width, frame_rgba.height

                    # 读取帧延迟时间
                    try:
                        delay = pil_img.info.get("duration", 100)
                        if delay < 20:
                            delay = 100
                    except Exception:
                        delay = 100

                    logger.debug(f"[后台线程] 发送帧 {frame_index}: {w}x{h}, delay={delay}ms, data_len={len(data)}")
                    # 传递纯 Python 原生类型：绝对安全
                    self.frame_decoded.emit(data, w, h, delay, frame_index)
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
        frame_decoded(data, width, height, duration_ms, frame_index)
            - 传递原始字节数据，不传递任何 Qt 对象
        decoding_finished(total_frames)
        decoding_error(error_msg)
    """

    # 只传递 Python 原生类型
    frame_decoded = Signal(bytes, int, int, int, int)
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
        """启动后台解码"""
        self.cancel()

        self._thread = QThread(self)
        self._worker = GifDecoderWorker()

        self._worker.moveToThread(self._thread)

        # 连接信号（只转发 Python 原生类型）
        self._worker.frame_decoded.connect(self.frame_decoded.emit)
        self._worker.decoding_finished.connect(self._on_finished)
        self._worker.decoding_finished.connect(self.decoding_finished.emit)
        self._worker.decoding_error.connect(self._on_error)
        self._worker.decoding_error.connect(self.decoding_error.emit)

        self._thread.started.connect(lambda: self._worker.decode_all_frames(file_path))
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
        self._is_running = False

    def _on_error(self, error_msg: str):
        self._is_running = False

    def _on_thread_finished(self):
        self._is_running = False

    def _cleanup(self):
        self._worker = None
        self._thread = None