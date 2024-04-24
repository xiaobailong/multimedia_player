from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import (QPixmap, QImage)

from loguru import logger
from PIL import ImageGrab

logger.add("log/file_{time:YYYY-MM-DD}.log", rotation="500 MB", enqueue=True, format="{time} {level} {message}", filter="",
           level="INFO")

class ShowLayout(QVBoxLayout):

    def __init__(self, main_window, *args, **kwargs):
        super(*args, **kwargs).__init__(*args, **kwargs)

        self.main_window = main_window

        self.titleQLabel = QLabel("Title")
        self.titleQLabel.setText("Title")
        self.titleQLabel.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.titleQLabel.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.addWidget(self.titleQLabel)

        self.pictureQLabel = QLabel("Picture")
        self.pictureQLabel.setText("Picture")
        self.pictureQLabel.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.qscrollarea = QScrollArea()
        screen = ImageGrab.grab()
        screen_width, screen_height = screen.size
        print(f"屏幕大小为：{screen_width} x {screen_height}")
        self.screen_width=int(screen_width * 3 / 4)
        self.screen_height=int(screen_height * 3 / 4)
        print(self.screen_width, self.screen_height)
        self.qscrollarea.setGeometry(QRect(0, 0, self.screen_width, self.screen_height))
        self.qscrollarea.setWidgetResizable(True)
        self.qscrollarea.setWidget(self.pictureQLabel)
        self.addWidget(self.qscrollarea)

    def fcku(self, filePath):
        logger.info(filePath)
        self.main_window.dataManager.saveIndex(self.main_window.counter)
        self.titleQLabel.setText(filePath)

        fckimage = QImage(filePath)

        pil_image = self.m_resize(self.screen_width, self.screen_height, fckimage)

        pixmap = QPixmap.fromImage(pil_image)

        self.pictureQLabel.resize(pil_image.width(), pil_image.height())
        self.pictureQLabel.setPixmap(pixmap)

    def m_resize(self, w_box, h_box, pil_image):  # 参数是：要适应的窗口宽、高、Image.open后的图片

        w, h = pil_image.width(), pil_image.height()  # 获取图像的原始大小

        f1 = 1.0 * w_box / w
        f2 = 1.0 * h_box / h

        factor = min([f1, f2])

        width = int(w * factor)
        height = int(h * factor)

        return pil_image.scaled(width, height)
