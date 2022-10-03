# -*- coding: utf-8 -*-

import sqlite3
from loguru import logger

class Sqlite3Client:

    conn = sqlite3.connect(':memory:')

    def __init__(self, *args, **kwargs):
        self.conn = sqlite3.connect('slideshow_player.db')

    def showData(self,sql):
        c = self.conn.cursor()
        cursor = c.execute(sql)
        for row in cursor:
            logger.info(row)

    def exeQuery(self,sql):
        c = self.conn.cursor()
        cursor = c.execute(sql)
        return cursor

    def exeUpdate(self,sql):
        c = self.conn.cursor()
        c.execute(sql)
        self.conn.commit()

    def close(self):
        self.conn.close()

if __name__ == '__main__':

    client = Sqlite3Client()

    # sqlCreateTable='create table people(id int primary key,name varcahr(10),address varcahr(50))'
    sqlInsert0='insert into people values(1,"李宁","Shenyang")'
    sqlInsert1 = 'insert into people values(2,"超人","克星")'
    sqlUpdate='UPDATE people set address = "shandong" where ID=1'
    # selectSql="SELECT id, name, address  from people"
    # selectSql="SELECT id, name, address  from people where id = (SELECT max(id)  from people)"
    # selectSql = "SELECT *  from history"

    selectSql = 'SELECT name FROM sqlite_master WHERE type = "table"'

    client.showData(selectSql)

    client.close()
