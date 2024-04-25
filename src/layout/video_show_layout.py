import cv2
from PyQt5.QtGui import QPixmap, qRgb
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtMultimediaWidgets import QVideoWidget
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *

from loguru import logger
from PIL import ImageGrab
from moviepy.editor import *

from src.layout.click_jump_slider import ClickJumpSlider

logger.add("log/file_{time:YYYY-MM-DD}.log", rotation="500 MB", enqueue=True, format="{time} {level} {message}",
           filter="",
           level="INFO")


class VideoShowLayout(QVBoxLayout):

    def __init__(self, main_window, *args, **kwargs):
        super(*args, **kwargs).__init__(*args, **kwargs)

        self.main_window = main_window
        self.path = ''
        self.cut_state = 0
        self.cut_start = 0.0
        self.cut_end = 0.0
        self.bar_slider_maxvalue = 1000
        self.state = False
        self.pause_count = 0

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

        self.bar_slider = ClickJumpSlider(Qt.Horizontal)
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

        self.stop_btn = QPushButton()
        self.stop_btn.setText("暂停")
        self.stop_btn.clicked.connect(self.run_or_stop)
        self.bar_hbox.addWidget(self.stop_btn)

        self.up_btn = QPushButton()
        self.up_btn.setText("快进")
        self.up_btn.clicked.connect(self.up_time)
        self.bar_hbox.addWidget(self.up_btn)
        self.down_btn = QPushButton()
        self.down_btn.setText("快退")
        self.down_btn.clicked.connect(self.down_time)
        self.bar_hbox.addWidget(self.down_btn)

        self.cut_bar_hbox = QHBoxLayout()
        self.cut_bar_hbox.setObjectName("cut_bar_hbox")

        self.cut_bar_slider = ClickJumpSlider(Qt.Horizontal)
        self.cut_bar_slider.valueChanged.connect(self.cut_slider_progress_clicked)
        self.cut_bar_slider.setObjectName("cut_bar_slider")
        self.cut_bar_slider.setMaximum(self.bar_slider_maxvalue)
        self.cut_bar_slider.setMinimum(0)

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

        self.cut_bar_hbox.addWidget(self.cut_bar_slider)
        self.cut_bar_hbox.addWidget(self.cut_bar_label_start)
        self.cut_bar_hbox.addWidget(self.cut_bar_edit_start)
        self.cut_bar_hbox.addWidget(self.cut_bar_label_end)
        self.cut_bar_hbox.addWidget(self.cut_bar_edit_end)

        self.cut_btn = QPushButton()
        self.cut_btn.setText("剪切")
        self.cut_btn.clicked.connect(self.video_cut)
        self.cut_bar_hbox.addWidget(self.cut_btn)

        self.screenshot_button = QPushButton('截图')
        self.screenshot_button.clicked.connect(self.take_screenshot)
        self.bar_hbox.addWidget(self.screenshot_button)

        self.fullScreenBtn = QPushButton("全屏")
        self.bar_hbox.addWidget(self.fullScreenBtn)
        self.fullScreenBtn.pressed.connect(main_window.full_screen_custom)

        self.bar_hbox_qwidget = QWidget()
        self.bar_hbox_qwidget.setLayout(self.bar_hbox)

        self.cut_bar_hbox_qwidget = QWidget()
        self.cut_bar_hbox_qwidget.setLayout(self.cut_bar_hbox)

        self.addWidget(self.qscrollarea)
        self.addWidget(self.bar_hbox_qwidget)
        self.addWidget(self.cut_bar_hbox_qwidget)

        self.timer = QTimer()  # 定义定时器
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.onTimerOut)

    def take_screenshot(self):

        try:
            vc = cv2.VideoCapture(self.path)
            vc.set(cv2.CAP_PROP_POS_MSEC, self.player.position())
            rval, frame = vc.read()
            if rval:
                save_path = self.path.replace('.mp4', "_" + str(self.player.position()) + ".jpg")
                logger.info("save_path: " + save_path)
                cv2.imencode('.jpg', frame)[1].tofile(save_path)
                qimg = self.CV2QImage(frame)

                mime_data = QMimeData()
                mime_data.setImageData(qimg)
                QApplication.clipboard().setMimeData(mime_data)

                self.main_window.model.refresh()
            else:
                logger.info("视频加载失败失败")
        except Exception as e:
            logger.info(f"获取视频封面图失败: {e}")

    def CV2QImage(self, cv_image):

        width = cv_image.shape[1]
        height = cv_image.shape[0]

        pixmap = QPixmap(width, height)
        qimg = pixmap.toImage()

        for row in range(0, height):
            for col in range(0, width):
                b = cv_image[row, col, 0]
                g = cv_image[row, col, 1]
                r = cv_image[row, col, 2]

                pix = qRgb(r, g, b)
                qimg.setPixel(col, row, pix)

        return qimg  # 转换完成，返回

    def delete(self):
        logger.info('delete')
        if os.path.exists(self.path):
            self.player.stop()
            os.remove(self.path)

    # 快进
    def up_time(self):
        num = self.player.position() + int(self.player.duration() / 100)
        self.player.setPosition(num)
        self.onTimerOut()

    # 快退
    def down_time(self):
        num = self.player.position() - int(self.player.duration() / 20)
        self.player.setPosition(num)
        self.onTimerOut()

    def pause(self):
        self.pause_count += 1
        if self.pause_count % 2 == 0:
            self.player.pause()
        else:
            self.player.play()

    def run_or_stop(self):
        if self.state:
            self.player.pause()
            self.timer.stop()
            self.state = False
            self.stop_btn.setText("播放")
        else:
            if self.player.position() < self.player.duration():
                self.player.play()
                self.timer.start()
                self.state = True
                self.stop_btn.setText("暂停")
            else:
                self.timer.start()
                self.bar_slider.setValue(0)
                self.player.setPosition(0)
                self.player.play()

    def slider_progress_moved(self):

        if self.bar_slider.move_type != 'time':
            self.player.setPosition(round(self.bar_slider.value() * self.player.duration() / self.bar_slider.maximum()))

        m, s = divmod(self.player.position() / 1000, 60)
        h, m = divmod(m, 60)
        text = "%02d:%02d:%02d" % (h, m, s)
        self.bar_label.setText('已播放:' + text)

    def cut_slider_progress_clicked(self):
        tangent = self.cut_bar_slider.value() / self.cut_bar_slider.maximum() * self.player.duration()
        m, s = divmod(tangent / 1000, 60)
        h, m = divmod(m, 60)
        text = "%02d:%02d:%02d" % (h, m, s)

        if self.cut_state % 2 == 0:
            self.cut_bar_edit_start.setText(text)
            self.cut_start = tangent
        else:
            self.cut_bar_edit_end.setText(text)
            self.cut_end = tangent

        self.cut_state += 1

    def fcku(self, filePath):
        logger.info(filePath)
        self.titleQLabel.setText(filePath)
        self.path = filePath

        self.player.setMedia(QMediaContent(QUrl.fromLocalFile(r'' + filePath)))
        self.player.play()
        self.state = True

        self.timer.start()

    def onTimerOut(self):

        position = self.player.position()
        duration = self.player.duration()

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
            self.stop_btn.setText("播放")
            self.state = False
            self.timer.stop()

    def is_video(self, path):
        return path.lower().endswith(
            ('.mp4'))

    def setVisible(self, visible):
        self.titleQLabel.setVisible(visible)

    def video_cut(self):

        file_name = (self.path.replace('.mp4', "_")
                     + str(int(self.cut_start * 1000)).replace('.', '') + '-'
                     + str(int(self.cut_end * 1000)).replace('.', '') + '.mp4')

        start_text = self.cut_bar_edit_start.text().split(':')
        start = int(start_text[0]) * 3600 + int(start_text[1]) * 60 + int(start_text[2])
        end_text = self.cut_bar_edit_end.text().split(':')
        end = int(end_text[0]) * 3600 + int(end_text[1]) * 60 + int(end_text[2])

        video = VideoFileClip(self.path)
        video = video.subclip(start, end)
        video.write_videofile(file_name)

        self.main_window.model.refresh()
