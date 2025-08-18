import os
import configparser
import logging

from nicegui import ui, events

logger = logging.getLogger("tables_ini")

def get_tables_path():
    return os.path.expanduser("~/tables")

def parse_meta_ini(meta_path):
    import os
    import configparser

    config = configparser.ConfigParser()
    config.optionxform = str  # preserve case
    try:
        config.read(meta_path, encoding="utf-8")
        vpsdb = config["VPSdb"] if "VPSdb" in config else {}
        vpxfile = config["VPXFile"] if "VPXFile" in config else {}

        def get_field(field):
            value = vpxfile.get(field, "")
            if not value:
                value = vpsdb.get(field, "")
            return value

        data = {
            "filename": get_field("filename"),
            "id": get_field("id"),
            "name": get_field("name"),
            "manufacturer": get_field("manufacturer"),
            "year": get_field("year"),
            "type": get_field("type"),
            "rom": get_field("rom"),
            "version": get_field("version"),
            "detectnfozzy": get_field("detectnfozzy"),
            "detectfleep": get_field("detectfleep"),
            "detectssf": get_field("detectssf"),
            "detectlut": get_field("detectlut"),
            "detectscorebit": get_field("detectscorebit"),
            "detectfastflips": get_field("detectfastflips"),
            "detectflex": get_field("detectflex"),
            "patch_applied": get_field("patch_applied")
        }
        data["table_path"] = os.path.dirname(meta_path)
        return data
    except Exception as e:
        logger.error(f"Erro ao ler {meta_path}: {e}")
        return {}

def scan_tables_ini():
    tables_path = get_tables_path()
    rows = []
    if not os.path.exists(tables_path):
        logger.warning(f"Tables path does not exist: {tables_path}. Skipping scan.")
        ui.notify("Diretório de tabelas não encontrado. Por favor, crie '~/tables' ou configure o caminho.", type="negative")
        return []

    for root, _, files in os.walk(tables_path):
        if "meta.ini" in files:
            meta_path = os.path.join(root, "meta.ini")
            data = parse_meta_ini(meta_path)
            if data:
                # Adiciona o caminho da mesa para referência
                data["table_path"] = root
                rows.append(data)
    return rows

def load_metadata_from_ini():
    return scan_tables_ini()

def build():
    table_data = load_metadata_from_ini()

    ui.markdown(f"## Installed Tables ({len(table_data)})")
    with ui.row().classes("q-my-md"):
        ui.button("Scan Tables", on_click=lambda: ui.run_javascript('window.location.reload()')).props("color=primary")
        ui.button("Missing Tables", on_click=lambda: ui.run_javascript('window.location.reload()')).props("color=red")

    # Define colunas básicas baseadas nas chaves mais comuns
    columns = [
        {'name': 'filename', 'label': 'Arquivo', 'field': 'filename'},
        {'name': 'id', 'label': 'VPS ID', 'field': 'id'},
        {'name': 'name', 'label': 'Nome', 'field': 'name', 'align': 'left'},
        {'name': 'manufacturer', 'label': 'Fabricante', 'field': 'manufacturer'},
        {'name': 'year', 'label': 'Ano', 'field': 'year'},
        {'name': 'rom', 'label': 'ROM', 'field': 'rom'},
        {'name': 'version', 'label': 'Versão', 'field': 'version'},
        {'name': 'detectnfozzy', 'label': 'NFOZZY', 'field': 'detectnfozzy'},
        {'name': 'detectfleep','label': 'Fleep','field': 'detectfleep'},
        {'name': 'detectssf','label': 'Scorebit','field': 'detectssf'},
        {'name': 'detectlut','label': 'LUT','field': 'detectlut'},
        {'name': 'detectscorebit','label': 'Scorebit','field': 'detectscorebit'},
        {'name': 'detectfastflips','label': 'FastFlips','field': 'detectfastflips'},
        {'name': 'detectflex','label': 'FlexDMD','field': 'detectflex'},
        {'name': 'patch_applied', 'label': 'VPX Patch applied?', 'field': 'patch_applied'}
    ]

    def on_row_click(e: events.GenericEventArguments):
        if len(e.args) > 1:
            row_data = e.args[1]
            table_name = row_data.get('filename') or row_data.get('name')
            if table_name:
                ui.navigate.to(f'/table_details_ini/{table_name}')
            else:
                ui.notify("Erro: Não foi possível obter o nome da tabela.", type="negative")
        else:
            ui.notify("Erro: Formato inesperado do evento de clique na linha.", type="negative")

    ui.table(
        columns=columns,
        rows=table_data,
        row_key='filename'
    ).on('row-click', on_row_click).classes("w-full cursor-pointer")

def build_table_details_page_content(table_data_row):
    ui.label(f"Detalhes da Tabela (INI): {table_data_row.get('filename', table_data_row.get('name',''))}").classes("text-xl font-bold q-my-md")
    ui.separator()
    with ui.column().classes("gap-2 q-my-md"):
        for key, value in table_data_row.items():
            ui.label(f"**{key}:** {value}").props('strong')
    ui.button("Voltar para a Lista de Tabelas (INI)", on_click=lambda: ui.navigate.to('/tables_ini')).classes("mt-4")

