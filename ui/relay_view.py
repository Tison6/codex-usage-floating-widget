"""
Relay Station View Widget.
Renders tabbed/accordion cards for Square API and AIHub monitoring in the expanded widget.
"""

from typing import Dict, Any, List, Optional
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QStackedWidget
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QCursor


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
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(6)

        # 1. Header with Tab Toggle
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel("🌐 中转站状态")
        self.title_lbl.setStyleSheet("font-size: 11px; font-weight: 700; color: #94A3B8;")

        # Tab Buttons
        tab_container = QHBoxLayout()
        tab_container.setSpacing(4)

        self.btn_square = QPushButton("Square API")
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
                padding: 1px 8px;
                font-size: 10px;
                font-weight: 600;
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
        layout.addLayout(header)

        # 2. Stacked Content (Square API vs AIHub)
        self.stack = QStackedWidget(self)
        
        # Panel 0: Square API
        self.square_panel = QWidget()
        self.init_square_panel()
        self.stack.addWidget(self.square_panel)

        # Panel 1: AIHub
        self.aihub_panel = QWidget()
        self.init_aihub_panel()
        self.stack.addWidget(self.aihub_panel)

        layout.addWidget(self.stack)

    def init_square_panel(self):
        p_layout = QVBoxLayout(self.square_panel)
        p_layout.setContentsMargins(4, 4, 4, 4)
        p_layout.setSpacing(5)

        # Sub-header: Square balance / usage
        self.sq_status_lbl = QLabel("正在获取 Square API 数据...")
        self.sq_status_lbl.setStyleSheet("font-size: 10px; color: #64748B;")
        p_layout.addWidget(self.sq_status_lbl)

        # Container for model rows
        self.sq_models_container = QVBoxLayout()
        self.sq_models_container.setSpacing(4)
        p_layout.addLayout(self.sq_models_container)

    def init_aihub_panel(self):
        p_layout = QVBoxLayout(self.aihub_panel)
        p_layout.setContentsMargins(4, 4, 4, 4)
        p_layout.setSpacing(5)

        # Sub-header: AIHub user balance & status
        self.aihub_header_layout = QHBoxLayout()
        self.aihub_balance_lbl = QLabel("余额: --")
        self.aihub_balance_lbl.setStyleSheet("font-size: 11px; font-weight: 700; color: #10B981;")
        
        self.aihub_status_lbl = QLabel("已连接")
        self.aihub_status_lbl.setStyleSheet("font-size: 10px; color: #94A3B8;")

        self.aihub_header_layout.addWidget(self.aihub_balance_lbl)
        self.aihub_header_layout.addStretch()
        self.aihub_header_layout.addWidget(self.aihub_status_lbl)
        p_layout.addLayout(self.aihub_header_layout)

        # Groups Table Header
        tbl_hdr = QHBoxLayout()
        tbl_hdr.setContentsMargins(2, 0, 2, 0)
        c1 = QLabel("低价分组 (≤0.2x)")
        c1.setStyleSheet("font-size: 9px; color: #64748B; font-weight: 700;")
        c2 = QLabel("倍率")
        c2.setStyleSheet("font-size: 9px; color: #64748B; font-weight: 700;")
        c3 = QLabel("缓存率")
        c3.setStyleSheet("font-size: 9px; color: #64748B; font-weight: 700;")
        c4 = QLabel("TTFT")
        c4.setStyleSheet("font-size: 9px; color: #64748B; font-weight: 700;")
        
        tbl_hdr.addWidget(c1, 4)
        tbl_hdr.addWidget(c2, 2)
        tbl_hdr.addWidget(c3, 2)
        tbl_hdr.addWidget(c4, 2)
        p_layout.addLayout(tbl_hdr)

        # Container for top 3 group rows
        self.aihub_groups_container = QVBoxLayout()
        self.aihub_groups_container.setSpacing(3)
        p_layout.addLayout(self.aihub_groups_container)

        # Pelican Verification Action Row
        self.btn_pelican = QPushButton("🦤 鹈鹕检测实测图 [查看最新 5 张 ↗]")
        self.btn_pelican.setCursor(Qt.PointingHandCursor)
        self.btn_pelican.setFixedHeight(22)
        self.btn_pelican.setStyleSheet("""
            QPushButton {
                background: rgba(16, 185, 129, 0.12);
                border: 1px solid rgba(16, 185, 129, 0.3);
                border-radius: 4px;
                color: #34D399;
                font-size: 10px;
                font-weight: 600;
                padding: 1px 6px;
            }
            QPushButton:hover {
                background: rgba(16, 185, 129, 0.22);
                border-color: #10B981;
                color: #6EE7B7;
            }
        """)
        self.btn_pelican.clicked.connect(self.pelican_clicked.emit)
        p_layout.addWidget(self.btn_pelican)

    def switch_tab(self, index: int):
        self.current_tab = index
        self.stack.setCurrentIndex(index)
        self.btn_square.setChecked(index == 0)
        self.btn_aihub.setChecked(index == 1)

    def update_square_data(self, data: Dict[str, Any]):
        """Render Square API models and prices."""
        self._square_data = data
        if not data.get("success"):
            self.sq_status_lbl.setText(f"⚠️ {data.get('error', '获取失败')}")
            return

        balance_info = data.get("balance", {})
        used = balance_info.get("total_usage")
        if used is not None:
            self.sq_status_lbl.setText(f"🟢 Square API 正常 (总用量: ${used:.2f})")
        else:
            self.sq_status_lbl.setText(f"🟢 Square API 正常 (公开价格)")

        # Clear old rows
        while self.sq_models_container.count():
            item = self.sq_models_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                # Clear sub-layout
                while item.layout().count():
                    sub = item.layout().takeAt(0)
                    if sub.widget():
                        sub.widget().deleteLater()

        models = data.get("models", [])
        for m in models:
            m_box = QFrame()
            m_box.setStyleSheet("""
                QFrame {
                    background: rgba(255, 255, 255, 0.03);
                    border: 1px solid rgba(255, 255, 255, 0.05);
                    border-radius: 4px;
                    padding: 2px 4px;
                }
            """)
            mb_layout = QVBoxLayout(m_box)
            mb_layout.setContentsMargins(4, 2, 4, 2)
            mb_layout.setSpacing(2)

            m_title = QLabel(f"• {m['display_name']} (基准 {m['base_ratio']}x)")
            m_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #E2E8F0;")
            mb_layout.addWidget(m_title)

            for g in m.get("groups", []):
                g_row = QHBoxLayout()
                g_row.setContentsMargins(6, 0, 0, 0)
                
                badge = " 🟢鹈鹕" if g.get("is_pelican_verified") else ""
                name_lbl = QLabel(f"{g['name']}{badge}:")
                name_lbl.setStyleSheet("font-size: 9px; color: #94A3B8;")
                
                mult_lbl = QLabel(f"{g['effective_multiplier']:.2f}x")
                mult_lbl.setStyleSheet("font-size: 9px; font-weight: 700; color: #38BDF8;")

                price_lbl = QLabel(f"入${g['input_price_1m']}/出${g['output_price_1m']}")
                price_lbl.setStyleSheet("font-size: 9px; color: #64748B;")

                g_row.addWidget(name_lbl)
                g_row.addWidget(mult_lbl)
                g_row.addStretch()
                g_row.addWidget(price_lbl)
                mb_layout.addLayout(g_row)

            self.sq_models_container.addWidget(m_box)

    def update_aihub_data(self, data: Dict[str, Any]):
        """Render AIHub account balance, top 3 groups, and pelican status."""
        self._aihub_data = data
        if not data.get("success"):
            self.aihub_status_lbl.setText("⚠️ 获取失败")
            return

        bal = data.get("balance")
        if bal is not None:
            self.aihub_balance_lbl.setText(f"余额: ¥{bal:.2f}")
        else:
            self.aihub_balance_lbl.setText("余额: 未知")
        
        self.aihub_status_lbl.setText(f"更新于 {data.get('updated_at', '--')}")

        # Clear old rows
        while self.aihub_groups_container.count():
            item = self.aihub_groups_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    sub = item.layout().takeAt(0)
                    if sub.widget():
                        sub.widget().deleteLater()

        top_groups = data.get("top_groups", [])
        for i, g in enumerate(top_groups[:3]):
            row_w = QFrame()
            row_w.setStyleSheet("""
                QFrame {
                    background: rgba(255, 255, 255, 0.02);
                    border-radius: 3px;
                }
            """)
            r_lay = QHBoxLayout(row_w)
            r_lay.setContentsMargins(4, 2, 4, 2)
            
            c_name = QLabel(f"{i+1}. {g['code']}")
            c_name.setStyleSheet("font-size: 9px; font-weight: 600; color: #CBD5E1;")

            c_mult = QLabel(g.get("multiplier_str", "--"))
            c_mult.setStyleSheet("font-size: 9px; font-weight: 700; color: #34D399;")

            c_hit = QLabel(g.get("cache_hit_rate", "-"))
            c_hit.setStyleSheet("font-size: 9px; color: #94A3B8;")

            c_ttft = QLabel(g.get("ttft_str", "--"))
            c_ttft.setStyleSheet("font-size: 9px; color: #64748B;")

            r_lay.addWidget(c_name, 4)
            r_lay.addWidget(c_mult, 2)
            r_lay.addWidget(c_hit, 2)
            r_lay.addWidget(c_ttft, 2)
            self.aihub_groups_container.addWidget(row_w)

        # Update button text with cached pelican count
        pelicans = data.get("pelican_images", [])
        if pelicans:
            latest_time = pelicans[0].get("published_at_str", "")
            self.btn_pelican.setText(f"🦤 鹈鹕检测实测图 [最新 {latest_time} ↗]")
        else:
            self.btn_pelican.setText("🦤 鹈鹕检测实测图 [查看最新 5 张 ↗]")
