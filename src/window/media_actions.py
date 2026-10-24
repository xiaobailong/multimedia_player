# -*- coding: utf-8 -*-
"""普通模式左侧文件树的媒体操作。

包含：目录展开 / 右键菜单 / 打开目录 / 复制 / 移动 / 删除 / 载入播放列表 /
点击树节点播放。全部方法原样来自 ``Player.py``，只做位置搬运。
"""
import os
import shutil

import send2trash
from PyQt5.QtWidgets import QAbstractItemView, QMenu
from loguru import logger

from src.layout.styled_dialogs import ask_yes_no, pick_directory, show_warning
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
        """左侧树右键菜单，按用途分 4 组：加载列表 / 文件操作 / 路径设置 / 私密操作。"""
        try:
            index = self.treeView.indexAt(pos)
            if not index.isValid():
                index = self.treeView.currentIndex()
            self.path_right_click = self.model.filePath(index)
            has_target = bool(self.path_right_click)
            is_dir = has_target and os.path.isdir(self.path_right_click)

            menu = QMenu(self.treeView)

            # ---- 分组 1：把目录加载成播放列表（只对目录有意义）----
            load_pic_action = menu.addAction(u'加载为幻灯片列表')
            load_pic_action.setEnabled(is_dir)
            load_pic_action.triggered.connect(self.load_for_pic_show)

            load_video_action = menu.addAction(u'加载为视频列表')
            load_video_action.setEnabled(is_dir)
            load_video_action.triggered.connect(self.load_for_video_lise)

            menu.addSeparator()

            # ---- 分组 2：文件操作 ----
            copy_action = menu.addAction(u'复制到...')
            copy_action.setEnabled(has_target)
            copy_action.triggered.connect(self.copy)

            move_action = menu.addAction(u'移动到...')
            move_action.setEnabled(has_target)
            move_action.triggered.connect(self.move)

            delete_action = menu.addAction(u'删除（移至回收站）')
            delete_action.setEnabled(has_target)
            delete_action.triggered.connect(self.delete)

            refresh_action = menu.addAction(u'刷新')
            refresh_action.triggered.connect(self.refresh)

            menu.addSeparator()

            # ---- 分组 3：路径设置（路径类配置只对目录有意义）----
            screenshot_action = menu.addAction(u'设置为截图路径')
            screenshot_action.setEnabled(is_dir)
            screenshot_action.triggered.connect(self.load_for_video_screenshot)

            cut_action = menu.addAction(u'设置为剪切路径')
            cut_action.setEnabled(is_dir)
            cut_action.triggered.connect(self.load_for_video_cut)

            expand_action = menu.addAction(u'设置为默认展开')
            expand_action.setEnabled(is_dir)
            expand_action.triggered.connect(self.set_expand_path)

            menu.addSeparator()

            # ---- 分组 4：私密操作（列表 / 加解密 / 私密库标记）----
            private_menu = menu.addMenu(u'私密操作')

            private_slideshow_action = private_menu.addAction(u'加载私密幻灯片（含密文）')
            private_slideshow_action.setEnabled(is_dir)
            private_slideshow_action.triggered.connect(self.load_private_slideshow_for_target)

            private_video_action = private_menu.addAction(u'加载私密视频列表（含密文）')
            private_video_action.setEnabled(is_dir)
            private_video_action.triggered.connect(self.load_private_video_list_for_target)

            private_menu.addSeparator()

            encrypt_action = private_menu.addAction(u'加密该路径下的图片和视频')
            encrypt_action.setEnabled(has_target)
            encrypt_action.triggered.connect(self._encrypt_current_target)

            decrypt_action = private_menu.addAction(u'解密该路径下的文件')
            decrypt_action.setEnabled(has_target)
            decrypt_action.triggered.connect(self._decrypt_current_target)

            private_menu.addSeparator()

            marked = is_dir and self.is_private_library_root(self.path_right_click)
            mark_action = private_menu.addAction(
                u'取消私密库标记' if marked else u'标记为私密库（本目录全是密文）')
            mark_action.setEnabled(is_dir)
            mark_action.triggered.connect(self._toggle_private_library_target)

            menu.exec_(self.treeView.viewport().mapToGlobal(pos))
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

        # 标记为私密库的目录下全是密文：普通扫描一个都认不出，直接走解密列表
        if self.is_in_private_library(self.path_right_click):
            self._load_private_video_list(self.path_right_click)
            return

        self.config_manager.add_or_update(VideoShowLayout.video_show_list_key, self.path_right_click)
        self.video_show_layout.loadData(self.path_right_click)
        self.change_show(self.show_type_video)

    def load_for_pic_show(self):
        if os.path.isfile(self.path_right_click):
            return

        # 标记为私密库的目录下全是密文：普通扫描一个都认不出，直接走解密幻灯片
        if self.is_in_private_library(self.path_right_click):
            self._load_private_slideshow(self.path_right_click)
            return

        self.change_show(self.show_type_pic)
        self.inputAndExeLayout.set_content_path(self.path_right_click)

    def delete(self):
        target = self.path_right_click
        if not target:
            self.notice('请先在左侧树中选择要删除的文件或目录')
            return
        try:
            # 密文删掉就再也解不开了（密钥库只能证明它存在过），先确认一次
            if target and os.path.isfile(target) and self._is_encrypted_file(target):
                if not ask_yes_no(
                        self, '删除密文',
                        '该文件是加密文件（密文）。\n\n'
                        '删除后内容无法恢复，密钥库也无法再解开它。\n\n确定删除吗？',
                        default_yes=False):
                    return
            (path, filename) = os.path.split(target)
            os.chdir(path)
            if os.path.isfile(target):
                send2trash.send2trash(filename)
            if os.path.isdir(target):
                send2trash.send2trash(filename)
            self.notice(target + ' 文件已删除!!!')
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
            # 单击目录只做选中 / 展开：**不扫描、不切显示**。
            # 图片 / 视频列表只能由「右键菜单」或「文件菜单」显式触发（见 ADR-025）。
            return

        if not os.path.isfile(self.path):
            self.notice("非法文件路径: " + self.path)
            return

        if self.inputAndExeLayout.timer.isActive():
            self.inputAndExeLayout.timer.stop()

        # 密文（32 位 hex、无扩展名）没有可判定的后缀，先解到本次运行缓存；
        # 明文文件原样返回。解密只发生在点击这一处（ADR-026：模式已合并）
        try:
            play_path, display_name = self.private_service.resolve_playable(self.path)
        except Exception as e:
            logger.error(f'解密失败 {self.path}: {e}')
            self.notice('解密失败：' + str(e))
            show_warning(self, '密文文件', str(e))
            return

        if self.video_show_layout.is_video(play_path):
            # 点击单个视频：退出列表播放模式
            self.video_show_layout.play_mode = self.video_show_layout.play_mode_one
            self.video_show_layout.play_list.clear()
            self.video_show_layout.play_list_index = 0
            self.change_show(self.show_type_video)
            self.video_show_layout.play(play_path)
        elif self.pic_show_layout.is_pic(play_path):
            # 点击单个图片：退出幻灯片/列表模式
            self.pic_show_layout.counter = 0
            self.pic_show_layout.inputAndExeLayout.list_files.clear()
            self.change_show(self.show_type_pic)
            self.pic_show_layout.play(play_path)
        else:
            message = ('文件格式不支持：' + display_name
                       if play_path != self.path else '文件格式错误!!!')
            self.video_show_layout.titleQLabel.setText(message)
            self.pic_show_layout.titleQLabel.setText(message)
            self.notice(message)
            return

        if play_path != self.path:
            # 密文：标题栏显示原始文件名，而不是解密缓存里的路径
            try:
                self.title_bar.setInfo(os.path.splitext(display_name)[0], '')
            except Exception:
                pass
            self.notice('已解密并播放：' + display_name)

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
        # 标记为私密库的目录下全是密文：直接走解密幻灯片，避免"扫描完成 0 张"
        if self.is_in_private_library(directory):
            self._load_private_slideshow(directory)
            return
        self.change_show(self.show_type_pic)
        self.inputAndExeLayout.set_content_path(directory)

    def load_video_list_dialog(self):
        """文件菜单 → 加载为视频列表：选目录后递归扫描视频。"""
        directory = pick_directory(self, "选择视频目录", start_dir=self._list_dir_hint())
        if not directory or not os.path.isdir(directory):
            return
        # 标记为私密库的目录下全是密文：直接走解密视频列表
        if self.is_in_private_library(directory):
            self._load_private_video_list(directory)
            return
        self.config_manager.add_or_update(VideoShowLayout.video_show_list_key, directory)
        self.video_show_layout.loadData(directory)
        self.change_show(self.show_type_video)

