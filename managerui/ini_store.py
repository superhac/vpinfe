# app/ini_store.py
from __future__ import annotations
from configparser import RawConfigParser
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Tuple

class CaseSensitiveRawConfigParser(RawConfigParser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.optionxform = lambda s: s  # keep case

def _read_ini(path: Path) -> CaseSensitiveRawConfigParser:
    cfg = CaseSensitiveRawConfigParser()
    if path.exists():
        with path.open('r', encoding='utf-8', errors='ignore') as f:
            cfg.read_file(f)
    return cfg

def _write_ini(path: Path, cfg: CaseSensitiveRawConfigParser) -> None:
    with path.open('w', encoding='utf-8', newline='\n') as f:
        cfg.write(f)

def _to_dict(cfg: CaseSensitiveRawConfigParser) -> Dict[str, Dict[str, str]]:
    data: Dict[str, Dict[str, str]] = {}
    for section in cfg.sections():
        if section.startswith('Default '):
            continue
        sect: Dict[str, str] = {}
        for opt in cfg.options(section):
            sect[opt] = cfg.get(section, opt, fallback='') or ''
        data[section] = sect
    return data

@dataclass
class DiffItem:
    section: str
    option: str
    old: str
    new: str

class IniStore:
    """Global INI state + pub/sub for widget bindings."""
    def __init__(self, ini_path: Path):
        self.ini_path = ini_path
        self.cfg = _read_ini(ini_path)
        self.original = _to_dict(self.cfg)
        self.staged = {s: dict(kv) for s, kv in self.original.items()}
        # listeners: (section, option) -> list[callback(new_value:str)]
        self._listeners: Dict[Tuple[str, str], List[Callable[[str], None]]] = {}

    def get(self, section: str, option: str) -> str:
        return self.staged.get(section, {}).get(option, '')

    def set(self, section: str, option: str, value: str) -> None:
        self.staged.setdefault(section, {})[option] = value
        self._notify(section, option, value)

    def on_change(self, section: str, option: str, cb: Callable[[str], None]) -> None:
        self._listeners.setdefault((section, option), []).append(cb)

    def _notify(self, section: str, option: str, value: str) -> None:
        for cb in self._listeners.get((section, option), []):
            cb(value)

    def reload(self) -> None:
        """Reload from disk and push fresh values to bound widgets."""
        self.cfg = _read_ini(self.ini_path)
        self.original = _to_dict(self.cfg)
        self.staged = {s: dict(kv) for s, kv in self.original.items()}
        for (section, option), cbs in list(self._listeners.items()):
            val = self.get(section, option)
            for cb in cbs:
                cb(val)

    def diff(self) -> List[DiffItem]:
        diffs: List[DiffItem] = []
        secs = set(self.original.keys()) | set(self.staged.keys())
        for s in sorted(secs):
            oo = self.original.get(s, {})
            nn = self.staged.get(s, {})
            opts = set(oo.keys()) | set(nn.keys())
            for o in sorted(opts):
                old = oo.get(o, '')
                new = nn.get(o, '')
                if old != new:
                    diffs.append(DiffItem(s, o, old, new))
        return diffs

    def save(self) -> None:
        """Apply staged values to config and write file."""
        for section, kv in self.staged.items():
            if not self.cfg.has_section(section):
                self.cfg.add_section(section)
            for opt, val in kv.items():
                self.cfg.set(section, opt, val)
        _write_ini(self.ini_path, self.cfg)
        self.original = {s: dict(kv) for s, kv in self.staged.items()}
