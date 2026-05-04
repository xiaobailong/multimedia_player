# -*- coding: utf-8 -*-
"""
播放位置数据管理器：统一管理视频播放位置的保存和加载
"""
import os
from loguru import logger
from src.data_manager.sqlite3_client import Sqlite3Client


class PositionManager:
    """视频播放位置管理器"""

    def __init__(self):
        self.db_client = Sqlite3Client()
        self._init_table()

    def _init_table(self):
        """创建播放位置记忆表（如果不存在）"""
        sql = """CREATE TABLE IF NOT EXISTS video_play_position (
            file_path TEXT PRIMARY KEY NOT NULL,
            position INTEGER NOT NULL,
            duration INTEGER NOT NULL,
            update_time TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        )"""
        self.db_client.exeUpdate(sql)
        logger.debug("播放位置表已初始化")

    def save_position(self, file_path: str, position: int, duration: int):
        """
        保存指定文件的播放位置。
        前 5 秒（5000ms）的位置不保存，避免保存启动阶段的 0 位置。
        
        Args:
            file_path: 视频文件路径
            position: 当前播放位置（毫秒）
            duration: 视频总时长（毫秒）
        """
        if not file_path or not os.path.exists(file_path):
            return
        if position <= 5000:  # 前 5 秒不保存
            return
        if duration <= 0:
            return

        # 使用参数化查询，避免 SQL 注入
        sql = """INSERT OR REPLACE INTO video_play_position (file_path, position, duration, update_time)
                 VALUES (?, ?, ?, datetime('now','localtime'))"""
        try:
            self.db_client.exeUpdate(sql, (file_path, position, duration))
        except Exception as e:
            logger.warning(f"保存播放位置失败 ({file_path}): {e}")

    def load_position(self, file_path: str) -> int:
        """
        加载指定文件的上次播放位置。
        
        Args:
            file_path: 视频文件路径
            
        Returns:
            上次播放位置（毫秒），无记录时返回 0
        """
        if not file_path:
            return 0

        sql = "SELECT position, duration FROM video_play_position WHERE file_path = ?"
        try:
            cursor = self.db_client.exeQuery(sql, (file_path,))
            row = cursor.fetchone()
            if row:
                # 验证保存的位置不超过视频时长
                pos, dur = row[0], row[1]
                if 0 < pos <= dur:
                    return pos
                logger.debug(f"播放位置无效（{pos}/{dur}），忽略")
            else:
                logger.debug(f"未找到播放位置记录: {file_path}")
        except Exception as e:
            logger.warning(f"加载播放位置失败 ({file_path}): {e}")
        return 0

    def delete_position(self, file_path: str):
        """删除指定文件的播放位置记录"""
        if not file_path:
            return
        try:
            self.db_client.exeUpdate("DELETE FROM video_play_position WHERE file_path = ?", (file_path,))
            logger.debug(f"已删除播放位置记录: {file_path}")
        except Exception as e:
            logger.warning(f"删除播放位置失败 ({file_path}): {e}")

    def delete_all_positions(self):
        """清空所有播放位置记录"""
        try:
            self.db_client.exeUpdate("DELETE FROM video_play_position")
            logger.debug("已清空所有播放位置记录")
        except Exception as e:
            logger.warning(f"清空播放位置失败: {e}")