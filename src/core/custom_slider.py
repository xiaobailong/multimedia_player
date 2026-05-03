from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QSlider, QStyleOptionSlider, QStyle

from loguru import logger


class CustomSlider(QSlider):

    def __init__(self, *__args):
        super().__init__( *__args)
        self.move_type = 'click'

    def mousePressEvent(self, event):

        self.move_type = 'click'

        try:
            # Bug D 修复: subControlRect 在 widget 未完全初始化时可能崩溃
            # 使用 try/except 保护，确保 slider 在任何状态下都能响应点击
            option = QStyleOptionSlider()
            self.initStyleOption(option)
            style = self.style()
            if style is None:
                # 样式未就绪时直接设置值
                self._set_value_from_event(event)
                return

            rect = style.subControlRect(
                QStyle.ComplexControl.CC_Slider,
                option,
                QStyle.SubControl.SC_SliderHandle,
                self
            )

            if rect is not None and rect.contains(event.pos()):
                super(CustomSlider, self).mousePressEvent(event)
                return
        except Exception as e:
            logger.warning(f"CustomSlider mousePressEvent 异常: {e}")
            # 异常时直接设置值，不中断用户操作

        self._set_value_from_event(event)

    def _set_value_from_event(self, event):
        """根据鼠标事件位置设置滑块值"""
        try:
            style = self.style()
            if style is None:
                return
            if self.orientation() == Qt.Orientation.Horizontal:
                self.setValue(style.sliderValueFromPosition(
                    self.minimum(), self.maximum(),
                    event.x() if not self.invertedAppearance() else (self.width(
                    ) - event.x()), self.width()))
            else:
                self.setValue(style.sliderValueFromPosition(
                    self.minimum(), self.maximum(),
                    (self.height() - event.y()) if not self.invertedAppearance(
                    ) else event.y(), self.height()))
        except Exception as e:
            logger.warning(f"CustomSlider _set_value_from_event 异常: {e}")
