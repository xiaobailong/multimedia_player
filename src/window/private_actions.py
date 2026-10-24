# -*- coding: utf-8 -*-
"""私密模式：模式切换、私密库加载、密文播放、批量加解密。"""
import os

from loguru import logger
from PyQt5.QtWidgets import QApplication, QMenu

from src.layout.styled_dialogs import (ProgressDialog, ask_yes_no, pick_directory,
                                       show_error, show_info, show_warning)
from src.private_mode.private_batch_thread import PrivateBatchThread


class PrivateActionsMixin:
    """私密模式相关的窗口动作。"""

    def _toggle_private_mode(self, enable):
        if enable == self.private_mode:
            return

        self.private_mode = enable

        if enable:
            # 切换到私密模式
            self._save_normal_state()
            self.normal_mode_action.setChecked(False)
            self.private_mode_action.setChecked(True)

            # 隐藏普通树
            self.treeView.setVisible(False)
            self.toggle_tree_action.setEnabled(False)

            # 隐藏普通模式的视频/图片
            self.video_show_qwidget.setVisible(False)
            self.pic_show_qwidget.setVisible(False)

            # 检查是否有私密库路径
            if self.config_manager.exist(self.private_library_path_key):
                private_path = self.config_manager.get(self.private_library_path_key)
                if os.path.isdir(private_path):
                    self._load_private_library(private_path)
                else:
                    self._show_private_overlay()
            else:
                self._show_private_overlay()

            self.statusLabel.setText("私密模式")
        else:
            # 切换回普通模式
            self.normal_mode_action.setChecked(True)
            self.private_mode_action.setChecked(False)

            # 隐藏私密切换相关控件
            self.private_tree_view.setVisible(False)
            self.private_overlay_widget.setVisible(False)

            # 恢复普通模式状态
            self._restore_normal_state()
            self.toggle_tree_action.setEnabled(True)

            self.statusLabel.setText("普通模式")

    def _save_normal_state(self):
        """保存普通模式下的UI状态"""
        self._saved_tree_visible = self.tree_visible
        self._saved_tree_sizes = self.mainQWidget.sizes()
        self._saved_video_visible = self.video_show_qwidget.isVisible()
        self._saved_pic_visible = self.pic_show_qwidget.isVisible()

    def _restore_normal_state(self):
        """恢复普通模式下的UI状态"""
        if hasattr(self, '_saved_tree_visible'):
            self.tree_visible = self._saved_tree_visible
            self.treeView.setVisible(self._saved_tree_visible)
        else:
            self.treeView.setVisible(True)
            self.tree_visible = True
        if hasattr(self, 'toggle_tree_action'):
            self.toggle_tree_action.setChecked(self.tree_visible)

        if hasattr(self, '_saved_video_visible') and self._saved_video_visible:
            self.video_show_qwidget.setVisible(True)
        if hasattr(self, '_saved_pic_visible') and self._saved_pic_visible:
            self.pic_show_qwidget.setVisible(True)

        if hasattr(self, '_saved_tree_sizes'):
            self.mainQWidget.setSizes(self._saved_tree_sizes)

    def _show_private_overlay(self):
        """显示私密模式覆盖层（无路径状态）"""
        self.private_overlay_widget.setVisible(True)
        self.video_show_qwidget.setVisible(False)
        self.pic_show_qwidget.setVisible(False)
        self.private_tree_view.setVisible(False)
        # 无路径时树隐藏，右侧工作区占满
        self.mainQWidget.setSizes([0, 0, 1])

    def _open_private_library(self):
        """打开私密库文件夹选择对话框"""
        selected_path = pick_directory(self, "选择私密库文件夹")
        if not selected_path or not os.path.isdir(selected_path):
            return

        self.config_manager.add_or_update(self.private_library_path_key, selected_path)
        self._load_private_library(selected_path)

    def _load_private_library(self, path):
        """加载私密库路径到左侧树"""
        self.private_overlay_widget.setVisible(False)
        self.private_tree_view.setVisible(True)
        self.private_tree_model.refresh()
        root_index = self.private_tree_model.index(path)
        self.private_tree_view.setRootIndex(root_index)
        # 展开根目录
        self.private_tree_view.setExpanded(root_index, True)
        # 私密树 : 工作区 = left : right
        self.mainQWidget.setSizes([0, 10000 * self.left, 10000 * self.right])
        if self.private_service.has_key():
            self.notice('私密模式：已加载密钥')
        else:
            self.notice('私密模式：尚未导入密钥，加密文件请先「密钥 → 导入密钥」')

    def _on_private_tree_clicked(self, qmodelindex):
        """私密模式下树节点点击事件（点到密文时先解密再交给现有展示逻辑）"""
        # 私密模式下不要执行"点目录 → 扫普通图片列表"的排队任务
        self._cancel_pic_scan()
        file_path = self.private_tree_model.filePath(qmodelindex)

        if os.path.isdir(file_path):
            self._load_private_slideshow(file_path)
            return

        if not os.path.isfile(file_path):
            return

        # 停止幻灯片定时器
        if self.inputAndExeLayout.timer.isActive():
            self.inputAndExeLayout.timer.stop()

        # 密文 → 解密到本次运行缓存；明文 → 原样返回
        try:
            play_path, display_name = self.private_service.resolve_playable(file_path)
        except Exception as e:
            logger.error(f'私密文件解密失败 {file_path}: {e}')
            self.notice('解密失败：' + str(e))
            show_warning(self, '私密文件', str(e))
            return

        # 根据文件类型切换显示（复用普通模式的播放 / 看图功能）
        if self.video_show_layout.is_video(play_path):
            self.video_show_layout.play_mode = self.video_show_layout.play_mode_one
            self.video_show_layout.play_list.clear()
            self.video_show_layout.play_list_index = 0
            self.change_show(self.show_type_video)
            self.video_show_layout.play(play_path)
        elif self.pic_show_layout.is_pic(play_path):
            self.pic_show_layout.counter = 0
            self.pic_show_layout.inputAndExeLayout.list_files.clear()
            self.pic_show_layout.inputAndExeLayout.list_files.append(play_path)
            self.change_show(self.show_type_pic)
            self.pic_show_layout.play(play_path)
        else:
            message = '文件格式不支持：' + display_name
            self.video_show_layout.titleQLabel.setText(message)
            self.pic_show_layout.titleQLabel.setText(message)
            self.notice(message)
            return

        # 标题栏显示原始文件名（而不是解密缓存里的路径）
        try:
            self.title_bar.setInfo(os.path.splitext(display_name)[0], '')
        except Exception:
            pass

    def _load_private_slideshow(self, dir_path):
        """私密目录：把目录下的图片（含密文）准备好，交给幻灯片功能展示。"""
        try:
            images = self.private_service.list_images(dir_path)
        except Exception as e:
            logger.error(f'读取私密目录失败 {dir_path}: {e}')
            self.notice('读取目录失败：' + str(e))
            return

        if not images:
            self.pic_show_qwidget.setVisible(False)
            self.video_show_qwidget.setVisible(False)
            self.private_overlay_widget.setVisible(False)
            self.notice('该目录下没有可展示的图片')
            return

        progress = ProgressDialog(self, '私密模式', '正在解密图片...', len(images))
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

        # 私密模式：文件已解密到缓存目录，列表直接用解密后的明文路径
        # （先取消后台扫描，避免其它目录的扫描结果覆盖这里的列表）
        self.inputAndExeLayout.cancel_scan()
        self._cancel_pic_scan()   # 手动填充列表前，先丢掉排队中的普通目录扫描
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

    # ============================================
    #  私密模式：左侧树右键（加密 / 解密）
    # ============================================
    def _private_right_click_menu(self, pos):
        """私密模式左侧树右键菜单（只有私密模式才有）。"""
        if not self.private_mode:
            return

        index = self.private_tree_view.indexAt(pos)
        if index.isValid():
            target = self.private_tree_model.filePath(index)
        else:
            root_index = self.private_tree_view.rootIndex()
            target = self.private_tree_model.filePath(root_index) if root_index.isValid() else ''
        if not target:
            self.notice('请先在左侧树中选择目录')
            return

        menu = QMenu(self.private_tree_view)
        encrypt_action = menu.addAction('加密该路径下的图片和视频')
        decrypt_action = menu.addAction('解密该路径下的文件')
        menu.addSeparator()
        refresh_action = menu.addAction('刷新')

        chosen = menu.exec_(self.private_tree_view.viewport().mapToGlobal(pos))
        if chosen == encrypt_action:
            self._encrypt_private_path(target)
        elif chosen == decrypt_action:
            self._decrypt_private_path(target)
        elif chosen == refresh_action:
            self.private_tree_model.refresh()

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
            show_info(self, '私密模式', '已有加解密任务在运行，请等待完成。')
            return

        title = '正在加密' if mode == 'encrypt' else '正在解密'
        progress = ProgressDialog(self, '私密模式', '%s：%s' % (title, target), max(total, 1))
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
        self.private_tree_model.refresh()
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

        show_info(self, '私密模式', message)
        self.notice(message.replace('\n', ' '))

    def _on_private_batch_failed(self, message, progress):
        progress.close()
        self.private_batch_thread = None
        logger.error('私密批量操作失败: ' + message)
        show_error(self, '私密模式', '操作失败：\n' + message)
        self.notice('私密操作失败：' + message)
