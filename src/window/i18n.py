# -*- coding: utf-8 -*-
"""Qt 标准对话框的中文翻译。

不做这一步时，QMessageBox（是 / 否 / 确定 / 取消）、QFileDialog 等
Qt 标准对话框的按钮仍然是英文 —— 即使我们自己的文案全写成中文。
"""
from PyQt5.QtCore import QLibraryInfo, QTranslator
from PyQt5.QtWidgets import QApplication
from loguru import logger


class StandardButtonTranslator(QTranslator):
    """标准对话框按钮的兜底中文映射。

    Windows 平台主题（QPlatformTheme）取「是/否/确定/取消」时不会命中
    qt_zh_CN.qm 里的 QDialogButtonBox 条目，实测按钮仍显示 &Yes / &No / OK / Cancel。
    这里补一层 translate() 覆盖，context 不匹配时返回空串，交给后面的 Qt 翻译。
    """

    _TEXTS = {
        '&Yes': '是(&Y)', 'Yes': '是(&Y)',
        '&No': '否(&N)', 'No': '否(&N)',
        'OK': '确定', '&OK': '确定(&O)',
        'Cancel': '取消', '&Cancel': '取消(&C)',
        '&Apply': '应用(&A)', 'Apply': '应用',
        'Close': '关闭', '&Close': '关闭',
        'Abort': '中止', 'Retry': '重试', 'Ignore': '忽略',
        '&Save': '保存(&S)', 'Save': '保存',
        '&Discard': '放弃(&D)', 'Discard': '放弃',
        'Open': '打开', '&Open': '打开',
        'Help': '帮助', 'Reset': '重置',
        'Restore Defaults': '恢复默认值',
    }

    def translate(self, context, source_text, disambiguation=None, n=-1):
        if context in ('QPlatformTheme', 'QDialogButtonBox'):
            return self._TEXTS.get(source_text, '')
        return ''


def install_chinese_translator():
    """加载 Qt 自带的中文翻译（qt_zh_CN.qm）+ 标准按钮兜底。

    重复调用是安全的：应用上已经装过就直接返回。
    """
    app = QApplication.instance()
    if app is None:
        return
    if getattr(app, '_zh_cn_translator', None) is not None:
        return
    translations_path = QLibraryInfo.location(QLibraryInfo.TranslationsPath)
    translator = QTranslator(app)
    if translator.load('qt_zh_CN', translations_path):
        app.installTranslator(translator)
        app._zh_cn_translator = translator
        logger.info(f"已加载 Qt 中文翻译: {translations_path}")
    else:
        logger.warning(f"未找到 qt_zh_CN.qm（{translations_path}），标准对话框按钮可能仍为英文")

    button_translator = StandardButtonTranslator(app)
    app.installTranslator(button_translator)
    app._zh_cn_button_translator = button_translator
