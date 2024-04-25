from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QSlider, QStyleOptionSlider, QStyle


class ClickJumpSlider(QSlider):

    def __init__(self, *__args):
        super().__init__( *__args)
        self.move_type = 'click'

    def mousePressEvent(self, event):

        self.move_type = 'click'

        option = QStyleOptionSlider()
        self.initStyleOption(option)
        rect = self.style().subControlRect(QStyle.CC_Slider, option, QStyle.SC_SliderHandle, self)

        if rect.contains(event.pos()):
            super(ClickJumpSlider, self).mousePressEvent(event)
            return
        if self.orientation() == Qt.Horizontal:
            self.setValue(self.style().sliderValueFromPosition(
                self.minimum(), self.maximum(),
                event.x() if not self.invertedAppearance() else (self.width(
                ) - event.x()), self.width()))
        else:
            self.setValue(self.style().sliderValueFromPosition(
                self.minimum(), self.maximum(),
                (self.height() - event.y()) if not self.invertedAppearance(
                ) else event.y(), self.height()))
