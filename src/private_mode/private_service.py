# -*- coding: utf-8 -*-
"""私密模式核心服务：密钥管理 + 路径批量加解密 + 播放前按需解密。

与 privi 的对应关系：
    privi/lib/data/services/key_backup_service.dart      → 密钥包导入 / 导出
    privi/lib/data/services/media_encryption_service.dart → 文件加解密
    privi/lib/data/services/batch_encryption_service.dart → 批量加密
    privi/lib/data/services/filename_encryption_service.dart → 文件名加密

工程约定（照搬 privi 的安全顺序）：
    1. 加密：先落库 DEK 记录 → 再写密文 → 最后删源文件。中途崩溃时 DEK 一定在库里，
       不会出现"有密文但没密钥"的死文件。
    2. 解密：先解密到临时文件 → 校验非空 → 原子替换成正式文件名 → 最后删密文 / 删记录。
    3. 加密文件名：32 位小写 hex、无扩展名（privi ADR-042）。
"""

import base64
import hashlib
import mimetypes
import os
import shutil
import uuid
from datetime import datetime, timezone

from loguru import logger

from src.private_mode import privi_crypto
from src.private_mode.key_store import PrivateKeyStore
from src.utils.utils import get_private_cache_path

IMAGE_EXTENSIONS = ('.bmp', '.dib', '.png', '.jpg', '.jpeg', '.pbm', '.pgm',
                    '.ppm', '.tif', '.tiff', '.webp', '.gif')
VIDEO_EXTENSIONS = ('.mp4', '.mkv')
MEDIA_EXTENSIONS = IMAGE_EXTENSIONS + VIDEO_EXTENSIONS

TEMP_PREFIX = '.prv_tmp_'   # 加解密临时文件；不参与媒体扫描与加密


class PrivateServiceError(Exception):
    """私密操作失败（缺密钥 / 密钥不匹配 / 文件缺失）。"""


def safe_file_name(name, fallback='decrypted'):
    """把任意名字收敛成 Windows 合法文件名（privi 的原名来自 Android）。"""
    name = (name or '').strip().replace('\\', '_').replace('/', '_')
    for ch in '<>:"|?*':
        name = name.replace(ch, '_')
    name = name.strip(' .')
    return name or fallback


def _millis_from_timestamp(timestamp):
    try:
        return int(datetime.fromtimestamp(timestamp, timezone.utc).timestamp() * 1000)
    except (OSError, OverflowError, ValueError):
        return None


class PrivateService:
    """私密模式的唯一入口（UI 只跟它打交道）。"""

    def __init__(self, store=None, cache_dir=None):
        self.store = store or PrivateKeyStore()
        self.cache_dir = cache_dir or get_private_cache_path()
        os.makedirs(self.cache_dir, exist_ok=True)

    def close(self):
        try:
            self.store.close()
        except Exception:
            pass

    # ────────────────────────── 密钥管理 ──────────────────────────

    def has_key(self):
        return self.store.has_key()

    def key_info(self):
        material = self.store.key_material()
        if material is None:
            return None
        return {
            'salt': material.get('encryption_salt'),
            'source': material.get('kek_source'),
            'created_at': material.get('created_at'),
            'encrypted_count': self.store.count_encrypted(),
        }

    def ensure_key(self):
        """有密钥就返回 KEK；没有就生成一把随机 KEK（可再导出备份）。"""
        material = self.store.key_material()
        if material is not None:
            return material['kek']
        kek = privi_crypto.generate_dek()
        salt = base64.b64encode(os.urandom(16)).decode('ascii')
        self.store.save_key_material(kek, salt, 'imported')
        logger.info('已生成本机随机私密密钥，可通过「密钥 → 导出密钥」备份')
        return kek

    def _require_kek(self):
        material = self.store.key_material()
        if material is None:
            raise PrivateServiceError(
                '尚未导入密钥：请先通过「密钥 → 导入密钥」选择密册导出的 .db 密钥包')
        return material['kek']

    def inspect_key_package(self, file_path):
        return self.store.inspect_package(file_path)

    def import_key_package(self, file_path, overwrite_key=False):
        return self.store.import_package(file_path, overwrite_key=overwrite_key)

    def export_key_package(self, directory):
        return self.store.export_package(directory)


    # ────────────────────────── 文件识别 ──────────────────────────

    def is_media_file(self, path):
        return path.lower().endswith(MEDIA_EXTENSIONS)

    def describe(self, path):
        """返回 {encrypted, is_video, original_name, media}。

        判定"是密文"只认两条硬证据：
          ① 密钥库里有该文件的 DEK 记录（privi 导入的 / 本机加密的）；
          ② 文件头是 PRV2 魔数。
        不用"看起来不像明文媒体"这种启发式，避免把普通文本文件误判成密文。
        """
        media = self.store.find_media(path)
        encrypted = bool(media and (media.get('encrypted_dek') or '')) \
            or privi_crypto.is_v2_file(path)
        original_name = os.path.basename(path)
        is_video = False
        if media:
            original_name = media.get('original_name') or original_name
            is_video = bool(media.get('is_video'))
        if not is_video:
            is_video = original_name.lower().endswith(VIDEO_EXTENSIONS) \
                or path.lower().endswith(VIDEO_EXTENSIONS)
        return {
            'encrypted': encrypted,
            'is_video': is_video,
            'original_name': original_name,
            'media': media,
        }

    def is_video_path(self, path):
        return self.describe(path)['is_video']

    # ────────────────────────── 播放 / 展示前解密 ──────────────────────────

    def resolve_playable(self, path):
        """把树里点到的文件变成"现有播放/展示逻辑能直接吃"的路径。

        - 明文文件：原样返回；
        - 密文文件：按 DEK 解密到本次运行缓存（带原扩展名），返回缓存路径；
        返回值第二项是用于界面显示的原始文件名。

        背景：现有 PicShowLayout / VideoShowLayout 都按扩展名判类型，而 privi
        加密后的文件名是"32 位 hex、无扩展名"，所以必须先解密成带扩展名的明文。
        """
        info = self.describe(path)
        if not info['encrypted']:
            return path, info['original_name']

        media = info['media']
        if not media or not (media.get('encrypted_dek') or ''):
            raise PrivateServiceError(
                '文件已加密，但密钥库里没有对应记录，无法解密：\n%s\n\n'
                '请确认已通过「密钥 → 导入密钥」导入与这些文件配套的密钥包。' % path)

        dek = self._dek_for(media)
        cache_path = self._cache_path_for(path, info['original_name'])
        if not os.path.exists(cache_path):
            tmp = cache_path + '.part'
            try:
                privi_crypto.decrypt_file(path, tmp, dek)
                os.replace(tmp, cache_path)
            except Exception:
                if os.path.exists(tmp):
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
                raise

        # 记录本机真实路径，下次直接命中（导入包里的路径是 Android 路径）
        abs_path = os.path.normpath(os.path.abspath(path))
        if media.get('local_path') != abs_path:
            try:
                self.store.update_local_path(media['media_id'], abs_path)
            except Exception as e:
                logger.warning(f'更新媒体本机路径失败: {e}')
        return cache_path, info['original_name']

    def list_images(self, dir_path):
        """目录下可展示的图片（含密文），按修改时间升序。"""
        result = []
        for path in self._iter_files(dir_path):
            try:
                info = self.describe(path)
            except Exception as e:
                logger.warning(f'识别文件失败 {path}: {e}')
                continue
            if info['is_video']:
                continue
            if not (info['original_name'].lower().endswith(IMAGE_EXTENSIONS)
                    or path.lower().endswith(IMAGE_EXTENSIONS)):
                continue
            result.append(path)
        result.sort(key=self._mtime)
        return result

    @staticmethod
    def _mtime(path):
        try:
            return os.path.getmtime(path)
        except OSError:
            return 0

    def _cache_path_for(self, source_path, original_name):
        """每个密文一个缓存目录，目录内保留原始文件名（标题栏显示才友好）。"""
        key = os.path.normpath(os.path.abspath(source_path)).lower().encode('utf-8')
        folder = os.path.join(self.cache_dir, hashlib.md5(key).hexdigest()[:12])
        os.makedirs(folder, exist_ok=True)
        return os.path.join(folder, safe_file_name(original_name))

    def clear_cache(self):
        """清空解密缓存（启动 / 退出 / 批量操作后调用）。"""
        try:
            if os.path.isdir(self.cache_dir):
                shutil.rmtree(self.cache_dir, ignore_errors=True)
            os.makedirs(self.cache_dir, exist_ok=True)
        except Exception as e:
            logger.warning(f'清理解密缓存失败: {e}')

    def _dek_for(self, media):
        kek = self._require_kek()
        dek = privi_crypto.unwrap_dek(media.get('encrypted_dek'), kek)
        if dek is None:
            raise PrivateServiceError(
                '密钥不匹配：该文件不是用当前密钥加密的（密钥包与文件不是同一套）')
        return dek



    # ────────────────────────── 扫描 ──────────────────────────

    def _iter_files(self, target):
        if not target:
            return
        if os.path.isfile(target):
            yield target
            return
        if not os.path.isdir(target):
            return
        for root, dirs, files in os.walk(target):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for name in files:
                if name.startswith('.') or name.startswith(TEMP_PREFIX):
                    continue
                yield os.path.join(root, name)

    def scan_encryptable(self, target):
        """返回 (待加密的图片/视频, 跳过的文件数)。已加密 / 非媒体的跳过。"""
        files = []
        skipped = 0
        for path in self._iter_files(target):
            if not path.lower().endswith(MEDIA_EXTENSIONS):
                skipped += 1
                continue
            if privi_crypto.looks_encrypted(path):
                skipped += 1
                continue
            media = self.store.find_media(path)
            if media and (media.get('encrypted_dek') or ''):
                skipped += 1
                continue
            files.append(path)
        return files, skipped

    def scan_decryptable(self, target):
        """返回 (可解密的密文, 缺密钥记录的密文数)。

        "缺密钥"只统计真正的密文：带 PRV2 魔数，或"无扩展名 + 不是明文媒体"
        （privi ADR-042 的密文名一律无扩展名）。普通 .txt/.srt 不会被算进来。
        """
        files = []
        missing_key = 0
        for path in self._iter_files(target):
            media = self.store.find_media(path)
            if media and (media.get('encrypted_dek') or ''):
                files.append(path)
                continue
            if privi_crypto.is_v2_file(path):
                missing_key += 1
                continue
            if not os.path.splitext(path)[1] and privi_crypto.looks_encrypted(path):
                missing_key += 1
        return files, missing_key

    # ────────────────────────── 批量加密 / 解密 ──────────────────────────

    def encrypt_path(self, target, progress=None, should_cancel=None):
        """加密 [target] 下所有图片/视频（内容和文件名一起加密），删掉源文件。"""
        files, skipped = self.scan_encryptable(target)
        stats = {
            'total': len(files), 'done': 0, 'encrypted': 0, 'skipped': skipped,
            'failed': 0, 'kept_source': 0, 'cancelled': False, 'errors': [],
        }
        if not files:
            return stats
        self.ensure_key()
        for index, path in enumerate(files, 1):
            if should_cancel and should_cancel():
                stats['cancelled'] = True
                break
            if progress:
                progress(index - 1, len(files), os.path.basename(path))
            try:
                new_path = self.encrypt_one(path)
                stats['encrypted'] += 1
                if new_path is None:
                    stats['kept_source'] += 1
            except Exception as e:
                stats['failed'] += 1
                stats['errors'].append('%s: %s' % (os.path.basename(path), e))
                logger.error(f'加密失败 {path}: {e}')
            stats['done'] = index
        if progress:
            progress(stats['done'], len(files), '')
        logger.info(
            '批量加密完成: 总数=%d 成功=%d 跳过=%d 失败=%d 源文件未删=%d 取消=%s'
            % (stats['total'], stats['encrypted'], stats['skipped'],
               stats['failed'], stats['kept_source'], stats['cancelled']))
        return stats

    def decrypt_path(self, target, progress=None, should_cancel=None):
        """解密 [target] 下所有可解密的文件，恢复原文件名并删除密文。"""
        files, missing_key = self.scan_decryptable(target)
        stats = {
            'total': len(files), 'done': 0, 'decrypted': 0, 'skipped': 0,
            'failed': 0, 'kept_source': 0, 'missing_key': missing_key,
            'cancelled': False, 'errors': [],
        }
        if not files:
            return stats
        for index, path in enumerate(files, 1):
            if should_cancel and should_cancel():
                stats['cancelled'] = True
                break
            if progress:
                progress(index - 1, len(files), os.path.basename(path))
            try:
                restored = self.decrypt_one(path)
                stats['decrypted'] += 1
                if restored is None:
                    stats['kept_source'] += 1
            except Exception as e:
                stats['failed'] += 1
                stats['errors'].append('%s: %s' % (os.path.basename(path), e))
                logger.error(f'解密失败 {path}: {e}')
            stats['done'] = index
        if progress:
            progress(stats['done'], len(files), '')
        logger.info(
            '批量解密完成: 总数=%d 成功=%d 失败=%d 缺密钥=%d 密文未删=%d 取消=%s'
            % (stats['total'], stats['decrypted'], stats['failed'],
               stats['missing_key'], stats['kept_source'], stats['cancelled']))
        return stats



    # ────────────────────────── 单文件加解密 ──────────────────────────

    def encrypt_one(self, path):
        """加密单个文件：内容 → privi v2 容器，文件名 → 32 位随机 hex。

        :return: 新的密文路径；源文件删除失败时返回 None（密文与记录已保留）
        """
        if not os.path.isfile(path):
            raise PrivateServiceError('文件不存在: %s' % path)
        if privi_crypto.looks_encrypted(path):
            raise PrivateServiceError('文件看起来已经是密文，跳过以免重复加密')

        kek = self.ensure_key()
        name = os.path.basename(path)
        directory = os.path.dirname(path) or '.'
        abs_source = os.path.normpath(os.path.abspath(path))
        new_name = self._unique_encrypted_name(directory)
        new_path = os.path.join(directory, new_name)
        abs_target = os.path.normpath(os.path.abspath(new_path))

        dek = privi_crypto.generate_dek()
        nonce = privi_crypto.generate_nonce()
        encrypted_dek = privi_crypto.wrap_dek(dek, kek)
        try:
            stat = os.stat(path)
        except OSError as e:
            raise PrivateServiceError('读取文件属性失败: %s' % e)

        media_id = uuid.uuid4().hex
        # ① 先落库：崩溃时 DEK 已在库里，密文永远可解
        self.store.upsert_media(
            media_id=media_id,
            private_path=abs_target,
            file_name=new_name,
            local_path=abs_target,
            original_path=abs_source,
            original_name=name,
            mime_type=mimetypes.guess_type(name)[0],
            is_video=1 if name.lower().endswith(VIDEO_EXTENSIONS) else 0,
            size_bytes=stat.st_size,
            date_added=_millis_from_timestamp(stat.st_mtime),
            encrypted_dek=encrypted_dek,
        )

        tmp = os.path.join(directory, TEMP_PREFIX + uuid.uuid4().hex)
        try:
            _, _, expected = privi_crypto.encrypt_file(path, tmp, dek, nonce)
            actual = os.path.getsize(tmp)
            if actual != expected:
                raise PrivateServiceError(
                    '加密结果长度异常（%d != %d），已放弃替换' % (actual, expected))
            os.replace(tmp, new_path)
        except Exception:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            self.store.delete_media(media_id)
            raise

        # ② 删源文件（需求：只保留加密文件）
        try:
            os.remove(path)
        except OSError as e:
            logger.error(f'密文已生成但源文件删除失败 {path}: {e}')
            return None
        logger.info(f'已加密: {path} → {new_path}（{stat.st_size} 字节）')
        return new_path

    def decrypt_one(self, path):
        """解密单个文件并恢复原文件名，成功删除密文与索引记录。

        :return: 恢复后的明文路径；密文删除失败时返回 None
        """
        if not os.path.isfile(path):
            raise PrivateServiceError('文件不存在: %s' % path)
        media = self.store.find_media(path)
        if not media or not (media.get('encrypted_dek') or ''):
            raise PrivateServiceError('密钥库里没有该文件的 DEK 记录，无法解密')
        dek = self._dek_for(media)
        directory = os.path.dirname(path) or '.'
        tmp = os.path.join(directory, TEMP_PREFIX + uuid.uuid4().hex)
        try:
            written = privi_crypto.decrypt_file(path, tmp, dek)
            if written <= 0 and os.path.getsize(path) > privi_crypto.HEADER_V2_LEN + privi_crypto.TAG_LEN:
                raise PrivateServiceError('解密结果为空（%d 字节）' % written)
            original_name = safe_file_name(media.get('original_name') or '')
            if not original_name:
                original_name = 'decrypted_' + uuid.uuid4().hex[:8] + privi_crypto.sniff_extension(tmp)
            dest = self._free_path(directory, original_name)
            os.replace(tmp, dest)
        except Exception:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            raise

        try:
            os.remove(path)
            self.store.delete_media(media['media_id'])
        except OSError as e:
            logger.error(f'明文已恢复但密文删除失败 {path}: {e}')
            return None
        logger.info(f'已解密: {path} → {dest}（{written} 字节）')
        return dest

    def _unique_encrypted_name(self, directory):
        for _ in range(16):
            candidate = privi_crypto.random_file_name()
            if not os.path.exists(os.path.join(directory, candidate)):
                return candidate
        raise PrivateServiceError('目录内无法生成唯一的随机文件名')

    @staticmethod
    def _free_path(directory, name):
        """不覆盖已有文件：原名占用时追加 -2 / -3 …"""
        candidate = os.path.join(directory, name)
        if not os.path.exists(candidate):
            return candidate
        base, ext = os.path.splitext(name)
        for index in range(2, 100):
            candidate = os.path.join(directory, '%s-%d%s' % (base, index, ext))
            if not os.path.exists(candidate):
                return candidate
        return os.path.join(directory, '%s-%s%s' % (base, uuid.uuid4().hex[:8], ext))