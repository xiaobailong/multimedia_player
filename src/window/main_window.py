# -*- coding: utf-8 -*-
"""主窗口：只做「状态持有 + 界面组装 + 信号接线」。

功能实现按职责拆在同包的模块里：

| 模块 | 负责 |
| --- | --- |
| ``theme`` | 全局 QSS、目录树箭头图标、中央容器 / 菜单栏样式 |
| ``i18n`` | Qt 标准对话框中文翻译 |
| ``file_delegate`` / ``file_tree`` | 左侧文件树的委托与控件 |
| ``menu_bar`` | 菜单栏构建（动作仍指向本窗口的方法） |
| ``media_actions`` | 文件树 → 播放 / 复制 / 移动 / 删除 |
| ``view_actions`` | 全屏、快捷键、窗口状态、显示切换、关闭清理 |
| ``rating_actions`` | 评分（数字键 1~5） |
| ``collect_actions`` | 归集（批量拷贝） |
| ``private_actions`` | 私密功能（密文点开即解密播放 / 批量加解密 / 私密幻灯片） |
| ``key_actions`` | 密钥包导入 / 导出 / 状态 |
| ``tool_actions`` | 解码器 / ffmpeg / 幻灯片设置 / 关于 |
"""
import os

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QApplication, QLabel, QMainWindow, QSplitter,
                             QStatusBar, QVBoxLayout, QWidget)

from src.data_manager.config_manager import ConfigManager
from src.data_manager.rating_manager import RatingManager
from src.layout.custom_title_bar import CustomTitleBar
from src.layout.pic_show_layout import PicShowLayout
from src.layout.video_show_layout import VideoShowLayout
from src.private_mode.private_service import PrivateService
from src.window.collect_actions import CollectActionsMixin
from src.window.file_tree import FileTreeView, create_dir_model
from src.window.i18n import install_chinese_translator
from src.window.key_actions import KeyActionsMixin
from src.window.media_actions import MediaActionsMixin
from src.window.menu_bar import build_menu_bar
from src.window.private_actions import PrivateActionsMixin
from src.window.rating_actions import RatingActionsMixin
from src.window.theme import CENTRAL_WIDGET_STYLE, build_global_style_sheet
from src.window.tool_actions import ToolActionsMixin
from src.window.view_actions import ViewActionsMixin


class MainWindow(MediaActionsMixin, ViewActionsMixin, RatingActionsMixin,
                 CollectActionsMixin, PrivateActionsMixin, KeyActionsMixin,
                 ToolActionsMixin, QMainWindow):
    """应用主窗口。

    注意：mixin 必须排在 ``QMainWindow`` **之前**，否则 ``keyPressEvent`` /
    ``closeEvent`` / ``eventFilter`` / ``changeEvent`` 会被基类实现遮蔽。
    """

    # 配置键 / 显示类型 / 全屏状态（各 mixin 通过 self 访问，保持原有取值）
    expand_path_config_key = 'default.expand.path'
    open_path_config_key = 'default.open.path'
    private_library_path_key = 'private.library.path'
    private_library_dirs_key = 'private.library.dirs'
    show_type_video = 'video'
    show_type_pic = 'pic'
    normal = 0
    full = 1

    def __init__(self, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)

        # 界面全中文：加载 Qt 自带中文翻译，标准对话框（是/否/确定/取消）才不会显示英文
        install_chinese_translator()

        self._init_services()
        self._init_window()
        self._build_ui()
        self._restore_last_session()
        self._schedule_startup_checks()

    # ============================================
    #  初始化：状态 → 窗口 → 界面 → 会话恢复
    # ============================================
    def _init_services(self):
        """整个窗口生命周期共享的状态与后台服务句柄。"""
        self.path = ''
        self.path_right_click = ''
        self.left = 1
        self.right = 6
        self.config_manager = ConfigManager()
        # -- 媒体评分（按内容指纹存库，文件移动 / 改名后仍能识别）--
        self.rating_manager = RatingManager()
        # -- 私密模式密钥服务（与密册完全兼容的密钥包 / 加解密）--
        self.private_service = PrivateService()
        self.private_service.clear_cache()   # 上次运行残留的解密明文一律清掉
        self.private_batch_thread = None
        # 被标记为「私密库」的目录（本目录下全是密文，树里打标记 / 列表自动走解密分支）
        self._private_library_dirs = []
        self._load_private_library_dirs()
        # 归集后台线程（扫描 / 拷贝）
        self.collect_thread = None
        # 解码器安装后台线程（下载 / 安装）
        self.decoder_thread = None
        # ffmpeg 下载后台线程（开发环境缺失时自动下载）
        self.ffmpeg_thread = None
        self.style_sheet = self.styleSheet()
        self.full_screen_state = self.normal

    def _init_window(self):
        """窗口本身：无边框、标题、按屏幕可用区域定尺寸、全局暗色主题。"""
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
        self.setStyleSheet(build_global_style_sheet())

    def _build_ui(self):
        """组装界面：左侧树 + 右侧工作区 → 标题栏 + 菜单栏 + 状态栏。"""
        self.mainQWidget = QSplitter(Qt.Horizontal)

        self._build_media_views()
        self._build_file_trees()
        self._build_work_area()
        self._build_title_bar()
        self._build_status_bar()
        self._build_central_widget()

        # 全屏模式下，安装全局事件过滤器确保 Esc 键始终能退出全屏
        QApplication.instance().installEventFilter(self)

        self.show()

    def _build_media_views(self):
        """视频 / 图片展示区：两个 QWidget 叠在右侧工作区，同一时刻只显示一个。"""
        self.video_show_layout = VideoShowLayout(self)
        # 密文视频（无扩展名）播到哪一集解哪一集：布局只管路径，解密交给私密服务。
        # 用 lambda 而不是直接绑定方法，服务实例被替换/重建时也能跟上（ADR-027）。
        self.video_show_layout.set_path_resolver(
            lambda path: self.private_service.resolve_playable(path))
        self.pic_show_layout = PicShowLayout(self)
        self.inputAndExeLayout = self.pic_show_layout.inputAndExeLayout

        self.video_show_qwidget = QWidget()
        self.video_show_layout.setContentsMargins(0, 0, 0, 0)
        self.video_show_qwidget.setLayout(self.video_show_layout)

        self.pic_show_qwidget = QWidget()
        self.pic_show_layout.setContentsMargins(0, 0, 0, 0)
        self.pic_show_qwidget.setLayout(self.pic_show_layout)

    def _build_file_trees(self):
        """左侧文件树（唯一一棵）：普通文件与密文都在这里，点开密文时按需解密。"""
        self.model = create_dir_model()
        self.treeView = FileTreeView(self.model)
        self.treeView.setContextMenuPolicy(Qt.CustomContextMenu)
        self.treeView.customContextMenuRequested.connect(self.right_click_menu)
        self.treeView.clicked.connect(self.on_tree_clicked)
        self.treeView.selectionModel().selectionChanged.connect(self.on_selection_changed)
        self.mainQWidget.addWidget(self.treeView)

    def _build_work_area(self):
        """右侧工作区：视频 / 图片两个展示区（同一时刻只显示一个）。"""
        self.work = QVBoxLayout()
        self.work.setContentsMargins(0, 0, 0, 0)
        self.work.addWidget(self.video_show_qwidget)
        self.video_show_qwidget.setVisible(False)
        self.work.addWidget(self.pic_show_qwidget)

        self.workQWidget = QWidget()
        self.workQWidget.setLayout(self.work)

        self.mainQWidget.addWidget(self.workQWidget)
        # splitter 只有两栏：文件树 / 工作区，比例 left : right
        self.mainQWidget.setSizes([10000 * self.left, 10000 * self.right])

    def _build_title_bar(self):
        """自定义无边框标题栏（最小化 / 最大化 / 还原 / 关闭）。"""
        self.title_bar = CustomTitleBar(self)
        self.title_bar.windowMinimized.connect(self.showMinimized)
        self.title_bar.windowMaximized.connect(self.showMaximized)
        self.title_bar.windowRestored.connect(self._on_restored)
        self.title_bar.windowClosed.connect(self.close)

    def _build_status_bar(self):
        """状态栏：左侧状态文字 + 右侧常驻评分标签。"""
        self.statusbar = QStatusBar(self)
        self.statusbar.setObjectName("statusbar")
        self.statusLabel = QLabel()
        self.statusLabel.setText("就绪")
        self.statusbar.addPermanentWidget(self.statusLabel, stretch=1)

        # 右侧常驻显示当前媒体的评分（数字键 1~5 评分后立刻更新）
        self.ratingLabel = QLabel("评分：—")
        self.ratingLabel.setObjectName("ratingLabel")
        self.ratingLabel.setToolTip("按数字键 1~5 为当前图片 / 视频评分（按内容指纹保存，移动或改名后仍保留）")
        self.statusbar.addPermanentWidget(self.ratingLabel)

        self.tree_visible = True
        # 记录展开时的窗口比例，用于恢复
        self.tree_sizes = [10000 * self.left, 10000 * self.right]

    def _build_central_widget(self):
        """标题列 + 菜单栏 + 主区域 + 状态栏 装进中央容器。"""
        self._central_widget = QWidget()
        self._central_widget.setObjectName("centralWidget")
        self._central_widget.setStyleSheet(CENTRAL_WIDGET_STYLE)
        central_layout = QVBoxLayout(self._central_widget)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.title_bar)

        # -- 菜单栏 --
        self.menu_bar = build_menu_bar(self)
        central_layout.addWidget(self.menu_bar)

        central_layout.addWidget(self.mainQWidget, stretch=1)
        central_layout.addWidget(self.statusbar)

        self.setCentralWidget(self._central_widget)

    def _restore_last_session(self):
        """优先恢复上次「打开」的目录作为树的根；没有或失效时才走系统默认根 + 展开逻辑。"""
        open_path = ''
        if self.config_manager.exist(self.open_path_config_key):
            open_path = self.config_manager.get(self.open_path_config_key)
        if open_path and os.path.isdir(open_path):
            self._set_tree_root(open_path)
        elif self.config_manager.exist(self.expand_path_config_key):
            expand_path_config = self.config_manager.get(self.expand_path_config_key)
            self.expand_path(expand_path_config)

    def _schedule_startup_checks(self):
        """启动后的延迟自检：解码器 / ffmpeg（都放后台线程，不阻塞窗口显示）。"""
        # 启动后延迟检测解码器（避免阻塞窗口显示），未安装则引导自动 / 手动安装
        QTimer.singleShot(800, self._check_decoder)
        # 启动后延迟检测 ffmpeg.exe（开发环境缺失则自动下载）
        QTimer.singleShot(1500, self._check_ffmpeg)
