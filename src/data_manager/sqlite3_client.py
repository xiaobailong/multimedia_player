# -*- coding: utf-8 -*-

import apsw
from loguru import logger
from src.utils import get_db_path


class Sqlite3Client:

    def __init__(self, *args, **kwargs):
        db_path = get_db_path()
        self.conn = apsw.Connection(db_path)
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
