"""
GPU Server View Component.
Redesigned with unified Dark Glassmorphism aesthetic matching the left column.
Displays 5 GPUs (8号 A100 x2, 7号 L40S x3) in a sleek vertical stack and native history timeline.
"""

from typing import Dict, Any, List, Optional
import datetime
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QProgressBar, QComboBox, QStackedWidget
)
from PyQt5.QtCore import Qt, pyqtSignal, QRectF
from PyQt5.QtGui import QColor, QPainter, QBrush, QPen, QFont

from core.gpu_monitor import (
    GPUMonitor, get_hex_for_gpu_vram, clean_gpu_name, get_cn_name
)
from ui.icons import get_nvidia_pixmap


class GPUCardRow(QFrame):
    """Sleek dark card for a single GPU card matching the left Bluetooth/Codex aesthetic."""
    def __init__(self, sid: str, model: str, index: str, parent=None):
        super().__init__(parent)
        self.sid = sid
        self.model = model
        self.index = index

        self.setObjectName("GPUCardRow")
        self.setStyleSheet("""
            QFrame#GPUCardRow {
                background-color: rgba(255, 255, 255, 0.035);
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 6px;
            }
            QFrame#GPUCardRow:hover {
                background-color: rgba(255, 255, 255, 0.065);
                border: 1px solid rgba(118, 185, 0, 0.35);
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(7, 6, 7, 6)
        layout.setSpacing(4)

        # 1. Top Row: Title badge & User / Idle status
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(4)

        self.lbl_title = QLabel(f"{sid}号 · {model} [{index}]", self)
        self.lbl_title.setStyleSheet("""
            color: #E2E8F0;
            font-size: 10px;
            font-weight: 700;
        """)

        self.lbl_user = QLabel("🟢 空闲", self)
        self.lbl_user.setStyleSheet("""
            color: #10B981;
            font-size: 9px;
            font-weight: 700;
        """)

        top_row.addWidget(self.lbl_title)
        top_row.addStretch()
        top_row.addWidget(self.lbl_user)
        layout.addLayout(top_row)

        # 2. VRAM Progress Bar
        self.prog_bar = QProgressBar(self)
        self.prog_bar.setFixedHeight(4)
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

        # 3. Bottom Stats Row: Memory, Power, Utilization
        stats_row = QHBoxLayout()
        stats_row.setContentsMargins(0, 0, 0, 0)
        stats_row.setSpacing(4)

        self.lbl_mem = QLabel("🧠 0.0 / 0G (0%)", self)
        self.lbl_mem.setStyleSheet("font-size: 9px; color: #CBD5E1; font-family: 'Consolas', monospace;")
        self.lbl_mem.setToolTip("显存占用")

        self.lbl_power = QLabel("⚡ 0/0W", self)
        self.lbl_power.setStyleSheet("font-size: 9px; color: #94A3B8; font-family: 'Consolas', monospace;")
        self.lbl_power.setToolTip("功耗 / 额定")

        self.lbl_util = QLabel("⚙️ 0%", self)
        self.lbl_util.setStyleSheet("font-size: 9px; color: #94A3B8; font-family: 'Consolas', monospace;")
        self.lbl_util.setToolTip("利用率")

        stats_row.addWidget(self.lbl_mem)
        stats_row.addStretch()
        stats_row.addWidget(self.lbl_power)
        stats_row.addWidget(self.lbl_util)
        layout.addLayout(stats_row)

    def update_data(self, cdata: Dict[str, Any], model_name: str):
        """Update GPU metrics."""
        self.model = model_name
        self.lbl_title.setText(f"{self.sid}号 · {model_name} [{self.index}]")

        is_busy = cdata.get("is_busy", False)
        display_user = cdata.get("display_user", "Idle")

        if is_busy:
            self.lbl_user.setText(f"👤 {display_user}")
            self.lbl_user.setStyleSheet("""
                background-color: rgba(239, 68, 68, 0.18);
                color: #F87171;
                border: 1px solid rgba(239, 68, 68, 0.35);
                border-radius: 4px;
                padding: 1px 5px;
                font-size: 9px;
                font-weight: 700;
            """)
        else:
            self.lbl_user.setText("🟢 空闲")
            self.lbl_user.setStyleSheet("""
                color: #10B981;
                font-size: 9px;
                font-weight: 700;
                background: transparent;
                border: none;
            """)

        vram_pct = cdata.get("vram_pct", 0.0)
        self.prog_bar.setValue(int(round(vram_pct)))
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

        mem_u = cdata.get("memory_used_gb", 0.0)
        mem_t = cdata.get("memory_total_gb", 0.0)
        self.lbl_mem.setText(f"🧠 {mem_u:.1f}/{int(mem_t)}G ({vram_pct:.0f}%)")
        self.lbl_mem.setToolTip(f"显存: {cdata.get('memory_used', 0)} / {cdata.get('memory_total', 0)} MB")

        p_draw = cdata.get("power_draw", "0")
        p_lim = cdata.get("power_limit", "0")
        self.lbl_power.setText(f"⚡ {p_draw}/{p_lim}W")

        util = cdata.get("utilization", 0)
        self.lbl_util.setText(f"⚙️ {util}%")


class GanttTimelineCanvas(QWidget):
    """Native PyQt5 Gantt Chart Canvas for 7号 & 8号 server GPU history."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.intervals: List[Dict[str, Any]] = []
        self.days: int = 1
        self.setMinimumHeight(160)
        self.setStyleSheet("background-color: rgba(15, 23, 42, 0.6); border-radius: 6px;")

        self.user_palette = [
            "#3B82F6", "#10B981", "#F59E0B", "#EC4899",
            "#8B5CF6", "#06B6D4", "#E11D48", "#14B8A6"
        ]
        self.user_color_map: Dict[str, str] = {}

    def set_data(self, intervals: List[Dict[str, Any]], days: int = 1):
        # Filter only 7号 and 8号
        self.intervals = [x for x in intervals if x.get("sid") in ("7", "8")]
        self.days = days
        unique_tasks = sorted(list(set(x["task"] for x in self.intervals)))
        needed_h = max(160, len(unique_tasks) * 28 + 36)
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
        header_h = 22
        label_w = 110
        chart_w = w - label_w - 12

        # Draw time header
        painter.setPen(QColor("#94A3B8"))
        painter.setFont(QFont("Segoe UI", 8))
        num_ticks = 4
        for i in range(num_ticks + 1):
            t_frac = i / num_ticks
            tick_time = start_time + datetime.timedelta(seconds=total_seconds * t_frac)
            x = label_w + chart_w * t_frac
            time_str = tick_time.strftime("%m-%d %H:%M" if self.days > 1 else "%H:%M")
            painter.drawText(int(x - 25), 12, 50, 12, Qt.AlignCenter, time_str)
            painter.setPen(QPen(QColor(255, 255, 255, 12), 1, Qt.DashLine))
            painter.drawLine(int(x), header_h, int(x), h - 4)
            painter.setPen(QColor("#94A3B8"))

        # Draw task rows
        for r_idx, task_name in enumerate(unique_tasks):
            y = header_h + r_idx * row_h
            if r_idx % 2 == 1:
                painter.fillRect(label_w, y, int(chart_w), row_h, QColor(255, 255, 255, 4))

            painter.setPen(QColor("#E2E8F0"))
            painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
            painter.drawText(6, y + 3, label_w - 10, row_h - 6, Qt.AlignVCenter | Qt.AlignLeft, task_name)

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

            if bar_w > 32:
                painter.setPen(QColor("#FFFFFF"))
                painter.setFont(QFont("Segoe UI", 7, QFont.Bold))
                painter.drawText(QRectF(x1 + 2, y, bar_w - 4, row_h - 6), Qt.AlignCenter, itv["user"])


class GPUServerView(QWidget):
    """
    Complete GPU Server Monitoring View.
    Unified dark glassmorphism styling, single vertical stack of 5 GPUs (8号 x2, 7号 x3).
    """
    refresh_requested = pyqtSignal()

    def __init__(self, monitor: GPUMonitor, parent=None):
        super().__init__(parent)
        self.monitor = monitor

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 2, 4, 4)
        root.setSpacing(6)

        # 1. Header Bar: Title with NVIDIA logo, Refresh, Timestamp, DB badge
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)

        self.title_icon = QLabel(self)
        self.title_icon.setPixmap(get_nvidia_pixmap(14))

        self.title_lbl = QLabel("GPU 服务器", self)
        self.title_lbl.setStyleSheet("font-size: 11px; font-weight: 800; color: #FFFFFF;")

        self.btn_refresh = QPushButton("🔄", self)
        self.btn_refresh.setFixedSize(20, 20)
        self.btn_refresh.setToolTip("点击刷新 GPU 实时状态")
        self.btn_refresh.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.08);
                color: #E2E8F0;
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 4px;
                font-size: 10px;
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
            background-color: rgba(255, 255, 255, 0.05);
            color: #94A3B8;
            padding: 1px 4px;
            border-radius: 3px;
            font-size: 9px;
            font-family: 'Consolas', monospace;
        """)

        header.addWidget(self.title_icon)
        header.addWidget(self.title_lbl)
        header.addWidget(self.btn_refresh)
        header.addStretch()
        header.addWidget(self.badge_time)
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

        # --- View 0: Real-time Live Cards (Single Vertical Stack) ---
        self.scroll_live = QScrollArea(self)
        self.scroll_live.setWidgetResizable(True)
        self.scroll_live.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_live.viewport().setAutoFillBackground(False)
        self.scroll_live.setStyleSheet("""
            QScrollArea, QScrollArea > QWidget, QScrollArea > QWidget > QWidget {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                background: rgba(255, 255, 255, 0.02);
                width: 4px;
                border-radius: 2px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.15);
                border-radius: 2px;
            }
        """)

        self.live_container = QWidget()
        self.live_container.setStyleSheet("background: transparent;")
        self.live_layout = QVBoxLayout(self.live_container)
        self.live_layout.setContentsMargins(0, 2, 2, 2)
        self.live_layout.setSpacing(5)

        # Pre-create the 5 GPU card rows in order: 7号(3卡) + 8号(2卡)
        self.card_rows: Dict[str, GPUCardRow] = {}

        # 7号 cards (L40S - 0, 1, 2)
        for idx in ["0", "1", "2"]:
            key = f"7-{idx}"
            row = GPUCardRow("7", "L40S", idx, self.live_container)
            self.live_layout.addWidget(row)
            self.card_rows[key] = row

        # 8号 cards (A100 - 0, 1)
        for idx in ["0", "1"]:
            key = f"8-{idx}"
            row = GPUCardRow("8", "A100", idx, self.live_container)
            self.live_layout.addWidget(row)
            self.card_rows[key] = row

        self.live_layout.addStretch()
        self.scroll_live.setWidget(self.live_container)
        self.stack.addWidget(self.scroll_live)

        # --- View 1: History Gantt & Timeline ---
        self.hist_container = QWidget(self)
        hist_layout = QVBoxLayout(self.hist_container)
        hist_layout.setContentsMargins(0, 2, 0, 2)
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
                border: 1px solid rgba(255, 255, 255, 0.12);
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
                border: 1px solid rgba(255, 255, 255, 0.12);
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

        self.scroll_hist = QScrollArea(self.hist_container)
        self.scroll_hist.setWidgetResizable(True)
        self.scroll_hist.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_hist.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical {
                background: rgba(255, 255, 255, 0.02);
                width: 4px;
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

        self.switch_tab(0)

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
        """Render live GPU cards in single vertical column."""
        if not data.get("success"):
            return

        self.badge_time.setText(f"🕒 {data.get('last_update', '')}")

        servers = data.get("servers", {})
        for sid in ["8", "7"]:
            sinfo = servers.get(sid)
            if not sinfo:
                continue
            model_name = sinfo.get("model", "GPU")
            for cdata in sinfo.get("cards", []):
                idx = cdata.get("index", "0")
                key = f"{sid}-{idx}"
                if key in self.card_rows:
                    self.card_rows[key].update_data(cdata, model_name)

    def update_history_data(self, intervals: List[Dict[str, Any]]):
        """Render history Gantt visualization."""
        days = self.combo_days.currentData()
        self.gantt_canvas.set_data(intervals, days=days)
