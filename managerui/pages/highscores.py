import os
import io
import base64
import logging
import re
import configparser
from typing import List, Dict, Optional, Tuple
from nicegui import ui
from managerui.nvram_parser import parse_and_dump
from .tables import scan_tables

logger = logging.getLogger('highscores')

def create_tab():
    return ui.tab('Highscores', icon='emoji_events')

def load_wheel_data_uri(table_path: str) -> Optional[str]:
    wheel_path = os.path.join(table_path, 'wheel.png')
    if not os.path.exists(wheel_path):
        return None
    try:
        with open(wheel_path, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode('ascii')
            return f'data:image/png;base64,{b64}'
    except Exception as e:
        logger.warning(f'Falha ao carregar wheel: {wheel_path} ({e})')
        return None

# ----------------------------- Highscore parsing -----------------------------

HS_LINE_RE = re.compile(
    r'^\s*(?P<place>Grand Champion|High Score|First Place|Second Place|Third Place|Fourth Place|Player 1|Player 2|Player 3|Player 4)\s*:\s*(?:(?P<initials>[A-Za-z0-9]{1,4})\s+)?(?P<score>[\d\.\, ]+)\s*$',
    re.IGNORECASE
)

TOTAL_PLAYS_RE = re.compile(r'^\s*Total\s+Plays\s*:\s*(?P<plays>\d+)\s*$', re.IGNORECASE)

PLACE_TO_RANK = {
    'GRAND CHAMPION': 0,
    'HIGH SCORE': 1,
    'FIRST PLACE': 1,
    'PLAYER 1': 1,
    'SECOND PLACE': 2,
    'PLAYER 2': 2,
    'THIRD PLACE': 3,
    'PLAYER 3': 3,
    'FOURTH PLACE': 4,
    'PLAYER 4': 4,
}

RANK_TO_PLACE_INI = {
    1: ('First Place', 'High Score'),
    2: ('Second Place', 'High Score'),
    3: ('Third Place', 'High Score'),
    4: ('Fourth Place', 'High Score'),
}

def numeric_score(value: str) -> int:
    digits = re.sub(r'\D', '', value)
    try:
        return int(digits) if digits else 0
    except Exception:
        return 0

def parse_highscore_lines(lines: List[str]) -> List[Dict[str, str]]:
    entries = []
    for line in lines:
        m = HS_LINE_RE.match(line)
        if not m:
            continue
        place_raw = m.group('place') or ''
        initials = (m.group('initials') or '').strip()
        score_text = (m.group('score') or '').strip()

        place_key = place_raw.upper().strip()
        rank = PLACE_TO_RANK.get(place_key, 99)

        entries.append({
            'place_original': place_raw,
            'place_norm': 'Grand Champion' if rank == 0 else 'High Score' if rank == 1 else place_raw,
            'initials': initials,
            'score': score_text,
            'score_sort': numeric_score(score_text),
            'rank': rank,
        })

    # GC (0) + ranks 1..4
    filtered = [e for e in entries if e['rank'] in (0, 1, 2, 3, 4)]
    filtered.sort(key=lambda e: (e['rank'], -e['score_sort']))
    if any(e['rank'] == 0 for e in filtered):
        trimmed = []
        seen_ranks = set()
        gc_added = False
        for e in filtered:
            if e['rank'] == 0:
                if not gc_added:
                    trimmed.append(e)
                    gc_added = True
            else:
                if e['rank'] not in seen_ranks and len(seen_ranks) < 4:
                    trimmed.append(e)
                    seen_ranks.add(e['rank'])
        filtered = trimmed
    else:
        trimmed = []
        seen_ranks = set()
        for e in filtered:
            if e['rank'] not in seen_ranks and len(seen_ranks) < 4:
                trimmed.append(e)
                seen_ranks.add(e['rank'])
        filtered = trimmed

    return filtered

def parse_total_plays_from_lines(lines: List[str]) -> int:
    for line in lines:
        m = TOTAL_PLAYS_RE.match(line)
        if m:
            try:
                return int(m.group('plays'))
            except Exception:
                return 0
    return 0

def extract_nvram_scores_and_plays(nvram_path: str, rom_from_meta: str) -> Tuple[List[Dict[str, str]], int]:
    """Reads NVRAM and returns (entries, total_plays)."""
    try:
        parser = parse_and_dump(rom_from_meta.lower(), nvram_path, do_dump=False)
        lines = parser.high_scores()  # list[str]
        entries = parse_highscore_lines(lines)
        total_plays = parse_total_plays_from_lines(lines)
        return entries, total_plays
    except Exception as e:
        logger.error(f'Error extracting highscores for {rom_from_meta}: {e}')
        return [], 0

def extract_scores_from_vpreg(rom: str, vpreg_path: Optional[str] = None) -> Tuple[List[Dict[str, str]], int]:
    """Fallback: read highscores from ~/.vpinball/VPReg.ini (section == rom). Returns (entries, total_plays)."""
    try:
        if vpreg_path is None:
            vpreg_path = os.path.expanduser('~/.vpinball/VPReg.ini')
        if not os.path.exists(vpreg_path):
            logger.info(f'VPReg.ini not found at {vpreg_path}')
            return [], 0

        cfg = configparser.ConfigParser(interpolation=None)
        cfg.optionxform = str  
        try:
            with open(vpreg_path, 'r', encoding='utf-8', errors='ignore') as f:
                cfg.read_file(f)
        except UnicodeDecodeError:
            with open(vpreg_path, 'r', encoding='latin-1', errors='ignore') as f:
                cfg.read_file(f)

        sections_map = {s.lower(): s for s in cfg.sections()}
        sec_name = sections_map.get(rom.lower())
        if not sec_name:
            logger.error(f'Section for ROM {rom} not found in {vpreg_path}')
            return [], 0

        sec = cfg[sec_name]
        #print(f'[VPReg] section matched: "{sec_name}" for rom "{rom}"')
        entries: List[Dict[str, str]] = []

        # HighScore1..4 + HighScoreXName
        for rank in (1, 2, 3, 4):
            score_key = f'HighScore{rank}'
            name_key = f'HighScore{rank}Name'
            if score_key in sec:
                score_text = sec.get(score_key, '').strip()
                initials = sec.get(name_key, '').strip()
                place_original, place_norm = RANK_TO_PLACE_INI[rank]
                entries.append({
                    'place_original': place_original,
                    'place_norm': place_norm,
                    'initials': initials,
                    'score': score_text,
                    'score_sort': numeric_score(score_text),
                    'rank': rank,
                })

        total_plays = 0
        if 'TotalGamesPlayed' in sec:
            try:
                total_plays = int(sec.get('TotalGamesPlayed', '0').strip() or '0')
            except Exception:
                total_plays = numeric_score(sec.get('TotalGamesPlayed', '0'))

        entries = [e for e in entries if e['rank'] in (1, 2, 3, 4)]
        entries.sort(key=lambda e: (e['rank'], -e['score_sort']))

        #print(f'[VPReg] entries={len(entries)} plays={total_plays} for section "{sec_name}"')
        #for e in entries:
        #    print(f'[VPReg]  rank={e["rank"]} place="{e["place_original"]}" initials="{e["initials"]}" score="{e["score"]}"')

        return entries, total_plays
    except Exception as e:
        logger.error(f'Error reading VPReg.ini for {rom}: {e}')
        return [], 0

# ----------------------------- UI rendering -----------------------------

def render_panel(tab):
    with ui.tab_panel(tab):
        ui.label('Highscores')

        tables_info = scan_tables()
        rows: List[Dict[str, object]] = []

        for meta in tables_info:
            table_name = meta.get('name') or meta.get('filename') or '(Unknown)'
            rom = (meta.get('rom') or '').strip().lower()

            #print("ROM:", rom)

            table_path = meta.get('table_path', '')
            nvram_path = os.path.join(table_path, 'pinmame', 'nvram', f'{rom}.nv')

            entries: List[Dict[str, str]] = []
            total_plays: int = 0

            # Tries NVRAM and after VPReg.ini
            if os.path.exists(nvram_path):
                entries, total_plays = extract_nvram_scores_and_plays(nvram_path, rom)
                print(f'NVRAM result for "{rom}": entries={len(entries)} plays={total_plays}')
                if not entries:  
                    #print(f'Trying VPReg.ini for ROM "{rom}" (table="{table_name}")')
                    ini_entries, ini_plays = extract_scores_from_vpreg(rom)
                    #print(f'VPReg.ini by ROM "{rom}" -> entries={len(ini_entries)} plays={ini_plays}')
                    if ini_entries:
                        entries = ini_entries
                        total_plays = total_plays or ini_plays
            else:
                logger.info(f'NVRAM not found for {table_name} ({rom}) on {nvram_path}')
                #print(f'Trying VPReg.ini for ROM "{rom}" (table="{table_name}")')
                ini_entries, ini_plays = extract_scores_from_vpreg(rom)
                #print(f'VPReg.ini by ROM "{rom}" -> entries={len(ini_entries)} plays={ini_plays}')
                if ini_entries:
                    entries = ini_entries
                    total_plays = total_plays or ini_plays
            
            if not entries:
                #print(f'No highscores from NVRAM or VPReg for "{rom}" (table="{table_name}")')
                logger.info(f'No extracted highscores: {table_name} ({rom})')
                continue

            primary = next((e for e in entries if e['rank'] == 0), None)
            if primary is None:
                primary = next((e for e in entries if e['rank'] == 1), None)
            if primary is None:
                primary = entries[0]

            others = [e for e in entries if e is not primary]
            wheel_uri = load_wheel_data_uri(table_path)

            rows.append({
                'wheel': wheel_uri,
                'table': table_name,
                'rom': rom.lower(),
                'place': primary['place_norm'] if primary['rank'] in (0, 1) else primary['place_original'],
                'initials': primary['initials'],
                'score': primary['score'],
                'score_sort': primary['score_sort'],
                'others': others,
                'plays': int(total_plays) if isinstance(total_plays, int) else numeric_score(str(total_plays)),
            })
            #print(f'ADDED row "{table_name}" rom="{rom}" entries={len(entries)} plays={total_plays}')

        columns = [
            {'name': 'wheel', 'label': '', 'field': 'wheel', 'sortable': False, 'align': 'left'},
            {'name': 'table', 'label': 'Table', 'field': 'table', 'sortable': True, 'align': 'left'},
            {'name': 'rom', 'label': 'ROM', 'field': 'rom', 'sortable': True, 'align': 'left'},
            {'name': 'place', 'label': 'Place', 'field': 'place', 'sortable': False, 'align': 'left'},
            {'name': 'initials', 'label': 'Initials', 'field': 'initials', 'sortable': False, 'align': 'left'},
            {'name': 'score', 'label': 'Score', 'field': 'score_sort', 'sortable': True, 'align': 'right'},
            {'name': 'plays', 'label': 'Plays', 'field': 'plays', 'sortable': True, 'align': 'right'},
            {'name': 'details', 'label': '', 'field': 'others', 'sortable': False, 'align': 'left'},
        ]

        table = ui.table(
            columns=columns,
            rows=rows,
            row_key='rom',
            pagination={'rowsPerPage': 30}   
        ).classes('w-full')

        # Wheel Image
        table.add_slot('body-cell-wheel', r'''
          <q-td :props="props">
            <img v-if="props.row.wheel"
                 :src="props.row.wheel"
                 style="width:42px;height:42px;border-radius:8px;object-fit:contain" />
            <div v-else style="width:42px;height:42px;border-radius:8px;background:#eee"></div>
          </q-td>
        ''')

        table.add_slot('body-cell-score', r'''
          <q-td :props="props">
            {{ props.row.score }}
          </q-td>
        ''')

        table.add_slot('body-cell-details', r'''
          <q-td :props="props">
            <q-expansion-item dense dense-toggle expand-icon="expand_more"
                              label="See more"
                              v-if="props.row.others && props.row.others.length">
              <div v-for="(e, idx) in props.row.others" :key="idx" class="q-py-xs">
                <div class="text-caption">
                  <b>{{ e.place_original }}</b>:
                  <span v-if="e.initials && e.initials.length">{{ e.initials }} &nbsp </span>{{ e.score }}
                </div>
              </div>
            </q-expansion-item>
            <span v-else class="text-caption text-grey-7">—</span>
          </q-td>
        ''')

        table.props('row-key=rom binary-state')
        table.props('separator=horizontal')
        table.props('wrap-cells')
        table.props('sort-by="table"')

        if not rows:
            ui.notify('No High Score Found!', type='warning')
