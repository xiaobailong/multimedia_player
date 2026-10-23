# -*- coding: utf-8 -*-
"""目录树的文件名显示委托。

QDirModel 的第 0 列是文件名：超长名字截断显示，悬浮时再给出完整文件名与大小。
"""
import os

from PyQt5.QtCore import QEvent, QSize
from PyQt5.QtGui import QFontMetrics
from PyQt5.QtWidgets import QStyledItemDelegate, QToolTip


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
