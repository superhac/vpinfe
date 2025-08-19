from pynput.keyboard import Key, Controller
import time

class KeySimulator:

    # VPX Keymap
    VPX_MENU = Key.f12
    VPX_FRAME_COUNT = Key.f11
    VPX_TABLE_RESET = Key.f3
    VPX_VOLUME_UP = '='
    VPX_VOLUME_DOWN = '-'
    VPX_QUIT = 'q'
    VPX_PAUSE = 'p'
    VPX_ADD_BALL = 'b'
    
    # Pinmame
    PINMAME_OPEN_COIN_DOOR = Key.end
    
    def __init__(self):
        self.keyboard = Controller()

    def press(self, key):
        """Press and release a single key"""
        self.keyboard.press(key)
        self.keyboard.release(key)

    def hold(self, key, seconds=1):
        """Hold a key down for a given time"""
        self.keyboard.press(key)
        time.sleep(seconds)
        self.keyboard.release(key)

    def type_text(self, text):
        """Type out a full string"""
        self.keyboard.type(text)

    def combo(self, *keys):
        """Send a key combination (e.g., ctrl+c)"""
        for key in keys:
            self.keyboard.press(key)
        for key in reversed(keys):
            self.keyboard.release(key)


# Example usage:
if __name__ == "__main__":
    ks = KeySimulator()

    time.sleep(2)  # Give yourself time to switch windows
    #ks.type_text("Hello from pynput!")
    #ks.press(Key.enter)
    ks.press(KeySimulator.VPX_FRAMECOUNT)
    #ks.combo(Key.ctrl, 'c')   # Simulates Ctrl+C