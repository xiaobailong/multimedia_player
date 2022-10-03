from src.data_manager.Sqlite3Client import Sqlite3Client
# from Sqlite3Client import Sqlite3Client

import time
from loguru import logger

class DataManager:
    sqlite3Client = Sqlite3Client()
    currentId = 0

    def __init__(self, *args, **kwargs):

        self.sqlite3Client = Sqlite3Client()

        historyCreateTable = 'create table IF NOT EXISTS history(id integer  primary key autoincrement,file_path varcahr(256),size integer ,current_index integer ,create_time timestamp,update_time timestamp)'
        collectCreateTable = 'create table IF NOT EXISTS collect(id integer  primary key autoincrement,group_id integer,file_path varcahr(256),create_time timestamp,update_time timestamp)'
        groupCreateTable = 'create table IF NOT EXISTS group_info(group_id integer  primary key autoincrement,group_name varcahr(256),create_time timestamp,update_time timestamp)'

        self.sqlite3Client.exeUpdate(historyCreateTable)
        self.sqlite3Client.exeUpdate(collectCreateTable)
        self.sqlite3Client.exeUpdate(groupCreateTable)

        self.initGroup()

    def saveCollect(self, path, group_id):
        idQuerySql = 'SELECT count(0)  from collect where file_path="' + path + '" and group_id=' + str(group_id)
        cursor = self.sqlite3Client.exeQuery(idQuerySql)
        for row in cursor:
            self.groupCount = row[0]

        if self.groupCount == 0:
            t = time.time()
            t_ms = int(t * 1000)
            sqlInsert = 'insert into collect (file_path,group_id,create_time,update_time) values("' + path + '",' + str(group_id) + ',' + str(t_ms) + ',' + str(t_ms) + ')'
            self.sqlite3Client.exeUpdate(sqlInsert)
        else:
            logger.info("分组内已存在此文件！！！")

    def saveInputHistory(self, path, size):
        t = time.time()
        t_ms = int(t * 1000)
        sqlInsert = 'insert into history (file_path,size,current_index,create_time,update_time) values("' + path + '",' + str(size) + ',0,' + str(t_ms) + ',' + str(t_ms) + ')'
        self.sqlite3Client.exeUpdate(sqlInsert)
        idQuerySql = 'SELECT max(id)  from history'
        cursor = self.sqlite3Client.exeQuery(idQuerySql)
        for row in cursor:
            self.currentId = row[0]

    def initGroup(self):
        t = time.time()
        t_ms = int(t * 1000)
        idQuerySql = 'SELECT count(0)  from group_info'
        cursor = self.sqlite3Client.exeQuery(idQuerySql)
        for row in cursor:
            self.groupCount = row[0]
        if self.groupCount == 0:
            originInsert = 'insert into group_info (group_name,create_time,update_time) values("origin",' + str(t_ms) + ',' + str(t_ms) + ')'
            favouriteInsert = 'insert into group_info (group_name,create_time,update_time) values("favourite",' + str(t_ms) + ',' + str(t_ms) + ')'
            self.sqlite3Client.exeUpdate(originInsert)
            self.sqlite3Client.exeUpdate(favouriteInsert)

    def saveIndex(self, currentIndex):
        t = time.time()
        t_ms = int(t * 1000)
        sqlUpdate = 'UPDATE history set current_index=' + str(currentIndex) + ',update_time=' + str(t_ms) + ' where id=' + str(self.currentId)
        self.sqlite3Client.exeUpdate(sqlUpdate)

    def showData(self, tableName):
        sql = "SELECT *  from " + tableName
        logger.info(sql)
        self.sqlite3Client.showData(sql)

    def showTables(self):
        sql = "SELECT name FROM  sqlite_schema WHERE type ='table' AND  name NOT LIKE 'sqlite_%'"
        logger.info(sql)
        self.sqlite3Client.showData(sql)

    def deleteData(self, id):
        sqlDelete = 'delete from history where id=' + str(id)
        self.sqlite3Client.exeUpdate(sqlDelete)


if __name__ == '__main__':
    dataManager = DataManager()
    # dataManager.saveHistory("test",10)
    # for i in range(6,15):
    #     dataManager.deleteData(i)

    # dataManager.deleteData(15)
    # dataManager.saveCollect("test", 2)
    dataManager.showTables()
    dataManager.showData("history")
    dataManager.showData("collect")
    dataManager.showData("group_info")
