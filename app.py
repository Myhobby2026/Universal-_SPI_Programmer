#!/usr/bin/env python3
"""
Universal Programmer - Main Entry Point
Professional Tkinter GUI + Arduino Firmware

Supports:
- AVR ISP (ATmega, ATtiny)
- SPI Memory (W25Qxx, etc)
- I2C Memory (24Cxx series)

Architecture:
- Modular protocols
- Robust framed binary communication
- Threaded operations (no GUI freeze)
- Professional UI
"""

import sys
import os
import tkinter as tk
from tkinter import messagebox

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from gui.main_window import MainWindow
except ImportError as e:
    print(f"Failed to import GUI: {e}")
    print("Make sure you are running from project root and dependencies are installed")
    print("pip install -r requirements.txt")
    sys.exit(1)


def check_dependencies():
    """Check required dependencies"""
    missing = []
    try:
        import serial
    except ImportError:
        missing.append("pyserial")

    if missing:
        # Try to show messagebox, fallback to console
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "Missing Dependencies",
                f"Missing required packages: {', '.join(missing)}\n\n"
                "Please install with:\n"
                "pip install -r requirements.txt"
            )
            root.destroy()
        except Exception:
            print(f"Missing dependencies: {', '.join(missing)}")
            print("Install with: pip install -r requirements.txt")

        return False
    return True


def main():
    if not check_dependencies():
        sys.exit(1)

    # Create root window
    root = tk.Tk()

    # Set icon if available (optional)
    try:
        # For Windows, set AppUserModelID for taskbar icon grouping
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('UniversalProgrammer.Professional.1.0')
    except Exception:
        pass

    # Create main window
    app = MainWindow(root)

    # Center window
    try:
        root.update_idletasks()
        width = root.winfo_width()
        height = root.winfo_height()
        x = (root.winfo_screenwidth() // 2) - (width // 2)
        y = (root.winfo_screenheight() // 2) - (height // 2)
        root.geometry(f'{width}x{height}+{x}+{y}')
    except Exception:
        pass

    # Start main loop
    root.mainloop()


if __name__ == '__main__':
    main()
