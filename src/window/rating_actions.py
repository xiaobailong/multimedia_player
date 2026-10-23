# -*- coding: utf-8 -*-
"""媒体评分（数字键 1~5）：按内容指纹写库并刷新状态栏。"""
import os


class RatingActionsMixin:
    """评分相关的窗口动作。"""

    @staticmethod
    def _rating_stars(rating):
        """把 1~5 分渲染成 ★★★☆☆；未评分返回「—」。"""
        if not rating:
            return '—'
        rating = max(1, min(5, int(rating)))
        return '★' * rating + '☆' * (5 - rating)

    def current_media(self):
        """返回当前正在显示 / 播放的媒体 (路径, 类型)；没有则返回 ('', '')。"""
        if self.video_show_qwidget.isVisible():
            path = getattr(self.video_show_layout, 'path', '') or ''
            if path:
                return path, 'video'
        if self.pic_show_qwidget.isVisible():
            path = getattr(self.pic_show_layout, 'path', '') or ''
            if path:
                return path, 'image'
        return '', ''

    def refresh_rating_status(self, path=None):
        """刷新状态栏右侧的评分显示（切换图片 / 视频、评分后调用）。"""
        label = getattr(self, 'ratingLabel', None)
        if label is None:
            return
        if path is None:
            path = self.current_media()[0]
        rating = self.rating_manager.get_rating(path) if path else None
        if rating:
            label.setText('评分：%s（%d 星）' % (self._rating_stars(rating), rating))
            label.setToolTip('当前文件已评分 %d 星（按内容指纹保存，移动 / 改名后仍保留）' % rating)
        else:
            label.setText('评分：—')
            label.setToolTip('按数字键 1~5 为当前图片 / 视频评分'
                             '（按内容指纹保存，移动 / 改名后仍保留）')

    def _apply_rating(self, stars):
        """数字键 1~5：给当前图片 / 视频打分并写入数据库。"""
        path, media_type = self.current_media()
        if not path:
            self.notice('当前没有可评分的图片或视频')
            return
        if not os.path.isfile(path):
            self.notice('文件不存在，无法评分：' + path)
            return

        rating = self.rating_manager.set_rating(path, stars, media_type)
        if rating is None:
            self.notice('评分保存失败：无法读取文件内容')
            return

        self.refresh_rating_status(path)
        kind = '图片' if media_type == 'image' else '视频'
        self.notice('已为%s评分：%s（%d 星）— %s'
                    % (kind, self._rating_stars(rating), rating, os.path.basename(path)))
