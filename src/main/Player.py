import shutil
import sys
import os
import tempfile

import send2trash

from PyQt6.QtWidgets import *
from PyQt6.QtGui import QFileSystemModel
from PyQt6.QtCore import *
from PyQt6.QtGui import QFontMetrics

from loguru import logger

from src.db.config_manager import ConfigManager
from src.layout.pic_show_layout import PicShowLayout
from src.layout.video_show_layout import VideoShowLayout
from src.core.custom_title_bar import CustomTitleBar
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
        if index.model() is None:
            return super().helpEvent(event, view, option, index)
        tooltip_text = index.model().filePath(index)
        file_size = index.model().size(index) / (1024 * 1024)
        tooltip_text += f"\n{'%0.2f MB' % file_size}"
        QToolTip.showText(event.globalPos(), tooltip_text)
        return True


class MainWindow(QMainWindow):
    full = 0
    normal = 1
    full_screen_state = full

    left = 0.15
    right = 0.85

    show_type_pic = 1
    show_type_video = 2

    expand_path_config_key = 'expand_path'
    version = "V3.1.2"

    def __init__(self):
        super().__init__()
        logger.info(f"================== {self.version} ==================")

        self.selected_paths = set()

        self.config_manager = ConfigManager()

        self.media_widget = None  # 引用，用于控件共享

        # 窗口高宽比
        self.setMinimumSize(800, 600)
        self.setWindowTitle("多媒体播放器")

        # -- 无边框窗口设置 --
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)

        # 允许拖拽文件
        self.setAcceptDrops(True)

        # 窗口位置
        desktop = QApplication.primaryScreen().availableGeometry()
        self.setGeometry(int(desktop.width() * 0.05), int(desktop.height() * 0.05),
                         int(desktop.width() * 0.9), int(desktop.height() * 0.85))

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

        self.mainQWidget = QSplitter(Qt.Orientation.Horizontal)

        self.video_show_layout = VideoShowLayout(self)
        self.pic_show_layout = PicShowLayout(self)
        self.inputAndExeLayout = self.pic_show_layout.inputAndExeLayout

        self.video_show_qwidget = QWidget()
        self.video_show_layout.setContentsMargins(0, 0, 0, 0)
        self.video_show_qwidget.setLayout(self.video_show_layout)

        self.pic_show_qwidget = QWidget()
        self.pic_show_layout.setContentsMargins(0, 0, 0, 0)
        self.pic_show_qwidget.setLayout(self.pic_show_layout)

        self.model = QFileSystemModel()
        self.model.setRootPath("")  # 设置根路径为当前驱动器根
        self.model.sort(3, order=Qt.SortOrder.AscendingOrder)
        self.treeView = QTreeView()
        self.treeView.setModel(self.model)
        self.treeView.setRootIndex(self.model.index(""))  # 显示驱动器根目录
        self.treeView.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.treeView.customContextMenuRequested.connect(self.right_click_menu)
        # Bug E 修复: 安装事件过滤器拦截右键鼠标按下事件，在 selectionChanged 之前设置标志位
        self.treeView.viewport().installEventFilter(self)
        self.treeView.setColumnHidden(1, True)
        self.treeView.setColumnHidden(2, True)
        self.treeView.setColumnHidden(3, True)
        # 固定第一列宽度，禁用自动拉伸，使内容可溢出触发水平滚动条
        header = self.treeView.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setVisible(False)  # 隐藏 Name 表头
        self.treeView.setColumnWidth(0, 360)
        # 启用水平滚动条，始终显示
        self.treeView.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
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
        sizes = [int(10000 * self.left), int(10000 * self.right)]
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
        self.tree_sizes = [int(10000 * self.left), int(10000 * self.right)]

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
        # Bug E 修复: 右键菜单弹出期间阻止 selectionChanged → on_tree_clicked 切换布局
        # 从而防止 VLC 窗口管理器 native 崩溃 (0xC0000409)
        self._right_click_in_progress = True

        try:
            # 使用 indexAt(pos) 获取右键点击位置的具体索引，而非 currentIndex()
            # currentIndex() 返回的是当前选中的项，而非用户右键点击的项
            idx = self.treeView.indexAt(pos)
            if not idx.isValid():
                # 点击的是空白区域，不显示菜单
                return

            self.path_right_click = self.model.filePath(idx)

            # 清理上一次右键菜单（防止内存泄漏）
            old_menu = getattr(self.treeView, '_context_menu_obj', None)
            if old_menu is not None:
                old_menu.deleteLater()
                self.treeView._context_menu_obj = None

            # 创建新菜单
            menu = QMenu(self.treeView)
            self.treeView._context_menu_obj = menu

            # 注意：每个 action 用唯一的属性名存储，防止覆盖
            action_copy = menu.addAction(u'复制到')
            action_copy.triggered.connect(self.copy)

            action_move = menu.addAction(u'移动')
            action_move.triggered.connect(self.move)

            action_refresh = menu.addAction(u'刷新')
            action_refresh.triggered.connect(self.refresh)

            menu.addSeparator()

            action_delete = menu.addAction(u'删除')
            action_delete.triggered.connect(self.delete)

            menu.addSeparator()

            action_pic = menu.addAction(u'加载为幻灯片列表')
            action_pic.triggered.connect(self.load_for_pic_show)

            action_video = menu.addAction(u'加载为视频列表')
            action_video.triggered.connect(self.load_for_video_lise)

            menu.addSeparator()

            action_screenshot = menu.addAction(u'设置为截图路径')
            action_screenshot.triggered.connect(self.load_for_video_screenshot)

            action_cut = menu.addAction(u'设置为剪切路径')
            action_cut.triggered.connect(self.load_for_video_cut)

            action_expand = menu.addAction(u'设置默认展开')
            action_expand.triggered.connect(self.set_expand_path)

            # 使用 QMenu.exec() (PyQt6 官方接口) 而非废弃的 exec_()
            menu.exec(self.treeView.viewport().mapToGlobal(pos))
        except Exception as e:
            logger.exception(f"右键菜单异常: {e}")
            self.notice(f"右键菜单异常: {e}")
        finally:
            self._right_click_in_progress = False

    def set_expand_path(self, path):
        if os.path.isdir(self.path_right_click):
            self.config_manager.add_or_update(MainWindow.expand_path_config_key,self.path_right_click)

    def _refresh_model(self):
        """刷新文件系统模型（QFileSystemModel 没有 refresh() 方法）"""
        root = self.model.rootPath()
        self.model.setRootPath("")
        self.model.setRootPath(root)

    def copy(self):
        selected_path = QFileDialog.getExistingDirectory()  # 返回选中的文件夹路径
        if os.path.isdir(selected_path):
            (path, filename) = os.path.split(self.path_right_click)
            dst = os.path.join(selected_path, filename)
            logger.info('src:', self.path_right_click)
            logger.info('dst:', dst)
            shutil.copy(self.path_right_click, dst)
        self._refresh_model()

    def move(self):
        try:
            selected_path = QFileDialog.getExistingDirectory()  # 返回选中的文件夹路径
            if os.path.isdir(selected_path):
                (path, filename) = os.path.split(self.path_right_click)
                dst = os.path.join(selected_path, filename)
                shutil.move(self.path_right_click, dst)
            self._refresh_model()
        except Exception as e:
            self.notice("文件移动异常!!!" + str(e))

    def refresh(self):
        self._refresh_model()

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

        self.change_show(MainWindow.show_type_pic)
        self.inputAndExeLayout.load_pic_list(self.path_right_click)

    def delete(self):
        try:
            (path, filename) = os.path.split(self.path_right_click)
            os.chdir(path)
            if os.path.isfile(self.path_right_click):
                send2trash.send2trash(filename)
            if os.path.isdir(self.path_right_click):
                send2trash.send2trash(filename)
            self.notice(self.path_right_click + ' 文件已删除!!!')
            self._refresh_model()
        except Exception as e:
            self.notice("文件删除异常!!!" + str(e))

    def on_selection_changed(self, selected, deselected):
        # Bug E 修复: 右键菜单崩溃 0xC0000409 根因。
        # Qt 事件顺序: MouseButtonPress → selectionChanged → customContextMenuRequested
        # 事件过滤器在 MouseButtonPress 时设置 _right_click_in_progress = True
        # selectionChanged 应检查该标志立即返回，不触发 on_tree_clicked（否则 VLC 引擎正在
        # 初始化/轮询时又一个 on_tree_clicked 会停止/重启引擎，导致 native 崩溃）。
        if getattr(self, '_right_click_in_progress', False):
            return

        indexes = selected.indexes()
        for item in indexes:
            self.path = self.model.filePath(item)
            if self.pic_show_layout.is_pic(self.path):
                self.on_tree_clicked(item)

    def on_tree_clicked(self, qmodelindex):
        # 防止 clicked 和 selectionChanged 信号在 300ms 内重复调用导致的双重播放崩溃
        # clicked 和 selectionChanged 都会触发此函数，且 selectionChanged 在 clicked 之后
        # 顺序执行（非递归）。双重调用会导致 GIF 解码线程和定时器在 stop/start 间产生
        # 竞态条件，引发 native 崩溃 (0xC0000409)。
        now = QDateTime.currentMSecsSinceEpoch()
        if now - getattr(self, '_last_tree_click_time', 0) < 300:
            return
        self._last_tree_click_time = now

        self.path = self.model.filePath(qmodelindex)

        if self.inputAndExeLayout.timer.isActive():
            self.inputAndExeLayout.timer.stop()

        if os.path.isdir(self.path):
            if not self.pic_show_qwidget.isVisible():
                self.change_show(MainWindow.show_type_pic)
            # 停止当前图片/GIF 播放，防止后台线程访问过期控件
            if hasattr(self, 'pic_show_layout') and hasattr(self.pic_show_layout, 'media_widget'):
                self.pic_show_layout.media_widget.stopMedia()
            self.inputAndExeLayout.load_pic_list(self.path)
        elif os.path.isfile(self.path):
            if self.video_show_layout.is_video(self.path):
                # 点击单个视频：退出列表播放模式
                # 如果单循环按钮已勾选，保留循环模式而非重置为 play_mode_one
                if not self.video_show_layout.loop_btn.isChecked():
                    self.video_show_layout.play_mode = self.video_show_layout.play_mode_one
                else:
                    self.video_show_layout.play_mode = self.video_show_layout.play_mode_one_loop
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

        # 使用保存的状态恢复显示，而不是查询 isVisible()
        # full_screen_custom() 中视频布局未被隐藏，pic 布局已被隐藏
        if getattr(self, '_video_was_visible', False):
            # 视频布局从未被隐藏，但确保可见
            self.video_show_qwidget.setVisible(True)
        pic_was_visible = getattr(self, '_pic_was_visible', False)
        if pic_was_visible:
            # 恢复控制面板（输入栏、标题）的可见性
            self.pic_show_layout.inputQWidget.setVisible(True)
            self.pic_show_layout.titleQLabel.setVisible(True)
            # 不需要恢复定时器：全屏时我们没有停止定时器，定时器一直在运行
            # 但如果 slideshow_active 为 True 而定时器意外未运行，则重新启动
            pic_slideshow_active = getattr(self, '_pic_slideshow_active', False)
            if pic_slideshow_active:
                if (hasattr(self.pic_show_layout, 'inputAndExeLayout')
                        and self.pic_show_layout.inputAndExeLayout
                        and not self.pic_show_layout.inputAndExeLayout.timer.isActive()):
                    self.pic_show_layout.inputAndExeLayout.timer.start()
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
        self.mainQWidget.setStyleSheet("")
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
        if (event.key() == Qt.Key.Key_Escape):
            self.full_screen_state = MainWindow.normal
            self.screen_normal()
        if (event.key() == Qt.Key.Key_Left):
            if self.video_show_qwidget.isVisible():
                self.video_show_layout.down_time()
            if self.pic_show_qwidget.isVisible():
                self.pic_show_layout.down()
        if (event.key() == Qt.Key.Key_Right):
            if self.pic_show_qwidget.isVisible():
                self.pic_show_layout.up()
            if self.video_show_qwidget.isVisible():
                self.video_show_layout.up_time()
        if (event.key() == Qt.Key.Key_Space):
            if self.pic_show_qwidget.isVisible():
                self.pic_show_layout.pause()
            if self.video_show_qwidget.isVisible():
                self.video_show_layout.pause()
        if (event.key() == Qt.Key.Key_W):
            if self.video_show_qwidget.isVisible():
                self.video_show_layout.previous()
        if (event.key() == Qt.Key.Key_E):
            if self.video_show_qwidget.isVisible():
                self.video_show_layout.next()
        if (event.key() == Qt.Key.Key_F):
            self.full_screen_state += 1
            self.change_screen_full()
        if (event.key() == Qt.Key.Key_Delete):
            if self.pic_show_qwidget.isVisible():
                self.pic_show_layout.delete()
            if self.video_show_qwidget.isVisible():
                self.video_show_layout.delete()
        elif (event.key() == Qt.Key.Key_D and QApplication.keyboardModifiers() == Qt.KeyboardModifier.ControlModifier):
            if self.pic_show_qwidget.isVisible():
                self.pic_show_layout.delete()
            if self.video_show_qwidget.isVisible():
                self.video_show_layout.delete()
        elif (event.key() == Qt.Key.Key_D):
            if self.pic_show_qwidget.isVisible():
                self.pic_show_layout.up()
            if self.video_show_qwidget.isVisible():
                self.video_show_layout.up_time()
        if (event.key() == Qt.Key.Key_A):
            if self.video_show_qwidget.isVisible():
                self.video_show_layout.down_time()
            if self.pic_show_qwidget.isVisible():
                self.pic_show_layout.down()
        if (event.key() == Qt.Key.Key_S):
            if self.video_show_qwidget.isVisible():
                self.video_show_layout.screenshot()
        if (event.key() == Qt.Key.Key_Z):
            self.video_show_layout.get_video_start()
        if (event.key() == Qt.Key.Key_X):
            self.video_show_layout.get_video_end()
        if (event.key() == Qt.Key.Key_C):
            self.video_show_layout.video_cut()
        if (event.key() == Qt.Key.Key_B) and QApplication.keyboardModifiers() == Qt.KeyboardModifier.ControlModifier:
            self.toggle_tree()
        if (event.key() == Qt.Key.Key_O) and QApplication.keyboardModifiers() == Qt.KeyboardModifier.ShiftModifier:
            self.notice("shift + o")

    def full_screen_custom(self):
        # 视频全屏：不要隐藏视频布局（VLC 仍在渲染），只隐藏非播放 UI 元素
        # 隐藏视频布局会销毁 VLC 输出 HWND，VLC 写入已销毁的 HWND 导致 native 崩溃 (0xC0000409)
        # 图片/GIF 全屏同理：不要停止播放也不要隐藏图片控件。
        # stop_playback() 会销毁 GIF 帧缓存/定时器/后台解码线程并清除 QPixmap → 黑屏
        # setVisible(False) 隐藏 widget → 无法渲染 → 黑屏
        # 只需隐藏控制面板（输入栏、标题），让 media_widget 持续渲染
        self._video_was_visible = self.video_show_qwidget.isVisible()
        self._pic_was_visible = self.pic_show_qwidget.isVisible()
        if self._pic_was_visible:
            # 保存幻灯片状态，以便退出全屏后恢复
            self._pic_slideshow_active = self.pic_show_layout._slideshow_active
            # Bug Fix: 全屏时不要停止幻灯片定时器。
            # 定时器驱动 refreshPictures() → play() → playMedia() 切换下一张图片。
            # 只要不隐藏 media_widget，playMedia 在切换图片时正常工作。
            # 只需要隐藏控制面板（输入栏、标题），保持 media_widget 持续渲染。
            self.pic_show_layout.inputQWidget.setVisible(False)
            self.pic_show_layout.titleQLabel.setVisible(False)

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

        # 视频全屏时使用悬浮控制面板（必须在 showFullScreen 之后调用）
        if self._video_was_visible:
            QTimer.singleShot(300, self.video_show_layout.enter_fullscreen_mode)

    def change_show(self, show_type):
        if show_type == MainWindow.show_type_pic:
            # Bug E 修复: 在隐藏视频控件前必须安全停止 VLC 引擎，
            # 否则 native 窗口被销毁时位置轮询定时器仍在运行 → 访问已销毁 HWND → 0xC0000409
            if self.video_show_qwidget.isVisible():
                self.video_show_layout.media_widget.stopMedia()
            self.pic_show_qwidget.setVisible(True)
            self.video_show_qwidget.setVisible(False)
        if show_type == MainWindow.show_type_video:
            # 切换到视频前停止图片/GIF 播放，避免后台 GIF 解码线程在隐藏后访问控件崩溃
            if self.pic_show_qwidget.isVisible():
                self.pic_show_layout.media_widget.stopMedia()
            self.video_show_qwidget.setVisible(True)
            self.pic_show_qwidget.setVisible(False)

    def closeEvent(self, event):
        """关闭窗口时清理媒体资源"""
        if hasattr(self, 'video_show_layout'):
            self.video_show_layout.media_widget.stopMedia()
        if hasattr(self, 'pic_show_layout'):
            self.pic_show_layout.media_widget.stopMedia()
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
        """全局事件过滤器：全屏模式下始终能捕获键盘快捷键，不受焦点控件影响"""
        # Bug E 修复: treeView.viewport() 鼠标右键按下时在 selectionChanged 之前设标志位
        # 注意: return False 让事件继续传播，不影响右键菜单弹出
        if obj is self.treeView.viewport() and event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.RightButton:
                self._right_click_in_progress = True
            return False
        if event.type() == QEvent.Type.KeyPress:
            # Esc：退出全屏
            if event.key() == Qt.Key.Key_Escape and self.full_screen_state == MainWindow.full:
                self.full_screen_state = MainWindow.normal
                self.screen_normal()
                return True
            # M：全屏时切换悬浮控制面板显示/隐藏
            if event.key() == Qt.Key.Key_M and self.full_screen_state != MainWindow.normal:
                if hasattr(self, 'video_show_layout') and hasattr(self.video_show_layout, 'floating_panel'):
                    panel = self.video_show_layout.floating_panel
                    if panel.isVisible():
                        panel.hide_panel()
                    else:
                        panel.resizeToFitContent()
                        panel.repositionDefault()
                        panel.show_panel()
                return True
        return super().eventFilter(obj, event)

    def _on_restored(self):
        """从最大化还原后更新标题栏按钮图标"""
        self.title_bar.updateMaximizeIcon()

    def changeEvent(self, event):
        """窗口状态变化时更新标题栏按钮图标"""
        if event.type() == QEvent.Type.WindowStateChange:
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