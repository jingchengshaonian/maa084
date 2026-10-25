"""全局键盘监听：按下任意键输出其虚拟键码 (VK code)。

用 GetAsyncKeyState 轮询所有 256 个键，检测到按下时输出 VK code。
按 ESC 退出。
"""
import ctypes
import time
import sys

user32 = ctypes.windll.user32

VK_NAMES = {
    8: "BACK", 9: "TAB", 13: "ENTER", 16: "SHIFT", 17: "CTRL", 18: "ALT",
    20: "CAPSLOCK", 27: "ESC", 32: "SPACE",
    37: "LEFT", 38: "UP", 39: "RIGHT", 40: "DOWN",
    48: "0", 49: "1", 50: "2", 51: "3", 52: "4", 53: "5", 54: "6", 55: "7", 56: "8", 57: "9",
    65: "A", 66: "B", 67: "C", 68: "D", 69: "E", 70: "F", 71: "G", 72: "H", 73: "I",
    74: "J", 75: "K", 76: "L", 77: "M", 78: "N", 79: "O", 80: "P", 81: "Q", 82: "R",
    83: "S", 84: "T", 85: "U", 86: "V", 87: "W", 88: "X", 89: "Y", 90: "Z",
    96: "NUMPAD0", 97: "NUMPAD1", 98: "NUMPAD2", 99: "NUMPAD3", 100: "NUMPAD4",
    101: "NUMPAD5", 102: "NUMPAD6", 103: "NUMPAD7", 104: "NUMPAD8", 105: "NUMPAD9",
    106: "NUMPAD_MUL", 107: "NUMPAD_ADD", 109: "NUMPAD_SUB", 110: "NUMPAD_DOT", 111: "NUMPAD_DIV",
    112: "F1", 113: "F2", 114: "F3", 115: "F4", 116: "F5", 117: "F6",
    118: "F7", 119: "F8", 120: "F9", 121: "F10", 122: "F11", 123: "F12",
}

# 记录上一轮按下的键，避免重复输出
prev_pressed = set()

print("键盘监听已启动，按任意键输出 VK code，按 ESC 退出")
print("-" * 50)

try:
    while True:
        current_pressed = set()
        for vk in range(1, 256):
            # 最高位为1表示当前按下
            if user32.GetAsyncKeyState(vk) & 0x8000:
                current_pressed.add(vk)

        # 检测新按下的键（本轮有、上一轮没有）
        new_keys = current_pressed - prev_pressed
        for vk in new_keys:
            name = VK_NAMES.get(vk, "?")
            print(f"key={vk:4d}  name={name}")
            if vk == 27:  # ESC
                print("ESC pressed, exiting...")
                sys.exit(0)

        prev_pressed = current_pressed
        time.sleep(0.02)  # 50Hz 轮询

except KeyboardInterrupt:
    print("\n已退出")
