"""
AIHub Inspection & Candy Question 24-Hour History Timeline Dialog.
Features:
- Daily rows (1 row per day, latest date at the top).
- 24-hour horizontal time axis with configurable granularity (30m / 15m / 1h).
- Color-coded cells for Model Detection (🟢 通过 / 🟠 疑似 / 🔴 失败 / ⚪ 无数据)
  and Candy Question (🟢 通过 / 🔴 不通过 / ⚪ 无数据).
- Interactive hover tooltips and bottom detail inspection card.
- Provider switcher with instant search and filter.
"""

import sys
from typing import Dict, Any, List, Optional
from PyQt5.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QComboBox, QScrollArea, QGraphicsDropShadowEffect, QSizePolicy, QApplication
)
from PyQt5.QtCore import Qt, QRectF, QPoint, QPointF, pyqtSignal, QEvent
from PyQt5.QtGui import QColor, QPainter, QBrush, QPen, QFont, QCursor

from core.aihub_client import AIHubClient


COLOR_PASSED = QColor("#10B981")     # Emerald Green
COLOR_SUSPECTED = QColor("#F59E0B")  # Amber Orange
COLOR_WRONG = QColor("#EF4444")      # Rose Red
COLOR_EMPTY = QColor("#1E293B")      # Slate Dark
COLOR_FUTURE = QColor(255, 255, 255, 8)
COLOR_BORDER = QColor(255, 255, 255, 18)
COLOR_HOVER = QColor("#38BDF8")      # Sky Blue


class TimelineCanvas(QWidget):
    """
    High-performance custom-painted 24-hour timeline grid.
    Renders 1 row per day (today at top down to 7 days).
    """

    slot_hovered = pyqtSignal(dict)   # Emits hovered slot dict or empty dict
    slot_clicked = pyqtSignal(dict)   # Emits clicked slot dict

    def __init__(self, parent=None):
        super().__init__(parent)
        self.timeline_data: Dict[str, Any] = {}
        self.mode: str = "detection"  # "detection", "candy", "dual"
        self.selected_slot_key: Optional[str] = None  # f"{day_idx}_{slot_idx}"
        self.hovered_slot_key: Optional[str] = None
        self.hovered_slot_info: Optional[Dict[str, Any]] = None

        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # Layout metrics
        self.label_width = 82
        self.summary_width = 110
        self.header_height = 28
        self.cell_height_single = 16
        self.cell_height_dual = 28
        self.row_padding = 6
        self.cell_gap = 2

    def set_data(self, data: Dict[str, Any], mode: str = "detection"):
        self.timeline_data = data
        self.mode = mode
        self._update_geometry()
        self.update()

    def set_mode(self, mode: str):
        if self.mode != mode:
            self.mode = mode
            self._update_geometry()
            self.update()

    def _update_geometry(self):
        daily_rows = self.timeline_data.get("daily_rows", [])
        num_days = max(1, len(daily_rows))
        row_h = self.cell_height_dual if self.mode == "dual" else self.cell_height_single
        total_h = self.header_height + num_days * (row_h + self.row_padding) + 16
        self.setFixedHeight(total_h)

    def _get_grid_metrics(self):
        w = max(400, self.width())
        grid_left = self.label_width + 8
        grid_right = w - self.summary_width - 8
        grid_width = max(100, grid_right - grid_left)
        slots_per_day = self.timeline_data.get("slots_per_day", 48)
        cell_w = (grid_width - (slots_per_day - 1) * self.cell_gap) / max(1, slots_per_day)
        return grid_left, grid_width, slots_per_day, cell_w

    def paintEvent(self, event):
        daily_rows = self.timeline_data.get("daily_rows", [])
        if not daily_rows:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        grid_left, grid_width, slots_per_day, cell_w = self._get_grid_metrics()
        row_h = self.cell_height_dual if self.mode == "dual" else self.cell_height_single

        # -------------------------------------------------------------
        # 1. Header Time Axis (00:00, 02:00, ... 24:00)
        # -------------------------------------------------------------
        font_axis = QFont("Segoe UI", 8)
        painter.setFont(font_axis)
        painter.setPen(QColor("#64748B"))

        # Date label title
        painter.drawText(QRectF(4, 2, self.label_width, 18), Qt.AlignLeft | Qt.AlignVCenter, "日期")
        # Summary title
        summary_left = grid_left + grid_width + 8
        painter.drawText(QRectF(summary_left, 2, self.summary_width, 18), Qt.AlignLeft | Qt.AlignVCenter, "当日概览")

        # Time tick labels across 24h
        for hour in range(0, 25, 2):
            frac = hour / 24.0
            x = grid_left + frac * grid_width
            label = f"{hour:02d}:00" if hour < 24 else "24h"
            t_rect = QRectF(x - 18, 2, 36, 16)
            painter.drawText(t_rect, Qt.AlignCenter, label)

            # Subtle vertical tick mark
            painter.setPen(QPen(QColor(255, 255, 255, 12), 1, Qt.DotLine))
            painter.drawLine(QPointF(x, 18), QPointF(x, self.height() - 6))
            painter.setPen(QColor("#64748B"))

        # -------------------------------------------------------------
        # 2. Daily Rows (Latest day on top)
        # -------------------------------------------------------------
        for d_idx, day_info in enumerate(daily_rows):
            y = self.header_height + d_idx * (row_h + self.row_padding)

            # Left Date Label
            is_today = day_info.get("is_today", False)
            painter.setFont(QFont("Segoe UI", 8, QFont.Bold if is_today else QFont.Normal))
            if is_today:
                painter.setPen(QColor("#38BDF8"))
            elif d_idx == 1:
                painter.setPen(QColor("#94A3B8"))
            else:
                painter.setPen(QColor("#64748B"))

            label_rect = QRectF(4, y, self.label_width, row_h)
            painter.drawText(label_rect, Qt.AlignLeft | Qt.AlignVCenter, day_info.get("display_label", ""))

            # Right Summary Badge
            if self.mode == "candy":
                rate_str = day_info.get("candy_rate_str", "--")
                cnt_str = f"{day_info.get('candy_correct', 0)}/{day_info.get('candy_total', 0)}"
                main_rate = day_info.get("candy_correct", 0) / max(1, day_info.get("candy_total", 1))
            else:
                rate_str = day_info.get("det_rate_str", "--")
                cnt_str = f"{day_info.get('det_passed', 0)}/{day_info.get('det_total', 0)}"
                main_rate = day_info.get("det_passed", 0) / max(1, day_info.get("det_total", 1))

            sum_rect = QRectF(summary_left, y, self.summary_width, row_h)
            painter.setFont(QFont("Segoe UI", 7, QFont.Bold))
            if rate_str != "--":
                color_rate = "#10B981" if main_rate >= 0.9 else ("#F59E0B" if main_rate >= 0.7 else "#EF4444")
            else:
                color_rate = "#64748B"
            painter.setPen(QColor(color_rate))
            painter.drawText(sum_rect, Qt.AlignLeft | Qt.AlignVCenter, f"{rate_str} ({cnt_str})")

            # Slots Grid for this Day
            slots = day_info.get("slots", [])
            for s_idx, slot in enumerate(slots):
                x = grid_left + s_idx * (cell_w + self.cell_gap)
                slot_key = f"{d_idx}_{s_idx}"
                is_hovered = (self.hovered_slot_key == slot_key)
                is_selected = (self.selected_slot_key == slot_key)
                is_future = slot.get("is_future", False)

                if self.mode == "dual":
                    # Split cell: top half is detection, bottom half is candy
                    half_h = (row_h - 1) / 2.0
                    r_det = QRectF(x, y, cell_w, half_h)
                    r_candy = QRectF(x, y + half_h + 1, cell_w, half_h)

                    c_det = self._get_status_color(slot.get("det_status"), is_future)
                    c_candy = self._get_candy_color(slot.get("candy_status"), is_future)

                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QBrush(c_det))
                    painter.drawRoundedRect(r_det, 1.5, 1.5)

                    painter.setBrush(QBrush(c_candy))
                    painter.drawRoundedRect(r_candy, 1.5, 1.5)

                    # Highlight outline if hovered or selected
                    if is_hovered or is_selected:
                        full_r = QRectF(x - 1, y - 1, cell_w + 2, row_h + 2)
                        p_color = QColor("#FFFFFF") if is_selected else COLOR_HOVER
                        painter.setPen(QPen(p_color, 1.5))
                        painter.setBrush(Qt.NoBrush)
                        painter.drawRoundedRect(full_r, 2.5, 2.5)
                else:
                    # Single mode: detection or candy
                    r_cell = QRectF(x, y, cell_w, row_h)
                    if self.mode == "candy":
                        fill_c = self._get_candy_color(slot.get("candy_status"), is_future)
                    else:
                        fill_c = self._get_status_color(slot.get("det_status"), is_future)

                    painter.setPen(QPen(COLOR_BORDER, 0.5) if not is_future else Qt.NoPen)
                    painter.setBrush(QBrush(fill_c))
                    painter.drawRoundedRect(r_cell, 2.0, 2.0)

                    # Highlight outline if hovered or selected
                    if is_hovered or is_selected:
                        p_color = QColor("#FFFFFF") if is_selected else COLOR_HOVER
                        painter.setPen(QPen(p_color, 1.5))
                        painter.setBrush(Qt.NoBrush)
                        painter.drawRoundedRect(QRectF(x - 0.5, y - 0.5, cell_w + 1, row_h + 1), 2.5, 2.5)

        painter.end()

    def _get_status_color(self, status: Optional[str], is_future: bool) -> QColor:
        if is_future:
            return COLOR_FUTURE
        if status == "passed":
            return COLOR_PASSED
        elif status == "suspected":
            return COLOR_SUSPECTED
        elif status in ("wrong", "failed"):
            return COLOR_WRONG
        else:
            return COLOR_EMPTY

    def _get_candy_color(self, status: Optional[str], is_future: bool) -> QColor:
        if is_future:
            return COLOR_FUTURE
        if status == "correct":
            return COLOR_PASSED
        elif status == "wrong":
            return COLOR_WRONG
        else:
            return COLOR_EMPTY

    def mouseMoveEvent(self, event):
        slot_key, slot_info = self._get_slot_at_pos(event.pos())
        if slot_key != self.hovered_slot_key:
            self.hovered_slot_key = slot_key
            self.hovered_slot_info = slot_info
            self.update()
            if slot_info:
                self.slot_hovered.emit(slot_info)
                self._show_slot_tooltip(slot_info, event.globalPos())
            else:
                self.slot_hovered.emit({})
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        if self.hovered_slot_key is not None:
            self.hovered_slot_key = None
            self.hovered_slot_info = None
            self.update()
            self.slot_hovered.emit({})
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            slot_key, slot_info = self._get_slot_at_pos(event.pos())
            if slot_info:
                self.selected_slot_key = slot_key
                self.update()
                self.slot_clicked.emit(slot_info)
        super().mousePressEvent(event)

    def _get_slot_at_pos(self, pos: QPoint):
        daily_rows = self.timeline_data.get("daily_rows", [])
        if not daily_rows:
            return None, None

        grid_left, grid_width, slots_per_day, cell_w = self._get_grid_metrics()
        row_h = self.cell_height_dual if self.mode == "dual" else self.cell_height_single

        px = pos.x()
        py = pos.y()

        # Check vertical range
        if py < self.header_height:
            return None, None

        d_idx = int((py - self.header_height) // (row_h + self.row_padding))
        if d_idx < 0 or d_idx >= len(daily_rows):
            return None, None

        # Check horizontal range
        if px < grid_left or px > grid_left + grid_width:
            return None, None

        s_idx = int((px - grid_left) // (cell_w + self.cell_gap))
        if s_idx < 0 or s_idx >= slots_per_day:
            return None, None

        day_info = daily_rows[d_idx]
        slots = day_info.get("slots", [])
        if s_idx < len(slots):
            slot = slots[s_idx]
            info = {
                "day_index": d_idx,
                "date_str": day_info.get("date_str"),
                "display_label": day_info.get("display_label"),
                "slot_index": s_idx,
                "time_range": slot.get("time_range"),
                "det_status": slot.get("det_status"),
                "det_label": slot.get("det_label"),
                "candy_status": slot.get("candy_status"),
                "candy_label": slot.get("candy_label"),
                "candy_ans": slot.get("candy_ans"),
                "model": slot.get("model"),
                "reason": slot.get("reason"),
                "sample_time": slot.get("sample_time"),
                "eff": slot.get("eff"),
                "cache": slot.get("cache"),
                "sr": slot.get("sr"),
                "is_future": slot.get("is_future"),
            }
            return f"{d_idx}_{s_idx}", info

        return None, None

    def _show_slot_tooltip(self, slot: Dict[str, Any], global_pos: QPoint):
        if slot.get("is_future"):
            self.setToolTip(f"{slot.get('display_label')} {slot.get('time_range')}\n⏱ 未到时间")
            return

        date_lbl = slot.get("display_label", "")
        time_range = slot.get("time_range", "")
        det_lbl = slot.get("det_label", "")
        candy_lbl = slot.get("candy_label", "")
        candy_ans = slot.get("candy_ans", "")
        sample_time = slot.get("sample_time") or "时段内聚合"
        model = slot.get("model", "")

        candy_desc = f"{candy_lbl} (回答: {candy_ans})" if candy_ans else candy_lbl

        lines = [
            f"📅 {date_lbl} [{time_range}]",
            f"🎯 模型真实性检测: {det_lbl} (测试目标: {model or '默认'})",
            f"🍬 糖果题实测结果: {candy_desc}",
        ]
        if slot.get("reason"):
            lines.append(f"📝 官方检测说明: {slot.get('reason')}")
        if slot.get("eff") is not None or slot.get("cache") is not None or slot.get("sr") is not None:
            eff_s = f"{slot['eff']:.2f}x" if slot.get("eff") is not None else "--"
            c_s = f"{slot['cache']:.1f}%" if slot.get("cache") is not None else "--"
            sr_s = f"{slot['sr']:.1f}%" if slot.get("sr") is not None else "--"
            lines.append(f"⚡ 链路实测指标: 真实倍率 {eff_s} · 缓存率 {c_s} · 成功率 {sr_s}")
        if sample_time:
            lines.append(f"⏱ 采样时间: {sample_time}")

        self.setToolTip("\n".join(lines))


class AIHubHistoryDialog(QDialog):
    """
    Modern dark-themed popup dialog for inspecting 24-hour probe timeline history.
    """

    def __init__(self, aihub_client: AIHubClient, initial_code: str = "", initial_dimension: str = "detection", parent=None):
        super().__init__(parent)
        self.aihub_client = aihub_client
        self.current_code = initial_code
        self.current_dimension = initial_dimension  # "detection", "candy", "dual"
        self.current_granularity = 30               # 30 mins (48 blocks/day)
        self.current_days = 7                       # 7 days

        # Available provider codes
        self.all_providers = []
        if self.aihub_client.cached_data:
            self.all_providers = self.aihub_client.cached_data.get("all_providers", [])
        if not self.all_providers:
            try:
                data = self.aihub_client.fetch_data()
                self.all_providers = data.get("all_providers", [])
            except Exception:
                pass

        if not self.current_code and self.all_providers:
            self.current_code = self.all_providers[0]["code"]

        self.init_window()
        self.init_ui()
        self.load_data()

    def init_window(self):
        self.setWindowTitle("AIHub 探针实测与质量历史 (24h时间轴)")
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.resize(760, 540)

    def init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)

        container = QWidget(self)
        container.setObjectName("HistoryContainer")
        container.setStyleSheet("""
            QWidget#HistoryContainer {
                background-color: rgba(18, 22, 31, 0.98);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 12px;
            }
        """)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(22)
        shadow.setColor(QColor(0, 0, 0, 190))
        shadow.setOffset(0, 4)
        container.setGraphicsEffect(shadow)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        # -------------------------------------------------------------
        # 1. Header Bar: Title + Provider Selector + Close Button
        # -------------------------------------------------------------
        header = QHBoxLayout()
        header.setSpacing(8)

        title_lbl = QLabel("📊 AIHub 探针实测与质量历史 (24h时间轴)")
        title_lbl.setStyleSheet("font-size: 13px; font-weight: 700; color: #F1F5F9;")
        header.addWidget(title_lbl)

        header.addStretch()

        # Provider Selector ComboBox
        lbl_sel = QLabel("供应商:")
        lbl_sel.setStyleSheet("font-size: 10px; color: #94A3B8; font-weight: 600;")
        header.addWidget(lbl_sel)

        self.combo_provider = QComboBox()
        self.combo_provider.setStyleSheet("""
            QComboBox {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 4px;
                color: #38BDF8;
                font-size: 11px;
                font-weight: 700;
                padding: 2px 8px;
                min-width: 140px;
            }
            QComboBox QAbstractItemView {
                background: #1E293B;
                color: #F8FAFC;
                selection-background-color: #3B82F6;
                padding: 3px;
            }
        """)
        for p in self.all_providers:
            code = p.get("code", "")
            det = p.get("detection_dot", "")
            candy = p.get("candy_dot", "")
            self.combo_provider.addItem(f"{det}{candy} {code}", code)

        # Set initial selection
        idx = self.combo_provider.findData(self.current_code)
        if idx >= 0:
            self.combo_provider.setCurrentIndex(idx)
        self.combo_provider.currentIndexChanged.connect(self._on_provider_changed)
        header.addWidget(self.combo_provider)

        # Close button
        btn_close = QPushButton("✕")
        btn_close.setFixedSize(24, 24)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                color: #94A3B8;
                border: none;
                border-radius: 12px;
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: rgba(239, 68, 68, 0.3);
                color: #EF4444;
            }
        """)
        btn_close.clicked.connect(self.close)
        header.addWidget(btn_close)
        layout.addLayout(header)

        # -------------------------------------------------------------
        # 2. Control Row: Dimension Toggle + Granularity Toggle + Days
        # -------------------------------------------------------------
        ctrl_frame = QFrame()
        ctrl_frame.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 6px;
            }
        """)
        ctrl_lay = QHBoxLayout(ctrl_frame)
        ctrl_lay.setContentsMargins(8, 4, 8, 4)
        ctrl_lay.setSpacing(8)

        lbl_dim = QLabel("维度:")
        lbl_dim.setStyleSheet("font-size: 10px; font-weight: 700; color: #CBD5E1;")
        ctrl_lay.addWidget(lbl_dim)

        btn_style = """
            QPushButton {
                background: rgba(255, 255, 255, 0.05);
                color: #94A3B8;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 10px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.1);
                color: #F8FAFC;
            }
            QPushButton:checked {
                background: rgba(56, 189, 248, 0.2);
                border-color: #38BDF8;
                color: #38BDF8;
                font-weight: 700;
            }
        """

        self.btn_mode_det = QPushButton("🎯 模型真实性检测")
        self.btn_mode_det.setCheckable(True)
        self.btn_mode_det.setCursor(Qt.PointingHandCursor)
        self.btn_mode_det.setStyleSheet(btn_style)

        self.btn_mode_candy = QPushButton("🍬 糖果题实测")
        self.btn_mode_candy.setCheckable(True)
        self.btn_mode_candy.setCursor(Qt.PointingHandCursor)
        self.btn_mode_candy.setStyleSheet(btn_style)

        self.btn_mode_dual = QPushButton("📋 双维度对比")
        self.btn_mode_dual.setCheckable(True)
        self.btn_mode_dual.setCursor(Qt.PointingHandCursor)
        self.btn_mode_dual.setStyleSheet(btn_style)

        if self.current_dimension == "candy":
            self.btn_mode_candy.setChecked(True)
        elif self.current_dimension == "dual":
            self.btn_mode_dual.setChecked(True)
        else:
            self.btn_mode_det.setChecked(True)

        self.btn_mode_det.clicked.connect(lambda: self._set_dimension("detection"))
        self.btn_mode_candy.clicked.connect(lambda: self._set_dimension("candy"))
        self.btn_mode_dual.clicked.connect(lambda: self._set_dimension("dual"))

        ctrl_lay.addWidget(self.btn_mode_det)
        ctrl_lay.addWidget(self.btn_mode_candy)
        ctrl_lay.addWidget(self.btn_mode_dual)

        ctrl_lay.addStretch()

        # Granularity
        lbl_gran = QLabel("时序格数:")
        lbl_gran.setStyleSheet("font-size: 10px; font-weight: 700; color: #CBD5E1;")
        ctrl_lay.addWidget(lbl_gran)

        self.combo_gran = QComboBox()
        self.combo_gran.addItems(["30分钟 / 格 (48格/天) [推荐]", "15分钟 / 格 (96格/天)", "1小时 / 格 (24格/天)"])
        self.combo_gran.setStyleSheet("""
            QComboBox {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 4px;
                color: #CBD5E1;
                font-size: 9.5px;
                padding: 1px 6px;
            }
        """)
        self.combo_gran.currentIndexChanged.connect(self._on_granularity_changed)
        ctrl_lay.addWidget(self.combo_gran)

        # Days
        self.combo_days = QComboBox()
        self.combo_days.addItems(["近 7 天历史", "近 3 天历史", "仅今天"])
        self.combo_days.setStyleSheet("""
            QComboBox {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 4px;
                color: #CBD5E1;
                font-size: 9.5px;
                padding: 1px 6px;
            }
        """)
        self.combo_days.currentIndexChanged.connect(self._on_days_changed)
        ctrl_lay.addWidget(self.combo_days)

        layout.addWidget(ctrl_frame)

        # -------------------------------------------------------------
        # 3. Provider Live Overview Banner
        # -------------------------------------------------------------
        self.banner_frame = QFrame()
        self.banner_frame.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.02);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 6px;
                padding: 4px;
            }
        """)
        banner_lay = QHBoxLayout(self.banner_frame)
        banner_lay.setContentsMargins(8, 4, 8, 4)

        self.lbl_banner_info = QLabel("正在加载供应商历史...")
        self.lbl_banner_info.setStyleSheet("font-size: 10px; color: #CBD5E1;")
        banner_lay.addWidget(self.lbl_banner_info)
        layout.addWidget(self.banner_frame)

        # -------------------------------------------------------------
        # 4. Timeline Grid Canvas inside Scroll Area
        # -------------------------------------------------------------
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 6px;
            }
            QScrollBar:vertical {
                background: rgba(0, 0, 0, 0.2);
                width: 6px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.18);
                border-radius: 3px;
            }
        """)
        scroll.viewport().setStyleSheet("background: transparent; border: none;")

        self.canvas = TimelineCanvas(self)
        self.canvas.slot_hovered.connect(self._on_slot_hovered)
        self.canvas.slot_clicked.connect(self._on_slot_clicked)
        scroll.setWidget(self.canvas)
        layout.addWidget(scroll, 1)

        # -------------------------------------------------------------
        # 5. Detail Inspector Panel (Shows details of hovered / clicked cell)
        # -------------------------------------------------------------
        self.inspect_frame = QFrame()
        self.inspect_frame.setFixedHeight(68)
        self.inspect_frame.setStyleSheet("""
            QFrame {
                background: rgba(0, 0, 0, 0.4);
                border: 1px solid rgba(56, 189, 248, 0.25);
                border-radius: 6px;
                padding: 4px;
            }
        """)
        inspect_lay = QVBoxLayout(self.inspect_frame)
        inspect_lay.setContentsMargins(8, 4, 8, 4)
        inspect_lay.setSpacing(2)

        self.lbl_inspect_title = QLabel("💡 鼠标移动或点击上方时间方格，查看具体时间段实测详情")
        self.lbl_inspect_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #38BDF8;")
        inspect_lay.addWidget(self.lbl_inspect_title)

        self.lbl_inspect_desc = QLabel("支持查看模型真实性检测（测试目标/结论）、糖果题回答（21为通过）以及当时链路瞬时倍率、缓存率与成功率。")
        self.lbl_inspect_desc.setStyleSheet("font-size: 9.5px; color: #94A3B8;")
        inspect_lay.addWidget(self.lbl_inspect_desc)

        layout.addWidget(self.inspect_frame)

        # -------------------------------------------------------------
        # 6. Legend & Footer Bar
        # -------------------------------------------------------------
        footer = QHBoxLayout()
        footer.setSpacing(10)

        # Legend dots
        legend_items = [
            ("🟢", "#10B981", "通过 / 答案正确 (21)"),
            ("🟠", "#F59E0B", "疑似 / 存疑"),
            ("🔴", "#EF4444", "未通过 / 答案错误"),
            ("⚪", "#64748B", "无检测采样"),
            ("⬛", "#334155", "未来时段"),
        ]
        for emo, col, desc in legend_items:
            lbl_leg = QLabel(f"<span style='color: {col}; font-weight: 700;'>{emo}</span> <span style='font-size: 9px; color: #94A3B8;'>{desc}</span>")
            footer.addWidget(lbl_leg)

        footer.addStretch()

        btn_ok = QPushButton("确定")
        btn_ok.setCursor(Qt.PointingHandCursor)
        btn_ok.setStyleSheet("""
            QPushButton {
                background: #10B981;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                padding: 4px 18px;
                font-size: 10.5px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: #059669;
            }
        """)
        btn_ok.clicked.connect(self.close)
        footer.addWidget(btn_ok)
        layout.addLayout(footer)

        root.addWidget(container)

    def load_data(self):
        if not self.current_code:
            return

        # Fetch timeline data from AIHubClient
        tl_data = self.aihub_client.get_provider_timeline_data(
            code=self.current_code,
            days=self.current_days,
            granularity_mins=self.current_granularity
        )

        # Update banner
        prov = tl_data.get("provider") or {}
        det_dot = prov.get("detection_dot", "⚪")
        det_lbl = prov.get("detection_label", "未检")
        candy_dot = prov.get("candy_dot", "⚪")
        candy_lbl = prov.get("candy_label", "--")
        nom_mult = prov.get("multiplier_str", "--")
        eff_mult = prov.get("effective_multiplier_str") or "--"
        sr_str = prov.get("success_rate_str", "--")
        cache_str = prov.get("cache_hit_rate", "--")

        daily_rows = tl_data.get("daily_rows", [])
        total_det_tested = sum(r.get("det_total", 0) for r in daily_rows)
        total_det_passed = sum(r.get("det_passed", 0) for r in daily_rows)
        total_candy_tested = sum(r.get("candy_total", 0) for r in daily_rows)
        total_candy_correct = sum(r.get("candy_correct", 0) for r in daily_rows)

        det_rate = f"{(total_det_passed / total_det_tested * 100):.1f}%" if total_det_tested > 0 else "--"
        candy_rate = f"{(total_candy_correct / total_candy_tested * 100):.1f}%" if total_candy_tested > 0 else "--"

        b_text = (
            f"<b>供应商:</b> <span style='color: #38BDF8; font-weight: 700;'>{self.current_code}</span> "
            f"| <b>当前检测:</b> {det_dot} {det_lbl} | <b>当前糖果:</b> {candy_dot} {candy_lbl} "
            f"| <b>倍率:</b> {nom_mult} (实折 {eff_mult}) | <b>缓存:</b> {cache_str} | <b>成功率:</b> {sr_str}<br>"
            f"<span style='color: #94A3B8;'>历史统计 ({self.current_days}天): "
            f"模型检测通过率 <b style='color: #10B981;'>{det_rate}</b> ({total_det_passed}/{total_det_tested}) · "
            f"糖果题通过率 <b style='color: #10B981;'>{candy_rate}</b> ({total_candy_correct}/{total_candy_tested})</span>"
        )
        self.lbl_banner_info.setText(b_text)

        # Update canvas
        self.canvas.set_data(tl_data, mode=self.current_dimension)

    def _set_dimension(self, dim: str):
        self.current_dimension = dim
        self.btn_mode_det.setChecked(dim == "detection")
        self.btn_mode_candy.setChecked(dim == "candy")
        self.btn_mode_dual.setChecked(dim == "dual")
        self.canvas.set_mode(dim)

    def _on_granularity_changed(self, idx: int):
        if idx == 0:
            self.current_granularity = 30
        elif idx == 1:
            self.current_granularity = 15
        else:
            self.current_granularity = 60
        self.load_data()

    def _on_days_changed(self, idx: int):
        if idx == 0:
            self.current_days = 7
        elif idx == 1:
            self.current_days = 3
        else:
            self.current_days = 1
        self.load_data()

    def _on_provider_changed(self, idx: int):
        code = self.combo_provider.itemData(idx)
        if code and code != self.current_code:
            self.current_code = code
            self.load_data()

    def _on_slot_hovered(self, slot: Dict[str, Any]):
        if not slot:
            return
        self._display_slot_details(slot)

    def _on_slot_clicked(self, slot: Dict[str, Any]):
        if not slot:
            return
        self._display_slot_details(slot, is_pinned=True)

    def _display_slot_details(self, slot: Dict[str, Any], is_pinned: bool = False):
        if slot.get("is_future"):
            self.lbl_inspect_title.setText(f"⏱ {slot.get('display_label')} {slot.get('time_range')} (未到时间)")
            self.lbl_inspect_desc.setText("该时段尚未发生，等待探针后续自动采样。")
            return

        date_lbl = slot.get("display_label", "")
        time_range = slot.get("time_range", "")
        det_lbl = slot.get("det_label", "")
        det_st = slot.get("det_status", "")
        candy_lbl = slot.get("candy_label", "")
        candy_st = slot.get("candy_status", "")
        candy_ans = slot.get("candy_ans", "")
        model = slot.get("model", "")
        reason = slot.get("reason", "")

        det_color = "#10B981" if det_st == "passed" else ("#F59E0B" if det_st == "suspected" else ("#EF4444" if det_st in ("wrong", "failed") else "#64748B"))
        candy_color = "#10B981" if candy_st == "correct" else ("#EF4444" if candy_st == "wrong" else "#64748B")

        ans_desc = f"(回答: {candy_ans})" if candy_ans else ""
        pin_tag = " 📌 [已选定]" if is_pinned else ""

        self.lbl_inspect_title.setText(
            f"⏱ <b>{date_lbl} [{time_range}]</b>{pin_tag}  "
            f"🎯 模型检测: <b style='color: {det_color};'>{det_lbl}</b> ({model or '默认'})  "
            f"🍬 糖果题实测: <b style='color: {candy_color};'>{candy_lbl}</b> {ans_desc}"
        )

        eff_s = f"{slot['eff']:.2f}x" if slot.get("eff") is not None else "--"
        c_s = f"{slot['cache']:.1f}%" if slot.get("cache") is not None else "--"
        sr_s = f"{slot['sr']:.1f}%" if slot.get("sr") is not None else "--"
        sample_t = slot.get("sample_time") or "时段内聚合"

        reason_str = f"说明: {reason} | " if reason else ""
        self.lbl_inspect_desc.setText(
            f"{reason_str}采样时效: {sample_t} | 瞬时真实倍率: {eff_s} | 实测缓存率: {c_s} | 接口成功率: {sr_s}"
        )

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, "_drag_pos"):
            self.move(event.globalPos() - self._drag_pos)
            event.accept()
