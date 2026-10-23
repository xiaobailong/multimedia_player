# -*- coding: utf-8 -*-
"""归集：按评分 / 关键字 / 路径筛选媒体并批量拷贝（后台线程 + 进度弹框）。"""
import os

from loguru import logger
from PyQt5.QtWidgets import QDialog

from src.collect.collect_service import matches_kind
from src.collect.collect_thread import CollectThread
from src.layout.collect_dialog import CollectDialog
from src.layout.styled_dialogs import ProgressDialog, pick_directory, show_error, show_info


class CollectActionsMixin:
    """归集菜单背后的窗口动作。"""

    def _collect_default_root(self):
        """归集弹框「搜索目录」的默认值：当前选中的目录 / 当前媒体所在目录。"""
        candidates = []
        if self.path:
            candidates.append(self.path if os.path.isdir(self.path) else os.path.dirname(self.path))
        for media_path in (getattr(self.pic_show_layout, 'path', ''),
                           getattr(self.video_show_layout, 'path', '')):
            if media_path:
                candidates.append(os.path.dirname(media_path))
        candidates.append(os.path.expanduser('~'))
        for item in candidates:
            if item and os.path.isdir(item):
                return item
        return ''

    def _open_collect_dialog(self, mode):
        """打开归集参数弹框 → 选保存目录 → 启动后台归集线程。"""
        dialog = CollectDialog(self, mode=mode, default_root=self._collect_default_root())
        if dialog.exec_() != QDialog.Accepted:
            return
        params = dialog.params()

        dest_dir = pick_directory(self, '选择归集保存目录')
        if not dest_dir:
            return

        if mode == 'rating':
            paths, skipped = self._collect_rating_paths(
                params.get('min_rating', 1), params.get('kind', 'all'))
            if not paths:
                show_info(self, '归集', '没有符合条件的已评分媒体（文件可能已被移动或删除）。')
                return
            limit = int(params.get('limit') or 0)
            if limit > 0 and len(paths) > limit:
                skipped += len(paths) - limit
                paths = paths[:limit]
            params['paths'] = paths
            params['skipped'] = skipped

        self._run_collect(params, dest_dir)

    def _collect_rating_paths(self, min_rating, kind):
        """评分模式：查库 → 校验文件仍存在 → 类型过滤 → 去重，返回 (paths, skipped)。"""
        paths = []
        skipped = 0
        seen = set()
        for path, _rating in self.rating_manager.list_rated(min_rating):
            if not path or not os.path.isfile(path):
                skipped += 1
                continue
            if not matches_kind(path, kind):
                skipped += 1
                continue
            key = os.path.normcase(os.path.abspath(path))
            if key in seen:
                skipped += 1
                continue
            seen.add(key)
            paths.append(path)
        return paths, skipped

    def _run_collect(self, params, dest_dir):
        """启动归集线程（扫描与拷贝都在后台，避免 GUI 卡死）。"""
        if self.collect_thread is not None and self.collect_thread.isRunning():
            show_info(self, '归集', '已有归集任务在运行，请等待完成。')
            return

        progress = ProgressDialog(self, '归集', '正在准备…', 1)
        progress.show()

        thread = CollectThread(params, dest_dir, parent=self)
        thread.progress.connect(
            lambda done, total, text: self._on_collect_progress(progress, done, total, text))
        thread.completed.connect(lambda stats: self._on_collect_completed(stats, progress))
        thread.failed.connect(lambda message: self._on_collect_failed(message, progress))
        progress.canceled.connect(thread.cancel)

        self.collect_thread = thread
        self.notice('归集中：' + dest_dir)
        thread.start()

    @staticmethod
    def _on_collect_progress(progress, done, total, text):
        if total and total > 0:
            progress.setMaximum(total)
            progress.setValue(min(done, total))
        if text:
            progress.setLabelText(text)

    def _on_collect_completed(self, stats, progress):
        progress.setValue(progress.maximum())
        progress.close()
        self.collect_thread = None

        copied = stats.get('copied', 0)
        lines = ['归集完成：拷贝 %d 个文件到' % copied, stats.get('dest', '')]
        if stats.get('skipped'):
            lines.append('跳过 %d 个（类型不符 / 文件已不存在 / 重复 / 超出数量）' % stats['skipped'])
        if stats.get('failed'):
            lines.append('失败 %d 个' % stats['failed'])
        if stats.get('cancelled'):
            lines.append('任务已被取消（已拷贝的文件保留）')
        errors = stats.get('errors') or []
        if errors:
            lines.append('')
            lines.append('前几个错误：')
            lines.extend(errors[:5])
        show_info(self, '归集', '\n'.join(lines))
        self.notice('归集完成：%d 个文件 → %s' % (copied, stats.get('dest', '')))

    def _on_collect_failed(self, message, progress):
        progress.close()
        self.collect_thread = None
        logger.error('归集失败: ' + message)
        show_error(self, '归集', '归集失败：\n' + message)
        self.notice('归集失败：' + message)
