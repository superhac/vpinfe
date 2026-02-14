import os
import json
import shutil
import tempfile
from pathlib import Path
from nicegui import ui, run
from platformdirs import user_config_dir

from common.iniconfig import IniConfig

CONFIG_DIR = Path(user_config_dir("vpinfe", "vpinfe"))
VPINFE_INI_PATH = CONFIG_DIR / 'vpinfe.ini'

_INI_CFG = None


def _get_ini_config():
    global _INI_CFG
    if _INI_CFG is None:
        _INI_CFG = IniConfig(str(VPINFE_INI_PATH))
    return _INI_CFG


def _get_tables_path() -> str:
    try:
        cfg = _get_ini_config()
        tableroot = cfg.config.get('Settings', 'tablerootdir', fallback='').strip()
        if tableroot:
            return os.path.expanduser(tableroot)
    except Exception:
        pass
    return os.path.expanduser('~/tables')


def _scan_tables():
    """Scan for tables with .info and .vpx files, return list of dicts."""
    tables_path = _get_tables_path()
    tables = []

    if not os.path.exists(tables_path):
        return tables

    for root, _, files in os.walk(tables_path):
        current_dir = os.path.basename(root)
        info_file = f"{current_dir}.info"

        if info_file in files:
            vpx_files = [f for f in files if f.lower().endswith('.vpx')]
            if not vpx_files:
                continue

            meta_path = os.path.join(root, info_file)
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    raw = json.load(f)

                info = raw.get("Info", {})
                name = (info.get("Title") or current_dir).strip()
                manufacturer = info.get("Manufacturer", "")
                year = info.get("Year", "")

                tables.append({
                    'name': name,
                    'manufacturer': manufacturer,
                    'year': str(year) if year else '',
                    'table_dir_name': current_dir,
                    'table_path': root,
                })
            except Exception:
                pass

    tables.sort(key=lambda t: t['name'].lower())
    return tables


def build():
    ui.dark_mode(value=True)

    ui.add_head_html('''
    <style>
        body {
            margin: 0 !important;
            padding: 0 !important;
            background-color: #111827 !important;
        }
    </style>
    ''')

    with ui.column().classes('w-full items-center p-4'):
        ui.label('VPinFE Mobile VPXZ Download').classes('text-2xl font-bold text-white mb-4')

        loading = ui.label('Loading tables...').classes('text-gray-400')

        table_container = ui.column().classes('w-full')

        async def load_tables():
            tables = await run.io_bound(_scan_tables)
            loading.set_visibility(False)

            rows = []
            for t in tables:
                parts = [p for p in [t['manufacturer'], t['year']] if p]
                display = f"{t['name']} ({' '.join(parts)})" if parts else t['name']
                rows.append({
                    'display_name': display,
                    'table_dir_name': t['table_dir_name'],
                })

            columns = [
                {'name': 'display_name', 'label': 'Table', 'field': 'display_name', 'align': 'left', 'sortable': True},
            ]

            with table_container:
                tbl = ui.table(
                    columns=columns,
                    rows=rows,
                    row_key='table_dir_name',
                    pagination={'rowsPerPage': 25},
                ).classes('w-full').props('dark dense')

                tbl.add_slot('body-cell-display_name', '''
                    <q-td :props="props">
                        <q-btn flat dense icon="download" color="blue" class="q-mr-sm"
                            @click.stop="$parent.$emit('download', props.row)" />
                        {{ props.row.display_name }}
                    </q-td>
                ''')

                async def handle_download(e):
                    name = e.args['table_dir_name']

                    with ui.dialog() as dlg, ui.card().classes('bg-gray-800 p-6'):
                        with ui.row().classes('items-center gap-3'):
                            ui.spinner(size='lg')
                            ui.label(f'Preparing {name}.vpxz ...').classes('text-white')
                    dlg.open()

                    def create_zip():
                        tables_path = _get_tables_path()
                        tmp_dir = tempfile.mkdtemp()
                        zip_base = os.path.join(tmp_dir, name)
                        zip_path = shutil.make_archive(zip_base, 'zip', root_dir=tables_path, base_dir=name)
                        vpxz_path = zip_base + '.vpxz'
                        os.rename(zip_path, vpxz_path)
                        print(f"[Mobile] Created download archive: {vpxz_path}")
                        with open(vpxz_path, 'rb') as f:
                            data = f.read()
                        shutil.rmtree(tmp_dir, ignore_errors=True)
                        print(f"[Mobile] Cleaned up temp archive: {tmp_dir}")
                        return data

                    zip_bytes = await run.io_bound(create_zip)
                    dlg.close()
                    ui.download(zip_bytes, f'{name}.vpxz')

                tbl.on('download', handle_download)

        ui.timer(0.1, load_tables, once=True)
