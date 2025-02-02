import shutil

import send2trash
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtWidgets import QApplication

import sys, os

from loguru import logger

from src.data_manager.config_manager import ConfigManager
from src.layout.pic_input_layout import PicInputLayout
from src.layout.pic_show_layout import PicShowLayout
from src.layout.video_show_layout import VideoShowLayout

import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

logger.add("log/file_{time:YYYY-MM-DD}.log", rotation="500 MB", enqueue=True, format="{time} {level} {message}",
           filter="",
           level="INFO")


class MainWindow(QMainWindow):
    expand_path_config_key = 'default.expand.path'
    show_type_video = 'video'
    show_type_pic = 'pic'
    normal = 0
    full = 1

    def __init__(self, *args, **kwargs):

        super(MainWindow, self).__init__(*args, **kwargs)

        self.path = ''
        self.path_right_click = ''
        self.left = 1
        self.right = 6
        self.config_manager = ConfigManager()
        self.style_sheet = self.styleSheet()
        self.full_screen_state = MainWindow.normal

        self.setWindowTitle('多媒体播放器')
        self.resize(1500, 700)

        self.mainQWidget = QSplitter(Qt.Horizontal)

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
        self.model.sort(3, order=Qt.SortOrder.DescendingOrder)
        self.treeView = QTreeView()
        self.treeView.setModel(self.model)
        self.treeView.setContextMenuPolicy(Qt.CustomContextMenu)
        self.treeView.customContextMenuRequested.connect(self.right_click_menu)
        self.treeView.setColumnHidden(1, True)
        self.treeView.setColumnHidden(2, True)
        self.treeView.setColumnHidden(3, True)
        # self.treeView.setRootIndex(self.model.index("")) #设置默认加载的目录
        self.treeView.clicked.connect(self.on_tree_clicked)
        self.treeView.selectionModel().selectionChanged.connect(self.on_selection_changed)
        self.mainQWidget.addWidget(self.treeView)

        self.work = QVBoxLayout()
        self.work.setContentsMargins(0, 0, 0, 0)
        self.work.addWidget(self.video_show_qwidget)
        self.video_show_qwidget.setVisible(False)
        self.work.addWidget(self.pic_show_qwidget)
        self.workQWidget = QWidget()
        self.workQWidget.setLayout(self.work)

        self.mainQWidget.addWidget(self.workQWidget)
        sizes = [10000 * self.left, 10000 * self.right]
        self.mainQWidget.setSizes(sizes)

        self.setCentralWidget(self.mainQWidget)

        self.statusbar = QStatusBar(self)
        self.setStatusBar(self.statusbar)
        self.statusbar.setObjectName("statusbar")
        self.statusbar.setStyleSheet('QStatusBar::item {border: none;}')
        self.statusLabel = QLabel()
        self.statusLabel.setText("状态栏")
        self.statusbar.addPermanentWidget(self.statusLabel, stretch=1)

        self.show()

        if self.config_manager.exist(MainWindow.expand_path_config_key):
            expand_path_config = self.config_manager.get(MainWindow.expand_path_config_key)
            self.expand_path(expand_path_config)

    def expand_path(self, path):
        self.treeView.setExpanded(self.model.index(path), True)
        while True:
            if path != os.path.dirname(path):
                path = os.path.dirname(path)
                self.treeView.setExpanded(self.model.index(path), True)
                # print("当前目录的父目录_方式一： " + path)
            else:
                break

    def right_click_menu(self, pos):
        try:
            f = self.treeView.currentIndex()
            gp = QModelIndex(f)
            self.path_right_click = self.model.filePath(gp)

            self.treeView.contextMenu = QMenu()

            self.treeView.contextMenu.action_copy = self.treeView.contextMenu.addAction(u'复制到')
            self.treeView.contextMenu.action_copy.triggered.connect(self.copy)

            self.treeView.contextMenu.action_move = self.treeView.contextMenu.addAction(u'移动')
            self.treeView.contextMenu.action_move.triggered.connect(self.move)

            self.treeView.contextMenu.action_refresh = self.treeView.contextMenu.addAction(u'刷新')
            self.treeView.contextMenu.action_refresh.triggered.connect(self.refresh)

            self.treeView.contextMenu.action_delete = self.treeView.contextMenu.addAction(u'删除')
            self.treeView.contextMenu.action_delete.triggered.connect(self.delete)

            self.treeView.contextMenu.load_for_slideshow = self.treeView.contextMenu.addAction(u'加载为幻灯片列表')
            self.treeView.contextMenu.load_for_slideshow.triggered.connect(self.load_for_pic_show)

            self.treeView.contextMenu.load_for_slideshow = self.treeView.contextMenu.addAction(u'加载为视频列表')
            self.treeView.contextMenu.load_for_slideshow.triggered.connect(self.load_for_video_lise)

            self.treeView.contextMenu.load_for_slideshow = self.treeView.contextMenu.addAction(u'设置为截图路径')
            self.treeView.contextMenu.load_for_slideshow.triggered.connect(self.load_for_video_screenshot)

            self.treeView.contextMenu.load_for_slideshow = self.treeView.contextMenu.addAction(u'设置为剪切路径')
            self.treeView.contextMenu.load_for_slideshow.triggered.connect(self.load_for_video_cut)

            self.treeView.contextMenu.load_for_slideshow = self.treeView.contextMenu.addAction(u'设置默认展开')
            self.treeView.contextMenu.load_for_slideshow.triggered.connect(self.set_expand_path)

            self.treeView.contextMenu.exec_(self.mapToGlobal(pos))
        except Exception as e:
            self.notice(e)

    def set_expand_path(self, path):
        if os.path.isdir(self.path_right_click):
            self.config_manager.add_or_update(MainWindow.expand_path_config_key,self.path_right_click)

    def copy(self):
        selected_path = QFileDialog.getExistingDirectory()  # 返回选中的文件夹路径
        if os.path.isdir(selected_path):
            (path, filename) = os.path.split(self.path_right_click)
            dst = os.path.join(selected_path, filename)
            logger.info('src:', self.path_right_click)
            logger.info('dst:', dst)
            shutil.copy(self.path_right_click, dst)
        self.model.refresh()

    def move(self):
        try:
            selected_path = QFileDialog.getExistingDirectory()  # 返回选中的文件夹路径
            if os.path.isdir(selected_path):
                (path, filename) = os.path.split(self.path_right_click)
                dst = os.path.join(selected_path, filename)
                shutil.move(self.path_right_click, dst)
            self.model.refresh()
        except Exception as e:
            self.notice("文件移动异常!!!" + str(e))

    def refresh(self):
        self.model.refresh()

    def load_for_video_screenshot(self):
        if os.path.isfile(self.path_right_click):
            return

        self.config_manager.add_or_update(VideoShowLayout.video_screenshot_path_key, self.path_right_click)

    def load_for_video_cut(self):
        if os.path.isfile(self.path_right_click):
            return

        self.config_manager.add_or_update(VideoShowLayout.video_cut_path_key, self.path_right_click)

    def load_for_video_lise(self):
        if os.path.isfile(self.path_right_click):
            return

        self.config_manager.add_or_update(VideoShowLayout.video_show_list_key, self.path_right_click)
        self.video_show_layout.loadData(self.path_right_click)
        self.change_show(MainWindow.show_type_video)

    def load_for_pic_show(self):
        if os.path.isfile(self.path_right_click):
            return

        self.config_manager.add_or_update(PicInputLayout.pic_show_list_key, self.path_right_click)
        self.change_show(MainWindow.show_type_pic)
        self.inputAndExeLayout.inputPath.setText(self.path_right_click)
        self.inputAndExeLayout.load_pic_list()

    def delete(self):
        try:
            (path, filename) = os.path.split(self.path_right_click)
            os.chdir(path)
            if os.path.isfile(self.path_right_click):
                send2trash.send2trash(filename)
            if os.path.isdir(self.path_right_click):
                send2trash.send2trash(filename)
            self.notice(self.path_right_click + ' 文件已删除!!!')
            self.model.refresh()
        except Exception as e:
            self.notice("文件删除异常!!!" + str(e))

    def on_selection_changed(self, selected, deselected):
        indexes = selected.indexes()
        for item in indexes:
            self.path = self.model.filePath(item)
            if self.pic_show_layout.is_pic(self.path):
                self.on_tree_clicked(item)

    def on_tree_clicked(self, qmodelindex):
        self.path = self.model.filePath(qmodelindex)

        if self.inputAndExeLayout.timer.isActive():
            self.inputAndExeLayout.timer.stop()

        if os.path.isdir(self.path):
            if not self.pic_show_qwidget.isVisible():
                self.change_show(MainWindow.show_type_pic)
            self.inputAndExeLayout.inputPath.setText(self.path)
            self.inputAndExeLayout.load_pic_list()
        elif os.path.isfile(self.path):
            if self.video_show_layout.is_video(self.path):
                self.change_show(MainWindow.show_type_video)
                self.video_show_layout.play_mode = self.video_show_layout.play_mode_one
                self.video_show_layout.play(self.model.filePath(qmodelindex))
            elif self.pic_show_layout.is_pic(self.path):
                self.change_show(MainWindow.show_type_pic)
                self.pic_show_layout.play(self.model.filePath(qmodelindex))
            else:
                self.video_show_layout.titleQLabel.setText('文件格式错误!!!')
                self.pic_show_layout.titleQLabel.setText('文件格式错误!!!')
                self.notice('文件格式错误!!!')
        else:
            self.notice("非法文件路径: " + self.path)

    def change_screen_full(self):
        if self.full_screen_state % 2 == MainWindow.full:
            self.full_screen_custom()
        else:
            self.screen_normal()

    def screen_normal(self):
        if self.video_show_qwidget.isVisible():
            self.video_show_layout.setVisible(True)
        if self.pic_show_qwidget.isVisible():
            self.pic_show_layout.setVisible(True)
        self.treeView.setVisible(True)
        self.statusbar.setVisible(True)
        self.mainQWidget.setStyleSheet(self.style_sheet)
        self.showNormal()

    def keyPressEvent(self, event):
        if (event.key() == Qt.Key_Escape):
            self.screen_normal()
        if (event.key() == Qt.Key_Left):
            if self.video_show_qwidget.isVisible():
                self.video_show_layout.down_time()
            if self.pic_show_qwidget.isVisible():
                self.pic_show_layout.down()
        if (event.key() == Qt.Key_Right):
            if self.pic_show_qwidget.isVisible():
                self.pic_show_layout.up()
            if self.video_show_qwidget.isVisible():
                self.video_show_layout.up_time()
        if (event.key() == Qt.Key_Space):
            if self.pic_show_qwidget.isVisible():
                self.pic_show_layout.pause()
            if self.video_show_qwidget.isVisible():
                self.video_show_layout.pause()
        if (event.key() == Qt.Key_W):
            if self.video_show_qwidget.isVisible():
                self.video_show_layout.previous()
        if (event.key() == Qt.Key_E):
            if self.video_show_qwidget.isVisible():
                self.video_show_layout.next()
        if (event.key() == Qt.Key_F):
            self.full_screen_state += 1
            self.change_screen_full()
        if (event.key() == Qt.Key_Delete):
            if self.pic_show_qwidget.isVisible():
                self.pic_show_layout.delete()
            if self.video_show_qwidget.isVisible():
                self.video_show_layout.delete()
        if (event.key() == Qt.Key_D):
            if self.pic_show_qwidget.isVisible():
                self.pic_show_layout.up()
            if self.video_show_qwidget.isVisible():
                self.video_show_layout.up_time()
        if (event.key() == Qt.Key_A):
            if self.video_show_qwidget.isVisible():
                self.video_show_layout.down_time()
            if self.pic_show_qwidget.isVisible():
                self.pic_show_layout.down()
        if (event.key() == Qt.Key_S):
            if self.video_show_qwidget.isVisible():
                self.video_show_layout.screenshot()
        if (event.key() == Qt.Key_O) and QApplication.keyboardModifiers() == Qt.ShiftModifier:
            self.notice("shift + o")

    def full_screen_custom(self):
        if self.video_show_qwidget.isVisible():
            self.video_show_layout.setVisible(False)
        if self.pic_show_qwidget.isVisible():
            self.pic_show_layout.setVisible(False)

        self.treeView.setVisible(False)
        self.statusbar.setVisible(False)
        self.mainQWidget.setStyleSheet("border:none;")
        self.showFullScreen()

    def change_show(self, show_type):
        if show_type == MainWindow.show_type_pic:
            self.pic_show_qwidget.setVisible(True)
            self.video_show_qwidget.setVisible(False)
        if show_type == MainWindow.show_type_video:
            self.video_show_qwidget.setVisible(True)
            self.pic_show_qwidget.setVisible(False)

    def notice(self, content):
        self.statusLabel.setText(content)


if __name__ == '__main__':
    app = QApplication(sys.argv)

    window = MainWindow()
    window.show()

    app.exec()
