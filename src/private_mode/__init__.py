# -*- coding: utf-8 -*-
"""私密模式（与 privi 兼容的密钥 / 加解密）。

模块划分：
    privi_crypto.py          AES-256-GCM 容器与 DEK 包裹（与 privi 字节级一致）
    key_store.py             privi 密钥包（v2 SQLite / v1 JSON）导入导出 + 本机索引
    private_service.py       业务层：批量加解密、播放前按需解密
    private_batch_thread.py  批量操作的 QThread 包装

注意：这里不 import 任何子模块，避免与 `src/` 包初始化形成循环导入；
调用方请直接 `from src.private_mode.private_service import PrivateService`。
"""
