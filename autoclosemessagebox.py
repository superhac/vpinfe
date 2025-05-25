import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import os
import sys
from assetsutils import AssetsUtils

class AutocloseMessageBox:
    # A custom message box that automatically closes after a specified delay,
    # displaying a live countdown. Includes an 'OK' button to dismiss it sooner.

    def __init__(self, parent_window, title, message, delay_s=10):
        self.parent = parent_window
        self.delay_s = delay_s

        self.remaining_time_s = self.delay_s

        self.top = tk.Toplevel(parent_window)
        self.top.title(title)
        self.top.transient(parent_window)
        self.top.grab_set()
        self.top.resizable(False, False)
        self.icon_image = None

        icon_path = AssetsUtils.get_path("tilt-icon.png")

        if os.path.exists(icon_path):
            pil_image = Image.open(icon_path)
            self.icon_image = ImageTk.PhotoImage(pil_image)
            self.top.iconphoto(True, self.icon_image)

        main_frame = ttk.Frame(self.top, padding="15 15 15 15")
        main_frame.pack(fill="both", expand=True)

        # Message Label
        message_label = ttk.Label(main_frame, text=message, wraplength=300, justify="center")
        message_label.pack(pady=(0, 10))

        # Countdown Label
        self.countdown_label = ttk.Label(main_frame, text="", font=("Arial", 10, "bold"))
        self.countdown_label.pack(pady=(5, 15))

        # OK Button
        ok_button = ttk.Button(main_frame, text="OK", command=self._on_ok_clicked)
        ok_button.pack(pady=(10, 0))

        self.top.update_idletasks()

        # Get the required width for the content based on current layout.
        required_content_width = self.top.winfo_reqwidth()
        required_content_height = self.top.winfo_reqheight()
        minimum_dialog_width = max(required_content_width, 400)
        minimum_dialog_height = max(required_content_height, 200)
        self.top.minsize(width=minimum_dialog_width, height=minimum_dialog_height)
        self._center_window()

        self._autoclose_after_id = self.top.after(self.delay_s * 1000, self._timeout_destroy)

        self._countdown_after_id = None
        self._update_countdown() # Call once immediately to show initial time

        self.top.protocol("WM_DELETE_WINDOW", self._on_ok_clicked)

    def _center_window(self):
        self.parent.update_idletasks()

        parent_x = self.parent.winfo_x()
        parent_y = self.parent.winfo_y()
        parent_width = self.parent.winfo_width()
        parent_height = self.parent.winfo_height()

        top_width = self.top.winfo_width()
        top_height = self.top.winfo_height()

        x = parent_x + (parent_width // 2) - (top_width // 2)
        y = parent_y + (parent_height // 2) - (top_height // 2)

        self.top.geometry(f"+{x}+{y}")

    def _update_countdown(self):
        if self.top.winfo_exists():
            if self.remaining_time_s > 0:
                self.countdown_label.config(text=f"Closing in {self.remaining_time_s} seconds...")
                self.remaining_time_s -= 1
                self._countdown_after_id = self.top.after(1000, self._update_countdown)
            else:
                self.countdown_label.config(text="Closing now...")
        else:
            if self._countdown_after_id:
                self.top.after_cancel(self._countdown_after_id)
                self._countdown_after_id = None

    def _on_ok_clicked(self):
        if self._autoclose_after_id:
            self.top.after_cancel(self._autoclose_after_id)
            self._autoclose_after_id = None
        if self._countdown_after_id:
            self.top.after_cancel(self._countdown_after_id)
            self._countdown_after_id = None
        self.top.destroy()

    def _timeout_destroy(self):
        if self.top.winfo_exists():
            # If auto-closed, also cancel the countdown updates to be safe
            if self._countdown_after_id:
                self.top.after_cancel(self._countdown_after_id)
                self._countdown_after_id = None
            self.top.destroy()

    def show(self):
        self.parent.wait_window(self.top)
