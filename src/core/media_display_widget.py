# -*- coding: utf-8 -*-
"""
统一媒体显示组件：既能播放图片又能播放视频

功能：
1. 自动缩放（保持宽高比）
2. 支持 GIF 动画
3. 支持 VLC/MPV/Qt 三种视频后端（自动选择最优）
4. 窗口缩放自适应

兼容 macOS 10.9+ (2013年) 和 Windows 7+
"""
import os
from typing import Optional

from PIL import Image

from PyQt6.QtCore import (
    Qt, QTimer
)
from PyQt6.QtCore import pyqtSignal as Signal
from PyQt6.QtGui import (
    QPixmap, QImage, QResizeEvent
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea
)

from loguru import logger

from src.core.media_player_engine import (
    is_image_file, is_video_file,
    MediaEngine, VlcEngine, MpvEngine, QtEngine,
    VLC_AVAILABLE, MPV_AVAILABLE
)
from src.core.gif_gl_widget import GpuGifWidget, _HAS_OPENGL
from src.core.gif_decoder_thread import GifDecoderThread


class MediaDisplayWidget(QWidget):
    """
    统一媒体显示组件

    使用方式：
        widget = MediaDisplayWidget(parent)
        widget.playMedia("/path/to/video.mp4")  # 播放视频
        widget.playMedia("/path/to/image.jpg")  # 显示图片

    信号：
        mediaFinished - 媒体播放完成（视频结束或幻灯片切换）
        positionChanged(position_ms) - 播放位置变化
        mediaLoaded(file_path) - 媒体加载完成
        errorOccurred(error_msg) - 发生错误
    """

    mediaFinished = Signal()
    positionChanged = Signal(int)
    mediaLoaded = Signal(str)
    errorOccurred = Signal(str)

    # 缩放模式
    SCALE_FIT = 0       # 适应（保持宽高比）
    SCALE_FILL = 1      # 填充（裁剪）
    SCALE_ORIGINAL = 2  # 原始大小

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background-color: black;")

        # ---------- 内部布局 ----------
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        # 用于视频的 QVideoWidget/原生窗口
        self._video_container = QWidget(self)
        self._video_container.setStyleSheet("background-color: black;")

        # 用于静态图片的 QLabel
        self._image_label = QLabel(self)
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setStyleSheet("background-color: black;")
        self._image_label.setVisible(False)

        # 用于 GIF 的 GPU 加速渲染控件（回退: QLabel）
        self._gif_render_widget = GpuGifWidget(self)
        self._gif_render_widget.setVisible(False)
        self._gif_render_widget.setStyleSheet("background-color: black;")

        # 使用 QScrollArea 作为图片容器
        self._scroll_area = QScrollArea(self)
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_area.setWidget(self._image_label)
        self._scroll_area.setVisible(False)
        self._scroll_area.setStyleSheet("background-color: black; border: none;")

        self._layout.addWidget(self._video_container)
        self._layout.addWidget(self._scroll_area)
        self._layout.addWidget(self._gif_render_widget)

        # ---------- 状态 ----------
        self._current_path: str = ""
        self._media_type: str = ""  # "image" or "video"
        self._scale_mode: int = MediaDisplayWidget.SCALE_FIT

        # 视频引擎
        self._engine: Optional[MediaEngine] = None

        # 图片相关
        self._current_image: Optional[QImage] = None
        self._current_pixmap: Optional[QPixmap] = None

        # GIF 相关（硬件加速 + 后台解码）
        self._gif_frames: list = []
        self._gif_durations: list = []
        self._gif_idx: int = 0
        self._gif_timer: Optional[QTimer] = None
        self._gif_playing: bool = False
        self._gif_decoder_thread: Optional[GifDecoderThread] = None
        # -- 后台解码渐进式播放参数 --
        self._gif_background_decoding: bool = True  # 是否启用后台解码
        self._gif_total_frames: int = 0        # 总帧数（后台解码完成前为0）
        self._gif_progressive_mode: bool = False  # 后台解码进行中时的标记

        # 自适应定时器（防抖）
        self._resize_timer: Optional[QTimer] = None
        self._pending_resize: bool = False

        # ---------- 初始化引擎 ----------
        self._init_engine()

    def _init_engine(self):
        """延迟初始化视频引擎，首次播放视频时再初始化"""
        # VLC DLL 在某些 Windows 系统上加载时会导致崩溃 (0xC0000409)，
        # 因此改为懒加载：只在真正播放视频时才尝试初始化引擎
        self._engine = None

    def _on_engine_position(self, pos_ms: int):
        """引擎位置回调"""
        self.positionChanged.emit(pos_ms)

    def _on_engine_end(self):
        """引擎播放结束回调"""
        logger.info("媒体播放结束")
        self.mediaFinished.emit()

    def _on_engine_error(self, error_msg: str):
        """引擎错误回调"""
        logger.error(f"播放引擎错误: {error_msg}")
        self.errorOccurred.emit(error_msg)

    # ---------- 公共 API ----------

    def playMedia(self, file_path: str):
        """
        播放/显示媒体文件（图片或视频自动识别）

        Args:
            file_path: 媒体文件路径
        """
        if not file_path or not os.path.isfile(file_path):
            self.errorOccurred.emit(f"文件不存在: {file_path}")
            return

        self._current_path = file_path

        # 停止当前播放
        self.stopMedia()

        if is_image_file(file_path):
            self._play_image(file_path)
        elif is_video_file(file_path):
            self._play_video(file_path)
        else:
            # 尝试作为图片播放
            self._play_image(file_path)

        self.mediaLoaded.emit(file_path)

    def stopMedia(self):
        """停止所有播放"""
        self._stop_gif()
        self._stop_video()
        self._current_path = ""
        self._media_type = ""
        self._current_image = None
        self._current_pixmap = None
        self._image_label.clear()
        self._image_label.setVisible(False)
        self._scroll_area.setVisible(False)
        self._video_container.setVisible(False)

    def pauseMedia(self):
        """暂停/恢复"""
        if self._media_type == "video":
            if self._engine:
                self._engine.pause()
        # 图片模式不需要暂停操作

    def setScaleMode(self, mode: int):
        """设置缩放模式"""
        self._scale_mode = mode
        if self._media_type == "image":
            self._render_image()
        elif self._media_type == "video":
            # QVideoWidget 默认保持宽高比
            pass

    def getScaleMode(self) -> int:
        return self._scale_mode

    def getCurrentPath(self) -> str:
        return self._current_path

    def getMediaType(self) -> str:
        """返回 'image' 或 'video'"""
        return self._media_type

    def isImage(self) -> bool:
        return self._media_type == "image"

    def isVideo(self) -> bool:
        return self._media_type == "video"

    def isGif(self) -> bool:
        return self._media_type == "image" and self._current_path.lower().endswith('.gif')

    # ---------- 视频控制 API ----------

    def getPosition(self) -> int:
        """获取当前播放位置（毫秒）"""
        if self._engine and self._media_type == "video":
            return self._engine.get_position()
        return 0

    def getDuration(self) -> int:
        """获取视频总时长（毫秒）"""
        if self._engine and self._media_type == "video":
            return self._engine.get_duration()
        return 0

    def setPosition(self, pos_ms: int):
        """设置播放位置"""
        if self._engine and self._media_type == "video":
            self._engine.set_position(pos_ms)

    def isPlaying(self) -> bool:
        """是否正在播放"""
        if self._engine and self._media_type == "video":
            return self._engine.is_playing()
        return False

    def setVolume(self, vol: int):
        """设置音量 0-100"""
        if self._engine:
            self._engine.set_volume(vol)

    def getVolume(self) -> int:
        if self._engine:
            return self._engine.get_volume()
        return 50

    def screenshot(self, save_path: str) -> bool:
        """
        截图
        需要 VLC 或 MPV 后端支持，Qt 兜底后端不支持直接截图
        """
        if self._engine:
            if isinstance(self._engine, (VlcEngine, MpvEngine)):
                return self._engine.screenshot(save_path)
            else:
                logger.warning("Qt 后端不支持直接截图，请安装 python-vlc 或 python-mpv")
        return False

    def getEngineInfo(self) -> str:
        """获取当前引擎信息"""
        if isinstance(self._engine, VlcEngine):
            return "VLC"
        elif isinstance(self._engine, MpvEngine):
            return "MPV"
        elif isinstance(self._engine, QtEngine):
            return "Qt"
        return "None"

    # ---------- 图片播放 ----------

    def _play_image(self, file_path: str):
        """显示图片（直接加载，不使用延迟调用避免黑屏问题）"""
        self._media_type = "image"
        self._video_container.setVisible(False)
        self._scroll_area.setVisible(True)

        # 停止 GIF 帧切换
        self._stop_gif()

        # Bug A 修复: 显示图片之前确保 image_label 可见
        # stopMedia() 会将 image_label 隐藏，此处需恢复
        self._image_label.setVisible(True)

        # 显示 GIF 或静态图片（直接调用，不通过 QTimer.singleShot 延迟）
        # 延迟调用会导致加载滞后立即渲染，在组件的 viewport 尚未就绪时
        # 返回尺寸为 0 的 viewport，从而不渲染任何内容，出现黑屏
        if file_path.lower().endswith('.gif'):
            self._play_gif(file_path)
        else:
            self._load_static_image(file_path)

    def _load_static_image(self, file_path: str):
        """加载静态图片"""
        try:
            qimage = QImage(file_path)
            if qimage.isNull():
                logger.warning(f"无法加载图片: {file_path}")
                self.errorOccurred.emit(f"无法加载图片: {file_path}")
                return

            self._current_image = qimage
            self._render_image()
        except Exception as e:
            logger.error(f"加载图片失败: {e}")
            self.errorOccurred.emit(f"加载图片失败: {e}")

    def _render_image(self):
        """根据当前窗口尺寸重新渲染图片"""
        if self._current_image is None:
            return

        try:
            viewport_size = self._scroll_area.viewport().size()
            target_w = viewport_size.width()
            target_h = viewport_size.height()

            if target_w <= 0 or target_h <= 0:
                return

            if self._scale_mode == MediaDisplayWidget.SCALE_ORIGINAL:
                # 原始大小
                pixmap = QPixmap.fromImage(self._current_image)
                self._image_label.resize(pixmap.width(), pixmap.height())
                self._image_label.setPixmap(pixmap)
            elif self._scale_mode == MediaDisplayWidget.SCALE_FILL:
                # 填充（裁剪，不保持宽高比）
                pixmap = QPixmap.fromImage(
                    self._current_image.scaled(
                        target_w, target_h,
                        Qt.AspectRatioMode.IgnoreAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )
                )
                self._image_label.resize(target_w, target_h)
                self._image_label.setPixmap(pixmap)
            else:
                # SCALE_FIT: 保持宽高比适应
                scaled = self._current_image.scaled(
                    target_w, target_h,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                pixmap = QPixmap.fromImage(scaled)
                self._image_label.resize(scaled.width(), scaled.height())
                self._image_label.setPixmap(pixmap)

            self._current_pixmap = pixmap
        except Exception as e:
            logger.error(f"图片渲染失败: {e}")

    # ---------- GIF 播放 (硬件加速 + 后台解码) ----------

    def _play_gif(self, file_path: str):
        """
        播放 GIF 动画（全异步解码，边解码边播放）

        流程：
        1. 启动后台线程解码所有帧
        2. 首帧解码到达后立即显示并启动定时器
        3. 后续帧到达后填入缓存，定时器推进时自然切换
        4. 切换到其他媒体时自动停止解码和播放
        """
        if not os.path.isfile(file_path):
            self.errorOccurred.emit(f"GIF 文件不存在: {file_path}")
            return

        # 统一使用 QLabel 软件渲染（避免 Windows OpenGL 上下文未就绪导致的崩溃）
        self._gif_render_widget.setVisible(False)
        self._scroll_area.setVisible(True)
        self._image_label.setVisible(True)

        # 初始状态
        self._gif_frames = []
        self._gif_durations = []
        self._gif_idx = 0
        self._gif_playing = True
        self._gif_progressive_mode = True  # 后台解码进行中
        self._gif_total_frames = 0
        # 启动后台解码（边解码边播放）
        self._start_background_decoder(file_path)

    # ---------- 全异步解码 + 渐进式播放 ----------

    def _start_background_decoder(self, file_path: str):
        """启动后台解码器"""
        self._gif_decoder_thread = GifDecoderThread(self)
        self._gif_decoder_thread.frame_decoded.connect(self._on_gif_frame_decoded)
        self._gif_decoder_thread.decoding_finished.connect(self._on_gif_decoding_finished)
        self._gif_decoder_thread.decoding_error.connect(self._on_gif_decoding_error)
        self._gif_decoder_thread.decode(file_path)

        # 帧切换定时器（先不启动，等首帧到达后再启动）
        self._gif_timer = QTimer(self)
        self._gif_timer.setSingleShot(True)
        self._gif_timer.timeout.connect(self._advance_gif_frame_progressive)

    def _on_gif_frame_decoded(self, data: bytes, width: int, height: int, duration_ms: int, frame_index: int):
        """
        后台解码完成一帧（在主线程接收，将 bytes 转换为 QPixmap）

        安全策略：
        后台线程只发送 Python 原生类型（bytes + int），不发送任何 Qt 对象。
        在主线程中创建 QImage 和 QPixmap，绝对安全。

        关键行为：
        - 帧 0（首帧）到达时：立即显示并启动定时器
        - 后续帧到达时：追加到缓存，等待定时器推进后自然切换
        """
        if not self._gif_playing:
            return

        logger.debug(f"[主线程] 收到帧 {frame_index}: {width}x{height}, data_len={len(data)}")

        try:
            # 在主线程创建 QImage
            # 重要: QImage(const uchar*, width, height, Format) 不拷贝数据!
            # 它只存储指向 data 字节数组的指针。当 Python 的 bytes 对象被 GC 回收后，
            # QImage 内部指针变成悬空指针，导致后续 fromImage() 崩溃 (0xC000041D)。
            # 必须使用 .copy() 做深拷贝，让 QImage 拥有独立的数据所有权。
            raw_image = QImage(data, width, height, QImage.Format.Format_RGBA8888)
            if raw_image.isNull():
                logger.error(f"[主线程] 帧 {frame_index}: QImage 创建失败（null）")
                return

            # 深拷贝：确保 QImage 拥有独立的像素数据，不依赖 Python bytes 的生命周期
            image = raw_image.copy()

            # 在主线程将 QImage 转换为 QPixmap
            pixmap = QPixmap.fromImage(image)
            if pixmap.isNull():
                logger.error(f"[主线程] 帧 {frame_index}: QPixmap 创建失败（null）")
                return

            # 追加到缓存列表
            self._gif_frames.append(pixmap)
            self._gif_durations.append(duration_ms)
            logger.debug(f"[主线程] 帧 {frame_index} 转换成功，当前缓存 {len(self._gif_frames)} 帧")

            # 首帧到达时：立即显示并启动定时器
            if frame_index == 0:
                logger.info("[主线程] 首帧已解码，开始播放 GIF")
                self._show_gif_frame_gpu(0)
        except Exception as e:
            logger.error(f"[主线程] 帧 {frame_index} 转换失败: {e}")

    def _on_gif_decoding_finished(self, total_frames: int):
        """所有帧解码完成"""
        self._gif_total_frames = total_frames
        self._gif_progressive_mode = False
        logger.info(f"GIF 后台解码完成: 共 {total_frames} 帧")

    def _on_gif_decoding_error(self, error_msg: str):
        """解码出错"""
        logger.warning(f"GIF 后台解码出错: {error_msg}")
        self._gif_progressive_mode = False
        if not self._gif_frames:
            self.errorOccurred.emit(f"GIF 解码失败: {error_msg}")

    def _advance_gif_frame_progressive(self):
        """渐进式播放下切换到下一帧"""
        if not self._gif_playing:
            return

        next_idx = self._gif_idx + 1

        if next_idx >= len(self._gif_frames):
            if self._gif_progressive_mode:
                # 后台解码尚未完成，等待更多帧
                # 但先检查解码器是否仍在运行，防止解码器已取消/结束后
                # _gif_progressive_mode 未变 False 导致的无限 50ms 轮询
                decoder_running = (self._gif_decoder_thread is not None
                                   and self._gif_decoder_thread.is_running)
                if decoder_running:
                    # 解码器仍在运行，等待更多帧
                    if self._gif_playing and self._gif_timer is not None:
                        self._gif_timer.start(50)
                else:
                    # 解码器已停止但 _gif_progressive_mode 仍为 True
                    # 说明解码器被取消或出错，已无更多帧到达
                    # 此时正常循环到开头继续播放已解码的帧
                    self._gif_progressive_mode = False
                    next_idx = 0
                    self.mediaFinished.emit()
                return
            else:
                # 所有帧已解码且循环到末尾
                next_idx = 0
                self.mediaFinished.emit()

        self._gif_idx = next_idx
        if self._gif_playing:
            self._show_gif_frame_gpu(self._gif_idx)

    # ---------- 方案 B: 传统同步解码（回退方案） ----------

    def _play_gif_synchronous(self, file_path: str):
        """同步解码 GIF 所有帧（兼容旧方案，已优化 GPU 渲染）"""
        try:
            pil_img = Image.open(file_path)
            frames = []
            durations = []

            while True:
                frame_rgba = pil_img.convert("RGBA")
                data = frame_rgba.tobytes("raw", "RGBA")
                # QImage(const uchar*, ...) 不拷贝数据，直接引用 bytes 的内存。
                # Python 的 data 对象在离开作用域后可能被 GC 回收，导致 QImage
                # 内部指针变成悬空指针，fromImage() 读取时崩溃 (0xC000041D)。
                # 使用 .copy() 深拷贝，让 QImage 拥有独立的数据所有权。
                qimg = QImage(data, frame_rgba.width, frame_rgba.height,
                              QImage.Format.Format_RGBA8888).copy()
                frames.append(QPixmap.fromImage(qimg))

                try:
                    delay = pil_img.info.get("duration", 100)
                    if delay < 20:
                        delay = 100
                except Exception:
                    delay = 100
                durations.append(delay)

                try:
                    pil_img.seek(pil_img.tell() + 1)
                except EOFError:
                    break

            if not frames:
                logger.warning(f"GIF 无帧: {file_path}")
                self.errorOccurred.emit(f"GIF 无帧: {file_path}")
                return

            self._gif_frames = frames
            self._gif_durations = durations
            self._gif_idx = 0
            self._gif_playing = True

            # 显示第一帧（GPU 加速）
            self._show_gif_frame_gpu(0)

            # 启动帧切换定时器
            self._gif_timer = QTimer(self)
            self._gif_timer.setSingleShot(True)
            self._gif_timer.timeout.connect(self._advance_gif_frame_gpu)
            self._gif_timer.start(durations[0])

        except Exception as e:
            logger.error(f"GIF 解码失败: {e}")
            self.errorOccurred.emit(f"GIF 解码失败: {e}")

    def _advance_gif_frame_gpu(self):
        """切换到 GIF 下一帧（GPU 加速模式）"""
        if not self._gif_playing:
            return

        self._gif_idx += 1
        if self._gif_idx >= len(self._gif_frames):
            self._gif_idx = 0
            self.mediaFinished.emit()

        if self._gif_playing:
            self._show_gif_frame_gpu(self._gif_idx)

    def _show_gif_frame_gpu(self, idx: int):
        """使用 GPU 加速渲染显示指定帧"""
        if idx < 0 or idx >= len(self._gif_frames):
            logger.warning(f"[GIF 显示] 索引越界: idx={idx}, len={len(self._gif_frames)}")
            return

        try:
            frame = self._gif_frames[idx]
            if frame is None or frame.isNull():
                logger.error(f"[GIF 显示] 帧 {idx} 为空或无效")
                self._stop_gif()
                return

            logger.trace(f"[GIF 显示] 显示帧 {idx}, 尺寸={frame.width()}x{frame.height()}")

            # ==== 统一使用软件渲染（QLabel）显示 GIF ====
            # QOpenGLWidget + QPainter.drawPixmap 在 Windows 上存在 OpenGL 上下文
            # 生命周期问题：当控件刚 show/raise 时，OpenGL 上下文可能未就绪，
            # 此时调用 painter.drawPixmap() 会导致 GPU 驱动崩溃 (0xC000041D)
            # 因此统一使用 QLabel 软件渲染，避免 OpenGL 相关问题
            viewport = self._scroll_area.viewport()
            target_w = viewport.width() if viewport else self.width()
            target_h = viewport.height() if viewport else self.height()

            if target_w <= 0 or target_h <= 0:
                if self._gif_playing and idx < len(self._gif_durations) and self._gif_timer is not None:
                    self._gif_timer.start(self._gif_durations[idx])
                return

            if self._scale_mode == MediaDisplayWidget.SCALE_ORIGINAL:
                self._image_label.resize(frame.width(), frame.height())
                self._image_label.setPixmap(frame)
            elif self._scale_mode == MediaDisplayWidget.SCALE_FILL:
                scaled = frame.scaled(
                    target_w, target_h,
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self._image_label.resize(target_w, target_h)
                self._image_label.setPixmap(scaled)
            else:
                scaled = frame.scaled(
                    target_w, target_h,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self._image_label.resize(scaled.width(), scaled.height())
                self._image_label.setPixmap(scaled)

            # 启动下一帧定时器
            if self._gif_playing and idx < len(self._gif_durations) and self._gif_timer is not None:
                self._gif_timer.start(self._gif_durations[idx])

        except Exception as e:
            logger.error(f"GIF 帧显示失败: {e}")
            self._stop_gif()

    def _stop_gif(self):
        """停止 GIF 播放并释放资源"""
        self._gif_playing = False
        self._gif_progressive_mode = False

        # 取消后台解码
        if self._gif_decoder_thread and self._gif_decoder_thread.is_running:
            try:
                self._gif_decoder_thread.cancel()
            except Exception:
                pass

        # 停止帧切换定时器
        if self._gif_timer:
            try:
                self._gif_timer.stop()
                self._gif_timer.timeout.disconnect()
            except (TypeError, RuntimeError):
                pass
            self._gif_timer = None

        # 清除缓存
        self._gif_frames = []
        self._gif_durations = []
        self._gif_idx = 0

        # 清除 GPU 渲染控件
        self._gif_render_widget.clear_pixmap()
        self._gif_render_widget.setVisible(False)

    # ---------- 视频播放 ----------

    def _init_engine_lazy(self):
        """懒加载视频引擎（按需初始化，仅在播放视频时调用）"""
        if self._engine is not None:
            return True

        try:
            engine = MediaEngine.get_preferred_engine(self._video_container)
            if engine:
                self._engine = engine
                self._engine.set_position_callback(self._on_engine_position)
                self._engine.set_end_callback(self._on_engine_end)
                self._engine.set_error_callback(self._on_engine_error)
                return True
        except Exception as e:
            logger.warning(f"初始化播放引擎失败: {e}")
            self._engine = None

        return False

    def _play_video(self, file_path: str):
        """播放视频文件"""
        self._media_type = "video"
        self._scroll_area.setVisible(False)
        self._video_container.setVisible(True)

        if self._init_engine_lazy():
            try:
                self._engine.play(file_path)
                return
            except Exception as e:
                logger.error(f"引擎播放失败: {e}")

        self.errorOccurred.emit("没有可用的视频播放引擎")

    def _stop_video(self):
        """停止视频播放"""
        if self._engine:
            try:
                self._engine.stop()
            except Exception as e:
                logger.warning(f"停止视频播放失败: {e}")

    # ---------- 事件处理 ----------

    def resizeEvent(self, event: QResizeEvent):
        """窗口大小变化时自适应"""
        super().resizeEvent(event)

        if self._media_type == "image":
            # 防抖处理：延迟 150ms 后执行
            if self._resize_timer is None:
                self._resize_timer = QTimer(self)
                self._resize_timer.setSingleShot(True)
                self._resize_timer.timeout.connect(self._on_deferred_resize)

            self._pending_resize = True
            self._resize_timer.start(150)

    def _on_deferred_resize(self):
        """延迟执行的自适应渲染"""
        if not self._pending_resize:
            return
        self._pending_resize = False

        if self._media_type == "image":
            self._render_image()
        elif self._media_type == "video":
            # QVideoWidget 自动处理
            pass

    def closeEvent(self, event):
        """关闭时释放资源"""
        self.stopMedia()
        if self._engine:
            try:
                self._engine.release()
            except Exception:
                pass
        super().closeEvent(event)

    @staticmethod
    def isAvailable() -> bool:
        """检查是否有可用的播放引擎"""
        return VLC_AVAILABLE or MPV_AVAILABLE or True  # Qt 始终可用