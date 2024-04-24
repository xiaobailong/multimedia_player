from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
import os

from loguru import logger

logger.add("log/file_{time:YYYY-MM-DD}.log", rotation="500 MB", enqueue=True, format="{time} {level} {message}",
           filter="",
           level="INFO")


class InputAndExeLayout(QHBoxLayout):
    list_files = list()

    def __init__(self, main_window, *args, **kwargs):
        super(*args, **kwargs).__init__(*args, **kwargs)

        self.main_window = main_window

        self.inputPathTitle = QLabel()
        self.inputPathTitle.setText("文件路径:")
        self.inputPathTitle.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.addWidget(self.inputPathTitle)

        self.inputPath = QLineEdit()
        self.inputPath.setMaxLength(1000)
        self.inputPath.setPlaceholderText("输入文件路径")
        self.addWidget(self.inputPath)

        self.getPathBtn = QPushButton("获取路径")
        self.addWidget(self.getPathBtn)

        self.inputIntervalPathTitle = QLabel()
        self.inputIntervalPathTitle.setText("图片刷新时间间隔:")
        self.inputIntervalPathTitle.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.addWidget(self.inputIntervalPathTitle)

        self.inputInterval = QLineEdit()
        self.inputInterval.setMaxLength(1000)
        self.inputInterval.setPlaceholderText("输入图片更新时间间隔，单位为秒，默认5秒")
        self.addWidget(self.inputInterval)

        self.btn = QPushButton("幻灯片")
        self.addWidget(self.btn)

        self.startAndFullScreenBtn = QPushButton("幻灯片并全屏")
        self.addWidget(self.startAndFullScreenBtn)

        self.fullScreenBtn = QPushButton("全屏")
        self.addWidget(self.fullScreenBtn)

        self.setContentsMargins(0, 0, 0, 0)

        self.inputPath.textEdited.connect(self.text_edited)
        self.getPathBtn.pressed.connect(self.inputPathClicked)
        self.inputInterval.textEdited.connect(self.inputInterval_text_edited)

        self.btn.pressed.connect(main_window.start_process)
        self.fullScreenBtn.pressed.connect(main_window.fullScreenCustom)
        self.startAndFullScreenBtn.pressed.connect(main_window.startProcessWithFullScreen)

        self.timer = QTimer()
        self.timer.setInterval(5 * 1000)
        self.timer.timeout.connect(main_window.refreshPictures)

    def setVisible(self, visible):
        self.setVisible(visible)

    def text_edited(self, s):
        logger.info(s)
        self.content_path = s
        self.loadData()

    def inputPathClicked(self):
        # logger.info(self.inputPath.text())
        if len(self.inputPath.text()) == 0:
            selected_path = QFileDialog.getExistingDirectory()  # 返回选中的文件夹路径
            self.inputPath.setText(selected_path)

        self.content_path = self.inputPath.text()
        self.loadData()
        logger.info(self.content_path)

    def inputInterval_text_edited(self, s):
        logger.info("inputInterval_text_edited: " + s)
        if self.is_number(s):
            newTime = int(s) * 1000
            self.timer.setInterval(newTime)
        else:
            logger.info("请输入数字！！！")

    def loadData(self):
        if len(self.list_files) > 0:
            self.list_files.clear()
            self.main_window.counter = 0
        for root, dirs, files in os.walk(r"" + self.content_path):
            for file in files:
                img_path = os.path.join(root, file)
                if img_path.lower().endswith(
                        ('.bmp', '.dib', '.png', '.jpg', '.jpeg', '.pbm', '.pgm', '.ppm', '.tif', '.tiff', '.webp')):
                    self.list_files.append(img_path)
        self.main_window.dataManager.saveInputHistory(self.content_path, len(self.list_files))

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
