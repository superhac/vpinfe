from PyQt6.QtWidgets import QWidget, QGraphicsView, QGraphicsScene, QGraphicsProxyWidget
from PyQt6 import uic
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QTransform

class HUDOverlay(QWidget):
    def __init__(self, parent=None, rotation_angle=0):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)

        self.rotation_angle = rotation_angle

        # Setup QGraphicsView
        self.view = QGraphicsView(self)
        self.view.setStyleSheet("background: transparent; border: none;")
        self.view.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.view.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        # Setup QGraphicsScene and proxy
        self.scene = QGraphicsScene(self)
        self.view.setScene(self.scene)

         # Load UI into a widget (not into self)
        self.ui_widget = uic.loadUi("default-ui-template/hud.ui")
        self.ui_widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.proxy = QGraphicsProxyWidget()
        self.proxy.setWidget(self.ui_widget)
        self.scene.addItem(self.proxy)
        
        # Apply rotation with center adjustment
        self.apply_rotation()
        self.setVisible(True)

        # Force layout update later to avoid geometry 0x0 during init
        QTimer.singleShot(0, self.force_resize)

    def apply_rotation(self):
        rect = self.proxy.boundingRect()
        center = rect.center()
        transform = QTransform()
        transform.translate(center.x(), center.y())
        transform.rotate(self.rotation_angle)
        transform.translate(-center.x(), -center.y())
        self.proxy.setTransform(transform)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.view.setGeometry(0, 0, self.width(), self.height())
        self.view.setSceneRect(0, 0, self.width(), self.height())

    def force_resize(self):
        self.view.setGeometry(0, 0, self.width(), self.height())
        self.view.setSceneRect(0, 0, self.width(), self.height())




