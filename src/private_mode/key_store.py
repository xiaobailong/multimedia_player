# -*- coding: utf-8 -*-
"""私密模式：密钥环 / 目录密钥绑定 / 保险库数据与密钥包读写 + 本机密文索引。

对外支持 **两种 privi 数据文件**（靠 `meta.format` 区分，扩展名都是 `.db`）：

1. `privi-vault-data`（当前，「保险库数据」，privi ADR-049 / ADR-053）
   单个 SQLite 容器，容器版本 `meta.version = 1`、记录布局 `meta.manifestVersion = 6`：

       meta(key, value)
       media(id, position, file_name, ..., encrypted_dek, encryption_key_id, private_path, ...)
       albums(...) / album_groups(...) / memberships(...)
       encryption_keys(id, position, kek TEXT(base64), fingerprint, created_at, label, salt,
                       is_default)                 -- 密钥环（多把 KEK）
       app_settings(key, value)

2. `privi-key-backup`（旧「密钥包」，formatVersion = 2 / 也可读 v1 JSON）
   `meta` + `key_material(id=1)` + `media_keys(14 列)`，只有一把 KEK。

本机库（`player.db`）在此之上多出：

    vault_keys        密钥环（id = k_ + sha256(kek)[:16]，由密钥字节推导，与 privi 一致）
    vault_dir_key     目录 → 密钥绑定（不同私密库目录可以用不同密钥）
    media_keys.encryption_key_id
                      这条记录的 DEK 是哪把 KEK 包的（老记录启动时按默认密钥回填）
    media_keys 另有 file_name / local_path / updated_at 三列，用于在 Windows 上按文件名
    匹配 privi 的 Android 路径

导出时两种格式都只写 privi 定义的表 / 列，保证对方可读。
"""

import base64
import json
import os
import uuid
from datetime import datetime, timezone

import apsw
from loguru import logger

from src.data_manager.sqlite3_client import Sqlite3Client
from src.private_mode import privi_crypto
from src.utils.utils import get_db_path, get_private_key_db_path

# `ADR-028`：密钥表并入主库 player.db；批量线程与 UI 线程各有一条 apsw 连接，
# 同时写时让 SQLite 等待而不是立刻抛 database is locked。
DB_BUSY_TIMEOUT_MS = 5000

# 本机表结构（media_keys 比 privi 的两套格式都多几列，导出时忽略）
_LOCAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS key_material (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  encryption_salt TEXT,
  kek BLOB NOT NULL,
  kek_source TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS vault_keys (
  id TEXT PRIMARY KEY NOT NULL,
  kek BLOB NOT NULL,
  fingerprint TEXT,
  label TEXT,
  salt TEXT,
  created_at TEXT,
  is_default INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS vault_dir_key (
  path TEXT PRIMARY KEY NOT NULL,
  key_id TEXT NOT NULL,
  create_time TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS media_keys (
  media_id TEXT PRIMARY KEY NOT NULL,
  private_path TEXT NOT NULL,
  file_name TEXT,
  local_path TEXT,
  original_path TEXT,
  original_name TEXT NOT NULL,
  mime_type TEXT,
  is_video INTEGER NOT NULL DEFAULT 0,
  size_bytes INTEGER NOT NULL DEFAULT 0,
  width INTEGER,
  height INTEGER,
  duration_ms INTEGER,
  date_added INTEGER,
  date_taken INTEGER,
  encrypted_dek TEXT,
  content_digest TEXT,
  encryption_key_id TEXT,
  updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_media_keys_file_name ON media_keys (file_name);
CREATE INDEX IF NOT EXISTS idx_media_keys_local_path ON media_keys (local_path);
"""

# 导出用：与 privi 一字不差的三张表
_PACKAGE_SCHEMA = """
CREATE TABLE meta (
  key TEXT PRIMARY KEY NOT NULL,
  value TEXT
);
CREATE TABLE key_material (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  encryption_salt TEXT,
  kek BLOB NOT NULL,
  kek_source TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE media_keys (
  media_id TEXT PRIMARY KEY NOT NULL,
  private_path TEXT NOT NULL,
  original_path TEXT,
  original_name TEXT NOT NULL,
  mime_type TEXT,
  is_video INTEGER NOT NULL DEFAULT 0,
  size_bytes INTEGER NOT NULL DEFAULT 0,
  width INTEGER,
  height INTEGER,
  duration_ms INTEGER,
  date_added INTEGER,
  date_taken INTEGER,
  encrypted_dek TEXT,
  content_digest TEXT
);
CREATE INDEX idx_media_keys_private_path ON media_keys (private_path);
"""

# 保险库数据导出用：与 privi `vault_backup_database.dart` 的 `_schemaSql` 一字不差。
# albums / album_groups / memberships / app_settings 本程序不产生内容，只建空表
# （privi 的读取器按表名查询，缺表会直接报 malformed）。
_VAULT_SCHEMA = """
CREATE TABLE meta (
  key TEXT PRIMARY KEY NOT NULL,
  value TEXT
);
CREATE TABLE media (
  id TEXT PRIMARY KEY NOT NULL,
  position INTEGER NOT NULL,
  file_name TEXT NOT NULL,
  thumbnail_name TEXT,
  sha256 TEXT,
  byte_length INTEGER,
  original_path TEXT,
  source_platform TEXT,
  source_library_id TEXT,
  source_removal_pending INTEGER NOT NULL DEFAULT 0,
  content_digest TEXT,
  original_name TEXT,
  mime_type TEXT,
  is_video INTEGER,
  width INTEGER,
  height INTEGER,
  duration_ms INTEGER,
  rating INTEGER,
  date_added TEXT,
  date_taken TEXT,
  size_bytes INTEGER,
  deleted_at TEXT,
  encrypted_dek TEXT,
  encryption_key_id TEXT,
  private_path TEXT,
  thumbnail_path TEXT,
  play_count INTEGER,
  last_played_at TEXT
);
CREATE TABLE albums (
  id TEXT PRIMARY KEY NOT NULL,
  position INTEGER NOT NULL,
  name TEXT,
  is_system INTEGER NOT NULL DEFAULT 1,
  cover_media_id TEXT,
  created_at TEXT,
  system_kind TEXT,
  pinned_at TEXT,
  rating INTEGER,
  sort_index INTEGER,
  group_id TEXT
);
CREATE TABLE album_groups (
  id TEXT PRIMARY KEY NOT NULL,
  position INTEGER NOT NULL,
  name TEXT,
  created_at TEXT,
  sort_index INTEGER
);
CREATE TABLE memberships (
  album_id TEXT NOT NULL,
  media_id TEXT NOT NULL,
  added_at TEXT,
  position INTEGER NOT NULL,
  PRIMARY KEY (album_id, media_id)
);
CREATE TABLE encryption_keys (
  id TEXT PRIMARY KEY NOT NULL,
  position INTEGER NOT NULL,
  kek TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  created_at TEXT,
  label TEXT,
  salt TEXT,
  is_default INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE app_settings (
  key TEXT PRIMARY KEY NOT NULL,
  value TEXT
);
"""

MEDIA_COLUMNS = (
    'media_id', 'private_path', 'file_name', 'local_path', 'original_path',
    'original_name', 'mime_type', 'is_video', 'size_bytes', 'width', 'height',
    'duration_ms', 'date_added', 'date_taken', 'encrypted_dek',
    'content_digest', 'encryption_key_id', 'updated_at',
)

# 保险库数据 `media` 表的列顺序（与 _VAULT_SCHEMA 一致，导出时按它拼 INSERT）
VAULT_MEDIA_COLUMNS = (
    'id', 'position', 'file_name', 'thumbnail_name', 'sha256', 'byte_length',
    'original_path', 'source_platform', 'source_library_id',
    'source_removal_pending', 'content_digest', 'original_name', 'mime_type',
    'is_video', 'width', 'height', 'duration_ms', 'rating', 'date_added',
    'date_taken', 'size_bytes', 'deleted_at', 'encrypted_dek',
    'encryption_key_id', 'private_path', 'thumbnail_path', 'play_count',
    'last_played_at',
)


class KeyStoreError(Exception):
    """密钥库读写失败。"""


def utc_iso(moment=None):
    """privi 用 `DateTime.toIso8601String()`（UTC，毫秒 + Z）。"""
    moment = moment or datetime.now(timezone.utc)
    return moment.strftime('%Y-%m-%dT%H:%M:%S.') + ('%03d' % (moment.microsecond // 1000)) + 'Z'


def _norm_path(path):
    """比较 / 去重用的规范路径（Windows 下统一小写、去掉 `..` 与尾部斜杠）。"""
    if not path:
        return ''
    try:
        return os.path.normcase(os.path.normpath(os.path.abspath(path)))
    except (OSError, ValueError):
        return os.path.normcase(path)


def _as_bytes(value):
    """apsw 取 BLOB 可能给 memoryview；统一转 bytes，方便切分 / 比较。"""
    if value is None:
        return None
    if isinstance(value, memoryview):
        return bytes(value)
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, bytes):
        return value
    return None


def _iso_to_millis(value):
    """把 privi 保险库数据里的 ISO-8601 文本换成毫秒时间戳（本机库口径）。

    已经是数字（旧密钥包里的 `date_added` 就是 INTEGER 毫秒）时原样返回；
    解析不了就返回 None，不让一条脏数据拖垮整次导入。
    """
    if value is None or value == '':
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    try:
        moment = datetime.fromisoformat(text.replace('Z', '+00:00'))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    try:
        return int(moment.timestamp() * 1000)
    except (OSError, OverflowError, ValueError):
        return None


def _millis_to_iso(value):
    """毫秒时间戳 → privi 的 ISO-8601 文本；已经是文本时原样写回。"""
    if value is None or value == '':
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        return text if not text.isdigit() else _millis_to_iso(int(text))
    try:
        millis = int(value)
    except (TypeError, ValueError):
        return None
    try:
        return utc_iso(datetime.fromtimestamp(millis / 1000.0, timezone.utc))
    except (OSError, OverflowError, ValueError):
        return None


def _as_int(value, default=0):
    """宽松取整：`int(None)` / `int('abc')` 都回落到 default（导入时不让脏数据炸整包）。"""
    if value is None or value == '':
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default


def _decode_kek(value):
    """`encryption_keys.kek` / `key_material.kek` → 32 字节 bytes；非法返回 None。"""
    if value is None:
        return None
    raw = _as_bytes(value)
    if raw is not None:
        return raw if len(raw) == privi_crypto.KEK_LEN else None
    if isinstance(value, (list, tuple)):
        raw = bytes(int(item) & 0xFF for item in value)
        return raw if len(raw) == privi_crypto.KEK_LEN else None
    if isinstance(value, str):
        try:
            raw = base64.b64decode(value.strip())
        except Exception:
            return None
        return raw if len(raw) == privi_crypto.KEK_LEN else None
    return None


def _exec_dicts(conn, sql, params=()):
    cursor = conn.cursor()
    cursor.execute(sql, params)
    # apsw 只在语句执行期间提供 description，取完行就会抛 ExecutionCompleteError，
    # 所以必须先拿列名再迭代结果。
    try:
        names = [d[0] for d in (cursor.description or [])]
    except Exception:
        names = []
    result = []
    for row in cursor:
        result.append(dict(zip(names, row)))
    return result


def _exec_rows(conn, sql, params=()):
    cursor = conn.cursor()
    cursor.execute(sql, params)
    return cursor.fetchall()


def _run_script(conn, script):
    """apsw 的 execute 一次只能跑一条语句，这里按 ';' 拆开逐条执行。

    本地 schema 与导出 schema 都是纯 DDL，语句里不含 ';'，拆分是安全的。
    """
    for statement in script.split(';'):
        statement = statement.strip()
        if statement:
            conn.execute(statement)


def _tune_connection(conn):
    """设置 busy_timeout（多条连接写同一个库时等待而不是立刻报 locked）。"""
    try:
        conn.execute('PRAGMA busy_timeout = %d' % DB_BUSY_TIMEOUT_MS)
    except Exception as e:
        logger.warning(f'设置 busy_timeout 失败: {e}')


def _migrate_legacy_db(conn):
    """把旧的 `data/private_keys.db` 一次性并进主库（表名不变），旧文件改名为 `.bak`。

    幂等：`INSERT OR IGNORE`（`key_material.id` / `media_keys.media_id` 是主键），
    中途崩溃下次再跑一遍即可；迁移失败时**保留旧文件**，绝不删数据。
    """
    legacy_path = get_private_key_db_path()
    if not os.path.isfile(legacy_path):
        return
    if os.path.normcase(os.path.abspath(legacy_path)) == \
            os.path.normcase(os.path.abspath(get_db_path())):
        return
    try:
        conn.execute('ATTACH DATABASE ? AS legacy', (legacy_path,))
    except Exception as e:
        logger.error(f'挂载旧私密密钥库失败 {legacy_path}: {e}')
        return

    copied = False
    try:
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM legacy.sqlite_master WHERE type='table'")}
        if 'key_material' in tables:
            conn.execute(
                'INSERT OR IGNORE INTO key_material '
                '(id, encryption_salt, kek, kek_source, created_at) '
                'SELECT id, encryption_salt, kek, kek_source, created_at '
                'FROM legacy.key_material')
        if 'media_keys' in tables:
            legacy_columns = {row[1] for row in conn.execute(
                'PRAGMA legacy.table_info(media_keys)')}
            columns = [name for name in MEDIA_COLUMNS if name in legacy_columns]
            if columns:
                joined = ', '.join(columns)
                conn.execute('INSERT OR IGNORE INTO media_keys (%s) '
                             'SELECT %s FROM legacy.media_keys' % (joined, joined))
        copied = True
    except Exception as e:
        logger.error(f'迁移旧私密密钥库失败（旧文件保留，未删除）：{e}')
    finally:
        try:
            conn.execute('DETACH DATABASE legacy')
        except Exception:
            pass

    if not copied:
        return
    backup_path = legacy_path + '.bak'
    try:
        if os.path.exists(backup_path):
            os.remove(backup_path)
        os.replace(legacy_path, backup_path)
        logger.info(f'旧私密密钥库已并入 player.db，原文件备份为 {backup_path}')
    except OSError as e:
        logger.warning(f'旧私密密钥库已并入主库，但改名失败: {e}')


class PrivateKeyStore:
    """本机私密密钥库（SQLite / apsw）：密钥环 + 目录绑定 + privi 数据文件导入导出。"""

    FORMAT_TAG = 'privi-key-backup'          # 旧「密钥包」（单把 KEK）
    FORMAT_VERSION = 2
    VAULT_FORMAT_TAG = 'privi-vault-data'    # 当前「保险库数据」（privi ADR-053）
    VAULT_CONTAINER_VERSION = 1
    VAULT_MANIFEST_VERSION = 6
    VAULT_FILE_PREFIX = 'privi-vault-'
    KEK_BYTES = privi_crypto.KEK_LEN
    FILE_EXTENSION = '.db'

    def __init__(self, db_path=None, connection=None):
        """默认使用主库 `player.db` 的**共享连接**（`Sqlite3Client`）。

        - `connection=`：复用调用方已有连接（上层已持有连接时）；
        - `db_path=`：自建连接（**批量线程必须走这个** —— apsw 连接不能跨线程使用）；
        - 都不传：主库共享连接，并把旧的 `data/private_keys.db` 一次性并进来（`ADR-028`）。

        密钥表（`key_material` / `media_keys`）与配置、评分、播放位置同在 `player.db`，
        不再单独占一个数据库文件。
        """
        self._owns_connection = False
        if connection is not None:
            self.conn = connection
            self.db_path = db_path or get_db_path()
        elif db_path is not None:
            self.db_path = db_path
            parent = os.path.dirname(self.db_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            self.conn = apsw.Connection(self.db_path)
            self._owns_connection = True
        else:
            self.db_path = get_db_path()
            self.conn = Sqlite3Client().conn

        _tune_connection(self.conn)
        _run_script(self.conn, _LOCAL_SCHEMA)
        self._ensure_columns()
        if connection is None and not self._owns_connection:
            # 只在“用主库共享连接”时迁移；测试 / 批量线程的临时库不会碰真实数据
            _migrate_legacy_db(self.conn)
        self._bootstrap_key_ring()
        logger.info(f'私密密钥库: {self.db_path}')

    # ────────────────────────── 结构迁移 ──────────────────────────

    def _ensure_columns(self):
        """老库补列：`media_keys.encryption_key_id`（支持多密钥之前没有这一列）。

        `CREATE TABLE IF NOT EXISTS` 不会给已存在的表加列，所以必须显式检查并 ALTER。
        """
        try:
            columns = {row[1] for row in self.conn.execute('PRAGMA table_info(media_keys)')}
        except Exception as e:
            logger.warning(f'读取 media_keys 表结构失败: {e}')
            return
        if 'encryption_key_id' not in columns:
            try:
                self.conn.execute('ALTER TABLE media_keys ADD COLUMN encryption_key_id TEXT')
                logger.info('已给 media_keys 补上 encryption_key_id 列')
            except Exception as e:
                logger.error(f'给 media_keys 补列失败: {e}')

    def _bootstrap_key_ring(self):
        """让 `key_material`（旧：唯一一把 KEK）与 `vault_keys`（新：密钥环）保持一致。

        三种现场都要覆盖：
        1. 老库只有 `key_material` → 把它登记成密钥环里的默认密钥；
        2. 新库只有 `vault_keys`（例如只导入了保险库数据）→ 回写 `key_material`；
        3. 两者都有但没标默认 → 把 `key_material` 那把标成默认。

        最后给「有 DEK 但没有 key id」的老记录补上默认密钥 id：多密钥场景下
        状态显示和「这把文件用哪把密钥」才准确（没有 id 时解密仍会逐个试）。
        """
        try:
            material = self.key_material()
            keys = self.list_keys()
            if material is not None:
                key_id = privi_crypto.key_id_for(material['kek'])
                if not any(key['id'] == key_id for key in keys):
                    self.register_key(
                        material['kek'],
                        label='本机密钥',
                        salt=material.get('encryption_salt'),
                        created_at=material.get('created_at'),
                    )
                    keys = self.list_keys()
                if not any(key.get('is_default') for key in keys):
                    self.set_default_key(key_id)
            elif keys:
                default = next((k for k in keys if k.get('is_default')), keys[0])
                key = self.get_key(default['id'])
                if key is not None:
                    self.save_key_material(
                        key['kek'], key.get('salt'), 'imported',
                        key.get('created_at') or utc_iso())
        except Exception as e:
            logger.error(f'初始化密钥环失败: {e}')
            return

        default_id = self.default_key_id()
        if not default_id:
            return
        try:
            self.conn.execute(
                "UPDATE media_keys SET encryption_key_id = ? "
                "WHERE (encryption_key_id IS NULL OR encryption_key_id = '') "
                "AND encrypted_dek IS NOT NULL AND encrypted_dek <> ''",
                (default_id,))
        except Exception as e:
            logger.warning(f'回填 media_keys.encryption_key_id 失败: {e}')

    # ────────────────────────── 密钥环（多把 KEK） ──────────────────────────

    def list_keys(self):
        """密钥环摘要（**不含 KEK 明文字节**，避免被日志 / 界面顺手打出去）。"""
        rows = _exec_dicts(
            self.conn,
            'SELECT id, fingerprint, label, salt, created_at, is_default '
            'FROM vault_keys ORDER BY is_default DESC, created_at, id')
        return [{
            'id': row['id'],
            'fingerprint': row.get('fingerprint') or '',
            'label': row.get('label') or '',
            'salt': row.get('salt'),
            'created_at': row.get('created_at'),
            'is_default': bool(row.get('is_default')),
        } for row in rows]

    def get_key(self, key_id):
        """按 id 取一把完整密钥（含 `kek` bytes）；不存在返回 None。"""
        if not key_id:
            return None
        rows = _exec_dicts(self.conn, 'SELECT * FROM vault_keys WHERE id = ?', (key_id,))
        if not rows:
            return None
        row = rows[0]
        kek = _as_bytes(row.get('kek'))
        if not kek or len(kek) != self.KEK_BYTES:
            return None
        row['kek'] = kek
        row['is_default'] = bool(row.get('is_default'))
        return row

    def register_key(self, kek, label=None, salt=None, created_at=None, is_default=False):
        """登记一把 KEK，返回它的 id（幂等）。

        id 由密钥字节推导（`k_` + sha256 前 16 位），所以：
        - 重复登记同一把密钥不会产生第二条记录；
        - 导入别人导出的密钥环时本机默认密钥不受影响（除非显式 `set_default_key`）。
        """
        if not kek or len(kek) != self.KEK_BYTES:
            raise KeyStoreError('KEK 长度必须是 %d 字节' % self.KEK_BYTES)
        kek = bytes(kek)
        key_id = privi_crypto.key_id_for(kek)
        if self.get_key(key_id) is not None:
            return key_id
        self.conn.execute(
            'INSERT INTO vault_keys (id, kek, fingerprint, label, salt, created_at, is_default) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            (key_id, kek, privi_crypto.key_fingerprint(kek), label,
             salt, created_at or utc_iso(), 1 if is_default else 0))
        return key_id

    def default_key(self):
        """当前默认密钥（含 `kek`）；没有返回 None。"""
        rows = _exec_dicts(
            self.conn,
            'SELECT id FROM vault_keys ORDER BY is_default DESC, created_at, id LIMIT 1')
        if not rows:
            return None
        return self.get_key(rows[0]['id'])

    def default_key_id(self):
        key = self.default_key()
        return key['id'] if key else None

    def set_default_key(self, key_id):
        """把某把密钥设为默认（没有目录绑定的新文件都用它加密）。"""
        key = self.get_key(key_id)
        if key is None:
            raise KeyStoreError('密钥不存在: %s' % key_id)
        self.conn.execute('UPDATE vault_keys SET is_default = 0')
        self.conn.execute('UPDATE vault_keys SET is_default = 1 WHERE id = ?', (key_id,))
        # 旧代码 / 旧版本只看 key_material，这里保持同步
        self.save_key_material(key['kek'], key.get('salt'), 'imported',
                               key.get('created_at') or utc_iso())
        logger.info(f'默认密钥已切换为 {key_id}')

    def ensure_default_key(self):
        """有默认密钥就返回 KEK；否则生成一把随机密钥并登记为默认。"""
        key = self.default_key()
        if key is not None:
            return key['kek']
        keys = self.list_keys()
        if keys:
            self.set_default_key(keys[0]['id'])
            return self.default_key()['kek']
        kek = privi_crypto.generate_dek()
        salt = base64.b64encode(os.urandom(16)).decode('ascii')
        created = utc_iso()
        self.register_key(kek, label='本机密钥', salt=salt,
                          created_at=created, is_default=True)
        self.save_key_material(kek, salt, 'imported', created)
        logger.info('已生成本机随机私密密钥，可通过「密钥 → 导出保险库数据」备份')
        return kek

    # ────────────────────────── 目录密钥绑定 ──────────────────────────

    def bind_directory(self, directory, key_id):
        """把某个目录（含其子目录）绑定到一把密钥。

        加密时按「最长前缀匹配」选密钥：`D:\\vaultA` 绑 key1、`D:\\vaultA\\kids` 绑 key2，
        则 `kids` 里的文件用 key2，`vaultA` 其余部分用 key1；没绑定的目录走默认密钥。
        """
        if not directory:
            raise KeyStoreError('目录不能为空')
        if self.get_key(key_id) is None:
            raise KeyStoreError('密钥不存在: %s' % key_id)
        path = os.path.normpath(os.path.abspath(directory))
        self.conn.execute(
            'INSERT OR REPLACE INTO vault_dir_key (path, key_id, create_time) VALUES (?, ?, ?)',
            (path, key_id, utc_iso()))
        logger.info(f'目录密钥绑定: {path} → {key_id}')

    def unbind_directory(self, directory):
        """解除某个目录的密钥绑定（只删绑定，不删密钥、不删文件）。"""
        path = os.path.normpath(os.path.abspath(directory))
        self.conn.execute('DELETE FROM vault_dir_key WHERE path = ?', (path,))

    def list_directory_bindings(self):
        """所有目录绑定（附带密钥标签，方便界面直接显示）。"""
        rows = _exec_dicts(
            self.conn,
            'SELECT d.path, d.key_id, d.create_time, k.label, k.is_default '
            'FROM vault_dir_key d LEFT JOIN vault_keys k ON k.id = d.key_id '
            'ORDER BY d.path')
        return [{
            'path': row['path'],
            'key_id': row['key_id'],
            'create_time': row.get('create_time'),
            'label': row.get('label') or '',
            'is_default': bool(row.get('is_default')),
            'missing_key': row.get('label') is None,
        } for row in rows]

    def key_id_for_directory(self, path):
        """按最长前缀匹配返回该路径绑定的密钥 id；没有绑定返回 None。"""
        if not path:
            return None
        target = _norm_path(path)
        if not target:
            return None
        best_id = None
        best_len = -1
        for row in _exec_dicts(self.conn, 'SELECT path, key_id FROM vault_dir_key'):
            base = _norm_path(row['path'])
            if not base:
                continue
            if target == base or target.startswith(base + os.sep):
                if len(base) > best_len:
                    best_id = row['key_id']
                    best_len = len(base)
        if best_id and self.get_key(best_id) is None:
            return None
        return best_id

    def key_for_directory(self, path):
        """返回该路径绑定的完整密钥；没绑定 / 密钥已被删掉时返回 None。"""
        key_id = self.key_id_for_directory(path)
        return self.get_key(key_id) if key_id else None

    def key_for_encryption(self, path):
        """加密某个路径时该用哪把密钥：目录绑定 → 默认密钥（会自动生成）。

        :param path: 待加密文件（或目录）的路径
        :return: `{'id', 'kek', ...}`；永远有值
        """
        directory = path if os.path.isdir(path) else (os.path.dirname(path) or '.')
        bound = self.key_for_directory(directory)
        if bound is not None:
            return bound
        kek = self.ensure_default_key()
        key = self.get_key(privi_crypto.key_id_for(kek))
        if key is None:
            raise KeyStoreError('默认密钥登记失败')
        return key

    # ────────────────────────── 主密钥（KEK） ──────────────────────────

    def key_material(self):
        """返回 {encryption_salt, kek, kek_source, created_at} 或 None。"""
        rows = _exec_dicts(
            self.conn,
            'SELECT encryption_salt, kek, kek_source, created_at '
            'FROM key_material WHERE id = 1',
        )
        if not rows:
            return None
        row = rows[0]
        kek = row.get('kek')
        if isinstance(kek, memoryview):
            kek = bytes(kek)
        if not kek or len(kek) != self.KEK_BYTES:
            return None
        row['kek'] = bytes(kek)
        return row

    def save_key_material(self, kek, salt=None, source='imported', created_at=None):
        self.conn.execute(
            'INSERT OR REPLACE INTO key_material '
            '(id, encryption_salt, kek, kek_source, created_at) '
            'VALUES (1, ?, ?, ?, ?)',
            (salt, bytes(kek), source, created_at or utc_iso()),
        )

    def has_key(self):
        return self.key_material() is not None

    # ────────────────────────── 媒体索引 ──────────────────────────

    def find_media(self, file_path):
        """按绝对路径 → 文件名顺序查一条记录（privi 的私密路径是 Android 路径，
        拷到 Windows 后只能靠文件名对上）。"""
        path = os.path.normpath(os.path.abspath(file_path))
        rows = _exec_dicts(
            self.conn,
            'SELECT * FROM media_keys WHERE local_path = ? OR private_path = ? LIMIT 1',
            (path, path),
        )
        if rows:
            return rows[0]
        name = os.path.basename(path)
        rows = _exec_dicts(
            self.conn,
            'SELECT * FROM media_keys WHERE file_name = ? '
            "ORDER BY CASE WHEN encrypted_dek IS NULL OR encrypted_dek = '' THEN 1 ELSE 0 END LIMIT 1",
            (name,),
        )
        return rows[0] if rows else None

    def upsert_media(self, **fields):
        row = {column: None for column in MEDIA_COLUMNS}
        row.update({k: v for k, v in fields.items() if k in row})
        row['updated_at'] = row.get('updated_at') or utc_iso()
        placeholders = ', '.join('?' for _ in MEDIA_COLUMNS)
        self.conn.execute(
            'INSERT OR REPLACE INTO media_keys (%s) VALUES (%s)'
            % (', '.join(MEDIA_COLUMNS), placeholders),
            tuple(row[column] for column in MEDIA_COLUMNS),
        )
        return row

    def update_local_path(self, media_id, local_path, private_path=None):
        self.conn.execute(
            'UPDATE media_keys SET local_path = ?, private_path = ?, updated_at = ? '
            'WHERE media_id = ?',
            (local_path, private_path or local_path, utc_iso(), media_id),
        )

    def delete_media(self, media_id):
        if not media_id:
            return
        self.conn.execute('DELETE FROM media_keys WHERE media_id = ?', (media_id,))

    def list_media(self):
        return _exec_dicts(
            self.conn,
            'SELECT * FROM media_keys ORDER BY COALESCE(date_added, 0), media_id',
        )

    def count_encrypted(self):
        rows = _exec_rows(
            self.conn,
            "SELECT COUNT(1) FROM media_keys WHERE encrypted_dek IS NOT NULL AND encrypted_dek <> ''",
        )
        return int(rows[0][0]) if rows else 0

    def close(self):
        """只关自己开的连接；共享的 `player.db` 连接归 `Sqlite3Client` 管。"""
        if not self._owns_connection:
            return
        try:
            self.conn.close()
        except Exception:
            pass



    # ──────────── privi 数据文件（保险库数据 / 旧密钥包）：只读检查 + 导入 ────────────

    def inspect_package(self, file_path):
        """只读检查数据文件，返回摘要 dict；认不出来时返回 None。

        摘要里一定有 `kind`：`vault`（保险库数据）/ `key_package`（旧 .db 密钥包）
        / `legacy_json`（v1 JSON 密钥包），界面据此显示不同文案。
        """
        package = self._read_package(file_path)
        return package['summary'] if package else None

    def import_package(self, file_path, overwrite_key=False):
        """导入 privi 数据文件（保险库数据 / 旧密钥包 / 旧 JSON）。

        - 保险库数据：**密钥环整体登记**，本机默认密钥默认不动（多把密钥共存）；
        - 旧密钥包：只有一把 KEK，与本机默认不同时按 `overwrite_key` 决定是否切换；
        - 媒体记录：按「id → 本机密文文件名」匹配，已有 DEK 不覆盖。

        :return: {ok, reason, message, summary, kind, imported, updated, skipped, keys}
        """
        package = self._read_package(file_path)
        if package is None:
            return {'ok': False, 'reason': 'malformed',
                    'message': '不是可识别的 privi 数据文件'
                               '（支持「保险库数据」.db、旧版 .db 密钥包与 v1 JSON）'}
        summary = package['summary']
        if package['unsupported_version']:
            return {'ok': False, 'reason': 'unsupportedVersion', 'summary': summary,
                    'message': '%s 版本 %s 高于本程序支持的版本，拒绝导入'
                               % (summary.get('kind_label') or '数据文件',
                                  summary.get('container_version')
                                  or summary.get('manifest_version')
                                  or summary.get('version'))}

        try:
            added_keys = self._import_keys(package, overwrite_key)
        except KeyStoreError as e:
            return {'ok': False, 'reason': 'key_conflict', 'summary': summary,
                    'message': str(e)}
        except Exception as e:
            logger.error(f'写入密钥失败: {e}')
            return {'ok': False, 'reason': 'failed', 'summary': summary,
                    'message': str(e)}

        default_id = package.get('default_key_id')
        if default_id and self.get_key(default_id) is None:
            # 包里的 id 与密钥字节对不上（或这把密钥没导进来）：回落到本机默认密钥，
            # 不要把不存在的 id 写进记录（否则解密时只能靠逐把试）
            default_id = None
        if default_id is None:
            default_id = self.default_key_id()
        imported = updated = skipped = 0
        for row in package['rows']:
            try:
                result = self._import_media_row(row, default_key_id=default_id)
            except Exception as e:
                logger.warning(f'导入媒体密钥记录失败: {e}')
                result = 'skipped'
            if result == 'imported':
                imported += 1
            elif result == 'updated':
                updated += 1
            else:
                skipped += 1

        logger.info('数据文件导入完成: 类型=%s 新增密钥=%d 新增记录=%d 更新=%d 跳过=%d'
                    % (summary.get('kind'), added_keys, imported, updated, skipped))
        return {'ok': True, 'reason': 'imported', 'kind': summary.get('kind'),
                'imported': imported, 'updated': updated, 'skipped': skipped,
                'keys': added_keys, 'summary': summary}

    def _import_keys(self, package, overwrite_key):
        """把包里的密钥登记进密钥环；返回新增了几把。

        保险库数据带的是**密钥环**：全部登记，默认密钥只在「本机还没有」或
        `overwrite_key` 时才切换 —— 这样导入别人的密钥不会让本机已有文件失效。
        旧密钥包只有一把：与本机默认不同时沿用旧语义，先报 `key_conflict` 让用户确认。
        """
        keys = package.get('keys') or []
        if not keys:
            return 0
        before = len(self.list_keys())
        if package['kind'] == 'vault':
            # 关键：导入的密钥一律先按「非默认」登记，最后再显式选一个默认。
            # 否则包里 is_default=1 的行会和本机默认密钥并存（两条 is_default=1），
            # `default_key()` 可能挑到导入的那把，等于偷偷换掉了本机默认密钥。
            local_default_id = self.default_key_id()
            derived_ids = [privi_crypto.key_id_for(item['kek']) for item in keys]
            for item in keys:
                self.register_key(item['kek'],
                                  label=item.get('label') or '导入的密钥',
                                  salt=item.get('salt'),
                                  created_at=item.get('created_at'),
                                  is_default=False)
            wanted = (package.get('default_key_id') or '').strip()
            target_default = None
            if wanted and wanted in derived_ids:
                target_default = wanted
            elif wanted:
                # 包里记录的 id 与密钥字节对不上（版本/手改）：按行里标的 is_default 兜底
                target_default = None
            if target_default is None:
                index = next((i for i, item in enumerate(keys) if item.get('is_default')), 0)
                target_default = derived_ids[index]
            if overwrite_key or local_default_id is None:
                self.set_default_key(target_default)
            return len(self.list_keys()) - before

        # 旧密钥包：单把密钥
        kek = keys[0]['kek']
        material = self.key_material()
        if material is not None and material['kek'] != kek and not overwrite_key:
            raise KeyStoreError('本机已存在另一把不同的密钥，继续导入会覆盖默认密钥，'
                                '导致本机此前加密的文件无法再解密。')
        key_id = self.register_key(kek,
                                   label=keys[0].get('label') or '导入的密钥',
                                   salt=keys[0].get('salt'),
                                   created_at=keys[0].get('created_at'))
        if material is None or overwrite_key:
            self.set_default_key(key_id)
        return len(self.list_keys()) - before

    def _import_media_row(self, row, default_key_id=None):
        private_path = (row.get('private_path') or '').strip()
        original_name = (row.get('original_name') or '').strip()
        if not original_name and private_path:
            original_name = os.path.basename(private_path.replace('\\', '/'))
        if not original_name:
            return 'skipped'
        file_name = os.path.basename(private_path.replace('\\', '/')) or original_name
        dek = (row.get('encrypted_dek') or '').strip()
        media_id = (row.get('media_id') or '').strip() or uuid.uuid4().hex
        # privi 保险库数据里每条记录都带 encryption_key_id（ADR-050）；
        # 老格式没有这一列时按包里的默认密钥补，解密时才能直接命中。
        key_id = (row.get('encryption_key_id') or '').strip() or default_key_id

        same_id = _exec_dicts(self.conn, 'SELECT * FROM media_keys WHERE media_id = ?', (media_id,))
        if same_id:
            return self._merge_media_row(same_id[0], dek, key_id)

        same_name = _exec_dicts(self.conn, 'SELECT * FROM media_keys WHERE file_name = ?', (file_name,))
        if same_name:
            return self._merge_media_row(same_name[0], dek, key_id)

        self.upsert_media(
            media_id=media_id,
            private_path=private_path or file_name,
            file_name=file_name,
            local_path=None,
            original_path=row.get('original_path'),
            original_name=original_name,
            mime_type=row.get('mime_type'),
            is_video=1 if row.get('is_video') else 0,
            size_bytes=int(row.get('size_bytes') or 0),
            width=row.get('width'),
            height=row.get('height'),
            duration_ms=row.get('duration_ms'),
            date_added=row.get('date_added'),
            date_taken=row.get('date_taken'),
            encrypted_dek=dek or None,
            content_digest=row.get('content_digest'),
            encryption_key_id=key_id or None,
        )
        return 'imported'

    def _merge_media_row(self, current, dek, key_id):
        """已存在的记录：**不覆盖**已有 DEK（文件可能在本包之后重新加密过），只补缺的。"""
        media_id = current['media_id']
        if (current.get('encrypted_dek') or ''):
            if dek and key_id and not (current.get('encryption_key_id') or ''):
                self.conn.execute(
                    'UPDATE media_keys SET encryption_key_id = ?, updated_at = ? '
                    'WHERE media_id = ?',
                    (key_id, utc_iso(), media_id),
                )
                return 'updated'
            return 'skipped'
        if not dek:
            return 'skipped'
        self.conn.execute(
            'UPDATE media_keys SET encrypted_dek = ?, '
            'encryption_key_id = COALESCE(?, encryption_key_id), updated_at = ? '
            'WHERE media_id = ?',
            (dek, key_id, utc_iso(), media_id),
        )
        return 'updated'



    def _read_package(self, file_path):
        """读数据文件，返回统一结构（`kind` / `keys` / `rows` / `summary`）。"""
        if not file_path or not os.path.isfile(file_path):
            return None
        try:
            with open(file_path, 'rb') as f:
                head = f.read(16)
        except OSError as e:
            logger.warning(f'读取数据文件失败: {e}')
            return None
        if head.startswith(b'SQLite format 3\x00'):
            return self._read_sqlite_package(file_path)
        if head[:1] == b'{':
            return self._read_legacy_json(file_path)
        return None

    def _read_sqlite_package(self, file_path):
        """读 .db：按 `meta.format` 分派到「保险库数据」或旧「密钥包」。"""
        conn = None
        try:
            conn = apsw.Connection(file_path, flags=apsw.SQLITE_OPEN_READONLY)
            tables = {row[0] for row in _exec_rows(
                conn, "SELECT name FROM sqlite_master WHERE type = 'table'")}
            if 'meta' not in tables:
                logger.warning('数据文件缺少 meta 表')
                return None
            meta = {row['key']: row['value'] for row in _exec_dicts(
                conn, 'SELECT key, value FROM meta')}
            fmt = meta.get('format')
            if fmt == self.VAULT_FORMAT_TAG:
                return self._read_vault_container(conn, tables, meta)
            if fmt == self.FORMAT_TAG:
                return self._read_key_package(conn, tables, meta)
            logger.warning('数据文件的 format 不是 privi 格式: %s' % fmt)
            return None
        except Exception as e:
            logger.warning(f'读取 SQLite 数据文件失败: {e}')
            return None
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    def _read_vault_container(self, conn, tables, meta):
        """「保险库数据」容器（privi ADR-053）：meta + media + encryption_keys（+ 其它表）。"""
        container_version = _as_int(meta.get('version'))
        if container_version <= 0:
            logger.warning('保险库数据缺少合法的容器版本')
            return None
        manifest_version = _as_int(meta.get('manifestVersion'),
                                   self.VAULT_MANIFEST_VERSION) or self.VAULT_MANIFEST_VERSION

        keys = []
        if 'encryption_keys' in tables:
            for row in _exec_dicts(conn, 'SELECT * FROM encryption_keys ORDER BY position'):
                kek = _decode_kek(row.get('kek'))
                if kek is None:
                    logger.warning('保险库数据里有一把 KEK 不合法，已跳过')
                    continue
                keys.append({
                    'id': (row.get('id') or '').strip() or privi_crypto.key_id_for(kek),
                    'kek': kek,
                    'fingerprint': (row.get('fingerprint') or '').strip()
                                   or privi_crypto.key_fingerprint(kek),
                    'created_at': row.get('created_at'),
                    'label': (row.get('label') or '').strip() or None,
                    'salt': row.get('salt'),
                    'is_default': bool(row.get('is_default')),
                })

        default_key_id = (meta.get('defaultKeyId') or '').strip() or None
        if default_key_id is None and keys:
            default_key_id = next((k['id'] for k in keys if k['is_default']), keys[0]['id'])

        rows = []
        if 'media' in tables:
            for index, row in enumerate(_exec_dicts(conn, 'SELECT * FROM media ORDER BY position')):
                rows.append(self._normalize_vault_media_row(row, index))

        summary = {
            'kind': 'vault',
            'kind_label': '保险库数据',
            'version': container_version,
            'container_version': container_version,
            'manifest_version': manifest_version,
            'sqlite': True,
            'created_at': meta.get('exportedAt') or meta.get('verifiedAt'),
            'file_count': len(rows),
            'encrypted_file_count': sum(1 for r in rows if r.get('encrypted_dek')),
            'key_count': len(keys),
            'default_key_id': default_key_id,
            'has_salt': bool(meta.get('encryptionSalt')),
            'includes_media': meta.get('includesMedia') == '1',
        }
        return {
            'kind': 'vault',
            'keys': keys,
            'default_key_id': default_key_id,
            'rows': rows,
            'summary': summary,
            'unsupported_version': (container_version > self.VAULT_CONTAINER_VERSION
                                    or manifest_version > self.VAULT_MANIFEST_VERSION),
        }

    @staticmethod
    def _normalize_vault_media_row(row, index=0):
        """把 privi `media` 表的行收敛成本机的行口径（时间换成毫秒、补 file_name）。"""
        private_path = (row.get('private_path') or '').strip()
        file_name = (row.get('file_name') or '').strip()
        original_name = (row.get('original_name') or '').strip()
        if not private_path and file_name:
            private_path = file_name
        if not file_name and private_path:
            file_name = os.path.basename(private_path.replace('\\', '/'))
        return {
            'media_id': (row.get('id') or '').strip() or uuid.uuid4().hex,
            'position': index,
            'private_path': private_path,
            'original_path': row.get('original_path'),
            'original_name': original_name or file_name,
            'mime_type': row.get('mime_type'),
            'is_video': 1 if row.get('is_video') else 0,
            'size_bytes': _as_int(row.get('size_bytes')),
            'width': _as_int(row.get('width'), None),
            'height': _as_int(row.get('height'), None),
            'duration_ms': _as_int(row.get('duration_ms'), None),
            'date_added': _iso_to_millis(row.get('date_added')),
            'date_taken': _iso_to_millis(row.get('date_taken')),
            'encrypted_dek': (row.get('encrypted_dek') or '').strip(),
            'content_digest': row.get('content_digest'),
            'encryption_key_id': (row.get('encryption_key_id') or '').strip(),
        }

    def _read_key_package(self, conn, tables, meta):
        """旧「密钥包」（`privi-key-backup`）：只有一把 KEK。"""
        version = _as_int(meta.get('version'))
        if version <= 0:
            logger.warning('密钥包 version 非法')
            return None
        key_rows = _exec_dicts(conn, 'SELECT encryption_salt, kek FROM key_material LIMIT 1')
        if not key_rows:
            logger.warning('密钥包没有 key_material 记录')
            return None
        kek = _decode_kek(key_rows[0].get('kek'))
        if kek is None:
            logger.warning('密钥包里的 KEK 不是 %d 字节' % self.KEK_BYTES)
            return None
        rows = []
        if version <= self.FORMAT_VERSION and 'media_keys' in tables:
            rows = _exec_dicts(conn, 'SELECT * FROM media_keys')
        salt = key_rows[0].get('encryption_salt')
        key_id = privi_crypto.key_id_for(kek)
        summary = {
            'kind': 'key_package',
            'kind_label': '密钥包（旧格式）',
            'version': version,
            'sqlite': True,
            'created_at': meta.get('createdAt'),
            'file_count': len(rows),
            'encrypted_file_count': sum(1 for r in rows if (r.get('encrypted_dek') or '')),
            'key_count': 1,
            'default_key_id': key_id,
            'has_salt': bool(salt),
        }
        return {
            'kind': 'key_package',
            'keys': [{
                'id': key_id,
                'kek': kek,
                'fingerprint': privi_crypto.key_fingerprint(kek),
                'created_at': meta.get('createdAt'),
                'label': '导入的密钥',
                'salt': salt,
                'is_default': True,
            }],
            'default_key_id': key_id,
            'rows': rows,
            'summary': summary,
            'unsupported_version': version > self.FORMAT_VERSION,
        }

    def _read_legacy_json(self, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            logger.warning(f'读取 v1 JSON 密钥包失败: {e}')
            return None
        if not isinstance(data, dict) or data.get('format') != self.FORMAT_TAG:
            return None
        version = data.get('version')
        if not isinstance(version, int) or version <= 0:
            return None
        summary = {
            'kind': 'legacy_json',
            'kind_label': '密钥包（v1 JSON）',
            'version': version,
            'sqlite': False,
            'created_at': data.get('createdAt'),
            'file_count': 0,
            'encrypted_file_count': 0,
            'key_count': 1,
            'has_salt': bool(data.get('encryptionSalt')),
        }
        if version > self.FORMAT_VERSION:
            return {'kind': 'legacy_json', 'keys': [], 'default_key_id': None,
                    'rows': [], 'summary': summary, 'unsupported_version': True}
        raw_kek = data.get('kek')
        if isinstance(raw_kek, str):
            try:
                kek = base64.b64decode(raw_kek)
            except Exception:
                return None
        elif isinstance(raw_kek, list):
            try:
                kek = bytes(int(item) & 0xFF for item in raw_kek)
            except (TypeError, ValueError):
                return None
        else:
            return None
        if len(kek) != self.KEK_BYTES:
            return None
        key_id = privi_crypto.key_id_for(kek)
        summary['default_key_id'] = key_id
        return {
            'kind': 'legacy_json',
            'keys': [{
                'id': key_id,
                'kek': kek,
                'fingerprint': privi_crypto.key_fingerprint(kek),
                'created_at': data.get('createdAt'),
                'label': '导入的密钥',
                'salt': data.get('encryptionSalt'),
                'is_default': True,
            }],
            'default_key_id': key_id,
            'rows': [],
            'summary': summary,
            'unsupported_version': False,
        }



    # ────────────────────────── 导出（privi v2 格式） ──────────────────────────

    def suggested_file_name(self, moment=None):
        moment = moment or datetime.now(timezone.utc)
        return 'privi-key-%s%s' % (moment.strftime('%Y%m%d-%H%M%S'), self.FILE_EXTENSION)

    def export_package(self, directory, moment=None):
        """把本机 KEK + 文件名/DEK 映射写成 privi 可读的 SQLite 密钥包。

        :return: 生成的文件绝对路径
        """
        material = self.key_material()
        if material is None:
            raise KeyStoreError('尚未导入或生成密钥，无法导出')
        if not directory or not os.path.isdir(directory):
            raise KeyStoreError('导出目录不存在: %s' % directory)

        created = (moment or datetime.now(timezone.utc)).astimezone(timezone.utc)
        file_path = os.path.join(directory, self.suggested_file_name(created))
        if os.path.exists(file_path):
            os.remove(file_path)

        rows = self.list_media()
        encrypted_count = sum(1 for r in rows if (r.get('encrypted_dek') or ''))

        conn = None
        try:
            conn = apsw.Connection(file_path)
            conn.execute('PRAGMA journal_mode = DELETE')
            conn.execute('PRAGMA user_version = %d' % self.FORMAT_VERSION)
            _run_script(conn, _PACKAGE_SCHEMA)

            conn.execute('BEGIN')
            try:
                for key, value in (
                    ('format', self.FORMAT_TAG),
                    ('version', str(self.FORMAT_VERSION)),
                    ('createdAt', utc_iso(created)),
                    ('fileCount', str(len(rows))),
                    ('encryptedFileCount', str(encrypted_count)),
                    ('warning',
                     'Raw vault key plus per-file DEKs and filename mapping: together '
                     'with the vault folder it decrypts every file. Keep it offline '
                     'or in an encrypted cloud folder.'),
                ):
                    conn.execute('INSERT INTO meta (key, value) VALUES (?, ?)', (key, value))

                conn.execute(
                    'INSERT INTO key_material '
                    '(id, encryption_salt, kek, kek_source, created_at) '
                    'VALUES (1, ?, ?, ?, ?)',
                    (material.get('encryption_salt'), material['kek'],
                     material.get('kek_source') or 'imported', utc_iso(created)),
                )

                for row in rows:
                    private_path = row.get('local_path') or row.get('private_path') or ''
                    conn.execute(
                        'INSERT OR REPLACE INTO media_keys '
                        '(media_id, private_path, original_path, original_name, '
                        'mime_type, is_video, size_bytes, width, height, '
                        'duration_ms, date_added, date_taken, encrypted_dek, '
                        'content_digest) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                        (
                            row.get('media_id') or uuid.uuid4().hex,
                            private_path,
                            row.get('original_path'),
                            row.get('original_name') or os.path.basename(private_path),
                            row.get('mime_type'),
                            1 if row.get('is_video') else 0,
                            int(row.get('size_bytes') or 0),
                            row.get('width'),
                            row.get('height'),
                            row.get('duration_ms'),
                            row.get('date_added'),
                            row.get('date_taken'),
                            row.get('encrypted_dek'),
                            row.get('content_digest'),
                        ),
                    )
                conn.execute('COMMIT')
            except Exception:
                try:
                    conn.execute('ROLLBACK')
                except Exception:
                    pass
                raise
        except Exception:
            # 半截的 SQLite 文件仍然能打开，看起来像"导出成功"，必须删掉
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
                conn = None
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    pass
            raise
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

        logger.info(f'已导出 privi 兼容密钥包: {file_path}（{len(rows)} 条记录）')
        return file_path

    # ──────────────── 导出：保险库数据（privi-vault-*.db，privi ADR-053） ────────────────

    def suggested_vault_file_name(self, moment=None):
        """`privi-vault-YYYYMMDD-HHMMSS.db`（与 privi `_VaultBackupDatabaseCodec` 一致）。"""
        moment = (moment or datetime.now(timezone.utc)).astimezone(timezone.utc)
        return '%s%s%s' % (self.VAULT_FILE_PREFIX, moment.strftime('%Y%m%d-%H%M%S'),
                           self.FILE_EXTENSION)

    def _vault_media_values(self, row, index, default_key_id):
        """本机 media_keys 的一行 → privi `media` 表的一行（列见 VAULT_MEDIA_COLUMNS）。"""
        private_path = row.get('local_path') or row.get('private_path') or ''
        file_name = row.get('file_name') or os.path.basename(
            str(private_path).replace('\\', '/')) or ''
        original_name = row.get('original_name') or file_name
        key_id = (row.get('encryption_key_id') or '').strip()
        if not key_id and row.get('encrypted_dek'):
            # 老记录没记 key id：按导出时的默认密钥标注，privi 那边才解得开
            key_id = default_key_id
        return {
            'id': row.get('media_id') or uuid.uuid4().hex,
            'position': index,
            'file_name': file_name,
            'thumbnail_name': None,
            'sha256': None,
            'byte_length': None,
            'original_path': row.get('original_path'),
            'source_platform': None,
            'source_library_id': None,
            'source_removal_pending': 0,
            'content_digest': row.get('content_digest'),
            'original_name': original_name,
            'mime_type': row.get('mime_type'),
            'is_video': 1 if row.get('is_video') else 0,
            'width': row.get('width'),
            'height': row.get('height'),
            'duration_ms': row.get('duration_ms'),
            'rating': None,
            'date_added': _millis_to_iso(row.get('date_added')),
            'date_taken': _millis_to_iso(row.get('date_taken')),
            'size_bytes': _as_int(row.get('size_bytes'), None),
            'deleted_at': None,
            'encrypted_dek': row.get('encrypted_dek'),
            'encryption_key_id': key_id or None,
            'private_path': private_path,
            'thumbnail_path': None,
            'play_count': None,
            'last_played_at': None,
        }

    def export_vault_package(self, directory, moment=None):
        """把密钥环 + 密钥索引写成 privi 可导入的「保险库数据」SQLite 容器。

        与 privi `ADR-053` 对齐：`meta.format = privi-vault-data`、`meta.version = 1`、
        `meta.manifestVersion = 6`，表结构一字不差；`journal_mode = DELETE` 保证
        只有一个 `.db` 文件（不会留 `-wal` / `-shm` 兄弟文件）。

        albums / album_groups / memberships / app_settings 只建空表：本程序没有相册，
        也没有 privi 的设置项，写空表既能被 privi 正常读取，也不会污染对方的设置。

        :return: 生成的文件绝对路径
        """
        keys = self.list_keys()
        if not keys:
            raise KeyStoreError('尚未导入或生成密钥，无法导出')
        if not directory or not os.path.isdir(directory):
            raise KeyStoreError('导出目录不存在: %s' % directory)

        created = (moment or datetime.now(timezone.utc)).astimezone(timezone.utc)
        file_path = os.path.join(directory, self.suggested_vault_file_name(created))
        if os.path.exists(file_path):
            os.remove(file_path)

        default_key = self.default_key()
        default_key_id = default_key['id'] if default_key else keys[0]['id']

        # privi 的校验器要求「media.file_name 唯一」（它用文件名当引用键）：
        # 本机可能有多条记录指向同一个密文名（历史数据 / 手工改库），导出前必须去重，
        # 否则 privi 会判定 malformedManifest 整包拒收。
        # 去重时**优先保留带 encrypted_dek 的那条**（否则对方拿到的是打不开的空记录）。
        chosen = {}
        order = []
        skipped_duplicates = 0
        for row in self.list_media():
            private_path = row.get('local_path') or row.get('private_path') or ''
            file_name = row.get('file_name') or os.path.basename(
                str(private_path).replace('\\', '/'))
            if not file_name:
                skipped_duplicates += 1
                continue
            existing = chosen.get(file_name)
            if existing is None:
                chosen[file_name] = row
                order.append(file_name)
            elif not (existing.get('encrypted_dek') or '') \
                    and (row.get('encrypted_dek') or ''):
                chosen[file_name] = row
                skipped_duplicates += 1
            else:
                skipped_duplicates += 1
        if skipped_duplicates:
            logger.warning('导出时跳过 %d 条空文件名 / 重复文件名的记录（privi 要求文件名唯一）'
                           % skipped_duplicates)

        rows = [chosen[file_name] for file_name in order]
        encrypted_count = sum(1 for r in rows if (r.get('encrypted_dek') or ''))

        conn = None
        try:
            conn = apsw.Connection(file_path)
            conn.execute('PRAGMA journal_mode = DELETE')
            conn.execute('PRAGMA user_version = %d' % self.VAULT_CONTAINER_VERSION)
            _run_script(conn, _VAULT_SCHEMA)

            conn.execute('BEGIN')
            try:
                for key, value in (
                    ('format', self.VAULT_FORMAT_TAG),
                    ('version', str(self.VAULT_CONTAINER_VERSION)),
                    ('manifestVersion', str(self.VAULT_MANIFEST_VERSION)),
                    ('exportedAt', utc_iso(created)),
                    ('verifiedAt', utc_iso(created)),
                    ('itemCount', str(len(rows))),
                    ('totalBytes', '0'),
                    ('includesMedia', '0'),
                    ('mediaCount', str(len(rows))),
                    ('albumCount', '0'),
                    ('groupCount', '0'),
                    ('membershipCount', '0'),
                    ('encryptionKeyCount', str(len(keys))),
                    ('appSettingCount', '0'),
                    ('encryptionSalt', (default_key or {}).get('salt')),
                    ('defaultKeyId', default_key_id),
                    ('warning',
                     'Plaintext vault keys: anyone who has this file and the vault folder '
                     'can decrypt every media file. Keep it offline or in an encrypted '
                     'cloud folder.'),
                ):
                    if value is None:
                        continue
                    conn.execute('INSERT INTO meta (key, value) VALUES (?, ?)',
                                 (key, str(value)))

                placeholders = ', '.join('?' for _ in VAULT_MEDIA_COLUMNS)
                insert_sql = 'INSERT INTO media (%s) VALUES (%s)' % (
                    ', '.join(VAULT_MEDIA_COLUMNS), placeholders)
                for index, row in enumerate(rows):
                    values = self._vault_media_values(row, index, default_key_id)
                    conn.execute(insert_sql,
                                 tuple(values[column] for column in VAULT_MEDIA_COLUMNS))

                for position, item in enumerate(keys):
                    key = self.get_key(item['id'])
                    if key is None:
                        continue
                    conn.execute(
                        'INSERT INTO encryption_keys '
                        '(id, position, kek, fingerprint, created_at, label, salt, is_default) '
                        'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                        (item['id'], position,
                         base64.b64encode(key['kek']).decode('ascii'),
                         item.get('fingerprint') or privi_crypto.key_fingerprint(key['kek']),
                         item.get('created_at'), item.get('label'), item.get('salt'),
                         1 if item.get('is_default') else 0))
                conn.execute('COMMIT')
            except Exception:
                try:
                    conn.execute('ROLLBACK')
                except Exception:
                    pass
                raise
        except Exception:
            # 半截的 SQLite 文件仍然能打开，看起来像"导出成功"，必须删掉
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
                conn = None
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    pass
            raise
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

        logger.info('已导出 privi 保险库数据: %s（媒体 %d 条 / 密钥 %d 把，其中 %d 条带加密密钥）'
                    % (file_path, len(rows), len(keys), encrypted_count))
        return file_path

