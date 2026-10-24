# -*- coding: utf-8 -*-
"""普通模式左侧文件树的媒体操作。

包含：目录展开 / 右键菜单 / 打开目录 / 复制 / 移动 / 删除 / 载入播放列表 /
点击树节点播放。全部方法原样来自 ``Player.py``，只做位置搬运。
"""
import os
import shutil

import send2trash
from PyQt5.QtCore import QModelIndex, Qt
from PyQt5.QtWidgets import QAbstractItemView, QMenu
from loguru import logger

from src.layout.styled_dialogs import pick_directory
from src.layout.video_show_layout import VideoShowLayout


class MediaActionsMixin:
    """文件树 → 播放 / 文件操作。"""


    def expand_path(self, path):
        original_path = path  # 保存原始目标路径，用于后续滚动定位
        self.treeView.setExpanded(self.model.index(path), True)
        while True:
            if path != os.path.dirname(path):
                path = os.path.dirname(path)
                self.treeView.setExpanded(self.model.index(path), True)
            else:
                break
        # 展开完成后将原始目标目录滚动到树形控件中间位置
        target_index = self.model.index(original_path)
        self.treeView.scrollTo(target_index, QAbstractItemView.PositionAtCenter)

    def right_click_menu(self, pos):
        try:
            f = self.treeView.currentIndex()
            gp = QModelIndex(f)
            self.path_right_click = self.model.filePath(gp)

            self.treeView.contextMenu = QMenu()

            self.treeView.contextMenu.action_copy = self.treeView.contextMenu.addAction(u'复制到')
            self.treeView.contextMenu.action_copy.triggered.connect(self.copy)

            self.treeView.contextMenu.action_move = self.treeView.contextMenu.addAction(u'移动')
            self.treeView.contextMenu.action_move.triggered.connect(self.move)

            self.treeView.contextMenu.action_refresh = self.treeView.contextMenu.addAction(u'刷新')
            self.treeView.contextMenu.action_refresh.triggered.connect(self.refresh)

            self.treeView.contextMenu.action_delete = self.treeView.contextMenu.addAction(u'删除')
            self.treeView.contextMenu.action_delete.triggered.connect(self.delete)

            self.treeView.contextMenu.load_for_slideshow = self.treeView.contextMenu.addAction(u'加载为幻灯片列表')
            self.treeView.contextMenu.load_for_slideshow.triggered.connect(self.load_for_pic_show)

            self.treeView.contextMenu.load_for_slideshow = self.treeView.contextMenu.addAction(u'加载为视频列表')
            self.treeView.contextMenu.load_for_slideshow.triggered.connect(self.load_for_video_lise)

            self.treeView.contextMenu.load_for_slideshow = self.treeView.contextMenu.addAction(u'设置为截图路径')
            self.treeView.contextMenu.load_for_slideshow.triggered.connect(self.load_for_video_screenshot)

            self.treeView.contextMenu.load_for_slideshow = self.treeView.contextMenu.addAction(u'设置为剪切路径')
            self.treeView.contextMenu.load_for_slideshow.triggered.connect(self.load_for_video_cut)

            self.treeView.contextMenu.load_for_slideshow = self.treeView.contextMenu.addAction(u'设置默认展开')
            self.treeView.contextMenu.load_for_slideshow.triggered.connect(self.set_expand_path)

            self.treeView.contextMenu.exec_(self.mapToGlobal(pos))
        except Exception as e:
            self.notice(e)

    def set_expand_path(self, path):
        if os.path.isdir(self.path_right_click):
            self.config_manager.add_or_update(self.expand_path_config_key,self.path_right_click)

    def open_directory(self):
        """文件菜单 → 打开：选择目录并作为左侧树的根，同时记住该路径供下次启动恢复。"""
        start_dir = ''
        if self.config_manager.exist(self.open_path_config_key):
            start_dir = self.config_manager.get(self.open_path_config_key)
            if not os.path.isdir(start_dir):
                start_dir = ''
        selected_path = pick_directory(self, "选择文件夹", start_dir=start_dir)
        if not selected_path or not os.path.isdir(selected_path):
            return
        self.config_manager.add_or_update(self.open_path_config_key, selected_path)
        self._set_tree_root(selected_path)

    def _set_tree_root(self, path):
        """将普通模式左侧树的根设置为指定目录，并展开该根节点。"""
        self.model.refresh()
        root_index = self.model.index(path)
        self.treeView.setRootIndex(root_index)
        self.treeView.setExpanded(root_index, True)
        self.path = path

    def copy(self):
        selected_path = pick_directory(self, "选择复制目标文件夹")  # 返回选中的文件夹路径
        if os.path.isdir(selected_path):
            (path, filename) = os.path.split(self.path_right_click)
            dst = os.path.join(selected_path, filename)
            logger.info('src:', self.path_right_click)
            logger.info('dst:', dst)
            shutil.copy(self.path_right_click, dst)
        self.model.refresh()

    def move(self):
        try:
            selected_path = pick_directory(self, "选择移动目标文件夹")  # 返回选中的文件夹路径
            if os.path.isdir(selected_path):
                (path, filename) = os.path.split(self.path_right_click)
                dst = os.path.join(selected_path, filename)
                shutil.move(self.path_right_click, dst)
            self.model.refresh()
        except Exception as e:
            self.notice("文件移动异常!!!" + str(e))

    def refresh(self):
        self.model.refresh()

    def load_for_video_screenshot(self):
        if os.path.isfile(self.path_right_click):
            return

        self.config_manager.add_or_update(VideoShowLayout.video_screenshot_path_key, self.path_right_click)

    def load_for_video_cut(self):
        if os.path.isfile(self.path_right_click):
            return

        self.config_manager.add_or_update(VideoShowLayout.video_cut_path_key, self.path_right_click)

    def load_for_video_lise(self):
        if os.path.isfile(self.path_right_click):
            return

        self.config_manager.add_or_update(VideoShowLayout.video_show_list_key, self.path_right_click)
        self.video_show_layout.loadData(self.path_right_click)
        self.change_show(self.show_type_video)

    def load_for_pic_show(self):
        if os.path.isfile(self.path_right_click):
            return

        self.change_show(self.show_type_pic)
        self.inputAndExeLayout.set_content_path(self.path_right_click)

    def delete(self):
        try:
            (path, filename) = os.path.split(self.path_right_click)
            os.chdir(path)
            if os.path.isfile(self.path_right_click):
                send2trash.send2trash(filename)
            if os.path.isdir(self.path_right_click):
                send2trash.send2trash(filename)
            self.notice(self.path_right_click + ' 文件已删除!!!')
            self.model.refresh()
        except Exception as e:
            self.notice("文件删除异常!!!" + str(e))

    def on_selection_changed(self, selected, deselected):
        indexes = selected.indexes()
        for item in indexes:
            self.path = self.model.filePath(item)
            if self.pic_show_layout.is_pic(self.path):
                self.on_tree_clicked(item)

    def on_tree_clicked(self, qmodelindex):
        self.path = self.model.filePath(qmodelindex)

        if os.path.isdir(self.path):
            # 单击目录只做选中 / 展开：**不扫描、不切模式**。
            # 图片 / 视频列表只能由「右键菜单」或「文件菜单」显式触发
            # （见 load_for_pic_show / load_for_video_lise / load_pic_list_dialog / load_video_list_dialog），
            # 否则在树里翻目录会顺带扫一堆大目录（ADR-025）。
            return

        if not os.path.isfile(self.path):
            self.notice("非法文件路径: " + self.path)
            return

        if self.inputAndExeLayout.timer.isActive():
            self.inputAndExeLayout.timer.stop()

        if self.video_show_layout.is_video(self.path):
            # 点击单个视频：退出列表播放模式
            self.video_show_layout.play_mode = self.video_show_layout.play_mode_one
            self.video_show_layout.play_list.clear()
            self.video_show_layout.play_list_index = 0
            self.change_show(self.show_type_video)
            self.video_show_layout.play(self.model.filePath(qmodelindex))
        elif self.pic_show_layout.is_pic(self.path):
            # 点击单个图片：退出幻灯片/列表模式
            self.pic_show_layout.counter = 0
            self.pic_show_layout.inputAndExeLayout.list_files.clear()
            self.change_show(self.show_type_pic)
            self.pic_show_layout.play(self.model.filePath(qmodelindex))
        else:
            self.video_show_layout.titleQLabel.setText('文件格式错误!!!')
            self.pic_show_layout.titleQLabel.setText('文件格式错误!!!')
            self.notice('文件格式错误!!!')

    # ============================================
    #  显式加载列表（文件菜单 / 右键菜单触发）
    # ============================================
    def _list_dir_hint(self):
        """选目录对话框的起始目录：当前选中项（文件则取所在目录）。"""
        path = self.path or ''
        if path and os.path.isdir(path):
            return path
        if path and os.path.isfile(path):
            return os.path.dirname(path)
        return ''

    def load_pic_list_dialog(self):
        """文件菜单 → 加载为幻灯片列表：选目录后扫描图片。

        与右键「加载为幻灯片列表」等价；点目录本身不再自动触发扫描（ADR-025）。
        """
        directory = pick_directory(self, "选择图片目录", start_dir=self._list_dir_hint())
        if not directory or not os.path.isdir(directory):
            return
        self.change_show(self.show_type_pic)
        self.inputAndExeLayout.set_content_path(directory)

    def load_video_list_dialog(self):
        """文件菜单 → 加载为视频列表：选目录后递归扫描视频。"""
        directory = pick_directory(self, "选择视频目录", start_dir=self._list_dir_hint())
        if not directory or not os.path.isdir(directory):
            return
        self.config_manager.add_or_update(VideoShowLayout.video_show_list_key, directory)
        self.video_show_layout.loadData(directory)
        self.change_show(self.show_type_video)

