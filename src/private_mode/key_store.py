# -*- coding: utf-8 -*-
"""私密模式：与 privi 兼容的密钥包读写 + 本机密文索引。

密钥包格式完全对齐 privi（`key_backup_service.dart`，formatVersion = 2）：

    meta(key, value)                                  -- format/version/createdAt/...
    key_material(id=1, encryption_salt, kek BLOB, kek_source, created_at)
    media_keys(media_id, private_path, original_path, original_name, mime_type,
               is_video, size_bytes, width, height, duration_ms, date_added,
               date_taken, encrypted_dek, content_digest)

本机库在此基础上多了 3 列（file_name / local_path / updated_at）用于在 Windows
上按文件名匹配 privi 的 Android 路径；导出时只写 privi 的 14 列，保证对方可读。
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

# 本机表结构（media_keys 比私密包多 3 列，导出时忽略）
_LOCAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS key_material (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  encryption_salt TEXT,
  kek BLOB NOT NULL,
  kek_source TEXT NOT NULL,
  created_at TEXT NOT NULL
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

MEDIA_COLUMNS = (
    'media_id', 'private_path', 'file_name', 'local_path', 'original_path',
    'original_name', 'mime_type', 'is_video', 'size_bytes', 'width', 'height',
    'duration_ms', 'date_added', 'date_taken', 'encrypted_dek',
    'content_digest', 'updated_at',
)


class KeyStoreError(Exception):
    """密钥库读写失败。"""


def utc_iso(moment=None):
    """privi 用 `DateTime.toIso8601String()`（UTC，毫秒 + Z）。"""
    moment = moment or datetime.now(timezone.utc)
    return moment.strftime('%Y-%m-%dT%H:%M:%S.') + ('%03d' % (moment.microsecond // 1000)) + 'Z'


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
    """本机私密密钥库（SQLite / apsw），同时负责 privi 密钥包的导入导出。"""

    FORMAT_TAG = 'privi-key-backup'
    FORMAT_VERSION = 2
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
        if connection is None and not self._owns_connection:
            # 只在“用主库共享连接”时迁移；测试 / 批量线程的临时库不会碰真实数据
            _migrate_legacy_db(self.conn)
        logger.info(f'私密密钥库: {self.db_path}')

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



    # ────────────────────── privi 密钥包：读取 / 导入 ──────────────────────

    def inspect_package(self, file_path):
        """只读检查密钥包，返回摘要 dict；不是 privi 包时返回 None。"""
        package = self._read_package(file_path)
        return package['summary'] if package else None

    def import_package(self, file_path, overwrite_key=False):
        """导入 privi 密钥包（v2 SQLite / v1 JSON）。

        :return: {ok, reason, message, summary, imported, updated, skipped}
        """
        package = self._read_package(file_path)
        if package is None:
            return {'ok': False, 'reason': 'malformed',
                    'message': '不是可识别的 privi 密钥包（支持 v2 .db 与 v1 JSON）'}
        if package['unsupported_version']:
            return {'ok': False, 'reason': 'unsupportedVersion',
                    'summary': package['summary'],
                    'message': '密钥包版本 %s 高于本程序支持的 %d，拒绝导入'
                               % (package['summary'].get('version'), self.FORMAT_VERSION)}

        material = self.key_material()
        key_conflict = bool(material and material['kek'] != package['kek'])
        if key_conflict and not overwrite_key:
            return {'ok': False, 'reason': 'key_conflict',
                    'summary': package['summary'],
                    'message': '本机已存在另一把不同的密钥，继续导入会覆盖它，'
                               '导致本机此前加密的文件无法再解密。'}

        try:
            self.save_key_material(package['kek'], package['salt'], 'imported',
                                   package['created_at'] or utc_iso())
        except Exception as e:
            logger.error(f'写入密钥失败: {e}')
            return {'ok': False, 'reason': 'failed', 'message': str(e)}

        imported = updated = skipped = 0
        for row in package['rows']:
            try:
                result = self._import_media_row(row)
            except Exception as e:
                logger.warning(f'导入媒体密钥记录失败: {e}')
                result = 'skipped'
            if result == 'imported':
                imported += 1
            elif result == 'updated':
                updated += 1
            else:
                skipped += 1

        logger.info(f'密钥包导入完成: 新增={imported} 更新={updated} 跳过={skipped}')
        return {'ok': True, 'reason': 'imported', 'imported': imported,
                'updated': updated, 'skipped': skipped, 'summary': package['summary']}

    def _import_media_row(self, row):
        private_path = (row.get('private_path') or '').strip()
        original_name = (row.get('original_name') or '').strip()
        if not original_name and private_path:
            original_name = os.path.basename(private_path.replace('\\', '/'))
        if not original_name:
            return 'skipped'
        file_name = os.path.basename(private_path.replace('\\', '/')) or original_name
        dek = (row.get('encrypted_dek') or '').strip()
        media_id = (row.get('media_id') or '').strip() or uuid.uuid4().hex

        same_id = _exec_dicts(self.conn, 'SELECT * FROM media_keys WHERE media_id = ?', (media_id,))
        if same_id:
            current = same_id[0]
            # 本机已有 DEK 时不覆盖：文件可能在本包之后重新加密过，旧 DEK 已不匹配
            if (current.get('encrypted_dek') or '') or not dek:
                return 'skipped'
            self.conn.execute(
                'UPDATE media_keys SET encrypted_dek = ?, updated_at = ? WHERE media_id = ?',
                (dek, utc_iso(), media_id),
            )
            return 'updated'

        same_name = _exec_dicts(self.conn, 'SELECT * FROM media_keys WHERE file_name = ?', (file_name,))
        if same_name:
            target = same_name[0]
            if dek and not (target.get('encrypted_dek') or ''):
                self.conn.execute(
                    'UPDATE media_keys SET encrypted_dek = ?, updated_at = ? WHERE media_id = ?',
                    (dek, utc_iso(), target['media_id']),
                )
                return 'updated'
            return 'skipped'

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
        )
        return 'imported'



    def _read_package(self, file_path):
        if not file_path or not os.path.isfile(file_path):
            return None
        try:
            with open(file_path, 'rb') as f:
                head = f.read(16)
        except OSError as e:
            logger.warning(f'读取密钥包失败: {e}')
            return None
        if head.startswith(b'SQLite format 3\x00'):
            return self._read_sqlite_package(file_path)
        if head[:1] == b'{':
            return self._read_legacy_json(file_path)
        return None

    def _read_sqlite_package(self, file_path):
        conn = None
        try:
            conn = apsw.Connection(file_path, flags=apsw.SQLITE_OPEN_READONLY)
            tables = {row[0] for row in _exec_rows(
                conn, "SELECT name FROM sqlite_master WHERE type = 'table'")}
            if 'meta' not in tables or 'key_material' not in tables:
                logger.warning('密钥包缺少 meta / key_material 表')
                return None
            meta = {row['key']: row['value'] for row in _exec_dicts(
                conn, 'SELECT key, value FROM meta')}
            if meta.get('format') != self.FORMAT_TAG:
                logger.warning('密钥包 format 不是 %s: %s' % (self.FORMAT_TAG, meta.get('format')))
                return None
            try:
                version = int(meta.get('version') or 0)
            except (TypeError, ValueError):
                version = 0
            if version <= 0:
                logger.warning('密钥包 version 非法')
                return None
            key_rows = _exec_dicts(
                conn, 'SELECT encryption_salt, kek FROM key_material LIMIT 1')
            if not key_rows:
                logger.warning('密钥包没有 key_material 记录')
                return None
            kek = key_rows[0].get('kek')
            if isinstance(kek, memoryview):
                kek = bytes(kek)
            if not kek or len(kek) != self.KEK_BYTES:
                logger.warning('密钥包里的 KEK 不是 %d 字节' % self.KEK_BYTES)
                return None
            rows = []
            if version <= self.FORMAT_VERSION and 'media_keys' in tables:
                rows = _exec_dicts(conn, 'SELECT * FROM media_keys')
            salt = key_rows[0].get('encryption_salt')
            summary = {
                'version': version,
                'sqlite': True,
                'created_at': meta.get('createdAt'),
                'file_count': len(rows),
                'encrypted_file_count': sum(
                    1 for r in rows if (r.get('encrypted_dek') or '')),
                'has_salt': bool(salt),
            }
            return {
                'kek': bytes(kek),
                'salt': salt,
                'rows': rows,
                'summary': summary,
                'created_at': meta.get('createdAt'),
                'unsupported_version': version > self.FORMAT_VERSION,
            }
        except Exception as e:
            logger.warning(f'读取 SQLite 密钥包失败: {e}')
            return None
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

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
            'version': version,
            'sqlite': False,
            'created_at': data.get('createdAt'),
            'file_count': 0,
            'encrypted_file_count': 0,
            'has_salt': bool(data.get('encryptionSalt')),
        }
        if version > self.FORMAT_VERSION:
            return {'kek': b'', 'salt': None, 'rows': [], 'summary': summary,
                    'created_at': None, 'unsupported_version': True}
        raw_kek = data.get('kek')
        if isinstance(raw_kek, str):
            try:
                kek = base64.b64decode(raw_kek)
            except Exception:
                return None
        elif isinstance(raw_kek, list):
            kek = bytes(raw_kek)
        else:
            return None
        if len(kek) != self.KEK_BYTES:
            return None
        return {'kek': kek, 'salt': data.get('encryptionSalt'), 'rows': [],
                'summary': summary, 'created_at': data.get('createdAt'),
                'unsupported_version': False}



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

