# -*- coding: utf-8 -*-
"""普通模式左侧文件树的媒体操作。

包含：目录展开 / 右键菜单 / 打开目录 / 复制 / 移动 / 删除 / 载入播放列表 /
点击树节点播放。全部方法原样来自 ``Player.py``，只做位置搬运。
"""
import os
import shutil

import send2trash
from PyQt5.QtCore import QModelIndex, Qt, QTimer
from PyQt5.QtWidgets import QAbstractItemView, QMenu
from loguru import logger

from src.layout.styled_dialogs import pick_directory
from src.layout.video_show_layout import VideoShowLayout


class MediaActionsMixin:
    """文件树 → 播放 / 文件操作。"""

    # 点目录后延迟多久才真正去扫图片（见 _schedule_pic_scan）
    PIC_SCAN_DEBOUNCE_MS = 300


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

        if self.inputAndExeLayout.timer.isActive():
            self.inputAndExeLayout.timer.stop()

        if os.path.isdir(self.path):
            if not self.pic_show_qwidget.isVisible():
                self.change_show(self.show_type_pic)
            # 说明：单击目录（含点展开箭头）就会加载该目录的图片列表，不是右键才触发。
            # 但用户经常只是展开树 / 快速翻目录，每个目录都立刻扫一遍很浪费
            # （C:/Users 这种要几百 ms 到几秒，还会刷一堆"拒绝访问"），
            # 所以延迟一小会儿，只扫"最后停下来的那个目录"。
            self._schedule_pic_scan(self.path)
        elif os.path.isfile(self.path):
            self._cancel_pic_scan()   # 点了具体文件：放弃还在排队的目录扫描
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
        else:
            self.notice("非法文件路径: " + self.path)

    # ============================================
    #  点目录 → 加载图片列表（带防抖）
    # ============================================
    def _schedule_pic_scan(self, directory):
        """延迟把目录交给图片列表：连续点目录 / 展开树时只扫最后停下的那个。

        单击目录本身就会加载该目录的图片（这是既有交互，不需要右键）；
        但展开树、快速翻目录时每个目录都立刻扫一遍很浪费（大目录几百 ms~几秒），
        所以这里做成 300ms 防抖：期间又点了别的目录就重置计时器。
        """
        self._pending_pic_scan_dir = directory
        timer = getattr(self, '_pic_scan_timer', None)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._apply_pending_pic_scan)
            self._pic_scan_timer = timer
        timer.start(self.PIC_SCAN_DEBOUNCE_MS)

    def _apply_pending_pic_scan(self):
        """防抖计时到点：真正去扫图片列表（期间模式变了就放弃）。"""
        directory = getattr(self, '_pending_pic_scan_dir', '')
        self._pending_pic_scan_dir = ''
        if not directory or not os.path.isdir(directory):
            return
        # 期间可能已经切到视频 / 私密模式，或用户已经点了别的文件
        if self.private_mode or self.video_show_qwidget.isVisible():
            return
        self.inputAndExeLayout.set_content_path(directory)

    def _cancel_pic_scan(self):
        """取消还在排队的目录图片扫描（点了文件 / 切到视频模式时调用）。"""
        self._pending_pic_scan_dir = ''
        timer = getattr(self, '_pic_scan_timer', None)
        if timer is not None and timer.isActive():
            timer.stop()

