# -*- coding: utf-8 -*-
"""媒体评分数据管理器：按「文件内容指纹」保存图片 / 视频的 1~5 星评分。

为什么不用文件路径做主键：
    文件被移动到别的目录、或者被改名后路径就变了，按路径存的评分会全部失效。
    这里用内容指纹（`src.utils.utils.file_fingerprint`：大小 + 首尾各 1MB 的 blake2b）
    作为主键，移动 / 改名后仍然能命中同一条记录。

表结构（player.db，独立表，不影响既有表）::

    media_rating(
        fingerprint TEXT PRIMARY KEY,   -- 内容指纹
        rating      INTEGER NOT NULL,   -- 1~5
        media_type  TEXT,               -- image / video
        last_path   TEXT,               -- 最近一次见到的路径（便于排查）
        file_size   INTEGER,
        create_time TEXT,
        update_time TEXT
    )
"""
import os

from loguru import logger

from src.data_manager.sqlite3_client import Sqlite3Client
from src.utils.utils import file_fingerprint


class RatingManager:
    """图片 / 视频评分管理器（按内容指纹索引）。"""

    RATING_MIN = 1
    RATING_MAX = 5

    def __init__(self):
        self.db_client = Sqlite3Client()
        # path -> (size, mtime_ns, fingerprint)：同一文件重复读盘只算一次
        self._fingerprint_cache = {}
        self._init_table()

    def _init_table(self):
        """创建评分表（如果不存在）。"""
        sql = """CREATE TABLE IF NOT EXISTS media_rating (
            fingerprint TEXT PRIMARY KEY NOT NULL,
            rating INTEGER NOT NULL,
            media_type TEXT,
            last_path TEXT,
            file_size INTEGER,
            create_time TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            update_time TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        )"""
        self.db_client.exeUpdate(sql)
        # 便于按路径排查「这份文件现在的评分是多少」
        self.db_client.exeUpdate(
            "CREATE INDEX IF NOT EXISTS idx_media_rating_last_path ON media_rating(last_path)")
        logger.debug("媒体评分表已初始化")

    # ------------------------------------------------------------------
    #  指纹
    # ------------------------------------------------------------------
    def fingerprint(self, path):
        """取文件内容指纹（带缓存；文件大小 / mtime 变化时重新计算）。"""
        if not path or not os.path.isfile(path):
            return ''
        try:
            stat = os.stat(path)
        except OSError as e:
            logger.warning(f'读取文件信息失败 {path}: {e}')
            return ''

        cached = self._fingerprint_cache.get(path)
        if cached and cached[0] == stat.st_size and cached[1] == stat.st_mtime_ns:
            return cached[2]

        value = file_fingerprint(path)
        if value:
            self._fingerprint_cache[path] = (stat.st_size, stat.st_mtime_ns, value)
        return value

    def forget(self, path):
        """丢弃某个路径的指纹缓存（文件被删除 / 替换后调用）。"""
        self._fingerprint_cache.pop(path, None)

    # ------------------------------------------------------------------
    #  评分读写
    # ------------------------------------------------------------------
    def get_rating(self, path):
        """按路径取评分：先算内容指纹再查表；没有记录返回 None。"""
        value = self.fingerprint(path)
        if not value:
            return None
        return self.get_rating_by_fingerprint(value)

    def get_rating_by_fingerprint(self, fingerprint):
        """按内容指纹取评分；没有记录返回 None。"""
        if not fingerprint:
            return None
        try:
            cursor = self.db_client.exeQuery(
                "SELECT rating FROM media_rating WHERE fingerprint = ?", (fingerprint,))
            row = cursor.fetchone()
            return int(row[0]) if row else None
        except Exception as e:
            logger.warning(f'读取评分失败: {e}')
            return None

    def set_rating(self, path, rating, media_type=''):
        """保存评分（1~5），返回实际写入的评分；失败返回 None。

        同一份文件（指纹相同）再次评分时只更新记录，并刷新 `last_path`，
        这样文件换目录后表里记录的位置也会跟着更新。
        """
        try:
            rating = int(rating)
        except (TypeError, ValueError):
            logger.warning(f'非法评分值: {rating!r}')
            return None
        rating = max(self.RATING_MIN, min(self.RATING_MAX, rating))

        value = self.fingerprint(path)
        if not value:
            logger.warning(f'无法计算文件指纹，跳过评分: {path}')
            return None

        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0

        try:
            cursor = self.db_client.exeQuery(
                "SELECT rating FROM media_rating WHERE fingerprint = ?", (value,))
            exists = cursor.fetchone() is not None
            if exists:
                self.db_client.exeUpdate(
                    """UPDATE media_rating
                       SET rating = ?, media_type = ?, last_path = ?, file_size = ?,
                           update_time = datetime('now','localtime')
                       WHERE fingerprint = ?""",
                    (rating, media_type, path, size, value))
            else:
                self.db_client.exeUpdate(
                    """INSERT INTO media_rating (fingerprint, rating, media_type, last_path, file_size)
                       VALUES (?, ?, ?, ?, ?)""",
                    (value, rating, media_type, path, size))
        except Exception as e:
            logger.warning(f'保存评分失败 ({path}): {e}')
            return None
        return rating

    def delete_rating(self, path):
        """删除某个文件的评分记录（按内容指纹）。"""
        value = self.fingerprint(path)
        if not value:
            return False
        try:
            self.db_client.exeUpdate(
                "DELETE FROM media_rating WHERE fingerprint = ?", (value,))
            return True
        except Exception as e:
            logger.warning(f'删除评分失败 ({path}): {e}')
            return False

    def rating_count(self):
        """已评分文件数量（状态栏 / 排查用）。"""
        try:
            cursor = self.db_client.exeQuery("SELECT COUNT(*) FROM media_rating")
            row = cursor.fetchone()
            return int(row[0]) if row else 0
        except Exception as e:
            logger.warning(f'统计评分数量失败: {e}')
            return 0

    def list_rated(self, min_rating=1):
        """按评分从高到低返回 [(最近路径, 评分)]，供「按评分归集」使用。

        注意：返回的是**最后一次见到的路径**，文件可能已被移动 / 删除，
        调用方需要自己校验 `os.path.isfile`。
        """
        try:
            cursor = self.db_client.exeQuery(
                """SELECT last_path, rating FROM media_rating
                   WHERE rating >= ? AND last_path IS NOT NULL AND last_path <> ''
                   ORDER BY rating DESC, update_time DESC""",
                (int(min_rating),))
            return [(row[0], int(row[1])) for row in cursor]
        except Exception as e:
            logger.warning(f'读取评分列表失败: {e}')
            return []
