import sys
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *


class FloatingControlPanel(QWidget):
    """全屏模式下悬浮显示的视频控制面板，支持拖拽调整位置"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        # 拖拽相关
        self._dragging = False
        self._drag_pos = QPoint()
        self._mouse_press_pos = QPoint()

        # 自动隐藏定时器
        self._auto_hide_timer = QTimer(self)
        self._auto_hide_timer.setInterval(3000)  # 3秒无操作自动隐藏
        self._auto_hide_timer.timeout.connect(self._auto_hide)
        self._is_visible = True

        # 主布局
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.setSpacing(0)

        # 半透明背景面板
        self._container = QWidget()
        self._container.setObjectName("floatingContainer")
        self._container.setStyleSheet("""
            #floatingContainer {
                background-color: rgba(24, 24, 37, 220);
                border-radius: 10px;
                border: 1px solid rgba(137, 180, 250, 60);
            }
        """)
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(4, 2, 4, 4)
        self._container_layout.setSpacing(2)

        # 顶部：隐藏按钮
        self._top_bar = QHBoxLayout()
        self._top_bar.setContentsMargins(0, 0, 0, 0)
        self._top_bar.addStretch()

        self._hide_btn = QPushButton("✕")
        self._hide_btn.setFixedSize(20, 20)
        self._hide_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 30);
                color: rgba(255, 255, 255, 180);
                border: none;
                border-radius: 10px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(255, 80, 80, 150);
                color: white;
            }
        """)
        self._hide_btn.clicked.connect(self.hide_panel)
        self._top_bar.addWidget(self._hide_btn)

        self._container_layout.addLayout(self._top_bar)

        self._main_layout.addWidget(self._container)

        # 等待被添加的控件槽位
        self._control_widgets = []

        self.setMouseTracking(True)
        self._container.setMouseTracking(True)

    def addControlWidget(self, widget):
        """添加控制控件到面板"""
        self._container_layout.addWidget(widget)
        self._control_widgets.append(widget)

    def clearControlWidgets(self):
        """清空所有控制控件（不销毁）"""
        for w in self._control_widgets[:]:
            self._container_layout.removeWidget(w)
            self._control_widgets.remove(w)

    def showEvent(self, event):
        super().showEvent(event)
        # 显示后启动自动隐藏定时器
        self._is_visible = True
        self._auto_hide_timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._auto_hide_timer.stop()

    def _auto_hide(self):
        """自动隐藏面板"""
        if self._is_visible and not self._dragging:
            self._is_visible = False
            self._fade_to(0)

    def _fade_to(self, opacity):
        """渐变透明度"""
        anim = QPropertyAnimation(self, b"windowOpacity")
        anim.setDuration(300)
        anim.setStartValue(self.windowOpacity())
        anim.setEndValue(opacity)
        anim.start()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._mouse_press_pos = event.globalPos()
            self._drag_pos = self.pos()
            # 拖拽时取消自动隐藏
            self._auto_hide_timer.stop()
            # 拖拽时完全不透明
            if self.windowOpacity() < 1.0:
                self._fade_to(1.0)
            event.accept()

    def mouseMoveEvent(self, event):
        if self._dragging and event.buttons() == Qt.MouseButton.LeftButton:
            delta = event.globalPos() - self._mouse_press_pos
            new_pos = self._drag_pos + delta
            # 限制在父窗口范围内
            if self.parent():
                parent_rect = self.parent().geometry()
                # 留出边距，确保不超出屏幕
                new_x = max(0, min(new_pos.x(), parent_rect.width() - self.width()))
                new_y = max(0, min(new_pos.y(), parent_rect.height() - self.height()))
                self.move(new_x, new_y)
            else:
                self.move(new_pos)
            event.accept()
        else:
            # 鼠标悬浮时显示面板
            if not self._is_visible:
                self._is_visible = True
                self._fade_to(1.0)
            self._auto_hide_timer.start()
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            # 拖拽结束后重新启动自动隐藏
            self._auto_hide_timer.start()
            event.accept()

    def enterEvent(self, event):
        # 鼠标进入面板区域，取消自动隐藏
        self._auto_hide_timer.stop()
        if not self._is_visible:
            self._is_visible = True
            self._fade_to(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        # 鼠标离开面板区域，重新启动自动隐藏
        self._auto_hide_timer.start()
        super().leaveEvent(event)

    def keyPressEvent(self, event):
        """捕获键盘事件，将 Esc 转发给 MainWindow 退出全屏"""
        if event.key() == Qt.Key.Key_Escape:
            # 不让事件继续传播，直接转发给父窗口（MainWindow）
            if self.parent():
                self.parent().keyPressEvent(event)
            return
        super().keyPressEvent(event)

    def hide_panel(self):
        """手动隐藏面板（通过点击✕按钮）"""
        self._is_visible = False
        self._auto_hide_timer.stop()
        self.hide()

    def show_panel(self):
        """手动显示面板"""
        self._is_visible = True
        self.setWindowOpacity(1.0)
        self.show()
        self._auto_hide_timer.start()

    def resizeToFitContent(self):
        """根据内容调整面板大小"""
        self.adjustSize()
        # 限制最大宽度为父窗口宽度
        if self.parent():
            max_width = self.parent().width() - 20
            if self.width() > max_width:
                self.setFixedWidth(max_width)
                self.adjustSize()

    def repositionDefault(self):
        """将面板定位到底部居中"""
        if self.parent():
            parent_rect = self.parent().geometry()
            new_x = (parent_rect.width() - self.width()) // 2
            new_y = parent_rect.height() - self.height() - 20
            self.move(max(0, new_x), max(0, new_y))