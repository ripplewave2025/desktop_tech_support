"""
System Tray Icon for Zora.

Uses pystray to create a system tray icon with context menu.
Shows alert badge when monitoring detects issues.
"""

import logging
import threading
import webbrowser
from typing import Optional, Callable

logger = logging.getLogger("zora.tray")

# Default Zora URL
ZORA_URL = "http://127.0.0.1:8000"


def _create_icon_image(size=64, has_alert=False):
    """Create a simple Zora icon image using PIL.

    Blue shield icon. Orange dot overlay when alerts are active.
    """
    try:
        from PIL import Image, ImageDraw

        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Shield shape (filled blue circle as simple icon)
        margin = size // 8
        draw.ellipse(
            [margin, margin, size - margin, size - margin],
            fill=(59, 130, 246, 255),  # Blue
            outline=(37, 99, 235, 255),
            width=2,
        )

        # "Z" letter in center
        center = size // 2
        font_size = size // 3
        try:
            from PIL import ImageFont
            font = ImageFont.truetype("arial.ttf", font_size)
        except Exception:
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), "Z", font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        draw.text(
            (center - text_w // 2, center - text_h // 2 - 2),
            "Z",
            fill=(255, 255, 255, 255),
            font=font,
        )

        # Alert badge (orange dot in top-right)
        if has_alert:
            badge_size = size // 4
            draw.ellipse(
                [size - badge_size - margin, margin,
                 size - margin, margin + badge_size],
                fill=(249, 115, 22, 255),  # Orange
            )

        return img
    except ImportError:
        # No PIL available — create minimal icon
        from PIL import Image
        return Image.new("RGBA", (size, size), (59, 130, 246, 255))


class ZoraTray:
    """System tray icon with context menu."""

    def __init__(
        self,
        url: str = ZORA_URL,
        watcher=None,
        on_quit: Optional[Callable] = None,
    ):
        self._url = url
        self._watcher = watcher
        self._on_quit = on_quit
        self._icon = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """Start the tray icon in a background thread."""
        if self._running:
            return

        try:
            import pystray
        except ImportError:
            logger.warning("pystray not installed — system tray disabled. Install with: pip install pystray")
            return

        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="ZoraTray")
        self._thread.start()
        logger.info("System tray icon started")

    def _run(self):
        """Create and run the tray icon (blocking — runs in thread)."""
        import pystray

        image = _create_icon_image(has_alert=False)

        menu = pystray.Menu(
            pystray.MenuItem("Open Zora", self._open_zora, default=True),
            pystray.MenuItem("Run Quick Check", self._quick_check),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Alerts", self._show_alerts),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit Zora", self._quit),
        )

        self._icon = pystray.Icon(
            "Zora",
            image,
            "Zora AI — Your PC's Best Friend",
            menu,
        )

        # Start alert badge updater
        if self._watcher:
            threading.Thread(target=self._update_badge, daemon=True).start()

        try:
            self._icon.run()
        except Exception as e:
            logger.error(f"Tray icon error: {e}")
        finally:
            self._running = False

    def _update_badge(self):
        """Periodically update tray icon badge based on alert count."""
        import time
        last_has_alert = False

        while self._running and self._icon:
            try:
                has_alert = self._watcher.active_count > 0 if self._watcher else False
                if has_alert != last_has_alert:
                    self._icon.icon = _create_icon_image(has_alert=has_alert)
                    alert_count = self._watcher.active_count if self._watcher else 0
                    if has_alert:
                        self._icon.title = f"Zora AI — {alert_count} alert{'s' if alert_count != 1 else ''}"
                    else:
                        self._icon.title = "Zora AI — Your PC's Best Friend"
                    last_has_alert = has_alert
            except Exception:
                pass
            time.sleep(5)

    # ─── Menu Actions ──────────────────────────────────
    def _open_zora(self, icon=None, item=None):
        """Open Zora in browser."""
        webbrowser.open(self._url)

    def _quick_check(self, icon=None, item=None):
        """Run a quick system check via API."""
        try:
            import urllib.request
            urllib.request.urlopen(f"{self._url}/api/system", timeout=5)
            webbrowser.open(self._url)
        except Exception:
            webbrowser.open(self._url)

    def _show_alerts(self, icon=None, item=None):
        """Open Zora with alerts focus."""
        webbrowser.open(f"{self._url}?tab=alerts")

    def _quit(self, icon=None, item=None):
        """Quit Zora."""
        self._running = False
        if self._icon:
            self._icon.stop()
        if self._on_quit:
            self._on_quit()

    def stop(self):
        """Stop the tray icon."""
        self._running = False
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass
