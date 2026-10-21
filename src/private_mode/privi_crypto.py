# -*- coding: utf-8 -*-
"""与 privi 完全兼容的 AES-256-GCM 加解密实现。

方案来源（逐项对齐，不自己另定格式）：
    privi/lib/data/services/media_encryption_service.dart
        —— 两层密钥：随机 DEK 加密文件内容，KEK 包裹 DEK
    privi/lib/data/services/native_crypto_service.dart
        —— 容器格式说明
    privi/android/app/src/main/kotlin/com/privi/app/CryptoHandler.kt
        —— 字节级布局（magic / baseNonce / plaintextSize / chunkSize / 分块 tag）

两层密钥：
    随机 DEK(32 字节) --AES-256-GCM--> 加密媒体文件内容
    KEK(32 字节)      --AES-256-GCM--> 包裹 DEK（base64 后存库 / 密钥包）

媒体文件容器（读取两种都支持，写出统一用 v2，privi 可读）：
    v1（历史）: [nonce:12][ciphertext:N][auth_tag:16]
    v2（当前）: [magic b'PRV2':4][baseNonce:8][plaintextSize:8][chunkSize:4]
                + n 个分块，每块 = ciphertext(<= chunkSize) + auth_tag:16
                分块 nonce = baseNonce(8) + int32_be(index)

DEK 包裹（privi MediaEncryptionService.encryptDek）：
    base64([nonce:12][ciphertext:32][auth_tag:16])
"""

import base64
import os
import secrets
import struct

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

DEK_LEN = 32            # AES-256
KEK_LEN = 32
NONCE_LEN = 12
TAG_LEN = 16
BASE_NONCE_LEN = 8      # v2 的 baseNonce
CHUNK_SIZE = 1024 * 1024  # privi: V2_CHUNK_SIZE = 1 MiB
MAX_CHUNK_SIZE = 64 * 1024 * 1024
HEADER_V2_LEN = 4 + BASE_NONCE_LEN + 8 + 4  # 24
MAGIC_V2 = b'PRV2'


class PriviCryptoError(Exception):
    """加解密失败（格式错误 / 认证失败 / 文件截断）。"""


# ────────────────────────────── 基础原语 ──────────────────────────────

def generate_dek():
    """32 字节随机 DEK（AES-256）。"""
    return secrets.token_bytes(DEK_LEN)


def generate_nonce():
    """12 字节随机 nonce；v2 只取前 8 字节当 baseNonce（与 privi 一致）。"""
    return secrets.token_bytes(NONCE_LEN)


def random_file_name():
    """privi ADR-042：32 位小写 hex、不带扩展名的随机文件名。"""
    return secrets.token_hex(16)


def _aes_gcm_encrypt(key, nonce, data):
    encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    body = encryptor.update(data) + encryptor.finalize()
    return body, encryptor.tag


def _aes_gcm_decrypt(key, nonce, body, tag):
    decryptor = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
    return decryptor.update(body) + decryptor.finalize()


def _chunk_nonce(base_nonce, index):
    """分块 nonce = baseNonce(8) + int32 大端序号（CryptoHandler.chunkNonce）。"""
    return bytes(base_nonce[:BASE_NONCE_LEN]) + struct.pack('>i', index)


# ────────────────────────────── DEK 包裹 ──────────────────────────────

def wrap_dek(dek, kek):
    """用 KEK 包裹 DEK，返回 base64([nonce:12][ciphertext][tag:16])。"""
    if len(kek) != KEK_LEN:
        raise PriviCryptoError('KEK 长度必须是 %d 字节，实际 %d' % (KEK_LEN, len(kek)))
    nonce = generate_nonce()
    body, tag = _aes_gcm_encrypt(kek, nonce, dek)
    return base64.b64encode(nonce + body + tag).decode('ascii')


def unwrap_dek(encrypted_dek_base64, kek):
    """解出 DEK；密钥不匹配 / 数据被篡改时返回 None（privi 同样语义）。"""
    if not encrypted_dek_base64 or len(kek) != KEK_LEN:
        return None
    try:
        raw = base64.b64decode(encrypted_dek_base64)
    except Exception:
        return None
    if len(raw) < NONCE_LEN + TAG_LEN:
        return None
    nonce = raw[:NONCE_LEN]
    body = raw[NONCE_LEN:-TAG_LEN]
    tag = raw[-TAG_LEN:]
    try:
        return _aes_gcm_decrypt(kek, nonce, body, tag)
    except (InvalidTag, ValueError):
        return None


# ────────────────────────────── 明文识别 ──────────────────────────────
# 与 privi MediaEncryptionService._looksLikePlainMedia 对齐：用于判断
# "这个文件到底是密文还是明文"，避免把明文当密文重复加密。

def looks_like_plain_media(path):
    try:
        with open(path, 'rb') as f:
            head = f.read(16)
    except OSError:
        return False
    if len(head) < 4:
        return False
    if head.startswith(b'\xff\xd8\xff'):          # JPEG（第 4 字节随 EXIF/JFIF 变）
        return True
    if head.startswith(b'\x89PNG\r\n\x1a\n'):     # PNG
        return True
    if head.startswith(b'GIF8'):                  # GIF
        return True
    if len(head) >= 8 and head[4:8] == b'ftyp':   # MP4/MOV/M4A/3GP/HEIC/AVIF
        return True
    if head.startswith(b'RIFF') and len(head) >= 12:
        fourcc = head[8:12]
        if fourcc in (b'AVI ', b'WEBP'):
            return True
    if head.startswith(b'\x1a\x45\xdf\xa3'):      # WebM / MKV
        return True
    if head.startswith(b'II*\x00') or head.startswith(b'MM\x00*'):  # TIFF 家族
        return True
    if head.startswith(b'FLV\x01'):
        return True
    if head.startswith(b'0&\xb2u\x8ef\xcf\x11'):  # ASF (WMV/WMA)
        return True
    if len(head) >= 10 and head[0:2] == b'BM' and head[6:10] == b'\x00\x00\x00\x00':
        return True                               # BMP（需 6 个约束字节，防误判）
    return False


def sniff_extension(path):
    """按文件头猜扩展名；用于原文件名丢失时给解密结果补扩展名。"""
    try:
        with open(path, 'rb') as f:
            head = f.read(16)
    except OSError:
        return ''
    if head.startswith(b'\xff\xd8\xff'):
        return '.jpg'
    if head.startswith(b'\x89PNG\r\n\x1a\n'):
        return '.png'
    if head.startswith(b'GIF8'):
        return '.gif'
    if len(head) >= 8 and head[4:8] == b'ftyp':
        return '.mp4'
    if head.startswith(b'RIFF') and len(head) >= 12:
        if head[8:12] == b'WEBP':
            return '.webp'
        if head[8:12] == b'AVI ':
            return '.avi'
    if head.startswith(b'\x1a\x45\xdf\xa3'):
        return '.mkv'
    if head.startswith(b'II*\x00') or head.startswith(b'MM\x00*'):
        return '.tif'
    if head.startswith(b'FLV\x01'):
        return '.flv'
    if head.startswith(b'0&\xb2u\x8ef\xcf\x11'):
        return '.wmv'
    if head.startswith(b'BM'):
        return '.bmp'
    return ''


def is_v2_file(path):
    try:
        if os.path.getsize(path) < HEADER_V2_LEN:
            return False
        with open(path, 'rb') as f:
            return f.read(4) == MAGIC_V2
    except OSError:
        return False


def looks_encrypted(path):
    """判断文件是否为 privi 密文。

    v2 有 'PRV2' 魔数，直接判定；v1 没有魔数，只能按"不是已知明文媒体格式
    且长度足够（nonce+tag）"推断 —— 与 privi 的 looksEncrypted 思路一致。
    只对媒体文件调用，避免把任意文本文件误判成密文。
    """
    if not os.path.isfile(path):
        return False
    if is_v2_file(path):
        return True
    try:
        size = os.path.getsize(path)
    except OSError:
        return False
    if size < NONCE_LEN + TAG_LEN:
        return False
    return not looks_like_plain_media(path)


# ────────────────────────────── 文件加解密 ──────────────────────────────

def expected_v2_size(plaintext_size):
    """v2 容器长度 = 24 + 明文 + 16 * 分块数。"""
    if plaintext_size <= 0:
        return HEADER_V2_LEN
    chunks = (plaintext_size + CHUNK_SIZE - 1) // CHUNK_SIZE
    return HEADER_V2_LEN + plaintext_size + TAG_LEN * chunks


def encrypt_file(src_path, dest_path, dek, nonce):
    """按 privi v2 容器加密 [src_path] 到 [dest_path]。

    :return: (明文长度, 分块数, 密文长度)
    """
    if len(dek) != DEK_LEN:
        raise PriviCryptoError('DEK 长度必须是 %d 字节' % DEK_LEN)
    if len(nonce) < BASE_NONCE_LEN:
        raise PriviCryptoError('nonce 长度不足 %d 字节' % BASE_NONCE_LEN)
    base_nonce = bytes(nonce[:BASE_NONCE_LEN])
    plaintext_size = os.path.getsize(src_path)
    chunks = 0
    with open(src_path, 'rb') as src, open(dest_path, 'wb') as dest:
        dest.write(MAGIC_V2)
        dest.write(base_nonce)
        dest.write(struct.pack('>q', plaintext_size))
        dest.write(struct.pack('>i', CHUNK_SIZE))
        index = 0
        while True:
            chunk = src.read(CHUNK_SIZE)
            if not chunk:
                break
            body, tag = _aes_gcm_encrypt(dek, _chunk_nonce(base_nonce, index), chunk)
            dest.write(body)
            dest.write(tag)
            index += 1
        chunks = index
    return plaintext_size, chunks, expected_v2_size(plaintext_size)


def decrypt_file(src_path, dest_path, dek):
    """解密 privi 密文（自动识别 v1 / v2）到 [dest_path]。

    :return: 写入的明文字节数
    """
    if len(dek) != DEK_LEN:
        raise PriviCryptoError('DEK 长度必须是 %d 字节' % DEK_LEN)
    if not os.path.isfile(src_path):
        raise PriviCryptoError('文件不存在: %s' % src_path)
    try:
        if is_v2_file(src_path):
            return _decrypt_v2(src_path, dest_path, dek)
        return _decrypt_v1(src_path, dest_path, dek)
    except (InvalidTag, ValueError) as e:
        raise PriviCryptoError('解密失败（认证不通过，密钥不匹配或文件被篡改）: %s' % e)


def _decrypt_v2(src_path, dest_path, dek):
    with open(src_path, 'rb') as src:
        header = src.read(HEADER_V2_LEN)
        if len(header) != HEADER_V2_LEN or header[:4] != MAGIC_V2:
            raise PriviCryptoError('不是合法的 PRV2 容器')
        base_nonce = header[4:12]
        plaintext_size = struct.unpack('>q', header[12:20])[0]
        chunk_size = struct.unpack('>i', header[20:24])[0]
        if plaintext_size < 0 or chunk_size <= 0 or chunk_size > MAX_CHUNK_SIZE:
            raise PriviCryptoError('PRV2 头非法: size=%d chunk=%d' % (plaintext_size, chunk_size))
        written = 0
        index = 0
        remaining = plaintext_size
        with open(dest_path, 'wb') as dest:
            while remaining > 0:
                this_len = min(remaining, chunk_size)
                payload = src.read(this_len + TAG_LEN)
                if len(payload) != this_len + TAG_LEN:
                    raise PriviCryptoError('密文被截断（分块 %d）' % index)
                body = payload[:this_len]
                tag = payload[this_len:]
                plain = _aes_gcm_decrypt(dek, _chunk_nonce(base_nonce, index), body, tag)
                dest.write(plain)
                written += len(plain)
                remaining -= this_len
                index += 1
    return written


def _decrypt_v1(src_path, dest_path, dek):
    size = os.path.getsize(src_path)
    if size < NONCE_LEN + TAG_LEN:
        raise PriviCryptoError('文件太小，不是合法的 v1 密文: %d 字节' % size)
    with open(src_path, 'rb') as src:
        nonce = src.read(NONCE_LEN)
        src.seek(size - TAG_LEN)
        tag = src.read(TAG_LEN)
        src.seek(NONCE_LEN)
        remaining = size - NONCE_LEN - TAG_LEN
        written = 0
        decryptor = Cipher(algorithms.AES(dek), modes.GCM(nonce, tag)).decryptor()
        with open(dest_path, 'wb') as dest:
            while remaining > 0:
                chunk = src.read(min(CHUNK_SIZE, remaining))
                if not chunk:
                    raise PriviCryptoError('密文被截断')
                dest.write(decryptor.update(chunk))
                remaining -= len(chunk)
            dest.write(decryptor.finalize())
            written = dest.tell()
    return written

