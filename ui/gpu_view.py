"""
GPU Server View Component.
Displays real-time multi-server GPU status (matching Streamlit card layout)
and historical Gantt-style usage timeline natively in PyQt5.
"""

from typing import Dict, Any, List, Optional
import datetime
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QGridLayout, QProgressBar, QComboBox,
    QStackedWidget, QToolTip
)
from PyQt5.QtCore import Qt, pyqtSignal, QRectF, QPoint
from PyQt5.QtGui import QColor, QPainter, QBrush, QPen, QFont, QLinearGradient

from core.gpu_monitor import (
    GPUMonitor, get_hex_for_gpu_vram, clean_gpu_name, get_cn_name
)


class VerticalModelLabel(QLabel):
    """Vertical model text label rendered via QPainter for crisp layout."""
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.raw_text = text
        self.setFixedWidth(28)

    def setModelText(self, text: str):
        self.raw_text = text
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QColor("#E2E8F0"))
        font = QFont("Segoe UI", 8, QFont.Bold)
        painter.setFont(font)

        painter.save()
        # Rotate 90 degrees clockwise (standard book-spine top-to-bottom reading)
        painter.translate(self.width() / 2, self.height() / 2)
        painter.rotate(90)
        text_rect = QRectF(-self.height() / 2, -self.width() / 2, self.height(), self.width())
        painter.drawText(text_rect, Qt.AlignCenter, self.raw_text)
        painter.restore()


class GPUCardWidget(QFrame):
    """Single GPU card status card matching the layout in 图3."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("GPUCard")
        self.setStyleSheet("""
            QFrame#GPUCard {
                background-color: rgba(30, 41, 59, 0.75);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px;
            }
            QFrame#GPUCard:hover {
                background-color: rgba(30, 41, 59, 0.95);
                border: 1px solid rgba(118, 185, 0, 0.45);
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 4, 5, 4)
        layout.setSpacing(3)

        # 1. Header: Left [Model - Index], Right [User / Idle]
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(3)

        self.lbl_name = QLabel("A100 - 0", self)
        self.lbl_name.setStyleSheet("""
            background-color: #334155;
            color: #E2E8F0;
            padding: 1px 4px;
            border-radius: 3px;
            font-size: 9px;
            font-weight: 700;
        """)

        self.lbl_user = QLabel("🟢 Idle", self)
        self.lbl_user.setStyleSheet("""
            font-size: 9px;
            font-weight: 700;
            color: #10B981;
        """)

        header.addWidget(self.lbl_name)
        header.addStretch()
        header.addWidget(self.lbl_user)
        layout.addLayout(header)

        # 2. VRAM Progress Bar
        self.prog_bar = QProgressBar(self)
        self.prog_bar.setFixedHeight(5)
        self.prog_bar.setTextVisible(False)
        self.prog_bar.setRange(0, 100)
        self.prog_bar.setValue(0)
        self.prog_bar.setStyleSheet("""
            QProgressBar {
                background-color: rgba(255, 255, 255, 0.08);
                border: none;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background-color: #10B981;
                border-radius: 2px;
            }
        """)
        layout.addWidget(self.prog_bar)

        # 3. Bottom Row: Memory, Power, Utilization
        stats = QHBoxLayout()
        stats.setContentsMargins(0, 0, 0, 0)
        stats.setSpacing(4)

        self.lbl_mem = QLabel("🧠 0.0/80G", self)
        self.lbl_mem.setStyleSheet("font-size: 9px; color: #CBD5E1;")
        self.lbl_mem.setToolTip("显存占用")

        self.lbl_power = QLabel("⚡ 0/300W", self)
        self.lbl_power.setStyleSheet("font-size: 9px; color: #94A3B8;")
        self.lbl_power.setToolTip("当前功率 / 额定功率")

        self.lbl_util = QLabel("⚙️ 0%", self)
        self.lbl_util.setStyleSheet("font-size: 9px; color: #94A3B8;")
        self.lbl_util.setToolTip("GPU 利用率")

        stats.addWidget(self.lbl_mem)
        stats.addStretch()
        stats.addWidget(self.lbl_power)
        stats.addWidget(self.lbl_util)
        layout.addLayout(stats)

    def update_card(self, card_data: Dict[str, Any]):
        """Render GPU card metrics."""
        gpu_name = card_data.get("name", "GPU")
        idx = card_data.get("index", "0")
        self.lbl_name.setText(f"{gpu_name} - {idx}")

        is_busy = card_data.get("is_busy", False)
        display_user = card_data.get("display_user", "Idle")

        if is_busy:
            self.lbl_user.setText(f"👤 {display_user}")
            self.lbl_user.setStyleSheet("""
                background-color: rgba(239, 68, 68, 0.2);
                color: #F87171;
                padding: 1px 4px;
                border-radius: 3px;
                font-size: 10px;
                font-weight: 700;
            """)
        else:
            self.lbl_user.setText("🟢 Idle")
            self.lbl_user.setStyleSheet("""
                color: #10B981;
                font-size: 10px;
                font-weight: 700;
            """)

        vram_pct = card_data.get("vram_pct", 0.0)
        self.prog_bar.setValue(int(round(vram_pct)))

        # Update progress chunk color based on threshold (<10% green, 10-30% orange, >=30% red)
        chunk_col = get_hex_for_gpu_vram(vram_pct)
        self.prog_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: rgba(255, 255, 255, 0.08);
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {chunk_col};
                border-radius: 2px;
            }}
        """)

        mem_u_gb = card_data.get("memory_used_gb", 0.0)
        mem_t_gb = card_data.get("memory_total_gb", 0.0)
        self.lbl_mem.setText(f"🧠 {mem_u_gb}/{int(mem_t_gb)}G")
        self.lbl_mem.setToolTip(f"显存: {card_data.get('memory_used', 0)} / {card_data.get('memory_total', 0)} MB ({vram_pct}%)")

        p_draw = card_data.get("power_draw", "0")
        p_lim = card_data.get("power_limit", "0")
        self.lbl_power.setText(f"⚡ {p_draw}/{p_lim}W")

        util = card_data.get("utilization", 0)
        self.lbl_util.setText(f"⚙️ {util}%")


class ServerBlockWidget(QWidget):
    """Server block: Left red server ID + dark model strip; Right grid of GPU cards."""
    def __init__(self, sid: str, model: str, parent=None):
        super().__init__(parent)
        self.sid = sid
        self.model = model

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 6)
        layout.setSpacing(6)

        # 1. Left Badge Column
        left_box = QWidget(self)
        left_box.setFixedWidth(28)
        left_layout = QVBoxLayout(left_box)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        # Red ID header
        self.id_box = QLabel(sid, left_box)
        self.id_box.setFixedHeight(24)
        self.id_box.setAlignment(Qt.AlignCenter)
        self.id_box.setStyleSheet("""
            background-color: #EF4444;
            color: #FFFFFF;
            font-size: 13px;
            font-weight: 800;
            border-top-left-radius: 5px;
            border-top-right-radius: 5px;
        """)
        left_layout.addWidget(self.id_box)

        # Dark model strip
        self.model_bar = VerticalModelLabel(model, left_box)
        self.model_bar.setStyleSheet("""
            background-color: #1E293B;
            border-bottom-left-radius: 5px;
            border-bottom-right-radius: 5px;
        """)
        left_layout.addWidget(self.model_bar, 1)

        layout.addWidget(left_box)

        # 2. Right Cards Grid
        self.cards_grid_widget = QWidget(self)
        self.cards_grid = QGridLayout(self.cards_grid_widget)
        self.cards_grid.setContentsMargins(0, 0, 0, 0)
        self.cards_grid.setSpacing(6)

        layout.addWidget(self.cards_grid_widget, 1)

        self.cards_map: Dict[str, GPUCardWidget] = {}

    def update_server(self, sinfo: Dict[str, Any]):
        """Update cards inside this server block."""
        self.model = sinfo.get("model", self.model)
        self.model_bar.setModelText(self.model)

        cards = sinfo.get("cards", [])
        columns_per_row = 2 if len(cards) <= 2 else 3

        for i, cdata in enumerate(cards):
            idx = cdata.get("index", str(i))
            if idx not in self.cards_map:
                card_w = GPUCardWidget(self.cards_grid_widget)
                row = i // columns_per_row
                col = i % columns_per_row
                self.cards_grid.addWidget(card_w, row, col)
                self.cards_map[idx] = card_w

            self.cards_map[idx].update_card(cdata)


class GanttTimelineCanvas(QWidget):
    """
    Native PyQt5 Gantt Chart Canvas.
    Visualizes user occupancy sessions on GPU cards over past N days.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.intervals: List[Dict[str, Any]] = []
        self.days: int = 1
        self.setMinimumHeight(160)
        self.setStyleSheet("background-color: rgba(15, 23, 42, 0.6); border-radius: 6px;")

        # User distinct color generator
        self.user_palette = [
            "#3B82F6", "#10B981", "#F59E0B", "#EC4899",
            "#8B5CF6", "#06B6D4", "#E11D48", "#14B8A6"
        ]
        self.user_color_map: Dict[str, str] = {}

    def set_data(self, intervals: List[Dict[str, Any]], days: int = 1):
        self.intervals = intervals
        self.days = days
        
        # Calculate needed canvas height dynamically based on active unique cards
        unique_tasks = sorted(list(set(x["task"] for x in intervals)))
        needed_h = max(180, len(unique_tasks) * 28 + 40)
        self.setFixedHeight(needed_h)
        self.update()

    def _get_user_color(self, username: str) -> str:
        if username not in self.user_color_map:
            idx = len(self.user_color_map) % len(self.user_palette)
            self.user_color_map[username] = self.user_palette[idx]
        return self.user_color_map[username]

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        w = self.width()
        h = self.height()

        if not self.intervals:
            painter.setPen(QColor("#64748B"))
            painter.setFont(QFont("Segoe UI", 9))
            painter.drawText(self.rect(), Qt.AlignCenter, "暂无历史占用记录")
            return

        now = datetime.datetime.now()
        start_time = now - datetime.timedelta(days=self.days)
        total_seconds = (now - start_time).total_seconds()
        if total_seconds <= 0:
            return

        unique_tasks = sorted(list(set(x["task"] for x in self.intervals)), reverse=True)
        row_h = 26
        header_h = 24
        label_w = 110
        chart_w = w - label_w - 15

        # Draw time header
        painter.setPen(QColor("#94A3B8"))
        painter.setFont(QFont("Segoe UI", 8))
        num_ticks = 4
        for i in range(num_ticks + 1):
            t_frac = i / num_ticks
            tick_time = start_time + datetime.timedelta(seconds=total_seconds * t_frac)
            x = label_w + chart_w * t_frac
            time_str = tick_time.strftime("%m-%d %H:%M" if self.days > 1 else "%H:%M")
            painter.drawText(int(x - 25), 14, 50, 12, Qt.AlignCenter, time_str)
            # Vertical gridline
            painter.setPen(QPen(QColor(255, 255, 255, 12), 1, Qt.DashLine))
            painter.drawLine(int(x), header_h, int(x), h - 5)
            painter.setPen(QColor("#94A3B8"))

        # Draw task rows
        for r_idx, task_name in enumerate(unique_tasks):
            y = header_h + r_idx * row_h
            # Row background
            if r_idx % 2 == 1:
                painter.fillRect(label_w, y, int(chart_w), row_h, QColor(255, 255, 255, 4))

            # Task label (e.g. 8号 A100 [0])
            painter.setPen(QColor("#E2E8F0"))
            painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
            painter.drawText(6, y + 4, label_w - 10, row_h - 8, Qt.AlignVCenter | Qt.AlignLeft, task_name)

        # Draw intervals
        for itv in self.intervals:
            task_name = itv["task"]
            if task_name not in unique_tasks:
                continue
            r_idx = unique_tasks.index(task_name)
            y = header_h + r_idx * row_h + 3

            itv_start = max(start_time, itv["start_dt"])
            itv_finish = min(now, itv["finish_dt"])
            if itv_finish <= itv_start:
                continue

            sec_start = (itv_start - start_time).total_seconds()
            sec_end = (itv_finish - start_time).total_seconds()

            x1 = label_w + (sec_start / total_seconds) * chart_w
            x2 = label_w + (sec_end / total_seconds) * chart_w
            bar_w = max(4.0, x2 - x1)

            user_color = QColor(self._get_user_color(itv["user"]))
            painter.setBrush(QBrush(user_color))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(QRectF(x1, y, bar_w, row_h - 6), 3, 3)

            # Draw username if width fits
            if bar_w > 32:
                painter.setPen(QColor("#FFFFFF"))
                painter.setFont(QFont("Segoe UI", 7, QFont.Bold))
                painter.drawText(QRectF(x1 + 2, y, bar_w - 4, row_h - 6), Qt.AlignCenter, itv["user"])


class GPUServerView(QWidget):
    """
    Complete GPU Server Monitoring View.
    Includes:
    - Top Status Bar (Refresh, Timestamp, DB badge)
    - Tab Switcher (⚡ 实时状态, 📅 历史占用)
    - Tab 1: Real-time Multi-server GPU cards matching 图3
    - Tab 2: Historical Gantt timeline visualization & occupancy session log
    """
    refresh_requested = pyqtSignal()

    def __init__(self, monitor: GPUMonitor, parent=None):
        super().__init__(parent)
        self.monitor = monitor

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(6)

        # 1. Header Bar
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)

        self.title_icon = QLabel("🟢", self)
        self.title_icon.setStyleSheet("font-size: 11px;")

        self.title_lbl = QLabel("GPU服务器监控", self)
        self.title_lbl.setStyleSheet("font-size: 11px; font-weight: 800; color: #FFFFFF;")

        self.btn_refresh = QPushButton("↻ 刷新", self)
        self.btn_refresh.setFixedSize(50, 20)
        self.btn_refresh.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.08);
                color: #E2E8F0;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 4px;
                font-size: 9px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #0284C7;
                color: #FFFFFF;
                border-color: #0284C7;
            }
        """)
        self.btn_refresh.clicked.connect(self._on_refresh_clicked)

        self.badge_time = QLabel("🕒 --:--:--", self)
        self.badge_time.setStyleSheet("""
            background-color: rgba(255, 255, 255, 0.06);
            color: #94A3B8;
            padding: 1px 5px;
            border-radius: 3px;
            font-size: 9px;
        """)

        self.badge_db = QLabel("📡 0.0 M", self)
        self.badge_db.setStyleSheet("""
            background-color: rgba(255, 255, 255, 0.06);
            color: #94A3B8;
            padding: 1px 5px;
            border-radius: 3px;
            font-size: 9px;
        """)
        self.badge_db.setToolTip(f"数据库文件: {self.monitor.db_path}")

        header.addWidget(self.title_icon)
        header.addWidget(self.title_lbl)
        header.addWidget(self.btn_refresh)
        header.addStretch()
        header.addWidget(self.badge_time)
        header.addWidget(self.badge_db)
        root.addLayout(header)

        # 2. Tab Bar: [⚡ 实时状态] | [📅 历史占用]
        tab_bar = QHBoxLayout()
        tab_bar.setContentsMargins(0, 0, 0, 0)
        tab_bar.setSpacing(4)

        self.btn_tab_live = QPushButton("⚡ 实时状态", self)
        self.btn_tab_live.setFixedHeight(22)
        self.btn_tab_live.setCursor(Qt.PointingHandCursor)
        self.btn_tab_live.clicked.connect(lambda: self.switch_tab(0))

        self.btn_tab_hist = QPushButton("📅 历史占用", self)
        self.btn_tab_hist.setFixedHeight(22)
        self.btn_tab_hist.setCursor(Qt.PointingHandCursor)
        self.btn_tab_hist.clicked.connect(lambda: self.switch_tab(1))

        tab_bar.addWidget(self.btn_tab_live)
        tab_bar.addWidget(self.btn_tab_hist)
        tab_bar.addStretch()
        root.addLayout(tab_bar)

        # 3. Stacked View
        self.stack = QStackedWidget(self)

        # --- View 0: Real-time Live Cards ---
        self.scroll_live = QScrollArea(self)
        self.scroll_live.setWidgetResizable(True)
        self.scroll_live.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_live.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical {
                background: rgba(255, 255, 255, 0.02);
                width: 5px;
                border-radius: 2px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.15);
                border-radius: 2px;
            }
        """)

        self.live_container = QWidget()
        self.live_layout = QVBoxLayout(self.live_container)
        self.live_layout.setContentsMargins(2, 2, 2, 2)
        self.live_layout.setSpacing(6)
        self.live_layout.addStretch()
        self.scroll_live.setWidget(self.live_container)
        self.stack.addWidget(self.scroll_live)

        # --- View 1: History Gantt & Timeline ---
        self.hist_container = QWidget(self)
        hist_layout = QVBoxLayout(self.hist_container)
        hist_layout.setContentsMargins(2, 2, 2, 2)
        hist_layout.setSpacing(6)

        hist_ctrl_row = QHBoxLayout()
        hist_ctrl_row.setContentsMargins(0, 0, 0, 0)
        hist_ctrl_row.setSpacing(6)

        hist_lbl = QLabel("查看范围:", self.hist_container)
        hist_lbl.setStyleSheet("font-size: 10px; color: #94A3B8;")

        self.combo_days = QComboBox(self.hist_container)
        self.combo_days.addItem("过去 1 天", 1)
        self.combo_days.addItem("过去 3 天", 3)
        self.combo_days.addItem("过去 7 天", 7)
        self.combo_days.setStyleSheet("""
            QComboBox {
                background-color: #1E293B;
                color: #E2E8F0;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 4px;
                padding: 1px 6px;
                font-size: 10px;
            }
            QComboBox QAbstractItemView {
                background-color: #1E293B;
                color: #E2E8F0;
                selection-background-color: #0284C7;
            }
        """)
        self.combo_days.currentIndexChanged.connect(self._on_days_changed)

        self.btn_hist_refresh = QPushButton("↻ 载入历史", self.hist_container)
        self.btn_hist_refresh.setFixedSize(65, 20)
        self.btn_hist_refresh.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.08);
                color: #E2E8F0;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 4px;
                font-size: 9px;
            }
            QPushButton:hover {
                background-color: #0284C7;
                color: #FFFFFF;
            }
        """)
        self.btn_hist_refresh.clicked.connect(self._on_hist_refresh_clicked)

        hist_ctrl_row.addWidget(hist_lbl)
        hist_ctrl_row.addWidget(self.combo_days)
        hist_ctrl_row.addWidget(self.btn_hist_refresh)
        hist_ctrl_row.addStretch()
        hist_layout.addLayout(hist_ctrl_row)

        # Scroll area for Gantt canvas
        self.scroll_hist = QScrollArea(self.hist_container)
        self.scroll_hist.setWidgetResizable(True)
        self.scroll_hist.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_hist.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical {
                background: rgba(255, 255, 255, 0.02);
                width: 5px;
                border-radius: 2px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.15);
                border-radius: 2px;
            }
        """)
        self.gantt_canvas = GanttTimelineCanvas(self.hist_container)
        self.scroll_hist.setWidget(self.gantt_canvas)
        hist_layout.addWidget(self.scroll_hist, 1)

        self.stack.addWidget(self.hist_container)
        root.addWidget(self.stack, 1)

        # Server widgets mapping
        self.server_widgets: Dict[str, ServerBlockWidget] = {}

        # Set default tab styling
        self.switch_tab(0)

        # Hook monitor signals
        self.monitor.realtime_updated.connect(self.update_live_data)
        self.monitor.history_updated.connect(self.update_history_data)

    def switch_tab(self, index: int):
        """Switch active tab between Live (0) and History (1)."""
        self.stack.setCurrentIndex(index)
        if index == 0:
            self.btn_tab_live.setStyleSheet("""
                background-color: #0284C7;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                font-size: 10px;
                font-weight: 700;
                padding: 2px 10px;
            """)
            self.btn_tab_hist.setStyleSheet("""
                background-color: transparent;
                color: #94A3B8;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 4px;
                font-size: 10px;
                font-weight: 600;
                padding: 2px 10px;
            """)
        else:
            self.btn_tab_hist.setStyleSheet("""
                background-color: #0284C7;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                font-size: 10px;
                font-weight: 700;
                padding: 2px 10px;
            """)
            self.btn_tab_live.setStyleSheet("""
                background-color: transparent;
                color: #94A3B8;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 4px;
                font-size: 10px;
                font-weight: 600;
                padding: 2px 10px;
            """)
            # Trigger history query when opening history tab for the first time
            if not self.gantt_canvas.intervals:
                days = self.combo_days.currentData()
                self.monitor.fetch_history_async(days=days)

    def _on_refresh_clicked(self):
        self.refresh_requested.emit()
        self.monitor.live_worker.start()

    def _on_days_changed(self):
        days = self.combo_days.currentData()
        self.monitor.fetch_history_async(days=days)

    def _on_hist_refresh_clicked(self):
        days = self.combo_days.currentData()
        self.monitor.fetch_history_async(days=days)

    def update_live_data(self, data: Dict[str, Any]):
        """Render live GPU cards."""
        if not data.get("success"):
            return

        self.badge_time.setText(f"🕒 {data.get('last_update', '')}")
        self.badge_db.setText(f"📡 {data.get('db_size_mb', '0.0')} M")

        servers = data.get("servers", {})
        server_order = data.get("server_order", list(servers.keys()))

        for sid in server_order:
            sinfo = servers[sid]
            if sid not in self.server_widgets:
                sb = ServerBlockWidget(sid, sinfo.get("model", "GPU"), self.live_container)
                # Insert before the trailing stretch
                self.live_layout.insertWidget(self.live_layout.count() - 1, sb)
                self.server_widgets[sid] = sb

            self.server_widgets[sid].update_server(sinfo)

    def update_history_data(self, intervals: List[Dict[str, Any]]):
        """Render history Gantt visualization."""
        days = self.combo_days.currentData()
        self.gantt_canvas.set_data(intervals, days=days)
