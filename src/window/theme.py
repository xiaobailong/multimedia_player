# -*- coding: utf-8 -*-
"""主窗口的全局暗色主题（QSS）。

样式表集中在这里，``MainWindow`` 只负责调用 :func:`build_global_style_sheet`。
目录树展开 / 收起箭头图标是运行时自绘的 PNG（见 :func:`ensure_tree_branch_icons`），
QSS 里用占位符替换成真实路径。
"""
import os

from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtGui import QColor, QPainter, QPen, QPixmap, QPolygon
from loguru import logger

from src.utils.utils import get_app_data_path

# 中央容器：普通模式（圆角 + 描边）与全屏模式（无边框）两套
CENTRAL_WIDGET_STYLE = """
#centralWidget {
    background-color: #1e1e2e;
    border: 1px solid #45475a;
    border-radius: 8px;
}
"""

CENTRAL_WIDGET_FULLSCREEN_STYLE = """
#centralWidget {
    background-color: #1e1e2e;
    border: none;
    border-radius: 0px;
}
"""

# 菜单栏 / 菜单项
MENU_BAR_STYLE = """
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
"""

# 主窗口全局样式（__TREE_BRANCH_CLOSED__ / __TREE_BRANCH_OPEN__ 为图标占位符）
_MAIN_WINDOW_STYLE = """
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
QPushButton:checked {
    background-color: #89b4fa;
    color: #1e1e2e;
    border-color: #89b4fa;
}
QPushButton:checked:hover {
    background-color: #b4d0fb;
}
QPushButton#video_primary_btn {
    background-color: #89b4fa;
    color: #1e1e2e;
    border: 1px solid #89b4fa;
    font-weight: bold;
}
QPushButton#video_primary_btn:hover {
    background-color: #b4d0fb;
}
QPushButton#video_primary_btn:pressed {
    background-color: #74c7ec;
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
QLabel#ratingLabel {
    color: #89b4fa;
    font-size: 13px;
    padding-right: 6px;
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
"""


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


def ensure_tree_branch_icons():
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


def build_global_style_sheet():
    """主窗口全局样式表：把目录树箭头图标的真实路径替换进占位符。"""
    branch_closed_icon, branch_open_icon = ensure_tree_branch_icons()
    return (_MAIN_WINDOW_STYLE
            .replace('__TREE_BRANCH_CLOSED__', branch_closed_icon)
            .replace('__TREE_BRANCH_OPEN__', branch_open_icon))
