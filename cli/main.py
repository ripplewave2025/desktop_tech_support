#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Desktop Tech Support — CLI Entry Point

Usage:
  python -m cli.main                    # Interactive menu
  python -m cli.main --diagnose printer # Run specific diagnostic
  python -m cli.main --diagnose all     # Run all diagnostics
  python -m cli.main --sysinfo          # Show system info
  python -m cli.main --help             # Show help
"""

import sys
import io
import argparse
import json
import os

# Fix Windows console encoding for narrator output
try:
    if sys.stdout and hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
except Exception:
    pass

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


DIAGNOSTIC_MODULES = {
    "printer": ("diagnostics.printer", "PrinterDiagnostic"),
    "internet": ("diagnostics.internet", "InternetDiagnostic"),
    "software": ("diagnostics.software", "SoftwareDiagnostic"),
    "hardware": ("diagnostics.hardware", "HardwareDiagnostic"),
    "files": ("diagnostics.files", "FilesDiagnostic"),
    "display": ("diagnostics.display", "DisplayDiagnostic"),
    "audio": ("diagnostics.audio", "AudioDiagnostic"),
    "security": ("diagnostics.security", "SecurityDiagnostic"),
}

BANNER = """
  ============================================================
   Desktop Tech Support
   Windows Troubleshooting & Automation
  ============================================================
   Powered by the Zora Narrator System
  ============================================================
"""


def load_diagnostic(name: str):
    """Dynamically load a diagnostic module."""
    module_path, class_name = DIAGNOSTIC_MODULES[name]
    import importlib
    mod = importlib.import_module(module_path)
    return getattr(mod, class_name)


def run_diagnostic(name: str, auto_fix: bool = False):
    """Run a named diagnostic."""
    print(f"\n  Loading {name} diagnostic...")
    DiagClass = load_diagnostic(name)
    diag = DiagClass()
    results = diag.run(auto_fix=auto_fix)
    return diag.get_summary()


def show_system_info():
    """Display system information."""
    from core.process_manager import ProcessManager
    pm = ProcessManager()
    info = pm.get_system_info()
    print(f"\n  System Information")
    print(f"  {'=' * 50}")
    print(f"  CPU:    {info.cpu_percent}% ({info.cpu_count} cores)")
    print(f"  Memory: {info.memory_used_gb}/{info.memory_total_gb} GB ({info.memory_percent}%)")
    print(f"  Disk:   {info.disk_free_gb} GB free ({info.disk_percent}% used)")
    print(f"  Uptime: {info.uptime_hours} hours")
    print(f"  {'=' * 50}")


def interactive_menu():
    """Show interactive diagnostic selection menu."""
    print(BANNER)

    categories = list(DIAGNOSTIC_MODULES.keys())

    while True:
        print("\n  Choose a diagnostic category:\n")
        for i, name in enumerate(categories, 1):
            module_path, class_name = DIAGNOSTIC_MODULES[name]
            print(f"    {i}. {name.capitalize():12s}")

        print(f"\n    {len(categories)+1}. Run ALL diagnostics")
        print(f"    {len(categories)+2}. System Information")
        print(f"    0. Exit\n")

        try:
            choice = input("  Enter choice (number): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Goodbye!")
            break

        if choice == "0" or choice.lower() == "exit":
            print("\n  Goodbye! Your computer is in good hands.")
            break
        elif choice == str(len(categories) + 1):
            print("\n  Running ALL diagnostics...\n")
            all_summaries = []
            for name in categories:
                try:
                    summary = run_diagnostic(name)
                    all_summaries.append(summary)
                except Exception as e:
                    print(f"\n  [Error] {name}: {e}")

            # Final report
            print(f"\n  {'=' * 56}")
            print(f"  FINAL REPORT")
            print(f"  {'=' * 56}")
            total_ok = sum(s["ok"] for s in all_summaries)
            total_warn = sum(s["warnings"] for s in all_summaries)
            total_err = sum(s["errors"] for s in all_summaries)
            total_fix = sum(s["fixed"] for s in all_summaries)
            print(f"  OK: {total_ok}  |  Warnings: {total_warn}  |  Errors: {total_err}  |  Fixed: {total_fix}")
            print(f"  {'=' * 56}")
        elif choice == str(len(categories) + 2):
            show_system_info()
        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(categories):
                    name = categories[idx]
                    try:
                        run_diagnostic(name)
                    except Exception as e:
                        print(f"\n  [Error] {e}")
                else:
                    print("\n  Invalid choice. Try again.")
            except ValueError:
                # Try by name
                if choice.lower() in DIAGNOSTIC_MODULES:
                    try:
                        run_diagnostic(choice.lower())
                    except Exception as e:
                        print(f"\n  [Error] {e}")
                else:
                    print("\n  Invalid choice. Try again.")


def main():
    parser = argparse.ArgumentParser(
        description="Desktop Tech Support - Windows Troubleshooting",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m cli.main                     Interactive menu
  python -m cli.main --diagnose printer  Run printer diagnostic
  python -m cli.main --diagnose all      Run all diagnostics
  python -m cli.main --sysinfo           Show system info
  python -m cli.main --auto-fix          Auto-fix with permission
        """,
    )
    parser.add_argument(
        "--diagnose", "-d",
        choices=list(DIAGNOSTIC_MODULES.keys()) + ["all"],
        help="Run a specific diagnostic category",
    )
    parser.add_argument(
        "--auto-fix", action="store_true",
        help="Automatically attempt fixes (still asks permission)",
    )
    parser.add_argument(
        "--sysinfo", action="store_true",
        help="Show system information",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output results as JSON",
    )

    args = parser.parse_args()

    if args.sysinfo:
        show_system_info()
        return

    if args.diagnose:
        if args.diagnose == "all":
            summaries = []
            for name in DIAGNOSTIC_MODULES:
                try:
                    s = run_diagnostic(name, auto_fix=args.auto_fix)
                    summaries.append(s)
                except Exception as e:
                    print(f"\n  [Error] {name}: {e}")
            if args.json:
                print(json.dumps(summaries, indent=2))
        else:
            try:
                summary = run_diagnostic(args.diagnose, auto_fix=args.auto_fix)
                if args.json:
                    print(json.dumps(summary, indent=2))
            except Exception as e:
                print(f"\n  [Error] {e}")
                sys.exit(1)
        return

    # No args -> interactive menu
    interactive_menu()


if __name__ == "__main__":
    main()
