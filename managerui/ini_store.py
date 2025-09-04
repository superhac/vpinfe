# app/ini_store.py
from __future__ import annotations
from configparser import RawConfigParser
import re
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
        # keep raw lines to preserve comments and order on save
        try:
            with self.ini_path.open('r', encoding='utf-8', errors='ignore') as f:
                self._raw_lines: List[str] = f.read().splitlines(keepends=True)
        except FileNotFoundError:
            self._raw_lines = []

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
        try:
            with self.ini_path.open('r', encoding='utf-8', errors='ignore') as f:
                self._raw_lines = f.read().splitlines(keepends=True)
        except FileNotFoundError:
            self._raw_lines = []
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
        """Apply staged values, preserving comments and order in the INI file."""
        diffs = self.diff()
        # Always read current file content to repair any external or previous formatting issues
        try:
            with self.ini_path.open('r', encoding='utf-8', errors='ignore') as f:
                lines = f.read().splitlines(keepends=True)
        except Exception:
            lines = list(self._raw_lines)

        # Heal common formatting issues: value on the next line after 'key ='
        def _heal_broken_assignments(lines_in: List[str]) -> Tuple[List[str], bool]:
            out = list(lines_in)
            changed = False
            i = 0
            while i < len(out) - 1:
                cur = out[i]
                cur_s = cur.rstrip('\r\n')
                # match '  Key   =   '
                m = re.match(r"^(\s*)([^=:#\[\];]+?)(\s*=\s*)$", cur_s)
                if m:
                    lead, key, eq = m.groups()
                    # find first non-blank line after current
                    j = i + 1
                    while j < len(out) and out[j].strip() == '':
                        j += 1
                    if j < len(out):
                        nxt_s = out[j].rstrip('\r\n')
                        # bare value (no '=', ':', not section/comment)
                        if nxt_s and not nxt_s.lstrip().startswith((';', '#', '[')) and ('=' not in nxt_s) and (':' not in nxt_s):
                            out[i] = f"{lead}{key}{eq}{nxt_s}\n"
                            # delete merged line and any blank lines in between
                            del out[i + 1:j + 1]
                            changed = True
                            continue  # re-check current index after merge
                i += 1
            return out, changed

        # run healer until stable (handles multiple occurrences)
        total_healed = False
        while True:
            lines, healed = _heal_broken_assignments(lines)
            total_healed = total_healed or healed
            if not healed:
                break

        def _find_section_bounds(section: str) -> Tuple[int, int]:
            sec_header_re = re.compile(r"^\s*\[\s*" + re.escape(section) + r"\s*\]\s*$")
            any_header_re = re.compile(r"^\s*\[.+\]\s*$")
            start = -1
            for i, ln in enumerate(lines):
                if sec_header_re.match(ln):
                    start = i
                    break
            if start == -1:
                return -1, -1
            # end is next section header or EOF
            for j in range(start + 1, len(lines)):
                if any_header_re.match(lines[j]):
                    return start, j
            return start, len(lines)

        def _replace_option_line(line: str, key: str, new_val: str) -> str:
            # Preserve spacing and trailing comments/quotes when possible
            m = re.match(r"^(\s*)([^=:#]+?)(\s*=\s*)(.*?)(\s*)([;#].*)?$", line)
            if not m:
                return f"{key}={new_val}\n"
            g1, found_key, g3, old_val, g5, comment = m.groups()
            # keep quoting style if present
            sval = old_val.strip()
            if (len(sval) >= 2) and ((sval[0] == sval[-1]) and sval[0] in ('"', "'")):
                new_txt = f"{sval[0]}{new_val}{sval[0]}"
            else:
                new_txt = new_val
            return f"{g1}{found_key}{g3}{new_txt}{g5}{comment or ''}\n"

        for d in diffs:
            sec = d.section
            opt = d.option
            # sanitize new value to a single line
            new_val = str(d.new).replace('\r', '').replace('\n', ' ').strip()

            s_start, s_end = _find_section_bounds(sec)
            if s_start == -1:
                # append new section at EOF
                if lines and not lines[-1].endswith('\n'):
                    lines[-1] += '\n'
                if lines and (lines[-1].strip() != ''):
                    lines.append('\n')
                lines.append(f"[{sec}]\n")
                lines.append(f"{opt}={new_val}\n")
                continue

            # find option in section
            opt_re = re.compile(r"^\s*" + re.escape(opt) + r"\s*=", re.IGNORECASE)
            found_idx = -1
            for i in range(s_start + 1, s_end):
                ln = lines[i]
                if ln.lstrip().startswith((';', '#')):
                    continue
                if opt_re.match(ln):
                    found_idx = i
                    break
            if found_idx != -1:
                # Write a clean 'key = value' line
                lines[found_idx] = f"{opt} = {new_val}\n"
                # Remove any immediate stray bare value line for this key (skip blank lines)
                j = found_idx + 1
                # delete blank lines directly following
                while j < s_end and lines[j].strip() == '':
                    del lines[j]
                    s_end -= 1
                # delete one bare value line if present
                if j < s_end:
                    nxt = lines[j].rstrip('\r\n')
                    if nxt and not nxt.lstrip().startswith((';', '#', '[')) and ('=' not in nxt) and (':' not in nxt):
                        del lines[j]
                        s_end -= 1
            else:
                # insert before s_end, keeping within the section
                insert_pos = s_end
                # ensure there is a newline before insertion if last line not blank
                if insert_pos > 0 and lines[insert_pos-1].strip() != '':
                    lines.insert(insert_pos, f"{opt}={new_val}\n")
                else:
                    lines.insert(insert_pos, f"{opt}={new_val}\n")

        # Heal once more after modifications to catch any new patterns
        while True:
            lines, healed2 = _heal_broken_assignments(lines)
            total_healed = total_healed or healed2
            if not healed2:
                break

        # Removed final fallback concatenation to avoid corrupting valid assignments

        # If nothing changed but we healed, still write back
        if diffs or total_healed:
            with self.ini_path.open('w', encoding='utf-8', newline='\n') as f:
                f.writelines(lines)

        # Refresh in-memory state
        if diffs or total_healed:
            self._raw_lines = lines
            self.cfg = _read_ini(self.ini_path)
            self.original = _to_dict(self.cfg)
            self.staged = {s: dict(kv) for s, kv in self.original.items()}
