# Known Limitations

This document outlines the current limitations of Desktop Tech Support. Understanding these will help you set expectations and identify areas for improvement.

---

## Platform Limitations

| Limitation | Details |
|------------|---------|
| **Windows only** | Built exclusively for Windows 10/11. No macOS or Linux support. |
| **Desktop session required** | Window management and screen capture require an active desktop session. Will not work in headless/remote-only environments. |
| **Admin required for some fixes** | Service restarts (Print Spooler, Audio) and firewall changes require Administrator privileges. |
| **No ARM64 support tested** | All testing done on x86/x64 Windows. ARM-based Windows devices (Surface Pro X) are untested. |

## Diagnostic Limitations

### Printer
- Cannot detect network printers that aren't added to Windows
- Cannot install missing printer drivers
- Cannot fix hardware issues (paper jams, ink levels)

### Internet
- Bandwidth measurement is approximate (measures total system I/O, not per-app)
- Cannot diagnose ISP-level issues or router configuration
- WiFi signal strength only available for the connected network
- Cannot fix router/modem issues

### Software
- Cannot detect all types of application crashes (only process status)
- Windows Update check is service-level only — cannot enumerate pending updates
- Cannot uninstall or repair specific applications

### Hardware
- Temperature sensors rarely available on Windows (psutil limitation)
- Cannot detect specific hardware failures (bad RAM, failing SSD)
- Battery health (cycle count, wear level) not accessible via psutil
- Cannot measure CPU thermals on most consumer hardware

### Files
- Large file scan limited to user profile (skips AppData for speed)
- Cannot recover deleted files
- Cannot detect file corruption

### Display
- DPI scaling detection uses registry (may not reflect runtime changes)
- Cannot detect color calibration issues
- Multi-monitor arrangement detection is basic (position only)

### Audio
- Cannot detect individual application volume levels
- Cannot identify specific audio codec issues
- Bluetooth audio device pairing issues not covered

### Security
- Suspicious process detection uses a simple name-matching heuristic — NOT a real malware scanner
- Cannot detect rootkits, fileless malware, or advanced persistent threats
- Port scanning is passive (checks listening ports only)
- Cannot replace a proper antivirus solution

## Technical Limitations

| Area | Limitation |
|------|-----------|
| **OCR** | Requires Tesseract OCR installed separately. Accuracy depends on screen DPI, font, and background contrast. |
| **Template matching** | Works best with exact pixel matches. Scale/rotation changes will cause misses. |
| **Rate limiting** | Sliding window is per-process — won't protect across multiple instances. |
| **Input simulation** | Some applications with elevated privileges may reject simulated input. UAC prompts cannot be interacted with. |
| **Window automation** | UWP/modern Windows apps have limited pywinauto support compared to Win32 apps. |

## What This Tool Is NOT

- **Not a replacement for antivirus software** — the security diagnostic provides basic checks only
- **Not a remote access tool** — designed for local use (remote support requires separate screen sharing)
- **Not a system repair tool** — cannot fix corrupted Windows installations (use DISM/SFC for that)
- **Not a hardware diagnostic** — cannot test RAM, GPU, or storage at a hardware level (use manufacturer tools)
- **Not AI-powered yet** — diagnostics follow rule-based logic, not machine learning

## Reporting New Limitations

If you discover a limitation not listed here, please [open an issue](https://github.com/ripplewave2025/desktop_tech_support/issues) with:
1. What you expected to work
2. What actually happened
3. Your Windows version and hardware
