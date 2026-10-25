"""模板叠加对比工具。

流程：
    1. 自动截 1280x720 图并显示
    2. 文件对话框选模板叠加，调透明度/位置

截图方式（--screencap）：1=GDI 2=FramePool 4=DXGI_DesktopDup 8=DXGI_DesktopDup_Window
    16=PrintWindow 32=ScreenDC  传 0 尝试全部方式（自动回退）
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import re
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

import cv2
import numpy as np

WORKING_DIR = Path(__file__).parent.parent.resolve()
DEFAULT_IMAGE_DIR = WORKING_DIR / "assets" / "resource" / "image"
W, H = 1280, 720

NAME_RE = re.compile(
    r"^(?P<page>.+)_(?P<x>\d+)_(?P<y>\d+)_(?P<w>\d+)_(?P<h>\d+)"
    r"__(?P<rx>\d+)_(?P<ry>\d+)_(?P<rw>\d+)_(?P<rh>\d+)\.png$"
)

KEY_LEFT, KEY_UP, KEY_RIGHT, KEY_DOWN = 2424832, 2490368, 2555904, 2621440

HELP_LINES = [
    "[o]选模板  [r]重截图  [s]保存  [0]重置  [g]green_mask  [q/ESC]退出",
    "左键=放到点击处  方向键=微调  Shift+方向键=10px",
]


def parse_name(path: Path):
    m = NAME_RE.match(path.name)
    if not m:
        return None
    g = m.groupdict()
    return {
        "path": path,
        "page": g["page"],
        "box": tuple(int(g[k]) for k in ("x", "y", "w", "h")),
        "roi": tuple(int(g[k]) for k in ("rx", "ry", "rw", "rh")),
    }


def imread_unicode(path: Path):
    data = np.fromfile(str(path), dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def imwrite_unicode(path: Path, img: np.ndarray):
    ok, buf = cv2.imencode(path.suffix or ".png", img)
    if ok:
        buf.tofile(str(path))
    return ok


def pick_template(initial_dir: Path):
    """弹出文件对话框选模板，返回 (info_dict_or_None, img_or_None)。"""
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口
    path = filedialog.askopenfilename(
        title="选择模板图片",
        initialdir=str(initial_dir),
        filetypes=[("PNG 模板", "*.png"), ("所有文件", "*.*")],
    )
    root.destroy()
    if not path:
        return None, None
    p = Path(path)
    info = parse_name(p)
    img = imread_unicode(p)
    if info is None:
        print(f"警告: 文件名不符合规范，无法解析坐标: {p.name}")
        # 仍然加载图片，但 box 默认 0,0,img.shape
        h, w = img.shape[:2]
        info = {"path": p, "page": p.stem, "box": (0, 0, w, h), "roi": (0, 0, w, h)}
    info["img"] = img
    return info, img


def find_window(keyword: str):
    user32 = ctypes.windll.user32
    results = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def enum_proc(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                if keyword.lower() in buf.value.lower():
                    results.append((hwnd, buf.value))
        return True

    user32.EnumWindows(enum_proc, 0)
    if not results:
        print(f"未找到标题含 '{keyword}' 的可见窗口，请确认游戏已启动")
        return None
    if len(results) > 1:
        print(f"匹配到 {len(results)} 个窗口，使用第一个：")
        for h, t in results:
            print(f"  0x{h:X}  {t}")
    return results[0]


def fit_client_size(hwnd: int, w: int, h: int):
    user32 = ctypes.windll.user32
    style = user32.GetWindowLongW(hwnd, -16)
    ex_style = user32.GetWindowLongW(hwnd, -20)
    rect = wt.RECT(0, 0, w, h)
    user32.AdjustWindowRectEx(ctypes.byref(rect), style, False, ex_style)
    user32.MoveWindow(hwnd, 0, 0, rect.right - rect.left, rect.bottom - rect.top, True)


class GameCapture:
    def __init__(self, hwnd: int, screencap_method: int):
        from maa.controller import Win32Controller

        self.ctrl = Win32Controller(hwnd, screencap_method=screencap_method)
        self.ctrl.post_connection().wait()

    def capture(self) -> np.ndarray:
        for attempt in range(3):
            self.ctrl.post_screencap().wait()
            img = self.ctrl.cached_image
            if img is not None and img.size > 0 and img.any():
                if img.shape[:2] != (H, W):
                    img = cv2.resize(img, (W, H))
                return img
            print(f"截图尝试 {attempt + 1}/3 失败，重试...")
            time.sleep(0.5)
        raise RuntimeError("截图连续 3 次失败，尝试 --screencap 换截图方式（试 1 / 4 / 8 / 32）")


def draw_help(view: np.ndarray):
    """在左上角画半透明快捷键帮助。"""
    overlay = view.copy()
    x0, y0, pad = 10, 10, 6
    for i, line in enumerate(HELP_LINES):
        y = y0 + 20 * i + pad
        cv2.putText(overlay, line, (x0 + pad, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    # 半透明背景
    (tw, th), _ = cv2.getTextSize(HELP_LINES[0], cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
    box_w = max(cv2.getTextSize(l, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0][0] for l in HELP_LINES) + pad * 2
    box_h = 20 * len(HELP_LINES) + pad * 2
    cv2.rectangle(overlay, (x0, y0), (x0 + box_w, y0 + box_h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.55, view, 0.45, 0, view)
    # 重新画文字到半透明背景上
    for i, line in enumerate(HELP_LINES):
        y = y0 + 20 * i + pad + 14
        cv2.putText(view, line, (x0 + pad, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)


def draw_tpl_info(view: np.ndarray, info, alpha, ox, oy, green_mask):
    """在右上角画当前模板信息。"""
    gm_str = "GM=on" if green_mask else "GM=off"
    lines = [
        f"模板: {info['path'].name}",
        f"尺寸: {info['img'].shape[1]}x{info['img'].shape[0]}  {gm_str}",
        f"坐标: ({ox}, {oy})  alpha={alpha}%",
    ]
    x0, y0, pad = W - 310, 10, 6
    box_h = 20 * len(lines) + pad * 2
    cv2.rectangle(view, (x0, y0), (W - 10, y0 + box_h), (0, 0, 0), -1)
    for i, line in enumerate(lines):
        y = y0 + 20 * i + pad + 14
        color = (0, 255, 0) if green_mask else (0, 255, 255)
        cv2.putText(view, line, (x0 + pad, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)


def detect_green_mask(img: np.ndarray, threshold: float = 0.15) -> bool:
    """检测模板是否使用绿色背景（MaaFW green_mask=true 的典型做法）。"""
    b, g, r = cv2.split(img)
    # 绿色像素：G 通道显著高于 R 和 B
    green_pixels = np.sum((g > r * 1.5) & (g > b * 1.5))
    total = img.shape[0] * img.shape[1]
    return green_pixels / total > threshold


def build_green_mask(img: np.ndarray) -> np.ndarray:
    """返回 0/255 掩码，绿色区域为 0（透明），其余为 255（不透明）。"""
    b, g, r = cv2.split(img)
    mask = np.where((g > r * 1.4) & (g > b * 1.4), 0, 255).astype(np.uint8)
    return mask


def main():
    ap = argparse.ArgumentParser(description="模板叠加对比工具")
    ap.add_argument("--window", default="LimbusCompany", help="游戏窗口标题关键字")
    ap.add_argument("--image-dir", default=str(DEFAULT_IMAGE_DIR), help="文件对话框初始目录")
    ap.add_argument("--screencap", type=int, default=16, help="截图方式，默认 16=PrintWindow（对窗口状态不敏感），2=FramePool，1=GDI")
    ap.add_argument("--no-resize", action="store_true", help="不调整游戏窗口大小")
    ap.add_argument("--template", default=None, help="启动时直接加载此模板路径（跳过对话框）")
    args = ap.parse_args()

    found = find_window(args.window)
    if not found:
        return
    hwnd = found[0]

    if not args.no_resize:
        try:
            fit_client_size(hwnd, W, H)
            time.sleep(0.5)
        except (PermissionError, OSError) as e:
            print(f"警告: 调整窗口大小失败 ({e})，继续运行。加 --no-resize 跳过。")

    capture = GameCapture(hwnd, args.screencap)
    screen = capture.capture()
    print(f"截图: {screen.shape[1]}x{screen.shape[0]}")

    print("快捷键: [o]选模板  [r]重截图  [s]保存  [0]重置  [g]green_mask  [q/ESC]退出")
    print("        左键=放到点击处  方向键=微调  Shift+方向键=10px")

    # 加载第一个模板
    if args.template:
        tpl_info = parse_name(Path(args.template))
        tpl_info["img"] = imread_unicode(Path(args.template))
    else:
        tpl_info, _ = pick_template(Path(args.image_dir))
    if tpl_info is None:
        print("未选择模板，退出")
        return
    print(f"当前模板: {tpl_info['path'].name}  原坐标({tpl_info['box'][0]},{tpl_info['box'][1]})")

    user32 = ctypes.windll.user32
    out_dir = Path(__file__).parent / "compare_out"
    out_dir.mkdir(exist_ok=True)

    # 初始 green_mask 检测
    state = {
        "ox": tpl_info["box"][0],
        "oy": tpl_info["box"][1],
        "alpha": 50,
        "green_mask": detect_green_mask(tpl_info["img"]),
    }
    print(f"  green_mask={'on' if state['green_mask'] else 'off'}  (自动检测)")

    def on_mouse(event, mx, my, flags, _):
        if event == cv2.EVENT_LBUTTONDOWN:
            state["ox"], state["oy"] = mx, my

    def on_alpha(v):
        state["alpha"] = v

    cv2.namedWindow("overlay", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("overlay", W, H + 40)
    cv2.setMouseCallback("overlay", on_mouse)
    cv2.createTrackbar("alpha", "overlay", 50, 100, on_alpha)

    while True:
        alpha_pct = state["alpha"]
        alpha = alpha_pct / 100.0
        ox, oy = state["ox"], state["oy"]
        th, tw = tpl_info["img"].shape[:2]

        view = screen.copy()

        # 模板叠加
        px0, py0 = ox, oy
        vh, vw = view.shape[:2]
        px1, py1 = min(px0 + tw, vw), min(py0 + th, vh)
        sx, sy = max(0, -px0), max(0, -py0)
        if px1 > max(0, px0) and py1 > max(0, py0):
            region = view[py0 + sy:py1, px0 + sx:px1]
            piece = tpl_info["img"][sy:sy + region.shape[0], sx:sx + region.shape[1]]
            if state["green_mask"]:
                # 只在非绿色区域混合，绿色区域保持截图原样（与 MaaFW green_mask 行为一致）
                gmask = build_green_mask(piece)
                fg = cv2.bitwise_and(piece, piece, mask=gmask)
                bg_mask = cv2.bitwise_not(gmask)
                blended = cv2.addWeighted(fg, 1.0 - alpha, region, alpha, 0)
                blended[bg_mask > 0] = region[bg_mask > 0]
                view[py0 + sy:py1, px0 + sx:px1] = blended
            else:
                view[py0 + sy:py1, px0 + sx:px1] = cv2.addWeighted(region, alpha, piece, 1.0 - alpha, 0)
            cv2.rectangle(view, (px0 + sx, py0 + sy), (px1 - 1, py1 - 1), (0, 255, 0), 1)

        draw_help(view)
        draw_tpl_info(view, tpl_info, alpha_pct, ox, oy, state["green_mask"])

        cv2.setWindowTitle("overlay", f"模板叠加对比  |  {tpl_info['path'].name}")
        cv2.imshow("overlay", view)

        key = cv2.waitKeyEx(30)
        if key in (ord("q"), 27):
            break
        elif key == ord("o"):
            info, _ = pick_template(Path(args.image_dir))
            if info is not None:
                tpl_info = info
                state["ox"], state["oy"] = info["box"][0], info["box"][1]
                state["green_mask"] = detect_green_mask(tpl_info["img"])
                cv2.setTrackbarPos("alpha", "overlay", 50)
                print(f"切换到: {tpl_info['path'].name}  green_mask={'on' if state['green_mask'] else 'off'}")
        elif key == ord("g"):
            state["green_mask"] = not state["green_mask"]
            print(f"green_mask -> {'on' if state['green_mask'] else 'off'}")
        elif key in (KEY_LEFT, KEY_RIGHT, KEY_UP, KEY_DOWN):
            step = 10 if user32.GetAsyncKeyState(0x10) & 0x8000 else 1
            dx, dy = {KEY_LEFT: (-step, 0), KEY_RIGHT: (step, 0), KEY_UP: (0, -step), KEY_DOWN: (0, step)}[key]
            state["ox"], state["oy"] = ox + dx, oy + dy
        elif key == ord("0"):
            x, y, _, _ = tpl_info["box"]
            state["ox"], state["oy"] = x, y
        elif key == ord("r"):
            screen = capture.capture()
        elif key == ord("s"):
            stamp = time.strftime("%H%M%S")
            out = out_dir / f"{tpl_info['page']}_{stamp}.png"
            imwrite_unicode(out, view)
            print(f"已保存: {out}")

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
