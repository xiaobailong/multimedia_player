from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
import os

from loguru import logger

from src.data_manager.config_manager import ConfigManager

logger.add("log/file_{time:YYYY-MM-DD}.log", rotation="500 MB", enqueue=True, format="{time} {level} {message}",
           filter="",
           level="INFO")


class PicInputLayout(QHBoxLayout):
    pic_show_list_key = 'pic.show.list'

    def __init__(self, pic_show_layout, *args, **kwargs):
        super(*args, **kwargs).__init__(*args, **kwargs)

        self.content_path = ''
        self.pic_show_layout = pic_show_layout
        self.list_files = list()
        self.config_manager = ConfigManager()

        self.inputPathTitle = QLabel()
        self.inputPathTitle.setText("文件路径:")
        self.inputPathTitle.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.addWidget(self.inputPathTitle)

        self.inputPath = QLineEdit()
        self.inputPath.setMaxLength(1000)
        self.inputPath.setPlaceholderText("输入文件路径")
        if self.config_manager.exist(PicInputLayout.pic_show_list_key):
            history_path = self.config_manager.get(PicInputLayout.pic_show_list_key)
            self.inputPath.setText(history_path)
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
        self.getPathBtn.pressed.connect(self.load_pic_list)
        self.inputInterval.textEdited.connect(self.input_interval_text_edited)

        self.timer = QTimer()
        self.timer.setInterval(5 * 1000)
        self.timer.timeout.connect(pic_show_layout.refreshPictures)

    def setVisible(self, visible):
        self.setVisible(visible)

    def text_edited(self, s):
        logger.info(s)
        self.content_path = s
        self.loadData()

    def load_pic_list(self):
        if len(self.inputPath.text()) == 0:
            selected_path = QFileDialog.getExistingDirectory()  # 返回选中的文件夹路径
            self.inputPath.setText(selected_path)

        self.content_path = self.inputPath.text()
        self.config_manager.add_or_update(PicInputLayout.pic_show_list_key, self.content_path)
        self.loadData()
        logger.info(self.content_path)

    def input_interval_text_edited(self, s):
        if self.is_number(s):
            newTime = int(s) * 1000
            self.timer.setInterval(newTime)
        else:
            logger.info("请输入数字！！！")

    def loadData(self):
        if len(self.list_files) > 0:
            self.list_files.clear()
            self.pic_show_layout.counter = 0

        for root, dirs, files in os.walk(r"" + self.content_path):
            file_date_tuple_list = [(os.path.join(root,x),os.path.getmtime(os.path.join(root,x))) for x in files]
            file_date_tuple_list.sort(key=lambda x: x[1])
            for img_path in file_date_tuple_list:
                if img_path[0].lower().endswith(
                        ('.bmp', '.dib', '.png', '.jpg', '.jpeg', '.pbm', '.pgm', '.ppm', '.tif', '.tiff', '.webp')):
                    self.list_files.append(img_path[0])

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
