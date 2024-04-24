from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtMultimediaWidgets import QVideoWidget
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *

from loguru import logger
from PIL import ImageGrab

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
        logger.info(f"屏幕大小为：{screen_width} x {screen_height}")
        self.screen_width = int(screen_width * 2 / 3)
        self.screen_height = int(screen_height * 2 / 3)
        logger.info(str(self.screen_width), str(self.screen_height))
        self.qscrollarea.setGeometry(QRect(0, 0, self.screen_width, self.screen_height))

        self.qscrollarea.setWidgetResizable(True)
        self.qscrollarea.setWidget(self.vw)
        self.addWidget(self.qscrollarea)

    def fcku(self, filePath):
        logger.info(filePath)
        self.main_window.dataManager.saveIndex(self.main_window.counter)
        self.titleQLabel.setText(filePath)

        # 选取视频文件，很多同学要求一打开就能播放，就是在这个地方填写默认的播放视频的路径
        self.player.setMedia(QMediaContent(QUrl.fromLocalFile(r'' + filePath)))
        self.player.play()

    def is_video(self, path):
        return path.lower().endswith(
            ('.mp4'))
