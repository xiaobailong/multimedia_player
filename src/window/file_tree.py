# -*- coding: utf-8 -*-
"""左侧文件树（普通文件与密文共用同一棵树、同一套事件）。

密文（32 位 hex、无扩展名）与普通媒体文件都在这棵树里：
- 点文件 → `MediaActionsMixin.on_tree_clicked`：密文先解密到缓存再播，明文直接播；
- 右键 → `MediaActionsMixin.right_click_menu`：分组后的文件操作 / 私密操作。

私密曾经是独立的第二棵树 + 模式切换，已按 `ADR-026` 合并掉。
"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDirModel, QHeaderView, QTreeView

from src.window.file_delegate import FileDisplayDelegate


class FileTreeView(QTreeView):
    """固定第一列宽度的文件树：文件名截断 + 悬浮提示 + 常显水平滚动条。"""

    COLUMN_WIDTH = 360

    def __init__(self, model, parent=None):
        super(FileTreeView, self).__init__(parent)
        self.setModel(model)
        # 只显示 Name 列（1/2/3 分别是大小 / 类型 / 修改时间）
        self.setColumnHidden(1, True)
        self.setColumnHidden(2, True)
        self.setColumnHidden(3, True)
        # 固定第一列宽度，禁用自动拉伸，使内容可溢出触发水平滚动条
        header = self.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setVisible(False)  # 隐藏 Name 表头
        self.setColumnWidth(0, self.COLUMN_WIDTH)
        # 启用水平滚动条，始终显示；默认在最左侧（Qt 原生行为），不做 setValue 干预
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        # 自定义委托：文件名截断 + 悬浮显示
        self.setItemDelegate(FileDisplayDelegate(self))


def create_dir_model():
    """目录树模型：按修改时间倒序（与原实现一致）。"""
    model = QDirModel()
    model.sort(3, order=Qt.SortOrder.DescendingOrder)
    return model
