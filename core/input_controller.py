#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Input Controller — Simulate mouse and keyboard input.

Uses pynput for modern, reliable input control.
"""

import time
from typing import Optional, Tuple


class InputController:
    """Mouse and keyboard simulation with smooth animation."""

    def __init__(self, mouse_move_duration: float = 0.2,
                 typing_interval: float = 0.01,
                 click_delay: float = 0.1):
        self._mouse_move_duration = mouse_move_duration
        self._typing_interval = typing_interval
        self._click_delay = click_delay

        from pynput.mouse import Controller as MouseController
        from pynput.keyboard import Controller as KeyboardController
        self._mouse = MouseController()
        self._keyboard = KeyboardController()

    # ─── Mouse ───────────────────────────────────────────────

    def get_mouse_position(self) -> Tuple[int, int]:
        return self._mouse.position

    def move_mouse(self, x: int, y: int, duration: Optional[float] = None):
        """Move mouse to absolute position with smooth animation."""
        duration = duration if duration is not None else self._mouse_move_duration
        if duration <= 0:
            self._mouse.position = (x, y)
            return

        start_x, start_y = self._mouse.position
        steps = max(int(duration / 0.016), 5)  # ~60fps

        for i in range(1, steps + 1):
            t = i / steps
            # Ease-in-out interpolation
            t = t * t * (3 - 2 * t)
            cx = int(start_x + (x - start_x) * t)
            cy = int(start_y + (y - start_y) * t)
            self._mouse.position = (cx, cy)
            time.sleep(duration / steps)

    def move_mouse_relative(self, dx: int, dy: int, duration: Optional[float] = None):
        """Move mouse relative to current position."""
        cx, cy = self._mouse.position
        self.move_mouse(cx + dx, cy + dy, duration)

    def click(self, x: Optional[int] = None, y: Optional[int] = None,
              button: str = "left", count: int = 1):
        """Click at position (or current position if not specified)."""
        from pynput.mouse import Button

        if x is not None and y is not None:
            self.move_mouse(x, y, duration=0.05)
            time.sleep(self._click_delay)

        btn = Button.left if button == "left" else (
            Button.right if button == "right" else Button.middle
        )
        self._mouse.click(btn, count)

    def double_click(self, x: Optional[int] = None, y: Optional[int] = None):
        self.click(x, y, button="left", count=2)

    def right_click(self, x: Optional[int] = None, y: Optional[int] = None):
        self.click(x, y, button="right")

    def scroll(self, clicks: int, direction: str = "down"):
        """Scroll the mouse wheel. Positive = up, negative = down."""
        amount = -abs(clicks) if direction == "down" else abs(clicks)
        self._mouse.scroll(0, amount)

    def drag(self, start_x: int, start_y: int, end_x: int, end_y: int,
             duration: float = 0.3):
        """Drag from one position to another."""
        from pynput.mouse import Button

        self.move_mouse(start_x, start_y, duration=0.1)
        time.sleep(0.05)
        self._mouse.press(Button.left)
        time.sleep(0.05)
        self.move_mouse(end_x, end_y, duration=duration)
        time.sleep(0.05)
        self._mouse.release(Button.left)

    # ─── Keyboard ────────────────────────────────────────────

    def type_text(self, text: str, interval: Optional[float] = None):
        """Type text with optional inter-character delay."""
        interval = interval if interval is not None else self._typing_interval
        for char in text:
            self._keyboard.type(char)
            if interval > 0:
                time.sleep(interval)

    def press_key(self, key: str):
        """Press and release a single key."""
        k = self._resolve_key(key)
        self._keyboard.press(k)
        time.sleep(0.02)
        self._keyboard.release(k)

    def hotkey(self, *keys: str):
        """Press a key combination (e.g., hotkey('ctrl', 'c'))."""
        resolved = [self._resolve_key(k) for k in keys]
        for k in resolved:
            self._keyboard.press(k)
            time.sleep(0.02)
        for k in reversed(resolved):
            self._keyboard.release(k)
            time.sleep(0.02)

    def hold_key(self, key: str, duration: float = 0.5):
        """Hold a key for a duration."""
        k = self._resolve_key(key)
        self._keyboard.press(k)
        time.sleep(duration)
        self._keyboard.release(k)

    def _resolve_key(self, key_name: str):
        """Convert string key name to pynput Key enum."""
        from pynput.keyboard import Key

        key_map = {
            "ctrl": Key.ctrl_l, "ctrl_l": Key.ctrl_l, "ctrl_r": Key.ctrl_r,
            "alt": Key.alt_l, "alt_l": Key.alt_l, "alt_r": Key.alt_r,
            "shift": Key.shift_l, "shift_l": Key.shift_l, "shift_r": Key.shift_r,
            "win": Key.cmd, "cmd": Key.cmd, "super": Key.cmd,
            "enter": Key.enter, "return": Key.enter,
            "tab": Key.tab,
            "esc": Key.esc, "escape": Key.esc,
            "space": Key.space,
            "backspace": Key.backspace,
            "delete": Key.delete, "del": Key.delete,
            "insert": Key.insert,
            "home": Key.home, "end": Key.end,
            "page_up": Key.page_up, "pageup": Key.page_up,
            "page_down": Key.page_down, "pagedown": Key.page_down,
            "up": Key.up, "down": Key.down, "left": Key.left, "right": Key.right,
            "caps_lock": Key.caps_lock,
            "num_lock": Key.num_lock,
            "scroll_lock": Key.scroll_lock,
            "print_screen": Key.print_screen,
            "pause": Key.pause,
            "menu": Key.menu,
            "f1": Key.f1, "f2": Key.f2, "f3": Key.f3, "f4": Key.f4,
            "f5": Key.f5, "f6": Key.f6, "f7": Key.f7, "f8": Key.f8,
            "f9": Key.f9, "f10": Key.f10, "f11": Key.f11, "f12": Key.f12,
        }

        lower = key_name.lower()
        if lower in key_map:
            return key_map[lower]

        # Single character
        if len(key_name) == 1:
            return key_name

        raise ValueError(f"Unknown key: {key_name}")
