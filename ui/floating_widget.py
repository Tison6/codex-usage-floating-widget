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
from core.square_client import SquareAPIClient
from core.aihub_client import AIHubClient
from core.server_monitor import MultiServerMonitor, get_hex_for_cpu
from core.gpu_monitor import GPUMonitor, get_hex_for_gpu_vram
from ui.battery_view import BatteryView
from ui.codex_view import CodexQuotaView
from ui.status_light import CodexStatusLight
from ui.settings_dialog import SettingsDialog
from ui.relay_view import RelayStationView
from ui.gpu_view import GPUServerView
from ui.pelican_viewer import PelicanViewerDialog
from ui.icons import get_openai_pixmap, get_cpu_pixmap, get_nvidia_pixmap
from ui.styles import MAIN_STYLESHEET, get_main_stylesheet


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


class RelayFetchWorker(QThread):
    """Background worker to query Square API and AIHub without freezing UI."""
    square_ready = pyqtSignal(dict)
    aihub_ready = pyqtSignal(dict)

    def __init__(self, square_client: SquareAPIClient, aihub_client: AIHubClient, force: bool = False):
        super().__init__()
        self.sq_client = square_client
        self.ai_client = aihub_client
        self.force = force

    def run(self):
        try:
            sq = self.sq_client.fetch_data(force=self.force)
            self.square_ready.emit(sq)
        except Exception as e:
            self.square_ready.emit({"success": False, "error": str(e)})

        try:
            ai = self.ai_client.fetch_data(force=self.force)
            self.aihub_ready.emit(ai)
        except Exception as e:
            self.aihub_ready.emit({"success": False, "error": str(e)})


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
        self._relay_worker: Optional[RelayFetchWorker] = None
        self.activity_tracker = CodexActivityTracker(self.cfg.get("codex_home"))
        
        # Relay Station clients
        self.square_client = SquareAPIClient(self.cfg.get("square_api_key"), config=self.cfg)
        self.aihub_client = AIHubClient(
            config=self.cfg,
            email=self.cfg.get("aihub_email", ""),
            password=self.cfg.get("aihub_password", ""),
        )
        
        # Multi-Server CPU Monitor (quad, e5, 8375c)
        self.server_monitor = MultiServerMonitor(self.cfg.get("servers", None))
        self.server_monitor.servers_updated.connect(self.on_server_cpu_updated)
        self.server_monitor.start()

        # Multi-Server GPU Monitor (D:/gpu_history.db)
        self.gpu_monitor = GPUMonitor()
        self.gpu_monitor.realtime_updated.connect(self.on_gpu_data_updated)
        self.gpu_monitor.start()
        
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
        self.setStyleSheet(get_main_stylesheet(self.widget_scale))

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
        self.title_icon.setStyleSheet(f"font-size: {max(8, int(round(11 * self.widget_scale)))}px;")
        
        self.title_text = QLabel("状态小组件", self.expanded_container)
        self.title_text.setProperty("class", "TitleLabel")
        
        btn_sz = max(14, int(round(18 * self.widget_scale)))
        self.btn_mini_toggle = QPushButton("➖", self.expanded_container)
        self.btn_mini_toggle.setProperty("class", "IconButton")
        self.btn_mini_toggle.setFixedSize(btn_sz, btn_sz)
        self.btn_mini_toggle.setToolTip("收起为迷你胶囊模式")
        self.btn_mini_toggle.clicked.connect(self.collapse_to_mini)
        
        self.btn_settings = QPushButton("⚙️", self.expanded_container)
        self.btn_settings.setProperty("class", "IconButton")
        self.btn_settings.setFixedSize(btn_sz, btn_sz)
        self.btn_settings.setToolTip("偏好设置")
        self.btn_settings.clicked.connect(self.open_settings)
        
        title_bar.addWidget(self.title_icon)
        title_bar.addWidget(self.title_text)
        title_bar.addStretch()
        title_bar.addWidget(self.btn_mini_toggle)
        title_bar.addWidget(self.btn_settings)
        self.exp_layout.addLayout(title_bar)
        
        # Horizontal Three-Column Content (Left: Bluetooth + Codex, Middle: Relay Stations, Right: GPU Servers)
        self.cols_widget = QWidget(self.expanded_container)
        cols_layout = QHBoxLayout(self.cols_widget)
        cols_layout.setContentsMargins(0, 0, 0, 0)
        cols_layout.setSpacing(8)
        
        # --- Left Column: Devices & Official Codex ---
        self.left_col = QWidget(self.cols_widget)
        self.left_col.setFixedWidth(int(210 * self.widget_scale))
        left_layout = QVBoxLayout(self.left_col)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)
        
        # Bluetooth Battery View
        self.battery_view = BatteryView(self.left_col, scale=self.widget_scale)
        left_layout.addWidget(self.battery_view)
        
        # Divider Line
        divider = QFrame(self.left_col)
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet("background-color: rgba(255, 255, 255, 0.06); height: 1px; border: none;")
        left_layout.addWidget(divider)
        
        # Codex Quota View
        self.codex_view = CodexQuotaView(self.quota_tracker, self.left_col, scale=self.widget_scale)
        self.codex_view.refresh_requested.connect(lambda: self.fetch_codex_async(force=True))
        left_layout.addWidget(self.codex_view)
        left_layout.addStretch()
        cols_layout.addWidget(self.left_col)
        
        # Vertical Separator between Left and Middle
        v_sep = QFrame(self.cols_widget)
        v_sep.setFrameShape(QFrame.VLine)
        v_sep.setStyleSheet("background-color: rgba(255, 255, 255, 0.08); width: 1px; border: none;")
        cols_layout.addWidget(v_sep)
        
        # --- Middle Column: Relay Stations (Square API & AIHub) ---
        self.mid_col = QWidget(self.cols_widget)
        self.mid_col.setFixedWidth(int(485 * self.widget_scale))
        mid_layout = QVBoxLayout(self.mid_col)
        mid_layout.setContentsMargins(0, 0, 0, 0)
        mid_layout.setSpacing(6)
        
        self.relay_view = RelayStationView(self.mid_col, scale=self.widget_scale)
        self.relay_view.pelican_clicked.connect(self.open_pelican_viewer)
        self.relay_view.filter_dialog_requested.connect(self.open_square_filter_dialog)
        self.relay_view.aihub_filter_requested.connect(self.open_aihub_filter_dialog)
        self.relay_view.aihub_mode_toggled.connect(self.on_aihub_mode_toggled)
        self.relay_view.refresh_requested.connect(lambda: self.fetch_relay_async(force=True))
        mid_layout.addWidget(self.relay_view)
        mid_layout.addStretch()
        cols_layout.addWidget(self.mid_col)

        # Vertical Separator between Middle and Right
        v_sep2 = QFrame(self.cols_widget)
        v_sep2.setFrameShape(QFrame.VLine)
        v_sep2.setStyleSheet("background-color: rgba(255, 255, 255, 0.08); width: 1px; border: none;")
        cols_layout.addWidget(v_sep2)

        # --- Right Column: GPU Servers (matching dark aesthetic of left column) ---
        self.right_col = QWidget(self.cols_widget)
        self.right_col.setFixedWidth(int(295 * self.widget_scale))
        right_layout = QVBoxLayout(self.right_col)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        self.gpu_view = GPUServerView(self.gpu_monitor, self.right_col, scale=self.widget_scale)
        right_layout.addWidget(self.gpu_view)
        cols_layout.addWidget(self.right_col)
        
        self.exp_layout.addWidget(self.cols_widget)
        self.root_layout.addWidget(self.expanded_container)
        
        # -------------------------------------------------------------
        # 2. Mini Mode Container (2-row compact layout, click anywhere to expand)
        # -------------------------------------------------------------
        self.mini_container = QWidget(self)
        self.mini_container.setObjectName("MiniWidget")
        self.mini_container.setCursor(Qt.PointingHandCursor)
        self.mini_container.setToolTip("点击展开状态小组件 (按住可自由拖拽)")
        
        self.mini_vbox = QVBoxLayout(self.mini_container)
        self.mini_vbox.setContentsMargins(6, 2, 6, 2)
        self.mini_vbox.setSpacing(1)

        # === Row 1 (Top): 1 BT + 5 GPUs ===
        self.row1_layout = QHBoxLayout()
        self.row1_layout.setContentsMargins(0, 0, 0, 0)
        self.row1_layout.setSpacing(max(1, int(round(2 * self.widget_scale))))

        self.mini_bt_lbl = QLabel("📶 --", self.mini_container)

        self.mini_sep1 = QLabel("|", self.mini_container)

        self.mini_nvidia_icon = QLabel(self.mini_container)
        self.mini_nvidia_icon.setToolTip("GPU 显存占用 (7号 L40S x3 · 8号 A100 x2)")

        # 5 GPU card labels (7号: 0, 1, 2; 8号: 0, 1) interleaved with '·'
        self.mini_gpu_0 = QLabel("--", self.mini_container)
        self.mini_gpu_1 = QLabel("--", self.mini_container)
        self.mini_gpu_2 = QLabel("--", self.mini_container)
        self.mini_gpu_3 = QLabel("--", self.mini_container)
        self.mini_gpu_4 = QLabel("--", self.mini_container)

        self.mini_gpu_labels = [
            self.mini_gpu_0, self.mini_gpu_1, self.mini_gpu_2,
            self.mini_gpu_3, self.mini_gpu_4
        ]

        self.row1_layout.addWidget(self.mini_bt_lbl)
        self.row1_layout.addWidget(self.mini_sep1)
        self.row1_layout.addWidget(self.mini_nvidia_icon)

        self.mini_gpu_dots = []
        for i, lbl in enumerate(self.mini_gpu_labels):
            if i > 0:
                dot = QLabel("·", self.mini_container)
                self.mini_gpu_dots.append(dot)
                self.row1_layout.addWidget(dot)
            self.row1_layout.addWidget(lbl)

        self.row1_layout.addStretch()
        self.mini_vbox.addLayout(self.row1_layout)

        # === Row 2 (Bottom): 2 OpenAI Quotas + Spinner + 3 CPUs ===
        self.row2_layout = QHBoxLayout()
        self.row2_layout.setContentsMargins(0, 0, 0, 0)
        self.row2_layout.setSpacing(max(1, int(round(2 * self.widget_scale))))

        self.mini_openai_icon = QLabel(self.mini_container)
        self.mini_openai_icon.setToolTip("ChatGPT / Codex 剩余限额")

        self.mini_cdx_5h = QLabel("--", self.mini_container)
        self.mini_cdx_dot = QLabel("·", self.mini_container)
        self.mini_cdx_wk = QLabel("--", self.mini_container)
        self.mini_status_light = CodexStatusLight(self.mini_container, size=max(8, int(round(13 * self.widget_scale))))

        self.mini_sep2 = QLabel("|", self.mini_container)

        self.mini_cpu_icon = QLabel(self.mini_container)
        self.mini_cpu_icon.setToolTip("服务器 CPU 利用率 (quad / e5 / 8375c)")

        self.mini_srv_quad = QLabel("--", self.mini_container)
        self.mini_srv_e5 = QLabel("--", self.mini_container)
        self.mini_srv_8375c = QLabel("--", self.mini_container)

        self.mini_srv_labels = {
            "quad": self.mini_srv_quad,
            "e5": self.mini_srv_e5,
            "8375c": self.mini_srv_8375c,
        }

        self.row2_layout.addWidget(self.mini_openai_icon)
        self.row2_layout.addWidget(self.mini_cdx_5h)
        self.row2_layout.addWidget(self.mini_cdx_dot)
        self.row2_layout.addWidget(self.mini_cdx_wk)
        self.row2_layout.addWidget(self.mini_status_light)
        self.row2_layout.addWidget(self.mini_sep2)
        self.row2_layout.addWidget(self.mini_cpu_icon)

        self.mini_srv_dots = []
        srv_keys = ["quad", "e5", "8375c"]
        for i, sid in enumerate(srv_keys):
            if i > 0:
                dot = QLabel("·", self.mini_container)
                self.mini_srv_dots.append(dot)
                self.row2_layout.addWidget(dot)
            self.row2_layout.addWidget(self.mini_srv_labels[sid])

        self.row2_layout.addStretch()
        self.mini_vbox.addLayout(self.row2_layout)

        # Ensure clicks anywhere on labels or status light trigger container expand
        all_mini_widgets = [
            self.mini_bt_lbl, self.mini_sep1, self.mini_nvidia_icon,
            *self.mini_gpu_labels, *self.mini_gpu_dots,
            self.mini_openai_icon, self.mini_cdx_5h, self.mini_cdx_dot, self.mini_cdx_wk,
            self.mini_status_light, self.mini_sep2, self.mini_cpu_icon,
            *self.mini_srv_labels.values(), *self.mini_srv_dots
        ]
        for w in all_mini_widgets:
            w.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            
        self.mini_container.mousePressEvent = self.mousePressEvent
        self.mini_container.mouseMoveEvent = self.mouseMoveEvent
        self.mini_container.mouseReleaseEvent = self.mouseReleaseEvent
        
        self.root_layout.addWidget(self.mini_container)
        
        # Apply scaled styling to mini labels & icons
        self.update_mini_scale_styling()
        
        # Apply initial mode display
        self.update_mode_visibility()

    def get_mini_font_size(self, base_px: int = 10) -> int:
        """Calculate scaled font size for mini capsule items."""
        return max(7, int(round(base_px * self.widget_scale + 1e-5)))

    def update_mini_scale_styling(self):
        """Update fonts, icon sizes, and layout paddings for mini capsule based on scale."""
        if not hasattr(self, "mini_container"):
            return

        # 1. Margins and Spacing
        pad_x = max(3, int(round(5 * self.widget_scale)))
        pad_y = max(1, int(round(2 * self.widget_scale)))
        self.mini_vbox.setContentsMargins(pad_x, pad_y, pad_x, pad_y)
        self.mini_vbox.setSpacing(max(1, int(round(1 * self.widget_scale))))
        
        spacing = max(1, int(round(2 * self.widget_scale)))
        self.row1_layout.setSpacing(spacing)
        self.row2_layout.setSpacing(spacing)

        # 2. Icon sizes
        icon_sz = max(9, int(round(13 * self.widget_scale)))
        self.mini_nvidia_icon.setPixmap(get_nvidia_pixmap(icon_sz))
        self.mini_openai_icon.setPixmap(get_openai_pixmap(icon_sz))
        self.mini_cpu_icon.setPixmap(get_cpu_pixmap(icon_sz))

        # 3. Separators & Dots
        sep_fs = self.get_mini_font_size(9)
        dot_fs = self.get_mini_font_size(9)
        sep_style = f"font-size: {sep_fs}px; color: #4B5563; font-weight: 400;"
        dot_style = f"font-size: {dot_fs}px; color: #6B7280; font-weight: 400;"

        self.mini_sep1.setStyleSheet(sep_style)
        self.mini_sep2.setStyleSheet(sep_style)
        self.mini_cdx_dot.setStyleSheet(dot_style)
        for dot in self.mini_gpu_dots:
            dot.setStyleSheet(dot_style)
        for dot in self.mini_srv_dots:
            dot.setStyleSheet(dot_style)

        # 4. Status Light Size
        st_sz = max(8, int(round(13 * self.widget_scale)))
        self.mini_status_light.set_size(st_sz)

        # 5. Re-render labels with new scaled font sizes
        self._render_mini_bluetooth()
        self.update_mini_quota_display()
        self._render_mini_server_cpu()
        self._render_mini_gpu()

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
        base_w = int(round(1055 * self.widget_scale))
        if self.is_mini:
            self.root_layout.setContentsMargins(2, 2, 2, 2)
            self.expanded_container.hide()
            self.mini_container.show()
            self.setFixedSize(int(round(156 * self.widget_scale)), int(round(37 * self.widget_scale)))
        else:
            self.root_layout.setContentsMargins(6, 6, 6, 6)
            self.mini_container.hide()
            self.expanded_container.show()
            self.setFixedWidth(base_w)
            self.setMinimumHeight(150)
            self.setMaximumHeight(16777215)
            self.adjustSize()

    def set_scale(self, scale_val: float):
        """Set UI size scale and dynamically recompute all fonts, margins, and subviews."""
        self.widget_scale = float(scale_val)
        self.cfg.set("scale", self.widget_scale)
        
        # 1. Update window-level QSS stylesheet (dynamically scales all standard fonts)
        self.setStyleSheet(get_main_stylesheet(self.widget_scale))
        
        # 2. Update title bar buttons and icon
        title_fs = max(8, int(round(11 * self.widget_scale)))
        self.title_icon.setStyleSheet(f"font-size: {title_fs}px;")
        btn_sz = max(14, int(round(18 * self.widget_scale)))
        self.btn_mini_toggle.setFixedSize(btn_sz, btn_sz)
        self.btn_settings.setFixedSize(btn_sz, btn_sz)
        
        # 3. Update column fixed widths
        if hasattr(self, "left_col"):
            self.left_col.setFixedWidth(int(round(210 * self.widget_scale)))
        if hasattr(self, "mid_col"):
            self.mid_col.setFixedWidth(int(round(485 * self.widget_scale)))
        if hasattr(self, "right_col"):
            self.right_col.setFixedWidth(int(round(295 * self.widget_scale)))
            
        # 4. Notify subviews to update their custom internal fonts and item heights
        if hasattr(self, "battery_view") and hasattr(self.battery_view, "set_scale"):
            self.battery_view.set_scale(self.widget_scale)
        if hasattr(self, "codex_view") and hasattr(self.codex_view, "set_scale"):
            self.codex_view.set_scale(self.widget_scale)
        if hasattr(self, "relay_view") and hasattr(self.relay_view, "set_scale"):
            self.relay_view.set_scale(self.widget_scale)
        if hasattr(self, "gpu_view") and hasattr(self.gpu_view, "set_scale"):
            self.gpu_view.set_scale(self.widget_scale)
            
        # 5. Update mini capsule fonts, icon pixmaps, and spacings
        self.update_mini_scale_styling()
        
        # 6. Re-apply mode visibility and geometry
        self.update_mode_visibility()

    def apply_theme_and_opacity(self):
        """Apply configured opacity."""
        opacity = self.cfg.get("opacity", 0.95)
        self.setWindowOpacity(float(opacity))

    def restore_position(self):
        """Restore saved window coordinates or place near top-right."""
        pos = self.cfg.get("window_pos")
        screen = QApplication.primaryScreen().availableGeometry()
        expected_w = int(round(1055 * self.widget_scale)) if not self.is_mini else int(round(156 * self.widget_scale))
        if pos and len(pos) == 2:
            x = max(screen.left() + 10, min(pos[0], screen.right() - expected_w))
            y = max(screen.top() + 10, min(pos[1], screen.bottom() - 150))
            self.move(x, y)
        else:
            self.move(screen.right() - expected_w - 20, screen.top() + 80)

    def setup_timers(self):
        """Setup non-blocking timers."""
        # 1. Bluetooth timer
        self.bt_timer = QTimer(self)
        self.bt_timer.timeout.connect(self.scan_bluetooth_async)
        bt_sec = max(3, int(self.cfg.get("bt_interval_sec", 10)))
        self.bt_timer.start(bt_sec * 1000)
        
        # 2. Codex Quota timer (every minute)
        self.codex_timer = QTimer(self)
        self.codex_timer.timeout.connect(lambda: self.fetch_codex_async(force=True))
        cdx_sec = max(20, int(self.cfg.get("codex_interval_sec", 60)))
        self.codex_timer.start(cdx_sec * 1000)
        
        # 3. Status Light & Activity timer (1s interval)
        self.activity_timer = QTimer(self)
        self.activity_timer.timeout.connect(self.check_codex_activity_fast)
        self.activity_timer.start(1000)

        # 4. Relay Station timer (Square API & AIHub, every minute)
        self.relay_timer = QTimer(self)
        self.relay_timer.timeout.connect(lambda: self.fetch_relay_async(force=True))
        relay_sec = max(20, int(self.cfg.get("relay_interval_sec", 60)))
        self.relay_timer.start(relay_sec * 1000)

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
        """Trigger async scan for Bluetooth, Codex, and Relay Stations."""
        self.scan_bluetooth_async()
        self.fetch_codex_async(force=force)
        self.fetch_relay_async(force=force)

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
        self._render_mini_bluetooth()
        if not self.is_mini:
            self.adjustSize()

    def _render_mini_bluetooth(self):
        """Render Bluetooth device battery in mini capsule."""
        devices = getattr(self, "_current_devices", [])
        fs = self.get_mini_font_size(10)
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
            
            self.mini_bt_lbl.setText(f"{icon} {bat}")
            self.mini_bt_lbl.setStyleSheet(f"font-size: {fs}px; font-weight: 700; color: {color};")
            self.mini_bt_lbl.setToolTip(f"显示外设: {target_dev.get('name')} ({bat}%)\n(共 {len(devices)} 台设备在线)")
        else:
            self.mini_bt_lbl.setText("📶 --")
            self.mini_bt_lbl.setStyleSheet(f"font-size: {fs}px; font-weight: 700; color: #9CA3AF;")
            self.mini_bt_lbl.setToolTip("无在线蓝牙设备")

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
        
        # If fetch failed (transient network or proxy hiccup), schedule a fast retry in 5s
        if not data.get("success"):
            QTimer.singleShot(5000, lambda: self.fetch_codex_async(force=True))
            
        if not self.is_mini:
            self.adjustSize()

    def fetch_relay_async(self, force: bool = False):
        """Asynchronously fetch Square API and AIHub data in background."""
        if self._relay_worker and self._relay_worker.isRunning():
            return
            
        self._relay_worker = RelayFetchWorker(self.square_client, self.aihub_client, force=force)
        self._relay_worker.square_ready.connect(self.on_square_data_received)
        self._relay_worker.aihub_ready.connect(self.on_aihub_data_received)
        self._relay_worker.start()

    def on_square_data_received(self, data: Dict[str, Any]):
        """Render Square API data."""
        self.relay_view.update_square_data(data)
        if not self.is_mini:
            self.adjustSize()

    def on_aihub_data_received(self, data: Dict[str, Any]):
        """Render AIHub data."""
        self.relay_view.update_aihub_data(data)
        if not self.is_mini:
            self.adjustSize()

    def on_aihub_mode_toggled(self, new_mode: bool):
        """Handle user toggling between AIHub automatic filter mode and manual checked mode."""
        self.aihub_client.set_auto_mode(new_mode)
        self.fetch_relay_async(force=True)

    def open_pelican_viewer(self, provider_item_or_images=None, code=""):
        """Open Pelican Test Image Viewer dialog with all historical images loaded dynamically online."""
        if hasattr(self, "_pelican_dlg") and self._pelican_dlg is not None:
            try:
                if self._pelican_dlg.isVisible():
                    self._pelican_dlg.raise_()
                    self._pelican_dlg.activateWindow()
                    return
            except Exception:
                self._pelican_dlg = None

        from ui.pelican_viewer import PelicanViewerDialog
        dlg = PelicanViewerDialog(provider_item_or_images, aihub_client=self.aihub_client, operator_code=code, parent=self)
        self._pelican_dlg = dlg
        try:
            dlg.exec_()
        finally:
            self._pelican_dlg = None

    def open_square_filter_dialog(self):
        """Open Square API interactive group and model filter selection dialog."""
        from ui.square_filter_dialog import SquareFilterDialog
        dlg = SquareFilterDialog(self.square_client, parent=self)
        dlg.filters_changed.connect(lambda: self.fetch_relay_async(force=True))
        dlg.exec_()

    def open_aihub_filter_dialog(self):
        """Open AIHub interactive provider filter selection dialog with live stats."""
        from ui.square_filter_dialog import AIHubFilterDialog
        dlg = AIHubFilterDialog(self.aihub_client, parent=self)
        dlg.filters_changed.connect(lambda: self.fetch_relay_async(force=True))
        dlg.exec_()

    def update_mini_quota_display(self):
        """Render mini quota with concise 5H · Week format and dynamic health colors."""
        data = self._current_codex_data
        fs = self.get_mini_font_size(10)
        if not data or not data.get("success"):
            self.mini_cdx_5h.setText("--")
            self.mini_cdx_5h.setStyleSheet(f"font-size: {fs}px; font-weight: 700; color: #EF4444;")
            self.mini_cdx_dot.hide()
            self.mini_cdx_wk.hide()
            self.mini_cdx_5h.setToolTip("ChatGPT 状态: 获取失败")
            self.mini_openai_icon.setToolTip("ChatGPT 状态: 获取失败")
            return

        five_h = data.get("five_hour_window")
        weekly = data.get("weekly_window") or data.get("primary_window")
        
        fh_rem = five_h.get("remaining_percent", 100) if five_h else None
        wk_rem = weekly.get("remaining_percent", 100) if weekly else None
        
        col_5h = get_health_color(fh_rem) if fh_rem is not None else "#10B981"
        col_wk = get_health_color(wk_rem) if wk_rem is not None else "#10B981"
        
        if five_h and weekly:
            self.mini_cdx_5h.setText(str(fh_rem))
            self.mini_cdx_5h.setStyleSheet(f"font-size: {fs}px; font-weight: 700; color: {col_5h};")
            self.mini_cdx_5h.show()
            self.mini_cdx_dot.show()
            self.mini_cdx_wk.setText(str(wk_rem))
            self.mini_cdx_wk.setStyleSheet(f"font-size: {fs}px; font-weight: 700; color: {col_wk};")
            self.mini_cdx_wk.show()
        elif weekly:
            self.mini_cdx_5h.setText(str(wk_rem))
            self.mini_cdx_5h.setStyleSheet(f"font-size: {fs}px; font-weight: 700; color: {col_wk};")
            self.mini_cdx_5h.show()
            self.mini_cdx_dot.hide()
            self.mini_cdx_wk.hide()
        elif five_h:
            self.mini_cdx_5h.setText(str(fh_rem))
            self.mini_cdx_5h.setStyleSheet(f"font-size: {fs}px; font-weight: 700; color: {col_5h};")
            self.mini_cdx_5h.show()
            self.mini_cdx_dot.hide()
            self.mini_cdx_wk.hide()
        else:
            self.mini_cdx_5h.setText("OK")
            self.mini_cdx_5h.setStyleSheet(f"font-size: {fs}px; font-weight: 700; color: #10B981;")
            self.mini_cdx_dot.hide()
            self.mini_cdx_wk.hide()

        tip_lines = [f"ChatGPT {data.get('plan_type','PLUS')}"]
        if five_h:
            tip_lines.append(f"• 5H 剩余: {fh_rem}% (倒计时: {five_h.get('reset_countdown','')})")
        if weekly:
            tip_lines.append(f"• 周限额 剩余: {wk_rem}% (倒计时: {weekly.get('reset_countdown','')})")
        tooltip = "\n".join(tip_lines)
        self.mini_cdx_5h.setToolTip(tooltip)
        self.mini_cdx_wk.setToolTip(tooltip)
        self.mini_openai_icon.setToolTip(tooltip)

    def on_server_cpu_updated(self, data: Dict[str, float]):
        """Update mini capsule with 3 server CPU utilization values (quad, e5, 8375c)."""
        self._current_server_cpu = data
        self._render_mini_server_cpu()

    def _render_mini_server_cpu(self):
        """Render server CPU values in mini capsule."""
        data = getattr(self, "_current_server_cpu", {})
        fs = self.get_mini_font_size(10)
        tip_parts = []
        for sid in ["quad", "e5", "8375c"]:
            val = data.get(sid, -1.0)
            lbl = self.mini_srv_labels.get(sid)
            if not lbl:
                continue
            if val < 0:
                lbl.setText("--")
                lbl.setStyleSheet(f"font-size: {fs}px; font-weight: 700; color: #64748B;")
                tip_parts.append(f"{sid}: 离线")
            else:
                num_str = f"{int(round(val))}"
                color = get_hex_for_cpu(val)
                lbl.setText(num_str)
                lbl.setStyleSheet(f"font-size: {fs}px; font-weight: 700; color: {color};")
                tip_parts.append(f"{sid}: {val:.1f}%")

        tooltip = "服务器CPU利用率 (quad / e5 / 8375c)\n" + " | ".join(tip_parts)
        self.mini_cpu_icon.setToolTip(tooltip)
        for lbl in self.mini_srv_labels.values():
            lbl.setToolTip(tooltip)

    def on_gpu_data_updated(self, data: Dict[str, Any]):
        """Render GPU mini stats and refresh expanded view."""
        self._current_gpu_data = data
        self._render_mini_gpu()
        if not self.is_mini:
            self.adjustSize()

    def _render_mini_gpu(self):
        """Render GPU card stats in mini capsule."""
        data = getattr(self, "_current_gpu_data", {})
        fs = self.get_mini_font_size(10)
        if not data or not data.get("success"):
            for lbl in self.mini_gpu_labels:
                lbl.setText("--")
                lbl.setStyleSheet(f"font-size: {fs}px; font-weight: 700; color: #64748B;")
                lbl.setToolTip("GPU: 离线")
            self.mini_nvidia_icon.setToolTip("GPU 服务器: 离线")
            return

        five_cards = data.get("five_cards", [])
        for i, lbl in enumerate(self.mini_gpu_labels):
            if i < len(five_cards):
                c = five_cards[i]
                val = c.get("val", 0)
                num_str = f"{int(round(val))}"
                lbl.setText(num_str)
                lbl.setStyleSheet(f"font-size: {fs}px; font-weight: 700; color: {c.get('color', '#64748B')};")
                lbl.setToolTip(c.get("tooltip", ""))
            else:
                lbl.setText("--")
                lbl.setStyleSheet(f"font-size: {fs}px; font-weight: 700; color: #64748B;")
                lbl.setToolTip("GPU: 无数据")

        tt = data.get("five_cards_tt", "GPU 显存占用 (7号 L40S x3 · 8号 A100 x2)")
        self.mini_nvidia_icon.setToolTip(tt)

        if not self.is_mini:
            self.adjustSize()

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
        menu.setStyleSheet(get_main_stylesheet(self.widget_scale))
        
        act_mode = menu.addAction("💊 切换为迷你胶囊" if not self.is_mini else "📖 展开详细面板")
        act_mode.triggered.connect(self.toggle_mode)
        
        menu.addSeparator()
        
        # Size Scaling Submenu
        size_menu = menu.addMenu("📏 窗口缩放尺寸")
        scale_options = [
            ("80%", 0.80),
            ("100% (标准)", 1.00),
            ("120%", 1.20),
            ("140%", 1.40),
        ]
        for label, scale_v in scale_options:
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
        act_exit.triggered.connect(self.close)
        
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
        new_scale = float(self.cfg.get("scale", 1.0))
        if abs(new_scale - self.widget_scale) > 0.001:
            self.set_scale(new_scale)

        self.apply_theme_and_opacity()
        
        bt_sec = max(3, int(self.cfg.get("bt_interval_sec", 10)))
        self.bt_timer.setInterval(bt_sec * 1000)
        
        cdx_sec = max(20, int(self.cfg.get("codex_interval_sec", 60)))
        self.codex_timer.setInterval(cdx_sec * 1000)
        
        self.codex_client = CodexUsageClient(self.cfg.get("auth_file_path"))
        self.refresh_all_data(force=True)

    def closeEvent(self, event):
        """Clean shutdown of background threads on close."""
        if hasattr(self, "server_monitor") and self.server_monitor:
            try:
                self.server_monitor.stop()
            except Exception:
                pass
        if hasattr(self, "gpu_monitor") and self.gpu_monitor:
            try:
                self.gpu_monitor.stop()
            except Exception:
                pass
        super().closeEvent(event)
