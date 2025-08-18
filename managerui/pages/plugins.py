from nicegui import ui

def build():
    ui.label("Plugins").classes("text-2xl font-bold mb-4")

    with ui.card().classes('w-full p-4'):
        ui.label("Core Plugins").classes("text-lg font-semibold mb-2")
        with ui.row().classes('gap-4'):
            ui.switch("AlphaDMD")
            b2s_switch = ui.switch("B2S")
            dof_switch = ui.switch("DOF")
            ui.switch("ScoreView")
            ui.switch("Remote Control")

        def on_dof_change(e):
            if e.args and e.args[0] is True:
                b2s_switch.value = True
                ui.notify('B2S is required for DOF', type='positive', position='bottom')
        dof_switch.on('update:model-value', on_dof_change)

        DOF_BEHAVIOR_OPTIONS = {
            0: "Sound FX",
            1: "DOF",
            2: "Both",
        }
        dof_widgets = {}
        dof_options_column = ui.column().bind_visibility_from(dof_switch, 'value').classes('gap-2 mt-4')
        with dof_options_column:
            ui.label("DOF Controller Options").classes("text-lg font-semibold")
            with ui.row().classes('gap-4 flex-wrap'):
                for key, label in {
                    "DOFContactors": "Contactors",
                    "DOFKnocker": "Knocker",
                    "DOFChimes": "Chimes",
                    "DOFBell": "Bell",
                    "DOFGear": "Gear",
                    "DOFShaker": "Shaker",
                    "DOFFlippers": "Flippers",
                    "DOFTargets": "Targets",
                    "DOFDroptargets": "Drop Targets"
                }.items():
                    dof_widgets[key] = ui.select(
                        options=DOF_BEHAVIOR_OPTIONS,
                        label=label,
                        value=2
                    ).props("dense").style("min-width: 120px").classes("w-48")

    with ui.card().classes('w-full p-4 mt-4'):
        with ui.row().classes('items-center'):
            dmdutil_switch = ui.switch("DMDUtil").props('color=primary')
            ui.label("DMD Settings").classes("text-lg font-semibold")

        with ui.column().bind_visibility_from(dmdutil_switch, 'value').classes('w-full mt-4 p-4 border rounded-lg'):
            ui.label("DMDUtil Options").classes("text-xl font-bold mb-4")
            
            with ui.row().classes('w-full gap-8'):
                with ui.column().classes('flex-1'):
                    ui.label("Luminescence Tint").classes("text-md font-semibold")
                    ui.number("LumTintR", value=255, min=0, max=255, step=1).props('dense')
                    ui.number("LumTintG", value=255, min=0, max=255, step=1).props('dense')
                    ui.number("LumTintB", value=255, min=0, max=255, step=1).props('dense')
                    
                    ui.separator().classes('my-4')

                    ui.label("ZeDMD").classes("text-md font-semibold")
                    ui.switch("ZeDMD")
                    ui.input("ZeDMDDevice")
                    ui.switch("ZeDMDDebug")
                    ui.number("ZeDMDBrightness", value=100)
                    ui.switch("ZeDMDWiFi")
                    ui.input("ZeDMDWiFiAddr")

                with ui.column().classes('flex-1'):
                    ui.label("Pixelcade").classes("text-md font-semibold")
                    ui.switch("Pixelcade")
                    ui.input("PixelcadeDevice")

                    ui.separator().classes('my-4')

                    ui.label("DMD Server").classes("text-md font-semibold")
                    ui.switch("DMDServer")
                    ui.input("DMDServerAddr")
                    ui.number("DMDServerPort")
                    
                    ui.separator().classes('my-4')

                    ui.label("Dumping & Other").classes("text-md font-semibold")
                    ui.switch("DumpDMDTxt")
                    ui.switch("DumpDMDRaw")
                    ui.switch("FindDisplays")