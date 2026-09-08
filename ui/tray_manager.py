"""
System Tray Icon and Context Menu Manager.
"""

from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QAction, QApplication
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QFont
from PyQt5.QtCore import Qt


def create_tray_icon_pixmap() -> QPixmap:
    """Generate a crisp programmatic icon for the system tray."""
    size = 32
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    
    # Background circle
    painter.setBrush(QColor(59, 130, 246))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(2, 2, 28, 28, 6, 6)
    
    # Inner symbol (⚡)
    painter.setPen(QColor(255, 255, 255))
    font = QFont("Segoe UI Emoji", 14, QFont.Bold)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "⚡")
    
    painter.end()
    return pixmap


class TrayManager:
    """Manages Windows System Tray icon and interactions."""
    
    def __init__(self, floating_widget, parent=None):
        self.widget = floating_widget
        self.tray = QSystemTrayIcon(parent or floating_widget)
        
        # Set icon
        pixmap = create_tray_icon_pixmap()
        self.tray.setIcon(QIcon(pixmap))
        self.tray.setToolTip("桌面悬浮插件 (蓝牙电量 + ChatGPT限额)")
        
        self.init_menu()
        self.tray.activated.connect(self.on_tray_activated)
        self.tray.show()

    def init_menu(self):
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background-color: #181E2C;
                color: #E5E7EB;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 18px 6px 12px;
                border-radius: 4px;
                font-size: 12px;
            }
            QMenu::item:selected {
                background-color: #3B82F6;
                color: #FFFFFF;
            }
            QMenu::separator {
                height: 1px;
                background: rgba(255, 255, 255, 0.1);
                margin: 4px 6px;
            }
        """)
        
        act_toggle = menu.addAction("👁️ 显示 / 隐藏悬浮窗")
        act_toggle.triggered.connect(self.toggle_widget_visibility)
        
        act_mode = menu.addAction("💊 切换迷你 / 展开模式")
        act_mode.triggered.connect(self.widget.toggle_mode)
        
        menu.addSeparator()
        
        act_refresh = menu.addAction("🔄 立即刷新数据")
        act_refresh.triggered.connect(lambda: self.widget.refresh_all_data(force=True))
        
        act_settings = menu.addAction("⚙️ 偏好设置...")
        act_settings.triggered.connect(self.widget.open_settings)
        
        menu.addSeparator()
        
        act_exit = menu.addAction("✕ 退出程序")
        act_exit.triggered.connect(QApplication.instance().quit)
        
        self.tray.setContextMenu(menu)

    def on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.toggle_widget_visibility()

    def toggle_widget_visibility(self):
        if self.widget.isVisible():
            self.widget.hide()
        else:
            self.widget.show()
            self.widget.raise_()
            self.widget.activateWindow()
