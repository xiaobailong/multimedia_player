# -*- coding: utf-8 -*-
"""密钥管理：导入 / 导出 privi 数据文件、密钥与目录管理、查看密钥状态。

支持两种 privi 数据文件（扩展名都是 `.db`，靠 `meta.format` 区分）：

- **保险库数据**（`privi-vault-data`，privi ADR-053）：密钥环 + 全部密钥索引，
  记录布局 v6，容器是单个 SQLite 文件；
- 旧**密钥包**（`privi-key-backup` v2，或更早的 v1 JSON）：只有一把 KEK + 文件名映射。

导入时自动识别格式，不需要用户先选类型。
"""
import os

from loguru import logger

from src.layout.styled_dialogs import (ask_yes_no, pick_directory, pick_open_file,
                                       show_error, show_info, show_warning)
from src.layout.vault_key_dialog import VaultKeyDialog


class KeyActionsMixin:
    """密钥菜单背后的窗口动作。"""

    def _import_key_package(self):
        """导入 privi「保险库数据」/ 旧密钥包（自动识别格式）。"""
        file_path = pick_open_file(
            self, '导入保险库数据 / 密钥包',
            filters=['保险库数据 / 密钥包 (*.db *.json)', '所有文件 (*.*)'])
        if not file_path:
            return

        try:
            summary = self.private_service.inspect_key_package(file_path)
        except Exception as e:
            logger.error(f'检查数据文件失败: {e}')
            summary = None
        if summary is None:
            show_warning(
                self, '导入保险库数据',
                '该文件不是密册导出的数据文件。\n\n'
                '需要密册「设置 → 保险库数据 → 导出」生成的 privi-vault-*.db；\n'
                '旧版 .db 密钥包与 v1 JSON 密钥包也支持。')
            return

        kind = summary.get('kind')
        if kind == 'vault':
            detail = ('类型：保险库数据（privi-vault-data）\n'
                      '容器版本：%s    记录布局：%s\n'
                      '导出时间：%s\n'
                      '媒体记录：%d 条（其中 %d 条带加密密钥）\n'
                      '密钥数量：%d 把' % (
                          summary.get('container_version', '-'),
                          summary.get('manifest_version', '-'),
                          summary.get('created_at') or '-',
                          summary.get('file_count', 0),
                          summary.get('encrypted_file_count', 0),
                          summary.get('key_count', 0)))
        else:
            detail = ('类型：%s\n密钥包版本：%s\n创建时间：%s\n'
                      '文件记录：%d 条（其中 %d 条带加密密钥）\n包含盐值：%s' % (
                          summary.get('kind_label') or '密钥包',
                          summary.get('version', '-'),
                          summary.get('created_at') or '-',
                          summary.get('file_count', 0),
                          summary.get('encrypted_file_count', 0),
                          '是' if summary.get('has_salt') else '否'))

        if not ask_yes_no(
                self, '导入保险库数据',
                detail + '\n\n导入后会用它解开本机的私密文件；'
                         '本机已有的密钥不会被覆盖，新密钥一起加入密钥环。继续？'):
            return

        result = self.private_service.import_key_package(file_path)
        if not result.get('ok') and result.get('reason') == 'key_conflict':
            if not ask_yes_no(
                    self, '密钥冲突',
                    (result.get('message') or '') + '\n\n仍要把导入的密钥设为默认吗？',
                    default_yes=False):
                self.notice('已取消导入密钥')
                return
            result = self.private_service.import_key_package(file_path, overwrite_key=True)

        if not result.get('ok'):
            show_warning(self, '导入保险库数据', result.get('message') or '导入失败')
            return

        message = ('导入成功。\n新增密钥 %d 把，新增文件记录 %d 条，更新 %d 条，跳过 %d 条。' % (
            result.get('keys', 0), result.get('imported', 0),
            result.get('updated', 0), result.get('skipped', 0)))
        if result.get('kind') == 'vault':
            message += ('\n\n提示：不同私密库目录可以使用不同密钥，'
                        '可在「密钥 → 密钥与目录管理」里绑定。')
        show_info(self, '导入保险库数据', message)
        self.notice(message.splitlines()[0])
        self.model.refresh()

    def _export_vault_data(self):
        """导出 privi 可直接导入的「保险库数据」（密钥环 + 全部密钥索引）。"""
        if not self.private_service.has_key():
            show_warning(
                self, '导出保险库数据',
                '当前还没有可导出的密钥。\n'
                '请先导入密册导出的保险库数据，或先对文件执行一次加密（会自动生成密钥）。')
            return

        directory = pick_directory(self, '选择保险库数据导出目录')
        if not directory:
            return

        try:
            path = self.private_service.export_vault_data(directory)
        except Exception as e:
            logger.error(f'导出保险库数据失败: {e}')
            show_error(self, '导出保险库数据', '导出失败：\n' + str(e))
            return

        show_info(
            self, '导出保险库数据',
            '已导出与密册「保险库数据」完全兼容的数据库：\n%s\n\n'
            '文件里包含明文密钥环与全部密钥索引，配合私密目录可解密全部文件；\n'
            '请离线保存或放进加密网盘，不要外传。' % path)
        self.notice('已导出保险库数据：' + path)

    def _export_key_package(self):
        """导出旧版密钥包（只带默认密钥 + 文件名映射，兼容旧版密册）。"""
        if not self.private_service.has_key():
            show_warning(
                self, '导出密钥包',
                '当前还没有可导出的密钥。\n'
                '请先导入 privi 导出的密钥包，或先对文件执行一次加密（会自动生成密钥）。')
            return

        directory = pick_directory(self, '选择密钥包导出目录')
        if not directory:
            return

        try:
            path = self.private_service.export_key_package(directory)
        except Exception as e:
            logger.error(f'导出密钥包失败: {e}')
            show_error(self, '导出密钥包', '导出失败：\n' + str(e))
            return

        show_info(
            self, '导出密钥包',
            '已导出旧版密钥包（privi-key-backup v2）：\n%s\n\n'
            '注意：这种格式只带**默认密钥**与文件名映射；'
            '如果用了多把密钥（不同目录绑了不同密钥），请改用「导出保险库数据」。' % path)
        self.notice('已导出密钥包：' + path)

    def _manage_keys(self, start_dir=''):
        """密钥与目录管理：密钥环、默认密钥、目录密钥绑定。"""
        if not self.private_service.has_key():
            if not ask_yes_no(
                    self, '密钥与目录管理',
                    '当前还没有任何密钥。\n'
                    '继续将自动生成一把随机密钥（可随时导出备份）。继续？'):
                return
            try:
                self.private_service.ensure_key()
            except Exception as e:
                logger.error(f'生成密钥失败: {e}')
                show_error(self, '密钥与目录管理', '生成密钥失败：\n' + str(e))
                return

        VaultKeyDialog(self, self.private_service, start_dir=start_dir).exec_()
        self.notice('密钥与目录管理：已刷新')
        self.model.refresh()

    def _bind_key_for_target(self):
        """右键 → 私密操作 → 为当前目录绑定密钥（打开密钥与目录管理框）。"""
        target = self.path_right_click
        if not target or not os.path.isdir(target):
            self.notice('请先在左侧树中选择一个目录')
            return
        self._manage_keys(start_dir=target)

    def _show_key_status(self):
        """密钥状态：默认密钥、密钥环大小、目录绑定数量。"""
        info = self.private_service.key_info()
        if info is None:
            show_info(
                self, '密钥状态',
                '尚未导入密钥。\n\n'
                '可通过「密钥 → 导入保险库数据 / 密钥包」选择密册导出的 '
                'privi-vault-*.db；\n'
                '也可以直接对私密目录执行加密（会自动生成新密钥）。')
            return

        bindings = info.get('bindings') or []
        binding_text = '无'
        if bindings:
            binding_text = '\n'.join(
                '    %s → %s' % (item.get('path'),
                                item.get('label') or ('（密钥已丢失）' if item.get('missing_key')
                                                      else '未命名密钥'))
                for item in bindings[:8])
            if len(bindings) > 8:
                binding_text += '\n    …… 另有 %d 个目录' % (len(bindings) - 8)

        show_info(
            self, '密钥状态',
            '密钥数量：%d 把\n'
            '默认密钥：%s\n'
            '密钥 id：%s\n'
            '指纹：%s…\n'
            '创建时间：%s\n'
            '已记录加密文件：%d 个\n'
            '盐值：%s\n\n'
            '目录密钥绑定（%d 个）：\n%s' % (
                info.get('key_count', 0),
                info.get('default_label') or '未命名密钥',
                info.get('default_key_id') or '-',
                (info.get('fingerprint') or '')[:16] or '-',
                info.get('created_at') or '-',
                info.get('encrypted_count', 0),
                '有' if info.get('salt') else '无',
                info.get('binding_count', 0),
                binding_text))
