from PyQt6 import uic
from PyQt6.QtWidgets import (
    QApplication, QWidget, QGraphicsView, QGraphicsScene, QGraphicsProxyWidget, QPushButton
)
from PyQt6.QtGui import QPixmap, QTransform
from PyQt6.QtCore import Qt, QObject, QTimer
from pinlog import get_logger
from inputdefs import InputDefs
import screennames
from tables import Tables
from filesutils import FilesUtils
import sys
from ui.mainmenu import MainMenu

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
        #QTimer.singleShot(5000, lambda: FullscreenImageWindow.deiconify_all())

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
        self.menu = MainMenu(self, "default-ui-template/menu_template.ui")
        global logger
        logger = get_logger()
        
        self.assignedScreen = screen  # ✅ Avoid shadowing QWidget.screen()
        self.setGeometry(self.assignedScreen.geometry())
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setWindowState(Qt.WindowState.WindowFullScreen)
        self.screenName = screenname
        self.cacheManager = None

        if stylesheet:
            self.setStyleSheet(stylesheet)

        self.ui = self.load_ui_widget("default-ui-template/image_window.ui")
        self.ui.setParent(self)
        self.ui.setGeometry(0, 0, self.assignedScreen.geometry().width(), self.assignedScreen.geometry().height())

        self.ui.imageLabel.setGeometry(0, 0, self.assignedScreen.geometry().width(), self.assignedScreen.geometry().height())

        self.showFullScreen()
        FullscreenImageWindow.windows.append(self)
                    
    def toggle_menu(self, rotation_degree=0):
        if self != FullscreenImageWindow.menuWindow:
            return

        if self.menu.is_visible():
            self.menu.hide()
            FullscreenImageWindow.isMenuUp = False
        else:
            self.menu.show(rotation_degree=rotation_degree)
            FullscreenImageWindow.isMenuUp = True
    
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
        if pixmap.size() != self.assignedScreen.geometry().size():
            pixmap = pixmap.scaled(
                self.assignedScreen.geometry().width(), self.assignedScreen.geometry().height(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation
            )

        self.ui.imageLabel.setPixmap(pixmap)
    
    def remove_menu(self):
        if self == FullscreenImageWindow.menuWindow:
            FullscreenImageWindow.isMenuUp = False
            if hasattr(self, "menu_view") and self.menu_view is not None:
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
                    if self == FullscreenImageWindow.menuWindow:
                        self.toggle_menu()
                case InputDefs.SELECT:
                    return "Launch"
                case _:
                    logger.debug(f"No action for that control send.")
        else:
            print("menu control: ", control)
            if self == FullscreenImageWindow.menuWindow:  # this is the window with the menu!
                match control:
                    case InputDefs.LEFT:
                        self.menu.navigate_down()
                    case InputDefs.RIGHT:
                        self.menu.navigate_up()
                    case InputDefs.SELECT:
                        return self.menu.select()
                    case InputDefs.MENU:
                        self.toggle_menu()
                    case _:
                        logger.debug(f"No action for that control send.")
        return None
                    
    def addCacheManager(self, cachemanager):
        self.cacheManager = cachemanager
        print("cacheManager set")
    
    def nextImage(self):
        self.cacheManager.load_next()

    def prevImage(self):
        self.cacheManager.load_previous()
