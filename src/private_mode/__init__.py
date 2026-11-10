# -*- coding: utf-8 -*-
"""私密模式（与密册 / privi 兼容的密钥与加解密）。

模块划分：
    privi_crypto.py          AES-256-GCM 容器与 DEK / KEK 包裹（与 privi 字节级一致），
                             以及密钥环 id（`k_` + sha256(kek)[:16]）
    key_store.py             privi「保险库数据」（privi-vault-data，v6 记录布局）与旧
                             「密钥包」（privi-key-backup v2 / v1 JSON）的导入导出；
                             本机密钥环 `vault_keys`、目录密钥绑定 `vault_dir_key`、
                             密文索引 `media_keys`（都在 data/player.db，见 ADR-028）
    private_service.py       业务层：多密钥选择、批量加解密、播放前按需解密
    private_batch_thread.py  批量操作的 QThread 包装

多密钥：一个保险库可以有多把 KEK，每条媒体记录用 `encryption_key_id` 记住自己的
DEK 是哪把 KEK 包的；不同私密库目录可以绑定不同密钥（最长前缀匹配）。

注意：这里不 import 任何子模块，避免与 `src/` 包初始化形成循环导入；
调用方请直接 `from src.private_mode.private_service import PrivateService`。
"""