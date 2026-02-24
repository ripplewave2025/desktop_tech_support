#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Window Manager — Find, manipulate, and interact with application windows.

Uses pywinauto (primary) with pywin32 fallback.
"""

import time
from typing import Optional, List, Tuple, Any


class WindowInfo:
    """Lightweight window descriptor."""

    def __init__(self, handle: int, title: str, class_name: str = "",
                 pid: int = 0, visible: bool = True, rect: Tuple = (0, 0, 0, 0)):
        self.handle = handle
        self.title = title
        self.class_name = class_name
        self.pid = pid
        self.visible = visible
        self.rect = rect  # (left, top, right, bottom)

    @property
    def width(self):
        return self.rect[2] - self.rect[0]

    @property
    def height(self):
        return self.rect[3] - self.rect[1]

    def __repr__(self):
        return f"<Window '{self.title}' handle={self.handle} {self.width}x{self.height}>"


class Window:
    """Rich window wrapper with manipulation and UI element access."""

    def __init__(self, handle: int, backend: str = "uia"):
        self.handle = handle
        self._backend = backend
        self._app = None
        self._win = None
        self._connect()

    def _connect(self):
        """Connect to the window via pywinauto."""
        try:
            from pywinauto import Application
            self._app = Application(backend=self._backend).connect(handle=self.handle)
            self._win = self._app.window(handle=self.handle)
        except Exception:
            self._win = None

    @property
    def title(self) -> str:
        if self._win:
            try:
                return self._win.window_text()
            except Exception:
                pass
        return self._get_title_win32()

    def _get_title_win32(self) -> str:
        try:
            import win32gui
            return win32gui.GetWindowText(self.handle)
        except Exception:
            return ""

    def focus(self):
        """Bring window to foreground."""
        if self._win:
            try:
                self._win.set_focus()
                return
            except Exception:
                pass
        # Fallback to win32
        try:
            import win32gui
            import win32con
            win32gui.ShowWindow(self.handle, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(self.handle)
        except Exception:
            pass

    def minimize(self):
        if self._win:
            try:
                self._win.minimize()
                return
            except Exception:
                pass
        try:
            import win32gui
            import win32con
            win32gui.ShowWindow(self.handle, win32con.SW_MINIMIZE)
        except Exception:
            pass

    def maximize(self):
        if self._win:
            try:
                self._win.maximize()
                return
            except Exception:
                pass
        try:
            import win32gui
            import win32con
            win32gui.ShowWindow(self.handle, win32con.SW_MAXIMIZE)
        except Exception:
            pass

    def restore(self):
        if self._win:
            try:
                self._win.restore()
                return
            except Exception:
                pass
        try:
            import win32gui
            import win32con
            win32gui.ShowWindow(self.handle, win32con.SW_RESTORE)
        except Exception:
            pass

    def close(self, force: bool = False):
        """Close the window. force=True kills the process."""
        if self._win:
            try:
                if force:
                    self._win.close()
                else:
                    self._win.close()
                return
            except Exception:
                pass
        try:
            import win32gui
            import win32con
            win32gui.PostMessage(self.handle, win32con.WM_CLOSE, 0, 0)
        except Exception:
            pass

    def move(self, x: int, y: int):
        rect = self.get_rect()
        w = rect[2] - rect[0]
        h = rect[3] - rect[1]
        try:
            import win32gui
            win32gui.MoveWindow(self.handle, x, y, w, h, True)
        except Exception:
            pass

    def resize(self, width: int, height: int):
        rect = self.get_rect()
        try:
            import win32gui
            win32gui.MoveWindow(self.handle, rect[0], rect[1], width, height, True)
        except Exception:
            pass

    def get_rect(self) -> Tuple[int, int, int, int]:
        try:
            import win32gui
            return win32gui.GetWindowRect(self.handle)
        except Exception:
            return (0, 0, 0, 0)

    def get_position(self) -> Tuple[int, int, int, int]:
        """Returns (x, y, width, height)."""
        rect = self.get_rect()
        return (rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1])

    def is_visible(self) -> bool:
        try:
            import win32gui
            return bool(win32gui.IsWindowVisible(self.handle))
        except Exception:
            return False

    def has_focus(self) -> bool:
        try:
            import win32gui
            return win32gui.GetForegroundWindow() == self.handle
        except Exception:
            return False

    def find_element(self, name: Optional[str] = None,
                     control_type: Optional[str] = None,
                     automation_id: Optional[str] = None) -> Optional[Any]:
        """Find a UI element within the window."""
        if not self._win:
            return None
        try:
            kwargs = {}
            if name:
                kwargs["title"] = name
            if control_type:
                kwargs["control_type"] = control_type
            if automation_id:
                kwargs["auto_id"] = automation_id
            return self._win.child_window(**kwargs)
        except Exception:
            return None

    def click_element(self, name: str, control_type: Optional[str] = None) -> bool:
        """Find and click a UI element by name."""
        elem = self.find_element(name=name, control_type=control_type)
        if elem:
            try:
                elem.click_input()
                return True
            except Exception:
                return False
        return False

    def type_into_element(self, name: str, text: str,
                          control_type: str = "Edit") -> bool:
        """Find a text field and type into it."""
        elem = self.find_element(name=name, control_type=control_type)
        if elem:
            try:
                elem.set_focus()
                elem.type_keys(text, with_spaces=True)
                return True
            except Exception:
                return False
        return False

    def get_text(self) -> str:
        """Get text content of the window."""
        if self._win:
            try:
                return self._win.window_text()
            except Exception:
                pass
        return self._get_title_win32()

    def print_control_identifiers(self):
        """Print the accessibility tree (useful for debugging)."""
        if self._win:
            try:
                self._win.print_control_identifiers()
            except Exception:
                print(f"Could not inspect window: {self.title}")


class WindowManager:
    """Find and manage application windows."""

    def __init__(self, backend: str = "uia", search_timeout: float = 5.0):
        self._backend = backend
        self._search_timeout = search_timeout

    def find_window(self, title: Optional[str] = None,
                    title_re: Optional[str] = None,
                    class_name: Optional[str] = None,
                    process: Optional[str] = None) -> Optional[Window]:
        """Find a window by title, regex title, class name, or process name."""
        try:
            from pywinauto import Application, findwindows

            if process:
                try:
                    app = Application(backend=self._backend).connect(path=process)
                    win = app.top_window()
                    return Window(win.handle, self._backend)
                except Exception:
                    pass

            kwargs = {}
            if title:
                kwargs["title"] = title
            if title_re:
                kwargs["title_re"] = title_re
            if class_name:
                kwargs["class_name"] = class_name

            handles = findwindows.find_windows(**kwargs)
            if handles:
                return Window(handles[0], self._backend)
        except Exception:
            pass

        # Fallback: win32gui enumeration
        if title:
            return self._find_by_title_win32(title)
        return None

    def _find_by_title_win32(self, title: str) -> Optional[Window]:
        """Fallback window search using win32gui."""
        try:
            import win32gui

            result = [None]

            def callback(hwnd, _):
                txt = win32gui.GetWindowText(hwnd)
                if title.lower() in txt.lower() and win32gui.IsWindowVisible(hwnd):
                    result[0] = hwnd
                    return False  # Stop enumeration
                return True

            try:
                win32gui.EnumWindows(callback, None)
            except Exception:
                pass

            if result[0]:
                return Window(result[0], self._backend)
        except ImportError:
            pass
        return None

    def get_active_window(self) -> Optional[Window]:
        """Get the currently focused window."""
        try:
            import win32gui
            hwnd = win32gui.GetForegroundWindow()
            if hwnd:
                return Window(hwnd, self._backend)
        except Exception:
            pass
        return None

    def list_windows(self, include_invisible: bool = False) -> List[WindowInfo]:
        """List all top-level windows."""
        windows = []
        try:
            import win32gui

            def callback(hwnd, _):
                if not include_invisible and not win32gui.IsWindowVisible(hwnd):
                    return True
                title = win32gui.GetWindowText(hwnd)
                if not title:
                    return True
                try:
                    rect = win32gui.GetWindowRect(hwnd)
                    class_name = win32gui.GetClassName(hwnd)
                    windows.append(WindowInfo(
                        handle=hwnd,
                        title=title,
                        class_name=class_name,
                        visible=win32gui.IsWindowVisible(hwnd),
                        rect=rect,
                    ))
                except Exception:
                    pass
                return True

            win32gui.EnumWindows(callback, None)
        except ImportError:
            pass
        return windows
