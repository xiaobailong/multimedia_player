import shutil
import sys
import os
import tempfile

import send2trash

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtCore import QTranslator, QLibraryInfo
from PyQt5.QtGui import QFontMetrics, QKeySequence, QPixmap, QPainter, QPen, QColor, QPolygon
from PyQt5.QtMultimedia import QMediaContent
from PyQt5.QtWidgets import QApplication

from loguru import logger

from src import ConfigManager
from src import PicInputLayout
from src import PicShowLayout
from src import VideoShowLayout
from src import CustomTitleBar
from src.private_mode.private_batch_thread import PrivateBatchThread
from src.private_mode.private_service import PrivateService
from src.utils.utils import get_log_path, get_app_data_path

import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

log_dir = get_log_path()
logger.add(os.path.join(log_dir, "file_{time:YYYY-MM-DD}.log"), rotation="500 MB", format="{time} {level} {message}",
           filter="",
           level="INFO")
logger.info(f"日志目录: {log_dir}")


class _StandardButtonTranslator(QTranslator):
    """标准对话框按钮的兜底中文映射。

    Windows 平台主题（QPlatformTheme）取「是/否/确定/取消」时不会命中
    qt_zh_CN.qm 里的 QDialogButtonBox 条目，实测按钮仍显示 &Yes / &No / OK / Cancel。
    这里补一层 translate() 覆盖，context 不匹配时返回空串，交给后面的 Qt 翻译。
    """

    _TEXTS = {
        '&Yes': '是(&Y)', 'Yes': '是(&Y)',
        '&No': '否(&N)', 'No': '否(&N)',
        'OK': '确定', '&OK': '确定(&O)',
        'Cancel': '取消', '&Cancel': '取消(&C)',
        '&Apply': '应用(&A)', 'Apply': '应用',
        'Close': '关闭', '&Close': '关闭',
        'Abort': '中止', 'Retry': '重试', 'Ignore': '忽略',
        '&Save': '保存(&S)', 'Save': '保存',
        '&Discard': '放弃(&D)', 'Discard': '放弃',
        'Open': '打开', '&Open': '打开',
        'Help': '帮助', 'Reset': '重置',
        'Restore Defaults': '恢复默认值',
    }

    def translate(self, context, source_text, disambiguation=None, n=-1):
        if context in ('QPlatformTheme', 'QDialogButtonBox'):
            return self._TEXTS.get(source_text, '')
        return ''


def _install_chinese_translator():
    """加载 Qt 自带的中文翻译（qt_zh_CN.qm）+ 标准按钮兜底。

    不做这一步时，QMessageBox（是 / 否 / 确定 / 取消）、QFileDialog 等
    Qt 标准对话框的按钮仍然是英文 —— 即使我们自己的文案全写成中文。
    """
    app = QApplication.instance()
    if app is None:
        return
    if getattr(app, '_zh_cn_translator', None) is not None:
        return
    translations_path = QLibraryInfo.location(QLibraryInfo.TranslationsPath)
    translator = QTranslator(app)
    if translator.load('qt_zh_CN', translations_path):
        app.installTranslator(translator)
        app._zh_cn_translator = translator
        logger.info(f"已加载 Qt 中文翻译: {translations_path}")
    else:
        logger.warning(f"未找到 qt_zh_CN.qm（{translations_path}），标准对话框按钮可能仍为英文")

    button_translator = _StandardButtonTranslator(app)
    app.installTranslator(button_translator)
    app._zh_cn_button_translator = button_translator


def _draw_tree_branch_icon(path, expanded, color='#a6adc8'):
    """画一个浅色 chevron（收起 → `>`，展开 → `v`），用于目录树 branch 指示器。"""
    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(QColor(color))
    pen.setWidth(2)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    if expanded:
        points = [QPoint(4, 6), QPoint(8, 10), QPoint(12, 6)]
    else:
        points = [QPoint(6, 4), QPoint(10, 8), QPoint(6, 12)]
    painter.drawPolyline(QPolygon(points))
    painter.end()
    pixmap.save(path)
    return path.replace('\\', '/')


def _ensure_tree_branch_icons():
    """生成（或复用）目录树展开 / 收起箭头图标，返回 (closed_url, open_url)。

    为什么不用 Qt 默认绘制：样式表里出现 `QTreeView::branch` 规则后，
    没有显式 image 的状态会由样式引擎用接近底色的颜色绘制，
    深色主题下"展开后的收起箭头"几乎与背景同色、看不见（见 ISSUE-008）。
    这里自绘两个浅色 chevron，closed / open 两种状态都显式指定 image。
    """
    icon_dir = os.path.join(get_app_data_path(), 'theme')
    os.makedirs(icon_dir, exist_ok=True)
    closed_path = os.path.join(icon_dir, 'tree_branch_closed.png')
    open_path = os.path.join(icon_dir, 'tree_branch_open.png')
    try:
        if not os.path.isfile(closed_path):
            _draw_tree_branch_icon(closed_path, expanded=False)
        if not os.path.isfile(open_path):
            _draw_tree_branch_icon(open_path, expanded=True)
    except Exception as e:
        logger.warning(f'生成目录树箭头图标失败: {e}')
    return closed_path.replace('\\', '/'), open_path.replace('\\', '/')


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
    private_library_path_key = 'private.library.path'
    show_type_video = 'video'
    show_type_pic = 'pic'
    normal = 0
    full = 1

    def __init__(self, *args, **kwargs):

        super(MainWindow, self).__init__(*args, **kwargs)

        # 界面全中文：加载 Qt 自带中文翻译，标准对话框（是/否/确定/取消）才不会显示英文
        _install_chinese_translator()

        self.path = ''
        self.path_right_click = ''
        self.left = 1
        self.right = 6
        self.config_manager = ConfigManager()
        # -- 私密模式密钥服务（与 privi 完全兼容的密钥包 / 加解密）--
        self.private_service = PrivateService()
        self.private_service.clear_cache()   # 上次运行残留的解密明文一律清掉
        self.private_batch_thread = None
        self.style_sheet = self.styleSheet()
        self.full_screen_state = MainWindow.normal
        self.private_mode = False

        # -- 无边框窗口设置 --
        self.setWindowFlags(Qt.FramelessWindowHint)

        self.setWindowTitle('多媒体播放器')
        # 根据屏幕可用尺寸调整窗口大小，确保不超出屏幕
        desktop = QApplication.desktop()
        screen_rect = desktop.availableGeometry()
        win_w = min(1500, screen_rect.width() - 80)
        win_h = min(700, screen_rect.height() - 80)
        self.resize(win_w, win_h)

        # ---- 全局暗色主题 ----
        # 目录树展开/收起箭头：closed / open 两种状态都显式指定 image
        # （原来 closed 只有 border-image: none，open 没有图像 ⇒ 展开后的箭头与深色背景同色、看不见）
        branch_closed_icon, branch_open_icon = _ensure_tree_branch_icons()
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
                image: url("__TREE_BRANCH_CLOSED__");
                border-image: none;
            }
            QTreeView::branch:has-children:open {
                image: url("__TREE_BRANCH_OPEN__");
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
        """.replace('__TREE_BRANCH_CLOSED__', branch_closed_icon)
           .replace('__TREE_BRANCH_OPEN__', branch_open_icon))

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

        # ---- 私密模式左侧树 ----
        self.private_tree_model = QDirModel()
        self.private_tree_model.sort(3, order=Qt.SortOrder.DescendingOrder)
        self.private_tree_view = QTreeView()
        self.private_tree_view.setModel(self.private_tree_model)
        self.private_tree_view.setColumnHidden(1, True)
        self.private_tree_view.setColumnHidden(2, True)
        self.private_tree_view.setColumnHidden(3, True)
        private_header = self.private_tree_view.header()
        private_header.setStretchLastSection(False)
        private_header.setSectionResizeMode(0, QHeaderView.Fixed)
        private_header.setVisible(False)
        self.private_tree_view.setColumnWidth(0, 360)
        self.private_tree_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.private_tree_view.setItemDelegate(FileDisplayDelegate(self.private_tree_view))
        self.private_tree_view.clicked.connect(self._on_private_tree_clicked)
        self.private_tree_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.private_tree_view.customContextMenuRequested.connect(self._private_right_click_menu)
        self.private_tree_view.setVisible(False)
        self.mainQWidget.addWidget(self.private_tree_view)

        self.work = QVBoxLayout()
        self.work.setContentsMargins(0, 0, 0, 0)
        self.work.addWidget(self.video_show_qwidget)
        self.video_show_qwidget.setVisible(False)
        self.work.addWidget(self.pic_show_qwidget)

        # ---- 私密模式覆盖层：无路径时显示"打开私密库"按钮 ----
        self.private_overlay_widget = QWidget()
        private_overlay_layout = QVBoxLayout(self.private_overlay_widget)
        private_overlay_layout.setAlignment(Qt.AlignCenter)
        self.open_private_lib_btn = QPushButton("打开私密库")
        self.open_private_lib_btn.setFixedSize(160, 48)
        self.open_private_lib_btn.setStyleSheet("""
            QPushButton {
                background-color: #89b4fa;
                color: #1e1e2e;
                border: none;
                border-radius: 8px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #b4d0fb;
            }
        """)
        self.open_private_lib_btn.clicked.connect(self._open_private_library)
        private_overlay_layout.addWidget(self.open_private_lib_btn)
        self.private_overlay_widget.setVisible(False)
        self.work.addWidget(self.private_overlay_widget)

        self.workQWidget = QWidget()
        self.workQWidget.setLayout(self.work)

        self.mainQWidget.addWidget(self.workQWidget)
        # splitter 含 3 个 widget: treeView / private_tree_view / workQWidget
        # 普通模式下 private_tree_view 隐藏，比例为 left : 0 : right
        sizes = [10000 * self.left, 0, 10000 * self.right]
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
        self.statusLabel.setText("就绪")
        self.statusbar.addPermanentWidget(self.statusLabel, stretch=1)

        self.toggle_tree_btn = QPushButton("◀ 隐藏列表")
        self.toggle_tree_btn.setFixedSize(90, 22)
        self.toggle_tree_btn.clicked.connect(self.toggle_tree)
        self.statusbar.addPermanentWidget(self.toggle_tree_btn)

        self.tree_visible = True
        # 记录展开时的窗口比例，用于恢复
        self.tree_sizes = [10000 * self.left, 10000 * self.right]

        # -- 主布局: 标题列 + 菜单栏 + mainQWidget + 状态栏 --
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

        # -- 菜单栏 --
        self._setup_menu_bar()
        central_layout.addWidget(self.menu_bar)

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
        original_path = path  # 保存原始目标路径，用于后续滚动定位
        self.treeView.setExpanded(self.model.index(path), True)
        while True:
            if path != os.path.dirname(path):
                path = os.path.dirname(path)
                self.treeView.setExpanded(self.model.index(path), True)
            else:
                break
        # 展开完成后将原始目标目录滚动到树形控件中间位置
        target_index = self.model.index(original_path)
        self.treeView.scrollTo(target_index, QAbstractItemView.PositionAtCenter)

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

        self.change_show(MainWindow.show_type_pic)
        self.inputAndExeLayout.set_content_path(self.path_right_click)

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
            self.inputAndExeLayout.set_content_path(self.path)
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
        if self.private_mode:
            self.treeView.setVisible(False)
            self.private_tree_view.setVisible(True)
        else:
            self.treeView.setVisible(True)
        self.statusbar.setVisible(True)
        # 恢复标题栏
        self.title_bar.setVisible(True)
        # 恢复菜单栏（全屏时被隐藏）
        self.menu_bar.setVisible(True)
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
            self.notice("快捷键：Shift + O")

    def full_screen_custom(self):
        if self.video_show_qwidget.isVisible():
            self.video_show_layout.setVisible(False)
        if self.pic_show_qwidget.isVisible():
            self.pic_show_layout.setVisible(False)

        self.treeView.setVisible(False)
        self.private_tree_view.setVisible(False)
        self.statusbar.setVisible(False)
        # 隐藏标题栏
        self.title_bar.setVisible(False)
        # 全屏时隐藏菜单栏（Esc / F 退出全屏后恢复）
        self.menu_bar.setVisible(False)
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
        # 停止后台目录扫描线程，避免退出时 QThread 仍在运行
        if hasattr(self, 'inputAndExeLayout'):
            self.inputAndExeLayout.cancel_scan(wait_ms=1500)
        if hasattr(self, 'video_show_layout'):
            # 关闭前先保存当前播放位置（无论是否处于暂停状态）
            if self.video_show_layout.path and os.path.exists(self.video_show_layout.path):
                pos = self.video_show_layout.player.position()
                dur = self.video_show_layout.player.duration()
                self.video_show_layout.position_manager.save_position(
                    self.video_show_layout.path, pos, dur
                )

            if self.video_show_layout.timer.isActive():
                self.video_show_layout.timer.stop()
            # 停止播放并释放媒体资源
            self.video_show_layout.player.stop()
            self.video_show_layout.player.setMedia(QMediaContent())
            # 断开视频输出，防止 CVDisplayLink 回调访问已释放对象
            self.video_show_layout.player.setVideoOutput(None)

        # 退出时清掉私密模式的解密缓存（明文不应落盘留存）
        try:
            if hasattr(self, 'private_service'):
                self.private_service.clear_cache()
                self.private_service.close()
        except Exception as e:
            logger.warning(f'退出时清理私密缓存失败: {e}')

        event.accept()

    def toggle_tree(self):
        if self.private_mode:
            return
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
        if event.type() == QEvent.KeyPress:
            # Esc：退出全屏
            if event.key() == Qt.Key_Escape and self.full_screen_state == MainWindow.full:
                self.full_screen_state = MainWindow.normal
                self.screen_normal()
                return True
            # M：全屏时切换悬浮控制面板显示/隐藏
            if event.key() == Qt.Key_M and self.full_screen_state != MainWindow.normal:
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
        if event.type() == QEvent.WindowStateChange:
            self.title_bar.updateMaximizeIcon()
        super().changeEvent(event)

    def notice(self, content):
        self.statusLabel.setText(content)

    # ============================================
    #  菜单栏
    # ============================================
    def _setup_menu_bar(self):
        self.menu_bar = QMenuBar(self)
        self.menu_bar.setStyleSheet("""
            QMenuBar {
                background-color: #181825;
                color: #cdd6f4;
                border-bottom: 1px solid #313244;
                padding: 2px 8px;
                font-size: 13px;
            }
            QMenuBar::item {
                padding: 4px 10px;
                border-radius: 4px;
            }
            QMenuBar::item:selected {
                background-color: #45475a;
            }
            QMenu {
                background-color: #1e1e2e;
                color: #cdd6f4;
                border: 1px solid #45475a;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 28px 6px 16px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #45475a;
            }
            QMenu::separator {
                height: 1px;
                background-color: #313244;
                margin: 4px 8px;
            }
        """)

        # ---- 文件菜单 ----
        file_menu = self.menu_bar.addMenu("文件(&F)")
        exit_action = QAction("退出(&Q)", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # ---- 密钥菜单（privi 兼容的密钥包导入 / 导出）----
        key_menu = self.menu_bar.addMenu("密钥(&K)")

        self.import_key_action = QAction("导入密钥...", self)
        self.import_key_action.triggered.connect(self._import_key_package)
        key_menu.addAction(self.import_key_action)

        self.export_key_action = QAction("导出密钥...", self)
        self.export_key_action.triggered.connect(self._export_key_package)
        key_menu.addAction(self.export_key_action)

        key_menu.addSeparator()

        self.key_status_action = QAction("密钥状态...", self)
        self.key_status_action.triggered.connect(self._show_key_status)
        key_menu.addAction(self.key_status_action)

        # ---- 视图菜单 ----
        view_menu = self.menu_bar.addMenu("视图(&V)")

        mode_group = QActionGroup(self)
        mode_group.setExclusive(True)

        self.normal_mode_action = QAction("普通模式", self)
        self.normal_mode_action.setCheckable(True)
        self.normal_mode_action.setChecked(True)
        self.normal_mode_action.triggered.connect(lambda checked: checked and self._toggle_private_mode(False))
        mode_group.addAction(self.normal_mode_action)
        view_menu.addAction(self.normal_mode_action)

        self.private_mode_action = QAction("私密模式", self)
        self.private_mode_action.setCheckable(True)
        self.private_mode_action.setChecked(False)
        self.private_mode_action.triggered.connect(lambda checked: checked and self._toggle_private_mode(True))
        mode_group.addAction(self.private_mode_action)
        view_menu.addAction(self.private_mode_action)

        # ---- 控制菜单（图片悬浮控制栏的显隐）----
        control_menu = self.menu_bar.addMenu("控制(&C)")

        self.show_control_action = QAction("显示控制器", self)
        self.show_control_action.setCheckable(True)
        self.show_control_action.setChecked(True)
        self.show_control_action.triggered.connect(self._toggle_pic_control_panel)
        control_menu.addAction(self.show_control_action)

        # 点击面板 ✕ 隐藏后，回写菜单勾选状态
        self.pic_show_layout.controlPanelVisibilityChanged.connect(
            self._on_pic_control_panel_visibility_changed)

        # ---- 设置菜单 ----
        settings_menu = self.menu_bar.addMenu("设置(&S)")

        self.slideshow_settings_action = QAction("幻灯片...", self)
        self.slideshow_settings_action.triggered.connect(self._show_slideshow_settings)
        settings_menu.addAction(self.slideshow_settings_action)

        # ---- 帮助菜单 ----
        help_menu = self.menu_bar.addMenu("帮助(&H)")
        about_action = QAction("关于(&A)...", self)
        about_action.triggered.connect(self._show_about_dialog)
        help_menu.addAction(about_action)

    def _toggle_private_mode(self, enable):
        if enable == self.private_mode:
            return

        self.private_mode = enable

        if enable:
            # 切换到私密模式
            self._save_normal_state()
            self.normal_mode_action.setChecked(False)
            self.private_mode_action.setChecked(True)

            # 隐藏普通树
            self.treeView.setVisible(False)
            self.toggle_tree_btn.setEnabled(False)

            # 隐藏普通模式的视频/图片
            self.video_show_qwidget.setVisible(False)
            self.pic_show_qwidget.setVisible(False)

            # 检查是否有私密库路径
            if self.config_manager.exist(MainWindow.private_library_path_key):
                private_path = self.config_manager.get(MainWindow.private_library_path_key)
                if os.path.isdir(private_path):
                    self._load_private_library(private_path)
                else:
                    self._show_private_overlay()
            else:
                self._show_private_overlay()

            self.statusLabel.setText("私密模式")
        else:
            # 切换回普通模式
            self.normal_mode_action.setChecked(True)
            self.private_mode_action.setChecked(False)

            # 隐藏私密切换相关控件
            self.private_tree_view.setVisible(False)
            self.private_overlay_widget.setVisible(False)

            # 恢复普通模式状态
            self._restore_normal_state()
            self.toggle_tree_btn.setEnabled(True)

            self.statusLabel.setText("普通模式")

    def _save_normal_state(self):
        """保存普通模式下的UI状态"""
        self._saved_tree_visible = self.tree_visible
        self._saved_tree_sizes = self.mainQWidget.sizes()
        self._saved_video_visible = self.video_show_qwidget.isVisible()
        self._saved_pic_visible = self.pic_show_qwidget.isVisible()

    def _restore_normal_state(self):
        """恢复普通模式下的UI状态"""
        if hasattr(self, '_saved_tree_visible'):
            self.tree_visible = self._saved_tree_visible
            self.treeView.setVisible(self._saved_tree_visible)
            if self._saved_tree_visible:
                self.toggle_tree_btn.setText("◀ 隐藏列表")
            else:
                self.toggle_tree_btn.setText("▶ 展开列表")
        else:
            self.treeView.setVisible(True)
            self.toggle_tree_btn.setText("◀ 隐藏列表")
            self.tree_visible = True

        if hasattr(self, '_saved_video_visible') and self._saved_video_visible:
            self.video_show_qwidget.setVisible(True)
        if hasattr(self, '_saved_pic_visible') and self._saved_pic_visible:
            self.pic_show_qwidget.setVisible(True)

        if hasattr(self, '_saved_tree_sizes'):
            self.mainQWidget.setSizes(self._saved_tree_sizes)

    def _show_private_overlay(self):
        """显示私密模式覆盖层（无路径状态）"""
        self.private_overlay_widget.setVisible(True)
        self.video_show_qwidget.setVisible(False)
        self.pic_show_qwidget.setVisible(False)
        self.private_tree_view.setVisible(False)
        # 无路径时树隐藏，右侧工作区占满
        self.mainQWidget.setSizes([0, 0, 1])

    def _open_private_library(self):
        """打开私密库文件夹选择对话框"""
        selected_path = QFileDialog.getExistingDirectory(self, "选择私密库文件夹")
        if not selected_path or not os.path.isdir(selected_path):
            return

        self.config_manager.add_or_update(MainWindow.private_library_path_key, selected_path)
        self._load_private_library(selected_path)

    def _load_private_library(self, path):
        """加载私密库路径到左侧树"""
        self.private_overlay_widget.setVisible(False)
        self.private_tree_view.setVisible(True)
        self.private_tree_model.refresh()
        root_index = self.private_tree_model.index(path)
        self.private_tree_view.setRootIndex(root_index)
        # 展开根目录
        self.private_tree_view.setExpanded(root_index, True)
        # 私密树 : 工作区 = left : right
        self.mainQWidget.setSizes([0, 10000 * self.left, 10000 * self.right])
        if self.private_service.has_key():
            self.notice('私密模式：已加载密钥')
        else:
            self.notice('私密模式：尚未导入密钥，加密文件请先「密钥 → 导入密钥」')

    def _on_private_tree_clicked(self, qmodelindex):
        """私密模式下树节点点击事件（点到密文时先解密再交给现有展示逻辑）"""
        file_path = self.private_tree_model.filePath(qmodelindex)

        if os.path.isdir(file_path):
            self._load_private_slideshow(file_path)
            return

        if not os.path.isfile(file_path):
            return

        # 停止幻灯片定时器
        if self.inputAndExeLayout.timer.isActive():
            self.inputAndExeLayout.timer.stop()

        # 密文 → 解密到本次运行缓存；明文 → 原样返回
        try:
            play_path, display_name = self.private_service.resolve_playable(file_path)
        except Exception as e:
            logger.error(f'私密文件解密失败 {file_path}: {e}')
            self.notice('解密失败：' + str(e))
            QMessageBox.warning(self, '私密文件', str(e))
            return

        # 根据文件类型切换显示（复用普通模式的播放 / 看图功能）
        if self.video_show_layout.is_video(play_path):
            self.video_show_layout.play_mode = self.video_show_layout.play_mode_one
            self.video_show_layout.play_list.clear()
            self.video_show_layout.play_list_index = 0
            self.change_show(MainWindow.show_type_video)
            self.video_show_layout.play(play_path)
        elif self.pic_show_layout.is_pic(play_path):
            self.pic_show_layout.counter = 0
            self.pic_show_layout.inputAndExeLayout.list_files.clear()
            self.pic_show_layout.inputAndExeLayout.list_files.append(play_path)
            self.change_show(MainWindow.show_type_pic)
            self.pic_show_layout.play(play_path)
        else:
            message = '文件格式不支持：' + display_name
            self.video_show_layout.titleQLabel.setText(message)
            self.pic_show_layout.titleQLabel.setText(message)
            self.notice(message)
            return

        # 标题栏显示原始文件名（而不是解密缓存里的路径）
        try:
            self.title_bar.setInfo(os.path.splitext(display_name)[0], '')
        except Exception:
            pass

    def _load_private_slideshow(self, dir_path):
        """私密目录：把目录下的图片（含密文）准备好，交给幻灯片功能展示。"""
        try:
            images = self.private_service.list_images(dir_path)
        except Exception as e:
            logger.error(f'读取私密目录失败 {dir_path}: {e}')
            self.notice('读取目录失败：' + str(e))
            return

        if not images:
            self.pic_show_qwidget.setVisible(False)
            self.video_show_qwidget.setVisible(False)
            self.private_overlay_widget.setVisible(False)
            self.notice('该目录下没有可展示的图片')
            return

        progress = QProgressDialog('正在解密图片...', '取消', 0, len(images), self)
        progress.setWindowTitle('私密模式')
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)

        playable = []
        display_names = []
        for index, path in enumerate(images):
            if progress.wasCanceled():
                break
            progress.setValue(index)
            progress.setLabelText('解密：' + os.path.basename(path))
            QApplication.processEvents()
            try:
                cache_path, display_name = self.private_service.resolve_playable(path)
            except Exception as e:
                logger.warning(f'私密图片解密失败 {path}: {e}')
                continue
            playable.append(cache_path)
            display_names.append(display_name)
        progress.setValue(len(images))
        progress.close()

        if not playable:
            self.notice('没有可展示的图片（可能是缺少配套密钥）')
            return

        # 私密模式：文件已解密到缓存目录，列表直接用解密后的明文路径
        # （先取消后台扫描，避免其它目录的扫描结果覆盖这里的列表）
        self.inputAndExeLayout.cancel_scan()
        self.inputAndExeLayout.content_path = dir_path
        self.inputAndExeLayout.list_files.clear()
        self.inputAndExeLayout.list_files.extend(playable)
        self.pic_show_layout.counter = 0
        self.change_show(MainWindow.show_type_pic)
        self.pic_show_layout.play(playable[0])
        try:
            self.title_bar.setInfo(os.path.splitext(display_names[0])[0],
                                   '(1/%d)' % len(playable))
        except Exception:
            pass

    # ============================================
    #  私密模式：左侧树右键（加密 / 解密）
    # ============================================
    def _private_right_click_menu(self, pos):
        """私密模式左侧树右键菜单（只有私密模式才有）。"""
        if not self.private_mode:
            return

        index = self.private_tree_view.indexAt(pos)
        if index.isValid():
            target = self.private_tree_model.filePath(index)
        else:
            root_index = self.private_tree_view.rootIndex()
            target = self.private_tree_model.filePath(root_index) if root_index.isValid() else ''
        if not target:
            self.notice('请先在左侧树中选择目录')
            return

        menu = QMenu(self.private_tree_view)
        encrypt_action = menu.addAction('加密该路径下的图片和视频')
        decrypt_action = menu.addAction('解密该路径下的文件')
        menu.addSeparator()
        refresh_action = menu.addAction('刷新')

        chosen = menu.exec_(self.private_tree_view.viewport().mapToGlobal(pos))
        if chosen == encrypt_action:
            self._encrypt_private_path(target)
        elif chosen == decrypt_action:
            self._decrypt_private_path(target)
        elif chosen == refresh_action:
            self.private_tree_model.refresh()

    def _encrypt_private_path(self, target):
        try:
            files, skipped = self.private_service.scan_encryptable(target)
        except Exception as e:
            logger.error(f'扫描待加密文件失败 {target}: {e}')
            self.notice('扫描失败：' + str(e))
            return
        if not files:
            QMessageBox.information(self, '加密', '该路径下没有需要加密的图片/视频文件。')
            return

        if not self.private_service.has_key():
            answer = QMessageBox.question(
                self, '尚未导入密钥',
                '当前还没有密钥。\n继续将自动生成一把新的随机密钥'
                '（可通过「密钥 → 导出密钥」备份）。\n\n继续？',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if answer != QMessageBox.Yes:
                return

        answer = QMessageBox.question(
            self, '加密确认',
            '即将加密 %d 个图片/视频文件：\n%s\n\n'
            '将同时加密文件内容与文件名，加密后源文件会被删除，只保留加密文件。\n'
            '另有 %d 个非媒体 / 已加密文件会被跳过。\n\n继续？'
            % (len(files), target, skipped),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        self._run_private_batch('encrypt', target, len(files))

    def _decrypt_private_path(self, target):
        try:
            files, missing_key = self.private_service.scan_decryptable(target)
        except Exception as e:
            logger.error(f'扫描待解密文件失败 {target}: {e}')
            self.notice('扫描失败：' + str(e))
            return
        if not files:
            message = '该路径下没有可解密的文件。'
            if missing_key:
                message += '\n另有 %d 个密文没有配套密钥记录（请先导入密钥）。' % missing_key
            QMessageBox.information(self, '解密', message)
            return

        detail = ''
        if missing_key:
            detail = '\n另有 %d 个密文没有配套密钥记录，会被跳过。' % missing_key
        answer = QMessageBox.question(
            self, '解密确认',
            '即将解密 %d 个文件：\n%s\n\n'
            '解密后恢复原文件名并删除密文。%s\n\n继续？'
            % (len(files), target, detail),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        self._run_private_batch('decrypt', target, len(files))

    def _run_private_batch(self, mode, target, total):
        if self.private_batch_thread is not None and self.private_batch_thread.isRunning():
            QMessageBox.information(self, '私密模式', '已有加解密任务在运行，请等待完成。')
            return

        title = '正在加密' if mode == 'encrypt' else '正在解密'
        progress = QProgressDialog(title, '取消', 0, max(total, 1), self)
        progress.setWindowTitle('私密模式')
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        thread = PrivateBatchThread(mode, target, parent=self)
        thread.progress.connect(
            lambda done, all_count, name: self._on_private_batch_progress(progress, done, all_count, name))
        thread.completed.connect(
            lambda stats: self._on_private_batch_completed(mode, stats, progress))
        thread.failed.connect(
            lambda message: self._on_private_batch_failed(message, progress))
        progress.canceled.connect(thread.cancel)

        self.private_batch_thread = thread
        self.statusLabel.setText('%s：%s' % (title, target))
        thread.start()

    @staticmethod
    def _on_private_batch_progress(progress, done, total, name):
        progress.setMaximum(max(total, 1))
        progress.setValue(min(done, max(total, 1)))
        if name:
            progress.setLabelText(name)

    def _on_private_batch_completed(self, mode, stats, progress):
        progress.setValue(progress.maximum())
        progress.close()
        self.private_batch_thread = None

        # 加解密后缓存里的明文已经过期，清掉重新按需解密
        self.private_service.clear_cache()
        self.private_tree_model.refresh()
        self.model.refresh()

        if mode == 'encrypt':
            message = '加密完成：成功 %d 个，跳过 %d 个，失败 %d 个。' % (
                stats.get('encrypted', 0), stats.get('skipped', 0), stats.get('failed', 0))
            if stats.get('kept_source'):
                message += '\n有 %d 个文件已加密但源文件删除失败（密文已生成）。' % stats['kept_source']
        else:
            message = '解密完成：成功 %d 个，失败 %d 个。' % (
                stats.get('decrypted', 0), stats.get('failed', 0))
            if stats.get('missing_key'):
                message += '\n有 %d 个密文没有配套密钥记录，已跳过。' % stats['missing_key']
            if stats.get('kept_source'):
                message += '\n有 %d 个文件明文已恢复但密文删除失败。' % stats['kept_source']
        if stats.get('cancelled'):
            message += '\n任务已被取消（已处理的文件不受影响，可重跑）。'
        errors = stats.get('errors') or []
        if errors:
            message += '\n\n前几个错误：\n' + '\n'.join(errors[:5])

        QMessageBox.information(self, '私密模式', message)
        self.notice(message.replace('\n', ' '))

    def _on_private_batch_failed(self, message, progress):
        progress.close()
        self.private_batch_thread = None
        logger.error('私密批量操作失败: ' + message)
        QMessageBox.critical(self, '私密模式', '操作失败：\n' + message)
        self.notice('私密操作失败：' + message)

    # ============================================
    #  密钥管理（导入 / 导出 / 状态）
    # ============================================
    def _import_key_package(self):
        """导入 privi 导出的密钥数据库（v2 SQLite，兼容 v1 JSON）。"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, '导入 privi 密钥数据库', '',
            '密钥数据库 (*.db *.json);;所有文件 (*.*)')
        if not file_path:
            return

        try:
            summary = self.private_service.inspect_key_package(file_path)
        except Exception as e:
            logger.error(f'检查密钥包失败: {e}')
            summary = None
        if summary is None:
            QMessageBox.warning(
                self, '导入密钥',
                '该文件不是 privi 导出的密钥包。\n'
                '（需要 privi「设置 → 导出密钥」生成的 .db，或旧版 v1 JSON）')
            return

        detail = ('密钥包版本：%s\n创建时间：%s\n文件记录：%d 条（其中 %d 条带加密密钥）\n包含盐值：%s' % (
            summary.get('version', '-'),
            summary.get('created_at') or '-',
            summary.get('file_count', 0),
            summary.get('encrypted_file_count', 0),
            '是' if summary.get('has_salt') else '否'))
        answer = QMessageBox.question(
            self, '导入密钥',
            detail + '\n\n导入后将使用该密钥包解开本机的私密文件，继续？',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if answer != QMessageBox.Yes:
            return

        result = self.private_service.import_key_package(file_path)
        if not result.get('ok') and result.get('reason') == 'key_conflict':
            answer = QMessageBox.question(
                self, '密钥冲突',
                result.get('message', '') + '\n\n仍要覆盖本机密钥吗？',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                self.notice('已取消导入密钥')
                return
            result = self.private_service.import_key_package(file_path, overwrite_key=True)

        if not result.get('ok'):
            QMessageBox.warning(self, '导入密钥', result.get('message') or '导入失败')
            return

        message = ('密钥导入成功。\n新增文件记录 %d 条，更新 %d 条，跳过 %d 条。' % (
            result.get('imported', 0), result.get('updated', 0), result.get('skipped', 0)))
        QMessageBox.information(self, '导入密钥', message)
        self.notice(message.replace('\n', ' '))
        self.private_tree_model.refresh()

    def _export_key_package(self):
        """导出与 privi 完全一致的密钥数据库文件（SQLite，*.db）。"""
        if not self.private_service.has_key():
            QMessageBox.warning(
                self, '导出密钥',
                '当前还没有可导出的密钥。\n'
                '请先导入 privi 导出的密钥包，或先对文件执行一次加密（会自动生成密钥）。')
            return

        directory = QFileDialog.getExistingDirectory(self, '选择密钥导出目录')
        if not directory:
            return

        try:
            path = self.private_service.export_key_package(directory)
        except Exception as e:
            logger.error(f'导出密钥失败: {e}')
            QMessageBox.critical(self, '导出密钥', '导出失败：\n' + str(e))
            return

        QMessageBox.information(
            self, '导出密钥',
            '已导出与 privi 完全兼容的密钥数据库：\n%s\n\n'
            '⚠ 密钥包等同于明文密钥，配合私密目录可解密全部文件；'
            '请离线保存或放进加密网盘，不要外传。' % path)
        self.notice('已导出密钥：' + path)

    def _show_key_status(self):
        info = self.private_service.key_info()
        if info is None:
            QMessageBox.information(
                self, '密钥状态',
                '尚未导入密钥。\n\n'
                '可通过「密钥 → 导入密钥」选择 privi 导出的 .db 密钥包；\n'
                '也可以直接对私密目录执行加密（会自动生成新密钥）。')
            return
        QMessageBox.information(
            self, '密钥状态',
            '密钥来源：%s\n创建时间：%s\n已记录加密文件：%d 个\n盐值：%s' % (
                info.get('source') or '-',
                info.get('created_at') or '-',
                info.get('encrypted_count', 0),
                '有' if info.get('salt') else '无'))

    def _show_slideshow_settings(self):
        """「设置 → 幻灯片」：调整幻灯片自动播放的时间间隔（秒），确认后立即生效并持久化。"""
        layout = self.inputAndExeLayout

        dialog = QDialog(self)
        dialog.setWindowTitle("幻灯片设置")
        dialog.setModal(True)
        dialog.setMinimumWidth(360)

        spin = QSpinBox()
        spin.setRange(PicInputLayout.min_interval_seconds, PicInputLayout.max_interval_seconds)
        spin.setSuffix(" 秒")
        spin.setValue(layout.get_interval_seconds())

        form = QFormLayout()
        form.setContentsMargins(20, 16, 20, 8)
        form.setSpacing(10)
        form.addRow("幻灯片播放时间间隔:", spin)

        tip = QLabel("设置后立即生效，下次启动沿用该间隔。")
        tip.setWordWrap(True)
        form.addRow(tip)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)

        root = QVBoxLayout(dialog)
        root.addLayout(form)
        root.addWidget(buttons)

        if dialog.exec_() != QDialog.Accepted:
            return

        seconds = layout.set_interval_seconds(spin.value())
        self.notice("幻灯片时间间隔已设置为 %d 秒" % seconds)

    def _toggle_pic_control_panel(self, checked):
        """菜单「控制 → 显示控制器」：勾选显示、取消隐藏。"""
        if checked:
            self.pic_show_layout.show_control_panel()
        else:
            self.pic_show_layout.hide_control_panel()

    def _on_pic_control_panel_visibility_changed(self, visible):
        """点击悬浮面板上的 ✕ 隐藏后，同步菜单勾选状态。"""
        if hasattr(self, 'show_control_action'):
            self.show_control_action.setChecked(visible)

    def _show_about_dialog(self):
        """显示关于对话框"""
        version = "未知"
        try:
            version_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION")
            if os.path.exists(version_path):
                with open(version_path, "r", encoding="utf-8") as f:
                    version = f.read().strip()
        except Exception:
            pass

        import platform
        python_version = platform.python_version()
        try:
            from PyQt5.QtCore import QT_VERSION_STR
            pyqt_version = QT_VERSION_STR
        except ImportError:
            pyqt_version = "5.15.10"

        about_text = (
            f"<h2>多媒体播放器</h2>"
            f"<p><b>版本：</b>{version}</p>"
            f"<p><b>构建信息：</b></p>"
            f"<ul>"
            f"<li>Python 运行环境：{python_version}</li>"
            f"<li>Qt（PyQt5）版本：{pyqt_version}</li>"
            f"<li>操作系统：{platform.system()} {platform.release()}</li>"
            f"</ul>"
            f"<p>基于 PyQt5 与 OpenCV 的桌面多媒体播放器，<br>"
            f"支持视频/音频播放、裁剪、截图、幻灯片等功能。</p>"
        )

        QMessageBox.about(self, "关于 多媒体播放器", about_text)


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