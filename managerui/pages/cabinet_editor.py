import xml.etree.ElementTree as ET
from xml.dom import minidom
from nicegui import ui, app

config = {
    'cabinet_name': 'MyCabinet',
    'controller': {
        'name': 'Boognish',
        'led_counts': [94, 94, 32, 32, 0, 0, 0, 0],
        'com_port': 'COM1',
        'timeout': 300,
        'baud_rate': 2000000,
        'open_wait': 300,
        'handshake_start_wait': 100,
        'handshake_end_wait': 100,
        'send_per_ledstrip': True,
        'use_compression': True,
        'test_on_connect': False,
    },
    'led_strips': [
        {'name': 'RightPlayfield', 'height': 94, 'ledwiz_output': 1},
        {'name': 'LeftPlayfield', 'height': 94, 'ledwiz_output': 4},
        {'name': 'RightRing', 'height': 32, 'ledwiz_output': 7},
        {'name': 'LeftRing', 'height': 32, 'ledwiz_output': 11},
    ],
    'ledwiz': {
        'number': 30
    }
}

def generate_cabinet_xml():
    
    cabinet_attributes = {
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xmlns:xsd": "http://www.w3.org/2001/XMLSchema"
    }
    root = ET.Element("Cabinet", cabinet_attributes)

    ET.SubElement(root, "Name").text = config['cabinet_name']

    # OutputControllers
    output_controllers = ET.SubElement(root, "OutputControllers")
    wemos = ET.SubElement(output_controllers, "WemosD1MPStripController")
    ctrl_config = config['controller']
    ET.SubElement(wemos, "Name").text = ctrl_config['name']
    for i, count in enumerate(ctrl_config['led_counts'], 1):
        ET.SubElement(wemos, f"NumberOfLedsStrip{i}").text = str(count)
    ET.SubElement(wemos, "ComPortName").text = ctrl_config['com_port']
    ET.SubElement(wemos, "ComPortTimeOutMs").text = str(ctrl_config['timeout'])
    ET.SubElement(wemos, "ComPortBaudRate").text = str(ctrl_config['baud_rate'])
    ET.SubElement(wemos, "ComPortOpenWaitMs").text = str(ctrl_config['open_wait'])
    ET.SubElement(wemos, "ComPortHandshakeStartWaitMs").text = str(ctrl_config['handshake_start_wait'])
    ET.SubElement(wemos, "ComPortHandshakeEndWaitMs").text = str(ctrl_config['handshake_end_wait'])
    ET.SubElement(wemos, "SendPerLedstripLength").text = str(ctrl_config['send_per_ledstrip']).lower()
    ET.SubElement(wemos, "UseCompression").text = str(ctrl_config['use_compression']).lower()
    ET.SubElement(wemos, "TestOnConnect").text = str(ctrl_config['test_on_connect']).lower()

    # Toys
    toys = ET.SubElement(root, "Toys")
    
    # LedStrips
    first_led_counter = 1
    for strip_config in config['led_strips']:
        strip_xml = ET.SubElement(toys, "LedStrip")
        ET.SubElement(strip_xml, "Name").text = strip_config['name']
        ET.SubElement(strip_xml, "Width").text = "1"
        ET.SubElement(strip_xml, "Height").text = str(strip_config['height'])
        ET.SubElement(strip_xml, "LedStripArrangement").text = "LeftRightTopDown"
        ET.SubElement(strip_xml, "ColorOrder").text = "RGB"
        ET.SubElement(strip_xml, "FirstLedNumber").text = str(first_led_counter)
        ET.SubElement(strip_xml, "FadingCurveName").text = "SwissLizardsLedCurve"
        ET.SubElement(strip_xml, "Brightness").text = "100"
        ET.SubElement(strip_xml, "OutputControllerName").text = ctrl_config['name']
        
        first_led_counter += strip_config['height']

    # LedWizEquivalent
    ledwiz_eq = ET.SubElement(toys, "LedWizEquivalent")
    ET.SubElement(ledwiz_eq, "Name").text = f"LedWizEquivalent {config['ledwiz']['number']}"
    outputs = ET.SubElement(ledwiz_eq, "Outputs")
    for strip_config in config['led_strips']:
        output = ET.SubElement(outputs, "LedWizEquivalentOutput")
        ET.SubElement(output, "OutputName").text = strip_config['name']
        ET.SubElement(output, "LedWizEquivalentOutputNumber").text = str(strip_config['ledwiz_output'])
    ET.SubElement(ledwiz_eq, "LedWizNumber").text = str(config['ledwiz']['number'])

    xml_string = ET.tostring(root, 'utf-8')
    reparsed = minidom.parseString(xml_string)
    pretty_xml = reparsed.toprettyxml(indent="  ", encoding="utf-8")

    return b'<?xml version="1.0"?>\n' + pretty_xml.split(b'\n', 1)[1]

def build():
    ui.label("Editor de Cabinet.xml").classes("text-2xl font-bold mb-4")

    with ui.card().classes('w-full p-4'):
        ui.label("Configurações Gerais").classes("text-lg font-semibold mb-2")
        ui.input("Nome do Cabinet", placeholder="Ex: MichiCab").bind_value(config, 'cabinet_name')
        ui.input("Nome do Controller", placeholder="Ex: Boognish").bind_value(config['controller'], 'name')
        ui.input("Porta COM", placeholder="Ex: COM3").bind_value(config['controller'], 'com_port')

    strips_container = ui.column().classes('w-full gap-4 mt-4')

    def update_led_strips_ui():
        strips_container.clear()
        with strips_container:
            ui.label("LED Strips").classes("text-lg font-semibold")
            
            first_led_counter = 1
            for i, strip in enumerate(config['led_strips']):
                with ui.card().classes('w-full p-4'):
                    with ui.row().classes('w-full items-center justify-between'):
                        ui.label(f"Strip #{i+1}").classes('text-md font-bold')
                        ui.button(icon='delete', on_click=lambda i=i: remove_strip(i)).props('flat round color=negative')

                    with ui.row().classes('w-full gap-4 items-center'):
                        ui.input("Nome", placeholder="Ex: RightPlayfield").bind_value(strip, 'name').classes('flex-grow')
                        
                        ui.number("Nº de LEDs (Height)", min=1, step=1).bind_value(strip, 'height').on('update:model-value', update_led_strips_ui)
                        
                        ui.input("Primeiro LED", value=str(first_led_counter)).props('readonly')
                        ui.number("DOF Port", min=1, step=1).bind_value(strip, 'ledwiz_output')
                
                first_led_counter += strip['height']

            if len(config['led_strips']) < 10:
                ui.button("Adicionar Led Strip", on_click=add_strip, icon='add').props('color=positive')

    def add_strip():
        if len(config['led_strips']) < 10:
            new_strip_num = len(config['led_strips']) + 1
            config['led_strips'].append({
                'name': f'NovaStrip{new_strip_num}',
                'height': 60,
                'ledwiz_output': new_strip_num * 2
            })
            update_led_strips_ui()
            ui.notify(f"Strip #{new_strip_num} adicionada!")

    def remove_strip(index):
        removed_name = config['led_strips'][index]['name']
        config['led_strips'].pop(index)
        update_led_strips_ui()
        ui.notify(f"Strip '{removed_name}' removida.")

    with ui.card().classes('w-full p-4 mt-4'):
        ui.label("Configurações LedWiz").classes("text-lg font-semibold mb-2")
        ui.number("Número do LedWiz", min=1, step=1).bind_value(config['ledwiz'], 'number')

    def handle_download():
        xml_content = generate_cabinet_xml()
        ui.download(xml_content, 'Cabinet.xml', 'application/xml')
        ui.notify("Cabinet.xml created successfully!", type='positive')

    ui.button("Create Cabinet.xml", on_click=handle_download, icon='download').props('color=primary').classes('mt-4')

    update_led_strips_ui()