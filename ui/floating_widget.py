"""
Main Desktop Floating Widget.
Supports frameless dragging, screen edge snapping, mini-capsule / compact expanded modes,
dynamic opacity, stay-on-top, size scaling, ChatGPT CodeX status light,
click-to-expand, auto-collapse on focus loss, and health-based color transitions.
"""

from typing import List, Dict, Any, Optional
import os
import time
import psutil

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QMenu, QAction, QApplication, QDesktopWidget, QGraphicsDropShadowEffect, QDialog
)
from PyQt5.QtCore import Qt, QPoint, QTimer, QThread, pyqtSignal, QEvent
from PyQt5.QtGui import QColor, QCursor, QFont

from core.config_manager import ConfigManager
from core.bt_scanner import BluetoothScanner
from core.codex_client import CodexUsageClient
from core.quota_tracker import QuotaTracker
from core.codex_activity_tracker import CodexActivityTracker
from ui.battery_view import BatteryView
from ui.codex_view import CodexQuotaView
from ui.status_light import CodexStatusLight
from ui.settings_dialog import SettingsDialog
from ui.styles import MAIN_STYLESHEET


def get_health_color(percent: int) -> str:
    """Return health color dynamically based on remaining percentage."""
    if percent > 50:
        return "#10B981"  # Healthy Green (>50%)
    elif percent >= 20:
        return "#F59E0B"  # Amber/Orange (20%~50%)
    else:
        return "#EF4444"  # Alert Red (<20%)


class BluetoothScanWorker(QThread):
    """Background worker to scan Bluetooth devices without blocking the main UI thread."""
    devices_ready = pyqtSignal(list)
    
    def __init__(self, only_connected: bool = True):
        super().__init__()
        self.only_connected = only_connected
        
    def run(self):
        try:
            devs = BluetoothScanner.get_connected_devices(only_connected=self.only_connected)
            self.devices_ready.emit(devs)
        except Exception:
            self.devices_ready.emit([])


class CodexFetchWorker(QThread):
    """Asynchronous worker thread to query ChatGPT / Codex usage without blocking UI."""
    data_ready = pyqtSignal(dict)
    
    def __init__(self, client: CodexUsageClient, force: bool = False):
        super().__init__()
        self.client = client
        self.force = force
        
    def run(self):
        result = self.client.fetch_usage(force=self.force)
        self.data_ready.emit(result)


class FloatingWidget(QWidget):
    """Frameless translucent desktop floating widget with auto-collapse & instant interaction."""
    
    def __init__(self, config_manager: ConfigManager):
        super().__init__()
        self.cfg = config_manager
        self.codex_client = CodexUsageClient(self.cfg.get("auth_file_path"))
        self.quota_tracker = QuotaTracker()
        
        # State variables
        self.is_mini = self.cfg.get("is_mini_mode", False)
        self.is_locked = self.cfg.get("lock_position", False)
        self.widget_scale = self.cfg.get("scale", 1.0)
        
        self._drag_pos = QPoint()
        self._press_global_pos = QPoint()
        self._is_dragging = False
        self._current_devices: List[Dict[str, Any]] = []
        self._current_codex_data: Dict[str, Any] = {}
        
        # Async workers & Mature Activity tracker
        self._bt_worker: Optional[BluetoothScanWorker] = None
        self._codex_worker: Optional[CodexFetchWorker] = None
        self.activity_tracker = CodexActivityTracker(self.cfg.get("codex_home"))
        
        # Window setup
        self.init_window_flags()
        self.init_ui()
        self.apply_theme_and_opacity()
        self.restore_position()
        
        # Timers
        self.setup_timers()
        
        # Initial fetch
        self.refresh_all_data(force=True)

    def init_window_flags(self):
        """Set frameless, tool window (hidden from taskbar), translucent, and stay-on-top flags."""
        flags = Qt.FramelessWindowHint | Qt.Tool
        if self.cfg.get("always_on_top", True):
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet(MAIN_STYLESHEET)

    def init_ui(self):
        """Build widget layout for both Expanded and Mini modes."""
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(6, 6, 6, 6)
        
        # Drop shadow effect
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setColor(QColor(0, 0, 0, 150))
        shadow.setOffset(0, 3)
        self.setGraphicsEffect(shadow)

        # -------------------------------------------------------------
        # 1. Expanded Mode Container
        # -------------------------------------------------------------
        self.expanded_container = QWidget(self)
        self.expanded_container.setObjectName("MainWidget")
        self.exp_layout = QVBoxLayout(self.expanded_container)
        self.exp_layout.setContentsMargins(8, 7, 8, 7)
        self.exp_layout.setSpacing(6)
        
        # Title Bar (No '✕' button - close is managed via tray)
        title_bar = QHBoxLayout()
        title_bar.setContentsMargins(2, 0, 2, 0)
        
        self.title_icon = QLabel("⚡", self.expanded_container)
        self.title_icon.setStyleSheet("font-size: 11px;")
        
        self.title_text = QLabel("状态小组件", self.expanded_container)
        self.title_text.setProperty("class", "TitleLabel")
        
        self.btn_mini_toggle = QPushButton("➖", self.expanded_container)
        self.btn_mini_toggle.setProperty("class", "IconButton")
        self.btn_mini_toggle.setFixedSize(18, 18)
        self.btn_mini_toggle.setToolTip("收起为迷你胶囊模式")
        self.btn_mini_toggle.clicked.connect(self.collapse_to_mini)
        
        self.btn_settings = QPushButton("⚙️", self.expanded_container)
        self.btn_settings.setProperty("class", "IconButton")
        self.btn_settings.setFixedSize(18, 18)
        self.btn_settings.setToolTip("偏好设置")
        self.btn_settings.clicked.connect(self.open_settings)
        
        title_bar.addWidget(self.title_icon)
        title_bar.addWidget(self.title_text)
        title_bar.addStretch()
        title_bar.addWidget(self.btn_mini_toggle)
        title_bar.addWidget(self.btn_settings)
        self.exp_layout.addLayout(title_bar)
        
        # Bluetooth Battery View
        self.battery_view = BatteryView(self.expanded_container)
        self.exp_layout.addWidget(self.battery_view)
        
        # Divider Line
        divider = QFrame(self.expanded_container)
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet("background-color: rgba(255, 255, 255, 0.06); height: 1px; border: none;")
        self.exp_layout.addWidget(divider)
        
        # Codex Quota View
        self.codex_view = CodexQuotaView(self.quota_tracker, self.expanded_container)
        self.codex_view.refresh_requested.connect(lambda: self.fetch_codex_async(force=True))
        self.exp_layout.addWidget(self.codex_view)
        
        self.root_layout.addWidget(self.expanded_container)
        
        # -------------------------------------------------------------
        # 2. Mini Mode Container (Click anywhere to expand)
        # -------------------------------------------------------------
        self.mini_container = QWidget(self)
        self.mini_container.setObjectName("MiniWidget")
        self.mini_container.setCursor(Qt.PointingHandCursor)
        self.mini_container.setToolTip("点击展开状态小组件 (按住可自由拖拽)")
        
        self.mini_layout = QHBoxLayout(self.mini_container)
        self.mini_layout.setContentsMargins(8, 4, 8, 4)
        self.mini_layout.setSpacing(6)
        
        self.mini_bt_lbl = QLabel("📶 --%", self.mini_container)
        self.mini_bt_lbl.setStyleSheet("font-size: 10px; font-weight: 700; color: #10B981;")
        
        mini_sep = QLabel("|", self.mini_container)
        mini_sep.setStyleSheet("color: rgba(255,255,255,0.2);")
        
        # Clean dual quota: 🤖 100% · 84%
        self.mini_cdx_lbl = QLabel("🤖 --% · --%", self.mini_container)
        self.mini_cdx_lbl.setStyleSheet("font-size: 10px; font-weight: 700;")
        
        # Status light placed on the right
        self.mini_status_light = CodexStatusLight(self.mini_container, size=13)
        
        self.mini_layout.addWidget(self.mini_bt_lbl)
        self.mini_layout.addWidget(mini_sep)
        self.mini_layout.addWidget(self.mini_cdx_lbl)
        self.mini_layout.addWidget(self.mini_status_light)
        
        # Ensure clicks anywhere on labels or status light trigger container expand
        for w in (self.mini_bt_lbl, mini_sep, self.mini_cdx_lbl, self.mini_status_light):
            w.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            
        self.mini_container.mousePressEvent = self.mousePressEvent
        self.mini_container.mouseMoveEvent = self.mouseMoveEvent
        self.mini_container.mouseReleaseEvent = self.mouseReleaseEvent
        
        self.root_layout.addWidget(self.mini_container)
        
        # Apply initial mode display
        self.update_mode_visibility()

    def expand_to_full(self):
        """Expand to full detailed card."""
        if self.is_mini:
            self.is_mini = False
            self.cfg.set("is_mini_mode", False)
            self.update_mode_visibility()
            self.activateWindow()

    def collapse_to_mini(self):
        """Collapse back to mini capsule."""
        if not self.is_mini:
            self.is_mini = True
            self.cfg.set("is_mini_mode", True)
            self.update_mode_visibility()

    def toggle_mode(self):
        """Toggle between Mini capsule and Expanded card."""
        if self.is_mini:
            self.expand_to_full()
        else:
            self.collapse_to_mini()

    def changeEvent(self, event):
        """Auto-collapse to mini capsule when losing window focus (clicking elsewhere)."""
        if event.type() == QEvent.ActivationChange:
            if not self.isActiveWindow() and not self.is_mini:
                # Do not collapse if user is interacting with settings dialog or menus
                if not self.findChildren(QDialog) and not QApplication.activeModalWidget():
                    self.collapse_to_mini()
        super().changeEvent(event)

    def update_mode_visibility(self):
        """Instant toggle between mini and expanded views with zero lag."""
        base_w = int(240 * self.widget_scale)
        if self.is_mini:
            self.expanded_container.hide()
            self.mini_container.show()
            self.setFixedSize(int(215 * self.widget_scale), int(42 * self.widget_scale))
        else:
            self.mini_container.hide()
            self.expanded_container.show()
            self.setFixedWidth(base_w)
            self.setMinimumHeight(150)
            self.setMaximumHeight(800)
            self.adjustSize()

    def set_scale(self, scale_val: float):
        """Set UI size scale."""
        self.widget_scale = scale_val
        self.cfg.set("scale", scale_val)
        self.update_mode_visibility()

    def apply_theme_and_opacity(self):
        """Apply configured opacity."""
        opacity = self.cfg.get("opacity", 0.95)
        self.setWindowOpacity(float(opacity))

    def restore_position(self):
        """Restore saved window coordinates or place near top-right."""
        pos = self.cfg.get("window_pos")
        screen = QApplication.primaryScreen().availableGeometry()
        if pos and len(pos) == 2:
            x = max(screen.left() + 10, min(pos[0], screen.right() - 240))
            y = max(screen.top() + 10, min(pos[1], screen.bottom() - 150))
            self.move(x, y)
        else:
            self.move(screen.right() - 250, screen.top() + 80)

    def setup_timers(self):
        """Setup non-blocking timers."""
        # 1. Bluetooth timer
        self.bt_timer = QTimer(self)
        self.bt_timer.timeout.connect(self.scan_bluetooth_async)
        bt_sec = max(3, int(self.cfg.get("bt_interval_sec", 10)))
        self.bt_timer.start(bt_sec * 1000)
        
        # 2. Codex Quota timer
        self.codex_timer = QTimer(self)
        self.codex_timer.timeout.connect(lambda: self.fetch_codex_async(force=False))
        cdx_sec = max(20, int(self.cfg.get("codex_interval_sec", 60)))
        self.codex_timer.start(cdx_sec * 1000)
        
        # 3. Status Light & Activity timer (1s interval)
        self.activity_timer = QTimer(self)
        self.activity_timer.timeout.connect(self.check_codex_activity_fast)
        self.activity_timer.start(1000)

    # -------------------------------------------------------------
    # Fast Activity & Data Methods
    # -------------------------------------------------------------
    def check_codex_activity_fast(self):
        """Accurate activity check based on real-time Codex session event logs (zero jitter)."""
        is_running, _ = self.activity_tracker.check_is_running()
        self._set_status_light_running(is_running)

    def _set_status_light_running(self, running: bool):
        """Update both mini and expanded status lights."""
        self.mini_status_light.set_running_state(running)
        self.codex_view.set_codex_running_state(running)

    def refresh_all_data(self, force: bool = True):
        """Trigger async scan for Bluetooth and Codex."""
        self.scan_bluetooth_async()
        self.fetch_codex_async(force=force)

    def scan_bluetooth_async(self):
        """Asynchronously scan Bluetooth devices in background thread."""
        if self._bt_worker and self._bt_worker.isRunning():
            return
            
        only_conn = self.cfg.get("only_connected", True)
        self._bt_worker = BluetoothScanWorker(only_connected=only_conn)
        self._bt_worker.devices_ready.connect(self.on_bluetooth_devices_received)
        self._bt_worker.start()

    def on_bluetooth_devices_received(self, devices: List[Dict[str, Any]]):
        """Receive devices from background worker without blocking UI."""
        self._current_devices = devices
        self.battery_view.update_devices(devices)
        
        if devices:
            # Priority 1: Vibe Coding with DJI Mic Mini / DJI Mic (always pinned to front)
            dji_dev = next((d for d in devices if "dji" in d.get("name", "").lower()), None)
            if not dji_dev:
                dji_dev = next((d for d in devices if "mic" in d.get("name", "").lower()), None)
            if dji_dev:
                target_dev = dji_dev
            else:
                # Priority 2: Fallback to the connected device with the lowest battery
                target_dev = min(devices, key=lambda x: x.get("battery", 100))
                
            icon = target_dev.get("icon", "📶")
            bat = target_dev.get("battery", 0)
            color = target_dev.get("status_color", "#10B981")
            
            self.mini_bt_lbl.setText(f"{icon} {bat}%")
            self.mini_bt_lbl.setStyleSheet(f"font-size: 10px; font-weight: 700; color: {color};")
            self.mini_bt_lbl.setToolTip(f"显示外设: {target_dev.get('name')} ({bat}%)\n(共 {len(devices)} 台设备在线)")
        else:
            self.mini_bt_lbl.setText("📶 离线")
            self.mini_bt_lbl.setStyleSheet("font-size: 10px; font-weight: 500; color: #9CA3AF;")
            self.mini_bt_lbl.setToolTip("无在线蓝牙设备")
            
        if not self.is_mini:
            self.adjustSize()

    def fetch_codex_async(self, force: bool = False):
        """Run async thread for ChatGPT/Codex quota lookup."""
        if self._codex_worker and self._codex_worker.isRunning():
            return
            
        self._codex_worker = CodexFetchWorker(self.codex_client, force=force)
        self._codex_worker.data_ready.connect(self.on_codex_data_received)
        self._codex_worker.start()

    def on_codex_data_received(self, data: Dict[str, Any]):
        """Callback when Codex data arrives."""
        self._current_codex_data = data
        self.codex_view.update_data(data)
        self.update_mini_quota_display()
            
        if not self.is_mini:
            self.adjustSize()

    def update_mini_quota_display(self):
        """Render mini quota with concise 100% · 84% format and dynamic health colors."""
        data = self._current_codex_data
        if not data or not data.get("success"):
            self.mini_cdx_lbl.setText("🤖 异常")
            self.mini_cdx_lbl.setStyleSheet("font-size: 10px; font-weight: 700; color: #EF4444;")
            self.mini_cdx_lbl.setToolTip("ChatGPT 状态: 获取失败")
            return

        five_h = data.get("five_hour_window")
        weekly = data.get("weekly_window") or data.get("primary_window")
        
        fh_rem = five_h.get("remaining_percent", 100) if five_h else None
        wk_rem = weekly.get("remaining_percent", 100) if weekly else None
        
        col_5h = get_health_color(fh_rem) if fh_rem is not None else "#10B981"
        col_wk = get_health_color(wk_rem) if wk_rem is not None else "#10B981"
        
        # Super clean display: 🤖 100% · 84% (Left is 5H, Right is Week)
        if five_h and weekly:
            html = f'🤖 <span style="color:{col_5h};font-weight:700;">{fh_rem}%</span> · <span style="color:{col_wk};font-weight:700;">{wk_rem}%</span>'
        elif weekly:
            html = f'🤖 <span style="color:{col_wk};font-weight:700;">{wk_rem}%</span>'
        elif five_h:
            html = f'🤖 <span style="color:{col_5h};font-weight:700;">{fh_rem}%</span>'
        else:
            html = '🤖 正常'

        self.mini_cdx_lbl.setText(html)
        
        tip_lines = [f"ChatGPT {data.get('plan_type','PLUS')}"]
        if five_h:
            tip_lines.append(f"• 5H 剩余: {fh_rem}% (倒计时: {five_h.get('reset_countdown','')})")
        if weekly:
            tip_lines.append(f"• 周限额 剩余: {wk_rem}% (倒计时: {weekly.get('reset_countdown','')})")
        self.mini_cdx_lbl.setToolTip("\n".join(tip_lines))

    # -------------------------------------------------------------
    # Mouse Dragging & Click-to-Expand Interaction
    # -------------------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self.is_locked:
            self._is_dragging = False
            self._press_global_pos = event.globalPos()
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if (event.buttons() & Qt.LeftButton) and not self.is_locked:
            delta = (event.globalPos() - self._press_global_pos).manhattanLength()
            if delta > 4:
                self._is_dragging = True
                self.move(event.globalPos() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            # If clicked without dragging while in mini capsule mode -> Expand!
            if not self._is_dragging and self.is_mini:
                self.expand_to_full()
            elif self._is_dragging:
                self._is_dragging = False
                if self.cfg.get("auto_snap", True):
                    self.snap_to_screen_edge()
                pos = self.pos()
                self.cfg.set("window_pos", [pos.x(), pos.y()])
            event.accept()

    def snap_to_screen_edge(self):
        """Snap window to edge if within 25px threshold."""
        screen = QApplication.primaryScreen().availableGeometry()
        geo = self.frameGeometry()
        snap_threshold = 25
        
        new_x = geo.x()
        new_y = geo.y()
        
        if abs(geo.left() - screen.left()) < snap_threshold:
            new_x = screen.left() + 6
        elif abs(geo.right() - screen.right()) < snap_threshold:
            new_x = screen.right() - geo.width() - 6
            
        if abs(geo.top() - screen.top()) < snap_threshold:
            new_y = screen.top() + 6
        elif abs(geo.bottom() - screen.bottom()) < snap_threshold:
            new_y = screen.bottom() - geo.height() - 6
            
        self.move(new_x, new_y)

    # -------------------------------------------------------------
    # Context Menu & Settings
    # -------------------------------------------------------------
    def contextMenuEvent(self, event):
        """Show modern dark right-click menu."""
        menu = QMenu(self)
        menu.setStyleSheet(MAIN_STYLESHEET)
        
        act_mode = menu.addAction("💊 切换为迷你胶囊" if not self.is_mini else "📖 展开详细面板")
        act_mode.triggered.connect(self.toggle_mode)
        
        menu.addSeparator()
        
        # Size Scaling Submenu
        size_menu = menu.addMenu("📏 窗口缩放尺寸")
        for label, scale_v in [("紧凑 (85%)", 0.85), ("标准 (100%)", 1.0), ("放大 (115%)", 1.15)]:
            act_s = size_menu.addAction(label)
            act_s.setCheckable(True)
            act_s.setChecked(abs(self.widget_scale - scale_v) < 0.05)
            act_s.triggered.connect(lambda checked, s=scale_v: self.set_scale(s))
        
        menu.addSeparator()
        
        is_top = self.cfg.get("always_on_top", True)
        act_top = menu.addAction("📌 窗口置顶" + (" (已开启)" if is_top else " (已关闭)"))
        act_top.setCheckable(True)
        act_top.setChecked(is_top)
        act_top.triggered.connect(self.toggle_stay_on_top)
        
        act_lock = menu.addAction("🔒 锁定窗口位置" + (" (已锁定)" if self.is_locked else ""))
        act_lock.setCheckable(True)
        act_lock.setChecked(self.is_locked)
        act_lock.triggered.connect(self.toggle_lock_position)
        
        menu.addSeparator()
        
        act_refresh = menu.addAction("🔄 立即刷新数据")
        act_refresh.triggered.connect(lambda: self.refresh_all_data(force=True))
        
        act_settings = menu.addAction("⚙️ 偏好设置...")
        act_settings.triggered.connect(self.open_settings)
        
        menu.addSeparator()
        
        act_hide = menu.addAction("🗕 隐藏到系统托盘")
        act_hide.triggered.connect(self.hide)
        
        act_exit = menu.addAction("✕ 退出程序")
        act_exit.triggered.connect(QApplication.instance().quit)
        
        menu.exec_(QCursor.pos())

    def toggle_stay_on_top(self):
        """Toggle stay on top flag dynamically."""
        curr = self.cfg.get("always_on_top", True)
        new_val = not curr
        self.cfg.set("always_on_top", new_val)
        
        pos = self.pos()
        self.init_window_flags()
        self.move(pos)
        self.show()

    def toggle_lock_position(self):
        """Toggle mouse drag locking."""
        self.is_locked = not self.is_locked
        self.cfg.set("lock_position", self.is_locked)

    def open_settings(self):
        """Open settings dialog."""
        dlg = SettingsDialog(self.cfg, self)
        dlg.settings_saved.connect(self.on_settings_applied)
        dlg.exec_()

    def on_settings_applied(self):
        """Reload timers and styles after settings saved."""
        self.apply_theme_and_opacity()
        
        bt_sec = max(3, int(self.cfg.get("bt_interval_sec", 10)))
        self.bt_timer.setInterval(bt_sec * 1000)
        
        cdx_sec = max(20, int(self.cfg.get("codex_interval_sec", 60)))
        self.codex_timer.setInterval(cdx_sec * 1000)
        
        self.codex_client = CodexUsageClient(self.cfg.get("auth_file_path"))
        self.refresh_all_data(force=True)
