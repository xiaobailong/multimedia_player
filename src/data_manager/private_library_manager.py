# -*- coding: utf-8 -*-
"""私密库目录标记（本机表 `private_library_dir`）。

为什么不放 `config`：标记是「一组目录」，之前存成一整个 JSON 字符串，既不好查，
也被 `ConfigManager` 字符串拼 SQL 的写法限制（路径里有单引号就炸）。
单独一张表 + 参数化 SQL，增删就是一条语句（`ADR-028`）。

语义：被标记的目录（含其子目录）视为「全是密文」——
树里显示 `[私密库]`，加载幻灯片 / 视频列表时自动走解密分支。
"""
from loguru import logger

from src.data_manager.sqlite3_client import Sqlite3Client


class PrivateLibraryManager:
    """私密库目录标记的增删查。"""

    TABLE = 'private_library_dir'

    def __init__(self):
        self.db_client = Sqlite3Client()
        self._init_table()

    def _init_table(self):
        self.db_client.exeUpdate(
            "CREATE TABLE IF NOT EXISTS private_library_dir ("
            "  path TEXT PRIMARY KEY NOT NULL,"
            "  create_time TEXT NOT NULL DEFAULT (datetime('now','localtime'))"
            ")")
        logger.debug('私密库标记表已初始化')

    def list_dirs(self):
        """返回被标记的目录（按标记时间升序）；读不出来时返回空列表。"""
        try:
            cursor = self.db_client.exeQuery(
                'SELECT path FROM private_library_dir ORDER BY create_time, path')
            return [row[0] for row in cursor if row and row[0]]
        except Exception as e:
            logger.warning(f'读取私密库标记失败: {e}')
            return []

    def contains(self, path):
        if not path:
            return False
        try:
            cursor = self.db_client.exeQuery(
                'SELECT 1 FROM private_library_dir WHERE path = ? LIMIT 1', (path,))
            return cursor.fetchone() is not None
        except Exception as e:
            logger.warning(f'查询私密库标记失败 {path}: {e}')
            return False

    def add(self, path):
        self.db_client.exeUpdate(
            'INSERT OR IGNORE INTO private_library_dir(path) VALUES(?)', (path,))

    def remove(self, path):
        self.db_client.exeUpdate(
            'DELETE FROM private_library_dir WHERE path = ?', (path,))
