import cv2
from PyQt5.QtGui import QPixmap, qRgb
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtMultimediaWidgets import QVideoWidget
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *

from loguru import logger
from PIL import ImageGrab

from src.layout.click_jump_slider import ClickJumpSlider

logger.add("log/file_{time:YYYY-MM-DD}.log", rotation="500 MB", enqueue=True, format="{time} {level} {message}",
           filter="",
           level="INFO")


class VideoShowLayout(QVBoxLayout):

    def __init__(self, main_window, *args, **kwargs):
        super(*args, **kwargs).__init__(*args, **kwargs)

        self.main_window = main_window
        self.path = ''
        self.cut_state = 0
        self.cut_start = 0.0
        self.cut_end = 0.0

        self.titleQLabel = QLabel("Title")
        self.titleQLabel.setText("Title")
        self.titleQLabel.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.titleQLabel.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.addWidget(self.titleQLabel)

        self.player = QMediaPlayer()
        # 定义视频显示的widget
        self.video_widget = QVideoWidget()
        self.video_widget.show()
        # 视频播放输出的widget，就是上面定义的
        self.player.setVideoOutput(self.video_widget)

        self.qscrollarea = QScrollArea()

        screen = ImageGrab.grab()
        screen_width, screen_height = screen.size
        # logger.info(f"屏幕大小为：{screen_width} x {screen_height}")
        self.screen_width = int(screen_width * 2 / 3)
        self.screen_height = int(screen_height * 2 / 3)
        # logger.info(str(self.screen_width), str(self.screen_height))
        self.qscrollarea.setGeometry(QRect(0, 0, self.screen_width, self.screen_height))

        self.qscrollarea.setWidgetResizable(True)
        self.qscrollarea.setWidget(self.video_widget)

        self.bar_hbox = QHBoxLayout()
        self.bar_hbox.setObjectName("bar_hbox")

        self.bar_slider = ClickJumpSlider(Qt.Horizontal)
        self.bar_slider.valueChanged.connect(self.slider_progress_moved)
        self.bar_slider.setObjectName("bar_slider")

        self.bar_label = QLabel(self.bar_slider)
        self.bar_label.setMaximumSize(QSize(50, 10))
        self.bar_label.setObjectName("bar_label")

        self.bar_hbox.addWidget(self.bar_slider)
        self.bar_hbox.addWidget(self.bar_label)

        self.stop_btn = QPushButton()
        self.stop_btn.setText("暂停")
        self.stop_btn.clicked.connect(self.run_or_stop)
        self.bar_hbox.addWidget(self.stop_btn)

        self.cut_bar_hbox = QHBoxLayout()
        self.cut_bar_hbox.setObjectName("cut_bar_hbox")

        self.cut_bar_slider = ClickJumpSlider(Qt.Horizontal)
        self.cut_bar_slider.valueChanged.connect(self.cut_slider_progress_clicked)
        self.cut_bar_slider.setObjectName("cut_bar_slider")

        self.cut_bar_label_start = QLabel(self.cut_bar_slider)
        self.cut_bar_label_start.setMaximumSize(QSize(50, 10))
        self.cut_bar_label_start.setObjectName("cut_bar_label_start")
        self.cut_bar_label_start.setText("开始")
        self.cut_bar_label_end = QLabel(self.cut_bar_slider)
        self.cut_bar_label_end.setMaximumSize(QSize(50, 10))
        self.cut_bar_label_end.setObjectName("cut_bar_label_end")
        self.cut_bar_label_end.setText("结束")

        self.cut_bar_hbox.addWidget(self.cut_bar_slider)
        self.cut_bar_hbox.addWidget(self.cut_bar_label_start)
        self.cut_bar_hbox.addWidget(self.cut_bar_label_end)

        self.cut_btn = QPushButton()
        self.cut_btn.setText("剪切")
        self.cut_btn.clicked.connect(self.video_cut)
        self.cut_bar_hbox.addWidget(self.cut_btn)

        self.screenshot_button = QPushButton('截图')
        self.screenshot_button.clicked.connect(self.take_screenshot)
        self.bar_hbox.addWidget(self.screenshot_button)

        self.fullScreenBtn = QPushButton("全屏")
        self.bar_hbox.addWidget(self.fullScreenBtn)
        self.fullScreenBtn.pressed.connect(main_window.full_screen_custom)

        self.bar_hbox_qwidget = QWidget()
        self.bar_hbox_qwidget.setLayout(self.bar_hbox)

        self.cut_bar_hbox_qwidget = QWidget()
        self.cut_bar_hbox_qwidget.setLayout(self.cut_bar_hbox)

        self.addWidget(self.qscrollarea)
        self.addWidget(self.bar_hbox_qwidget)
        self.addWidget(self.cut_bar_hbox_qwidget)

        self.timer = QTimer()  # 定义定时器
        self.maxValue = 1000  # 设置进度条的最大值

        self.state = False

    def take_screenshot(self):

        try:
            # 读取视频
            vc = cv2.VideoCapture(self.path)
            # 设置读取位置，1000毫秒
            vc.set(cv2.CAP_PROP_POS_MSEC, self.player.position())
            # 读取当前帧，rval用于判断读取是否成功
            rval, frame = vc.read()
            if rval:
                save_path = self.path.replace('.mp4', "_" + str(self.player.position()) + ".jpg")
                logger.info("save_path: " + save_path)
                cv2.imencode('.jpg', frame)[1].tofile(save_path)
                qimg = self.CV2QImage(frame)

                # 将图像复制到粘贴板
                mime_data = QMimeData()
                mime_data.setImageData(qimg)
                QApplication.clipboard().setMimeData(mime_data)
            else:
                logger.info("视频加载失败失败")
        except Exception as e:
            logger.info(f"获取视频封面图失败: {e}")

    def CV2QImage(self, cv_image):

        width = cv_image.shape[1]  # 获取图片宽度
        height = cv_image.shape[0]  # 获取图片高度

        pixmap = QPixmap(width, height)  # 根据已知的高度和宽度新建一个空的QPixmap,
        qimg = pixmap.toImage()  # 将pximap转换为QImage类型的qimg

        # 循环读取cv_image的每个像素的r,g,b值，构成qRgb对象，再设置为qimg内指定位置的像素
        for row in range(0, height):
            for col in range(0, width):
                b = cv_image[row, col, 0]
                g = cv_image[row, col, 1]
                r = cv_image[row, col, 2]

                pix = qRgb(r, g, b)
                qimg.setPixel(col, row, pix)

        return qimg  # 转换完成，返回

    def run_or_stop(self):
        if self.state:
            self.player.pause()
            self.timer.stop()
            self.state = False
            self.stop_btn.setText("播放")
        else:
            self.player.play()
            self.timer.start()
            self.state = True
            self.stop_btn.setText("暂停")

    def slider_progress_moved(self):
        self.timer.stop()
        self.player.setPosition(round(self.bar_slider.value() * self.player.duration() / 100))

    def cut_slider_progress_clicked(self):
        tangent = self.cut_bar_slider.value() / 100 * self.player.duration()
        # logger.info('cut_slider_progress_clicked: ' + str(self.cut_bar_slider.value()) + ":" + str(tangent))
        m, s = divmod(tangent / 1000, 60)
        h, m = divmod(m, 60)
        text = "%02d:%02d:%02d" % (h, m, s)
        if self.cut_state % 2 == 0:
            self.cut_bar_label_start.setText(text)
            self.cut_start = tangent
        else:
            self.cut_bar_label_end.setText(text)
            self.cut_end = tangent

        self.cut_state += 1

    def fcku(self, filePath):
        logger.info(filePath)
        self.titleQLabel.setText(filePath)
        self.path = filePath

        # 选取视频文件，很多同学要求一打开就能播放，就是在这个地方填写默认的播放视频的路径
        self.player.setMedia(QMediaContent(QUrl.fromLocalFile(r'' + filePath)))
        self.player.play()
        self.state = True

        self.timer.setInterval(1000)
        self.timer.start()
        self.timer.timeout.connect(self.onTimerOut)

    def onTimerOut(self):
        position = self.player.position()
        duration = self.player.duration()
        value = round(position * 100 / duration)
        self.bar_slider.setValue(value)

        m, s = divmod(self.player.position() / 1000, 60)
        h, m = divmod(m, 60)
        text = "%02d:%02d:%02d" % (h, m, s)
        self.bar_label.setText(text)
        # self.widget.doubleClickedItem.connect(self.videoDoubleClicked)

    def is_video(self, path):
        return path.lower().endswith(
            ('.mp4'))

    def setVisible(self, visible):
        self.titleQLabel.setVisible(visible)

    def video_cut(self):

        cap = cv2.VideoCapture(self.path)  # 打开视频文件
        fps = cap.get(cv2.CAP_PROP_FPS)  # 获得视频文件的帧率
        width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)  # 获得视频文件的帧宽
        height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)  # 获得视频文件的帧高

        file_name = (self.path.replace('.mp4', "_")
                     + str(int(self.cut_start * 1000)).replace('.', '') + '-'
                     + str(int(self.cut_end * 1000)).replace('.', '') + '.mp4')

        size = (int(width), int(height))  # 保存视频的大小

        videoWriter = cv2.VideoWriter(file_name, cv2.VideoWriter_fourcc('X', 'V', 'I', 'D'), fps, size)

        start = int(self.cut_start / 1000 * fps)
        end = int(self.cut_end / 1000 * fps)

        logger.info(str(start) + '_' + str(end))

        i = 0
        while True:
            success, frame = cap.read()
            if success:
                i += 1
                # logger.info('i = ', i)
                if start <= i <= end:
                    # logger.info('写入第' + str(i) + '帧')
                    videoWriter.write(frame)
            else:
                # logger.info('end')
                break

        cap.release()
        videoWriter.release()

        logger.info('视频截取成功：' + file_name)
