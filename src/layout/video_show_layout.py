import os, glob
import time
import subprocess

import send2trash
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtMultimediaWidgets import QVideoWidget
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *

from loguru import logger

from src.data_manager.config_manager import ConfigManager
from src.data_manager.position_manager import PositionManager
from src.layout.floating_control_panel import FloatingControlPanel
from src.layout.video_cut_thread import VideoCutThread
from src.layout.custom_slider import CustomSlider
from src.layout.range_slider import QRangeSlider
from src.utils import get_ffmpeg_path as utils_get_ffmpeg_path


class VideoShowLayout(QVBoxLayout):
    video_show_list_key = 'video.show.list'
    video_show_path_key = 'video.show.path'
    video_screenshot_path_key = 'video.screenshot.path'
    video_cut_path_key = 'video.cut.path'
    ffmpeg_path_key = "video.ffmpeg.path"
    play_mode_one = 0       # 单次播放
    play_mode_list = 1      # 列表播放
    play_mode_one_loop = 2  # 单视频循环播放

    def __init__(self, main_window, *args, **kwargs):
        super(*args, **kwargs).__init__(*args, **kwargs)

        self.main_window = main_window
        self.path = ''
        self.cut_start = 0
        self.cut_end = 1000
        self.bar_slider_maxvalue = 1000
        self.play_state = False
        self.config_manager = ConfigManager()
        self.play_list = []
        self.play_list_index = 0
        self.play_mode = VideoShowLayout.play_mode_one

        # 播放位置记忆（使用 PositionManager 统一管理）
        self._position_save_count = 0  # 每 5 秒保存一次
        self.position_manager = PositionManager()

        self.get_ffmpeg_path()

        self.titleQLabel = QLabel("Title")
        self.titleQLabel.setText("Title")
        self.titleQLabel.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.titleQLabel.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.titleQLabel.setVisible(False)  # 路径已移至窗口标题栏显示
        self.addWidget(self.titleQLabel)

        self.player = QMediaPlayer()
        self.video_widget = QVideoWidget()
        self.player.setVideoOutput(self.video_widget)

        # 媒体状态变化信号：加载完成后跳转到记忆位置
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self._pending_seek_position = -1  # 待跳转的播放位置（-1 表示无跳转）
        self._pending_seek_attempts = 0   # 已重试次数（timer 后备）

        self.qscrollarea = QScrollArea()

        # Use PyQt5 QDesktopWidget instead of PIL.ImageGrab for screen size
        desktop = QApplication.desktop()
        screen_width = desktop.width()
        screen_height = desktop.height()
        self.screen_width = int(screen_width * main_window.left / (main_window.left + main_window.right))
        self.screen_height = int(screen_height * main_window.left / (main_window.left + main_window.right))
        self.qscrollarea.setGeometry(QRect(0, 0, self.screen_width, self.screen_height))

        self.qscrollarea.setWidgetResizable(True)
        self.qscrollarea.setWidget(self.video_widget)

        self.bar_hbox = QHBoxLayout()
        self.bar_hbox.setObjectName("bar_hbox")

        self.bar_slider = CustomSlider(Qt.Horizontal)
        self.bar_slider.valueChanged.connect(self.slider_progress_moved)
        self.bar_slider.setObjectName("bar_slider")
        self.bar_slider.setMaximum(self.bar_slider_maxvalue)
        self.bar_slider.setMinimum(0)

        self.bar_label = QLabel()
        self.bar_label.setText("已播放:00:00:00")
        self.bar_label_all = QLabel()
        self.bar_label_all.setText("总时长:00:00:00")

        self.bar_hbox.addWidget(self.bar_slider)
        self.bar_hbox.addWidget(self.bar_label)
        self.bar_hbox.addWidget(self.bar_label_all)

        self.controal_hbox = QHBoxLayout()
        self.controal_hbox.setObjectName("controal_hbox")

        self.down_btn = QPushButton()
        self.down_btn.setText("快退")
        self.down_btn.clicked.connect(self.down_time)
        self.controal_hbox.addWidget(self.down_btn)
        self.stop_btn = QPushButton()
        self.stop_btn.setText("播放")
        self.stop_btn.clicked.connect(self.run_or_stop)
        self.controal_hbox.addWidget(self.stop_btn)
        self.up_btn = QPushButton()
        self.up_btn.setText("快进")
        self.up_btn.clicked.connect(self.up_time)
        self.controal_hbox.addWidget(self.up_btn)

        self.previous_btn = QPushButton()
        self.previous_btn.setText("上一个")
        self.previous_btn.clicked.connect(self.previous)
        self.controal_hbox.addWidget(self.previous_btn)
        self.list_btn = QPushButton()
        self.list_btn.setText("播放列表")
        self.list_btn.clicked.connect(self.run_list)
        self.controal_hbox.addWidget(self.list_btn)
        self.loop_btn = QPushButton()
        self.loop_btn.setText("🔂 单曲循环")
        self.loop_btn.setCheckable(True)
        self.loop_btn.toggled.connect(self._toggle_loop)
        self.controal_hbox.addWidget(self.loop_btn)
        self.next_btn = QPushButton()
        self.next_btn.setText("下一个")
        self.next_btn.clicked.connect(self.next)
        self.controal_hbox.addWidget(self.next_btn)

        self.delete_btn = QPushButton()
        self.delete_btn.setText("删除")
        self.delete_btn.clicked.connect(self.delete)
        self.controal_hbox.addWidget(self.delete_btn)

        self.screenshot_button = QPushButton('截图')
        self.screenshot_button.clicked.connect(self.screenshot)
        self.controal_hbox.addWidget(self.screenshot_button)

        self.fullScreenBtn = QPushButton("全屏")
        self.controal_hbox.addWidget(self.fullScreenBtn)
        self.fullScreenBtn.pressed.connect(main_window.full_screen_custom)

        self.cut_bar_hbox = QHBoxLayout()
        self.cut_bar_hbox.setObjectName("cut_bar_hbox")

        self.cut_bar_label_start = QPushButton()
        self.cut_bar_label_start.setText("开始:")
        self.cut_bar_label_start.clicked.connect(self.get_video_start)
        self.cut_bar_edit_start = QLineEdit()
        self.cut_bar_edit_start.setMaximumSize(QSize(70, 30))
        self.cut_bar_edit_start.setObjectName("cut_bar_label_start")
        self.cut_bar_edit_start.setText("00:00:00")
        self.cut_bar_label_end = QPushButton()
        self.cut_bar_label_end.clicked.connect(self.get_video_end)
        self.cut_bar_label_end.setText("结束:")
        self.cut_bar_edit_end = QLineEdit()
        self.cut_bar_edit_end.setMaximumSize(QSize(70, 30))
        self.cut_bar_edit_end.setObjectName("cut_bar_label_end")
        self.cut_bar_edit_end.setText("00:00:00")

        self.cut_bar_slider = QRangeSlider()
        self.cut_bar_slider.startValueChanged.connect(self.slider_start)
        self.cut_bar_slider.endValueChanged.connect(self.slider_end)
        self.cut_bar_slider.setMax(self.bar_slider_maxvalue)
        self.cut_bar_slider.setMin(0)
        self.cut_bar_slider.setRange(0, self.bar_slider_maxvalue)

        self.cut_bar_hbox.addWidget(self.cut_bar_slider)
        self.cut_bar_hbox.addWidget(self.cut_bar_label_start)
        self.cut_bar_hbox.addWidget(self.cut_bar_edit_start)
        self.cut_bar_hbox.addWidget(self.cut_bar_label_end)
        self.cut_bar_hbox.addWidget(self.cut_bar_edit_end)

        self.cut_btn = QPushButton()
        self.cut_btn.setText("剪切")
        self.cut_btn.clicked.connect(self.video_cut)
        self.cut_bar_hbox.addWidget(self.cut_btn)

        self.bar_hbox_qwidget = QWidget()
        self.bar_hbox_qwidget.setLayout(self.bar_hbox)

        self.controal_hbox_qwidget = QWidget()
        self.controal_hbox_qwidget.setLayout(self.controal_hbox)

        self.cut_bar_hbox_qwidget = QWidget()
        self.cut_bar_hbox_qwidget.setLayout(self.cut_bar_hbox)

        self.addWidget(self.qscrollarea)
        # 记录控制控件的插入位置（在 qscrollarea 之后）
        self._control_widget_start_index = self.count()
        self.addWidget(self.bar_hbox_qwidget)
        self.addWidget(self.controal_hbox_qwidget)
        self.addWidget(self.cut_bar_hbox_qwidget)

        # 全屏悬浮控制面板（初始不添加控件）
        self.floating_panel = FloatingControlPanel(main_window)
        self.floating_panel.setWindowOpacity(1.0)
        self.floating_panel.hide()
        self._is_fullscreen = False

        self.timer = QTimer()
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.onTimerOut)

        # 监听窗口大小变化：视频 QScrollArea 自适应
        self.main_window.installEventFilter(self)

    def enter_fullscreen_mode(self):
        """进入全屏模式：将控制控件移动到悬浮面板，只保留视频画面"""
        self._is_fullscreen = True
        # 隐藏标题（全屏时不需要显示文件路径）
        self.titleQLabel.setVisible(False)

        # 将控制控件从主布局移除并添加到悬浮面板
        self._move_controls_to_panel()

        # 显示悬浮面板
        QTimer.singleShot(500, self._show_floating_panel)

    def exit_fullscreen_mode(self):
        """退出全屏模式：恢复到普通布局"""
        self._is_fullscreen = False
        # 隐藏悬浮面板并从面板中移除控件
        self.floating_panel.hide()
        self.floating_panel.clearControlWidgets()

        # 将控制控件恢复到主布局中的正确位置
        self._restore_controls_from_panel()

        # 恢复标题显示
        self.titleQLabel.setVisible(True)
        self.bar_hbox_qwidget.setVisible(True)
        self.controal_hbox_qwidget.setVisible(True)
        self.cut_bar_hbox_qwidget.setVisible(True)

    def _move_controls_to_panel(self):
        """将控制控件从主布局移动到悬浮面板"""
        # 从主布局移除
        for w in [self.bar_hbox_qwidget, self.controal_hbox_qwidget, self.cut_bar_hbox_qwidget]:
            self.removeWidget(w)
            w.setParent(None)

        # 添加到悬浮面板（确保它们可见，因为之前可能被 setVisible(False) 隐藏了）
        self.floating_panel.addControlWidget(self.bar_hbox_qwidget)
        self.floating_panel.addControlWidget(self.controal_hbox_qwidget)
        self.floating_panel.addControlWidget(self.cut_bar_hbox_qwidget)
        self.bar_hbox_qwidget.setVisible(True)
        self.controal_hbox_qwidget.setVisible(True)
        self.cut_bar_hbox_qwidget.setVisible(True)

    def _restore_controls_from_panel(self):
        """将控制控件从悬浮面板恢复到主布局"""
        # 控件已在 clearControlWidgets 中被移出 panel，只需插入回主布局
        # 按原有顺序插入到 qscrollarea 之后
        index = self._control_widget_start_index
        self.insertWidget(index, self.bar_hbox_qwidget)
        self.insertWidget(index + 1, self.controal_hbox_qwidget)
        self.insertWidget(index + 2, self.cut_bar_hbox_qwidget)

    def _show_floating_panel(self):
        """延迟显示悬浮面板（等待全屏切换完成）"""
        if not self._is_fullscreen:
            return
        self.floating_panel.resizeToFitContent()
        self.floating_panel.repositionDefault()
        self.floating_panel.setWindowOpacity(1.0)
        self.floating_panel.show()

    def previous(self):
        if len(self.play_list) == 0 or len(self.play_list) == self.play_list_index:
            self.main_window.notice('列表未加载或已全部播放完毕')
            self.play_mode = VideoShowLayout.play_mode_one
            return
        self.play_list_index -= 1
        if self.play_list_index <= 0:
            self.play_list_index = 0
        self.play(self.play_list[self.play_list_index])

    def next(self):
        if len(self.play_list) == 0 or len(self.play_list) == self.play_list_index:
            self.main_window.notice('列表未加载或已全部播放完毕')
            self.play_mode = VideoShowLayout.play_mode_one
            return
        self.play_list_index += 1
        if self.play_list_index >= len(self.play_list):
            self.play_list_index = len(self.play_list) - 1
        self.play(self.play_list[self.play_list_index])

    def run_list(self):
        # 如果按钮文本是"重播列表"，表示用户想重新播放整个列表
        if self.list_btn.text() == "重播列表":
            self.play_list_index = 0
            self.list_btn.setText("播放列表")
            self.play_state = True
            self.stop_btn.setText('暂停')
            self.play_mode = VideoShowLayout.play_mode_list
            if len(self.play_list) > 0:
                self.play(self.play_list[0])
            return

        if len(self.play_list) == 0 or self.play_list_index >= len(self.play_list):
            # 列表播放完毕，切换按钮为"重播列表"
            self.list_btn.setText("重播列表")
            self.main_window.notice('列表已全部播放完毕，点击"重播列表"重新播放')
            self.play_mode = VideoShowLayout.play_mode_one
            self.play_state = False
            self.stop_btn.setText('播放')
            return

        self.play_state = True
        self.stop_btn.setText('暂停')
        self.play_mode = VideoShowLayout.play_mode_list
        self.play(self.play_list[self.play_list_index])

    def up_time(self):
        num = self.player.position() + int(self.player.duration() / 100)
        self.player.setPosition(num)
        self.onTimerOut()

    def down_time(self):
        num = self.player.position() - int(self.player.duration() / 80)
        self.player.setPosition(num)
        self.onTimerOut()

    def pause(self):
        if self.play_state:
            self._save_position()  # 暂停时保存位置
            self.player.pause()
            self.play_state = False
            self.stop_btn.setText("播放")
        else:
            self.player.play()
            self.play_state = True
            self.stop_btn.setText("暂停")

    def run_or_stop(self):
        if self.play_state:
            self._save_position()  # 停止时保存位置
            self.player.pause()
            self.timer.stop()
            self.play_state = False
            self.stop_btn.setText("播放")
        else:
            if self.player.position() < self.player.duration():
                self.player.play()
                self.timer.start()
                self.play_state = True
                self.stop_btn.setText("暂停")
            else:
                self.timer.start()
                self.bar_slider.setValue(0)
                self.player.setPosition(0)
                self.player.play()

    def play(self, filePath):
        self.titleQLabel.setText(filePath)
        self.path = filePath

        # 更新标题栏：显示文件名和播放进度
        self._update_title_bar(filePath)

        # 先加载上次播放位置（必须在 setMedia 之前，因为 durationChanged 信号可能在
        # setMedia 时立刻触发，需要 _pending_seek_position 已就绪）
        saved_pos = self._load_position()
        self._pending_seek_position = saved_pos if saved_pos > 0 else -1
        if saved_pos > 0:
            self.main_window.notice(f"正在恢复上次播放位置...")

        self.player.setMedia(QMediaContent(QUrl.fromLocalFile(r'' + filePath)))
        self.player.play()
        self.play_state = True
        self.stop_btn.setText("暂停")

        self.timer.start()

        # 播放开始后自动聚焦到视频区域（方便键盘快捷键操作）
        self.video_widget.setFocus()

    def _update_title_bar(self, filePath):
        """更新窗口标题栏显示文件名和播放进度"""
        basename = os.path.basename(filePath) if filePath else ""
        filename = os.path.splitext(basename)[0]
        total = len(self.play_list)
        if total > 0 and 0 <= self.play_list_index < total:
            progress = f"({self.play_list_index + 1}/{total})"
        else:
            progress = ""
        try:
            self.main_window.title_bar.setInfo(filename, progress)
        except Exception as e:
            logger.warning(f"更新标题栏失败: {e}")

    def _seek_to_saved_position(self, saved_pos, duration=None):
        """
        跳转到保存的播放位置。
        
        Args:
            saved_pos: 要跳转的位置（毫秒）
            duration: 当前视频时长（毫秒），可选。传 None 时从 player.duration() 获取
        """
        if duration is None:
            duration = self.player.duration()
        if saved_pos > 0 and saved_pos < duration:
            self.player.setPosition(saved_pos)
            self.main_window.notice(f"已恢复上次播放位置")
            return True
        logger.debug(f"跳转失败: saved_pos={saved_pos}, duration={duration}")
        return False

    def _on_media_status_changed(self, status):
        """
        媒体状态变化时，尝试执行待跳转。
        QMediaPlayer 状态枚举：
            2=LoadingMedia, 3=LoadedMedia, 4=StalledMedia, 
            5=BufferingMedia, 6=BufferedMedia, 7=EndOfMedia, 8=InvalidMedia
        macOS AVFoundation 上，bufferedMedia(6) 是确认媒体已完全可操作的最佳时机。
        """
        logger.debug(f"媒体状态变化: {status}, 待跳转位置: {self._pending_seek_position}")
        if self._pending_seek_position > 0:
            if status in (QMediaPlayer.BufferedMedia, QMediaPlayer.LoadedMedia):
                # 延迟 200ms 确保播放器内部状态已就绪，setPosition 不会丢失
                QTimer.singleShot(200, lambda: self._try_pending_seek())
        elif status in (QMediaPlayer.InvalidMedia, QMediaPlayer.EndOfMedia):
            self._pending_seek_position = -1

    def _on_duration_changed(self, duration):
        """
        durationChanged 作为 _on_media_status_changed 的后备。
        如果 _pending_seek_position 还未被消费，在此处触发延迟跳转。
        """
        logger.debug(f"时长已就绪: {duration}ms, 待跳转位置: {self._pending_seek_position}")
        if self._pending_seek_position > 0 and duration > 0:
            QTimer.singleShot(200, lambda: self._try_pending_seek())

    def _try_pending_seek(self):
        """
        执行待跳转。仅当播放器处于 BufferedMedia/LoadedMedia 状态时才跳转，
        否则延迟重试。macOS AVFoundation 在 Loading 状态下调用 setPosition 会被忽略。
        """
        if self._pending_seek_position <= 0:
            return
        
        # 检查播放器状态：仅在 BufferedMedia(6) 或 LoadedMedia(3) 时才能安全 seek
        media_status = self.player.mediaStatus()
        if media_status not in (QMediaPlayer.BufferedMedia, QMediaPlayer.LoadedMedia):
            logger.debug(f"播放器未就绪（状态={media_status}），延迟重试跳转 position={self._pending_seek_position}")
            # 每秒重试一次，最多重试 5 次
            self._pending_seek_attempts += 1
            if self._pending_seek_attempts <= 5:
                QTimer.singleShot(1000, self._try_pending_seek)
            else:
                logger.warning(f"等待播放器就绪超时，放弃跳转 position={self._pending_seek_position}")
                self._pending_seek_position = -1
            return
        
        saved_pos = self._pending_seek_position
        self._pending_seek_position = -1  # 清除标记，避免重复跳转
        self._pending_seek_attempts = 0
        success = self._seek_to_saved_position(saved_pos)
        if success:
            logger.info(f"已恢复上次播放位置: {saved_pos}")

    def slider_start(self, value):
        tangent = value / self.bar_slider_maxvalue * self.player.duration()
        m, s = divmod(tangent / 1000, 60)
        h, m = divmod(m, 60)
        text = "%02d:%02d:%02d" % (h, m, s)
        self.cut_bar_edit_start.setText(text)
        self.cut_start = int(tangent / 1000)

    def slider_end(self, value):
        tangent = value / self.bar_slider_maxvalue * self.player.duration()
        if tangent == 0:
            return
        m, s = divmod(tangent / 1000, 60)
        h, m = divmod(m, 60)
        text = "%02d:%02d:%02d" % (h, m, s)
        self.cut_bar_edit_end.setText(text)
        self.cut_end = int(tangent / 1000)

    def slider_progress_moved(self):
        if self.bar_slider.move_type != 'time':
            self.player.setPosition(round(self.bar_slider.value() * self.player.duration() / self.bar_slider.maximum()))

        m, s = divmod(self.player.position() / 1000, 60)
        h, m = divmod(m, 60)
        text = "%02d:%02d:%02d" % (h, m, s)
        self.bar_label.setText('已播放:' + text)

    def onTimerOut(self):
        position = self.player.position()
        duration = self.player.duration()
        self.cut_bar_slider.duration = self.player.duration() / 1000

        if duration == 0:
            return

        value = round(position * self.bar_slider.maximum() / duration)
        self.bar_slider.setValue(value)
        self.bar_slider.move_type = 'time'

        m, s = divmod(self.player.position() / 1000, 60)
        h, m = divmod(m, 60)
        text = "%02d:%02d:%02d" % (h, m, s)
        self.bar_label.setText('已播放:' + text)
        m, s = divmod(self.player.duration() / 1000, 60)
        h, m = divmod(m, 60)
        text = "%02d:%02d:%02d" % (h, m, s)
        self.bar_label_all.setText('总时长:' + text)

        # 每 5 秒保存一次播放位置
        self._position_save_count += 1
        if self._position_save_count >= 5:
            self._position_save_count = 0
            self._save_position()

        if self.player.position() == self.player.duration():
            if self.play_mode == VideoShowLayout.play_mode_list:
                self.play_list_index += 1
                self.run_list()
                return
            elif self.play_mode == VideoShowLayout.play_mode_one_loop:
                # 单视频循环：从头重新播放
                self.player.setPosition(0)
                self.player.play()
                self.play_state = True
                self.stop_btn.setText("暂停")
                return
            self.stop_btn.setText("播放")
            self.play_state = False
            self.timer.stop()

    def _toggle_loop(self, checked):
        """切换单视频循环模式"""
        if checked:
            self.play_mode = VideoShowLayout.play_mode_one_loop
            self.main_window.notice("已开启单曲循环")
        else:
            self.play_mode = VideoShowLayout.play_mode_one
            self.main_window.notice("已关闭单曲循环")

    def is_video(self, path):
        return path.lower().endswith(('.mp4', '.mkv'))

    def setVisible(self, visible):
        self.titleQLabel.setVisible(visible)
        self.video_widget.setStyleSheet("border:none;")
        self.bar_hbox_qwidget.setVisible(visible)
        self.controal_hbox_qwidget.setVisible(visible)
        self.cut_bar_hbox_qwidget.setVisible(visible)

    def screenshot(self):
        try:
            (path, filename) = os.path.split(self.path)
            (file, ext) = os.path.splitext(filename)
            new_path = os.path.expanduser('~') + os.sep + 'Downloads' + os.sep + file + '_'
            if self.config_manager.exist(VideoShowLayout.video_screenshot_path_key):
                new_path = self.config_manager.get(VideoShowLayout.video_screenshot_path_key) + os.sep + file + '_'

            save_path = new_path + '_' + str(self.player.position()) + '.jpg'

            ffmpeg_path = self.get_ffmpeg_path()
            if not os.path.exists(ffmpeg_path):
                self.main_window.notice('ffmpeg路径获取错误： ' + ffmpeg_path)
                return

            position_sec = self.player.position() / 1000
            command = [
                ffmpeg_path,
                '-ss', str(position_sec),
                '-i', self.path,
                '-vframes', '1',
                '-q:v', '2',
                '-y',
                save_path
            ]
            subprocess.run(command, capture_output=True, timeout=30)

            if os.path.exists(save_path):
                self.main_window.notice('截图成功，保存到 ' + save_path)
                self.main_window.model.refresh()
            else:
                self.main_window.notice("截图失败!!!")
        except subprocess.TimeoutExpired:
            self.main_window.notice("截图超时!!!")
        except Exception as e:
            logger.error(f"截图失败: {e}")
            self.main_window.notice(f"截图失败: {e}")

    def get_video_start(self):
        m, s = divmod(self.player.position() / 1000, 60)
        h, m = divmod(m, 60)
        text = "%02d:%02d:%02d" % (h, m, s)
        self.cut_bar_edit_start.setText(text)

    def get_video_end(self):
        m, s = divmod(self.player.position() / 1000, 60)
        h, m = divmod(m, 60)
        text = "%02d:%02d:%02d" % (h, m, s)
        self.cut_bar_edit_end.setText(text)

    def video_cut(self):
        (path, filename) = os.path.split(self.path)
        (file, ext) = os.path.splitext(filename)
        new_path = os.path.expanduser('~') + os.sep + 'Downloads' + os.sep + file + '_'
        if self.config_manager.exist(VideoShowLayout.video_cut_path_key):
            new_path = self.config_manager.get(VideoShowLayout.video_cut_path_key) + os.sep + file + '_'

        file_name = new_path + self.cut_bar_edit_start.text().replace(':',
                                                                      '') + '-' + self.cut_bar_edit_end.text().replace(
            ':', '') + ext
        ffmpeg_path = self.get_ffmpeg_path()
        if not os.path.exists(ffmpeg_path):
            self.main_window.notice('ffmpeg路径获取错误： ' + ffmpeg_path)
            return
        get_video_max_time = self.get_video_max_time()
        if self.cut_bar_edit_start.text() >= self.cut_bar_edit_end.text() or self.cut_bar_edit_end.text() > get_video_max_time:
            self.main_window.notice(
                '时间设置错误： ' + self.cut_bar_edit_start.text() + '-' + self.cut_bar_edit_end.text())
            return
        command = ffmpeg_path + ' -ss ' + self.cut_bar_edit_start.text() + ' -to ' + self.cut_bar_edit_end.text() + ' -i "' + self.path + '" -vcodec copy -acodec copy "' + file_name + '"'
        logger.info(command)

        self.video_cut_thread = VideoCutThread(command, file_name)
        self.video_cut_thread.finished.connect(self.video_cut_thread_finished)
        self.video_cut_thread.start()

    def get_video_max_time(self):
        m, s = divmod(self.player.duration() / 1000, 60)
        h, m = divmod(m, 60)
        return "%02d:%02d:%02d" % (h, m, s)

    def get_ffmpeg_path(self):
        if self.config_manager.exist(self.ffmpeg_path_key):
            ffmpeg_path = self.config_manager.get(self.ffmpeg_path_key)
            if os.path.exists(ffmpeg_path):
                return ffmpeg_path
            else:
                self.config_manager.remove(self.ffmpeg_path_key)

        ffmpeg_path = utils_get_ffmpeg_path()
        if os.path.exists(ffmpeg_path):
            if not self.config_manager.exist(self.ffmpeg_path_key):
                self.config_manager.add_or_update(self.ffmpeg_path_key, ffmpeg_path)
            return ffmpeg_path

        path_env = os.environ.get('PATH') or os.environ.get('Path', '')
        for item in path_env.split(os.pathsep):
            candidate = os.path.join(item, 'ffmpeg')
            if os.path.exists(candidate):
                if not self.config_manager.exist(self.ffmpeg_path_key):
                    self.config_manager.add_or_update(self.ffmpeg_path_key, candidate)
                return candidate

        return ffmpeg_path

    def video_cut_thread_finished(self, file_name, count):
        while not os.path.exists(file_name):
            if count > 60:
                return
            time.sleep(1)
            if os.path.exists(file_name):
                self.main_window.notice('视频剪切成功，保存到 ' + file_name)
                self.main_window.model.refresh()
                return
            count + -1

    def loadData(self, path):
        if len(self.play_list) > 0:
            self.play_list.clear()
            self.play_list_index = 0

        # 重新加载列表时恢复按钮文本为"播放列表"
        self.list_btn.setText("播放列表")

        files = filter(os.path.isfile, glob.glob(os.path.join(path, "*.mp4")))

        file_date_tuple_list = [(x, os.path.getmtime(x)) for x in files]
        file_date_tuple_list.sort(key=lambda x: x[1])

        for file in file_date_tuple_list:
            if self.is_video(file[0]):
                self.play_list.append(file[0])

    def delete(self):
        if len(self.path) > 0 and self.is_video(self.path):
            (path, filename) = os.path.split(self.path)
            deleted_file_path = self.path
            deleted_file_index = -1
            # 记录被删除文件在播放列表中的位置
            for i, p in enumerate(self.play_list):
                if p == deleted_file_path:
                    deleted_file_index = i
                    break
            # 从播放列表中移除被删除的文件
            if deleted_file_index >= 0:
                self.play_list.pop(deleted_file_index)
                if self.play_list_index > deleted_file_index:
                    self.play_list_index -= 1
                elif self.play_list_index == deleted_file_index:
                    # 当前播放的被删除了，尝试播放下一个
                    if self.play_list_index >= len(self.play_list):
                        self.play_list_index = len(self.play_list) - 1

            # 释放媒体资源，删除和播放下一个延迟到媒体释放完成后执行
            self.player.setMedia(QMediaContent())
            self.player.setVideoOutput(None)
            QTimer.singleShot(200, lambda: self._do_delete(path, filename, deleted_file_path))
        else:
            self.next()

    def _save_position(self):
        """保存当前播放位置到数据库"""
        if not self.path or not os.path.exists(self.path):
            return
        position = self.player.position()
        duration = self.player.duration()
        self.position_manager.save_position(self.path, position, duration)

    def _load_position(self):
        """从数据库加载上次播放位置，返回 position（毫秒），无记录则返回 0"""
        return self.position_manager.load_position(self.path)

    def eventFilter(self, obj, event):
        """监听窗口大小变化事件，视频 QVideoWidget 自适应"""
        if event.type() == QEvent.Resize:
            # QScrollArea 的 setWidgetResizable(True) 会自动处理
            pass  # 交由 QScrollArea 自身处理自适应
        return super().eventFilter(obj, event)

    def _do_delete(self, path, filename, deleted_file_path):
        """实际执行文件删除并播放下一个（在媒体释放后调用）"""
        try:
            # 清理数据库中的播放位置记录
            self.position_manager.delete_position(deleted_file_path)

            os.chdir(path)
            send2trash.send2trash(filename)
            self.main_window.notice(deleted_file_path + ' 文件已删除!!!')
            self.main_window.model.refresh()

            # 首先尝试从播放列表播放下一个
            if len(self.play_list) > 0 and 0 <= self.play_list_index < len(self.play_list):
                self.player.setVideoOutput(self.video_widget)
                self.play(self.play_list[self.play_list_index])
            else:
                # 播放列表为空，扫描目录找下一个视频
                files = filter(os.path.isfile, glob.glob(os.path.join(path, "*.mp4")))
                file_date_tuple_list = [(x, os.path.getmtime(x)) for x in files]
                file_date_tuple_list.sort(key=lambda x: x[1])

                # 找到删除文件的位置，播放下一个
                found = False
                next_file = None
                for file in file_date_tuple_list:
                    if found:
                        next_file = file[0]
                        break
                    if file[0] == deleted_file_path:
                        found = True

                # 如果没有下一个，播放下一个前一个
                if not next_file and len(file_date_tuple_list) > 0:
                    next_file = file_date_tuple_list[-1][0]

                if next_file and os.path.exists(next_file):
                    self.player.setVideoOutput(self.video_widget)
                    self.play(next_file)
                else:
                    self.player.setVideoOutput(self.video_widget)
        except Exception as e:
            self.player.setVideoOutput(self.video_widget)
            self.main_window.notice("文件删除异常!!!" + str(e))
