# -*- coding: utf-8 -*-

import apsw
from loguru import logger
from src.utils.utils import get_db_path


class Sqlite3Client:

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, *args, **kwargs):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        db_path = get_db_path()
        self.conn = apsw.Connection(db_path)
        # 私密密钥表也在这个库里，批量线程会另开一条连接并发写：
        # 让 SQLite 等待一会儿，而不是立刻抛 database is locked（ADR-028 / PIT-018）
        try:
            self.conn.execute('PRAGMA busy_timeout = 5000')
        except apsw.Error as e:
            logger.warning(f'设置 busy_timeout 失败: {e}')
        logger.info(f"数据库路径: {db_path}")

    def showData(self, sql):
        c = self.conn.cursor()
        cursor = c.execute(sql)
        for row in cursor:
            logger.info(row)

    def exeQuery(self, sql, params=None):
        c = self.conn.cursor()
        if params:
            cursor = c.execute(sql, params)
        else:
            cursor = c.execute(sql)
        return cursor

    def exeUpdate(self, sql, params=None):
        c = self.conn.cursor()
        if params:
            c.execute(sql, params)
        else:
            c.execute(sql)
        # apsw 没有 commit() 方法，需要显式执行 COMMIT 语句提交事务
        # 如果是 DDL（如 CREATE TABLE IF NOT EXISTS 表已存在）可能无活动事务，忽略错误
        try:
            self.conn.execute("COMMIT")
        except apsw.SQLError:
            pass

    def close(self):
        self.conn.close()


if __name__ == '__main__':
    client = Sqlite3Client()

    # sqlCreateTable='create table people(id int primary key,name varcahr(10),address varcahr(50))'
    sqlInsert0 = 'insert into people values(1,"李宁","Shenyang")'
    sqlInsert1 = 'insert into people values(2,"超人","克星")'
    sqlUpdate = 'UPDATE people set address = "shandong" where ID=1'
    # selectSql="SELECT id, name, address  from people"
    # selectSql="SELECT id, name, address  from people where id = (SELECT max(id)  from people)"
    # selectSql = "SELECT *  from history"

    selectSql = 'SELECT name FROM sqlite_master WHERE type = "table"'

    client.showData(selectSql)

    client.close()