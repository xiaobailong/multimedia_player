# -*- coding: utf-8 -*-
"""归集弹框：按评分 / 关键字 / 路径筛选媒体文件，之后由主窗口选择保存目录并拷贝。

三种模式共用一个对话框（与主窗口同款深色无边框外壳，见 `ADR-016`）：
- rating  : 评分不低于 N 星
- keyword : 指定目录 + 文件名关键字
- path    : 指定目录（递归），可选「顺序取前 N 个 / 随机抽取 N 个」
"""
import os

from PyQt5.QtWidgets import (QComboBox, QFormLayout, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QSpinBox, QWidget)
from PyQt5.QtCore import Qt

from src.collect.collect_service import KIND_ALL, KIND_IMAGE, KIND_VIDEO
from src.layout.styled_dialogs import StyledDialog, pick_directory, show_warning


class CollectDialog(StyledDialog):
    """归集参数对话框。"""

    TITLES = {
        'rating': '按评分归集',
        'keyword': '按关键字归集',
        'path': '按路径归集',
    }

    TIPS = {
        'rating': '把评分 ≥ 所选分数的图片 / 视频拷贝到指定目录。\n'
                  '评分按内容指纹保存，文件移动或改名后仍然能识别。',
        'keyword': '在所选目录（含子目录）里查找文件名包含关键字的文件，\n'
                   '支持选择文件类型与归集数量。',
        'path': '递归扫描所选目录，把其中的图片 / 视频拷贝到指定目录；\n'
                '可选「顺序取前 N 个」或「随机抽取 N 个」。',
    }

    def __init__(self, parent=None, mode='rating', default_root=''):
        super().__init__(parent, self.TITLES.get(mode, '归集'), width=540)
        self.mode = mode

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        # 评分模式：评分下限
        self.rating_spin = None
        if mode == 'rating':
            self.rating_spin = QSpinBox()
            self.rating_spin.setRange(1, 5)
            self.rating_spin.setValue(3)
            self.rating_spin.setSuffix(' 星')
            self.rating_spin.setMaximumWidth(140)
            form.addRow('评分不低于:', self.rating_spin)

        # 关键字 / 路径模式：搜索目录
        self.dir_edit = None
        self.browse_btn = None
        if mode in ('keyword', 'path'):
            self.dir_edit = QLineEdit(default_root or '')
            self.dir_edit.setPlaceholderText('选择要扫描的目录')
            self.dir_edit.setCursorPosition(0)   # 路径较长时显示开头（见 PIT-013）
            self.browse_btn = QPushButton('浏览...')
            self.browse_btn.setFixedHeight(30)
            self.browse_btn.clicked.connect(self._browse_root)
            dir_row = QWidget()
            dir_layout = QHBoxLayout(dir_row)
            dir_layout.setContentsMargins(0, 0, 0, 0)
            dir_layout.setSpacing(8)
            dir_layout.addWidget(self.dir_edit, 1)
            dir_layout.addWidget(self.browse_btn)
            form.addRow('搜索目录:', dir_row)

        # 关键字模式：关键字输入
        self.keyword_edit = None
        if mode == 'keyword':
            self.keyword_edit = QLineEdit()
            self.keyword_edit.setPlaceholderText('文件名包含的关键字（不区分大小写）')
            form.addRow('关键字:', self.keyword_edit)

        # 通用：文件类型
        self.kind_combo = QComboBox()
        self.kind_combo.addItem('图片 + 视频', KIND_ALL)
        self.kind_combo.addItem('仅图片', KIND_IMAGE)
        self.kind_combo.addItem('仅视频', KIND_VIDEO)
        self.kind_combo.setMaximumWidth(160)
        form.addRow('文件类型:', self.kind_combo)

        # 通用：归集数量（0 = 不限制）
        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(0, 99999)
        self.limit_spin.setValue(0)
        self.limit_spin.setSpecialValueText('不限')
        self.limit_spin.setSuffix(' 个')
        self.limit_spin.setMaximumWidth(160)
        form.addRow('归集数量:', self.limit_spin)

        # 路径模式：顺序 / 随机
        self.order_combo = None
        if mode == 'path':
            self.order_combo = QComboBox()
            self.order_combo.addItem('顺序（扫描到的前 N 个）', 'sequence')
            self.order_combo.addItem('随机抽取 N 个', 'random')
            self.order_combo.setMaximumWidth(220)
            form.addRow('选择方式:', self.order_combo)
            # 数量为「不限」时顺序 / 随机没有意义，置灰提示
            self.limit_spin.valueChanged.connect(self._sync_order_enabled)
            self._sync_order_enabled()

        self._body_layout.addLayout(form)

        tip = QLabel(self.TIPS.get(mode, ''))
        tip.setObjectName('dialogText')
        tip.setWordWrap(True)
        self._body_layout.addWidget(tip)

        self._body_layout.addLayout(self.make_button_row('开始归集', '取消'))

    # ------------------------------------------------------------------
    def _sync_order_enabled(self):
        """路径模式下：数量为「不限」时顺序 / 随机选项没有意义，置灰。"""
        if self.order_combo is not None:
            self.order_combo.setEnabled(self.limit_spin.value() > 0)

    def _browse_root(self):
        start = self.dir_edit.text().strip() if self.dir_edit is not None else ''
        selected = pick_directory(self, '选择要扫描的目录', start if os.path.isdir(start) else '')
        if selected:
            self.dir_edit.setText(selected)
            self.dir_edit.setCursorPosition(0)

    def accept(self):
        """确定前做基础校验（目录存在、关键字非空）。"""
        if self.mode in ('keyword', 'path'):
            root = self.dir_edit.text().strip() if self.dir_edit is not None else ''
            if not root or not os.path.isdir(root):
                show_warning(self, '归集', '请选择一个存在的搜索目录。')
                return
        if self.mode == 'keyword':
            keyword = self.keyword_edit.text().strip() if self.keyword_edit is not None else ''
            if not keyword:
                show_warning(self, '归集', '请输入要匹配的文件名关键字。')
                return
        super().accept()

    def params(self):
        """把界面上的选择整理成归集线程需要的参数字典。"""
        result = {
            'mode': self.mode,
            'kind': self.kind_combo.currentData(),
            'limit': int(self.limit_spin.value()),
        }
        if self.mode == 'rating':
            result['min_rating'] = int(self.rating_spin.value())
        else:
            result['root'] = self.dir_edit.text().strip()
        if self.mode == 'keyword':
            result['keyword'] = self.keyword_edit.text().strip()
        if self.mode == 'path':
            result['order'] = self.order_combo.currentData()
        return result
