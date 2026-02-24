#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Screen Capture & Vision — Screenshots, OCR, and image recognition.

Uses mss for fast capture, pytesseract for OCR, and opencv for template matching.
"""

import os
import time
from typing import Optional, List, Tuple, Dict, Any

import mss
import mss.tools
from PIL import Image


class ScreenCapture:
    """Capture screen regions and extract text/images."""

    def __init__(self, ocr_language: str = "eng", screenshot_format: str = "png"):
        self._ocr_lang = ocr_language
        self._format = screenshot_format
        self._sct = mss.mss()

    def list_monitors(self) -> List[Dict[str, int]]:
        """List all monitors. Index 0 = all monitors combined."""
        return [dict(m) for m in self._sct.monitors]

    def capture(self, region: Optional[Tuple[int, int, int, int]] = None,
                monitor: int = 0) -> Image.Image:
        """
        Capture screenshot.
        
        Args:
            region: (left, top, width, height) or None for full screen
            monitor: monitor index (0=all, 1=primary, 2=secondary...)
        """
        if region:
            left, top, width, height = region
            bbox = {"left": left, "top": top, "width": width, "height": height}
        else:
            bbox = self._sct.monitors[monitor]

        raw = self._sct.grab(bbox)
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        return img

    def capture_to_file(self, filepath: str,
                        region: Optional[Tuple[int, int, int, int]] = None,
                        monitor: int = 0) -> str:
        """Capture screenshot and save to file."""
        img = self.capture(region=region, monitor=monitor)
        os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else ".", exist_ok=True)
        img.save(filepath)
        return os.path.abspath(filepath)

    def read_text(self, region: Optional[Tuple[int, int, int, int]] = None,
                  lang: Optional[str] = None) -> str:
        """OCR — extract text from screen or region."""
        import pytesseract
        img = self.capture(region=region)
        text = pytesseract.image_to_string(img, lang=lang or self._ocr_lang)
        return text.strip()

    def read_text_detailed(self, region: Optional[Tuple[int, int, int, int]] = None,
                           lang: Optional[str] = None) -> List[Dict[str, Any]]:
        """OCR with confidence scores and bounding boxes."""
        import pytesseract
        img = self.capture(region=region)
        data = pytesseract.image_to_data(img, lang=lang or self._ocr_lang, output_type=pytesseract.Output.DICT)

        results = []
        for i in range(len(data["text"])):
            text = data["text"][i].strip()
            if not text:
                continue
            results.append({
                "text": text,
                "confidence": data["conf"][i],
                "x": data["left"][i],
                "y": data["top"][i],
                "width": data["width"][i],
                "height": data["height"][i],
            })
        return results

    def find_text(self, needle: str,
                  region: Optional[Tuple[int, int, int, int]] = None) -> List[Tuple[int, int, int, int]]:
        """Find all occurrences of text on screen. Returns list of (x, y, w, h)."""
        details = self.read_text_detailed(region=region)
        matches = []
        for item in details:
            if needle.lower() in item["text"].lower() and item["confidence"] > 30:
                matches.append((item["x"], item["y"], item["width"], item["height"]))
        return matches

    def find_image(self, template_path: str,
                   confidence: float = 0.8,
                   region: Optional[Tuple[int, int, int, int]] = None) -> Optional[Tuple[int, int, int, int]]:
        """Find a template image on screen using OpenCV template matching."""
        import cv2
        import numpy as np

        screen = self.capture(region=region)
        screen_np = np.array(screen)
        screen_gray = cv2.cvtColor(screen_np, cv2.COLOR_RGB2GRAY)

        template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
        if template is None:
            return None

        result = cv2.matchTemplate(screen_gray, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val >= confidence:
            tw, th = template.shape[::-1]
            return (max_loc[0], max_loc[1], tw, th)
        return None

    def wait_for_image(self, template_path: str,
                       timeout: float = 10.0,
                       confidence: float = 0.8,
                       interval: float = 0.5) -> Optional[Tuple[int, int, int, int]]:
        """Wait for template image to appear on screen."""
        start = time.time()
        while time.time() - start < timeout:
            result = self.find_image(template_path, confidence=confidence)
            if result:
                return result
            time.sleep(interval)
        return None

    def get_pixel_color(self, x: int, y: int) -> Tuple[int, int, int]:
        """Get RGB color of a specific pixel."""
        img = self.capture(region=(x, y, 1, 1))
        return img.getpixel((0, 0))
