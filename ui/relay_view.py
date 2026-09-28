"""
Relay Station View Widget.
Renders real-time monitored tables for Square API and AIHub.
Supports interactive group/model filtering and per-provider Pelican test image thumbnails.
"""

from typing import Dict, Any, List, Optional
import os

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QStackedWidget, QScrollArea, QGridLayout, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal, QSize
from PyQt5.QtGui import QPixmap, QColor, QFont, QCursor


SCROLL_STYLE = """
    QScrollArea {
        background: transparent;
        border: none;
    }
    QScrollArea > QWidget > QWidget {
        background: transparent;
    }
    QScrollBar:vertical {
        border: none;
        background: rgba(255, 255, 255, 0.03);
        width: 4px;
        margin: 0px;
        border-radius: 2px;
    }
    QScrollBar::handle:vertical {
        background: rgba(255, 255, 255, 0.18);
        border-radius: 2px;
        min-height: 20px;
    }
    QScrollBar::handle:vertical:hover {
        background: rgba(59, 130, 246, 0.5);
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }
"""


class ClickableThumbnail(QLabel):
    """Mini clickable thumbnail image representing a provider's detection artifact."""
    clicked = pyqtSignal(list, str)  # (operator_images, operator_code)

    def __init__(self, provider_item: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.provider_item = provider_item
        self.setFixedSize(38, 18)
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("点击查看该运营商的历史检测图")
        self.setStyleSheet("""
            QLabel {
                background: rgba(16, 185, 129, 0.08);
                border: 1px solid rgba(16, 185, 129, 0.28);
                border-radius: 3px;
                color: #64748B;
                font-size: 8px;
            }
            QLabel:hover {
                background: rgba(16, 185, 129, 0.22);
                border-color: rgba(16, 185, 129, 0.6);
            }
        """)

        local_path = provider_item.get("local_image_path", "")
        if local_path and os.path.exists(local_path):
            pix = QPixmap(local_path)
            if not pix.isNull():
                scaled = pix.scaled(QSize(36, 16), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.setPixmap(scaled)
            else:
                self.setText("📷")
        else:
            self.setText("无图")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            images = self.provider_item.get("operator_images", [])
            code = self.provider_item.get("code", "AIHub")
            self.clicked.emit(images, code)
            event.accept()
        else:
            super().mousePressEvent(event)


class RelayStationView(QWidget):
    """Component for displaying Square API & AIHub live stats in expanded mode."""

    pelican_clicked = pyqtSignal(list, str)  # (operator_images, operator_code)
    filter_dialog_requested = pyqtSignal()
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

        # Main Card container
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

        # Divider
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

        # Sub-header with Filter Button
        sub_hdr = QHBoxLayout()
        self.sq_status_lbl = QLabel("🟢 Square API (实时监控)")
        self.sq_status_lbl.setStyleSheet("font-size: 10px; font-weight: 600; color: #10B981;")

        self.btn_sq_filter = QPushButton("⚙️ 勾选监控")
        self.btn_sq_filter.setCursor(Qt.PointingHandCursor)
        self.btn_sq_filter.setToolTip("手动勾选想要监控的分组与模型")
        self.btn_sq_filter.setStyleSheet("""
            QPushButton {
                background: rgba(59, 130, 246, 0.15);
                border: 1px solid rgba(59, 130, 246, 0.35);
                border-radius: 3px;
                color: #60A5FA;
                font-size: 8px;
                font-weight: 600;
                padding: 1px 5px;
            }
            QPushButton:hover {
                background: rgba(59, 130, 246, 0.28);
                color: #93C5FD;
            }
        """)
        self.btn_sq_filter.clicked.connect(self.filter_dialog_requested.emit)

        sub_hdr.addWidget(self.sq_status_lbl)
        sub_hdr.addStretch()
        sub_hdr.addWidget(self.btn_sq_filter)
        p_layout.addLayout(sub_hdr)

        # Scroll Area for Square Monitored Rows
        self.sq_scroll = QScrollArea()
        self.sq_scroll.setWidgetResizable(True)
        self.sq_scroll.setFixedHeight(235)
        self.sq_scroll.setStyleSheet(SCROLL_STYLE)
        self.sq_scroll.viewport().setStyleSheet("background: transparent; border: none;")
        self.sq_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.sq_scroll_content = QWidget()
        self.sq_scroll_content.setStyleSheet("background: transparent;")
        self.sq_grid = QGridLayout(self.sq_scroll_content)
        self.sq_grid.setContentsMargins(1, 1, 1, 1)
        self.sq_grid.setHorizontalSpacing(4)
        self.sq_grid.setVerticalSpacing(3)
        self.sq_scroll.setWidget(self.sq_scroll_content)
        p_layout.addWidget(self.sq_scroll)

    def init_aihub_panel(self):
        p_layout = QVBoxLayout(self.aihub_panel)
        p_layout.setContentsMargins(0, 1, 0, 1)
        p_layout.setSpacing(4)

        # Sub-header (NO balance display per user request)
        sub_hdr = QHBoxLayout()
        self.aihub_title_lbl = QLabel("AIHub 供应商实测 (前 10 低价分组)")
        self.aihub_title_lbl.setStyleSheet("font-size: 10px; font-weight: 700; color: #10B981;")

        self.aihub_status_lbl = QLabel("实时更新")
        self.aihub_status_lbl.setStyleSheet("font-size: 8px; color: #94A3B8;")

        sub_hdr.addWidget(self.aihub_title_lbl)
        sub_hdr.addStretch()
        sub_hdr.addWidget(self.aihub_status_lbl)
        p_layout.addLayout(sub_hdr)

        # Scroll Area for 10 Providers Table
        self.aihub_scroll = QScrollArea()
        self.aihub_scroll.setWidgetResizable(True)
        self.aihub_scroll.setFixedHeight(235)
        self.aihub_scroll.setStyleSheet(SCROLL_STYLE)
        self.aihub_scroll.viewport().setStyleSheet("background: transparent; border: none;")
        self.aihub_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.aihub_scroll_content = QWidget()
        self.aihub_scroll_content.setStyleSheet("background: transparent;")
        self.aihub_grid = QGridLayout(self.aihub_scroll_content)
        self.aihub_grid.setContentsMargins(1, 1, 1, 1)
        self.aihub_grid.setHorizontalSpacing(4)
        self.aihub_grid.setVerticalSpacing(3)
        self.aihub_scroll.setWidget(self.aihub_scroll_content)
        p_layout.addWidget(self.aihub_scroll)

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
        """Render Square API real-time monitored groups, models, and descriptions."""
        self._square_data = data
        if not data.get("success"):
            self.sq_status_lbl.setText(f"⚠️ {data.get('error', '获取失败')}")
            return

        balance_info = data.get("balance", {})
        used = balance_info.get("total_usage")
        if used is not None:
            self.sq_status_lbl.setText(f"🟢 Square (已用: ${used:.2f})")
        else:
            self.sq_status_lbl.setText("🟢 Square (实时监控)")

        # Clear grid
        while self.sq_grid.count():
            item = self.sq_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Header Titles
        h_titles = ["关注分组", "倍率", "对应勾选模型", "实时说明/特性"]
        h_aligns = [Qt.AlignLeft, Qt.AlignCenter, Qt.AlignLeft, Qt.AlignLeft]
        for col_idx, (title, align) in enumerate(zip(h_titles, h_aligns)):
            h_lbl = QLabel(title)
            h_lbl.setAlignment(align | Qt.AlignVCenter)
            h_lbl.setStyleSheet("font-size: 8px; font-weight: 700; color: #64748B;")
            self.sq_grid.addWidget(h_lbl, 0, col_idx)

        colors = ["#10B981", "#38BDF8", "#F59E0B", "#A78BFA", "#EAB308", "#EC4899", "#34D399", "#60A5FA"]

        monitored_rows = data.get("monitored_rows", [])
        if not monitored_rows:
            empty_lbl = QLabel("暂无勾选的分组，请点击右上角 [⚙️ 勾选监控] 选择")
            empty_lbl.setStyleSheet("font-size: 9px; color: #94A3B8; padding: 10px;")
            self.sq_grid.addWidget(empty_lbl, 1, 0, 1, 4, Qt.AlignCenter)
        else:
            for row_idx, r in enumerate(monitored_rows, start=1):
                color = colors[(row_idx - 1) % len(colors)]
                raw_g = r["group_name"]
                if "鹈鹕" in raw_g:
                    short_g = "已过鹈鹕"
                elif "特惠" in raw_g:
                    short_g = "特惠分组"
                elif "4.1" in raw_g and "专门" in raw_g:
                    short_g = "4.1专门"
                elif "ultra" in raw_g:
                    short_g = "ultra"
                elif "aws" in raw_g:
                    short_g = "aws-cc"
                elif "官方" in raw_g:
                    short_g = "官方max"
                elif "pro" in raw_g:
                    short_g = "pro专享"
                elif "terra" in raw_g:
                    short_g = "terra"
                elif "混池" in raw_g:
                    short_g = "混池优惠"
                else:
                    short_g = raw_g.replace("gpt-", "").replace("claude-", "")[:6]

                g_lbl = QLabel(short_g)
                g_lbl.setToolTip(raw_g)
                g_lbl.setStyleSheet(f"font-size: 9px; font-weight: 700; color: {color};")

                mult_lbl = QLabel(r["ratio_str"])
                mult_lbl.setAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                mult_lbl.setStyleSheet("font-size: 8px; font-weight: 600; color: #60A5FA;")

                models_lbl = QLabel(r["models_str"])
                models_lbl.setToolTip(r["models_str"])
                models_lbl.setStyleSheet("font-size: 8px; color: #CBD5E1;")

                desc_lbl = QLabel(r.get("desc", ""))
                desc_lbl.setToolTip(r.get("desc", ""))
                desc_lbl.setStyleSheet("font-size: 8px; color: #94A3B8;")

                self.sq_grid.addWidget(g_lbl, row_idx, 0)
                self.sq_grid.addWidget(mult_lbl, row_idx, 1)
                self.sq_grid.addWidget(models_lbl, row_idx, 2)
                self.sq_grid.addWidget(desc_lbl, row_idx, 3)

        self.sq_scroll_content.adjustSize()
        self.stack.adjustSize()
        self.card.adjustSize()

    def update_aihub_data(self, data: Dict[str, Any]):
        """Render AIHub top 10 providers with thumbnails on the right (一一对应)."""
        self._aihub_data = data
        if not data.get("success"):
            self.aihub_status_lbl.setText("⚠️ 获取失败")
            return

        self.aihub_status_lbl.setText(f"{data.get('updated_at', '刚刚')}")

        # Clear grid
        while self.aihub_grid.count():
            item = self.aihub_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Header: 供应商, 倍率, 缓存率, TTFT, 实测图
        h_titles = ["供应商 (≤0.2x)", "倍率", "缓存率", "TTFT", "实测图"]
        h_aligns = [Qt.AlignLeft, Qt.AlignCenter, Qt.AlignRight, Qt.AlignRight, Qt.AlignCenter]
        for col_idx, (title, align) in enumerate(zip(h_titles, h_aligns)):
            h_lbl = QLabel(title)
            h_lbl.setAlignment(align | Qt.AlignVCenter)
            h_lbl.setStyleSheet("font-size: 8px; font-weight: 700; color: #64748B;")
            self.aihub_grid.addWidget(h_lbl, 0, col_idx)

        top_groups = data.get("top_groups", [])
        for row_idx, g in enumerate(top_groups[:10], start=1):
            c_name = QLabel(f"{row_idx}. {g['code']}")
            c_name.setToolTip(g["code"])
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

            # Right column: individual clickable thumbnail
            thumb = ClickableThumbnail(g, self.aihub_scroll_content)
            thumb.clicked.connect(self.pelican_clicked.emit)

            self.aihub_grid.addWidget(c_name, row_idx, 0)
            self.aihub_grid.addWidget(c_mult, row_idx, 1)
            self.aihub_grid.addWidget(c_hit, row_idx, 2)
            self.aihub_grid.addWidget(c_ttft, row_idx, 3)
            self.aihub_grid.addWidget(thumb, row_idx, 4, Qt.AlignCenter | Qt.AlignVCenter)

        self.aihub_scroll_content.adjustSize()
        self.stack.adjustSize()
        self.card.adjustSize()
