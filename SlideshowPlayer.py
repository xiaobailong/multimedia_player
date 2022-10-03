from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import (QPixmap, QImage)
from PyQt5.QtWidgets import QApplication

import sys, os
from loguru import logger
logger.add("log/file_{time}.log", rotation="500 MB", enqueue=True,format="{time} {level} {message}", filter="", level="INFO")

from src.data_manager.DataManager import DataManager

class MainWindow(QMainWindow):
    list_files = list()
    pause = False

    def __init__(self, *args, **kwargs):

        super(MainWindow, self).__init__(*args, **kwargs)

        self.setWindowTitle('Pictures')
        self.resize(2560, 1440)
        self.counter = 0
        self.dataManager = DataManager()

        layout = QVBoxLayout()

        self.inputAndExeLayout = QHBoxLayout()
        self.showLayout = QVBoxLayout()

        self.inputPathTitle = QLabel()
        self.inputPathTitle.setText("文件路径:")
        self.inputPathTitle.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.inputAndExeLayout.addWidget(self.inputPathTitle)
        self.inputPath = QLineEdit()
        self.inputPath.setMaxLength(1000)
        self.inputPath.setPlaceholderText("输入文件路径")
        self.inputPath.textEdited.connect(self.text_edited)
        self.inputAndExeLayout.addWidget(self.inputPath)
        self.getPathBtn = QPushButton("获取路径")
        self.getPathBtn.pressed.connect(self.inputPathClicked)
        self.inputAndExeLayout.addWidget(self.getPathBtn)

        self.inputIntervalPathTitle = QLabel()
        self.inputIntervalPathTitle.setText("图片刷新时间间隔:")
        self.inputIntervalPathTitle.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.inputAndExeLayout.addWidget(self.inputIntervalPathTitle)
        self.inputInterval = QLineEdit()
        self.inputInterval.setMaxLength(1000)
        self.inputInterval.setPlaceholderText("输入图片更新时间间隔，单位为秒，默认5秒")
        self.inputInterval.textEdited.connect(self.inputInterval_text_edited)
        self.inputAndExeLayout.addWidget(self.inputInterval)

        self.btn = QPushButton("开始")
        self.btn.pressed.connect(self.start_process)
        self.inputAndExeLayout.addWidget(self.btn)

        self.fullScreenBtn = QPushButton("全屏")
        self.fullScreenBtn.pressed.connect(self.fullScreenCustom)
        self.inputAndExeLayout.addWidget(self.fullScreenBtn)

        self.startAndFullScreenBtn = QPushButton("开始并全屏")
        self.startAndFullScreenBtn.pressed.connect(self.startProcessWithFullScreen)
        self.inputAndExeLayout.addWidget(self.startAndFullScreenBtn)

        self.titleQLabel = QLabel("Title")
        self.titleQLabel.setText("Title")
        self.titleQLabel.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.titleQLabel.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.showLayout.addWidget(self.titleQLabel)

        self.pictureQLabel = QLabel("Picture")
        self.pictureQLabel.setText("Picture")
        self.pictureQLabel.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.qscrollarea = QScrollArea()
        self.qscrollarea.setGeometry(QRect(50, 100, 600, 500))
        self.qscrollarea.setWidgetResizable(True)
        self.qscrollarea.setWidget(self.pictureQLabel)
        self.showLayout.addWidget(self.qscrollarea)

        self.showQWidget = QWidget()
        self.showLayout.setContentsMargins(0, 0, 0, 0)
        self.showQWidget.setLayout(self.showLayout)
        self.inputQWidget = QWidget()
        self.inputAndExeLayout.setContentsMargins(0, 0, 0, 0)
        self.inputQWidget.setLayout(self.inputAndExeLayout)

        layout.addWidget(self.inputQWidget)
        layout.addWidget(self.showQWidget)
        layout.setContentsMargins(0, 0, 0, 0)

        w = QWidget()
        w.setLayout(layout)
        self.setCentralWidget(w)

        self.show()

        self.timer = QTimer()
        self.timer.setInterval(5 * 1000)
        self.timer.timeout.connect(self.refreshPictures)

        # 检测键盘回车按键，函数名字不要改，这是重写键盘事件

    def keyPressEvent(self, event):
        # 这里event.key（）显示的是按键的编码
        logger.info("按下：" + str(event.key()))
        # 举例，这里Qt.Key_A注意虽然字母大写，但按键事件对大小写不敏感
        if (event.key() == Qt.Key_Escape):
            self.inputQWidget.setVisible(True)
            self.titleQLabel.setVisible(True)
            self.showNormal()
        if (event.key() == Qt.Key_A):
            self.counter -= 1
            self.refreshPicturesOnly()
        if (event.key() == Qt.Key_D):
            self.counter += 1
            self.refreshPicturesOnly()
        if (event.key() == Qt.Key_S):
            logger.info("add : "+self.list_files[self.counter])
            self.dataManager.saveCollect(self.list_files[self.counter], 2)
        if (event.key() == Qt.Key_1):
            logger.info('测试：1')
        if (event.key() == Qt.Key_Enter):
            logger.info('测试：Enter')
        if (event.key() == Qt.Key_Left):
            logger.info('测试：Key_Left')
        if (event.key() == Qt.Key_Right):
            self.counter += 1
            self.refreshPictures()
            logger.info('测试：Key_Right')
        if (event.key() == Qt.Key_Space):
            if self.timer.isActive():
                self.timer.stop()
            else:
                self.timer.start()
            logger.info("Key_Space")
        # 当需要组合键时，要很多种方式，这里举例为“shift+单个按键”，也可以采用shortcut、或者pressSequence的方法。
        if (event.key() == Qt.Key_A):
            if QApplication.keyboardModifiers() == Qt.ShiftModifier:
                self.counter -= 1
                self.refreshPicturesOnly()
            else:
                logger.info("A")
        if (event.key() == Qt.Key_D):
            if QApplication.keyboardModifiers() == Qt.ShiftModifier:
                self.counter += 1
                self.refreshPicturesOnly()
            else:
                logger.info("A")

        if (event.key() == Qt.Key_O) and QApplication.keyboardModifiers() == Qt.ShiftModifier:
            logger.info("shift + o")

    def inputPathClicked(self):
        self.content_path = QFileDialog.getExistingDirectory()  # 返回选中的文件夹路径
        self.inputPath.setText(self.content_path)
        self.loadData()
        logger.info(self.content_path)

    def inputInterval_text_edited(self, s):
        logger.info("inputInterval_text_edited: " + s)
        if self.is_number(s):
            newTime = int(s)
            self.timer.setInterval(newTime * 1000)
        else:
            logger.info("请输入数字！！！")

    def text_edited(self, s):
        logger.info(s)
        self.content_path = s
        self.loadData()

    def start_process(self):
        self.timer.start()
        self.fcku(self.list_files[self.counter])
        self.btn.setText("开始")
        self.startAndFullScreenBtn.setText("开始并全屏")

    def loadData(self):
        if len(self.list_files) > 0:
            self.list_files.clear()
            self.counter = 0
        for root, dirs, files in os.walk(r"" + self.content_path):
            for file in files:
                img_path = os.path.join(root, file)
                if img_path.lower().endswith(
                        ('.bmp', '.dib', '.png', '.jpg', '.jpeg', '.pbm', '.pgm', '.ppm', '.tif', '.tiff')):
                    self.list_files.append(img_path)
        self.dataManager.saveInputHistory(self.content_path, len(self.list_files))

    def startProcessWithFullScreen(self):
        self.start_process()
        self.inputQWidget.setVisible(False)
        self.titleQLabel.setVisible(False)
        self.showFullScreen()

    def fullScreenCustom(self):
        if self.counter == 0:
            self.start_process()
        self.inputQWidget.setVisible(False)
        self.titleQLabel.setVisible(False)
        self.showFullScreen()

    def refreshPictures(self):
        if len(self.list_files) == 0:
            return
        img_path = self.list_files[self.counter]
        self.fcku(img_path)
        self.counter += 1

    def refreshPicturesOnly(self):
        if len(self.list_files) == 0:
            return
        img_path = self.list_files[self.counter]
        self.fcku(img_path)

    def fcku(self, filePath):

        logger.info(filePath)
        self.dataManager.saveIndex(self.counter)
        self.titleQLabel.setText(filePath)

        fckimage = QImage(filePath)

        pil_image = self.m_resize(self.qscrollarea.width(), self.qscrollarea.height(), fckimage)

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

    def is_number(self, s):
        try:
            float(s)
            return True
        except ValueError:
            pass

        try:
            import unicodedata
            unicodedata.numeric(s)
            return True
        except (TypeError, ValueError):
            pass

        return False


if __name__ == '__main__':
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    app.exec()
