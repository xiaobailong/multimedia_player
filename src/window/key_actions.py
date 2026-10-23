# -*- coding: utf-8 -*-
"""密钥管理：导入 / 导出与密册兼容的密钥包、查看密钥状态。"""
from loguru import logger

from src.layout.styled_dialogs import (ask_yes_no, pick_directory, pick_open_file,
                                       show_error, show_info, show_warning)


class KeyActionsMixin:
    """密钥菜单背后的窗口动作。"""

    def _import_key_package(self):
        """导入密册导出的密钥数据库（v2 SQLite，兼容 v1 JSON）。"""
        file_path = pick_open_file(
            self, '导入密册密钥数据库',
            filters=['密钥数据库 (*.db *.json)', '所有文件 (*.*)'])
        if not file_path:
            return

        try:
            summary = self.private_service.inspect_key_package(file_path)
        except Exception as e:
            logger.error(f'检查密钥包失败: {e}')
            summary = None
        if summary is None:
            show_warning(
                self, '导入密钥',
                '该文件不是密册导出的密钥包。\n'
                '（需要密册「设置 → 导出密钥」生成的 .db，或旧版 v1 JSON）')
            return

        detail = ('密钥包版本：%s\n创建时间：%s\n文件记录：%d 条（其中 %d 条带加密密钥）\n包含盐值：%s' % (
            summary.get('version', '-'),
            summary.get('created_at') or '-',
            summary.get('file_count', 0),
            summary.get('encrypted_file_count', 0),
            '是' if summary.get('has_salt') else '否'))
        if not ask_yes_no(
                self, '导入密钥',
                detail + '\n\n导入后将使用该密钥包解开本机的私密文件，继续？'):
            return

        result = self.private_service.import_key_package(file_path)
        if not result.get('ok') and result.get('reason') == 'key_conflict':
            if not ask_yes_no(
                    self, '密钥冲突',
                    result.get('message', '') + '\n\n仍要覆盖本机密钥吗？', default_yes=False):
                self.notice('已取消导入密钥')
                return
            result = self.private_service.import_key_package(file_path, overwrite_key=True)

        if not result.get('ok'):
            show_warning(self, '导入密钥', result.get('message') or '导入失败')
            return

        message = ('密钥导入成功。\n新增文件记录 %d 条，更新 %d 条，跳过 %d 条。' % (
            result.get('imported', 0), result.get('updated', 0), result.get('skipped', 0)))
        show_info(self, '导入密钥', message)
        self.notice(message.replace('\n', ' '))
        self.private_tree_model.refresh()

    def _export_key_package(self):
        """导出与密册完全一致的密钥数据库文件（SQLite，*.db）。"""
        if not self.private_service.has_key():
            show_warning(
                self, '导出密钥',
                '当前还没有可导出的密钥。\n'
                '请先导入 privi 导出的密钥包，或先对文件执行一次加密（会自动生成密钥）。')
            return

        directory = pick_directory(self, '选择密钥导出目录')
        if not directory:
            return

        try:
            path = self.private_service.export_key_package(directory)
        except Exception as e:
            logger.error(f'导出密钥失败: {e}')
            show_error(self, '导出密钥', '导出失败：\n' + str(e))
            return

        show_info(
            self, '导出密钥',
            '已导出与密册完全兼容的密钥数据库：\n%s\n\n'
            '⚠ 密钥包等同于明文密钥，配合私密目录可解密全部文件；'
            '请离线保存或放进加密网盘，不要外传。' % path)
        self.notice('已导出密钥：' + path)

    def _show_key_status(self):
        info = self.private_service.key_info()
        if info is None:
            show_info(
                self, '密钥状态',
                '尚未导入密钥。\n\n'
                '可通过「密钥 → 导入密钥」选择密册导出的 .db 密钥包；\n'
                '也可以直接对私密目录执行加密（会自动生成新密钥）。')
            return
        show_info(
            self, '密钥状态',
            '密钥来源：%s\n创建时间：%s\n已记录加密文件：%d 个\n盐值：%s' % (
                info.get('source') or '-',
                info.get('created_at') or '-',
                info.get('encrypted_count', 0),
                '有' if info.get('salt') else '无'))
