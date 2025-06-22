from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt, QTimer, QRectF
import multiprocessing
from ui.imagecacheworker import ImageCacheWorker
from ui.imageworkermanager import ImageWorkerManager
from inputdefs import InputDefs
from globalsignals import dispatcher
import logging
import sys

logger = None

class FullscreenWindow(QGraphicsView):
    
    windows = []
    menuWindow = None
    isMenuUp = False
    
    @staticmethod
    def iconify_all():
        for win in FullscreenWindow.windows:
            if win.isVisible():
                win.original_geometry = win.geometry()
                win.original_screen = win.screen()
                win.showNormal()
                QTimer.singleShot(100, win.showMinimized)

    @staticmethod
    def deiconify_all(delay=600):
        def restore_one(index):
            if index >= len(FullscreenWindow.windows):
                return
            win = FullscreenWindow.windows[index]
            if win.original_screen:
                geo = win.original_screen.geometry()
                win.move(geo.topLeft())
            win.showNormal()
            win.raise_()
            win.activateWindow()
            if win.windowHandle():
                win.windowHandle().requestActivate()
            QTimer.singleShot(100, lambda: win.showFullScreen())
            QTimer.singleShot(delay, lambda: restore_one(index + 1))
        restore_one(0)
    
    def __init__(self, screen, screenname, tables, stylesheet=None, menuRotation=0):
        super().__init__()
        
        # logging
        global logger
        logger = logging.getLogger()
        
        dispatcher.customEvent.connect(self.handle_event)
        self.assignedScreen = screen
        self.screenName = screenname
        self.menuRotation = menuRotation
        self.tables = tables
        
        # image caching
        self.cacheManager = None
        self.image_cache_worker = None
        self.image_command_queue = None
        self.image_result_queue = None
        self.backgroundImagePixmap = None
        
        # Fullscreen setup
        self.setFrameStyle(0)
        self.setLineWidth(0)
        self.setMidLineWidth(0)
        self.setContentsMargins(0, 0, 0, 0)
        self.setViewportMargins(0, 0, 0, 0)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setWindowState(Qt.WindowState.WindowFullScreen)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setGeometry(self.assignedScreen.geometry())

        # Set up scene
        self.scene = QGraphicsScene()
        self.setScene(self.scene)
        
        self.showFullScreen()
        FullscreenWindow.windows.append(self)
        
        # setup image caching
        self.addCacheManager()

    def handle_event(self, event_type: str, data: dict):
        match event_type:
            case "gamepad":
                logger.debug(f"Receiver got event: {event_type} with data: {data}")
                match data['op']:
                    case InputDefs.LEFT:
                        self.prevImage()
                    case InputDefs.RIGHT:
                         self.nextImage()
                    case InputDefs.SELECT:
                        if FullscreenWindow.menuWindow == self:
                            dispatcher.customEvent.emit("main", {"op": "lanuch","index":  self.cacheManager.current_index, 
                                                                 "windowClass":f"{self.__class__.__module__}.{self.__class__.__name__}"})
                    case InputDefs.MENU:
                        pass
                        #self.toggle_menu()
                    case _:
                        logger.debug(f"No action for that control send.")
            case "windows":
                if data['value'] == 'quit':
                    self.quit()
    
    def getCurrentIndex(self):
        return self.cacheManager.current_index
    
    def getClass(self):
        return f"{self.__class__.__module__}.{self.__class__.__name__}"             
    
    def addCacheManager(self):
        if sys.platform == "darwin":
            multiprocessing.set_start_method('spawn', force=True)

        self.image_command_queue = multiprocessing.Queue()
        self.image_result_queue = multiprocessing.Queue()
        self.image_cache_worker = ImageCacheWorker(self.tables, self.screenName, self.image_command_queue, self.image_result_queue, self.assignedScreen.geometry())
        self.cacheManager = ImageWorkerManager(self, self.tables,  self.image_command_queue, self.image_result_queue)
        self.cacheManager.loadLogo()
        self.image_cache_worker.start()
        QTimer.singleShot(5000, lambda:  self.cacheManager.set_image_by_index(0))  # load first image after 5 secs.. logo time 
        
    def set_pixmap(self, pixmap: QPixmap):
        if not isinstance(pixmap, QPixmap):
            raise TypeError("Expected a QPixmap")

        #  scale if screen and image size don't match
        if pixmap.size() != self.assignedScreen.geometry().size():
            pixmap = pixmap.scaled(
                self.assignedScreen.geometry().size(),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )

        if hasattr(self, "backgroundImagePixmap") and isinstance(self.backgroundImagePixmap, QGraphicsPixmapItem):
            self.backgroundImagePixmap.setPixmap(pixmap)
        else:
            self.backgroundImagePixmap = QGraphicsPixmapItem(pixmap)
            self.scene.addItem(self.backgroundImagePixmap)

        self.scene.setSceneRect(QRectF(self.backgroundImagePixmap.boundingRect()))
         
    def nextImage(self):
        print("next image")
        self.cacheManager.load_next()

    def prevImage(self):
        print("prev image")
        self.cacheManager.load_previous()
        
    def quit(self):
        self.image_command_queue.put('quit')   # Tell worker to clean up and exit
        self.image_cache_worker.join()