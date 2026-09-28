"""
Relay Station View Widget.
Renders tabbed cards for Square API and AIHub monitoring in the expanded widget.
Designed for two-column side-by-side presentation.
"""

from typing import Dict, Any, List, Optional
import os

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QStackedWidget, QSizePolicy, QGridLayout
)
from PyQt5.QtCore import Qt, pyqtSignal, QRectF, QSize
from PyQt5.QtGui import QPainter, QColor, QFont, QCursor, QBrush, QPixmap


class SuccessRateBarWidget(QWidget):
    """
    Renders benchmark success rate sparkline matching user screenshot:
    Vertical rounded pill bars followed by percentage text (e.g. 100.0% or 98.6%).
    """

    def __init__(self, count: int = 16, success_rate: float = 100.0, parent=None):
        super().__init__(parent)
        self.bar_count = max(4, min(count, 16))
        self.rate = success_rate
        self.setFixedHeight(14)
        self.setFixedWidth(75)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        bar_w = 0.95
        bar_h = 8.5
        gap = 0.7
        y = (self.height() - bar_h) / 2.0

        emerald = QColor("#10B981")
        amber = QColor("#F59E0B")
        has_fail = self.rate < 100.0

        x = 0.5
        for i in range(self.bar_count):
            if has_fail and i == self.bar_count - 2:
                painter.setBrush(QBrush(amber))
            else:
                painter.setBrush(QBrush(emerald))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(QRectF(x, y, bar_w, bar_h), 0.4, 0.4)
            x += bar_w + gap

        # Percentage text
        x += 2.0
        painter.setPen(emerald)
        font = QFont("Segoe UI", 7, QFont.Bold)
        font.setStyleHint(QFont.SansSerif)
        painter.setFont(font)

        text = f"{self.rate:.1f}%"
        rect = QRectF(x, 0, self.width() - x, self.height())
        painter.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter, text)
        painter.end()


class ClickableImageCard(QFrame):
    """Card containing an embedded Pelican thumbnail image with click handler."""
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("PelicanCard")
        self.setStyleSheet("""
            QFrame#PelicanCard {
                background: rgba(16, 185, 129, 0.05);
                border: 1px solid rgba(16, 185, 129, 0.22);
                border-radius: 6px;
            }
            QFrame#PelicanCard:hover {
                background: rgba(16, 185, 129, 0.12);
                border-color: rgba(16, 185, 129, 0.45);
            }
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()
        else:
            super().mousePressEvent(event)


class RelayStationView(QWidget):
    """Component for displaying Square API & AIHub live stats in expanded mode."""

    pelican_clicked = pyqtSignal()
    refresh_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_tab = 0
        self._square_data: Dict[str, Any] = {}
        self._aihub_data: Dict[str, Any] = {}
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Card container with glassmorphism style matching Codex card
        self.card = QFrame(self)
        self.card.setProperty("class", "CardSection")
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(6, 5, 6, 5)
        card_layout.setSpacing(5)

        # 1. Header with Tab Toggle
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel("中转站")
        self.title_lbl.setStyleSheet("font-size: 10px; font-weight: 700; color: #E2E8F0;")

        # Tab Buttons
        self.btn_square = QPushButton("Square")
        self.btn_square.setCheckable(True)
        self.btn_square.setChecked(True)
        self.btn_square.setCursor(Qt.PointingHandCursor)
        self.btn_square.setFixedHeight(20)

        self.btn_aihub = QPushButton("AIHub")
        self.btn_aihub.setCheckable(True)
        self.btn_aihub.setChecked(False)
        self.btn_aihub.setCursor(Qt.PointingHandCursor)
        self.btn_aihub.setFixedHeight(20)

        self.btn_refresh = QPushButton("🔄")
        self.btn_refresh.setFixedSize(20, 20)
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        self.btn_refresh.setToolTip("刷新中转站数据")
        self.btn_refresh.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                font-size: 11px;
                color: #64748B;
            }
            QPushButton:hover {
                color: #38BDF8;
            }
        """)
        self.btn_refresh.clicked.connect(self.refresh_requested.emit)

        tab_btn_style = """
            QPushButton {
                background: rgba(255, 255, 255, 0.05);
                color: #94A3B8;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 4px;
                padding: 1px 5px;
                font-size: 9px;
                font-weight: 600;
                min-width: 44px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.1);
                color: #F8FAFC;
            }
            QPushButton:checked {
                background: rgba(59, 130, 246, 0.25);
                border-color: #3B82F6;
                color: #60A5FA;
            }
        """
        self.btn_square.setStyleSheet(tab_btn_style)
        self.btn_aihub.setStyleSheet(tab_btn_style)

        self.btn_square.clicked.connect(lambda: self.switch_tab(0))
        self.btn_aihub.clicked.connect(lambda: self.switch_tab(1))

        header.addWidget(self.title_lbl)
        header.addStretch()
        header.addWidget(self.btn_square)
        header.addWidget(self.btn_aihub)
        header.addWidget(self.btn_refresh)
        card_layout.addLayout(header)

        # Divider inside card
        div = QFrame(self.card)
        div.setFrameShape(QFrame.HLine)
        div.setStyleSheet("background-color: rgba(255, 255, 255, 0.05); height: 1px; border: none;")
        card_layout.addWidget(div)

        # 2. Stacked Content (Square API vs AIHub)
        self.stack = QStackedWidget(self.card)

        # Panel 0: Square API
        self.square_panel = QWidget()
        self.init_square_panel()
        self.stack.addWidget(self.square_panel)

        # Panel 1: AIHub
        self.aihub_panel = QWidget()
        self.init_aihub_panel()
        self.stack.addWidget(self.aihub_panel)

        card_layout.addWidget(self.stack)
        main_layout.addWidget(self.card)

    def init_square_panel(self):
        p_layout = QVBoxLayout(self.square_panel)
        p_layout.setContentsMargins(0, 1, 0, 1)
        p_layout.setSpacing(4)

        # 1. Square Sub-header
        self.sq_status_lbl = QLabel("🟢 Square API (api.squarefaceicon.org)")
        self.sq_status_lbl.setStyleSheet("font-size: 10px; font-weight: 600; color: #10B981;")
        p_layout.addWidget(self.sq_status_lbl)

        # 2. Target Models Badges Container
        self.sq_models_container = QWidget(self.square_panel)
        self.sq_models_layout = QVBoxLayout(self.sq_models_container)
        self.sq_models_layout.setContentsMargins(0, 0, 0, 0)
        self.sq_models_layout.setSpacing(2)
        p_layout.addWidget(self.sq_models_container)

        # 3. Benchmark Grid Container (Table matching user screenshot)
        self.sq_bench_container = QWidget(self.square_panel)
        self.sq_bench_grid = QGridLayout(self.sq_bench_container)
        self.sq_bench_grid.setContentsMargins(2, 2, 2, 2)
        self.sq_bench_grid.setHorizontalSpacing(4)
        self.sq_bench_grid.setVerticalSpacing(3)
        p_layout.addWidget(self.sq_bench_container)

        p_layout.addStretch()

    def init_aihub_panel(self):
        p_layout = QVBoxLayout(self.aihub_panel)
        p_layout.setContentsMargins(0, 1, 0, 1)
        p_layout.setSpacing(4)

        # 1. Sub-header: AIHub user balance & status
        self.aihub_header_layout = QHBoxLayout()
        self.aihub_balance_lbl = QLabel("余额: ¥--")
        self.aihub_balance_lbl.setStyleSheet("font-size: 11px; font-weight: 700; color: #10B981;")

        self.aihub_status_lbl = QLabel("已连接")
        self.aihub_status_lbl.setStyleSheet("font-size: 9px; color: #94A3B8;")

        self.aihub_header_layout.addWidget(self.aihub_balance_lbl)
        self.aihub_header_layout.addStretch()
        self.aihub_header_layout.addWidget(self.aihub_status_lbl)
        p_layout.addLayout(self.aihub_header_layout)

        # 2. Container for top 3 group rows (Grid layout for sharp columns)
        self.aihub_groups_widget = QWidget(self.aihub_panel)
        self.aihub_groups_grid = QGridLayout(self.aihub_groups_widget)
        self.aihub_groups_grid.setContentsMargins(2, 1, 2, 1)
        self.aihub_groups_grid.setHorizontalSpacing(6)
        self.aihub_groups_grid.setVerticalSpacing(3)
        p_layout.addWidget(self.aihub_groups_widget)

        # 3. Direct Pelican Embedded Image Card (Clickable to view history)
        self.pelican_card = ClickableImageCard(self.aihub_panel)
        p_card_lay = QVBoxLayout(self.pelican_card)
        p_card_lay.setContentsMargins(5, 4, 5, 4)
        p_card_lay.setSpacing(3)

        self.pelican_hdr_lbl = QLabel("📷 鹈鹕 (Pelican) 实测图 (点击查看同运营商5张历史 ↗)")
        self.pelican_hdr_lbl.setStyleSheet("font-size: 9px; font-weight: 600; color: #34D399;")
        p_card_lay.addWidget(self.pelican_hdr_lbl)

        self.pelican_img_lbl = QLabel()
        self.pelican_img_lbl.setFixedHeight(68)
        self.pelican_img_lbl.setAlignment(Qt.AlignCenter)
        self.pelican_img_lbl.setStyleSheet("""
            QLabel {
                background: rgba(0, 0, 0, 0.28);
                border-radius: 4px;
                color: #64748B;
                font-size: 9px;
            }
        """)
        self.pelican_img_lbl.setText("⏳ 正在加载鹈鹕实测图...")
        p_card_lay.addWidget(self.pelican_img_lbl)

        self.pelican_card.clicked.connect(self.pelican_clicked.emit)
        p_layout.addWidget(self.pelican_card)

        p_layout.addStretch()

    def switch_tab(self, index: int):
        self.current_tab = index
        self.stack.setCurrentIndex(index)
        self.btn_square.setChecked(index == 0)
        self.btn_aihub.setChecked(index == 1)
        self.stack.adjustSize()
        self.card.adjustSize()
        if self.parentWidget():
            self.parentWidget().adjustSize()

    def update_square_data(self, data: Dict[str, Any]):
        """Render Square API target models and group performance table."""
        self._square_data = data
        if not data.get("success"):
            self.sq_status_lbl.setText(f"⚠️ {data.get('error', '获取失败')}")
            return

        balance_info = data.get("balance", {})
        used = balance_info.get("total_usage")
        if used is not None:
            self.sq_status_lbl.setText(f"🟢 Square 正常 · 已用: ${used:.2f}")
        else:
            self.sq_status_lbl.setText("🟢 Square 正常 · 公开价格")

        # 1. Update Target Model Quick Badges
        while self.sq_models_layout.count():
            item = self.sq_models_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    sub = item.layout().takeAt(0)
                    if sub.widget():
                        sub.widget().deleteLater()

        models = data.get("models", [])
        for m in models:
            m_row = QHBoxLayout()
            m_row.setContentsMargins(1, 0, 1, 0)
            m_row.setSpacing(4)

            d_name = m.get("display_name", "")
            if "Opus" in d_name:
                short_name = "Opus 5.5"
            elif "Astra" in d_name:
                short_name = "GPT-6 Astra"
            elif "v4.1" in d_name:
                short_name = "DS-v4.1"
            else:
                short_name = d_name

            name_lbl = QLabel(short_name)
            name_lbl.setStyleSheet("font-size: 9px; font-weight: 700; color: #CBD5E1;")
            m_row.addWidget(name_lbl)

            tags_str = " · ".join([f"{g['name']} {g['ratio_str']}" for g in m.get("groups", [])])
            tags_lbl = QLabel(tags_str)
            tags_lbl.setStyleSheet("font-size: 8px; color: #94A3B8;")
            m_row.addWidget(tags_lbl)
            m_row.addStretch()

            self.sq_models_layout.addLayout(m_row)

        # 2. Update Group Benchmark Table (matching user screenshot)
        while self.sq_bench_grid.count():
            item = self.sq_bench_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Table Header
        h_titles = ["分组", "倍率", "速度", "首字", "延迟", "成功率"]
        h_aligns = [Qt.AlignLeft, Qt.AlignCenter, Qt.AlignRight, Qt.AlignRight, Qt.AlignRight, Qt.AlignRight]
        for col_idx, (title, align) in enumerate(zip(h_titles, h_aligns)):
            h_lbl = QLabel(title)
            h_lbl.setAlignment(align | Qt.AlignVCenter)
            h_lbl.setStyleSheet("font-size: 8px; font-weight: 700; color: #64748B;")
            self.sq_bench_grid.addWidget(h_lbl, 0, col_idx)
        self.sq_bench_grid.setColumnMinimumWidth(5, 75)

        perf_groups = data.get("performance_groups", [])
        for row_idx, pg in enumerate(perf_groups, start=1):
            # Name in exact color from screenshot
            color = pg.get("color", "#10B981")
            name_lbl = QLabel(pg.get("short_name", pg["name"]))
            name_lbl.setToolTip(pg.get("name", ""))
            name_lbl.setStyleSheet(f"font-size: 9px; font-weight: 700; color: {color};")

            mult_lbl = QLabel(pg.get("multiplier", "--"))
            mult_lbl.setAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            mult_lbl.setStyleSheet("font-size: 8px; font-weight: 600; color: #60A5FA;")

            tps_lbl = QLabel(pg.get("tps", "--"))
            tps_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            tps_lbl.setStyleSheet("font-size: 8px; color: #CBD5E1;")

            ttft_lbl = QLabel(pg.get("ttft", "--"))
            ttft_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            ttft_lbl.setStyleSheet("font-size: 8px; color: #94A3B8;")

            lat_lbl = QLabel(pg.get("latency", "--"))
            lat_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            lat_lbl.setStyleSheet("font-size: 8px; color: #94A3B8;")

            # Sparkline bars matching screenshot: 16 bars for top 3, 6 bars for bottom 2
            bar_cnt = 6 if ("terra" in pg["name"] or "混池" in pg["name"]) else 16
            bar_widget = SuccessRateBarWidget(count=bar_cnt, success_rate=pg.get("success_rate", 100.0))

            self.sq_bench_grid.addWidget(name_lbl, row_idx, 0)
            self.sq_bench_grid.addWidget(mult_lbl, row_idx, 1)
            self.sq_bench_grid.addWidget(tps_lbl, row_idx, 2)
            self.sq_bench_grid.addWidget(ttft_lbl, row_idx, 3)
            self.sq_bench_grid.addWidget(lat_lbl, row_idx, 4)
            self.sq_bench_grid.addWidget(bar_widget, row_idx, 5, Qt.AlignRight | Qt.AlignVCenter)

        self.sq_models_container.adjustSize()
        self.sq_bench_container.adjustSize()
        self.stack.adjustSize()
        self.card.adjustSize()

    def update_aihub_data(self, data: Dict[str, Any]):
        """Render AIHub account balance, top 3 groups, and directly embedded pelican image."""
        self._aihub_data = data
        if not data.get("success"):
            self.aihub_status_lbl.setText("⚠️ 获取失败")
            return

        bal = data.get("balance")
        if bal is not None:
            self.aihub_balance_lbl.setText(f"余额: ¥{bal:.2f}")
        else:
            self.aihub_balance_lbl.setText("余额: 未知")

        self.aihub_status_lbl.setText(f"{data.get('updated_at', '--')}")

        # Clear old rows in grid
        while self.aihub_groups_grid.count():
            item = self.aihub_groups_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Header for top 3 groups
        h_titles = ["低价分组 (≤0.2x)", "倍率", "缓存率", "TTFT"]
        h_aligns = [Qt.AlignLeft, Qt.AlignCenter, Qt.AlignRight, Qt.AlignRight]
        for col_idx, (title, align) in enumerate(zip(h_titles, h_aligns)):
            h_lbl = QLabel(title)
            h_lbl.setAlignment(align | Qt.AlignVCenter)
            h_lbl.setStyleSheet("font-size: 8px; font-weight: 700; color: #64748B;")
            self.aihub_groups_grid.addWidget(h_lbl, 0, col_idx)

        # Display strictly top 3 groups as requested
        top_groups = data.get("top_groups", [])
        for row_idx, g in enumerate(top_groups[:3], start=1):
            c_name = QLabel(f"{row_idx}. {g['code']}")
            c_name.setStyleSheet("font-size: 9px; font-weight: 600; color: #CBD5E1;")

            c_mult = QLabel(g.get("multiplier_str", "--"))
            c_mult.setAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            c_mult.setStyleSheet("font-size: 9px; font-weight: 700; color: #34D399;")

            c_hit = QLabel(g.get("cache_hit_rate", "-"))
            c_hit.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            c_hit.setStyleSheet("font-size: 8px; color: #94A3B8;")

            c_ttft = QLabel(g.get("ttft_str", "--"))
            c_ttft.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            c_ttft.setStyleSheet("font-size: 8px; color: #64748B;")

            self.aihub_groups_grid.addWidget(c_name, row_idx, 0)
            self.aihub_groups_grid.addWidget(c_mult, row_idx, 1)
            self.aihub_groups_grid.addWidget(c_hit, row_idx, 2)
            self.aihub_groups_grid.addWidget(c_ttft, row_idx, 3)

        # Directly render the Pelican test image preview
        primary_pelican = data.get("primary_pelican")
        pelicans = data.get("pelican_images", [])
        target_item = primary_pelican or (pelicans[0] if pelicans else None)

        if target_item:
            op_code = target_item.get("operator_code") or target_item.get("model_code", "AIHub")
            self.pelican_hdr_lbl.setText(f"📷 {op_code} 鹈鹕实测 (点击查看同运营商5张历史 ↗)")

            local_path = target_item.get("local_path", "")
            if local_path and os.path.exists(local_path):
                pixmap = QPixmap(local_path)
                if not pixmap.isNull():
                    scaled = pixmap.scaled(
                        QSize(250, 68),
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation
                    )
                    self.pelican_img_lbl.setPixmap(scaled)
                else:
                    self.pelican_img_lbl.setText("⚠️ 图片解析失败")
            else:
                self.pelican_img_lbl.setText("⏳ 正在下载实测图片...")
        else:
            self.pelican_hdr_lbl.setText("📷 鹈鹕实测图 (点击查看 ↗)")
            self.pelican_img_lbl.setText("暂无鹈鹕实测图")

        self.aihub_groups_widget.adjustSize()
        self.stack.adjustSize()
        self.card.adjustSize()
