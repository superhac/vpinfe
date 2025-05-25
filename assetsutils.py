import sys

class AssetsUtils:
    _prefix = (
        sys._MEIPASS + "/assets/"
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')
        else "assets/"
    )

    @classmethod
    def get_path(cls, name: str) -> str | None:
        return f"{cls._prefix}{name}" if name else None
