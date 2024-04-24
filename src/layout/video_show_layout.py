from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtMultimediaWidgets import QVideoWidget
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *

from loguru import logger
from PIL import ImageGrab

from src.layout.click_jump_slider import ClickJumpSlider

logger.add("log/file_{time:YYYY-MM-DD}.log", rotation="500 MB", enqueue=True, format="{time} {level} {message}",
           filter="",
           level="INFO")


class VideoShowLayout(QVBoxLayout):

    def __init__(self, main_window, *args, **kwargs):
        super(*args, **kwargs).__init__(*args, **kwargs)

        self.main_window = main_window

        self.titleQLabel = QLabel("Title")
        self.titleQLabel.setText("Title")
        self.titleQLabel.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.titleQLabel.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.addWidget(self.titleQLabel)

        self.player = QMediaPlayer()
        # 定义视频显示的widget
        self.vw = QVideoWidget()
        self.vw.show()
        # 视频播放输出的widget，就是上面定义的
        self.player.setVideoOutput(self.vw)

        self.qscrollarea = QScrollArea()

        screen = ImageGrab.grab()
        screen_width, screen_height = screen.size
        # logger.info(f"屏幕大小为：{screen_width} x {screen_height}")
        self.screen_width = int(screen_width * 2 / 3)
        self.screen_height = int(screen_height * 2 / 3)
        # logger.info(str(self.screen_width), str(self.screen_height))
        self.qscrollarea.setGeometry(QRect(0, 0, self.screen_width, self.screen_height))

        self.qscrollarea.setWidgetResizable(True)
        self.qscrollarea.setWidget(self.vw)

        self.bar_hbox = QHBoxLayout()
        self.bar_hbox.setObjectName("bar_hbox")

        self.bar_slider = ClickJumpSlider(Qt.Horizontal)
        self.bar_slider.valueChanged.connect(self.slider_progress_moved)
        self.bar_slider.setObjectName("bar_slider")

        self.bar_label = QLabel(self.bar_slider)
        self.bar_label.setMaximumSize(QSize(50, 10))
        self.bar_label.setObjectName("bar_label")

        self.bar_hbox.addWidget(self.bar_slider)
        self.bar_hbox.addWidget(self.bar_label)
        self.stop_btn = QPushButton()
        self.stop_btn.setText("暂停")
        self.stop_btn.clicked.connect(self.run_or_stop)
        self.bar_hbox.addWidget(self.stop_btn)

        self.bar_hbox_qwidget = QWidget()
        self.bar_hbox_qwidget.setLayout(self.bar_hbox)
        self.addWidget(self.bar_hbox_qwidget)

        self.addWidget(self.qscrollarea)

        self.timer = QTimer()  # 定义定时器
        self.maxValue = 1000  # 设置进度条的最大值

        self.state = False

    def run_or_stop(self):
        if self.state:
            self.player.pause()
            self.timer.stop()
            self.state = False
            self.stop_btn.setText("播放")
        else:
            self.player.play()
            self.timer.start()
            self.state = True
            self.stop_btn.setText("暂停")

    def slider_progress_moved(self):
        self.timer.stop()
        self.player.setPosition(round(self.bar_slider.value() * self.player.duration() / 100))

    def fcku(self, filePath):
        logger.info(filePath)
        self.main_window.dataManager.saveIndex(self.main_window.counter)
        self.titleQLabel.setText(filePath)

        # 选取视频文件，很多同学要求一打开就能播放，就是在这个地方填写默认的播放视频的路径
        self.player.setMedia(QMediaContent(QUrl.fromLocalFile(r'' + filePath)))
        self.player.play()
        self.state = True

        self.timer.setInterval(1000)
        self.timer.start()
        self.timer.timeout.connect(self.onTimerOut)

    def onTimerOut(self):
        position = self.player.position()
        duration = self.player.duration()
        value = round(position * 100 / duration)
        self.bar_slider.setValue(value)

        m, s = divmod(self.player.position() / 1000, 60)
        h, m = divmod(m, 60)
        text = "%02d:%02d:%02d" % (h, m, s)
        self.bar_label.setText(text)
        # self.widget.doubleClickedItem.connect(self.videoDoubleClicked)

    def is_video(self, path):
        return path.lower().endswith(
            ('.mp4'))
