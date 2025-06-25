from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsTextItem, QGraphicsItemGroup
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QBrush, QColor, QFont
from globalsignals import dispatcher

class MenuOverlay:
    def __init__(self, scene, rect, options=None, rotation=0):
        if options is None:
            options = ["Test", "Quit"]
        self.scene = scene
        self.rect = rect
        self.options = options
        self.rotation = rotation
        self.text_items = []
        self.current_index = 0
        self.menu_rect_item = None
        self.menu_group = None
        self._add_menu_text_and_bg()

    def _add_menu_text_and_bg(self):
        font = QFont()
        font.setPointSize(40)
        # Calculate text bounding box
        temp_text_items = []
        max_width = 0
        total_height = 0
        for option in self.options:
            text = QGraphicsTextItem(option)
            text.setFont(font)
            br = text.boundingRect()
            max_width = max(max_width, br.width())
            total_height += br.height() + 20  # 20px vertical spacing
            temp_text_items.append((text, br))
        total_height -= 20  # Remove last extra spacing
        # 5% border based on text area
        border_x = max_width * 0.05
        border_y = total_height * 0.05
        menu_width = max_width + 2 * border_x
        menu_height = total_height + 2 * border_y
        x = self.rect.x() + (self.rect.width() - menu_width) / 2
        y = self.rect.y() + (self.rect.height() - menu_height) / 2
        menu_rect = QRectF(x, y, menu_width, menu_height)
        self.menu_rect_item = QGraphicsRectItem(menu_rect)
        self.menu_rect_item.setBrush(QBrush(QColor(0, 0, 0, 180)))
        self.menu_rect_item.setZValue(100)
        self.text_items.clear()
        # Center text vertically and horizontally in the menu area
        current_y = y + border_y
        for idx, (text, br) in enumerate(temp_text_items):
            text.setFont(font)
            text.setDefaultTextColor(Qt.GlobalColor.white)
            text.setZValue(101)
            text_x = x + (menu_width - br.width()) / 2
            text.setPos(text_x, current_y)
            # Do NOT rotate each text item, just position them
            self.text_items.append(text)
            current_y += br.height() + 20
        # Group background and text, then rotate the group
        self.menu_group = QGraphicsItemGroup()
        self.menu_group.addToGroup(self.menu_rect_item)
        for text in self.text_items:
            self.menu_group.addToGroup(text)
        if self.rotation:
            self.menu_group.setTransformOriginPoint(menu_rect.center())
            self.menu_group.setRotation(self.rotation)
        self._update_highlight()

    def _update_highlight(self):
        for idx, text in enumerate(self.text_items):
            if idx == self.current_index:
                text.setDefaultTextColor(Qt.GlobalColor.yellow)
            else:
                text.setDefaultTextColor(Qt.GlobalColor.white)

    def move_up(self):
        if self.current_index > 0:
            self.current_index -= 1
        else:
            self.current_index = len(self.options) - 1  # Roll over to last
        self._update_highlight()

    def move_down(self):
        if self.current_index < len(self.options) - 1:
            self.current_index += 1
        else:
            self.current_index = 0  # Roll over to first
        self._update_highlight()

    def show(self):
        self.scene.addItem(self.menu_group)

    def hide(self):
        self.scene.removeItem(self.menu_group)

    def is_visible(self):
        return self.menu_rect_item.scene() is not None

    def option_selected(self):
        
        selected = self.options[self.current_index]
        match selected:
            case "Test":
                dispatcher.customEvent.emit("main", {"op": "test"})
            case "Quit":
                dispatcher.customEvent.emit("main", {"op": "quit"})
