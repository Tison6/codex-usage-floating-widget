"""
Desktop Floating Widget - Main Entry Point.
Monitors connected Bluetooth device battery levels and ChatGPT/Codex usage quotas.
"""

import sys
import os
import traceback
import hashlib
import tempfile

# Ensure pythonw does not crash when printing
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

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
from PyQt5.QtCore import Qt, QLockFile
from PyQt5.QtNetwork import QLocalServer, QLocalSocket

from core.config_manager import ConfigManager


def main():
    # Enable High DPI support
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    if hasattr(QApplication, "setHighDpiScaleFactorRoundingPolicy"):
        QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # Keep running in system tray
    app.setApplicationName("DesktopBatteryCodexWidget")
    app.setApplicationDisplayName("桌面悬浮插件 (蓝牙电量 & ChatGPT限额)")

    instance_name = "desktop-floating-widget-" + hashlib.sha256(os.path.normcase(BASE_DIR).encode()).hexdigest()[:20]
    # Windows named pipes allow multiple listeners, so use an exclusive file lock.
    instance_lock = QLockFile(os.path.join(tempfile.gettempdir(), instance_name + ".lock"))
    instance_lock.setStaleLockTime(0)
    if not instance_lock.tryLock(0):
        if instance_lock.error() != QLockFile.LockFailedError:
            raise RuntimeError("无法创建悬浮窗进程锁")
        existing = QLocalSocket(app)
        existing.connectToServer(instance_name)
        if existing.waitForConnected(1000):
            existing.disconnectFromServer()
        return

    server = QLocalServer(app)
    if not server.listen(instance_name):
        raise RuntimeError("无法启动悬浮窗通信 " + server.errorString())

    from ui.floating_widget import FloatingWidget
    from ui.tray_manager import TrayManager

    config_mgr = ConfigManager(BASE_DIR)
    widget = FloatingWidget(config_mgr)
    tray = TrayManager(widget)
    app.aboutToQuit.connect(widget.close)

    def activate_existing():
        while server.hasPendingConnections():
            connection = server.nextPendingConnection()
            connection.disconnectFromServer()
            connection.deleteLater()
        tray.show_and_activate_widget()

    server.newConnection.connect(activate_existing)
    widget.show()
    widget.raise_()
    widget.activateWindow()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
