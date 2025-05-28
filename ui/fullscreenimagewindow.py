from PyQt6 import uic
from PyQt6.QtWidgets import (
    QApplication, QWidget, QGraphicsView, QGraphicsScene, QGraphicsProxyWidget
)
from PyQt6.QtGui import QPixmap, QTransform
from PyQt6.QtCore import Qt, QObject, QTimer
from pinlog import get_logger
from inputdefs import InputDefs
import screennames
from tables import Tables
from filesutils import FilesUtils
import sys

logger = None

class FullscreenImageWindow(QWidget):
    windows = []  # Static array of all the windows of this type.
    menuWindow = None # static the window thats going to render the window
    isMenuUp = False # static is the menu up?
    
    @staticmethod
    def iconify_all():
        for win in FullscreenImageWindow.windows:
            if win.isVisible():
                win.original_geometry = win.geometry()
                win.original_screen = win.screen()
                
                win.showNormal()  # Must exit fullscreen first
                QTimer.singleShot(100, win.showMinimized)  # Delay avoids GNOME race

        # Start restore after delay (avoid nesting inside iconify loop)
        QTimer.singleShot(5000, lambda: FullscreenImageWindow.deiconify_all())

    @staticmethod
    def deiconify_all(delay=600):
        def restore_one(index):
            if index >= len(FullscreenImageWindow.windows):
                return

            win = FullscreenImageWindow.windows[index]
            print(f"Restoring: {win.windowTitle()}")

            # Force re-position to original screen
            if win.original_screen:
                geo = win.original_screen.geometry()
                win.move(geo.topLeft())  # or use win.original_geometry if needed

            win.showNormal()
            win.raise_()
            win.activateWindow()

            if win.windowHandle():
                win.windowHandle().requestActivate()

            # Delay before fullscreen helps with GNOME
            QTimer.singleShot(100, lambda: win.showFullScreen())

            # Move to next window
            QTimer.singleShot(delay, lambda: restore_one(index + 1))

        restore_one(0)
        
    def __init__(self, screen, screenname: screennames.ScreenNames, tables: Tables, stylesheet=None):
        super().__init__()
        global logger
        logger = get_logger()
        
        self.setGeometry(screen.geometry())
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setWindowState(Qt.WindowState.WindowFullScreen)
        self.screenName = screenname
        self.cacheManager = None

        self.screen = screen  # Store for reuse

        if stylesheet:
            self.setStyleSheet(stylesheet)

        self.ui = self.load_ui_widget("default-ui-template/image_window.ui")
        self.ui.setParent(self)
        self.ui.setGeometry(0, 0, self.screen.geometry().width(), self.screen.geometry().height())

        self.ui.imageLabel.setGeometry(0, 0, self.screen.geometry().width(), self.screen.geometry().height())

        self.menu_view = None
        self.showFullScreen()
        FullscreenImageWindow.windows.append(self)

    def toggle_menu(self, menu_ui_file="default-ui-template/menu_template.ui", rotation_degree=0):
        if self == FullscreenImageWindow.menuWindow:
            if self.menu_view is not None: # menu up toggle off
                self.remove_menu()
                return  

            menu_widget = self.load_ui_widget(menu_ui_file)
            menu_widget.show()  # Ensure visible

            buttons = {
                'Resume': menu_widget.findChild(QWidget, 'btnResume'),
                'Test': menu_widget.findChild(QWidget, 'btnTest'),
                'Quit': menu_widget.findChild(QWidget, 'btnQuit'),
                'Iconify': menu_widget.findChild(QWidget, 'btnIconify')
            }

            scene = QGraphicsScene()
            proxy = QGraphicsProxyWidget()
            proxy.setWidget(menu_widget)
            menuON = True

            # Calculate center for rotation
            center = menu_widget.rect().center()
            transform = QTransform()
            transform.translate(center.x(), center.y())
            transform.rotate(rotation_degree)
            transform.translate(-center.x(), -center.y())
            proxy.setTransform(transform)

            screen_geometry = self.geometry()
            screen_center_x = screen_geometry.width() // 2
            screen_center_y = screen_geometry.height() // 2

            # Position the proxy at the center of the screen minus half of the rotated widget size
            # Note: width and height swap depending on rotation, so it's approximate
            if rotation_degree % 180 == 0:
                # 0 or 180 degrees — no width/height swap
                pos_x = screen_center_x - menu_widget.width() // 2
                pos_y = screen_center_y - menu_widget.height() // 2
            else:
                # 90 or 270 degrees — width and height swap
                pos_x = screen_center_x - menu_widget.height() // 2
                pos_y = screen_center_y - menu_widget.width() // 2

            proxy.setPos(pos_x, pos_y)

            scene.addItem(proxy)

            self.menu_view = QGraphicsView(scene, self)
            self.menu_view.setGeometry(0, 0, screen_geometry.width(), screen_geometry.height())
            self.menu_view.setSceneRect(0, 0, screen_geometry.width(), screen_geometry.height())
            self.menu_view.setStyleSheet("background: transparent; border: none;")
            self.menu_view.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            self.menu_view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.menu_view.raise_()
            self.menu_view.show()

            # Connect quit button
            if buttons['Quit'] is not None:
                buttons['Quit'].clicked.connect(QApplication.instance().quit)
            if buttons['Resume'] is not None:
                buttons['Resume'].clicked.connect(self.remove_menu)
            if buttons['Iconify'] is not None:
                buttons['Iconify'].clicked.connect(lambda: FullscreenImageWindow.iconify_all(FullscreenImageWindow.windows))
            if buttons['Test'] is not None:
                buttons['Test'].clicked.connect(self.select_executable)
    
    def select_executable(self):
        executable = FilesUtils.select_file(
            caption="Select an Executable",
            filters=[FilesUtils.FILTER_EXECUTABLE, FilesUtils.FILTER_ALL],
            parent=self
        )
        if executable:
            logger.info(f"Executable selected: {executable}")
        else:
            logger.info("No executable selected.")

    def set_pixmap(self, pixmap: QPixmap):
        if not isinstance(pixmap, QPixmap):
            raise TypeError("Expected a QPixmap")

        # Optional: scale only if needed
        if pixmap.size() != self.screen.geometry().size():
            pixmap = pixmap.scaled(
                self.screen.geometry().width(), self.screen.geometry().height(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation
            )

        self.ui.imageLabel.setPixmap(pixmap)
    
    def remove_menu(self):
        if self == FullscreenImageWindow.menuWindow:
            FullscreenImageWindow.isMenuUp = False
            if self.menu_view is not None:
                scene = self.menu_view.scene()
                if scene is not None:
                    scene.clear()  # Removes all items from the scene

                self.menu_view.deleteLater()  # Schedules the view for deletion
                self.menu_view = None

    def load_ui_widget(self, ui_file):
        return uic.loadUi(ui_file)
    
    def processInputControl(self, control):
        
        if not FullscreenImageWindow.isMenuUp:
            match control:
                case InputDefs.LEFT:
                    self.nextImage()
                case InputDefs.RIGHT:
                    self.prevImage()
                case InputDefs.MENU:
                    print("menu button")
                    if self == FullscreenImageWindow.menuWindow:
                        self.toggle_menu()
                case _:
                    logger.debug(f"No action for that control send.")
                
        
    def addCacheManager(self, cachemanager):
        self.cacheManager = cachemanager
        print("cacheManager set")
    
    def nextImage(self):
        self.cacheManager.load_next()

    def prevImage(self):
        self.cacheManager.load_previous()
