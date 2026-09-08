"""
Desktop Floating Widget - Main Entry Point.
Monitors connected Bluetooth device battery levels and ChatGPT/Codex usage quotas.
"""

import sys
import os
import traceback

# Ensure current directory is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Setup error logging
def excepthook(exc_type, exc_value, exc_tb):
    err_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    print("Unhandled exception:\n", err_text)
    try:
        with open(os.path.join(BASE_DIR, "error.log"), "a", encoding="utf-8") as f:
            f.write(f"\n--- Error: ---\n{err_text}\n")
    except Exception:
        pass
    sys.__excepthook__(exc_type, exc_value, exc_tb)

sys.excepthook = excepthook

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

from core.config_manager import ConfigManager
from ui.floating_widget import FloatingWidget
from ui.tray_manager import TrayManager


def main():
    # Enable High DPI support
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # Keep running in system tray
    app.setApplicationName("DesktopBatteryCodexWidget")
    app.setApplicationDisplayName("桌面悬浮插件 (蓝牙电量 & ChatGPT限额)")

    config_mgr = ConfigManager(BASE_DIR)
    widget = FloatingWidget(config_mgr)
    tray = TrayManager(widget)

    widget.show()
    widget.raise_()
    widget.activateWindow()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
