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
        self.path_right_click = ''
        self.left = 1
        self.right = 3

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

        self.model = QDirModel()
        self.treeView = QTreeView()
        self.treeView.setModel(self.model)
        self.treeView.setContextMenuPolicy(Qt.CustomContextMenu)
        self.treeView.customContextMenuRequested.connect(self.right_click_menu)
        self.treeView.setColumnHidden(1, True)
        self.treeView.setColumnHidden(2, True)
        self.treeView.setColumnHidden(3, True)
        self.treeView.clicked.connect(self.onTreeClicked)
        self.layout.addWidget(self.treeView, stretch=self.left)

        self.work = QVBoxLayout()
        self.work.addWidget(self.video_show_qwidget)
        self.video_show_qwidget.setVisible(False)
        self.work.addWidget(self.pic_show_qwidget)
        self.workQWidget = QWidget()
        self.workQWidget.setLayout(self.work)

        self.layout.addWidget(self.workQWidget, stretch=self.right)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.mainQWidget = QWidget()
        self.mainQWidget.setLayout(self.layout)
        self.setCentralWidget(self.mainQWidget)

        # 定义状态栏
        self.statusbar = QStatusBar(self)
        # 将状态栏设置为当前窗口的状态栏
        self.setStatusBar(self.statusbar)
        # 设置状态栏的对象名称
        self.statusbar.setObjectName("statusbar")
        # 设置状态栏样式
        self.statusbar.setStyleSheet('QStatusBar::item {border: none;}')
        # 定义文本标签
        self.statusLabel = QLabel()
        # 设置文本标签显示内容
        self.statusLabel.setText("进度")
        # 定义水平进度条
        self.progressBar = QProgressBar()
        # 设置进度条的范围，参数1为最小值，参数2为最大值（可以调得更大，比如1000
        self.progressBar.setRange(0, 100)
        # 设置进度条的初始值
        self.progressBar.setValue(0)
        self.statusbar.addPermanentWidget(self.statusLabel, stretch=1)
        self.statusbar.addPermanentWidget(self.progressBar, stretch=4)
        self.statusbar.setVisible(False)

        self.show()

    def right_click_menu(self, pos):
        try:
            f = self.treeView.currentIndex()
            gp = QModelIndex(f)
            self.path_right_click = self.model.filePath(gp)

            self.treeView.contextMenu = QMenu()
            self.treeView.contextMenu.action_delete = self.treeView.contextMenu.addAction(u'删除')
            self.treeView.contextMenu.action_delete.triggered.connect(self.delete)
            self.treeView.contextMenu.load_for_slideshow = self.treeView.contextMenu.addAction(u'加载为幻灯片')
            self.treeView.contextMenu.load_for_slideshow.triggered.connect(self.load_for_slideshow)
            self.treeView.contextMenu.exec_(self.mapToGlobal(pos))
            self.treeView.contextMenu.show()
        except Exception as e:
            logger.error(e)

    def load_for_slideshow(self):
        if os.path.isfile(self.path_right_click):
            return

        if not self.pic_show_qwidget.isVisible():
            self.pic_show_qwidget.setVisible(True)
            self.video_show_qwidget.setVisible(False)
        self.inputAndExeLayout.inputPath.setText(self.path_right_click)
        self.inputAndExeLayout.inputPathClicked()

    def delete(self):
        try:
            os.remove(self.path_right_click)
            logger.info(self.path_right_click + ' 文件已删除!!!')
            self.model.refresh()
        except:
            logger.error("文件删除异常!!!")

    def onTreeClicked(self, qmodelindex):
        self.path = self.model.filePath(qmodelindex)

        if self.inputAndExeLayout.timer.isActive():
            self.inputAndExeLayout.timer.stop()

        if os.path.isdir(self.path):
            if not self.pic_show_qwidget.isVisible():
                self.pic_show_qwidget.setVisible(True)
                self.video_show_qwidget.setVisible(False)
            self.inputAndExeLayout.inputPath.setText(self.path)
            self.inputAndExeLayout.inputPathClicked()
        elif os.path.isfile(self.path):
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

    def keyPressEvent(self, event):
        if (event.key() == Qt.Key_Escape):
            if self.video_show_layout.is_video(self.path):
                self.video_show_layout.setVisible(True)
            else:
                self.pic_show_layout.setVisible(True)
            self.treeView.setVisible(True)
            self.showNormal()
        if (event.key() == Qt.Key_Left):
            # logger.info('测试：Key_Left')
            self.video_show_layout.down_time()
            self.pic_show_layout.down()
        if (event.key() == Qt.Key_Right):
            self.pic_show_layout.up()
            self.video_show_layout.up_time()
        if (event.key() == Qt.Key_Space):
            self.pic_show_layout.pause()
            self.video_show_layout.pause()
        if (event.key() == Qt.Key_D):
            self.pic_show_layout.up()
            self.video_show_layout.up_time()
        if (event.key() == Qt.Key_A):
            self.video_show_layout.down_time()
            self.pic_show_layout.down()
        if (event.key() == Qt.Key_S):
            self.video_show_layout.take_screenshot()
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
