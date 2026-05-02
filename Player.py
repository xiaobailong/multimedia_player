import shutil
import sys
import os
import tempfile

import send2trash

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import QFontMetrics, QPainter, QPen, QColor
from PyQt5.QtMultimedia import QMediaContent
from PyQt5.QtWidgets import QApplication

from loguru import logger

from src.data_manager.config_manager import ConfigManager
from src.layout.pic_input_layout import PicInputLayout
from src.layout.pic_show_layout import PicShowLayout
from src.layout.video_show_layout import VideoShowLayout
from src.layout.custom_title_bar import CustomTitleBar
from src.utils import get_log_path

import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

log_dir = get_log_path()
logger.add(os.path.join(log_dir, "file_{time:YYYY-MM-DD}.log"), rotation="500 MB", format="{time} {level} {message}",
           filter="",
           level="INFO")
logger.info(f"日志目录: {log_dir}")


class FileDisplayDelegate(QStyledItemDelegate):
    """自定义委托：文件名只显示前20字符，sizeHint返回完整宽度触发滚动条，悬浮显示全名和文件大小"""

    def displayText(self, value, locale):
        text = value
        if len(text) > 40:
            text = text[:40] + "..."
        return text

    def sizeHint(self, option, index):
        if index.model() is None:
            return super().sizeHint(option, index)
        text = index.model().fileName(index)
        font_metrics = QFontMetrics(option.font)
        text_width = font_metrics.horizontalAdvance(text) + 40  # 完整文件名宽度 + 图标/边距余量
        return QSize(text_width, super().sizeHint(option, index).height())

    def helpEvent(self, event, view, option, index):
        if event.type() == QEvent.ToolTip and index.model() is not None:
            file_path = index.model().filePath(index)
            file_name = index.model().fileName(index)
            if os.path.isfile(file_path):
                size_bytes = os.path.getsize(file_path)
                size_str = self._format_size(size_bytes)
                QToolTip.showText(event.globalPos(), f"{file_name}\n大小: {size_str}")
            else:
                QToolTip.showText(event.globalPos(), file_name)
            return True
        return super().helpEvent(event, view, option, index)

    @staticmethod
    def _format_size(bytes_size):
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_size < 1024:
                return f"{bytes_size:.1f} {unit}"
            bytes_size /= 1024
        return f"{bytes_size:.1f} TB"


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

        # -- 无边框窗口设置 --
        self.setWindowFlags(Qt.FramelessWindowHint)

        self.setWindowTitle('多媒体播放器')
        self.resize(1500, 700)

        # ---- 全局暗色主题 ----
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #1e1e2e;
                color: #cdd6f4;
            }
            QLabel {
                background: transparent;
                color: #cdd6f4;
            }
            QPushButton {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 4px;
                padding: 4px 12px;
                min-height: 22px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #45475a;
                border-color: #585b70;
            }
            QPushButton:pressed {
                background-color: #585b70;
            }
            QLineEdit {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #89b4fa;
            }
            QScrollBar:horizontal {
                background-color: #181825;
                height: 10px;
                border: none;
                border-radius: 5px;
            }
            QScrollBar::handle:horizontal {
                background-color: #45475a;
                min-width: 30px;
                border-radius: 5px;
            }
            QScrollBar::handle:horizontal:hover {
                background-color: #585b70;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
            }
            QScrollBar:vertical {
                background-color: #181825;
                width: 10px;
                border: none;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background-color: #45475a;
                min-height: 30px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #585b70;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QTreeView {
                background-color: #1e1e2e;
                color: #cdd6f4;
                border: none;
                outline: none;
                font-size: 13px;
            }
            QTreeView::item {
                min-height: 26px;
                padding: 2px 4px;
            }
            QTreeView::item:selected {
                background-color: #45475a;
                color: #cdd6f4;
            }
            QTreeView::item:hover {
                background-color: #313244;
            }
            QTreeView::branch:has-children:closed {
                border-image: none;
            }
            QHeaderView::section {
                background-color: #181825;
                color: #a6adc8;
                border: none;
                border-bottom: 1px solid #313244;
                padding: 4px;
                font-size: 13px;
            }
            QSplitter::handle {
                background-color: #313244;
                width: 2px;
            }
            QStatusBar {
                background-color: #181825;
                color: #a6adc8;
                border-top: 1px solid #313244;
                font-size: 13px;
            }
            QStatusBar::item {
                border: none;
            }
            QScrollArea {
                border: none;
                background-color: #1e1e2e;
            }
            QVideoWidget {
                background-color: #000000;
            }
            QSlider::groove:horizontal {
                background-color: #313244;
                height: 6px;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background-color: #89b4fa;
                width: 14px;
                height: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background-color: #b4d0fb;
                width: 16px;
                height: 16px;
                margin: -6px 0;
                border-radius: 8px;
            }
            QSlider::sub-page:horizontal {
                background-color: #89b4fa;
                border-radius: 3px;
            }
        """)

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
        # 固定第一列宽度，禁用自动拉伸，使内容可溢出触发水平滚动条
        header = self.treeView.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setVisible(False)  # 隐藏 Name 表头
        self.treeView.setColumnWidth(0, 360)
        # 启用水平滚动条，始终显示
        self.treeView.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        # 水平滚动条默认在最左侧（Qt 原生行为），不做任何 setValue 干预
        # 自定义委托：文件名截断 + 悬浮显示
        self.treeView.setItemDelegate(FileDisplayDelegate(self.treeView))
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

        # -- 自定义标题栏 --
        self.title_bar = CustomTitleBar(self)
        self.title_bar.windowMinimized.connect(self.showMinimized)
        self.title_bar.windowMaximized.connect(self.showMaximized)
        self.title_bar.windowRestored.connect(self._on_restored)
        self.title_bar.windowClosed.connect(self.close)

        # -- 状态栏 --
        self.statusbar = QStatusBar(self)
        self.statusbar.setObjectName("statusbar")
        self.statusLabel = QLabel()
        self.statusLabel.setText("状态栏")
        self.statusbar.addPermanentWidget(self.statusLabel, stretch=1)

        self.toggle_tree_btn = QPushButton("◀ 隐藏列表")
        self.toggle_tree_btn.setFixedSize(90, 22)
        self.toggle_tree_btn.clicked.connect(self.toggle_tree)
        self.statusbar.addPermanentWidget(self.toggle_tree_btn)

        self.tree_visible = True
        # 记录展开时的窗口比例，用于恢复
        self.tree_sizes = [10000 * self.left, 10000 * self.right]

        # -- 主布局: 标题列 + mainQWidget + 状态栏 --
        self._central_widget = QWidget()
        self._central_widget.setObjectName("centralWidget")
        self._central_widget.setStyleSheet("""
            #centralWidget {
                background-color: #1e1e2e;
                border: 1px solid #45475a;
                border-radius: 8px;
            }
        """)
        central_layout = QVBoxLayout(self._central_widget)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.title_bar)
        central_layout.addWidget(self.mainQWidget, stretch=1)
        central_layout.addWidget(self.statusbar)

        self.setCentralWidget(self._central_widget)

        # 全屏模式下，安装全局事件过滤器确保 Esc 键始终能退出全屏
        QApplication.instance().installEventFilter(self)

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
                # 点击单个视频：退出列表播放模式
                self.video_show_layout.play_mode = self.video_show_layout.play_mode_one
                self.video_show_layout.play_list.clear()
                self.video_show_layout.play_list_index = 0
                self.change_show(MainWindow.show_type_video)
                self.video_show_layout.play(self.model.filePath(qmodelindex))
            elif self.pic_show_layout.is_pic(self.path):
                # 点击单个图片：退出幻灯片/列表模式
                self.pic_show_layout.counter = 0
                self.pic_show_layout.inputAndExeLayout.list_files.clear()
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
        # 先退出全屏模式（将控制控件从悬浮面板恢复到主布局）
        if hasattr(self, 'video_show_layout') and self.video_show_layout._is_fullscreen:
            self.video_show_layout.exit_fullscreen_mode()

        if self.video_show_qwidget.isVisible():
            self.video_show_layout.setVisible(True)
        if self.pic_show_qwidget.isVisible():
            self.pic_show_layout.setVisible(True)
        self.treeView.setVisible(True)
        self.statusbar.setVisible(True)
        # 恢复标题栏
        self.title_bar.setVisible(True)
        self._central_widget.setStyleSheet("""
            #centralWidget {
                background-color: #1e1e2e;
                border: 1px solid #45475a;
                border-radius: 8px;
            }
        """)
        self.mainQWidget.setStyleSheet(self.style_sheet)
        self.full_screen_state = MainWindow.normal

        # 如果全屏前是最大化状态，恢复最大化
        if getattr(self, '_was_maximized_before_fullscreen', False):
            self.showMaximized()
        elif hasattr(self, 'normal_rect'):
            x, y, w, h = self.normal_rect
            self.showNormal()
            # macOS 退出原生全屏有动画，动画完成后会重置窗口尺寸
            # 延迟 1 秒确保动画完全结束后再恢复原始大小和位置
            QTimer.singleShot(1000, lambda: self.setGeometry(x, y, w, h))
        else:
            self.showNormal()

    def keyPressEvent(self, event):
        if (event.key() == Qt.Key_Escape):
            self.full_screen_state = MainWindow.normal
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
        if (event.key() == Qt.Key_M) and self.full_screen_state != MainWindow.normal:
            # M 键在全屏时切换控制面板的显示/隐藏
            if hasattr(self, 'video_show_layout') and hasattr(self.video_show_layout, 'floating_panel'):
                panel = self.video_show_layout.floating_panel
                if panel.isVisible():
                    panel.hide_panel()
                else:
                    panel.resizeToFitContent()
                    panel.repositionDefault()
                    panel.show_panel()
        if (event.key() == Qt.Key_Delete):
            if self.pic_show_qwidget.isVisible():
                self.pic_show_layout.delete()
            if self.video_show_qwidget.isVisible():
                self.video_show_layout.delete()
        elif (event.key() == Qt.Key_D and QApplication.keyboardModifiers() == Qt.ControlModifier):
            if self.pic_show_qwidget.isVisible():
                self.pic_show_layout.delete()
            if self.video_show_qwidget.isVisible():
                self.video_show_layout.delete()
        elif (event.key() == Qt.Key_D):
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
        if (event.key() == Qt.Key_Z):
            self.video_show_layout.get_video_start()
        if (event.key() == Qt.Key_X):
            self.video_show_layout.get_video_end()
        if (event.key() == Qt.Key_C):
            self.video_show_layout.video_cut()
        if (event.key() == Qt.Key_B) and QApplication.keyboardModifiers() == Qt.ControlModifier:
            self.toggle_tree()
        if (event.key() == Qt.Key_O) and QApplication.keyboardModifiers() == Qt.ShiftModifier:
            self.notice("shift + o")

    def full_screen_custom(self):
        if self.video_show_qwidget.isVisible():
            self.video_show_layout.setVisible(False)
        if self.pic_show_qwidget.isVisible():
            self.pic_show_layout.setVisible(False)

        self.treeView.setVisible(False)
        self.statusbar.setVisible(False)
        # 隐藏标题栏
        self.title_bar.setVisible(False)
        self._central_widget.setStyleSheet("""
            #centralWidget {
                background-color: #1e1e2e;
                border: none;
                border-radius: 0px;
            }
        """)
        self.mainQWidget.setStyleSheet("border:none;")
        self.full_screen_state = MainWindow.full
        # 保存窗口状态用于退出全屏时恢复（支持正常/最大化/全屏等多种状态）
        self._saved_window_state = self.saveGeometry()
        # 如果当前是最大化状态，额外保存客户区几何参数用于 setGeometry 恢复
        if self.isMaximized():
            self._was_maximized_before_fullscreen = True
            # 先取消最大化获取正常几何参数
            self.showNormal()
            self.normal_rect = (self.x(), self.y(), self.width(), self.height())
            # 再回到最大化状态以便进入全屏
            self.showMaximized()
        else:
            self._was_maximized_before_fullscreen = False
            self.normal_rect = (self.x(), self.y(), self.width(), self.height())
        self.showFullScreen()

        # 视频全屏时使用悬浮控制面板
        if self.video_show_qwidget.isVisible():
            QTimer.singleShot(300, self.video_show_layout.enter_fullscreen_mode)

    def change_show(self, show_type):
        if show_type == MainWindow.show_type_pic:
            self.pic_show_qwidget.setVisible(True)
            self.video_show_qwidget.setVisible(False)
        if show_type == MainWindow.show_type_video:
            self.video_show_qwidget.setVisible(True)
            self.pic_show_qwidget.setVisible(False)

    def closeEvent(self, event):
        """关闭窗口时清理视频播放器资源，防止 macOS AVFoundation 崩溃"""
        # 停止定时器
        if hasattr(self, 'video_show_layout'):
            if self.video_show_layout.timer.isActive():
                self.video_show_layout.timer.stop()
            # 停止播放并释放媒体资源
            self.video_show_layout.player.stop()
            self.video_show_layout.player.setMedia(QMediaContent())
            # 断开视频输出，防止 CVDisplayLink 回调访问已释放对象
            self.video_show_layout.player.setVideoOutput(None)

        event.accept()

    def toggle_tree(self):
        if self.tree_visible:
            # 隐藏前保存当前比例
            self.tree_sizes = self.mainQWidget.sizes()
            self.treeView.setVisible(False)
            self.toggle_tree_btn.setText("▶ 展开列表")
            self.tree_visible = False
        else:
            self.treeView.setVisible(True)
            self.toggle_tree_btn.setText("◀ 隐藏列表")
            self.tree_visible = True
            # 恢复展开时的比例
            self.mainQWidget.setSizes(self.tree_sizes)

    def eventFilter(self, obj, event):
        """全局事件过滤器：全屏模式下始终能捕获 Esc 键退出全屏"""
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
            if self.full_screen_state == MainWindow.full:
                self.full_screen_state = MainWindow.normal
                self.screen_normal()
                return True
        return super().eventFilter(obj, event)

    def _on_restored(self):
        """从最大化还原后更新标题栏按钮图标"""
        self.title_bar.updateMaximizeIcon()

    def changeEvent(self, event):
        """窗口状态变化时更新标题栏按钮图标"""
        if event.type() == QEvent.WindowStateChange:
            self.title_bar.updateMaximizeIcon()
        super().changeEvent(event)

    def notice(self, content):
        self.statusLabel.setText(content)


if __name__ == '__main__':
    app = QApplication(sys.argv)

    # 单实例锁：使用 QLockFile 防止重复启动多个副本
    # QLockFile 基于文件锁，进程退出时 OS 自动释放，不会残留
    lock_file_path = os.path.join(tempfile.gettempdir(), "多媒体播放器.lock")
    lock_file = QLockFile(lock_file_path)
    if not lock_file.tryLock(100):
        logger.warning("已有实例在运行，退出当前进程")
        sys.exit(0)

    window = MainWindow()
    window.show()

    app.exec()
