# -*- coding: utf-8 -*-
"""
媒体播放引擎抽象层：提供统一的视频/图片播放接口

支持后端：
1. VLC (python-vlc) - 首选，硬件加速好，跨平台成熟
2. MPV (python-mpv) - 高性能备选
3. Qt (QMediaPlayer) - 兜底方案，始终可用

自动按优先级选择可用后端。
兼容 macOS 10.9+ (2013年) 和 Windows 7+
"""
import os
import sys
import logging
from abc import ABC, abstractmethod
from typing import Optional, Callable

from PyQt6.QtCore import QUrl, QTimer, QRect, Qt, QEvent
from PyQt6.QtGui import QPixmap, QImage, QResizeEvent, QPaintEvent, QPainter
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QScrollArea
from PyQt6.QtMultimedia import QMediaPlayer
from PyQt6.QtMultimediaWidgets import QVideoWidget

from loguru import logger

# 尝试导入 python-vlc
try:
    import vlc
    VLC_AVAILABLE = True
except ImportError:
    VLC_AVAILABLE = False
    logger.info("python-vlc 未安装，VLC 后端不可用")

# 尝试导入 python-mpv
try:
    import mpv
    MPV_AVAILABLE = True
except ImportError:
    MPV_AVAILABLE = False
    logger.info("python-mpv 未安装，MPV 后端不可用")


# ---------- 常量 ----------

SUPPORTED_IMAGE_EXTENSIONS = (
    '.bmp', '.dib', '.png', '.jpg', '.jpeg', '.pbm', '.pgm', '.ppm',
    '.tif', '.tiff', '.webp', '.gif'
)

SUPPORTED_VIDEO_EXTENSIONS = (
    '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v',
    '.3gp', '.mpg', '.mpeg', '.ts', '.mts'
)


def is_image_file(path: str) -> bool:
    """判断文件是否为支持的图片格式"""
    if not path:
        return False
    return path.lower().endswith(SUPPORTED_IMAGE_EXTENSIONS)


def is_video_file(path: str) -> bool:
    """判断文件是否为支持的视频格式"""
    if not path:
        return False
    return path.lower().endswith(SUPPORTED_VIDEO_EXTENSIONS)


def is_media_file(path: str) -> bool:
    """判断文件是否为支持的媒体文件（图片或视频）"""
    return is_image_file(path) or is_video_file(path)


# ---------- 抽象播放引擎 ----------

class MediaEngine(ABC):
    """媒体播放引擎抽象基类"""

    def __init__(self, widget: QWidget):
        self._widget = widget
        self._position_callback: Optional[Callable[[int], None]] = None
        self._end_callback: Optional[Callable[[], None]] = None
        self._error_callback: Optional[Callable[[str], None]] = None

    @abstractmethod
    def play(self, file_path: str):
        """开始播放"""
        ...

    @abstractmethod
    def stop(self):
        """停止播放"""
        ...

    @abstractmethod
    def pause(self):
        """暂停/恢复"""
        ...

    @abstractmethod
    def set_position(self, pos_ms: int):
        """设置播放位置（毫秒）"""
        ...

    @abstractmethod
    def get_position(self) -> int:
        """获取当前播放位置（毫秒）"""
        ...

    @abstractmethod
    def get_duration(self) -> int:
        """获取总时长（毫秒）"""
        ...

    @abstractmethod
    def is_playing(self) -> bool:
        """是否正在播放"""
        ...

    @abstractmethod
    def set_volume(self, vol: int):
        """设置音量 0-100"""
        ...

    @abstractmethod
    def get_volume(self) -> int:
        """获取音量"""
        ...

    def set_position_callback(self, callback: Callable[[int], None]):
        """设置位置回调"""
        self._position_callback = callback

    def set_end_callback(self, callback: Callable[[], None]):
        """设置播放结束回调"""
        self._end_callback = callback

    def set_error_callback(self, callback: Callable[[str], None]):
        """设置错误回调"""
        self._error_callback = callback

    @abstractmethod
    def screenshot(self, save_path: str) -> bool:
        """截图并保存到路径，返回是否成功"""
        ...

    @abstractmethod
    def release(self):
        """释放资源"""
        ...

    @staticmethod
    def get_preferred_engine(widget: QWidget) -> Optional['MediaEngine']:
        """获取首选可用引擎，按 VLC > MPV > Qt 优先级"""
        if VLC_AVAILABLE:
            try:
                engine = VlcEngine(widget)
                logger.info("使用 VLC 后端 (python-vlc)")
                return engine
            except Exception as e:
                logger.warning(f"VLC 初始化失败: {e}")

        if MPV_AVAILABLE:
            try:
                engine = MpvEngine(widget)
                logger.info("使用 MPV 后端 (python-mpv)")
                return engine
            except Exception as e:
                logger.warning(f"MPV 初始化失败: {e}")

        logger.info("使用 Qt 后端 (QMediaPlayer)")
        return QtEngine(widget)


# ---------- VLC 后端 ----------

class VlcEngine(MediaEngine):
    """基于 python-vlc 的视频播放引擎"""

    def __init__(self, widget: QWidget):
        super().__init__(widget)
        if not VLC_AVAILABLE:
            raise RuntimeError("python-vlc 未安装")

        # VLC 核心实例
        self._instance = vlc.Instance([
            '--no-xlib',
            '--no-audio',           # 我们只需要视频输出
            '--quiet',
            '--avcodec-hw=any',     # 启用硬件加速
        ])
        self._player = self._instance.media_player_new()

        # 设置视频输出到 Qt 窗口
        if sys.platform == 'win32':
            # Windows: 使用 HWND
            self._player.set_hwnd(int(widget.winId()))
        elif sys.platform == 'darwin':
            # macOS: 使用 NSView
            self._player.set_nsobject(int(widget.winId()))
        else:
            # Linux: 使用 X11
            self._player.set_xwindow(int(widget.winId()))

        self._media: Optional[vlc.Media] = None
        self._duration: int = 0
        self._position_timer: Optional[QTimer] = None

    def play(self, file_path: str):
        self.stop()
        if not os.path.isfile(file_path):
            logger.error(f"文件不存在: {file_path}")
            return

        self._media = self._instance.media_new(file_path)
        self._player.set_media(self._media)
        self._media.parse()
        self._duration = self._media.get_duration()

        self._player.play()

        # 启动位置轮询
        self._start_position_timer()

    def stop(self):
        self._stop_position_timer()
        if self._player:
            self._player.stop()
        self._media = None

    def pause(self):
        if self._player.is_playing():
            self._player.pause()
        else:
            self._player.play()
            self._start_position_timer()

    def set_position(self, pos_ms: int):
        if self._player:
            self._player.set_time(pos_ms)

    def get_position(self) -> int:
        if self._player:
            return self._player.get_time()
        return 0

    def get_duration(self) -> int:
        if self._media:
            return self._media.get_duration()
        if self._player:
            return self._player.get_length()
        return 0

    def is_playing(self) -> bool:
        return self._player is not None and self._player.is_playing()

    def set_volume(self, vol: int):
        if self._player:
            self._player.audio_set_volume(max(0, min(100, vol)))

    def get_volume(self) -> int:
        if self._player:
            return self._player.audio_get_volume()
        return 50

    def screenshot(self, save_path: str) -> bool:
        """VLC 截图"""
        try:
            from PIL import Image
            # VLC 直接截图较为复杂，使用临时方案
            if self._player:
                self._player.video_take_snapshot(0, save_path, 0, 0)
                return os.path.exists(save_path)
        except Exception as e:
            logger.error(f"VLC 截图失败: {e}")
        return False

    def release(self):
        self.stop()
        if self._player:
            self._player.release()
            self._player = None
        if self._instance:
            self._instance.release()
            self._instance = None

    def _start_position_timer(self):
        self._stop_position_timer()
        self._position_timer = QTimer(self._widget)
        self._position_timer.setInterval(500)  # 500ms 轮询
        self._position_timer.timeout.connect(self._on_timer)
        self._position_timer.start()

    def _stop_position_timer(self):
        if self._position_timer:
            self._position_timer.stop()
            self._position_timer = None

    def _on_timer(self):
        if not self._player or not self._player.is_playing():
            if self._end_callback:
                self._end_callback()
            self._stop_position_timer()
            return

        pos = self.get_position()
        if self._position_callback:
            self._position_callback(pos)


# ---------- MPV 后端 ----------

class MpvEngine(MediaEngine):
    """基于 python-mpv 的视频播放引擎"""

    def __init__(self, widget: QWidget):
        super().__init__(widget)
        if not MPV_AVAILABLE:
            raise RuntimeError("python-mpv 未安装")

        self._player = mpv.MPV(
            wid=str(int(widget.winId())),
            vo='gpu',               # GPU 视频输出
            hwdec='auto',           # 自动硬件解码
            cache='yes',
            volume=50,
            keep_open=False,
        )

        self._player.register_event_callback(self._on_mpv_event)
        self._position_timer: Optional[QTimer] = None
        self._duration: int = 0

    def play(self, file_path: str):
        self.stop()
        if not os.path.isfile(file_path):
            logger.error(f"文件不存在: {file_path}")
            return
        self._player.play(file_path)
        self._start_position_timer()

    def stop(self):
        self._stop_position_timer()
        try:
            self._player.stop()
        except Exception:
            pass

    def pause(self):
        try:
            self._player.pause = not self._player.pause
        except Exception:
            pass

    def set_position(self, pos_ms: int):
        try:
            self._player.time_pos = pos_ms / 1000.0
        except Exception:
            pass

    def get_position(self) -> int:
        try:
            pos = self._player.time_pos
            if pos is not None:
                return int(pos * 1000)
        except Exception:
            pass
        return 0

    def get_duration(self) -> int:
        try:
            dur = self._player.duration
            if dur is not None:
                return int(dur * 1000)
        except Exception:
            pass
        return 0

    def is_playing(self) -> bool:
        try:
            return not self._player.pause and self._player.time_pos is not None
        except Exception:
            return False

    def set_volume(self, vol: int):
        try:
            self._player.volume = max(0, min(100, vol))
        except Exception:
            pass

    def get_volume(self) -> int:
        try:
            return self._player.volume
        except Exception:
            return 50

    def screenshot(self, save_path: str) -> bool:
        """MPV 截图"""
        try:
            self._player.screenshot_to_file(save_path)
            return os.path.exists(save_path)
        except Exception as e:
            logger.error(f"MPV 截图失败: {e}")
        return False

    def release(self):
        self.stop()
        try:
            self._player.terminate()
        except Exception:
            pass
        self._player = None

    def _on_mpv_event(self, event):
        """MPV 事件回调"""
        if event.get('event') == 'end-file':
            if self._end_callback:
                self._end_callback()
            self._stop_position_timer()

    def _start_position_timer(self):
        self._stop_position_timer()
        self._position_timer = QTimer(self._widget)
        self._position_timer.setInterval(500)
        self._position_timer.timeout.connect(self._on_timer)
        self._position_timer.start()

    def _stop_position_timer(self):
        if self._position_timer:
            self._position_timer.stop()
            self._position_timer = None

    def _on_timer(self):
        if not self.is_playing():
            return
        pos = self.get_position()
        if self._position_callback:
            self._position_callback(pos)


# ---------- Qt 后端（兜底） ----------

class QtEngine(MediaEngine):
    """基于 Qt QMediaPlayer 的视频播放引擎（兜底方案）"""

    def __init__(self, widget: QWidget):
        super().__init__(widget)
        self._player = QMediaPlayer()
        self._video_widget = QVideoWidget()
        self._player.setVideoOutput(self._video_widget)

        # 将 QVideoWidget 嵌入到 widget 中
        self._video_widget.setParent(widget)
        self._video_widget.setGeometry(QRect(0, 0, widget.width(), widget.height()))
        self._video_widget.setVisible(True)

        # 连接信号
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.mediaStatusChanged.connect(self._on_media_status)

        self._last_position: int = 0

    def play(self, file_path: str):
        if not os.path.isfile(file_path):
            logger.error(f"文件不存在: {file_path}")
            return
        self._player.setSource(QUrl.fromLocalFile(file_path))
        self._player.play()

    def stop(self):
        self._player.stop()

    def pause(self):
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def set_position(self, pos_ms: int):
        self._player.setPosition(pos_ms)

    def get_position(self) -> int:
        return self._player.position()

    def get_duration(self) -> int:
        return self._player.duration()

    def is_playing(self) -> bool:
        return self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def set_volume(self, vol: int):
        self._player.setVolume(max(0, min(100, vol)))

    def get_volume(self) -> int:
        return self._player.volume()

    def screenshot(self, save_path: str) -> bool:
        """Qt 后端通过 ffmpeg 外部截图"""
        logger.warning("Qt 后端不支持直接截图，请安装 VLC 或 MPV")
        return False

    def release(self):
        self.stop()
        self._player = None
        self._video_widget = None

    def _on_position_changed(self, pos: int):
        self._last_position = pos
        if self._position_callback:
            self._position_callback(pos)

    def _on_media_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self._end_callback:
                self._end_callback()

    def resize_video_widget(self, w: int, h: int):
        """调整视频窗口大小"""
        if self._video_widget:
            self._video_widget.setGeometry(QRect(0, 0, w, h))