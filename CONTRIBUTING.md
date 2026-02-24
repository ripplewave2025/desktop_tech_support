# Contributing to Desktop Tech Support

Thank you for your interest in improving Windows tech support automation! This project welcomes contributions from developers, IT professionals, and anyone who wants to make tech support more accessible.

---

## How to Contribute

### 1. Report Issues
- Open a [GitHub Issue](https://github.com/ripplewave2025/desktop_tech_support/issues)
- Include: Windows version, Python version, error output, and steps to reproduce

### 2. Add a New Diagnostic Module
Each diagnostic follows the same pattern. To add one:

1. Create `diagnostics/your_module.py`
2. Subclass `BaseDiagnostic`
3. Implement `diagnose()` returning `List[DiagnosticResult]`
4. Optionally implement `apply_fix()`
5. Register it in `cli/main.py` under `DIAGNOSTIC_MODULES`

```python
from .base import BaseDiagnostic, DiagnosticResult

class YourDiagnostic(BaseDiagnostic):
    CATEGORY = "your_category"
    DESCRIPTION = "Your Category Troubleshooting"

    def diagnose(self):
        results = []
        # Your diagnostic logic here
        results.append(DiagnosticResult("Check Name", "ok", "Details"))
        return results
```

### 3. Improve Existing Diagnostics
- Add more checks to existing modules
- Improve error messages and narrator scripts
- Add manufacturer-specific fixes (see `docs/SUPPORT_RESOURCES.md`)

### 4. Fix Bugs
- Fork the repo, create a branch, fix the issue, submit a PR
- Include tests for your fix

---

## Development Setup

```powershell
git clone https://github.com/ripplewave2025/desktop_tech_support.git
cd desktop_tech_support
python setup.py
python -m unittest discover -s tests -v
```

## Code Style

- Python 3.8+ compatible
- Type hints encouraged
- Docstrings for all public methods
- Narrator messages must be non-technical and friendly
- All fixes must ask user permission via `ask_permission()`

## Safety Rules for Contributors

> **CRITICAL**: All automation actions MUST go through the SafetyController.

- Never bypass safety checks
- Never auto-execute destructive actions without user permission
- Never interact with system-critical paths (System32, registry boot keys)
- Always provide rollback information when applying fixes
- Test on a non-production machine first

## Testing

```powershell
# Run all tests
python -m unittest discover -s tests -v

# Run specific suite
python -m unittest tests.test_safety -v
```

All PRs must pass the existing test suite. Add tests for new features.

## Areas We Need Help With

| Area | Description |
|------|-------------|
| **Bluetooth diagnostics** | Pairing issues, driver detection |
| **VPN troubleshooting** | Connection drops, DNS leaks |
| **Windows Update deep dive** | Stuck updates, DISM/SFC integration |
| **Accessibility** | Screen reader compatibility, high-contrast support |
| **Localization** | Narrator messages in other languages |
| **Manufacturer-specific fixes** | Dell, HP, Lenovo, ASUS, Acer specific tools |
| **Zora avatar overlay** | PyQt5/PySide6 transparent window with animated avatar |

---

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
