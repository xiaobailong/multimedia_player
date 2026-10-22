# -*- coding: utf-8 -*-
"""可复用的方形关闭按钮（自绘 ✕）。

视频全屏悬浮控制面板（``FloatingControlPanel``）与图片播放控制面板（``PicShowLayout``）
共用同一个视觉样式：常态淡粉方框 + 粉红 ✕，hover 粉底反色。
"""
from PyQt5.QtWidgets import QPushButton, QSizePolicy
from PyQt5.QtCore import Qt, QRectF, QPointF
from PyQt5.QtGui import QPainter, QColor, QPen


class SquareCloseButton(QPushButton):
    """用 QPainter 画的方形关闭按钮（粉红 ✕，hover 粉底反色），与标题栏关闭按钮风格一致

    .. note::
       全局 / 父级 QSS 给 `QPushButton` 设的 ``min-height`` + ``padding`` 会把控件最小高度
       抬到 32px，``setFixedSize`` 的正方形会被拉成竖条（见 ISSUE-009）。所以这里先用控件
       自身样式表把度量清零，再固定尺寸。

    :param parent: 父控件
    :param size: 正方形边长（px），默认 18；图片控制面板用 24 与其它按钮齐平
    :param tooltip: 悬浮提示文案
    """

    CLOSE_COLOR = "#f38ba8"
    HOVER_TEXT_COLOR = "#1e1e2e"

    DEFAULT_SIZE = 18        # 默认正方形边长（px）
    RADIUS = 4               # 圆角半径基准，18px 时正好 4px

    def __init__(self, parent=None, size=DEFAULT_SIZE, tooltip="关闭"):
        super().__init__(parent)
        # 必须排在 setFixedSize 之前：清掉全局 / 父级 QSS 撑出来的最小高度与内边距
        self.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                padding: 0px;
                margin: 0px;
                min-width: 0px;
                min-height: 0px;
            }
        """)
        self.setFixedSize(size, size)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        # 鼠标专用控件：不参与键盘焦点（避免点过关闭按钮后方向键失效）
        self.setFocusPolicy(Qt.NoFocus)
        self.setToolTip(tooltip)
        self._hover = False

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # 内缩半个像素，避免抗锯齿的边缘被控件边界裁掉
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        side = min(self.width(), self.height())
        radius = max(3.0, side * 0.22)
        if self._hover:
            p.setBrush(QColor(self.CLOSE_COLOR))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(rect, radius, radius)
            x_color = QColor(self.HOVER_TEXT_COLOR)
            pen_width = max(1.5, side / 11.0)
        else:
            # 常态也给一个极淡的方形底 + 描边，让人一眼看出这是"方形按钮"而不是漂浮的叉
            p.setBrush(QColor(243, 139, 168, 26))
            p.setPen(QPen(QColor(243, 139, 168, 110), 1))
            p.drawRoundedRect(rect, radius, radius)
            x_color = QColor(self.CLOSE_COLOR)
            pen_width = max(1.4, side / 12.0)
        p.setPen(QPen(x_color, pen_width, Qt.SolidLine, Qt.RoundCap))
        m = side * 0.3
        p.drawLine(QPointF(rect.left() + m, rect.top() + m),
                   QPointF(rect.right() - m, rect.bottom() - m))
        p.drawLine(QPointF(rect.right() - m, rect.top() + m),
                   QPointF(rect.left() + m, rect.bottom() - m))
        p.end()
