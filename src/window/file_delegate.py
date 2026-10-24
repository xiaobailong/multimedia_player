# -*- coding: utf-8 -*-
"""目录树的文件名显示委托。

QDirModel 的第 0 列是文件名：超长名字截断显示，悬浮时再给出完整文件名与大小；
被标记为「私密库」的目录额外加 ``[私密库]`` 后缀并用高亮色绘制（`ADR-027`）。
"""
import os

from PyQt5.QtCore import QEvent, QSize
from PyQt5.QtGui import QColor, QFontMetrics, QPalette
from PyQt5.QtWidgets import (QApplication, QStyle, QStyleOptionViewItem,
                             QStyledItemDelegate, QToolTip)

PRIVATE_MARK_SUFFIX = '  [私密库]'
PRIVATE_MARK_COLOR = QColor('#f9e2af')


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
        if self._is_private_root(index.model().filePath(index)):
            text_width += font_metrics.horizontalAdvance(PRIVATE_MARK_SUFFIX)
        return QSize(text_width, super().sizeHint(option, index).height())

    def _is_private_root(self, path):
        """这一行是否是被标记为「私密库」的目录（判断逻辑放在窗口 mixin 里）。"""
        if not path:
            return False
        view = self.parent()
        window = view.window() if view is not None else None
        checker = getattr(window, 'is_private_library_root', None)
        if checker is None:
            return False
        try:
            return bool(checker(path))
        except Exception:
            return False

    def paint(self, painter, option, index):
        """私密库目录：文件名后追加 [私密库] 并用高亮色，其余行走默认绘制。"""
        model = index.model()
        path = model.filePath(index) if model is not None else ''
        if not self._is_private_root(path):
            super().paint(painter, option, index)
            return

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = (opt.text or model.fileName(index)) + PRIVATE_MARK_SUFFIX
        opt.palette.setColor(QPalette.Text, PRIVATE_MARK_COLOR)
        opt.palette.setColor(QPalette.HighlightedText, PRIVATE_MARK_COLOR)
        style = opt.widget.style() if opt.widget is not None else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)

    def helpEvent(self, event, view, option, index):
        if event.type() == QEvent.ToolTip and index.model() is not None:
            file_path = index.model().filePath(index)
            file_name = index.model().fileName(index)
            if os.path.isfile(file_path):
                size_bytes = os.path.getsize(file_path)
                size_str = self._format_size(size_bytes)
                QToolTip.showText(event.globalPos(), f"{file_name}\n大小: {size_str}")
            elif self._is_private_root(file_path):
                QToolTip.showText(event.globalPos(),
                                  f"{file_name}\n私密库：本目录下都是加密文件，"
                                  f"点密文即可解密播放")
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
