from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsProxyWidget, QPushButton, QApplication
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QTransform
from PyQt6 import uic

class MainMenu:
    def __init__(self, parent_window, ui_file):
        self.parent = parent_window
        self.ui_file = ui_file
        self.menu_widget = None
        self.menu_view = None
        self.proxy = None
        self.buttons = {}
        self.button_index = []
        self.focus_index = 0

    def show(self, rotation_degree=0):
        self.menu_widget = uic.loadUi(self.ui_file)
        self.menu_widget.setParent(None)
        self.menu_widget.adjustSize()
        self.menu_widget.show()

        QApplication.processEvents()

        self.buttons = {
            'Resume': self.menu_widget.findChild(QPushButton, 'btnResume'),
            'Test': self.menu_widget.findChild(QPushButton, 'btnTest'),
            'Quit': self.menu_widget.findChild(QPushButton, 'btnQuit'),
            'Iconify': self.menu_widget.findChild(QPushButton, 'btnIconify')
        }

        self.button_index = [self.buttons['Resume'], self.buttons['Test'],
                             self.buttons['Iconify'], self.buttons['Quit']]

        scene = QGraphicsScene()
        self.proxy = QGraphicsProxyWidget()
        self.proxy.setWidget(self.menu_widget)

        # Set transform origin to center of the widget
        center = self.menu_widget.rect().center()
        self.proxy.setTransformOriginPoint(float(center.x()), float(center.y()))

        # Apply rotation if needed
        transform = QTransform()
        transform.rotate(rotation_degree)
        self.proxy.setTransform(transform)

        # Get screen size and compute position
        screen_geometry = self.parent.geometry()
        screen_center_x = screen_geometry.width() // 2
        screen_center_y = screen_geometry.height() // 2

        # Adjust for rotation
        if rotation_degree % 180 == 0:
            w = self.menu_widget.width()
            h = self.menu_widget.height()
        else:
            w = self.menu_widget.height()
            h = self.menu_widget.width()

        pos_x = screen_center_x - w // 2
        pos_y = screen_center_y - h // 2

        self.proxy.setPos(pos_x, pos_y)
        scene.addItem(self.proxy)

        self.menu_view = QGraphicsView(scene, self.parent)
        self.menu_view.setGeometry(0, 0, screen_geometry.width(), screen_geometry.height())
        self.menu_view.setSceneRect(0, 0, screen_geometry.width(), screen_geometry.height())
        self.menu_view.setStyleSheet("background: transparent; border: none;")
        self.menu_view.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.menu_view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.menu_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.menu_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.menu_view.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.menu_view.setInteractive(False)
        self.menu_view.raise_()
        self.menu_view.show()

        self.connect_buttons()
        self.update_styles()

    def connect_buttons(self):
        if self.buttons['Quit']:
            self.buttons['Quit'].clicked.connect(QApplication.instance().quit)
        if self.buttons['Resume']:
            self.buttons['Resume'].clicked.connect(self.hide)
        if self.buttons['Iconify']:
            from ui.fullscreenimagewindow import FullscreenImageWindow
            self.buttons['Iconify'].clicked.connect(FullscreenImageWindow.iconify_all)
        if self.buttons['Test']:
            self.buttons['Test'].clicked.connect(self.parent.select_executable)

    def hide(self):
        if self.menu_view:
            scene = self.menu_view.scene()
            if scene:
                scene.clear()
            self.menu_view.deleteLater()
            self.menu_view = None
            self.proxy = None
            self.menu_widget = None
            self.focus_index = 0

    def navigate_up(self):
        self.focus_index = (self.focus_index - 1) % len(self.button_index)
        self.update_styles()

    def navigate_down(self):
        self.focus_index = (self.focus_index + 1) % len(self.button_index)
        self.update_styles()
        
    def select(self):
        btn = self.button_index[self.focus_index]
        for name, button in self.buttons.items():
            if button == btn:
                return name
        return None

    def update_styles(self):
        for i, btn in enumerate(self.button_index):
            if i == self.focus_index:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #555555;
                        color: white;
                        border: 2px solid #AAAAAA;
                        font-weight: bold;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #333333;
                        color: white;
                        border: none;
                    }
                """)

    def is_visible(self):
        return self.menu_view is not None
