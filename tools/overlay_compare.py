"""模板叠加对比工具（GUI）。

直接运行即打开界面：
    - 截图游戏窗口：把游戏窗口调整为 1280x720 后截图，按原分辨率显示
    - 上传图片：选择模板图片，按文件名中的坐标自动摆放，并在图片四周画绿框

模板文件名约定：页面名_x_y_w_h__rx_ry_rw_rh.png（如 主界面_299_628_178_57__...png）
    数字依次为图片位置 x, y, 宽, 高。文件名不符合约定时，取名称中前两个数字作为 x, y。

截图方式（--screencap）：1=GDI 2=FramePool 4=DXGI_DesktopDup 8=DXGI_DesktopDup_Window
    16=PrintWindow 32=ScreenDC
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import re
import tempfile
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import cv2
import numpy as np

WORKING_DIR = Path(__file__).parent.parent.resolve()
DEFAULT_IMAGE_DIR = WORKING_DIR / "assets" / "resource" / "image"
W, H = 1280, 720

NAME_RE = re.compile(
    r"^(?P<page>.+)_(?P<x>\d+)_(?P<y>\d+)_(?P<w>\d+)_(?P<h>\d+)"
    r"__(?P<rx>\d+)_(?P<ry>\d+)_(?P<rw>\d+)_(?P<rh>\d+)\.png$"
)

GREEN = (0, 255, 0)
BORDER = 2


def parse_template(path: Path, img: np.ndarray) -> dict:
    """解析模板文件名，得到叠加位置；解析失败时用名称中前两个数字。"""
    m = NAME_RE.match(path.name)
    if m:
        g = m.groupdict()
        return {
            "path": path,
            "page": g["page"],
            "box": tuple(int(g[k]) for k in ("x", "y", "w", "h")),
            "roi": tuple(int(g[k]) for k in ("rx", "ry", "rw", "rh")),
        }

    nums = [int(n) for n in re.findall(r"\d+", path.stem)]
    h, w = img.shape[:2]
    x, y = (nums[0], nums[1]) if len(nums) >= 2 else (0, 0)
    return {"path": path, "page": path.stem, "box": (x, y, w, h), "roi": (x, y, w, h)}


def imread_unicode(path: Path):
    data = np.fromfile(str(path), dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


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
    return results[0] if results else None


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
            time.sleep(0.5)
        raise RuntimeError("截图连续 3 次失败，可尝试换 --screencap（1 / 4 / 8 / 32）")


class OverlayApp:
    def __init__(self, root: tk.Tk, args):
        self.root = root
        self.args = args
        self.screen = np.zeros((H, W, 3), np.uint8)
        self.tpl = None
        self.tpl_info = None
        self.capture = None
        self.photo = None
        self.tmp_path = Path(tempfile.gettempdir()) / "maa084_overlay.png"

        bar = tk.Frame(root)
        bar.pack(fill=tk.X, padx=8, pady=6)

        tk.Button(bar, text="截图游戏窗口", command=self.on_capture).pack(side=tk.LEFT)
        tk.Button(bar, text="上传图片", command=self.on_upload).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        self.status = tk.Label(bar, text="请先截图或上传图片", anchor="w")
        self.status.pack(side=tk.LEFT, padx=12)

        self.canvas = tk.Canvas(
            root, width=W, height=H, bg="black", highlightthickness=0
        )
        self.canvas.pack()

        self._redraw()

    def on_capture(self):
        self.root.config(cursor="watch")
        self.root.update_idletasks()
        try:
            if self.capture is None:
                found = find_window(self.args.window)
                if not found:
                    raise RuntimeError(f"未找到标题含 '{self.args.window}' 的可见窗口")
                hwnd = found[0]
                if not self.args.no_resize:
                    fit_client_size(hwnd, W, H)
                    time.sleep(0.5)
                self.capture = GameCapture(hwnd, self.args.screencap)
            self.screen = self.capture.capture()
        except Exception as e:
            messagebox.showerror("截图失败", str(e))
            return
        finally:
            self.root.config(cursor="")
        self._redraw()

    def on_upload(self):
        path = filedialog.askopenfilename(
            parent=self.root,
            title="选择模板图片",
            initialdir=str(self.args.image_dir),
            filetypes=[("PNG 模板", "*.png"), ("所有文件", "*.*")],
        )
        if not path:
            return
        img = imread_unicode(Path(path))
        if img is None:
            messagebox.showerror("上传失败", f"无法读取图片：{path}")
            return
        self.tpl_info = parse_template(Path(path), img)
        self.tpl = img
        self._redraw()

    def _compose(self) -> np.ndarray:
        view = self.screen.copy()
        if self.tpl is None:
            return view

        x, y = self.tpl_info["box"][:2]
        th, tw = self.tpl.shape[:2]
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(W, x + tw), min(H, y + th)
        if x1 > x0 and y1 > y0:
            view[y0:y1, x0:x1] = self.tpl[y0 - y:y1 - y, x0 - x:x1 - x]

        # 图片四周一圈绿框
        cv2.rectangle(view, (x, y), (x + tw - 1, y + th - 1), GREEN, BORDER, cv2.LINE_8)
        return view

    def _redraw(self):
        view = self._compose()
        ok, buf = cv2.imencode(".png", view)
        if not ok:
            return
        buf.tofile(str(self.tmp_path))
        self.photo = tk.PhotoImage(file=str(self.tmp_path))
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo)

        if self.tpl is None:
            self.status.config(text=f"截图 {self.screen.shape[1]}x{self.screen.shape[0]} | 请上传图片")
        else:
            x, y, tw, th = self.tpl_info["box"]
            self.status.config(
                text=f"截图 {self.screen.shape[1]}x{self.screen.shape[0]} | "
                f"{self.tpl_info['path'].name}  位置({x}, {y})  尺寸{tw}x{th}"
            )


def main():
    ap = argparse.ArgumentParser(description="模板叠加对比工具")
    ap.add_argument("--window", default="LimbusCompany", help="游戏窗口标题关键字")
    ap.add_argument("--image-dir", default=str(DEFAULT_IMAGE_DIR), help="文件对话框初始目录")
    ap.add_argument(
        "--screencap",
        type=int,
        default=16,
        help="截图方式，默认 16=PrintWindow，2=FramePool，1=GDI",
    )
    ap.add_argument("--no-resize", action="store_true", help="不调整游戏窗口大小")
    args = ap.parse_args()

    root = tk.Tk()
    root.title("模板叠加对比")
    root.resizable(False, False)
    OverlayApp(root, args)
    root.mainloop()


if __name__ == "__main__":
    main()
