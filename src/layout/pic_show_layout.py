from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import (QPixmap, QImage)

from loguru import logger
from PIL import ImageGrab

from src.layout.input_and_exe_layout import InputAndExeLayout

logger.add("log/file_{time:YYYY-MM-DD}.log", rotation="500 MB", enqueue=True, format="{time} {level} {message}",
           filter="",
           level="INFO")


class PicShowLayout(QVBoxLayout):

    def __init__(self, main_window, *args, **kwargs):
        super(*args, **kwargs).__init__(*args, **kwargs)

        self.main_window = main_window
        self.counter = 0
        self.path = ''
        self.scale = (main_window.right * 4 + 3) / ((main_window.right + main_window.left) * 4)

        self.inputAndExeLayout = InputAndExeLayout(self)
        self.inputQWidget = QWidget()
        self.inputAndExeLayout.setContentsMargins(0, 0, 0, 0)
        self.inputQWidget.setLayout(self.inputAndExeLayout)
        self.addWidget(self.inputQWidget)

        self.inputAndExeLayout.btn.pressed.connect(self.start_process)
        self.inputAndExeLayout.fullScreenBtn.pressed.connect(main_window.full_screen_custom)
        self.inputAndExeLayout.startAndFullScreenBtn.pressed.connect(self.startProcessWithFullScreen)

        self.titleQLabel = QLabel("Title")
        self.titleQLabel.setText("Title")
        self.titleQLabel.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.titleQLabel.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.addWidget(self.titleQLabel)

        self.pictureQLabel = QLabel("Picture")
        self.pictureQLabel.setText("Picture")
        self.pictureQLabel.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)

        self.qscrollarea = QScrollArea()

        # screen = ImageGrab.grab()
        # self.screen_width, self.screen_height = screen.size
        self.screen_width = int(self.main_window.width() * self.scale)
        self.screen_height = int(self.main_window.height() * self.scale)
        # self.screen_height = self.main_window.height()
        # self.screen_width = self.main_window.width()
        self.qscrollarea.setGeometry(QRect(0, 0, self.screen_width, self.screen_height))

        self.qscrollarea.setWidgetResizable(True)
        self.qscrollarea.setWidget(self.pictureQLabel)
        self.addWidget(self.qscrollarea)

    def fcku(self, filePath):
        logger.info(filePath)
        self.path = filePath

        self.titleQLabel.setText(filePath)

        fckimage = QImage(filePath)

        self.screen_width = int(self.main_window.width() * self.scale)
        self.screen_height = int(self.main_window.height() * self.scale)
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

    def is_pic(self, path):
        return path.lower().endswith(
            ('.bmp', '.dib', '.png', '.jpg', '.jpeg', '.pbm', '.pgm', '.ppm', '.tif', '.tiff', '.webp'))

    def setVisible(self, visible):
        self.inputQWidget.setVisible(visible)
        self.titleQLabel.setVisible(visible)

    def refreshPictures(self):
        self.counter += 1
        self.refreshPicturesOnly()

    def refreshPicturesOnly(self):
        if len(self.inputAndExeLayout.list_files) == 0:
            return
        img_path = self.inputAndExeLayout.list_files[self.counter]
        self.fcku(img_path)

    def up(self):
        self.counter += 1
        self.refreshPicturesOnly()

    def down(self):
        self.counter -= 1
        self.refreshPicturesOnly()

    def start_process(self):
        self.inputAndExeLayout.timer.start()
        self.fcku(self.inputAndExeLayout.list_files[self.counter])

    def startProcessWithFullScreen(self):
        self.start_process()
        self.main_window.full_screen_custom()

    def pause(self):
        if self.inputAndExeLayout.timer.isActive():
            self.inputAndExeLayout.timer.stop()
        else:
            self.inputAndExeLayout.timer.start()
