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
import sys
from typing import Optional, Callable, Any

from PIL import Image

from PyQt6.QtCore import (
    Qt, QTimer, QRect, QEvent, QUrl
)
from PyQt6.QtCore import pyqtSignal as Signal
from PyQt6.QtGui import (
    QPixmap, QImage, QResizeEvent, QPainter, QColor
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea, QApplication
)

from loguru import logger

from src.core.media_player_engine import (
    is_image_file, is_video_file,
    MediaEngine, VlcEngine, MpvEngine, QtEngine,
    VLC_AVAILABLE, MPV_AVAILABLE
)


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

        # 用于图片的 QLabel
        self._image_label = QLabel(self)
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setStyleSheet("background-color: black;")
        self._image_label.setVisible(False)

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

        # ---------- 状态 ----------
        self._current_path: str = ""
        self._media_type: str = ""  # "image" or "video"
        self._scale_mode: int = MediaDisplayWidget.SCALE_FIT

        # 视频引擎
        self._engine: Optional[MediaEngine] = None

        # 图片相关
        self._current_image: Optional[QImage] = None
        self._current_pixmap: Optional[QPixmap] = None

        # GIF 相关
        self._gif_frames: list = []
        self._gif_durations: list = []
        self._gif_idx: int = 0
        self._gif_timer: Optional[QTimer] = None
        self._gif_playing: bool = False

        # 自适应定时器（防抖）
        self._resize_timer: Optional[QTimer] = None
        self._pending_resize: bool = False

        # ---------- 初始化引擎 ----------
        self._init_engine()

    def _init_engine(self):
        """初始化视频引擎，按 VLC > MPV > Qt 优先级"""
        try:
            engine = MediaEngine.get_preferred_engine(self._video_container)
            if engine:
                self._engine = engine
                self._engine.set_position_callback(self._on_engine_position)
                self._engine.set_end_callback(self._on_engine_end)
                self._engine.set_error_callback(self._on_engine_error)
        except Exception as e:
            logger.warning(f"初始化播放引擎失败: {e}")
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
        """显示图片"""
        self._media_type = "image"
        self._video_container.setVisible(False)
        self._scroll_area.setVisible(True)

        # 停止 GIF 帧切换
        self._stop_gif()

        # 显示 GIF 或静态图片
        if file_path.lower().endswith('.gif'):
            QTimer.singleShot(0, lambda: self._play_gif(file_path))
        else:
            QTimer.singleShot(0, lambda: self._load_static_image(file_path))

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

    # ---------- GIF 播放 ----------

    def _play_gif(self, file_path: str):
        """使用 Pillow 解码 GIF 帧动画播放"""
        if not os.path.isfile(file_path):
            self.errorOccurred.emit(f"GIF 文件不存在: {file_path}")
            return

        try:
            pil_img = Image.open(file_path)
            frames = []
            durations = []

            while True:
                frame_rgba = pil_img.convert("RGBA")
                data = frame_rgba.tobytes("raw", "RGBA")
                qimg = QImage(data, frame_rgba.width, frame_rgba.height, QImage.Format.Format_RGBA8888)
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

            # 显示第一帧
            self._show_gif_frame(0)

            # 启动帧切换定时器
            self._gif_timer = QTimer(self)
            self._gif_timer.setSingleShot(True)
            self._gif_timer.timeout.connect(self._advance_gif_frame)
            self._gif_timer.start(durations[0])

        except Exception as e:
            logger.error(f"GIF 解码失败: {e}")
            self.errorOccurred.emit(f"GIF 解码失败: {e}")

    def _advance_gif_frame(self):
        """切换到 GIF 下一帧"""
        if not self._gif_playing:
            return

        self._gif_idx += 1
        if self._gif_idx >= len(self._gif_frames):
            self._gif_idx = 0
            # 完成一次循环，触发 mediaFinished
            self.mediaFinished.emit()

        self._show_gif_frame(self._gif_idx)

    def _show_gif_frame(self, idx: int):
        """显示指定帧并缩放"""
        if idx < 0 or idx >= len(self._gif_frames):
            return

        try:
            viewport = self._scroll_area.viewport()
            target_w = viewport.width() if viewport else self.width()
            target_h = viewport.height() if viewport else self.height()

            if target_w <= 0 or target_h <= 0:
                self._gif_timer.start(self._gif_durations[idx])
                return

            frame = self._gif_frames[idx]

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

            # 继续下一帧（如果还有）
            if self._gif_playing and idx < len(self._gif_durations):
                self._gif_timer.start(self._gif_durations[idx])

        except Exception as e:
            logger.error(f"GIF 帧显示失败: {e}")
            self._stop_gif()

    def _stop_gif(self):
        """停止 GIF 播放"""
        self._gif_playing = False
        if self._gif_timer:
            try:
                self._gif_timer.stop()
                self._gif_timer.timeout.disconnect()
            except (TypeError, RuntimeError):
                pass
            self._gif_timer = None
        self._gif_frames = []
        self._gif_durations = []
        self._gif_idx = 0

    # ---------- 视频播放 ----------

    def _play_video(self, file_path: str):
        """播放视频文件"""
        self._media_type = "video"
        self._scroll_area.setVisible(False)
        self._video_container.setVisible(True)

        if not self._engine:
            logger.warning("没有可用的播放引擎，尝试重新初始化")
            self._init_engine()

        if self._engine:
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