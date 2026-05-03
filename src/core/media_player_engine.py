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
from abc import ABC, abstractmethod
from typing import Optional, Callable

from PyQt6.QtCore import QUrl, QTimer, QRect
from PyQt6.QtWidgets import QWidget
from PyQt6.QtMultimedia import QMediaPlayer
from PyQt6.QtMultimediaWidgets import QVideoWidget

from loguru import logger

# VLC 可用性（懒加载，避免模块导入时加载 libvlc.dll 导致崩溃）
# 注意：vlc.Instance() 会加载 libvlc.dll，某些 Windows 系统上
# 加载 DLL 时可能发生堆栈缓冲区溢出 (0xC0000409)。
# 因此不在模块级别创建 Instance，改为懒加载方式。
VLC_AVAILABLE = False
try:
    import vlc  # 仅导入 Python 包（不加载 DLL），这是安全的
    VLC_AVAILABLE = True  # 标记 vlc 包已安装，后续实际使用时再验证 DLL
    logger.info("python-vlc 已安装，VLC DLL 将在首次使用时加载")
except ImportError:
    logger.info("python-vlc 未安装，VLC 后端不可用")
except Exception as e:
    logger.info(f"导入 vlc 失败，VLC 后端不可用: {e}")


def _check_vlc_dll() -> bool:
    """检查 libvlc.dll 实际可用性（仅在 VLC 引擎实际创建时调用）"""
    try:
        instance = vlc.Instance(['--no-xlib', '--quiet'])
        instance.release()
        return True
    except Exception as e:
        logger.warning(f"libvlc.dll 不可用: {e}")
        return False

# MPV 可用性（懒加载 — 不导入 python-mpv，不搜索 DLL，不在模块加载时执行任何操作）
# python-mpv 导入时会尝试加载 libmpv-2.dll，某些 Windows 系统上
# 加载 DLL 时可能导致崩溃 (0xC0000409)。
# 因此改为懒加载方式，只在需要时动态导入和检测。
MPV_AVAILABLE = False
# 标记 python-mpv 包是否可能可用（没有实际导入，仅保存一个符号）
_MPV_PACKAGE_NAME = "mpv"


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
        """
        获取首选可用引擎，按 VLC > MPV > Qt 优先级

        注意事项：
        - VLC/MPV DLL 的实际加载在此方法中完成，不在模块导入时加载
        - DLL 加载失败时自动降级到下一个可用引擎
        - 此方法只会在首次播放视频时调用（懒加载策略）
        """
        # ---- 尝试 VLC ----
        if VLC_AVAILABLE:
            try:
                engine = VlcEngine(widget)
                logger.info("使用 VLC 后端 (python-vlc)")
                return engine
            except Exception as e:
                logger.warning(f"VLC 初始化失败: {e}")

        # ---- 尝试 MPV ----
        try:
            # MPV 也是懒加载：不依赖模块级 MPV_AVAILABLE，而是动态导入
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
            '--quiet',
            '--avcodec-hw=any',     # 启用硬件加速
        ])
        self._player = self._instance.media_player_new()
        # Bug 修复: 标记 VLC 是否已处于 Ended 状态，防止 stop() 死锁
        # libvlc_media_player_stop() 在 Ended 状态下调用会导致内部互斥锁死锁
        self._media_ended: bool = False

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
        # 注意：不调用 self.stop() - 调用方（MediaDisplayWidget.playMedia）已通过 stopMedia() 停止
        # 在 VLC Ended 状态下重复调用 stop() 可能导致 libvlc 内部死锁
        if not os.path.isfile(file_path):
            logger.error(f"文件不存在: {file_path}")
            return

        self._media = self._instance.media_new(file_path)
        self._player.set_media(self._media)
        # Bug 修复: 移除阻塞的 self._media.parse() 调用
        # libvlc_media_parse() 是同步操作，会阻塞 UI 线程直到元数据解析完成，
        # 对于某些文件（特别是网络流或格式不标准的文件）可能耗时很长，
        # 导致程序在切换视频时无响应。
        # 播放时长通过 self._player.get_length() 异步获取（已在 get_duration() 中兜底）
        self._duration = 0

        # 重置 Ended 标志，新视频开始播放
        self._media_ended = False

        self._player.play()

        # 启动位置轮询
        self._start_position_timer()

    def stop(self):
        self._stop_position_timer()
        if self._player:
            # Bug 修复: 使用 _media_ended 标志避免在 Ended 状态下调用 get_state() 导致死锁
            # 问题背景:
            # 1. VLC 播完视频后 _on_timer() 检测到 State.Ended，设置 _media_ended = True
            # 2. _end_callback 被 singleShot 延迟调用
            # 3. 回调链最终调用到此 stop()
            # 4. 此时调用 get_state() 本身也可能触发 libvlc 内部互斥锁死锁
            # 因此直接检查 _media_ended 标志，避免任何 libvlc 调用
            if self._media_ended:
                logger.debug("_media_ended=True, 跳过 VLC stop() 和 get_state() 以避免死锁")
            else:
                try:
                    self._player.stop()
                except Exception:
                    pass
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
        if not self._player:
            return

        try:
            # Bug E 修复: VLC timer 可能在任何时刻被触发（包括右键菜单操作时）
            # 如果 widget 不可见（例如切换窗口或右键菜单打开），跳过本次回调
            # 避免在文件系统操作（复制/移动/删除）时访问 VLC 内部状态导致崩溃
            if self._widget and not self._widget.isVisible():
                return
        except Exception:
            return  # widget 可能已被销毁

        try:
            if not self._player.is_playing():
                # Bug 8 修复: 使用 VLC 状态机准确区分"暂停"和"播放结束"
                # 暂停时 is_playing() 返回 False，但不应触发 end_callback
                # - VLC State.Paused: 用户按了暂停
                # - VLC State.Ended: 播放真正结束
                # - Bug C 修复: 当 is_playing() 为 False 但 get_state() 仍返回 Playing 时，
                #   说明 VLC 正处于 Playing→Paused 过渡期，此时不做任何操作
                try:
                    state = self._player.get_state()
                except Exception:
                    state = None

                if state == vlc.State.Ended:
                    # Bug 修复: 标记 Ended 状态，防止后续 stop() 调用导致死锁
                    # libvlc_media_player_stop() 在 Ended 状态下调用会导致内部互斥锁死锁
                    self._media_ended = True
                    if self._end_callback:
                        # Bug 修复: 使用 singleShot 延迟回调，避免定时器重入问题
                        # 直接调用 _end_callback() 可能导致：
                        # 1. 回调链中 stop() + play() 重新创建了定时器
                        # 2. 本方法末尾的 _stop_position_timer() 会误杀新创建的定时器
                        # 3. VLC 在 Ended 状态下直接 stop() 可能死锁
                        QTimer.singleShot(0, self._end_callback)
                    self._stop_position_timer()
                elif state == vlc.State.Paused:
                    # 真正的暂停状态，不触发 end_callback
                    pass
                elif state == vlc.State.Playing:
                    # Bug C 修复: Playing 但 is_playing() 返回 False → 过渡期，忽略
                    pass
                else:
                    # 状态未知(State.Stopped/State.Error/None)时
                    # 使用位置作为兜底判断
                    pos = self._player.get_time()
                    dur = self._player.get_length()
                    if dur > 0 and pos >= dur - 1000:
                        if self._end_callback:
                            self._end_callback()
                        self._stop_position_timer()
                return

            pos = self.get_position()
            if self._position_callback:
                self._position_callback(pos)
        except Exception as e:
            logger.warning(f"VLC _on_timer 异常 (可能由右键菜单操作引起): {e}")
            # Bug E 修复: 异常时不崩溃，静默跳过本次回调
            return


# ---------- MPV 后端 ----------

class MpvEngine(MediaEngine):
    """基于 python-mpv 的视频播放引擎

    注意：python-mpv 导入时会加载 libmpv-2.dll，DLL 加载失败时将抛出异常。
    为避免模块导入时崩溃，mpv 的导入在 __init__ 中动态完成（懒加载）。
    """

    def __init__(self, widget: QWidget):
        super().__init__(widget)

        # 动态导入 python-mpv（libmpv-2.dll 的加载在此完成）
        # 某些 Windows 系统上加载 DLL 可能导致 0xC0000409 崩溃，
        # 因此这里使用 try/except 捕获，失败时降级到 Qt 引擎
        try:
            import mpv as _mpv_module
        except ImportError:
            raise RuntimeError("python-mpv 未安装")
        except Exception as e:
            raise RuntimeError(f"python-mpv 加载失败: {e}")

        # 保存引用以防止被 GC
        self._mpv_module = _mpv_module

        self._player = _mpv_module.MPV(
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

    def _has_media(self) -> bool:
        """检查 mpv 是否已加载媒体文件，防止在未加载时访问原生属性导致 0xC0000409 崩溃"""
        try:
            return self._player is not None and self._player.duration is not None
        except Exception:
            return False

    def set_position(self, pos_ms: int):
        if not self._has_media():
            return
        try:
            self._player.time_pos = pos_ms / 1000.0
        except Exception:
            pass

    def get_position(self) -> int:
        if not self._has_media():
            return 0
        try:
            pos = self._player.time_pos
            if pos is not None:
                return int(pos * 1000)
        except Exception:
            pass
        return 0

    def get_duration(self) -> int:
        if not self._has_media():
            return 0
        try:
            dur = self._player.duration
            if dur is not None:
                return int(dur * 1000)
        except Exception:
            pass
        return 0

    def is_playing(self) -> bool:
        if not self._has_media():
            return False
        try:
            return not self._player.pause
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
                # Bug 修复: 使用 singleShot 延迟回调，避免定时器重入问题
                QTimer.singleShot(0, self._end_callback)
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