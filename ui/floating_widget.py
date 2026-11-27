"""
Main Desktop Floating Widget.
Supports frameless dragging, screen edge snapping, mini-capsule / compact expanded modes,
dynamic opacity, stay-on-top, size scaling, ChatGPT CodeX status light,
click-to-expand, auto-collapse on focus loss, and health-based color transitions.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import os
import sys
import time
import ctypes
from ctypes import wintypes
import psutil

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QSizePolicy, QMenu, QAction, QApplication, QDesktopWidget, QGraphicsDropShadowEffect, QDialog, QToolTip
)
from PyQt5.QtCore import Qt, QPoint, QTimer, QThread, pyqtSignal, QEvent, QObject
from PyQt5.QtGui import QColor, QCursor, QFont

from core.config_manager import ConfigManager
from core.bt_scanner import BluetoothScanner
from core.codex_client import CodexUsageClient
from core.claude_client import ClaudeUsageClient
from core.quota_tracker import QuotaTracker
from core.codex_activity_tracker import CodexActivityTracker
from core.claude_activity_tracker import ClaudeActivityTracker
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
from ui.icons import get_claude_pixmap, get_openai_pixmap, get_cpu_pixmap, get_nvidia_pixmap
from ui.typography import pixel_font
from ui.styles import MAIN_STYLESHEET, get_main_stylesheet


USER32 = None
if sys.platform == "win32":
    USER32 = ctypes.WinDLL("user32", use_last_error=True)
    USER32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, wintypes.UINT,
    ]
    USER32.SetWindowPos.restype = wintypes.BOOL
    USER32.IsWindowVisible.argtypes = [wintypes.HWND]
    USER32.IsWindowVisible.restype = wintypes.BOOL
    USER32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    USER32.ShowWindow.restype = wintypes.BOOL
    USER32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    USER32.SetWindowLongPtrW.restype = ctypes.c_ssize_t


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
            devs = BluetoothScanner.get_connected_devices(only_connected=self.only_connected, include_standby=True)
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


class CodexActivityWorker(QThread):
    """Check Codex activity without scanning session files on the UI thread."""
    activity_ready = pyqtSignal(bool, bool)

    def __init__(self, tracker: CodexActivityTracker, claude_tracker):
        super().__init__()
        self.tracker = tracker
        self.claude_tracker = claude_tracker

    def run(self):
        try:
            is_running, _ = self.tracker.check_is_running()
        except Exception:
            is_running = False
        try:
            claude_running, _ = self.claude_tracker.check_is_running()
        except Exception:
            claude_running = False
        self.activity_ready.emit(is_running, claude_running)


class ToolTipZOrderFilter(QObject):
    """Event filter ensuring Qt QToolTip windows always render in front of topmost frameless widgets."""
    def __init__(self, main_win):
        super().__init__(main_win)
        self.main_win = main_win

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.ToolTip:
            QTimer.singleShot(1, self.main_win.fix_tooltip_zorder)
            QTimer.singleShot(35, self.main_win.fix_tooltip_zorder)
        return False


class FloatingWidget(QWidget):
    """Frameless translucent desktop floating widget with auto-collapse & instant interaction."""
    
    def __init__(self, config_manager: ConfigManager):
        super().__init__()
        self.cfg = config_manager
        self.codex_client = CodexUsageClient(self.cfg.get("auth_file_path"))
        self.quota_tracker = QuotaTracker()
        self.claude_client = ClaudeUsageClient(self.cfg.get("claude_auth_file_path"))
        self.claude_tracker = QuotaTracker(history_name="claude_quota_history.json")
        self._claude_worker = None
        self._watched_screen = None
        self._display_update_timer = QTimer(self)
        self._display_update_timer.setSingleShot(True)
        self._display_update_timer.setInterval(300)
        self._display_update_timer.timeout.connect(self._refresh_display_metrics)
        
        # State variables
        self.is_mini = self.cfg.get("is_mini_mode", False)
        self.is_locked = self.cfg.get("lock_position", False)
        self.requested_scale = float(self.cfg.get("scale", 1.0))
        saved_pos = self.cfg.get("window_pos", [100, 100])
        screen = QApplication.screenAt(QPoint(*saved_pos)) or QApplication.primaryScreen()
        self.widget_scale = self._fit_scale(self.requested_scale, screen)

        # Tooltip Z-order event filter (prevents QToolTip from being drawn behind the topmost widget)
        self._tooltip_filter = ToolTipZOrderFilter(self)
        app_inst = QApplication.instance()
        if app_inst:
            app_inst.installEventFilter(self._tooltip_filter)
        
        self._drag_pos = QPoint()
        self._press_global_pos = QPoint()
        self._is_dragging = False
        self._user_hidden = False
        self._closing = False
        self._current_devices: List[Dict[str, Any]] = []
        self._current_codex_data: Dict[str, Any] = {}
        self._current_claude_data: Dict[str, Any] = {}
        
        # Async workers & Mature Activity tracker
        self._bt_worker: Optional[BluetoothScanWorker] = None
        self._codex_worker: Optional[CodexFetchWorker] = None
        self._relay_worker: Optional[RelayFetchWorker] = None
        self._activity_worker: Optional[CodexActivityWorker] = None
        self.activity_tracker = CodexActivityTracker(self.cfg.get("codex_home"))
        self.claude_activity_tracker = ClaudeActivityTracker()
        
        # Relay Station clients
        self.square_client = SquareAPIClient(self.cfg.get("square_api_key"), config=self.cfg)
        self.aihub_client = AIHubClient(
            config=self.cfg,
            email=self.cfg.get("aihub_email", ""),
            password=self.cfg.get("aihub_password", ""),
        )
        
        # Multi-Server CPU Monitor (quad, e5, 8375c)
        self.server_monitor = MultiServerMonitor(
            self.cfg.get("servers", []), self.cfg.get("gpu_servers", [])
        )
        self.server_monitor.servers_updated.connect(self.on_server_cpu_updated)
        self.server_monitor.start()

        # Multi-Server GPU Monitor with local connection and history settings.
        gpu_db_path = self.cfg.get("gpu_db_path") or os.path.join(
            os.path.dirname(self.cfg.config_path), "data", "gpu_history.db"
        )
        self.gpu_monitor = GPUMonitor(
            db_path=os.path.expanduser(gpu_db_path),
            servers=self.cfg.get("gpu_servers", []),
        )
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
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFont(pixel_font("Segoe UI", max(7, round(10 * self.widget_scale))))
        self.setStyleSheet(get_main_stylesheet(self.widget_scale))

    def init_ui(self):
        """Build widget layout for both Expanded and Mini modes."""
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(0)

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
        cols_layout.setSpacing(6)
        self.cols_layout = cols_layout
        
        # --- Left Column: Devices & Official Codex ---
        self.left_col = QWidget(self.cols_widget)
        self.left_col.setFixedWidth(round(190 * self.widget_scale))
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
        
        self.claude_view = CodexQuotaView(
            self.claude_tracker, self.left_col, scale=self.widget_scale, provider="Claude"
        )
        self.claude_view.refresh_requested.connect(lambda: self.fetch_claude_async(force=True))
        left_layout.addWidget(self.claude_view)

        # Codex Quota View
        self.codex_view = CodexQuotaView(self.quota_tracker, self.left_col, scale=self.widget_scale)
        self.codex_view.refresh_requested.connect(lambda: self.fetch_codex_async(force=True))
        left_layout.addWidget(self.codex_view)
        left_layout.addStretch()
        self.left_col.installEventFilter(self)
        self.left_scroll = QScrollArea(self.cols_widget)
        self.left_scroll.setWidgetResizable(True)
        self.left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.left_scroll.setFrameShape(QFrame.NoFrame)
        self.left_scroll.setWidget(self.left_col)
        cols_layout.addWidget(self.left_scroll)
        
        # Vertical Separator between Left and Middle
        v_sep = QFrame(self.cols_widget)
        v_sep.setFrameShape(QFrame.VLine)
        v_sep.setStyleSheet("background-color: rgba(255, 255, 255, 0.08); width: 1px; border: none;")
        cols_layout.addWidget(v_sep)
        
        # --- Middle Column: Relay Stations (Square API & AIHub) ---
        self.mid_col = QWidget(self.cols_widget)
        self.mid_col.setMinimumWidth(0)
        self.mid_col.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        mid_layout = QVBoxLayout(self.mid_col)
        mid_layout.setContentsMargins(0, 0, 0, 0)
        mid_layout.setSpacing(6)
        
        self.relay_view = RelayStationView(self.mid_col, scale=self.widget_scale)
        self.relay_view.filter_dialog_requested.connect(self.open_square_filter_dialog)
        self.relay_view.aihub_filter_requested.connect(self.open_aihub_filter_dialog)
        self.relay_view.history_timeline_requested.connect(self.open_aihub_history_dialog)
        self.relay_view.aihub_mode_toggled.connect(self.on_aihub_mode_toggled)
        self.relay_view.refresh_requested.connect(lambda: self.fetch_relay_async(force=True))
        mid_layout.addWidget(self.relay_view, 1)
        cols_layout.addWidget(self.mid_col, 1)

        # Vertical Separator between Middle and Right
        v_sep2 = QFrame(self.cols_widget)
        v_sep2.setFrameShape(QFrame.VLine)
        v_sep2.setStyleSheet("background-color: rgba(255, 255, 255, 0.08); width: 1px; border: none;")
        cols_layout.addWidget(v_sep2)

        # --- Right Column: GPU Servers (matching dark aesthetic of left column) ---
        self.right_col = QWidget(self.cols_widget)
        self.right_col.setFixedWidth(int(round(178 * self.widget_scale)))
        right_layout = QVBoxLayout(self.right_col)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        self.gpu_view = GPUServerView(self.gpu_monitor, self.right_col, scale=self.widget_scale)
        self.server_monitor.host_stats_updated.connect(self.gpu_view.update_host_stats)
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

        # === Row 1 (Top): 1 BT + 5 GPUs + 3 GPU-Server CPUs ===
        self.row1_layout = QHBoxLayout()
        self.row1_layout.setContentsMargins(0, 0, 0, 0)
        self.row1_layout.setSpacing(max(1, int(round(2 * self.widget_scale))))

        self.mini_bt_lbl = QLabel("📶 --", self.mini_container)

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

        self.row1_layout.addWidget(self.mini_nvidia_icon)

        self.mini_gpu_dots = []
        for i, lbl in enumerate(self.mini_gpu_labels):
            if i > 0:
                dot = QLabel("·", self.mini_container)
                self.mini_gpu_dots.append(dot)
                self.row1_layout.addWidget(dot)
            self.row1_layout.addWidget(lbl)

        # Separator '|' between 5 GPUs and 3 GPU-Server CPUs
        self.mini_sep_gpu_cpu = QLabel("|", self.mini_container)
        self.row1_layout.addWidget(self.mini_sep_gpu_cpu)

        # 3 GPU-Server CPU labels (4号, 7号, 8号) interleaved with '·' (no extra logo)
        self.mini_gpu_cpu_4 = QLabel("--", self.mini_container)
        self.mini_gpu_cpu_7 = QLabel("--", self.mini_container)
        self.mini_gpu_cpu_8 = QLabel("--", self.mini_container)

        self.mini_gpu_cpu_labels = {
            "4": self.mini_gpu_cpu_4,
            "7": self.mini_gpu_cpu_7,
            "8": self.mini_gpu_cpu_8,
        }

        self.mini_gpu_cpu_dots = []
        gpu_srv_keys = ["4", "7", "8"]
        for i, sid in enumerate(gpu_srv_keys):
            if i > 0:
                dot = QLabel("·", self.mini_container)
                self.mini_gpu_cpu_dots.append(dot)
                self.row1_layout.addWidget(dot)
            self.row1_layout.addWidget(self.mini_gpu_cpu_labels[sid])

        self.row1_layout.addStretch()
        self.mini_vbox.addLayout(self.row1_layout)

        # === Row 2 (Bottom): OpenAI Quotas + Battery + CPUs ===
        self.row2_layout = QHBoxLayout()
        self.row2_layout.setContentsMargins(0, 0, 0, 0)
        self.row2_layout.setSpacing(max(1, int(round(2 * self.widget_scale))))

        self.mini_claude_icon = QLabel(self.mini_container)
        self.mini_claude_5h = QLabel("--", self.mini_container)
        self.mini_claude_dot = QLabel("·", self.mini_container)
        self.mini_claude_wk = QLabel("--", self.mini_container)
        self.mini_claude_sep = QLabel("|", self.mini_container)
        for label in (self.mini_claude_icon, self.mini_claude_5h, self.mini_claude_dot, self.mini_claude_wk, self.mini_claude_sep):
            self.row2_layout.addWidget(label)
            label.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        self.mini_openai_icon = QLabel(self.mini_container)
        self.mini_openai_icon.setToolTip("ChatGPT / Codex 剩余限额")

        self.mini_cdx_5h = QLabel("--", self.mini_container)
        self.mini_cdx_dot = QLabel("·", self.mini_container)
        self.mini_cdx_wk = QLabel("--", self.mini_container)

        self.mini_sep1 = QLabel("|", self.mini_container)
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
        self.row2_layout.addWidget(self.mini_sep1)
        self.row2_layout.addWidget(self.mini_bt_lbl)
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

        # Ensure clicks anywhere on labels trigger container expand
        all_mini_widgets = [
            self.mini_nvidia_icon,
            *self.mini_gpu_labels, *self.mini_gpu_dots,
            self.mini_sep_gpu_cpu,
            *self.mini_gpu_cpu_labels.values(), *self.mini_gpu_cpu_dots,
            self.mini_openai_icon, self.mini_cdx_5h, self.mini_cdx_dot, self.mini_cdx_wk,
            self.mini_sep1, self.mini_bt_lbl, self.mini_sep2, self.mini_cpu_icon,
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
        self._apply_expanded_spacing()
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
        self.mini_claude_icon.setPixmap(get_claude_pixmap(icon_sz))
        self.mini_cpu_icon.setPixmap(get_cpu_pixmap(icon_sz))

        # 3. Separators & Dots
        sep_fs = self.get_mini_font_size(9)
        dot_fs = self.get_mini_font_size(9)
        sep_style = f"font-size: {sep_fs}px; color: #4B5563; font-weight: 400; padding: 0 {max(1, int(round(2 * self.widget_scale)))}px;"
        dot_style = f"font-size: {dot_fs}px; color: #6B7280; font-weight: 400;"

        self.mini_claude_sep.setStyleSheet(sep_style)
        self.mini_claude_dot.setStyleSheet(dot_style)
        self.mini_sep1.setStyleSheet(sep_style)
        self.mini_sep_gpu_cpu.setStyleSheet(sep_style)
        self.mini_sep2.setStyleSheet(sep_style)
        self.mini_cdx_dot.setStyleSheet(dot_style)
        for dot in self.mini_gpu_dots:
            dot.setStyleSheet(dot_style)
        for dot in self.mini_gpu_cpu_dots:
            dot.setStyleSheet(dot_style)
        for dot in self.mini_srv_dots:
            dot.setStyleSheet(dot_style)

        # 4. Re-apply border color state
        self._set_status_light_running(getattr(self, "_codex_running", False), getattr(self, "_claude_running", False))

        # 5. Re-render labels with new scaled font sizes
        self._render_mini_bluetooth()
        self.update_mini_quota_display()
        self.update_mini_claude_display()
        self._render_mini_server_cpu()
        self._render_mini_gpu()

    def _recenter_around(self, center_point):
        """Reposition window so that its center matches center_point while staying within screen bounds."""
        if not center_point or center_point.x() < -1000 or center_point.y() < -1000:
            screen = QApplication.primaryScreen().availableGeometry()
            center_point = QPoint(screen.right() - 150, screen.top() + 100)

        w = self.width()
        h = self.height()
        
        new_x = center_point.x() - w // 2
        new_y = center_point.y() - h // 2
        
        screen = QApplication.screenAt(center_point)
        if not screen:
            screen = QApplication.primaryScreen()
        if screen:
            s_geo = screen.availableGeometry()
            # Clamp vertically
            if new_y < s_geo.top() + 6:
                new_y = s_geo.top() + 6
            elif new_y + h > s_geo.bottom() - 6:
                new_y = max(s_geo.top() + 6, s_geo.bottom() - h - 6)
                
            # Clamp horizontally
            if new_x < s_geo.left() + 6:
                new_x = s_geo.left() + 6
            elif new_x + w > s_geo.right() - 6:
                new_x = max(s_geo.left() + 6, s_geo.right() - w - 6)
                
        self.move(new_x, new_y)
        self.cfg.set("window_pos", [new_x, new_y])

    def expand_to_full(self):
        """Expand to full detailed card, expanding symmetrically around center."""
        if self.is_mini:
            old_center = self.frameGeometry().center()
            self._last_mini_pos = self.pos()
            self._last_mini_center = old_center
            self._expanded_dragged = False
            self.is_mini = False
            self._expand_timestamp = time.time()
            self.cfg.set("is_mini_mode", False)
            self.update_mode_visibility()
            self._recenter_around(old_center)
            self.raise_()
            self.activateWindow()
            self.setFocus()

    def collapse_to_mini(self):
        """Collapse back to mini capsule, shrinking back symmetrically to center."""
        if not self.is_mini:
            old_center = self.frameGeometry().center()
            self.is_mini = True
            self.cfg.set("is_mini_mode", True)
            self.update_mode_visibility()
            
            center_to_use = old_center
            if not getattr(self, "_expanded_dragged", False) and hasattr(self, "_last_mini_center"):
                center_to_use = self._last_mini_center
                
            self._recenter_around(center_to_use)

    def toggle_mode(self):
        """Toggle between Mini capsule and Expanded card."""
        if self.is_mini:
            self.expand_to_full()
        else:
            self.collapse_to_mini()

    def _has_active_modal_or_dialog(self) -> bool:
        """Check if any modal, popup, or active dialog is currently open or visible."""
        if QApplication.activeModalWidget() is not None:
            return True
        if QApplication.activePopupWidget() is not None:
            return True
        for d in self.findChildren(QDialog):
            if d.isVisible():
                return True
        for w in QApplication.topLevelWidgets():
            if isinstance(w, (QDialog, QMenu)) and w.isVisible() and w != self:
                return True
        return False

    def _check_auto_collapse_safety(self):
        """Safety check to auto-collapse if window is expanded but lost active focus."""
        if self.is_mini:
            return
        if time.time() - getattr(self, "_expand_timestamp", 0) < 0.6:
            return
        if QApplication.mouseButtons() != Qt.NoButton or getattr(self, "_dragging", False):
            return
        if self._has_active_modal_or_dialog():
            return
        if not self.isActiveWindow():
            self.collapse_to_mini()

    def changeEvent(self, event):
        """Auto-collapse to mini capsule when losing window focus; reject minimization unless user-hidden."""
        if event.type() == QEvent.WindowStateChange:
            if self.isMinimized() and not getattr(self, "_user_hidden", False):
                QTimer.singleShot(0, self.ensure_topmost)
        elif event.type() in (QEvent.ActivationChange, QEvent.WindowDeactivate):
            if not self.isActiveWindow() and not self.is_mini:
                # Do not collapse if user is interacting with an open dialog or menu
                if not self._has_active_modal_or_dialog():
                    self.collapse_to_mini()
        super().changeEvent(event)

    def nativeEvent(self, eventType, message):
        """Intercept Windows messages to prevent Win+D from moving or minimizing the floating widget."""
        if sys.platform == "win32" and eventType == "windows_generic_MSG":
            try:
                msg = wintypes.MSG.from_address(int(message))
                # WM_SYSCOMMAND (0x0112): Block SC_MINIMIZE (0xF020)
                if msg.message == 0x0112 and (msg.wParam & 0xFFF0) == 0xF020:
                    if not getattr(self, "_user_hidden", False):
                        return True, 0
                # WM_WINDOWPOSCHANGING (0x0046): Block moving to -32000 (Win+D minimize)
                elif msg.message == 0x0046 and msg.lParam:
                    class _WINDOWPOS(ctypes.Structure):
                        _fields_ = [
                            ('hwnd', wintypes.HWND),
                            ('hwndInsertAfter', wintypes.HWND),
                            ('x', ctypes.c_int),
                            ('y', ctypes.c_int),
                            ('cx', ctypes.c_int),
                            ('cy', ctypes.c_int),
                            ('flags', wintypes.UINT)
                        ]
                    pos = _WINDOWPOS.from_address(msg.lParam)
                    if (pos.x <= -30000 or pos.y <= -30000) and not getattr(self, "_user_hidden", False):
                        pos.flags |= (0x0001 | 0x0002)  # SWP_NOSIZE | SWP_NOMOVE
                        return True, 0
            except Exception:
                pass
        return super().nativeEvent(eventType, message)

    def hideEvent(self, event):
        """Catch accidental system hiding (e.g. Win+D or screen power cycle) and resurrect."""
        if not getattr(self, "_user_hidden", False) and not getattr(self, "_closing", False):
            QTimer.singleShot(150, self.ensure_topmost)
        super().hideEvent(event)

    def fix_tooltip_zorder(self):
        """Ensure any active QToolTip window is owned by this window and placed at the top of the topmost band."""
        if sys.platform != "win32":
            return
        try:
            u32 = USER32
            hwnd_main = int(self.winId())
            for w in QApplication.topLevelWidgets():
                if w != self and "QLabel" in w.__class__.__name__:
                    hwnd_tip = int(w.winId())
                    # Setting the main window as owner ensures Windows always paints the tooltip in front
                    u32.SetWindowLongPtrW(hwnd_tip, -8, hwnd_main)  # GWLP_HWNDPARENT = -8
                    u32.SetWindowPos(hwnd_tip, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
        except Exception:
            pass

    def ensure_topmost(self):
        """Ensure window remains visible and topmost unless user explicitly hid it."""
        if getattr(self, "_user_hidden", False) or getattr(self, "_closing", False):
            return
        if self.isMinimized():
            self.setWindowState(self.windowState() & ~Qt.WindowMinimized)
            self.showNormal()
        if not self.isVisible():
            self.show()
        if USER32 is not None:
            hwnd = int(self.winId())
            if not USER32.IsWindowVisible(hwnd):
                USER32.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE
            if self.cfg.get("always_on_top", True) and not QToolTip.isVisible() and not self._has_active_modal_or_dialog():
                USER32.SetWindowPos(
                    hwnd, -1, 0, 0, 0, 0,
                    0x0001 | 0x0002 | 0x0010 | 0x0040 | 0x0200,
                )  # Keep size, position, focus and owner order while restoring visibility.
        elif self.cfg.get("always_on_top", True) and not QToolTip.isVisible() and not self._has_active_modal_or_dialog():
            self.raise_()

    def update_mode_visibility(self):
        """Instant toggle between mini and expanded views with zero lag."""
        base_w = int(round(850 * self.widget_scale))
        base_h = self._expanded_content_height()
        if self.is_mini:
            self.root_layout.setContentsMargins(0, 0, 0, 0)
            self.expanded_container.hide()
            self.mini_container.show()
            self._resize_mini_to_contents()
        else:
            self.root_layout.setContentsMargins(0, 0, 0, 0)
            self.mini_container.hide()
            self.expanded_container.show()
            self.setFixedSize(base_w, base_h)
            self._schedule_content_resize()

    def eventFilter(self, obj, event):
        if obj is getattr(self, "left_col", None) and event.type() == QEvent.LayoutRequest:
            self._schedule_content_resize()
        return super().eventFilter(obj, event)

    def _expanded_content_height(self):
        for component in (self.battery_view, self.claude_view, self.codex_view):
            component.ensurePolished()
            component.layout().invalidate()
            component.layout().activate()
        self.left_col.layout().invalidate()
        content = self.left_col.layout().sizeHint().height()
        margins = self.exp_layout.contentsMargins()
        title = self.exp_layout.itemAt(0).sizeHint().height()
        desired = max(round(360 * self.widget_scale), content + title + margins.top() + margins.bottom() + self.exp_layout.spacing() + 4)
        screen = self.windowHandle().screen() if self.windowHandle() else QApplication.primaryScreen()
        return min(desired, screen.availableGeometry().height() - 20)

    def _schedule_content_resize(self):
        if getattr(self, "_height_update_pending", False):
            return
        self._height_update_pending = True
        QTimer.singleShot(100, self._resize_expanded_to_contents)

    def _resize_expanded_to_contents(self):
        self._height_update_pending = False
        if self.is_mini:
            return
        height = self._expanded_content_height()
        if height != self.height():
            self.setFixedSize(round(850 * self.widget_scale), height)
            screen = self.windowHandle().screen() if self.windowHandle() else QApplication.primaryScreen()
            area = screen.availableGeometry()
            self.move(max(area.left(), min(self.x(), area.right() - self.width() + 1)),
                      max(area.top(), min(self.y(), area.bottom() - self.height() + 1)))

    def _resize_mini_to_contents(self):
        if not self.is_mini:
            return
        self.mini_vbox.invalidate()
        hint = self.mini_vbox.sizeHint()
        self.setFixedSize(
            max(round(178 * self.widget_scale), hint.width() + 4),
            max(round(35 * self.widget_scale), hint.height() + 4),
        )

    @staticmethod
    def _fit_scale(requested, screen):
        available = screen.availableGeometry()
        return min(max(0.5, float(requested)), (available.width() - 20) / 850, (available.height() - 20) / 450)

    def _apply_expanded_spacing(self):
        scale = self.widget_scale
        self.exp_layout.setContentsMargins(round(8 * scale), round(7 * scale), round(8 * scale), round(7 * scale))
        self.exp_layout.setSpacing(max(2, round(6 * scale)))
        self.cols_layout.setSpacing(max(2, round(6 * scale)))
        self.left_scroll.setFixedWidth(round(190 * scale))
        # The scrollbar uses space within the left column only when needed.
        self.left_col.setMinimumWidth(0)
        self.left_col.setMaximumWidth(16777215)
        for col in (self.left_col, self.mid_col, self.right_col):
            col.layout().setSpacing(max(2, round(6 * scale)))

    def showEvent(self, event):
        super().showEvent(event)
        handle = self.windowHandle()
        if handle and not getattr(self, "_screen_connected", False):
            handle.screenChanged.connect(self._on_screen_changed)
            app = QApplication.instance()
            app.screenAdded.connect(self._schedule_display_update)
            app.screenRemoved.connect(self._schedule_display_update)
            self._screen_connected = True
            self._watch_screen(handle.screen())

    def _watch_screen(self, screen):
        if screen is self._watched_screen:
            return
        previous = self._watched_screen
        if previous is not None:
            try:
                previous.availableGeometryChanged.disconnect(self._schedule_display_update)
                previous.geometryChanged.disconnect(self._schedule_display_update)
                previous.logicalDotsPerInchChanged.disconnect(self._schedule_display_update)
            except (RuntimeError, TypeError):
                pass
        self._watched_screen = screen
        if screen is not None:
            screen.availableGeometryChanged.connect(self._schedule_display_update)
            screen.geometryChanged.connect(self._schedule_display_update)
            screen.logicalDotsPerInchChanged.connect(self._schedule_display_update)

    def _schedule_display_update(self, *args):
        # RDP reconnects may emit several screen and DPI updates in succession.
        self._display_update_timer.start()

    def _on_screen_changed(self, screen):
        self._watch_screen(screen)
        self._schedule_display_update()

    def _refresh_display_metrics(self):
        handle = self.windowHandle()
        screen = handle.screen() if handle else None
        screen = screen or QApplication.primaryScreen()
        if screen is not None:
            self._watch_screen(screen)
            self.set_scale(self.requested_scale, persist=False)

    def _keep_on_screen(self, screen):
        area = screen.availableGeometry()
        self.move(
            max(area.left(), min(self.x(), area.right() - self.width() + 1)),
            max(area.top(), min(self.y(), area.bottom() - self.height() + 1)),
        )

    def set_scale(self, scale_val: float, persist: bool = True):
        """Set UI size scale and dynamically recompute all fonts, margins, and subviews."""
        self.requested_scale = max(0.5, float(scale_val))
        handle = self.windowHandle()
        screen = handle.screen() if handle else QApplication.screenAt(self.geometry().center())
        screen = screen or QApplication.primaryScreen()
        self.widget_scale = self._fit_scale(self.requested_scale, screen)
        if persist:
            self.cfg.set("scale", self.requested_scale)
        
        # 1. Update window-level QSS stylesheet (dynamically scales all standard fonts)
        self.setFont(pixel_font("Segoe UI", max(7, round(10 * self.widget_scale))))
        self.setStyleSheet(get_main_stylesheet(self.widget_scale))
        
        # 2. Update title bar buttons and icon
        title_fs = max(8, int(round(11 * self.widget_scale)))
        self.title_icon.setStyleSheet(f"font-size: {title_fs}px;")
        btn_sz = max(14, int(round(18 * self.widget_scale)))
        self.btn_mini_toggle.setFixedSize(btn_sz, btn_sz)
        self.btn_settings.setFixedSize(btn_sz, btn_sz)
        
        # 3. Update column fixed widths
        if hasattr(self, "left_col"):
            self.left_scroll.setFixedWidth(round(190 * self.widget_scale))
        if hasattr(self, "right_col"):
            self.right_col.setFixedWidth(int(round(178 * self.widget_scale)))
            
        # 4. Notify subviews to update their custom internal fonts and item heights
        if hasattr(self, "battery_view") and hasattr(self.battery_view, "set_scale"):
            self.battery_view.set_scale(self.widget_scale)
        if hasattr(self, "codex_view") and hasattr(self.codex_view, "set_scale"):
            self.codex_view.set_scale(self.widget_scale)
        if hasattr(self, "relay_view") and hasattr(self.relay_view, "set_scale"):
            self.relay_view.set_scale(self.widget_scale)
        if hasattr(self, "gpu_view") and hasattr(self.gpu_view, "set_scale"):
            self.gpu_view.set_scale(self.widget_scale)
            
        self.claude_view.set_scale(self.widget_scale)
        self._apply_expanded_spacing()

        # 5. Update mini capsule fonts, icon pixmaps, and spacings
        self.update_mini_scale_styling()
        
        # 6. Re-apply mode visibility and geometry
        self.update_mode_visibility()
        self._keep_on_screen(screen)

    def apply_theme_and_opacity(self):
        """Apply configured opacity."""
        opacity = self.cfg.get("opacity", 0.95)
        self.setWindowOpacity(float(opacity))

    def restore_position(self):
        """Restore saved window coordinates or place near top-right."""
        pos = self.cfg.get("window_pos")
        screen = QApplication.screenAt(QPoint(*pos)) if pos and len(pos) == 2 else None
        screen = screen or QApplication.primaryScreen()
        area = screen.availableGeometry()
        if pos and len(pos) == 2:
            self.move(*pos)
        else:
            self.move(area.right() - self.width() - 20, area.top() + 80)
        self._keep_on_screen(screen)

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
        self.codex_timer.setInterval(cdx_sec * 1000)
        if self.cfg.get("codex_quota_enabled", True):
            self.codex_timer.start()
        
        self.claude_timer = QTimer(self)
        self.claude_timer.timeout.connect(self.fetch_claude_async)
        self.claude_timer.setInterval(max(60, int(self.cfg.get("claude_interval_sec", 60))) * 1000)
        if self.cfg.get("claude_quota_enabled", True):
            self.claude_timer.start()

        # 3. Status Light & Activity timer. The file scan runs in a worker.
        self.activity_timer = QTimer(self)
        self.activity_timer.timeout.connect(self.check_codex_activity_fast)
        self.activity_timer.start(2000)

        # 4. Relay Station timer (Square API & AIHub, every minute)
        self.relay_timer = QTimer(self)
        self.relay_timer.timeout.connect(lambda: self.fetch_relay_async(force=True))
        relay_sec = max(20, int(self.cfg.get("relay_interval_sec", 60)))
        self.relay_timer.start(relay_sec * 1000)

        # 5. Safety auto-collapse check timer
        self._expand_timestamp = 0
        self.focus_check_timer = QTimer(self)
        self.focus_check_timer.timeout.connect(self._check_auto_collapse_safety)
        self.focus_check_timer.start(350)

        # 6. Anti-disappearing and topmost watchdog timer (every 2.5s)
        self.watchdog_timer = QTimer(self)
        self.watchdog_timer.timeout.connect(self.ensure_topmost)
        self.watchdog_timer.start(2500)

    # -------------------------------------------------------------
    # Fast Activity & Data Methods
    # -------------------------------------------------------------
    def check_codex_activity_fast(self):
        """Schedule an activity check without blocking the UI event loop."""
        if self._activity_worker is not None:
            return

        self._activity_worker = CodexActivityWorker(self.activity_tracker, self.claude_activity_tracker)
        self._activity_worker.activity_ready.connect(self._set_status_light_running)
        self._activity_worker.finished.connect(self._on_activity_worker_finished)
        self._activity_worker.start()

    def _on_activity_worker_finished(self):
        worker = self.sender()
        if worker is None:
            return
        if worker is self._activity_worker:
            self._activity_worker = None
        worker.deleteLater()

    def _set_status_light_running(self, running: bool, claude_running: bool = False):
        self._codex_running = running
        self._claude_running = claude_running
        state = "both" if running and claude_running else "codex" if running else "claude" if claude_running else "idle"
        for container in (self.mini_container, self.expanded_container):
            if container.property("activity_state") == state:
                continue
            container.setProperty("activity_state", state)
            container.style().unpolish(container)
            container.style().polish(container)
            container.update()

    def refresh_all_data(self, force: bool = True):
        """Trigger async scan for Bluetooth, Codex, and Relay Stations."""
        self.scan_bluetooth_async()
        self.fetch_codex_async(force=force)
        self.fetch_claude_async(force=force)
        self.fetch_relay_async(force=force)

    def scan_bluetooth_async(self):
        """Asynchronously scan Bluetooth devices in background thread."""
        if self._bt_worker is not None:
            return
            
        only_conn = self.cfg.get("only_connected", True)
        self._bt_worker = BluetoothScanWorker(only_connected=only_conn)
        self._bt_worker.devices_ready.connect(self.on_bluetooth_devices_received)
        self._bt_worker.finished.connect(self._on_bt_worker_finished)
        self._bt_worker.start()

    def _on_bt_worker_finished(self):
        worker = self.sender()
        if worker is None:
            return
        if worker is self._bt_worker:
            self._bt_worker = None
        worker.deleteLater()

    def on_bluetooth_devices_received(self, devices: List[Dict[str, Any]]):
        """Receive devices from background worker without blocking UI."""
        self._current_devices = devices
        previous_count = len(self.battery_view._last_devices)
        self.battery_view.update_devices(devices)
        if min(previous_count, 2) != min(len(devices), 2):
            self._schedule_content_resize()
        self._render_mini_bluetooth()

    def _render_mini_bluetooth(self):
        """Render Bluetooth device battery in mini capsule."""
        all_devices = getattr(self, "_current_devices", [])
        devices = [device for device in all_devices if isinstance(device.get("battery"), (int, float))]
        fs = self.get_mini_font_size(10)
        if devices:
            # Priority 1: Microphone (DJI, Mic, Rode, Shure, 麦克风, or 🎙️ icon)
            mic_dev = next((d for d in devices if any(k in d.get("name", "").lower() for k in ["dji", "mic", "rode", "麦克风", "话筒", "shure", "lark", "hollyland"]) or d.get("icon") == "🎙️"), None)
            if mic_dev:
                target_dev = mic_dev
            else:
                # Priority 2: Fallback to the connected device with the lowest battery
                target_dev = min(devices, key=lambda x: x.get("battery", 100))
                
            icon = target_dev.get("icon", "📶")
            bat = target_dev.get("battery", 0)
            color = target_dev.get("status_color", "#10B981")
            
            self.mini_bt_lbl.setText(f"{icon} {bat}")
            self.mini_bt_lbl.setStyleSheet(f"font-size: {fs}px; font-weight: 700; color: {color};")
            self.mini_bt_lbl.setToolTip(f"显示外设: {target_dev.get('name')} ({bat}%)\n(共 {len(all_devices)} 台设备在线)")
        else:
            self.mini_bt_lbl.setText(f"📶 {len(all_devices)}台" if all_devices else "📶 --")
            self.mini_bt_lbl.setStyleSheet(f"font-size: {fs}px; font-weight: 700; color: #9CA3AF;")
            self.mini_bt_lbl.setToolTip("在线设备未提供电量" if all_devices else "无在线蓝牙设备")

    def fetch_claude_async(self, force=False):
        if not self.cfg.get("claude_quota_enabled", True):
            self.on_claude_data_received({"success": False, "disabled": True, "error": "额度检测已关闭"})
            return
        if self._claude_worker is not None:
            return
        self._claude_worker = CodexFetchWorker(self.claude_client, force=force)
        self._claude_worker.data_ready.connect(self.on_claude_data_received)
        self._claude_worker.finished.connect(self._on_claude_worker_finished)
        self._claude_worker.start()

    def on_claude_data_received(self, data):
        if not self.cfg.get("claude_quota_enabled", True):
            data = {"success": False, "disabled": True, "error": "额度检测已关闭"}
        self._current_claude_data = data
        self.claude_view.update_data(data)
        self._schedule_content_resize()
        self.update_mini_claude_display()

    def _on_claude_worker_finished(self):
        worker = self.sender()
        if worker is None:
            return
        if worker is self._claude_worker:
            self._claude_worker = None
        worker.deleteLater()

    def fetch_codex_async(self, force: bool = False):
        """Run async thread for ChatGPT/Codex quota lookup."""
        if not self.cfg.get("codex_quota_enabled", True):
            self.on_codex_data_received({"success": False, "disabled": True, "error": "额度检测已关闭"})
            return
        if self._codex_worker is not None:
            return
            
        self._codex_worker = CodexFetchWorker(self.codex_client, force=force)
        self._codex_worker.data_ready.connect(self.on_codex_data_received)
        self._codex_worker.finished.connect(self._on_codex_worker_finished)
        self._codex_worker.start()

    def _on_codex_worker_finished(self):
        worker = self.sender()
        if worker is None:
            return
        if worker is self._codex_worker:
            self._codex_worker = None
        worker.deleteLater()

    def on_codex_data_received(self, data: Dict[str, Any]):
        """Callback when Codex data arrives."""
        if not self.cfg.get("codex_quota_enabled", True):
            data = {"success": False, "disabled": True, "error": "额度检测已关闭"}
        self._current_codex_data = data
        self.codex_view.update_data(data)
        self._schedule_content_resize()
        self.update_mini_quota_display()
        
        # If fetch failed (transient network or proxy hiccup), schedule a fast retry in 5s
        if not data.get("success") and not data.get("disabled"):
            QTimer.singleShot(5000, lambda: self.fetch_codex_async(force=True))
            
        if not self.is_mini:
            self._schedule_content_resize()

    def fetch_relay_async(self, force: bool = False):
        """Asynchronously fetch Square API and AIHub data in background."""
        if self._relay_worker is not None:
            return
            
        self._relay_worker = RelayFetchWorker(self.square_client, self.aihub_client, force=force)
        self._relay_worker.square_ready.connect(self.on_square_data_received)
        self._relay_worker.aihub_ready.connect(self.on_aihub_data_received)
        self._relay_worker.finished.connect(self._on_relay_worker_finished)
        self._relay_worker.start()

    def _on_relay_worker_finished(self):
        worker = self.sender()
        if worker is None:
            return
        if worker is self._relay_worker:
            self._relay_worker = None
        worker.deleteLater()

    def on_square_data_received(self, data: Dict[str, Any]):
        """Render Square API data."""
        self.relay_view.update_square_data(data)
        if not self.is_mini:
            self._schedule_content_resize()

    def on_aihub_data_received(self, data: Dict[str, Any]):
        """Render AIHub data."""
        # Apply current exclusions even if a worker started before the user's click.
        excluded = set(self.aihub_client.get_excluded_providers())
        visible_data = dict(data)
        for key in ("monitored_providers", "top_groups"):
            if key in data:
                visible_data[key] = [row for row in data[key] or [] if row.get("code") not in excluded]
        visible_data["excluded_codes"] = sorted(excluded)
        self.relay_view.update_aihub_data(visible_data)
        if not self.is_mini:
            self._schedule_content_resize()

    def on_aihub_mode_toggled(self, new_mode: bool):
        """Handle user toggling between AIHub automatic filter mode and manual checked mode."""
        self.aihub_client.set_auto_mode(new_mode)
        self.fetch_relay_async(force=True)

    def on_aihub_history_filters_changed(self):
        """Apply a history-window exclusion immediately, then recompute monitored rows."""
        self.on_aihub_data_received(self.aihub_client.cached_data or self.relay_view._aihub_data)
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
            dlg.deleteLater()
            self.raise_()
            self.activateWindow()

    def open_square_filter_dialog(self):
        """Open Square API interactive group and model filter selection dialog."""
        try:
            from ui.square_filter_dialog import SquareFilterDialog
            dlg = SquareFilterDialog(self.square_client, parent=self)
            dlg.filters_changed.connect(lambda: self.fetch_relay_async(force=True))
            try:
                dlg.exec_()
            finally:
                dlg.deleteLater()
                self.raise_()
                self.activateWindow()
        except Exception as e:
            import traceback
            traceback.print_exc()

    def open_aihub_filter_dialog(self):
        """Open AIHub interactive provider filter selection dialog with live stats."""
        try:
            from ui.square_filter_dialog import AIHubFilterDialog
            dlg = AIHubFilterDialog(self.aihub_client, parent=self)
            dlg.filters_changed.connect(lambda: self.fetch_relay_async(force=True))
            try:
                dlg.exec_()
            finally:
                dlg.deleteLater()
                self.raise_()
                self.activateWindow()
        except Exception as e:
            import traceback
            traceback.print_exc()

    def open_aihub_history_dialog(self, code: str = "", dimension: str = "dual"):
        """Open AIHub 24-hour probe and candy timeline visualization dialog."""
        try:
            from ui.history_timeline_dialog import AIHubHistoryDialog
            dlg = AIHubHistoryDialog(self.aihub_client, initial_code=code, initial_dimension=dimension, parent=self)
            dlg.filters_changed.connect(self.on_aihub_history_filters_changed)
            try:
                dlg.exec_()
            finally:
                dlg.deleteLater()
                self.raise_()
                self.activateWindow()
        except Exception as e:
            import traceback
            traceback.print_exc()

    def update_mini_quota_display(self):
        self._render_mini_quota(
            self._current_codex_data, "ChatGPT", self.mini_cdx_5h, self.mini_cdx_dot,
            self.mini_cdx_wk, self.mini_openai_icon, self.quota_tracker,
        )

    def update_mini_claude_display(self):
        self._render_mini_quota(
            self._current_claude_data, "Claude", self.mini_claude_5h, self.mini_claude_dot,
            self.mini_claude_wk, self.mini_claude_icon, self.claude_tracker,
        )

    def _render_mini_quota(self, data, provider, short_label, dot, weekly_label, icon, tracker):
        data = data or {}
        fs = self.get_mini_font_size(10)
        if not data or not data.get("success"):
            limited = provider == "Claude" and "请求受限" in data.get("error", "")
            short_label.setText("已关" if data.get("disabled") else "限流" if limited else "--")
            color = "#94A3B8" if data.get("disabled") else "#EF4444"
            short_label.setStyleSheet(f"font-size: {fs}px; font-weight: 700; color: {color};")
            dot.hide()
            weekly_label.hide()
            error_tip = f"{provider} 状态: {data.get('error', '获取失败')}"
            if data.get("retry_at"):
                error_tip += "\n下次重试: " + datetime.fromtimestamp(data["retry_at"]).strftime("%H:%M:%S")
            short_label.setToolTip(error_tip)
            icon.setToolTip(error_tip)
            self._resize_mini_to_contents()
            return

        five_h = data.get("five_hour_window")
        weekly = data.get("weekly_window") or data.get("primary_window")
        
        fh_rem = five_h.get("remaining_percent", 100) if five_h else None
        wk_rem = weekly.get("remaining_percent", 100) if weekly else None
        
        if provider == "Claude":
            fh_rem = round(float(fh_rem)) if fh_rem is not None else None
            wk_rem = round(float(wk_rem)) if wk_rem is not None else None

        col_5h = get_health_color(fh_rem) if fh_rem is not None else "#10B981"
        col_wk = get_health_color(wk_rem) if wk_rem is not None else "#10B981"
        
        if five_h and weekly:
            short_label.setText(str(fh_rem))
            short_label.setStyleSheet(f"font-size: {fs}px; font-weight: 700; color: {col_5h};")
            short_label.show()
            dot.show()
            weekly_label.setText(str(wk_rem))
            weekly_label.setStyleSheet(f"font-size: {fs}px; font-weight: 700; color: {col_wk};")
            weekly_label.show()
        elif weekly:
            short_label.setText(str(wk_rem))
            short_label.setStyleSheet(f"font-size: {fs}px; font-weight: 700; color: {col_wk};")
            short_label.show()
            dot.hide()
            weekly_label.hide()
        elif five_h:
            short_label.setText(str(fh_rem))
            short_label.setStyleSheet(f"font-size: {fs}px; font-weight: 700; color: {col_5h};")
            short_label.show()
            dot.hide()
            weekly_label.hide()
        else:
            short_label.setText("OK")
            short_label.setStyleSheet(f"font-size: {fs}px; font-weight: 700; color: #10B981;")
            dot.hide()
            weekly_label.hide()

        if data.get("stale"):
            stale_label = weekly_label if weekly and five_h else short_label
            stale_label.setText(stale_label.text() + "*")

        tip_lines = [f"{provider} {data.get('plan_type','PLUS')}"]
        if data.get("stale"):
            tip_lines.append("* 暂用旧数据。" + data.get("error", "等待刷新"))
            if data.get("fetched_at"):
                tip_lines.append("最近读取: " + datetime.fromtimestamp(data["fetched_at"]).strftime("%m-%d %H:%M:%S"))
        if five_h:
            fh_tip = f"• 5H 剩余: {fh_rem}% (倒计时: {five_h.get('reset_countdown','')})"
            if tracker:
                fh_ana = tracker.get_analysis_for_current_cycle(five_h)
                if fh_ana.get("has_data") and fh_ana.get("exhaustion_text"):
                    fh_tip += f" [{fh_ana['exhaustion_text']}]"
            tip_lines.append(fh_tip)
        if weekly:
            wk_tip = f"• 周限额 剩余: {wk_rem}% (倒计时: {weekly.get('reset_countdown','')})"
            if tracker:
                wk_ana = tracker.get_analysis_for_current_cycle(weekly)
                if wk_ana.get("has_data") and wk_ana.get("exhaustion_text"):
                    wk_tip += f" [{wk_ana['exhaustion_text']}]"
            tip_lines.append(wk_tip)
        tooltip = "\n".join(tip_lines)
        short_label.setToolTip(tooltip)
        weekly_label.setToolTip(tooltip)
        icon.setToolTip(tooltip)

        self._resize_mini_to_contents()

    def on_server_cpu_updated(self, data: Dict[str, float]):
        """Update mini capsule with 3 server CPU utilization values (quad, e5, 8375c)."""
        self._current_server_cpu = data
        self._render_mini_server_cpu()
        self._resize_mini_to_contents()

    def _render_mini_server_cpu(self):
        """Render server CPU values in mini capsule (Row 1: 7, 8, 4; Row 2: quad, e5, 8375c)."""
        data = getattr(self, "_current_server_cpu", {})
        fs = self.get_mini_font_size(10)

        # 1. GPU Server CPUs in Row 1: 4号, 7号, 8号
        if hasattr(self, "mini_gpu_cpu_labels"):
            gpu_tip_parts = []
            gpu_srv_names = {"4": "4号 (2080Ti)", "7": "7号 (L40S)", "8": "8号 (A100)"}
            for sid in ["4", "7", "8"]:
                val = data.get(sid, -1.0)
                lbl = self.mini_gpu_cpu_labels.get(sid)
                if not lbl:
                    continue
                name = gpu_srv_names.get(sid, sid)
                if val < 0:
                    lbl.setText("--")
                    style = f"font-size: {fs}px; font-weight: 700; color: #64748B;"
                    if lbl.styleSheet() != style:
                        lbl.setStyleSheet(style)
                    gpu_tip_parts.append(f"{name}: 离线")
                else:
                    num_str = f"{int(round(val))}"
                    color = get_hex_for_cpu(val)
                    lbl.setText(num_str)
                    style = f"font-size: {fs}px; font-weight: 700; color: {color};"
                    if lbl.styleSheet() != style:
                        lbl.setStyleSheet(style)
                    gpu_tip_parts.append(f"{name}: {val:.1f}%")

            gpu_cpu_tt = "GPU服务器 CPU利用率 (4号 / 7号 / 8号)\n" + " | ".join(gpu_tip_parts)
            if hasattr(self, "mini_sep_gpu_cpu"):
                self.mini_sep_gpu_cpu.setToolTip(gpu_cpu_tt)
            for lbl in self.mini_gpu_cpu_labels.values():
                lbl.setToolTip(gpu_cpu_tt)

        # 2. CPU Server CPUs in Row 2: quad, e5, 8375c
        if hasattr(self, "mini_srv_labels"):
            cpu_tip_parts = []
            for sid in ["quad", "e5", "8375c"]:
                val = data.get(sid, -1.0)
                lbl = self.mini_srv_labels.get(sid)
                if not lbl:
                    continue
                if val < 0:
                    lbl.setText("--")
                    style = f"font-size: {fs}px; font-weight: 700; color: #64748B;"
                    if lbl.styleSheet() != style:
                        lbl.setStyleSheet(style)
                    cpu_tip_parts.append(f"{sid}: 离线")
                else:
                    num_str = f"{int(round(val))}"
                    color = get_hex_for_cpu(val)
                    lbl.setText(num_str)
                    style = f"font-size: {fs}px; font-weight: 700; color: {color};"
                    if lbl.styleSheet() != style:
                        lbl.setStyleSheet(style)
                    cpu_tip_parts.append(f"{sid}: {val:.1f}%")

            tooltip = "CPU服务器 CPU利用率 (quad / e5 / 8375c)\n" + " | ".join(cpu_tip_parts)
            if hasattr(self, "mini_cpu_icon"):
                self.mini_cpu_icon.setToolTip(tooltip)
            for lbl in self.mini_srv_labels.values():
                lbl.setToolTip(tooltip)

    def on_gpu_data_updated(self, data: Dict[str, Any]):
        """Render GPU mini stats and refresh expanded view."""
        self._current_gpu_data = data
        self._render_mini_gpu()

    def _render_mini_gpu(self):
        """Render GPU card stats in mini capsule."""
        data = getattr(self, "_current_gpu_data", {})
        fs = self.get_mini_font_size(10)
        if not data or not data.get("success"):
            for lbl in self.mini_gpu_labels:
                lbl.setText("--")
                style = f"font-size: {fs}px; font-weight: 700; color: #64748B;"
                if lbl.styleSheet() != style:
                    lbl.setStyleSheet(style)
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
                style = f"font-size: {fs}px; font-weight: 700; color: {c.get('color', '#64748B')};"
                if lbl.styleSheet() != style:
                    lbl.setStyleSheet(style)
                lbl.setToolTip(c.get("tooltip", ""))
            else:
                lbl.setText("--")
                style = f"font-size: {fs}px; font-weight: 700; color: #64748B;"
                if lbl.styleSheet() != style:
                    lbl.setStyleSheet(style)
                lbl.setToolTip("GPU: 无数据")

        tt = data.get("five_cards_tt", "GPU 显存占用 (7号 L40S x3 · 8号 A100 x2)")
        self.mini_nvidia_icon.setToolTip(tt)

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
                if not self.is_mini:
                    self._expanded_dragged = True
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
                if pos.x() > -1000 and pos.y() > -1000:
                    self.cfg.set("window_pos", [pos.x(), pos.y()])
                    if self.is_mini:
                        self._last_mini_pos = pos
                        self._last_mini_center = self.frameGeometry().center()
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
            act_s.setChecked(abs(self.requested_scale - scale_v) < 0.05)
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
        try:
            dlg.exec_()
        finally:
            dlg.deleteLater()
            self.raise_()
            self.activateWindow()

    def on_settings_applied(self):
        """Reload timers and styles after settings saved."""
        new_scale = float(self.cfg.get("scale", 1.0))
        if abs(new_scale - self.requested_scale) > 0.001:
            self.set_scale(new_scale)

        self.apply_theme_and_opacity()
        
        bt_sec = max(3, int(self.cfg.get("bt_interval_sec", 10)))
        self.bt_timer.setInterval(bt_sec * 1000)
        
        cdx_sec = max(20, int(self.cfg.get("codex_interval_sec", 60)))
        self.codex_timer.setInterval(cdx_sec * 1000)

        for provider, timer in (("codex", self.codex_timer), ("claude", self.claude_timer)):
            if self.cfg.get(provider + "_quota_enabled", True):
                timer.start()
            else:
                timer.stop()
        
        self.codex_client = CodexUsageClient(self.cfg.get("auth_file_path"))
        self.refresh_all_data(force=True)

    def closeEvent(self, event):
        """Clean shutdown of background threads on close."""
        self._closing = True
        for timer_name in (
            "bt_timer", "codex_timer", "claude_timer", "activity_timer", "relay_timer",
            "focus_check_timer", "watchdog_timer", "_display_update_timer",
        ):
            timer = getattr(self, timer_name, None)
            if timer is not None:
                timer.stop()

        self._watch_screen(None)
        if getattr(self, "_screen_connected", False):
            app = QApplication.instance()
            app.screenAdded.disconnect(self._schedule_display_update)
            app.screenRemoved.disconnect(self._schedule_display_update)
            self.windowHandle().screenChanged.disconnect(self._on_screen_changed)
            self._screen_connected = False

        workers = [
            (attr_name, getattr(self, attr_name, None))
            for attr_name in ("_bt_worker", "_codex_worker", "_claude_worker", "_relay_worker", "_activity_worker")
        ]
        workers = [(attr_name, worker) for attr_name, worker in workers if worker is not None]

        for _, worker in workers:
            try:
                if worker.isRunning():
                    worker.requestInterruption()
            except RuntimeError:
                pass

        deadline = time.monotonic() + 8.0
        for attr_name, worker in workers:
            try:
                if worker.isRunning():
                    remaining_ms = max(0, int((deadline - time.monotonic()) * 1000))
                    if remaining_ms:
                        worker.wait(remaining_ms)
                if not worker.isRunning():
                    worker.deleteLater()
                    setattr(self, attr_name, None)
            except RuntimeError:
                setattr(self, attr_name, None)

        app_inst = QApplication.instance()
        if app_inst and getattr(self, "_tooltip_filter", None) is not None:
            app_inst.removeEventFilter(self._tooltip_filter)

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
