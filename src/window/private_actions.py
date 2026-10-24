# -*- coding: utf-8 -*-
"""私密媒体动作：打开私密库、密文点开即解密、批量加解密、私密幻灯片。

私密不再是独立的界面模式（见 ADR-026）：加密 / 解密只是普通工作区里的文件操作，
密文在目录树里被点开时按需解密到本次运行的缓存目录，退出 / 批量操作后清空。
"""
import json
import os

from loguru import logger
from PyQt5.QtWidgets import QApplication

from src.layout.styled_dialogs import (ProgressDialog, ask_yes_no, pick_directory,
                                       show_error, show_info)
from src.layout.video_show_layout import VideoShowLayout
from src.private_mode.private_batch_thread import PrivateBatchThread


class PrivateActionsMixin:
    """私密媒体相关的窗口动作（模式已合并，只保留功能入口）。"""

    # ============================================
    #  入口：打开私密库 / 私密幻灯片
    # ============================================
    def _open_private_library(self):
        """文件菜单 → 打开私密库：选目录并把它设为左侧树的根（等价于打开该目录）。"""
        start_dir = ''
        if self.config_manager.exist(self.private_library_path_key):
            saved = self.config_manager.get(self.private_library_path_key)
            if saved and os.path.isdir(saved):
                start_dir = saved

        selected_path = pick_directory(self, '选择私密库文件夹', start_dir=start_dir)
        if not selected_path or not os.path.isdir(selected_path):
            return

        self.config_manager.add_or_update(self.private_library_path_key, selected_path)
        self._set_tree_root(selected_path)
        self.expand_path(selected_path)
        if self.private_service.has_key():
            self.notice('私密库：已加载密钥')
        else:
            self.notice('私密库：尚未导入密钥，加密文件请先「密钥 → 导入密钥」')

    # ============================================
    #  私密库标记：记住「这个目录下全是密文」
    # ============================================
    def _load_private_library_dirs(self):
        """从配置读出被标记的私密库目录（JSON 数组），缓存成绝对路径列表。"""
        self._private_library_dirs = []
        if not self.config_manager.exist(self.private_library_dirs_key):
            return
        raw = self.config_manager.get(self.private_library_dirs_key) or ''
        try:
            values = json.loads(raw) if raw.strip() else []
        except (TypeError, ValueError):
            logger.warning('私密库标记配置无法解析: %r' % raw)
            return
        if not isinstance(values, list):
            return
        result = []
        for value in values:
            if isinstance(value, str) and value.strip():
                result.append(os.path.normpath(os.path.abspath(value)))
        self._private_library_dirs = result

    def _save_private_library_dirs(self, paths):
        self.config_manager.add_or_update(
            self.private_library_dirs_key,
            json.dumps(paths, ensure_ascii=False) if paths else '')
        self._private_library_dirs = list(paths)
        try:
            self.model.refresh()
            self.treeView.viewport().update()
        except Exception as e:
            logger.warning(f'刷新私密库标记失败: {e}')

    def is_private_library_root(self, path):
        """这一行目录本身是否被标记为私密库（树里只给被标记的那一行打标记）。"""
        if not path:
            return False
        key = os.path.normcase(os.path.normpath(os.path.abspath(path)))
        return any(os.path.normcase(p) == key
                   for p in getattr(self, '_private_library_dirs', []))

    def is_in_private_library(self, path):
        """path 自身或任一祖先被标记为私密库（标记对子目录同样生效）。"""
        if not path:
            return False
        marks = {os.path.normcase(p) for p in getattr(self, '_private_library_dirs', [])}
        if not marks:
            return False
        current = os.path.normcase(os.path.normpath(os.path.abspath(path)))
        while True:
            if current in marks:
                return True
            parent = os.path.dirname(current)
            if parent == current:
                return False
            current = parent

    def _toggle_private_library_target(self):
        """右键 → 私密操作 → 标记 / 取消标记本目录为私密库。"""
        target = self.path_right_click
        if not target or not os.path.isdir(target):
            self.notice('请先在左侧树中选择一个目录')
            return
        target = os.path.normpath(os.path.abspath(target))
        paths = list(getattr(self, '_private_library_dirs', []))
        key = os.path.normcase(target)
        if any(os.path.normcase(p) == key for p in paths):
            paths = [p for p in paths if os.path.normcase(p) != key]
            self._save_private_library_dirs(paths)
            self.notice('已取消私密库标记：' + target)
        else:
            paths.append(target)
            self._save_private_library_dirs(paths)
            self.notice('已标记为私密库（本目录下按密文处理）：' + target)

    def load_private_pic_list_dialog(self):
        """文件菜单 → 加载为私密幻灯片列表：选目录后解密其中图片并按序展示。"""
        directory = pick_directory(self, '选择私密目录（可含密文）',
                                   start_dir=self._private_list_start_dir())
        if not directory or not os.path.isdir(directory):
            return
        self._load_private_slideshow(directory)

    def load_private_video_list_dialog(self):
        """文件菜单 → 加载为私密视频列表：选目录后把视频（含密文）加入播放列表。"""
        directory = pick_directory(self, '选择私密视频目录（可含密文）',
                                   start_dir=self._private_list_start_dir())
        if not directory or not os.path.isdir(directory):
            return
        self._load_private_video_list(directory)

    def _private_list_start_dir(self):
        """私密列表选择框的起始目录：优先当前选中项，其次上次打开过的私密库。"""
        start_dir = self._list_dir_hint()
        if not start_dir and self.config_manager.exist(self.private_library_path_key):
            saved = self.config_manager.get(self.private_library_path_key)
            if saved and os.path.isdir(saved):
                start_dir = saved
        return start_dir

    def load_private_video_list_for_target(self):
        """右键 → 私密操作 → 加载私密视频列表（含密文）：作用于右键选中的目录。"""
        target = self.path_right_click
        if not target or not os.path.isdir(target):
            self.notice('请在左侧树中选择一个目录')
            return
        self._load_private_video_list(target)

    def _load_private_video_list(self, dir_path):
        """私密目录：列表里放密文原路径，播到哪一集才解密（不预先解密大文件）。

        `VideoShowLayout` 通过 `set_path_resolver()` 注入的解析器在 `play()` 里
        把密文换成缓存明文，所以这里可以直接把密文路径塞进 `play_list`。
        """
        try:
            videos = self.private_service.list_videos(dir_path)
        except Exception as e:
            logger.error(f'读取私密视频目录失败 {dir_path}: {e}')
            self.notice('读取目录失败：' + str(e))
            return
        if not videos:
            self.notice('该目录下没有可播放的视频（或缺少配套密钥）')
            return

        layout = self.video_show_layout
        layout.cancel_scan()
        layout.play_list.clear()
        layout.play_list.extend(videos)
        layout.play_list_index = 0
        layout._list_reset_mode = False
        layout.play_mode = layout.play_mode_list
        self.config_manager.add_or_update(VideoShowLayout.video_show_list_key, dir_path)
        self.change_show(self.show_type_video)
        layout.play(videos[0])
        self.notice('私密视频列表：%d 个（%s）' % (len(videos), dir_path))

    def load_private_slideshow_for_target(self):
        """右键 → 私密操作 → 加载私密幻灯片（含密文）：作用于右键选中的目录。"""
        target = self.path_right_click
        if not target or not os.path.isdir(target):
            self.notice('请在左侧树中选择一个目录')
            return
        self._load_private_slideshow(target)

    def _is_encrypted_file(self, path):
        """判断文件是否为密文（右键「删除」前的二次确认用）。"""
        if not path or not os.path.isfile(path):
            return False
        try:
            return bool(self.private_service.describe(path).get('encrypted'))
        except Exception as e:
            logger.warning(f'判断密文失败 {path}: {e}')
            return False

    def _load_private_slideshow(self, dir_path):
        """私密目录：把目录下的图片（含密文）解密到缓存，交给幻灯片功能展示。"""
        try:
            images = self.private_service.list_images(dir_path)
        except Exception as e:
            logger.error(f'读取私密目录失败 {dir_path}: {e}')
            self.notice('读取目录失败：' + str(e))
            return

        if not images:
            self.pic_show_qwidget.setVisible(False)
            self.video_show_qwidget.setVisible(False)
            self.notice('该目录下没有可展示的图片')
            return

        progress = ProgressDialog(self, '私密幻灯片', '正在解密图片...', len(images))
        progress.show()
        QApplication.processEvents()

        playable = []
        display_names = []
        for index, path in enumerate(images):
            if progress.is_canceled():
                break
            progress.setValue(index)
            progress.setLabelText('解密：' + os.path.basename(path))
            QApplication.processEvents()
            try:
                cache_path, display_name = self.private_service.resolve_playable(path)
            except Exception as e:
                logger.warning(f'私密图片解密失败 {path}: {e}')
                continue
            playable.append(cache_path)
            display_names.append(display_name)
        progress.setValue(len(images))
        progress.close()

        if not playable:
            self.notice('没有可展示的图片（可能是缺少配套密钥）')
            return

        # 列表里直接用解密后的明文路径；先取消后台扫描，避免其它目录的扫描结果覆盖
        self.inputAndExeLayout.cancel_scan()
        self.inputAndExeLayout.content_path = dir_path
        self.inputAndExeLayout.list_files.clear()
        self.inputAndExeLayout.list_files.extend(playable)
        self.pic_show_layout.counter = 0
        self.change_show(self.show_type_pic)
        self.pic_show_layout.play(playable[0])
        try:
            self.title_bar.setInfo(os.path.splitext(display_names[0])[0],
                                   '(1/%d)' % len(playable))
        except Exception:
            pass
        self.notice('私密幻灯片：%d 张（%s）' % (len(playable), dir_path))

    # ============================================
    #  批量加解密（右键「私密操作」触发）
    # ============================================
    def _encrypt_current_target(self):
        """右键 → 私密操作 → 加密该路径下的图片和视频。"""
        target = self.path_right_click
        if not target or not os.path.exists(target):
            self.notice('请先在左侧树中选择文件或目录')
            return
        self._encrypt_private_path(target)

    def _decrypt_current_target(self):
        """右键 → 私密操作 → 解密该路径下的文件。"""
        target = self.path_right_click
        if not target or not os.path.exists(target):
            self.notice('请先在左侧树中选择文件或目录')
            return
        self._decrypt_private_path(target)

    def _encrypt_private_path(self, target):
        try:
            files, skipped = self.private_service.scan_encryptable(target)
        except Exception as e:
            logger.error(f'扫描待加密文件失败 {target}: {e}')
            self.notice('扫描失败：' + str(e))
            return
        if not files:
            show_info(self, '加密', '该路径下没有需要加密的图片/视频文件。')
            return

        if not self.private_service.has_key():
            if not ask_yes_no(
                    self, '尚未导入密钥',
                    '当前还没有密钥。\n继续将自动生成一把新的随机密钥'
                    '（可通过「密钥 → 导出密钥」备份）。\n\n继续？'):
                return

        if not ask_yes_no(
                self, '加密确认',
                '即将加密 %d 个图片/视频文件：\n%s\n\n'
                '将同时加密文件内容与文件名，加密后源文件会被删除，只保留加密文件。\n'
                '另有 %d 个非媒体 / 已加密文件会被跳过。\n\n继续？'
                % (len(files), target, skipped), default_yes=False):
            return
        self._run_private_batch('encrypt', target, len(files))

    def _decrypt_private_path(self, target):
        try:
            files, missing_key = self.private_service.scan_decryptable(target)
        except Exception as e:
            logger.error(f'扫描待解密文件失败 {target}: {e}')
            self.notice('扫描失败：' + str(e))
            return
        if not files:
            message = '该路径下没有可解密的文件。'
            if missing_key:
                message += '\n另有 %d 个密文没有配套密钥记录（请先导入密钥）。' % missing_key
            show_info(self, '解密', message)
            return

        detail = ''
        if missing_key:
            detail = '\n另有 %d 个密文没有配套密钥记录，会被跳过。' % missing_key
        if not ask_yes_no(
                self, '解密确认',
                '即将解密 %d 个文件：\n%s\n\n'
                '解密后恢复原文件名并删除密文。%s\n\n继续？'
                % (len(files), target, detail), default_yes=False):
            return
        self._run_private_batch('decrypt', target, len(files))

    def _run_private_batch(self, mode, target, total):
        if self.private_batch_thread is not None and self.private_batch_thread.isRunning():
            show_info(self, '私密操作', '已有加解密任务在运行，请等待完成。')
            return

        title = '正在加密' if mode == 'encrypt' else '正在解密'
        progress = ProgressDialog(self, '私密操作', '%s：%s' % (title, target), max(total, 1))
        progress.show()

        thread = PrivateBatchThread(mode, target, parent=self)
        thread.progress.connect(
            lambda done, all_count, name: self._on_private_batch_progress(progress, done, all_count, name))
        thread.completed.connect(
            lambda stats: self._on_private_batch_completed(mode, stats, progress))
        thread.failed.connect(
            lambda message: self._on_private_batch_failed(message, progress))
        progress.canceled.connect(thread.cancel)

        self.private_batch_thread = thread
        self.statusLabel.setText('%s：%s' % (title, target))
        thread.start()

    @staticmethod
    def _on_private_batch_progress(progress, done, total, name):
        progress.setMaximum(max(total, 1))
        progress.setValue(min(done, max(total, 1)))
        if name:
            progress.setLabelText(name)

    def _on_private_batch_completed(self, mode, stats, progress):
        progress.setValue(progress.maximum())
        progress.close()
        self.private_batch_thread = None

        # 加解密后缓存里的明文已经过期，清掉重新按需解密
        self.private_service.clear_cache()
        self.model.refresh()

        if mode == 'encrypt':
            message = '加密完成：成功 %d 个，跳过 %d 个，失败 %d 个。' % (
                stats.get('encrypted', 0), stats.get('skipped', 0), stats.get('failed', 0))
            if stats.get('kept_source'):
                message += '\n有 %d 个文件已加密但源文件删除失败（密文已生成）。' % stats['kept_source']
        else:
            message = '解密完成：成功 %d 个，失败 %d 个。' % (
                stats.get('decrypted', 0), stats.get('failed', 0))
            if stats.get('missing_key'):
                message += '\n有 %d 个密文没有配套密钥记录，已跳过。' % stats['missing_key']
            if stats.get('kept_source'):
                message += '\n有 %d 个文件明文已恢复但密文删除失败。' % stats['kept_source']
        if stats.get('cancelled'):
            message += '\n任务已被取消（已处理的文件不受影响，可重跑）。'
        errors = stats.get('errors') or []
        if errors:
            message += '\n\n前几个错误：\n' + '\n'.join(errors[:5])

        show_info(self, '私密操作', message)
        self.notice(message.replace('\n', ' '))

    def _on_private_batch_failed(self, message, progress):
        progress.close()
        self.private_batch_thread = None
        logger.error('私密批量操作失败: ' + message)
        show_error(self, '私密操作', '操作失败：\n' + message)
        self.notice('私密操作失败：' + message)
