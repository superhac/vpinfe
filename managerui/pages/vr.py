from nicegui import ui



def build():
    with ui.row().classes('items-center'):
        ui.label('VR Mode')
        vr_mode = ui.select(['VR enabled', 'VR disabled'], value='VR enabled')
    
    with ui.row():
        # === Table Setup ===
        with ui.column().classes('border rounded p-4').style('min-width: 260px'):
            ui.label('Table Setup').classes('font-bold')
            scale_checkbox = ui.checkbox('Scale Table to width (in cm)')
            scaling = ui.input('Scaling')
            slope = ui.input('Slope')
            orientation = ui.input('Table Orientation')
            table_x = ui.input('Table X').props('type=number').value = '0.0'
            table_y = ui.input('Table Y').props('type=number').value = '0.0'
            table_height = ui.input('Table Height').props('type=number').value = '0.0'
    
        # === Button Assignments ===
        with ui.column().classes('border rounded p-4').style('min-width: 260px'):
            ui.label('Button Assignments').classes('font-bold')
            with ui.row():
                ui.button('Table Recenter')
                ui.label('NumPad 5')
            ui.select(['(none)', 'Option1', 'Option2'], label='', value='(none)')
    
            with ui.row():
                ui.button('TableUp')
                ui.label('NumPad 8')
            ui.select(['(none)', 'Option1', 'Option2'], label='', value='(none)')
    
            with ui.row():
                ui.button('TableDown')
                ui.label('NumPad 2')
            ui.select(['(none)', 'Option1', 'Option2'], label='', value='(none)')
    
    with ui.row():
        # === Backglass DMD/Capture ===
        with ui.column().classes('border rounded p-4').style('min-width: 260px'):
            ui.label('Backglass DMD/Capture').classes('font-bold')
            ui.checkbox('Capture External Backglass')
            ui.checkbox('Capture External DMD')
    
        # === Performance and Troubleshooting ===
        with ui.column().classes('border rounded p-4').style('min-width: 260px'):
            ui.label('Performance and Troubleshooting').classes('font-bold')
            ui.select(['RGB 8', 'RGB 16'], label='Framebuffer Format', value='RGB 8')
            ui.input('Near Plane')
    
        # === Preview ===
        with ui.column().classes('border rounded p-4').style('min-width: 260px'):
            ui.label('Preview').classes('font-bold')
            with ui.row().classes('items-center'):
                ui.label('Preview Mode')
                ui.select(['Disabled', 'Enabled'], value='Disabled')
                ui.checkbox('Shrink to fit')
            ui.input('Width')
            ui.input('Height')
    
    ui.button('Save Changes').classes('mt-4 bg-blue-500 text-white')