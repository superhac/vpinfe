from PyQt6.QtCore import QObject, pyqtSignal

class GlobalSignals(QObject):
    customEvent = pyqtSignal(str, dict)

dispatcher = GlobalSignals()

