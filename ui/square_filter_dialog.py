"""
Relay Stations Group & Provider Selection Dialogs.
Allows users to manually check and uncheck which Square groups/models and AIHub providers to monitor,
displaying live parameters (multiplier, cache rate, TTFT/latency, success rates) to make informed choices.
"""

from typing import List, Dict, Any, Set, Optional
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QWidget, QScrollArea, QCheckBox, QFrame,
    QGraphicsDropShadowEffect, QComboBox, QLineEdit
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QCursor

from core.square_client import DEFAULT_SELECTED_GROUPS, DEFAULT_SELECTED_MODELS, DEFAULT_GROUP_MODELS
from core.aihub_client import DEFAULT_SELECTED_PROVIDERS, is_ds_or_glm_provider
from PyQt5.QtCore import QRectF
from PyQt5.QtGui import QPainter

class DetectionDot(QWidget):
    """Compact circular status dot for AIHub model verification status."""
    def __init__(self, status: str = "other", tooltip: str = "", size: int = 8, parent=None):
        super().__init__(parent)
        self.status = status
        self._size = size
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        if tooltip:
            self.setToolTip(tooltip)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if self.status == "passed":
            color = QColor("#10B981")
            glow = QColor(16, 185, 129, 65)
        elif self.status == "suspected":
            color = QColor("#F59E0B")
            glow = QColor(245, 158, 11, 65)
        else:
            color = QColor("#64748B")
            glow = QColor(100, 116, 139, 45)

        painter.setPen(Qt.NoPen)
        painter.setBrush(glow)
        r = float(self._size) / 2.0
        painter.drawEllipse(0, 0, self._size, self._size)
        painter.setBrush(color)
        inner = max(2.0, r * 0.65)
        painter.drawEllipse(QRectF(r - inner / 2.0, r - inner / 2.0, inner, inner))

SCROLL_STYLE = """
    QScrollArea {
        background: transparent;
        border: none;
    }
    QScrollBar:vertical {
        border: none;
        background: rgba(255, 255, 255, 0.03);
        width: 5px;
        margin: 0px;
        border-radius: 2px;
    }
    QScrollBar::handle:vertical {
        background: rgba(255, 255, 255, 0.2);
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

CHECKBOX_STYLE = """
    QCheckBox {
        color: #E2E8F0;
        font-size: 11px;
        font-weight: 600;
        spacing: 6px;
    }
    QCheckBox::indicator {
        width: 14px;
        height: 14px;
        border: 1px solid rgba(255, 255, 255, 0.25);
        border-radius: 3px;
        background: rgba(255, 255, 255, 0.05);
    }
    QCheckBox::indicator:hover {
        border-color: #38BDF8;
        background: rgba(56, 189, 248, 0.1);
    }
    QCheckBox::indicator:checked {
        background: #10B981;
        border-color: #10B981;
    }
"""


class SquareFilterDialog(QDialog):
    """Modern dark-themed popup dialog for configuring Square monitored groups and models."""

    filters_changed = pyqtSignal()

    def __init__(self, square_client, parent=None):
        super().__init__(parent)
        self.square_client = square_client
        self.group_checkboxes: Dict[str, QCheckBox] = {}
        self.model_checkboxes: Dict[str, QCheckBox] = {}

        self.init_window()
        self.init_ui()

    def init_window(self):
        self.setWindowTitle("Square API 监控项筛选")
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.resize(560, 520)

    def init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)

        container = QWidget(self)
        container.setObjectName("FilterContainer")
        container.setStyleSheet("""
            QWidget#FilterContainer {
                background-color: rgba(20, 24, 33, 0.98);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 12px;
            }
        """)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 4)
        container.setGraphicsEffect(shadow)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        # 1. Header Bar
        header = QHBoxLayout()
        title_lbl = QLabel("⚙️ 勾选 Square 监控项 (实时生效)")
        title_lbl.setStyleSheet("font-size: 13px; font-weight: 700; color: #F1F5F9;")

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

        header.addWidget(title_lbl)
        header.addStretch()
        header.addWidget(btn_close)
        layout.addLayout(header)

        # 2. Tabs: Groups vs Models
        tabs = QTabWidget()
        tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px;
                background: rgba(15, 18, 26, 0.6);
            }
            QTabBar::tab {
                background: rgba(255, 255, 255, 0.05);
                color: #94A3B8;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                padding: 5px 12px;
                font-size: 11px;
                font-weight: 600;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background: rgba(59, 130, 246, 0.25);
                border: 1px solid rgba(59, 130, 246, 0.4);
                border-bottom: none;
                color: #60A5FA;
            }
        """)

        # Tab 1: Groups Tab
        tab_groups = QWidget()
        self.init_groups_tab(tab_groups)
        tabs.addTab(tab_groups, "1. 勾选关注分组 (含实时参数)")

        # Tab 2: Models Tab
        tab_models = QWidget()
        self.init_models_tab(tab_models)
        tabs.addTab(tab_models, "2. 勾选关注模型")

        layout.addWidget(tabs, 1)

        # 3. Footer Bar with Quick Actions and Save
        footer = QHBoxLayout()
        btn_preset = QPushButton("推荐预设")
        btn_preset.setCursor(Qt.PointingHandCursor)
        btn_preset.setStyleSheet("""
            QPushButton {
                background: rgba(59, 130, 246, 0.15);
                color: #60A5FA;
                border: 1px solid rgba(59, 130, 246, 0.3);
                border-radius: 5px;
                padding: 4px 10px;
                font-size: 11px;
            }
            QPushButton:hover {
                background: rgba(59, 130, 246, 0.25);
            }
        """)
        btn_preset.clicked.connect(self.apply_recommended_preset)

        btn_save = QPushButton("保存并应用")
        btn_save.setCursor(Qt.PointingHandCursor)
        btn_save.setStyleSheet("""
            QPushButton {
                background: #10B981;
                color: #FFFFFF;
                border: none;
                border-radius: 5px;
                padding: 4px 16px;
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: #059669;
            }
        """)
        btn_save.clicked.connect(self.save_and_apply)

        footer.addWidget(btn_preset)
        footer.addStretch()
        footer.addWidget(btn_save)
        layout.addLayout(footer)

        root.addWidget(container)

    def init_groups_tab(self, parent_widget: QWidget):
        layout = QVBoxLayout(parent_widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Actions row
        act_row = QHBoxLayout()
        tip_lbl = QLabel("提示: 勾选分组将在主界面展示其速度、延迟与成功率")
        tip_lbl.setStyleSheet("font-size: 10px; color: #94A3B8;")
        act_row.addWidget(tip_lbl)
        act_row.addStretch()

        btn_all = QPushButton("全选")
        btn_all.setFixedHeight(20)
        btn_all.setCursor(Qt.PointingHandCursor)
        btn_all.setStyleSheet("font-size: 10px; color: #60A5FA; background: transparent; border: none;")
        btn_all.clicked.connect(lambda: self.toggle_all_groups(True))

        btn_none = QPushButton("清空")
        btn_none.setFixedHeight(20)
        btn_none.setCursor(Qt.PointingHandCursor)
        btn_none.setStyleSheet("font-size: 10px; color: #64748B; background: transparent; border: none;")
        btn_none.clicked.connect(lambda: self.toggle_all_groups(False))

        act_row.addWidget(btn_all)
        act_row.addWidget(btn_none)
        layout.addLayout(act_row)

        # Table Column Header
        h_row = QHBoxLayout()
        h_row.setContentsMargins(8, 2, 8, 2)
        h_g = QLabel("分组名称")
        h_g.setStyleSheet("font-size: 9px; font-weight: 700; color: #64748B;")
        h_row.addWidget(h_g)
        h_row.addStretch()

        for title, w in [("倍率", 44), ("速度", 50), ("延迟", 48), ("成功率", 52)]:
            lbl = QLabel(title)
            lbl.setFixedWidth(w)
            lbl.setAlignment(Qt.AlignCenter if title in ["倍率", "成功率"] else Qt.AlignRight)
            lbl.setStyleSheet("font-size: 9px; font-weight: 700; color: #64748B;")
            h_row.addWidget(lbl)
        layout.addLayout(h_row)

        # Scroll Area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(SCROLL_STYLE)
        scroll.viewport().setStyleSheet("background: transparent; border: none;")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        c_layout = QVBoxLayout(content)
        c_layout.setContentsMargins(2, 2, 2, 2)
        c_layout.setSpacing(4)

        all_groups = (self.square_client.cached_data or {}).get("all_groups", [])
        cur_selected = set(self.square_client.get_selected_groups())

        if not all_groups:
            all_groups = [{"name": g, "ratio_str": "--", "desc": ""} for g in DEFAULT_SELECTED_GROUPS]

        for g in all_groups:
            g_name = g["name"]
            row = QFrame()
            row.setStyleSheet("""
                QFrame {
                    background: rgba(255, 255, 255, 0.03);
                    border: 1px solid rgba(255, 255, 255, 0.05);
                    border-radius: 4px;
                }
                QFrame:hover {
                    background: rgba(255, 255, 255, 0.06);
                }
            """)
            r_lay = QHBoxLayout(row)
            r_lay.setContentsMargins(6, 4, 6, 4)
            r_lay.setSpacing(6)

            cb = QCheckBox(g_name)
            cb.setChecked(g_name in cur_selected)
            cb.setStyleSheet(CHECKBOX_STYLE)
            self.group_checkboxes[g_name] = cb
            r_lay.addWidget(cb)
            r_lay.addStretch()

            # Multiplier badge
            ratio_lbl = QLabel(g.get("ratio_str", "--"))
            ratio_lbl.setFixedWidth(44)
            ratio_lbl.setAlignment(Qt.AlignCenter)
            ratio_lbl.setStyleSheet("""
                background: rgba(59, 130, 246, 0.2);
                color: #60A5FA;
                border-radius: 3px;
                padding: 1px 3px;
                font-size: 9px;
                font-weight: 700;
            """)
            r_lay.addWidget(ratio_lbl)

            # Speed
            tps_lbl = QLabel(g.get("tps", "--"))
            tps_lbl.setFixedWidth(50)
            tps_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            tps_lbl.setStyleSheet("font-size: 9px; color: #CBD5E1;")
            r_lay.addWidget(tps_lbl)

            # Latency
            lat_lbl = QLabel(g.get("latency", "--"))
            lat_lbl.setFixedWidth(48)
            lat_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            lat_lbl.setStyleSheet("font-size: 9px; color: #94A3B8;")
            r_lay.addWidget(lat_lbl)

            # Success rate
            sr_val = g.get("success_rate", 100.0)
            sr_lbl = QLabel(f"{sr_val:.1f}%")
            sr_lbl.setFixedWidth(52)
            sr_lbl.setAlignment(Qt.AlignCenter)
            sr_lbl.setStyleSheet("font-size: 9px; font-weight: 700; color: #10B981;")
            r_lay.addWidget(sr_lbl)

            c_layout.addWidget(row)

        c_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)

    def init_models_tab(self, parent_widget: QWidget):
        layout = QVBoxLayout(parent_widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Actions row
        act_row = QHBoxLayout()
        tip_lbl = QLabel("提示: 勾选的模型将自动映射并在所属分组下列出")
        tip_lbl.setStyleSheet("font-size: 10px; color: #94A3B8;")
        act_row.addWidget(tip_lbl)
        act_row.addStretch()

        btn_all = QPushButton("全选")
        btn_all.setFixedHeight(20)
        btn_all.setCursor(Qt.PointingHandCursor)
        btn_all.setStyleSheet("font-size: 10px; color: #60A5FA; background: transparent; border: none;")
        btn_all.clicked.connect(lambda: self.toggle_all_models(True))

        btn_none = QPushButton("清空")
        btn_none.setFixedHeight(20)
        btn_none.setCursor(Qt.PointingHandCursor)
        btn_none.setStyleSheet("font-size: 10px; color: #64748B; background: transparent; border: none;")
        btn_none.clicked.connect(lambda: self.toggle_all_models(False))

        act_row.addWidget(btn_all)
        act_row.addWidget(btn_none)
        layout.addLayout(act_row)

        # Scroll Area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(SCROLL_STYLE)
        scroll.viewport().setStyleSheet("background: transparent; border: none;")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        c_layout = QVBoxLayout(content)
        c_layout.setContentsMargins(2, 2, 2, 2)
        c_layout.setSpacing(4)

        all_models = (self.square_client.cached_data or {}).get("all_models", [])
        cur_selected = set(self.square_client.get_selected_models())

        if not all_models:
            all_models = [{"name": m, "display_name": m, "enable_groups": []} for m in DEFAULT_SELECTED_MODELS]

        for m in all_models:
            m_name = m["name"]
            d_name = m.get("display_name", m_name)
            row = QFrame()
            row.setStyleSheet("""
                QFrame {
                    background: rgba(255, 255, 255, 0.03);
                    border: 1px solid rgba(255, 255, 255, 0.05);
                    border-radius: 4px;
                }
                QFrame:hover {
                    background: rgba(255, 255, 255, 0.06);
                }
            """)
            r_lay = QHBoxLayout(row)
            r_lay.setContentsMargins(6, 4, 6, 4)

            cb = QCheckBox(f"{d_name} ({m_name})")
            cb.setChecked(m_name in cur_selected)
            cb.setStyleSheet(CHECKBOX_STYLE)
            self.model_checkboxes[m_name] = cb
            r_lay.addWidget(cb)
            r_lay.addStretch()

            eg_count = len(m.get("enable_groups", []))
            cnt_lbl = QLabel(f"支持 {eg_count} 个分组")
            cnt_lbl.setStyleSheet("font-size: 10px; color: #64748B;")
            r_lay.addWidget(cnt_lbl)

            c_layout.addWidget(row)

        c_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)

    def toggle_all_groups(self, checked: bool):
        for cb in self.group_checkboxes.values():
            cb.setChecked(checked)

    def toggle_all_models(self, checked: bool):
        for cb in self.model_checkboxes.values():
            cb.setChecked(checked)

    def apply_recommended_preset(self):
        for name, cb in self.group_checkboxes.items():
            cb.setChecked(name in DEFAULT_SELECTED_GROUPS)
        for name, cb in self.model_checkboxes.items():
            cb.setChecked(name in DEFAULT_SELECTED_MODELS)

    def save_and_apply(self):
        selected_groups = [name for name, cb in self.group_checkboxes.items() if cb.isChecked()]
        selected_models = [name for name, cb in self.model_checkboxes.items() if cb.isChecked()]

        self.square_client.set_selected_groups(selected_groups)
        self.square_client.set_selected_models(selected_models)

        # Force re-computation of monitored rows
        self.square_client.fetch_data(force=True)
        self.filters_changed.emit()
        self.close()

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


class AIHubFilterDialog(QDialog):
    """Modern dark-themed popup dialog for configuring AIHub monitored providers with live stats."""

    filters_changed = pyqtSignal()

    def __init__(self, aihub_client, parent=None):
        super().__init__(parent)
        self.aihub_client = aihub_client
        self.provider_checkboxes: Dict[str, QCheckBox] = {}
        self.provider_exclude_checkboxes: Dict[str, QCheckBox] = {}
        self.provider_data_map: Dict[str, Dict[str, Any]] = {}
        self.excluded_providers = set(self.aihub_client.get_excluded_providers() or [])

        if not self.aihub_client.cached_data:
            try:
                self.aihub_client.fetch_data()
            except Exception:
                pass

        self.init_window()
        self.init_ui()

    def init_window(self):
        self.setWindowTitle("AIHub 供应商监控项筛选")
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.resize(650, 530)

    def init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)

        container = QWidget(self)
        container.setObjectName("FilterContainer")
        container.setStyleSheet("""
            QWidget#FilterContainer {
                background-color: rgba(20, 24, 33, 0.98);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 12px;
            }
        """)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 4)
        container.setGraphicsEffect(shadow)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        # 1. Header Bar
        header = QHBoxLayout()
        title_lbl = QLabel("⚙️ 勾选 AIHub 监控供应商 (实时参数筛选)")
        title_lbl.setStyleSheet("font-size: 13px; font-weight: 700; color: #F1F5F9;")

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

        header.addWidget(title_lbl)
        header.addStretch()
        header.addWidget(btn_close)
        layout.addLayout(header)

        # 1. Mode Selection Row: [🤖 自动模式 (按阈值动态筛选)] vs [✋ 手动模式 (按勾选项)]
        mode_frame = QFrame()
        mode_frame.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 6px;
            }
        """)
        mode_lay = QHBoxLayout(mode_frame)
        mode_lay.setContentsMargins(8, 4, 8, 4)
        mode_lay.setSpacing(8)

        lbl_mode_title = QLabel("监控模式:")
        lbl_mode_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #E2E8F0;")
        mode_lay.addWidget(lbl_mode_title)

        mode_btn_style = """
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
                background: rgba(16, 185, 129, 0.2);
                border-color: #10B981;
                color: #34D399;
                font-weight: 700;
            }
        """

        self.btn_dlg_auto = QPushButton("🤖 自动模式 (按默认阈值每分钟动态更新)")
        self.btn_dlg_auto.setCheckable(True)
        self.btn_dlg_auto.setCursor(Qt.PointingHandCursor)
        self.btn_dlg_auto.setStyleSheet(mode_btn_style)

        self.btn_dlg_manual = QPushButton("✋ 手动模式 (按勾选的供应商)")
        self.btn_dlg_manual.setCheckable(True)
        self.btn_dlg_manual.setCursor(Qt.PointingHandCursor)
        self.btn_dlg_manual.setStyleSheet(mode_btn_style)

        cur_auto = self.aihub_client.get_auto_mode()
        self.btn_dlg_auto.setChecked(cur_auto)
        self.btn_dlg_manual.setChecked(not cur_auto)

        self.btn_dlg_auto.clicked.connect(self._on_dlg_auto_clicked)
        self.btn_dlg_manual.clicked.connect(self._on_dlg_manual_clicked)

        mode_lay.addWidget(self.btn_dlg_auto)
        mode_lay.addWidget(self.btn_dlg_manual)
        mode_lay.addStretch()
        layout.addWidget(mode_frame)

        # Subtitle & Action bar
        act_row = QHBoxLayout()
        tip_lbl = QLabel("查看各供应商实时倍率、缓存率与成功率，低成功率(<50%)已高亮标红")
        tip_lbl.setStyleSheet("font-size: 10px; color: #94A3B8;")
        act_row.addWidget(tip_lbl)
        act_row.addStretch()

        btn_good = QPushButton("⭐ 推荐预设")
        btn_good.setFixedHeight(20)
        btn_good.setCursor(Qt.PointingHandCursor)
        btn_good.setStyleSheet("font-size: 10px; color: #34D399; background: transparent; border: none; font-weight: 600;")
        btn_good.setToolTip("自动勾选推荐监控的优质供应商")
        btn_good.clicked.connect(self.apply_good_preset)

        btn_all = QPushButton("全选")
        btn_all.setFixedHeight(20)
        btn_all.setCursor(Qt.PointingHandCursor)
        btn_all.setStyleSheet("font-size: 10px; color: #60A5FA; background: transparent; border: none;")
        btn_all.clicked.connect(lambda: self.toggle_all(True))

        btn_none = QPushButton("清空")
        btn_none.setFixedHeight(20)
        btn_none.setCursor(Qt.PointingHandCursor)
        btn_none.setStyleSheet("font-size: 10px; color: #64748B; background: transparent; border: none;")
        btn_none.clicked.connect(lambda: self.toggle_all(False))

        act_row.addWidget(btn_good)
        act_row.addWidget(btn_all)
        act_row.addWidget(btn_none)
        layout.addLayout(act_row)

        # 2. Numeric Composite Filter Bar (Filtering by success rate, cache rate, effective & nominal multiplier)
        f_frame = QFrame()
        f_frame.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px;
            }
            QLabel {
                font-size: 10px;
                color: #CBD5E1;
            }
        """)
        f_lay = QHBoxLayout(f_frame)
        f_lay.setContentsMargins(8, 4, 8, 4)
        f_lay.setSpacing(5)

        lbl_f = QLabel("复合筛选:")
        lbl_f.setStyleSheet("font-size: 10px; font-weight: 700; color: #38BDF8;")
        f_lay.addWidget(lbl_f)

        input_style = """
            QLineEdit {
                background: rgba(0, 0, 0, 0.45);
                border: 1px solid rgba(255, 255, 255, 0.16);
                border-radius: 3px;
                color: #F8FAFC;
                font-size: 10px;
                font-weight: 600;
                padding: 1px 3px;
            }
            QLineEdit:focus {
                border-color: #38BDF8;
            }
        """

        # 1. 成功率 >=
        f_lay.addWidget(QLabel("成功率≥"))
        self.edit_min_sr = QLineEdit("80")
        self.edit_min_sr.setFixedWidth(34)
        self.edit_min_sr.setAlignment(Qt.AlignCenter)
        self.edit_min_sr.setStyleSheet(input_style)
        f_lay.addWidget(self.edit_min_sr)
        f_lay.addWidget(QLabel("%"))

        # 2. 缓存率 >=
        f_lay.addWidget(QLabel("缓存率≥"))
        self.edit_min_cache = QLineEdit("80")
        self.edit_min_cache.setFixedWidth(34)
        self.edit_min_cache.setAlignment(Qt.AlignCenter)
        self.edit_min_cache.setStyleSheet(input_style)
        f_lay.addWidget(self.edit_min_cache)
        f_lay.addWidget(QLabel("%"))

        # 3. 真实倍率 <=
        f_lay.addWidget(QLabel("真实倍率≤"))
        self.edit_max_eff = QLineEdit("0.25")
        self.edit_max_eff.setFixedWidth(40)
        self.edit_max_eff.setAlignment(Qt.AlignCenter)
        self.edit_max_eff.setStyleSheet(input_style)
        f_lay.addWidget(self.edit_max_eff)

        # 4. 标准倍率 <=
        f_lay.addWidget(QLabel("标准倍率≤"))
        self.edit_max_nom = QLineEdit("0.25")
        self.edit_max_nom.setFixedWidth(40)
        self.edit_max_nom.setAlignment(Qt.AlignCenter)
        self.edit_max_nom.setStyleSheet(input_style)
        f_lay.addWidget(self.edit_max_nom)

        # 5. 模型检测状态
        f_lay.addWidget(QLabel("检测:"))
        self.combo_detect = QComboBox()
        self.combo_detect.addItems(["全部", "仅通过 🟢", "通过+待定 🟢⚪", "仅疑似 🟠"])
        self.combo_detect.setStyleSheet("""
            QComboBox {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 4px;
                color: #CBD5E1;
                font-size: 9px;
                padding: 1px 4px;
            }
            QComboBox QAbstractItemView {
                background: #1E293B;
                color: #F8FAFC;
                selection-background-color: #3B82F6;
            }
        """)
        f_lay.addWidget(self.combo_detect)

        f_lay.addStretch()

        btn_filter = QPushButton("确定筛选")
        btn_filter.setCursor(Qt.PointingHandCursor)
        btn_filter.setFixedHeight(22)
        btn_filter.setStyleSheet("""
            QPushButton {
                background: rgba(59, 130, 246, 0.25);
                border: 1px solid rgba(59, 130, 246, 0.5);
                border-radius: 4px;
                color: #93C5FD;
                font-size: 10px;
                font-weight: 700;
                padding: 1px 8px;
            }
            QPushButton:hover {
                background: rgba(59, 130, 246, 0.45);
                color: #FFFFFF;
            }
        """)
        btn_filter.clicked.connect(self.apply_numeric_filter)
        f_lay.addWidget(btn_filter)

        layout.addWidget(f_frame)

        # 3. Table Column Header
        h_row = QHBoxLayout()
        h_row.setContentsMargins(8, 2, 8, 2)
        h_row.setSpacing(6)

        h_sel = QLabel("监听")
        h_sel.setFixedWidth(24)
        h_sel.setStyleSheet("font-size: 9px; font-weight: 700; color: #10B981;")
        h_sel.setToolTip("勾选监听")
        h_row.addWidget(h_sel)

        h_exc = QLabel("剔除")
        h_exc.setFixedWidth(26)
        h_exc.setStyleSheet("font-size: 9px; font-weight: 700; color: #EF4444;")
        h_exc.setToolTip("勾选剔除后，无论在自动模式还是手动模式下，该供应商均被排除不会被监控")
        h_row.addWidget(h_exc)

        h_prov = QLabel("检测 / 供应商代码")
        h_prov.setStyleSheet("font-size: 9px; font-weight: 700; color: #64748B;")
        h_prov.setToolTip("AIHub 模型真实性检测:\n🟢 绿色: 模型检测通过\n🟠 橙色: 模型疑似非原生/掺水/存在异常\n⚪ 灰色: 待定/样本不足/未检测")
        h_row.addWidget(h_prov)
        h_row.addStretch()

        for title, w in [("倍率", 40), ("真实倍率", 46), ("缓存率", 44), ("TTFT", 40), ("成功率", 52), ("实测图", 36)]:
            lbl = QLabel(title)
            lbl.setFixedWidth(w)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("font-size: 9px; font-weight: 700; color: #64748B;")
            h_row.addWidget(lbl)
        layout.addLayout(h_row)

        # 4. Scroll Area for Providers
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(SCROLL_STYLE)
        scroll.viewport().setStyleSheet("background: transparent; border: none;")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        c_layout = QVBoxLayout(content)
        c_layout.setContentsMargins(2, 2, 2, 2)
        c_layout.setSpacing(4)

        all_providers = (self.aihub_client.cached_data or {}).get("all_providers", [])
        all_providers = sorted(all_providers, key=lambda x: x["code"].lower())
        cur_selected = set(self.aihub_client.get_selected_providers() or [])

        for p in all_providers:
            code = p["code"]
            self.provider_data_map[code] = p

            row = QFrame()
            row.setStyleSheet("""
                QFrame {
                    background: rgba(255, 255, 255, 0.03);
                    border: 1px solid rgba(255, 255, 255, 0.05);
                    border-radius: 4px;
                }
                QFrame:hover {
                    background: rgba(255, 255, 255, 0.06);
                }
            """)
            r_lay = QHBoxLayout(row)
            r_lay.setContentsMargins(6, 4, 6, 4)
            r_lay.setSpacing(6)

            is_exc = code in self.excluded_providers or (is_ds_or_glm_provider(code, p) and code not in cur_selected)

            # Column 1: Select Checkbox (监听)
            cb = QCheckBox()
            cb.setFixedWidth(22)
            cb.setChecked(code in cur_selected and not is_exc)
            cb.setEnabled(not is_exc)
            cb.setStyleSheet(CHECKBOX_STYLE)
            cb.setCursor(Qt.PointingHandCursor)
            cb.setToolTip(f"监听 {code}")
            cb.stateChanged.connect(self.update_count_label)
            self.provider_checkboxes[code] = cb
            r_lay.addWidget(cb)

            # Column 2: Exclude Checkbox (剔除)
            cb_exc = QCheckBox()
            cb_exc.setFixedWidth(24)
            cb_exc.setChecked(is_exc)
            cb_exc.setCursor(Qt.PointingHandCursor)
            cb_exc.setToolTip(f"剔除 {code}：勾选后在自动和手动模式下均排除")
            cb_exc.setStyleSheet("""
                QCheckBox {
                    padding-left: 2px;
                }
                QCheckBox::indicator {
                    width: 13px;
                    height: 13px;
                    border-radius: 3px;
                    border: 1px solid rgba(239, 68, 68, 0.45);
                    background: rgba(255, 255, 255, 0.04);
                }
                QCheckBox::indicator:hover {
                    border-color: #EF4444;
                    background: rgba(239, 68, 68, 0.18);
                }
                QCheckBox::indicator:checked {
                    background-color: #EF4444;
                    border-color: #EF4444;
                }
            """)
            def _make_exc_handler(c_code=code, m_cb=cb):
                def _handler(state):
                    if state == Qt.Checked:
                        m_cb.setChecked(False)
                        m_cb.setEnabled(False)
                    else:
                        m_cb.setEnabled(True)
                    self.update_count_label()
                return _handler

            cb_exc.stateChanged.connect(_make_exc_handler())
            self.provider_exclude_checkboxes[code] = cb_exc
            r_lay.addWidget(cb_exc)

            # Detection Dot
            det_status = p.get("detection_status", "other")
            det_tip = p.get("detection_tip", "")
            dot = DetectionDot(det_status, tooltip=det_tip, size=9, parent=row)
            r_lay.addWidget(dot)

            # Provider Code Label + Gray Description Note
            detail = (p.get("public_detail") or "").strip()
            is_on = bool(p.get("available", True)) and bool(p.get("visible_in_hall", True))
            off_tag = "" if is_on else " <span style='font-size: 8px; color: #EF4444; font-weight: 700;'>[已下架]</span>"
            if detail:
                code_lbl = QLabel(f"<span style='font-size: 10px; font-weight: 600; color: {'#64748B' if is_exc else '#E2E8F0'};'>{code}</span>{off_tag} <span style='font-size: 8.5px; color: #64748B;'>{detail}</span>")
            else:
                code_lbl = QLabel(f"<span style='font-size: 10px; font-weight: 600; color: {'#64748B' if is_exc else '#E2E8F0'};'>{code}</span>{off_tag}")
            code_lbl.setCursor(Qt.PointingHandCursor)
            code_lbl.mousePressEvent = lambda e, m_cb=cb, exc=is_exc: m_cb.setChecked(not m_cb.isChecked()) if not exc else None
            r_lay.addWidget(code_lbl)
            r_lay.addStretch()

            # Multipliers: Standard/Nominal and Real/Effective
            nom_mult = p.get("multiplier_str", "--")
            eff_mult = p.get("effective_multiplier_str") or "--"

            nom_lbl = QLabel(nom_mult)
            nom_lbl.setFixedWidth(40)
            nom_lbl.setAlignment(Qt.AlignCenter)
            nom_lbl.setToolTip(f"标准/原始倍率: {nom_mult}")
            nom_lbl.setStyleSheet("""
                background: rgba(59, 130, 246, 0.15);
                color: #60A5FA;
                border-radius: 3px;
                padding: 1px 2px;
                font-size: 9px;
                font-weight: 600;
            """)
            r_lay.addWidget(nom_lbl)

            mult_lbl = QLabel(eff_mult)
            mult_lbl.setFixedWidth(46)
            mult_lbl.setAlignment(Qt.AlignCenter)
            mult_lbl.setToolTip(f"真实倍率: {eff_mult} (含实际缓存计费折算)\n名义倍率: {nom_mult}")
            mult_lbl.setStyleSheet("""
                background: rgba(16, 185, 129, 0.18);
                color: #34D399;
                border-radius: 3px;
                padding: 1px 2px;
                font-size: 9px;
                font-weight: 700;
            """)
            r_lay.addWidget(mult_lbl)

            # Cache hit rate
            cache_lbl = QLabel(p.get("cache_hit_rate", "-"))
            cache_lbl.setFixedWidth(44)
            cache_lbl.setAlignment(Qt.AlignCenter)
            cache_lbl.setStyleSheet("font-size: 9px; color: #94A3B8;")
            r_lay.addWidget(cache_lbl)

            # TTFT
            ttft_lbl = QLabel(p.get("ttft_str", "--"))
            ttft_lbl.setFixedWidth(40)
            ttft_lbl.setAlignment(Qt.AlignCenter)
            ttft_lbl.setStyleSheet("font-size: 9px; color: #64748B;")
            r_lay.addWidget(ttft_lbl)

            # Success rate with warning color if bad
            has_sr = bool(p.get("has_success_rate"))
            sr_raw = p.get("success_rate")
            sr_text = p.get("success_rate_str", "--")
            sr_lbl = QLabel()
            sr_lbl.setFixedWidth(52)
            sr_lbl.setAlignment(Qt.AlignCenter)

            if not has_sr or sr_raw is None or sr_text == "--":
                sr_lbl.setText("--")
                sr_lbl.setStyleSheet("font-size: 9px; color: #64748B;")
                sr_lbl.setToolTip("暂无实测成功率统计")
            else:
                sr_val = float(sr_raw)
                if sr_val < 50.0:
                    sr_lbl.setText(f"⚠️ {sr_text}")
                    sr_lbl.setStyleSheet("""
                        background: rgba(239, 68, 68, 0.2);
                        border: 1px solid rgba(239, 68, 68, 0.4);
                        color: #EF4444;
                        border-radius: 3px;
                        padding: 1px 2px;
                        font-size: 8px;
                        font-weight: 700;
                    """)
                    sr_lbl.setToolTip(f"该供应商成功率仅 {sr_val:.1f}%，极不稳定，建议取消勾选！")
                elif sr_val < 90.0:
                    sr_lbl.setText(sr_text)
                    sr_lbl.setStyleSheet("font-size: 9px; font-weight: 600; color: #F59E0B;")
                else:
                    sr_lbl.setText(sr_text)
                    sr_lbl.setStyleSheet("font-size: 9px; font-weight: 600; color: #10B981;")

            r_lay.addWidget(sr_lbl)

            # Has image indicator
            has_img = bool(p.get("has_image"))
            img_lbl = QLabel("📷" if has_img else "-")
            img_lbl.setFixedWidth(36)
            img_lbl.setAlignment(Qt.AlignCenter)
            img_lbl.setStyleSheet("font-size: 10px; color: #10B981;" if has_img else "font-size: 9px; color: #475569;")
            if has_img:
                img_lbl.setCursor(Qt.PointingHandCursor)
                img_lbl.setToolTip("点击查看实测图 (鹈鹕测图记录)")
                def _make_pelican_handler(prov=p):
                    def _open_pelican(e):
                        try:
                            from ui.pelican_viewer import PelicanViewerDialog
                            dlg = PelicanViewerDialog(prov, self.aihub_client, prov.get("code", ""), self)
                            dlg.exec_()
                        except Exception as err:
                            print(f"Error opening Pelican viewer: {err}")
                    return _open_pelican
                img_lbl.mousePressEvent = _make_pelican_handler(p)
            r_lay.addWidget(img_lbl)
            c_layout.addWidget(row)

        c_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        # Footer
        footer = QHBoxLayout()
        self.count_lbl = QLabel("")
        self.count_lbl.setStyleSheet("font-size: 10px; color: #94A3B8;")
        self.update_count_label()
        footer.addWidget(self.count_lbl)
        footer.addStretch()

        btn_save = QPushButton("保存并应用")
        btn_save.setCursor(Qt.PointingHandCursor)
        btn_save.setStyleSheet("""
            QPushButton {
                background: #10B981;
                color: #FFFFFF;
                border: none;
                border-radius: 5px;
                padding: 4px 16px;
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: #059669;
            }
        """)
        btn_save.clicked.connect(self.save_and_apply)
        footer.addWidget(btn_save)
        layout.addLayout(footer)

        root.addWidget(container)

    def update_count_label(self):
        checked = sum(1 for cb in self.provider_checkboxes.values() if cb.isChecked())
        excluded = sum(1 for cb_e in self.provider_exclude_checkboxes.values() if cb_e.isChecked())
        total = len(self.provider_checkboxes)
        self.count_lbl.setText(f"已勾选: {checked}  |  🚫 已剔除: {excluded}  |  总计: {total} 个供应商")

    def toggle_all(self, checked: bool):
        for code, cb in self.provider_checkboxes.items():
            cb_e = self.provider_exclude_checkboxes.get(code)
            if checked and cb_e and cb_e.isChecked():
                cb.setChecked(False)
            else:
                cb.setChecked(checked)
        self.update_count_label()

    def apply_numeric_filter(self):
        """Filter provider checkboxes based on numeric threshold inputs."""
        def parse_val(text: str) -> Optional[float]:
            t = text.strip().replace("%", "").replace("x", "")
            if not t:
                return None
            try:
                return float(t)
            except ValueError:
                return None

        min_sr = parse_val(self.edit_min_sr.text())
        min_cache = parse_val(self.edit_min_cache.text())
        max_eff = parse_val(self.edit_max_eff.text())
        max_nom = parse_val(self.edit_max_nom.text())
        det_mode = self.combo_detect.currentText()

        for code, p in self.provider_data_map.items():
            cb = self.provider_checkboxes.get(code)
            cb_e = self.provider_exclude_checkboxes.get(code)
            if not cb:
                continue

            # Excluded providers are skipped and left unchecked
            if cb_e and cb_e.isChecked():
                cb.setChecked(False)
                continue

            # Model verification filter
            det_status = p.get("detection_status", "other")
            if "仅通过" in det_mode and det_status != "passed":
                cb.setChecked(False)
                continue
            elif "通过+待定" in det_mode and det_status == "suspected":
                cb.setChecked(False)
                continue
            elif "仅疑似" in det_mode and det_status != "suspected":
                cb.setChecked(False)
                continue

            has_sr = bool(p.get("has_success_rate"))
            sr_raw = p.get("success_rate")
            if min_sr is not None:
                if not has_sr or sr_raw is None or float(sr_raw) < min_sr:
                    cb.setChecked(False)
                    continue

            has_cache = bool(p.get("has_cache_rate"))
            cache_val = p.get("cache_hit_val", 0.0)
            if min_cache is not None:
                if not has_cache or cache_val < min_cache:
                    cb.setChecked(False)
                    continue

            eff_raw = p.get("effective_multiplier")
            if max_eff is not None:
                if eff_raw is None or float(eff_raw) > max_eff:
                    cb.setChecked(False)
                    continue

            nom_mult = float(p.get("rate_multiplier", 1.0))
            if max_nom is not None and nom_mult > max_nom:
                cb.setChecked(False)
                continue

            cb.setChecked(True)

        self.update_count_label()

    def _on_dlg_auto_clicked(self):
        self.btn_dlg_auto.setChecked(True)
        self.btn_dlg_manual.setChecked(False)

    def _on_dlg_manual_clicked(self):
        self.btn_dlg_auto.setChecked(False)
        self.btn_dlg_manual.setChecked(True)

    def apply_good_preset(self):
        for code, cb in self.provider_checkboxes.items():
            cb_e = self.provider_exclude_checkboxes.get(code)
            if cb_e and cb_e.isChecked():
                cb.setChecked(False)
            elif is_ds_or_glm_provider(code):
                cb.setChecked(False)
                if cb_e:
                    cb_e.setChecked(True)
            else:
                cb.setChecked(code in DEFAULT_SELECTED_PROVIDERS)
        self.update_count_label()

    def save_and_apply(self):
        # Save mode
        is_auto = self.btn_dlg_auto.isChecked()
        self.aihub_client.set_auto_mode(is_auto)

        # Save excluded providers
        excluded_codes = [code for code, cb_e in self.provider_exclude_checkboxes.items() if cb_e.isChecked()]
        self.aihub_client.set_excluded_providers(excluded_codes)

        # Save selected providers (excluding any that are blacklisted)
        selected_codes = [code for code, cb in self.provider_checkboxes.items() if cb.isChecked() and code not in excluded_codes]
        self.aihub_client.set_selected_providers(selected_codes)

        # Force re-computation of monitored rows
        self.aihub_client.fetch_data(force=True)
        self.filters_changed.emit()
        self.close()

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
