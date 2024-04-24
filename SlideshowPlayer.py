from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtWidgets import QApplication

import sys, os
from loguru import logger

from src.layout.input_and_exe_layout import InputAndExeLayout
from src.layout.show_layout import ShowLayout
from src.data_manager.DataManager import DataManager

logger.add("log/file_{time:YYYY-MM-DD}.log", rotation="500 MB", enqueue=True, format="{time} {level} {message}", filter="",
           level="INFO")

class MainWindow(QMainWindow):
    pause = False

    def __init__(self, *args, **kwargs):

        super(MainWindow, self).__init__(*args, **kwargs)

        self.setWindowTitle('Pictures')
        # self.resize(2560, 1440)
        self.counter = 0
        self.dataManager = DataManager()

        self.layout = QHBoxLayout()

        self.inputAndExeLayout = InputAndExeLayout(self)
        self.showLayout = ShowLayout(self)

        self.showQWidget = QWidget()
        self.showLayout.setContentsMargins(0, 0, 0, 0)
        self.showQWidget.setLayout(self.showLayout)

        self.inputQWidget = QWidget()
        self.inputAndExeLayout.setContentsMargins(0, 0, 0, 0)
        self.inputQWidget.setLayout(self.inputAndExeLayout)

        # Window系统提供的模式
        self.model = QDirModel()
        # 创建一个QtreeView部件
        self.treeView = QTreeView()
        # 为部件添加模式
        self.treeView.setModel(self.model)
        self.treeView.setWindowTitle("")
        # 绑定点击事件
        self.treeView.clicked.connect(self.onTreeClicked)
        # 将创建的窗口进行添加
        self.layout.addWidget(self.treeView, stretch=1)

        self.work = QVBoxLayout()
        self.work.addWidget(self.inputQWidget)
        self.work.addWidget(self.showQWidget)
        self.workQWidget = QWidget()
        self.workQWidget.setLayout(self.work)

        self.layout.addWidget(self.workQWidget, stretch=3)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.mainQWidget = QWidget()
        self.mainQWidget.setLayout(self.layout)
        self.setCentralWidget(self.mainQWidget)

        self.show()

    def onTreeClicked(self, qmodelindex):
        path = self.model.filePath(qmodelindex)
        if os.path.isdir(path):
            # logger.info("it's a directory: " + path)
            self.inputAndExeLayout.inputPath.setText(path)
            self.inputAndExeLayout.inputPathClicked()
        elif os.path.isfile(path):
            # logger.info("it's a normal file: " + path)
            self.showLayout.fcku(self.model.filePath(qmodelindex))
        else:
            logger.info("it's a special file(socket,FIFO,device file): " + path)

    # 检测键盘回车按键，函数名字不要改，这是重写键盘事件
    def keyPressEvent(self, event):
        # 这里event.key（）显示的是按键的编码
        logger.info("按下：" + str(event.key()))
        # 举例，这里Qt.Key_A注意虽然字母大写，但按键事件对大小写不敏感
        if (event.key() == Qt.Key_Escape):
            self.inputQWidget.setVisible(True)
            self.showLayout.titleQLabel.setVisible(True)
            self.treeView.setVisible(True)
            self.showNormal()
        if (event.key() == Qt.Key_A):
            self.counter -= 1
            self.refreshPicturesOnly()
        if (event.key() == Qt.Key_D):
            self.counter += 1
            self.refreshPicturesOnly()
        if (event.key() == Qt.Key_S):
            logger.info("add : " + self.inputAndExeLayout.list_files[self.counter])
            self.dataManager.saveCollect(self.inputAndExeLayout.list_files[self.counter], 2)
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
            if self.inputAndExeLayout.timer.isActive():
                self.inputAndExeLayout.timer.stop()
            else:
                self.inputAndExeLayout.timer.start()
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

    def refreshPictures(self):
        if len(self.inputAndExeLayout.list_files) == 0:
            return
        img_path = self.inputAndExeLayout.list_files[self.counter]
        # logger.info(self.showLayout.pictureQLabel.size())
        # logger.info(self.showLayout.sizeConstraint())
        self.showLayout.fcku(img_path)
        self.counter += 1

    def refreshPicturesOnly(self):
        if len(self.inputAndExeLayout.list_files) == 0:
            return
        img_path = self.inputAndExeLayout.list_files[self.counter]
        self.showLayout.fcku(img_path)

    def start_process(self):
        self.inputAndExeLayout.timer.start()
        self.showLayout.fcku(self.inputAndExeLayout.list_files[self.counter])
        self.inputAndExeLayout.btn.setText("开始")
        self.inputAndExeLayout.startAndFullScreenBtn.setText("开始并全屏")

    def fullScreenCustom(self):
        if self.counter == 0:
            self.start_process()
        self.inputQWidget.setVisible(False)
        self.showLayout.titleQLabel.setVisible(False)
        self.treeView.setVisible(False)
        self.showFullScreen()
        self.showLayout.pictureQLabel.showFullScreen()

    def startProcessWithFullScreen(self):
        self.start_process()
        self.inputQWidget.setVisible(False)
        self.showLayout.titleQLabel.setVisible(False)
        self.treeView.setVisible(False)
        self.showFullScreen()

if __name__ == '__main__':
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    app.exec()
