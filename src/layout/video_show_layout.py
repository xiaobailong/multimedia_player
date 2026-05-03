# -*- coding: utf-8 -*-
"""
视频展示布局：管理视频播放、播放列表、截图、剪切

已重构为使用统一的 MediaDisplayWidget + MediaEngine 体系。
支持下层引擎自动选择：VLC > MPV > Qt（兜底）。
兼容 macOS 10.9+ (2013年) 和 Windows 7+
"""
import os, glob
import time
import subprocess

import send2trash
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import QIcon

from loguru import logger

from src.db.config_manager import ConfigManager
from src.core.floating_control_panel import FloatingControlPanel
from src.db.sqlite3_client import Sqlite3Client
from src.core.video_cut_thread import VideoCutThread
from src.core.custom_slider import CustomSlider
from src.core.range_slider import QRangeSlider
from src.core.media_display_widget import MediaDisplayWidget, is_video_file
from src.utils import get_log_path, get_ffmpeg_path as utils_get_ffmpeg_path


class VideoShowLayout(QVBoxLayout):
    video_show_list_key = 'video.show.list'
    video_show_path_key = 'video.show.path'
    video_screenshot_path_key = 'video.screenshot.path'
    video_cut_path_key = 'video.cut.path'
    ffmpeg_path_key = "video.ffmpeg.path"
    play_mode_one = 0
    play_mode_list = 1
    play_mode_list_end = 2  # 列表已全部播放完，按钮显示"重播列表"

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

        # 播放位置记忆
        self._position_save_count = 0  # 每 5 秒保存一次
        self.db_client = Sqlite3Client()
        self._init_position_table()

        self.get_ffmpeg_path()

        self.titleQLabel = QLabel("Title")
        self.titleQLabel.setText("Title")
        self.titleQLabel.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.titleQLabel.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        self.titleQLabel.setVisible(False)  # 路径已移至窗口标题栏显示
        self.addWidget(self.titleQLabel)

        # ---- 使用统一的 MediaDisplayWidget 替代 QMediaPlayer + QVideoWidget ----
        self.media_widget = MediaDisplayWidget(self.main_window.mainQWidget)
        self.media_widget.mediaFinished.connect(self._on_media_finished)
        self.media_widget.positionChanged.connect(self._on_position_changed)
        self.media_widget.errorOccurred.connect(self._on_media_error)

        self.qscrollarea = QScrollArea()

        # PyQt6: QDesktopWidget removed, use QApplication.primaryScreen() instead
        screen = QApplication.primaryScreen()
        screen_width = screen.size().width() if screen else 1920
        screen_height = screen.size().height() if screen else 1080
        self.screen_width = int(screen_width * main_window.left / (main_window.left + main_window.right))
        self.screen_height = int(screen_height * main_window.left / (main_window.left + main_window.right))
        self.qscrollarea.setGeometry(QRect(0, 0, self.screen_width, self.screen_height))

        self.qscrollarea.setWidgetResizable(True)
        self.qscrollarea.setWidget(self.media_widget)

        self.bar_hbox = QHBoxLayout()
        self.bar_hbox.setObjectName("bar_hbox")

        self.bar_slider = CustomSlider(Qt.Orientation.Horizontal)
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

        # 不再需要定时器轮询位置，MediaDisplayWidget 的 positionChanged 信号已处理
        self._position_save_count = 0

        # 监听窗口大小变化：视频 QScrollArea 自适应
        self.main_window.installEventFilter(self)

        # 如果引擎不支持直接截图，禁用截图按钮
        self._check_screenshot_support()

    def _check_screenshot_support(self):
        """检查当前引擎是否支持截图"""
        engine_info = self.media_widget.getEngineInfo()
        if engine_info == "Qt":
            logger.warning("Qt 兜底引擎不支持直接截图，截图按钮功能受限")
        else:
            logger.info(f"使用 {engine_info} 引擎，支持直接截图")

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
        if self.play_mode == VideoShowLayout.play_mode_list_end:
            # "重播列表"被点击：重置到列表开头重新播放
            self.play_list_index = 0
            self.play_mode = VideoShowLayout.play_mode_list
            self.list_btn.setText("播放列表")
            self.play_state = True
            self.stop_btn.setText('暂停')
            self.play(self.play_list[self.play_list_index])
            return
        if len(self.play_list) == 0 or len(self.play_list) == self.play_list_index:
            self.main_window.notice('列表未加载或已全部播放完毕')
            self.play_mode = VideoShowLayout.play_mode_one
            return
        self.play_state = True
        self.stop_btn.setText('暂停')
        self.play_mode = VideoShowLayout.play_mode_list
        if self.play_list_index >= len(self.play_list):
            self.play_mode = VideoShowLayout.play_mode_one
            self.play_state = False
            self.stop_btn.setText('播放')
        else:
            self.play(self.play_list[self.play_list_index])

    def up_time(self):
        num = self.media_widget.getPosition() + int(self.media_widget.getDuration() / 100)
        self.media_widget.setPosition(num)
        self._on_position_changed(self.media_widget.getPosition())

    def down_time(self):
        num = self.media_widget.getPosition() - int(self.media_widget.getDuration() / 80)
        self.media_widget.setPosition(num)
        self._on_position_changed(self.media_widget.getPosition())

    def pause(self):
        if self.play_state:
            self._save_position()  # 暂停时保存位置
            self.media_widget.pauseMedia()
            self.play_state = False
            self.stop_btn.setText("播放")
        else:
            self.media_widget.pauseMedia()
            self.play_state = True
            self.stop_btn.setText("暂停")

    def run_or_stop(self):
        if self.play_state:
            self._save_position()  # 停止时保存位置
            self.media_widget.pauseMedia()
            self.play_state = False
            self.stop_btn.setText("播放")
        else:
            if self.media_widget.getPosition() < self.media_widget.getDuration() or self.media_widget.getDuration() == 0:
                self.media_widget.pauseMedia()
                self.play_state = True
                self.stop_btn.setText("暂停")
            else:
                self.bar_slider.setValue(0)
                self.media_widget.setPosition(0)
                self.media_widget.pauseMedia()

    def play(self, filePath):
        self.titleQLabel.setText(filePath)
        self.path = filePath

        # 更新标题栏：显示文件名和播放进度
        self._update_title_bar(filePath)

        # 使用统一的 MediaDisplayWidget 播放
        self.media_widget.playMedia(filePath)
        self.play_state = True
        self.stop_btn.setText("暂停")

        # 从数据库加载上次播放位置，延迟等媒体加载完成后跳转
        saved_pos = self._load_position()
        if saved_pos > 0:
            QTimer.singleShot(500, lambda: self._seek_to_saved_position(saved_pos))

        # 播放开始后自动聚焦到视频区域（方便键盘快捷键操作）
        self.media_widget.setFocus()

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

    def _seek_to_saved_position(self, saved_pos):
        """跳转到保存的播放位置"""
        if saved_pos < self.media_widget.getDuration():
            self.media_widget.setPosition(saved_pos)
            self.main_window.notice(f"已恢复上次播放位置")

    def _on_media_finished(self):
        """媒体播放完成回调"""
        # 重新启用进度条更新（一个循环结束）
        self.play_state = False
        self.stop_btn.setText("播放")

        # 视频播放完成，删除数据库中的播放位置记录
        # 下次再播放该文件时从头开始看
        self._remove_position()

        if self.play_mode == VideoShowLayout.play_mode_list:
            self.play_list_index += 1
            if self.play_list_index >= len(self.play_list):
                # 列表已全部播放完毕，按钮改为"重播列表"
                self.play_mode = VideoShowLayout.play_mode_list_end
                self.list_btn.setText("重播列表")
            else:
                self.run_list()

    def _on_position_changed(self, pos_ms):
        """播放位置变化回调（由 MediaDisplayWidget positionChanged 信号触发）"""
        # 更新进度条
        duration = self.media_widget.getDuration()
        self.cut_bar_slider.duration = duration / 1000 if duration > 0 else 0

        if duration == 0:
            return

        value = round(pos_ms * self.bar_slider.maximum() / duration)
        # 必须在 setValue 之前设置 move_type，否则 valueChanged 信号触发时
        # slider_progress_moved 会看到旧的 move_type 并错误执行 seek
        self.bar_slider.move_type = 'time'
        self.bar_slider.setValue(value)

        m, s = divmod(pos_ms / 1000, 60)
        h, m = divmod(m, 60)
        text = "%02d:%02d:%02d" % (h, m, s)
        self.bar_label.setText('已播放:' + text)
        m, s = divmod(duration / 1000, 60)
        h, m = divmod(m, 60)
        text = "%02d:%02d:%02d" % (h, m, s)
        self.bar_label_all.setText('总时长:' + text)

        # 每 5 秒保存一次播放位置（约 5 次回调乘以 1000ms ≈ 5s）
        self._position_save_count += 1
        if self._position_save_count >= 5:
            self._position_save_count = 0
            self._save_position()

    def _on_media_error(self, error_msg: str):
        """媒体播放错误回调"""
        logger.error(f"视频播放错误: {error_msg}")
        self.main_window.notice(f"播放错误: {error_msg}")

    def slider_start(self, value):
        tangent = value / self.bar_slider_maxvalue * self.media_widget.getDuration()
        m, s = divmod(tangent / 1000, 60)
        h, m = divmod(m, 60)
        text = "%02d:%02d:%02d" % (h, m, s)
        self.cut_bar_edit_start.setText(text)
        self.cut_start = int(tangent / 1000)

    def slider_end(self, value):
        tangent = value / self.bar_slider_maxvalue * self.media_widget.getDuration()
        if tangent == 0:
            return
        m, s = divmod(tangent / 1000, 60)
        h, m = divmod(m, 60)
        text = "%02d:%02d:%02d" % (h, m, s)
        self.cut_bar_edit_end.setText(text)
        self.cut_end = int(tangent / 1000)

    def slider_progress_moved(self):
        if self.bar_slider.move_type != 'time':
            self.media_widget.setPosition(
                round(self.bar_slider.value() * self.media_widget.getDuration() / self.bar_slider.maximum())
            )

        m, s = divmod(self.media_widget.getPosition() / 1000, 60)
        h, m = divmod(m, 60)
        text = "%02d:%02d:%02d" % (h, m, s)
        self.bar_label.setText('已播放:' + text)

    def is_video(self, path):
        return is_video_file(path)

    def setVisible(self, visible):
        self.titleQLabel.setVisible(visible)
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

            save_path = new_path + '_' + str(self.media_widget.getPosition()) + '.jpg'

            # 尝试使用引擎直接截图（VLC/MPV 支持）
            if self.media_widget.screenshot(save_path):
                self.main_window.notice('截图成功，保存到 ' + save_path)
                self.main_window._refresh_model()
                return

            # 引擎截图失败，回退到 ffmpeg 截图
            ffmpeg_path = self.get_ffmpeg_path()
            if not os.path.exists(ffmpeg_path):
                self.main_window.notice('ffmpeg路径获取错误： ' + ffmpeg_path)
                return

            position_sec = self.media_widget.getPosition() / 1000
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
                self.main_window._refresh_model()
            else:
                self.main_window.notice("截图失败!!!")
        except subprocess.TimeoutExpired:
            self.main_window.notice("截图超时!!!")
        except Exception as e:
            logger.error(f"截图失败: {e}")
            self.main_window.notice(f"截图失败: {e}")

    def get_video_start(self):
        m, s = divmod(self.media_widget.getPosition() / 1000, 60)
        h, m = divmod(m, 60)
        text = "%02d:%02d:%02d" % (h, m, s)
        self.cut_bar_edit_start.setText(text)

    def get_video_end(self):
        m, s = divmod(self.media_widget.getPosition() / 1000, 60)
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
        m, s = divmod(self.media_widget.getDuration() / 1000, 60)
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

    def video_cut_thread_finished(self, file_name, retcode):
        if retcode != 0:
            self.main_window.notice('视频剪切失败，返回码: ' + str(retcode))
            return
        # 等待文件写入完成（最多等 60 秒）
        for _ in range(60):
            if os.path.exists(file_name):
                self.main_window._refresh_model()
                self.main_window.notice('视频剪切成功，保存到 ' + file_name)
                return
            time.sleep(1)
        self.main_window.notice('视频剪切超时，文件未生成')

    def loadData(self, path):
        if len(self.play_list) > 0:
            self.play_list.clear()
            self.play_list_index = 0

        files = filter(os.path.isfile, glob.glob(os.path.join(path, "*.mp4")))

        file_date_tuple_list = [(x, os.path.getmtime(x)) for x in files]
        file_date_tuple_list.sort(key=lambda x: x[1])

        for file in file_date_tuple_list:
            if self.is_video(file[0]):
                self.play_list.append(file[0])

        # 加载新列表时，重置按钮文本为"播放列表"
        self.play_mode = VideoShowLayout.play_mode_one
        self.list_btn.setText("播放列表")

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

            # 停止当前播放并清理
            self.media_widget.stopMedia()
            QTimer.singleShot(200, lambda: self._do_delete(path, filename, deleted_file_path))
        else:
            self.next()

    def _init_position_table(self):
        """创建播放位置记忆表（如果不存在）"""
        sql = """CREATE TABLE IF NOT EXISTS video_play_position (
            file_path TEXT PRIMARY KEY NOT NULL,
            position INTEGER NOT NULL,
            duration INTEGER NOT NULL,
            update_time TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        )"""
        self.db_client.exeUpdate(sql)

    def _save_position(self):
        """保存当前播放位置到数据库"""
        if not self.path or not os.path.exists(self.path):
            return
        position = self.media_widget.getPosition()
        duration = self.media_widget.getDuration()
        if position <= 30:  # 刚开始几秒不保存
            return
        # 使用 INSERT OR REPLACE 更新记录
        sql = f"""INSERT OR REPLACE INTO video_play_position (file_path, position, duration, update_time)
                  VALUES ('{self.path.replace("'", "''")}', {position}, {duration}, datetime('now','localtime'))"""
        try:
            self.db_client.exeUpdate(sql)
        except Exception as e:
            logger.warning(f"保存播放位置失败: {e}")

    def _remove_position(self):
        """从数据库删除当前文件的播放位置记录"""
        if not self.path:
            return
        escaped_path = self.path.replace("'", "''")
        sql = f"DELETE FROM video_play_position WHERE file_path = '{escaped_path}'"
        try:
            self.db_client.exeUpdate(sql)
        except Exception as e:
            logger.warning(f"删除播放位置失败: {e}")

    def _load_position(self):
        """从数据库加载播放位置，返回 position（毫秒），无记录则返回 0"""
        if not self.path:
            return 0
        escaped_path = self.path.replace("'", "''")
        sql = f"SELECT position FROM video_play_position WHERE file_path = '{escaped_path}'"
        try:
            cursor = self.db_client.exeQuery(sql)
            row = cursor.fetchone()
            if row:
                return row[0]
        except Exception as e:
            logger.warning(f"加载播放位置失败: {e}")
        return 0

    def eventFilter(self, obj, event):
        """监听窗口大小变化事件，自动缩放 MediaDisplayWidget"""
        if event.type() == QEvent.Type.Resize:
            # QScrollArea 的 setWidgetResizable(True) 会自动处理
            pass  # 交由 QScrollArea 自身处理自适应
        return super().eventFilter(obj, event)

    def _do_delete(self, path, filename, deleted_file_path):
        """实际执行文件删除并播放下一个（在媒体释放后调用）"""
        try:
            # 清理数据库中的播放位置记录
            escaped_path = deleted_file_path.replace("'", "''")
            self.db_client.exeUpdate(f"DELETE FROM video_play_position WHERE file_path = '{escaped_path}'")

            os.chdir(path)
            send2trash.send2trash(filename)
            self.main_window.notice(deleted_file_path + ' 文件已删除!!!')
            self.main_window._refresh_model()

            # 首先尝试从播放列表播放下一个
            if len(self.play_list) > 0 and 0 <= self.play_list_index < len(self.play_list):
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
                    self.play(next_file)
        except Exception as e:
            self.main_window.notice("文件删除异常!!!" + str(e))