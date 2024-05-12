import os
import time

import cv2
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtMultimediaWidgets import QVideoWidget
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *

from loguru import logger
from PIL import ImageGrab

from src.data_manager.config_manager import ConfigManager
from src.layout.video_cut_thread import VideoCutThread
from src.layout.custom_slider import CustomSlider
from src.layout.range_slider import QRangeSlider

logger.add("log/file_{time:YYYY-MM-DD}.log", rotation="500 MB", enqueue=True, format="{time} {level} {message}",
           filter="",
           level="INFO")


class VideoShowLayout(QVBoxLayout):
    video_show_list_key = 'video.show.list'
    video_show_path_key = 'video.show.path'
    video_screenshot_path_key = 'video.screenshot.path'
    video_cut_path_key = 'video.cut.path'
    ffmpeg_path_key = "video.ffmpeg.path"
    play_mode_one = 0
    play_mode_list = 1

    def __init__(self, main_window, *args, **kwargs):
        super(*args, **kwargs).__init__(*args, **kwargs)

        self.main_window = main_window
        self.path = ''
        self.cut_start = 0
        self.cut_end = 1000
        self.bar_slider_maxvalue = 1000
        self.play_state = False
        self.pause_count = 0
        self.config_manager = ConfigManager()
        self.play_list = []
        self.play_list_index = 0
        self.play_mode = VideoShowLayout.play_mode_one

        self.get_ffmpeg_path()

        self.titleQLabel = QLabel("Title")
        self.titleQLabel.setText("Title")
        self.titleQLabel.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.titleQLabel.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.addWidget(self.titleQLabel)

        self.player = QMediaPlayer()
        self.video_widget = QVideoWidget()
        self.video_widget.show()
        self.player.setVideoOutput(self.video_widget)

        self.qscrollarea = QScrollArea()

        screen = ImageGrab.grab()
        screen_width, screen_height = screen.size
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
        self.next_btn = QPushButton()
        self.next_btn.setText("下一个")
        self.next_btn.clicked.connect(self.next)
        self.controal_hbox.addWidget(self.next_btn)

        self.screenshot_button = QPushButton('截图')
        self.screenshot_button.clicked.connect(self.screenshot)
        self.controal_hbox.addWidget(self.screenshot_button)

        self.fullScreenBtn = QPushButton("全屏")
        self.controal_hbox.addWidget(self.fullScreenBtn)
        self.fullScreenBtn.pressed.connect(main_window.full_screen_custom)

        self.cut_bar_hbox = QHBoxLayout()
        self.cut_bar_hbox.setObjectName("cut_bar_hbox")

        self.cut_bar_label_start = QLabel()
        self.cut_bar_label_start.setText("开始:")
        self.cut_bar_edit_start = QLineEdit()
        self.cut_bar_edit_start.setMaximumSize(QSize(70, 30))
        self.cut_bar_edit_start.setObjectName("cut_bar_label_start")
        self.cut_bar_edit_start.setText("00:00:00")
        self.cut_bar_label_end = QLabel()
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
        self.addWidget(self.bar_hbox_qwidget)
        self.addWidget(self.controal_hbox_qwidget)
        self.addWidget(self.cut_bar_hbox_qwidget)

        self.timer = QTimer()  # 定义定时器
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.onTimerOut)

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
        num = self.player.position() + int(self.player.duration() / 100)
        self.player.setPosition(num)
        self.onTimerOut()

    # 快退
    def down_time(self):
        num = self.player.position() - int(self.player.duration() / 80)
        self.player.setPosition(num)
        self.onTimerOut()

    def pause(self):
        self.pause_count += 1
        if self.pause_count % 2 == 0:
            self.player.pause()
            self.play_state = False
            self.stop_btn.setText("播放")
        else:
            self.player.play()
            self.play_state = True
            self.stop_btn.setText("暂停")

    def run_or_stop(self):
        if self.play_state:
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

        self.player.setMedia(QMediaContent(QUrl.fromLocalFile(r'' + filePath)))
        self.player.play()
        self.play_state = True
        self.stop_btn.setText("暂停")

        self.timer.start()

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

        if self.player.position() == self.player.duration():
            if self.play_mode == VideoShowLayout.play_mode_list:
                self.play_list_index += 1
                self.run_list()
                return
            self.stop_btn.setText("播放")
            self.play_state = False
            self.timer.stop()

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
            vc = cv2.VideoCapture(self.path)
            vc.set(cv2.CAP_PROP_POS_MSEC, self.player.position())
            rval, frame = vc.read()

            if rval:
                (path, filename) = os.path.split(self.path)
                (file, ext) = os.path.splitext(filename)
                new_path = os.path.expanduser('~') + os.sep + 'Downloads' + os.sep + file + '_'
                if self.config_manager.exist(VideoShowLayout.video_screenshot_path_key):
                    new_path = self.config_manager.get(VideoShowLayout.video_screenshot_path_key) + os.sep + file + '_'

                save_path = new_path + '_' + str(self.player.position()) + '.jpg'
                cv2.imencode('.jpg', frame)[1].tofile(save_path)

                if os.path.exists(save_path):
                    self.main_window.notice('截图成功，保存到 ' + save_path)
                    self.main_window.model.refresh()
            else:
                self.main_window.notice("截图视频加载失败失败!!!")
        except Exception as e:
            logger.info(f"获取视频封面图失败: {e}")

    def video_cut(self):

        (path, filename) = os.path.split(self.path)
        (file, ext) = os.path.splitext(filename)
        new_path = os.path.expanduser('~') + os.sep + 'Downloads' + os.sep + file + '_'
        if self.config_manager.exist(VideoShowLayout.video_cut_path_key):
            new_path = self.config_manager.get(VideoShowLayout.video_cut_path_key) + os.sep + file + '_'

        file_name = new_path + self.cut_bar_edit_start.text().replace(':', '') + '-' + self.cut_bar_edit_end.text().replace(':', '') + ext
        ffmpeg_path = self.get_ffmpeg_path()
        if not os.path.exists(ffmpeg_path):
            self.main_window.notice('ffmpeg路径获取错误： ' + ffmpeg_path)
            return
        get_video_max_time = self.get_video_max_time()
        if self.cut_bar_edit_start.text() >= self.cut_bar_edit_end.text() or self.cut_bar_edit_end.text() > get_video_max_time:
            self.main_window.notice('时间设置错误： ' + self.cut_bar_edit_start.text() + '-' + self.cut_bar_edit_end.text())
            return
        command = os.getcwd() + '/libs/ffmpeg/ffmpeg.exe -ss ' + self.cut_bar_edit_start.text() + ' -to ' + self.cut_bar_edit_end.text() + ' -i "' + self.path + '" -vcodec copy -acodec copy "' + file_name + '"'
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

        ffmpeg_path = os.getcwd() + '/libs/ffmpeg/ffmpeg.exe'
        if os.path.exists(ffmpeg_path):
            if not self.config_manager.exist(self.ffmpeg_path_key):
                self.config_manager.add_or_update(self.ffmpeg_path_key, ffmpeg_path)
            return ffmpeg_path
        else:
            value = os.environ.get('Path')
            for item in value.split(";"):
                if '\\bin' in item or 'ffmpeg' in item:
                    ffmpeg_path = os.path.join(item, 'ffmpeg.exe')
                    if os.path.exists(ffmpeg_path):
                        if not self.config_manager.exist(self.ffmpeg_path_key):
                            self.config_manager.add_or_update(self.ffmpeg_path_key, ffmpeg_path)
                        return ffmpeg_path
                    else:
                        ffmpeg_path = os.getcwd() + '/libs/ffmpeg/ffmpeg.exe'

        return ffmpeg_path

    def video_cut_thread_finished(self, file_name):
        while not os.path.exists(file_name):
            time.sleep(1)
            if os.path.exists(file_name):
                self.main_window.notice('视频剪切成功，保存到 ' + file_name)
                self.main_window.model.refresh()
                return

    def loadData(self, path):
        if len(self.play_list) > 0:
            self.play_list.clear()
            self.play_list_index = 0

        for root, dirs, files in os.walk(r"" + path):
            for file in files:
                video_path = os.path.join(root, file)
                if self.is_video(video_path):
                    self.play_list.append(video_path)
