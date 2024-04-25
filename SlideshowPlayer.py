from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtWidgets import QApplication

import sys, os
from loguru import logger

from src.layout.pic_show_layout import PicShowLayout
from src.layout.video_show_layout import VideoShowLayout
from src.data_manager.DataManager import DataManager

logger.add("log/file_{time:YYYY-MM-DD}.log", rotation="500 MB", enqueue=True, format="{time} {level} {message}",
           filter="",
           level="INFO")


class MainWindow(QMainWindow):
    pause = False

    def __init__(self, *args, **kwargs):

        super(MainWindow, self).__init__(*args, **kwargs)

        self.path = ''

        self.setWindowTitle('多媒体播放器')
        self.resize(1500, 700)
        self.dataManager = DataManager()

        self.layout = QHBoxLayout()

        self.video_show_layout = VideoShowLayout(self)
        self.pic_show_layout = PicShowLayout(self)
        self.inputAndExeLayout = self.pic_show_layout.inputAndExeLayout

        self.video_show_qwidget = QWidget()
        self.video_show_layout.setContentsMargins(0, 0, 0, 0)
        self.video_show_qwidget.setLayout(self.video_show_layout)

        self.pic_show_qwidget = QWidget()
        self.pic_show_layout.setContentsMargins(0, 0, 0, 0)
        self.pic_show_qwidget.setLayout(self.pic_show_layout)

        # Window系统提供的模式
        self.model = QDirModel()
        # 创建一个QtreeView部件
        self.treeView = QTreeView()
        # 为部件添加模式
        self.treeView.setModel(self.model)
        self.treeView.setWindowTitle("")
        self.treeView.setColumnHidden(1, True)
        self.treeView.setColumnHidden(2, True)
        self.treeView.setColumnHidden(3, True)
        # 绑定点击事件
        self.treeView.clicked.connect(self.onTreeClicked)
        # 将创建的窗口进行添加
        self.layout.addWidget(self.treeView, stretch=1)

        self.work = QVBoxLayout()
        self.work.addWidget(self.video_show_qwidget)
        self.video_show_qwidget.setVisible(False)
        self.work.addWidget(self.pic_show_qwidget)
        self.workQWidget = QWidget()
        self.workQWidget.setLayout(self.work)

        self.layout.addWidget(self.workQWidget, stretch=2)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.mainQWidget = QWidget()
        self.mainQWidget.setLayout(self.layout)
        self.setCentralWidget(self.mainQWidget)

        self.show()

    def onTreeClicked(self, qmodelindex):
        self.path = self.model.filePath(qmodelindex)

        if self.inputAndExeLayout.timer.isActive():
            self.inputAndExeLayout.timer.stop()

        if os.path.isdir(self.path):
            # logger.info("it's a directory: " + path)
            if not self.pic_show_qwidget.isVisible():
                self.pic_show_qwidget.setVisible(True)
                self.video_show_qwidget.setVisible(False)
            self.inputAndExeLayout.inputPath.setText(self.path)
            self.inputAndExeLayout.inputPathClicked()
        elif os.path.isfile(self.path):
            # logger.info("it's a normal file: " + path)
            self.change_show(self.path)
            if self.video_show_layout.is_video(self.path):
                self.video_show_layout.fcku(self.model.filePath(qmodelindex))
            elif self.pic_show_layout.is_pic(self.path):
                self.pic_show_layout.fcku(self.model.filePath(qmodelindex))
            else:
                self.video_show_layout.titleQLabel.setText('文件格式错误!!!')
                self.pic_show_layout.titleQLabel.setText('文件格式错误!!!')
                logger.error('文件格式错误!!!')
        else:
            logger.info("it's a special file(socket,FIFO,device file): " + self.path)

    # 检测键盘回车按键，函数名字不要改，这是重写键盘事件
    def keyPressEvent(self, event):
        # 这里event.key（）显示的是按键的编码
        # logger.info("按下：" + str(event.key()))
        # 举例，这里Qt.Key_A注意虽然字母大写，但按键事件对大小写不敏感
        if (event.key() == Qt.Key_Escape):
            if self.video_show_layout.is_video(self.path):
                self.video_show_layout.setVisible(True)
            else:
                self.pic_show_layout.setVisible(True)
            self.treeView.setVisible(True)
            self.showNormal()
        if (event.key() == Qt.Key_A):
            self.pic_show_layout.down()
        if (event.key() == Qt.Key_D):
            self.pic_show_layout.up()
        # if (event.key() == Qt.Key_S):
        # logger.info("add : " + self.inputAndExeLayout.list_files[self.pic_show_layout.counter])
        # self.dataManager.saveCollect(self.inputAndExeLayout.list_files[self.pic_show_layout.counter], 2)
        # if (event.key() == Qt.Key_1):
        #     logger.info('测试：1')
        # if (event.key() == Qt.Key_Enter):
        #     logger.info('测试：Enter')
        if (event.key() == Qt.Key_Left):
            # logger.info('测试：Key_Left')
            self.pic_show_layout.down()
        if (event.key() == Qt.Key_Right):
            self.pic_show_layout.up()
            # logger.info('测试：Key_Right')
        if (event.key() == Qt.Key_Space):
            self.pic_show_layout.pause()
            self.video_show_layout.run_or_stop()
            # logger.info("Key_Space")
        # 当需要组合键时，要很多种方式，这里举例为“shift+单个按键”，也可以采用shortcut、或者pressSequence的方法。
        if (event.key() == Qt.Key_A):
            if QApplication.keyboardModifiers() == Qt.ShiftModifier:
                self.pic_show_layout.down()
            else:
                logger.info("A")
        if (event.key() == Qt.Key_D):
            if QApplication.keyboardModifiers() == Qt.ShiftModifier:
                self.pic_show_layout.up()
            else:
                logger.info("A")

        if (event.key() == Qt.Key_O) and QApplication.keyboardModifiers() == Qt.ShiftModifier:
            logger.info("shift + o")

    def full_screen_custom(self):
        if self.video_show_layout.is_video(self.path):
            self.video_show_layout.setVisible(False)
        else:
            self.pic_show_layout.setVisible(False)
        self.treeView.setVisible(False)
        self.showFullScreen()

    def change_show(self, path):
        if self.video_show_layout.is_video(path):
            if not self.video_show_qwidget.isVisible():
                self.video_show_qwidget.setVisible(True)
                self.pic_show_qwidget.setVisible(False)
        elif self.pic_show_layout.is_pic(path):
            if not self.pic_show_qwidget.isVisible():
                self.pic_show_qwidget.setVisible(True)
                self.video_show_qwidget.setVisible(False)


if __name__ == '__main__':
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    app.exec()
