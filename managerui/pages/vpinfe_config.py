from nicegui import ui
from common.iniconfig import IniConfig

INI_PATH = './vpinfe.ini'

def build():
    config = IniConfig(INI_PATH)
    ui.label('VPINFE Config').classes('text-2xl font-bold mb-4')

    with ui.card().classes('w-full p-4'):
        ui.label('Settings').classes('text-lg font-semibold mb-2')
        with ui.row().classes('gap-4'):
            vpxbinpath = ui.input('VPinballX Executable Path', value=config.config.get('Settings', 'vpxbinpath', fallback=''))
        with ui.row().classes('gap-4'):
            tablerootdir = ui.input('Tables Root Directory', value=config.config.get('Settings', 'tablerootdir', fallback=''))
        with ui.row().classes('gap-4'):
            theme = ui.input('Theme', value=config.config.get('Settings', 'theme', fallback=''))

    with ui.card().classes('w-full p-4 mt-4'):
        ui.label('Joystick Mapping').classes('text-lg font-semibold mb-2')
        with ui.row().classes('gap-4'):
            joyleft = ui.input('Joy Left', value=config.config.get('Settings', 'joyleft', fallback=''))
            joyright = ui.input('Joy Right', value=config.config.get('Settings', 'joyright', fallback=''))
            joyup = ui.input('Joy Up', value=config.config.get('Settings', 'joyup', fallback=''))
            joydown = ui.input('Joy Down', value=config.config.get('Settings', 'joydown', fallback=''))
            joyselect = ui.input('Joy Select', value=config.config.get('Settings', 'joyselect', fallback=''))
            joymenu = ui.input('Joy Menu', value=config.config.get('Settings', 'joymenu', fallback=''))
            joyback = ui.input('Joy Back', value=config.config.get('Settings', 'joyback', fallback=''))
            joyexit = ui.input('Joy Exit', value=config.config.get('Settings', 'joyexit', fallback=''))
            joyfav = ui.input('Joy Favorite', value=config.config.get('Settings', 'joyfav', fallback=''))

    with ui.card().classes('w-full p-4 mt-4'):
        ui.label('Logger').classes('text-lg font-semibold mb-2')
        with ui.row().classes('gap-4'):
            logger_level = ui.input('Logger Level', value=config.config.get('Logger', 'level', fallback=''))
            logger_console = ui.input('Logger Console', value=config.config.get('Logger', 'console', fallback=''))
            logger_file = ui.input('Logger File', value=config.config.get('Logger', 'file', fallback=''))

    with ui.card().classes('w-full p-4 mt-4'):
        ui.label('Media').classes('text-lg font-semibold mb-2')
        with ui.row().classes('gap-4'):
            media_tabletype = ui.input('Table Type', value=config.config.get('Media', 'tabletype', fallback=''))
            media_tableres = ui.input('Table Resolution', value=config.config.get('Media', 'tableresolution', fallback=''))

    with ui.card().classes('w-full p-4 mt-4'):
        ui.label('Displays').classes('text-lg font-semibold mb-2')
        with ui.row().classes('gap-4'):
            displays_bg = ui.input('BG Screen ID', value=config.config.get('Displays', 'bgscreenid', fallback=''))
            displays_dmd = ui.input('DMD Screen ID', value=config.config.get('Displays', 'dmdscreenid', fallback=''))
            displays_table = ui.input('Table Screen ID', value=config.config.get('Displays', 'tablescreenid', fallback=''))

    def save_config():
        config.config.set('Settings', 'vpxbinpath', vpxbinpath.value)
        config.config.set('Settings', 'tablerootdir', tablerootdir.value)
        config.config.set('Settings', 'theme', theme.value)
        config.config.set('Settings', 'joyleft', joyleft.value)
        config.config.set('Settings', 'joyright', joyright.value)
        config.config.set('Settings', 'joyup', joyup.value)
        config.config.set('Settings', 'joydown', joydown.value)
        config.config.set('Settings', 'joyselect', joyselect.value)
        config.config.set('Settings', 'joymenu', joymenu.value)
        config.config.set('Settings', 'joyback', joyback.value)
        config.config.set('Settings', 'joyexit', joyexit.value)
        config.config.set('Settings', 'joyfav', joyfav.value)
        config.config.set('Logger', 'level', logger_level.value)
        config.config.set('Logger', 'console', logger_console.value)
        config.config.set('Logger', 'file', logger_file.value)
        config.config.set('Media', 'tabletype', media_tabletype.value)
        config.config.set('Media', 'tableresolution', media_tableres.value)
        config.config.set('Displays', 'bgscreenid', displays_bg.value)
        config.config.set('Displays', 'dmdscreenid', displays_dmd.value)
        config.config.set('Displays', 'tablescreenid', displays_table.value)
        with open(INI_PATH, 'w') as f:
            config.config.write(f)
        ui.notify('Configuration Savaed', type='positive')

    ui.button('💾 Save Changes', on_click=save_config).props('color=primary')
