"""验证 key 38 (VK_UP) 是否被游戏接收。运行前确保 LimbusCompany 在前台且处于路线图界面。"""
import ctypes
import time
from maa.controller import Win32Controller
from maa.define import MaaWin32InputMethodEnum

user32 = ctypes.windll.user32
hwnd = user32.FindWindowW(None, "LimbusCompany")
if not hwnd:
    print("未找到 LimbusCompany 窗口，请确认游戏已启动")
    exit(1)

print(f"找到窗口句柄: {hex(hwnd)}")
ctrl = Win32Controller(hwnd, keyboard_method=MaaWin32InputMethodEnum.Seize)

# 必须先连接，初始化输入单元
print("连接控制器...")
ctrl.post_connection().wait()
print("已连接")

print("3 秒后发送 VK_UP (key=38)...")
time.sleep(3)
print("发送前，请确保游戏窗口在前台并处于路线图界面")

ctrl.post_click_key(38).wait()
print("已发送 key=38 (VK_UP)，观察游戏是否移动了选中项")
print("若未移动：检查窗口是否前台 / keyboard 是否为 Seize")
