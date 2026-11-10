# -*- coding: utf-8 -*-
"""私密模式自测（无 GUI）：保险库数据 v6 / 密钥环 / 多密钥 / 目录绑定 / 旧包兼容。

跑法（仓库根）：
    python scripts\\tools\\selftest_vault_data.py           # 跑完自动清理 tmp\\selftest_vault_data
    python scripts\\tools\\selftest_vault_data.py --keep    # 保留现场，便于用 SQLite 工具查看导出的 .db

为什么放在 scripts\\tools\\：这是「保险库数据导入导出」的回归判据
（见 memory-bank `ISSUE-016` / `ADR-029`），不是一次性的临时探针。
产物一律放仓库根 `tmp\\selftest_vault_data\\`（`.clinerules/tmp-files.md`），跑完删除。
"""
import base64
import os
import shutil
import sys

import apsw

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from src.private_mode import privi_crypto                      # noqa: E402
from src.private_mode.key_store import PrivateKeyStore        # noqa: E402
from src.private_mode.private_service import PrivateService    # noqa: E402

ROOT = os.path.join(PROJECT_ROOT, 'tmp', 'selftest_vault_data')
FAILS = []


def check(name, condition, detail=''):
    if condition:
        print('  PASS  %s' % name)
    else:
        print('  FAIL  %s  %s' % (name, detail))
        FAILS.append(name)


def main():
    if os.path.isdir(ROOT):
        shutil.rmtree(ROOT, ignore_errors=True)
    os.makedirs(ROOT)
    vault_a = os.path.join(ROOT, 'vaultA')
    kids = os.path.join(vault_a, 'kids')
    vault_b = os.path.join(ROOT, 'vaultB')
    for path in (vault_a, kids, vault_b):
        os.makedirs(path)

    # ---------- 1. 两把密钥 + 目录绑定 ----------
    print('[1] 密钥环与目录绑定')
    store = PrivateKeyStore(os.path.join(ROOT, 'player.db'))
    kek1 = store.ensure_default_key()
    key1_id = store.default_key_id()
    kek2 = privi_crypto.generate_dek()
    key2_id = store.register_key(kek2, label='第二把密钥', salt='salt2')
    check('默认密钥 id 由密钥推导', key1_id == privi_crypto.key_id_for(kek1), key1_id)
    check('密钥环有 2 把', len(store.list_keys()) == 2)
    store.bind_directory(vault_a, key1_id)
    store.bind_directory(kids, key2_id)
    store.bind_directory(vault_b, key2_id)
    check('最长前缀：vaultA 用 key1', store.key_id_for_directory(vault_a) == key1_id)
    check('最长前缀：vaultA\\kids 用 key2', store.key_id_for_directory(kids) == key2_id)
    check('最长前缀：文件路径也能匹配',
          store.key_id_for_directory(os.path.join(kids, 'x.mp4')) == key2_id)

    # ---------- 2. 按目录用不同密钥加密 ----------
    print('[2] 分目录加密')
    service = PrivateService(store=store, cache_dir=os.path.join(ROOT, 'cache'))
    sources = {}
    for path, payload in (
            (os.path.join(vault_a, 'a.jpg'), b'JPEG-A' * 100),
            (os.path.join(kids, 'b.mp4'), b'MP4-KIDS' * 200),
            (os.path.join(vault_b, 'c.jpg'), b'JPEG-C' * 100)):
        with open(path, 'wb') as fh:
            fh.write(payload)
        sources[path] = payload

    encrypted = {}
    for path in sources:
        new_path = service.encrypt_one(path)
        encrypted[path] = new_path
        check('加密后源文件已删除', not os.path.exists(path), path)
        check('密文存在', bool(new_path) and os.path.exists(new_path), str(new_path))

    def key_of(path):
        media = store.find_media(encrypted[path])
        return (media or {}).get('encryption_key_id')

    check('vaultA\\a.jpg 用 key1', key_of(os.path.join(vault_a, 'a.jpg')) == key1_id,
          str(key_of(os.path.join(vault_a, 'a.jpg'))))
    check('vaultA\\kids\\b.mp4 用 key2', key_of(os.path.join(kids, 'b.mp4')) == key2_id)
    check('vaultB\\c.jpg 用 key2', key_of(os.path.join(vault_b, 'c.jpg')) == key2_id)

    # ---------- 3. 播放前按需解密 ----------
    print('[3] 按需解密')
    for path, payload in sources.items():
        cache_path, display_name = service.resolve_playable(encrypted[path])
        with open(cache_path, 'rb') as fh:
            got = fh.read()
        check('解密内容一致 %s' % os.path.basename(path), got == payload,
              '%d != %d' % (len(got), len(payload)))

    # ---------- 4. 导出保险库数据（privi 容器） ----------
    print('[4] 导出 privi-vault-data')
    # 造一条「重复密文文件名」的脏记录：privi 要求 media.file_name 唯一，
    # 导出时必须自动跳过，否则对方的校验器会整包拒收（malformedManifest）。
    dup_source = encrypted[os.path.join(vault_b, 'c.jpg')]
    dup_media = store.find_media(dup_source) or {}
    store.upsert_media(media_id='dup-name-1', private_path=dup_source,
                       file_name=dup_media.get('file_name'), local_path=None,
                       original_name='dup.jpg')
    exported = store.export_vault_package(ROOT)
    check('文件名形如 privi-vault-*.db',
          os.path.basename(exported).startswith('privi-vault-')
          and exported.endswith('.db'), os.path.basename(exported))
    check('没有 -wal 兄弟文件', not os.path.exists(exported + '-wal'))

    conn = apsw.Connection(exported, flags=apsw.SQLITE_OPEN_READONLY)
    meta = {row[0]: row[1] for row in conn.execute('SELECT key, value FROM meta')}
    check('meta.format', meta.get('format') == 'privi-vault-data', str(meta.get('format')))
    check('meta.version 容器版本 1', meta.get('version') == '1', str(meta.get('version')))
    check('meta.manifestVersion 记录布局 6',
          meta.get('manifestVersion') == '6', str(meta.get('manifestVersion')))
    check('meta.defaultKeyId', meta.get('defaultKeyId') == key1_id)
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    expected_tables = {'meta', 'media', 'albums', 'album_groups', 'memberships',
                       'encryption_keys', 'app_settings'}
    check('七张表齐全', expected_tables.issubset(tables), str(sorted(tables)))
    media_cols = [row[1] for row in conn.execute('PRAGMA table_info(media)')]
    expected_cols = ['id', 'position', 'file_name', 'thumbnail_name', 'sha256',
                     'byte_length', 'original_path', 'source_platform',
                     'source_library_id', 'source_removal_pending', 'content_digest',
                     'original_name', 'mime_type', 'is_video', 'width', 'height',
                     'duration_ms', 'rating', 'date_added', 'date_taken', 'size_bytes',
                     'deleted_at', 'encrypted_dek', 'encryption_key_id',
                     'private_path', 'thumbnail_path', 'play_count', 'last_played_at']
    check('media 表列与 privi 一致', media_cols == expected_cols, str(media_cols))
    rows = list(conn.execute(
        'SELECT id, file_name, encrypted_dek, encryption_key_id FROM media'))
    check('导出 3 条媒体记录', len(rows) == 3, str(len(rows)))
    check('每条都带 encryption_key_id', all(row[3] for row in rows))
    file_names = [row[1] for row in rows]
    check('导出的 file_name 唯一（privi 校验要求）',
          len(file_names) == len(set(file_names)), str(file_names))
    keys = list(conn.execute('SELECT id, kek, fingerprint, is_default FROM encryption_keys'))
    check('导出 2 把密钥', len(keys) == 2, str(len(keys)))
    check('KEK 可 base64 解码且 32 字节',
          all(len(base64.b64decode(row[1])) == 32 for row in keys))
    check('指纹 = sha256(kek)',
          all(row[2] == privi_crypto.key_fingerprint(base64.b64decode(row[1]))
              for row in keys))
    conn.close()

    # ---------- 5. 导入到"另一台机器" ----------
    print('[5] 导入到新库（模拟换机 / 导入 privi 数据）')
    store2 = PrivateKeyStore(os.path.join(ROOT, 'player2.db'))
    result = store2.import_package(exported)
    check('导入成功', result.get('ok'), str(result))
    check('识别为保险库数据', result.get('kind') == 'vault', str(result.get('kind')))
    check('导入 2 把密钥', result.get('keys') == 2, str(result))
    check('导入 3 条记录', result.get('imported') == 3, str(result))
    check('默认密钥沿用包里的', store2.default_key_id() == key1_id, store2.default_key_id())
    imported_row = store2.find_media(encrypted[os.path.join(vault_a, 'a.jpg')]) or {}
    check('ISO 时间已转回毫秒整数',
          isinstance(imported_row.get('date_added'), int) and imported_row['date_added'] > 0,
          str(imported_row.get('date_added')))
    check('记录里的 key id 与导出时一致',
          imported_row.get('encryption_key_id') == key1_id,
          str(imported_row.get('encryption_key_id')))

    service2 = PrivateService(store=store2, cache_dir=os.path.join(ROOT, 'cache2'))
    for path, payload in sources.items():
        cache_path, _ = service2.resolve_playable(encrypted[path])
        with open(cache_path, 'rb') as fh:
            check('新库能解密 %s（按 key id 命中）' % os.path.basename(path),
                  fh.read() == payload)

    # 默认密钥换成另一把：仍应靠 encryption_key_id 解出（多密钥核心场景）
    store2.set_default_key(key2_id)
    cache_path, _ = service2.resolve_playable(encrypted[os.path.join(vault_a, 'a.jpg')])
    with open(cache_path, 'rb') as fh:
        check('默认密钥不是它那把时仍能解密',
              fh.read() == sources[os.path.join(vault_a, 'a.jpg')])
    store2.set_default_key(key1_id)

    # ---------- 6. 旧密钥包仍可用 ----------
    print('[6] 旧密钥包导出 / 导入（兼容性回归）')
    legacy_dir = os.path.join(ROOT, 'legacy')
    os.makedirs(legacy_dir)
    legacy_path = store.export_package(legacy_dir)
    check('旧包文件名 privi-key-*.db',
          os.path.basename(legacy_path).startswith('privi-key-'),
          os.path.basename(legacy_path))
    conn = apsw.Connection(legacy_path, flags=apsw.SQLITE_OPEN_READONLY)
    legacy_meta = {row[0]: row[1] for row in conn.execute('SELECT key, value FROM meta')}
    conn.close()
    check('旧包 format=privi-key-backup',
          legacy_meta.get('format') == 'privi-key-backup', str(legacy_meta.get('format')))
    summary = store2.inspect_package(legacy_path)
    check('旧包能被识别', bool(summary) and summary.get('kind') == 'key_package',
          str(summary))

    # ---------- 7. 目录绑定不随数据文件迁移 ----------
    print('[7] 数据文件只带密钥与索引，不带目录绑定')
    check('新库没有目录绑定', store2.list_directory_bindings() == [])

    # ---------- 8. 本机已有同名记录时只补 DEK（不覆盖、不重复） ----------
    print('[8] 已有记录只补 DEK')
    store3 = PrivateKeyStore(os.path.join(ROOT, 'player3.db'))
    store3.upsert_media(media_id='local-1', private_path=r'D:\vault\x.jpg',
                        file_name=file_names[0], local_path=r'D:\vault\x.jpg',
                        original_name='x.jpg')
    result3 = store3.import_package(exported)
    check('有记录被更新（补 DEK）', result3.get('updated', 0) >= 1, str(result3))
    local_row = store3.find_media(r'D:\vault\x.jpg') or {}
    check('补上的 DEK 带 key id',
          bool(local_row.get('encrypted_dek')) and bool(local_row.get('encryption_key_id')))
    same_name = [r for r in store3.list_media() if r.get('file_name') == file_names[0]]
    check('没有插入重复的同名记录', len(same_name) == 1, str(len(same_name)))

    # ---------- 9. 版本过高时明确拒收 ----------
    print('[9] 容器版本过高时拒收')
    bad_dir = os.path.join(ROOT, 'bad')
    os.makedirs(bad_dir)
    bad_path = os.path.join(bad_dir, 'privi-vault-20990101-000000.db')
    conn = apsw.Connection(bad_path)
    conn.execute('CREATE TABLE meta (key TEXT PRIMARY KEY NOT NULL, value TEXT)')
    conn.execute("INSERT INTO meta VALUES ('format', 'privi-vault-data')")
    conn.execute("INSERT INTO meta VALUES ('version', '9')")
    conn.close()
    bad_summary = store3.inspect_package(bad_path)
    check('能识别出容器版本 9',
          bool(bad_summary) and bad_summary.get('container_version') == 9, str(bad_summary))
    bad_result = store3.import_package(bad_path)
    check('拒收高版本',
          bad_result.get('ok') is False
          and bad_result.get('reason') == 'unsupportedVersion', str(bad_result))

    # ---------- 10. 导入不改变本机已有默认密钥 ----------
    print('[10] 导入到已有默认密钥的库：本机默认密钥不变')
    store4 = PrivateKeyStore(os.path.join(ROOT, 'player4.db'))
    store4.ensure_default_key()
    local_id = store4.default_key_id()
    result4 = store4.import_package(exported)
    check('导入成功', result4.get('ok'), str(result4))
    check('本机默认密钥没被换掉', store4.default_key_id() == local_id,
          '%s != %s' % (store4.default_key_id(), local_id))
    check('密钥环共 3 把（本机 1 + 导入 2）', len(store4.list_keys()) == 3,
          str(len(store4.list_keys())))
    check('只有一条 is_default',
          sum(1 for item in store4.list_keys() if item['is_default']) == 1)
    service4 = PrivateService(store=store4, cache_dir=os.path.join(ROOT, 'cache4'))
    cache_path, _ = service4.resolve_playable(encrypted[os.path.join(vault_a, 'a.jpg')])
    with open(cache_path, 'rb') as fh:
        check('本机默认密钥不是那把时也能解密（靠 key id）',
              fh.read() == sources[os.path.join(vault_a, 'a.jpg')])
    service4.close()
    store4.close()

    service.close()
    service2.close()
    store.close()
    store2.close()
    store3.close()

    if '--keep' in sys.argv:
        print('\n现场保留在: %s' % ROOT)
    else:
        shutil.rmtree(ROOT, ignore_errors=True)
        # 顺手收掉空的 tmp\（别让仓库根留一个空目录；tmp\ 里还有别的东西时 rmdir 会失败，忽略即可）
        try:
            os.rmdir(os.path.dirname(ROOT))
        except OSError:
            pass

    print()
    if FAILS:
        print('FAILED %d 项: %s' % (len(FAILS), ', '.join(FAILS)))
        return 1
    print('ALL PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
