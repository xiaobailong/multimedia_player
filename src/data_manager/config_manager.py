from src.data_manager.sqlite3_client import Sqlite3Client

import time
from loguru import logger


class ConfigManager:

    def __init__(self, *args, **kwargs):
        self.sqlite3Client = Sqlite3Client()

        table = 'create table IF NOT EXISTS config(key string,value string,create_time string,update_time string)'

        self.sqlite3Client.exeUpdate(table)

    def add(self, key, value):
        key_query_sql = "SELECT count(0) as ccount from config where key='" + key + "'"
        cursor = self.sqlite3Client.exeQuery(key_query_sql)
        for row in cursor:
            self.ccount = row[0]

        if self.ccount == 0:
            current_time = time.strftime("%Y-%m-%d %H:%M:%S")
            sqlInsert = "insert into config(key,value,create_time,update_time) values('" + key + "','" + value + "','" + current_time + "','" + current_time + "')"
            self.sqlite3Client.exeUpdate(sqlInsert)
        else:
            logger.info("配置已存在！！！")

    def get(self, key):
        query_sql = "SELECT value from config where key='" + key + "'"
        cursor = self.sqlite3Client.exeQuery(query_sql)
        for row in cursor:
            return row[0]

    def exist(self, key):
        key_query_sql = "SELECT count(0) as ccount from config where key='" + key + "'"
        cursor = self.sqlite3Client.exeQuery(key_query_sql)

        for row in cursor:
            self.ccount = row[0]

        if self.ccount == 0:
            return False
        else:
            return True

    def add_or_update(self, key, value):
        if not self.exist(key):
            self.add(key, value)
        else:
            self.update(key, value)

    def update(self, key, value):
        current_time = time.strftime("%Y-%m-%d %H:%M:%S")
        update_sql = "update config set value='" + value + "',update_time='" + current_time + "' where key='" + key + "'"
        self.sqlite3Client.exeUpdate(update_sql)

    def remove(self, key):
        sql_delete = "delete from config where key='" + key + "'"
        self.sqlite3Client.exeUpdate(sql_delete)
        vacuum_sql = "VACUUM"
        self.sqlite3Client.exeUpdate(vacuum_sql)


if __name__ == '__main__':
    config_manager = ConfigManager()

    # config_manager.add('a','b')
    config_manager.update('a', 'd')
    # value=config_manager.get('a')
    # print(value)
    # config_manager.remove('a')
