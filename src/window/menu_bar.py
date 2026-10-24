# -*- coding: utf-8 -*-
"""主菜单栏构建。

这里只负责「建菜单 + 连信号 + 设置快捷键」；每个菜单项背后做什么，
仍然由 ``window``（各 mixin）里的方法决定。
"""
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import QAction, QActionGroup, QMenuBar

from src.window.theme import MENU_BAR_STYLE


def build_menu_bar(window):
    """构建主菜单栏并返回 QMenuBar。

    需要在别处回写勾选状态的 QAction 全部挂到 ``window`` 上
    （``normal_mode_action`` / ``private_mode_action`` / ``toggle_tree_action`` /
    ``show_control_action`` 等），与重构前保持同一套属性名。
    """
    menu_bar = QMenuBar(window)
    menu_bar.setStyleSheet(MENU_BAR_STYLE)

    # ---- 文件菜单 ----
    file_menu = menu_bar.addMenu("文件(&F)")
    open_action = QAction("打开...(&O)", window)
    open_action.setShortcut(QKeySequence("Ctrl+O"))
    open_action.triggered.connect(window.open_directory)
    file_menu.addAction(open_action)

    file_menu.addSeparator()

    exit_action = QAction("退出(&Q)", window)
    exit_action.setShortcut(QKeySequence("Ctrl+Q"))
    exit_action.triggered.connect(window.close)
    file_menu.addAction(exit_action)

    # ---- 密钥菜单（密册兼容的密钥包导入 / 导出）----
    key_menu = menu_bar.addMenu("密钥(&K)")

    window.import_key_action = QAction("导入密钥...", window)
    window.import_key_action.triggered.connect(window._import_key_package)
    key_menu.addAction(window.import_key_action)

    window.export_key_action = QAction("导出密钥...", window)
    window.export_key_action.triggered.connect(window._export_key_package)
    key_menu.addAction(window.export_key_action)

    key_menu.addSeparator()

    window.key_status_action = QAction("密钥状态...", window)
    window.key_status_action.triggered.connect(window._show_key_status)
    key_menu.addAction(window.key_status_action)

    # ---- 视图菜单 ----
    view_menu = menu_bar.addMenu("视图(&V)")

    mode_group = QActionGroup(window)
    mode_group.setExclusive(True)

    window.normal_mode_action = QAction("普通模式", window)
    window.normal_mode_action.setCheckable(True)
    window.normal_mode_action.setChecked(True)
    window.normal_mode_action.triggered.connect(
        lambda checked: checked and window._toggle_private_mode(False))
    mode_group.addAction(window.normal_mode_action)
    view_menu.addAction(window.normal_mode_action)

    window.private_mode_action = QAction("私密模式", window)
    window.private_mode_action.setCheckable(True)
    window.private_mode_action.setChecked(False)
    window.private_mode_action.triggered.connect(
        lambda checked: checked and window._toggle_private_mode(True))
    mode_group.addAction(window.private_mode_action)
    view_menu.addAction(window.private_mode_action)

    view_menu.addSeparator()

    window.toggle_tree_action = QAction("文件列表面板", window)
    window.toggle_tree_action.setCheckable(True)
    window.toggle_tree_action.setChecked(True)
    window.toggle_tree_action.setShortcut("Ctrl+B")
    window.toggle_tree_action.triggered.connect(window.toggle_tree)
    view_menu.addAction(window.toggle_tree_action)

    # ---- 视图菜单：显示控制器（图片悬浮控制栏的显隐）----
    window.show_control_action = QAction("显示控制器", window)
    window.show_control_action.setCheckable(True)
    window.show_control_action.setChecked(True)
    window.show_control_action.triggered.connect(window._toggle_pic_control_panel)
    view_menu.addAction(window.show_control_action)

    # 点击面板 ✕ 隐藏后，回写菜单勾选状态
    window.pic_show_layout.controlPanelVisibilityChanged.connect(
        window._on_pic_control_panel_visibility_changed)

    # ---- 归集菜单（按评分 / 关键字 / 路径批量拷贝到指定目录）----
    collect_menu = menu_bar.addMenu("归集(&G)")

    window.collect_rating_action = QAction("按评分归集...", window)
    window.collect_rating_action.triggered.connect(
        lambda: window._open_collect_dialog('rating'))
    collect_menu.addAction(window.collect_rating_action)

    window.collect_keyword_action = QAction("按关键字归集...", window)
    window.collect_keyword_action.triggered.connect(
        lambda: window._open_collect_dialog('keyword'))
    collect_menu.addAction(window.collect_keyword_action)

    window.collect_path_action = QAction("按路径归集...", window)
    window.collect_path_action.triggered.connect(
        lambda: window._open_collect_dialog('path'))
    collect_menu.addAction(window.collect_path_action)

    # ---- 设置菜单 ----
    settings_menu = menu_bar.addMenu("设置(&S)")

    window.slideshow_settings_action = QAction("幻灯片...", window)
    window.slideshow_settings_action.triggered.connect(window._show_slideshow_settings)
    settings_menu.addAction(window.slideshow_settings_action)

    # ---- 帮助菜单 ----
    help_menu = menu_bar.addMenu("帮助(&H)")

    window.decoder_info_action = QAction("解码器(&D)...", window)
    window.decoder_info_action.triggered.connect(window._show_decoder_info)
    help_menu.addAction(window.decoder_info_action)

    window.shortcuts_action = QAction("快捷键(&K)...", window)
    window.shortcuts_action.triggered.connect(window._show_shortcuts_dialog)
    help_menu.addAction(window.shortcuts_action)

    help_menu.addSeparator()

    about_action = QAction("关于(&A)...", window)
    about_action.triggered.connect(window._show_about_dialog)
    help_menu.addAction(about_action)

    return menu_bar