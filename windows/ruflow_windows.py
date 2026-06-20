#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ctypes
import json
import math
import os
import queue
import re
import subprocess
import sys
import threading
import time
import wave
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    from ctypes import wintypes


DEFAULT_MODEL_NAME = "gigaam-v3-e2e-rnnt"
MODEL_NAME = DEFAULT_MODEL_NAME
DEFAULT_HOTKEY = "ctrl+shift+f9"
DEFAULT_TRIGGER = "mouse"
DEFAULT_MOUSE_BUTTON = "x1"
DEFAULT_PASS_THROUGH_MOUSE_BUTTON = False
DEFAULT_BINDING_SEQUENCE = ("mouse:x1", "mouse:x1")
MAX_BINDING_EVENTS = 8
BINDING_SEQUENCE_TIMEOUT_SECONDS = 1.4
DEFAULT_MAX_DURATION_SECONDS = 0.0
DEFAULT_SAMPLE_RATE = 16_000
DEFAULT_CHANNELS = 1
DEFAULT_SAMPLE_WIDTH_BYTES = 2
WM_QUIT = 0x0012
LLMHF_INJECTED = 0x00000001
DOUBLE_CLICK_SECONDS = 0.34
RESULT_PASTE_SECONDS = 20.0
THREAD_PRIORITY_BELOW_NORMAL = -1
THREAD_PRIORITY_ABOVE_NORMAL = 1
_SENTENCE_END_RE = re.compile(r"[.!?]+(?=\s|$)")
_HOTKEY_SPLIT_RE = re.compile(r"\s*\+\s*|\s+")
_MODIFIER_ALIASES = {
    "control": "ctrl",
    "cmd": "win",
    "command": "win",
    "option": "alt",
    "windows": "win",
}
_MODIFIER_KEYS = {"ctrl", "alt", "shift", "win"}
_MOUSE_BUTTON_DISPLAY = {
    "x1": "Mouse X1",
    "x2": "Mouse X2",
}
_BINDING_MOUSE_ALIASES = {
    "mouse:x1": "mouse:x1",
    "x1": "mouse:x1",
    "back": "mouse:x1",
    "mouse x1": "mouse:x1",
    "mouse button 4": "mouse:x1",
    "mouse:x2": "mouse:x2",
    "x2": "mouse:x2",
    "forward": "mouse:x2",
    "mouse x2": "mouse:x2",
    "mouse button 5": "mouse:x2",
    "mouse:left": "mouse:left",
    "left": "mouse:left",
    "lbutton": "mouse:left",
    "mouse:right": "mouse:right",
    "right": "mouse:right",
    "rbutton": "mouse:right",
    "mouse:middle": "mouse:middle",
    "middle": "mouse:middle",
    "mbutton": "mouse:middle",
}
_BINDING_DISPLAY_NAMES = {
    "ctrl": "Ctrl",
    "alt": "Alt",
    "shift": "Shift",
    "win": "Win",
    "esc": "Esc",
    "enter": "Enter",
    "space": "Space",
    "tab": "Tab",
    "backspace": "Backspace",
    "delete": "Delete",
    "insert": "Insert",
    "pageup": "Page Up",
    "pagedown": "Page Down",
    "mouse:left": "ЛКМ",
    "mouse:right": "ПКМ",
    "mouse:middle": "СКМ",
    "mouse:x1": "Mouse X1",
    "mouse:x2": "Mouse X2",
}
_MODEL_DIR_SAFE_RE = re.compile(r"[^A-Za-z0-9_.-]+")
CONFIG_FILE_NAME = "config.json"
_TK_MODIFIER_STATE_BITS = {
    "shift": 0x0001,
    "ctrl": 0x0004,
    "alt": 0x0008,
    "win": 0x0040,
}
_TK_MODIFIER_KEYSYMS = {
    "Control_L": "ctrl",
    "Control_R": "ctrl",
    "Shift_L": "shift",
    "Shift_R": "shift",
    "Alt_L": "alt",
    "Alt_R": "alt",
    "Meta_L": "win",
    "Meta_R": "win",
    "Super_L": "win",
    "Super_R": "win",
    "Win_L": "win",
    "Win_R": "win",
}
_TK_KEY_ALIASES = {
    "Escape": "esc",
    "Return": "enter",
    "KP_Enter": "enter",
    "BackSpace": "backspace",
    "Delete": "delete",
    "Insert": "insert",
    "Prior": "pageup",
    "Next": "pagedown",
    "space": "space",
    "Tab": "tab",
}
_VK_TOKEN_ALIASES = {
    0x08: "backspace",
    0x09: "tab",
    0x0D: "enter",
    0x10: "shift",
    0x11: "ctrl",
    0x12: "alt",
    0x14: "capslock",
    0x1B: "esc",
    0x20: "space",
    0x21: "pageup",
    0x22: "pagedown",
    0x23: "end",
    0x24: "home",
    0x25: "left",
    0x26: "up",
    0x27: "right",
    0x28: "down",
    0x2D: "insert",
    0x2E: "delete",
    0x5B: "win",
    0x5C: "win",
    0xA0: "shift",
    0xA1: "shift",
    0xA2: "ctrl",
    0xA3: "ctrl",
    0xA4: "alt",
    0xA5: "alt",
}


if sys.platform == "win32":
    LRESULT = ctypes.c_ssize_t
    LPARAM = ctypes.c_ssize_t
    WPARAM = ctypes.c_size_t


    class MousePoint(ctypes.Structure):
        _fields_ = [
            ("x", ctypes.c_long),
            ("y", ctypes.c_long),
        ]


    class MSLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [
            ("pt", MousePoint),
            ("mouseData", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_size_t),
        ]


    class KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [
            ("vkCode", wintypes.DWORD),
            ("scanCode", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_size_t),
        ]


class RuFlowWindowsError(RuntimeError):
    pass


class ClipboardError(RuFlowWindowsError):
    pass


class ASRError(RuFlowWindowsError):
    pass


@dataclass(frozen=True)
class Hotkey:
    modifiers: tuple[str, ...]
    key: str

    @property
    def display_name(self) -> str:
        return "+".join((*[part.capitalize() for part in self.modifiers], self.key.capitalize()))

    @property
    def ui_display_name(self) -> str:
        return " + ".join((*[part.capitalize() for part in self.modifiers], self.key.capitalize()))


@dataclass(frozen=True)
class ASRResult:
    text: str
    duration_ms: int
    model: str


@dataclass(frozen=True)
class ControlWindowResult:
    action: str
    config: dict[str, Any]


class DictationPresenter:
    def show_recording(self, anchor: tuple[int, int] | None, trigger_name: str) -> None:
        pass

    def show_audio_level(self, level: float) -> None:
        pass

    def show_recognizing(self, anchor: tuple[int, int] | None) -> None:
        pass

    def show_result(self, text: str, duration_ms: int) -> None:
        pass

    def show_pasted(self, anchor: tuple[int, int] | None) -> None:
        pass

    def show_error(self, message: str) -> None:
        pass

    def show_cancelled(self) -> None:
        pass

    def run(self) -> None:
        pass

    def stop(self) -> None:
        pass


class ConsolePresenter(DictationPresenter):
    def show_recording(self, anchor: tuple[int, int] | None, trigger_name: str) -> None:
        del anchor
        print(f"Recording... use {trigger_name} again to transcribe.")

    def show_audio_level(self, level: float) -> None:
        del level

    def show_recognizing(self, anchor: tuple[int, int] | None) -> None:
        del anchor
        print("Recognizing...")

    def show_result(self, text: str, duration_ms: int) -> None:
        print(text)
        print(f"Copied text in {duration_ms} ms. Double-click left mouse button or press Ctrl+V to paste.")

    def show_pasted(self, anchor: tuple[int, int] | None) -> None:
        del anchor
        print("Pasted.")

    def show_error(self, message: str) -> None:
        print(f"RuFlow error: {message}", file=sys.stderr)

    def show_cancelled(self) -> None:
        print("Recording canceled.")

    def run(self) -> None:
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass


class PopoverPresenter(DictationPresenter):
    PANEL_BG = "#171a1f"
    PANEL_BORDER = "#2b3037"
    RECORDING_SIZE = (190, 42)
    RECOGNIZING_SIZE = (126, 32)
    RESULT_SIZE = (142, 32)
    PASTED_SIZE = (100, 32)
    ERROR_SIZE = (126, 32)
    WAVE_BAR_COLOR = "#8c949e"
    WAVE_BAR_WIDTH = 2
    WAVE_BAR_COUNT = 40
    WAVE_BAR_SPACING = 4.8
    WAVE_SCROLL_PX = 1.15
    WAVE_MARGIN = 8.0
    WAVE_CENTER_Y = 21.0

    def __init__(self) -> None:
        self._events: queue.Queue[tuple[str, tuple[Any, ...]]] = queue.Queue()
        self._root: Any | None = None
        self._window: Any | None = None
        self._canvas: Any | None = None
        self._timer_item: int | None = None
        self._timer_badge_item: int | None = None
        self._status_pulse_items: list[int] = []
        self._bar_items: list[int] = []
        self._wave_levels: list[float] = []
        self._wave_scroll_px = 0.0
        self._anchor: tuple[int, int] | None = None
        self._state = "hidden"
        self._animation_step = 0
        self._recording_started_at = 0.0
        self._audio_level = 0.0
        self._visual_level = 0.0
        self._last_audio_level_at = 0.0
        self._hide_after_id: str | None = None
        self._tray_icon: Any | None = None

    def show_recording(self, anchor: tuple[int, int] | None, trigger_name: str) -> None:
        self._events.put(("recording", (anchor, trigger_name)))

    def show_audio_level(self, level: float) -> None:
        self._events.put(("level", (level,)))

    def show_recognizing(self, anchor: tuple[int, int] | None) -> None:
        self._events.put(("recognizing", (anchor,)))

    def show_result(self, text: str, duration_ms: int) -> None:
        self._events.put(("result", (text, duration_ms)))

    def show_pasted(self, anchor: tuple[int, int] | None) -> None:
        self._events.put(("pasted", (anchor,)))

    def show_error(self, message: str) -> None:
        self._events.put(("error", (message,)))

    def show_cancelled(self) -> None:
        self._events.put(("cancelled", ()))

    def stop(self) -> None:
        self._events.put(("stop", ()))

    def run(self) -> None:
        import tkinter as tk

        self._root = tk.Tk()
        self._root.withdraw()
        self._start_tray_icon()
        self._root.after(40, self._process_events)
        self._root.after(80, self._animate)
        self._root.mainloop()

    def _build_window(self) -> None:
        if self._root is None or self._window is not None:
            return

        import tkinter as tk

        window = tk.Toplevel(self._root)
        window.withdraw()
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        try:
            window.attributes("-alpha", 0.97)
            window.attributes("-toolwindow", True)
        except tk.TclError:
            pass

        window.configure(bg=self.PANEL_BG)
        window.bind("<Escape>", lambda _event: self._hide())

        canvas = tk.Canvas(
            window,
            width=self.RECORDING_SIZE[0],
            height=self.RECORDING_SIZE[1],
            bg=self.PANEL_BG,
            bd=0,
            highlightthickness=0,
            relief="flat",
        )
        canvas.pack(fill="both", expand=True)

        self._window = window
        self._canvas = canvas

    def _process_events(self) -> None:
        while True:
            try:
                name, args = self._events.get_nowait()
            except queue.Empty:
                break

            if name == "recording":
                self._handle_recording(*args)
            elif name == "level":
                self._handle_level(*args)
            elif name == "recognizing":
                self._handle_recognizing(*args)
            elif name == "result":
                self._handle_result(*args)
            elif name == "pasted":
                self._handle_pasted(*args)
            elif name == "error":
                self._handle_error(*args)
            elif name == "cancelled":
                self._handle_cancelled()
            elif name == "stop":
                self._stop_tray_icon()
                if self._root is not None:
                    self._root.quit()

        if self._root is not None:
            self._root.after(40, self._process_events)

    def _handle_recording(self, anchor: tuple[int, int] | None, trigger_name: str) -> None:
        del trigger_name
        self._build_window()
        self._cancel_scheduled_hide()
        self._state = "recording"
        self._recording_started_at = time.monotonic()
        self._audio_level = 0.0
        self._visual_level = 0.0
        self._wave_levels = [0.0] * self.WAVE_BAR_COUNT
        self._wave_scroll_px = 0.0
        self._anchor = anchor or cursor_position()
        self._draw_recording()
        self._show(*self.RECORDING_SIZE)

    def _handle_level(self, level: float) -> None:
        self._audio_level = max(0.0, min(1.0, float(level)))
        self._last_audio_level_at = time.monotonic()

    def _handle_recognizing(self, anchor: tuple[int, int] | None) -> None:
        self._build_window()
        self._cancel_scheduled_hide()
        self._state = "recognizing"
        self._anchor = anchor or self._anchor or cursor_position()
        self._draw_status("Распознаю", None, "#7ab7ff", *self.RECOGNIZING_SIZE)
        self._show(*self.RECOGNIZING_SIZE)

    def _handle_result(self, text: str, duration_ms: int) -> None:
        del text, duration_ms
        self._build_window()
        self._cancel_scheduled_hide()
        self._state = "result"
        self._anchor = cursor_position()
        self._draw_status("Готово к вставке", None, "#74dd8b", *self.RESULT_SIZE)
        self._show(*self.RESULT_SIZE)
        self._schedule_hide(int(RESULT_PASTE_SECONDS * 1000))

    def _handle_pasted(self, anchor: tuple[int, int] | None) -> None:
        self._build_window()
        self._cancel_scheduled_hide()
        self._state = "pasted"
        self._anchor = anchor or cursor_position()
        self._draw_status("Вставлено", None, "#74dd8b", *self.PASTED_SIZE)
        self._show(*self.PASTED_SIZE)
        self._schedule_hide(1200)

    def _handle_error(self, message: str) -> None:
        print(f"RuFlow error: {message}", file=sys.stderr)
        self._build_window()
        self._cancel_scheduled_hide()
        self._state = "error"
        self._anchor = cursor_position()
        self._draw_status("Не распознано", None, "#ffcc66", *self.ERROR_SIZE)
        self._show(*self.ERROR_SIZE)
        self._schedule_hide(2800)

    def _handle_cancelled(self) -> None:
        self._state = "hidden"
        self._hide()

    def _hide(self) -> None:
        self._state = "hidden"
        if self._window is not None:
            self._window.withdraw()

    def _show(self, width: int, height: int) -> None:
        if self._window is None:
            return
        x, y = self._anchor or cursor_position()
        screen_width = self._window.winfo_screenwidth()
        screen_height = self._window.winfo_screenheight()
        margin = 12
        offset = 18
        taskbar_guard = 64
        left = min(max(margin, x + offset), max(margin, screen_width - width - margin))
        if y + offset + height > screen_height - taskbar_guard:
            top = y - height - offset
        else:
            top = y + offset
        top = min(max(margin, top), max(margin, screen_height - height - taskbar_guard))
        self._window.geometry(f"{width}x{height}+{left}+{top}")
        self._window.deiconify()
        self._window.lift()

    def _animate(self) -> None:
        if self._canvas is not None:
            self._animation_step = (self._animation_step + 1) % 100_000
            if self._state == "recording":
                self._anchor = cursor_position()
                self._show(*self.RECORDING_SIZE)
                self._animate_recording()
            elif self._state == "recognizing":
                self._anchor = cursor_position()
                self._show(*self.RECOGNIZING_SIZE)
                self._animate_status()
            elif self._state == "result":
                self._anchor = cursor_position()
                self._show(*self.RESULT_SIZE)
            elif self._state == "pasted":
                self._anchor = cursor_position()
                self._show(*self.PASTED_SIZE)
            elif self._state == "error":
                self._anchor = cursor_position()
                self._show(*self.ERROR_SIZE)

        if self._root is not None:
            self._root.after(33, self._animate)

    def _animate_recording(self) -> None:
        if self._canvas is None:
            return

        now = time.monotonic()
        self._wave_scroll_px += self.WAVE_SCROLL_PX
        while self._wave_scroll_px >= self.WAVE_BAR_SPACING:
            self._wave_scroll_px -= self.WAVE_BAR_SPACING
            self._wave_levels.append(self._current_wave_sample(now))
            self._wave_levels = self._wave_levels[-self.WAVE_BAR_COUNT:]

        if self._timer_item is not None:
            elapsed = max(0, int(now - self._recording_started_at))
            minutes, seconds = divmod(elapsed, 60)
            timer_text = f"{minutes:02d}:{seconds:02d}"
            self._canvas.itemconfigure(self._timer_item, text=timer_text)

        width, _height = self.RECORDING_SIZE
        wave_left = self.WAVE_MARGIN
        wave_right = width - self.WAVE_MARGIN
        clip_left = wave_left
        clip_right = wave_right
        center_y = self.WAVE_CENTER_Y
        last_index = len(self._wave_levels) - 1
        for index, item in enumerate(self._bar_items):
            x = wave_right - (last_index - index) * self.WAVE_BAR_SPACING - self._wave_scroll_px
            if x < clip_left or x > clip_right:
                self._canvas.itemconfigure(item, state="hidden")
                continue

            self._canvas.itemconfigure(item, state="normal")
            level = self._wave_levels[index] if index < len(self._wave_levels) else 0.0
            height = 4.0 + min(1.0, level) * 26.0
            self._canvas.coords(item, x, center_y - height / 2, x, center_y + height / 2)
            self._canvas.itemconfigure(item, fill=self.WAVE_BAR_COLOR)

        if self._timer_badge_item is not None:
            self._canvas.tag_raise(self._timer_badge_item)
        if self._timer_item is not None:
            self._canvas.tag_raise(self._timer_item)

    def _current_wave_sample(self, now: float) -> float:
        if now - self._last_audio_level_at >= 0.28:
            return 0.0
        level = max(0.0, min(1.0, self._audio_level))
        return min(1.0, level * 0.9)

    def _animate_status(self) -> None:
        if self._canvas is None or not self._status_pulse_items:
            return
        step = self._animation_step
        center_y = max(1, self._canvas.winfo_height()) / 2
        for index, item in enumerate(self._status_pulse_items):
            height = 7 + 6 * (0.5 + 0.5 * math.sin(step * 0.5 + index * 1.7))
            x = 19 + index * 6
            self._canvas.coords(item, x, center_y - height / 2, x, center_y + height / 2)

    def _draw_recording(self) -> None:
        if self._canvas is None:
            return

        width, height = self.RECORDING_SIZE
        self._canvas.configure(width=width, height=height, bg=self.PANEL_BG)
        self._canvas.delete("all")
        self._status_pulse_items = []
        self._timer_badge_item = None
        self._wave_levels = self._wave_levels or [0.0] * self.WAVE_BAR_COUNT
        self._round_rect(self._canvas, 1, 1, width - 1, height - 1, 10, fill=self.PANEL_BG, outline=self.PANEL_BORDER)

        self._bar_items = []
        for index in range(self.WAVE_BAR_COUNT):
            x = self.WAVE_MARGIN + index * self.WAVE_BAR_SPACING
            self._bar_items.append(
                self._canvas.create_line(
                    x,
                    self.WAVE_CENTER_Y,
                    x,
                    self.WAVE_CENTER_Y,
                    fill=self.WAVE_BAR_COLOR,
                    width=self.WAVE_BAR_WIDTH,
                    capstyle="round",
                )
            )

        badge_width = 38
        badge_height = 16
        self._timer_badge_item = self._round_rect(
            self._canvas,
            int(width / 2 - badge_width / 2),
            int(height / 2 - badge_height / 2),
            int(width / 2 + badge_width / 2),
            int(height / 2 + badge_height / 2),
            7,
            fill="#22262d",
            outline="#303640",
        )
        self._timer_item = self._canvas.create_text(
            width / 2,
            self.WAVE_CENTER_Y,
            anchor="center",
            text="00:00",
            fill="#e6eaee",
            font=("Segoe UI", 8),
        )

    def _draw_status(self, title: str, subtitle: str | None, accent: str, width: int, height: int) -> None:
        if self._canvas is None:
            return

        self._canvas.configure(width=width, height=height, bg=self.PANEL_BG)
        self._canvas.delete("all")
        self._timer_item = None
        self._timer_badge_item = None
        self._bar_items = []

        self._round_rect(self._canvas, 1, 1, width - 1, height - 1, 9, fill=self.PANEL_BG, outline=self.PANEL_BORDER)
        self._status_pulse_items = []
        if title == "Распознаю":
            for index in range(3):
                x = 16 + index * 6
                self._status_pulse_items.append(
                    self._canvas.create_line(
                        x,
                        height / 2 - 5,
                        x,
                        height / 2 + 5,
                        fill=self.WAVE_BAR_COLOR,
                        width=self.WAVE_BAR_WIDTH,
                        capstyle="round",
                    )
                )

        title_y = height / 2
        self._canvas.create_text(
            38 if self._status_pulse_items else width / 2,
            title_y,
            anchor="w" if self._status_pulse_items else "center",
            text=title,
            fill="#e6eaee" if title != "Не распознано" else "#f1d38a",
            font=("Segoe UI", 8, "bold" if title == "Готово к вставке" else "normal"),
        )
        if subtitle:
            self._canvas.create_text(
                width / 2,
                32,
                anchor="center",
                text=subtitle,
                fill="#aab2bd",
                font=("Segoe UI", 8),
            )

    def _schedule_hide(self, delay_ms: int) -> None:
        if self._window is None:
            return
        self._hide_after_id = self._window.after(delay_ms, self._hide)

    def _cancel_scheduled_hide(self) -> None:
        if self._window is not None and self._hide_after_id is not None:
            try:
                self._window.after_cancel(self._hide_after_id)
            except Exception:
                pass
        self._hide_after_id = None

    def _round_rect(self, canvas: Any, x1: int, y1: int, x2: int, y2: int, radius: int, **kwargs: Any) -> int:
        points = [
            x1 + radius,
            y1,
            x2 - radius,
            y1,
            x2,
            y1,
            x2,
            y1 + radius,
            x2,
            y2 - radius,
            x2,
            y2,
            x2 - radius,
            y2,
            x1 + radius,
            y2,
            x1,
            y2,
            x1,
            y2 - radius,
            x1,
            y1 + radius,
            x1,
            y1,
        ]
        return int(canvas.create_polygon(points, smooth=True, splinesteps=24, **kwargs))

    def _start_tray_icon(self) -> None:
        try:
            import pystray
            from PIL import Image, ImageDraw, ImageFont
        except Exception as error:
            print(f"RuFlow warning: tray icon is unavailable: {error}", file=sys.stderr)
            return

        image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((8, 8, 56, 56), radius=14, fill=(23, 26, 31, 255), outline=(80, 86, 96, 255), width=2)
        try:
            font = ImageFont.truetype("segoeuib.ttf", 30)
        except Exception:
            font = ImageFont.load_default()
        draw.text((32, 31), "R", fill=(230, 234, 238, 255), anchor="mm", font=font)

        menu = pystray.Menu(
            pystray.MenuItem("Настройки", lambda _icon, _item: self._open_settings_from_tray()),
            pystray.MenuItem("Выйти из RuFlow", lambda _icon, _item: self.stop()),
        )
        icon = pystray.Icon("RuFlow", image, "RuFlow", menu)
        self._tray_icon = icon
        try:
            icon.run_detached()
        except Exception as error:
            self._tray_icon = None
            print(f"RuFlow warning: tray icon did not start: {error}", file=sys.stderr)

    def _stop_tray_icon(self) -> None:
        icon = self._tray_icon
        self._tray_icon = None
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass

    def _open_settings_from_tray(self) -> None:
        try:
            subprocess.Popen(settings_command(), cwd=str(Path(__file__).resolve().parents[1]))
        except Exception as error:
            self.show_error(f"не удалось открыть настройки: {error}")


def parse_hotkey(value: str) -> Hotkey:
    parts = [part for part in _HOTKEY_SPLIT_RE.split(value.strip().lower()) if part]
    if len(parts) < 2:
        raise ValueError("hotkey must contain at least one modifier and one key, for example ctrl+alt+space")

    normalized = [_MODIFIER_ALIASES.get(part, part) for part in parts]
    modifiers = tuple(normalized[:-1])
    key = normalized[-1]

    if key in _MODIFIER_KEYS:
        raise ValueError("hotkey primary key cannot be a modifier")

    unknown_modifiers = [modifier for modifier in modifiers if modifier not in _MODIFIER_KEYS]
    if unknown_modifiers:
        raise ValueError(f"unsupported hotkey modifier(s): {', '.join(unknown_modifiers)}")

    if len(set(modifiers)) != len(modifiers):
        raise ValueError("hotkey contains duplicate modifiers")

    return Hotkey(modifiers=modifiers, key=key)


def format_hotkey_for_ui(value: str) -> str:
    return parse_hotkey(value).ui_display_name


def normalize_binding_token(value: str) -> str:
    normalized = str(value).strip().lower().replace("_", " ").replace("-", " ")
    normalized = re.sub(r"\s+", " ", normalized)
    if not normalized:
        raise ValueError("binding event cannot be empty")

    alias = _MODIFIER_ALIASES.get(normalized, normalized)
    alias = _BINDING_MOUSE_ALIASES.get(alias, alias)
    if alias.startswith("mouse "):
        alias = "mouse:" + alias.removeprefix("mouse ").strip()
    if alias in _BINDING_MOUSE_ALIASES:
        alias = _BINDING_MOUSE_ALIASES[alias]
    if alias.startswith("f") and re.fullmatch(r"f\d{1,2}", alias):
        return alias
    if len(alias) == 1:
        return alias
    if re.fullmatch(r"[a-z0-9 ]+", alias):
        return alias.replace(" ", "")
    if alias.startswith("mouse:") and alias in _BINDING_DISPLAY_NAMES:
        return alias
    raise ValueError(f"unsupported binding event: {value}")


def binding_token_from_tk_key(keysym: str, char: str = "") -> str | None:
    if keysym in _TK_MODIFIER_KEYSYMS:
        return _TK_MODIFIER_KEYSYMS[keysym]
    key = normalize_tk_key_name(keysym, char)
    if not key:
        return None
    try:
        return normalize_binding_token(key)
    except ValueError:
        return None


def binding_token_from_vk_code(vk_code: int) -> str | None:
    if vk_code in _VK_TOKEN_ALIASES:
        return _VK_TOKEN_ALIASES[vk_code]
    if 0x30 <= vk_code <= 0x39:
        return chr(vk_code).lower()
    if 0x41 <= vk_code <= 0x5A:
        return chr(vk_code).lower()
    if 0x60 <= vk_code <= 0x69:
        return str(vk_code - 0x60)
    if 0x70 <= vk_code <= 0x87:
        return f"f{vk_code - 0x6F}"
    return None


def parse_binding_sequence(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        parts = [part for part in re.split(r"\s*\+\s*|\s*,\s*", value.strip()) if part]
    elif isinstance(value, (list, tuple)):
        parts = [str(part) for part in value]
    else:
        raise ValueError("binding must be a list or + separated string")

    tokens = tuple(normalize_binding_token(part) for part in parts)
    if not tokens:
        raise ValueError("binding must contain at least one event")
    if len(tokens) > MAX_BINDING_EVENTS:
        raise ValueError(f"binding can contain up to {MAX_BINDING_EVENTS} events")
    return tokens


def format_binding_token(value: str) -> str:
    token = normalize_binding_token(value)
    if token in _BINDING_DISPLAY_NAMES:
        return _BINDING_DISPLAY_NAMES[token]
    if re.fullmatch(r"f\d{1,2}", token):
        return token.upper()
    if len(token) == 1:
        return token.upper()
    return token.capitalize()


def format_binding_sequence(value: Any) -> list[str]:
    return [format_binding_token(token) for token in parse_binding_sequence(value)]


def binding_sequence_to_config(value: Any) -> list[str]:
    return list(parse_binding_sequence(value))


def normalize_tk_key_name(keysym: str, char: str = "") -> str:
    if keysym in _TK_KEY_ALIASES:
        return _TK_KEY_ALIASES[keysym]
    if re.fullmatch(r"F\d{1,2}", keysym):
        return keysym.lower()
    if len(char) == 1 and char.strip():
        return char.lower()
    return keysym.replace("_", " ").strip().lower()


def hotkey_from_key_event(keysym: str, char: str, state: int, pressed_modifiers: set[str] | None = None) -> str | None:
    if keysym in _TK_MODIFIER_KEYSYMS:
        return None

    key = normalize_tk_key_name(keysym, char)
    if not key or key in _MODIFIER_KEYS:
        return None

    modifiers: list[str] = []
    source_modifiers = pressed_modifiers or set()
    for modifier in ("ctrl", "shift", "alt", "win"):
        if modifier in source_modifiers or state & _TK_MODIFIER_STATE_BITS[modifier]:
            modifiers.append(modifier)

    if not modifiers:
        return None

    return parse_hotkey("+".join((*modifiers, key))).display_name.lower()


def default_config_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "RuFlow"
    return Path.home() / "AppData" / "Roaming" / "RuFlow"


def default_config_path() -> Path:
    return default_config_dir() / CONFIG_FILE_NAME


def default_user_config() -> dict[str, Any]:
    return {
        "binding": list(DEFAULT_BINDING_SEQUENCE),
    }


def sanitize_user_config(payload: Any) -> dict[str, Any]:
    config = default_user_config()
    if not isinstance(payload, dict):
        return config

    binding = payload.get("binding")
    if binding is not None:
        try:
            config["binding"] = binding_sequence_to_config(binding)
            return config
        except ValueError:
            return config

    trigger = str(payload.get("trigger", DEFAULT_TRIGGER)).strip().lower()
    if trigger == "hotkey" and isinstance(payload.get("hotkey"), str):
        try:
            hotkey = parse_hotkey(str(payload["hotkey"]))
            config["binding"] = [*hotkey.modifiers, hotkey.key]
        except ValueError:
            pass
    elif isinstance(payload.get("mouse_button"), str):
        try:
            button = parse_mouse_button(str(payload["mouse_button"]))
            config["binding"] = [f"mouse:{button}", f"mouse:{button}"]
        except ValueError:
            pass

    return config


def load_user_config(config_path: Path | None = None) -> dict[str, Any]:
    path = config_path or default_config_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default_user_config()
    except (OSError, json.JSONDecodeError):
        return default_user_config()
    return sanitize_user_config(payload)


def save_user_config(config: dict[str, Any], config_path: Path | None = None) -> Path:
    path = config_path or default_config_path()
    sanitized = sanitize_user_config(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(sanitized, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def sentence_count(text: str) -> int:
    return len(_SENTENCE_END_RE.findall(text))


def format_for_insertion(raw_text: str) -> str:
    text = raw_text.strip()
    if text.endswith(".") and not text.endswith("...") and sentence_count(text) == 1:
        return text[:-1].strip()
    return text


def pcm16_audio_level(data: bytes) -> float:
    sample_bytes = len(data) - (len(data) % 2)
    if sample_bytes <= 0:
        return 0.0

    samples = memoryview(data[:sample_bytes]).cast("h")
    if not samples:
        return 0.0

    square_sum = sum(int(sample) * int(sample) for sample in samples)
    rms = math.sqrt(square_sum / len(samples)) / 32768.0
    if rms < 0.0025:
        return 0.0
    normalized = min(1.0, (rms - 0.0025) * 18.0)
    return normalized ** 0.65


def parse_asr_stdout(
    stdout: str,
    stderr: str = "",
    returncode: int = 0,
    *,
    expected_model: str = DEFAULT_MODEL_NAME,
) -> ASRResult:
    stdout = stdout.strip()
    if not stdout:
        detail = _short_message(stderr) if stderr else "ASR runner did not return JSON"
        raise ASRError(detail)

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as error:
        if returncode != 0 and stderr:
            raise ASRError(_short_message(stderr)) from error
        raise ASRError(f"ASR runner returned invalid JSON: {error}") from error

    model = str(payload.get("model", ""))
    if model != expected_model:
        raise ASRError(f"unexpected ASR model: {model or '<missing>'}")

    if payload.get("ok") is not True:
        raise ASRError(_short_message(str(payload.get("error") or stderr or "ASR failed")))

    text = str(payload.get("text") or "").strip()
    if not text:
        raise ASRError("ASR returned empty text")

    try:
        duration_ms = int(payload.get("duration_ms") or 0)
    except (TypeError, ValueError):
        duration_ms = 0

    return ASRResult(text=text, duration_ms=duration_ms, model=model)


def run_asr(
    *,
    mode: str,
    model_name: str,
    python_executable: Path,
    runner_path: Path,
    wav_path: Path,
    model_dir: Path | None,
    hf_insecure: bool,
    timeout_seconds: float | None,
) -> ASRResult:
    if mode == "in-process":
        return run_asr_in_process(
            wav_path=wav_path,
            model_name=model_name,
            model_dir=model_dir,
            hf_insecure=hf_insecure,
        )
    if mode != "subprocess":
        raise ASRError(f"unsupported ASR mode: {mode}")

    if not python_executable.exists():
        raise ASRError(f"Python executable not found: {python_executable}")
    if not runner_path.is_file():
        raise ASRError(f"ASR runner not found: {runner_path}")
    if not wav_path.is_file():
        raise ASRError(f"audio file not found: {wav_path}")

    env = os.environ.copy()
    if model_dir is not None:
        if not model_dir.is_dir():
            raise ASRError(f"model directory not found: {model_dir}")
        env["RUFLOW_GIGAAM_MODEL_DIR"] = str(model_dir)
        env["HF_HUB_OFFLINE"] = "1"
    env["RUFLOW_ASR_MODEL"] = model_name
    if hf_insecure:
        env["RUFLOW_HF_INSECURE"] = "1"

    try:
        process = subprocess.run(
            [str(python_executable), str(runner_path), str(wav_path)],
            cwd=str(runner_path.parent),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        raise ASRError(f"ASR timed out after {timeout_seconds:g} seconds") from error

    return parse_asr_stdout(
        process.stdout,
        process.stderr,
        process.returncode,
        expected_model=model_name,
    )


def run_asr_in_process(
    *,
    wav_path: Path,
    model_name: str,
    model_dir: Path | None,
    hf_insecure: bool,
) -> ASRResult:
    if not wav_path.is_file():
        raise ASRError(f"audio file not found: {wav_path}")

    updates: dict[str, str | None] = {}
    if model_dir is not None:
        if not model_dir.is_dir():
            raise ASRError(f"model directory not found: {model_dir}")
        updates["RUFLOW_GIGAAM_MODEL_DIR"] = str(model_dir)
        updates["HF_HUB_OFFLINE"] = "1"
    updates["RUFLOW_ASR_MODEL"] = model_name
    if hf_insecure:
        updates["RUFLOW_HF_INSECURE"] = "1"

    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from asr import runner as asr_runner

    started = time.perf_counter()
    try:
        with patched_environment(updates):
            text = asr_runner.recognize(wav_path, model_name=model_name)
    except Exception as error:
        raise ASRError(asr_runner.user_facing_error(error)) from error

    text = asr_runner.normalize_text(text)
    if not text:
        raise ASRError("ASR returned empty text")

    return ASRResult(
        text=text,
        duration_ms=int((time.perf_counter() - started) * 1000),
        model=model_name,
    )


@contextmanager
def patched_environment(updates: dict[str, str | None]):
    previous: dict[str, str | None] = {key: os.environ.get(key) for key in updates}
    try:
        for key, value in updates.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class WindowsAudioRecorder:
    def __init__(
        self,
        recordings_dir: Path,
        *,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        channels: int = DEFAULT_CHANNELS,
        sample_width_bytes: int = DEFAULT_SAMPLE_WIDTH_BYTES,
        level_callback: Any | None = None,
    ) -> None:
        self.recordings_dir = recordings_dir
        self.sample_rate = sample_rate
        self.channels = channels
        self.sample_width_bytes = sample_width_bytes
        self.level_callback = level_callback
        self._lock = threading.RLock()
        self._stream: Any | None = None
        self._wave_file: wave.Wave_write | None = None
        self._current_path: Path | None = None
        self._last_status: str | None = None
        self._last_level_report_at = 0.0

    def start(self) -> None:
        try:
            import sounddevice as sd
        except ImportError as error:
            raise RuFlowWindowsError("sounddevice is not installed; run scripts\\setup_windows.bat") from error

        self.cancel()
        self.recordings_dir.mkdir(parents=True, exist_ok=True)
        wav_path = self.recordings_dir / f"ruflow-{time.strftime('%Y%m%d-%H%M%S')}-{int(time.time() * 1000) % 1000:03d}.wav"
        wave_file = wave.open(str(wav_path), "wb")
        wave_file.setnchannels(self.channels)
        wave_file.setsampwidth(self.sample_width_bytes)
        wave_file.setframerate(self.sample_rate)

        stream = sd.RawInputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="int16",
            blocksize=max(1, int(self.sample_rate * 0.05)),
            callback=self._audio_callback,
        )

        with self._lock:
            self._wave_file = wave_file
            self._current_path = wav_path
            self._last_status = None
            self._stream = stream

        try:
            stream.start()
        except Exception:
            self.cancel()
            raise

    def stop(self) -> Path:
        with self._lock:
            stream = self._stream
            wav_path = self._current_path

        if stream is None or wav_path is None:
            raise RuFlowWindowsError("no active recording")

        try:
            stream.stop()
        finally:
            stream.close()

        with self._lock:
            self._stream = None
            wave_file = self._wave_file
            self._wave_file = None
            self._current_path = None
            last_status = self._last_status

        if wave_file is not None:
            wave_file.close()

        if last_status:
            print(f"Audio warning: {last_status}", file=sys.stderr)

        if not wav_path.is_file() or wav_path.stat().st_size <= 44:
            raise RuFlowWindowsError(f"recording was not created: {wav_path}")

        return wav_path

    def cancel(self) -> None:
        with self._lock:
            stream = self._stream
            self._stream = None
            wave_file = self._wave_file
            self._wave_file = None
            wav_path = self._current_path
            self._current_path = None

        if stream is not None:
            try:
                stream.stop()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass

        if wave_file is not None:
            wave_file.close()

        if wav_path is not None:
            try:
                wav_path.unlink()
            except FileNotFoundError:
                pass

    def _audio_callback(self, indata: Any, frames: int, time_info: Any, status: Any) -> None:
        del frames, time_info
        data = bytes(indata)
        level_callback = None
        should_report_level = False
        now = time.monotonic()

        with self._lock:
            if status:
                self._last_status = str(status)
            if self._wave_file is not None:
                self._wave_file.writeframes(data)
            if self.level_callback is not None and now - self._last_level_report_at >= 0.05:
                self._last_level_report_at = now
                level_callback = self.level_callback
                should_report_level = True

        if should_report_level and level_callback is not None:
            try:
                level_callback(pcm16_audio_level(data))
            except Exception:
                pass


class DictationController:
    def __init__(
        self,
        *,
        trigger_name: str,
        recorder: WindowsAudioRecorder,
        presenter: DictationPresenter,
        python_executable: Path,
        runner_path: Path,
        model_name: str,
        model_dir: Path | None,
        hf_insecure: bool,
        keep_recordings: bool,
        auto_paste: bool,
        copy_to_clipboard: bool,
        max_duration_seconds: float,
        asr_timeout_seconds: float | None,
        asr_mode: str,
    ) -> None:
        self.trigger_name = trigger_name
        self.recorder = recorder
        self.presenter = presenter
        self.python_executable = python_executable
        self.runner_path = runner_path
        self.model_name = model_name
        self.model_dir = model_dir
        self.hf_insecure = hf_insecure
        self.keep_recordings = keep_recordings
        self.auto_paste = auto_paste
        self.copy_to_clipboard = copy_to_clipboard
        self.max_duration_seconds = max_duration_seconds
        self.asr_timeout_seconds = asr_timeout_seconds
        self.asr_mode = asr_mode
        self._lock = threading.RLock()
        self._state = "idle"
        self._recording_timer: threading.Timer | None = None
        self._anchor: tuple[int, int] | None = None
        self._last_result_text: str | None = None
        self._paste_ready_until = 0.0

    def begin_recording(self, anchor: tuple[int, int] | None = None) -> None:
        with self._lock:
            self._expire_paste_ready_locked()
            if self._state != "idle":
                return
            self._state = "recording"
            self._anchor = anchor or cursor_position()
            self._last_result_text = None
            self._paste_ready_until = 0.0

        try:
            self.recorder.start()
        except Exception:
            with self._lock:
                self._state = "idle"
                self._anchor = None
            raise

        if self.max_duration_seconds > 0:
            timer = threading.Timer(self.max_duration_seconds, self.finish_recording)
            timer.daemon = True
            with self._lock:
                self._recording_timer = timer
            timer.start()

        self.presenter.show_recording(self._anchor, self.trigger_name)

    def finish_recording(self, anchor: tuple[int, int] | None = None) -> None:
        with self._lock:
            if self._state != "recording":
                return
            self._state = "saving"
            self._cancel_timer_locked()
            if anchor is not None:
                self._anchor = anchor
            anchor = self._anchor

        try:
            wav_path = self.recorder.stop()
        except Exception as error:
            self._fail(error)
            return

        self.presenter.show_recognizing(anchor)
        worker = threading.Thread(target=self._transcribe_and_insert, args=(wav_path,), daemon=True)
        worker.start()

    def cancel_recording(self) -> None:
        with self._lock:
            if self._state != "recording":
                return
            self._state = "idle"
            self._cancel_timer_locked()
            self._anchor = None

        self.recorder.cancel()
        self.presenter.show_cancelled()

    @property
    def is_recording(self) -> bool:
        with self._lock:
            return self._state == "recording"

    def paste_last_result(self, anchor: tuple[int, int] | None = None) -> bool:
        with self._lock:
            self._expire_paste_ready_locked()
            if self._state != "paste_ready" or not self._last_result_text:
                return False
            text = self._last_result_text

        try:
            set_clipboard_text(text)
            time.sleep(0.03)
            send_ctrl_v()
        except Exception as error:
            self.presenter.show_error(str(error))
            return True

        with self._lock:
            self._state = "idle"
            self._last_result_text = None
            self._paste_ready_until = 0.0
            self._anchor = None
        self.presenter.show_pasted(anchor)
        return True

    def _transcribe_and_insert(self, wav_path: Path) -> None:
        set_current_thread_priority(THREAD_PRIORITY_BELOW_NORMAL)
        next_state = "idle"
        last_result_text: str | None = None
        try:
            result = run_asr(
                mode=self.asr_mode,
                model_name=self.model_name,
                python_executable=self.python_executable,
                runner_path=self.runner_path,
                wav_path=wav_path,
                model_dir=self.model_dir,
                hf_insecure=self.hf_insecure,
                timeout_seconds=self.asr_timeout_seconds,
            )
            text = format_for_insertion(result.text)
            if not text:
                raise ASRError("ASR returned empty text after formatting")

            if self.copy_to_clipboard:
                set_clipboard_text(text)

            if self.auto_paste:
                send_ctrl_v()

            if not self.copy_to_clipboard and not self.auto_paste:
                print(text)
            elif self.copy_to_clipboard and not self.auto_paste:
                next_state = "paste_ready"
                last_result_text = text
            self.presenter.show_result(text, result.duration_ms)
        except Exception as error:
            self.presenter.show_error(str(error))
        finally:
            if not self.keep_recordings:
                try:
                    wav_path.unlink()
                except FileNotFoundError:
                    pass
            with self._lock:
                self._state = next_state
                self._last_result_text = last_result_text
                self._paste_ready_until = (
                    time.monotonic() + RESULT_PASTE_SECONDS if next_state == "paste_ready" else 0.0
                )
                self._anchor = None

    def _fail(self, error: Exception) -> None:
        self.presenter.show_error(str(error))
        with self._lock:
            self._state = "idle"
            self._cancel_timer_locked()
            self._anchor = None
        self.recorder.cancel()

    def _cancel_timer_locked(self) -> None:
        if self._recording_timer is not None:
            self._recording_timer.cancel()
            self._recording_timer = None

    def _expire_paste_ready_locked(self) -> None:
        if self._state == "paste_ready" and time.monotonic() > self._paste_ready_until:
            self._state = "idle"
            self._last_result_text = None
            self._paste_ready_until = 0.0


class KeyboardHotkeyLoop:
    def __init__(self, hotkey: Hotkey, controller: DictationController) -> None:
        self.hotkey = hotkey
        self.controller = controller
        self._is_hotkey_down = False
        self._lock = threading.RLock()
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        try:
            import keyboard
        except ImportError as error:
            raise RuFlowWindowsError("keyboard is not installed; run scripts\\setup_windows.bat") from error

        try:
            keyboard.on_press_key(self.hotkey.key, self._on_primary_down, suppress=False)
            keyboard.on_release_key(self.hotkey.key, self._on_primary_up, suppress=False)
            keyboard.on_press_key("esc", self._on_escape, suppress=False)
            for modifier in self.hotkey.modifiers:
                keyboard.on_release_key(modifier, self._on_modifier_up, suppress=False)
        except Exception as error:
            raise RuFlowWindowsError(
                "could not register global hotkey; try running the terminal as Administrator"
            ) from error
        self._started = True

    def run(self) -> None:
        self.start()
        import keyboard

        print(f"Ready. Hold {self.hotkey.display_name} to dictate. Press Ctrl+C to quit.")
        try:
            keyboard.wait()
        except KeyboardInterrupt:
            pass

    def _on_primary_down(self, event: Any) -> None:
        del event
        if not self._modifiers_pressed():
            return
        with self._lock:
            if self._is_hotkey_down:
                return
            self._is_hotkey_down = True
        try:
            self.controller.begin_recording()
        except Exception as error:
            print(f"RuFlow error: {error}", file=sys.stderr)
            with self._lock:
                self._is_hotkey_down = False

    def _on_primary_up(self, event: Any) -> None:
        del event
        self._release_hotkey()

    def _on_modifier_up(self, event: Any) -> None:
        del event
        self._release_hotkey()

    def _on_escape(self, event: Any) -> None:
        del event
        with self._lock:
            was_down = self._is_hotkey_down
            self._is_hotkey_down = False
        if was_down:
            self.controller.cancel_recording()

    def _release_hotkey(self) -> None:
        with self._lock:
            if not self._is_hotkey_down:
                return
            self._is_hotkey_down = False
        self.controller.finish_recording()

    def _modifiers_pressed(self) -> bool:
        import keyboard

        return all(keyboard.is_pressed(modifier) for modifier in self.hotkey.modifiers)


class BindingSequenceLoop:
    WH_KEYBOARD_LL = 13
    WH_MOUSE_LL = 14
    WM_KEYDOWN = 0x0100
    WM_KEYUP = 0x0101
    WM_SYSKEYDOWN = 0x0104
    WM_SYSKEYUP = 0x0105
    WM_LBUTTONDOWN = 0x0201
    WM_RBUTTONDOWN = 0x0204
    WM_MBUTTONDOWN = 0x0207
    WM_XBUTTONDOWN = 0x020B
    XBUTTON1 = 0x0001
    XBUTTON2 = 0x0002

    def __init__(
        self,
        *,
        binding: tuple[str, ...],
        controller: DictationController,
    ) -> None:
        self.binding = parse_binding_sequence(binding)
        self.controller = controller
        self._sequence: list[str] = []
        self._pressed_key_tokens: set[str] = set()
        self._last_event_at = 0.0
        self._last_left_click_at = 0.0
        self._lock = threading.RLock()
        self._action_queue: queue.Queue[tuple[str, tuple[Any, ...]]] = queue.Queue()
        self._action_thread: threading.Thread | None = None
        self._hook_thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._mouse_hook: Any | None = None
        self._keyboard_hook: Any | None = None
        self._mouse_hook_proc: Any | None = None
        self._keyboard_hook_proc: Any | None = None
        self._user32: Any | None = None
        self._mouse_ready = threading.Event()
        self._keyboard_ready = threading.Event()
        self._stop_requested = threading.Event()
        self._startup_error: Exception | None = None

    @property
    def display_name(self) -> str:
        return " + ".join(format_binding_sequence(self.binding))

    def start(self) -> None:
        self._action_thread = threading.Thread(target=self._run_actions, name="RuFlowBindingActions", daemon=True)
        self._action_thread.start()
        self._hook_thread = threading.Thread(target=self._run_hooks, name="RuFlowBindingHooks", daemon=True)
        self._hook_thread.start()
        if not self._keyboard_ready.wait(timeout=3):
            raise RuFlowWindowsError("keyboard hook did not start")
        if not self._mouse_ready.wait(timeout=3):
            raise RuFlowWindowsError("mouse hook did not start")
        if self._startup_error is not None:
            raise RuFlowWindowsError(f"could not register input hook: {self._startup_error}")

    def run(self) -> None:
        self.start()
        print(f"Ready. Press {self.display_name} to start/stop dictation. Press Ctrl+C to quit.")
        try:
            while not self._stop_requested.is_set():
                time.sleep(0.25)
        except KeyboardInterrupt:
            self.stop()

    def stop(self) -> None:
        self._stop_requested.set()
        self._action_queue.put(("stop", ()))
        if self._thread_id is not None:
            ctypes.WinDLL("user32", use_last_error=True).PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._hook_thread is not None and self._hook_thread.is_alive():
            self._hook_thread.join(timeout=2)
        if self._action_thread is not None and self._action_thread.is_alive():
            self._action_thread.join(timeout=2)

    def _dispatch_action(self, name: str, *args: Any) -> None:
        self._action_queue.put((name, args))

    def _run_actions(self) -> None:
        while not self._stop_requested.is_set():
            name, args = self._action_queue.get()
            if name == "stop":
                return
            try:
                if name == "toggle":
                    self._toggle_recording(*args)
                elif name == "paste":
                    self.controller.paste_last_result(*args)
                elif name == "cancel":
                    self.controller.cancel_recording()
            except Exception as error:
                self.controller.presenter.show_error(str(error))

    def _toggle_recording(self, anchor: tuple[int, int]) -> None:
        if self.controller.is_recording:
            self.controller.finish_recording(anchor)
        else:
            self.controller.begin_recording(anchor)

    def _register_binding_event(self, token: str, anchor: tuple[int, int]) -> None:
        should_toggle = False
        now = time.monotonic()
        with self._lock:
            if now - self._last_event_at > BINDING_SEQUENCE_TIMEOUT_SECONDS:
                self._sequence.clear()
            self._last_event_at = now
            self._sequence.append(token)
            if len(self._sequence) > len(self.binding):
                self._sequence = self._sequence[-len(self.binding) :]
            if tuple(self._sequence) == self.binding:
                self._sequence.clear()
                should_toggle = True
        if should_toggle:
            self._dispatch_action("toggle", anchor)

    def _register_keyboard_token(self, token: str, *, pressed: bool, anchor: tuple[int, int]) -> None:
        with self._lock:
            if not pressed:
                self._pressed_key_tokens.discard(token)
                return
            if token in self._pressed_key_tokens:
                return
            self._pressed_key_tokens.add(token)

        if token == "esc" and self.controller.is_recording:
            self._dispatch_action("cancel")
        else:
            self._register_binding_event(token, anchor)

    def _run_hooks(self) -> None:
        set_current_thread_priority(THREAD_PRIORITY_ABOVE_NORMAL)
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        hook_proc_type = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, WPARAM, LPARAM)
        self._mouse_hook_proc = hook_proc_type(self._handle_mouse_event)
        self._keyboard_hook_proc = hook_proc_type(self._handle_keyboard_event)
        self._user32 = user32

        kernel32.GetCurrentThreadId.argtypes = []
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD
        self._thread_id = kernel32.GetCurrentThreadId()

        user32.SetWindowsHookExW.argtypes = [ctypes.c_int, hook_proc_type, ctypes.c_void_p, wintypes.DWORD]
        user32.SetWindowsHookExW.restype = wintypes.HHOOK
        user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, WPARAM, LPARAM]
        user32.CallNextHookEx.restype = LRESULT
        user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
        user32.UnhookWindowsHookEx.restype = wintypes.BOOL
        user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        user32.GetMessageW.restype = ctypes.c_int
        user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.TranslateMessage.restype = wintypes.BOOL
        user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.DispatchMessageW.restype = LRESULT

        try:
            self._keyboard_hook = user32.SetWindowsHookExW(self.WH_KEYBOARD_LL, self._keyboard_hook_proc, None, 0)
            if not self._keyboard_hook:
                self._startup_error = ctypes.WinError(ctypes.get_last_error())
                self._keyboard_ready.set()
                self._mouse_ready.set()
                return
            self._keyboard_ready.set()

            self._mouse_hook = user32.SetWindowsHookExW(self.WH_MOUSE_LL, self._mouse_hook_proc, None, 0)
            if not self._mouse_hook:
                self._startup_error = ctypes.WinError(ctypes.get_last_error())
                self._mouse_ready.set()
                return
            self._mouse_ready.set()

            msg = wintypes.MSG()
            while not self._stop_requested.is_set() and user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            if self._keyboard_hook:
                user32.UnhookWindowsHookEx(self._keyboard_hook)
                self._keyboard_hook = None
            if self._mouse_hook:
                user32.UnhookWindowsHookEx(self._mouse_hook)
                self._mouse_hook = None
            self._user32 = None

    def _handle_keyboard_event(self, n_code: int, w_param: int, l_param: int) -> int:
        if n_code < 0:
            return self._call_next_keyboard_hook(n_code, w_param, l_param)
        if w_param not in (self.WM_KEYDOWN, self.WM_SYSKEYDOWN, self.WM_KEYUP, self.WM_SYSKEYUP):
            return self._call_next_keyboard_hook(n_code, w_param, l_param)

        event = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
        token = binding_token_from_vk_code(int(event.vkCode))
        if token is not None:
            self._register_keyboard_token(
                token,
                pressed=w_param in (self.WM_KEYDOWN, self.WM_SYSKEYDOWN),
                anchor=cursor_position(),
            )
        return self._call_next_keyboard_hook(n_code, w_param, l_param)

    def _handle_mouse_event(self, n_code: int, w_param: int, l_param: int) -> int:
        if n_code < 0:
            return self._call_next_mouse_hook(n_code, w_param, l_param)
        if w_param not in (self.WM_LBUTTONDOWN, self.WM_RBUTTONDOWN, self.WM_MBUTTONDOWN, self.WM_XBUTTONDOWN):
            return self._call_next_mouse_hook(n_code, w_param, l_param)

        event = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
        if event.flags & LLMHF_INJECTED:
            return self._call_next_mouse_hook(n_code, w_param, l_param)
        anchor = (int(event.pt.x), int(event.pt.y))

        token: str | None = None
        if w_param == self.WM_LBUTTONDOWN:
            self._handle_left_click_for_paste(anchor)
            token = "mouse:left"
        elif w_param == self.WM_RBUTTONDOWN:
            token = "mouse:right"
        elif w_param == self.WM_MBUTTONDOWN:
            token = "mouse:middle"
        elif w_param == self.WM_XBUTTONDOWN:
            button_code = (event.mouseData >> 16) & 0xFFFF
            if button_code == self.XBUTTON1:
                token = "mouse:x1"
            elif button_code == self.XBUTTON2:
                token = "mouse:x2"

        if token is not None:
            self._register_binding_event(token, anchor)
        return self._call_next_mouse_hook(n_code, w_param, l_param)

    def _handle_left_click_for_paste(self, anchor: tuple[int, int]) -> None:
        now = time.monotonic()
        should_paste = False
        with self._lock:
            if now - self._last_left_click_at <= DOUBLE_CLICK_SECONDS:
                self._last_left_click_at = 0.0
                should_paste = True
            else:
                self._last_left_click_at = now
        if should_paste:
            self._dispatch_action("paste", anchor)

    def _call_next_mouse_hook(self, n_code: int, w_param: int, l_param: int) -> int:
        user32 = self._user32 or ctypes.WinDLL("user32", use_last_error=True)
        return int(user32.CallNextHookEx(self._mouse_hook, n_code, WPARAM(w_param).value, LPARAM(l_param).value))

    def _call_next_keyboard_hook(self, n_code: int, w_param: int, l_param: int) -> int:
        user32 = self._user32 or ctypes.WinDLL("user32", use_last_error=True)
        return int(user32.CallNextHookEx(self._keyboard_hook, n_code, WPARAM(w_param).value, LPARAM(l_param).value))


def parse_mouse_button(value: str) -> str:
    normalized = (
        value.strip()
        .lower()
        .replace("button", "")
        .replace("mouse", "")
        .replace("_", "")
        .replace("-", "")
        .replace(" ", "")
    )
    aliases = {
        "x1": "x1",
        "xbutton1": "x1",
        "back": "x1",
        "4": "x1",
        "x2": "x2",
        "xbutton2": "x2",
        "forward": "x2",
        "5": "x2",
    }
    try:
        return aliases[normalized]
    except KeyError as error:
        raise ValueError("mouse button must be x1 or x2") from error


class MouseXButtonLoop:
    WH_MOUSE_LL = 14
    WM_LBUTTONDOWN = 0x0201
    WM_LBUTTONUP = 0x0202
    WM_XBUTTONDOWN = 0x020B
    WM_XBUTTONUP = 0x020C
    XBUTTON1 = 0x0001
    XBUTTON2 = 0x0002

    def __init__(
        self,
        *,
        mouse_button: str,
        controller: DictationController,
        suppress: bool,
    ) -> None:
        self.mouse_button = parse_mouse_button(mouse_button)
        self.controller = controller
        self.suppress = suppress
        self._target_button_code = self.XBUTTON1 if self.mouse_button == "x1" else self.XBUTTON2
        self._is_button_down = False
        self._is_left_button_down = False
        self._last_left_click_at = 0.0
        self._recording_active = False
        self._single_click_pending = False
        self._single_click_timer: threading.Timer | None = None
        self._lock = threading.RLock()
        self._action_queue: queue.Queue[tuple[str, tuple[Any, ...]]] = queue.Queue()
        self._action_thread: threading.Thread | None = None
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._hook: Any | None = None
        self._hook_proc: Any | None = None
        self._user32: Any | None = None
        self._ready = threading.Event()
        self._stop_requested = threading.Event()
        self._startup_error: Exception | None = None

    @property
    def display_name(self) -> str:
        return _MOUSE_BUTTON_DISPLAY[self.mouse_button]

    def start(self) -> None:
        self._register_escape_cancel()
        self._action_thread = threading.Thread(target=self._run_actions, name="RuFlowMouseActions", daemon=True)
        self._action_thread.start()
        self._thread = threading.Thread(target=self._run_hook, name="RuFlowMouseHook", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=3):
            raise RuFlowWindowsError("mouse hook did not start")
        if self._startup_error is not None:
            raise RuFlowWindowsError(f"could not register mouse hook: {self._startup_error}")

    def run(self) -> None:
        self.start()
        print(
            f"Ready. Double-click {self.display_name} to start/stop dictation. "
            "Double-click left mouse button to paste. Press Ctrl+C to quit."
        )
        try:
            while self._thread is not None and self._thread.is_alive():
                time.sleep(0.25)
        except KeyboardInterrupt:
            self.stop()

    def stop(self) -> None:
        self._stop_requested.set()
        self._cancel_pending_single_click()
        self._action_queue.put(("stop", ()))
        if self._thread_id is not None:
            ctypes.WinDLL("user32", use_last_error=True).PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2)
        if self._action_thread is not None and self._action_thread.is_alive():
            self._action_thread.join(timeout=2)

    def _register_escape_cancel(self) -> None:
        try:
            import keyboard

            keyboard.on_press_key("esc", lambda _event: self._cancel_if_recording(), suppress=False)
        except Exception:
            pass

    def _cancel_if_recording(self) -> None:
        with self._lock:
            self._is_button_down = False
            self._recording_active = False
        self._dispatch_action("cancel")

    def _dispatch_action(self, name: str, *args: Any) -> None:
        self._action_queue.put((name, args))

    def _run_actions(self) -> None:
        while not self._stop_requested.is_set():
            name, args = self._action_queue.get()
            if name == "stop":
                return

            try:
                if name == "begin":
                    self.controller.begin_recording(*args)
                elif name == "finish":
                    self.controller.finish_recording(*args)
                elif name == "toggle":
                    self._toggle_recording(*args)
                elif name == "paste":
                    self.controller.paste_last_result(*args)
                elif name == "cancel":
                    self.controller.cancel_recording()
            except Exception as error:
                self.controller.presenter.show_error(str(error))
                with self._lock:
                    self._is_button_down = False
                    self._recording_active = False

    def _toggle_recording(self, anchor: tuple[int, int]) -> None:
        if self.controller.is_recording:
            with self._lock:
                self._recording_active = False
            self.controller.finish_recording(anchor)
            return

        with self._lock:
            self._recording_active = True
        try:
            self.controller.begin_recording(anchor)
        except Exception:
            with self._lock:
                self._recording_active = False
            raise

    def _run_hook(self) -> None:
        set_current_thread_priority(THREAD_PRIORITY_ABOVE_NORMAL)
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        hook_proc_type = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, WPARAM, LPARAM)
        self._hook_proc = hook_proc_type(self._handle_event)
        self._user32 = user32

        kernel32.GetCurrentThreadId.argtypes = []
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD

        self._thread_id = kernel32.GetCurrentThreadId()

        user32.SetWindowsHookExW.argtypes = [ctypes.c_int, hook_proc_type, ctypes.c_void_p, wintypes.DWORD]
        user32.SetWindowsHookExW.restype = wintypes.HHOOK
        user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, WPARAM, LPARAM]
        user32.CallNextHookEx.restype = LRESULT
        user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
        user32.UnhookWindowsHookEx.restype = wintypes.BOOL
        user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        user32.GetMessageW.restype = ctypes.c_int
        user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.TranslateMessage.restype = wintypes.BOOL
        user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.DispatchMessageW.restype = LRESULT

        try:
            self._hook = user32.SetWindowsHookExW(self.WH_MOUSE_LL, self._hook_proc, None, 0)
            if not self._hook:
                self._startup_error = ctypes.WinError(ctypes.get_last_error())
                self._ready.set()
                return

            self._ready.set()
            msg = wintypes.MSG()
            while not self._stop_requested.is_set() and user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            if self._hook:
                user32.UnhookWindowsHookEx(self._hook)
                self._hook = None
            self._user32 = None

    def _handle_event(self, n_code: int, w_param: int, l_param: int) -> int:
        if n_code < 0:
            return self._call_next_hook(n_code, w_param, l_param)

        if w_param not in (self.WM_LBUTTONDOWN, self.WM_LBUTTONUP, self.WM_XBUTTONDOWN, self.WM_XBUTTONUP):
            return self._call_next_hook(n_code, w_param, l_param)

        event = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
        if event.flags & LLMHF_INJECTED:
            return self._call_next_hook(n_code, w_param, l_param)

        anchor = (int(event.pt.x), int(event.pt.y))
        if w_param == self.WM_LBUTTONDOWN:
            self._handle_left_button_down(anchor)
            return self._call_next_hook(n_code, w_param, l_param)
        if w_param == self.WM_LBUTTONUP:
            self._handle_left_button_up(anchor)
            return self._call_next_hook(n_code, w_param, l_param)

        button_code = (event.mouseData >> 16) & 0xFFFF
        if button_code != self._target_button_code:
            return self._call_next_hook(n_code, w_param, l_param)

        if w_param == self.WM_XBUTTONDOWN:
            self._handle_button_down(anchor)
        elif w_param == self.WM_XBUTTONUP:
            self._handle_button_up(anchor)

        if self.suppress:
            return 1
        return self._call_next_hook(n_code, w_param, l_param)

    def _call_next_hook(self, n_code: int, w_param: int, l_param: int) -> int:
        user32 = self._user32 or ctypes.WinDLL("user32", use_last_error=True)
        return int(user32.CallNextHookEx(self._hook, n_code, WPARAM(w_param).value, LPARAM(l_param).value))

    def _handle_button_down(self, anchor: tuple[int, int]) -> None:
        del anchor
        with self._lock:
            self._is_button_down = True

    def _handle_button_up(self, anchor: tuple[int, int]) -> None:
        with self._lock:
            if not self._is_button_down:
                return
            self._is_button_down = False
        self._handle_click(anchor)

    def _handle_left_button_down(self, anchor: tuple[int, int]) -> None:
        del anchor
        with self._lock:
            self._is_left_button_down = True

    def _handle_left_button_up(self, anchor: tuple[int, int]) -> None:
        should_paste = False
        now = time.monotonic()
        with self._lock:
            if not self._is_left_button_down:
                return
            self._is_left_button_down = False
            if now - self._last_left_click_at <= DOUBLE_CLICK_SECONDS:
                self._last_left_click_at = 0.0
                should_paste = True
            else:
                self._last_left_click_at = now

        if should_paste:
            self._dispatch_action("paste", anchor)

    def _handle_click(self, anchor: tuple[int, int]) -> None:
        should_toggle = False

        with self._lock:
            if self._single_click_pending:
                self._cancel_pending_single_click_locked()
                should_toggle = True
            else:
                self._single_click_pending = True
                timer = threading.Timer(DOUBLE_CLICK_SECONDS, self._flush_single_click)
                timer.daemon = True
                self._single_click_timer = timer
                timer.start()

        if should_toggle:
            self._dispatch_action("toggle", anchor)

    def _flush_single_click(self) -> None:
        should_replay = False
        with self._lock:
            if not self._single_click_pending:
                return
            self._single_click_pending = False
            self._single_click_timer = None
            should_replay = self.suppress and not self._recording_active and not self._stop_requested.is_set()

        if should_replay:
            replay_xbutton_click(self._target_button_code)

    def _cancel_pending_single_click(self) -> None:
        with self._lock:
            self._cancel_pending_single_click_locked()

    def _cancel_pending_single_click_locked(self) -> None:
        if self._single_click_timer is not None:
            self._single_click_timer.cancel()
            self._single_click_timer = None
        self._single_click_pending = False


def replay_xbutton_click(button_code: int) -> None:
    if sys.platform != "win32":
        return

    mouseeventf_xdown = 0x0080
    mouseeventf_xup = 0x0100
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.mouse_event.argtypes = [
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_size_t,
    ]
    user32.mouse_event.restype = None
    user32.mouse_event(mouseeventf_xdown, 0, 0, button_code, 0)
    time.sleep(0.01)
    user32.mouse_event(mouseeventf_xup, 0, 0, button_code, 0)


class MouseBindingCapture:
    WH_MOUSE_LL = 14
    WM_LBUTTONDOWN = 0x0201
    WM_RBUTTONDOWN = 0x0204
    WM_MBUTTONDOWN = 0x0207
    WM_XBUTTONDOWN = 0x020B
    XBUTTON1 = 0x0001
    XBUTTON2 = 0x0002

    def __init__(self, callback: Any) -> None:
        self.callback = callback
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._hook: Any | None = None
        self._hook_proc: Any | None = None
        self._user32: Any | None = None
        self._ready = threading.Event()
        self._stop_requested = threading.Event()

    def start(self) -> None:
        if sys.platform != "win32" or self._thread is not None:
            return
        self._stop_requested.clear()
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, name="RuFlowBindingCapture", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=2)

    def stop(self) -> None:
        self._stop_requested.set()
        if self._thread_id is not None:
            ctypes.WinDLL("user32", use_last_error=True).PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None
        self._thread_id = None

    def _run(self) -> None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        hook_proc_type = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, WPARAM, LPARAM)
        self._hook_proc = hook_proc_type(self._handle_event)
        self._user32 = user32

        kernel32.GetCurrentThreadId.argtypes = []
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD
        self._thread_id = kernel32.GetCurrentThreadId()

        user32.SetWindowsHookExW.argtypes = [ctypes.c_int, hook_proc_type, ctypes.c_void_p, wintypes.DWORD]
        user32.SetWindowsHookExW.restype = wintypes.HHOOK
        user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, WPARAM, LPARAM]
        user32.CallNextHookEx.restype = LRESULT
        user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
        user32.UnhookWindowsHookEx.restype = wintypes.BOOL
        user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        user32.GetMessageW.restype = ctypes.c_int
        user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.TranslateMessage.restype = wintypes.BOOL
        user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.DispatchMessageW.restype = LRESULT

        try:
            self._hook = user32.SetWindowsHookExW(self.WH_MOUSE_LL, self._hook_proc, None, 0)
            self._ready.set()
            if not self._hook:
                return
            msg = wintypes.MSG()
            while not self._stop_requested.is_set() and user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            if self._hook:
                user32.UnhookWindowsHookEx(self._hook)
                self._hook = None
            self._user32 = None

    def _handle_event(self, n_code: int, w_param: int, l_param: int) -> int:
        if n_code >= 0:
            token: str | None = None
            if w_param == self.WM_XBUTTONDOWN:
                event = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                button_code = (event.mouseData >> 16) & 0xFFFF
                if button_code == self.XBUTTON1:
                    token = "mouse:x1"
                elif button_code == self.XBUTTON2:
                    token = "mouse:x2"
            if token is not None:
                try:
                    self.callback(token)
                except Exception:
                    pass

        user32 = self._user32 or ctypes.WinDLL("user32", use_last_error=True)
        return int(user32.CallNextHookEx(self._hook, n_code, WPARAM(w_param).value, LPARAM(l_param).value))


def cursor_position() -> tuple[int, int]:
    if sys.platform != "win32":
        return (0, 0)
    point = MousePoint()
    if ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
        return (int(point.x), int(point.y))
    return (0, 0)


def set_current_thread_priority(priority: int) -> None:
    if sys.platform != "win32":
        return

    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentThread.argtypes = []
        kernel32.GetCurrentThread.restype = wintypes.HANDLE
        kernel32.SetThreadPriority.argtypes = [wintypes.HANDLE, ctypes.c_int]
        kernel32.SetThreadPriority.restype = wintypes.BOOL
        kernel32.SetThreadPriority(kernel32.GetCurrentThread(), priority)
    except Exception:
        pass


def default_recordings_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "RuFlow" / "Recordings"
    return Path.home() / "AppData" / "Roaming" / "RuFlow" / "Recordings"


def default_models_dir() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / "RuFlow" / "Models"
    return Path.home() / "AppData" / "Local" / "RuFlow" / "Models"


def app_runtime_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1] / "dist" / "windows" / "RuFlow"


def bundled_models_dir() -> Path:
    return app_runtime_dir() / "models"


def bundled_model_dir(model_name: str) -> Path:
    return bundled_models_dir() / safe_model_dir_name(model_name)


def default_logs_dir() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / "RuFlow" / "Logs"
    return Path.home() / "AppData" / "Local" / "RuFlow" / "Logs"


def default_log_path() -> Path:
    return default_logs_dir() / "ruflow.log"


def ensure_standard_streams(log_path: Path | None = None) -> Path | None:
    if sys.stdout is not None and sys.stderr is not None:
        return None

    try:
        target_path = log_path or default_log_path()
        target_path.parent.mkdir(parents=True, exist_ok=True)
        stream = target_path.open("a", encoding="utf-8", buffering=1)
        path: Path | None = target_path
    except Exception:
        stream = open(os.devnull, "w", encoding="utf-8", buffering=1)
        path = None

    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream

    return path


def safe_model_dir_name(model_name: str) -> str:
    safe = _MODEL_DIR_SAFE_RE.sub("-", model_name.strip()).strip(".-")
    return safe or DEFAULT_MODEL_NAME


def default_model_dir(model_name: str) -> Path:
    return default_models_dir() / safe_model_dir_name(model_name)


def model_dir_has_files(model_dir: Path) -> bool:
    return model_dir.is_dir() and (model_dir / "config.json").is_file()


def ensure_model_available(model_name: str, model_dir: Path | None, *, hf_insecure: bool) -> Path | None:
    if model_dir is not None:
        if not model_dir.is_dir():
            raise ASRError(f"model directory not found: {model_dir}")
        return model_dir

    bundled_dir = bundled_model_dir(model_name)
    if model_dir_has_files(bundled_dir):
        return bundled_dir

    target_dir = default_model_dir(model_name)
    if model_dir_has_files(target_dir):
        return target_dir

    try:
        ensure_standard_streams()
        print(f"RuFlow: downloading ASR model {model_name} to {target_dir}", file=sys.stderr)
        download_asr_model(model_name, target_dir, hf_insecure=hf_insecure)
    except Exception as error:
        raise ASRError(model_download_error(error)) from error

    return target_dir


def download_asr_model(model_name: str, model_dir: Path, *, hf_insecure: bool) -> None:
    model_dir.mkdir(parents=True, exist_ok=True)
    with patched_environment({"RUFLOW_HF_INSECURE": "1"} if hf_insecure else {}):
        from asr.runner import configure_huggingface

        configure_huggingface()

        from onnx_asr.loader import create_asr_resolver

        resolver = create_asr_resolver(model_name, model_dir, offline=False)
        resolver.resolve_model()


def model_download_error(error: Exception) -> str:
    message = str(error) or error.__class__.__name__
    lower_message = message.lower()
    if "certificate_verify_failed" in lower_message or "self-signed certificate" in lower_message:
        return (
            "не удалось скачать модель с Hugging Face: ошибка проверки SSL-сертификата. "
            "Проверьте настройки прокси/сертификатов или повторите запуск с --hf-insecure для локальной отладки."
        )
    if "connecterror" in lower_message or "connection" in lower_message or "timed out" in lower_message:
        return "не удалось скачать модель с Hugging Face. Проверьте интернет, VPN и настройки прокси."
    return f"не удалось скачать модель: {message}"


def should_show_model_download_status(
    *,
    no_popover: bool,
    no_model_download: bool,
    transcribe: str | None,
    requested_model_dir: Path | None,
    model_name: str,
) -> bool:
    if no_popover or no_model_download or transcribe or requested_model_dir is not None:
        return False
    return not (model_dir_has_files(bundled_model_dir(model_name)) or model_dir_has_files(default_model_dir(model_name)))


def download_model_command(model_name: str, model_dir: Path | None, *, hf_insecure: bool) -> int:
    ensure_standard_streams()
    try:
        resolved_dir = model_dir or default_model_dir(model_name)
        if not model_dir_has_files(resolved_dir):
            print(f"RuFlow: downloading ASR model {model_name} to {resolved_dir}", file=sys.stderr)
            download_asr_model(model_name, resolved_dir, hf_insecure=hf_insecure)
    except ASRError as error:
        print(f"RuFlow error: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"RuFlow error: {model_download_error(error)}", file=sys.stderr)
        return 1
    print(f"RuFlow: ASR model is ready at {resolved_dir}")
    return 0


def ensure_model_available_with_status(
    model_name: str,
    model_dir: Path | None,
    *,
    hf_insecure: bool,
) -> Path | None:
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception:
        return ensure_model_available(model_name, model_dir, hf_insecure=hf_insecure)

    result_queue: queue.Queue[tuple[bool, Path | None | Exception]] = queue.Queue(maxsize=1)

    def worker() -> None:
        try:
            result_queue.put((True, ensure_model_available(model_name, model_dir, hf_insecure=hf_insecure)))
        except Exception as error:
            result_queue.put((False, error))

    root = tk.Tk()
    root.withdraw()
    root.title("RuFlow")
    root.resizable(False, False)
    root.attributes("-topmost", True)
    try:
        root.attributes("-toolwindow", True)
    except tk.TclError:
        pass

    frame = ttk.Frame(root, padding=(18, 14, 18, 16))
    frame.grid(row=0, column=0, sticky="nsew")
    title = ttk.Label(frame, text="Скачиваю модель", font=("Segoe UI", 10))
    title.grid(row=0, column=0, sticky="w")
    detail = ttk.Label(
        frame,
        text="Первый запуск RuFlow. Распознавание будет работать локально после загрузки.",
        font=("Segoe UI", 8),
        wraplength=300,
    )
    detail.grid(row=1, column=0, sticky="w", pady=(5, 10))
    progress = ttk.Progressbar(frame, mode="indeterminate", length=300)
    progress.grid(row=2, column=0, sticky="ew")
    progress.start(12)

    root.update_idletasks()
    width = max(340, root.winfo_width())
    height = max(92, root.winfo_height())
    cursor_x, cursor_y = cursor_position()
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    left = min(max(16, cursor_x + 18), max(16, screen_width - width - 16))
    top = min(max(16, cursor_y + 18), max(16, screen_height - height - 80))
    root.geometry(f"{width}x{height}+{left}+{top}")
    root.deiconify()
    root.lift()

    outcome: dict[str, Path | None | Exception] = {}

    def poll() -> None:
        try:
            ok, value = result_queue.get_nowait()
        except queue.Empty:
            root.after(80, poll)
            return

        outcome["value"] = value
        if ok:
            root.destroy()
            return

        progress.stop()
        progress.grid_remove()
        title.configure(text="Не удалось скачать модель")
        detail.configure(text=_short_message(str(value), 220))
        close_button = ttk.Button(frame, text="Закрыть", command=root.destroy)
        close_button.grid(row=2, column=0, sticky="e", pady=(2, 0))
        root.after(10_000, root.destroy)

    threading.Thread(target=worker, name="RuFlowModelDownload", daemon=True).start()
    root.after(80, poll)
    root.mainloop()

    value = outcome.get("value")
    if isinstance(value, Exception):
        raise value
    return value if isinstance(value, Path) else None


def list_audio_devices() -> None:
    try:
        import sounddevice as sd
    except ImportError as error:
        raise RuFlowWindowsError("sounddevice is not installed; run scripts\\setup_windows.bat") from error

    devices = sd.query_devices()
    print(f"default device: {sd.default.device}")
    for index, device in enumerate(devices):
        input_channels = int(device.get("max_input_channels") or 0)
        output_channels = int(device.get("max_output_channels") or 0)
        marker = ""
        if index == sd.default.device[0]:
            marker = " [default input]"
        print(f"{index}: {device['name']} in={input_channels} out={output_channels}{marker}")


def paste_text(text: str, *, restore_delay_seconds: float = 0.2) -> None:
    if sys.platform != "win32":
        raise ClipboardError("Windows clipboard paste is available only on Windows")

    snapshot = get_clipboard_text()
    set_clipboard_text(text)
    time.sleep(0.03)
    send_ctrl_v()
    time.sleep(restore_delay_seconds)
    if snapshot is not None:
        set_clipboard_text(snapshot)


def get_clipboard_text() -> str | None:
    user32, kernel32 = _win32_clipboard_api()
    if not user32.IsClipboardFormatAvailable(13):
        return None

    _open_clipboard(user32)
    try:
        handle = user32.GetClipboardData(13)
        if not handle:
            return ""
        locked = kernel32.GlobalLock(handle)
        if not locked:
            return ""
        try:
            return ctypes.wstring_at(locked)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def set_clipboard_text(text: str) -> None:
    user32, kernel32 = _win32_clipboard_api()
    data = ctypes.create_unicode_buffer(text)
    size = ctypes.sizeof(data)
    hglobal = kernel32.GlobalAlloc(0x0002, size)
    if not hglobal:
        raise ClipboardError("GlobalAlloc failed")

    locked = kernel32.GlobalLock(hglobal)
    if not locked:
        kernel32.GlobalFree(hglobal)
        raise ClipboardError("GlobalLock failed")

    ctypes.memmove(locked, data, size)
    kernel32.GlobalUnlock(hglobal)

    _open_clipboard(user32)
    try:
        if not user32.EmptyClipboard():
            raise ClipboardError("EmptyClipboard failed")
        if not user32.SetClipboardData(13, hglobal):
            kernel32.GlobalFree(hglobal)
            raise ClipboardError("SetClipboardData failed")
        hglobal = None
    finally:
        user32.CloseClipboard()

    if hglobal is not None:
        kernel32.GlobalFree(hglobal)


def send_ctrl_v() -> None:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    vk_control = 0x11
    vk_v = 0x56
    keyeventf_keyup = 0x0002
    user32.keybd_event(vk_control, 0, 0, 0)
    user32.keybd_event(vk_v, 0, 0, 0)
    user32.keybd_event(vk_v, 0, keyeventf_keyup, 0)
    user32.keybd_event(vk_control, 0, keyeventf_keyup, 0)


def _win32_clipboard_api() -> tuple[Any, Any]:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    hglobal = getattr(wintypes, "HGLOBAL", wintypes.HANDLE)

    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.argtypes = []
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
    user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.SetClipboardData.argtypes = [wintypes.UINT, hglobal]
    user32.SetClipboardData.restype = wintypes.HANDLE

    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = hglobal
    kernel32.GlobalLock.argtypes = [hglobal]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [hglobal]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalFree.argtypes = [hglobal]
    kernel32.GlobalFree.restype = hglobal

    return user32, kernel32


def _open_clipboard(user32: Any, *, retries: int = 20, delay_seconds: float = 0.025) -> None:
    for _ in range(retries):
        if user32.OpenClipboard(None):
            return
        time.sleep(delay_seconds)
    raise ClipboardError("OpenClipboard failed")


def _short_message(message: str, limit: int = 240) -> str:
    text = message.strip() or "unknown error"
    if len(text) <= limit:
        return text
    return text[:limit].rstrip()


def settings_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--settings"]
    return [sys.executable, str(Path(__file__).resolve()), "--settings"]


def run_control_window(config_path: Path | None = None, *, allow_launch: bool) -> ControlWindowResult:
    try:
        import tkinter as tk
    except Exception as error:
        print(f"RuFlow error: settings UI is unavailable: {error}", file=sys.stderr)
        return ControlWindowResult("error", load_user_config(config_path))

    config = load_user_config(config_path)
    result = ControlWindowResult("quit", config)
    colors = {
        "bg": "#f8fafc",
        "card": "#ffffff",
        "card_muted": "#f1f5f9",
        "card_soft": "#f8fafc",
        "chip": "#eef2f7",
        "chip_hover": "#e2e8f0",
        "text": "#0f172a",
        "muted": "#64748b",
        "border": "#e2e8f0",
        "border_strong": "#cbd5e1",
        "primary": "#18181b",
        "primary_hover": "#27272a",
        "primary_text": "#ffffff",
        "focus": "#2563eb",
        "focus_soft": "#eff6ff",
        "danger": "#b91c1c",
        "success": "#047857",
    }
    spacing = {
        "shell": 24,
        "card_x": 24,
        "card_y": 22,
        "field_gap": 8,
        "section_gap": 18,
        "button_gap": 8,
    }

    def rounded_rect(canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int, radius: int, **kwargs: Any) -> None:
        points = [
            x1 + radius,
            y1,
            x2 - radius,
            y1,
            x2,
            y1,
            x2,
            y1 + radius,
            x2,
            y2 - radius,
            x2,
            y2,
            x2 - radius,
            y2,
            x1 + radius,
            y2,
            x1,
            y2,
            x1,
            y2 - radius,
            x1,
            y1 + radius,
            x1,
            y1,
        ]
        canvas.create_polygon(points, smooth=True, **kwargs)

    root = tk.Tk()
    root.title("RuFlow")
    root.resizable(False, False)
    root.configure(bg=colors["bg"])

    binding_tokens: list[str] = list(parse_binding_sequence(config["binding"]))
    status_var = tk.StringVar(
        value="Нажмите на поле и задайте бинд любыми клавишами или кнопками мыши."
        if allow_launch
        else "Измените бинд и нажмите «Сохранить»."
    )
    capture_active = tk.BooleanVar(value=False)
    captured_tokens: list[str] = []
    previous_tokens: list[str] = list(binding_tokens)
    mouse_capture: MouseBindingCapture | None = None
    capture_mode = "replace"
    last_added_token: str | None = None
    last_added_at = 0.0

    shell = tk.Frame(root, bg=colors["bg"], padx=spacing["shell"], pady=spacing["shell"])
    shell.grid(row=0, column=0, sticky="nsew")
    shell.columnconfigure(0, weight=1)

    header = tk.Frame(shell, bg=colors["bg"])
    header.grid(row=0, column=0, sticky="ew")
    header.columnconfigure(0, weight=1)
    tk.Label(
        header,
        text="RuFlow",
        bg=colors["bg"],
        fg=colors["text"],
        font=("Segoe UI", 21, "bold"),
    ).grid(row=0, column=0)
    tk.Label(
        header,
        text="Локальный голосовой ввод",
        bg=colors["bg"],
        fg=colors["muted"],
        font=("Segoe UI", 9),
    ).grid(row=1, column=0, pady=(3, 0))

    card_wrap = tk.Canvas(shell, width=532, height=410, bg=colors["bg"], highlightthickness=0, bd=0)
    card_wrap.grid(row=1, column=0, sticky="ew", pady=(spacing["section_gap"], 0))
    rounded_rect(card_wrap, 1, 1, 531, 409, 18, fill=colors["card"], outline=colors["border"], width=1)
    card = tk.Frame(card_wrap, bg=colors["card"], padx=spacing["card_x"], pady=spacing["card_y"])
    card_wrap.create_window(266, 205, window=card, width=498, height=376)
    card.columnconfigure(0, weight=1)

    def label(parent: tk.Misc, text: str, *, muted: bool = False, bg: str | None = None) -> tk.Label:
        return tk.Label(
            parent,
            text=text,
            bg=bg or colors["card"],
            fg=colors["muted"] if muted else colors["text"],
            font=("Segoe UI", 9, "normal" if muted else "bold"),
            anchor="w",
        )

    def set_status(text: str, *, error: bool = False, ok: bool = False) -> None:
        status_var.set(text)
        status_label.configure(fg=colors["danger"] if error else colors["success"] if ok else colors["muted"])

    def make_button(parent: tk.Misc, text: str, command: Any, *, primary: bool = False) -> tk.Button:
        bg = colors["primary"] if primary else colors["card"]
        fg = colors["primary_text"] if primary else colors["text"]
        border = colors["primary"] if primary else colors["border_strong"]
        button = tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=colors["primary_hover"] if primary else colors["card_muted"],
            activeforeground=fg,
            font=("Segoe UI", 10, "bold" if primary else "normal"),
            padx=16,
            pady=8,
            cursor="hand2",
            highlightbackground=border,
            highlightthickness=1,
            bd=0,
            relief="flat",
            takefocus=True,
        )

        def on_enter(_event: Any) -> None:
            button.configure(bg=colors["primary_hover"] if primary else colors["card_muted"])

        def on_leave(_event: Any) -> None:
            button.configure(bg=bg)

        button.bind("<Enter>", on_enter)
        button.bind("<Leave>", on_leave)
        button.bind("<FocusIn>", lambda _event: button.configure(highlightbackground=colors["focus"]))
        button.bind("<FocusOut>", lambda _event: button.configure(highlightbackground=border))
        button.bind("<Return>", lambda _event: (command(), "break")[1])
        button.bind("<space>", lambda _event: (command(), "break")[1])
        return button

    wave = tk.Canvas(card, width=224, height=42, bg=colors["card"], highlightthickness=0, bd=0)
    wave.grid(row=0, column=0, pady=(2, 18))

    binding_canvas_width = 460
    binding_canvas_height = 132
    binding_canvas = tk.Canvas(
        card,
        width=binding_canvas_width,
        height=binding_canvas_height,
        bg=colors["card"],
        highlightthickness=0,
        bd=0,
        cursor="hand2",
        takefocus=True,
    )
    binding_canvas.grid(row=1, column=0, sticky="ew")
    rounded_rect(
        binding_canvas,
        1,
        1,
        binding_canvas_width - 1,
        binding_canvas_height - 1,
        16,
        fill=colors["card_soft"],
        outline=colors["border_strong"],
        width=1,
    )
    binding_surface = tk.Frame(binding_canvas, bg=colors["card_soft"], padx=16, pady=14, cursor="hand2", takefocus=True)
    binding_canvas.create_window(
        binding_canvas_width // 2,
        binding_canvas_height // 2,
        window=binding_surface,
        width=binding_canvas_width - 18,
        height=binding_canvas_height - 18,
    )
    binding_surface.columnconfigure(0, weight=1)

    chips_frame = tk.Frame(binding_surface, bg=colors["card_soft"])
    chips_frame.grid(row=0, column=0, sticky="ew")
    chips_frame.columnconfigure(0, weight=1)

    chip_actions = tk.Frame(binding_surface, bg=colors["card_soft"])
    chip_actions.grid(row=1, column=0, pady=(10, 0))

    def make_link_button(parent: tk.Misc, text: str, command: Any) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=colors["card_soft"],
            fg=colors["muted"],
            activebackground=colors["card_soft"],
            activeforeground=colors["text"],
            font=("Segoe UI", 8, "bold"),
            padx=9,
            pady=3,
            cursor="hand2",
            bd=0,
            relief="flat",
            takefocus=True,
        )

    hint_label = tk.Label(
        card,
        text="Повторы считаются отдельно: Enter + Enter + Enter может быть отдельным биндом.",
        bg=colors["card"],
        fg=colors["muted"],
        font=("Segoe UI", 9),
        anchor="center",
        justify="center",
        wraplength=390,
    )
    hint_label.grid(row=2, column=0, sticky="ew", pady=(10, spacing["section_gap"]))

    def current_edit_tokens() -> list[str]:
        return captured_tokens if capture_active.get() else binding_tokens

    def remove_binding_token(index: int) -> None:
        nonlocal binding_tokens, captured_tokens
        tokens = list(current_edit_tokens())
        if 0 <= index < len(tokens):
            del tokens[index]
        if capture_active.get():
            captured_tokens = tokens
        else:
            binding_tokens = tokens
        redraw_chips(tokens)
        set_status("Удалено. Не забудьте сохранить изменения.", ok=True)

    def clear_binding_tokens() -> None:
        nonlocal binding_tokens, captured_tokens
        if capture_active.get():
            captured_tokens = []
        else:
            binding_tokens = []
        redraw_chips([])
        set_status("Бинд очищен. Нажмите по области и задайте новый.", error=True)

    def redraw_chips(tokens: list[str]) -> None:
        for child in chips_frame.winfo_children():
            child.destroy()
        for child in chip_actions.winfo_children():
            child.destroy()

        if not tokens and capture_active.get():
            tk.Label(
                chips_frame,
                text="Слушаю ввод...",
                bg=colors["card_soft"],
                fg=colors["focus"],
                font=("Segoe UI", 10, "bold"),
                wraplength=380,
                justify="center",
            ).grid(row=0, column=0, sticky="ew")
            make_link_button(chip_actions, "Отменить", lambda: stop_binding_capture(restore=True)).grid(row=0, column=0)
            return

        if not tokens:
            tk.Label(
                chips_frame,
                text="Бинд не задан",
                bg=colors["card_soft"],
                fg=colors["muted"],
                font=("Segoe UI", 10, "bold"),
                justify="center",
            ).grid(row=0, column=0, sticky="ew")
            make_link_button(chip_actions, "Задать бинд", lambda: start_binding_capture(mode="replace")).grid(row=0, column=0)
            return

        rows: list[tk.Frame] = []
        row_frame = tk.Frame(chips_frame, bg=colors["card_soft"])
        row_frame.grid(row=0, column=0)
        rows.append(row_frame)
        row_width = 0
        max_row_width = 390
        for index, token in enumerate(tokens):
            token_text = format_binding_token(token)
            token_width = max(56, 16 + len(token_text) * 8 + 24)
            separator_width = 18 if index > 0 else 0
            if row_width and row_width + separator_width + token_width > max_row_width:
                row_frame = tk.Frame(chips_frame, bg=colors["card_soft"])
                row_frame.grid(row=len(rows), column=0, pady=(4, 0))
                rows.append(row_frame)
                row_width = 0
            if index > 0:
                tk.Label(
                    row_frame,
                    text="+",
                    bg=colors["card_soft"],
                    fg=colors["muted"],
                    font=("Segoe UI", 9, "bold"),
                ).pack(side="left", padx=4)
                row_width += separator_width
            chip = tk.Frame(
                row_frame,
                bg=colors["chip"],
                padx=9,
                pady=4,
                cursor="hand2",
            )
            chip.pack(side="left", padx=2)
            tk.Label(
                chip,
                text=token_text,
                bg=colors["chip"],
                fg=colors["text"],
                font=("Segoe UI", 9, "bold"),
                cursor="hand2",
            ).pack(side="left")
            tk.Button(
                chip,
                text="×",
                command=lambda token_index=index: remove_binding_token(token_index),
                bg=colors["chip"],
                fg=colors["muted"],
                activebackground=colors["chip_hover"],
                activeforeground=colors["text"],
                font=("Segoe UI", 9, "bold"),
                padx=3,
                pady=0,
                cursor="hand2",
                bd=0,
                relief="flat",
                takefocus=False,
            ).pack(side="left", padx=(6, 0))
            row_width += token_width

        if capture_active.get():
            make_link_button(chip_actions, "Готово", stop_binding_capture).grid(row=0, column=0, padx=(0, 8))
            make_link_button(chip_actions, "Отменить", lambda: stop_binding_capture(restore=True)).grid(row=0, column=1)
        else:
            make_link_button(chip_actions, "Изменить", lambda: start_binding_capture(mode="replace")).grid(row=0, column=0, padx=(0, 8))
            make_link_button(chip_actions, "Добавить", lambda: start_binding_capture(mode="append")).grid(row=0, column=1, padx=(0, 8))
            make_link_button(chip_actions, "Очистить", clear_binding_tokens).grid(row=0, column=2)

    def draw_wave(frame: int = 0) -> None:
        wave.delete("all")
        center_y = 21
        for index in range(22):
            x = 8 + index * 10
            phase = (frame + index) / 3.0
            height = 8 + int((math.sin(phase) + 1) * 10)
            color = colors["text"] if 5 <= index <= 16 else colors["border_strong"]
            wave.create_line(x, center_y - height // 2, x, center_y + height // 2, fill=color, width=2)
        root.after(90, lambda: draw_wave(frame + 1))

    def update_binding_surface(active: bool) -> None:
        binding_canvas.delete("all")
        rounded_rect(
            binding_canvas,
            1,
            1,
            binding_canvas_width - 1,
            binding_canvas_height - 1,
            16,
            fill=colors["focus_soft"] if active else colors["card_soft"],
            outline=colors["focus"] if active else colors["border_strong"],
            width=1,
        )
        binding_canvas.create_window(
            binding_canvas_width // 2,
            binding_canvas_height // 2,
            window=binding_surface,
            width=binding_canvas_width - 18,
            height=binding_canvas_height - 18,
        )
        binding_surface.configure(bg=colors["focus_soft"] if active else colors["card_soft"])
        chips_frame.configure(bg=colors["focus_soft"] if active else colors["card_soft"])
        redraw_chips(captured_tokens if active else binding_tokens)

    def start_binding_capture(_event: Any | None = None, *, mode: str = "replace") -> str:
        nonlocal previous_tokens, captured_tokens, mouse_capture, capture_mode, last_added_token, last_added_at
        if capture_active.get():
            return "break"
        capture_mode = "append" if mode == "append" else "replace"
        previous_tokens = list(binding_tokens)
        captured_tokens = list(binding_tokens) if capture_mode == "append" else []
        last_added_token = None
        last_added_at = 0.0
        capture_active.set(True)
        update_binding_surface(True)
        binding_surface.focus_set()
        set_status(
            "Добавляйте нажатия к текущему бинду."
            if capture_mode == "append"
            else "Нажимайте новую последовательность. Enter можно нажать хоть пять раз.",
            ok=True,
        )
        if mouse_capture is None:
            mouse_capture = MouseBindingCapture(lambda token: root.after(0, lambda: add_binding_token(token) if capture_active.get() else None))
        mouse_capture.start()
        return "break"

    def stop_binding_capture(*, restore: bool = False) -> None:
        nonlocal binding_tokens, captured_tokens, mouse_capture
        if mouse_capture is not None:
            mouse_capture.stop()
        if restore:
            captured_tokens = []
            binding_tokens = list(previous_tokens)
        elif captured_tokens:
            binding_tokens = list(captured_tokens)
        capture_active.set(False)
        captured_tokens = []
        update_binding_surface(False)

    def add_binding_token(token: str) -> None:
        nonlocal captured_tokens, last_added_token, last_added_at
        now = time.monotonic()
        if token.startswith("mouse:") and token == last_added_token and now - last_added_at < 0.12:
            return
        if len(captured_tokens) >= MAX_BINDING_EVENTS:
            set_status(f"Максимум {MAX_BINDING_EVENTS} нажатий в одном бинде.", error=True)
            return
        last_added_token = token
        last_added_at = now
        captured_tokens.append(token)
        redraw_chips(captured_tokens)
        set_status(
            "Бинд обновлён. Нажмите «Сохранить и запустить»."
            if allow_launch
            else "Бинд обновлён. Нажмите «Сохранить».",
            ok=True,
        )

    def handle_binding_key(event: Any) -> str:
        if not capture_active.get():
            return ""
        token = binding_token_from_tk_key(event.keysym, getattr(event, "char", ""))
        if token is not None:
            add_binding_token(token)
        return "break"

    def handle_binding_mouse(token: str) -> str:
        if not capture_active.get():
            start_binding_capture()
        add_binding_token(token)
        return "break"

    binding_surface.bind("<Button-1>", lambda _event: start_binding_capture(mode="replace") if not capture_active.get() else "break")
    binding_surface.bind("<Button-2>", lambda _event: handle_binding_mouse("mouse:middle"))
    binding_surface.bind("<Button-3>", lambda _event: handle_binding_mouse("mouse:right"))
    binding_surface.bind("<FocusOut>", lambda _event: None)
    binding_canvas.bind("<Button-1>", lambda _event: start_binding_capture(mode="replace") if not capture_active.get() else "break")
    binding_canvas.bind("<FocusOut>", lambda _event: None)
    root.bind_all("<KeyPress>", handle_binding_key)
    root.bind("<Escape>", lambda _event: (stop_binding_capture(restore=True), "break")[1] if capture_active.get() else "")

    status_label = tk.Label(
        card,
        textvariable=status_var,
        bg=colors["card"],
        fg=colors["muted"],
        font=("Segoe UI", 9),
        anchor="w",
        justify="left",
        wraplength=492,
    )
    status_label.grid(row=3, column=0, sticky="ew", pady=(0, spacing["section_gap"]))

    buttons = tk.Frame(card, bg=colors["card"])
    buttons.grid(row=4, column=0, sticky="ew")
    buttons.columnconfigure(0, weight=1)

    def collect_config() -> dict[str, Any] | None:
        if capture_active.get():
            stop_binding_capture()
        try:
            binding = binding_sequence_to_config(binding_tokens)
        except ValueError as error:
            set_status(str(error), error=True)
            return None
        return {"binding": binding}

    def save(action: str) -> None:
        nonlocal result
        next_config = collect_config()
        if next_config is None:
            return
        save_user_config(next_config, config_path)
        result = ControlWindowResult(action, sanitize_user_config(next_config))
        root.destroy()

    def close() -> None:
        nonlocal result
        stop_binding_capture(restore=True)
        result = ControlWindowResult("quit", load_user_config(config_path))
        root.destroy()

    make_button(buttons, "Закрыть", close).grid(row=0, column=0, sticky="w")
    if allow_launch:
        make_button(buttons, "Только сохранить", lambda: save("save")).grid(
            row=0,
            column=1,
            sticky="e",
            padx=(0, spacing["button_gap"]),
        )
        make_button(buttons, "Сохранить и запустить", lambda: save("launch"), primary=True).grid(row=0, column=2, sticky="e")
    else:
        make_button(buttons, "Сохранить", lambda: save("save"), primary=True).grid(row=0, column=2, sticky="e")

    redraw_chips(binding_tokens)
    draw_wave()

    root.update_idletasks()
    width = max(570, root.winfo_width())
    height = max(540 if allow_launch else 510, root.winfo_height())
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    left = int((screen_width - width) / 2)
    top = int((screen_height - height) / 2)
    root.geometry(f"{width}x{height}+{max(0, left)}+{max(0, top)}")
    root.minsize(width, height)
    root.maxsize(width, height)
    root.mainloop()
    return result


def run_settings_window(config_path: Path | None = None) -> int:
    result = run_control_window(config_path, allow_launch=False)
    return 1 if result.action == "error" else 0


def should_show_control_window(
    args: argparse.Namespace,
    raw_args: list[str],
    config_path: Path | None = None,
) -> bool:
    if raw_args:
        return False
    if args.settings or args.first_run or args.list_devices or args.transcribe or args.background or args.download_model:
        return False
    return not (config_path or default_config_path()).is_file()


def build_arg_parser() -> argparse.ArgumentParser:
    repo_root = Path(__file__).resolve().parents[1]
    user_config = load_user_config()
    parser = argparse.ArgumentParser(description="RuFlow Windows dictation adapter")
    default_asr_mode = "in-process" if getattr(sys, "frozen", False) else "subprocess"
    parser.add_argument("--settings", action="store_true", help="open the settings window and exit")
    parser.add_argument("--first-run", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--background", action="store_true", help="start dictation in the background without the control window")
    parser.add_argument("--download-model", action="store_true", help="download the default ASR model and exit")
    parser.add_argument(
        "--trigger",
        choices=("mouse", "hotkey"),
        default=str(user_config.get("trigger", DEFAULT_TRIGGER)),
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--mouse-button", default=str(user_config.get("mouse_button", DEFAULT_MOUSE_BUTTON)), help=argparse.SUPPRESS)
    parser.add_argument(
        "--pass-through-mouse-button",
        action=argparse.BooleanOptionalAction,
        default=bool(user_config.get("pass_through_mouse_button", DEFAULT_PASS_THROUGH_MOUSE_BUTTON)),
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--hotkey", default=str(user_config.get("hotkey", DEFAULT_HOTKEY)), help=argparse.SUPPRESS)
    parser.add_argument(
        "--binding",
        default="+".join(str(part) for part in user_config["binding"]),
        help="dictation trigger sequence, for example enter+enter or mouse:x1+mouse:x1",
    )
    parser.add_argument("--python", default=sys.executable, help="Python executable used to run asr/runner.py")
    parser.add_argument("--runner", default=str(repo_root / "asr" / "runner.py"), help="path to asr/runner.py")
    parser.add_argument("--recordings-dir", default=str(default_recordings_dir()), help="directory for temporary WAV files")
    parser.add_argument(
        "--model",
        default=os.environ.get("RUFLOW_ASR_MODEL", DEFAULT_MODEL_NAME),
        help="onnx-asr model name, for example gigaam-v3-e2e-rnnt",
    )
    parser.add_argument("--model-dir", default=os.environ.get("RUFLOW_GIGAAM_MODEL_DIR"), help="local ASR model directory")
    parser.add_argument(
        "--no-model-download",
        action="store_true",
        help="do not download the default ASR model on first launch",
    )
    parser.add_argument("--hf-insecure", action="store_true", help="set RUFLOW_HF_INSECURE=1 for local corporate SSL workaround")
    parser.add_argument("--keep-recordings", action="store_true", help="do not delete WAV files after recognition")
    parser.add_argument("--auto-paste", action="store_true", help="paste recognized text into the active window automatically")
    parser.add_argument("--no-clipboard", action="store_true", help="do not copy recognized text to the clipboard")
    parser.add_argument("--no-popover", action="store_true", help="disable the cursor popover and print status to the console")
    parser.add_argument("--no-paste", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--list-devices", action="store_true", help="print audio devices and exit")
    parser.add_argument("--transcribe", help="transcribe one WAV file and exit without registering a hotkey")
    parser.add_argument(
        "--max-duration",
        type=float,
        default=DEFAULT_MAX_DURATION_SECONDS,
        help="maximum recording duration in seconds; 0 disables the limit",
    )
    parser.add_argument("--asr-timeout", type=float, default=0.0, help="ASR timeout in seconds; 0 disables the timeout")
    parser.add_argument(
        "--asr-mode",
        choices=("subprocess", "in-process"),
        default=default_asr_mode,
        help="ASR execution mode; packaged builds use in-process by default",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    ensure_standard_streams()

    if sys.platform != "win32":
        print("RuFlow Windows adapter must be run on Windows.", file=sys.stderr)
        return 2

    raw_args = list(sys.argv[1:] if argv is None else argv)
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.settings:
        return run_settings_window()

    if args.first_run or should_show_control_window(args, raw_args):
        control_result = run_control_window(None, allow_launch=True)
        if control_result.action == "error":
            return 1
        if control_result.action != "launch":
            return 0
        args.binding = "+".join(str(part) for part in control_result.config["binding"])

    if args.list_devices:
        try:
            list_audio_devices()
        except RuFlowWindowsError as error:
            print(f"RuFlow error: {error}", file=sys.stderr)
            return 1
        return 0

    model_name = str(args.model).strip() or DEFAULT_MODEL_NAME
    requested_model_dir = Path(args.model_dir).expanduser() if args.model_dir else None
    if args.download_model:
        return download_model_command(model_name, requested_model_dir, hf_insecure=args.hf_insecure)
    try:
        if args.no_model_download:
            model_dir = requested_model_dir
        elif should_show_model_download_status(
            no_popover=args.no_popover,
            no_model_download=args.no_model_download,
            transcribe=args.transcribe,
            requested_model_dir=requested_model_dir,
            model_name=model_name,
        ):
            model_dir = ensure_model_available_with_status(
                model_name,
                requested_model_dir,
                hf_insecure=args.hf_insecure,
            )
        else:
            model_dir = ensure_model_available(model_name, requested_model_dir, hf_insecure=args.hf_insecure)
    except ASRError as error:
        print(f"RuFlow error: {error}", file=sys.stderr)
        return 1

    if args.transcribe:
        try:
            result = run_asr(
                mode=args.asr_mode,
                model_name=model_name,
                python_executable=Path(args.python).expanduser(),
                runner_path=Path(args.runner).expanduser(),
                wav_path=Path(args.transcribe).expanduser(),
                model_dir=model_dir,
                hf_insecure=args.hf_insecure,
                timeout_seconds=args.asr_timeout if args.asr_timeout > 0 else None,
            )
        except ASRError as error:
            print(f"RuFlow error: {error}", file=sys.stderr)
            return 1
        print(result.text)
        return 0

    try:
        binding = parse_binding_sequence(args.binding)
    except ValueError as error:
        parser.error(str(error))

    presenter: DictationPresenter = ConsolePresenter() if args.no_popover else PopoverPresenter()
    trigger_name = " + ".join(format_binding_sequence(binding))

    controller = DictationController(
        trigger_name=trigger_name,
        recorder=WindowsAudioRecorder(
            Path(args.recordings_dir).expanduser(),
            level_callback=presenter.show_audio_level,
        ),
        presenter=presenter,
        python_executable=Path(args.python).expanduser(),
        runner_path=Path(args.runner).expanduser(),
        model_name=model_name,
        model_dir=model_dir,
        hf_insecure=args.hf_insecure,
        keep_recordings=args.keep_recordings,
        auto_paste=args.auto_paste and not args.no_paste,
        copy_to_clipboard=(not args.no_clipboard) or args.auto_paste,
        max_duration_seconds=args.max_duration,
        asr_timeout_seconds=args.asr_timeout if args.asr_timeout > 0 else None,
        asr_mode=args.asr_mode,
    )

    loop = BindingSequenceLoop(binding=binding, controller=controller)

    try:
        if isinstance(presenter, PopoverPresenter):
            loop.start()
            print(f"Ready. Press {trigger_name} to start/stop dictation. Press Ctrl+C to quit.")
            presenter.run()
        else:
            loop.run()
    except KeyboardInterrupt:
        pass
    except RuFlowWindowsError as error:
        print(f"RuFlow error: {error}", file=sys.stderr)
        return 1
    finally:
        loop.stop()
        presenter.stop()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
