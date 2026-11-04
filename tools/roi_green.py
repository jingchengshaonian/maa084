"""矩形选区涂绿工具（可缩放）。

流程：
    1. 弹窗选一张图片，窗口按屏幕大小自适应（不会与图片等大而跑到屏幕外）
    2. 左键拖拽框出矩形区域，实时以绿色半透明高亮，并显示 ROI 坐标
    3. 松开后选区保留；按 s 保存（选区被涂成纯绿 #00FF00）

视图操作：
    滚轮 / +/- : 缩放（以光标为中心）    0 : 恢复自适应
    右键或中键拖拽 : 平移（放大后使用）

快捷键：
    [o]重新选图  [c]清除选区  [s]保存  [q/ESC]退出
"""
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

import cv2
import numpy as np

WORKING_DIR = Path(__file__).parent.parent.resolve()
DEFAULT_IMAGE_DIR = WORKING_DIR / "assets" / "resource" / "image"
WINDOW = "ROI Green Picker"
GREEN = (0, 255, 0)
MIN_SCALE, MAX_SCALE = 0.05, 8.0
PAD = 40
HUD_H = 34


def imread_unicode(path: Path):
    data = np.fromfile(str(path), dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def imwrite_unicode(path: Path, img: np.ndarray):
    ok, buf = cv2.imencode(path.suffix or ".png", img)
    if ok:
        buf.tofile(str(path))
    return ok


def pick_image(initial_dir: Path):
    if not initial_dir.is_dir():
        initial_dir = WORKING_DIR
    root = tk.Tk()
    root.withdraw()
    path = filedialog.askopenfilename(
        title="选择图片",
        initialdir=str(initial_dir),
        filetypes=[("图片", "*.png *.jpg *.jpeg *.bmp"), ("所有文件", "*.*")],
    )
    root.destroy()
    return Path(path) if path else None


def screen_size():
    root = tk.Tk()
    root.withdraw()
    w, h = root.winfo_screenwidth(), root.winfo_screenheight()
    root.destroy()
    return w, h


class Viewer:
    def __init__(self, img: np.ndarray, canvas_w: int, canvas_h: int):
        self.img = img
        self.h, self.w = img.shape[:2]
        self.canvas_w = canvas_w
        self.canvas_h = canvas_h - HUD_H

        self.scale = 1.0
        self.offset = [0, 0]  # 图片左上角在画布中的位置
        self.start = None  # 选区起点（图片坐标）
        self.end = None
        self.dragging = False
        self.panning = False
        self.pan_anchor = (0, 0)
        self.pan_origin = (0, 0)
        self.reset_view()

    # ---------- 视图 ----------
    def reset_view(self):
        self.scale = min(self.canvas_w / self.w, self.canvas_h / self.h)
        self.offset = [0, 0]
        self.clamp_offset()

    def clamp_offset(self):
        disp_w, disp_h = self.w * self.scale, self.h * self.scale
        cw, ch = self.canvas_w, self.canvas_h
        # 允许少量留白，避免缩放到边缘时光标锚点被强制拉走
        if disp_w <= cw:
            self.offset[0] = (cw - disp_w) / 2
        else:
            self.offset[0] = min(PAD, max(cw - disp_w - PAD, self.offset[0]))
        if disp_h <= ch:
            self.offset[1] = (ch - disp_h) / 2
        else:
            self.offset[1] = min(PAD, max(ch - disp_h - PAD, self.offset[1]))

    def zoom_at(self, cx, cy, factor):
        ix = (cx - self.offset[0]) / self.scale
        iy = (cy - self.offset[1]) / self.scale
        limit = min(MAX_SCALE, 20000 / max(self.w, self.h))
        new_scale = max(MIN_SCALE, min(limit, self.scale * factor))
        if new_scale == self.scale:
            return
        self.scale = new_scale
        self.offset = [cx - ix * self.scale, cy - iy * self.scale]
        self.clamp_offset()

    def to_image(self, mx, my):
        x = int(round((mx - self.offset[0]) / self.scale))
        y = int(round((my - self.offset[1]) / self.scale))
        return max(0, min(x, self.w - 1)), max(0, min(y, self.h - 1))

    # ---------- 鼠标 ----------
    def on_mouse(self, event, x, y, flags, param):
        if event == cv2.EVENT_MOUSEWHEEL:
            self.zoom_at(x, y, 1.15 if flags > 0 else 1 / 1.15)
        elif event == cv2.EVENT_LBUTTONDOWN:
            self.start = self.to_image(x, y)
            self.end = self.start
            self.dragging = True
        elif event == cv2.EVENT_MOUSEMOVE:
            if self.dragging:
                self.end = self.to_image(x, y)
            elif self.panning:
                self.offset[0] = self.pan_origin[0] + x - self.pan_anchor[0]
                self.offset[1] = self.pan_origin[1] + y - self.pan_anchor[1]
                self.clamp_offset()
        elif event == cv2.EVENT_LBUTTONUP and self.dragging:
            self.end = self.to_image(x, y)
            self.dragging = False
            if self.size() == 0:  # 只单击未拖动，忽略
                self.start = self.end = None
        elif event in (cv2.EVENT_RBUTTONDOWN, cv2.EVENT_MBUTTONDOWN):
            self.panning = True
            self.pan_anchor = (x, y)
            self.pan_origin = tuple(self.offset)
        elif event in (cv2.EVENT_RBUTTONUP, cv2.EVENT_MBUTTONUP):
            self.panning = False

    # ---------- 选区 ----------
    def rect(self):
        if not self.start or not self.end:
            return None
        x1, y1 = self.start
        x2, y2 = self.end
        return min(x1, x2), min(y1, y2), abs(x2 - x1) + 1, abs(y2 - y1) + 1

    def size(self):
        r = self.rect()
        return 0 if r is None else r[2] * r[3]

    # ---------- 绘制 ----------
    def render(self):
        cw, ch = self.canvas_w, self.canvas_h
        canvas = np.zeros((ch, cw, 3), np.uint8)

        disp_w = max(1, int(round(self.w * self.scale)))
        disp_h = max(1, int(round(self.h * self.scale)))
        interp = cv2.INTER_AREA if self.scale < 1 else cv2.INTER_NEAREST
        disp = cv2.resize(self.img, (disp_w, disp_h), interpolation=interp)

        ox, oy = int(round(self.offset[0])), int(round(self.offset[1]))
        x0, y0 = max(0, ox), max(0, oy)
        x1, y1 = min(cw, ox + disp_w), min(ch, oy + disp_h)
        if x1 > x0 and y1 > y0:
            canvas[y0:y1, x0:x1] = disp[y0 - oy:y1 - oy, x0 - ox:x1 - ox]

        rect = self.rect()
        if rect:
            rx, ry, rw, rh = rect
            p1 = (ox + int(rx * self.scale), oy + int(ry * self.scale))
            p2 = (ox + int((rx + rw - 1) * self.scale), oy + int((ry + rh - 1) * self.scale))
            p1c = (max(0, min(p1[0], cw - 1)), max(0, min(p1[1], ch - 1)))
            p2c = (max(0, min(p2[0], cw - 1)), max(0, min(p2[1], ch - 1)))
            if p2c[0] > p1c[0] and p2c[1] > p1c[1]:
                overlay = canvas.copy()
                cv2.rectangle(overlay, p1c, p2c, GREEN, -1)
                cv2.addWeighted(overlay, 0.35, canvas, 0.65, 0, canvas)
            cv2.rectangle(canvas, p1c, p2c, GREEN, 2)
            info = f"[{rx},{ry},{rw},{rh}]  {rw}x{rh}"
        else:
            info = "drag left button to select area"

        out = np.zeros((self.canvas_h + HUD_H, cw, 3), np.uint8)
        out[:ch] = canvas
        cv2.putText(out, info, (8, ch + 22), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (0, 255, 0), 1, cv2.LINE_AA)
        zoom_txt = f"{self.scale * 100:.0f}%"
        (tw, _), _ = cv2.getTextSize(zoom_txt, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
        cv2.putText(out, zoom_txt, (cw - tw - 10, ch + 22), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (200, 200, 200), 1, cv2.LINE_AA)
        return out

    # ---------- 保存 ----------
    def save(self, src: Path):
        rect = self.rect()
        if not rect:
            print("没有选区，未保存")
            return
        x, y, w, h = rect
        img = self.img.copy()
        cv2.rectangle(img, (x, y), (x + w - 1, y + h - 1), GREEN, -1)
        out_path = src.parent / f"{src.stem}_green.png"
        if imwrite_unicode(out_path, img):
            print(f"已保存: {out_path}  ROI=[{x},{y},{w},{h}]")
        else:
            print(f"保存失败: {out_path}")


def main():
    src = pick_image(DEFAULT_IMAGE_DIR)
    if src is None:
        print("未选择图片")
        return
    img = imread_unicode(src)
    if img is None:
        print(f"无法读取图片: {src}")
        return

    sw, sh = screen_size()
    cw, ch = int(sw * 0.75), int(sh * 0.75) - HUD_H
    viewer = Viewer(img, cw, ch + HUD_H)
    cv2.namedWindow(WINDOW, cv2.WINDOW_AUTOSIZE)
    cv2.setMouseCallback(WINDOW, viewer.on_mouse)
    cv2.moveWindow(WINDOW, max(0, (sw - cw) // 2), max(0, (sh - ch - HUD_H) // 2))

    while True:
        cv2.imshow(WINDOW, viewer.render())
        key = cv2.waitKey(20) & 0xFF
        if key in (27, ord("q")):
            break
        if key == ord("c"):
            viewer.start = viewer.end = None
        elif key == ord("0"):
            viewer.reset_view()
        elif key in (ord("+"), ord("=")):
            viewer.zoom_at(viewer.canvas_w // 2, viewer.canvas_h // 2, 1.25)
        elif key in (ord("-"), ord("_")):
            viewer.zoom_at(viewer.canvas_w // 2, viewer.canvas_h // 2, 1 / 1.25)
        elif key == ord("s"):
            viewer.save(src)
        elif key == ord("o"):
            new_src = pick_image(src.parent)
            if new_src is None:
                continue
            new_img = imread_unicode(new_src)
            if new_img is None:
                print(f"无法读取图片: {new_src}")
                continue
            src, img = new_src, new_img
            viewer = Viewer(img, cw, ch + HUD_H)
            cv2.setMouseCallback(WINDOW, viewer.on_mouse)
            cv2.setWindowTitle(WINDOW, f"{WINDOW} - {src.name}")

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
