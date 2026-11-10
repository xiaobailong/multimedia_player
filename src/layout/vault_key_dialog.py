# -*- coding: utf-8 -*-
"""密钥与目录管理：密钥环（多把 KEK）+ 目录密钥绑定。

为什么需要这个界面：

- privi「保险库数据」导出的是**密钥环**（可能有多把 KEK，每把带标签 / 指纹），
  导入后这些密钥会共存，不能像以前那样"最后导入的那把赢"；
- 本程序允许**不同私密库目录使用不同密钥**（`vault_dir_key` 表，最长前缀匹配），
  于是"旧保险库用旧密钥、新保险库用新密钥"可以并存，互不破坏。

界面只做三件事：把某把设为默认、把某把绑定到某目录、解除绑定。
不提供"删除密钥"：密钥一旦删掉，对应文件就再也解不开（风险太大）。
"""
import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                             QPushButton)

from src.layout.styled_dialogs import (StyledDialog, ask_yes_no, pick_directory,
                                       show_info, show_warning)


class VaultKeyDialog(StyledDialog):
    """密钥环 / 目录密钥绑定管理框。"""

    def __init__(self, parent=None, private_service=None, start_dir=''):
        super().__init__(parent, '密钥与目录管理', width=680)
        self.private_service = private_service
        self.start_dir = start_dir or ''

        tip = QLabel(
            '密钥环里可以有多把密钥：没有绑定目录的文件用「默认密钥」加密，\n'
            '绑定了密钥的目录（含子目录）用各自绑定的密钥加密；\n'
            '解密时按记录里的密钥 id 自动选密钥（找不到就逐把试）。')
        tip.setObjectName('dialogText')
        tip.setWordWrap(True)
        self._body_layout.addWidget(tip)

        key_title = QLabel('密钥环')
        key_title.setObjectName('dialogText')
        self._body_layout.addWidget(key_title)

        self.key_list = QListWidget()
        self.key_list.setMinimumHeight(130)
        self._body_layout.addWidget(self.key_list)

        key_buttons = QHBoxLayout()
        key_buttons.setContentsMargins(0, 0, 0, 0)
        key_buttons.setSpacing(8)
        self.default_btn = QPushButton('设为默认密钥')
        self.default_btn.setFixedHeight(30)
        self.default_btn.clicked.connect(self._set_default)
        key_buttons.addWidget(self.default_btn)
        self.bind_btn = QPushButton('为目录绑定该密钥...')
        self.bind_btn.setFixedHeight(30)
        self.bind_btn.clicked.connect(self._bind_directory)
        key_buttons.addWidget(self.bind_btn)
        key_buttons.addStretch(1)
        refresh_btn = QPushButton('刷新')
        refresh_btn.setFixedHeight(30)
        refresh_btn.clicked.connect(self._reload)
        key_buttons.addWidget(refresh_btn)
        self._body_layout.addLayout(key_buttons)

        bind_title = QLabel('目录密钥绑定')
        bind_title.setObjectName('dialogText')
        self._body_layout.addWidget(bind_title)

        self.binding_list = QListWidget()
        self.binding_list.setMinimumHeight(110)
        self._body_layout.addWidget(self.binding_list)

        bind_buttons = QHBoxLayout()
        bind_buttons.setContentsMargins(0, 0, 0, 0)
        bind_buttons.setSpacing(8)
        unbind_btn = QPushButton('解除所选绑定')
        unbind_btn.setFixedHeight(30)
        unbind_btn.clicked.connect(self._unbind)
        bind_buttons.addWidget(unbind_btn)
        bind_buttons.addStretch(1)
        self._body_layout.addLayout(bind_buttons)

        self._body_layout.addLayout(self.make_button_row('关闭', ''))
        self._reload()

    # ------------------------------------------------------------------

    def _reload(self):
        """重新读密钥环与目录绑定（所有操作后都调一次，界面立刻反映结果）。"""
        try:
            keys = self.private_service.list_keys()
            bindings = self.private_service.list_directory_bindings()
            default_id = self.private_service.default_key_id()
        except Exception as e:
            show_warning(self, '密钥与目录管理', '读取密钥库失败：\n%s' % e)
            return

        self.key_list.clear()
        for key in keys:
            label = key.get('label') or '未命名密钥'
            mark = '★ ' if key['id'] == default_id else '   '
            text = '%s%s    %s…    %s' % (
                mark, label, key['id'][2:10], key.get('created_at') or '')
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, key['id'])
            self.key_list.addItem(item)
        if self.key_list.count():
            self.key_list.setCurrentRow(0)

        self.binding_list.clear()
        for binding in bindings:
            if binding.get('missing_key'):
                label = '（密钥已丢失）'
            else:
                label = binding.get('label') or '未命名密钥'
            text = '%s    →    %s（%s…）' % (
                binding['path'], label, binding['key_id'][2:10])
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, binding['path'])
            self.binding_list.addItem(item)

    def _selected_key_id(self):
        item = self.key_list.currentItem()
        return item.data(Qt.UserRole) if item is not None else None

    def _set_default(self):
        key_id = self._selected_key_id()
        if not key_id:
            show_warning(self, '密钥与目录管理', '请先在上面选中一把密钥。')
            return
        try:
            self.private_service.set_default_key(key_id)
        except Exception as e:
            show_warning(self, '密钥与目录管理', '设置默认密钥失败：\n%s' % e)
            return
        self._reload()
        show_info(self, '密钥与目录管理',
                  '默认密钥已切换为：\n%s\n\n'
                  '之后没有绑定目录的文件都用它加密（已加密的文件不受影响）。'
                  % self.private_service.key_label(key_id))

    def _bind_directory(self):
        key_id = self._selected_key_id()
        if not key_id:
            show_warning(self, '密钥与目录管理', '请先在上面选中一把要绑定的密钥。')
            return
        start = self.start_dir if os.path.isdir(self.start_dir) else ''
        directory = pick_directory(self, '选择要绑定该密钥的目录', start_dir=start)
        if not directory or not os.path.isdir(directory):
            return
        try:
            self.private_service.bind_directory_key(directory, key_id)
        except Exception as e:
            show_warning(self, '密钥与目录管理', '绑定失败：\n%s' % e)
            return
        self.start_dir = directory
        self._reload()
        show_info(self, '密钥与目录管理',
                  '已把目录绑定到：\n%s\n\n目录：%s\n\n'
                  '该目录及其子目录里的文件在加密时使用这把密钥'
                  '（更具体的子目录可以再单独绑定成别的密钥）。'
                  % (self.private_service.key_label(key_id), directory))

    def _unbind(self):
        item = self.binding_list.currentItem()
        if item is None:
            show_warning(self, '密钥与目录管理', '请先在下面选中一条目录绑定。')
            return
        path = item.data(Qt.UserRole)
        if not ask_yes_no(
                self, '解除绑定',
                '解除下面这个目录的密钥绑定？\n%s\n\n'
                '只删除绑定关系，不会删除密钥，也不会改动任何文件。' % path,
                default_yes=False):
            return
        try:
            self.private_service.unbind_directory_key(path)
        except Exception as e:
            show_warning(self, '密钥与目录管理', '解除绑定失败：\n%s' % e)
            return
        self._reload()
