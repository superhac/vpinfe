from PyQt6.QtWidgets import QFileDialog
import sys

class FilesUtils:
    # 🔒 File filter constants (can be used by callers)
    FILTER_ALL = "All Files (*.*)"
    FILTER_CONFIG = "Configuration Files (*.ini)"
    FILTER_IMAGES = "Images (*.png *.jpg *.jpeg)"

    # Platform-aware executable filter
    if sys.platform.startswith("win"):
        FILTER_EXECUTABLE = "Executables (*.exe)"
    elif sys.platform == "darwin":
        FILTER_EXECUTABLE = "Applications (*.app)"
    else:  # Linux and others
        FILTER_EXECUTABLE = "Executables (*)"

    _assets_prefix = (
        sys._MEIPASS + "/assets"
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')
        else "assets"
    )

    @staticmethod
    def get_asset_path(name: str) -> str | None:
        return f"{FilesUtils._assets_prefix}/{name}" if name else None

    @staticmethod
    def _file_selector(caption="Select a File", file_types=None, parent=None):
        file_filter = ";;".join(file_types or [FilesUtils.FILTER_ALL])
        file_path, _ = QFileDialog.getOpenFileName(parent, caption, "", file_filter)
        return file_path

    @staticmethod
    def _directory_selector(caption="Select Directory", parent=None):
        return QFileDialog.getExistingDirectory(parent, caption, "")

    @staticmethod
    def select_file(caption=None, filters=None, parent=None):
        caption = caption or "Select a File"
        filters = filters or [FilesUtils.FILTER_CONFIG, FilesUtils.FILTER_IMAGES, FilesUtils.FILTER_ALL]
        file_path = FilesUtils._file_selector(caption, file_types=filters, parent=parent)
        return file_path

    @staticmethod
    def select_directory(caption="Choose a Folder", parent=None):
        dir_path = FilesUtils._directory_selector(caption, parent=parent)
        return dir_path
