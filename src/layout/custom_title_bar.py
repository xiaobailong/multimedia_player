from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from loguru import logger


class CustomTitleBar(QWidget):
    """无边框窗口的自定义标题栏"""
    windowMinimized = pyqtSignal()
    windowMaximized = pyqtSignal()
    windowRestored = pyqtSignal()
    windowClosed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(34)
        self.setObjectName("customTitleBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 0, 0)
        layout.setSpacing(4)

        self._icon_label = QLabel("\U0001f3ac")
        self._icon_label.setFixedSize(20, 20)
        self._icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._icon_label)

        self._title_label = QLabel("多媒体播放器")
        self._title_label.setStyleSheet("color: #cdd6f4; font-size: 13px; font-weight: bold;")
        layout.addWidget(self._title_label)

        # 播放进度标签（放在标题后面，stretch 前面）
        self._progress_label = QLabel("")
        self._progress_label.setStyleSheet("color: #a6adc8; font-size: 12px;")
        layout.addWidget(self._progress_label)

        layout.addStretch()

        self._min_btn = self._create_btn("\u2500")
        self._min_btn.clicked.connect(self.windowMinimized.emit)
        layout.addWidget(self._min_btn)

        self._max_btn = self._create_btn("\u25a1")
        self._max_btn.clicked.connect(self._on_max_clicked)
        layout.addWidget(self._max_btn)

        self._close_btn = self._create_btn("\u2715")
        self._close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #f38ba8;
                border: none;
                border-radius: 4px;
                padding: 4px 12px;
                font-size: 14px;
                font-weight: bold;
                min-height: 22px;
            }
            QPushButton:hover {
                background-color: #f38ba8;
                color: #1e1e2e;
            }
        """)
        self._close_btn.clicked.connect(self.windowClosed.emit)
        layout.addWidget(self._close_btn)

        self.setStyleSheet("""
            CustomTitleBar {
                background-color: #181825;
                border-bottom: 1px solid #313244;
            }
        """)
        # 确保按钮接受鼠标事件
        self.setAttribute(Qt.WA_StyledBackground, True)

    def _create_btn(self, text):
        btn = QPushButton(text)
        btn.setFixedSize(36, 26)
        btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #cdd6f4;
                border: none;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 14px;
                min-height: 22px;
            }
            QPushButton:hover {
                background-color: #45475a;
            }
        """)
        return btn

    def _on_max_clicked(self):
        window = self.window()
        if window.isMaximized():
            window.showNormal()
            self._max_btn.setText("\u25a1")
        else:
            window.showMaximized()
            self._max_btn.setText("\u2740")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            child = self.childAt(event.pos())
            if child is not None and child is not self:
                logger.debug(f"[TitleBar] click on child: {child}")
                super().mousePressEvent(event)
                return
            logger.debug("[TitleBar] mousePressEvent on blank area -> startSystemMove")
            # 使用 Qt 5.15+ 原生系统拖拽 API，Windows 自己处理移动
            window_handle = self.window().windowHandle()
            if window_handle:
                window_handle.startSystemMove()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            child = self.childAt(event.pos())
            if child is not None and child is not self:
                super().mouseDoubleClickEvent(event)
                return
            logger.debug("[TitleBar] double click blank area -> maximize/restore")
            self._on_max_clicked()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def setInfo(self, filename, progress=""):
        """设置标题栏显示信息
        :param filename: 当前播放的文件名（绝对路径或简短名称）
        :param progress: 进度文字，如 "(3/10)"
        """
        self._title_label.setText(filename)
        self._progress_label.setText(progress)

    def updateMaximizeIcon(self):
        if self.window().isMaximized():
            self._max_btn.setText("\u2740")
        else:
            self._max_btn.setText("\u25a1")
