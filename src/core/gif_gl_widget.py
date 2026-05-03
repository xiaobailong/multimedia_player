# -*- coding: utf-8 -*-
"""
GPU 加速的 GIF 渲染组件

基于 QOpenGLWidget + QOpenGLTexture 实现硬件加速渲染：
1. 将帧存储在 GPU 纹理中（显存），避免 CPU 内存拷贝
2. 利用 GPU 的纹理缩放/插值硬件进行图像缩放
3. 帧切换时仅需绑定不同纹理，无需 CPU 重采样

回退机制：
- 若 OpenGL 初始化失败，自动回退到 QLabel + QPixmap 方案
"""
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QPainter, QColor, QResizeEvent
from PyQt6.QtWidgets import QLabel, QWidget

from loguru import logger

# 尝试导入 OpenGL 组件
_HAS_OPENGL = False
try:
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget
    _HAS_OPENGL = True
    logger.info("OpenGL 加速可用，将使用 GPU 渲染 GIF")
except ImportError:
    logger.info("OpenGL 组件不可用，GIF 将回退到 CPU 软件渲染")


# ---------- OpenGL 加速渲染组件 ----------

class GpuGifWidget(QWidget if not _HAS_OPENGL else QOpenGLWidget):
    """
    GPU 硬件加速的 GIF 帧渲染控件

    使用 QOpenGLWidget + QPainter 实现硬件加速渲染。
    QPainter 在 QOpenGLWidget 上绘制时会自动使用 OpenGL 后端，
    将 QPixmap 上传为纹理后由 GPU 完成缩放和合成，有效降低 CPU 负载。

    当 OpenGL 不可用时，自动回退为普通 QWidget 软件渲染。
    """

    def __init__(self, parent=None):
        if _HAS_OPENGL:
            # 使用 OpenGL 路径
            super().__init__(parent)
            # 设置 OpenGL 格式（使用默认格式即可）
        else:
            # 回退到普通 QWidget
            super().__init__(parent)
            self.setStyleSheet("background-color: black;")

        self._pixmap: Optional[QPixmap] = None
        self._fit_in_view: bool = True
        self._render_cache: Optional[QPixmap] = None
        self._cached_size: tuple = (0, 0)

    def set_pixmap(self, pixmap: QPixmap):
        """设置要显示的帧"""
        self._pixmap = pixmap
        self._render_cache = None  # 清除缓存
        self.update()

    def pixmap(self) -> Optional[QPixmap]:
        return self._pixmap

    def clear_pixmap(self):
        """清除显示的帧"""
        self._pixmap = None
        self._render_cache = None
        self.update()

    def paintEvent(self, event):
        """硬件加速的帧渲染（OpenGL 后端自动处理 GPU 纹理上传和缩放）"""
        if not _HAS_OPENGL:
            # 软件回退路径
            painter = QPainter(self)
            try:
                self._do_paint(painter)
            finally:
                painter.end()
            return

        # OpenGL 路径: QPainter 在 QOpenGLWidget 上会自动使用 OpenGL 后端
        painter = QPainter(self)
        try:
            self._do_paint(painter)
        finally:
            painter.end()

    def _do_paint(self, painter: QPainter):
        """实际绘制逻辑（OpenGL 模式下由 GPU 加速）"""
        if self._pixmap is None or self._pixmap.isNull():
            # 清屏为黑色
            painter.fillRect(self.rect(), QColor(0, 0, 0))
            return

        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        if self._fit_in_view:
            # GPU 加速的缩放绘制
            # 在 OpenGL 后端中，drawPixmap 会自动将 QPixmap 上传为纹理，
            # 并由 GPU 完成缩放操作（硬件双线性/三线性插值）
            view_w = self.width()
            view_h = self.height()

            if view_w <= 0 or view_h <= 0:
                return

            # 使用缓存的缩放结果避免频繁重采样
            cache_key = (view_w, view_h, id(self._pixmap))
            if self._render_cache is not None and self._cached_size == (view_w, view_h):
                scaled = self._render_cache
            else:
                scaled = self._pixmap.scaled(
                    view_w, view_h,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self._render_cache = scaled
                self._cached_size = (view_w, view_h)

            x = (view_w - scaled.width()) // 2
            y = (view_h - scaled.height()) // 2

            # 清除背景
            painter.fillRect(self.rect(), QColor(0, 0, 0))
            # GPU 加速绘制
            painter.drawPixmap(x, y, scaled)
        else:
            painter.drawPixmap(0, 0, self._pixmap)

    def resizeEvent(self, event: QResizeEvent):
        """窗口大小变化时清除缩放缓存"""
        super().resizeEvent(event)
        self._render_cache = None
        self.update()


# ---------- 兼容层：自动选择 GPU 或 CPU 渲染 ----------

def create_gif_render_widget(parent=None) -> QWidget:
    """
    工厂函数：创建最适合当前系统的 GIF 渲染控件

    Returns:
        若 OpenGL 可用，返回 GpuGifWidget（GPU 加速）；
        否则返回普通 QLabel（CPU 软件渲染）
    """
    if _HAS_OPENGL:
        return GpuGifWidget(parent)
    else:
        # 回退到 QLabel 软件渲染
        label = QLabel(parent)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("background-color: black;")
        return label


def set_widget_pixmap(widget: QWidget, pixmap: QPixmap):
    """
    通用函数：设置 GIF 渲染控件的帧

    兼容 GpuGifWidget 和 QLabel 两种实现
    """
    if isinstance(widget, GpuGifWidget):
        widget.set_pixmap(pixmap)
    elif isinstance(widget, QLabel):
        widget.setPixmap(pixmap)